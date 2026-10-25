"""The resume wrapper reruns only after a host refusal, classified from real refusals of the real runners."""

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from hypothesis import given, settings, strategies as st
import pytest

from scripts import resume_after_host_refusal as resume

ROOT = Path(__file__).parents[1]

# Each scenario runs the actual scheduler or bridge code in a child, with a synthetic host reading and runner, or a
# real job process (a sleeping interpreter in place of the engine job) where the bridge has to stop one.
SCENARIOS = textwrap.dedent('''
    import sys, threading, time
    from pathlib import Path
    from triple_lock import host, jobs
    from scripts import run_model_v2_j_bridge as bridge

    tmp, scenario = Path(sys.argv[1]), sys.argv[2]
    jobs.WORKDIRS = tmp / "workers"
    low = {"available_gib": 38.0, "load_1m": 1.0, "cpu_count": 18}
    high = {**low, "available_gib": 90.0}
    MICROCOSM = "microcosm_uk_2024_25@a133f37a"

    def build(refuse, other):
        failing, refusing = threading.Event(), threading.Event()

        def admission(kind, arg, workdir, stop):
            if arg["i"] in refuse:
                if other:
                    assert failing.wait(10)  # the failing job is running before this one is refused
                    refusing.set()
                host.measure = lambda: dict(low)
                jobs.host_admission(jobs.MINIMUM_AVAILABLE_GIB, "after_slot_acquisition")

        def runner(kind, arg, workdir, engine, stop):
            if arg["i"] in other:
                failing.set()
                assert refusing.wait(10)  # and fails only once the other job is being refused
                raise ValueError("a model error")
            return {"safe": True}

        jobs.run_jobs([("path", {"i": i}) for i in range(2)], workers=2, cache=tmp / "cache",
                      runner=runner, admission=admission, log=lambda *a: None)

    def bridge_batch(n, interval=60):
        return bridge.run_batch([(str(i), ("path", {"dataset": MICROCOSM, "i": i})) for i in range(n)], n,
                                tmp / "cache", monitor_interval=interval)

    def real_job_processes():
        # The real job runner (_run_isolated) and run_child, with a sleeping interpreter for the engine job.
        run_child = jobs.run_child
        jobs.run_child = lambda cmd, cwd, env=None, stop=None, **kw: run_child(
            [sys.executable, "-c", "import time; time.sleep(60)"], cwd, env, stop, **kw)

    def job_process_started():
        deadline = time.monotonic() + 30
        while not jobs._children:
            assert time.monotonic() < deadline, "the job process never started"
            time.sleep(.01)

    if scenario == "build_refused":
        build(refuse={0, 1}, other=set())
    elif scenario == "build_refused_and_failed":
        build(refuse={0}, other={1})
    elif scenario == "build_before_batch":
        host.measure = lambda: dict(low)
        jobs.host_admission(jobs.MINIMUM_AVAILABLE_GIB * 2, "before_batch")
    elif scenario == "bridge_before_batch":
        host.measure = lambda: dict(low)
        bridge.memory_check(minimum_gib=40)
    elif scenario == "bridge_while_running":
        # The monitor finds the host saturated and stops the running job process.
        real_job_processes()
        host.measure = lambda: {**low, "available_gib": 7.0} if jobs._children else dict(high)  # below 8 GiB
        bridge_batch(1, interval=.05)
    elif scenario == "bridge_refused_while_a_job_runs":
        # The second slot is refused while the first job's process runs; the refusal stops that process.
        real_job_processes()
        readings = iter([high])
        def measure():
            reading = next(readings, None)
            if reading is None:
                job_process_started()
                return dict(low)
            return dict(reading)
        host.measure = measure
        bridge_batch(2)
    elif scenario == "bridge_refused_and_failed":
        # One job fails with a model error while the second slot is refused.
        failing, refusing = threading.Event(), threading.Event()
        readings = iter([high])
        def measure():
            reading = next(readings, None)
            if reading is None:
                assert failing.wait(10)
                refusing.set()
                return dict(low)
            return dict(reading)
        def runner(kind, arg, workdir, engine, stop):
            failing.set()
            assert refusing.wait(10)
            raise ValueError("a model error")
        host.measure, jobs._run_isolated = measure, runner
        bridge_batch(2)
    elif scenario == "bridge_killed_then_refused":
        # The first job's process is killed by something else (as the kernel's memory killer would) and unregistered;
        # the second slot is then refused, and only after that does the first worker classify its job's exit.
        run_child, killed = jobs.run_child, threading.Event()
        def child(cmd, cwd, env=None, stop=None, **kw):
            result = run_child([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"],
                               cwd, env, stop, **kw)
            killed.set()
            assert stop.wait(10)
            return result
        jobs.run_child = child
        readings = iter([high])
        def measure():
            reading = next(readings, None)
            if reading is None:
                assert killed.wait(10)
                return dict(low)
            return dict(reading)
        host.measure = measure
        bridge_batch(2)
    elif scenario == "bridge_monitor_failed":
        # The host cannot be read once the job runs: the monitor stops the batch.
        real_job_processes()
        def measure():
            if jobs._children:
                raise PermissionError(1, "Operation not permitted")
            return dict(high)
        host.measure = measure
        bridge_batch(1, interval=.05)
    elif scenario == "other_error":
        raise RuntimeError("1 job(s) failed and 0 did not run; the rest finished and are cached:\\n"
                           "path job 0123456789ab: build job admission refused: imitation in another type")
    elif scenario == "refusal_then_other_error":
        try:
            host.measure = lambda: dict(low)
            jobs.host_admission(40, "before_batch")
        except host.HostSaturated:
            raise RuntimeError("cleanup failed after the refusal")
''')


