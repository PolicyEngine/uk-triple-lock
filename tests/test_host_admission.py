"""Host admission: a fixed memory floor, and a load limit of TRIPLE_LOCK_MAX_LOAD_PER_CPU (default 6) per CPU.

No model job, survey or real host reading: every reading here is synthetic.
"""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from scripts import run_model_v2_j_bridge as bridge
from triple_lock import engine, host

ENV = host.MAX_LOAD_PER_CPU_ENV


def rehearsal_driver():
    path = Path(__file__).parents[1] / "scripts/run_model_v2_j_rehearsal.py"
    spec = importlib.util.spec_from_file_location("host_admission_rehearsal_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REHEARSAL = rehearsal_driver()


@pytest.fixture(autouse=True)
def no_configured_limit(monkeypatch):
    """Each test starts from the default; a developer's own setting must not decide a test."""
    monkeypatch.delenv(ENV, raising=False)


# ── Configuration ───────────────────────────────────────────────────────


def test_default_is_six_times_the_cpu_count():
    assert host.DEFAULT_MAX_LOAD_PER_CPU == 6
    assert host.configuration() == {"max_load_per_cpu": 6.0, "source": "default", "environment_variable": ENV}
    applied = host.assess(100, 0, 18, 40)
    assert applied["load_limit"] == 108 and applied["max_load_per_cpu"] == 6
    assert host.assess(100, 0, 4, 40)["load_limit"] == 24


def test_environment_overrides_the_default(monkeypatch):
    monkeypatch.setenv(ENV, "3")
    assert host.configuration() == {"max_load_per_cpu": 3.0, "source": "environment", "environment_variable": ENV}
    assert host.assess(100, 54, 18, 40) == {"minimum_available_gib": 40, "max_load_per_cpu": 3.0,
                                            "load_limit": 54.0, "admitted": True}
    assert host.assess(100, 54.01, 18, 40)["admitted"] is False
    monkeypatch.setenv(ENV, "2.5")
    assert host.assess(100, 0, 4, 40)["load_limit"] == 10


def test_a_runner_flag_overrides_the_environment(monkeypatch):
    monkeypatch.setenv(ENV, "3")
    assert host.configuration(10) == {"max_load_per_cpu": 10.0, "source": "flag", "environment_variable": ENV}
    assert host.assess(100, 150, 18, 40, max_load_per_cpu=10)["admitted"] is True


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_environment_variable_is_the_default(monkeypatch, blank):
    monkeypatch.setenv(ENV, blank)
    assert host.configuration()["source"] == "default" and host.max_load_per_cpu() == 6


@pytest.mark.parametrize("bad", ["0", "-1", "nan", "inf", "-inf", "six", "1e400"])
def test_a_malformed_environment_limit_is_refused_never_read_as_no_limit(monkeypatch, bad):
    monkeypatch.setenv(ENV, bad)
    with pytest.raises(ValueError, match=ENV):
        host.configuration()
    with pytest.raises(ValueError, match=ENV):
        host.assess(100, 0, 18, 40)


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, -math.inf, "six"])
def test_a_malformed_flag_is_refused_whatever_the_environment(monkeypatch, bad):
    monkeypatch.setenv(ENV, "6")
    with pytest.raises(ValueError, match="--max-load-per-cpu"):
        host.configuration(bad)


@pytest.mark.parametrize("cpus", [0, -1, None, 2.0, True])
def test_the_cpu_count_must_be_a_positive_integer(cpus):
    with pytest.raises(ValueError, match="cpu_count"):
        host.assess(100, 0, cpus, 40)


# ── Admission ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("floor", [8, 40, 80, 120])
@pytest.mark.parametrize("load", [0, 1, 36, 107.9, 1e6])
def test_memory_below_the_floor_refuses_whatever_the_load(floor, load):
    assert host.assess(floor - 0.01, load, 18, floor)["admitted"] is False
    assert host.refuses(floor - 0.01, load, minimum_gib=floor, load_limit=math.inf)


@pytest.mark.parametrize("load", [36.01, 50, 66.11, 72, 100, 108])
def test_load_between_two_and_six_times_the_cpus_no_longer_refuses(load):
    """2x was the old cutoff (36 on 18 CPUs); 66.11 was a refused Part J reading on 11 October."""
    assert host.assess(57, load, 18, 40)["admitted"] is True


@pytest.mark.parametrize("load", [108.01, 220.12, 252.84, 333.82])
def test_load_above_six_times_the_cpus_still_refuses(load):
    """The other Part J readings (18 CPUs, about 57 GiB free) remain above the new limit."""
    assert host.assess(57, load, 18, 40)["admitted"] is False


