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

* benefit rates uprated by ``gov.benefit_uprating_cpi`` grow by the path's
  calendar CPI the year before (the Pension Credit guarantee is not among them:
  every run sets it from May-July earnings, below);
* CPI-indexed thresholds (the NI lower earnings limit) grow by the path's
  calendar CPI the same year;
* employment income grows by the path's earnings the same year;
* the model's own triple lock is max(CPI, earnings, 2.5%) of the path's
  calendar measures the year before, and its new State Pension compounds it;
* the Pension Credit standard minimum guarantee grows by the path's May-July
  earnings the year before, never cut.

Also moving with the path: survey amounts policyengine-uk uprates by CPI
(reported benefits, consumption) and private pension income (the previous
year's RPI, capped at 5%). Not moving: dividend, property and savings income and
wealth, self-employment income, rents, council tax and mortgage interest;
``not_moving`` records their growth on every run. Calendar 2026 growth, which
sets April 2027's benefit uprating, is the model's own on every path.

The State Pension flat rates are set from each rule applied to the path's
statutory inputs (September CPI, May-July AWE, to 0.1 point as published, by
rules.round_rate). Three more inputs are fixed the same way under both rules:

* each person's State Pension type (basic or new) is held at its survey-year
  value; survey ages are not advanced, and policyengine-uk would otherwise move
  a cohort from the basic to the new State Pension each year while still paying
  its additional pension on the basic basis, counting part of it twice. Every
  run reads the types back from the model in every year, fails if any differs
  from the held one, and records the counts;
* the additional State Pension is the survey-year amount grown by September CPI
  (published to April 2026, the path's after), as in law, for people over State
  Pension age that year;
* the State Pension age is 67 from 2028-29 (config.STATE_PENSION_AGE_CHANGES),
  and the Pension Credit standard minimum guarantee rises with the path's
  May-July earnings growth (config.PENSION_CREDIT_GUARANTEE; SSAA 1992 s150A).

A Scenario simulation builds a second, default-path simulation as its
``baseline``; every run drops it before calculating, so no variable compares
against it, and records that employer NI incidence is zero.

Jobs
----
``run_jobs`` runs each job in its own process and session, in a per-worker
directory that keeps the downloaded dataset between jobs (the managed loader
reuses a file whose sha256 matches). Each result is cached in ``JOB_CACHE``
under a key hashing the job's kind and arguments, what the engine's code
computes (``engine_semantics``: each file's syntax tree without comments or
docstrings) and the installed package versions, so an interrupted build
resumes, a changed engine reruns and an edit to its prose alone reruns nothing.
The results file's provenance keeps the files' raw hashes (``engine_hashes``),
so it still goes stale on any edit.

A worker waiting for a directory another process holds logs who holds it and
gives up after ``LOCK_TIMEOUT_S``. When a job fails, the queued jobs are
cancelled, the running ones finish (and are cached), and every failure is
reported. Ctrl-C, SIGTERM or SIGHUP stops every running job's process group at
once; a job whose build dies without that (SIGKILL) notices it has lost its
parent and stops itself (``watch_parent``).
"""

import argparse
import ast
import contextlib
import hashlib
import importlib.metadata
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import tomllib
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
    PENSION_CREDIT_GUARANTEE,
    POLICIES,
    REPO,
    SPENDING_DETAIL,
    STATE_PENSION_AGE_CHANGES,
    STATUTORY_YEARS,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)

BN = 1e9
MOVE_WITH_CPI = ["rpi", "cpih"]
# Parameters whose growth each run checks against the path: (path, calendar series, lag in years).
PATH_PARAMETERS = {
    "benefit_uprating_cpi": ("gov.benefit_uprating_cpi", "cpi", 1),
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
# Sources that define what a job computes (every module a job imports from this package); a change to what one
# computes reruns every job.
ENGINE_FILES = ["engine.py", "model_horizon.py", "rules.py", "config.py", "breakdowns.py"]
TRACKED_PACKAGES = ["policyengine", "policyengine-uk", "policyengine-core", "microdf-python", "numpy", "pandas"]
WORKDIRS = REPO / ".cache" / "workers"
REFORM = "burnham_2030"
PENSION_TYPES = ("BASIC", "NEW", "NONE")
# A worker directory another process holds this long fails the job (the holder is named in the log meanwhile).
LOCK_TIMEOUT_S = 3600
LOCK_POLL_S = 2.0
LOCK_LOG_EVERY_S = 300
# Seconds a stopped job gets between SIGTERM and SIGKILL; how often a job checks that its build is still alive.
KILL_GRACE_S = 10
PARENT_POLL_S = 2.0
PARENT_ENV = "TRIPLE_LOCK_PARENT_PID"


class PathNotFollowed(RuntimeError):
    """A model series did not follow the path in some year: the result would not be a run of that path."""


class SourceChanged(RuntimeError):
    """Engine code changed between the start of the build and a job."""


class LockTimeout(RuntimeError):
    """Another process held a worker directory for longer than the timeout."""


class Aborted(RuntimeError):
    """The build was stopping (a failed job or a signal), so this job did not start."""


class Terminated(SystemExit):
    """SIGTERM or SIGHUP, raised in the main thread so the running jobs are stopped before the build exits."""


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


def scenario_changes(spec, parameters):
    """Everything set before the data load: the path's growth and the State Pension age."""
    return {**econ_changes(spec, parameters), **STATE_PENSION_AGE_CHANGES}


def september_cpi(spec):
    """{determination year: September CPI} for the additional pension's uprating: published, then the path's.

    The path's figures are the statutory CPI the rules see (rules.round_rate at the spec's precision).
    """
    decimals = spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)
    out = {int(y): float(v) for y, v in spec["september_cpi_history"].items()}
    out.update({int(y): float(rules.round_rate(float(v), decimals)) for y, v in spec["statutory_cpi"].items()})
    return out


def guarantee_growth(statutory_earnings, years=HORIZON, decimals=CENTRAL_RATE_DECIMALS):
    """{year: the Pension Credit guarantee's rise}: May-July earnings the year before as the rules see it, never cut."""
    return {y: max(float(rules.round_rate(float(statutory_earnings[y - 1]), decimals)), 0.0) for y in years}


def pension_credit_levels(parameters, statutory_earnings, decimals=CENTRAL_RATE_DECIMALS):
    """{parameter path: {year: weekly}}: the 2026-27 guarantees grown by May-July earnings, never cut."""
    growth = guarantee_growth(statutory_earnings, HORIZON, decimals)
    out = {}
    for path in PENSION_CREDIT_GUARANTEE.values():
        level = float(parameters.get_child(path)(f"{BASE_YEAR}-06-01"))
        out[path] = {}
        for y in HORIZON:
            level *= 1 + growth[y]
            out[path][y] = level
    return out


def amounts_reform(levels_by_path):
    """Reform dict setting parameters (by path) to a value for each fiscal year."""
    return {path: {f"{y}-01-01.{y}-12-31": float(v) for y, v in by_year.items()} for path, by_year in levels_by_path.items()}


def spec_rates(spec):
    """Each rule's rates and weekly flat-rate levels on a path, from its statutory inputs."""
    cpi = {int(y): float(v) for y, v in spec["statutory_cpi"].items()}
    earnings = {int(y): float(v) for y, v in spec["statutory_earnings"].items()}
    decimals = spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)
    rates = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals) for p in POLICIES}
    return cpi, earnings, rates


