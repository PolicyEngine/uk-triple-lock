"""Fail-closed publication checks on private inputs, without fiscal reruns.

The audit reads the model's input and pension-component arrays. It never
returns those arrays, monetary sums, identifiers or weights. A single central
input audit covers the paired paths only after their common age rules,
data-year ceilings and positive uprating multipliers have been verified.
"""

import ast
import hashlib
import inspect
import json
import os
import re
import subprocess
import tempfile
import tomllib
from contextlib import chdir
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
    "state_pension": "549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352",
}
ROUNDING_RTOL = 8 * np.finfo(np.float32).eps


class PublicationBlocked(RuntimeError):
    """A result cannot safely be published; errors contain no private counts."""


def fiscal_function_sha256():
    """Keep the exact fiscal-function provenance separate from publication code."""
    return hashlib.sha256(inspect.getsource(AV.run_validation_path).encode()).hexdigest()


def plan_sha256(plan):
    """Bind the audit to exactly the completed public macro paths and provenance."""
    return hashlib.sha256(engine._canonical(plan).encode()).hexdigest()


def canonical_bundle(bundle):
    """The exact public bundle contract returned by each full-model job."""
    return {name: bundle[name] for name in ("bundle_id", "policyengine_version", "model_version",
                                           "runtime_dataset", "certified_data_build_id")}


def _git(*args):
    """Read the contained worktree git when present; never write git metadata."""
    contained = REPO / ".cache" / "workspace.git"
    env = os.environ.copy()
    if contained.is_dir():
        env.update(GIT_DIR=str(contained), GIT_WORK_TREE=str(REPO))
    return subprocess.check_output(["git", *args], cwd=REPO, env=env)


def _checkout_provenance():
    return {"head": _git("rev-parse", "HEAD").decode().strip(),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=normal").strip()),
            "engine_semantics": engine.engine_semantics(), "validation_semantics": AV.validation_semantics(),
            "publication_code_sha256": _publication_code_hashes()}


def _publication_code_hashes():
    return {name: engine.file_hash(path) for name, path in {
                "ageing_publication.py": Path(__file__),
                "publish_ageing_validation.py": REPO / "scripts" / "publish_ageing_validation.py",
                "report_ageing_validation.py": REPO / "scripts" / "report_ageing_validation.py"}.items()}


def _head_source_verification(plan):
    """Independently bind every saved semantic hash to the named git tree."""
    sources = {**plan["engine_semantics"], **plan["validation_semantics"]}
    if any(plan["engine_semantics"][name] != digest for name, digest in plan["validation_semantics"].items()
           if name in plan["engine_semantics"]):
        raise PublicationBlocked("calculation source maps disagree")
    try:
        for name, expected in sources.items():
            if name == "pyproject.toml":
                path = name
            elif name == "ons_npp_2024_uk_age_sex.csv":
                path = f"data/{name}"
            elif re.fullmatch(r"[a-z_]+\.py", name):
                path = f"src/triple_lock/{name}"
            else:
                raise PublicationBlocked("calculation source name is not audited")
            content = _git("show", f"{plan['calculation_head']}:{path}")
            if name.endswith(".csv"):
                measured = hashlib.sha256(content).hexdigest()
            else:
                text = content.decode("utf-8")
                canonical = (json.dumps(tomllib.loads(text), sort_keys=True, default=str) if name.endswith(".toml")
                             else ast.dump(engine._DropBareStrings().visit(ast.parse(text, filename=path))))
                measured = hashlib.sha256(canonical.encode()).hexdigest()
            if measured != expected:
                raise PublicationBlocked("saved calculation source does not match its git head")
    except (subprocess.CalledProcessError, UnicodeError, SyntaxError, tomllib.TOMLDecodeError):
        raise PublicationBlocked("calculation head source verification failed") from None
    return {"verified": True, "head": plan["calculation_head"], "engine_semantics": plan["engine_semantics"],
            "validation_semantics": plan["validation_semantics"], "files_checked": len(sources)}


