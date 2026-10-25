"""The bridge's memory floors and observations, on the real scheduler with synthetic jobs.

Every floor reads host-wide available memory, which already excludes what the
batch's running jobs hold, not what an admitted job is about to load. Before a
batch the caller keeps 40 GiB for each cold Microcosm job. Each acquired slot
keeps 40 GiB for the one job it admits beyond what the batch's other admitted
Microcosm jobs may still allocate of their 40 GiB (jobs.ColdReservations, with
admissions serialized). The monitor, which runs while the batch's jobs are
resident, keeps only the host's safety floor, and never waits on the memory
observer. No model or survey data.
"""

import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import threading
import time
from types import SimpleNamespace

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from scripts import run_model_v2_j_bridge as bridge

MICROCOSM = "microcosm_uk_2024_25@a133f37a"
EFRS = "enhanced_frs_2024_25@1.58.0"
CPUS = 18
COLD = bridge.COLD_JOB_MINIMUM_GIB


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


def reading(available):
    return {"available_gib": available, "load_1m": 0.0, "cpu_count": CPUS}


class SequentialHost:
    """Each job is admitted only once the jobs before it are resident; available = before - their memory.

    A job's resident memory is what the reservations read for the worker thread
    running it (jobs.started_job_rss_gib), as for a real job process.
    """

    def __init__(self, before, residents):
        self.before, self.residents = before, residents
        self.changed = threading.Condition()
        self.entered = self.resident = 0
        self.held = {}  # worker thread ident -> its job's resident memory
        self.sampled = threading.Event()  # the monitor has read the host with every job resident

    def available(self):
        return max(self.before - sum(self.held.values()), 0.0)

    def measure(self):
        with self.changed:
            if self.resident == len(self.residents):
                self.sampled.set()
            return reading(self.available())

    def memory(self, owner):
        with self.changed:
            return self.held.get(owner)

    @contextlib.contextmanager
    def slot_lock(self, workdir, *args, stop=None, **kwargs):
        with self.changed:
            order, self.entered = self.entered, self.entered + 1
            while self.resident < order and not stop.is_set():
                self.changed.wait(.005)
        yield

    def runner(self, kind, arg, workdir, engine, stop):
        with self.changed:
            self.held[threading.get_ident()] = self.residents[self.resident]
            self.resident += 1
            self.changed.notify_all()
        while not (self.sampled.is_set() or stop.is_set()):
            self.sampled.wait(.005)
        return {"safe": True}

    def install(self, monkeypatch, tmp_path):
        scheduler(monkeypatch, tmp_path, self.runner)
        monkeypatch.setattr(bridge.jobs, "slot_lock", self.slot_lock)
        monkeypatch.setattr(bridge.jobs, "started_job_rss_gib", self.memory)
        monkeypatch.setattr(bridge.host, "measure", self.measure)


def test_floors_reserve_room_only_for_jobs_about_to_load():
    assert bridge.batch_resources(paths([MICROCOSM] * 2), 2)["minimum_gib"] == 2 * COLD
    assert bridge.batch_resources(paths([MICROCOSM, EFRS]), 2)["minimum_gib"] == COLD
    assert bridge.batch_resources(paths([EFRS] * 3), 3)["minimum_gib"] == COLD
    assert bridge.cold_budget_gib("path", {"dataset": MICROCOSM}) == COLD
    assert bridge.cold_budget_gib("coverage", {"dataset": "populace_uk_2024_25@x"}) == COLD
    assert bridge.cold_budget_gib("path", {"dataset": EFRS}) == 0
    assert 0 < bridge.RUNNING_MINIMUM_GIB < COLD


def test_a_second_slot_keeps_its_floor_beyond_the_first_jobs_reservation(monkeypatch, tmp_path):
    """While the first job's process has not started or cannot be read, all 40 GiB of it are still to come."""
    floors, ticked, both = [], threading.Event(), threading.Barrier(2, timeout=10)

    def memory_check(max_load_per_cpu=None, minimum_gib=40):
        floors.append(minimum_gib)
        if minimum_gib == bridge.RUNNING_MINIMUM_GIB:
            ticked.set()
        return reading(90.0)

    def runner(kind, arg, workdir, engine, stop):
        both.wait()  # the first job holds its reservation until the second has been admitted and started
        assert ticked.wait(10)
        return {"safe": True}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "memory_check", memory_check)
    assert bridge.run_batch(paths([MICROCOSM] * 2), 2, tmp_path / "cache", monitor_interval=.01) == [{"safe": True}] * 2
    admissions = sorted(floor for floor in floors if floor != bridge.RUNNING_MINIMUM_GIB)
    assert admissions == [COLD, 2 * COLD]
    assert bridge.RUNNING_MINIMUM_GIB in floors


