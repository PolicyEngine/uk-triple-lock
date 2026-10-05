#!/usr/bin/env python3
"""The four-way ageing factorial plus legacy/total controls on the engine's own path jobs, aggregates only (triple_lock.ageing_validation).

    python scripts/validate_ageing.py --plan                     # job counts and the paired draws; runs nothing
    python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json
"""

from triple_lock.ageing_validation import main


if __name__ == "__main__":
    raise SystemExit(main())
