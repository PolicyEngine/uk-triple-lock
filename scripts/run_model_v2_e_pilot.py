"""Run part E from a frozen source export; save only disclosure-checked aggregates.

The source export, private job cache and output must be inside this workspace.
--plan describes the 252 jobs without loading a survey or starting any job.
The driver imports every triple_lock module from --source, so development edits
in the live workspace cannot reach a running worker. Raw job results remain in
the source export's owner-only cache and never enter the public output.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys

PRIMARY = "enhanced_frs_2024_25@1.56.16"
TREATMENTS = {name: (name, "kept") for name in ("frozen", "reweight", "types", "both", "total")}
TREATMENTS["both_full_new"] = ("both", "full_new")
YEARS = (2034, 2039)
COVERAGE_YEARS = (2024, 2025, 2026, 2027, 2028, 2029, 2030, *YEARS)
GEOGRAPHIES = ("uk", "gb")
MEASURES = ("gross", "net")
COUNTRIES = ("ENGLAND", "SCOTLAND", "WALES")
MIN_RECORDS = 10
CONTRASTS = {
    "retyped_level_upper_minus_kept": {"both_full_new": 1, "both": -1},
    "total_population_effect": {"total": 1, "frozen": -1},
    "age_structure_effect": {"reweight": 1, "total": -1},
    "reweight_effect": {"reweight": 1, "frozen": -1},
    "types_effect": {"types": 1, "frozen": -1},
    "combined_effect": {"both": 1, "frozen": -1},
    "interaction": {"both": 1, "reweight": -1, "types": -1, "frozen": 1},
}
PUBLIC_CONTRAST_NAMES = {"age_structure_effect": "reweight_minus_ons_total"}


def public_contrast_name(name):
    # Preserve executed job arguments and their cache keys. The two treatments
    # have different population totals, so this is not an isolated age effect.
    return PUBLIC_CONTRAST_NAMES.get(name, name)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan(specifications, draw_provenance):
    """Preserve D's exact paired indices, multiplicities and stratum masses."""
    paired = {int(i): row for i, row in specifications["paired"].items()}
    sample = {}
    for i, row in paired.items():
        count, stratum = int(row["times_drawn"]), int(row["stratum"])
        if count < 1:
            raise ValueError("paired macro draws must have positive multiplicities")
        sample.setdefault(stratum, []).extend([i] * count)
    if len(paired) != 40 or sum(map(len, sample.values())) != 40:
        raise ValueError("part E requires the original 40 distinct paired macro draw indices and slots")
    if min(map(len, sample.values())) < 2:
        raise ValueError("every paired stratum needs two slots")
    probabilities = {int(k): float(p) for k, p in specifications["paired_strata_probability"].items()}
    zero_mass = float(specifications["identical_rates_probability"])
    if (set(sample) != set(probabilities) or any(p < 0 for p in probabilities.values())
            or abs(sum(probabilities.values()) + (0 if 0 in probabilities else zero_mass) - 1) > 1e-10):
        raise ValueError("paired stratum probabilities do not match the committed design")
    paths = {"central": specifications["central"],
             **{f"draw_{i}": row["spec"] for i, row in sorted(paired.items())}}
    jobs, labels, execution_jobs, execution_labels = [], [], [], []
    for name, specification in paths.items():
        batch = {}
        for treatment, (mode, level) in TREATMENTS.items():
            batch[treatment] = {**deepcopy(specification), "dataset": PRIMARY,
                                "demography": mode, "retyped_level": level,
                                "fiscal_output_years": list(YEARS)}
            jobs.append(("path", batch[treatment]))
            labels.append((name, treatment))
        execution_jobs.append(("treatment_paths", {"specs": batch, "contrasts": CONTRASTS}))
        execution_labels.append((name, None))
    for treatment, (mode, level) in TREATMENTS.items():
        jobs.append(("coverage", {"years": list(COVERAGE_YEARS), "dataset": PRIMARY,
                                  "september_cpi_history": specifications["september_cpi_history"],
                                  "spec": specifications["central"], "demography": mode,
                                  "retyped_level": level}))
        labels.append(("coverage", treatment))
        execution_jobs.append(jobs[-1])
        execution_labels.append(labels[-1])
    return {"jobs": jobs, "labels": labels, "sample": sample, "probabilities": probabilities,
            "execution_jobs": execution_jobs, "execution_labels": execution_labels,
            "identical_rates_probability": zero_mass, "draw_provenance": draw_provenance}


