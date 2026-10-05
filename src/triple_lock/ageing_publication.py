"""Fail-closed publication checks on private inputs, without fiscal reruns.

The audit reads the model's input and pension-component arrays. It never
returns those arrays, monetary sums, identifiers or weights. A single central
input audit covers the paired paths only after their common age rules,
data-year ceilings and positive uprating multipliers have been verified.
"""

import hashlib
import inspect
import json
import os
import tempfile
from itertools import combinations
from pathlib import Path

import numpy as np

from . import ageing_validation as AV, engine
from .config import BASE_YEAR, HORIZON, POLICIES, REPO, STATE_PENSION_AGE_CHANGES

MIN_RECORDS = 10
COMPONENTS = ("basic_state_pension", "new_state_pension", "additional_state_pension", "state_pension")
INPUTS = ("age", "state_pension_type", "additional_state_pension", "person_weight",
          "is_household_head", "is_benunit_head")
# Read in full on the managed 2.90.2 bundle: basic/new are a fixed data-year
# share times the period's flat rate; ASP is overridden by the shared pin.
# A changed formula requires a new proof before the one-path audit is reused.
READ_PENSION_FORMULAS = {
    "basic_state_pension": "80fcb72367d5cfe5f693e0d5d4fd86337028443ca0b3dab225eff96e97cf8aa3",
    "new_state_pension": "cc6ed27cede8a02b1bfc25fcbd7dbb8b05e1fe3ea3c160762bec5cfcbe7b8e2c",
    "additional_state_pension": "b36dd29ab73166135941d0a8e5cead2b9eb983ae1b5ce586a9839806e4e7c1bd",
}


class PublicationBlocked(RuntimeError):
    """A result cannot safely be published; errors contain no private counts."""


def fiscal_function_sha256():
    """Keep the exact fiscal-function provenance separate from publication code."""
    return hashlib.sha256(inspect.getsource(AV.run_validation_path).encode()).hexdigest()


def plan_sha256(plan):
    """Bind the audit to exactly the completed public macro paths and provenance."""
    return hashlib.sha256(engine._canonical(plan).encode()).hexdigest()


def _changed(left, right):
    a, b = np.asarray(left), np.asarray(right)
    if a.ndim != 1 or a.shape != b.shape:
        raise PublicationBlocked("publication audit arrays are not aligned")
    if a.dtype.kind in "fc" and (not np.isfinite(a).all() or not np.isfinite(b).all()):
        raise PublicationBlocked("publication audit has non-finite inputs")
    return a != b


def input_support(snapshots, person_households, person_gb, household_gb):
    """Check each field, component and union on both entities, then linked cells.

    A union with many people cannot excuse a small component difference, or
    many people belonging to fewer than ten households. GB input differences
    block all publication. Small differences inside a marginal cell withhold
    its complete age/geography family across every linked table.
    """
    if set(snapshots) != set(AV.RUN_MODES):
        raise PublicationBlocked("publication audit requires all five treatments")
    years = set(snapshots["legacy"])
    if not years or any(set(mode) != years for mode in snapshots.values()):
        raise PublicationBlocked("publication audit years differ across treatments")
    membership = np.asarray(person_households, dtype=int)
    person_gb, household_gb = np.asarray(person_gb, bool), np.asarray(household_gb, bool)
    if (membership.shape != person_gb.shape or np.any(membership < 0)
            or np.any(membership >= len(household_gb))
            or not np.array_equal(person_gb, household_gb[membership])):
        raise PublicationBlocked("publication audit entity geography or membership differs")
    withheld = {"age": False, "geography": False}
    pairs = 0

    def small(mask):
        n = int(np.count_nonzero(mask))
        return 0 < n < MIN_RECORDS

    for left, right in combinations(AV.RUN_MODES, 2):
        for year in sorted(years):
            a, b = snapshots[left][year], snapshots[right][year]
            if any(set(a[entity]) != set(b[entity]) for entity in ("person", "household")):
                raise PublicationBlocked("publication audit fields differ across treatments")
            changed_people = [_changed(a["person"][name], b["person"][name]) for name in a["person"]]
            changed_households = [_changed(a["household"][name], b["household"][name]) for name in a["household"]]
            # Person changes can affect household income even if the head's
            # field is the only changed input; count household support too.
            changed_households.extend(np.bincount(membership, weights=mask, minlength=len(household_gb)) > 0
                                      for mask in changed_people)
            changed_people.append(np.logical_or.reduce(changed_people))
            changed_households.append(np.logical_or.reduce(changed_households))
            if any(small(mask & person_gb) for mask in changed_people) or any(
                    small(mask & household_gb) for mask in changed_households):
                raise PublicationBlocked("publication withheld: a treatment difference has small record support")
            for family, columns in (("age", ("age_cell",)), ("geography", ("country", "region"))):
                for column in columns:
                    labels = np.union1d(a[column], b[column])
                    for label in labels:
                        # Use both memberships: a record moving between age
                        # cells belongs to the support of both changed totals.
                        cell = person_gb & ((a[column] == label) | (b[column] == label))
                        homes = np.bincount(membership, weights=cell, minlength=len(household_gb)) > 0
                        if any(small(mask & cell) for mask in changed_people) or any(
                                small(mask & homes) for mask in changed_households):
                            withheld[family] = True
            pairs += 1
    return {"passed": True, "minimum_contributing_records": MIN_RECORDS,
            "person_and_household_support_checked": True, "field_component_and_union_support_checked": True,
            "pair_year_checks": pairs, "years": sorted(years), "withheld_families": withheld}


