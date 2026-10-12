"""The ordinary build's real job scheduler admits against synthetic host readings."""

import json
from unittest import mock

import pytest
from hypothesis import given, settings, strategies as st

from triple_lock import cli, engine, host, jobs, pipeline
from triple_lock.config import SENSITIVITY_DATASET


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
        assert not launched and not list(cache.glob("*.json"))


@pytest.mark.parametrize("workers", [1, 2])
def test_microcosm_batch_reserves_forty_gib_per_worker(scheduler, monkeypatch, workers):
    run, launched, _ = scheduler
    work = [("path", {"dataset": SENSITIVITY_DATASET})]
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 40 * workers - 0.01,
                                                 "load_1m": 0, "cpu_count": 18})
    with pytest.raises(host.HostSaturated):
        run(work, workers)
    assert not launched
    monkeypatch.setattr(host, "measure", lambda: {"available_gib": 40 * workers,
                                                 "load_1m": 0, "cpu_count": 18})
    decisions = run(work, workers)[0]["model"]["host_admission"]
    assert decisions["batch"]["minimum_available_gib"] == 40 * workers
    assert decisions["launch"]["minimum_available_gib"] == 40


@pytest.mark.parametrize("memory,load", [(39.99, 0), (100, 108.01)])
def test_host_is_rechecked_after_slot_acquisition_before_any_child(scheduler, monkeypatch, memory, load):
    run, launched, cache = scheduler
    readings = iter([{"available_gib": 100, "load_1m": 0, "cpu_count": 18},
                     {"available_gib": memory, "load_1m": load, "cpu_count": 18}])

    def measure():
        reading = next(readings)
        if reading["available_gib"] == memory and reading["load_1m"] == load:
            assert (jobs.WORKDIRS / "slot0" / ".lock").read_text().startswith("pid ")
        return reading

    monkeypatch.setattr(host, "measure", measure)
    with pytest.raises(RuntimeError, match="admission refused") as error:
        run([("path", {"i": i}) for i in range(3)])
    (refusal,) = error.value.host_admissions
    assert refusal["phase"] == "after_slot_acquisition" and refusal["admitted"] is False
    assert refusal["available_gib"] == memory and refusal["load_1m"] == load
    assert not launched and not list(cache.glob("*.json"))


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
def test_cli_defaults_to_one_microcosm_worker(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setattr(pipeline, "build", lambda **kwargs: (calls.append(kwargs) or {}, {}))
    monkeypatch.setattr(pipeline, "write", lambda *args: None)
    assert cli.main(arguments) == 0
    assert calls[0]["sensitivity_workers"] == expected


def test_build_admission_is_outside_fiscal_cache_semantics():
    assert "jobs.py" not in engine.ENGINE_FILES
