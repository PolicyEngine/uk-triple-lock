"""CLI entry point for the ``triple-lock-build`` command."""

import argparse

from .config import DASHBOARD_COPY, OUTPUT, SCENARIO_DIR


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The Burnham plan against the triple lock: every figure from full PolicyEngine UK runs"
    )
    parser.add_argument("--workers", type=int, default=3, help="concurrent Enhanced FRS model processes")
    parser.add_argument("--sensitivity-workers", type=int, default=2,
                        help="concurrent Microcosm model processes (about 35 GB of memory each)")
    parser.add_argument("--allow-dirty", action="store_true", help="build from a tree with uncommitted changes")
    parser.add_argument("--scenario", metavar="NAME",
                        help="only run the central path with one scenario's specified rates (obr_premium); write that "
                             "run, records redacted, to --out, not the results file")
    parser.add_argument("--out", help="where --scenario writes its run (default data/scenarios/NAME.json)")
    args = parser.parse_args(argv)

    if args.scenario:
        return scenario(args.scenario, args.out, args.allow_dirty)

    from .engine import terminate_on_signals
    from .pipeline import build, write

    # SIGTERM or SIGHUP stops the running model processes before the build exits (engine.run_jobs, run_child).
    with terminate_on_signals():
        write(build(workers=args.workers, allow_dirty=args.allow_dirty, sensitivity_workers=args.sensitivity_workers),
              [OUTPUT, DASHBOARD_COPY])
    return 0


def scenario(name, out=None, allow_dirty=False):
    """One scenario run (pipeline.scenario), written to ``out``; never to the results file or its dashboard copy."""
    from pathlib import Path

    from .engine import terminate_on_signals
    from .pipeline import scenario as run_scenario
    from .pipeline import write
    from .trajectories import SCENARIOS

    if name not in SCENARIOS:
        raise SystemExit(f"unknown scenario {name!r}: one of {sorted(SCENARIOS)}")
    out = Path(out) if out else SCENARIO_DIR / f"{name}.json"
    if out.resolve() in (OUTPUT.resolve(), DASHBOARD_COPY.resolve()):
        raise SystemExit("--scenario must not overwrite the results file or its dashboard copy")
    with terminate_on_signals():
        write(run_scenario(name, allow_dirty=allow_dirty), [out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
