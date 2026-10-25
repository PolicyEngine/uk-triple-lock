"""The bridge's memory floors and observations, on the real scheduler with synthetic jobs.

Every floor reads host-wide available memory, which already excludes the
batch's own resident jobs. So no floor may reserve room for a job that is
already resident: before a batch the caller keeps 40 GiB for each cold job,
each acquired slot keeps 40 GiB for the one job it admits, and the monitor,
which runs while the batch's jobs are resident, keeps only the host's safety
floor. No model or survey data.
"""

import contextlib
import subprocess
import sys
import threading

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from scripts import run_model_v2_j_bridge as bridge

MICROCOSM = "microcosm_uk_2024_25@a133f37a"
EFRS = "enhanced_frs_2024_25@1.58.0"
CPUS = 18


def scheduler(monkeypatch, tmp_path, runner):
    """The actual scheduler, with no package probe, cache hit or model child."""
    monkeypatch.setattr(bridge.jobs, "WORKDIRS", tmp_path / "workers")
    monkeypatch.setattr(bridge.jobs, "engine_semantics", lambda: {"synthetic": "scheduler"})
    monkeypatch.setattr(bridge.jobs, "package_versions", lambda: {})
    monkeypatch.setattr(bridge.jobs, "cached", lambda *a, **kw: None)
    monkeypatch.setattr(bridge.jobs, "_run_isolated", runner)
    monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)


def paths(datasets):
    """Distinct path jobs (distinct cache keys) on the given datasets."""
    return [(str(i), ("path", {"dataset": dataset, "draw": i})) for i, dataset in enumerate(datasets)]


class SequentialHost:
    """Each job is admitted only once the jobs before it are resident; available = before - their memory."""

    def __init__(self, before, residents):
        self.before, self.residents = before, residents
        self.changed = threading.Condition()
        self.entered = self.resident = 0
        self.sampled = threading.Event()  # the monitor has read the host with every job resident

    def available(self):
        return max(self.before - sum(self.residents[:self.resident]), 0.0)

    def measure(self):
        with self.changed:
            if self.resident == len(self.residents):
                self.sampled.set()
            return {"available_gib": self.available(), "load_1m": 0.0, "cpu_count": CPUS}

    @contextlib.contextmanager
    def slot_lock(self, workdir, *args, stop=None, **kwargs):
        with self.changed:
            order, self.entered = self.entered, self.entered + 1
            while self.resident < order and not stop.is_set():
                self.changed.wait(.005)
        yield

    def runner(self, kind, arg, workdir, engine, stop):
        with self.changed:
            self.resident += 1
            self.changed.notify_all()
        while not (self.sampled.is_set() or stop.is_set()):
            self.sampled.wait(.005)
        return {"safe": True}

    def install(self, monkeypatch, tmp_path):
        scheduler(monkeypatch, tmp_path, self.runner)
        monkeypatch.setattr(bridge.jobs, "slot_lock", self.slot_lock)
        monkeypatch.setattr(bridge.host, "measure", self.measure)


def test_floors_reserve_room_only_for_jobs_about_to_load():
    assert bridge.batch_resources(paths([MICROCOSM] * 2), 2)["minimum_gib"] == 2 * bridge.COLD_JOB_MINIMUM_GIB
    assert bridge.batch_resources(paths([MICROCOSM, EFRS]), 2)["minimum_gib"] == bridge.COLD_JOB_MINIMUM_GIB
    assert bridge.batch_resources(paths([EFRS] * 3), 3)["minimum_gib"] == bridge.COLD_JOB_MINIMUM_GIB
    assert 0 < bridge.RUNNING_MINIMUM_GIB < bridge.COLD_JOB_MINIMUM_GIB


def test_each_slot_keeps_one_cold_floor_and_the_monitor_the_running_floor(monkeypatch, tmp_path):
    floors, ticked = [], threading.Event()

    def memory_check(max_load_per_cpu=None, minimum_gib=40):
        floors.append(minimum_gib)
        if minimum_gib == bridge.RUNNING_MINIMUM_GIB:
            ticked.set()
        return {"available_gib": 90.0, "load_1m": 0.0}

    def runner(kind, arg, workdir, engine, stop):
        assert ticked.wait(10)
        return {"safe": True}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "memory_check", memory_check)
    assert bridge.run_batch(paths([MICROCOSM] * 2), 2, tmp_path / "cache", monitor_interval=.01) == [{"safe": True}] * 2
    assert floors.count(bridge.COLD_JOB_MINIMUM_GIB) == 2
    assert set(floors) == {bridge.COLD_JOB_MINIMUM_GIB, bridge.RUNNING_MINIMUM_GIB}


