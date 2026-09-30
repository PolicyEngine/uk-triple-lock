"""Full PolicyEngine UK runs of the two rules on a growth path, each in its own process, cached by input.

Every fiscal and household figure in the results comes from a job here; nothing
is scaled from another run.

How a path enters the model
---------------------------
A path's calendar-year CPI and earnings growth for 2027-2039 replace
``gov.economic_assumptions.yoy_growth.obr`` (RPI and CPIH move by the same
amount as CPI) in a Scenario applied before the data load. (The same changes
passed as a reform are a silent no-op: the derived series are built at load
time.) Each job first extends policyengine-uk's derived series to 2042
(model_horizon: without it benefit rates stop following the path after April
2029). Each run records, and fails unless, in every year 2027-28 to 2039-40:

* benefit rates uprated by ``gov.benefit_uprating_cpi`` (the Pension Credit
  guarantee among them) grow by the path's calendar CPI the year before;
* CPI-indexed thresholds (the NI lower earnings limit) grow by the path's
  calendar CPI the same year;
* employment income grows by the path's earnings the same year;
* the model's own triple lock is max(CPI, earnings, 2.5%) of the path's
  calendar measures the year before, and its new State Pension compounds it.

Also moving with the path: survey amounts policyengine-uk uprates by CPI
(reported benefits, consumption) and private pension income (the previous
year's RPI, capped at 5%). Not moving: dividend, property and savings income and
wealth, self-employment income, rents, council tax and mortgage interest;
``not_moving`` records their growth on every run. Calendar 2026 growth, which
sets April 2027's benefit uprating, is the model's own on every path.

The State Pension flat rates are set from each rule applied to the path's
statutory inputs (September CPI, May-July AWE; rates to 3 dp). The additional
State Pension is pinned to the unreformed model on the same path, so it is the
same in both runs. A Scenario simulation builds a second, default-path
simulation as its ``baseline``; every run drops it before calculating, so no
variable compares against it, and records that employer NI incidence is zero.

Jobs
----
``run_jobs`` runs each job in its own process, in a per-worker directory that
keeps the downloaded dataset between jobs (the managed loader reuses a file
whose sha256 matches). Each result is cached in ``JOB_CACHE`` under a key
hashing the job's kind and arguments, this module's sources and the installed
package versions, so an interrupted build resumes and a changed engine reruns.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import queue
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import rules
from .config import (
    BASE_YEAR,
    CALENDAR_YEARS,
    CENTRAL_RATE_DECIMALS,
    DISTRIBUTION_YEARS,
    FINAL_YEAR,
    FISCAL_COMPONENTS,
    FLAT_RATE_PARAMETERS,
    HORIZON,
    JOB_CACHE,
    MODEL_TRIPLE_LOCK_PARAMETER,
    OBR_GROWTH,
    PINNED_VARIABLES,
    POLICIES,
    REPO,
    SPENDING_DETAIL,
    STATUTORY_YEARS,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)

BN = 1e9
MOVE_WITH_CPI = ["rpi", "cpih"]
# Parameters whose growth each run checks against the path: (path, calendar series, lag in years).
PATH_PARAMETERS = {
    "benefit_uprating_cpi": ("gov.benefit_uprating_cpi", "cpi", 1),
    "pension_credit_guarantee_single": ("gov.dwp.pension_credit.guarantee_credit.minimum_guarantee.SINGLE", "cpi", 1),
    "ni_lower_earnings_limit": ("gov.hmrc.national_insurance.class_1.thresholds.lower_earnings_limit", "cpi", 0),
}
# Growth indices are stored to 5 dp; this bounds the resulting error in a year's growth.
PATH_GROWTH_TOL = 5e-5
MODEL_AMOUNT_REL_TOL = 2e-4  # the model's own weekly amounts compound 5 dp indices over up to 17 years
PROPORTIONALITY_TOL_GBP = 0.01  # £ a year, per person
# Survey amounts the path does not move, recorded to show it, and one it does move beyond those checked.
NOT_MOVING = ["self_employment_income", "dividend_income", "property_income", "savings_interest_income", "rent",
              "council_tax"]
ALSO_MOVING = ["private_pension_income"]
LARGEST_HOUSEHOLD_VARIABLES = ("housing_benefit", "pension_credit", "state_pension", "basic_state_pension",
                               "new_state_pension")
# Sources that define what a job computes; a change reruns every job.
ENGINE_FILES = ["engine.py", "model_horizon.py", "rules.py", "config.py", "breakdowns.py"]
TRACKED_PACKAGES = ["policyengine", "policyengine-uk", "policyengine-core", "microdf-python", "numpy"]
WORKDIRS = REPO / ".cache" / "workers"
REFORM = "burnham_2030"


class PathNotFollowed(RuntimeError):
    """A model series did not follow the path in some year: the result would not be a run of that path."""


class SourceChanged(RuntimeError):
    """Engine code changed between the start of the build and a job."""


# ── Parameters and reforms ───────────────────────────────────────────────


def base_levels(parameters):
    """2026-27 weekly flat-rate amounts every rule compounds from."""
    return {name: float(parameters.get_child(path)(f"{BASE_YEAR}-06-01")) for name, path in FLAT_RATE_PARAMETERS.items()}


def flat_rate_reform(levels_by_parameter):
    """Reform dict setting each flat-rate amount for each fiscal year.

    Parameters are held on calendar-year periods after policyengine-uk's
    fiscal-year conversion, so year ``y`` covers 2027-04 to 2028-03 when read as
    ``param(y)``. Each year needs its own value: setting only 2027 would leave
    2028 on the unreformed amount.
    """
    return {FLAT_RATE_PARAMETERS[name]: {f"{y}-01-01.{y}-12-31": float(level) for y, level in levels.items()}
            for name, levels in levels_by_parameter.items()}


def econ_changes(spec, parameters):
    """Scenario parameter changes putting a path's calendar growth into the model's economic assumptions."""
    obr = parameters.get_child(OBR_GROWTH)
    cpi_node = obr.get_child("consumer_price_index")
    changes = {
        f"{OBR_GROWTH}.consumer_price_index": {f"year:{y}-01-01:1": float(spec["cpi"][y]) for y in CALENDAR_YEARS},
        f"{OBR_GROWTH}.average_earnings": {f"year:{y}-01-01:1": float(spec["earnings"][y]) for y in CALENDAR_YEARS},
    }
    for series in MOVE_WITH_CPI:
        node = obr.get_child(series)
        changes[f"{OBR_GROWTH}.{series}"] = {
            f"year:{y}-01-01:1": float(node(f"{y}-01-01")) + float(spec["cpi"][y]) - float(cpi_node(f"{y}-01-01"))
            for y in CALENDAR_YEARS
        }
    return changes


def spec_rates(spec):
    """Each rule's rates and weekly flat-rate levels on a path, from its statutory inputs."""
    cpi = {int(y): float(v) for y, v in spec["statutory_cpi"].items()}
    earnings = {int(y): float(v) for y, v in spec["statutory_earnings"].items()}
    decimals = spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)
    rates = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals) for p in POLICIES}
    return cpi, earnings, rates


