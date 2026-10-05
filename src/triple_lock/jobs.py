"""Running engine jobs: each in its own process and session, in a worker directory, cached by input.

How jobs are scheduled, isolated and stopped never changes what one computes,
so this module is not part of the job cache key (engine.ENGINE_FILES): an edit
here reruns nothing. The cache keeps each job's output as the job wrote it.

* ``run_jobs`` runs [(kind, arg), ...] on a pool of workers, reusing cached
  results. Each worker owns a directory under ``WORKDIRS`` that keeps the
  downloaded dataset between jobs (the managed loader reuses a file whose sha256
  matches). When a job fails it is named at once, the queued jobs are cancelled,
  the running ones finish (and are cached), and every failed job is reported.
* ``run_child`` starts each job in a new session, so stopping its process group
  stops anything it started. Ctrl-C, SIGTERM or SIGHUP (``terminate_on_signals``)
  stops every running job's group at once (``kill_children``); a job whose build
  dies without that (SIGKILL) notices it has lost its parent and stops itself
  (``watch_parent``).
* ``slot_lock`` holds a worker directory against other processes; a worker
  waiting for one logs who holds it and gives up after ``LOCK_TIMEOUT_S``.

``python -m triple_lock.jobs --job INPUT OUTPUT`` is the job process: it watches
its parent, then runs ``engine._job``.
"""

import argparse
import contextlib
import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .config import JOB_CACHE, REPO
from .engine import SourceChanged, _canonical, _keys_to_int, cache_path, cached, engine_semantics, job_key, package_versions

WORKDIRS = REPO / ".cache" / "workers"
# A worker directory another process holds this long fails the job (the holder is named in the log meanwhile).
LOCK_TIMEOUT_S = 3600
LOCK_POLL_S = 2.0
LOCK_LOG_EVERY_S = 300
# Seconds a stopped job gets between SIGTERM and SIGKILL; how often a job checks that its build is still alive.
KILL_GRACE_S = 10
PARENT_POLL_S = 2.0
PARENT_ENV = "TRIPLE_LOCK_PARENT_PID"


class LockTimeout(RuntimeError):
    """Another process held a worker directory for longer than the timeout."""


class Aborted(RuntimeError):
    """The build was stopping (a failed job or a signal), so this job did not start."""


class Terminated(SystemExit):
    """SIGTERM or SIGHUP, raised in the main thread so the running jobs are stopped before the build exits."""


_children = {}  # pid -> Popen: every job process running now
_children_lock = threading.Lock()


_children = {}  # pid -> Popen: every job process running now
_children_lock = threading.Lock()


def _signal_group(pgid, sig):
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def _reap_group(proc):
    proc.wait()
    _signal_group(proc.pid, signal.SIGKILL)


def run_child(cmd, cwd, env=None, stop=None):
    """Run ``cmd`` to the end in a new session; returns (returncode, stdout, stderr).

    The child leads its own process group, so stopping the group stops anything
    it started too. It is registered while it runs, for kill_children; if the
    wait is interrupted in this thread (Ctrl-C, or a signal raised as an
    exception) the group is killed before the exception goes on. When the child
    exits, anything it left running in its group is killed (at once, and again
    before the worker directory is released), so no descendant can keep using
    it or hold its output open (one that starts its own session with setsid
    leaves the group and is not reached). The child is told this process's id
    (PARENT_ENV) for watch_parent. Once ``stop`` is set this starts nothing and
    raises Aborted.
    """
    env = {**os.environ, **(env or {}), PARENT_ENV: str(os.getpid())}
    proc = None
    try:
        with _children_lock:
            if stop is not None and stop.is_set():
                raise Aborted("the build is stopping")
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, start_new_session=True)
            _children[proc.pid] = proc
        # When the job exits, anything it left running in its group goes too: it would otherwise outlive the build,
        # or hold the output pipes open and keep communicate() waiting.
        threading.Thread(target=_reap_group, args=(proc,), name=f"reap-{proc.pid}", daemon=True).start()
        out, err = proc.communicate()
    except BaseException:
        if proc is not None:
            _signal_group(proc.pid, signal.SIGKILL)
            proc.wait()
        raise
    finally:
        if proc is not None:
            # The group outlives the child while any descendant remains in it (one that closed its output, so
            # communicate() returned): stop those too, still under the registry, so kill_children sees the job
            # meanwhile.
            _signal_group(proc.pid, signal.SIGKILL)
            with _children_lock:
                _children.pop(proc.pid, None)
    return proc.returncode, out, err