def calculation_metadata(plan):
    """Metadata recorded before models run, without changing the supplied plan."""
    provenance = _checkout_provenance()
    if provenance["engine_semantics"] != plan["engine_semantics"] or provenance["validation_semantics"] != plan["validation_semantics"]:
        raise PublicationBlocked("calculation plan does not match the current source")
    result = {"calculation_head": provenance["head"], "calculation_provenance": provenance,
              "fiscal_function_sha256": fiscal_function_sha256()}
    if (plan.get("packages", {}).get("policyengine") == "5.3.0"
            and plan.get("packages", {}).get("policyengine-uk") == "2.90.2"):
        result["calibration_anchor"] = {
            "source_calibration_year": 2025, "source_data_tag": "1.56.16",
            "source_commit": "12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3", "runtime_anchor_year": plan["calibration_year"],
            "runtime_restores_builder_calibration": False, "verified_artifact_calibration_manifest": False,
            "source_url": "https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57",
            "weights_basis": f"Native runtime {plan['calibration_year']} weights; builder calibration preservation unverified"}
    return result


def _verify_plan_sources(plan):
    current = _checkout_provenance()
    saved = plan.get("calculation_provenance", {})
    if (not re.fullmatch(r"[0-9a-f]{40}", str(plan.get("calculation_head", "")))
            or saved.get("head") != plan["calculation_head"] or not isinstance(saved.get("dirty"), bool)
            or saved.get("engine_semantics") != plan.get("engine_semantics")
            or saved.get("validation_semantics") != plan.get("validation_semantics")
            or current["engine_semantics"] != plan.get("engine_semantics")
            or current["validation_semantics"] != plan.get("validation_semantics")
            or plan.get("fiscal_function_sha256") != fiscal_function_sha256()):
        raise PublicationBlocked("publication audit must use the exact saved calculation sources and head")
    _head_source_verification(plan)
    return current


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
    year_pairs = 0
    contrasts = 0

    def small(mask):
        n = int(np.count_nonzero(mask))
        return 0 < n < MIN_RECORDS

    def check(a, b, changed_people, direct_households, cell_households, linked_rows=None):
        changed_people = [*changed_people, np.logical_or.reduce(changed_people)]
        mapped = [np.bincount(membership, weights=mask, minlength=len(household_gb)) > 0 for mask in changed_people]
        global_households = [*direct_households, *mapped]
        global_households.append(np.logical_or.reduce(global_households))
        if any(small(mask & person_gb) for mask in changed_people) or any(
                small(mask & household_gb) for mask in global_households):
            raise PublicationBlocked("publication withheld: a treatment or year difference has small record support")
        for family, columns in (("age", ("age_cell",)), ("geography", ("country", "region"))):
            if withheld[family]:
                continue
            for column in columns:
                rows = linked_rows or (a, b)
                for label in np.unique(np.concatenate([row[column] for row in rows])):
                    cell = person_gb & np.logical_or.reduce([row[column] == label for row in rows])
                    homes = np.bincount(membership, weights=cell, minlength=len(household_gb)) > 0
                    # Household support must come from the changed members
                    # inside this cell, never from another member outside it.
                    from_cell = [np.bincount(membership, weights=mask & cell, minlength=len(household_gb)) > 0
                                 for mask in changed_people]
                    if any(small(mask & cell) for mask in changed_people) or any(
                            small(mask) for mask in from_cell) or any(small(mask & homes) for mask in cell_households):
                        withheld[family] = True
                        break
                if withheld[family]:
                    break

    ordered_years = sorted(years)
    if ordered_years != list(range(ordered_years[0], ordered_years[-1] + 1)):
        raise PublicationBlocked("publication audit years must include every consecutive year")
    for left, right in combinations(AV.RUN_MODES, 2):
        for year in ordered_years:
            a, b = snapshots[left][year], snapshots[right][year]
            if any(set(a[entity]) != set(b[entity]) for entity in ("person", "household")):
                raise PublicationBlocked("publication audit fields differ across treatments")
            people = [_changed(a["person"][name], b["person"][name]) for name in a["person"]]
            people.append(_changed(a["age_cell"], b["age_cell"]))
            houses = [_changed(a["household"][name], b["household"][name]) for name in a["household"]]
            weights = [_changed(a["household"][name], b["household"][name])
                       for name in a["household"] if name in ("household_weight", "weight")]
            check(a, b, people, houses, weights)
            pairs += 1
    for mode in AV.RUN_MODES:
        for first, second in combinations(ordered_years, 2):
            a, b = snapshots[mode][first], snapshots[mode][second]
            people = [_changed(a["person"][name], b["person"][name])
                      for name in a["person"] if name in ("age", "state_pension_type", "type", "is_SP_age",
                                                        "is_household_head", "is_benunit_head", "head",
                                                        "months_since_last_birthday")]
            people.append(_changed(a["age_cell"], b["age_cell"]))
            for name in COMPONENTS:
                if name in a["person"]:
                    people.append(_changed(a["person"][name] > 0, b["person"][name] > 0))
            person_weight = next(name for name in ("person_weight", "weight") if name in a["person"])
            household_weight = next(name for name in ("household_weight", "weight") if name in a["household"])
            pw, person_factor = _weight_residual(a["person"][person_weight], b["person"][person_weight], person_gb)
            hw, household_factor = _weight_residual(a["household"][household_weight], b["household"][household_weight], household_gb)
            people.append(pw)
            houses = [hw]
            # Strip each component's common uprating. A recipient can retain
            # ASP while its protected-payment amount changes after retyping.
            for name in ("basic_state_pension", "new_state_pension", "additional_state_pension"):
                if name not in a.get("normalised_person", {}) or name not in b.get("normalised_person", {}):
                    raise PublicationBlocked("publication audit requires normalised pension components")
                pa, pb = a["normalised_person"][name], b["normalised_person"][name]
                ha, hb = a["normalised_household"][name], b["normalised_household"][name]
                people.extend((~np.isclose(pa, pb, rtol=ROUNDING_RTOL, atol=0),
                               ~np.isclose(pa * a["person"][person_weight] * person_factor,
                                           pb * b["person"][person_weight], rtol=ROUNDING_RTOL, atol=0)))
                houses.extend((~np.isclose(ha, hb, rtol=ROUNDING_RTOL, atol=0),
                               ~np.isclose(ha * a["household"][household_weight] * household_factor,
                                           hb * b["household"][household_weight], rtol=ROUNDING_RTOL, atol=0)))
            check(a, b, people, houses, [hw])
            year_pairs += 1
    # Four snapshots are needed: two individually large differences can
    # overlap on fewer than ten records when the treatment contrast changes.
    for left, right in combinations(AV.RUN_MODES, 2):
        for first, second in combinations(ordered_years, 2):
            a, b = snapshots[left][first], snapshots[right][first]
            c, d = snapshots[left][second], snapshots[right][second]
            people, houses, weight_houses = _contrast_masks(a, b, c, d, person_gb, household_gb)
            check(a, c, people, houses, weight_houses, (a, b, c, d))
            contrasts += 1
    return {"passed": True, "minimum_contributing_records": MIN_RECORDS,
            "person_and_household_support_checked": True, "field_component_and_union_support_checked": True,
            "pair_year_checks": pairs, "years": ordered_years, "withheld_families": withheld,
            "consecutive_year_support_checked": True, "consecutive_year_checks": 5 * (len(ordered_years) - 1),
            "all_year_pairs_support_checked": True, "all_year_pair_checks": year_pairs,
            "treatment_contrast_year_support_checked": True, "treatment_contrast_year_checks": contrasts,
            "pension_recipient_and_type_changes_checked": True, "age_cell_changes_checked": True,
            "weights_beyond_common_factor_checked": True,
            "floating_point_storage_tolerance": "eight float32 epsilons for normalised components and common-factor weights; other input masks are exact"}


