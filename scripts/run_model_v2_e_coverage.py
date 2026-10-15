"""Six fresh part E coverage jobs with corrected actual-change support.

No fiscal path runs or output scaling. The frozen source, owner-only cache
and aggregate output stay within the assigned workspace. --plan loads no
survey and starts no PolicyEngine run. Root allocates execution slots.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

PRIMARY = "enhanced_frs_2024_25@1.56.16"
MIN_RECORDS = 10


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes(source):
    python_files = sorted([*(source / "src").rglob("*.py"), *(source / "scripts").rglob("*.py")])
    files = [*python_files,
             source / "pyproject.toml", source / "requirements-lock.txt"]
    if not python_files or any(not path.is_file() for path in files):
        raise ValueError("the frozen source must include Python source and dependency declarations")
    return {str(path.relative_to(source)): digest(path) for path in files}


def shared_driver(path):
    specification = importlib.util.spec_from_file_location("e_coverage_helpers", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def plan(specifications, draw_provenance, helper):
    original = helper.plan(specifications, draw_provenance)
    selected = [(job, label) for job, label in zip(original["execution_jobs"], original["execution_labels"], strict=True)
                if job[0] == "coverage"]
    jobs, labels = zip(*selected, strict=True)
    if len(jobs) != 6 or {mode for _, mode in labels} != set(helper.TREATMENTS):
        raise ValueError("coverage replacement requires all six original E treatments")
    if any(set(arguments["years"]) != set(helper.COVERAGE_YEARS) for _, arguments in jobs):
        raise ValueError("coverage replacement must calculate every original coverage year")
    return {"jobs": list(jobs), "labels": list(labels)}


def execute(design, runner, workers, cache):
    if workers not in (1, 2, 3):
        raise ValueError("coverage permits at most three Enhanced FRS workers")
    outputs = runner(design["jobs"], workers=workers, slot_prefix="pilot-e-coverage-efrs", cache=cache)
    coverage = {mode: output for (_, mode), output in zip(design["labels"], outputs, strict=True)}
    if len(coverage) != 6:
        raise ValueError("every fresh coverage treatment must return exactly once")
    return coverage


def support_receipts(coverage, countries):
    rows = []
    for mode, run in coverage.items():
        support = run["state_pension_country_contrast_support"]
        for year in run["by_year"]:
            if year not in support or any(country not in support[year] for country in countries):
                raise ValueError("every coverage country requires an actual model support receipt")
            for country in countries:
                receipt = support[year][country]
                count = receipt.get("records")
                available = (receipt.get("status") == "available" and type(count) is int
                             and (count == 0 or count >= MIN_RECORDS))
                rows.append({"treatment": mode, "year": int(year), "country": country,
                             "status": "available" if available else "suppressed",
                             "contributing_records": count if available else None})
    return rows


def main(args):
    workspace, source = Path.cwd().resolve(), args.source.resolve()
    if not source.is_relative_to(workspace) or not args.out.resolve().is_relative_to(workspace):
        raise ValueError("frozen source, its cache and output must stay in the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_head):
        raise ValueError("--source-head must be a full exported commit SHA")
    helper_path = source / "scripts" / "run_model_v2_e_pilot.py"
    helper = shared_driver(helper_path)
    specifications = json.loads(args.specs.read_text())
    committed = json.loads((source / "data" / "results.json").read_text())
    design = plan(specifications, committed["expected_value"]["draws"], helper)
    hashes = source_hashes(source)
    provenance = {"status": "pilot on an uncertified data/model pair; not for quoting", "certified": False,
                  "quote_eligible": False, "calculation_head": args.source_head, "dataset": PRIMARY,
                  "specs_sha256": digest(args.specs), "source_export": str(source.relative_to(workspace)),
                  "minimum_contributing_records": MIN_RECORDS,
                  "coverage_years": list(helper.COVERAGE_YEARS), "treatments": list(helper.TREATMENTS),
                  "job_counts": {"path": 0, "coverage": 6, "total": 6},
                  "maximum_enhanced_frs_workers": args.workers,
                  "source_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                  "source_file_sha256": hashes,
                  "aggregation_source_sha256": {"driver": digest(__file__), "coverage_helpers": digest(helper_path)},
                  "record_redaction": "triple_lock.pipeline.redact_records; aggregate selection only",
                  "level_support_definition": "Positive-weight re-typed records whose stored new State Pension "
                                              "flat amount actually changes under the full-new bound; "
                                              "already-full amounts do not contribute."}
    if args.plan:
        result = {"provenance": provenance, "status": "planned; no PolicyEngine runs started", "labels": design["labels"]}
    else:
        sys.path.insert(0, str(source / "src"))
        os.environ["PYTHONPATH"] = str(source / "src")
        modules = {name: importlib.import_module(f"triple_lock.{name}")
                   for name in ("engine", "jobs", "pipeline", "ageing_validation", "datasets")}
        if any(not Path(module.__file__).resolve().is_relative_to(source) for module in modules.values()):
            raise ValueError("a scientific module was imported outside the frozen source")
        engine, jobs = modules["engine"], modules["jobs"]
        packages = engine.package_versions()
        if packages["policyengine-uk"] != "2.120.0" or packages["policyengine-core"] != "3.32.16":
            raise ValueError("coverage requires policyengine-uk 2.120.0 / core 3.32.16")
        provenance.update({"packages": packages, "engine_semantics": engine.engine_semantics(),
                           "dataset_sha256": modules["datasets"].DATASETS[PRIMARY]["sha256"],
                           "data_built_with": modules["datasets"].DATASETS[PRIMARY]["built_with"]})
        specifications = engine._keys_to_int(specifications)
        design = plan(specifications, committed["expected_value"]["draws"], helper)
        coverage = execute(design, jobs.run_jobs, args.workers, source / ".cache" / "jobs-pilot-e-coverage")
        if any(set(run["by_year"]) != set(helper.COVERAGE_YEARS) for run in coverage.values()):
            raise ValueError("every completed coverage treatment must return every requested year")
        benchmark_source, benchmarks = helper.read_country_benchmarks(args.country_benchmarks)
        result = {"complete": True, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provenance": provenance,
                  "coverage": helper.coverage_tables(coverage, modules["ageing_validation"].dwp_forecasts(),
                                                     benchmark_source, benchmarks),
                  "country_contrast_support_receipts": support_receipts(coverage, helper.COUNTRIES)}
        modules["pipeline"].redact_records(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote aggregate coverage {'plan' if args.plan else 'replacement'} to {args.out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
    parser.add_argument("--country-benchmarks", type=Path, default=Path("data/pilot/country_benchmarks.json"))
    parser.add_argument("--out", type=Path, default=Path("data/pilot/model_v2_e_coverage.json"))
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--plan", action="store_true")
    main(parser.parse_args())
