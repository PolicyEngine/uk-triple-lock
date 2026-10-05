"""Aggregate-only full-model validation of the four demographic treatments.

The paired sample is read from the committed expected-value results, rather
than redrawn. Every treatment runs those same paths on the Enhanced FRS. The
worker shares the engine's scenarios and reforms, but does not collect its
single-record concentration diagnostics. No record arrays or weights enter
the returned result. Intermediate jobs and model data stay under .cache.
"""

import argparse
import contextlib
import gc
import hashlib
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import engine, expected_value as EV, rules
from .central import central_path
from .config import (
    BASE_YEAR, FISCAL_COMPONENTS, FLAT_RATE_PARAMETERS,
    HORIZON, POLICIES, REPO, STATUTORY_YEARS,
)
from .dwp import TABLES, TABLES_PAGE, TABLES_URL

MODES = ("frozen", "reweight", "types", "both")
RUN_MODES = ("legacy", *MODES)
MIN_RECORDS = 10
BN = 1e9
SOURCE_RESULTS = REPO / "data" / "results.json"
AGE_BANDS = ((0, 60, "under_60"), (60, 65, "60_64"), (65, 70, "65_69"),
             (70, 75, "70_74"), (75, 80, "75_79"), (80, 85, "80_84"),
             (85, 90, "85_89"), (90, 200, "90_plus"))
REGIONS = {"NORTH_EAST", "NORTH_WEST", "YORKSHIRE", "EAST_MIDLANDS", "WEST_MIDLANDS",
           "EAST_OF_ENGLAND", "LONDON", "SOUTH_EAST", "SOUTH_WEST", "WALES", "SCOTLAND",
           "NORTHERN_IRELAND"}
RECEIPT_PREFIX = "TRIPLE_LOCK_AGEING_RECEIPT "


def validation_semantics():
    """Include worker code, public population targets and draw generation in cache identity."""
    sources = {name: engine.source_semantics(REPO / "src" / "triple_lock" / name)
               for name in ("ageing_validation.py", "demography.py", "expected_value.py", "central.py",
                            "ts_monthly.py", "ts_methods.py", "ts_backtest.py")}
    targets = REPO / "data" / "ons_npp_2024_uk_age_sex.csv"
    sources["ons_npp_2024_uk_age_sex.csv"] = engine.file_hash(targets)
    return sources


def paired_sample(source):
    """Preserve the exact Microcosm-paired indices, multiplicities and stratum masses."""
    ev = source["expected_value"]
    sample = {int(row["stratum"]): [] for row in ev["strata"]}
    by_draw = {}
    for row in ev["paths"]:
        n = int(row.get("times_drawn_sensitivity", 0))
        if n:
            i, k = int(row["draw"]), int(row["stratum"])
            if i in by_draw or n < 1 or k not in sample:
                raise ValueError("invalid paired sample in source results")
            sample[k].extend([i] * n)
            by_draw[i] = row
    for row in ev["strata"]:
        k = int(row["stratum"])
        if len(sample[k]) != int(row["sensitivity_paths"]) or len(sample[k]) < 2:
            raise ValueError(f"paired sample does not match stratum {k}")
    if sum(map(len, sample.values())) != EV.N_PATHS_SENSITIVITY:
        raise ValueError("source does not contain the required 40 Microcosm-paired draws")
    W = {int(row["stratum"]): float(row["probability"]) for row in ev["strata"]}
    W0 = float(ev["identical_rates"]["probability"])
    if not np.isclose(sum(W.values()) + W0, 1, atol=1e-10):
        raise ValueError("source stratum probabilities do not sum to one")
    return sample, W, W0, by_draw


def validation_plan(source_path=SOURCE_RESULTS, central_only=False, calibration_year=None):
    """Prepare full-model jobs without loading a survey or running PolicyEngine."""
    source_path = Path(source_path)
    source = json.loads(source_path.read_text())
    sample, W, W0, stored = paired_sample(source)
    c = central_path()
    from .trajectories import central_spec

    specs = {"central": central_spec(c)}
    if not central_only:
        ev = source["expected_value"]
        provenance = ev["draws"]
        draws = EV.draws(c, n=int(provenance["n"]), seed=int(provenance["seed"]), kind=provenance["shocks"])
        draw_kind = ev["calibrations"][ev["primary"]]["draws"]
        ds = draws[draw_kind]
        for i in sorted(stored):
            spec = EV.path_spec(ds, i)
            for variable, key in (("cpi", "statutory_cpi"), ("earnings", "statutory_earnings")):
                actual = np.array([spec[key][y] for y in STATUTORY_YEARS])
                expected = np.array([stored[i]["statutory"][variable][str(y)] for y in STATUTORY_YEARS])
                if not np.allclose(actual, expected, rtol=0, atol=1e-12):
                    raise ValueError(f"draw {i} no longer reproduces the committed paired path")
            specs[f"draw_{i}"] = spec
    semantics = validation_semantics()
    jobs, labels = [], []
    for path_name, spec in specs.items():
        for mode in RUN_MODES:
            arg = {**spec, "demography": mode, "validation_semantics": semantics}
            if calibration_year is not None:
                arg["demography_calibration_year"] = int(calibration_year)
            # All jobs use the bundle's certified Enhanced FRS, including the paired draws.
            arg.pop("dataset", None)
            jobs.append(("ageing_path", arg))
            labels.append((path_name, mode))
    return {"jobs": jobs, "labels": labels, "sample": sample, "W": W, "W0": W0,
            "source_sha256": engine.file_hash(source_path), "source": str(source_path.relative_to(REPO))
            if source_path.is_relative_to(REPO) else source_path.name,
            "central_only": central_only, "calibration_year": calibration_year, "validation_semantics": semantics,
            "engine_semantics": engine.engine_semantics(), "packages": engine.package_versions()}


