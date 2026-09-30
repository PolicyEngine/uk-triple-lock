"""Example pensioners on one path: how much of the State Pension they lose comes back through tax and benefits.

Each example is a hypothetical household run through PolicyEngine UK (a
situation, no survey data) under both rules, 2027-28 to 2039-40, on a path:
its CPI and earnings growth enter the model's economic assumptions before the
parameters are built, exactly as in the full runs (engine.scenario_changes, with
the horizon extension), and the flat rates and the earnings-linked Pension
Credit guarantee are set as in the full runs (engine.set_flat_rates). Every pensioner receives the full flat rate (their
reported State Pension is above it) and no additional State Pension.

The examples' own amounts are stated in 2026-27 terms and grow with the path's
calendar CPI: private pension income (as a CPI-linked pension would), rent and
council tax. Each pensioner is the stated age in every year, so the examples
describe a pensioner of that age in each year, not one person ageing. Every
example claims all it is entitled to; the renters are existing Housing Benefit
claimants, which policyengine-uk requires before it pays Housing Benefit.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .config import (BASE_YEAR, CALENDAR_YEARS, CENTRAL_RATE_DECIMALS, FLAT_RATE_PARAMETERS, HORIZON, JOB_CACHE, POLICIES,
                     REPO)

WEEKS = 52
EXAMPLES = {
    "owner": {
        "label": "Single pensioner aged 70, State Pension only, owns their home",
        "age": 70, "private_pension": 0, "rent_weekly": 0, "tenure": "OWNED_OUTRIGHT", "council_tax": 2_000,
    },
    "private_pension": {
        "label": "Single pensioner aged 70 with a £15,000 private pension, owns their home",
        "age": 70, "private_pension": 15_000, "rent_weekly": 0, "tenure": "OWNED_OUTRIGHT", "council_tax": 2_000,
    },
    "social_renter": {
        "label": "Single pensioner aged 70, State Pension only, rents from the council at £120 a week",
        "age": 70, "private_pension": 0, "rent_weekly": 120, "tenure": "RENT_FROM_COUNCIL", "council_tax": 1_800,
    },
    "basic_renter": {
        "label": "Single pensioner aged 90 on the old basic State Pension, rents from the council at £120 a week",
        "age": 90, "private_pension": 0, "rent_weekly": 120, "tenure": "RENT_FROM_COUNCIL", "council_tax": 1_800,
    },
}
OUTPUTS = {
    "state_pension": ["basic_state_pension", "new_state_pension"],
    "income_tax": ["income_tax"],
    "pension_credit": ["pension_credit"],
    "housing_benefit": ["housing_benefit"],
    "council_tax_reduction": ["council_tax_benefit"],
    "winter_fuel_payment": ["winter_fuel_allowance"],
    "net_income": ["household_net_income"],
}
HOUSEHOLD_LEVEL = {"household_net_income"}


def cpi_index(calendar_cpi):
    """Price level relative to 2026 for each year, from calendar CPI growth."""
    out, level = {BASE_YEAR: 1.0}, 1.0
    for y in CALENDAR_YEARS:
        level *= 1 + calendar_cpi[y]
        out[y] = level
    return out


def situation(example, index):
    e = EXAMPLES[example]
    years = HORIZON

    def each(value):
        return {y: value for y in years}

    def grown(value):
        return {y: value * index[y] for y in years}

    return {
        "people": {"pensioner": {
            "age": each(e["age"]),
            "state_pension_reported": each(1_000_000),  # above any flat rate: the full rate
            "additional_state_pension": each(0.0),
            "private_pension_income": grown(e["private_pension"]),
            "housing_benefit_reported": each(1.0 if e["rent_weekly"] else 0.0),
        }},
        "benunits": {"benunit": {
            "members": ["pensioner"],
            # Claims everything it is entitled to. policyengine-uk pays Housing Benefit only to a benefit unit
            # already claiming it (new working-age claims go to Universal Credit); a renter here is one.
            "claims_all_entitled_benefits": each(True),
            # Over State Pension age: no Universal Credit (policyengine-uk would otherwise let the take-up
            # switch above stop its Housing Benefit).
            "would_claim_uc": each(False),
        }},
        "households": {"household": {
            "members": ["pensioner"],
            "rent": grown(e["rent_weekly"] * WEEKS),
            "council_tax": grown(e["council_tax"]),
            "tenure_type": each(e["tenure"]),
        }},
    }


def run_examples(spec):
    """{example: {policy: {output: {year: £ a year}}}} on one path."""
    from policyengine_uk import CountryTaxBenefitSystem, Simulation
    from policyengine_uk.utils.scenario import Scenario

    from . import engine, rules

    parameters = CountryTaxBenefitSystem().parameters
    changes = engine.scenario_changes(spec, parameters)
    base = engine.base_levels(parameters)
    _, earnings, rates = engine.spec_rates(spec)
    pc_levels = engine.pension_credit_levels(parameters, earnings, spec.get("rate_decimals", CENTRAL_RATE_DECIMALS))
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}
    index = cpi_index({int(y): float(v) for y, v in spec["cpi"].items()})
    out = {}
    for example in EXAMPLES:
        out[example] = {}
        for policy in POLICIES:
            sim = Simulation(situation=situation(example, index),
                             scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))
            sim.baseline = None
            engine.set_flat_rates(sim, levels[policy], pc_levels)
            applied = {y: float(sim.tax_benefit_system.parameters.get_child(
                FLAT_RATE_PARAMETERS["new_state_pension"])(f"{y}-06-01")) for y in HORIZON}
            if any(abs(applied[y] / levels[policy]["new_state_pension"][y] - 1) > 1e-9 for y in HORIZON):
                raise RuntimeError("the flat rates did not reach the example household's model")
            out[example][policy] = {
                name: {y: float(sum(sim.calculate(v, y).sum() for v in vs)) for y in HORIZON}
                for name, vs in OUTPUTS.items()
            }
    return {"examples": {k: {"label": v["label"], **{f: v[f] for f in ("age", "private_pension", "rent_weekly",
                                                                     "council_tax", "tenure")}}
                         for k, v in EXAMPLES.items()},
            "results": out}


# ── Isolation and caching (each path in its own process: the horizon extension patches the model) ──


def _hash(obj):
    return hashlib.sha256(json.dumps(json.loads(json.dumps(obj, default=float)), sort_keys=True).encode()).hexdigest()


def key(spec):
    """What the examples' cache key holds: the spec, what the engine and this module compute (their syntax trees,
    engine.source_semantics) and the package versions."""
    from . import engine

    here = Path(__file__).resolve()
    return _hash({"kind": "households", "arg": spec, "engine": engine.engine_semantics(),
                  "households": engine.source_semantics(here), "packages": engine.package_versions()})


def run(spec, cache=JOB_CACHE, log=print):
    """Cached, isolated run of ``run_examples`` on one path spec (rate_decimals, cpi, earnings, statutory_*).

    The examples run in their own process and session (jobs.run_child), one at a time in their directory across
    processes (jobs.slot_lock).
    """
    from . import engine, jobs

    k = key(spec)
    path = Path(cache) / f"households-{k[:24]}.json"
    if path.is_file():
        return engine._keys_to_int(json.loads(path.read_text())["result"])
    work = REPO / ".cache" / "workers" / "households"
    with jobs.slot_lock(work, log):
        inp, out = work / f"in-{k[:12]}.json", work / f"out-{k[:12]}.json"
        inp.write_text(json.dumps({"spec": spec, "key": k}, default=float))
        try:
            code, _, stderr = jobs.run_child([sys.executable, "-m", "triple_lock.households", "--job", str(inp),
                                                str(out)], cwd=work, env={"PYTHONPATH": str(REPO / "src")})
            if code != 0:
                raise RuntimeError(f"household examples failed (exit {code}):\n{stderr[-4000:]}")
            res = json.loads(out.read_text())
        finally:
            inp.unlink(missing_ok=True)
            out.unlink(missing_ok=True)
    if key(spec) != k:
        raise engine.SourceChanged("engine or household sources changed during the household examples")
    Path(cache).mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"key": k, "spec": spec, "result": res}, default=float, allow_nan=False))
    tmp.replace(path)
    return engine._keys_to_int(res)


def main(argv=None):
    from . import engine, jobs, model_horizon

    parser = argparse.ArgumentParser(description="Example households on one path (internal)")
    parser.add_argument("--job", nargs=2, required=True)
    args = parser.parse_args(argv)
    jobs.watch_parent()
    payload = json.loads(Path(args.job[0]).read_text())
    spec = engine._keys_to_int(payload["spec"])
    if key(payload["spec"]) != payload["key"]:
        raise engine.SourceChanged("engine or household sources changed between the start of the build and this job")
    model_horizon.install()
    Path(args.job[1]).write_text(json.dumps(run_examples(spec), default=float, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