@pytest.fixture(scope="module")
def stderr_of(tmp_path_factory):
    script = tmp_path_factory.mktemp("scenarios") / "scenarios.py"
    script.write_text(SCENARIOS)
    seen = {}

    def run(scenario):
        if scenario not in seen:
            tmp = tmp_path_factory.mktemp(scenario)
            done = subprocess.run([sys.executable, str(script), str(tmp), scenario], cwd=ROOT, capture_output=True,
                                  text=True, env={**os.environ, "PYTHONPATH": str(ROOT)}, timeout=120)
            seen[scenario] = (done.returncode, done.stderr)
        return seen[scenario]

    return run


@pytest.mark.parametrize("scenario", ["build_refused", "build_before_batch", "bridge_before_batch",
                                      "bridge_while_running", "bridge_refused_while_a_job_runs"])
def test_real_refusals_are_rerun(stderr_of, scenario):
    returncode, stderr = stderr_of(scenario)
    assert returncode == 1, stderr
    assert resume.final_exception(stderr)[0] == resume.HOST_SATURATED
    assert resume.is_host_refusal(returncode, stderr)


@pytest.mark.parametrize("scenario", ["build_refused_and_failed", "bridge_refused_and_failed", "bridge_killed_then_refused",
                                      "bridge_monitor_failed", "other_error", "refusal_then_other_error"])
def test_any_other_failure_is_not_rerun(stderr_of, scenario):
    returncode, stderr = stderr_of(scenario)
    assert returncode == 1, stderr
    assert not resume.is_host_refusal(returncode, stderr)


@pytest.mark.parametrize("scenario", ["build_refused_and_failed", "bridge_refused_and_failed"])
def test_a_mixed_failure_is_host_saturated_but_lists_the_model_error(stderr_of, scenario):
    """The scheduler raises HostSaturated if any job was refused, and the bridge passes its report on: the job lines
    decide."""
    returncode, stderr = stderr_of(scenario)
    kind, lines = resume.final_exception(stderr)
    assert kind == resume.HOST_SATURATED
    assert any("a model error" in line for line in lines)
    assert any(line.startswith("2 job(s) failed") for line in lines)


def test_a_job_the_refusal_stopped_did_not_run_and_is_no_failure(stderr_of):
    """The bridge's refusal stops the first job's process: the report counts it as not run, and lists only the
    refused job, so the attempt is rerun from cache."""
    _, stderr = stderr_of("bridge_refused_while_a_job_runs")
    _, lines = resume.final_exception(stderr)
    assert lines[0].startswith("bridge stopped because host saturation was observed")
    assert any(line.startswith("1 job(s) failed and 1 did not run") for line in lines)


def test_a_job_killed_by_something_else_stays_a_failure_when_a_refusal_follows(stderr_of):
    """The refusal's kill_children found no running process, so it did not cause the first job's death: the report
    lists that job's own exit beside the refusal, and the attempt is not rerun."""
    _, stderr = stderr_of("bridge_killed_then_refused")
    _, lines = resume.final_exception(stderr)
    assert any(line.startswith("2 job(s) failed and 0 did not run") for line in lines)
    assert any("(exit -9)" in line for line in lines)


def test_a_monitor_that_could_not_read_the_host_is_a_failure(stderr_of):
    _, stderr = stderr_of("bridge_monitor_failed")
    kind, lines = resume.final_exception(stderr)
    assert kind == "RuntimeError" and lines[0].startswith("bridge stopped because its host monitor failed")
    assert "PermissionError" in stderr


