"""Running jobs: failures are all reported, no job outlives its build, no worker waits silently (no PolicyEngine).

* run_jobs: every job that failed is named, those that failed while the others finished included; every job that
  finished is cached; the counts add up (a Hypothesis property over random outcomes).
* run_child starts each job in its own session; kill_children stops the job and anything it started.
* A build stopped by Ctrl-C, SIGTERM or SIGHUP stops its jobs; a job whose build is SIGKILLed stops itself.
* slot_lock logs who holds a worker directory, times out, and gives up when the build stops.
"""

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine, jobs
from triple_lock.config import REPO

ENV = {**os.environ, "PYTHONPATH": str(REPO / "src")}


def alive(pid):
    """True while ``pid`` runs (a zombie counts as gone)."""
    try:
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    except OSError:
        return False
    return bool(state) and not state.startswith("Z")


def wait_until(condition, timeout=20.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def read_pids(path, n, timeout=120.0):  # generous: a loaded machine can take a while to start Python
    assert wait_until(lambda: path.exists() and len(path.read_text().split()) >= n, timeout), "processes never started"
    return [int(p) for p in path.read_text().split()[:n]]


# A job that records its pid, starts a grandchild that records its own, and sleeps. Like a real job it watches its
# parent, so a failed test cannot leave it (or its grandchild) running.
SLEEPER = textwrap.dedent("""
    import os, subprocess, sys, time
    from triple_lock import jobs
    jobs.watch_parent(0.1)
    out = sys.argv[1]
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    with open(out, "a") as f:
        f.write(f"{os.getpid()} {child.pid}\\n")
    time.sleep(120)
""")


# ── run_jobs reports every failure ─────────────────────────────────────


def test_run_jobs_reports_a_job_that_fails_while_the_others_finish(tmp_path, monkeypatch):
    """Job 0 fails first; job 1, already running, fails only after run_jobs has seen job 0's failure. Job 0 is named
    in the log at once; both are reported at the end (before, the second was lost); the queued jobs are cancelled or
    finish, and what finished is cached."""
    monkeypatch.setattr(jobs, "WORKDIRS", tmp_path / "workers")
    second_started, failure_seen = threading.Event(), threading.Event()
    finished = set()

    def runner(kind, arg, workdir, engine_, stop):
        if arg["i"] == 0:
            second_started.wait(10)
            raise RuntimeError("job zero broke")
        if arg["i"] == 1:
            second_started.set()
            assert failure_seen.wait(10)
            raise RuntimeError("job one broke too")
        if stop.is_set():
            raise jobs.Aborted("stopping")
        finished.add(arg["i"])
        return {"i": arg["i"]}

    logged = []

    def log(message):
        logged.append(message)
        if message.startswith("Cancelling the queued jobs"):
            failure_seen.set()

    work = [("t", {"i": i}) for i in range(4)]
    with pytest.raises(RuntimeError) as err:
        jobs.run_jobs(work, workers=2, log=log, cache=tmp_path / "cache", runner=runner)
    message = str(err.value)
    assert "job zero broke" in message and "job one broke too" in message
    # The first failure is named as soon as it happens, before the running job finishes.
    first = next(i for i, m in enumerate(logged) if m.startswith("Failed: ") and "job zero broke" in m)
    assert first < logged.index("Cancelling the queued jobs and waiting for the running ones")
    n_failed, n_not_run = map(int, re.match(r"(\d+) job\(s\) failed and (\d+) did not run", message).groups())
    assert n_failed == 2 and n_not_run + len(finished) == 2
    for i in finished:
        assert engine.cached("t", {"i": i}, cache=tmp_path / "cache") == {"i": i}


@settings(max_examples=40, deadline=None)
@given(outcomes=st.lists(st.sampled_from(["ok", "fail"]), min_size=1, max_size=8), workers=st.integers(1, 3))
def test_run_jobs_accounts_for_every_job(outcomes, workers):
    """For any outcomes: with no failure every result comes back in order and is cached; with failures run_jobs
    raises naming exactly the jobs that failed, every job that finished is cached, and failed + not run + finished
    is every job."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        calls = {"ok": set(), "fail": set(), "aborted": set()}
        lock = threading.Lock()

        def runner(kind, arg, workdir, engine_, stop):
            i = arg["i"]
            if stop.is_set():
                with lock:
                    calls["aborted"].add(i)
                raise jobs.Aborted("stopping")
            with lock:
                calls[outcomes[i]].add(i)
            if outcomes[i] == "fail":
                raise RuntimeError(f"job {i} broke")
            return {"i": i}

        saved = jobs.WORKDIRS
        jobs.WORKDIRS = d / "workers"
        try:
            work = [("t", {"i": i}) for i in range(len(outcomes))]
            if "fail" not in outcomes:
                assert jobs.run_jobs(work, workers=workers, log=lambda m: None, cache=d / "cache",
                                       runner=runner) == [{"i": i} for i in range(len(outcomes))]
                assert calls["ok"] == set(range(len(outcomes)))
                return
            with pytest.raises(RuntimeError) as err:
                jobs.run_jobs(work, workers=workers, log=lambda m: None, cache=d / "cache", runner=runner)
        finally:
            jobs.WORKDIRS = saved
        message = str(err.value)
        n_failed, n_not_run = map(int, re.match(r"(\d+) job\(s\) failed and (\d+) did not run", message).groups())
        assert {int(i) for i in re.findall(r"job (\d+) broke", message)} == calls["fail"] and n_failed == len(calls["fail"])
        assert n_failed + n_not_run + len(calls["ok"]) == len(outcomes)
        for i in calls["ok"]:
            assert engine.cached("t", {"i": i}, cache=d / "cache") == {"i": i}


def test_the_cache_keeps_what_the_job_wrote(tmp_path, monkeypatch):
    """jobs.py is outside the cache key, which is safe only because it stores each job's output unchanged."""
    monkeypatch.setattr(jobs, "WORKDIRS", tmp_path / "workers")
    output = {"saving_bn": {"2039": {"gross": 8.4123456789012345, "net": -0.1}}, "labels": ["floor", "cpi"], "n": 3}
    got = jobs.run_jobs([("t", {"i": 0})], workers=1, log=lambda m: None, cache=tmp_path / "cache",
                        runner=lambda kind, arg, workdir, engine_, stop: output)
    record = json.loads(engine.cache_path("t", engine.job_key("t", {"i": 0}), tmp_path / "cache").read_text())
    assert record["result"] == output and got == [engine._keys_to_int(output)]
    assert engine.cached("t", {"i": 0}, cache=tmp_path / "cache") == engine._keys_to_int(output)


def test_the_job_process_runs_the_engine_job(tmp_path):
    """python -m triple_lock.jobs --job INPUT OUTPUT runs engine._job (here on a stub job kind, without the model)."""
    inp, out = tmp_path / "in.json", tmp_path / "out.json"
    inp.write_text(json.dumps({"kind": "echo", "arg": {"x": 1}, "engine": engine.engine_semantics()}))
    script = ("import sys; from triple_lock import engine, jobs, model_horizon; "
              "model_horizon.install = lambda: None; engine.JOBS['echo'] = lambda arg: {'got': arg}; "
              "sys.exit(jobs.main(['--job', sys.argv[1], sys.argv[2]]))")
    code, _, err = jobs.run_child([sys.executable, "-c", script, str(inp), str(out)], cwd=tmp_path, env=ENV)
    assert code == 0, err
    assert json.loads(out.read_text()) == {"got": {"x": 1}}


# ── Process groups ──────────────────────────────────────────────────────


def test_run_child_starts_the_job_in_its_own_session(tmp_path):
    code, out, _ = jobs.run_child([sys.executable, "-c", "import os; print(os.getpid(), os.getpgrp(), os.getsid(0))"],
                                    cwd=tmp_path)
    pid, pgid, sid = map(int, out.split())
    assert code == 0 and pid == pgid == sid and pgid != os.getpgrp()


def test_run_child_tells_the_job_its_parent(tmp_path):
    _, out, _ = jobs.run_child([sys.executable, "-c", f"import os; print(os.environ['{jobs.PARENT_ENV}'])"],
                                 cwd=tmp_path)
    assert int(out) == os.getpid()


def test_run_child_starts_nothing_once_the_build_is_stopping(tmp_path):
    stop = threading.Event()
    stop.set()
    with pytest.raises(jobs.Aborted):
        jobs.run_child([sys.executable, "-c", "open('ran', 'w')"], cwd=tmp_path, stop=stop)
    assert not (tmp_path / "ran").exists()


def test_kill_children_stops_a_job_and_what_it_started(tmp_path):
    pids = tmp_path / "pids"
    (tmp_path / "sleeper.py").write_text(SLEEPER)
    result = {}
    thread = threading.Thread(target=lambda: result.update(code=jobs.run_child(
        [sys.executable, str(tmp_path / "sleeper.py"), str(pids)], cwd=tmp_path)[0]))
    thread.start()
    job, grandchild = read_pids(pids, 2)
    stop = threading.Event()
    assert jobs.kill_children(stop, grace=5) == 1
    thread.join(20)
    assert not thread.is_alive() and result["code"] < 0 and stop.is_set()
    assert wait_until(lambda: not alive(job) and not alive(grandchild))


# A job that starts a grandchild in its own process group, which closes its output so communicate() can return,
# records both pids and exits at once, leaving the grandchild running.
LEAVER = textwrap.dedent("""
    import os, subprocess, sys
    out = sys.argv[1]
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(out, "a") as f:
        f.write(f"{os.getpid()} {child.pid}\\n")
""")


def test_run_child_stops_what_a_finished_job_left_behind(tmp_path):
    """The job exits 0 with a grandchild still running in its group (María's review of #10): run_child kills the
    group before it returns, so nothing keeps using the worker directory after its lock is released."""
    pids = tmp_path / "pids"
    (tmp_path / "leaver.py").write_text(LEAVER)
    code, _, _ = jobs.run_child([sys.executable, str(tmp_path / "leaver.py"), str(pids)], cwd=tmp_path)
    assert code == 0
    _, grandchild = read_pids(pids, 2)
    assert wait_until(lambda: not alive(grandchild), timeout=10)
    assert not jobs._children


def test_a_second_signal_does_not_cut_the_kill_short(tmp_path):
    """A job that ignores SIGTERM still dies when another signal interrupts kill_children's grace period."""
    stubborn = ("import os, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)")
    thread = threading.Thread(target=jobs.run_child, args=([sys.executable, "-c", stubborn, str(tmp_path / "pid")],),
                              kwargs={"cwd": tmp_path})
    thread.start()
    (job,) = read_pids(tmp_path / "pid", 1)
    with pytest.raises(jobs.Terminated):
        with jobs.terminate_on_signals():
            threading.Timer(0.5, os.kill, (os.getpid(), signal.SIGTERM)).start()
            jobs.kill_children(grace=30)
    thread.join(20)
    assert wait_until(lambda: not alive(job), 10)


BUILD = textwrap.dedent("""
    import signal, sys
    from pathlib import Path
    from triple_lock import jobs

    # As a build started from a terminal: whatever the test runner's own dispositions (a CI shell may start it with
    # SIGINT or SIGHUP ignored), SIGINT raises KeyboardInterrupt and SIGHUP is not ignored.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGHUP, signal.SIG_DFL)

    tmp = Path(sys.argv[1])
    jobs.WORKDIRS = tmp / "workers"

    def runner(kind, arg, workdir, engine_, stop):
        code, _, err = jobs.run_child([sys.executable, str(tmp / "sleeper.py"), str(tmp / "pids")], cwd=workdir,
                                        stop=stop)
        raise RuntimeError(f"exit {code}")

    jobs.run_jobs([("t", {"i": i}) for i in range(2)], workers=2, cache=tmp / "cache", runner=runner)
""")


@pytest.mark.parametrize("sig, code", [(signal.SIGTERM, 128 + signal.SIGTERM), (signal.SIGHUP, 128 + signal.SIGHUP),
                                       (signal.SIGINT, -signal.SIGINT)])
def test_a_stopped_build_stops_its_jobs(tmp_path, sig, code):
    """SIGTERM, SIGHUP or Ctrl-C to a build: every running job and its children are killed, and the build exits
    (Terminated's 128 + signal; an uncaught KeyboardInterrupt re-raises SIGINT) instead of waiting for them."""
    (tmp_path / "sleeper.py").write_text(SLEEPER)
    (tmp_path / "build.py").write_text(BUILD)
    build = subprocess.Popen([sys.executable, str(tmp_path / "build.py"), str(tmp_path)], env=ENV,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        pids = read_pids(tmp_path / "pids", 4)
        build.send_signal(sig)
        _, err = build.communicate(timeout=30)
    finally:
        if build.poll() is None:  # never leave a build behind a failed test
            build.kill()
            build.wait(10)
        recorded = (tmp_path / "pids").read_text().split() if (tmp_path / "pids").exists() else []
        for pid in map(int, recorded):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, signal.SIGKILL)  # a recorded sleeper's group: the job and its grandchild
    assert build.returncode == code, err
    assert wait_until(lambda: not any(alive(p) for p in pids)), [p for p in pids if alive(p)]


LOST_PARENT = textwrap.dedent("""
    import sys, time
    from triple_lock import jobs

    code, out, err = jobs.run_child([sys.executable, "-c", (
        "import os, sys, time; from triple_lock import jobs; jobs.watch_parent(0.1); "
        "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)"), sys.argv[1]], cwd=".")
""")


def test_a_job_stops_itself_when_its_build_is_killed_outright(tmp_path):
    """SIGKILL cannot be handled: the job notices its build is gone (watch_parent) and stops."""
    (tmp_path / "build.py").write_text(LOST_PARENT)
    build = subprocess.Popen([sys.executable, str(tmp_path / "build.py"), str(tmp_path / "pid")], env=ENV,
                             cwd=tmp_path)
    (job,) = read_pids(tmp_path / "pid", 1)
    assert alive(job)
    build.kill()
    build.wait(10)
    assert wait_until(lambda: not alive(job), 10)


def test_watch_parent_does_nothing_outside_run_child(monkeypatch):
    monkeypatch.delenv(jobs.PARENT_ENV, raising=False)
    assert jobs.watch_parent() is None


def test_terminate_on_signals_raises_in_the_main_thread_and_restores_handlers():
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(jobs.Terminated) as err:
        with jobs.terminate_on_signals():
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)
    assert err.value.code == 128 + signal.SIGTERM
    assert signal.getsignal(signal.SIGTERM) == before