def execute_design(design, run_jobs, *, workers, cache):
    """Run 41 fresh treatment batches plus coverage, then flatten aggregate results.

    A fresh batch process loads one pristine same-path setup. Six full paths
    each use independent simulation clones and calculate all thirteen fiscal
    years; publication selects 2034/2039 after the complete calculations.
    Transient household contributions are discarded after counting contrast
    support. Only aggregate results cross the process boundary.
    """
    if workers not in (1, 2):
        raise ValueError("part E treatment batches allow at most two Enhanced FRS workers")
    outputs = run_jobs(design["execution_jobs"], workers=workers, slot_prefix="pilot-e-efrs", cache=cache)
    grouped, coverage = {}, {}
    for (name, treatment), result in zip(design["execution_labels"], outputs, strict=True):
        if name == "coverage":
            coverage[treatment] = result
        else:
            if set(result) != set(TREATMENTS):
                raise ValueError("treatment batch must return every treatment aggregate exactly once")
            grouped[name] = result
    if sum(map(len, grouped.values())) + len(coverage) != len(design["labels"]):
        raise ValueError("flattened batch results do not match the 252 planned scientific run labels")
    return grouped, coverage


def _supported(count):
    return isinstance(count, int) and (count == 0 or count >= MIN_RECORDS)


def _linked_geographic_support(uk, gb):
    """UK/GB publication also exposes their Northern Ireland complement."""
    return (_supported(uk) and _supported(gb) and uk >= gb and _supported(uk - gb))


def _saving(run, year, geography, measure):
    row = run["saving_bn"][year]
    return float(row["gb"][measure] if geography == "gb" else row[measure])


def fiscal_suppression(grouped):
    """Suppress a whole linked output family if any path/treatment/year is small.

    A family joins UK and GB, years, and every treatment; retaining the other
    geography or treatment must not expose a suppressed cell by subtraction.
    Counts are engine-computed household contributors to each policy contrast.
    """
    withheld = {}
    for measure in MEASURES:
        withheld[measure] = any(not _linked_geographic_support(
            run.get("saving_support_records_by_year", {}).get(year, {}).get("uk", {}).get(measure),
            run.get("saving_support_records_by_year", {}).get(year, {}).get("gb", {}).get(measure))
            for runs in grouped.values() for run in runs.values() for year in YEARS)
    return withheld


