"""Parameter-only pension-age Housing Benefit and Savings Credit audit.

This diagnostic deliberately makes no production policy choice. It reads the
committed forecast/scenario inputs, calls the engine's guarantee builder, and
reproduces the certified model's rounded lagged-CPI index. No dataset is loaded.
The component option is a sensitivity, not an assertion of future enacted law.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from . import engine, rules
from .config import (AWE_CSV, BASE_YEAR, CENTRAL_FORECAST_CSV, CENTRAL_RATE_DECIMALS, CPI_CSV,
                     FINAL_YEAR, HORIZON, PENSION_CREDIT_GUARANTEE, REPO)

SNAPSHOT = REPO / "data/diagnostics/hb_allowance_parameter_snapshot.json"
OUTPUT = REPO / "data/diagnostics/pension_age_allowances.json"
ANNUAL_OUTPUT = REPO / "data/diagnostics/pension_age_allowances.csv"
MEAN_SPEC_DIR = REPO / "data/pilot/c2-dry-run"
HB_PATHS = {name: f"gov.dwp.housing_benefit.allowances.{name}.aged"
            for name in ("single", "couple", "lone_parent")}
SC_PATHS = {name: f"gov.dwp.pension_credit.savings_credit.threshold.{name.upper()}"
            for name in ("single", "couple")}


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _last_value(node, instant=f"{BASE_YEAR}-06-01"):
    values = node["values"]
    value = values[max(date for date in values if date <= instant)]
    return float(value["value"] if isinstance(value, dict) else value)


def snapshot_base_values(snapshot, source="upstream"):
    """The enacted 2026 bases and index anchor, independently snapshotted from main and the installed model."""
    files = snapshot["files"]
    pc = files["gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml"][source]["yaml"]
    sc = files["gov/dwp/pension_credit/savings_credit/threshold.yaml"][source]["yaml"]
    phase = files["gov/dwp/pension_credit/savings_credit/rate/phase_in.yaml"][source]["yaml"]
    out = {PENSION_CREDIT_GUARANTEE[name]: _last_value(pc[name.upper()]) for name in ("single", "couple")}
    out.update({path: _last_value(files[f"gov/dwp/housing_benefit/allowances/{name}/aged.yaml"][source]["yaml"])
                for name, path in HB_PATHS.items()})
    out.update({path: _last_value(sc[name.upper()]) for name, path in SC_PATHS.items()})
    return out, _last_value(phase)


def verify_index_anchor(snapshot):
    """Derive the recorded 2026 rounded index independently from each source's historical CPI."""
    meta = snapshot["index_projection"]
    for source in ("upstream", "installed"):
        history = snapshot["files"]["gov/economic_assumptions/yoy_growth.yaml"][source]["yaml"]["obr"]["consumer_price_index"]
        index = 1.0  # lag_cpi.py starts the lagged index in 2010.
        for year in range(2011, BASE_YEAR + 1):
            index = round(index * (1 + _last_value(history, f"{year - 1}-01-01")), meta["round_decimals"])
        if index != meta["lagged_cpi_2026"]:
            raise ValueError(f"{source} historical CPI does not reproduce the recorded 2026 index")
        if _last_value(history) != meta["calendar_cpi_2026"]:
            raise ValueError(f"{source} 2026 calendar CPI differs from the recorded model value")


class SnapshotParameters:
    """Read-only 2026 parameter adapter accepted by engine.pension_credit_levels."""

    def __init__(self, values):
        self.values = values

    def get_child(self, path):
        def read(instant):
            if instant != f"{BASE_YEAR}-06-01":
                raise ValueError("The snapshot only supplies the enacted 2026 base")
            return self.values[path]
        return read