def test_terminate_on_signals_keeps_an_ignored_sighup_ignored():
    """A build started under nohup must survive the terminal closing."""
    before = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with jobs.terminate_on_signals():
            assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
            assert signal.getsignal(signal.SIGTERM) not in (signal.SIG_DFL, signal.SIG_IGN)
    finally:
        signal.signal(signal.SIGHUP, before)


# ── Worker directories ──────────────────────────────────────────────────


def hold(workdir, released, acquired):
    with jobs.slot_lock(workdir, log=lambda m: None):
        acquired.set()
        released.wait(20)


def test_slot_lock_names_the_holder_and_times_out(tmp_path):
    released, acquired, logs = threading.Event(), threading.Event(), []
    holder = threading.Thread(target=hold, args=(tmp_path / "efrs0", released, acquired))
    holder.start()
    assert acquired.wait(10)
    try:
        with pytest.raises(jobs.LockTimeout, match=f"held by pid {os.getpid()} since"):
            with jobs.slot_lock(tmp_path / "efrs0", log=logs.append, timeout=0.5, poll=0.05):
                pytest.fail("acquired a held lock")
    finally:
        released.set()
        holder.join(10)
    assert logs and f"held by pid {os.getpid()}" in logs[0]
    with jobs.slot_lock(tmp_path / "efrs0", log=logs.append, timeout=0.5, poll=0.05):
        pass  # free again once the holder lets go


