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
    """One full run of trajectories.obr_premium_spec, written to ``out`` without its record-level fields."""
    import json
    from pathlib import Path

    from . import engine, trajectories
    from .central import central_path

    if Path(out).resolve() in (OUTPUT.resolve(), DASHBOARD_COPY.resolve()):
        raise SystemExit("--obr-premium must not overwrite the results file or its dashboard copy")
    spec = trajectories.obr_premium_spec(central_path())
    run = engine.run_jobs([("path", {k: v for k, v in spec.items() if k not in ("id", "label", "source")})],
                          workers=1, slot_prefix="efrs")[0]
    # Never write which survey record moves a figure, its weight or amounts: keep only how much it contributes
    # (as pipeline.redact_records does, without importing the full build).
    keep = ("contribution_bn", "share_of_income_change")
    run.pop("bundle", None)
    run["largest_household"] = {k: run["largest_household"][k] for k in keep}
    run["concentration_by_year"] = {y: {k: c[k] for k in keep} for y, c in run["concentration_by_year"].items()}
    result = {k: spec[k] for k in ("id", "label", "source", "triple_lock_rates")} | {"run": run}
    Path(out).write_text(json.dumps(result, indent=1, default=float, allow_nan=False) + "\n")
    print(f"Run written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
