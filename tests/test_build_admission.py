"""The ordinary build's real job scheduler admits against synthetic host readings."""

import json
import threading
from unittest import mock

import pytest
from hypothesis import given, settings, strategies as st

from scripts import run_model_v2_j_bridge as bridge
from triple_lock import cli, engine, host, jobs, pipeline
from triple_lock.config import PRIMARY_DATASET, SENSITIVITY_DATASET


@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    monkeypatch.delenv(host.MAX_LOAD_PER_CPU_ENV, raising=False)
    monkeypatch.setattr(jobs, "WORKDIRS", tmp_path / "workers")
    monkeypatch.setattr(jobs, "engine_semantics", lambda: {"synthetic": "engine"})
    monkeypatch.setattr(jobs, "package_versions", lambda: {"synthetic": "packages"})
    launched = []

    def isolated(kind, arg, workdir, semantics, stop):
        launched.append((kind, arg))
        return {"saving_bn": 1.0, "model": {"dataset": "synthetic"}}

    monkeypatch.setattr(jobs, "_run_isolated", isolated)

    def run(work=None, workers=1):
        return jobs.run_jobs(work or [("path", {})], workers=workers, cache=tmp_path / "cache", log=lambda _: None)

    return run, launched, tmp_path / "cache"


@pytest.mark.parametrize("memory,load,admitted", [
    (40, 108, True), (39.99, 0, False), (100, 108.01, False), (39.99, 108.01, False),
])
def test_build_admission_boundaries(scheduler, monkeypatch, memory, load, admitted):
    run, launched, cache = scheduler
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": memory, "load_1m": load, "cpu_count": 18})
    if admitted:
        result = run()[0]
        decisions = result["model"]["host_admission"]
        assert decisions["batch"]["phase"] == "before_batch"
        assert decisions["launch"]["phase"] == "after_slot_acquisition"
        for decision in decisions.values():
            assert decision["available_gib"] == memory and decision["load_1m"] == load
            assert decision["minimum_available_gib"] == 40
            assert decision["load_limit"] == 108 and decision["admitted"] is True
        (record,) = cache.glob("*.json")
        assert json.loads(record.read_text())["host_admission"] == decisions
        assert launched == [("path", {})]
    else:
        with pytest.raises(host.HostSaturated) as error:
            run()
        assert error.value.host_admission["admitted"] is False
        assert error.value.host_admissions == [error.value.host_admission]
        assert not launched and not list(cache.glob("*.json"))


@pytest.mark.parametrize("workers,count", [(1, 1), (2, 1), (2, 2), (3, 1), (3, 2), (3, 4)])
def test_microcosm_batch_reserves_forty_gib_per_concurrent_uncached_job(scheduler, monkeypatch, workers, count):
    run, launched, _ = scheduler
    work = [("path", {"dataset": PRIMARY_DATASET, "i": i}) for i in range(count)]
    floor = 40 * min(workers, count)
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": floor - 0.01,
                                                 "load_1m": 0, "cpu_count": 18})
    with pytest.raises(host.HostSaturated) as error:
        run(work, workers)
    assert error.value.host_admission["minimum_available_gib"] == floor
    assert not launched
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": floor,
                                                 "load_1m": 0, "cpu_count": 18})
    decisions = run(work, workers)[0]["model"]["host_admission"]
    assert decisions["batch"]["minimum_available_gib"] == floor
    assert decisions["launch"]["minimum_available_gib"] == 40


def test_microcosm_batch_floor_counts_only_uncached_microcosm_jobs(scheduler, monkeypatch):
    run, launched, _ = scheduler
    work = [("path", {"dataset": PRIMARY_DATASET, "i": i}) for i in range(3)]
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 120, "load_1m": 0, "cpu_count": 18})
    run(work[:2], workers=3)
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 40, "load_1m": 0, "cpu_count": 18})
    result = run(work + [("path", {"dataset": SENSITIVITY_DATASET, "i": "enhanced-frs"})], workers=3)
    assert result[2]["model"]["host_admission"]["batch"]["minimum_available_gib"] == 40
    assert len(launched) == 4