def _path_proof(plan, parameters, data_year, years):
    """Verify why the same input-support sets apply to every macro path."""
    if plan.get("calibration_year") is None or data_year >= min(HORIZON):
        raise PublicationBlocked("publication audit requires an explicit pre-forecast calibration")
    base = engine.base_levels(parameters)
    caps = parameters.gov.dwp.state_pension
    if any(not np.isfinite(float(node.amount(data_year))) or float(node.amount(data_year)) <= 0
           for node in (caps.basic_state_pension, caps.new_state_pension)):
        raise PublicationBlocked("publication audit data-year pension ceilings must be positive")
    paths = {}
    for label, (_, spec) in zip(plan["labels"], plan["jobs"], strict=True):
        if spec.get("dataset") is not None or spec.get("demography_calibration_year") != plan["calibration_year"]:
            raise PublicationBlocked("publication audit paths do not share the dataset and calibration")
        changes = engine.scenario_changes(spec, parameters)
        spa = {name: value for name, value in changes.items() if name.startswith("gov.dwp.state_pension.age.")}
        if spa != STATE_PENSION_AGE_CHANGES or any(name.startswith("gov.dwp.state_pension.") and name not in spa
                                                 for name in changes):
            raise PublicationBlocked("publication audit paths differ in pension-age rules or data-year ceilings")
        cpi = engine.september_cpi(spec)
        index = 1.0
        for year in range(data_year + 1, max(years) + 1):
            rate = float(cpi[year - 1])
            index *= 1 + max(rate, 0.0)
            if not np.isfinite(rate) or not np.isfinite(index) or index <= 0:
                raise PublicationBlocked("publication audit CPI multipliers must stay finite and positive")
        _, _, rates = engine.spec_rates(spec)
        for policy in POLICIES:
            for variable, start in base.items():
                levels = AV.rules.level_path(start, rates[policy], HORIZON)
                if any(not np.isfinite(value) or value <= 0 for value in levels.values()):
                    raise PublicationBlocked("publication audit flat-rate multipliers must stay finite and positive")
        paths[label[0]] = True
    return {"paths_checked": len(paths), "identical_state_pension_age_changes": True,
            "data_year_flat_rate_ceilings_unchanged": True, "positive_common_uprating_multipliers": True,
            "reason": "types, ages, weights and heads are dataset-only; each pension component is multiplied by a common positive path factor"}


