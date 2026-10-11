"""Pre-Budget certified-bundle bridge; full runs and aggregate-only receipts.

The pilot's forty paired Enhanced FRS figures are reused exactly from E.
An intermediate model/core/port step holds data at 1.56.16. This separates
the data step on the central path and coverage; paired attribution is combined.
Every job still calculates the complete thirteen-year horizon.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import threading
import os

from triple_lock import datasets, dwp, engine, expected_value, jobs, pipeline

PILOT = "enhanced_frs_2024_25@1.56.16"
CERTIFIED = "enhanced_frs_2024_25@1.58.0"
YEARS = (2034, 2039)
COVERAGE_YEARS = (*range(2024, 2031), *YEARS)
METRICS = {
    "state_pension_bn": ("state_pension", "state_pension_in_gb", 1),
    "state_pension_recipients": ("state_pension", "state_pension_caseload_in_gb", 1e6),
    "pension_credit_bn": ("pension_credit", "pension_credit", 1),
    "pension_credit_benefit_units": ("pension_credit", "pension_credit_caseload", 1e6),
    "housing_benefit_bn": ("housing_benefit", "housing_benefit", 1),
    "housing_benefit_pension_age_bn": ("housing_benefit_pension_age", "housing_benefit_pension_age", 1),
    "council_tax_reduction_bn": ("council_tax_reduction", None, 1),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def supported(count):
    return type(count) is int and (count == 0 or count >= 10)


def linked_support(uk, gb):
    return supported(uk) and supported(gb) and uk >= gb and supported(uk - gb)


def design(specs, dataset, central_only=False):
    paired = {int(i): row for i, row in specs["paired"].items()}
    sample = {}
    for i, row in paired.items():
        if type(row["times_drawn"]) is not int or row["times_drawn"] < 1:
            raise ValueError("paired multiplicities must be positive integers")
        sample.setdefault(int(row["stratum"]), []).extend([i] * row["times_drawn"])
    weights = {int(k): float(v) for k, v in specs["paired_strata_probability"].items()}
    if len(paired) != 40 or sum(map(len, sample.values())) != 40 or min(map(len, sample.values())) < 2:
        raise ValueError("bridge requires the original forty distinct paired indices")
    if set(weights) != set(sample) or abs(sum(weights.values()) + specs["identical_rates_probability"] - 1) > 1e-10:
        raise ValueError("paired probabilities do not match the frozen pilot design")
    paths = {"central": specs["central"]}
    if not central_only:
        paths.update({f"draw_{i}": row["spec"] for i, row in sorted(paired.items())})
    planned = [(name, ("path", {**deepcopy(spec), "dataset": dataset, "demography": "both",
                                "retyped_level": "kept", "fiscal_output_years": list(YEARS)}))
               for name, spec in paths.items()]
    planned.append(("coverage", ("coverage", {"years": list(COVERAGE_YEARS), "dataset": dataset,
                                               "spec": specs["central"], "demography": "both",
                                               "september_cpi_history": specs["september_cpi_history"]})))
    return planned, sample, weights


def saving_tables(runs, sample, weights, n_draws=50000):
    """Close the UK/GB/year/path family if its policy support is insufficient."""
    output = {"central": [], "paired": []}
    for measure in ("gross", "net"):
        available = all(linked_support(
            run["saving_support_records_by_year"][year]["uk"][measure],
            run["saving_support_records_by_year"][year]["gb"][measure])
            for run in runs.values() for year in YEARS)
        for geography in ("UK", "GB"):
            for year in YEARS:
                def value(name):
                    row = runs[name]["saving_bn"][year]
                    return row[measure] if geography == "UK" else row["gb"][measure]
                meta = {"geography": geography, "year": year, "measure": measure,
                        "status": "available" if available else "withheld_family"}
                output["central"].append({**meta, "value_bn": value("central") if available else None, "se": None})
                if all(f"draw_{i}" in runs for idx in sample.values() for i in idx):
                    estimate = expected_value.stratified_estimate(
                        {k: [value(f"draw_{i}") for i in idx] for k, idx in sample.items()}, weights, n_draws)
                    output["paired"].append({**meta, "estimate_bn": estimate if available else None})
    return output


def coverage_tables(run):
    targets = dwp.coverage_targets_by_year(years=list(range(2024, 2031)))
    rows = []
    for metric, (programme, target, scale) in METRICS.items():
        available = all(linked_support(table["uk"]["programme_support_records"].get(programme),
                                       table["gb"]["programme_support_records"].get(programme))
                        for table in run["by_year"].values())
        for year, table in run["by_year"].items():
            benchmark = targets[year]["values"][target] if target and year in targets else None
            rows.append({"year": year, "metric": metric, "unit": "people or benefit units" if scale == 1e6 else "£bn",
                         "status": "available" if available else "withheld_family",
                         "UK": table["uk"][metric] if available else None,
                         "GB": table["gb"][metric] if available else None,
                         "DWP_GB": None if benchmark is None else benchmark * scale,
                         "GB_over_DWP": table["gb"][metric] / (benchmark * scale)
                         if available and benchmark else None,
                         "support_UK": table["uk"]["programme_support_records"].get(programme) if available else None,
                         "support_GB": table["gb"]["programme_support_records"].get(programme) if available else None})
    return {"rows": rows, "source": dwp.TABLES_PAGE, "source_sha256": digest(dwp.TABLES),
            "geography": "GB excludes Northern Ireland; published overseas State Pension is subtracted. "
                         "No DWP forecast is extended beyond 2030–31. CTR comparator unavailable."}


def memory_check():
    import psutil
    import os
    memory = psutil.virtual_memory().available / 2**30
    load = os.getloadavg()[0]
    if memory < 40 or load > 2 * (os.cpu_count() or 1):
        raise RuntimeError(f"Host saturated: {memory:.1f} GiB available; load {load:.1f}; bridge stops before new jobs")
    return {"available_gib": memory, "load_1m": load}


def main(args):
    destination = args.out.resolve()
    workspace = Path.cwd().resolve()
    if (destination.name == "results.json" or not destination.is_relative_to(workspace)
            or not any(destination.is_relative_to(workspace / name) for name in ("data/pilot", ".cache"))):
        raise ValueError("bridge receipts belong under data/pilot or .cache in the assigned workspace")
    if args.workers not in (1, 2, 3):
        raise ValueError("at most three Enhanced FRS workers")
    if engine.package_versions()["policyengine-uk"] != "2.125.1":
        raise ValueError("certified bridge requires policyengine-uk 2.125.1")
    specs_path = Path("data/pilot/d_macro_specs.json")
    specs = engine._keys_to_int(json.loads(specs_path.read_text()))
    dataset = PILOT if args.pair == "model-step" else CERTIFIED
    planned, sample, weights = design(specs, dataset, args.pair == "model-step")
    preflight = pipeline.housing_benefit_passport_preflight()
    runs, timings = {}, []
    cache = Path(".cache/J-bridge-jobs")
    public = {
        "run_kind": "pre_budget_bridge", "quote_eligible": False, "minimum_contributing_records": 10,
        "label": "pre-Budget certified-bundle bridge; not for quoting",
        "provenance": {"calculation": pipeline.git_state(), "engine_hashes": engine.engine_hashes(),
                       "packages": engine.package_versions(), "dataset": datasets.provenance(dataset),
                       "numeric_threads": {k: os.environ.get(k) for k in
                                           ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
                       "specs_sha256": digest(specs_path), "preflight": preflight},
        "paired_macro_design": {"indices_by_stratum": sample, "probabilities_by_stratum": weights,
                                "n_first_phase": 50000, "seed": 20260929,
                                "zero_probability": specs["identical_rates_probability"]},
        "attribution": "Intermediate model/core/engine-port step holds data at 1.56.16; data step holds the "
                       "new model/core/port fixed. Intermediate paired runs are absent; paired attribution "
                       "is combined. No isolated model, core or port causal decomposition is claimed.",
    }
    pilot = json.loads(Path("data/pilot/model_v2_e.json").read_text())
    public["retained_pilot"] = {
        "source": "data/pilot/model_v2_e.json", "sha256": digest("data/pilot/model_v2_e.json"),
        "policyengine_uk": "2.120.0", "policyengine_core": "3.32.16", "dataset": PILOT,
        "certified": False, "fiscal": {kind: [r for r in pilot["fiscal"][kind]
                                                if r["treatment_or_contrast"] == "both"]
                                       for kind in ("central", "paired")},
        "note": "Exact committed forty-paired-index full both/kept configuration; figures copied unchanged. "
                "The old entitlement Housing Benefit passport is retained, with its pilot limitation.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(planned), args.workers):
        batch = planned[offset:offset + args.workers]
        memory = memory_check()
        cold = [not engine.cached(kind, arg, cache=cache) for _, (kind, arg) in batch]
        started = time.monotonic()
        finished = threading.Event()

        def monitor():
            while not finished.wait(5):
                try:
                    memory_check()
                except RuntimeError:
                    jobs.kill_children()
                    return

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            output = jobs.run_jobs([job for _, job in batch], workers=args.workers,
                                   slot_prefix="J-bridge-efrs", cache=cache)
        finally:
            finished.set()
        elapsed = time.monotonic() - started
        timings.append({"labels": [name for name, _ in batch], "kinds": [job[0] for _, job in batch],
                        "cold": cold, "wall_seconds": elapsed, "host_before": memory})
        for (name, _), run in zip(batch, output, strict=True):
            runs[name] = run
        public.update({"complete": len(runs) == len(planned), "completed_labels": list(runs),
                       "generated_at": datetime.now(timezone.utc).isoformat(), "timings": timings})
        if "central" in runs:
            public["fiscal"] = saving_tables({k: v for k, v in runs.items() if k != "coverage"}, sample, weights)
        if "coverage" in runs:
            public["coverage"] = coverage_tables(runs["coverage"])
        # A partial sample has no paired estimate: wait for all forty paths.
        if len(runs) < len(planned) - 1:
            public["fiscal"]["paired"] = []
        pipeline.redact_records(public)
        args.out.write_text(json.dumps(public, indent=2, allow_nan=False) + "\n")
        print(f"Bridge checkpoint: {len(runs)}/{len(planned)} labels in {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", choices=("model-step", "certified"), required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