@pytest.mark.parametrize("memory,load", [(39.99, 0), (100, 108.01)])
def test_host_is_rechecked_after_slot_acquisition_before_any_child(scheduler, monkeypatch, memory, load):
    run, launched, cache = scheduler
    readings = iter([{"available_gib": 120, "load_1m": 0, "cpu_count": 18},
                     {"available_gib": memory, "load_1m": load, "cpu_count": 18}])

    def measure():
        reading = next(readings)
        if reading["available_gib"] == memory and reading["load_1m"] == load:
            assert (jobs.WORKDIRS / "slot0" / ".lock").read_text().startswith("pid ")
        return reading

    monkeypatch.setattr(host, "measure", measure)
    with pytest.raises(host.HostSaturated, match="admission refused") as error:
        run([("path", {"i": i}) for i in range(3)])
    (refusal,) = error.value.host_admissions
    assert refusal["phase"] == "after_slot_acquisition" and refusal["admitted"] is False
    assert refusal["available_gib"] == memory and refusal["load_1m"] == load
    assert not launched and not list(cache.glob("*.json"))


def test_launch_refusal_preserves_host_decisions_and_other_concurrent_failures(scheduler, monkeypatch):
    run, _, cache = scheduler
    runner_started, refusal_ready = threading.Event(), threading.Event()
    lock, launch_count = threading.Lock(), [0]
    refused = {"phase": "after_slot_acquisition", "admitted": False, "available_gib": 39,
               "minimum_available_gib": 40, "load_1m": 0, "cpu_count": 18, "load_limit": 108}

    def admission(minimum_gib, phase):
        if phase == "before_batch":
            return {"phase": phase, "admitted": True}
        with lock:
            launch_count[0] += 1
            first = launch_count[0] == 1
        if first:
            return {"phase": phase, "admitted": True}
        assert runner_started.wait(10)
        refusal_ready.set()
        raise host.HostSaturated("synthetic host refusal", decisions=[refused])

    def isolated(*args):
        runner_started.set()
        assert refusal_ready.wait(10)
        raise ValueError("synthetic model failure")

    monkeypatch.setattr(jobs, "host_admission", admission)
    monkeypatch.setattr(jobs, "_run_isolated", isolated)
    with pytest.raises(host.HostSaturated) as error:
        run([("path", {"i": i}) for i in range(2)], workers=2)
    assert error.value.host_admissions == [refused]
    assert "synthetic host refusal" in str(error.value)
    assert "synthetic model failure" in str(error.value)
    assert not list(cache.glob("*.json"))


def test_cached_job_keeps_launch_provenance_and_needs_no_host_admission(scheduler, monkeypatch):
    run, launched, _ = scheduler
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 100, "load_1m": 0, "cpu_count": 18})
    original = run()[0]
    monkeypatch.setattr(host, "measure", lambda: pytest.fail("cached job launched no process"))
    cached = run()[0]
    assert cached["model"]["host_admission"] == original["model"]["host_admission"]
    assert cached["model"]["host_admission_cache_hit"] is True
    assert len(launched) == 1


def test_build_uses_the_environment_load_limit(scheduler, monkeypatch):
    run, launched, _ = scheduler
    monkeypatch.setenv(host.MAX_LOAD_PER_CPU_ENV, "2")
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 100, "load_1m": 36.01, "cpu_count": 18})
    with pytest.raises(host.HostSaturated) as error:
        run()
    assert error.value.host_admission["load_limit"] == 36
    assert not launched