def _categorical_contrast_masks(a, b, c, d):
    """Compare signed category-indicator contrasts, retaining their direction."""
    arrays = [np.asarray(value) for value in (a, b, c, d)]
    if any(value.ndim != 1 or value.shape != arrays[0].shape for value in arrays):
        raise PublicationBlocked("publication contrast arrays are not aligned")
    return [((arrays[0] == label).astype(int) - (arrays[1] == label).astype(int)) !=
            ((arrays[2] == label).astype(int) - (arrays[3] == label).astype(int))
            for label in np.unique(np.concatenate(arrays))]


def _contrast_masks(a, b, c, d, person_gb, household_gb):
    """Support of (A-B) in year two minus its normalised year-one contrast."""
    people, houses = [], []
    for name in a["person"]:
        if name in ("state_pension_type", "type"):
            people.extend(_categorical_contrast_masks(*(row["person"][name] for row in (a, b, c, d))))
        elif name in ("age", "is_SP_age", "is_household_head", "is_benunit_head", "head", "months_since_last_birthday"):
            values = [np.asarray(row["person"][name], dtype=float) for row in (a, b, c, d)]
            people.append(_changed(values[0] - values[1], values[2] - values[3]))
    people.extend(_categorical_contrast_masks(*(row["age_cell"] for row in (a, b, c, d))))
    for name in COMPONENTS:
        if name in a["person"]:
            values = [(np.asarray(row["person"][name]) > 0).astype(int) for row in (a, b, c, d)]
            people.append(_changed(values[0] - values[1], values[2] - values[3]))
    weight_houses = []
    for entity, target, gb in (("person", people, person_gb), ("household", houses, household_gb)):
        weight_name = next(name for name in (f"{entity}_weight", "weight") if name in a[entity])
        wa, wb, wc, wd = [np.asarray(row[entity][weight_name], dtype=float) for row in (a, b, c, d)]
        _, fa = _weight_residual(wa, wc, gb)
        _, fb = _weight_residual(wb, wd, gb)
        weight_change = ~np.isclose(wa - wb, wc / fa - wd / fb, rtol=ROUNDING_RTOL, atol=0)
        target.append(weight_change)
        if entity == "household":
            weight_houses.append(weight_change)
        for name in ("basic_state_pension", "new_state_pension", "additional_state_pension"):
            try:
                pa, pb, pc, pd = [np.asarray(row[f"normalised_{entity}"][name], dtype=float) for row in (a, b, c, d)]
            except KeyError:
                raise PublicationBlocked("publication contrast requires normalised pension components") from None
            target.extend((~np.isclose(pa - pb, pc - pd, rtol=ROUNDING_RTOL, atol=0),
                           ~np.isclose(pa * wa - pb * wb, pc * wc / fa - pd * wd / fb,
                                       rtol=ROUNDING_RTOL, atol=0)))
    return people, houses, weight_houses


