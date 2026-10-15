"""Remove single-survey-record diagnostics from the published results files.

FRS records are licensed data: nothing published may describe one record, including its weighted contribution to a
total. This drops every key in SINGLE_RECORD_KEYS, at any depth, from data/results.json and the dashboard's copy, and
rewrites both in the build's format (pipeline.write), so nothing else in either file changes.

    python scripts/redact_single_record_fields.py
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATHS = [REPO / "data" / "results.json", REPO / "dashboard" / "public" / "data" / "results.json"]

# Keep in step with tests/test_results.py::test_no_published_json_has_single_record_fields.
SINGLE_RECORD_KEYS = {"largest_household", "concentration_by_year", "largest_record_bn", "net_excluding_largest_record"}


def strip(obj):
    """Drop SINGLE_RECORD_KEYS at every depth, in place, keeping the order of everything else."""
    if isinstance(obj, dict):
        for key in [k for k in obj if k in SINGLE_RECORD_KEYS]:
            del obj[key]
        for value in obj.values():
            strip(value)
    elif isinstance(obj, list):
        for value in obj:
            strip(value)
    return obj


def dumps(results):
    # The build's writer (triple_lock.pipeline.write).
    return json.dumps(results, indent=1, default=float, allow_nan=False) + "\n"


def main():
    for path in PATHS:
        text = path.read_text()
        results = json.loads(text)
        if dumps(results) != text:
            raise SystemExit(f"{path} is not in the build's format: refusing to rewrite it")
        path.write_text(dumps(strip(results)))
        print(f"Redacted {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