def test_concurrent_slots_cannot_admit_two_cold_jobs_on_the_same_headroom(monkeypatch, tmp_path):
    """The batch passes its 80 GiB gate; other work then leaves 60 GiB; both workers reach admission before either
    job allocates anything. One 40 GiB budget fits, two do not: exactly one job starts, the other is refused."""
    available = [80.0]
    launched, killed = [], []

    def runner(kind, arg, workdir, engine, stop):
        launched.append(arg["draw"])
        assert stop.wait(10)  # allocates nothing until the batch stops
        return {"safe": True}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge.host, "measure", lambda: reading(available[0]))
    kill_children = bridge.jobs.kill_children
    monkeypatch.setattr(bridge.jobs, "kill_children", lambda stop=None, **kw: killed.append(1) or kill_children(stop))
    batch = paths([MICROCOSM] * 2)
    bridge.memory_check(minimum_gib=bridge.batch_resources(batch, 2)["minimum_gib"])  # main's gate: 80 GiB
    available[0] = 60.0
    with pytest.raises(bridge.host.HostSaturated, match="host saturation") as error:
        bridge.run_batch(batch, 2, tmp_path / "cache", monitor_interval=60)
    assert len(launched) == 1 and killed
    (refusal,) = error.value.host_admissions
    assert refusal["available_gib"] == 60.0 and refusal["minimum_available_gib"] == 2 * COLD


def test_a_resident_microcosm_job_does_not_trip_its_own_admission_floor(monkeypatch, tmp_path):
    """24 October, 23:55Z: 54.5 GiB available before any job; a ~30 GiB worker leaves about 25 GiB."""
    host = SequentialHost(54.5, [29.5])
    host.install(monkeypatch, tmp_path)
    observed = {}
    assert bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache",
                            monitor_interval=.01, observed=observed) == [{"safe": True}]
    assert observed["samples"] >= 1 and observed["minimum_available_gib"] == 25.0


def test_a_second_slot_counts_the_first_resident_job_once(monkeypatch, tmp_path):
    """92.6 GiB before; the first Microcosm job holds 18.1 GiB and may take 21.9 GiB more. The 74.5 GiB left covers
    the second job's 40 GiB beyond that (61.9 GiB), where counting the first job's memory twice would need 98.1."""
    host = SequentialHost(92.6, [18.1, 18.1])
    host.install(monkeypatch, tmp_path)
    assert bridge.run_batch(paths([MICROCOSM] * 2), 2, tmp_path / "cache", monitor_interval=.01) == [{"safe": True}] * 2


def test_a_second_slot_leaves_room_for_the_first_job_to_finish_loading(monkeypatch, tmp_path):
    """70 GiB before; the first job holds 18.1 GiB and may take 21.9 GiB more. 51.9 GiB is left: above one 40 GiB
    floor, but the two jobs could need 61.9 GiB of it, so the second is refused."""
    host = SequentialHost(70.0, [18.1, 18.1])
    host.install(monkeypatch, tmp_path)
    with pytest.raises(bridge.host.HostSaturated) as error:
        bridge.run_batch(paths([MICROCOSM] * 2), 2, tmp_path / "cache", monitor_interval=.01)
    (refusal,) = error.value.host_admissions
    assert refusal["available_gib"] == pytest.approx(51.9)
    assert refusal["minimum_available_gib"] == pytest.approx(COLD + COLD - 18.1)


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
@given(before=st.floats(0, 160), residents=st.lists(st.floats(0, 64), min_size=1, max_size=2),
       microcosm=st.booleans())
