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
import tempfile

from triple_lock import datasets, dwp, engine, expected_value, jobs, pipeline
from triple_lock.historical_publication import PROOF, verify_historical_publication_redaction

PILOT = "enhanced_frs_2024_25@1.56.16"
CERTIFIED = "enhanced_frs_2024_25@1.58.0"
YEARS = (2034, 2039)
COVERAGE_YEARS = (*range(2024, 2031), *YEARS)
REVIEWED_RECIPE_SHA256 = "35a6c7e7e3ed46942e2187c8460147b14fabb6deafadfc6a30a06b7ddc12b061"
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
    available = all(linked_support(
        run["saving_support_records_by_year"][year]["uk"].get(measure),
        run["saving_support_records_by_year"][year]["gb"].get(measure))
        for run in runs.values() for year in YEARS for measure in ("gross", "net", "offset"))
    for measure in ("gross", "net"):
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


def hb_family_supported(tables):
    """Close total/older HB and their working-age and geographic complements."""
    for table in tables:
        uk = table["uk"]["programme_support_records"]
        gb = table["gb"]["programme_support_records"]
        for name in ("housing_benefit", "housing_benefit_pension_age"):
            if not linked_support(uk.get(name), gb.get(name)):
                return False
        working_uk = uk["housing_benefit"] - uk["housing_benefit_pension_age"]
        working_gb = gb["housing_benefit"] - gb["housing_benefit_pension_age"]
        if not linked_support(working_uk, working_gb):
            return False
    return True


def coverage_tables(run):
    targets = dwp.coverage_targets_by_year(years=list(range(2024, 2031)))
    rows = []
    for metric, (programme, target, scale) in METRICS.items():
        available = all(linked_support(table["uk"]["programme_support_records"].get(programme),
                                       table["gb"]["programme_support_records"].get(programme))
                        for table in run["by_year"].values())
        if programme in ("housing_benefit", "housing_benefit_pension_age"):
            available = available and hb_family_supported(run["by_year"].values())
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


def run_batch(batch, workers, cache, monitor_interval=5):
    """Share saturation cancellation with slot waits and child admission."""
    stop, finished, saturated = threading.Event(), threading.Event(), threading.Event()

    def check_host():
        try:
            return memory_check()
        except RuntimeError:
            saturated.set()
            jobs.kill_children(stop)
            raise

    def admission(kind, arg, workdir, scheduler_stop):
        # This runs inside the acquired slot: an earlier host snapshot may be
        # stale after waiting for another build to release the directory.
        check_host()

    def monitor():
        while not finished.wait(monitor_interval):
            try:
                check_host()
            except RuntimeError:
                return

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        output = jobs.run_jobs([job for _, job in batch], workers=workers,
                               slot_prefix="J-bridge-efrs", cache=cache,
                               stop=stop, admission=admission)
    except RuntimeError:
        if saturated.is_set():
            raise RuntimeError("bridge stopped because host saturation was observed during this batch") from None
        raise
    finally:
        finished.set()
        watcher.join()
    if saturated.is_set():
        raise RuntimeError("bridge stopped because host saturation was observed during this batch")
    return output