def _region(sim, year, entity):
    values = np.asarray(sim.calculate("region", year, map_to=entity).to_numpy()).astype(str)
    if set(np.unique(values)) - REGIONS:
        raise ValueError("model region values are not the documented UK region enumeration")
    return values


def _total(sim, variable, year, mask):
    """Aggregate the run's own weighted output on its own entity; never scale a total."""
    values = sim.calculate(variable, year, map_to="household")
    if len(values) != len(mask):
        raise ValueError("household aggregate mask does not match the model")
    return float(values[mask].sum()) / BN


def gb_totals(sim, years):
    out = {}
    for y in years:
        gb = _region(sim, y, "household") != "NORTHERN_IRELAND"
        if int(gb.sum()) < MIN_RECORDS:
            raise ValueError("fewer than ten GB household records")
        household_weight = np.asarray(sim.calculate("household_weight", y).to_numpy(), dtype=float)
        output_weight = np.asarray(sim.calculate("household_net_income", y).weights.to_numpy(), dtype=float)
        if not np.array_equal(household_weight, output_weight):
            raise engine.PathNotFollowed("weighted outputs do not use the pinned household weights")
        row = {name: sum(_total(sim, variable, y, gb) for variable in variables)
               for name, variables in FISCAL_COMPONENTS.items()}
        for variable in ("gov_balance", "household_net_income", "state_pension",
                         "basic_state_pension", "new_state_pension"):
            row[variable] = _total(sim, variable, y, gb)
        out[y] = row
    return out


def coverage_cell(values, weights, mask, min_records=MIN_RECORDS):
    """A pension coverage cell, suppressing every nonzero contributor set below ten records."""
    mask = np.asarray(mask, dtype=bool)
    recipient = mask & (values["state_pension"] > 0)
    if 0 < int(recipient.sum()) < min_records:
        return {"status": "suppressed", "records": None, "recipients_m": None,
                **{f"{v}_bn": None for v in values}, "basic_recipients_m": None, "new_recipients_m": None}
    row = {"status": "available", "records": int(recipient.sum()),
           "recipients_m": float(weights[recipient].sum() / 1e6)}
    for v, amounts in values.items():
        contributors = mask & (amounts > 0)
        n = int(contributors.sum())
        # A zero amount does not disclose an individual. Small nonzero sums are suppressed.
        row[f"{v}_bn"] = None if 0 < n < min_records else float(weights[mask] @ amounts[mask] / BN)
        if v in ("basic_state_pension", "new_state_pension"):
            key = "basic" if v == "basic_state_pension" else "new"
            row[f"{key}_recipients_m"] = None if 0 < n < min_records else float(weights[contributors].sum() / 1e6)
    if any(value is None for value in row.values()):
        # Totals would otherwise disclose a small component by subtraction.
        row = {key: "suppressed" if key == "status" else None for key in row}
    return row


def complementary_suppression(rows):
    """Prevent an unpublished small cell being recovered from a published marginal total."""
    suppressed = [key for key, row in rows.items() if row["status"] == "suppressed"]
    if suppressed:
        # Two small cells can jointly have fewer than ten contributors. Hide
        # an additional >=10-contributor cell for every affected metric.
        available = {key: row for key, row in rows.items() if row["status"] == "available"}
        hide = set()
        metrics = [name for name in next(iter(rows.values())) if name.endswith(("_bn", "_m"))]
        for metric in metrics:
            candidates = [key for key, row in available.items()
                          if row["records"] >= MIN_RECORDS and row.get(metric) is not None and row[metric] > 0]
            if candidates and not hide.intersection(candidates):
                hide.add(min(candidates, key=lambda k: available[k]["records"]))
        for key in hide:
            rows[key] = {name: "suppressed" if name == "status" else None for name in rows[key]}
    return rows


