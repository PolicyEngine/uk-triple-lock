"""CLI entry point for the ``triple-lock-build`` command."""

import argparse

from .config import DASHBOARD_COPY, OUTPUT, SCENARIO_DIR


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The Burnham plan against the triple lock: every figure from full PolicyEngine UK runs"
    )
    parser.add_argument("--workers", type=int, default=3, help="concurrent primary Microcosm model processes; start with 1 until peak memory is measured")
    parser.add_argument("--sensitivity-workers", type=int, default=1,
                        help="concurrent Enhanced FRS 1.58.2 sensitivity model processes")
    parser.add_argument("--allow-dirty", action="store_true", help="build from a tree with uncommitted changes")
    parser.add_argument("--uncertainty-ruling", choices=("a", "b", "c"),
                        help="record Max's d955 ruling: a scenario envelope, b model-conditional expected value, "
                             "c suspended-treatment screen")
    parser.add_argument("--uncertainty-handoff", help="directory containing ts_uncertainty's handoff.json")
    parser.add_argument("--pre-budget", action="store_true",
                        help="write an interim pre-Budget file (requires --uncertainty-ruling a or c): a shows scenarios "
                             "only; c shows a provisional model-conditional expected value with C2 dry-run checks "
                             "and the paired dataset cross-check, "
                             "until the binding post-Budget score (docs/REBUILD.md, Interim pre-Budget release)")
    parser.add_argument("--mean-path-scenarios", action="store_true",
                        help="run only paired ±0.5pp mean-path scenarios, independently of C1 adequacy")
    parser.add_argument("--scenario", metavar="NAME",
                        help="only rerun one scenario (obr_premium; a full build runs them all) and write it, records "
                             "redacted, to --out, not the results file")
    parser.add_argument("--without-mean-paths", action="store_true",
                        help="write a scenarios-first interim file to --out: every run of the full build except the "
                             "paired mean paths, with the same jobs, so the full build reuses them (needs ruling a, "
                             "or c on a binding handoff whose primary failed C2; docs/REBUILD.md, Scenarios first)")
    parser.add_argument("--out", help="where --scenario writes its run (default data/scenarios/NAME.json), or where "
                                      "--without-mean-paths writes its interim file (required)")
    args = parser.parse_args(argv)
    if args.scenario and args.mean_path_scenarios:
        parser.error("choose either --scenario or --mean-path-scenarios")
    if args.without_mean_paths and (args.scenario or args.mean_path_scenarios or args.pre_budget):
        parser.error("--without-mean-paths is a full build's interim file, not --scenario, --mean-path-scenarios "
                     "or --pre-budget")
    if args.without_mean_paths and not args.out:
        parser.error("--without-mean-paths requires --out: the interim file never replaces the results file")
    if args.out and not (args.scenario or args.mean_path_scenarios or args.without_mean_paths):
        parser.error("--out requires --scenario NAME, --mean-path-scenarios or --without-mean-paths")
    if args.pre_budget and (args.scenario or args.mean_path_scenarios):
        parser.error("--pre-budget labels a full build's results file, not --scenario or --mean-path-scenarios")
    if args.pre_budget and args.uncertainty_ruling not in ("a", "c"):
        parser.error("--pre-budget requires --uncertainty-ruling a or c; b is obsolete (c: provisional, on the C2 dry run)")
    if args.pre_budget and args.uncertainty_handoff:
        parser.error("--pre-budget generates its own scenario design; it takes no --uncertainty-handoff")

    if args.mean_path_scenarios:
        from pathlib import Path
        from .jobs import terminate_on_signals
        from .pipeline import mean_path_scenarios, write
        out = Path(args.out) if args.out else SCENARIO_DIR / "mean_paths.json"
        if out.resolve() in (OUTPUT.resolve(), DASHBOARD_COPY.resolve()):
            parser.error("--mean-path-scenarios must not overwrite the results file or dashboard copy")
        with terminate_on_signals():
            write(mean_path_scenarios(workers=args.workers, allow_dirty=args.allow_dirty,
                                      uncertainty_ruling=args.uncertainty_ruling,
                                      handoff_path=args.uncertainty_handoff), [out])
        return 0

    if args.scenario:
        return scenario(args.scenario, args.out, args.allow_dirty)

    from pathlib import Path
    from .jobs import terminate_on_signals
    from .pipeline import build, write

    if args.without_mean_paths:
        out = Path(args.out)
        if out.resolve() in (OUTPUT.resolve(), DASHBOARD_COPY.resolve()) or out.resolve().parent == SCENARIO_DIR.resolve():
            parser.error("--without-mean-paths must not write the results file, its dashboard copy or a scenario file")
    # SIGTERM or SIGHUP stops the running model processes before the build exits (jobs.run_jobs, run_child).
    with terminate_on_signals():
        results, scenarios = build(workers=args.workers, allow_dirty=args.allow_dirty,
                                   sensitivity_workers=args.sensitivity_workers,
                                   uncertainty_ruling=args.uncertainty_ruling,
                                   uncertainty_handoff=args.uncertainty_handoff, pre_budget=args.pre_budget,
                                   mean_paths=not args.without_mean_paths)
        if args.without_mean_paths:  # the full build writes the results file and the scenario files
            write(results, [out])
            return 0
        write(results, [OUTPUT, DASHBOARD_COPY])
        for name, run in scenarios.items():  # one rebuild refreshes every scenario run too
            write(run, [SCENARIO_DIR / f"{name}.json"])
    return 0


def scenario(name, out=None, allow_dirty=False):
    """One scenario run (pipeline.scenario), written to ``out``; never to the results file or its dashboard copy."""
    from pathlib import Path

    from .jobs import terminate_on_signals
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