def rate_sources(cpi, earnings, rates, years=HORIZON, decimals=CENTRAL_RATE_DECIMALS):
    """{policy: {year: source}} naming what set each year's rise, from the inputs as the rules saw them.

    Triple lock: rules.triple_lock_source, as the history table labels it ("floor"
    whenever neither input exceeds 2.5%, CPI when the inputs tie). Burnham plan:
    "triple_lock" before the switch; after it "earnings_path" when it tops up to
    its earnings path, otherwise "cpi" above 2.5% and "floor" at or below it.
    """
    out = {p: {} for p in POLICIES}
    for y in years:
        c, e = float(rules.round_rate(cpi[y - 1], decimals)), float(rules.round_rate(earnings[y - 1], decimals))
        out["triple_lock"][y] = rules.triple_lock_source(c, e)
        if y < SWITCH_YEAR:
            out[REFORM][y] = "triple_lock"
            continue
        floor = float(rules.round_rate(max(c, TRIPLE_LOCK_FLOOR), decimals))
        out[REFORM][y] = "earnings_path" if rates[REFORM][y] > floor + 1e-12 else rules.burnham_floor_source(c)
    return out


def model_triple_lock_rate(earnings, cpi):
    """The model's own triple-lock rate from calendar growth, rounded as policyengine-uk's add_triple_lock rounds it.

    That is Python's round() to 3 dp, not rules.round_rate: this reproduces the model to check it, so it rounds as
    the model does (the two differ only on exact half-grid inputs).
    """
    return round(max(earnings, cpi, TRIPLE_LOCK_FLOOR), 3)


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