def pension_coverage(sim, years):
    """GB totals plus marginal age and country/region tables; no survey-record outputs."""
    out = {}
    for y in years:
        ages = np.asarray(sim.calculate("age", y).to_numpy())
        regions = _region(sim, y, "person")
        weights = np.asarray(sim.calculate("person_weight", y).to_numpy(), dtype=float)
        values = {v: np.asarray(sim.calculate(v, y).to_numpy(), dtype=float)
                  for v in ("state_pension", "basic_state_pension", "new_state_pension", "additional_state_pension")}
        if any(a.shape != weights.shape for a in [ages, regions, *values.values()]):
            raise ValueError("person coverage arrays differ in shape")
        gb = regions != "NORTHERN_IRELAND"
        cell = lambda mask: coverage_cell(values, weights, mask)
        countries = np.where(regions == "WALES", "Wales", np.where(regions == "SCOTLAND", "Scotland", "England"))
        by_country = complementary_suppression({name: cell(gb & (countries == name)) for name in ("England", "Scotland", "Wales")})
        by_region = {name: cell(gb & (regions == name)) for name in sorted(REGIONS - {"NORTHERN_IRELAND"})}
        if any(row["status"] == "suppressed" for row in [*by_country.values(), *by_region.values()]):
            # Country and region margins overlap. Withhold the finer table if
            # either has suppression, avoiding recovery across the hierarchy.
            by_region = {key: row if row["status"] == "available" and row["records"] == 0 else
                         {name: "suppressed" if name == "status" else None for name in row}
                         for key, row in by_region.items()}
        out[y] = {"GB": cell(gb),
                  "by_age": complementary_suppression({name: cell(gb & (ages >= lo) & (ages < hi)) for lo, hi, name in AGE_BANDS}),
                  "by_country": by_country, "by_region": by_region}
    return out


def run_validation_path(spec):
    """A full PolicyEngine run of both rules with the treatment pinned in all simulations."""
    from policyengine_uk.utils.scenario import Scenario
    from . import demography

    started = time.monotonic()
    last_stage = started

    def stage(name):
        nonlocal last_stage
        now = time.monotonic()
        print(json.dumps({"validation_stage": name, "stage_seconds": round(now - last_stage, 3),
                          "elapsed_seconds": round(now - started, 3)}), flush=True)
        last_stage = now

    stage("start")
    mode = spec["demography"]
    if mode not in RUN_MODES or spec.get("dataset") is not None:
        raise ValueError("validation requires a named treatment on the certified Enhanced FRS")
    reference = engine._managed()
    stage("reference_built")
    parameters, bundle = reference.tax_benefit_system.parameters, reference.policyengine_bundle
    base = engine.base_levels(parameters)
    changes = engine.scenario_changes(spec, parameters)
    del reference
    _, earnings, rates = engine.spec_rates(spec)
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}
    pc_levels = engine.pension_credit_levels(parameters, earnings, spec.get("rate_decimals", 3))

    def build():
        return engine._managed(scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))

    baseline = build()
    stage("baseline_built")
    data_year = int(min(baseline.dataset.years))
    years = sorted({data_year, *range(data_year, BASE_YEAR + 1), *HORIZON})
    engine.set_flat_rates(baseline, {}, pc_levels)
    if mode == "legacy":
        pinned, _ = engine.pinned_inputs(baseline, years, engine.september_cpi(spec))
    else:
        pinned, _ = demography.pinned_inputs(baseline, years, engine.september_cpi(spec), mode=mode,
                                            calibration_year=spec.get("demography_calibration_year"))
    engine.pin(baseline, pinned)
    stage("baseline_inputs_pinned")
    checks = {} if mode == "legacy" else {"baseline": demography.validate_inputs(baseline, pinned, years, mode=mode)}
    if mode != "legacy":
        checks["data_year"] = demography.data_year_diagnostics(baseline, pinned, data_year)
    stage("baseline_checked")
    del baseline
    totals, coverage = {}, {}
    for policy in POLICIES:
        sim = build()
        stage(f"{policy}_built")
        engine.set_flat_rates(sim, levels[policy], pc_levels)
        for y in HORIZON:
            for variable, parameter in FLAT_RATE_PARAMETERS.items():
                actual = float(sim.tax_benefit_system.parameters.get_child(parameter)(f"{y}-06-01"))
                if not np.isclose(actual, levels[policy][variable][y], rtol=0, atol=1e-8):
                    raise engine.PathNotFollowed("model flat-rate parameter differs from the path's rule")
        engine.pin(sim, pinned)
        engine.held_pension_types(sim, pinned, years)
        if mode != "legacy":
            checks[policy] = demography.validate_inputs(sim, pinned, years, mode=mode)
        stage(f"{policy}_inputs_checked")
        totals[policy] = gb_totals(sim, years)
        stage(f"{policy}_totals_calculated")
        coverage[policy] = pension_coverage(sim, years)
        stage(f"{policy}_coverage_calculated")
        for y in years:
            model_asp = np.asarray(sim.calculate("additional_state_pension", y).to_numpy(), dtype=float)
            if not np.allclose(model_asp, pinned["additional_state_pension"][y], rtol=0, atol=0.01):
                raise engine.PathNotFollowed("model additional State Pension differs from the identical rule input")
            for variable in ("state_pension", "basic_state_pension", "new_state_pension"):
                person_total = coverage[policy][y]["GB"][f"{variable}_bn"]
                if person_total is not None and not np.isclose(person_total, totals[policy][y][variable], rtol=1e-6, atol=1e-6):
                    raise engine.PathNotFollowed("person and household GB aggregates disagree")
        del sim
    stage("finished")
    tl, plan = totals["triple_lock"], totals["burnham_2030"]
    proportionality_error = 0.0
    for y in HORIZON:
        for variable in FLAT_RATE_PARAMETERS:
            expected = tl[y][variable] * levels["burnham_2030"][variable][y] / levels["triple_lock"][variable][y]
            proportionality_error = max(proportionality_error, abs(plan[y][variable] - expected))
        if not np.isclose(plan[y]["additional_state_pension"], tl[y]["additional_state_pension"], rtol=0, atol=1e-6):
            raise engine.PathNotFollowed("additional State Pension aggregate differs between the two rules")
    if proportionality_error > 1e-4:
        raise engine.PathNotFollowed("GB flat-rate pensions do not follow the two rules' flat-rate ratio")
    if mode != "legacy":
        checks["rules"] = {"max_flat_rate_proportionality_error_bn": proportionality_error,
                           "additional_pension_identical_under_both_rules": True}
    savings = {y: {"gross": tl[y]["state_pension_flat_rate"] - plan[y]["state_pension_flat_rate"],
                   "net": plan[y]["gov_balance"] - tl[y]["gov_balance"],
                   "household_income_change": plan[y]["household_net_income"] - tl[y]["household_net_income"]}
               for y in years}
    return {"mode": mode, "dataset": bundle["runtime_dataset"], "data_year": data_year,
            "geography": "Great Britain (Northern Ireland excluded using the model region)",
            "saving_bn": savings, "totals_bn": totals, "coverage": coverage, "checks": checks,
            "bundle": {k: bundle[k] for k in ("bundle_id", "policyengine_version", "model_version",
                                                "runtime_dataset", "certified_data_build_id")}}


