#!/usr/bin/env python3
"""The four-way ageing factorial plus legacy/total controls on the engine's own path jobs, aggregates only (triple_lock.ageing_validation).

    python scripts/validate_ageing.py --plan                     # job counts and the paired draws; runs nothing
    python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json

The rebuild's step 3 (docs/REBUILD.md): every run but --plan starts PolicyEngine jobs whose net savings depend on the
Housing Benefit passport, so it first runs the build's preflight and refuses a policyengine-uk that keys the passport
on Guarantee Credit entitlement (pipeline.housing_benefit_passport_preflight, policyengine-uk#1927). The check sits
here, not in triple_lock.ageing_validation, whose bytes the pilot's source correspondence binds.
"""

import sys

from triple_lock.ageing_validation import main
from triple_lock.pipeline import housing_benefit_passport_preflight


def run(argv=None, preflight=housing_benefit_passport_preflight):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not {"--plan", "-h", "--help"} & set(argv):
        preflight()
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(run())
