#!/usr/bin/env python3
"""Bounded pre-Budget rehearsal; separate receipts, no results.json or fiscal expected value.

Every model job is an ordinary full PolicyEngine run. --plan starts no model
jobs. The driver never calls pipeline.build and never accepts a binding C2
handoff. Root coordinates Microcosm stages with other workers on the host.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import threading
import time

from triple_lock import ageing_validation as AV, central, datasets, engine, expected_value as EV, jobs, pipeline, trajectories
from triple_lock.config import HORIZON, PRIMARY_DATASET, REPO, SENSITIVITY_DATASET

STAGES = ("central", "coverage", "scenarios", "validation", "sample", "core", "all")
CERTIFIED_PACKAGES = {"policyengine": "6.2.6", "policyengine-uk": "2.125.1", "policyengine-core": "3.33.0"}
NUMERIC_THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                   "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def execution_environment():
    """Scientific packages, certified primary artifact and the exact driver bytes."""
    return {"packages": pipeline.package_versions(), "dataset": datasets.provenance(PRIMARY_DATASET),
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "numeric_threads": {name: os.environ.get(name) for name in NUMERIC_THREADS}}


def certified_environment():
    environment = execution_environment()
    if any(environment["packages"].get(name) != version for name, version in CERTIFIED_PACKAGES.items()):
        raise ValueError("rehearsal requires the exact certified 6.2.6 / 2.125.1 / 3.33.0 bundle")
    if environment["dataset"].get("certified") is not True:
        raise ValueError("rehearsal requires the certified primary dataset artifact and release manifest")
    return environment


def check_execution(start, environment, where):
    pipeline.check_unchanged(start, where)
    if execution_environment() != environment:
        raise engine.SourceChanged(f"rehearsal packages, dataset certification, driver or numeric threads changed at {where}")


def serialized_receipt(report):
    return (json.dumps(report, indent=1, default=float, allow_nan=False) + "\n").encode("utf-8")


def private_temporary_receipt(report, destination, payload):
    """Write through an exclusively created descriptor; never follow a temp symlink."""
    destination = pipeline.validate_write_paths(report, [destination])[0]
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def host_snapshot(*, vm_stat=True):
    import psutil

    memory = psutil.virtual_memory()
    snapshot = {"available_gib": memory.available / 2**30, "load_1m": os.getloadavg()[0],
                "cpu_count": os.cpu_count() or 1}
    if vm_stat:
        try:
            observed = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True)
            snapshot["vm_stat"] = observed.stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            snapshot["vm_stat"] = "unavailable on this host; psutil memory check retained"
    return snapshot


def check_host(snapshot, minimum_gib):
    if snapshot["available_gib"] < minimum_gib or snapshot["load_1m"] > 2 * snapshot["cpu_count"]:
        raise RuntimeError("rehearsal stopped: host memory or load exceeds the documented worker budget")


def planning_estimate(timings, unique_runs, paired_runs, workers, sensitivity_workers):
    """The sole extrapolation: cold-job means for future runtime planning."""
    cold = defaultdict(list)
    for row in timings:
        if row["cache"] == "cold" and row["status"] == "completed":
            cold[(row["dataset"], row["kind"])].append(row["wall_seconds"])
    measured = {f"{dataset}.{kind}": {"cold_jobs": len(values), "mean_wall_seconds": statistics.mean(values)}
                for (dataset, kind), values in cold.items()}
    outcomes = {}
    for passes in (True, False):
        efrs = {"path": 3 * unique_runs + 6 + (5 * (1 + paired_runs) if passes else 5),
                "coverage": 7, "history": 4}
        microcosm = {"path": paired_runs if passes else 0, "coverage": 1}
        missing = [f"{dataset}.{kind}" for dataset, counts in (("efrs", efrs), ("microcosm", microcosm))
                   for kind, count in counts.items() if count and (dataset, kind) not in cold]
        optimistic_seconds = None if missing else sum(
            count * statistics.mean(cold[(dataset, kind)]) / concurrency
            for dataset, counts, concurrency in (("efrs", efrs, workers),
                                                 ("microcosm", microcosm, sensitivity_workers))
            for kind, count in counts.items() if count)
        # pipeline.build runs its central path, OBR wedge and two dataset
        # coverage jobs with one worker each. Their latency cannot be divided
        # by the worker cap used by the draw/trajectory/validation batches.
        serial = {"efrs": {"path": 2, "coverage": 1}, "microcosm": {"coverage": 1}}
        parallel = {
            "efrs": {kind: count - serial["efrs"].get(kind, 0) for kind, count in efrs.items()},
            "microcosm": {kind: count - serial["microcosm"].get(kind, 0) for kind, count in microcosm.items()},
        }
        planned_seconds = None if missing else (
            sum(count * statistics.mean(cold[(dataset, kind)])
                for dataset, counts in serial.items() for kind, count in counts.items())
            + sum(count * statistics.mean(cold[(dataset, kind)]) / concurrency
                  for dataset, concurrency in (("efrs", workers), ("microcosm", sensitivity_workers))
                  for kind, count in parallel[dataset].items() if count))
        outcomes["primary_passes" if passes else "primary_fails"] = {
            "enhanced_frs_jobs": efrs, "microcosm_jobs": microcosm,
            "ideal_parallel_wall_hours": None if optimistic_seconds is None else optimistic_seconds / 3600,
            "planned_stage_wall_hours": None if planned_seconds is None else planned_seconds / 3600,
            "serial_jobs": serial, "parallel_jobs": parallel,
            "unmeasured_job_types": missing}
    return {"label": "planning estimate only; not a published fiscal number",
            "method": "completed cold job means times logical job counts; planned stages add serial central, OBR wedge "
                      "and dataset coverage jobs to the remaining batches / configured worker caps; stages sequential; "
                      "cache hits excluded from measured means",
            "optimistic_bound": "ideal_parallel_wall_hours divides every logical job by its dataset's worker cap, "
                                "including jobs that the build runs serially; an optimistic comparison only",
            "limitations": "excludes input preparation, C2 scoring, review, paper/dashboard work, scheduling, "
                           "partial worker batches, cache reuse and contention",
            "measured_types": measured, "post_Budget_build_plus_validation": outcomes}


class TimedJobs:
    """Time cold engine jobs and checkpoint safe metadata after every completion."""

    def __init__(self, report, checkpoint, guard=None):
        self.report, self.checkpoint = report, checkpoint
        self.guard = guard or (lambda where: None)
        self.lock = threading.RLock()
        self.stop = threading.Event()

    def __call__(self, requested, *, workers=1, slot_prefix="efrs", log=print):
        if self.stop.is_set():
            raise jobs.Aborted("rehearsal stopped before another model batch could start")
        self.guard("before model batch")
        requested = list(requested)
        datasets = {"microcosm" if argument.get("dataset") == SENSITIVITY_DATASET else "efrs"
                    for _, argument in requested}
        if len(datasets) > 1:
            raise ValueError("rehearsal runs Enhanced FRS and Microcosm stages separately")
        dataset = next(iter(datasets), "efrs")
        if workers not in range(1, (2 if dataset == "microcosm" else 3) + 1):
            raise ValueError("rehearsal worker cap exceeded")
        snapshot = host_snapshot()
        self.report["host_checks"].append(snapshot)
        try:
            check_host(snapshot, 40 * workers if dataset == "microcosm" else 40)
        except RuntimeError:
            jobs.kill_children(self.stop)
            raise
        semantic, packages = engine.engine_semantics(), engine.package_versions()
        warm = [(kind, arg) for kind, arg in requested if engine.cached(kind, arg, semantic, packages) is not None]
        self.report["timings"].extend({"dataset": dataset, "kind": kind,
                                       "job_key": engine.job_key(kind, arg, semantic, packages),
                                       "cache": "warm", "status": "completed", "wall_seconds": None}
                                      for kind, arg in warm)
        self.checkpoint()

        def admission(kind, argument, workdir, stop):
            # The scheduler calls this only after acquiring the worker slot.
            # A host check before a potentially long slot wait is insufficient.
            # Keep 40 GiB available at every new launch, for either dataset.
            # Worker caps permit concurrency; they do not reserve memory or
            # promise parallel launches when another job uses that headroom.
            self.guard("after worker slot acquisition")
            snapshot = host_snapshot()
            with self.lock:
                self.report["host_checks"].append({**snapshot, "phase": "after_slot_acquisition"})
                self.checkpoint()
            try:
                check_host(snapshot, 40)
            except RuntimeError:
                jobs.kill_children(stop)
                raise

        def isolated(kind, argument, workdir, semantics, stop):
            started = time.monotonic()
            status = "failed"
            finished = threading.Event()

            def monitor():
                while not finished.wait(5):
                    try:
                        check_host(host_snapshot(vm_stat=False), 8)
                    except RuntimeError:
                        jobs.kill_children(stop)
                        return

            watcher = threading.Thread(target=monitor, name="rehearsal-host-monitor", daemon=True)
            watcher.start()
            try:
                result = jobs._run_isolated(kind, argument, workdir, semantics, stop)
                if stop.is_set():
                    raise jobs.Aborted("rehearsal stopped during the model job")
                status = "completed"
                return result
            finally:
                finished.set()
                watcher.join()
                with self.lock:
                    self.report["timings"].append({"dataset": dataset, "kind": kind,
                                                   "job_key": engine.job_key(kind, argument, semantic, packages),
                                                   "cache": "cold", "status": status,
                                                   "wall_seconds": time.monotonic() - started})
                    self.checkpoint()

        started = time.monotonic()
        result = jobs.run_jobs(requested, workers=workers, slot_prefix=slot_prefix, log=log,
                               runner=isolated, stop=self.stop, admission=admission)
        if self.stop.is_set():
            raise jobs.Aborted("rehearsal stopped during the model batch")
        self.guard("after model batch")
        self.report["batches"].append({"dataset": dataset, "jobs": len(requested), "workers": workers,
                                       "warm_jobs": len(warm), "wall_seconds": time.monotonic() - started})
        self.checkpoint()
        return result


def core_plan(inputs, base_weekly):
    spec = {k: v for k, v in trajectories.central_spec(inputs).items() if k not in ("id", "label", "source")}
    cov = {"years": pipeline.COVERAGE_YEARS, "september_cpi_history": central.september_cpi_history(), "spec": spec}
    future, _ = trajectories.forward_specs(inputs, base_weekly)
    cpi, earnings = trajectories.history_inputs()
    history = trajectories.history_groups(cpi, earnings)
    changing = [group for group in history if group["changes_anything"]]
    scenario_jobs = [("path", {k: v for k, v in row.items() if k not in ("id", "label", "source", "selection")})
                     for row in future]
    scenario_jobs += [trajectories.history_job(group) for group in changing]
    scenario_jobs += [("path", {k: v for k, v in trajectories.obr_premium_spec(inputs).items()
                               if k not in ("id", "label", "source")})]
    modes = AV.RUN_MODES
    validation_jobs = [("path", AV.canonical({**spec, "demography": mode})) for mode in modes]
    validation_jobs += [("coverage", AV.canonical({**cov, "demography": mode})) for mode in modes]
    return {"central": [("path", spec)], "coverage": [("coverage", cov)],
            "microcosm_coverage": [("coverage", {**cov, "dataset": SENSITIVITY_DATASET})],
            "scenarios": scenario_jobs, "validation": validation_jobs,
            "validation_modes": list(modes), "scenario_ids": [row["id"] for row in future] + ["obr_premium"],
            "history_switch_years": [group["switch_years"] for group in changing],
            "historical_model_years": list(trajectories.HISTORY_MODEL_YEARS)}


def validation_receipt(modes, results):
    """Record completed engine invariants without any fiscal or survey table.

    Individual treatment support counts cannot certify treatment contrasts or
    UK/GB complements. This timing rehearsal therefore copies no path/coverage
    amounts, caseloads, support counts, contrasts or record diagnostics.
    """
    if len(results) != 2 * len(modes):
        raise ValueError("rehearsal validation requires one path and coverage result per mode")
    paths, coverage = results[:len(modes)], results[len(modes):]
    if any(run["fixed_inputs"]["demography"] != mode for mode, run in zip(modes, paths, strict=True)):
        raise ValueError("rehearsal path did not use its requested population treatment")
    if any(run["demography"] != mode for mode, run in zip(modes, coverage, strict=True)):
        raise ValueError("rehearsal coverage did not use its requested population treatment")
    if any(run["fixed_inputs"]["calculated_fiscal_years"] != list(HORIZON) for run in paths):
        raise ValueError("rehearsal validation path did not calculate the full horizon")
    return {"rehearsal": True, "quote_eligible": False, "status": "completed",
            "method": "Central-only full PolicyEngine runs of the four-way factorial plus legacy/total controls; timing and invariants only.",
            "modes": list(modes), "path_jobs": len(paths), "coverage_jobs": len(coverage),
            "invariants": {"requested_treatments_used": True, "full_horizon_paths": True,
                           "all_engine_jobs_completed": True},
            "fiscal_tables_omitted": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--handoff", type=Path, required=True, help="current C2 dry-run directory")
    parser.add_argument("--output-dir", type=Path, default=REPO / ".cache" / "J-rehearsal")
    parser.add_argument("--stage", choices=STAGES, default="all")
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--sensitivity-workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--sample-runs", type=int, choices=range(1, 21), default=20)
    parser.add_argument("--microcosm-runs", type=int, choices=(0, 1, 2), default=2)
    parser.add_argument("--skip-microcosm-coverage", action="store_true", help="root allocates that memory-intensive stage separately")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--plan", action="store_true", help="validate current handoff and print counts; no model jobs")
    args = parser.parse_args(argv)
    directory = pipeline.rehearsal_output_directory(args.output_dir)
    start = pipeline.snapshot()
    if start["git_dirty"] and not args.allow_dirty and not args.plan:
        parser.error("commit input/code changes first, or record them with --allow-dirty")
    environment = certified_environment()
    inputs = central.central_path()
    sample = EV.rehearsal_design(inputs, args.handoff, n_runs=args.sample_runs, n_sensitivity=args.microcosm_runs)
    from policyengine_uk.system import system
    plan = core_plan(inputs, engine.base_levels(system.parameters)["new_state_pension"])
    report = {"rehearsal": True, "run_kind": "rehearsal", "quote_eligible": False,
              "expected_value_authorized": False, "rehearsal_output_dir": str(directory.relative_to(REPO)),
              "label": "pre-Budget rehearsal; not for quoting", "stage": args.stage,
              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "status": "planned" if args.plan else "running",
              "provenance": {**start, **sample["provenance"], **environment},
              "job_plan": {key: len(value) for key, value in plan.items() if key in STAGES or key == "microcosm_coverage"},
              "validation_modes": plan["validation_modes"], "scenario_ids": plan["scenario_ids"],
              "history_switch_years": plan["history_switch_years"], "historical_model_years": plan["historical_model_years"],
              "sample_indices": sample["indices"], "sensitivity_indices": sample["sensitivity_indices"],
              "numeric_threads": environment["numeric_threads"],
              "timings": [], "batches": [], "host_checks": []}
    def guard(where):
        check_execution(start, environment, where)

    guard("after rehearsal planning")
    if args.plan:
        print(json.dumps(report, indent=1, default=float, allow_nan=False))
        return 0

    def checkpoint():
        guard("before receipt checkpoint")
        destination = directory / f"{args.stage}-receipt.json"
        pipeline.validate_write_paths(report, [destination])
        previous = destination.read_bytes() if destination.exists() else None
        temporary = private_temporary_receipt(report, destination, serialized_receipt(report))
        # Recheck after serialization and before committing the atomic receipt.
        # A drifted run keeps its last valid checkpoint, never a completed one.
        try:
            guard("after receipt serialization")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(destination)
        try:
            guard("after receipt checkpoint")
        except BaseException:
            # Preserve a prior valid receipt if drift occurred during commit.
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                rollback = private_temporary_receipt(report, destination, previous)
                try:
                    rollback.replace(destination)
                finally:
                    rollback.unlink(missing_ok=True)
            raise

    runner = TimedJobs(report, checkpoint, guard)
    try:
        guard("before passport preflight")
        report["provenance"]["preflight"] = pipeline.housing_benefit_passport_preflight()
        guard("after passport preflight")
        checkpoint()
        with jobs.terminate_on_signals():
            for stage in ("central", "coverage", "scenarios", "validation"):
                if args.stage in (stage, "core", "all"):
                    guard(f"before {stage} stage")
                    results = runner(plan[stage], workers=args.workers, slot_prefix="efrs")
                    guard(f"after {stage} stage")
                    report.setdefault("completed_stages", []).append(stage)
                    if stage == "validation":
                        report["validation"] = validation_receipt(plan["validation_modes"], results)
                    if stage == "coverage" and not args.skip_microcosm_coverage:
                        guard("before Microcosm coverage stage")
                        runner(plan["microcosm_coverage"], workers=1, slot_prefix="microcosm")
                        guard("after Microcosm coverage stage")
            if args.stage in ("sample", "all"):
                guard("before timing sample")
                sample_result = EV.rehearsal_sample(
                    inputs, args.handoff, n_runs=args.sample_runs, n_sensitivity=args.microcosm_runs,
                    workers=args.workers, sensitivity_workers=args.sensitivity_workers, runner=runner)
                guard("after timing sample")
                report["sample"] = sample_result
        guard("the end of the rehearsal")
        report["planning_estimate"] = planning_estimate(
            report["timings"], sample["provenance"]["full_design_unique_runs"],
            sample["provenance"]["full_design_paired_runs"], args.workers, args.sensitivity_workers)
        report["status"] = "completed"
    except BaseException as error:
        # Private survey errors are already kept owner-only by jobs._run_isolated.
        # Record an exception class here, never potentially record-bearing text.
        report.update(status="failed", failure_type=type(error).__name__)
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        checkpoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