def _weight_residual(left, right, mask):
    a, b = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(a <= 0) or np.any(b <= 0):
        raise PublicationBlocked("publication audit weights must be aligned, finite and positive")
    factor = float(np.median((b / a)[mask]))
    return ~np.isclose(a * factor, b, rtol=ROUNDING_RTOL, atol=0), factor


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
        if spa != STATE_PENSION_AGE_CHANGES or any(name.startswith(("gov.dwp.state_pension.", "gov.contrib.")) and name not in spa
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
            "reason": "types, ages, weights and heads are path-independent dataset inputs; each basic/new/additional pension component has a common positive path factor. This checks pinned-input and pension-component support, not every nonlinear programme state. Period-derived birth years and Savings Credit cohort eligibility remain outside the proof; exact recovery from published net and household-income totals is assumed to be prevented by their nonlinear programme calculations."}


def collect_input_support(plan):
    """Reconstruct private input support once; calculate no fiscal or income total."""
    _verify_plan_sources(plan)
    private = REPO / ".cache" / "ageing-publication-model"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    with chdir(private):
        return _collect_input_support(plan)


def _collect_input_support(plan):
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
    p = pristine.tax_benefit_system.parameters.gov.dwp.state_pension
    caps = {name: {year: float(getattr(p, name).amount(year)) for year in years}
            for name in ("basic_state_pension", "new_state_pension")}
    if any(not np.isfinite(value) or value <= 0 for by_year in caps.values() for value in by_year.values()):
        raise PublicationBlocked("publication audit model flat-rate ceilings must stay finite and positive")
    contribution = pristine.tax_benefit_system.parameters.gov.contrib
    if any(bool(contribution.abolish_state_pension(year)) or not np.isfinite(1 + contribution.cec.state_pension_increase(year))
           or 1 + contribution.cec.state_pension_increase(year) <= 0 for year in years):
        raise PublicationBlocked("publication audit aggregate pension factor must stay finite and positive")
    cpi_indices, index = {}, 1.0
    cpi = engine.september_cpi(central)
    for year in years:
        if year > data_year:
            index *= 1 + max(cpi[year - 1], 0.0)
        cpi_indices[year] = index
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
        person_inputs = (*INPUTS, "is_SP_age", *(name for name in ("months_since_last_birthday",)
                                                if name in sim.tax_benefit_system.variables))
        _assert_audited_pins(sim, pinned, years, person_inputs)
        rows = {}
        for year in years:
            person = {name: np.asarray(sim.calculate(name, year).to_numpy()).copy() for name in person_inputs}
            household = {"household_weight": np.asarray(sim.calculate("household_weight", year).to_numpy()).copy()}
            normalised_person, normalised_household = {}, {}
            for component in COMPONENTS:
                amount = np.asarray(sim.calculate(component, year).to_numpy(), dtype=float)
                person[component] = amount.copy()
                person[f"weighted_{component}"] = amount * person["person_weight"]
                household_amount = np.asarray(sim.calculate(component, year, map_to="household").to_numpy(), dtype=float)
                household[component] = household_amount
                household[f"weighted_{component}"] = household_amount * household["household_weight"]
                if component != "state_pension":
                    factor = cpi_indices[year] if component == "additional_state_pension" else caps[component][year]
                    normalised_person[component] = amount / factor
                    normalised_household[component] = household_amount / factor
            rows[year] = {"person": person, "household": household,
                          "normalised_person": normalised_person, "normalised_household": normalised_household,
                          "age_cell": np.searchsorted([hi for _, hi, _ in AV.AGE_BANDS], person["age"], side="right"),
                          "region": person_region,
                          "country": np.where(person_region == "WALES", "Wales", np.where(person_region == "SCOTLAND", "Scotland", "England"))}
        snapshots[mode] = rows
        del sim
    result = input_support(snapshots, membership, person_gb, household_gb)
    result["macro_path_support_proof"] = proof
    result["fiscal_function_sha256"] = fiscal_function_sha256()
    result["publication_guard_sha256"] = engine.file_hash(__file__)
    result["publication_code_sha256"] = _publication_code_hashes()
    result["plan_sha256"] = plan_sha256(plan)
    result["model_version"] = reference.policyengine_bundle["model_version"]
    result["pension_formula_sha256"] = formulas
    result["audit_engine_semantics"] = engine.engine_semantics()
    result["audit_validation_semantics"] = AV.validation_semantics()
    result["bundle"] = canonical_bundle(reference.policyengine_bundle)
    result["dataset"] = reference.policyengine_bundle["runtime_dataset"]
    result["data_year"] = data_year
    result["pinned_keys_checked"] = True
    result["calibration_anchor"] = plan.get("calibration_anchor")
    result["calculation_head"] = plan["calculation_head"]
    result["calculation_source_head_verification"] = _head_source_verification(plan)
    result["calculation_provenance"] = {**plan["calculation_provenance"],
                                        "plan_sha256": result["plan_sha256"], "fiscal_function_sha256": result["fiscal_function_sha256"]}
    return result


