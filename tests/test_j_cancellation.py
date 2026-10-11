"""Synthetic completion races must not turn a saturation stop into timings."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def driver():
    path = Path(__file__).parents[1] / "scripts/run_model_v2_j_rehearsal.py"
    spec = importlib.util.spec_from_file_location("j_cancellation_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_runner(monkeypatch, tmp_path):
    rehearsal = driver()
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: {
        "available_gib": 100, "load_1m": 0, "cpu_count": 4, "vm_stat": "synthetic healthy host"})
    for namespace in (rehearsal.engine, rehearsal.jobs):
        monkeypatch.setattr(namespace, "engine_semantics", lambda: {})
        monkeypatch.setattr(namespace, "package_versions", lambda: {})
        monkeypatch.setattr(namespace, "cached", lambda *a, **kw: None)
    monkeypatch.setattr(rehearsal.jobs, "WORKDIRS", tmp_path / "workers")
    report = {"host_checks": [], "timings": [], "batches": []}
    return rehearsal, report, rehearsal.TimedJobs(report, lambda: None)


def test_child_success_racing_stop_is_not_a_completed_cold_measurement(monkeypatch, tmp_path):
    rehearsal, report, runner = setup_runner(monkeypatch, tmp_path)

    def completed_child(kind, argument, workdir, semantics, stop):
        stop.set()  # monitor cancellation arrives immediately before completion
        return {"synthetic_complete_child": True}

    monkeypatch.setattr(rehearsal.jobs, "_run_isolated", completed_child)
    real_scheduler = rehearsal.jobs.run_jobs
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda requested, **kw:
                        real_scheduler(requested, cache=tmp_path / "cache", **kw))
    with pytest.raises(RuntimeError, match="failed"):
        runner([("path", {"synthetic": True})], log=lambda _: None)
    assert runner.stop.is_set()
    assert len(report["timings"]) == 1
    assert report["timings"][0]["status"] == "failed"
    assert report["batches"] == []
    assert rehearsal.planning_estimate(report["timings"], 161, 40, 3, 2)["measured_types"] == {}


def test_monitor_cancellation_during_join_is_not_a_completed_cold_measurement(monkeypatch, tmp_path):
    rehearsal, report, runner = setup_runner(monkeypatch, tmp_path)
    phases = []

    class JoiningMonitor:
        def __init__(self, *, target, name, daemon):
            assert name == "rehearsal-host-monitor" and daemon is True

        def start(self):
            phases.append("monitor_started")

        def join(self):
            # An in-flight host check finishes during monitor teardown,
            # after the successful child returned with no cancellation.
            assert phases == ["monitor_started", "child_completed"]
            assert not runner.stop.is_set()
            runner.stop.set()
            phases.append("cancelled_during_join")

    # Replace only this driver's thread factory: the real scheduler still
    # uses its own worker pool, locks and cancellation event.
    monkeypatch.setattr(rehearsal, "threading", SimpleNamespace(
        Event=rehearsal.threading.Event, Thread=JoiningMonitor))

    def completed_child(kind, argument, workdir, semantics, stop):
        assert stop is runner.stop and not stop.is_set()
        phases.append("child_completed")
        return {"synthetic_complete_child": True}

    monkeypatch.setattr(rehearsal.jobs, "_run_isolated", completed_child)
    real_scheduler = rehearsal.jobs.run_jobs
    cache = tmp_path / "cache"
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda requested, **kw:
                        real_scheduler(requested, cache=cache, **kw))
    with pytest.raises(RuntimeError, match="failed"):
        runner([("path", {"synthetic": True})], log=lambda _: None)
    assert phases == ["monitor_started", "child_completed", "cancelled_during_join"]
    assert runner.stop.is_set()
    assert len(report["timings"]) == 1
    assert report["timings"][0]["status"] == "failed"
    assert report["batches"] == []
    assert list(cache.glob("*.json")) == []
    assert rehearsal.planning_estimate(report["timings"], 161, 40, 3, 2)["measured_types"] == {}


def test_batch_success_racing_stop_cannot_record_completed_batch(monkeypatch, tmp_path):
    rehearsal, report, runner = setup_runner(monkeypatch, tmp_path)

    def completed_scheduler(requested, **kwargs):
        kwargs["stop"].set()
        return [{"synthetic_complete_child": True}]

    monkeypatch.setattr(rehearsal.jobs, "run_jobs", completed_scheduler)
    with pytest.raises(rehearsal.jobs.Aborted, match="stopped during the model batch"):
        runner([("path", {"synthetic": True})], log=lambda _: None)
    assert runner.stop.is_set()
    assert report["timings"] == []
    assert report["batches"] == []