@pytest.mark.parametrize("report,rerun", [
    ("1 job(s) failed and 0 did not run; the rest finished and are cached:\n"
     "path job 0123456789ab: Host saturated: 7.0 GiB available (floor 8 GiB)", True),
    # A report that counts more failures than it lists, or lists one that was not refused, is not rerun.
    ("2 job(s) failed and 0 did not run; the rest finished and are cached:\n"
     "path job 0123456789ab: Host saturated: 7.0 GiB available (floor 8 GiB)", False),
    ("1 job(s) failed and 0 did not run; the rest finished and are cached:\n"
     "path job 0123456789ab: path job failed in w (exit 1)", False),
    ("0 job(s) failed and 2 did not run; the rest finished and are cached:\n", True),
])
def test_the_report_must_account_for_every_failed_job(report, rerun):
    stderr = ("Traceback (most recent call last):\n  File \"x\", line 1, in <module>\n"
              "triple_lock.host.HostSaturated: bridge stopped because host saturation was observed during this "
              "batch:\n" + report + "\n")
    assert resume.is_host_refusal(1, stderr) is rerun


@pytest.mark.parametrize("returncode", [0, 75, 130, 137, 143, -9])
def test_exit_codes_that_are_never_rerun(stderr_of, returncode):
    _, stderr = stderr_of("build_refused")
    assert not resume.is_host_refusal(returncode, stderr)


def test_no_traceback_is_not_a_refusal():
    assert resume.final_exception("heavy_run: waiting for a heavy slot\n") is None
    assert not resume.is_host_refusal(1, "Host saturated: but not in a traceback\n")


ATTEMPT = st.sampled_from(["refused", "failed", "succeeded", "ceiling"])


@settings(max_examples=200, deadline=None)
@given(outcomes=st.lists(ATTEMPT, min_size=1, max_size=8), max_attempts=st.integers(1, 8))
def test_resume_stops_at_the_first_attempt_that_is_not_a_refusal(tmp_path_factory, outcomes, max_attempts):
    """Invariant: attempts = min(first non-refusal + 1, max_attempts); the result is that attempt's exit code."""
    refusal = ("Traceback (most recent call last):\n  File \"x\", line 1, in <module>\n"
               "triple_lock.host.HostSaturated: Host saturated: 7.0 GiB available (floor 8 GiB)\n")
    stderr = {"refused": (1, refusal), "failed": (1, "Traceback (most recent call last):\nValueError: no\n"),
              "succeeded": (0, ""), "ceiling": (137, refusal)}
    queue = list(outcomes) + ["refused"] * max_attempts
    calls, sleeps = [], []

    def run(command):
        calls.append(command)
        return stderr[queue[len(calls) - 1]]

    log = tmp_path_factory.mktemp("log") / "attempts.jsonl"
    result = resume.resume(["cmd"], log, max_attempts=max_attempts, wait_seconds=3, run=run, sleep=sleeps.append)
    first_other = next((i for i, outcome in enumerate(queue) if outcome != "refused"), len(queue))
    expected_attempts = min(first_other + 1, max_attempts)
    assert len(calls) == expected_attempts
    assert result == stderr[queue[expected_attempts - 1]][0]
    assert sleeps == [3] * (expected_attempts - 1)  # a wait follows every attempt but the last
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert [r["attempt"] for r in records] == list(range(1, expected_attempts + 1))
    assert all(r["outcome"] == "host_refusal" for r in records[:-1])


def test_the_command_line_reruns_a_real_refusal_from_its_state(tmp_path):
    """Two real HostSaturated exits, then success: three attempts, exit 0."""
    state = tmp_path / "count"
    fake = tmp_path / "fake.py"
    fake.write_text(textwrap.dedent(f'''
        from pathlib import Path
        from triple_lock import host
        state = Path({str(state)!r})
        n = int(state.read_text()) if state.exists() else 0
        state.write_text(str(n + 1))
        if n < 2:
            raise host.HostSaturated("Host saturated: 30.0 GiB available (floor 40 GiB); bridge stops before new jobs")
        print("done")
    '''))
    log = tmp_path / "attempts.jsonl"
    done = subprocess.run([sys.executable, "scripts/resume_after_host_refusal.py", "--log", str(log),
                           "--wait-seconds", "0", "--max-attempts", "5", "--", sys.executable, str(fake)],
                          cwd=ROOT, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)},
                          timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "done"
    assert [json.loads(line)["outcome"] for line in log.read_text().splitlines()] == [
        "host_refusal", "host_refusal", "succeeded"]


def test_the_command_line_requires_a_command(tmp_path):
    with pytest.raises(SystemExit):
        resume.main(["--log", str(tmp_path / "log.jsonl"), "--"])