def _assert_audited_pins(sim, pinned, years, person_inputs):
    covered = {*person_inputs, "household_weight", "benunit_weight"}
    if set(pinned) - covered:
        raise PublicationBlocked("publication audit does not cover every pinned input")
    if "benunit_weight" in pinned:
        membership = np.asarray(sim.household.members_entity_id, dtype=int)
        units = np.asarray(sim.benunit.members_entity_id, dtype=int)
        lo, hi = np.full(sim.benunit.count, len(sim.household.ids)), np.full(sim.benunit.count, -1)
        np.minimum.at(lo, units, membership)
        np.maximum.at(hi, units, membership)
        if np.any(lo != hi):
            raise PublicationBlocked("publication audit benefit units do not map to one household")
        for year in years:
            weights = np.asarray(sim.calculate("household_weight", year).to_numpy())
            if not np.array_equal(np.asarray(sim.calculate("benunit_weight", year).to_numpy()), weights[lo]):
                raise PublicationBlocked("publication audit benefit-unit weights differ from household weights")


def guard_results(plan, results, audit):
    """Apply before summarising: block GB bypasses and withhold linked families."""
    publication = _verify_plan_sources(plan)
    if len(results) != len(plan["jobs"]) or len(plan["labels"]) != len(results) or any(result is None for result in results):
        raise PublicationBlocked("publication requires every completed full-model job")
    groups = {}
    for label, (kind, spec) in zip(plan["labels"], plan["jobs"], strict=True):
        path, mode = label
        if kind != "ageing_path" or mode != spec.get("demography") or mode in groups.setdefault(path, set()):
            raise PublicationBlocked("publication job labels do not match their unique treatments")
        groups[path].add(mode)
    expected_paths = {"central"} if plan["central_only"] else {"central", *(f"draw_{draw}" for draws in plan["sample"].values() for draw in draws)}
    if set(groups) != expected_paths or any(modes != set(AV.RUN_MODES) for modes in groups.values()):
        raise PublicationBlocked("publication plan does not contain every paired path and treatment")
    data_year = results[0]["data_year"]
    expected_years = list(range(data_year, max(HORIZON) + 1))
    bundle = results[0]["bundle"]
    dataset = results[0]["dataset"]
    for (path, mode), result in zip(plan["labels"], results, strict=True):
        if result.get("mode") != mode or result.get("dataset") != dataset or result.get("data_year") != data_year or result.get("bundle") != bundle or set(result["coverage"]) != set(POLICIES):
            raise PublicationBlocked("publication jobs differ in dataset year, model bundle or policies")
        if any(sorted(map(int, tables)) != expected_years for tables in result["coverage"].values()):
            raise PublicationBlocked("publication jobs do not cover every result year")
    if (audit.get("passed") is not True or audit.get("fiscal_function_sha256") != fiscal_function_sha256()
            or audit.get("fiscal_function_sha256") != plan["fiscal_function_sha256"]):
        raise PublicationBlocked("publication audit is missing or belongs to another fiscal function")
    if (audit.get("plan_sha256") != plan_sha256(plan) or audit.get("publication_guard_sha256") != engine.file_hash(__file__)
            or audit.get("publication_code_sha256") != publication["publication_code_sha256"]
            or audit.get("audit_engine_semantics") != plan["engine_semantics"]
            or audit.get("audit_validation_semantics") != plan["validation_semantics"]
            or audit.get("audit_engine_semantics", {}).get("demography.py") != plan["validation_semantics"].get("demography.py")):
        raise PublicationBlocked("publication audit belongs to another job plan, source or guard version")
    if (audit.get("years") != expected_years or audit.get("data_year") != data_year or audit.get("dataset") != dataset
            or audit.get("model_version") != bundle["model_version"] or audit.get("bundle") != bundle
            or audit.get("pension_formula_sha256") != READ_PENSION_FORMULAS):
        raise PublicationBlocked("publication audit does not cover the result years, bundle and read formulas")
    if (audit.get("calculation_head") != plan["calculation_head"] or audit.get("calibration_anchor") != plan.get("calibration_anchor")
            or audit.get("calculation_provenance") != {**plan["calculation_provenance"], "plan_sha256": plan_sha256(plan),
                                                       "fiscal_function_sha256": plan["fiscal_function_sha256"]}):
        raise PublicationBlocked("publication audit calculation-head or calibration provenance differs")
    if audit.get("calculation_source_head_verification") != _head_source_verification(plan):
        raise PublicationBlocked("publication audit calculation source-head verification differs")
    flags = ("person_and_household_support_checked", "field_component_and_union_support_checked",
             "consecutive_year_support_checked", "pension_recipient_and_type_changes_checked",
             "age_cell_changes_checked", "weights_beyond_common_factor_checked", "pinned_keys_checked",
             "all_year_pairs_support_checked", "treatment_contrast_year_support_checked")
    if any(audit.get(flag) is not True for flag in flags):
        raise PublicationBlocked("publication audit support checks are incomplete")
    if (type(audit.get("pair_year_checks")) is not int or audit["pair_year_checks"] != 10 * len(expected_years)
            or type(audit.get("consecutive_year_checks")) is not int or audit["consecutive_year_checks"] != 5 * (len(expected_years) - 1)
            or type(audit.get("all_year_pair_checks")) is not int or audit["all_year_pair_checks"] != 5 * len(expected_years) * (len(expected_years) - 1) // 2
            or type(audit.get("treatment_contrast_year_checks")) is not int or audit["treatment_contrast_year_checks"] != 10 * len(expected_years) * (len(expected_years) - 1) // 2
            or type(audit.get("minimum_contributing_records")) is not int or audit["minimum_contributing_records"] < MIN_RECORDS):
        raise PublicationBlocked("publication audit support counts are incomplete")
    proof = audit.get("macro_path_support_proof", {})
    if (type(proof.get("paths_checked")) is not int or proof["paths_checked"] != len(groups)
            or any(proof.get(flag) is not True for flag in ("identical_state_pension_age_changes", "data_year_flat_rate_ceilings_unchanged", "positive_common_uprating_multipliers"))):
        raise PublicationBlocked("publication audit macro-path proof is incomplete")
    if set(audit.get("withheld_families", {})) != {"age", "geography"} or any(type(value) is not bool for value in audit["withheld_families"].values()):
        raise PublicationBlocked("publication audit family decisions are invalid")
    audit["publication_provenance"] = publication
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