def rate_sources(cpi, earnings, rates, years=HORIZON, decimals=CENTRAL_RATE_DECIMALS):
    """{policy: {year: source}} naming what set each year's rise.

    Triple lock: "earnings", "cpi" or "floor" (2.5%). Burnham plan: "triple_lock"
    before the switch; after it "cpi" or "floor" when it pays the higher of CPI
    and 2.5%, or "earnings_path" when it tops up to its earnings path.
    """
    out = {p: {} for p in POLICIES}
    for y in years:
        c, e = cpi[y - 1], earnings[y - 1]
        top = max(c, e, TRIPLE_LOCK_FLOOR)
        out["triple_lock"][y] = "earnings" if top == e else "cpi" if top == c else "floor"
        if y < SWITCH_YEAR:
            out[REFORM][y] = "triple_lock"
            continue
        floor = max(c, TRIPLE_LOCK_FLOOR)
        floor = round(floor, decimals) if decimals is not None else floor
        if rates[REFORM][y] > floor + 1e-12:
            out[REFORM][y] = "earnings_path"
        else:
            out[REFORM][y] = "cpi" if c >= TRIPLE_LOCK_FLOOR else "floor"
    return out


# ── Simulation helpers ───────────────────────────────────────────────────


def _managed(dataset=None, **kwargs):
    from policyengine.tax_benefit_models.uk import managed_microsimulation

    sim = managed_microsimulation(**({"dataset": dataset} if dataset else {}), **kwargs)
    sim.baseline = None  # a Scenario's default-path comparator; nothing may compare against it
    return sim


