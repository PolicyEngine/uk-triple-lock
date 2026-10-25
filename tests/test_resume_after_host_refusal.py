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

# Each scenario runs the actual scheduler or bridge code in a child, with a synthetic host reading and runner.
SCENARIOS = textwrap.dedent('''
    import sys, threading, time
    from pathlib import Path
    from triple_lock import host, jobs
    from scripts import run_model_v2_j_bridge as bridge

    tmp, scenario = Path(sys.argv[1]), sys.argv[2]
    jobs.WORKDIRS = tmp / "workers"
    low = {"available_gib": 38.0, "load_1m": 1.0, "cpu_count": 18}
    started = threading.Event()

    def build(refuse, other):
        def admission(kind, arg, workdir, stop):
            if arg["i"] in refuse:
                if other:
                    assert started.wait(10)  # the other job is running before this one is refused
                host.measure = lambda: dict(low)
                jobs.host_admission(jobs.MINIMUM_AVAILABLE_GIB, "after_slot_acquisition")

        def runner(kind, arg, workdir, engine, stop):
            if arg["i"] in other:
                started.set()
                raise ValueError("a model error")
            return {"safe": True}

        jobs.run_jobs([("path", {"i": i}) for i in range(2)], workers=2, cache=tmp / "cache",
                      runner=runner, admission=admission, log=lambda *a: None)

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
        running = threading.Event()
        host.measure = lambda: {**low, "available_gib": 7.0 if running.is_set() else 54.5}
        def runner(kind, arg, workdir, engine, stop):
            running.set()
            stop.wait(10)
            return {"safe": True}
        jobs.WORKDIRS, jobs._run_isolated = tmp / "workers", runner
        bridge.run_batch([("central", ("path", {"dataset": "microcosm_uk_2024_25@a133f37a"}))], 1,
                         tmp / "cache", monitor_interval=.01)
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
                                      "bridge_while_running"])
def test_real_refusals_are_rerun(stderr_of, scenario):
    returncode, stderr = stderr_of(scenario)
    assert returncode == 1, stderr
    assert resume.final_exception(stderr)[0] == resume.HOST_SATURATED
    assert resume.is_host_refusal(returncode, stderr)


@pytest.mark.parametrize("scenario", ["build_refused_and_failed", "other_error", "refusal_then_other_error"])
def test_any_other_failure_is_not_rerun(stderr_of, scenario):
    returncode, stderr = stderr_of(scenario)
    assert returncode == 1, stderr
    assert not resume.is_host_refusal(returncode, stderr)


def test_the_mixed_build_failure_is_host_saturated_but_lists_the_model_error(stderr_of):
    """jobs.run_jobs raises HostSaturated if any job was refused, so the job lines decide."""
    returncode, stderr = stderr_of("build_refused_and_failed")
    kind, lines = resume.final_exception(stderr)
    assert kind == resume.HOST_SATURATED
    assert any("a model error" in line for line in lines)


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
