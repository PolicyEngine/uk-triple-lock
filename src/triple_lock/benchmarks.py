"""Published costings of the triple lock, paired with the closest figure here.

``data/benchmarks.csv`` lists the verified entries from docs/sources.md.
Each row names ``our_metric``, a dotted path into the results; the loader
resolves it against the results being built and raises if the file, a
column or a path is missing.
"""

import csv

from .config import BENCHMARKS_CSV
COLUMNS = [
    "id",
    "publisher",
    "title",
    "date",
    "url",
    "figure_text",
    "comparison",
    "our_metric",
    "like_for_like",
    "note",
    "verified",
]
VERIFIED = {"true": True, "false": False}
LIKE_FOR_LIKE = {"yes", "partial", "no"}


def resolve(results, dotted_path):
    """Follow a dotted path; a numeric part indexes a list or matches an integer (year) key."""
    node = results
    for part in dotted_path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        elif part not in node and part.lstrip("-").isdigit() and int(part) in node:
            node = node[int(part)]
        else:
            node = node[part]
    return node


def load_benchmarks(results, path=BENCHMARKS_CSV, skip_expected_value=False):
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path} is missing columns {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} has no rows")
    out = []
    for row in rows:
        if skip_expected_value and row["our_metric"].startswith("expected_value."):
            continue
        for column in COLUMNS:
            if not row[column].strip():
                raise ValueError(f"{path}: {row['id']!r} has an empty {column}")
        if row["like_for_like"] not in LIKE_FOR_LIKE:
            raise ValueError(f"{path}: {row['id']!r} like_for_like must be one of {sorted(LIKE_FOR_LIKE)}")
        if not row["url"].startswith("https://"):
            raise ValueError(f"{path}: {row['id']!r} url is not https")
        value = resolve(results, row["our_metric"])
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: {row['id']!r} our_metric does not point at a number")
        if row["verified"] not in VERIFIED:
            raise ValueError(f"{path}: {row['id']!r} verified must be true or false")
        out.append({**{c: row[c] for c in COLUMNS}, "verified": VERIFIED[row["verified"]], "our_value": value})
    return out