def set_flat_rates(sim, levels, extra=None):
    """Set the flat rates (by name) and any other amounts (by parameter path) for every horizon year."""
    from policyengine_uk.utils.scenario import Scenario

    Scenario.from_reform({**flat_rate_reform(levels), **amounts_reform(extra or {})}).simulation_modifier(sim)
    sim.tax_benefit_system.reset_parameter_caches()


def pinned_inputs(sim, years, sep_cpi):
    """Inputs every run of a path shares: pension types held at the survey year, and the additional pension.

    Type in year y: the survey-year type for people over State Pension age in y,
    otherwise none. Additional pension in y: the survey-year amount (the model's
    own, uprating factor 1 in that year) x the product of (1 + September CPI of
    the year before, never negative) over the upratings since, for people over
    State Pension age in y.
    """
    data_year = int(min(sim.dataset.years))
    base_type = np.asarray(sim.calculate("state_pension_type", data_year).to_numpy()).astype(str)
    asp = sim.calculate("additional_state_pension", data_year).to_numpy().astype(float)
    out = {"state_pension_type": {}, "additional_state_pension": {}}
    index = 1.0
    for y in range(data_year, max(years) + 1):
        if y > data_year:
            index *= 1 + max(sep_cpi[y - 1], 0.0)
        if y in years:
            sp = sim.calculate("is_SP_age", y).to_numpy().astype(bool)
            out["state_pension_type"][y] = np.where(sp, base_type, "NONE")
            out["additional_state_pension"][y] = asp * index * sp
    return out, data_year


def pin(sim, pinned):
    for v, by_year in pinned.items():
        for y, values in by_year.items():
            sim.set_input(v, y, values)


WEIGHT_INPUTS = ("household_weight", "benunit_weight", "person_weight")


