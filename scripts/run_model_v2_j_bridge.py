"""Pinned model/data bridge; full runs and aggregate-only receipts.

Every job calculates the complete thirteen-year horizon. --config selects a
parameterised two-step bridge, with the complete forty-path paired design at
each new endpoint and exact from/to package and dataset pins in provenance.

The historical --pair mode retains the original bridge for reproducibility:
it reuses the pilot figures from E, holds data at 1.56.16 for its intermediate
model/core/port step and combines paired attribution. Its committed receipts
remain unchanged.
"""

import argparse
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import threading
import os
import re
import resource
import subprocess
import sys
import tempfile

import psutil

from triple_lock import datasets, dwp, engine, expected_value, host, jobs, pipeline
from triple_lock.historical_publication import PROOF, verify_historical_publication_redaction

try:
    from . import binding_bridge
except ImportError:  # direct invocation: python scripts/run_model_v2_j_bridge.py
    import binding_bridge

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


# Admission floors leave room for cold jobs about to load: 40 GiB for each before a batch (batch_resources), and for
# the one job each acquired slot admits. While a batch runs, its own jobs are already resident and counted out of
# available memory, so the monitor keeps only the host's safety floor (the rehearsal monitor's 8 GiB).
COLD_JOB_MINIMUM_GIB = 40
RUNNING_MINIMUM_GIB = 8


def memory_check(max_load_per_cpu=None, minimum_gib=40):
    """Keep the batch's memory floor available and enforce the shared load limit."""
    reading = host.measure()
    applied = host.assess(**reading, minimum_gib=minimum_gib, max_load_per_cpu=max_load_per_cpu)
    if not applied["admitted"]:
        raise host.HostSaturated(f"Host saturated: {host.describe(reading, applied)}; bridge stops before new jobs",
                                 decisions=[{**reading, **applied}])
    return {**reading, **applied}


def batch_resources(batch, workers):
    """Identify memory-heavy Microcosm jobs by family, independent of their role."""
    microcosm = sum(arg.get("dataset", "").startswith(("microcosm_", "populace_"))
                    for _, (_, arg) in batch)
    return {"slot_prefix": "J-bridge-microcosm" if microcosm else "J-bridge-efrs",
            "minimum_gib": COLD_JOB_MINIMUM_GIB * max(1, min(workers, microcosm))}


def own_memory_gib():
    """This process's and its descendants' (the batch's job processes) memory now, in GiB.

    Resident memory of each, the footprint summed over the whole tree (what
    heavy_run.sh counts), and the largest kernel lifetime footprint peak of
    any descendant; the footprint values are None off macOS.
    """
    descendants, pids = 0, [os.getpid()]
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):
            descendants += child.memory_info().rss
            pids.append(child.pid)
    read = footprints(pids)
    tree = sum(values.get("phys_footprint", 0) for values in read.values()) / 2**30 if read else None
    peaks = [values["phys_footprint_peak"] for pid, values in read.items()
             if pid != os.getpid() and "phys_footprint_peak" in values]
    return {"coordinator_rss": psutil.Process().memory_info().rss / 2**30, "jobs_rss": descendants / 2**30,
            "tree_footprint": tree, "job_footprint_peak": max(peaks) / 2**30 if peaks else None}


FOOTPRINT = Path("/usr/bin/footprint")
FOOTPRINT_HEADER = re.compile(r"^.* \[(\d+)\]: .*Footprint: ")
FOOTPRINT_FIELD = re.compile(r"^\s+(phys_footprint|phys_footprint_peak): (\d+) B$")