def fiscal_tables(design, grouped, estimator):
    withheld = fiscal_suppression(grouped)
    central, paired = [], []
    families = {**{name: {name: 1} for name in TREATMENTS}, **CONTRASTS}
    contrast_withheld = {family: {} for family in CONTRASTS}
    for family, coefficients in CONTRASTS.items():
        for measure in MEASURES:
            receipts = []
            for runs in grouped.values():
                for year in YEARS:
                    for mode, run in runs.items():
                        if mode not in coefficients:
                            continue
                        counts = run.get("treatment_contrast_support_records_by_year", {}).get(year, {})
                        receipts.append(_linked_geographic_support(
                            counts.get("uk", {}).get(family, {}).get(measure),
                            counts.get("gb", {}).get(family, {}).get(measure)))
            contrast_withheld[family][measure] = not all(receipts)
    # These contrasts connect every treatment. Hiding only a difference or
    # one direct pair would leave algebraic recovery through other published
    # contrasts, so close the whole linked measure family when any fails.
    treatment_family_withheld = {measure: any(family[measure] for family in contrast_withheld.values())
                                 for measure in MEASURES}
    for family, coefficients in families.items():
        for geography in GEOGRAPHIES:
            for measure in MEASURES:
                for year in YEARS:
                    metadata = {"treatment_or_contrast": public_contrast_name(family), "geography": geography.upper(),
                                "measure": measure, "year": year}
                    if withheld[measure] or treatment_family_withheld[measure]:
                        reason = ("A linked full-run policy contrast or geography complement is unsupported "
                                  "or rests on fewer than ten records."
                                  if withheld[measure] else
                                  "Across-treatment contributor support is missing or suppressed; linked levels "
                                  "and contrasts are withheld to prevent recovery by subtraction.")
                        central.append({**metadata, "status": "withheld_family", "value_bn": None,
                                        "suppression_reason": reason})
                        paired.append({**metadata, "status": "withheld_family", "estimate_bn": None,
                                       "suppression_reason": reason})
                        continue
                    def value(name):
                        return sum(coefficient * _saving(grouped[name][mode], year, geography, measure)
                                   for mode, coefficient in coefficients.items())
                    central.append({**metadata, "status": "available", "value_bn": value("central"),
                                    "se": None, "interpretation": "deterministic central-path scenario"})
                    estimate = estimator.stratified_estimate(
                        {k: [value(f"draw_{i}") for i in indices] for k, indices in design["sample"].items()},
                        design["probabilities"], int(design["draw_provenance"]["n"]))
                    paired.append({**metadata, "status": "available", "estimate_bn": estimate,
                                   "interpretation": "model-conditional pilot path set; d955 presentation pending"})
    return {"central": central, "paired": paired,
            "suppression": {"whole_family_withheld": withheld, "minimum_records": MIN_RECORDS,
                            "contrast_family_withheld": {public_contrast_name(name): value
                                                         for name, value in contrast_withheld.items()},
                            "treatment_level_family_withheld": treatment_family_withheld,
                            "scope": "all linked paths, treatments, years, UK/GB geographies and their country complement",
                            "support_definition": "engine household contributors to the full-run policy contrast; "
                                                  "treatment differences use exact across-treatment household "
                                                  "contribution counts computed transiently inside each full-run batch"},
            "contrast_definitions": {"reweight_minus_ons_total":
                "Age/sex reweighting minus the ONS aggregate-total control. Their population totals differ; "
                "this contrast includes that difference. Use the separate matched-total supplement to isolate "
                "the age-structure effect at an equal population total."}}


def _withhold(row):
    return {key: "withheld_family" if key == "status" else None for key in row}


def linked_country_tables(coverage):
    tables = {mode: {year: deepcopy(table["gb"]["state_pension_by_country"])
                     for year, table in run["by_year"].items()} for mode, run in coverage.items()}
    withheld = any(row.get("status") != "available" or not _supported(row.get("records"))
                   for years in tables.values() for table in years.values() for row in table.values())
    for run in coverage.values():
        support = run.get("state_pension_country_contrast_support", {})
        for year in run["by_year"]:
            for country in COUNTRIES:
                receipt = support.get(year, {}).get(country, {})
                if receipt.get("status") != "available" or not _supported(receipt.get("records", receipt.get("count"))):
                    withheld = True
    if withheld:
        tables = {mode: {year: {country: _withhold(row) for country, row in table.items()}
                         for year, table in years.items()} for mode, years in tables.items()}
    return tables, withheld


def read_country_benchmarks(path):
    """Only an explicitly verified published aggregate source may supply values."""
    if path is None:
        return None, {}
    data = json.loads(Path(path).read_text())
    source = data["source"]
    if source.get("verified") is not True or not str(source.get("url", "")).startswith("https://"):
        raise ValueError("country benchmarks must name an explicitly verified published HTTPS source")
    rows = {(int(row["year"]), row["country"]): row for row in data["rows"]}
    if len(rows) != len(data["rows"]) or any(country not in COUNTRIES for _, country in rows):
        raise ValueError("duplicate or unrecognised country benchmark rows")
    return {**source, "file_sha256": digest(path)}, rows