def population_treatment(sim, pinned, data_year, years):
    """How a run treats the survey population, read from what it pins and what the model computes (run_path records
    it in fixed_inputs.population; the results' assumptions block is worded from it, and fails on a value it has no
    wording for, so a change to the population cannot leave the published wording behind):

    * ``weights``: "survey" when the run sets no weight input (the dataset's own weights, which move by year only
      as the dataset projects them), else "reweighted";
    * ``ages``: "survey_year" when every person's age in every year equals their survey-year age, else
      "aged_forward" if ages move between years, or "adjusted" if they differ from the survey's but do not move;
    * ``pension_types``: "survey_year" when every person over State Pension age in a year has their survey-year
      type pinned, else "not_survey_year"; "model" when the run pins no type.

    The static ageing planned in #14 §3 should record what it does by name where it does it: "ons_projection" for
    weights raked to the ONS projection and "cohort" for pension types by cohort (the assumptions block words both).
    ``sim`` must not have had ``pinned`` applied: its data-year values are the survey's.
    """
    weights = "reweighted" if any(v in pinned for v in WEIGHT_INPUTS) else "survey"
    survey_age = sim.calculate("age", data_year).to_numpy()
    by_year = {y: np.asarray(pinned["age"][y]) if "age" in pinned and y in pinned["age"]
               else sim.calculate("age", y).to_numpy() for y in years}
    if all(np.array_equal(a, survey_age) for a in by_year.values()):
        ages = "survey_year"
    elif all(np.array_equal(a, by_year[years[0]]) for a in by_year.values()):
        ages = "adjusted"
    else:
        ages = "aged_forward"
    if "state_pension_type" not in pinned:
        types = "model"
    else:
        survey_type = np.asarray(sim.calculate("state_pension_type", data_year).to_numpy()).astype(str)

        def survey_types(y):
            pinned_type = np.asarray(pinned["state_pension_type"][y]).astype(str)
            on = pinned_type != "NONE"
            return np.array_equal(pinned_type[on], survey_type[on])

        types = "survey_year" if all(survey_types(y) for y in years) else "not_survey_year"
    return {"weights": weights, "ages": ages, "pension_types": types}