def test_a_resident_microcosm_job_does_not_trip_its_own_admission_floor(monkeypatch, tmp_path):
    """24 October, 23:55Z: 54.5 GiB available before any job; a ~30 GiB worker leaves about 25 GiB."""
    host = SequentialHost(54.5, [29.5])
    host.install(monkeypatch, tmp_path)
    observed = {}
    assert bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache",
                            monitor_interval=.01, observed=observed) == [{"safe": True}]
    assert observed["samples"] >= 1 and observed["minimum_available_gib"] == 25.0


def test_a_second_slot_counts_the_first_resident_job_once(monkeypatch, tmp_path):
    """92.6 GiB before; the first Microcosm job leaves 74.5 GiB, room for the second job's 40 GiB but not for 80."""
    host = SequentialHost(92.6, [18.1, 18.1])
    host.install(monkeypatch, tmp_path)
    assert bridge.run_batch(paths([MICROCOSM] * 2), 2, tmp_path / "cache", monitor_interval=.01) == [{"safe": True}] * 2


def test_the_monitor_still_stops_the_batch_below_the_running_floor(monkeypatch, tmp_path):
    host = SequentialHost(54.5, [54.5 - bridge.RUNNING_MINIMUM_GIB + .1])
    host.install(monkeypatch, tmp_path)
    killed = []
    kill_children = bridge.jobs.kill_children
    monkeypatch.setattr(bridge.jobs, "kill_children",
                        lambda stop=None, **kw: killed.append(stop) or kill_children(stop, **kw))
    with pytest.raises(bridge.host.HostSaturated, match="host saturation") as error:
        bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01)
    assert killed and killed[0].is_set()
    assert error.value.host_admissions[0]["minimum_available_gib"] == bridge.RUNNING_MINIMUM_GIB


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(before=st.floats(0, 128), residents=st.lists(st.floats(0, 64), min_size=1, max_size=2),
       microcosm=st.integers(0, 2))
def test_a_batch_completes_exactly_when_each_admission_has_its_own_cold_room_and_the_host_keeps_its_floor(
        tmp_path, before, residents, microcosm):
    """Invariant: a job's own resident memory never counts against a floor reserved for it, only against later ones."""
    workers = len(residents)
    datasets = [MICROCOSM if i < microcosm else EFRS for i in range(workers)]
    admitted = all(before - sum(residents[:k]) >= bridge.COLD_JOB_MINIMUM_GIB for k in range(workers))
    completes = admitted and before - sum(residents) >= bridge.RUNNING_MINIMUM_GIB
    with pytest.MonkeyPatch.context() as monkeypatch:
        host = SequentialHost(before, residents)
        host.install(monkeypatch, tmp_path)
        if completes:
            assert bridge.run_batch(paths(datasets), workers, tmp_path / "cache",
                                    monitor_interval=.005) == [{"safe": True}] * workers
        else:
            with pytest.raises(bridge.host.HostSaturated):
                bridge.run_batch(paths(datasets), workers, tmp_path / "cache", monitor_interval=.005)


def test_observed_memory_includes_the_running_job_process(monkeypatch, tmp_path):
    """A real 64 MiB child: sampled while it runs, and in the kernel's peak once it has finished."""
    code = "import time; block = b'x' * (64 * 2**20); time.sleep(1)"

    def runner(kind, arg, workdir, engine, stop):
        subprocess.run([sys.executable, "-c", code], check=True)
        return {"safe": True}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "memory_check", lambda **kw: {"available_gib": 90.0, "load_1m": 0.0})
    observed = {}
    bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01, observed=observed)
    assert observed["interval_seconds"] == .01 and observed["samples"] >= 1
    assert observed["maximum_jobs_rss_gib"] >= 60 / 1024
    assert observed["peak_finished_job_rss_gib"] >= 60 / 1024
    assert observed["maximum_coordinator_rss_gib"] > 0
