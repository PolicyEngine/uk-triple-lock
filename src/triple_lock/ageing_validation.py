"""The four-way ageing design (#14 section 3), aggregates only: what represented ages, the ONS reweighting and cohort
pension types each do to the saving, alone and together, on paired full runs.

Every job is an ordinary engine path job (engine.run_path) with the path's ``demography`` set to a treatment
(config.DEMOGRAPHY_MODES), so the four-way runs and the published runs are one implementation, cached together: the
``both`` runs are the published ones. Jobs: the central path and the committed expected value's Microcosm-paired
draws (40), each under ``legacy`` (part A's engine treatment) and the four treatments ``frozen``, ``reweight``,
``types`` and ``both``, all on the primary Enhanced FRS; and one coverage job per treatment.

The contrasts are computed within each path before the stratified average (expected_value.stratified_estimate, with
the committed stratum probabilities; the identical-rates stratum saves exactly zero under every treatment):

* ``reweight_effect`` = reweight - frozen, ``types_effect`` = types - frozen, ``combined_effect`` = both - frozen;
* ``interaction`` = both - reweight - types + frozen (the four-way term, not two isolated effects);
* ``common_input_effect`` = frozen - legacy (represented ages and the birthday draw).

Part B's pilot of this design on policyengine-uk 2.90.2 ran its own worker and publication guard; its approved output
(data/ageing_validation.json, rendered as docs/AGEING_PILOT_RESULTS.md by scripts/report_ageing_validation.py) is
the historical record. Part D replaced that worker with the engine's own jobs: one implementation of the fiscal totals.

What is published: savings (UK and Great Britain) and their paired contrasts, State Pension spending against DWP's
matched GB totals, and State Pension by age (each cell on at least ten records, disclosure.py; the whole age family
withheld across treatments if any cell is suppressed in any, so no cell can be recovered by subtracting treatments).
No record id, weight or amount: ageing runs return no single-record diagnostic.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import engine, expected_value as EV
from .config import DEMOGRAPHY, DEMOGRAPHY_MODES, HORIZON, PRIMARY_DATASET, REPO
from .disclosure import MIN_RECORDS, complementary_suppression, coverage_cell  # noqa: F401  (re-exported)
from .dwp import TABLES, TABLES_PAGE, TABLES_URL

MODES = ("frozen", "reweight", "types", "both")  # factorial; total is a separate control
RUN_MODES = DEMOGRAPHY_MODES
SOURCE_RESULTS = REPO / "data" / "results.json"
COVERAGE_YEARS = [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2034, 2039]
CONTRASTS = ("reweight_effect", "types_effect", "combined_effect", "interaction", "common_input_effect",
             "population_total_effect", "age_structure_effect")
MAX_WORKERS = 3  # Enhanced FRS processes; this command starts no Microcosm one


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
    if not np.isclose(sum(W.values()) + (0 if 0 in W else W0), 1, atol=1e-10):
        raise ValueError("source stratum probabilities do not sum to one")
    return sample, W, W0, by_draw


def path_specs(source, central_only=False):
    """{label: spec}: the central path and each paired draw's spec, rebuilt from the committed draw design and checked
    against the statutory inputs the committed results recorded for it."""
    from .central import central_path
    from .config import STATUTORY_YEARS
    from .trajectories import central_spec

    c = central_path()
    specs = {"central": {k: v for k, v in central_spec(c).items() if k not in ("id", "label", "source")}}
    if central_only:
        return specs
    _, _, _, stored = paired_sample(source)
    ev = source["expected_value"]
    provenance = ev["draws"]
    if "form" in provenance:
        from .ts_uncertainty import future_draws
        ds = future_draws(provenance["form"], c, n=int(provenance["n"]), seed=int(provenance["seed"]))
    else:
        draws = EV.draws(c, n=int(provenance["n"]), seed=int(provenance["seed"]), kind=provenance["shocks"])
        ds = draws[ev["calibrations"][ev["primary"]]["draws"]]
    for i in sorted(stored):
        spec = EV.path_spec(ds, i)
        for variable, key in (("cpi", "statutory_cpi"), ("earnings", "statutory_earnings")):
            actual = np.array([spec[key][y] for y in STATUTORY_YEARS])
            expected = np.array([stored[i]["statutory"][variable][str(y)] for y in STATUTORY_YEARS])
            if not np.allclose(actual, expected, rtol=0, atol=1e-12):
                raise ValueError(f"draw {i} no longer reproduces the committed paired path")
        specs[f"draw_{i}"] = spec
    return specs


def canonical(arg):
    """A job argument as the build writes the same job: no ``dataset`` for the primary dataset and no ``demography``
    for the default treatment, so the ``both`` runs here and the build's own share one cache entry."""
    return {k: v for k, v in arg.items()
            if not (k == "dataset" and v == PRIMARY_DATASET) and not (k == "demography" and v == DEMOGRAPHY)}