def committed_paths(results, spec_dir=MEAN_SPEC_DIR):
    """Every future envelope path, its paired baseline, and the illustrated paths.

    The envelope stores paired fiscal aggregates; its exact macro inputs live
    in the committed spec files. The handoff is a separately refreshed
    provenance receipt, not a macro input to this diagnostic. The historical replay of April
    2017-2026 uses model years 2024-2026, rather than forecasting to 2039.
    """
    envelope = results["scenario_envelope"]

    def from_run(path_id, label, group, run):
        return {"id": path_id, "label": label, "group": group,
                "rate_decimals": run.get("rate_decimals", CENTRAL_RATE_DECIMALS),
                "statutory_earnings": {int(y): v for y, v in run["statutory"]["earnings"].items()},
                "statutory_cpi": {int(y): v for y, v in run["statutory"]["cpi"].items()},
                "cpi": {int(y): v for y, v in run["calendar"]["cpi"].items()}}

    paths = [from_run("central", "Central forecast", "central", results["central"]["run"]),
             from_run("obr_wedge", envelope["obr_wedge"]["label"], "obr_wedge", envelope["obr_wedge"]["run"])]
    for run in results["trajectories"]["paths"]:
        if run["id"] != "central":
            paths.append(from_run(run["id"], run["label"], "illustrated", run))

    # These committed macro inputs are stable across provenance-only handoff
    # refreshes. Do not hash/read that receipt as if it were a projection input.
    mean_specs = {name: f"{name}.specs.json"
                  for name in ("earnings_minus_0_5pp", "earnings_plus_0_5pp")}
    groups = {"paired_baseline": "monthly_var1_boot.specs.json"}
    for name in envelope["paired_earnings_mean_paths"]["scenarios"]:
        groups[name] = mean_specs[name]
    for group, filename in groups.items():
        for spec in json.loads((spec_dir / filename).read_text()):
            paths.append({"id": f"{group}/{spec['id']}", "label": spec["id"], "group": group,
                          "rate_decimals": spec.get("rate_decimals", CENTRAL_RATE_DECIMALS),
                          **{key: {int(y): v for y, v in spec[key].items()}
                             for key in ("cpi", "statutory_cpi", "statutory_earnings")}})
    if len({p["id"] for p in paths}) != len(paths):
        raise ValueError("Duplicate diagnostic path IDs")
    return paths, [spec_dir / filename for filename in groups.values()]


def cpi_indices(calendar_cpi, index_anchor, calendar_cpi_2026, decimals=5):
    """Mirror create_economic_assumption_indices: lag one year, round each index to 5 dp.

    Gov.benefit_uprating_cpi and its dependent amounts are ratios of these
    indices. They have no additional amount rounding. Calendar 2026 remains
    the model's own on every path, as in engine.econ_changes.
    """
    growth = {BASE_YEAR: calendar_cpi_2026, **calendar_cpi}
    indices = {BASE_YEAR: index_anchor}
    for year in HORIZON:
        indices[year] = round(indices[year - 1] * (1 + growth[year - 1]), decimals)
    return {year: index / index_anchor for year, index in indices.items()}


def component_cpi_indices(statutory_cpi, decimals):
    """Sensitivity: retained HB uplift/maximum Savings Credit follow nonnegative September CPI.

    Inputs use the engine's published precision; the cash components are not
    rounded each year. This is an explicit option, separate from current CPI
    projections and from the engine's guarantee override.
    """
    out = {BASE_YEAR: 1.0}
    for year in HORIZON:
        growth = max(float(rules.round_rate(statutory_cpi[year - 1], decimals)), 0.0)
        out[year] = out[year - 1] * (1 + growth)
    return out


def project_path(spec, snapshot):
    bases, phase_in = snapshot_base_values(snapshot)
    decimals = spec["rate_decimals"]
    guarantee = engine.pension_credit_levels(SnapshotParameters(bases), spec["statutory_earnings"], decimals)
    index_meta = snapshot["index_projection"]
    cpi = cpi_indices(spec["cpi"], index_meta["lagged_cpi_2026"], index_meta["calendar_cpi_2026"],
                      index_meta["round_decimals"])
    component_cpi = component_cpi_indices(spec["statutory_cpi"], decimals)
    annual, summary = [], {}
    for kind, parameters in (("hb", HB_PATHS), ("savings_threshold", SC_PATHS)):
        for name, path in parameters.items():
            guarantee_path = PENSION_CREDIT_GUARANTEE["single" if name == "lone_parent" else name]
            base_g = bases[guarantee_path]
            g_levels = {BASE_YEAR: base_g, **guarantee[guarantee_path]}
            series = []
            for year in [BASE_YEAR, *HORIZON]:
                g = g_levels[year]
                current = bases[path] * cpi[year]
                if kind == "hb":
                    component = g + (bases[path] - base_g) * component_cpi[year]
                else:
                    # Enacted maximum rounded to pennies as in PR #2092;
                    # £17.958 -> £17.96 (single), £20.10 (couple).
                    base_maximum = round(phase_in * (base_g - bases[path]), 2)
                    component = bases[path] if year == BASE_YEAR else g - base_maximum * component_cpi[year] / phase_in
                row = {"path": spec["id"], "group": spec["group"], "year": year,
                       "kind": kind, "relationship": name, "guarantee_weekly": g,
                       "current_weekly": current, "guarantee_minus_current_weekly": g - current,
                       "component_option_weekly": component,
                       "component_option_minus_current_weekly": component - current,
                       "guarantee_floor_option_weekly": max(current, g) if kind == "hb" else None}
                annual.append(row)
                series.append(row)
            final = series[-1]
            summary[f"{kind}_{name}"] = {
                "first_guarantee_exceeds_parameter_year": next((r["year"] for r in series
                                                                if r["guarantee_minus_current_weekly"] > 1e-10), None),
                "first_parameter_exceeds_guarantee_year": next((r["year"] for r in series
                                                                if r["guarantee_minus_current_weekly"] < -1e-10), None),
                **{key: final[key] for key in ("guarantee_weekly", "current_weekly", "guarantee_minus_current_weekly",
                                                "component_option_weekly", "component_option_minus_current_weekly",
                                                "guarantee_floor_option_weekly")}}
    return {"id": spec["id"], "label": spec["label"], "group": spec["group"], "parameters": summary}, annual