def totals(sim, years):
    """Weighted totals (£bn) by year: the fiscal components, gov_balance, household net income, spending detail."""
    out = {}
    for y in years:
        t = {name: sum(float(sim.calculate(v, y, map_to="household").sum()) for v in vs) / BN
             for name, vs in FISCAL_COMPONENTS.items()}
        t["gov_balance"] = float(sim.calculate("gov_balance", y, map_to="household").sum()) / BN
        t["household_net_income"] = float(sim.calculate("household_net_income", y).sum()) / BN
        for v in SPENDING_DETAIL:
            t[v] = float(sim.calculate(v, y, map_to="household").sum()) / BN
        out[y] = t
    return out


POVERTY = {"relative_ahc": "in_relative_poverty_ahc", "absolute_ahc": "in_poverty_ahc"}


def poverty(sim, years):
    """Poverty rates (%) by year, after housing costs: people over State Pension age and everyone.

    policyengine-uk's relative measure is household income below 60% of the
    household-weighted median in the same run (HBAI weights people); the absolute
    measure uses its fixed real threshold. Each person counts with their
    household's status.
    """
    out = {}
    for y in years:
        w = sim.calculate("person_weight", y).to_numpy()
        pensioner = sim.calculate("is_SP_age", y).to_numpy().astype(bool)
        out[y] = {}
        for name, variable in POVERTY.items():
            poor = sim.calculate(variable, y, map_to="person").to_numpy().astype(bool)
            out[y][f"pensioners_{name}"] = float(100 * w[pensioner & poor].sum() / w[pensioner].sum())
            out[y][f"everyone_{name}"] = float(100 * w[poor].sum() / w.sum())
    return out


def set_flat_rates(sim, levels):
    from policyengine_uk.utils.scenario import Scenario

    Scenario.from_reform(flat_rate_reform(levels)).simulation_modifier(sim)
    sim.tax_benefit_system.reset_parameter_caches()


def pin(sim, pinned):
    for v, by_year in pinned.items():
        for y, values in by_year.items():
            sim.set_input(v, y, values)


def _unweighted_total(sim, variable, year):
    """Sum over the variable's own entity, unweighted: its growth is the uprating applied, whatever the weights do."""
    return float(np.asarray(sim.calculate(variable, year).values, dtype=float).sum())


def _growth(level, years):
    return {y: level[y] / level[y - 1] - 1 if level[y - 1] else None for y in years}


def household_groups(sim, year):
    """Group label arrays (one per household) for every breakdown."""
    from .breakdowns import TENURE_GROUPS, age_band, decile_groups, household_type, map_labels

    decile, quintile = decile_groups(sim.calculate("household_income_decile", year).to_numpy())
    head_age = sim.map_result(
        sim.calculate("age", year).to_numpy() * sim.calculate("is_household_head", year).to_numpy(), "person", "household"
    )
    heads = sim.calculate("is_household_head", year, map_to="household").to_numpy()
    if not (heads == 1).all():
        raise ValueError("every household must have exactly one head")
    return {
        "decile": decile,
        "quintile": quintile,
        "region": np.asarray(sim.calculate("region", year).to_numpy()).astype(str),
        "tenure": map_labels(sim.calculate("tenure_type", year).to_numpy(), TENURE_GROUPS, "tenure"),
        "hh_type": household_type(
            sim.calculate("is_adult", year, map_to="household").to_numpy(),
            sim.calculate("is_SP_age", year, map_to="household").to_numpy(),
            sim.calculate("is_child", year, map_to="household").to_numpy(),
        ),
        "age_band": age_band(head_age),
    }


