"""Host admission for model jobs: a memory floor, and a load limit scaled to the host's CPUs.

On a shared host the one-minute load average measures contention, not danger: a
busy host slows a job, it neither changes what the job computes nor runs the
host out of memory. The memory floor is what protects the host and the run, so
each runner keeps its own floor and this module never changes one.

The load limit is ``TRIPLE_LOCK_MAX_LOAD_PER_CPU`` times the logical CPU count:
6 by default, Subfleet's own guard for background work (108 on an 18-CPU host).
A runner's ``--max-load-per-cpu`` overrides the environment. Every runner admits
through ``assess``, which refuses exactly when available memory is below the
floor or the load is above the limit (``refuses``), and returns the limits it
applied so the caller records them beside the reading.

Like scheduling (jobs.py), admission never changes what a job computes, so this
module is not part of the job cache key (engine.ENGINE_FILES).
"""

import math
import os

import psutil

MAX_LOAD_PER_CPU_ENV = "TRIPLE_LOCK_MAX_LOAD_PER_CPU"
DEFAULT_MAX_LOAD_PER_CPU = 6.0


class HostSaturated(RuntimeError):
    """Available memory is below the floor, or the one-minute load is above the limit."""

    def __init__(self, message, *, decisions=()):
        super().__init__(message)
        self.host_admissions = list(decisions)
        if len(self.host_admissions) == 1:
            self.host_admission = self.host_admissions[0]


def configuration(value=None, environ=None):
    """The per-CPU load limit and where it came from: ``value`` (a runner's flag), else the environment, else 6.

    Anything but a positive finite number is refused, never read as "no limit".
    """
    if value is not None:
        source = "flag"
    else:
        raw = (os.environ if environ is None else environ).get(MAX_LOAD_PER_CPU_ENV, "").strip()
        value, source = (raw, "environment") if raw else (DEFAULT_MAX_LOAD_PER_CPU, "default")
    try:
        per_cpu = float(value)
    except (TypeError, ValueError):
        per_cpu = math.nan
    if not (math.isfinite(per_cpu) and per_cpu > 0):
        raise ValueError(f"{MAX_LOAD_PER_CPU_ENV} / --max-load-per-cpu must be a positive finite number, not {value!r}")
    return {"max_load_per_cpu": per_cpu, "source": source, "environment_variable": MAX_LOAD_PER_CPU_ENV}


def max_load_per_cpu(value=None, environ=None):
    return configuration(value, environ)["max_load_per_cpu"]


def refuses(available_gib, load_1m, *, minimum_gib, load_limit):
    """Memory below the floor or load above the limit; a reading that is not a finite number refuses too."""
    if not (math.isfinite(available_gib) and math.isfinite(load_1m)):
        return True
    return available_gib < minimum_gib or load_1m > load_limit


def assess(available_gib, load_1m, cpu_count, minimum_gib, max_load_per_cpu=None):
    """The limits applied to one reading and whether it is admitted, for the caller to record before acting on it."""
    if type(cpu_count) is not int or cpu_count < 1:
        raise ValueError(f"cpu_count must be a positive integer, not {cpu_count!r}")
    per_cpu = configuration(max_load_per_cpu)["max_load_per_cpu"]
    limit = per_cpu * cpu_count
    return {"minimum_available_gib": minimum_gib, "max_load_per_cpu": per_cpu, "load_limit": limit,
            "admitted": not refuses(available_gib, load_1m, minimum_gib=minimum_gib, load_limit=limit)}


def describe(reading, applied):
    """One line naming what refused a reading: its memory against the floor and its load against the limit."""
    return (f"{reading['available_gib']:.1f} GiB available (floor {applied['minimum_available_gib']:g} GiB); "
            f"one-minute load {reading['load_1m']:.1f} (limit {applied['load_limit']:g} = "
            f"{applied['max_load_per_cpu']:g} x {reading['cpu_count']} CPUs)")


def measure():
    """Available memory (GiB), one-minute load and logical CPUs, now."""
    return {"available_gib": psutil.virtual_memory().available / 2**30, "load_1m": os.getloadavg()[0],
            "cpu_count": os.cpu_count() or 1}