def coverage_tables(coverage, dwp, benchmark_source=None, country_benchmarks=None):
    country_benchmarks = country_benchmarks or {}
    tables, withheld = linked_country_tables(coverage)
    rows = []
    country_metrics = ("recipients_m", "basic_state_pension_bn", "new_state_pension_bn", "state_pension_bn")
    for mode, years in tables.items():
        for year, table in years.items():
            for country in COUNTRIES:
                cell = table[country]
                benchmark = country_benchmarks.get((int(year), country), {})
                for metric in country_metrics:
                    target = benchmark.get(metric)
                    model = cell.get(metric)
                    rows.append({"treatment": mode, "year": int(year), "country": country, "metric": metric,
                                 "model": model, "model_status": cell["status"], "dwp": target,
                                 "difference": None if model is None or target is None else model - target,
                                 "benchmark_status": "available" if target is not None else "unavailable",
                                 "benchmark_reason": None if target is not None else
                                 "The committed spring 2026 workbook has no country forecast split; "
                                 "no verified published country benchmark supplied for this cell."})
    gb_rows = []
    for mode, run in coverage.items():
        for year, table in run["by_year"].items():
            target = dwp["years"].get(int(year))
            # Pension type/age cells enforce the component-level support rule.
            # Withhold the linked GB comparisons too when country tables fail,
            # so a suppressed country's complement cannot be reconstructed.
            for metric, model in (("state_pension_bn", table["gb"]["state_pension_bn"]),
                                  ("recipients_m", table["gb"]["state_pension_recipients"] / 1e6)):
                benchmark = target["GB"][metric] if target else None
                gb_rows.append({"treatment": mode, "year": int(year), "metric": metric,
                                "model_GB": None if withheld else model, "dwp_GB": benchmark,
                                "model_status": "withheld_family" if withheld else "available",
                                "benchmark_status": "available" if benchmark is not None else "unavailable",
                                "difference": None if withheld or benchmark is None else model - benchmark})
    receipts = []
    for mode, run in coverage.items():
        for year, table in run["by_year"].items():
            for geography in GEOGRAPHIES:
                for programme, count in table[geography].get("programme_support_records", {}).items():
                    receipts.append({"treatment": mode, "year": int(year), "geography": geography.upper(),
                                     "programme": programme, "status": "available" if _supported(count) else "suppressed",
                                     "contributing_records": count if _supported(count) else None})
    return {"country_cells": tables, "country_comparisons": rows, "gb_dwp_comparisons": gb_rows,
            "programme_support_receipts": receipts, "country_family_withheld": withheld,
            "country_benchmark_source": benchmark_source,
            "dwp": {key: value for key, value in dwp.items() if key != "years"},
            "geography_note": "GB totals exclude overseas State Pension. Basic/new GB benchmarks remain "
                              "unavailable because the workbook separates overseas only for their combined total."}


def historical_comparison(path):
    """Copy the repository's support-bound D table without changing its numbers."""
    evidence = json.loads(Path(path).read_text())
    provenance = evidence.get("provenance", {})
    audit = provenance.get("support_audit", {})
    if (provenance.get("calculation_head") != "498d970123adff4e8f05908e17c7b366ba71a28c"
            or provenance.get("policyengine_uk") != "2.120.0"
            or provenance.get("dataset") != PRIMARY
            or audit.get("status") != "passed"
            or audit.get("minimum_contributing_records") != MIN_RECORDS
            or not audit.get("receipts")):
        raise ValueError("historical D comparison requires the complete support-bound repository evidence")
    workspace = Path.cwd().resolve()
    for receipt in audit["receipts"]:
        receipt_path = (workspace / receipt["receipt"]).resolve()
        if not receipt_path.is_relative_to(workspace) or digest(receipt_path) != receipt["sha256"]:
            raise ValueError("historical D support receipt is outside the workspace or has changed")
        support = json.loads(receipt_path.read_text())
        if support.get("status") != "passed" or support.get("complete") is not True:
            raise ValueError("historical D fiscal support receipt is incomplete")
    return {"calculation_head": provenance["calculation_head"],
            "policyengine_uk": provenance["policyengine_uk"], "dataset": provenance["dataset"],
            "source_sha256": digest(path), "support_audit": deepcopy(audit), "rows": evidence["rows"],
            "interpretation": "retained historical part D full-run aggregates; not recalculated or scaled"}


def public_fixed_inputs(run):
    """Select aggregate checks and use an unambiguous public weight descriptor."""
    result = {key: deepcopy(run["fixed_inputs"].get(key)) for key in
              ("population", "ageing", "state_pension_accounting", "retyped_level")}
    population = result.get("population")
    if isinstance(population, dict) and "weights" in population:
        population["weight_treatment"] = population.pop("weights")
    # BASIC, NEW and NONE partition the model's complete person population.
    # Publish their aggregate sum, never individual survey weights.
    result["model_population_people_by_year"] = {
        year: sum(float(count) for count in counts.values())
        for year, counts in run["fixed_inputs"].get("held_pension_type_people", {}).items()}
    return result