def path_following(sim, calendar):
    """Growth of model series the path must drive, in every horizon year, against what the path says.

    ``calendar``: {"cpi"|"earnings": {calendar year: growth}} for 2026-2039 as the
    model received them. Raises PathNotFollowed if any series misses.
    """
    p = sim.tax_benefit_system.parameters
    years = [BASE_YEAR, *HORIZON]
    out, failures = {}, []

    def record(name, growth, expected, tol, **extra):
        err = max(abs(growth[y] - expected[y]) for y in HORIZON)
        out[name] = {**extra, "growth": growth, "expected": expected, "max_abs_error": err}
        if not err <= tol:
            failures.append(f"{name}: off by {err:.2e}")

    for name, (path, series, lag) in PATH_PARAMETERS.items():
        level = {y: float(p.get_child(path)(f"{y}-06-01")) for y in years}
        record(name, _growth(level, HORIZON), {y: calendar[series][y - lag] for y in HORIZON}, PATH_GROWTH_TOL,
               parameter=path, follows=f"calendar {'CPI' if series == 'cpi' else 'earnings'} growth "
                                       f"{'the year before' if lag else 'the same year'}")
    employment = {y: _unweighted_total(sim, "employment_income_before_lsr", y) for y in years}
    record("employment_income", _growth(employment, HORIZON), {y: calendar["earnings"][y] for y in HORIZON},
           PATH_GROWTH_TOL, variable="employment_income_before_lsr",
           follows="calendar earnings growth the same year (unweighted total)")
    model_tl = {y: float(p.get_child(MODEL_TRIPLE_LOCK_PARAMETER)(f"{y}-06-01")) for y in HORIZON}
    expected_tl = {y: round(max(calendar["earnings"][y - 1], calendar["cpi"][y - 1], TRIPLE_LOCK_FLOOR), 3)
                   for y in HORIZON}
    tl_err = max(abs(model_tl[y] - expected_tl[y]) for y in HORIZON)
    out["model_triple_lock"] = {"parameter": MODEL_TRIPLE_LOCK_PARAMETER, "rate": model_tl, "expected": expected_tl,
                                "max_abs_error": tl_err}
    if not tl_err <= 1e-12:
        failures.append(f"model_triple_lock: off by {tl_err:.2e}")
    nsp = {y: float(p.get_child(FLAT_RATE_PARAMETERS["new_state_pension"])(f"{y}-06-01")) for y in years}
    expected_nsp = rules.level_path(nsp[BASE_YEAR], model_tl, HORIZON)
    nsp_err = max(abs(nsp[y] / expected_nsp[y] - 1) for y in HORIZON)
    out["model_new_state_pension"] = {"weekly": nsp, "expected": expected_nsp, "max_rel_error": nsp_err}
    if not nsp_err <= MODEL_AMOUNT_REL_TOL:
        failures.append(f"model_new_state_pension: off by {nsp_err:.2e}")
    if failures:
        raise PathNotFollowed("; ".join(failures))
    return out


# ── Jobs ─────────────────────────────────────────────────────────────────