@pytest.mark.parametrize("memory,load", [(math.nan, 0), (100, math.nan), (math.inf, 0), (100, -math.inf)])
def test_a_reading_that_is_not_finite_refuses(memory, load):
    assert host.assess(memory, load, 18, 40)["admitted"] is False


def test_measure_reads_memory_load_and_cpus(monkeypatch):
    monkeypatch.setattr(host.psutil, "virtual_memory", lambda: SimpleNamespace(available=50 * 2**30))
    monkeypatch.setattr(host.os, "getloadavg", lambda: (66.11, 1.0, 2.0))
    monkeypatch.setattr(host.os, "cpu_count", lambda: None)
    assert host.measure() == {"available_gib": 50, "load_1m": 66.11, "cpu_count": 1}


def test_admission_is_outside_the_job_cache_key():
    """Admission never changes what a job computes, so editing it must rerun nothing."""
    assert "host.py" not in engine.ENGINE_FILES
    assert "host.py" not in engine.engine_semantics()


# ── Properties ──────────────────────────────────────────────────────────


finite = dict(allow_nan=False, allow_infinity=False)


@st.composite
def readings(draw):
    """A floor, CPU count and per-CPU limit, with memory and load drawn at, beside and away from both edges."""
    floor = draw(st.one_of(st.sampled_from([8, 40, 80, 120]), st.floats(0, 512, **finite)))
    cpus = draw(st.integers(1, 1024))
    per_cpu = draw(st.one_of(st.sampled_from([1, 2, 6, 10]), st.floats(0.01, 1000, **finite)))
    limit = per_cpu * cpus
    memory = draw(st.one_of(st.sampled_from([floor, math.nextafter(floor, -math.inf), math.nextafter(floor, math.inf)]),
                            st.floats(0, 4096, **finite)))
    load = draw(st.one_of(st.sampled_from([limit, math.nextafter(limit, -math.inf), math.nextafter(limit, math.inf),
                                           2 * cpus, 0.0]),
                          st.floats(0, 1e6, **finite)))
    return SimpleNamespace(memory=memory, load=load, cpus=cpus, floor=floor, per_cpu=per_cpu)


@settings(max_examples=2000, deadline=None)
@given(readings())
def test_refuses_if_and_only_if_memory_is_below_the_floor_or_load_is_above_the_limit(r):
    applied = host.assess(r.memory, r.load, r.cpus, r.floor, max_load_per_cpu=r.per_cpu)
    refused = r.memory < r.floor or r.load > r.per_cpu * r.cpus
    assert applied["admitted"] is not refused
    assert applied == {"minimum_available_gib": r.floor, "max_load_per_cpu": float(r.per_cpu),
                       "load_limit": r.per_cpu * r.cpus, "admitted": not refused}
    assert host.refuses(r.memory, r.load, minimum_gib=r.floor, load_limit=applied["load_limit"]) is refused


@settings(max_examples=500, deadline=None)
@given(st.floats(min_value=1e-6, max_value=1e6, **finite))
def test_any_positive_finite_environment_setting_round_trips(per_cpu):
    configured = host.configuration(environ={ENV: repr(per_cpu)})
    assert configured == {"max_load_per_cpu": per_cpu, "source": "environment", "environment_variable": ENV}


@settings(max_examples=500, deadline=None)
@given(readings())
def test_both_runners_admit_exactly_as_the_shared_helper(r):
    """Differential: the bridge's and rehearsal's admission agree with host.assess on every reading."""
    refused = not host.assess(r.memory, r.load, r.cpus, r.floor, max_load_per_cpu=r.per_cpu)["admitted"]
    snapshot = {"available_gib": r.memory, "load_1m": r.load, "cpu_count": r.cpus}
    applied = REHEARSAL.host_limits(snapshot, r.floor, r.per_cpu)
    assert applied["admitted"] is not refused
    if refused:
        with pytest.raises(host.HostSaturated, match="host memory or load"):
            REHEARSAL.check_host(snapshot, applied)
    else:
        REHEARSAL.check_host(snapshot, applied)
    # The bridge's floor is fixed at 40 GiB; compare it on the same load, CPUs and limit.
    bridge_refused = r.memory < 40 or r.load > r.per_cpu * r.cpus
    with mock.patch.object(bridge.host, "measure", lambda: dict(snapshot)):
        if bridge_refused:
            with pytest.raises(host.HostSaturated, match="Host saturated"):
                bridge.memory_check(max_load_per_cpu=r.per_cpu)
        else:
            recorded = bridge.memory_check(max_load_per_cpu=r.per_cpu)
            assert recorded == {**snapshot, "minimum_available_gib": 40, "max_load_per_cpu": float(r.per_cpu),
                                "load_limit": r.per_cpu * r.cpus, "admitted": True}