def footprints(pids, timeout=30):
    """Each pid's macOS phys_footprint and its kernel lifetime peak (bytes), read as heavy_run.sh reads them.

    phys_footprint counts compressed pages, unlike RSS; heavy_run.sh sums it
    over the command tree for its memory ceiling. Returns {} off macOS, and
    omits any pid footprint cannot read.
    """
    if not pids or not FOOTPRINT.exists():
        return {}
    command = [str(FOOTPRINT), "-f", "bytes", *(arg for pid in pids for arg in ("-p", str(pid)))]
    try:
        text = subprocess.run(command, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    found, pid = {}, None
    for line in text.splitlines():
        if header := FOOTPRINT_HEADER.match(line):
            pid = int(header.group(1))
        elif (field := FOOTPRINT_FIELD.match(line)) and pid is not None:
            found.setdefault(pid, {})[field.group(1)] = int(field.group(2))
    return {pid: values for pid, values in found.items() if pid in pids}


def peak_finished_job_rss_gib():
    """The kernel's high-water resident memory (GiB) of the largest finished descendant of this process so far."""
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return peak / 2**30 if sys.platform == "darwin" else peak / 2**20  # bytes on macOS, KiB on Linux


def run_batch(batch, workers, cache, monitor_interval=5, max_load_per_cpu=None, observed=None):
    """Share saturation cancellation with slot waits and child admission.

    The caller checks the whole batch's cold floor (batch_resources) before it
    starts. Each acquired slot admits its one cold job against
    COLD_JOB_MINIMUM_GIB, counting any job already resident, the batch's own
    included; the monitor, which runs while the batch's own jobs are resident,
    keeps RUNNING_MINIMUM_GIB. A supplied ``observed`` dict receives the
    monitor's memory samples: the lowest available memory, the largest resident
    memory of this process and of its job processes (RSS, which excludes
    compressed and swapped pages), the largest footprint of the whole tree and
    the largest kernel footprint peak of any job process (macOS
    phys_footprint, as heavy_run.sh counts it), and the kernel's peak RSS of
    any finished job process.
    """
    stop, finished, saturated = threading.Event(), threading.Event(), threading.Event()
    refusals = []
    resources = batch_resources(batch, workers)
    observed = {} if observed is None else observed
    observed.update({"interval_seconds": monitor_interval, "samples": 0, "minimum_available_gib": None,
                     "maximum_coordinator_rss_gib": None, "maximum_jobs_rss_gib": None,
                     "maximum_tree_footprint_gib": None, "peak_job_footprint_gib": None})

    def check_host(minimum_gib):
        try:
            return memory_check(max_load_per_cpu=max_load_per_cpu, minimum_gib=minimum_gib)
        except RuntimeError as error:
            refusals.extend(getattr(error, "host_admissions", []))
            saturated.set()
            jobs.kill_children(stop)
            raise

    def admission(kind, arg, workdir, scheduler_stop):
        # This runs inside the acquired slot: an earlier host snapshot may be
        # stale after waiting for another build to release the directory.
        check_host(COLD_JOB_MINIMUM_GIB)

    def record(reading):
        memory = own_memory_gib()
        observed["samples"] += 1
        for key, value, pick in (("minimum_available_gib", reading.get("available_gib"), min),
                                 ("maximum_coordinator_rss_gib", memory["coordinator_rss"], max),
                                 ("maximum_jobs_rss_gib", memory["jobs_rss"], max),
                                 ("maximum_tree_footprint_gib", memory["tree_footprint"], max),
                                 ("peak_job_footprint_gib", memory["job_footprint_peak"], max)):
            if value is not None:
                observed[key] = value if observed[key] is None else pick(observed[key], value)

    def monitor():
        while not finished.wait(monitor_interval):
            try:
                record(check_host(RUNNING_MINIMUM_GIB))
            except RuntimeError:
                return

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    try:
        output = jobs.run_jobs([job for _, job in batch], workers=workers,
                               slot_prefix=resources["slot_prefix"], cache=cache,
                               stop=stop, admission=admission)
    except RuntimeError:
        if saturated.is_set():
            raise host.HostSaturated("bridge stopped because host saturation was observed during this batch",
                                     decisions=refusals) from None
        raise
    finally:
        finished.set()
        watcher.join()
        observed["peak_finished_job_rss_gib"] = peak_finished_job_rss_gib()
    if saturated.is_set():
        raise host.HostSaturated("bridge stopped because host saturation was observed during this batch",
                                 decisions=refusals)
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
    paths = [Path(__file__), Path(binding_bridge.__file__), Path("scripts/run_model_v2_j_rehearsal.py"),
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
    if getattr(args, "validate_only", False) and args.config is None:
        raise ValueError("--validate-only requires --config")
    if getattr(args, "config", None) is not None:
        return binding_main(args)
    destination = args.out.resolve()
    workspace = Path.cwd().resolve()
    if (destination.name == "results.json" or not destination.is_relative_to(workspace)
            or not any(destination.is_relative_to(workspace / name) for name in ("data/pilot", ".cache"))):
        raise ValueError("bridge receipts belong under data/pilot or .cache in the assigned workspace")
    args.out = destination
    if args.workers not in (1, 2, 3):
        raise ValueError("at most three Enhanced FRS workers")
    # Resolve the load limit once, before any job: a malformed setting stops here, never mid-run.
    host_admission = {**host.configuration(args.max_load_per_cpu), "minimum_available_gib": COLD_JOB_MINIMUM_GIB,
                      "running_minimum_available_gib": RUNNING_MINIMUM_GIB}
    max_load_per_cpu = host_admission["max_load_per_cpu"]
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
                       "specs_sha256": hashlib.sha256(specs_bytes).hexdigest(), "preflight": preflight,
                       "host_admission": host_admission},
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
        memory = memory_check(max_load_per_cpu=max_load_per_cpu)
        cold = [not engine.cached(kind, arg, cache=cache) for _, (kind, arg) in batch]
        started = time.monotonic()
        output = run_batch(batch, args.workers, cache, max_load_per_cpu=max_load_per_cpu)
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


def binding_main(args):
    """Execute one pinned endpoint; a to receipt compares it with its from.

    Model/to compares against the exact committed 6.2.6 receipt. Data/to must reuse
    model/to, so the intermediate endpoint cannot silently be substituted.
    The unreleased bundle is deliberately not guessed or installed here.
    """
    workspace = Path.cwd().resolve()
    destination = args.out.resolve()
    protected = {workspace / f"data/pilot/J-bridge-{name}.json" for name in ("certified", "model-step")}
    if (destination.name == "results.json" or destination in protected
            or not destination.is_relative_to(workspace)
            or not any(destination.is_relative_to(workspace / name) for name in ("data/pilot", ".cache"))):
        raise ValueError("new bridge receipts belong under data/pilot or .cache and cannot overwrite historical receipts")
    if args.workers not in (1, 2, 3):
        raise ValueError("at most three bridge workers; Microcosm endpoints permit at most two")
    if args.step not in ("model", "data") or args.endpoint not in ("from", "to"):
        raise ValueError("configured bridges require --step model|data and --endpoint from|to")
    if args.endpoint == "to" and args.from_receipt is None:
        raise ValueError("a to endpoint requires --from-receipt for the separate step comparison")
    if args.step == "data" and args.endpoint == "from":
        raise ValueError("data/from reuses model/to; run data/to with --from-receipt pointing to model/to")
    input_paths = [args.config.resolve()]
    if args.from_receipt is not None:
        input_paths.append(args.from_receipt.resolve())
    if destination in input_paths:
        raise ValueError("bridge output cannot replace an input receipt or configuration")

    def with_inputs(current):
        current["bridge_input_files"] = {str(path): digest(path) for path in input_paths}
        current["bridge_files"] = {**current["bridge_files"], **current["bridge_input_files"]}
        return current

    initial = execution_snapshot()
    stable_bridge_files = dict(initial["bridge_files"])
    start = with_inputs(initial)

    def snapshot():
        return with_inputs(execution_snapshot())

    def guard():
        if snapshot() != start:
            raise engine.SourceChanged("binding bridge sources, inputs, packages or revision changed")

    config_raw = read_snapshot_bytes(input_paths[0], start)
    configuration = binding_bridge.validate_configuration(json.loads(config_raw))
    declared = configuration["steps"][args.step][args.endpoint]
    if (declared["dataset"]["name"].startswith("microcosm_") and args.workers > 2):
        raise ValueError("at most two Microcosm bridge workers; start with one until peak memory is measured")
    provenance = datasets.provenance(declared["dataset"]["name"])
    binding_bridge.validate_runtime(declared, start["packages"], provenance)
    if args.step == "data" and provenance.get("certified") is not True:
        raise ValueError("data/to requires the new released bundle's exact dataset certification")
    specs_path = Path("data/pilot/d_macro_specs.json")
    specs_raw = read_snapshot_bytes(specs_path, start)
    specs = engine._keys_to_int(json.loads(specs_raw))
    pilot = json.loads(read_snapshot_bytes(Path("data/pilot/model_v2_e.json"), start))
    binding = json.loads(read_snapshot_bytes(Path("data/pilot/cold-source-binding.json"), start))
    planned, sample, weights = design(specs, declared["dataset"]["name"])
    verify_pilot_recipe(specs_raw, pilot, sample, weights, binding)
    paired_design = {"indices_by_stratum": sample, "probabilities_by_stratum": weights,
                     "n_first_phase": 50000, "seed": 20260929,
                     "zero_probability": specs["identical_rates_probability"]}
    source = None
    if args.from_receipt is not None:
        source_raw = read_snapshot_bytes(input_paths[1], start)
        source = json.loads(source_raw)
        binding_bridge.validate_source_receipt(configuration, args.step, source, source_raw,
                                               paired_design, hashlib.sha256(specs_raw).hexdigest())
        if args.step == "data" and source["provenance"]["engine_hashes"] != start["engine_hashes"]:
            raise ValueError("data bridge step must hold engine sources fixed as well as the model bundle")
        if args.step == "data":
            previous = source["provenance"].get("execution_snapshot", {})
            for field in ("source_hashes", "input_hashes", "packages", "numeric_threads", "engine_hashes"):
                if field not in previous or field not in start or previous[field] != start[field]:
                    raise ValueError(f"data bridge step must hold {field} fixed as well as the model bundle")
            external = previous.get("bridge_input_files")
            files = previous.get("bridge_files", {})
            if (not isinstance(external, dict) or not isinstance(files, dict)
                    or any(files.get(path) != value for path, value in external.items())
                    or {path: value for path, value in files.items() if path not in external} != stable_bridge_files):
                raise ValueError("data bridge step must hold stable bridge files fixed, including driver, helper and lock")
    if getattr(args, "validate_only", False):
        guard()
        print(json.dumps({"validated": True, "step": args.step, "endpoint": args.endpoint,
                          "declared_pins": declared, "jobs_run": 0}, sort_keys=True))
        return
    host_admission = {**host.configuration(args.max_load_per_cpu),
                      "minimum_available_gib": batch_resources(planned, args.workers)["minimum_gib"],
                      "running_minimum_available_gib": RUNNING_MINIMUM_GIB}
    guard()
    check_resume(destination, start)
    preflight = pipeline.housing_benefit_passport_preflight()
    guard()
    public = {
        "run_kind": "binding_readiness_bridge", "quote_eligible": False,
        "minimum_contributing_records": 10,
        "label": f"Binding readiness {args.step} bridge {args.endpoint}; not for quoting",
        "bridge": {"configuration": configuration,
                   "configuration_sha256": binding_bridge.fingerprint(configuration),
                   "configuration_file_sha256": hashlib.sha256(config_raw).hexdigest(),
                   "step": args.step, "endpoint": args.endpoint, "declared_pins": declared,
                   **({"from_receipt": {"path": str(input_paths[1]), "sha256": digest(input_paths[1])}}
                      if source is not None else {})},
        "provenance": {"execution_snapshot": start, "packages": start["packages"], "dataset": provenance,
                       "engine_hashes": start["engine_hashes"], "preflight": preflight,
                       "specs_sha256": hashlib.sha256(specs_raw).hexdigest(), "host_admission": host_admission},
        "paired_macro_design": paired_design,
        "attribution": ("Model bundle changes with dataset bytes fixed." if args.step == "model"
                        else "Dataset bytes change with the model bundle and engine sources fixed."),
    }
    runs, timings = {}, []
    cache = Path(".cache/J-bridge-jobs")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(planned), args.workers):
        guard()
        batch = planned[offset:offset + args.workers]
        memory = memory_check(max_load_per_cpu=host_admission["max_load_per_cpu"],
                              minimum_gib=batch_resources(batch, args.workers)["minimum_gib"])
        cold = [not engine.cached(kind, arg, cache=cache) for _, (kind, arg) in batch]
        started, observed = time.monotonic(), {}
        output = run_batch(batch, args.workers, cache, max_load_per_cpu=host_admission["max_load_per_cpu"],
                           observed=observed)
        guard()
        elapsed = time.monotonic() - started
        timings.append({"labels": [name for name, _ in batch], "cold": cold,
                        "wall_seconds": elapsed, "host_before": memory, "memory_observed": observed})
        for (name, _), run in zip(batch, output, strict=True):
            runs[name] = run
        public.update({"complete": len(runs) == len(planned), "completed_labels": list(runs),
                       "generated_at": datetime.now(timezone.utc).isoformat(), "timings": timings,
                       "fiscal": saving_tables({k: v for k, v in runs.items() if k != "coverage"}, sample, weights)})
        if "coverage" in runs:
            public["coverage"] = coverage_tables(runs["coverage"])
        if public["complete"] and source is not None:
            public["comparison"] = binding_bridge.compare(source, public)
        pipeline.redact_records(public)
        guard()
        atomic_receipt(destination, public, guard)
        print(f"{args.step}/{args.endpoint} bridge checkpoint: {len(runs)}/{len(planned)} labels", flush=True)


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pair", choices=("model-step", "certified"), help="historical pre-Budget bridge")
    mode.add_argument("--config", type=Path, help="JSON with exact from/to pins for chained model and data steps")
    parser.add_argument("--step", choices=("model", "data"))
    parser.add_argument("--endpoint", choices=("from", "to"), default="to")
    parser.add_argument("--from-receipt", type=Path)
    parser.add_argument("--validate-only", action="store_true",
                        help="validate configured pins, source receipt and paired design; run no jobs or model preflights")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-load-per-cpu", type=float, default=None,
                        help=f"refuse new jobs above this one-minute load per CPU (default ${host.MAX_LOAD_PER_CPU_ENV}, "
                             f"else {host.DEFAULT_MAX_LOAD_PER_CPU:g}); the memory floors ({COLD_JOB_MINIMUM_GIB} GiB per cold "
                             f"Microcosm job at admission, {RUNNING_MINIMUM_GIB} GiB while jobs run) are fixed")
    return parser


if __name__ == "__main__":
    main(argument_parser().parse_args())