def publish_cached(plan, output, audit=None, execution_metadata=None, execution_log=None, integration_files=None):
    """Publish completed full runs only; missing jobs never start a model run."""
    if execution_log is None or not isinstance(integration_files, (tuple, list)) or len(integration_files) != 2 or any(path is None for path in integration_files):
        raise PublicationBlocked("publication requires the complete private execution log and both original integration evidence files")
    _verify_plan_sources(plan)
    metadata = _execution_metadata(plan, execution_metadata)
    results = [engine.cached(kind, arg, engine=plan["engine_semantics"], packages=plan["packages"])
               for kind, arg in plan["jobs"]]
    if any(result is None for result in results):
        raise PublicationBlocked("publication requires every completed full-model job")
    metadata["worker_execution"].update(_execution_log_metadata(plan, metadata["worker_execution"], execution_log))
    metadata["integration_evidence"] = _integration_file_evidence(plan, *integration_files)
    audit = collect_input_support(plan) if audit is None else audit
    guard_results(plan, results, audit)
    report = AV.summarise(plan, results)
    report["publication_privacy_audit"] = audit
    report.update(metadata)
    report.update({"plan_sha256": plan_sha256(plan), "fiscal_function_sha256": plan["fiscal_function_sha256"],
                   "calculation_head": plan["calculation_head"], "calculation_provenance": plan["calculation_provenance"],
                   "publication_provenance": audit["publication_provenance"], "calibration_anchor": plan.get("calibration_anchor")})
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