def _clean(value):
    return value.replace("\n", " ").strip() if isinstance(value, str) else value


def dwp_forecasts(path=TABLES):
    """Read every published nominal/caseload year, with GB-only comparisons where identifiable.

    Workbook Notes row 14 defines its coverage as Great Britain plus overseas,
    excluding Northern Ireland. The overseas row separates total expenditure
    and total caseload only. Basic/new GB numbers, age bands and regional
    forecasts therefore remain unavailable; no overseas share is allocated.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(wb["State Pension"].iter_rows(values_only=True))
        blocks = [i for i, row in enumerate(rows) if len(row) > 1 and isinstance(row[1], str)
                  and _clean(row[1]).startswith(("State Pension expenditure", "State Pension caseload"))]
        if len(blocks) != 3:
            raise ValueError("unexpected State Pension workbook blocks")
        nominal, caseload = blocks[0], blocks[2]

        def block(start, end):
            columns = {int(str(c)[:4]): j for j, c in enumerate(rows[start])
                       if isinstance(c, str) and re.match(r"^\d{4}/\d{2}", c)}
            labels = {_clean(row[1]): row for row in rows[start + 1:end] if len(row) > 1 and isinstance(row[1], str)}
            return columns, labels

        nc, nr = block(nominal, blocks[1])
        cc, cr = block(caseload, len(rows))
        if max(nc) != 2030 or max(cc) != 2030:
            raise ValueError("spring 2026 workbook forecast horizon changed")

        def number(table, label, col):
            value = table[label][col]
            if not isinstance(value, (int, float)):
                raise ValueError(f"DWP {label}: nonnumeric value")
            return float(value) / 1000

        out = {}
        for y in sorted(set(nc) & set(cc)):
            if y < 2024:
                continue
            n, c = nc[y], cc[y]
            out[y] = {
                "GB": {"state_pension_bn": number(nr, "Total", n) - number(nr, "State Pension paid outside UK included above", n),
                       "recipients_m": number(cr, "Total State Pension Caseload", c)
                                       - number(cr, "State Pension paid outside UK included above", c)},
                "GB_plus_overseas_context": {
                    "basic_state_pension_bn": number(nr, "of which State Pension (basic)", n),
                    "new_state_pension_bn": number(nr, "of which new State Pension  (excluding protected payments)", n),
                    "basic_recipients_m": number(cr, "of which State Pension (basic)", c),
                    "new_recipients_m": number(cr, "of which new State Pension", c),
                    "new_protected_payments_bn": number(nr, "of which new State Pension Protected Payments (including inherited elements)", n)},
            }
        return {"years": out, "source": TABLES_PAGE, "url": TABLES_URL, "sha256": engine.file_hash(path),
                "unavailable": {"GB_by_type": "Overseas expenditure/caseload are separated only for all State Pension types together.",
                                "by_age": "No State Pension age-band expenditure/caseload table in this workbook.",
                                "by_geography": "No country/region State Pension forecast table in this workbook.",
                                "after_2030": "No verified published long-term spending benchmark supplied."}}
    finally:
        wb.close()


def four_way(runs, selector):
    """Paired differences and the interaction, calculated before sampling uncertainty."""
    values = {mode: float(selector(runs[mode])) for mode in MODES}
    out = {**values, "reweight_effect": values["reweight"] - values["frozen"],
            "types_effect": values["types"] - values["frozen"],
            "combined_effect": values["both"] - values["frozen"],
            "interaction": values["both"] - values["reweight"] - values["types"] + values["frozen"]}
    if "legacy" in runs:
        out["legacy"] = float(selector(runs["legacy"]))
        # On 2.90.2 eligibility and ASP already match the legacy pins; the
        # common-input contrast measures represented ages and possible heads.
        out["common_input_effect"] = values["frozen"] - out["legacy"]
    return out


def withhold_linked_coverage(grouped):
    """Fail closed across every linked mode, year, policy and path before publication."""
    families = {"age": ("by_age",), "geography": ("by_country", "by_region")}
    tables = [year for runs in grouped.values() for run in runs.values()
              for policy in run["coverage"].values() for year in policy.values()]
    withheld = {}
    for family, names in families.items():
        # Zero cells are available, so a suppressed status always originates
        # from a positive small cell or its necessary complement.
        needed = any(row["status"] in ("suppressed", "withheld_family") for table in tables for name in names
                     for row in table.get(name, {}).values())
        withheld[family] = needed
        if needed:
            for table in tables:
                for name in names:
                    if name in table:
                        table[name] = {key: {field: "withheld_family" if field == "status" else None for field in row}
                                       for key, row in table[name].items()}
    for table in tables:
        gb = table.get("GB")
        if gb and (gb["records"] is None or gb["records"] < MIN_RECORDS):
            table["GB"] = {name: "suppressed" if name == "status" else None for name in gb}
    return {"age_tables_withheld": withheld["age"], "geography_tables_withheld": withheld["geography"],
            "scope": "whole linked family across all paths, modes, years and policies whenever positive suppression is needed"}


def summarise(plan, results):
    """Public aggregate tables and paired stratified estimates; never copy raw job payloads."""
    grouped = {}
    for (path, mode), result in zip(plan["labels"], results, strict=True):
        grouped.setdefault(path, {})[mode] = result
    if any(set(runs) != set(RUN_MODES) for runs in grouped.values()):
        raise ValueError("validation requires the legacy control and all four treatments for each path")
    suppression = withhold_linked_coverage(grouped)
    central = grouped["central"]
    central_four_way = {metric: {y: four_way(central, lambda r: r["saving_bn"][y][metric]) for y in HORIZON}
                        for metric in ("gross", "net", "household_income_change")}
    spending_four_way = {metric: {y: four_way(central, lambda r: r["totals_bn"]["triple_lock"][y][metric]) for y in HORIZON}
                         for metric in ("state_pension", "basic_state_pension", "new_state_pension")}
    estimated = {}
    if not plan["central_only"]:
        per_draw = {i: grouped[f"draw_{i}"] for indices in plan["sample"].values() for i in indices}
        for metric in central_four_way:
            estimated[metric] = {}
            for y in HORIZON:
                contrasts = {i: four_way(runs, lambda r: r["saving_bn"][y][metric]) for i, runs in per_draw.items()}
                estimated[metric][y] = {}
                for contrast in next(iter(contrasts.values())):
                    vals = {k: [contrasts[i][contrast] for i in indices] for k, indices in plan["sample"].items()}
                    mean, se = EV.stratified_mean(vals, plan["W"])
                    estimated[metric][y][contrast] = {"mean_bn": mean, "se_bn": se}
        # The omitted probability mass has identical flat-rate paths, so all treatment savings and contrasts are zero.
    dwp = dwp_forecasts()
    coverage_rows = []
    for mode, run in central.items():
        for y, tables in run["coverage"]["triple_lock"].items():
            target = dwp["years"].get(y)
            for metric in ("state_pension_bn", "recipients_m", "basic_state_pension_bn", "new_state_pension_bn",
                           "basic_recipients_m", "new_recipients_m"):
                benchmark = target["GB"].get(metric) if target else None
                model = tables["GB"][metric]
                context = target["GB_plus_overseas_context"].get(metric) if target else None
                coverage_rows.append({"year": y, "mode": mode, "metric": metric, "model_GB": model,
                                      "benchmark_GB": benchmark,
                                      "difference": model - benchmark if model is not None and benchmark is not None else None,
                                      "status": "available" if benchmark is not None else "unavailable",
                                      "published_GB_plus_overseas_context": context})
    bundle = central["both"]["bundle"]
    if any(result["bundle"] != bundle for result in results):
        raise ValueError("validation jobs use different PolicyEngine bundles")
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "complete_paired_design": not plan["central_only"], "source_results": plan["source"],
            "source_results_sha256": plan["source_sha256"], "bundle": bundle,
            "provenance": {"engine_semantics": plan["engine_semantics"],
                           "validation_semantics": plan["validation_semantics"], "packages": plan["packages"]},
            "dataset": central["both"]["dataset"], "data_year": central["both"]["data_year"],
            "calibration_year": plan.get("calibration_year"),
            "geography": central["both"]["geography"], "minimum_contributing_records": MIN_RECORDS,
            "suppression_policy": suppression,
            "paired_sample": {"draws_by_stratum": plan["sample"], "probability_by_stratum": plan["W"],
                              "identical_rule_probability": plan["W0"],
                              "identical_rule_treatment": "zero saving in every treatment; neither rule's flat rates differ"},
            "central_four_way_saving_bn": central_four_way, "central_four_way_spending_bn": spending_four_way,
            "expected_four_way_saving_bn": estimated, "coverage_comparisons": coverage_rows,
            "central_coverage": {mode: run["coverage"] for mode, run in central.items()}, "dwp": dwp,
            "checks": {path: {mode: run["checks"] for mode, run in runs.items()} for path, runs in grouped.items()},
            "method": "Full PolicyEngine UK runs for central and the exact committed 40 Microcosm-paired draw indices, "
                      "all on Enhanced FRS, four factorial treatments plus the original engine control, both rules; "
                      "no output scaling. Common_input_effect is frozen minus legacy. On 2.90.2 eligibility and "
                      "additional-pension pins already agree; the contrast measures represented ages and possible "
                      "household-head changes. The factorial weight and type "
                      "effects are conditional on those common inputs. The interaction is computed "
                      "within each paired path before stratified averaging. Standard errors preserve repeated draws. "
                      "GB type, age and geography benchmarks are unavailable where the workbook does not publish them."}


def host_resources():
    """Record CPU and RAM before starting model workers on the shared host."""
    import psutil

    memory = psutil.virtual_memory()
    return {"logical_cpus": os.cpu_count(), "total_ram_gib": round(memory.total / 2 ** 30, 2),
            "available_ram_gib": round(memory.available / 2 ** 30, 2),
            "load_average_1m": round(os.getloadavg()[0], 2)}


def isolated_runner(kind, arg, workdir, semantics, stop=None):
    """Use the engine's process-group management for this aggregate-only worker."""
    if kind != "ageing_path":
        raise ValueError("unknown ageing validation job")
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(engine._canonical([kind, arg]).encode()).hexdigest()[:12]
    inp, out = workdir / f"ageing-input-{tag}.json", workdir / f"ageing-output-{tag}.json"
    inp.write_text(json.dumps({"arg": arg, "engine": semantics}, default=float))
    try:
        code, _, _ = engine.run_child([sys.executable, "-m", "triple_lock.ageing_validation", "--job", str(inp), str(out)],
                                           cwd=workdir, env={"PYTHONPATH": str(REPO / "src")}, stop=stop)
        if code:
            raise RuntimeError(f"isolated ageing job failed (exit {code}); private exception text withheld")
        return json.loads(out.read_text())
    finally:
        inp.unlink(missing_ok=True)
        out.unlink(missing_ok=True)


