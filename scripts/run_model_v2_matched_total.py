"""Full-run matched-total supplement: 41 three-treatment Enhanced FRS batches.

Every treatment calculates all thirteen years before selecting 2034/2039.
No record-level contribution array or diagnostic enters this output. The
old ONS-total control is preserved in the separate six-treatment E pilot.
--plan starts no PolicyEngine run. Root allocates actual run slots separately.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys

PRIMARY = "enhanced_frs_2024_25@1.56.16"
TREATMENTS = {mode: (mode, "kept") for mode in ("frozen", "reweight", "total_matched")}
CONTRASTS = {
    "matched_population_total_effect": {"total_matched": 1, "frozen": -1},
    "matched_age_structure_effect": {"reweight": 1, "total_matched": -1},
}
YEARS = (2034, 2039)
MIN_RECORDS = 10


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shared_driver(path, *, matched=False):
    """A private module copy; never alter the running original E driver."""
    spec = importlib.util.spec_from_file_location("matched_total_fiscal_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if matched:
        module.TREATMENTS = dict(TREATMENTS)
        module.CONTRASTS = deepcopy(CONTRASTS)
    return module


def plan(specifications, draw_provenance, original_driver):
    original = original_driver.plan(specifications, draw_provenance)
    batches, labels = [], []
    for (name, _), (kind, arguments) in zip(original["execution_labels"], original["execution_jobs"], strict=True):
        if kind != "treatment_paths":
            continue
        specifications = {mode: {**deepcopy(arguments["specs"]["frozen"]), "demography": mode}
                          for mode in TREATMENTS}
        batches.append(("treatment_paths", {"specs": specifications, "contrasts": deepcopy(CONTRASTS)}))
        labels.append(name)
    if len(batches) != 41:
        raise ValueError("the matched-total supplement requires the original central plus forty paired paths")
    return {"execution_jobs": batches, "labels": labels,
            **{key: original[key] for key in ("sample", "probabilities", "identical_rates_probability", "draw_provenance")},
            "reference_execution_jobs": original["execution_jobs"],
            "reference_execution_labels": original["execution_labels"]}


def execute(design, runner, workers, cache):
    if workers not in (1, 2):
        raise ValueError("matched-total batches allow at most two Enhanced FRS workers")
    outputs = runner(design["execution_jobs"], workers=workers, slot_prefix="matched-total-efrs", cache=cache)
    grouped = dict(zip(design["labels"], outputs, strict=True))
    if len(grouped) != 41 or any(set(result) != set(TREATMENTS) for result in grouped.values()):
        raise ValueError("every matched-total batch must return all three treatment aggregates")
    return grouped


def population_receipts(grouped, relative_tolerance=1e-6):
    """Verify model-read totals against the exact shared target; aggregates only."""
    rows = []
    for label, runs in grouped.items():
        matched, reweight = runs["total_matched"]["fixed_inputs"], runs["reweight"]["fixed_inputs"]
        if not matched["ageing"]["weights_unchanged_through_anchor"]:
            raise ValueError("matched-total control changed the native anchor weights")
        targets = matched["ageing"]["target_population_people_by_year"]
        for year, target in targets.items():
            counts = matched["held_pension_type_records"][year]
            other_counts = reweight["held_pension_type_records"][year]
            if min(sum(counts.values()), sum(other_counts.values())) < MIN_RECORDS:
                raise ValueError("population receipt fails the ten-record minimum")
            totals = {"total_matched": sum(matched["held_pension_type_people"][year].values()),
                      "reweight": sum(reweight["held_pension_type_people"][year].values())}
            if not math.isfinite(target) or target <= 0 or any(not math.isfinite(value) for value in totals.values()):
                raise ValueError("population receipt contains a nonfinite or nonpositive total")
            if any(abs(value / target - 1) > relative_tolerance for value in totals.values()):
                raise ValueError("model population misses the shared matched-total target")
            if abs(totals["total_matched"] - totals["reweight"]) > 2 * relative_tolerance * target:
                raise ValueError("matched-total and reweight model populations differ beyond readback tolerance")
            if int(year) in YEARS:
                rows.append({"path": label, "year": int(year), "target_people": target,
                             "model_people": totals, "status": "available", "matched_within_tolerance": True})
    return {"status": "passed", "target_definition": "exact float64 sum of reweight's anchored age/sex targets",
            "target_relative_tolerance": relative_tolerance,
            "between_treatment_relative_tolerance": 2 * relative_tolerance, "rows": rows}


def check_reference(design, grouped, reference, cache, engine):
    """Compare fresh aggregate outputs to old cached outputs in memory only."""
    rows = []
    provenance = reference["provenance"]
    for (label, _), (kind, argument) in zip(design["reference_execution_labels"], design["reference_execution_jobs"], strict=True):
        if kind != "treatment_paths":
            continue
        old = engine.cached(kind, argument, engine=provenance["engine_semantics"],
                            packages=provenance["packages"], cache=cache)
        if old is None:
            raise ValueError("a reference E batch is missing; no reference job is run by this supplement")
        for mode in ("frozen", "reweight"):
            current, previous = grouped[label][mode], old[mode]
            for field in ("saving_bn", "totals_bn", "rates", "statutory"):
                if current[field] != previous[field]:
                    raise ValueError("fresh frozen/reweight aggregates differ from the existing E run")
            rows.append({"path": label, "treatment": mode, "exact_aggregate_match": True})
    if len(rows) != 82:
        raise ValueError("reference proof must cover forty-one paths under both unchanged treatments")
    return {"status": "passed", "passed": True, "reference_calculation_head": provenance["calculation_head"],
            "reference_engine_semantics": provenance["engine_semantics"],
            "matched_runs": len(rows), "fields": ["saving_bn", "totals_bn", "rates", "statutory"],
            "comparison": "exact equality of independently calculated aggregate results; no reused fiscal output",
            "rows": rows}


def main(args):
    workspace, source = Path.cwd().resolve(), args.source.resolve()
    if (not source.is_relative_to(workspace) or not args.out.resolve().is_relative_to(workspace)
            or (args.reference_cache is not None and not args.reference_cache.resolve().is_relative_to(workspace))):
        raise ValueError("frozen source, caches and public output must stay in the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_head):
        raise ValueError("--source-head must be a full exported commit SHA")
    if (args.reference_results is None) != (args.reference_cache is None):
        raise ValueError("reference results and reference cache must be supplied together")
    helper_path = source / "scripts" / "run_model_v2_e_pilot.py"
    original, matched = shared_driver(helper_path), shared_driver(helper_path, matched=True)
    specifications = json.loads(args.specs.read_text())
    specifications = {**specifications, "paired": {int(i): row for i, row in specifications["paired"].items()},
                      "paired_strata_probability": {int(i): p for i, p in specifications["paired_strata_probability"].items()}}
    committed = json.loads((source / "data" / "results.json").read_text())
    draw_provenance = {key: committed["expected_value"]["draws"][key] for key in ("n", "seed", "shocks")}
    design = plan(specifications, draw_provenance, original)
    provenance = {"status": "pilot on an uncertified data/model pair; not for quoting", "certified": False,
                  "quote_eligible": False, "calculation_head": args.source_head, "dataset": PRIMARY,
                  "specs_sha256": digest(args.specs), "draws": draw_provenance,
                  "paired_macro_draws": {"indices_by_stratum": design["sample"],
                                         "probability_by_stratum": design["probabilities"],
                                         "identical_rates_probability": design["identical_rates_probability"]},
                  "calculated_fiscal_years": list(range(2027, 2040)), "published_fiscal_years": list(YEARS),
                  "minimum_contributing_records": MIN_RECORDS, "record_redaction": "triple_lock.pipeline.redact_records; aggregate selection only",
                  "source_export": str(source.relative_to(workspace)),
                  "aggregation_source_sha256": {"driver": digest(__file__), "fiscal_helpers": digest(helper_path)},
                  "job_counts": {"path": 123, "coverage": 0, "total": 123},
                  "execution_job_counts": {"treatment_paths": 41, "coverage": 0, "total": 41},
                  "maximum_enhanced_frs_workers": args.workers}
    if args.plan:
        result = {"provenance": provenance, "status": "planned; no PolicyEngine runs started", "labels": design["labels"]}
    else:
        sys.path.insert(0, str(source / "src"))
        os.environ["PYTHONPATH"] = str(source / "src")
        modules = {name: importlib.import_module(f"triple_lock.{name}")
                   for name in ("engine", "jobs", "expected_value", "pipeline", "datasets")}
        if any(not Path(module.__file__).resolve().is_relative_to(source) for module in modules.values()):
            raise ValueError("a scientific module was imported outside the frozen source")
        engine, jobs, estimator = (modules[name] for name in ("engine", "jobs", "expected_value"))
        packages = engine.package_versions()
        if packages["policyengine-uk"] != "2.120.0" or packages["policyengine-core"] != "3.32.16":
            raise ValueError("the matched-total pilot requires policyengine-uk 2.120.0 / core 3.32.16")
        provenance.update({"packages": packages, "engine_semantics": engine.engine_semantics(),
                           "dataset_sha256": modules["datasets"].DATASETS[PRIMARY]["sha256"],
                           "data_built_with": modules["datasets"].DATASETS[PRIMARY]["built_with"]})
        provenance["aggregation_source_sha256"]["expected_value"] = digest(estimator.__file__)
        specifications = engine._keys_to_int(specifications)
        design = plan(specifications, draw_provenance, original)
        reference = None if args.reference_results is None else json.loads(args.reference_results.read_text())
        if reference is not None:
            previous = reference["provenance"]
            if (not re.fullmatch(r"[0-9a-f]{40}", previous["calculation_head"])
                    or previous["dataset"] != PRIMARY or previous["dataset_sha256"] != provenance["dataset_sha256"]
                    or previous["specs_sha256"] != provenance["specs_sha256"] or previous["draws"] != draw_provenance):
                raise ValueError("reference and supplement must share verified data, macro specs and paired draws")
        grouped = execute(design, jobs.run_jobs, args.workers, source / ".cache" / "jobs-matched-total")
        proof = ({"status": "pending", "passed": False, "reference_calculation_head": None, "matched_runs": 0,
                  "reason": "reference E results/cache not supplied; merging is blocked"}
                 if reference is None else check_reference(design, grouped, reference, args.reference_cache, engine))
        proof["calculation_head"] = args.source_head
        result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "provenance": provenance, "fiscal": matched.fiscal_tables(design, grouped, estimator),
                  "reference_equivalence": proof, "population_validation": population_receipts(grouped),
                  "fixed_inputs": {mode: matched.public_fixed_inputs(run) for mode, run in grouped["central"].items()},
                  "method": "Full independent PolicyEngine UK runs for frozen/reweight/total_matched on the central "
                            "path and original forty paired indices. Each run calculates all thirteen fiscal years "
                            "in the original order. Only publication selects 2034/2039. The one-margin control uses "
                            "the exact sum of anchored age/sex targets; paired contrasts use the original design "
                            "and both Monte Carlo variance components. No output scaling or fiscal reuse."}
        modules["pipeline"].redact_records(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote aggregate matched-total {'plan' if args.plan else 'supplement'} to {args.out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
    parser.add_argument("--reference-results", type=Path)
    parser.add_argument("--reference-cache", type=Path)
    parser.add_argument("--out", type=Path, default=Path("data/pilot/model_v2_matched_total.json"))
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--plan", action="store_true")
    main(parser.parse_args())