def _execution_metadata(plan, metadata):
    """Require the original producer's head and requested worker slots."""
    if (not isinstance(metadata, dict) or metadata.get("calculation_head") != plan["calculation_head"]
            or metadata.get("calculation_provenance") != plan["calculation_provenance"]
            or metadata.get("provenance", {}).get("engine_semantics") != plan["engine_semantics"]
            or metadata.get("provenance", {}).get("validation_semantics") != plan["validation_semantics"]
            or metadata.get("source_results_sha256") != plan["source_sha256"]
            or metadata.get("calibration_anchor", metadata.get("publication_privacy_audit", {}).get("calibration_anchor")) != plan.get("calibration_anchor")):
        raise PublicationBlocked("publication requires the original execution head and source metadata")
    worker = metadata.get("worker_execution", {})
    counts = {}
    for lower, old in (("enhanced_frs_workers", "Enhanced_FRS_workers"), ("microcosm_workers", "Microcosm_workers")):
        value = worker.get(lower, worker.get(old))
        if type(value) is not int or value < 0 or (lower in worker and old in worker and worker[lower] != worker[old]):
            raise PublicationBlocked("publication requires valid requested worker counts")
        counts[f"requested_{lower}"] = value
    if counts["requested_enhanced_frs_workers"] < 1 or counts["requested_microcosm_workers"] != 0:
        raise PublicationBlocked("publication requires Enhanced FRS workers and zero Microcosm workers")
    safe_worker = {name: worker[name] for name in ("persistent", "maximum_jobs_per_worker", "memory_diagnostics", "execution_driver_sha256") if name in worker}
    safe_worker.update(counts)
    host = metadata.get("host_before_runs", {})
    result = {"worker_execution": safe_worker,
              "host_before_runs": {name: host[name] for name in ("logical_cpus", "total_ram_gib", "available_ram_gib", "load_average_1m", "cpu_percent_before_runs") if name in host}}
    return result