def test_slot_lock_gives_up_when_the_build_stops(tmp_path):
    released, acquired, stop = threading.Event(), threading.Event(), threading.Event()
    holder = threading.Thread(target=hold, args=(tmp_path / "efrs0", released, acquired))
    holder.start()
    assert acquired.wait(10)
    threading.Timer(0.2, stop.set).start()
    start = time.monotonic()
    try:
        with pytest.raises(jobs.Aborted):
            with jobs.slot_lock(tmp_path / "efrs0", log=lambda m: None, timeout=60, poll=0.05, stop=stop):
                pytest.fail("acquired a held lock")
    finally:
        released.set()
        holder.join(10)
    assert time.monotonic() - start < 5


def test_slot_lock_waits_for_a_holder_that_lets_go(tmp_path):
    released, acquired, logs = threading.Event(), threading.Event(), []
    holder = threading.Thread(target=hold, args=(tmp_path / "efrs0", released, acquired))
    holder.start()
    assert acquired.wait(10)
    threading.Timer(0.3, released.set).start()
    with jobs.slot_lock(tmp_path / "efrs0", log=logs.append, timeout=10, poll=0.05):
        assert (tmp_path / "efrs0" / ".lock").read_text().startswith(f"pid {os.getpid()} since")
    holder.join(10)
    assert logs[0].startswith("  waiting for efrs0") and logs[-1].startswith("  efrs0 free after")
    assert (tmp_path / "efrs0" / ".lock").read_text() == ""