def kill_children(stop=None, grace=KILL_GRACE_S):
    """Stop every running job: SIGTERM each one's process group, SIGKILL after ``grace`` seconds; returns how many.

    Sets ``stop`` first, under the registry's lock, so no job starts afterwards.
    """
    with _children_lock:
        if stop is not None:
            stop.set()
        procs = list(_children.values())
    try:
        for p in procs:
            _signal_group(p.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        for p in procs:
            with contextlib.suppress(subprocess.TimeoutExpired):
                p.wait(timeout=max(0.0, deadline - time.monotonic()))
    finally:  # even when a second signal cuts the grace period short
        for p in procs:
            _signal_group(p.pid, signal.SIGKILL)  # whatever ignored SIGTERM, and anything a job left in its group
    return len(procs)


def watch_parent(interval=PARENT_POLL_S):
    """In a process run_child started: kill it, and anything it started, once the process that started it is gone.

    A build killed outright (SIGKILL) cannot stop its jobs, and macOS has no
    parent-death signal, so a daemon thread polls the parent's id: a job whose
    build dies is re-parented and stops within ``interval`` seconds instead of
    running on for hours. Does nothing in a process run_child did not start.
    """
    expected = os.environ.get(PARENT_ENV)
    if not expected:
        return None
    expected = int(expected)

    def stop_self():
        if os.getpgrp() == os.getpid():  # run_child made this process its group's leader
            os.killpg(os.getpid(), signal.SIGKILL)
        os.kill(os.getpid(), signal.SIGKILL)

    def loop():
        while True:
            if os.getppid() != expected:
                stop_self()
            time.sleep(interval)

    thread = threading.Thread(target=loop, name="watch-parent", daemon=True)
    thread.start()
    return thread


@contextlib.contextmanager
def terminate_on_signals(signums=(signal.SIGTERM, signal.SIGHUP)):
    """Within the block SIGTERM and SIGHUP raise Terminated in the main thread instead of ending the process at once,
    so whatever is waiting on a job can stop it first. A signal already ignored (nohup) stays ignored; off the main
    thread this does nothing."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def raise_terminated(signum, frame):
        raise Terminated(128 + signum)

    previous = {}
    for s in signums:
        if signal.getsignal(s) != signal.SIG_IGN:
            previous[s] = signal.signal(s, raise_terminated)
    try:
        yield
    finally:
        for s, handler in previous.items():
            signal.signal(s, signal.SIG_DFL if handler is None else handler)


def _lock_holder(path):
    with contextlib.suppress(OSError):
        text = Path(path).read_text().strip()
        if text:
            return text
    return "another process"


@contextlib.contextmanager
def slot_lock(workdir, log=print, timeout=LOCK_TIMEOUT_S, poll=LOCK_POLL_S, log_every=LOCK_LOG_EVERY_S, stop=None):
    """Hold the exclusive lock on a worker directory for the block, never waiting for it silently or for ever.

    While another process holds it, log who (the holder writes its pid and start
    time into the lock file) every ``log_every`` seconds and try again every
    ``poll``; give up with LockTimeout after ``timeout`` seconds, or with Aborted
    as soon as ``stop`` is set.
    """
    import fcntl

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / ".lock"
    with open(path, "a+") as f:  # "a+", not "w": opening must not erase the holder's line
        start, next_log, logged = time.monotonic(), 0.0, False
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waited = time.monotonic() - start
                if waited >= timeout:
                    raise LockTimeout(f"{workdir} is still held by {_lock_holder(path)} after {waited:.0f}s: "
                                      "run one build at a time") from None
                if waited >= next_log:
                    log(f"  waiting for {workdir.name}: held by {_lock_holder(path)}")
                    next_log, logged = next_log + log_every, True
                if stop is None:
                    time.sleep(poll)
                elif stop.wait(poll):
                    raise Aborted(f"the build stopped while waiting for {workdir.name}") from None
        if logged:
            log(f"  {workdir.name} free after {time.monotonic() - start:.0f}s")
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} since {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
        f.flush()
        try:
            yield
        finally:
            f.seek(0)
            f.truncate()
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)


def _run_isolated(kind, arg, workdir, engine, stop=None):
    """Run one job in its own process, session and working directory (the dataset lands in ./data and stays)."""
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(_canonical([kind, arg]).encode()).hexdigest()[:12]
    inp, out = workdir / f"input-{tag}.json", workdir / f"output-{tag}.json"
    inp.write_text(json.dumps({"kind": kind, "arg": arg, "engine": engine}, default=float))
    try:
        code, _, stderr = run_child([sys.executable, "-m", "triple_lock.jobs", "--job", str(inp), str(out)],
                                    cwd=workdir, env={"PYTHONPATH": str(REPO / "src")}, stop=stop)
        if code != 0:
            raise RuntimeError(f"{kind} job failed in {workdir} (exit {code}):\n{stderr[-4000:]}")
        return json.loads(out.read_text())
    finally:
        inp.unlink(missing_ok=True)
        out.unlink(missing_ok=True)


def run_jobs(jobs, workers=3, slot_prefix="slot", log=print, cache=JOB_CACHE, runner=None,
             lock_timeout=LOCK_TIMEOUT_S):
    """Run [(kind, arg), ...], reusing cached results; returns the results in order.

    Each worker owns a directory under WORKDIRS, so its downloaded dataset
    persists between jobs; slot_lock keeps a second build (or script) from using
    it at the same time. When a job fails the queued jobs are cancelled, the
    running ones finish and stay cached, and every failed job is reported,
    including any that failed while the others finished. Ctrl-C, SIGTERM or
    SIGHUP stops every running job at once (kill_children). ``runner(kind, arg,
    workdir, engine, stop)`` runs one job (default _run_isolated).
    """
    from concurrent.futures import FIRST_EXCEPTION, wait

    runner = runner or _run_isolated
    engine, packages = engine_semantics(), package_versions()
    results = [cached(kind, arg, engine, packages, cache) for kind, arg in jobs]
    todo = [i for i, r in enumerate(results) if r is None]
    log(f"{len(jobs) - len(todo)} of {len(jobs)} jobs cached; running {len(todo)} on {workers} workers")
    if not todo:
        return results
    Path(cache).mkdir(parents=True, exist_ok=True)
    slots = queue.Queue()
    for s in range(workers):
        slots.put(s)
    done = [0]
    stop = threading.Event()

    def work(i):
        try:
            return run_one(i)
        except BaseException:
            stop.set()  # at once: this worker would otherwise take the next queued job before the main thread looks
            raise

    def run_one(i):
        kind, arg = jobs[i]
        s = slots.get()
        try:
            with slot_lock(WORKDIRS / f"{slot_prefix}{s}", log, lock_timeout, stop=stop):
                started = datetime.now(timezone.utc)
                result = runner(kind, arg, WORKDIRS / f"{slot_prefix}{s}", engine, stop)
        finally:
            slots.put(s)
        if engine_semantics() != engine:
            raise SourceChanged("engine sources changed during the build")
        key = job_key(kind, arg, engine, packages)
        record = {"key": key, "kind": kind, "arg": arg, "engine": engine, "packages": packages,
                  "started_at": started.isoformat(timespec="seconds"),
                  "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": result}
        path = cache_path(kind, key, cache)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, default=float, allow_nan=False))
        tmp.replace(path)
        done[0] += 1
        log(f"  {kind} job done ({done[0]}/{len(todo)}) in "
            f"{(datetime.now(timezone.utc) - started).total_seconds():.0f}s")
        return _keys_to_int(result)

    def failure(f):
        return f"{jobs[futures[f]][0]} job {job_key(*jobs[futures[f]], engine, packages)[:12]}: {f.exception()}"

    pool = ThreadPoolExecutor(workers)
    futures, reported = {}, set()
    with terminate_on_signals():
        try:
            futures = {pool.submit(work, i): i for i in todo}
            finished, pending = wait(futures, return_when=FIRST_EXCEPTION)
            if pending:  # a job failed: say which now, start nothing more, and let the running jobs finish
                for f in finished:
                    if f.exception() is not None and not isinstance(f.exception(), Aborted):
                        log(f"Failed: {failure(f)}")
                        reported.add(f)
                log("Cancelling the queued jobs and waiting for the running ones")
                stop.set()
                for f in pending:
                    f.cancel()
            pool.shutdown(wait=True)
        except BaseException:  # Ctrl-C, SIGTERM or SIGHUP (Terminated), or an error here: stop the running jobs now
            try:
                log(f"Stopping: killed {kill_children(stop)} running job(s)")
            finally:
                for f in futures:
                    f.cancel()
                pool.shutdown(wait=True, cancel_futures=True)
                for f in futures:  # what had failed before the stop, which the exception going on does not say
                    if f.done() and not f.cancelled() and f.exception() is not None and f not in reported:
                        log(f"Failed before the stop: {failure(f)}")
            raise
    failed, not_run = [], 0
    for f in futures:
        if f.cancelled() or isinstance(f.exception(), Aborted):
            not_run += 1
        elif f.exception() is not None:
            failed.append(failure(f))
    if failed or not_run:
        raise RuntimeError(f"{len(failed)} job(s) failed and {not_run} did not run; the rest finished and are "
                           "cached:\n" + "\n".join(failed))
    for f, i in futures.items():
        results[i] = f.result()
    return results


def main(argv=None):
    """The job process: stop if the build that started it dies, then run the job."""
    from .engine import _job

    parser = argparse.ArgumentParser(description="One full-model job (internal)")
    parser.add_argument("--job", nargs=2, metavar=("INPUT", "OUTPUT"), required=True)
    args = parser.parse_args(argv)
    watch_parent()
    _job(*args.job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