def _private_file(path):
    path = Path(path).resolve()
    if not path.is_relative_to((REPO / ".cache").resolve()):
        raise PublicationBlocked("execution evidence must come from the assigned private cache")
    return path.read_bytes()


def _execution_log_metadata(plan, workers, path):
    """Count observed completions, including the original cache-hit count."""
    raw = _private_file(path)
    text = raw.decode("utf-8")
    starts = re.findall(r"(\d+) of (\d+) jobs cached; running (\d+) on (\d+) workers", text)
    if len(starts) != 1:
        raise PublicationBlocked("execution log must contain one complete original run")
    cached, planned, running, requested = map(int, starts[0])
    done = [(int(a), int(b)) for a, b in re.findall(r"ageing_path job done \((\d+)/(\d+)\)", text)]
    if (planned != len(plan["jobs"]) or cached + running != planned
            or requested != workers["requested_enhanced_frs_workers"]
            or sorted(index for index, total in done) != list(range(1, running + 1))
            or any(total != running for index, total in done)
            or re.search(r"Stopping:|A job failed:|SourceChanged|Traceback", text)
            or not re.search(r"^Wrote complete private aggregate execution report to ", text, re.MULTILINE)):
        raise PublicationBlocked("execution log is incomplete or does not match the saved job plan")
    first = json.loads(text.splitlines()[0])
    if (first.get("calculation_head") != plan["calculation_head"]
            or first.get("Enhanced_FRS_workers", first.get("enhanced_frs_workers")) != requested
            or first.get("Microcosm_workers", first.get("microcosm_workers")) != 0):
        raise PublicationBlocked("execution log calculation head or requested slots differ")
    return {"initial_cached_jobs": cached, "planned_jobs": planned, "completed_jobs": len(done),
            "execution_log_sha256": hashlib.sha256(raw).hexdigest()}


def _integration_file_evidence(plan, integration_path, equivalence_path):
    """Derive published control outcomes from their original private artifacts."""
    integration_raw, equivalence_raw = _private_file(integration_path), _private_file(equivalence_path)
    integration, equivalence = json.loads(integration_raw), json.loads(equivalence_raw)
    flags = ("legacy_matches_committed_central", "opt_in_engine_run_passed", "record_diagnostics_suppressed")
    preceding = equivalence.get("preceding_path")
    if (integration.get("source_semantics") != plan["engine_semantics"] or integration.get("packages") != plan["packages"]
            or any(integration.get(flag) is not True for flag in flags)
            or integration.get("max_legacy_saving_difference_bn") != 0 or integration.get("opt_in_demography") != "both"
            or equivalence.get("identical") is not True or equivalence.get("compared_path") != "central"
            or equivalence.get("mode") != "both" or equivalence.get("calibration_year") != plan.get("calibration_year")
            or equivalence.get("engine_semantics") != plan["engine_semantics"]
            or equivalence.get("validation_semantics") != plan["validation_semantics"]
            or [preceding, "legacy"] not in [list(label) for label in plan["labels"]]
            or preceding == "central"):
        raise PublicationBlocked("private integration evidence does not match the saved full-model calculation")
    # The verified calculation source selects a legacy preceding job and
    # executes three full jobs; the integration artifact describes two runs.
    return {**{flag: integration[flag] for flag in flags}, "persistent_matches_isolated": equivalence["identical"],
            "engine_semantics": integration["source_semantics"], "validation_semantics": equivalence["validation_semantics"],
            "preceding_mode": "legacy", "full_model_verification_jobs": 5,
            "integration_file_sha256": hashlib.sha256(integration_raw).hexdigest(),
            "equivalence_file_sha256": hashlib.sha256(equivalence_raw).hexdigest()}
