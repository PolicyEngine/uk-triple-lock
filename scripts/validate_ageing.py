#!/usr/bin/env python3
"""The four-way ageing factorial plus legacy/total controls, aggregates only.

    python scripts/validate_ageing.py --plan
    python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json

Both this wrapper and ``python -m triple_lock.ageing_validation`` delegate to the same
entry point. Real runs require the Housing Benefit Guarantee Credit receipt-passport
preflight (policyengine-uk#1927) and retain its observations in report provenance.
"""

from triple_lock.ageing_validation import main


def run(argv=None):
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(run())