def run_path(spec):
    """Full model runs of one path, fiscal 2027-28 to 2039-40: unreformed, triple lock and Burnham plan.

    ``spec``: calendar ``cpi``/``earnings`` for 2027-2039, ``statutory_cpi``/
    ``statutory_earnings`` for 2026-2038, optional ``rate_decimals`` and
    ``dataset`` (None: the bundle's certified default).
    """
    from policyengine_uk.utils.scenario import Scenario

    from .breakdowns import all_breakdowns, households_affected

    dataset = spec.get("dataset")
    reference = _managed(dataset)
    parameters = reference.tax_benefit_system.parameters
    bundle = reference.policyengine_bundle
    base = base_levels(parameters)
    changes = econ_changes(spec, parameters)
    model_2026 = {s: float(parameters.get_child(f"{OBR_GROWTH}.{name}")(f"{BASE_YEAR}-01-01"))
                  for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))}
    del reference

    cpi, earnings, rates = spec_rates(spec)
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}

    def build():
        return _managed(dataset, scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))

    unreformed = build()
    p = unreformed.tax_benefit_system.parameters
    applied_growth = {
        s: {y: float(p.get_child(f"{OBR_GROWTH}.{name}")(f"{y}-01-01")) for y in [BASE_YEAR, *CALENDAR_YEARS]}
        for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))
    }
    calendar = {s: {BASE_YEAR: model_2026[s], **{y: float(spec[s][y]) for y in CALENDAR_YEARS}}
                for s in ("cpi", "earnings")}
    following = path_following(unreformed, calendar)
    other_series = {
        group: {v: _growth({y: _unweighted_total(unreformed, v, y) for y in [BASE_YEAR, *HORIZON]}, HORIZON)
                for v in variables}
        for group, variables in (("not_moving", NOT_MOVING), ("also_moving", ALSO_MOVING))
    }
    pinned = {v: {y: unreformed.calculate(v, y).to_numpy() for y in HORIZON} for v in PINNED_VARIABLES}
    del unreformed

    run_totals, income, groups, applied_weekly, hh, flat, employer_ni, pov = {}, {}, {}, {}, {}, {}, {}, {}
    household_ids = None
    for policy in POLICIES:
        sim = build()
        set_flat_rates(sim, levels[policy])
        pin(sim, pinned)
        run_totals[policy] = totals(sim, HORIZON)
        pov[policy] = poverty(sim, HORIZON)
        income[policy] = {y: sim.calculate("household_net_income", y) for y in HORIZON}
        hh[policy] = {v: sim.calculate(v, FINAL_YEAR, map_to="household").to_numpy()
                      for v in ("household_id", *LARGEST_HOUSEHOLD_VARIABLES)}
        flat[policy] = {y: {n: sim.calculate(n, y).to_numpy().astype(float) for n in FLAT_RATE_PARAMETERS}
                        for y in HORIZON}
        employer_ni[policy] = float(
            sim.calculate("employer_ni_fixed_employer_cost_change", FINAL_YEAR, map_to="household").sum()) / BN
        if policy == "triple_lock":
            groups = {y: household_groups(sim, y) for y in DISTRIBUTION_YEARS}
            household_ids = sim.calculate("household_id", FINAL_YEAR).to_numpy()
        applied_weekly[policy] = {y: float(sim.tax_benefit_system.parameters.get_child(
            FLAT_RATE_PARAMETERS["new_state_pension"])(f"{y}-06-01")) for y in HORIZON}
        del sim

    # Every flat-rate pension scales by the ratio of the two rules' amounts (no data-year denominator moves).
    proportionality = max(
        float(np.abs(flat[REFORM][y][n] - flat["triple_lock"][y][n] * levels[REFORM][n][y]
                     / levels["triple_lock"][n][y]).max())
        for y in HORIZON for n in FLAT_RATE_PARAMETERS
    )
    if not proportionality <= PROPORTIONALITY_TOL_GBP:
        raise PathNotFollowed(f"flat-rate pensions are not proportional to the flat rates: off by £{proportionality:.4f}")
    if any(abs(v) > 1e-12 for v in employer_ni.values()):
        raise PathNotFollowed(f"employer NI incidence is not zero: {employer_ni}")

    change = {y: income[REFORM][y] - income["triple_lock"][y] for y in HORIZON}
    # For every year, the single household record that moves that year's net figure most
    # (arithmetic on this run's own output, a decomposition, not an estimate).
    concentration = {}
    for y in HORIZON:
        w_y = income["triple_lock"][y].weights.to_numpy()
        contrib = change[y].to_numpy() * w_y / BN
        k = int(np.argmax(np.abs(contrib)))
        total = float(contrib.sum())
        concentration[y] = {"household_id": int(household_ids[k]), "weight": float(w_y[k]),
                            "contribution_bn": float(contrib[k]),
                            "share_of_income_change": float(contrib[k] / total) if total else 0.0}
    weight = income["triple_lock"][FINAL_YEAR].weights.to_numpy()
    contribution = change[FINAL_YEAR].to_numpy() * weight / BN
    i = int(np.argmax(np.abs(contribution)))
    net_final = float(contribution.sum())
    flat_hh = {pol: hh[pol]["basic_state_pension"] + hh[pol]["new_state_pension"] for pol in POLICIES}
    largest = {
        "household_id": int(hh["triple_lock"]["household_id"][i]),
        "weight": float(weight[i]),
        "income_change_gbp": float(change[FINAL_YEAR].to_numpy()[i]),
        "contribution_bn": float(contribution[i]),
        "share_of_income_change": float(contribution[i] / net_final) if net_final else 0.0,
        "income_change_excluding_bn": float(net_final - contribution[i]),
        "gross_contribution_bn": float((flat_hh["triple_lock"][i] - flat_hh[REFORM][i]) * weight[i] / BN),
        "change_gbp": {v: float(hh[REFORM][v][i] - hh["triple_lock"][v][i])
                       for v in ("housing_benefit", "pension_credit", "state_pension")},
        "amounts_gbp": {pol: {v: float(hh[pol][v][i]) for v in ("housing_benefit", "pension_credit", "state_pension")}
                        for pol in POLICIES},
        "median_weight": float(np.median(weight)),
    }
    tl, bp = run_totals["triple_lock"], run_totals[REFORM]
    return {
        "dataset": dataset or bundle["runtime_dataset"],
        "rate_decimals": spec.get("rate_decimals", CENTRAL_RATE_DECIMALS),
        "statutory": {"cpi": cpi, "earnings": earnings},
        "calendar": {s: {y: float(spec[s][y]) for y in CALENDAR_YEARS} for s in ("cpi", "earnings")},
        "applied_growth": applied_growth,
        "path_following": following,
        **other_series,
        "rates": rates,
        "rate_sources": rate_sources(cpi, earnings, rates),
        "weekly": levels,
        "applied_new_state_pension": applied_weekly,
        "saving_bn": {
            y: {
                "gross": tl[y]["state_pension_flat_rate"] - bp[y]["state_pension_flat_rate"],
                "net": bp[y]["gov_balance"] - tl[y]["gov_balance"],
                "household_income_change": bp[y]["household_net_income"] - tl[y]["household_net_income"],
                "components": {k: bp[y][k] - tl[y][k] for k in FISCAL_COMPONENTS},
            }
            for y in HORIZON
        },
        "totals_bn": run_totals,
        "poverty_pct": pov,
        "households_affected": {y: households_affected(change[y]) for y in HORIZON},
        "distribution": {y: all_breakdowns(change[y], income["triple_lock"][y], groups[y]) for y in DISTRIBUTION_YEARS},
        "largest_household": largest,
        "concentration_by_year": concentration,
        "checks": {"max_proportionality_error_gbp": proportionality, "employer_ni_incidence_bn": employer_ni},
        "bundle": {k: bundle[k] for k in ("bundle_id", "policyengine_version", "model_version", "runtime_dataset",
                                           "runtime_dataset_uri", "certified_data_build_id")},
    }