def read_snapshot_bytes(path, snapshot):
    """Read once and bind the actual parser input to the initial snapshot."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != snapshot["bridge_files"][str(path)]:
        raise engine.SourceChanged(f"bridge input {path} differs from its initial execution snapshot")
    return raw


def verify_pilot_recipe(specs_bytes, pilot, sample, weights, binding):
    """Validate the exact frozen recipe bytes used to derive the job plan."""
    old_digest = pilot["provenance"]["specs_sha256"]
    current_digest = hashlib.sha256(specs_bytes).hexdigest()
    if current_digest != old_digest:
        redaction = binding.get("input_redactions", {}).get("data/pilot/d_macro_specs.json", {})
        if (redaction.get("original_specs_sha256") != old_digest
                or redaction.get("sanitized_specs_sha256") != current_digest
                or redaction.get("runnable_recipe_sha256") != REVIEWED_RECIPE_SHA256
                or hashlib.sha256(engine._canonical(json.loads(specs_bytes)).encode()).hexdigest()
                   != REVIEWED_RECIPE_SHA256):
            raise ValueError("bridge recipe differs from the original pilot configuration")
    recorded = engine._keys_to_int(pilot["provenance"]["paired_macro_draws"])
    if (sample != recorded["indices_by_stratum"] or weights != recorded["probability_by_stratum"]):
        raise ValueError("bridge paired draw indices, strata or probabilities differ from the pilot")


def execution_snapshot():
    """Freeze scientific sources, estimator/driver, inputs and installed packages.

    Output writes can change the dirty flag, so source identity uses hashes and
    the revision rather than requiring the build's own output to stay clean.
    """
    paths = [Path(__file__), Path("scripts/run_model_v2_j_rehearsal.py"),
             Path("pyproject.toml"), Path("requirements-lock.txt"),
             Path("data/pilot/d_macro_specs.json"), Path("data/pilot/model_v2_e.json"),
             Path("data/pilot/cold-source-binding.json"), Path(PROOF),
             Path("src/triple_lock/historical_publication.py")]
    if Path("uv.lock").exists():
        paths.append(Path("uv.lock"))
    return {"git_revision": pipeline.git_state()["git_revision"], **pipeline.hashes(),
            "engine_hashes": engine.engine_hashes(), "packages": pipeline.package_versions(),
            "bridge_files": {str(path): digest(path) for path in paths},
            "numeric_threads": {k: os.environ.get(k) for k in
                                ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")}}


def check_snapshot(start, where):
    if execution_snapshot() != start:
        raise engine.SourceChanged(f"bridge sources, inputs, packages or revision changed at {where}")


def check_resume(path, start):
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get("provenance", {}).get("execution_snapshot") != start:
            raise engine.SourceChanged("existing bridge receipt has incompatible source provenance")


def temporary_receipt(destination, payload):
    """Create an owner-only exclusive file for a receipt or exact-byte rollback."""
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_receipt(destination, public, guard):
    """Verify both sides of replacement and restore the prior valid bytes on drift."""
    previous = destination.read_bytes() if destination.exists() else None
    payload = (json.dumps(public, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temporary = temporary_receipt(destination, payload)
    try:
        guard()
        temporary.replace(destination)
        try:
            guard()
        except BaseException:
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                rollback = temporary_receipt(destination, previous)
                try:
                    rollback.replace(destination)
                finally:
                    rollback.unlink(missing_ok=True)
            raise
    finally:
        temporary.unlink(missing_ok=True)


def main(args):
    destination = args.out.resolve()
    workspace = Path.cwd().resolve()
    if (destination.name == "results.json" or not destination.is_relative_to(workspace)
            or not any(destination.is_relative_to(workspace / name) for name in ("data/pilot", ".cache"))):
        raise ValueError("bridge receipts belong under data/pilot or .cache in the assigned workspace")
    args.out = destination
    if args.workers not in (1, 2, 3):
        raise ValueError("at most three Enhanced FRS workers")
    start_snapshot = execution_snapshot()
    packages = start_snapshot["packages"]
    if any(packages[name] != version for name, version in
           (("policyengine", "6.2.6"), ("policyengine-uk", "2.125.1"), ("policyengine-core", "3.33.0"))):
        raise ValueError("bridge requires the exact certified 6.2.6 / 2.125.1 / 3.33.0 bundle")
    specs_path = Path("data/pilot/d_macro_specs.json")
    pilot_path = Path("data/pilot/model_v2_e.json")
    binding_path = Path("data/pilot/cold-source-binding.json")
    specs_bytes = read_snapshot_bytes(specs_path, start_snapshot)
    pilot_bytes = read_snapshot_bytes(pilot_path, start_snapshot)
    binding_bytes = read_snapshot_bytes(binding_path, start_snapshot)
    specs = engine._keys_to_int(json.loads(specs_bytes))
    pilot = json.loads(pilot_bytes)
    binding = json.loads(binding_bytes)
    # A snapshot detects drift during execution; it cannot authenticate an
    # already-edited pilot. Reuse only the independently pinned historical
    # fiscal content, verified from the exact buffer parsed above.
    pilot_correspondence = verify_historical_publication_redaction(
        workspace, supplied_bytes={str(pilot_path): pilot_bytes}, targets={str(pilot_path)})
    dataset = PILOT if args.pair == "model-step" else CERTIFIED
    planned, sample, weights = design(specs, dataset, args.pair == "model-step")
    verify_pilot_recipe(specs_bytes, pilot, sample, weights, binding)
    provenance = datasets.provenance(dataset)
    if args.pair == "certified" and provenance["certified"] is not True:
        raise ValueError("certified bridge requires matching dataset artifact and release certification")
    check_snapshot(start_snapshot, "bridge input validation")
    check_resume(args.out, start_snapshot)
    preflight = pipeline.housing_benefit_passport_preflight()
    check_snapshot(start_snapshot, "passport preflight")
    runs, timings = {}, []
    cache = Path(".cache/J-bridge-jobs")
    public = {
        "run_kind": "pre_budget_bridge", "quote_eligible": False, "minimum_contributing_records": 10,
        "label": "pre-Budget certified-bundle bridge; not for quoting",
        "provenance": {"execution_snapshot": start_snapshot,
                       "calculation": {"git_revision": start_snapshot["git_revision"]},
                       "engine_hashes": start_snapshot["engine_hashes"],
                       "packages": packages, "dataset": provenance,
                       "numeric_threads": {k: os.environ.get(k) for k in
                                           ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
                       "specs_sha256": hashlib.sha256(specs_bytes).hexdigest(), "preflight": preflight},
        "paired_macro_design": {"indices_by_stratum": sample, "probabilities_by_stratum": weights,
                                "n_first_phase": 50000, "seed": 20260929,
                                "zero_probability": specs["identical_rates_probability"]},
        "attribution": "Intermediate model/core/engine-port step holds data at 1.56.16; data step holds the "
                       "new model/core/port fixed. Intermediate paired runs are absent; paired attribution "
                       "is combined. No isolated model, core or port causal decomposition is claimed.",
    }
    public["retained_pilot"] = {
        "source": str(pilot_path), "sha256": hashlib.sha256(pilot_bytes).hexdigest(),
        "policyengine_uk": "2.120.0", "policyengine_core": "3.32.16", "dataset": PILOT,
        "certified": False, "fiscal": {kind: [r for r in pilot["fiscal"][kind]
                                                if r["treatment_or_contrast"] == "both"]
                                       for kind in ("central", "paired")},
        "historical_correspondence": pilot_correspondence,
        "note": "Exact committed forty-paired-index full both/kept configuration; figures copied unchanged. "
                "The old entitlement Housing Benefit passport is retained, with its pilot limitation.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(planned), args.workers):
        check_snapshot(start_snapshot, f"before batch {offset}")
        batch = planned[offset:offset + args.workers]
        memory = memory_check()
        cold = [not engine.cached(kind, arg, cache=cache) for _, (kind, arg) in batch]
        started = time.monotonic()
        output = run_batch(batch, args.workers, cache)
        check_snapshot(start_snapshot, f"after batch {offset}")
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
        check_snapshot(start_snapshot, f"before checkpoint {offset}")
        atomic_receipt(args.out, public, lambda: check_snapshot(start_snapshot, f"checkpoint commit {offset}"))
        print(f"Bridge checkpoint: {len(runs)}/{len(planned)} labels in {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", choices=("model-step", "certified"), required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args())