def held_pension_types(sim, pinned, years):
    """The State Pension types the model uses after ``pin``, checked person by person against the pinned array.

    Returns {year: {"records": {type: n}, "people": {type: weighted}}}, counted from
    ``sim.calculate("state_pension_type", year)``. Raises PathNotFollowed if any
    person's type in the model differs from the held one (an input the model
    ignored, recomputed or reordered), if the lengths differ, or if a type is not
    BASIC, NEW or NONE.
    """
    out = {}
    for y in years:
        held = np.asarray(pinned["state_pension_type"][y]).astype(str)
        model = np.asarray(sim.calculate("state_pension_type", y).to_numpy()).astype(str)
        if model.shape != held.shape:
            raise PathNotFollowed(f"the model has {model.size} State Pension types in {y}, the pinned array {held.size}")
        differ = int((model != held).sum())
        if differ:
            raise PathNotFollowed(f"{differ} people's State Pension type in {y} is not the held one")
        unknown = sorted(set(np.unique(model)) - set(PENSION_TYPES))
        if unknown:
            raise PathNotFollowed(f"unknown State Pension types in {y}: {unknown}")
        w = np.asarray(sim.calculate("person_weight", y).to_numpy(), dtype=float)
        out[y] = {"records": {t: int((model == t).sum()) for t in PENSION_TYPES},
                  "people": {t: float(w[model == t].sum()) for t in PENSION_TYPES}}
    return out


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
    expected_tl = {y: model_triple_lock_rate(calendar["earnings"][y - 1], calendar["cpi"][y - 1]) for y in HORIZON}
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
    changes = scenario_changes(spec, parameters)
    model_2026 = {s: float(parameters.get_child(f"{OBR_GROWTH}.{name}")(f"{BASE_YEAR}-01-01"))
                  for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))}
    del reference

    cpi, earnings, rates = spec_rates(spec)
    decimals = spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}
    pc_levels = pension_credit_levels(parameters, earnings, decimals)
    sep_cpi = september_cpi(spec)

    def build():
        return _managed(dataset, scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))

    unreformed = build()
    set_flat_rates(unreformed, {}, pc_levels)  # the model's own flat rates; the earnings-linked guarantee
    p = unreformed.tax_benefit_system.parameters
    applied_growth = {
        s: {y: float(p.get_child(f"{OBR_GROWTH}.{name}")(f"{y}-01-01")) for y in [BASE_YEAR, *CALENDAR_YEARS]}
        for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))
    }
    calendar = {s: {BASE_YEAR: model_2026[s], **{y: float(spec[s][y]) for y in CALENDAR_YEARS}}
                for s in ("cpi", "earnings")}
    following = path_following(unreformed, calendar)
    pc_applied = {y: float(p.get_child(PENSION_CREDIT_GUARANTEE["single"])(f"{y}-06-01")) for y in [BASE_YEAR, *HORIZON]}
    pc_growth = guarantee_growth(earnings, HORIZON, decimals)
    pc_err = max(abs(pc_applied[y] / pc_applied[y - 1] - 1 - pc_growth[y]) for y in HORIZON)
    following["pension_credit_guarantee_single"] = {
        "parameter": PENSION_CREDIT_GUARANTEE["single"], "weekly": pc_applied, "max_abs_error": pc_err,
        "follows": "May-July earnings growth the year before (never cut)"}
    if not pc_err <= 1e-9:
        raise PathNotFollowed(f"pension_credit_guarantee_single: off by {pc_err:.2e}")
    other_series = {
        group: {v: _growth({y: _unweighted_total(unreformed, v, y) for y in [BASE_YEAR, *HORIZON]}, HORIZON)
                for v in variables}
        for group, variables in (("not_moving", NOT_MOVING), ("also_moving", ALSO_MOVING))
    }
    pinned, data_year = pinned_inputs(unreformed, HORIZON, sep_cpi)
    population = population_treatment(unreformed, pinned, data_year, HORIZON)
    spa ={y: [float(v) for v in np.unique(unreformed.calculate("state_pension_age", y).to_numpy())] for y in HORIZON}
    del unreformed

    run_totals, income, groups, applied_weekly, hh, flat, employer_ni, pov = {}, {}, {}, {}, {}, {}, {}, {}
    held = {}
    household_ids = None
    for policy in POLICIES:
        sim = build()
        set_flat_rates(sim, levels[policy], pc_levels)
        pin(sim, pinned)
        held[policy] = held_pension_types(sim, pinned, HORIZON)  # the types the model uses are the held ones
        run_totals[policy] = totals(sim, HORIZON)
        pov[policy] = poverty(sim, HORIZON)
        income[policy] = {y: sim.calculate("household_net_income", y) for y in HORIZON}
        hh[policy] = {v: sim.calculate(v, FINAL_YEAR, map_to="household").to_numpy()
                      for v in ("household_id", *LARGEST_HOUSEHOLD_VARIABLES)}
        flat[policy] = {y: {n: sim.calculate(n, y).to_numpy().astype(float) for n in FLAT_RATE_PARAMETERS}
                        for y in HORIZON}
        employer_ni[policy] = max(
            abs(float(sim.calculate("employer_ni_fixed_employer_cost_change", y, map_to="household").sum())) / BN
            for y in HORIZON)
        if policy == "triple_lock":
            groups = {y: household_groups(sim, y) for y in DISTRIBUTION_YEARS}
            household_ids = sim.calculate("household_id", FINAL_YEAR).to_numpy()
        applied_weekly[policy] = {y: float(sim.tax_benefit_system.parameters.get_child(
            FLAT_RATE_PARAMETERS["new_state_pension"])(f"{y}-06-01")) for y in HORIZON}
        del sim

    # The model uses the rules' flat rates, read back after the reform.
    applied_err = max(abs(applied_weekly[p_][y] / levels[p_]["new_state_pension"][y] - 1) for p_ in POLICIES for y in HORIZON)
    if not applied_err <= 1e-9:
        raise PathNotFollowed(f"the model's new State Pension differs from the rule's by {applied_err:.2e}")
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
        "rate_sources": rate_sources(cpi, earnings, rates, HORIZON, spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)),
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
        "fixed_inputs": {
            "data_year": data_year,
            "population": population,  # population_treatment: weights, ages and pension types
            "state_pension_age": spa,
            "pension_credit_guarantee_single_weekly": pc_applied,
            # Counted from the model after pinning (held_pension_types checked every person under both rules).
            "held_pension_type_records": {y: held["triple_lock"][y]["records"] for y in HORIZON},
            "held_pension_type_people": {y: held["triple_lock"][y]["people"] for y in HORIZON},
        },
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
    ``years`` (the survey years), ``september_cpi_history`` (for the additional
    pension) and optional ``dataset``. Pension types are held at the survey year,
    as in run_path.
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
    pinned, _ = pinned_inputs(base, years, {int(y): float(v) for y, v in arg["september_cpi_history"].items()})
    pin(base, pinned)
    held_pension_types(base, pinned, years)
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
    held_pension_types(sim, pinned, years)
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
    pinned, _ = pinned_inputs(sim, [year], {int(y): float(v) for y, v in arg["september_cpi_history"].items()})
    pin(sim, pinned)  # as in the path runs: pension types held at the survey year
    held_pension_types(sim, pinned, [year])

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
    """sha256 of a file's bytes: provenance, so the results file goes stale on any edit."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _DropBareStrings(ast.NodeTransformer):
    """Remove docstrings and every other statement that is only a string: none changes what the code computes."""

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def source_semantics(path):
    """sha256 of what a source file says, not how it is written.

    Python: the syntax tree (``ast.dump``, no line numbers) without comments,
    docstrings or other statements that are only a string, so an edit to prose
    alone keeps the hash and any change to code, names or values moves it. TOML:
    the parsed document. Dropping docstrings is safe because no module the job
    key covers reads one at run time (tests/test_engine_pure.py checks).
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        canonical = json.dumps(tomllib.loads(text), sort_keys=True, default=str)
    else:
        canonical = ast.dump(_DropBareStrings().visit(ast.parse(text, filename=str(path))))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _engine_files(root=None, pyproject=None):
    here = Path(root) if root is not None else Path(__file__).resolve().parent
    return {**{name: here / name for name in ENGINE_FILES},
            "pyproject.toml": Path(pyproject) if pyproject is not None else REPO / "pyproject.toml"}