def actual_law_denominators(amounts, data_year):
    """Reform: policyengine-uk 2.90.2's basic and new State Pension formulas with the data-year flat rates fixed.

    Each person's pension is ``share x flat rate(period)``, where share is their
    reported survey-year pension as a share of the survey-year flat rate. The
    upstream formulas read that denominator from the (reformed) parameter tree,
    so changing the survey year's flat rate, as the past-years counterfactuals
    must, would also change everyone's share. Here the denominator is the
    actual-law amount (``amounts``), so every pension scales by the flat rate.
    """
    from policyengine_core.reforms import Reform
    from policyengine_uk.model_api import GBP, WEEKS_IN_YEAR, YEAR, Person, Variable, min_, where

    nsp_data_year, bsp_data_year = amounts["new_state_pension"], amounts["basic_state_pension"]

    class new_state_pension(Variable):
        label = "new State Pension"
        entity = Person
        definition_period = YEAR
        value_type = float
        unit = GBP

        def formula(person, period, parameters):
            pension_type = person("state_pension_type", period)
            eligible = pension_type == pension_type.possible_values.NEW
            reported_weekly = person("state_pension_reported", data_year) / WEEKS_IN_YEAR
            max_new_period = parameters.gov.dwp.state_pension.new_state_pension.amount(period)
            share = where(nsp_data_year > 0, min_(reported_weekly, nsp_data_year) / nsp_data_year, 0)
            return eligible * share * max_new_period * WEEKS_IN_YEAR

    class basic_state_pension(Variable):
        label = "basic State Pension"
        entity = Person
        definition_period = YEAR
        value_type = float
        unit = GBP

        def formula(person, period, parameters):
            reported = person("state_pension_reported", data_year) / WEEKS_IN_YEAR
            pension_type = person("state_pension_type", period)
            max_sp_period = parameters.gov.dwp.state_pension.basic_state_pension.amount(period)
            share = where(bsp_data_year > 0, min_(reported, bsp_data_year) / bsp_data_year, 0)
            return where(pension_type == pension_type.possible_values.BASIC, share * max_sp_period, 0) * WEEKS_IN_YEAR

    class reform(Reform):
        def apply(self):
            self.update_variable(new_state_pension)
            self.update_variable(basic_state_pension)

    return reform


