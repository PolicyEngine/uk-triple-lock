"""Rerun a build or bridge command after a host-admission refusal, until it succeeds or fails otherwise.

Both runners stop on a refusal (``triple_lock.host.HostSaturated``) and keep
every finished job in their cache, so a rerun repeats nothing that finished.
This wrapper reruns only when the attempt's last Python exception is
HostSaturated and every failed job it lists was refused admission. Any other
failure, an interrupt (130, 143), or heavy_run.sh's memory ceiling (137) or
nice refusal (75) ends it with that attempt's exit code. Each attempt is
appended to ``--log`` as one JSON line.

usage: python scripts/resume_after_host_refusal.py --log PATH [--wait-seconds 600] [--max-attempts 50] -- COMMAND...
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

HOST_SATURATED = "triple_lock.host.HostSaturated"
# jobs.host_admission (build), bridge memory_check before a batch, bridge run_batch while it runs.
REFUSALS = ("build job admission refused", "Host saturated", "bridge stopped because host saturation was observed")
JOB_LINE = re.compile(r"^\S+ job [0-9a-f]{12}: (.*)$")  # jobs.run_jobs: "<kind> job <key[:12]>: <exception>"
NEVER_RERUN = {0, 75, 130, 137, 143}


def final_exception(stderr):
    """The type and message lines of the last Python traceback in ``stderr``, or None."""
    marker = "Traceback (most recent call last):"
    start = stderr.rfind(marker)
    if start < 0:
        return None
    lines = stderr[start + len(marker):].splitlines()
    for k, line in enumerate(lines):
        if line and not line[0].isspace():  # frames are indented; the exception line is not
            kind, _, first = line.partition(": ")
            return kind, [first, *lines[k + 1:]]
    return None


def is_host_refusal(returncode, stderr):
    """True only when the attempt stopped because the host refused admission, and for no other reason."""
    if returncode in NEVER_RERUN or returncode < 0:
        return False
    final = final_exception(stderr)
    if final is None or final[0] != HOST_SATURATED:
        return False
    failed = [match.group(1) for match in map(JOB_LINE.match, final[1]) if match]
    if failed:
        return all(text.startswith(REFUSALS) for text in failed)
    return final[1][0].startswith(REFUSALS)


def run_attempt(command):
    """Run ``command`` with stdout inherited and stderr echoed and captured; returns (returncode, stderr)."""
    child = subprocess.Popen(command, stderr=subprocess.PIPE, text=True)
    previous = signal.signal(signal.SIGTERM, lambda signum, frame: child.terminate())
    captured = []
    try:
        for line in child.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()
            captured.append(line)
        return child.wait(), "".join(captured)
    finally:
        signal.signal(signal.SIGTERM, previous)


def resume(command, log, *, max_attempts=50, wait_seconds=600, run=run_attempt, sleep=time.sleep):
    """Attempt ``command`` until it succeeds, fails other than by a host refusal, or uses ``max_attempts``."""
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    returncode = None
    for attempt in range(1, max_attempts + 1):
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        returncode, stderr = run(command)
        outcome = ("succeeded" if returncode == 0 else
                   "host_refusal" if is_host_refusal(returncode, stderr) else "failed")
        final = final_exception(stderr)
        with log.open("a") as f:
            f.write(json.dumps({"attempt": attempt, "started_at": started,
                                "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "returncode": returncode, "outcome": outcome,
                                "exception": final[0] if final else None,
                                "message": final[1][0] if final else None}) + "\n")
        if outcome != "host_refusal":
            return returncode
        if attempt < max_attempts:
            print(f"resume_after_host_refusal: attempt {attempt} refused by the host; rerunning from cache in "
                  f"{wait_seconds:g} s", file=sys.stderr, flush=True)
            sleep(wait_seconds)
    print(f"resume_after_host_refusal: still refused after {max_attempts} attempts", file=sys.stderr, flush=True)
    return returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, required=True, help="JSON-lines record of every attempt")
    parser.add_argument("--wait-seconds", type=float, default=600)
    parser.add_argument("--max-attempts", type=int, default=50)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the command after --")
    if args.max_attempts < 1 or not args.wait_seconds >= 0:
        parser.error("--max-attempts must be at least 1 and --wait-seconds non-negative")
    return resume(command, args.log, max_attempts=args.max_attempts, wait_seconds=args.wait_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