def engine_hashes(root=None, pyproject=None):
    """{file: sha256 of its bytes} for the engine files and pyproject.toml: the results file's provenance."""
    return {name: file_hash(path) for name, path in _engine_files(root, pyproject).items()}


def engine_semantics(root=None, pyproject=None):
    """{file: source_semantics} for the engine files and pyproject.toml: what a job's cache key holds for the code."""
    return {name: source_semantics(path) for name, path in _engine_files(root, pyproject).items()}


def package_versions():
    return {name: importlib.metadata.version(name) for name in TRACKED_PACKAGES}


def _canonical(obj):
    """Stable JSON: keys as strings (as a job receives them), sorted."""
    return json.dumps(json.loads(json.dumps(obj, default=float)), sort_keys=True, separators=(",", ":"))


def job_key(kind, arg, engine=None, packages=None):
    """Hash of what determines a job's result: kind, arguments, what the engine computes, package versions."""
    payload = {"kind": kind, "arg": arg, "engine": engine or engine_semantics(),
               "packages": packages or package_versions()}
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


# ── Child processes, worker directories and signals ──────────────────────

_children = {}  # pid -> Popen: every job process running now
_children_lock = threading.Lock()


def _signal_group(pgid, sig):
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def run_child(cmd, cwd, env=None, stop=None):
    """Run ``cmd`` to the end in a new session; returns (returncode, stdout, stderr).

    The child leads its own process group, so stopping the group stops anything
    it started too. It is registered while it runs, for kill_children; if the
    wait is interrupted in this thread (Ctrl-C, or a signal raised as an
    exception) the group is killed before the exception goes on. The child is
    told this process's id (PARENT_ENV) for watch_parent. Once ``stop`` is set
    this starts nothing and raises Aborted.
    """
    env = {**os.environ, **(env or {}), PARENT_ENV: str(os.getpid())}
    with _children_lock:
        if stop is not None and stop.is_set():
            raise Aborted("the build is stopping")
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        _children[proc.pid] = proc
    try:
        out, err = proc.communicate()
    except BaseException:
        _signal_group(proc.pid, signal.SIGKILL)
        proc.wait()
        raise
    finally:
        with _children_lock:
            _children.pop(proc.pid, None)
    return proc.returncode, out, err