def test_a_batch_completes_exactly_when_its_gate_each_admission_and_the_running_floor_pass(
        tmp_path, before, residents, microcosm):
    """Invariant, on the real gate, scheduler and monitor: the batch gate keeps 40 GiB per concurrent cold job; the
    k-th admission keeps 40 GiB beyond each earlier job's larger of its memory and its cold budget (a job's own memory
    never counts against its own floor); the monitor keeps 8 GiB with every job resident."""
    workers, budget = len(residents), COLD if microcosm else 0
    batch = paths([MICROCOSM if microcosm else EFRS] * workers)
    gate = before >= bridge.batch_resources(batch, workers)["minimum_gib"]
    # As the host and the reservations compute them, in the same order: available memory with the earlier jobs
    # resident, and what those jobs may still allocate of their budgets.
    admitted = all(max(before - sum(residents[:k]), 0.0) >= COLD + sum(max(0.0, budget - r) for r in residents[:k])
                   for k in range(workers))
    completes = gate and admitted and max(before - sum(residents), 0.0) >= bridge.RUNNING_MINIMUM_GIB
    with pytest.MonkeyPatch.context() as monkeypatch:
        host = SequentialHost(before, residents)
        host.install(monkeypatch, tmp_path)

        def run():  # main: the batch gate, then the batch
            bridge.memory_check(minimum_gib=bridge.batch_resources(batch, workers)["minimum_gib"])
            return bridge.run_batch(batch, workers, tmp_path / "cache", monitor_interval=.005)

        if completes:
            assert run() == [{"safe": True}] * workers
        else:
            with pytest.raises(bridge.host.HostSaturated):
                run()


class Schedule:
    """The scheduler's reservations under an arbitrary interleaving, driven one step at a time.

    Each job is a thread that admits through jobs.ColdReservations and the real
    host rule (jobs.host_admission), then holds its reservation until told to
    finish. ``external`` is what the host has available with none of the
    batch's jobs resident; each job's resident memory is set by the schedule.
    """

    def __init__(self, external):
        self.external, self.resident, self.jobs = external, {}, {}
        self.reservations = bridge.jobs.ColdReservations(lambda kind, arg: arg["budget"], memory_gib=self.memory)

    def memory(self, owner):
        return self.resident.get(owner)

    def available(self):
        return self.external - sum(self.resident.values())

    def admit(self, name, budget):
        admitted, refused, finish = threading.Event(), threading.Event(), threading.Event()
        seen = {}

        def check(outstanding_gib):
            seen["available"], seen["outstanding"] = self.available(), outstanding_gib
            bridge.jobs.host_admission(bridge.jobs.MINIMUM_AVAILABLE_GIB + outstanding_gib, "after_slot_acquisition")

        def job():
            try:
                with self.reservations.admitting("path", {"budget": budget}, check):
                    self.resident[threading.get_ident()] = 0.0
                    admitted.set()
                    finish.wait(30)
            except bridge.host.HostSaturated:
                refused.set()
            finally:
                self.resident.pop(threading.get_ident(), None)

        thread = threading.Thread(target=job)
        thread.start()
        deadline = time.monotonic() + 10
        while not (admitted.is_set() or refused.is_set()):
            assert time.monotonic() < deadline, "the admission never finished"
            time.sleep(.001)
        if admitted.is_set():
            self.jobs[name] = SimpleNamespace(thread=thread, finish=finish, budget=budget)
        else:
            thread.join(10)
        return admitted.is_set(), seen

    def grow(self, name, gib):
        job = self.jobs[name]
        self.resident[job.thread.ident] = min(job.budget, self.resident[job.thread.ident] + gib)

    def finish(self, name):
        job = self.jobs.pop(name)
        job.finish.set()
        job.thread.join(10)

    def committed(self):
        """What the running jobs hold or may still allocate: each one's larger of its memory and its budget."""
        return sum(max(self.resident[job.thread.ident], job.budget) for job in self.jobs.values())


STEP = st.one_of(st.tuples(st.just("external"), st.floats(-60, 60)),
                 st.tuples(st.just("admit"), st.sampled_from([0, COLD])),
                 st.tuples(st.just("grow"), st.tuples(st.integers(0, 3), st.floats(0, COLD))),
                 st.tuples(st.just("finish"), st.integers(0, 3)))


@settings(max_examples=150, deadline=None)
@given(external=st.floats(0, 200), workers=st.integers(1, 3), cold=st.integers(1, 4),
       steps=st.lists(STEP, max_size=24))