def run_history(arg):
    """Full model runs for the survey years: actual law vs flat rates had the plan started earlier.

    ``arg``: ``level_ratio`` {year: Burnham index / triple-lock replay index} for
    ``years`` (the survey years), and optional ``dataset``.
    """
    dataset = arg.get("dataset")
    years = [int(y) for y in arg["years"]]
    ratio = {int(y): float(v) for y, v in arg["level_ratio"].items()}
    base = _managed(dataset)
    p = base.tax_benefit_system.parameters
    data_year = int(min(base.dataset.years))
    actual = {n: {y: float(p.get_child(path)(f"{y}-06-01")) for y in years} for n, path in FLAT_RATE_PARAMETERS.items()}
    denominators = {n: float(p.get_child(path)(f"{data_year}-06-01")) for n, path in FLAT_RATE_PARAMETERS.items()}
    levels = {n: {y: actual[n][y] * ratio[y] for y in years} for n in FLAT_RATE_PARAMETERS}
    pinned = {v: {y: base.calculate(v, y).to_numpy() for y in years} for v in PINNED_VARIABLES}
    base_totals = totals(base, years)
    base_flat = {y: {n: base.calculate(n, y).to_numpy().astype(float) for n in FLAT_RATE_PARAMETERS} for y in years}
    last = years[-1]
    base_income = base.calculate("household_net_income", last).to_numpy()
    weight = base.calculate("household_weight", last).to_numpy()
    del base
    sim = _managed(dataset)
    if int(min(sim.dataset.years)) != data_year:
        raise RuntimeError("the counterfactual simulation has a different survey year")
    sim.apply_reform(actual_law_denominators(denominators, data_year))
    set_flat_rates(sim, levels)
    pin(sim, pinned)
    applied = {y: float(sim.tax_benefit_system.parameters.get_child(FLAT_RATE_PARAMETERS["new_state_pension"])(
        f"{y}-06-01")) for y in years}
    cf_totals = totals(sim, years)
    proportionality = max(
        float(np.abs(sim.calculate(n, y).to_numpy().astype(float) - base_flat[y][n] * ratio[y]).max())
        for y in years for n in FLAT_RATE_PARAMETERS
    )
    if not proportionality <= PROPORTIONALITY_TOL_GBP:
        raise PathNotFollowed(f"counterfactual pensions are not actual x level ratio: off by £{proportionality:.4f}")
    change = sim.calculate("household_net_income", last).to_numpy() - base_income
    return {
        "actual_weekly": actual,
        "counterfactual_weekly": levels,
        "applied_new_state_pension": applied,
        "data_year": data_year,
        "data_year_denominator_weekly": denominators,
        "max_proportionality_error_gbp": proportionality,
        "saving_bn": {
            y: {
                "gross": base_totals[y]["state_pension_flat_rate"] - cf_totals[y]["state_pension_flat_rate"],
                "net": cf_totals[y]["gov_balance"] - base_totals[y]["gov_balance"],
                "components": {k: cf_totals[y][k] - base_totals[y][k] for k in FISCAL_COMPONENTS},
            }
            for y in years
        },
        "households_losing_pct": float(100 * (weight * (change < -1)).sum() / weight.sum()),
    }


def run_coverage(arg):
    """What a dataset holds in one year on the unreformed model: spending and caseloads to set against DWP."""
    dataset, year = arg.get("dataset"), int(arg["year"])
    sim = _managed(dataset)

    def total(variable, entity_mask=None):
        values = sim.calculate(variable, year)
        v, w = values.to_numpy().astype(float), values.weights.to_numpy()
        m = np.ones(len(v), dtype=bool) if entity_mask is None else entity_mask
        return float((v * w)[m].sum()) / BN

    def count(variable):
        values = sim.calculate(variable, year)
        return float(values.weights.to_numpy()[values.to_numpy() > 0].sum())

    person_sp_age = sim.calculate("is_SP_age", year).to_numpy().astype(bool)
    benunit_pensioner = sim.map_result(person_sp_age.astype(float), "person", "benunit") > 0
    age = sim.calculate("age", year).to_numpy()
    person_weight = sim.calculate("person_weight", year).to_numpy()
    pension_type = sim.calculate("state_pension_type", year).to_numpy().astype(str)
    return {
        "dataset": dataset or sim.policyengine_bundle["runtime_dataset"],
        "year": year,
        "state_pension_bn": total("state_pension"),
        "basic_state_pension_bn": total("basic_state_pension"),
        "new_state_pension_bn": total("new_state_pension"),
        "additional_state_pension_bn": total("additional_state_pension"),
        "state_pension_recipients": count("state_pension"),
        "state_pension_age_people": float(person_weight[person_sp_age].sum()),
        "pension_type_people": {t: float(person_weight[pension_type == t].sum()) for t in np.unique(pension_type)},
        "pension_credit_bn": total("pension_credit"),
        "pension_credit_benefit_units": count("pension_credit"),
        "housing_benefit_bn": total("housing_benefit"),
        "housing_benefit_pensioner_benefit_units_bn": total("housing_benefit", benunit_pensioner),
        "universal_credit_bn": total("universal_credit"),
        "max_age": float(age.max()),
        "people": float(person_weight.sum()),
        "max_household_weight": float(sim.calculate("household_weight", year).to_numpy().max()),
        "records": {"households": int(len(sim.calculate("household_weight", year))),
                    "people": int(len(person_weight))},
    }


JOBS = {"path": run_path, "history": run_history, "coverage": run_coverage}


# ── Caching and isolation ────────────────────────────────────────────────


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def engine_hashes():
    here = Path(__file__).resolve().parent
    hashes = {name: file_hash(here / name) for name in ENGINE_FILES}
    hashes["pyproject.toml"] = file_hash(REPO / "pyproject.toml")
    return hashes


def package_versions():
    return {name: importlib.metadata.version(name) for name in TRACKED_PACKAGES}


