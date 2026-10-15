"""Check that a results file can be given its assumptions block, before a full rebuild relies on it.

The build writes the block at its very end (pipeline.assumptions), and fails there if a figure is missing or a value
has no wording. Run this on the pilot's results (#14 §5) so a gap shows in seconds, not after the rebuild:

    PYTHONPATH=src python scripts/check_assumptions.py path/to/results.json

Prints each item's key and title, or the reason the block cannot be written (exit status 1).
"""

import json
import sys
from pathlib import Path

from triple_lock.pipeline import MissingFigure, assumptions


def main(path):
    try:
        block = assumptions(json.loads(Path(path).read_text()))
    except MissingFigure as error:
        print(f"{path}: no assumptions block: {error}")
        return 1
    for item in block:
        print(f"{item['key']}: {item['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/results.json"))
