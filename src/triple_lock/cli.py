"""CLI entry point for the ``triple-lock-build`` command."""

import argparse
import json
from pathlib import Path

from .config import DASHBOARD_COPY, ERROR_CSV, N_DRAWS, OUTPUT


def write_results(results, paths):
    text = json.dumps(results, indent=2, default=str) + "\n"
    for path in paths:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"Results written to {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cost, distribution and uncertainty of State Pension uprating rules"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--errors", type=Path, default=ERROR_CSV)
    parser.add_argument("--draws", type=int, default=N_DRAWS)
    parser.add_argument(
        "--sync",
        type=Path,
        nargs="*",
        default=[DASHBOARD_COPY],
        help="further copies of the results file (default: the dashboard's copy)",
    )
    args = parser.parse_args(argv)

    from .pipeline import DATASET_ENV, dataset_override, run_full_pipeline

    committed = {OUTPUT.resolve(), DASHBOARD_COPY.resolve()}
    if dataset_override() is not None and committed & {Path(p).resolve() for p in [args.output, *args.sync]}:
        parser.error(f"{DATASET_ENV} is set: pass --output elsewhere and an empty --sync, "
                     "so the committed results are not overwritten")

    results = run_full_pipeline(error_csv=args.errors.resolve(), n_draws=args.draws)
    write_results(results, [args.output, *args.sync])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