def _canonical(obj):
    """Stable JSON: keys as strings (as a job receives them), sorted."""
    return json.dumps(json.loads(json.dumps(obj, default=float)), sort_keys=True, separators=(",", ":"))


def job_key(kind, arg, engine=None, packages=None):
    """Hash of what determines a job's result: kind, arguments, engine sources, package versions."""
    payload = {"kind": kind, "arg": arg, "engine": engine or engine_hashes(), "packages": packages or package_versions()}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _keys_to_int(d):
    if isinstance(d, dict):
        return {int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k: _keys_to_int(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_keys_to_int(v) for v in d]
    return d


def cache_path(kind, key, cache=JOB_CACHE):
    return Path(cache) / f"{kind}-{key[:24]}.json"


def cached(kind, arg, engine=None, packages=None, cache=JOB_CACHE):
    """The cached result for a job, or None."""
    key = job_key(kind, arg, engine, packages)
    path = cache_path(kind, key, cache)
    if not path.is_file():
        return None
    record = json.loads(path.read_text())
    if record["key"] != key:
        raise RuntimeError(f"{path} holds a different job")
    return _keys_to_int(record["result"])


def _run_isolated(kind, arg, workdir, engine):
    """Run one job in its own process and working directory (the dataset lands in ./data and stays)."""
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(_canonical([kind, arg]).encode()).hexdigest()[:12]
    inp, out = workdir / f"input-{tag}.json", workdir / f"output-{tag}.json"
    inp.write_text(json.dumps({"kind": kind, "arg": arg, "engine": engine}, default=float))
    result = subprocess.run(
        [sys.executable, "-m", "triple_lock.engine", "--job", str(inp), str(out)],
        cwd=workdir, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    if result.returncode != 0:
        raise RuntimeError(f"{kind} job failed in {workdir}:\n{result.stderr[-4000:]}")
    text = out.read_text()
    inp.unlink()
    out.unlink()
    return json.loads(text)


def run_jobs(jobs, workers=3, slot_prefix="slot", log=print, cache=JOB_CACHE):
    """Run [(kind, arg), ...], reusing cached results; returns the results in order.

    Each worker owns a directory under WORKDIRS, so its downloaded dataset
    persists between jobs and no two processes share a data file.
    """
    engine, packages = engine_hashes(), package_versions()
    results = [cached(kind, arg, engine, packages, cache) for kind, arg in jobs]
    todo = [i for i, r in enumerate(results) if r is None]
    log(f"{len(jobs) - len(todo)} of {len(jobs)} jobs cached; running {len(todo)} on {workers} workers")
    if not todo:
        return results
    Path(cache).mkdir(parents=True, exist_ok=True)
    slots = queue.Queue()
    for s in range(workers):
        slots.put(s)
    done = [0]

    def work(i):
        kind, arg = jobs[i]
        s = slots.get()
        try:
            started = datetime.now(timezone.utc)
            result = _run_isolated(kind, arg, WORKDIRS / f"{slot_prefix}{s}", engine)
        finally:
            slots.put(s)
        if engine_hashes() != engine:
            raise SourceChanged("engine sources changed during the build")
        key = job_key(kind, arg, engine, packages)
        record = {"key": key, "kind": kind, "arg": arg, "engine": engine, "packages": packages,
                  "started_at": started.isoformat(timespec="seconds"),
                  "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "result": result}
        path = cache_path(kind, key, cache)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, default=float, allow_nan=False))
        tmp.replace(path)
        done[0] += 1
        log(f"  {kind} job done ({done[0]}/{len(todo)}) in "
            f"{(datetime.now(timezone.utc) - started).total_seconds():.0f}s")
        return _keys_to_int(result)

    with ThreadPoolExecutor(workers) as pool:
        futures = {i: pool.submit(work, i) for i in todo}
        for i, f in futures.items():
            results[i] = f.result()
    return results


def _job(inp, out):
    from . import model_horizon

    payload = json.loads(Path(inp).read_text())
    if engine_hashes() != payload["engine"]:
        raise SourceChanged("engine sources changed between the start of the build and this job")
    # Before any simulation: every series the path drives must reach the final year.
    model_horizon.install()
    arg = _keys_to_int(payload["arg"])
    result = JOBS[payload["kind"]](arg)
    Path(out).write_text(json.dumps(result, default=float, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description="One full-model job (internal)")
    parser.add_argument("--job", nargs=2, metavar=("INPUT", "OUTPUT"), required=True)
    args = parser.parse_args(argv)
    _job(*args.job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