def build(results_path=REPO / "data/results.json", snapshot_path=SNAPSHOT, spec_dir=MEAN_SPEC_DIR):
    from .central import central_path

    snapshot = json.loads(snapshot_path.read_text())
    verify_index_anchor(snapshot)
    bases, _ = snapshot_base_values(snapshot)
    installed_bases, _ = snapshot_base_values(snapshot, "installed")
    if bases != installed_bases:
        raise ValueError("Installed and current-main enacted 2026 bases differ; revise this diagnostic explicitly")
    results = json.loads(results_path.read_text())
    current_central = central_path()
    for key in ("calendar", "statutory"):
        saved = results["central"]["run"][key]
        current = {series: {str(year): value for year, value in by_year.items()}
                   for series, by_year in current_central[key].items()}
        if saved != current:
            raise ValueError(f"Committed central {key} no longer matches the engine's source inputs")
    paths, inputs = committed_paths(results, spec_dir)
    summaries, annual = [], []
    for spec in paths:
        summary, rows = project_path(spec, snapshot)
        summaries.append(summary)
        annual.extend(rows)
    inputs = [results_path, snapshot_path, CENTRAL_FORECAST_CSV, AWE_CSV, CPI_CSV, *inputs]
    return {"description": "Parameter-only diagnostic; no microsimulation and no production parameter changes",
            "years": [BASE_YEAR, FINAL_YEAR], "gap_sign": "guarantee minus parameter, GBP/week",
            "upstream_commit": snapshot["upstream_commit"], "installed_policyengine_uk_version":
            snapshot["installed_policyengine_uk_version"],
            "excluded": {"reason": "Historical legal replay, not a future forecast",
                         "uprating_years": results["scenario_envelope"]["last_decade_replay"]["years"],
                         "model_years": results["scenario_envelope"]["last_decade_replay"]["model_years"]},
            "options": {
                "current": "Whole allowance and Savings Credit threshold follow the rounded model lagged calendar CPI index",
                "component": "HB = guarantee + (HB_2026 - guarantee_2026) * nonnegative statutory CPI index; Savings threshold = guarantee - penny-rounded 2026 maximum Savings Credit * same index / phase-in rate",
                "guarantee_floor": "HB = max(current whole-CPI allowance, applied guarantee)"},
            "path_groups": dict(Counter(p["group"] for p in paths)),
            "input_sha256": {str(p.relative_to(REPO)): _digest(p) for p in inputs}, "paths": summaries}, annual


def annual_table(annual):
    """One readable CSV row per path/year, with exact series retained to ten decimal places."""
    rows = {}
    for entry in annual:
        key = entry["path"], entry["year"]
        row = rows.setdefault(key, {name: entry[name] for name in ("path", "group", "year")})
        relationship = "single" if entry["relationship"] == "lone_parent" else entry["relationship"]
        row[f"guarantee_{relationship}_weekly"] = entry["guarantee_weekly"]
        parameter = f"{entry['kind']}_{entry['relationship']}"
        row[f"{parameter}_current_weekly"] = entry["current_weekly"]
        row[f"{parameter}_component_option_weekly"] = entry["component_option_weekly"]
        if entry["kind"] == "hb":
            row[f"{parameter}_guarantee_floor_option_weekly"] = entry["guarantee_floor_option_weekly"]
    return [{k: f"{v:.10f}" if isinstance(v, float) else v for k, v in row.items()} for row in rows.values()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--annual-output", type=Path, default=ANNUAL_OUTPUT)
    args = parser.parse_args(argv)
    report, annual = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    args.annual_output.parent.mkdir(parents=True, exist_ok=True)
    annual_rows = annual_table(annual)
    with args.annual_output.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(annual_rows[0]))
        writer.writeheader()
        writer.writerows(annual_rows)
    print(json.dumps({"paths": len(report["paths"]), "annual_parameter_rows": len(annual),
                      "annual_csv_rows": len(annual_rows),
                      "output": str(args.output), "annual_output": str(args.annual_output)}, sort_keys=True))


if __name__ == "__main__":
    main()