def test_no_schedule_admits_more_cold_memory_than_the_host_has(external, workers, cold, steps):
    """Invariant, for any interleaving of admissions, loading, finishes and changes in other work after the batch
    gate: a slot admits exactly when available memory covers its 40 GiB floor beyond what the running jobs may still
    allocate (their budgets less what they hold), so at each admission the host has room for every admitted job to
    reach its budget. Without other work growing, available memory never falls below zero."""
    gate = bridge.jobs.MINIMUM_AVAILABLE_GIB * min(workers, cold)
    schedule = Schedule(external)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
        monkeypatch.setattr(bridge.host, "measure", lambda: reading(schedule.available()))
        if external < gate:  # the batch gate refuses: nothing is admitted
            with pytest.raises(bridge.host.HostSaturated):
                bridge.jobs.host_admission(gate, "before_batch")
            return
        bridge.jobs.host_admission(gate, "before_batch")
        others_grew, names = False, iter(range(10**6))
        try:
            for kind, value in steps:
                if kind == "external":
                    schedule.external = max(0.0, schedule.external + value)
                    others_grew |= value < 0
                elif kind == "admit" and len(schedule.jobs) < workers:
                    outstanding = sum(max(0.0, job.budget - schedule.resident[job.thread.ident])
                                      for job in schedule.jobs.values())
                    floor = bridge.jobs.MINIMUM_AVAILABLE_GIB + outstanding
                    available = schedule.available()
                    admitted, seen = schedule.admit(next(names), value)
                    assert seen["outstanding"] == pytest.approx(outstanding)
                    assert admitted == (available >= floor)
                    if admitted:
                        assert schedule.committed() <= schedule.external + 1e-9
                elif kind == "grow" and schedule.jobs:
                    which, gib = value
                    schedule.grow(sorted(schedule.jobs)[which % len(schedule.jobs)], gib)
                elif kind == "finish" and schedule.jobs:
                    schedule.finish(sorted(schedule.jobs)[value % len(schedule.jobs)])
                if not others_grew:
                    assert schedule.available() >= -1e-9
        finally:
            for name in list(schedule.jobs):
                schedule.finish(name)


def test_a_job_that_frees_memory_during_an_admission_is_not_credited_with_it(monkeypatch):
    """The 25 October concurrency review's schedule: A (40 GiB budget) holds 35 GiB when its memory is read and has
    freed 20 GiB by the host reading. A may then still take 25 GiB, so the slot needs 65 GiB, and the host shows
    70 - 15 = 55: refused, not admitted on the 45 GiB the first reading implied."""
    state = {"rss": 35.0}
    reservations = bridge.jobs.ColdReservations(lambda kind, arg: COLD, memory_gib=lambda owner: state["rss"])
    reservations._held["A"] = COLD

    def measure():
        state["rss"] = 15.0
        return reading(70.0 - state["rss"])

    floors = []

    def admit(outstanding_gib):
        floors.append(COLD + outstanding_gib)
        bridge.jobs.host_admission(COLD + outstanding_gib, "after_slot_acquisition")

    monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
    monkeypatch.setattr(bridge.host, "measure", measure)
    with pytest.raises(bridge.host.HostSaturated, match="55.0 GiB available"):
        with reservations.admitting("path", {}, admit):
            pytest.fail("admitted against memory A had already freed")
    assert floors == [45.0, 65.0]
    assert reservations._held == {"A": COLD}


# A running job: its cold budget, its memory at the start of the admission (above its budget too), and how fast that
# moves (GiB per reading; one way only).
RUNNING = st.tuples(st.sampled_from([0, COLD]), st.floats(0, 1.5 * COLD), st.floats(-COLD / 2, COLD / 2))