def kill_children(stop=None, grace=KILL_GRACE_S):
    """Stop every running job: SIGTERM each one's process group, SIGKILL after ``grace`` seconds; returns how many.

    Sets ``stop`` first, under the registry's lock, so no job starts afterwards.
    """
    with _children_lock:
        if stop is not None:
            stop.set()
        procs = list(_children.values())
    for p in procs:
        _signal_group(p.pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    for p in procs:
        with contextlib.suppress(subprocess.TimeoutExpired):
            p.wait(timeout=max(0.0, deadline - time.monotonic()))
    for p in procs:
        _signal_group(p.pid, signal.SIGKILL)  # whatever ignored SIGTERM, and anything a job left in its group
    return len(procs)


def watch_parent(interval=PARENT_POLL_S):
    """In a process run_child started: kill it, and anything it started, once the process that started it is gone.

    A build killed outright (SIGKILL) cannot stop its jobs, and macOS has no
    parent-death signal, so a daemon thread polls the parent's id: a job whose
    build dies is re-parented and stops within ``interval`` seconds instead of
    running on for hours. Does nothing in a process run_child did not start.
    """
    expected = os.environ.get(PARENT_ENV)
    if not expected:
        return None
    expected = int(expected)

    def stop_self():
        if os.getpgrp() == os.getpid():  # run_child made this process its group's leader
            os.killpg(os.getpid(), signal.SIGKILL)
        os.kill(os.getpid(), signal.SIGKILL)

    def loop():
        while True:
            if os.getppid() != expected:
                stop_self()
            time.sleep(interval)

    thread = threading.Thread(target=loop, name="watch-parent", daemon=True)
    thread.start()
    return thread


@contextlib.contextmanager
def terminate_on_signals(signums=(signal.SIGTERM, signal.SIGHUP)):
    """Within the block SIGTERM and SIGHUP raise Terminated in the main thread instead of ending the process at once,
    so whatever is waiting on a job can stop it first. A signal already ignored (nohup) stays ignored; off the main
    thread this does nothing."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def raise_terminated(signum, frame):
        raise Terminated(128 + signum)

    previous = {}
    for s in signums:
        if signal.getsignal(s) != signal.SIG_IGN:
            previous[s] = signal.signal(s, raise_terminated)
    try:
        yield
    finally:
        for s, handler in previous.items():
            signal.signal(s, signal.SIG_DFL if handler is None else handler)


def _lock_holder(path):
    with contextlib.suppress(OSError):
        text = Path(path).read_text().strip()
        if text:
            return text
    return "another process"


@contextlib.contextmanager
def slot_lock(workdir, log=print, timeout=LOCK_TIMEOUT_S, poll=LOCK_POLL_S, log_every=LOCK_LOG_EVERY_S, stop=None):
    """Hold the exclusive lock on a worker directory for the block, never waiting for it silently or for ever.

    While another process holds it, log who (the holder writes its pid and start
    time into the lock file) every ``log_every`` seconds and try again every
    ``poll``; give up with LockTimeout after ``timeout`` seconds, or with Aborted
    as soon as ``stop`` is set.
    """
    import fcntl

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / ".lock"
    with open(path, "a+") as f:  # "a+", not "w": opening must not erase the holder's line
        start, next_log, logged = time.monotonic(), 0.0, False
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waited = time.monotonic() - start
                if waited >= timeout:
                    raise LockTimeout(f"{workdir} is still held by {_lock_holder(path)} after {waited:.0f}s: "
                                      "run one build at a time") from None
                if waited >= next_log:
                    log(f"  waiting for {workdir.name}: held by {_lock_holder(path)}")
                    next_log, logged = next_log + log_every, True
                if stop is None:
                    time.sleep(poll)
                elif stop.wait(poll):
                    raise Aborted(f"the build stopped while waiting for {workdir.name}") from None
        if logged:
            log(f"  {workdir.name} free after {time.monotonic() - start:.0f}s")
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} since {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
        f.flush()
        try:
            yield
        finally:
            f.seek(0)
            f.truncate()
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)


def _run_isolated(kind, arg, workdir, engine, stop=None):
    """Run one job in its own process, session and working directory (the dataset lands in ./data and stays)."""
    workdir.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(_canonical([kind, arg]).encode()).hexdigest()[:12]
    inp, out = workdir / f"input-{tag}.json", workdir / f"output-{tag}.json"
    inp.write_text(json.dumps({"kind": kind, "arg": arg, "engine": engine}, default=float))
    try:
        code, _, stderr = run_child([sys.executable, "-m", "triple_lock.engine", "--job", str(inp), str(out)],
                                    cwd=workdir, env={"PYTHONPATH": str(REPO / "src")}, stop=stop)
        if code != 0:
            raise RuntimeError(f"{kind} job failed in {workdir} (exit {code}):\n{stderr[-4000:]}")
        return json.loads(out.read_text())
    finally:
        inp.unlink(missing_ok=True)
        out.unlink(missing_ok=True)


def run_jobs(jobs, workers=3, slot_prefix="slot", log=print, cache=JOB_CACHE, runner=None,
             lock_timeout=LOCK_TIMEOUT_S):
    """Run [(kind, arg), ...], reusing cached results; returns the results in order.

    Each worker owns a directory under WORKDIRS, so its downloaded dataset
    persists between jobs; slot_lock keeps a second build (or script) from using
    it at the same time. When a job fails the queued jobs are cancelled, the
    running ones finish and stay cached, and every failed job is reported,
    including any that failed while the others finished. Ctrl-C, SIGTERM or
    SIGHUP stops every running job at once (kill_children). ``runner(kind, arg,
    workdir, engine, stop)`` runs one job (default _run_isolated).
    """
    from concurrent.futures import FIRST_EXCEPTION, wait

    runner = runner or _run_isolated
    engine, packages = engine_semantics(), package_versions()
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
    stop = threading.Event()

    def work(i):
        kind, arg = jobs[i]
        s = slots.get()
        try:
            with slot_lock(WORKDIRS / f"{slot_prefix}{s}", log, lock_timeout, stop=stop):
                started = datetime.now(timezone.utc)
                result = runner(kind, arg, WORKDIRS / f"{slot_prefix}{s}", engine, stop)
        finally:
            slots.put(s)
        if engine_semantics() != engine:
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

    pool = ThreadPoolExecutor(workers)
    futures = {}
    try:
        with terminate_on_signals():
            futures = {pool.submit(work, i): i for i in todo}
            _, pending = wait(futures, return_when=FIRST_EXCEPTION)
            if pending:  # a job failed: start nothing more, and let the running jobs finish
                log("A job failed: cancelling the queued jobs and waiting for the running ones")
                stop.set()
                for f in pending:
                    f.cancel()
            pool.shutdown(wait=True)
    except BaseException:  # Ctrl-C, SIGTERM or SIGHUP (Terminated), or an error here: stop the running jobs now
        log(f"Stopping: killed {kill_children(stop)} running job(s)")
        for f in futures:
            f.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    failed, not_run = [], 0
    for f, i in futures.items():
        if f.cancelled() or isinstance(f.exception(), Aborted):
            not_run += 1
        elif f.exception() is not None:
            failed.append(f"{jobs[i][0]} job {job_key(*jobs[i], engine, packages)[:12]}: {f.exception()}")
    if failed or not_run:
        raise RuntimeError(f"{len(failed)} job(s) failed and {not_run} did not run; the rest finished and are "
                           "cached:\n" + "\n".join(failed))
    for f, i in futures.items():
        results[i] = f.result()
    return results


def _job(inp, out):
    from . import model_horizon

    watch_parent()
    payload = json.loads(Path(inp).read_text())
    if engine_semantics() != payload["engine"]:
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