@pytest.mark.parametrize("before_memory,before_load,launch_memory,launch_load,flag,admitted", [
    (100, 150, 100, 150, 10, True),
    (100, 150, 100, 150, 150 / 18, True),
    (100, 150, 100, 150, 8, False),
    (39.99, 150, 100, 150, 10, False),
    (100, 0, 100, 150, 8, False),
    (100, 150, 39.99, 150, 10, False),
])
def test_bridge_flag_governs_before_batch_and_actual_scheduler_admission(
    scheduler, monkeypatch, before_memory, before_load, launch_memory, launch_load, flag, admitted
):
    """The bridge's flag must survive its callback into the ordinary scheduler."""
    _, launched, cache = scheduler
    monkeypatch.setenv(host.MAX_LOAD_PER_CPU_ENV, "6")
    decisions = []
    real_assess = host.assess

    def inside_slot():
        path = jobs.WORKDIRS / "J-bridge-efrs0" / ".lock"
        return path.is_file() and path.read_text().startswith("pid ")

    def measure():
        memory, load = (launch_memory, launch_load) if inside_slot() else (before_memory, before_load)
        return {"available_gib": memory, "load_1m": load, "cpu_count": 18}

    def assess(*args, **kwargs):
        decision = real_assess(*args, **kwargs)
        decisions.append({"phase": "after_slot_acquisition" if inside_slot() else "before_batch", **decision})
        return decision

    monkeypatch.setattr(host, "measure", measure)
    monkeypatch.setattr(host, "assess", assess)

    def run_bridge_batch():
        # This is the bridge main's pre-batch check followed by its real batch
        # runner and real scheduler, with only the model process replaced.
        bridge.memory_check(max_load_per_cpu=flag)
        return bridge.run_batch([("central", ("path", {}))], 1, cache,
                                monitor_interval=60, max_load_per_cpu=flag)

    if admitted:
        assert run_bridge_batch()[0]["saving_bn"] == 1.0
        assert launched == [("path", {})]
        assert all(decision["admitted"] for decision in decisions)
    else:
        with pytest.raises(RuntimeError, match="Host saturated|host saturation"):
            run_bridge_batch()
        assert not launched and not list(cache.glob("*.json"))
        assert decisions[-1]["admitted"] is False
    expected_phases = ["before_batch"]
    if before_memory >= 40 and before_load <= flag * 18:
        expected_phases.append("after_slot_acquisition")
    assert [decision["phase"] for decision in decisions] == expected_phases
    assert all(decision["max_load_per_cpu"] == flag and decision["load_limit"] == flag * 18
               and decision["minimum_available_gib"] == 40 for decision in decisions)


@settings(max_examples=200, deadline=None)
@given(memory=st.floats(0, 200, allow_nan=False, allow_infinity=False),
       load=st.floats(0, 300, allow_nan=False, allow_infinity=False))
def test_build_refuses_if_and_only_if_below_memory_floor_or_above_load_limit(memory, load):
    reading = {"available_gib": memory, "load_1m": load, "cpu_count": 18}
    with mock.patch.object(host, "measure", return_value=reading), mock.patch.dict(
        "os.environ", {host.MAX_LOAD_PER_CPU_ENV: "6"}
    ):
        if memory < 40 or load > 108:
            with pytest.raises(host.HostSaturated):
                jobs.host_admission(40, "test")
        else:
            assert jobs.host_admission(40, "test")["admitted"] is True


@pytest.mark.parametrize("arguments,expected", [([], 1), (["--sensitivity-workers", "2"], 2)])
def test_cli_defaults_to_one_sensitivity_worker(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setattr(pipeline, "build", lambda **kwargs: (calls.append(kwargs) or {}, {}))
    monkeypatch.setattr(pipeline, "write", lambda *args: None)
    assert cli.main(arguments) == 0
    assert calls[0]["sensitivity_workers"] == expected


def test_build_admission_is_outside_fiscal_cache_semantics():
    assert "jobs.py" not in engine.ENGINE_FILES


def test_implicit_microcosm_primary_reserves_three_workers_without_penalizing_efrs(scheduler, monkeypatch):
    run, launched, _ = scheduler
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 119.99, "load_1m": 0, "cpu_count": 18})
    with pytest.raises(host.HostSaturated) as error:
        run([("path", {"i": i}) for i in range(3)], workers=3)
    assert error.value.host_admission["minimum_available_gib"] == 120
    assert not launched
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 40, "load_1m": 0, "cpu_count": 18})
    result = run([("path", {"dataset": SENSITIVITY_DATASET, "i": i}) for i in range(3)], workers=3)
    assert all(row["model"]["host_admission"]["batch"]["minimum_available_gib"] == 40 for row in result)