def validation_plan(source_path=SOURCE_RESULTS, central_only=False, modes=RUN_MODES, dataset=PRIMARY_DATASET):
    """The jobs (engine path and coverage jobs) and how to read them back, without loading a survey."""
    from .central import september_cpi_history

    source_path = Path(source_path)
    source = json.loads(source_path.read_text())
    # The central path alone needs no expected-value section (a file built under d955's scenario envelope has none).
    sample, W, W0 = ({}, {}, 1.0) if central_only else paired_sample(source)[:3]
    specs = path_specs(source, central_only)
    jobs, labels = [], []
    for name, spec in specs.items():
        for mode in modes:
            jobs.append(("path", canonical({**spec, "dataset": dataset, "demography": mode})))
            labels.append((name, mode))
    for mode in modes:
        jobs.append(("coverage", canonical({"years": COVERAGE_YEARS, "september_cpi_history": september_cpi_history(),
                                            "spec": specs["central"], "dataset": dataset, "demography": mode})))
        labels.append(("coverage", mode))
    return {"jobs": jobs, "labels": labels, "sample": sample, "W": W, "W0": W0, "modes": list(modes),
            "n_draws": None if central_only else int(source["expected_value"]["draws"]["n"]),
            "central_only": central_only, "dataset": dataset, "source_sha256": engine.file_hash(source_path),
            "source": str(source_path.relative_to(REPO)) if source_path.is_relative_to(REPO) else source_path.name}


def four_way(runs, selector):
    """Paired differences and the interaction, calculated before sampling uncertainty."""
    values = {mode: float(selector(runs[mode])) for mode in MODES}
    out = {**values, "reweight_effect": values["reweight"] - values["frozen"],
           "types_effect": values["types"] - values["frozen"],
           "combined_effect": values["both"] - values["frozen"],
           "interaction": values["both"] - values["reweight"] - values["types"] + values["frozen"]}
    if "legacy" in runs:
        out["legacy"] = float(selector(runs["legacy"]))
        out["common_input_effect"] = values["frozen"] - out["legacy"]
    if "total" in runs:
        out["total"] = float(selector(runs["total"]))
        out["population_total_effect"] = out["total"] - values["frozen"]
        out["age_structure_effect"] = values["reweight"] - out["total"]
    return out


def withhold_linked_coverage(grouped):
    """Fail closed across every linked mode, year, policy and path before publication: if any age (or geography) cell
    is suppressed anywhere, withhold that whole family everywhere, so no small cell is recovered by subtracting two
    treatments, years or policies. ``grouped``: {path: {mode: {"coverage": {policy: {year: tables}}}}}."""
    families = {"age": ("by_age",), "geography": ("by_country", "by_region")}
    tables = [year for runs in grouped.values() for run in runs.values()
              for policy in run["coverage"].values() for year in policy.values()]
    withheld = {}
    for family, names in families.items():
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


def _saving(run, year, measure, geography):
    s = run["saving_bn"][year]
    return s["gb"][measure] if geography == "gb" else s[measure]