@settings(max_examples=300, deadline=None)
@given(running=st.lists(RUNNING, max_size=3), margin=st.floats(-COLD, COLD))
def test_an_admission_never_credits_a_job_with_much_more_than_it_held_at_the_deciding_reading(running, margin):
    """Invariant: each running job's memory moves one way at its own rate on a clock that ticks at every reading, its
    own or the host's. If a slot admits, then at the last host reading the host had the slot's floor beyond what the
    running jobs could still allocate at that instant, less at most RECHECK_GIB. With no job's memory moving, a slot
    admits exactly when the single-reading rule passes."""
    clock, last = [0], {}

    def held(i, t):
        _, start, rate = running[i]
        return max(0.0, start + rate * t)

    # Other work leaves the host within ``margin`` of what the single-reading rule needs at the start, where the
    # order of the readings decides.
    external = max(0.0, COLD + sum(max(budget, start) for budget, start, _ in running) + margin)

    def memory(owner):
        clock[0] += 1
        return held(owner, clock[0])

    def measure():
        clock[0] += 1
        last["t"] = clock[0]
        return reading(external - sum(held(i, clock[0]) for i in range(len(running))))

    def still_to_take(t):
        return sum(max(0.0, budget - held(i, t)) for i, (budget, _, _) in enumerate(running))

    reservations = bridge.jobs.ColdReservations(lambda kind, arg: COLD, memory_gib=memory)
    reservations._held.update({i: budget for i, (budget, _, _) in enumerate(running)})
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
        monkeypatch.setattr(bridge.host, "measure", measure)
        try:
            with reservations.admitting("path", {}, lambda out: bridge.jobs.host_admission(
                    COLD + out, "after_slot_acquisition")):
                admitted = True
        except bridge.host.HostSaturated:
            admitted = False
    t = last["t"]
    available = external - sum(held(i, t) for i in range(len(running)))
    if admitted:
        assert available >= COLD + still_to_take(t) - bridge.jobs.RECHECK_GIB - 1e-9
    if all(rate == 0 for _, _, rate in running):
        assert admitted == (available >= COLD + still_to_take(t))


def test_an_observation_failure_never_stops_the_safety_checks(monkeypatch, tmp_path):
    """A process table the observer cannot read (a sandboxed sysctl): recorded, and the monitor still stops the
    batch when memory runs out afterwards."""
    failures, ran_out = [], threading.Event()

    def runner(kind, arg, workdir, engine, stop):
        deadline = time.monotonic() + 10
        while len(failures) < 3 and not stop.is_set():  # memory runs out only after three failed observations
            assert time.monotonic() < deadline
            time.sleep(.005)
        ran_out.set()
        assert stop.wait(10)
        return {"safe": True}

    def unreadable():
        failures.append(1)
        raise PermissionError(1, "Operation not permitted (originated from sysctl(KERN_PROC_ALL))")

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "own_memory_gib", unreadable)
    monkeypatch.setattr(bridge.host, "measure", lambda: reading(0.0 if ran_out.is_set() else 90.0))
    observed = {}
    with pytest.raises(bridge.host.HostSaturated, match="host saturation"):
        bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01, observed=observed)
    assert observed["observation_errors"] >= 3 and observed["observations"] == 0
    assert observed["first_observation_error"].startswith("PermissionError")


def test_a_slow_observation_never_delays_the_safety_checks(monkeypatch, tmp_path):
    """An observer reading that takes 2 s (as a footprint call can): memory runs out while it is under way, and the
    10 ms checks, on their own cadence, stop the batch well within a second."""
    reading_started, ran_out, stopped = threading.Event(), [], []

    def runner(kind, arg, workdir, engine, stop):
        assert reading_started.wait(10)
        ran_out.append(time.monotonic())
        assert stop.wait(10)
        stopped.append(time.monotonic())
        return {"safe": True}

    def slow():
        reading_started.set()
        time.sleep(2)
        return {"coordinator_rss": 1.0, "jobs_rss": 1.0, "tree_footprint": None, "job_footprint_peak": None,
                "footprint_error": None}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "own_memory_gib", slow)
    monkeypatch.setattr(bridge.host, "measure", lambda: reading(0.0 if ran_out else 90.0))
    with pytest.raises(bridge.host.HostSaturated, match="host saturation"):
        bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01)
    assert stopped[0] - ran_out[0] < 1.0


def test_a_monitor_that_cannot_read_the_host_stops_the_batch_and_fails(monkeypatch, tmp_path):
    """The host reading itself fails while the batch runs: the batch is stopped, and the error says the monitor
    failed (it is not a host refusal, so it is never rerun as one)."""
    running = threading.Event()

    def runner(kind, arg, workdir, engine, stop):
        running.set()
        assert stop.wait(10)
        return {"safe": True}

    def measure():
        if running.is_set():
            raise PermissionError(1, "Operation not permitted")
        return reading(90.0)

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge.host, "measure", measure)
    with pytest.raises(RuntimeError, match="host monitor failed") as error:
        bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01)
    assert not isinstance(error.value, bridge.host.HostSaturated)
    assert isinstance(error.value.__cause__, PermissionError)