def replacement_coverage(path, provenance):
    """Use a complete fresh coverage receipt without relabelling fiscal runs."""
    data = json.loads(Path(path).read_text())
    current = data.get("provenance", {})
    if data.get("complete") is not True or not re.fullmatch(r"[0-9a-f]{40}", current.get("calculation_head", "")):
        raise ValueError("replacement coverage requires six complete runs and their actual calculation head")
    for field in ("specs_sha256", "dataset", "dataset_sha256", "packages", "data_built_with"):
        if current.get(field) != provenance.get(field):
            raise ValueError(f"replacement coverage differs from fiscal inputs: {field}")
    if (current.get("minimum_contributing_records") != MIN_RECORDS
            or set(current.get("coverage_years", [])) != set(COVERAGE_YEARS)
            or set(current.get("treatments", [])) != set(TREATMENTS)
            or not re.fullmatch(r"[0-9a-f]{64}", current.get("source_sha256", ""))):
        raise ValueError("replacement coverage source or treatment/year design is incomplete")
    expected = {(mode, year, country) for mode in TREATMENTS for year in COVERAGE_YEARS for country in COUNTRIES}
    receipts = data.get("country_contrast_support_receipts", [])
    keys = [(row.get("treatment"), row.get("year"), row.get("country")) for row in receipts]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError("replacement coverage must carry every unique country contrast support receipt")
    for row in receipts:
        count, status = row.get("contributing_records"), row.get("status")
        if not ((status == "available" and type(count) is int and _supported(count))
                or (status == "suppressed" and count is None)):
            raise ValueError("replacement country support violates the ten-record disclosure rule")
    coverage = data["coverage"]
    comparisons = coverage.get("country_comparisons", [])
    metrics = ("recipients_m", "basic_state_pension_bn", "new_state_pension_bn", "state_pension_bn")
    comparison_keys = [(row.get("treatment"), row.get("year"), row.get("country"), row.get("metric"))
                       for row in comparisons]
    expected_comparisons = {(*key, metric) for key in expected for metric in metrics}
    gb_keys = [(row.get("treatment"), row.get("year"), row.get("metric"))
               for row in coverage.get("gb_dwp_comparisons", [])]
    expected_gb = {(mode, year, metric) for mode in TREATMENTS for year in COVERAGE_YEARS
                   for metric in ("recipients_m", "state_pension_bn")}
    if (len(comparison_keys) != len(expected_comparisons) or set(comparison_keys) != expected_comparisons
            or len(gb_keys) != len(expected_gb) or set(gb_keys) != expected_gb):
        raise ValueError("replacement coverage comparison tables have missing or duplicate cells")
    if any(row["status"] == "suppressed" for row in receipts):
        if (coverage.get("country_family_withheld") is not True
                or any(row.get("model_status") != "withheld_family" or row.get("model") is not None
                       or row.get("difference") is not None for row in comparisons)
                or any(row.get("model_status") != "withheld_family" or row.get("model_GB") is not None
                       or row.get("difference") is not None for row in coverage["gb_dwp_comparisons"])):
            raise ValueError("replacement coverage exposes a suppressed country through linked cells")
    return deepcopy(coverage), {**deepcopy(current), "receipt_sha256": digest(path),
                                "country_contrast_support_receipts": deepcopy(receipts),
                                "scope": "fresh coverage replaces coverage only; fiscal calculation provenance is unchanged"}


