"""Check Pension Credit and pension-age HB projections using invented inputs only.

Each macro Scenario is applied before an invented household is loaded. No
survey dataset is opened. The last check year, 2040, also exercises an explicit
amount beyond the engine's fiscal-2039 horizon; the installed indices stop in
2039, so that extra year is not a claim about an additional engine run.
"""

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
YEARS = list(range(2027, 2041))
FAMILIES = {"single": "single", "couple": "couple", "lone_parent": "single"}


def specifications():
    from triple_lock import central, engine, trajectories

    central_spec = trajectories.central_spec(central.central_path())
    specs = {"central": central_spec}
    for name, earnings in (("high_earnings", 0.0805), ("zero_or_negative_earnings", 0.0)):
        spec = dict(central_spec)
        spec.update(cpi={year: 0.02 for year in engine.CALENDAR_YEARS},
                    earnings={year: earnings for year in engine.CALENDAR_YEARS},
                    statutory_cpi={year: 0.02 for year in engine.STATUTORY_YEARS},
                    statutory_earnings={year: (earnings if name == "high_earnings" else
                                               (-0.02 if year % 2 else 0.0))
                                        for year in engine.STATUTORY_YEARS})
        specs[name] = spec
    return specs


def build(spec, parameters):
    from policyengine_uk import Simulation
    from policyengine_uk.utils.scenario import Scenario
    from triple_lock import engine

    simulation = Simulation(
        situation={"people": {"invented": {"age": {year: 82 for year in YEARS}}},
                   "benunits": {"b": {"members": ["invented"]}},
                   "households": {"h": {"members": ["invented"]}}},
        scenario=Scenario(parameter_changes=engine.scenario_changes(spec, parameters),
                          applied_before_data_load=True))
    simulation.baseline = None
    return simulation


def guarantees(parameters, spec):
    """The engine's levels plus one explicit boundary-year stress check."""
    from triple_lock import engine

    result = engine.pension_credit_levels(parameters, spec["statutory_earnings"],
                                          spec.get("rate_decimals", engine.CENTRAL_RATE_DECIMALS))
    last = engine.HORIZON[-1]
    boundary_earnings = spec["statutory_earnings"].get(last, spec["statutory_earnings"][last - 1])
    growth = engine.guarantee_growth({last: boundary_earnings}, [last + 1],
                                     spec.get("rate_decimals", engine.CENTRAL_RATE_DECIMALS))[last + 1]
    for levels in result.values():
        levels[last + 1] = levels[last] * (1 + growth)
    return result


def read(parameters, own, levels):
    from triple_lock import engine

    result = {}
    for year in YEARS:
        at = f"{year}-06-01"
        result[year] = {}
        for family in ("single", "couple"):
            path = engine.PENSION_CREDIT_GUARANTEE[family]
            pc = parameters.gov.dwp.pension_credit
            result[year][family] = {
                "processed_guarantee_weekly": own[path][year],
                "engine_guarantee_weekly": levels[path][year],
                "applied_guarantee_weekly": float(parameters.get_child(path)(at)),
                "savings_credit_threshold_weekly": float(pc.savings_credit.threshold.children[family.upper()](at)),
                "savings_credit_maximum_weekly": float(pc.savings_credit.maximum.children[family.upper()](at)),
                "savings_credit_phase_in": float(pc.savings_credit.rate.phase_in(at)),
            }
        result[year]["housing_benefit_allowances_weekly"] = {
            family: {cohort: float(parameters.get_child(
                f"gov.dwp.housing_benefit.allowances.{family}.{cohort}")(at))
                     for cohort in ("aged", "aged_from_cutoff")}
            for family in FAMILIES}
    return result


def errors(rows):
    result = {"guarantee": 0.0, "savings_credit_identity": 0.0,
              "higher_hb_identity": 0.0, "lower_hb_identity": 0.0,
              "hb_below_guarantee": 0.0}
    for row in rows.values():
        for family in ("single", "couple"):
            values = row[family]
            guarantee = values["applied_guarantee_weekly"]
            result["guarantee"] = max(result["guarantee"], abs(guarantee - values["engine_guarantee_weekly"]))
            result["savings_credit_identity"] = max(result["savings_credit_identity"], abs(
                (guarantee - values["savings_credit_threshold_weekly"]) * values["savings_credit_phase_in"]
                - values["savings_credit_maximum_weekly"]))
        for kind, family in FAMILIES.items():
            values = row[family]
            guarantee = values["applied_guarantee_weekly"]
            hb = row["housing_benefit_allowances_weekly"][kind]
            result["higher_hb_identity"] = max(result["higher_hb_identity"], abs(
                hb["aged"] - guarantee - values["savings_credit_maximum_weekly"]))
            result["lower_hb_identity"] = max(result["lower_hb_identity"], abs(hb["aged_from_cutoff"] - guarantee))
            result["hb_below_guarantee"] = max(result["hb_below_guarantee"],
                                               *(guarantee - amount for amount in hb.values()))
    return result


def check():
    from policyengine_uk.utils.scenario import Scenario
    from triple_lock import engine, rules

    packages = {name: importlib.metadata.version(name) for name in ("policyengine-uk", "policyengine-core")}
    if packages != {"policyengine-uk": "2.153.4", "policyengine-core": "3.33.3"}:
        raise RuntimeError("this compatibility check requires policyengine-uk 2.153.4 and policyengine-core 3.33.3")
    parameters = engine.model_parameters()
    result = {"scope": "parameter checks with one invented household; no survey data",
              "engine_fiscal_years": engine.HORIZON,
              "boundary_year": "2040 is an explicit-amount stress check beyond the engine horizon",
              "packages": packages, "paths": {}}
    for name, spec in specifications().items():
        pristine = build(spec, parameters)
        pc = guarantees(parameters, spec)
        own = {path: {year: float(pristine.tax_benefit_system.parameters.get_child(path)(f"{year}-06-01"))
                      for year in YEARS} for path in pc}
        _, _, rates = engine.spec_rates(spec)
        result["paths"][name] = {}
        for policy in engine.POLICIES:
            sim = pristine.clone(clone_tax_benefit_system=True)
            flat = {kind: rules.level_path(base, rates[policy], engine.HORIZON)
                    for kind, base in engine.base_levels(parameters).items()}
            # The prior setter only applied these two amount reforms. Retain
            # that exact operation here to exhibit the ordering regression.
            Scenario.from_reform({**engine.flat_rate_reform(flat), **engine.amounts_reform(pc)}).simulation_modifier(sim)
            sim.tax_benefit_system.reset_parameter_caches()
            before = read(sim.tax_benefit_system.parameters, own, pc)
            engine.set_flat_rates(sim, flat, pc)
            after = read(sim.tax_benefit_system.parameters, own, pc)
            result["paths"][name][policy] = {
                "before_max_abs_error_gbp_weekly": errors(before),
                "after_max_abs_error_gbp_weekly": errors(after),
                "before_engine_horizon_max_abs_error_gbp_weekly": errors({year: before[year] for year in engine.HORIZON}),
                "after_engine_horizon_max_abs_error_gbp_weekly": errors({year: after[year] for year in engine.HORIZON}),
                "before_years": before, "years": after}
    result["passed"] = all(all(error <= 1e-9 for error in policy["after_max_abs_error_gbp_weekly"].values())
                           for path in result["paths"].values() for policy in path.values())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = check()
    value = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        output = args.output.resolve()
        if not output.is_relative_to(ROOT):
            parser.error("--output must stay in the assigned workspace")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(value)
    else:
        print(value, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