def collect_input_support(plan):
    """Reconstruct private input support once; calculate no fiscal or income total."""
    from policyengine_uk.utils.scenario import Scenario
    from . import demography, model_horizon

    model_horizon.install()
    reference = engine._managed()
    parameters = reference.tax_benefit_system.parameters
    central = next(spec for (path, mode), (_, spec) in zip(plan["labels"], plan["jobs"], strict=True)
                   if path == "central" and mode == "both")
    changes = engine.scenario_changes(central, parameters)
    _, earnings, _ = engine.spec_rates(central)
    pc_levels = engine.pension_credit_levels(parameters, earnings, central.get("rate_decimals", 3))
    pristine = engine._managed(scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))
    engine.set_flat_rates(pristine, {}, pc_levels)
    formulas = {name: engine.file_hash(inspect.getfile(pristine.tax_benefit_system.variables[name].__class__))
                for name in COMPONENTS}
    if any(formulas[name] != expected for name, expected in READ_PENSION_FORMULAS.items()):
        raise PublicationBlocked("publication audit pension formulas require a new support proof")
    data_year = int(min(pristine.dataset.years))
    years = sorted({data_year, *range(data_year, BASE_YEAR + 1), *HORIZON})
    proof = _path_proof(plan, parameters, data_year, years)
    snapshots = {}
    membership = np.asarray(pristine.household.members_entity_id, dtype=int)
    person_region = np.asarray(pristine.calculate("region", data_year, map_to="person").to_numpy()).astype(str)
    household_region = np.asarray(pristine.calculate("region", data_year, map_to="household").to_numpy()).astype(str)
    person_gb, household_gb = person_region != "NORTHERN_IRELAND", household_region != "NORTHERN_IRELAND"
    # Installed clone copies every holder array and clones its tax system.
    # The pristine input model has calculated no fiscal or household income.
    for mode in AV.RUN_MODES:
        sim = pristine.clone()
        if mode == "legacy":
            pinned, _ = engine.pinned_inputs(sim, years, engine.september_cpi(central))
        else:
            pinned, _ = demography.pinned_inputs(sim, years, engine.september_cpi(central), mode=mode,
                                                calibration_year=plan["calibration_year"])
        engine.pin(sim, pinned)
        rows = {}
        for year in years:
            person = {name: np.asarray(sim.calculate(name, year).to_numpy()).copy() for name in INPUTS}
            household = {"household_weight": np.asarray(sim.calculate("household_weight", year).to_numpy()).copy()}
            for component in COMPONENTS:
                amount = np.asarray(sim.calculate(component, year).to_numpy(), dtype=float)
                person[component] = amount.copy()
                person[f"weighted_{component}"] = amount * person["person_weight"]
                household_amount = np.asarray(sim.calculate(component, year, map_to="household").to_numpy(), dtype=float)
                household[component] = household_amount
                household[f"weighted_{component}"] = household_amount * household["household_weight"]
            rows[year] = {"person": person, "household": household,
                          "age_cell": np.searchsorted([hi for _, hi, _ in AV.AGE_BANDS], person["age"], side="right"),
                          "region": person_region,
                          "country": np.where(person_region == "WALES", "Wales", np.where(person_region == "SCOTLAND", "Scotland", "England"))}
        snapshots[mode] = rows
        del sim
    result = input_support(snapshots, membership, person_gb, household_gb)
    result["macro_path_support_proof"] = proof
    result["fiscal_function_sha256"] = fiscal_function_sha256()
    result["publication_guard_sha256"] = engine.file_hash(__file__)
    result["plan_sha256"] = plan_sha256(plan)
    result["model_version"] = reference.policyengine_bundle["model_version"]
    result["pension_formula_sha256"] = formulas
    result["audit_engine_semantics"] = engine.engine_semantics()
    return result


def guard_results(plan, results, audit):
    """Apply before summarising: block GB bypasses and withhold linked families."""
    if not audit.get("passed") or audit.get("fiscal_function_sha256") != fiscal_function_sha256():
        raise PublicationBlocked("publication audit is missing or belongs to another fiscal function")
    if audit.get("plan_sha256") != plan_sha256(plan) or audit.get("publication_guard_sha256") != engine.file_hash(__file__):
        raise PublicationBlocked("publication audit belongs to another job plan or guard version")
    if len(results) != len(plan["jobs"]) or any(result is None for result in results):
        raise PublicationBlocked("publication requires every completed full-model job")
    for result in results:
        for policy in result["coverage"].values():
            for table in policy.values():
                if table["GB"]["status"] != "available" or table["GB"]["records"] is None or table["GB"]["records"] < MIN_RECORDS:
                    raise PublicationBlocked("publication withheld: a GB coverage row cannot support spending totals")
                for family, names in (("age", ("by_age",)), ("geography", ("by_country", "by_region"))):
                    if audit["withheld_families"][family]:
                        for name in names:
                            table[name] = {label: {field: "withheld_family" if field == "status" else None for field in row}
                                           for label, row in table[name].items()}
    return audit


def publish_cached(plan, output, audit=None, execution_metadata=None):
    """Publish completed full runs only; missing jobs never start a model run."""
    results = [engine.cached(kind, arg, engine=plan["engine_semantics"], packages=plan["packages"])
               for kind, arg in plan["jobs"]]
    if any(result is None for result in results):
        raise PublicationBlocked("publication requires every completed full-model job")
    audit = collect_input_support(plan) if audit is None else audit
    guard_results(plan, results, audit)
    report = AV.summarise(plan, results)
    report["publication_privacy_audit"] = audit
    if execution_metadata:
        report.update({name: execution_metadata[name] for name in ("worker_execution", "host_before_runs")
                       if name in execution_metadata})
    output = Path(output).resolve()
    if not output.is_relative_to(REPO):
        raise PublicationBlocked("publication output must stay in the assigned workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="ageing-publication-", suffix=".json", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return report
