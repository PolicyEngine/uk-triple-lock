"""Run the triple lock pipeline and write data/triple_lock_results.json.

Equivalent to the ``triple-lock-build`` console script. Run from the
repository root: policyengine.py looks for the certified dataset in ./data.
"""

from triple_lock.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