def summarise(plan, results):
    """Public aggregate tables and paired stratified estimates; never copies a raw job result."""
    grouped, coverage = {}, {}
    for (name, mode), result in zip(plan["labels"], results, strict=True):
        if name == "coverage":
            coverage[mode] = result
        else:
            grouped.setdefault(name, {})[mode] = result
    modes = plan["modes"]
    if any(set(runs) != set(modes) for runs in grouped.values()):
        raise ValueError("every path needs every treatment")
    factorial = set(MODES) <= set(modes)
    central = grouped["central"]
    measures = [(m, g) for g in ("uk", "gb") for m in ("gross", "net")]
    by_treatment = {"central": {mode: {g: {m: {y: _saving(run, y, m, g) for y in HORIZON} for m in ("gross", "net")}
                                       for g in ("uk", "gb")} for mode, run in central.items()}}
    expected = {}
    if not plan["central_only"]:
        per_draw = {i: grouped[f"draw_{i}"] for indices in plan["sample"].values() for i in indices}
        n_draws = plan.get("n_draws", EV.N_DRAWS)
        for mode in modes:
            expected[mode] = {g: {m: {y: EV.stratified_estimate(
                {k: [_saving(per_draw[i][mode], y, m, g) for i in idx] for k, idx in plan["sample"].items()},
                plan["W"], n_draws) for y in HORIZON} for m in ("gross", "net")} for g in ("uk", "gb")}
        if factorial:
            available_contrasts = [contrast for contrast in CONTRASTS
                                   if not (contrast == "common_input_effect" and "legacy" not in modes)
                                   and not (contrast in ("population_total_effect", "age_structure_effect")
                                            and "total" not in modes)]
            for contrast in available_contrasts:
                expected[contrast] = {g: {m: {y: EV.stratified_estimate(
                    {k: [four_way(per_draw[i], lambda r: _saving(r, y, m, g))[contrast] for i in idx]
                     for k, idx in plan["sample"].items()}, plan["W"], n_draws) for y in HORIZON}
                    for m in ("gross", "net")} for g in ("uk", "gb")}
    central_contrasts = ({g: {m: {y: four_way(central, lambda r: _saving(r, y, m, g)) for y in HORIZON}
                              for m in ("gross", "net")} for g in ("uk", "gb")} if factorial else None)
    by_age = {mode: {"coverage": {"triple_lock": {y: {"by_age": t["gb"]["state_pension_by_age"]}
                                                  for y, t in run["by_year"].items()}}}
              for mode, run in coverage.items()}
    suppression = withhold_linked_coverage({"coverage": by_age}) if coverage else None
    dwp = dwp_forecasts()
    rows = []
    for mode, run in coverage.items():
        for y, t in run["by_year"].items():
            target = dwp["years"].get(int(y))
            for metric, model in (("state_pension_bn", t["gb"]["state_pension_bn"]),
                                  ("recipients_m", t["gb"]["state_pension_recipients"] / 1e6)):
                benchmark = target["GB"][metric] if target else None
                rows.append({"year": int(y), "mode": mode, "metric": metric, "model_GB": model,
                             "benchmark_GB": benchmark,
                             "difference": None if benchmark is None else model - benchmark,
                             "status": "available" if benchmark is not None else "unavailable"})
    first = next(iter(central.values()))
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dataset": plan["dataset"], "model": first.get("model"), "modes": modes,
            "complete_paired_design": not plan["central_only"], "source_results": plan["source"],
            "source_results_sha256": plan["source_sha256"], "minimum_contributing_records": MIN_RECORDS,
            "paired_sample": {"draws_by_stratum": plan["sample"], "probability_by_stratum": plan["W"],
                              "identical_rule_probability": plan["W0"]},
            "central_saving_bn": by_treatment["central"], "central_four_way_saving_bn": central_contrasts,
            "expected_saving_bn": expected, "measures": [f"{g}.{m}" for m, g in measures],
            "coverage_comparisons": rows, "state_pension_by_age": by_age, "age_suppression": suppression,
            "dwp": {k: v for k, v in dwp.items() if k != "years"},
            "fixed_inputs": {mode: {k: run["fixed_inputs"].get(k) for k in ("population", "ageing",
                                                                            "state_pension_accounting")}
                             for mode, run in central.items()},
            "method": "Full PolicyEngine UK runs (engine.run_path) of the central path and the committed 40 "
                      "Microcosm-paired draws under each treatment, both rules, no output scaling. Contrasts are "
                      "computed within each path before stratified averaging; standard errors preserve repeated "
                      "draws and add the first-phase variance (expected_value.stratified_estimate)."}


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-o", "--output", type=Path, default=REPO / ".cache" / "ageing_validation.json",
                        help="aggregate report (default .cache/ageing_validation.json; nothing is committed)")
    parser.add_argument("--source-results", type=Path, default=SOURCE_RESULTS)
    parser.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=1,
                        help="Enhanced FRS processes (about 6 GB each); this command starts no Microcosm one")
    parser.add_argument("--modes", nargs="+", choices=RUN_MODES, default=list(RUN_MODES))
    parser.add_argument("--central-only", action="store_true", help="central path only: a preliminary run")
    parser.add_argument("--plan", action="store_true", help="print the job counts and paired draws; run nothing")
    args = parser.parse_args(argv)
    plan = validation_plan(args.source_results, args.central_only, tuple(args.modes))
    if args.plan:
        kinds = [kind for kind, _ in plan["jobs"]]
        print(json.dumps({"jobs": len(kinds), "path_jobs": kinds.count("path"),
                          "coverage_jobs": kinds.count("coverage"), "modes": plan["modes"],
                          "sample": plan["sample"], "W": plan["W"], "W0": plan["W0"]}, indent=2))
        return 0
    from . import jobs

    results = jobs.run_jobs(plan["jobs"], workers=args.workers, slot_prefix="efrs")
    report = summarise(plan, results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1, default=float, allow_nan=False) + "\n")
    print(f"Wrote the aggregate four-way report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