def main(args):
    workspace, source = Path.cwd().resolve(), args.source.resolve()
    if not source.is_relative_to(workspace) or not args.out.resolve().is_relative_to(workspace):
        raise ValueError("frozen source, its cache and public output must stay in the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_head):
        raise ValueError("--source-head must be the full exported commit SHA")
    sys.path.insert(0, str(source / "src"))
    os.environ["PYTHONPATH"] = str(source / "src")
    modules = {name: importlib.import_module(f"triple_lock.{name}")
               for name in ("engine", "jobs", "expected_value", "pipeline", "ageing_validation", "datasets")}
    if any(not Path(module.__file__).resolve().is_relative_to(source) for module in modules.values()):
        raise ValueError("a triple_lock module was imported outside the frozen source export")
    engine, jobs, estimator = (modules[name] for name in ("engine", "jobs", "expected_value"))
    specs = engine._keys_to_int(json.loads(args.specs.read_text()))
    committed = json.loads((source / "data" / "results.json").read_text())
    design = plan(specs, committed["expected_value"]["draws"])
    provenance = {"status": "pilot on an uncertified data/model pair; not for quoting", "certified": False,
                  "quote_eligible": False, "calculation_head": args.source_head,
                  "specs_sha256": digest(args.specs), "dataset": PRIMARY,
                  "dataset_sha256": modules["datasets"].DATASETS[PRIMARY]["sha256"],
                  "data_built_with": modules["datasets"].DATASETS[PRIMARY]["built_with"],
                  "packages": engine.package_versions(), "engine_semantics": engine.engine_semantics(),
                  "aggregation_source_sha256": {"driver": digest(__file__),
                                                "expected_value": digest(estimator.__file__)},
                  "minimum_contributing_records": MIN_RECORDS,
                  "record_redaction": "triple_lock.pipeline.redact_records; aggregate selection only",
                  "draws": {key: committed["expected_value"]["draws"][key] for key in ("n", "seed", "shocks")},
                  "paired_macro_draws": {"indices_by_stratum": design["sample"],
                                         "probability_by_stratum": design["probabilities"],
                                         "identical_rates_probability": design["identical_rates_probability"]},
                  "source_export": str(source.relative_to(workspace)),
                  "job_counts": {"path": 246, "coverage": 6, "total": 252},
                  "execution_job_counts": {"treatment_paths": 41, "coverage": 6, "total": 47},
                  "maximum_enhanced_frs_workers": args.workers}
    if args.plan:
        result = {"provenance": provenance, "status": "planned; no PolicyEngine runs started",
                  "labels": design["labels"]}
    else:
        if (provenance["packages"]["policyengine-uk"] != "2.120.0"
                or provenance["packages"]["policyengine-core"] != "3.32.16"):
            raise ValueError("this pilot requires policyengine-uk 2.120.0 and policyengine-core 3.32.16")
        cache = source / ".cache" / "jobs-pilot-e"
        grouped, coverage = execute_design(design, jobs.run_jobs, workers=args.workers, cache=cache)
        benchmark_source, country_benchmarks = read_country_benchmarks(args.country_benchmarks)
        result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "provenance": provenance, "fiscal": fiscal_tables(design, grouped, estimator),
                  "coverage": coverage_tables(coverage, modules["ageing_validation"].dwp_forecasts(),
                                              benchmark_source, country_benchmarks),
                  "historical_part_d": historical_comparison(args.historical),
                  "fixed_inputs": {treatment: public_fixed_inputs(run)
                                   for treatment, run in grouped["central"].items()},
                  "method": "Each figure comes from full PolicyEngine UK runs of both rules. The central path "
                            "and the original 40 Microcosm-paired macro indices run on Enhanced FRS for every "
                            "treatment. Contrasts are calculated within paths, then estimated using the original "
                            "stratum masses and both Monte Carlo variance components. No output scaling."}
        if args.coverage_results:
            result["coverage"], provenance["coverage_replacement"] = replacement_coverage(
                args.coverage_results, provenance)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    modules["pipeline"].redact_records(result)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote aggregate {'plan' if args.plan else 'pilot'} to {args.out}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="frozen git archive exported inside the workspace")
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
    parser.add_argument("--historical", type=Path, default=Path("data/pilot/integrated.json"))
    parser.add_argument("--country-benchmarks", type=Path)
    parser.add_argument("--coverage-results", type=Path, help="complete fresh six-treatment coverage receipt")
    parser.add_argument("--out", type=Path, default=Path("data/pilot/model_v2_e.json"))
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--plan", action="store_true")
    return parser


if __name__ == "__main__":
    main(build_parser().parse_args())