def _job(inp, out, initialise=True):
    from . import model_horizon

    if initialise:
        engine.watch_parent()
    payload = json.loads(Path(inp).read_text())
    if engine.engine_semantics() != payload["engine"]:
        raise engine.SourceChanged("engine code changed before the validation job")
    if validation_semantics() != payload["arg"]["validation_semantics"]:
        raise engine.SourceChanged("validation code/targets changed before the job")
    if initialise:
        model_horizon.install()
    result = run_validation_path(engine._keys_to_int(payload["arg"]))
    Path(out).write_text(json.dumps(result, default=float, allow_nan=False))


def _private_log(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    return os.fdopen(descriptor, "a", buffering=1)


def serve(input_stream=None, output_stream=None, job_fn=None, initialise=True):
    """One process, fresh full simulations per request; stdout carries receipts only."""
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    job_fn = job_fn or _job
    with _private_log(Path.cwd() / "ageing-worker-model.log") as progress:
        with contextlib.redirect_stdout(progress), contextlib.redirect_stderr(progress):
            if initialise:
                from . import model_horizon
                engine.watch_parent()
                model_horizon.install()
            for line in input_stream:
                token = None
                try:
                    request = json.loads(line)
                    token = request["token"]
                    if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
                        raise ValueError("invalid worker token")
                    inp, out = Path(request["input"]), Path(request["output"])
                    if any(path.parent.resolve() != Path.cwd().resolve() for path in (inp, out)):
                        raise ValueError("worker files must stay inside their locked cache directory")
                    out.unlink(missing_ok=True)
                    job_fn(inp, out, initialise=False)
                    if not out.is_file():
                        raise RuntimeError("worker did not write its aggregate result")
                    receipt = {"token": token, "ok": True}
                except Exception as exc:
                    # Exceptions may contain model inputs. Publish the class
                    # only, then retire this worker to discard failed state.
                    receipt = {"token": token, "ok": False, "error": type(exc).__name__}
                    progress.write(json.dumps({"error": type(exc).__name__,
                                               "frames": [{"file": Path(frame.filename).name, "line": frame.lineno,
                                                           "function": frame.name} for frame in traceback.extract_tb(exc.__traceback__)]}) + "\n")
                    output_stream.write(RECEIPT_PREFIX + json.dumps(receipt) + "\n")
                    output_stream.flush()
                    return 1
                gc.collect()  # release any simulation/holder reference cycles
                import psutil
                progress.write(json.dumps({"worker_rss_gib": round(psutil.Process().memory_info().rss / 2 ** 30, 3),
                                           "process_pid": os.getpid(), "completed_job_token": token}) + "\n")
                output_stream.write(RECEIPT_PREFIX + json.dumps(receipt) + "\n")
                output_stream.flush()
    return 0


class PersistentRunner:
    """Optional per-slot service using the engine's locks, cache and cancellation registry."""

    def __init__(self, command=None, max_jobs=20):
        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")
        self.command = command or [sys.executable, "-u", "-m", "triple_lock.ageing_validation", "--serve"]
        self.max_jobs = max_jobs
        self.workers = {}
        self.all_workers = []
        self.lock = threading.Lock()

    def __enter__(self):
        return self

    def _worker(self, workdir, stop):
        with self.lock:
            existing = self.workers.get(workdir)
            if existing and existing["process"].poll() is None:
                return existing
            if existing:
                self._unregister(existing["process"])
            workdir.mkdir(parents=True, exist_ok=True)
            stderr = _private_log(workdir / "ageing-worker-stderr.log")
            env = {**os.environ, "PYTHONPATH": str(REPO / "src"), engine.PARENT_ENV: str(os.getpid())}
            try:
                with engine._children_lock:
                    if stop is not None and stop.is_set():
                        raise engine.Aborted("the build is stopping")
                    proc = subprocess.Popen(self.command, cwd=workdir, env=env, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=stderr, text=True,
                                            bufsize=1, start_new_session=True)
                    engine._children[proc.pid] = proc
            except BaseException:
                stderr.close()
                raise
            receipts = queue.Queue()

            def read_receipts():
                try:
                    for line in proc.stdout:
                        if line.startswith(RECEIPT_PREFIX):
                            receipts.put(line[len(RECEIPT_PREFIX):])
                finally:
                    receipts.put(None)
                    proc.wait()
                    self._unregister(proc)

            reader = threading.Thread(target=read_receipts, daemon=True)
            reader.start()
            worker = {"process": proc, "receipts": receipts, "reader": reader, "stderr": stderr, "jobs": 0}
            self.workers[workdir] = worker
            self.all_workers.append(worker)
            return worker

    def __call__(self, kind, arg, workdir, semantics, stop=None):
        if kind != "ageing_path":
            raise ValueError("unknown ageing validation job")
        if stop is not None and stop.is_set():
            raise engine.Aborted("the build is stopping")
        workdir = Path(workdir).resolve()
        worker = self._worker(workdir, stop)
        token = uuid.uuid4().hex
        inp, out = workdir / f"ageing-input-{token}.json", workdir / f"ageing-output-{token}.json"
        inp.write_text(json.dumps({"arg": arg, "engine": semantics}, default=float))
        try:
            proc = worker["process"]
            try:
                proc.stdin.write(json.dumps({"token": token, "input": str(inp), "output": str(out)}) + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError("persistent ageing worker stopped before receiving the job") from exc
            while True:
                try:
                    response = worker["receipts"].get(timeout=0.25)
                    break
                except queue.Empty:
                    if proc.poll() is not None and not worker["reader"].is_alive():
                        raise RuntimeError("persistent ageing worker stopped before returning a receipt")
            if response is None:
                raise RuntimeError("persistent ageing worker stopped before returning a receipt")
            receipt = json.loads(response)
            if receipt.get("token") != token:
                raise RuntimeError("persistent ageing worker returned an unmatched receipt")
            if not receipt.get("ok"):
                error = receipt.get("error", "UnknownError")
                if not isinstance(error, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", error):
                    error = "UnknownError"
                raise RuntimeError(f"persistent ageing job failed ({error}); no private model inputs logged")
            if not out.is_file():
                raise RuntimeError("persistent ageing worker returned a receipt without aggregate output")
            result = json.loads(out.read_text())
            worker["jobs"] += 1
            if worker["jobs"] >= self.max_jobs:
                self._retire(worker)
            return result
        finally:
            inp.unlink(missing_ok=True)
            out.unlink(missing_ok=True)

    @staticmethod
    def _unregister(proc):
        with engine._children_lock:
            if engine._children.get(proc.pid) is proc:
                engine._children.pop(proc.pid, None)

    def _retire(self, worker):
        proc = worker["process"]
        with contextlib.suppress(OSError):
            proc.stdin.close()
        if proc.poll() is None:
            engine._signal_group(proc.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=engine.KILL_GRACE_S)
        if proc.poll() is None:
            engine._signal_group(proc.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=1)
        self._unregister(proc)
        worker["reader"].join(timeout=1)
        proc.stdout.close()
        worker["stderr"].close()
        with self.lock:
            self.workers = {key: value for key, value in self.workers.items() if value is not worker}
            if worker in self.all_workers:
                self.all_workers.remove(worker)

    def close(self):
        # All model futures have finished before run_jobs returns; termination
        # also handles startup failures or interrupted builds within ten seconds.
        workers = list(self.all_workers)
        for worker in workers:
            proc = worker["process"]
            with contextlib.suppress(OSError):
                proc.stdin.close()
            if proc.poll() is None:
                engine._signal_group(proc.pid, signal.SIGTERM)
        deadline = time.monotonic() + engine.KILL_GRACE_S
        for worker in workers:
            with contextlib.suppress(subprocess.TimeoutExpired):
                worker["process"].wait(timeout=max(0, deadline - time.monotonic()))
        for worker in workers:
            proc = worker["process"]
            if proc.poll() is None:
                engine._signal_group(proc.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=1)
            self._unregister(proc)
            worker["reader"].join(timeout=1)
            proc.stdout.close()
            worker["stderr"].close()
        self.workers.clear()
        self.all_workers.clear()

    def __exit__(self, *exc):
        self.close()


def verify_worker_equivalence(plan):
    """Run central both in isolation and after a different draw in a persistent worker."""
    jobs = dict(zip(plan["labels"], plan["jobs"], strict=True))
    central = jobs[("central", "both")]
    preceding = next(job for label, job in jobs.items() if label[0] != "central" and label[1] == "legacy")
    semantics = engine.engine_semantics()
    isolated_dir = engine.WORKDIRS / "ageing-equivalence-isolated"
    persistent_dir = engine.WORKDIRS / "ageing-equivalence-persistent"
    with engine.slot_lock(isolated_dir):
        isolated = isolated_runner(*central, isolated_dir, semantics)
    with engine.slot_lock(persistent_dir), PersistentRunner() as runner:
        runner(*preceding, persistent_dir, semantics)
        persistent = runner(*central, persistent_dir, semantics)
    if persistent != isolated:
        raise AssertionError("persistent and isolated aggregate results differ; no private differences published")
    return {"identical": True, "preceding_path": preceding[1]["id"], "compared_path": "central",
            "mode": "both", "calibration_year": plan["calibration_year"], "bundle": isolated["bundle"],
            "engine_semantics": semantics, "validation_semantics": plan["validation_semantics"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--source-results", type=Path, default=SOURCE_RESULTS)
    parser.add_argument("--calibration-year", type=int, help="Explicit Enhanced FRS calibration year; required for model runs")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=1,
                        help="Enhanced FRS workers only; this command starts no Microcosm workers")
    parser.add_argument("--persistent-workers", action="store_true", help="Reuse worker imports; build fresh full simulations for every job")
    parser.add_argument("--jobs-per-worker", type=int, default=20, help="Recycle each persistent worker after this many jobs (default 20)")
    parser.add_argument("--verify-workers", action="store_true", help="Compare one real central job in both runners after another persistent path")
    parser.add_argument("--central-only", action="store_true", help="Preliminary central-path run; explicitly incomplete")
    parser.add_argument("--plan", action="store_true", help="Print public draw indices and job count without running the model")
    parser.add_argument("--job", nargs=2, metavar=("INPUT", "OUTPUT"), help=argparse.SUPPRESS)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.serve:
        return serve()
    if args.job:
        try:
            _job(*args.job)
            return 0
        except Exception as exc:
            # The isolated transport receives only a class, never an exception
            # message or traceback containing private inputs.
            print(type(exc).__name__, file=sys.stderr, flush=True)
            return 1
    if not args.plan and args.calibration_year is None:
        parser.error("model runs require --calibration-year; this dataset has no verified calibration metadata")
    if args.jobs_per_worker < 1:
        parser.error("--jobs-per-worker must be positive")
    if args.verify_workers and args.central_only:
        parser.error("--verify-workers needs a noncentral path; omit --central-only")
    if args.output is None:
        args.output = REPO / (".cache/ageing-runner-equivalence.json" if args.verify_workers else "data/ageing_validation.json")
    plan = validation_plan(args.source_results, args.central_only, args.calibration_year)
    if args.plan:
        print(json.dumps({"jobs": len(plan["jobs"]), "sample": plan["sample"], "W": plan["W"],
                          "W0": plan["W0"], "calibration_year": plan["calibration_year"],
                          "source_sha256": plan["source_sha256"]}, indent=2))
        return 0
    resources = host_resources()
    print(f"Host: {resources['logical_cpus']} CPUs, {resources['total_ram_gib']} GiB RAM, "
          f"{resources['available_ram_gib']} GiB available; {args.workers} workers")
    if args.verify_workers:
        report = verify_worker_equivalence(plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        return 0
    from . import ageing_publication
    plan.update(ageing_publication.calculation_metadata(plan))
    with PersistentRunner(max_jobs=args.jobs_per_worker) if args.persistent_workers else contextlib.nullcontext(isolated_runner) as runner:
        results = engine.run_jobs(plan["jobs"], workers=args.workers, slot_prefix="ageing", runner=runner)
    audit = ageing_publication.collect_input_support(plan)
    ageing_publication.guard_results(plan, results, audit)
    report = summarise(plan, results)
    report["publication_privacy_audit"] = audit
    report["calculation_head"] = plan["calculation_head"]
    report["calculation_provenance"] = plan["calculation_provenance"]
    report["host_before_runs"] = resources
    report["worker_execution"] = {"persistent": args.persistent_workers,
                                  "enhanced_frs_workers": args.workers, "microcosm_workers": 0,
                                  "maximum_jobs_per_worker": args.jobs_per_worker if args.persistent_workers else 1,
                                  "memory_diagnostics": "private per-job RSS in .cache worker logs"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Wrote aggregate validation to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
