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
    parser.add_argument("--obr-premium", metavar="OUT",
                        help="only run the central path with the triple lock on the OBR's uprating line; write that "
                             "run (records redacted) to OUT, not the results file")
    args = parser.parse_args(argv)

    if args.obr_premium:
        return obr_premium(args.obr_premium)

    from .engine import terminate_on_signals
    from .pipeline import build, write

    # SIGTERM or SIGHUP stops the running model processes before the build exits (engine.run_jobs, run_child).
    with terminate_on_signals():
        write(build(workers=args.workers, allow_dirty=args.allow_dirty, sensitivity_workers=args.sensitivity_workers),
              [OUTPUT, DASHBOARD_COPY])
    return 0


def obr_premium(out):
    """One full run of trajectories.obr_premium_spec, written to ``out`` with record-level fields redacted."""
    from pathlib import Path

    from . import engine, trajectories
    from .central import central_path
    from .pipeline import redact_records, write

    if Path(out).resolve() in (OUTPUT.resolve(), DASHBOARD_COPY.resolve()):
        raise SystemExit("--obr-premium must not overwrite the results file or its dashboard copy")
    spec = trajectories.obr_premium_spec(central_path())
    run = engine.run_jobs([("path", {k: v for k, v in spec.items() if k not in ("id", "label", "source")})],
                          workers=1, slot_prefix="efrs")[0]
    run.pop("bundle", None)
    write(redact_records({k: spec[k] for k in ("id", "label", "source")} | {"run": run}), [out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