# Ctrl-C reaches run_batch while it waits for the observer, whose reading is still in progress.
INTERRUPTED = textwrap.dedent('''
    import json, os, signal, sys, threading, time
    from pathlib import Path
    from triple_lock import host, jobs
    from scripts import run_model_v2_j_bridge as bridge

    tmp = Path(sys.argv[1])
    jobs.WORKDIRS = tmp / "workers"
    reading_started, batch_returned = threading.Event(), threading.Event()
    run_jobs = jobs.run_jobs

    def returning(*a, **k):
        try:
            return run_jobs(*a, **k)
        finally:
            batch_returned.set()

    def slow():  # a footprint read takes up to FOOTPRINT_TIMEOUT_S
        if not reading_started.is_set():
            reading_started.set()
            assert batch_returned.wait(30)
            time.sleep(.5)  # run_batch is now waiting for this observer
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(1.5)
        return {"coordinator_rss": 1.0, "jobs_rss": 123.0, "tree_footprint": None, "job_footprint_peak": None,
                "footprint_error": None}

    def runner(kind, arg, workdir, engine, stop):
        assert reading_started.wait(10)
        return {"safe": True}

    jobs.run_jobs, jobs._run_isolated, bridge.own_memory_gib = returning, runner, slow
    host.measure = lambda: {"available_gib": 90.0, "load_1m": 0.0, "cpu_count": 18}
    observed = {}
    try:
        bridge.run_batch([("0", ("path", {"dataset": "microcosm_uk_2024_25@a133f37a"}))], 1, tmp / "cache",
                         monitor_interval=.01, observed=observed)
    except KeyboardInterrupt:
        at_exit = dict(observed)
        time.sleep(3)  # the observer's reading finishes, and the monitor would have ticked many times
        print(json.dumps({"interrupted": True, "at_exit": at_exit, "after": observed}))
    else:
        print(json.dumps({"interrupted": False}))
''')


def test_an_interrupt_while_the_batch_waits_for_its_threads_leaves_its_observations_as_returned(tmp_path):
    """Once run_batch has ended, even by Ctrl-C during its final wait for the observer, neither the observer nor the
    monitor changes what it reported."""
    script = tmp_path / "interrupted.py"
    script.write_text(INTERRUPTED)
    root = Path(__file__).parents[1]
    done = subprocess.run([sys.executable, str(script), str(tmp_path)], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(root)}, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout.splitlines()[-1])
    assert result["interrupted"]
    assert result["after"] == result["at_exit"]
    assert result["at_exit"]["maximum_jobs_rss_gib"] is None  # the reading in progress was never recorded


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
    if observed["observations"] == 0 and (observed["first_observation_error"] or "").startswith("PermissionError"):
        pytest.skip(f"this sandbox cannot read the process table: {observed['first_observation_error']}")
    assert observed["observations"] >= 1 and observed["observation_errors"] == 0
    assert observed["maximum_jobs_rss_gib"] >= 60 / 1024
    assert observed["peak_finished_job_rss_gib"] >= 60 / 1024
    assert observed["maximum_coordinator_rss_gib"] > 0
    if bridge.FOOTPRINT.exists():  # macOS: the footprint heavy_run.sh counts, and the job's kernel peak
        assert observed["maximum_tree_footprint_gib"] >= 60 / 1024
        assert observed["peak_job_footprint_gib"] >= 60 / 1024
    else:
        assert observed["maximum_tree_footprint_gib"] is observed["peak_job_footprint_gib"] is None


# The layout of `footprint -f bytes -p A -p B` on macOS 26 (regions trimmed): one section per process, then shared.
FOOTPRINT_OUTPUT = """======================================================================
claude [61932]: 64-bit    Footprint: 251692472 B (16384 bytes per page)
======================================================================

      Dirty         Clean   Reclaimable    Regions    Category
        ---           ---           ---        ---    ---
251643320 B   127614976 B   105398272 B        281    TOTAL

Shared with zsh [95965]:
      Dirty         Clean   Reclaimable    Regions    Category
        ---           ---           ---        ---    ---

Auxiliary data:
    phys_footprint: 251725240 B
    phys_footprint_peak: 292111776 B

======================================================================
zsh [95965]: 64-bit    Footprint: 1671528 B (16384 bytes per page)
======================================================================

Shared with claude [61932]:
      Dirty         Clean   Reclaimable    Regions    Category
        ---           ---           ---        ---    ---

Auxiliary data:
    phys_footprint: 1687912 B
    phys_footprint_peak: 1687912 B

======================================================================
Shared Cache F2E86C53-6052-388B-BA71-5A0C9B569413
======================================================================
"""


