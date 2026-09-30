"""CLI entry point for the ``triple-lock-build`` command."""

import argparse

from .config import DASHBOARD_COPY, OUTPUT


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The Burnham plan against the triple lock: every figure from full PolicyEngine UK runs"
    )
    parser.add_argument("--workers", type=int, default=3, help="concurrent Enhanced FRS model processes")
    parser.add_argument("--sensitivity-workers", type=int, default=2,
                        help="concurrent Microcosm model processes (about 35 GB of memory each)")
    parser.add_argument("--allow-dirty", action="store_true", help="build from a tree with uncommitted changes")
    args = parser.parse_args(argv)

    from .pipeline import build, write

    write(build(workers=args.workers, allow_dirty=args.allow_dirty, sensitivity_workers=args.sensitivity_workers),
          [OUTPUT, DASHBOARD_COPY])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
