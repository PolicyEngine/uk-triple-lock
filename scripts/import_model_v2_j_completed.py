"""Verify and import the completed, frozen Part J aggregates; start no model jobs.

Run with the locked environment, --run-root pointing to the b31137e rehearsal
checkout and --timings pointing to its runner's timings.txt. Verification reads
that checkout only. Publication uses Part J's atomic writer in this workspace.
Rehearsal fiscal results and raw engine caches never enter the output payload.
"""

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys


HEAD = "b31137ea055ab7e2b2ef7dd8b63df1302f5affdf"
# These completed receipt bytes were independently checked before import.
RECEIPTS = {
    "J-bridge-model-step.json": "e0576b897c81852b8961cd03538c46159e0bc16b8db9ba5ee50ea49a46c292b7",
    "J-bridge-certified.json": "f5f42f5a6e20eb251dd26a283b840fdb825843e8edc9078c02fea78f14b6ac2f",
    "J-rehearsal/core-receipt.json": "8611630afb278df60204137937750fe4df260668886372a31d972f78ec284560",
    "J-rehearsal/coverage-receipt.json": "ed06c052e6e0d8c417ebfc09127ec83e86f08572e414c6947446a0f97872d4ee",
    "J-rehearsal/sample-receipt.json": "16a30f96573521109ff3b6c2b57c0e311aa01e34e5e4aa24f5a9b2594b9568ea",
    "J-c2-dry-run/handoff.json": "8e8b8ab7ce9e3e11288b400ddcf946cd041773466247a4150b8ca3ab5033919d",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_receipts(root):
    receipts = {}
    for name, expected in RECEIPTS.items():
        raw = (root / ".cache" / name).read_bytes()
        require(digest(raw) == expected, f"Completed receipt bytes changed: {name}")
        receipts[name] = json.loads(raw)
    return receipts


def completed_wrappers(raw):
    rows = []
    for line in raw.splitlines():
        match = re.fullmatch(r"(\S+) attempt=(\d+) rc=(\d+) wall_s=(\d+) started=(\S+)", line)
        require(match is not None, "Malformed runner timing row")
        step, attempt, rc, wall, started = match.groups()
        if rc == "0":
            rows.append({"step": step, "attempt": int(attempt), "wall_seconds": int(wall), "started_at": started})
    expected = {"c2-dry-run", "bridge-model-step", "bridge-certified", "rehearsal-core", "rehearsal-coverage", "rehearsal-sample"}
    require(len(rows) == len(expected) and {row["step"] for row in rows} == expected,
            "Require exactly one completed run of every requested step")
    return rows


def cached_jobs(engine, requested, cache):
    """Read exact-key completed results; never admit a model job on a miss."""
    results = []
    for kind, argument in requested:
        result = engine.cached(kind, argument, cache=cache)
        require(result is not None, "Missing exact-key completed rehearsal cache")
        results.append(result)
    return results


def verify_passport(pipeline, provenance):
    passport = provenance["preflight"]["housing_benefit_guarantee_credit_passport"]
    facts = pipeline.passport_probe_facts()
    checks = pipeline.passport_checks(passport["observed"]["claims"], passport["observed"]["receipt_set"], facts["rent"])
    require(passport["keyed_on"] == "receipt" and passport["policyengine_uk"] == "2.125.1"
            and passport["probe"] == facts
            and passport["checks"] == [name for name, _ in checks]
            and all(passed for _, passed in checks), "Saved Housing Benefit receipt passport fails verification")


def verify_timings(engine, requested, receipt):
    """Bind every safe timing row, including repeated warm jobs, to its plan."""
    def dataset(argument):
        return "microcosm" if argument.get("dataset") == "populace_uk_2023" else "efrs"

    planned = Counter((dataset(arg), kind, engine.job_key(kind, arg)) for kind, arg in requested)
    rows = receipt["timings"]
    require(Counter((row["dataset"], row["kind"], row["job_key"]) for row in rows) == planned,
            "Rehearsal timing rows differ from the exact stage plan")
    for row in rows:
        require(row["status"] == "completed", "Failed timing cannot enter completed receipt")
        wall = row["wall_seconds"]
        require((row["cache"] == "warm" and wall is None)
                or (row["cache"] == "cold" and type(wall) in (int, float)
                    and math.isfinite(wall) and wall > 0), "Invalid completed cold/warm timing")
    return [{key: row[key] for key in ("dataset", "kind", "job_key", "cache", "status", "wall_seconds")}
            for row in rows]


def verify(root, timing_bytes):
    """Called in the frozen checkout with its original source and environment."""
    print("Verifying completed receipts with the frozen calculation source", file=sys.stderr, flush=True)
    from triple_lock import central, datasets, engine, expected_value as ev, pipeline
    from triple_lock.historical_publication import verify_historical_publication_redaction
    from triple_lock.ts_uncertainty import validate_c2_handoff

    receipts = read_receipts(root)
    require(pipeline.git_state() == {"git_revision": HEAD, "git_dirty": False}, "Require the clean calculation checkout")
    bridge = runpy.run_path(str(root / "scripts/run_model_v2_j_bridge.py"))
    rehearsal = runpy.run_path(str(root / "scripts/run_model_v2_j_rehearsal.py"))
    snapshot = bridge["execution_snapshot"]()
    specs_bytes = (root / "data/pilot/d_macro_specs.json").read_bytes()
    specs = engine._keys_to_int(json.loads(specs_bytes))
    pilot = json.loads((root / "data/pilot/model_v2_e.json").read_text())
    binding = json.loads((root / "data/pilot/cold-source-binding.json").read_text())
    correspondence = verify_historical_publication_redaction(root, targets={"data/pilot/model_v2_e.json"})
    verified = []
    for pair in ("model-step", "certified"):
        print(f"Verifying {pair} bridge caches and linked support", file=sys.stderr, flush=True)
        receipt = receipts[f"J-bridge-{pair}.json"]
        require(receipt["complete"] is True and receipt["quote_eligible"] is False,
                "Require a completed nonquotable bridge")
        require(receipt["provenance"]["execution_snapshot"] == snapshot, "Bridge calculation source/input/package drift")
        verify_passport(pipeline, receipt["provenance"])
        dataset = bridge["PILOT"] if pair == "model-step" else bridge["CERTIFIED"]
        require(datasets.provenance(dataset) == receipt["provenance"]["dataset"], "Bridge dataset certification drift")
        require(receipt["retained_pilot"]["historical_correspondence"] == correspondence, "Historical pilot binding differs")
        planned, sample, weights = bridge["design"](specs, dataset, pair == "model-step")
        bridge["verify_pilot_recipe"](specs_bytes, pilot, sample, weights, binding)
        require(engine._keys_to_int(receipt["paired_macro_design"]) == {
            "indices_by_stratum": sample, "probabilities_by_stratum": weights,
            "n_first_phase": 50000, "seed": 20260929,
            "zero_probability": specs["identical_rates_probability"]}, "Saved bridge paired design differs")
        retained = receipt["retained_pilot"]
        require(retained["sha256"] == digest((root / "data/pilot/model_v2_e.json").read_bytes())
                and retained["fiscal"] == {kind: [row for row in pilot["fiscal"][kind]
                                                 if row["treatment_or_contrast"] == "both"]
                                          for kind in ("central", "paired")}, "Retained pilot fiscal copy differs")
        require(receipt["completed_labels"] == [name for name, _ in planned], "Bridge labels incomplete")
        runs = {name: engine.cached(kind, arg, cache=root / ".cache/J-bridge-jobs")
                for name, (kind, arg) in planned}
        require(all(run is not None for run in runs.values()), "Missing exact-key bridge cache")
        require(bridge["saving_tables"]({k: v for k, v in runs.items() if k != "coverage"}, sample, weights)
                == receipt["fiscal"], "Fiscal tables or linked support changed")
        require(bridge["coverage_tables"](runs["coverage"]) == receipt["coverage"], "Coverage or complement support changed")
        verified.append({"pair": pair, "completed_labels": len(planned), "exact_cache_and_tables_match": True})

    handoff = receipts["J-c2-dry-run/handoff.json"]
    print("Verifying C2 dry handoff and reconstructing rehearsal plans", file=sys.stderr, flush=True)
    validate_c2_handoff(handoff, require_binding=False)
    require(handoff["run_kind"] == "dry_run" and handoff["expected_value_authorized"] is False, "C2 must remain unauthorized")
    require(json.loads((root / ".cache/J-c2-dry-run/scores.json").read_text()) == handoff["score_table"],
            "Standalone C2 scores differ from the verified handoff")
    inputs = central.central_path()
    sample = ev.rehearsal_design(inputs, root / ".cache/J-c2-dry-run", log=lambda *_: None)
    from policyengine_uk.system import system
    plan = rehearsal["core_plan"](inputs, engine.base_levels(system.parameters)["new_state_pension"])

    def cache_only_runner(requested, **_kwargs):
        return cached_jobs(engine, requested, root / ".cache/jobs")

    timings = []
    stages = []
    for stage in ("core", "coverage", "sample"):
        print(f"Verifying {stage} rehearsal provenance and timing caches", file=sys.stderr, flush=True)
        receipt = receipts[f"J-rehearsal/{stage}-receipt.json"]
        require(receipt["stage"] == stage and receipt["status"] == "completed" and receipt["quote_eligible"] is False
                and receipt["expected_value_authorized"] is False, "Rehearsal is incomplete or authorized")
        provenance = receipt["provenance"]
        require(provenance["git_revision"] == HEAD and provenance["git_dirty"] is False, "Rehearsal source differs")
        require(all(provenance[k] == v for k, v in pipeline.hashes().items()), "Rehearsal source/input hashes differ")
        require(all(provenance[k] == v for k, v in rehearsal["execution_environment"]().items()), "Rehearsal environment differs")
        require(receipt["sample_indices"] == sample["indices"] and receipt["sensitivity_indices"] == sample["sensitivity_indices"],
                "Rehearsal sample design differs")
        require(all(provenance[k] == v for k, v in sample["provenance"].items()),
                "Rehearsal C2/full-design provenance differs")
        verify_passport(pipeline, provenance)
        require(all(row["status"] == "completed" for row in receipt["timings"]), "Failed timing cannot enter completed receipt")
        for row in receipt["timings"]:
            cache_record = json.loads(engine.cache_path(row["kind"], row["job_key"], cache=root / ".cache/jobs").read_text())
            require(cache_record["key"] == row["job_key"], "Rehearsal timing cache key differs")
        require(receipt["job_plan"] == {key: len(value) for key, value in plan.items()
                                       if key in rehearsal["STAGES"] or key == "microcosm_coverage"},
                "Rehearsal core plan differs")
        stage_workers = 1 if stage == "coverage" else 3
        require(receipt["planning_estimate"] == rehearsal["planning_estimate"](
            receipt["timings"], sample["provenance"]["full_design_unique_runs"],
            sample["provenance"]["full_design_paired_runs"], stage_workers, 1),
            "Saved rehearsal planning estimate differs")
        stages.append({"stage": stage, "status": "completed", "completed_timing_rows": len(receipt["timings"])})
    core = receipts["J-rehearsal/core-receipt.json"]
    require(core["completed_stages"] == ["central", "coverage", "scenarios", "validation"], "Core stages incomplete")
    for stage in core["completed_stages"]:
        cache_only_runner(plan[stage])
    require(rehearsal["validation_receipt"](plan["validation_modes"], cache_only_runner(plan["validation"]))
            == core["validation"], "Cached full-horizon validation receipt differs")
    require(receipts["J-rehearsal/coverage-receipt.json"]["completed_stages"] == ["coverage"],
            "Separate coverage stage incomplete")
    cache_only_runner(plan["microcosm_coverage"])
    sample_jobs = []

    def sample_runner(requested, **kwargs):
        sample_jobs.extend(requested)
        return cache_only_runner(requested, **kwargs)

    reconstructed_sample = ev.rehearsal_sample(
        inputs, root / ".cache/J-c2-dry-run", n_runs=20, n_sensitivity=2,
        workers=3, sensitivity_workers=1, runner=sample_runner, log=lambda *_: None)
    require(reconstructed_sample == receipts["J-rehearsal/sample-receipt.json"]["sample"],
            "Cached 20+2 sample receipt or identical-rates check differs")
    stage_jobs = {"core": [job for stage in core["completed_stages"] for job in plan[stage]],
                  "coverage": [*plan["coverage"], *plan["microcosm_coverage"]], "sample": sample_jobs}
    for stage, requested in stage_jobs.items():
        rows = verify_timings(engine, requested, receipts[f"J-rehearsal/{stage}-receipt.json"])
        timings.extend({**row, "source_receipt": f"J-rehearsal/{stage}-receipt.json"} for row in rows)
    unique, paired = sample["provenance"]["full_design_unique_runs"], sample["provenance"]["full_design_paired_runs"]
    plans = {"3_efrs_1_microcosm": rehearsal["planning_estimate"](timings, unique, paired, 3, 1),
             "3_efrs_2_microcosm_projection": rehearsal["planning_estimate"](timings, unique, paired, 3, 2)}
    return {"bridges": {pair: receipts[f"J-bridge-{pair}.json"] for pair in ("model-step", "certified")},
            "verification": {"run_kind": "pre_budget_completed_verification", "quote_eligible": False,
                             "label": "pre-Budget completed bridge and rehearsal; not for quoting",
                             "calculation_head": HEAD, "receipt_sha256": RECEIPTS, "bridges": verified,
                             "rehearsal_stages": stages, "c2_dry_run_verified": True,
                             "saved_passport_checks_verified": True,
                             "cached_core_and_coverage_verified": True,
                             "cached_validation_receipt_verified": True,
                             "cached_20_plus_2_sample_receipt_verified": True,
                             "full_design_unique_runs": unique, "full_design_paired_runs": paired,
                             "rehearsal_fiscal_values_omitted": True},
            "runtime": {"quote_eligible": False, "label": "pre-Budget completed cold timings; model-runtime planning estimate",
                        "calculation_head": HEAD, "receipt_sha256": RECEIPTS,
                        "runner_timings_sha256": digest(timing_bytes), "completed_runner_steps": completed_wrappers(timing_bytes.decode()),
                        "timings": timings,
                        "estimates": plans, "measured_microcosm_workers": 1,
                        "two_microcosm_workers": "projection only; concurrent memory headroom is unmeasured"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--timings", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.run_root.resolve()
    timing_bytes = args.timings.read_bytes()
    if args.verify_only:
        print(json.dumps(verify(root, timing_bytes), allow_nan=False))
        return
    # Select the calculation checkout's own committed verifiers without writing
    # its bytecode, Git metadata, dataset bytes or caches.
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env.update(PYTHONPATH=str(root / "src"), PYTHONDONTWRITEBYTECODE="1")
    env.update({name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")})
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--run-root", str(root),
                             "--timings", str(args.timings.resolve()), "--verify-only"],
                            cwd=root, env=env, check=True, stdout=subprocess.PIPE, text=True)
    payload = json.loads(result.stdout)
    atomic_receipt = runpy.run_path(str(Path(__file__).with_name("run_model_v2_j_bridge.py")))["atomic_receipt"]
    destination = Path(__file__).resolve().parents[1] / "data/pilot"

    def guard():
        read_receipts(root)
        require(args.timings.read_bytes() == timing_bytes, "Runner timing log changed during import")

    for pair, receipt in payload["bridges"].items():
        atomic_receipt(destination / f"J-bridge-{pair}.json", receipt, guard)
    certified = payload["bridges"]["certified"]
    coverage = {"run_kind": "pre_budget_coverage", "quote_eligible": False,
                "label": "pre-Budget certified GB versus DWP coverage; not for quoting",
                "minimum_contributing_records": 10, "bridge_receipt_sha256": RECEIPTS["J-bridge-certified.json"],
                "provenance": certified["provenance"], "coverage": certified["coverage"]}
    atomic_receipt(destination / "J-coverage-gb-dwp.json", coverage, guard)
    atomic_receipt(destination / "J-completed-verification.json", payload["verification"], guard)
    atomic_receipt(destination / "J-runtime-planning.json", payload["runtime"], guard)
    print("Verified and imported two bridge receipts, certified coverage and safe completion/runtime metadata; no model jobs.")


if __name__ == "__main__":
    main()
