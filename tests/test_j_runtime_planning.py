"""Planning extrapolation from synthetic wall times; no PolicyEngine jobs."""

import importlib.util
from pathlib import Path

import pytest


def driver():
    path = Path(__file__).parents[1] / "scripts/run_model_v2_j_rehearsal.py"
    spec = importlib.util.spec_from_file_location("j_runtime_planning_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed_timings():
    return [{"dataset": dataset, "kind": kind, "wall_seconds": 3600.,
             "cache": "cold", "status": "completed"}
            for dataset, kinds in (("efrs", ("path", "coverage", "history")),
                                   ("microcosm", ("path", "coverage")))
            for kind in kinds]


@pytest.mark.parametrize("primary_passes", [True, False])
def test_worker_caps_do_not_halve_serial_paths_or_coverage(primary_passes):
    rehearsal = driver()
    key = "primary_passes" if primary_passes else "primary_fails"
    one = rehearsal.planning_estimate(completed_timings(), 161, 40, 1, 1)["post_Budget_build_plus_validation"][key]
    two = rehearsal.planning_estimate(completed_timings(), 161, 40, 2, 2)["post_Budget_build_plus_validation"][key]
    # Central, OBR wedge, primary coverage and Microcosm coverage each take a
    # full synthetic hour under either worker configuration.
    assert one["serial_jobs"] == two["serial_jobs"] == {
        "efrs": {"path": 2, "coverage": 1}, "microcosm": {"coverage": 1}}
    assert sum(sum(counts.values()) for counts in one["serial_jobs"].values()) == 4
    assert two["planned_stage_wall_hours"] == pytest.approx(4 + (one["planned_stage_wall_hours"] - 4) / 2)
    assert two["planned_stage_wall_hours"] == pytest.approx(two["ideal_parallel_wall_hours"] + 2)
    assert two["planned_stage_wall_hours"] > one["planned_stage_wall_hours"] / 2


def test_runtime_planning_preserves_gate_job_counts_and_labels_bound():
    estimate = driver().planning_estimate(completed_timings(), 161, 40, 3, 2)
    outcomes = estimate["post_Budget_build_plus_validation"]
    assert sum(outcomes["primary_passes"]["enhanced_frs_jobs"].values()) == 705
    assert sum(outcomes["primary_fails"]["enhanced_frs_jobs"].values()) == 505
    assert sum(outcomes["primary_passes"]["microcosm_jobs"].values()) == 41
    assert sum(outcomes["primary_fails"]["microcosm_jobs"].values()) == 1
    for row in outcomes.values():
        for dataset, field in (("efrs", "enhanced_frs_jobs"), ("microcosm", "microcosm_jobs")):
            assert {kind: count + row["serial_jobs"][dataset].get(kind, 0)
                    for kind, count in row["parallel_jobs"][dataset].items()} == row[field]
        # Three serial Enhanced FRS jobs add 2 hours relative to /3;
        # serial Microcosm coverage adds half an hour relative to /2.
        assert row["planned_stage_wall_hours"] == pytest.approx(row["ideal_parallel_wall_hours"] + 2.5)
    assert "planning estimate" in estimate["label"]
    assert "optimistic" in estimate["optimistic_bound"]
    assert "partial worker batches" in estimate["limitations"]


@pytest.mark.parametrize("missing_type", [("efrs", "path"), ("efrs", "coverage"),
                                         ("efrs", "history"), ("microcosm", "coverage")])
def test_missing_required_job_types_leave_both_planning_estimates_unavailable(missing_type):
    timings = [row for row in completed_timings() if (row["dataset"], row["kind"]) != missing_type]
    estimate = driver().planning_estimate(timings, 161, 40, 3, 2)
    for row in estimate["post_Budget_build_plus_validation"].values():
        assert row["ideal_parallel_wall_hours"] is None
        assert row["planned_stage_wall_hours"] is None
        assert ".".join(missing_type) in row["unmeasured_job_types"]


def test_missing_microcosm_paths_only_blocks_the_primary_pass_design():
    timings = [row for row in completed_timings() if (row["dataset"], row["kind"]) != ("microcosm", "path")]
    outcomes = driver().planning_estimate(timings, 161, 40, 3, 2)["post_Budget_build_plus_validation"]
    assert outcomes["primary_passes"]["planned_stage_wall_hours"] is None
    assert outcomes["primary_fails"]["planned_stage_wall_hours"] is not None
    assert outcomes["primary_fails"]["unmeasured_job_types"] == []


def test_warm_or_failed_jobs_cannot_supply_runtime_measurements():
    timings = [{"dataset": "efrs", "kind": "path", "wall_seconds": 1., "cache": "warm", "status": "completed"},
               {"dataset": "efrs", "kind": "path", "wall_seconds": 2., "cache": "cold", "status": "failed"}]
    estimate = driver().planning_estimate(timings, 161, 40, 3, 2)
    assert estimate["measured_types"] == {}
    for row in estimate["post_Budget_build_plus_validation"].values():
        assert row["ideal_parallel_wall_hours"] is None
        assert row["planned_stage_wall_hours"] is None
