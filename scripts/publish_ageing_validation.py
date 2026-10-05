#!/usr/bin/env python3
"""Audit private inputs and publish completed cached full-model ageing runs."""

import argparse
import json
import sys
from pathlib import Path

from triple_lock import ageing_publication as publication, ageing_validation as validation, engine
from triple_lock.config import REPO


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved-plan", type=Path, required=True, help="Full original job plan and calculation metadata saved before the model jobs")
    parser.add_argument("--calibration-year", type=int)
    parser.add_argument("--execution-report", type=Path, required=True, help="Original aggregate pilot report with calculation head and actual worker counts")
    parser.add_argument("--input-audit", type=Path, help="Private input audit already collected against exactly this saved plan")
    parser.add_argument("-o", "--output", type=Path, default=REPO / ".cache" / "ageing-pilot-approved.json")
    args = parser.parse_args(argv)
    if args.saved_plan:
        plan = engine._keys_to_int(json.loads(args.saved_plan.read_text()))
        if plan.get("calibration_year") is None:
            parser.error("saved plan must have an explicit calibration year")
    else:
        if args.calibration_year is None:
            parser.error("provide --calibration-year or --saved-plan")
        plan = validation.validation_plan(calibration_year=args.calibration_year)
    try:
        metadata = json.loads(args.execution_report.read_text()) if args.execution_report else None
        audit = json.loads(args.input_audit.read_text()) if args.input_audit else None
        publication.publish_cached(plan, args.output, audit=audit, execution_metadata=metadata)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, publication.PublicationBlocked) else type(exc).__name__
        print(f"Publication blocked: {reason}; no private values disclosed", file=sys.stderr)
        return 1
    print(f"Wrote publication-approved aggregate validation to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