def test_footprints_reads_each_process_section(monkeypatch, tmp_path):
    tool = tmp_path / "footprint"
    tool.write_text("")
    monkeypatch.setattr(bridge, "FOOTPRINT", tool)
    calls = []
    monkeypatch.setattr(bridge.subprocess, "run", lambda command, **kw: calls.append(command)
                        or SimpleNamespace(stdout=FOOTPRINT_OUTPUT, stderr="", returncode=0))
    assert bridge.footprints([95965, 61932]) == {
        61932: {"phys_footprint": 251725240, "phys_footprint_peak": 292111776},
        95965: {"phys_footprint": 1687912, "phys_footprint_peak": 1687912}}
    assert calls[0] == [str(tool), "-f", "bytes", "-p", "95965", "-p", "61932"]
    assert bridge.footprints([95965]) == {95965: {"phys_footprint": 1687912, "phys_footprint_peak": 1687912}}


def test_footprints_is_empty_off_macos_and_raises_when_the_tool_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "FOOTPRINT", tmp_path / "absent")
    assert bridge.footprints([1]) == {}
    tool = tmp_path / "footprint"
    tool.write_text("")
    monkeypatch.setattr(bridge, "FOOTPRINT", tool)
    assert bridge.footprints([]) == {}

    def hangs(command, **kw):
        raise subprocess.TimeoutExpired(command, kw["timeout"])

    monkeypatch.setattr(bridge.subprocess, "run", hangs)
    with pytest.raises(bridge.FootprintUnavailable, match="TimeoutExpired"):
        bridge.footprints([1])
    monkeypatch.setattr(bridge.subprocess, "run", lambda command, **kw: SimpleNamespace(
        stdout="", stderr="footprint: permission denied", returncode=66))
    with pytest.raises(bridge.FootprintUnavailable, match="exited 66: footprint: permission denied"):
        bridge.footprints([1])


def test_a_failed_footprint_read_is_counted_and_the_resident_memory_still_recorded(monkeypatch, tmp_path):
    def unavailable(pids, timeout=bridge.FOOTPRINT_TIMEOUT_S):
        raise bridge.FootprintUnavailable("footprint exited 66: permission denied")

    def runner(kind, arg, workdir, engine, stop):
        deadline = time.monotonic() + 10
        while observed["observations"] + observed["observation_errors"] < 2:
            assert time.monotonic() < deadline
            time.sleep(.005)
        return {"safe": True}

    scheduler(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(bridge, "footprints", unavailable)
    monkeypatch.setattr(bridge, "memory_check", lambda **kw: reading(90.0))
    observed = {}
    bridge.run_batch(paths([MICROCOSM]), 1, tmp_path / "cache", monitor_interval=.01, observed=observed)
    if observed["observations"] == 0 and (observed["first_observation_error"] or "").startswith("PermissionError"):
        pytest.skip(f"this sandbox cannot read the process table: {observed['first_observation_error']}")
    assert observed["footprint_errors"] == observed["observations"] >= 1
    assert observed["first_footprint_error"] == "footprint exited 66: permission denied"
    assert observed["maximum_coordinator_rss_gib"] > 0
    assert observed["maximum_tree_footprint_gib"] is observed["peak_job_footprint_gib"] is None


@pytest.mark.skipif(not bridge.FOOTPRINT.exists(), reason="macOS footprint tool")
def test_footprints_reads_a_live_process():
    child = subprocess.Popen([sys.executable, "-c", "import time; block = b'x' * (64 * 2**20); time.sleep(5)"])
    try:
        probe = subprocess.run([str(bridge.FOOTPRINT), "-f", "bytes", "-p", str(child.pid)],
                               capture_output=True, text=True, timeout=bridge.FOOTPRINT_TIMEOUT_S)
        if probe.returncode != 0:
            pytest.skip(f"footprint cannot read a child here (exit {probe.returncode}): {probe.stderr.strip()}")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            read = bridge.footprints([child.pid])
            if read.get(child.pid, {}).get("phys_footprint", 0) >= 60 * 2**20:
                break
            time.sleep(.1)
        assert read[child.pid]["phys_footprint"] >= 60 * 2**20
        assert read[child.pid]["phys_footprint_peak"] >= read[child.pid]["phys_footprint"]
    finally:
        child.kill()
        child.wait()
