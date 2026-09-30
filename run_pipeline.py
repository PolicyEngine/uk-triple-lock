"""Build data/results.json (and the dashboard's copy).

Equivalent to the ``triple-lock-build`` console script. Each model job runs in
its own working directory under .cache/workers, where policyengine.py keeps the
certified dataset; results are cached under .cache/jobs.
"""

from triple_lock.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
