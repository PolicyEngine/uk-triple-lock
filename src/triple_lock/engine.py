"""Full PolicyEngine UK runs of the two rules on a growth path, each in its own process, cached by input.

Every fiscal and household figure in the results comes from a job here; nothing
is scaled from another run. The model is policyengine-uk 2.120.0, pinned
directly, on datasets pinned to a revision and a SHA-256 (datasets.py); no
policyengine.py release certifies the pair, and every run records that.

How a path enters the model
---------------------------
A path's calendar-year CPI and earnings growth for 2027-2039 replace
``gov.economic_assumptions.yoy_growth.obr`` (RPI and CPIH move by the same
amount as CPI), and its statutory inputs for 2026-2038 (September CPI and
May-July AWE, each at its observation date) replace the model's
``statutory_uprating_inputs``, in a Scenario applied before the data load.
(The same changes passed as a reform are a silent no-op: the derived series
are built at load time.) Each job first extends the private pension
uprating, the one derived series policyengine-uk still stops before 2039-40
(model_horizon). Each run records, and fails unless, in every year 2027-28 to
2039-40:

* benefit rates uprated by ``gov.benefit_uprating_cpi`` grow by the path's
  calendar CPI the year before (the Pension Credit guarantee is not among them:
  every run sets it from May-July earnings, below);
* CPI-indexed thresholds (the NI lower earnings limit) grow by the path's
  calendar CPI the same year;
* employment income grows by the path's earnings the same year;
* the model's statutory inputs are the path's, its own triple lock is
  max(September CPI, May-July earnings, 2.5%) of them the year before (each
  input to 0.1 point as the model rounds it), and its new State Pension
  compounds that;
* the Pension Credit standard minimum guarantee grows by the path's May-July
  earnings the year before, never cut.

Also moving with the path: survey amounts policyengine-uk uprates by CPI
(reported benefits, consumption) and private pension income (the previous
year's RPI, capped at 5%). Not moving: dividend, property and savings income,
self-employment income, rents and council tax, whose growth ``not_moving``
records on every run. Calendar 2026 growth, which
sets April 2027's benefit uprating, is the model's own on every path.

The State Pension flat rates are set from each rule applied to the path's
statutory inputs (to 0.1 point as published, by rules.round_rate), or from a
rate the spec specifies for that rule and year (a scenario run:
``specified_rates``, rounded the same way). Under both rules:

* the population is the run's treatment (config.DEMOGRAPHY_MODES; the
  model-v2 treatment ``both`` unless the spec names another): represented ages
  above 80, a fixed birthday, ONS-projection weights after the data's
  calibration year and State Pension types by cohort (demography.py), pinned
  on every simulation of the run (pinned_inputs);
* the State Pension age is the model's own, by date of birth (the Pensions
  Act 1995 timetable, with the rise to 67), read through ``is_SP_age`` and
  ``state_pension_age`` on the ages the run uses; with ages held, a record's
  date of birth moves a year later each year, so 66-year-olds are partly over
  it in 2026-27 and 2027-28 and below it from 2028-29;
* each person's State Pension type is the treatment's (by cohort, or held at
  the survey year). Every run reads the types back from the model in every
  year, fails if any differs from the pinned one, and records the counts;
* the additional State Pension is the part of the reported pension (counted
  only over State Pension age in the data year) above the flat rate of each
  year's type, at the data year's flat rates, grown by September CPI
  (published to April 2026, the path's after), as in law, for people over
  State Pension age that year. Split by each year's type, as policyengine-uk's
  own flat-rate parts are, it never pays the band between the two flat rates
  twice; policyengine-uk 2.120.0 still scales it by the flat rates' ratio (its
  issue #1941), which would cut it under the Burnham plan. Every run checks the
  data year's identity basic + new + additional = the counted report, person
  by person (state_pension_accounting);
* the Pension Credit standard minimum guarantee rises with the path's May-July
  earnings growth (config.PENSION_CREDIT_GUARANTEE; SSAA 1992 s150A), where
  policyengine-uk 2.120.0 uprates it by CPI.

A Scenario simulation builds a second, default-path simulation as its
``baseline``; every run drops it before calculating, so no variable compares
against it, and records that employer NI incidence is zero.

The money
---------
The gross saving is the change in basic and new State Pension spending. The net
saving is the change in gov_balance, policyengine-uk's gov_tax less its
gov_spending; ``totals`` sums every variable on their lists (fiscal_variables),
so the components add up to it exactly. Every path and coverage run gives
Great Britain (households in England, Scotland and Wales) beside the UK.

Jobs
----
Each job (``JOBS``) runs in its own process, started by ``jobs.run_jobs``. Its
result is cached in ``JOB_CACHE`` under a key hashing the job's kind and
arguments, what the engine's code computes (``engine_semantics``: each engine
file's syntax tree without comments or docstrings) and the installed package
versions, so an interrupted build resumes, a changed engine reruns and an edit
to its prose alone reruns nothing. The results file's provenance keeps the
files' raw hashes (``engine_hashes``), so it still goes stale on any edit. How
jobs are scheduled, isolated and stopped (``jobs.py``) is not part of the key:
it never changes what a job computes, and the cache keeps each job's output as
the job wrote it.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import json
import sys
import tomllib
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np

from . import datasets, rules
from .disclosure import MIN_RECORDS, complementary_suppression, coverage_cell
from .config import (
    BASE_YEAR,
    CALENDAR_YEARS,
    CENTRAL_RATE_DECIMALS,
    DEMOGRAPHY,
    DEMOGRAPHY_MODES,
    DISTRIBUTION_YEARS,
    FINAL_YEAR,
    FISCAL_GROUPS,
    FISCAL_IDENTITY_TOL_BN,
    FISCAL_LEVEL_TOL_BN,
    FISCAL_MODEL_TOL_BN,
    FLAT_RATE_PARAMETERS,
    HORIZON,
    JOB_CACHE,
    MODEL_TRIPLE_LOCK_PARAMETER,
    STATUTORY_PARAMETERS,
    OBR_GROWTH,
    PENSION_CREDIT_GUARANTEE,
    POLICIES,
    POPULATION_PROJECTION,
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
ENGINE_FILES = ["__init__.py", "engine.py", "datasets.py", "model_horizon.py", "rules.py", "config.py", "breakdowns.py",
                "demography.py", "cohorts.py", "disclosure.py"]
# Data files a job reads besides the dataset (whose pin is in its arguments): hashed byte for byte.
ENGINE_DATA = {"ons_npp_2024_uk_age_sex.csv": POPULATION_PROJECTION}
TRACKED_PACKAGES = ["policyengine-uk", "policyengine-core", "microdf-python", "numpy", "pandas", "tables", "h5py",
                    "scipy"]  # scipy: the rake (demography.rake_households)
REFORM = "burnham_2030"
PENSION_TYPES = ("BASIC", "NEW", "NONE")
TOP_RECORDS = 10  # the published concentration measure's records (disclosure.MIN_RECORDS)


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


def statutory_changes(spec):
    """Scenario parameter changes putting a path's statutory inputs (September CPI and May-July AWE, 2026-2038) into
    the model's, each at its observation date, so the model builds its own triple lock from them.

    policyengine-uk (from 2.118.0) fills a year it has no figure for with calendar growth plus a forecast gap, and
    keeps a published one; setting every year replaces both, so the model's inputs are the path's (path_following
    reads them back). Unrounded, as the rules receive them: the model rounds them as it does (model_triple_lock_rate).
    """
    return {path: {f"year:{y}-{month_day}:1": float(spec[f"statutory_{series}"][y]) for y in STATUTORY_YEARS}
            for series, (path, month_day) in STATUTORY_PARAMETERS.items()}


def scenario_changes(spec, parameters):
    """Everything set before the data load: the path's calendar growth and its statutory inputs. (The State Pension
    age is the model's own, by date of birth.)"""
    return {**econ_changes(spec, parameters), **statutory_changes(spec)}


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
    specified = spec_specified(spec)
    rates = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals, specified=specified)
             for p in POLICIES}
    return cpi, earnings, rates


def spec_specified(spec):
    """A path's optional ``specified_rates``, {policy: {uprating year: rate}}: what a scenario run pays instead of
    that policy's rule (rules.rates_matrix). Empty when the spec has none, so the rules alone set every rate."""
    out = {p: {int(y): float(v) for y, v in by_year.items()} for p, by_year in spec.get("specified_rates", {}).items()}
    bad = sorted((p, y) for p, by_year in out.items() for y, v in by_year.items() if not np.isfinite(v))
    if bad:
        raise ValueError(f"specified rates must be finite numbers: NaN or infinity for {bad}")
    return out


def rate_sources(cpi, earnings, rates, years=HORIZON, decimals=CENTRAL_RATE_DECIMALS, specified=None):
    """{policy: {year: source}} naming what set each year's rise, from the inputs as the rules saw them.

    Triple lock: rules.triple_lock_source, as the history table labels it ("floor"
    whenever neither input exceeds 2.5%, CPI when the inputs tie). Burnham plan:
    "triple_lock" before the switch; after it "earnings_path" when it tops up to
    its earnings path, otherwise "cpi" above 2.5% and "floor" at or below it.
    A year in ``specified`` ({policy: {year: rate}}, as spec_specified reads it)
    is "specified" for that policy; before the switch the plan stays
    "triple_lock", since it pays the triple lock's rate, specified or not.
    """
    specified = specified or {}
    out = {p: {} for p in POLICIES}
    for y in years:
        c, e = float(rules.round_rate(cpi[y - 1], decimals)), float(rules.round_rate(earnings[y - 1], decimals))
        out["triple_lock"][y] = "specified" if y in specified.get("triple_lock", {}) else rules.triple_lock_source(c, e)
        if y < SWITCH_YEAR:
            out[REFORM][y] = "triple_lock"
            continue
        if y in specified.get(REFORM, {}):
            out[REFORM][y] = "specified"
            continue
        floor = float(rules.round_rate(max(c, TRIPLE_LOCK_FLOOR), decimals))
        out[REFORM][y] = "earnings_path" if rates[REFORM][y] > floor + 1e-12 else rules.burnham_floor_source(c)
    return out


def published_precision(rate):
    """A statutory input as policyengine-uk's create_triple_lock rounds it: to 0.1 point, halves away from zero, on
    the shortest decimal that reads back as the float (Decimal(repr(x)))."""
    return float(Decimal(repr(float(rate))).quantize(Decimal("0.001"), ROUND_HALF_UP))


def model_triple_lock_rate(earnings, cpi):
    """The model's own triple-lock rate for an April from the year before's statutory inputs (May-July earnings,
    September CPI), as policyengine-uk 2.118.0's add_triple_lock builds it under current law: the largest of the two
    inputs, each rounded by published_precision, and 2.5%.

    This reproduces the model to check it, so it rounds as the model does, not with rules.round_rate (numpy's halves
    to even): the two differ only on exact half-grid inputs.
    """
    return max(published_precision(earnings), published_precision(cpi), TRIPLE_LOCK_FLOOR)


# ── Simulation helpers ───────────────────────────────────────────────────


# What loading a dataset does to the survey population, declared by the code that loads it (_managed) and read by
# population_treatment, which fails without it: weights as the dataset holds them (uprated by year as the dataset
# does), ages as surveyed. A load or transform that reweights or ages the survey (#14 §3) replaces the declaration
# with what it did ("ons_projection", "adjusted", ...), since a change made inside the dataset leaves nothing to
# compare against: the dataset already holds the changed weights and ages.
LOADED_POPULATION = {"weights": "survey", "ages": "survey_year"}


def _managed(dataset=None, **kwargs):
    """A Microsimulation on a pinned dataset (datasets.materialize checks its SHA-256), with what it ran on attached
    (``sim.triple_lock_provenance``: the installed model, the dataset's pin, uncertified)."""
    from policyengine_uk import Microsimulation

    name = datasets.resolve(dataset)
    # A path, not a dataset object: every simulation reads the file afresh and extends it to later years with its own
    # parameters (the path's growth, under a Scenario applied before the data load).
    sim = Microsimulation(dataset=str(datasets.materialize(name)), **kwargs)
    sim.baseline = None  # a Scenario's default-path comparator; nothing may compare against it
    sim.triple_lock_population = dict(LOADED_POPULATION)
    sim.triple_lock_provenance = datasets.provenance(name)
    return sim


def model_parameters():
    """The unreformed model's processed parameters (no dataset: they do not depend on one)."""
    from policyengine_uk import CountryTaxBenefitSystem

    return CountryTaxBenefitSystem().parameters


STATE_PENSION_PARTS = ["basic_state_pension", "additional_state_pension", "new_state_pension"]


class NotDecomposable(PathNotFollowed):
    """gov_balance in some year is not the sum of the variables fiscal_variables lists."""


def fiscal_variables(parameters, year):
    """(tax, spending): the variables gov_balance adds and subtracts in ``year``, as policyengine-uk's gov_tax and
    gov_spending formulas list them (GOV_TAX_VARIABLES, GOV_SPENDING_VARIABLES), with their conditionals mirrored.

    gov_tax and gov_spending drop council tax, the high value council tax surcharge and council tax reduction while
    gov.contrib.abolish_council_tax is on. state_pension, in the spending list, is replaced by its three parts
    (basic, additional and new State Pension), which it sums when gov.contrib.abolish_state_pension is off and
    gov.contrib.cec.state_pension_increase is nil, as in current law; otherwise this raises NotDecomposable. Each
    formula reads its parameters at the start of the period, as here.
    """
    from policyengine_uk.variables.gov.gov_spending import GOV_SPENDING_VARIABLES
    from policyengine_uk.variables.gov.gov_tax import GOV_TAX_VARIABLES

    def at(path):
        return parameters.get_child(path)(f"{year}-01-01")

    tax, spending = list(GOV_TAX_VARIABLES), list(GOV_SPENDING_VARIABLES)
    if at("gov.contrib.abolish_council_tax"):
        tax = [v for v in tax if v not in ("council_tax", "high_value_council_tax_surcharge")]
        spending = [v for v in spending if v != "council_tax_benefit"]
    if at("gov.contrib.abolish_state_pension") or at("gov.contrib.cec.state_pension_increase") != 0:
        raise NotDecomposable(f"state_pension is not the sum of its parts in {year}")
    i = spending.index("state_pension")
    spending[i:i + 1] = STATE_PENSION_PARTS
    if len(set(tax)) != len(tax) or len(set(spending)) != len(spending) or set(tax) & set(spending):
        raise NotDecomposable(f"a variable is listed twice in {year}'s tax and spending lists")
    return tax, spending


def fiscal_groups(change, tax, spending):
    """{group: change} for FISCAL_GROUPS plus other_spending and other_tax, from {variable: change} over ``tax`` and
    ``spending``. Every variable is in exactly one group, so with spending counted negative they add up to the change
    in gov_balance."""
    grouped = {v for vs in FISCAL_GROUPS.values() for v in vs}
    if not grouped <= set(tax) | set(spending):
        raise NotDecomposable(f"groups name variables gov_balance does not count: {sorted(grouped - set(tax) - set(spending))}")
    out = {name: sum(change[v] for v in vs) for name, vs in FISCAL_GROUPS.items()}
    out["other_spending"] = sum(change[v] for v in spending if v not in grouped)
    out["other_tax"] = sum(change[v] for v in tax if v not in grouped)
    return out


def tax_groups(tax):
    """The groups whose variables gov_balance adds (taxes): the rest it subtracts."""
    return {name for name, vs in FISCAL_GROUPS.items() if set(vs) <= set(tax)} | {"other_tax"}


def net_from_components(components, tax):
    """The change in gov_balance the groups imply: taxes added, spending subtracted."""
    taxes = tax_groups(tax)
    return sum(c if name in taxes else -c for name, c in components.items())


GREAT_BRITAIN = ("ENGLAND", "SCOTLAND", "WALES")


def gb_mask(sim, year, entity="household"):
    """True for an entity's members in Great Britain: in households in England, Scotland or Wales (DWP's tables
    cover Great Britain; the model, the UK). Northern Ireland and a country policyengine-uk records as UNKNOWN (from
    an unknown region; neither the Enhanced FRS nor Microcosm has one) are outside it. A person takes their
    household's; a benefit unit, its members' (all in one household)."""
    country = np.asarray(sim.calculate("country", year, decode_enums=True).to_numpy()).astype(str)
    if not set(np.unique(country)) <= {*GREAT_BRITAIN, "NORTHERN_IRELAND", "UNKNOWN"}:
        raise ValueError(f"unexpected countries {sorted(set(np.unique(country)))}")
    household = np.isin(country, GREAT_BRITAIN)
    if entity == "household":
        return household
    person = np.asarray(sim.populations["household"].project(household)).astype(bool)
    return person if entity == "person" else np.asarray(sim.populations[entity].any(person)).astype(bool)


def _household_total(sim, variable, year, mask=None):
    """£bn, household-weighted, in float64; over the households in ``mask`` if given."""
    s = sim.calculate(variable, year, map_to="household")
    v = np.asarray(s.values, dtype=np.float64) * np.asarray(s.weights.values, dtype=np.float64)
    return float(v.sum() if mask is None else v[mask].sum()) / BN


def household_income_bridge(sim, year, tax, spending):
    """Independent right-hand side of G + H = market income - pension
    contributions + taxes outside H - spending outside H.

    Read household-income lists separately from fiscal lists. Their common
    variables cancel; the remaining terms are calculated from the model.
    """
    from policyengine_uk.variables.household.income.household_benefits import HOUSEHOLD_BENEFIT_VARIABLES
    from policyengine_uk.variables.gov.hmrc.household_tax import HOUSEHOLD_TAX_VARIABLES

    parameters = sim.tax_benefit_system.parameters
    at = lambda path: parameters.get_child(path)(f"{year}-01-01")
    ht, hb = set(HOUSEHOLD_TAX_VARIABLES), set(HOUSEHOLD_BENEFIT_VARIABLES)
    hb.remove("state_pension")
    hb.update(STATE_PENSION_PARTS)
    if at("gov.contrib.abolish_council_tax"):
        ht -= {"council_tax", "high_value_council_tax_surcharge"}
        hb.discard("council_tax_benefit")
    gt, gs = set(tax), set(spending)
    total = lambda variable: _household_total(sim, variable, year)
    value = total("household_market_income") - total("pension_contributions")
    value += sum(total(v) for v in sorted(gt - ht)) - sum(total(v) for v in sorted(ht - gt))
    value += sum(total(v) for v in sorted(hb - gs)) - sum(total(v) for v in sorted(gs - hb))
    # household_benefits has two optional broad uprating terms; mirror them
    # independently rather than assuming their parameters are zero.
    all_uprating = float(at("gov.contrib.benefit_uprating.all"))
    non_sp_uprating = float(at("gov.contrib.benefit_uprating.non_sp"))
    if all_uprating:
        value += all_uprating * sum(total(v) for v in sorted(hb - {"basic_income"}))
    if non_sp_uprating:
        value += non_sp_uprating * sum(total(v) for v in sorted(hb - {"basic_income", *STATE_PENSION_PARTS}))
    return value


def totals(sim, years):
    """Weighted totals (£bn) by year: every variable gov_balance adds or subtracts (``variables``), grouped as
    FISCAL_GROUPS and the rest; gov_balance as their float64 sum, taxes less spending, and the model's own float32
    total (``gov_balance_model``); household net income; the basic and new State Pension.

    ``gb``: the same groups, gov_balance, household net income and basic and new State Pension for Great Britain
    (households in England, Scotland and Wales). Raises NotDecomposable if the model's gov_balance is not the sum of the
    variables, to FISCAL_LEVEL_TOL_BN.
    """
    parameters = sim.tax_benefit_system.parameters
    out = {}
    for y in years:
        tax, spending = fiscal_variables(parameters, y)
        gb = gb_mask(sim, y)
        each = {v: _household_total(sim, v, y) for v in [*tax, *spending]}
        each_gb = {v: _household_total(sim, v, y, gb) for v in [*tax, *spending]}
        t = fiscal_groups(each, tax, spending)
        t["gov_balance"] = net_from_components(fiscal_groups(each, tax, spending), tax)
        t["gov_balance_model"] = _household_total(sim, "gov_balance", y)
        identity = abs(t["gov_balance"] - t["gov_balance_model"])
        if not identity <= FISCAL_LEVEL_TOL_BN:
            raise NotDecomposable(f"gov_balance in {y} is not its tax less its spending: off by £{identity:.3g}bn")
        t["household_net_income"] = _household_total(sim, "household_net_income", y)
        t["household_income_bridge"] = household_income_bridge(sim, y, tax, spending)
        income_identity = t["gov_balance"] + t["household_net_income"] - t["household_income_bridge"]
        if not abs(income_identity) <= FISCAL_LEVEL_TOL_BN:
            raise NotDecomposable(f"government/household income identity fails in {y}: £{income_identity:.3g}bn")
        for v in SPENDING_DETAIL:
            t[v] = each[v]
        t["gb"] = {**fiscal_groups(each_gb, tax, spending),
                   "gov_balance": net_from_components(fiscal_groups(each_gb, tax, spending), tax),
                   "household_net_income": _household_total(sim, "household_net_income", y, gb),
                   **{v: each_gb[v] for v in SPENDING_DETAIL}}
        t["variables"] = each
        t["tax_variables"] = sorted(tax)
        out[y] = t
    return out


def saving_components(policy_totals, base_totals):
    """The change from ``base_totals`` to ``policy_totals`` (one year each) in every fiscal group and variable, and
    the identity they meet: the groups, taxes added and spending subtracted, make the change in gov_balance (to
    FISCAL_IDENTITY_TOL_BN), and the model's own float32 gov_balance moves by the same to FISCAL_MODEL_TOL_BN."""
    tax = policy_totals["tax_variables"]
    if base_totals["tax_variables"] != tax or set(base_totals["variables"]) != set(policy_totals["variables"]):
        raise NotDecomposable("the two runs count different variables in gov_balance")
    groups = [*FISCAL_GROUPS, "other_spending", "other_tax"]
    components = {k: policy_totals[k] - base_totals[k] for k in groups}
    by_variable = {v: policy_totals["variables"][v] - base_totals["variables"][v] for v in policy_totals["variables"]}
    net = policy_totals["gov_balance"] - base_totals["gov_balance"]
    residual = net - net_from_components(components, tax)
    if not abs(residual) <= FISCAL_IDENTITY_TOL_BN:
        raise NotDecomposable(f"the components miss the change in gov_balance by £{residual:.3g}bn")
    model = policy_totals["gov_balance_model"] - base_totals["gov_balance_model"]
    if not abs(model - net) <= FISCAL_MODEL_TOL_BN:
        raise NotDecomposable(f"the model's float32 gov_balance moves by £{model - net:.3g}bn more than its parts")
    income_residual = None
    if "household_income_bridge" in policy_totals or "household_income_bridge" in base_totals:
        income_change = policy_totals["household_net_income"] - base_totals["household_net_income"]
        bridge_change = policy_totals["household_income_bridge"] - base_totals["household_income_bridge"]
        income_residual = net + income_change - bridge_change
        if not abs(income_residual) <= FISCAL_MODEL_TOL_BN:
            raise NotDecomposable(f"change in government/household income identity fails: £{income_residual:.3g}bn")
    return {"components": components, "components_by_variable": by_variable, "decomposition_residual": residual,
            "net_model_float32": model, "household_income_identity_residual": income_residual}


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


class Pinned(dict):
    """{variable: {year: values}}: the inputs every run of a path shares, set in each simulation by ``pin``.

    Not pinned, but carried for the run's checks and records: ``demography`` (the treatment), ``data_year``,
    ``reported`` (the data year's reported State Pension as the survey has it), ``over_pension_age`` ({year: the
    model's is_SP_age}) and, for an ageing treatment, ``treatment`` (the demography.Population it came from).
    """


def pinned_inputs(sim, years, sep_cpi, demography=None, anchor=None, retyped_level="kept"):
    """Inputs every run of a path shares, the same under both rules: the population, State Pension types, the
    additional State Pension and the data year's reported State Pension. Returns (Pinned, data year).

    ``demography`` names the treatment (config.DEMOGRAPHY_MODES; None: config.DEMOGRAPHY). An ageing treatment's
    population (demography.population: represented ages, a birthday, raked weights, survey head flags) is pinned on
    ``sim`` here, so the model's own State Pension age reads it; ``sim`` must not have been pinned before. ``legacy``
    keeps the survey's ages and weights.

    Types in year y: under ``legacy``, ``frozen`` and ``reweight`` each person's survey-year type, under ``types``
    and ``both`` their cohort's (demography); none for people below State Pension age in y (the model's is_SP_age).

    The State Pension accounting is one rule under every treatment. The reported State Pension counts only for
    people over State Pension age in the data year (demography.payable_reported; the data year's
    state_pension_reported is pinned to it). Each year it is split by that year's type at the type's data-year flat
    rate (demography.pension_components), as policyengine-uk's own formulas split it: the flat-rate part, which
    policyengine-uk scales by the flat rate, and the rest, the additional State Pension (SERPS, S2P and protected
    payments), pinned here at its data-year amount grown by September CPI (published to April 2026, the path's
    after; never cut), for people over State Pension age that year. So basic + new + additional equals the payable
    reported pension in the data year for every person, whatever the type, and a cut in the flat rates moves only
    the flat-rate parts. (policyengine-uk 2.120.0 uprates the additional pension by the flat rates' ratio, its issue
    #1941.) Splitting it by the survey year's type instead would pay the band between the two flat rates twice for
    everyone a cohort type moves from basic to new.
    """
    from policyengine_uk.model_api import WEEKS_IN_YEAR

    from . import demography as ageing

    mode = DEMOGRAPHY if demography is None else demography
    if mode not in DEMOGRAPHY_MODES:
        raise ValueError(f"unknown demography treatment {mode!r}: one of {DEMOGRAPHY_MODES}")
    if retyped_level not in ("kept", "full_new"):
        raise ValueError("retyped_level must be kept or full_new")
    data_year = int(min(sim.dataset.years))
    years = sorted({int(y) for y in years})
    every = sorted({data_year, *years})
    reported = np.asarray(sim.calculate("state_pension_reported", data_year).to_numpy(), dtype=float)
    out = Pinned()
    if mode == "legacy":
        survey_type = np.asarray(sim.calculate("state_pension_type", data_year).to_numpy()).astype(str)
        over = {y: np.asarray(sim.calculate("is_SP_age", y).to_numpy()).astype(bool) for y in every}
        types = {y: np.where(over[y], survey_type, "NONE") for y in every}
        survey_types = survey_type
    else:
        treatment = ageing.population(sim, every, mode, anchor)
        out.update(treatment)
        out.treatment = treatment
        over, types = treatment.over_pension_age, treatment.types
        survey_types = treatment.survey_types
    payable = ageing.payable_reported(reported, over[data_year])
    p = sim.tax_benefit_system.parameters.gov.dwp.state_pension
    caps = (float(p.basic_state_pension.amount(data_year)) * WEEKS_IN_YEAR,
            float(p.new_state_pension.amount(data_year)) * WEEKS_IN_YEAR)
    out["state_pension_reported"] = {data_year: payable}
    out["state_pension_type"], out["additional_state_pension"] = {}, {}
    index = 1.0
    for y in range(data_year, max(every) + 1):
        if y > data_year:
            index *= 1 + max(sep_cpi[y - 1], 0.0)
        if y in every:
            _, _, additional = ageing.pension_components(payable, types[y], *caps)
            out["state_pension_type"][y] = types[y]
            out["additional_state_pension"][y] = additional * index * over[y]
    out.demography, out.data_year, out.reported, out.over_pension_age = mode, data_year, reported, over
    out.retyped_level = retyped_level
    out.retyped_new = {y: (survey_types == "BASIC") & (types[y] == "NEW") & (y > data_year) for y in every}
    return out, data_year


def pin(sim, pinned):
    for v, by_year in pinned.items():
        for y, values in by_year.items():
            sim.set_input(v, y, values)
    if getattr(pinned, "retyped_level", "kept") == "full_new":
        from policyengine_uk.model_api import WEEKS_IN_YEAR
        from .demography import retyped_flat_rate

        for y, retyped in pinned.retyped_new.items():
            if not retyped.any():
                continue
            kept = np.asarray(sim.calculate("new_state_pension", y).to_numpy(), dtype=float)
            full = float(sim.tax_benefit_system.parameters.get_child(
                FLAT_RATE_PARAMETERS["new_state_pension"])(f"{y}-06-01")) * WEEKS_IN_YEAR
            sim.set_input("new_state_pension", y, retyped_flat_rate(kept, full, retyped, "full_new"))


WEIGHT_INPUTS = ("household_weight", "benunit_weight", "person_weight")


def population_treatment(sim, pinned, data_year, years):
    """How a run treats the survey population: {weights, ages, pension_types}, recorded by run_path in
    fixed_inputs.population. The results' assumptions block is worded from it and fails on a value it has no wording
    for, so a change to the population cannot leave the published wording behind.

    * ``weights`` and ``ages`` start from a declaration: an ageing treatment's (demography.Population.declared:
      "ons_projection" for raked weights, "adjusted" for represented ages), else the load's
      (``sim.triple_lock_population``, set by _managed; a simulation without one fails). What can be checked is:
      weights the run pins make "survey" weights wrong, and ages the run pins or the model moves between years make
      "survey_year" ages wrong (both raise PathNotFollowed); with survey-year ages declared, ages that move between
      years are recorded as "aged_forward".
    * ``pension_types``: the treatment's type rule ("survey_year" or "cohort") when the run pins types (held_pension_types
      then checks the model used them), "model" when it pins none.

    The survey ages are the treatment's (read before it pinned anything), else ``sim``'s data-year ages, so ``sim``
    must not have had survey ages replaced otherwise.
    """
    treatment = getattr(pinned, "treatment", None)
    declared = treatment.declared if treatment is not None else getattr(sim, "triple_lock_population", None)
    if not isinstance(declared, dict) or set(declared) != {"weights", "ages"}:
        raise PathNotFollowed("the simulation's load did not declare how it treats the survey population "
                              "(engine.LOADED_POPULATION)")
    weights, ages = declared["weights"], declared["ages"]
    if weights == "survey" and any(v in pinned for v in WEIGHT_INPUTS):
        raise PathNotFollowed("the run pins weights, but the load declared the survey's own weights")
    first = np.asarray(pinned["age"][years[0]]) if "age" in pinned else sim.calculate("age", years[0]).to_numpy()
    survey_age = treatment.survey_ages if treatment is not None else sim.calculate("age", data_year).to_numpy()
    by_year = [np.asarray(pinned["age"][y]) if "age" in pinned else sim.calculate("age", y).to_numpy() for y in years]
    moving = not all(np.array_equal(a, first) for a in by_year)
    if ages == "survey_year" and moving:
        ages = "aged_forward"
    elif ages == "survey_year" and not np.array_equal(first, survey_age):
        raise PathNotFollowed("the run's ages differ from the survey's, but the load declared survey-year ages")
    if "state_pension_type" not in pinned:
        types = "model"
    else:
        types = treatment.type_rule if treatment is not None else "survey_year"
    return {"weights": weights, "ages": ages, "pension_types": types}


def state_pension_age_band(sim, year):
    """[the youngest age (whole years) at which anyone is over State Pension age in ``year``, the youngest from which
    everyone is], one value when they coincide: the ages the run uses (survey or represented).

    policyengine-uk sets State Pension age by date of birth (is_SP_age, at 6 October); with ages held, a record's
    date of birth moves a year later each year, so while the age rises part of one age group is over it.
    """
    age = np.floor(np.asarray(sim.calculate("age", year).to_numpy(), dtype=float))
    over = np.asarray(sim.calculate("is_SP_age", year).to_numpy()).astype(bool)
    if not over.any():
        return []
    some = float(age[over].min())
    every = float(age[~over].max() + 1) if (~over).any() else float(age.min())
    return sorted({some, max(some, every)})


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
            raise PathNotFollowed(f"the model's State Pension types in {y} have shape {model.shape}, the pinned "
                                  f"array {held.shape}")
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


ACCOUNTING_TOL_GBP = 0.01  # £ a year, per person: the model stores amounts in float32


def additional_pension_followed(sim, pinned, years):
    """Largest gap (£ a year, per person) between the model's additional State Pension and the pinned one, in
    ``years``; PathNotFollowed over ACCOUNTING_TOL_GBP. Run in every policy's simulation, so the additional pension is
    the same under both rules and a change in the flat rates moves only the flat-rate parts."""
    gap = 0.0
    for y in years:
        model = np.asarray(sim.calculate("additional_state_pension", y).to_numpy(), dtype=float)
        gap = max(gap, float(np.abs(model - np.asarray(pinned["additional_state_pension"][y], dtype=float)).max()))
    if not gap <= ACCOUNTING_TOL_GBP:
        raise PathNotFollowed(f"the model's additional State Pension is off the pinned one by £{gap:.4f}")
    return gap


def state_pension_accounting(sim, pinned):
    """The data year's State Pension accounting, read from the model after ``pin``: aggregates only.

    For every person, basic + new + additional State Pension equals the reported State Pension the run counts (the
    survey's amount over State Pension age, nil below it: demography.payable_reported), to ACCOUNTING_TOL_GBP, and
    nobody below State Pension age is paid any. Raises PathNotFollowed otherwise. Records the survey's positive
    reports below State Pension age that the rule sets aside (records, people and £bn; withheld under ten records).
    """
    y = pinned.data_year
    parts = sum(np.asarray(sim.calculate(v, y).to_numpy(), dtype=float) for v in STATE_PENSION_PARTS)
    payable = np.asarray(pinned["state_pension_reported"][y], dtype=float)
    error = float(np.abs(parts - payable).max())
    if not error <= ACCOUNTING_TOL_GBP:
        raise PathNotFollowed(f"basic + new + additional State Pension is off the reported State Pension by "
                              f"£{error:.4f} in {y}")
    below = ~pinned.over_pension_age[y]
    if np.abs(parts[below]).max(initial=0.0) > 0:
        raise PathNotFollowed(f"State Pension paid below State Pension age in {y}")
    aside = below & (pinned.reported > 0)
    n = int(aside.sum())
    w = np.asarray(sim.calculate("person_weight", y).to_numpy(), dtype=float)
    shown = n == 0 or n >= MIN_RECORDS
    return {"data_year": y, "max_identity_error_gbp": error, "tolerance_gbp": ACCOUNTING_TOL_GBP,
            "reports_below_pension_age": {
                "records": n if shown else None,
                "people": float(w[aside].sum()) if shown else None,
                "reported_bn": float((w * pinned.reported)[aside].sum()) / BN if shown else None,
                "rule": "not State Pension in payment: no State Pension is payable below pensionable age "
                        "(demography.payable_reported)"}}


def ageing_record(pinned, readback=None):
    """What a run records about its ageing treatment (None under ``legacy``): the anchor year, the projection's
    SHA-256, whether top-coded ages were represented, the survey head flags kept, and (raked treatments) the largest
    relative miss of each year's ONS growth targets as the model read the weights back. Aggregates only."""
    treatment = getattr(pinned, "treatment", None)
    if treatment is None:
        return None
    return {"treatment": treatment.mode, "anchor_year": treatment.anchor,
            # Checked by demography.population on every use (it raises otherwise).
            "weights_unchanged_through_anchor": treatment.weights_unchanged_through_anchor,
            "population_projection_sha256": file_hash(POPULATION_PROJECTION),
            "represented_topcoding_applied": treatment.represented_topcoding_applied,
            "uncapped_age_fallback": treatment.uncapped_age_fallback,
            "survey_flags_pinned": list(treatment.survey_flags),
            # Records whose data-year type on the represented ages and birthday is not the one on the survey's own
            # (zero on the Enhanced FRS); withheld between one and nine (disclosure).
            "data_year_type_changes_records": (treatment.data_year_type_changes
                                               if treatment.data_year_type_changes == 0
                                               or treatment.data_year_type_changes >= MIN_RECORDS else None),
            "max_relative_cell_error": None if readback is None else readback["max_relative_cell_error"]}


def _unweighted_total(sim, variable, year):
    """Sum over the variable's own entity, unweighted: its growth is the uprating applied, whatever the weights do."""
    return float(np.asarray(sim.calculate(variable, year).values, dtype=float).sum())


def _number(value):
    return None if value is None else float(value)


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


def path_following(sim, calendar, statutory):
    """Model series the path must drive, in every horizon year, against what the path says.

    ``calendar``: {"cpi"|"earnings": {calendar year: growth}} for 2026-2039 as the
    model received them; ``statutory``: {"cpi"|"earnings": {year: input}} for
    2026-2038. Raises PathNotFollowed if any series misses.
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
    # The model's statutory inputs, read back where its triple lock reads them (each at its observation date).
    applied = {s: {y: _number(p.get_child(path)(f"{y}-{month_day}")) for y in STATUTORY_YEARS}
               for s, (path, month_day) in STATUTORY_PARAMETERS.items()}
    input_err = max(abs(applied[s][y] - float(statutory[s][y])) if applied[s][y] is not None else float("inf")
                    for s in applied for y in STATUTORY_YEARS)
    out["model_statutory_inputs"] = {"parameters": {s: path for s, (path, _) in STATUTORY_PARAMETERS.items()},
                                     "applied": applied, "max_abs_error": input_err,
                                     "follows": "the path's September CPI and May-July earnings"}
    if not input_err <= 1e-12:
        failures.append(f"model_statutory_inputs: off by {input_err:.2e}")
    model_tl = {y: float(p.get_child(MODEL_TRIPLE_LOCK_PARAMETER)(f"{y}-06-01")) for y in HORIZON}
    expected_tl = {y: model_triple_lock_rate(statutory["earnings"][y - 1], statutory["cpi"][y - 1]) for y in HORIZON}
    tl_err = max(abs(model_tl[y] - expected_tl[y]) for y in HORIZON)
    out["model_triple_lock"] = {"parameter": MODEL_TRIPLE_LOCK_PARAMETER, "rate": model_tl, "expected": expected_tl,
                                "max_abs_error": tl_err,
                                "follows": "max(May-July earnings, September CPI, 2.5%) the year before, each input "
                                           "to 0.1 point as the model rounds it"}
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
    ``statutory_earnings`` for 2026-2038, optional ``rate_decimals``,
    ``dataset`` (a datasets.DATASETS name; None: config.PRIMARY_DATASET), ``specified_rates``
    ({policy: {uprating year: rate}} paid instead of that rule: a scenario run) and ``demography`` (the population
    treatment, config.DEMOGRAPHY_MODES; None: config.DEMOGRAPHY).

    Under an ageing treatment the run returns no single-record diagnostic (``record_diagnostics_suppressed``): its
    weights are derived from the survey's, and a single household's weighted contribution would disclose one.
    """
    from policyengine_uk.utils.scenario import Scenario

    from .breakdowns import all_breakdowns, households_affected

    dataset = spec.get("dataset")
    parameters = model_parameters()
    base = base_levels(parameters)
    changes = scenario_changes(spec, parameters)
    model_2026 = {s: float(parameters.get_child(f"{OBR_GROWTH}.{name}")(f"{BASE_YEAR}-01-01"))
                  for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))}

    cpi, earnings, rates = spec_rates(spec)
    decimals = spec.get("rate_decimals", CENTRAL_RATE_DECIMALS)
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}
    pc_levels = pension_credit_levels(parameters, earnings, decimals)
    sep_cpi = september_cpi(spec)

    def build():
        return _managed(dataset, scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))

    unreformed = build()
    model = unreformed.triple_lock_provenance
    set_flat_rates(unreformed, {}, pc_levels)  # the model's own flat rates; the earnings-linked guarantee
    p = unreformed.tax_benefit_system.parameters
    applied_growth = {
        s: {y: float(p.get_child(f"{OBR_GROWTH}.{name}")(f"{y}-01-01")) for y in [BASE_YEAR, *CALENDAR_YEARS]}
        for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))
    }
    calendar = {s: {BASE_YEAR: model_2026[s], **{y: float(spec[s][y]) for y in CALENDAR_YEARS}}
                for s in ("cpi", "earnings")}
    following = path_following(unreformed, calendar, {"cpi": cpi, "earnings": earnings})
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
    treatment = spec.get("demography") or DEMOGRAPHY
    pinned, data_year = pinned_inputs(unreformed, HORIZON, sep_cpi, treatment,
                                    retyped_level=spec.get("retyped_level", "kept"))
    population = population_treatment(unreformed, pinned, data_year, HORIZON)
    spa = {y: state_pension_age_band(unreformed, y) for y in HORIZON}  # on the ages the run uses
    del unreformed

    run_totals, income, groups, applied_weekly, hh, flat, employer_ni, pov = {}, {}, {}, {}, {}, {}, {}, {}
    held, additional_gap, readback = {}, {}, None
    accounting = None
    household_ids = None
    flat_households, balance_households = {}, {}
    household_gb = None
    for policy in POLICIES:
        sim = build()
        set_flat_rates(sim, levels[policy], pc_levels)
        pin(sim, pinned)
        held[policy] = held_pension_types(sim, pinned, HORIZON)  # the types the model uses are the held ones
        additional_gap[policy] = additional_pension_followed(sim, pinned, HORIZON)
        if policy == "triple_lock":
            accounting = state_pension_accounting(sim, pinned)
            if treatment != "legacy":
                from .demography import readback as population_readback

                readback = population_readback(sim, pinned.treatment, HORIZON)
        run_totals[policy] = totals(sim, HORIZON)
        flat_households[policy] = {
            y: sum(np.asarray(sim.calculate(v, y, map_to="household").to_numpy(), dtype=float)
                   for v in ("basic_state_pension", "new_state_pension")) for y in HORIZON}
        balance_households[policy] = {
            y: np.asarray(sim.calculate("gov_balance", y).to_numpy(), dtype=float) for y in HORIZON}
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
            household_gb = gb_mask(sim, FINAL_YEAR)
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
    # The ten household records that move each year's net figure most, together: an aggregate over ten records, what
    # an ageing run publishes instead of a single record's contribution.
    top10 = {}
    for y in HORIZON:
        contrib = change[y].to_numpy() * income["triple_lock"][y].weights.to_numpy() / BN
        largest10 = np.argsort(-np.abs(contrib), kind="stable")[:TOP_RECORDS]
        total = float(contrib.sum())
        top10[y] = {"records": TOP_RECORDS, "contribution_bn": float(contrib[largest10].sum()),
                    "share_of_income_change": float(contrib[largest10].sum() / total) if total else 0.0}
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
        "dataset": model["runtime_dataset"],
        "rate_decimals": spec.get("rate_decimals", CENTRAL_RATE_DECIMALS),
        "statutory": {"cpi": cpi, "earnings": earnings},
        "calendar": {s: {y: float(spec[s][y]) for y in CALENDAR_YEARS} for s in ("cpi", "earnings")},
        "applied_growth": applied_growth,
        "path_following": following,
        **other_series,
        "rates": rates,
        "rate_sources": rate_sources(cpi, earnings, rates, HORIZON, decimals, spec_specified(spec)),
        "weekly": levels,
        "applied_new_state_pension": applied_weekly,
        "saving_bn": {
            y: {
                "gross": tl[y]["state_pension_flat_rate"] - bp[y]["state_pension_flat_rate"],
                "net": bp[y]["gov_balance"] - tl[y]["gov_balance"],
                "household_income_change": bp[y]["household_net_income"] - tl[y]["household_net_income"],
                **saving_components(bp[y], tl[y]),
                # Great Britain (households in England, Scotland and Wales), as DWP's figures are.
                "gb": {"gross": tl[y]["gb"]["state_pension_flat_rate"] - bp[y]["gb"]["state_pension_flat_rate"],
                       "net": bp[y]["gb"]["gov_balance"] - tl[y]["gb"]["gov_balance"],
                       "components": {k: bp[y]["gb"][k] - tl[y]["gb"][k] for k in [*FISCAL_GROUPS, "other_spending",
                                                                                   "other_tax"]}},
            }
            for y in HORIZON
        },
        "totals_bn": run_totals,
        "saving_support_records_by_year": {
            y: {geo: {measure: int(np.count_nonzero((arrays[REFORM][y] != arrays["triple_lock"][y]) & mask))
                      for measure, arrays in (("gross", flat_households), ("net", balance_households))}
                for geo, mask in (("uk", np.ones_like(household_gb)), ("gb", household_gb))}
            for y in HORIZON},
        "poverty_pct": pov,
        "households_affected": {y: households_affected(change[y]) for y in HORIZON},
        "distribution": {y: all_breakdowns(change[y], income["triple_lock"][y], groups[y]) for y in DISTRIBUTION_YEARS},
        # One or the other, never both: the single largest record's contribution and the ten largest records'
        # together would give a nine-record total by subtraction.
        **({"largest_household": largest, "concentration_by_year": concentration} if treatment == "legacy"
           else {"record_diagnostics_suppressed": True, "concentration_top10_by_year": top10}),
        "checks": {"max_proportionality_error_gbp": proportionality, "employer_ni_incidence_bn": employer_ni,
                   "max_additional_state_pension_gap_gbp": max(additional_gap.values())},
        "fixed_inputs": {
            "data_year": data_year,
            "demography": treatment,
            "retyped_level": pinned.retyped_level,
            "population": population,  # population_treatment: weights, ages and pension types
            "ageing": ageing_record(pinned, readback),
            "state_pension_accounting": accounting,
            "state_pension_age": spa,
            "pension_credit_guarantee_single_weekly": pc_applied,
            # Counted from the model after pinning (held_pension_types checked every person under both rules).
            "held_pension_type_records": {y: held["triple_lock"][y]["records"] for y in HORIZON},
            "held_pension_type_people": {y: held["triple_lock"][y]["people"] for y in HORIZON},
        },
        "model": model,
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
    pension), optional ``dataset`` and ``demography`` (the population treatment,
    as in run_path; None: config.DEMOGRAPHY).
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
    treatment = arg.get("demography") or DEMOGRAPHY
    pinned, _ = pinned_inputs(base, years, {int(y): float(v) for y, v in arg["september_cpi_history"].items()},
                              treatment)
    pin(base, pinned)
    held_pension_types(base, pinned, years)
    accounting = state_pension_accounting(base, pinned)
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
    additional_pension_followed(sim, pinned, years)
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
        "demography": treatment,
        "retyped_level": pinned.retyped_level,
        "state_pension_accounting": accounting,
        "data_year_denominator_weekly": denominators,
        "max_proportionality_error_gbp": proportionality,
        "saving_bn": {
            y: {
                "gross": base_totals[y]["state_pension_flat_rate"] - cf_totals[y]["state_pension_flat_rate"],
                "net": cf_totals[y]["gov_balance"] - base_totals[y]["gov_balance"],
                **saving_components(cf_totals[y], base_totals[y]),
            }
            for y in years
        },
        "households_losing_pct": float(100 * (weight * (change < -1)).sum() / weight.sum()),
    }


COVERAGE_AGE_BANDS = ((0, 60, "under_60"), (60, 65, "60_64"), (65, 70, "65_69"), (70, 75, "70_74"),
                      (75, 80, "75_79"), (80, 85, "80_84"), (85, 90, "85_89"), (90, 200, "90_plus"))


def coverage_stats(sim, year):
    """Spending (£bn) and caseloads (weighted people or benefit units) in one year, {"uk": ..., "gb": ...}: the whole
    model, and Great Britain (households in England, Scotland and Wales), as DWP's tables cover. State Pension
    spending and recipients are also given by age (COVERAGE_AGE_BANDS, the ages the run uses), each cell resting on at
    least ten records or suppressed (disclosure).

    Pension-age Housing Benefit is counted two ways: paid to benefit units under the pension-age Housing Benefit
    regulations (``housing_benefit_pension_age_regulations_apply``, nearest DWP's "over Pension Credit qualifying
    age"), and paid to benefit units with someone over State Pension age (what the results compared before
    model-v2).
    """
    def series(variable):
        s = sim.calculate(variable, year)
        entity = sim.tax_benefit_system.variables[variable].entity.key
        return np.asarray(s.values, dtype=np.float64), np.asarray(s.weights.values, dtype=np.float64), entity

    gb = {e: gb_mask(sim, year, e) for e in ("person", "benunit", "household")}
    sp_age = np.asarray(sim.calculate("is_SP_age", year).to_numpy()).astype(bool)
    benunit_pensioner = sim.map_result(sp_age.astype(float), "person", "benunit") > 0
    pension_age_rules = np.asarray(sim.calculate("housing_benefit_pension_age_regulations_apply", year).to_numpy()
                                   ).astype(bool)
    pension_type = np.asarray(sim.calculate("state_pension_type", year).to_numpy()).astype(str)
    person_weight = np.asarray(sim.calculate("person_weight", year).to_numpy(), dtype=np.float64)
    country = np.asarray(sim.calculate("country", year, decode_enums=True).to_numpy()).astype(str)
    household_weight = np.asarray(sim.calculate("household_weight", year).to_numpy(), dtype=np.float64)
    ages = np.asarray(sim.calculate("age", year).to_numpy(), dtype=np.float64)
    pension = {v: np.asarray(sim.calculate(v, year).to_numpy(), dtype=np.float64)
               for v in ("state_pension", *STATE_PENSION_PARTS)}
    households_by_country = {c: float(household_weight[country == c].sum()) for c in sorted(set(country))}
    out = {}
    for geo in ("uk", "gb"):
        def within(entity, extra=None):
            m = gb[entity] if geo == "gb" else np.ones_like(gb[entity])
            return m if extra is None else m & extra

        def total(variable, extra=None):
            v, w, e = series(variable)
            return float((v * w)[within(e, extra)].sum()) / BN

        def count(variable, extra=None):
            v, w, e = series(variable)
            return float(w[within(e, extra) & (v > 0)].sum())

        person = within("person")
        out[geo] = {
            "households_by_country": households_by_country if geo == "uk" else None,
            "state_pension_bn": total("state_pension"),
            "basic_state_pension_bn": total("basic_state_pension"),
            "new_state_pension_bn": total("new_state_pension"),
            "additional_state_pension_bn": total("additional_state_pension"),
            "state_pension_recipients": count("state_pension"),
            "state_pension_age_people": float(person_weight[person & sp_age].sum()),
            "pension_type_people": {t: float(person_weight[person & (pension_type == t)].sum())
                                    for t in sorted(set(pension_type))},
            "pension_credit_bn": total("pension_credit"),
            "guarantee_credit_bn": total("guarantee_credit"),
            "savings_credit_bn": total("savings_credit"),
            "pension_credit_benefit_units": count("pension_credit"),
            "housing_benefit_bn": total("housing_benefit"),
            "housing_benefit_benefit_units": count("housing_benefit"),
            "housing_benefit_pension_age_bn": total("housing_benefit", pension_age_rules),
            "housing_benefit_pension_age_benefit_units": count("housing_benefit", pension_age_rules),
            "housing_benefit_pensioner_benefit_units_bn": total("housing_benefit", benunit_pensioner),
            "council_tax_reduction_bn": total("council_tax_benefit"),
            "universal_credit_bn": total("universal_credit"),
            "people": float(person_weight[person].sum()),
            "state_pension_by_age": complementary_suppression(
                {name: coverage_cell(pension, person_weight, person & (ages >= lo) & (ages < hi))
                 for lo, hi, name in COVERAGE_AGE_BANDS}),
            "state_pension_by_country": complementary_suppression(
                {name: coverage_cell(pension, person_weight,
                                     person & np.asarray(sim.populations["household"].project(country == name), dtype=bool))
                 for name in GREAT_BRITAIN}),
            "programme_support_records": {
                name: int((within(series(variable)[2], extra) & (series(variable)[0] > 0)).sum())
                for name, variable, extra in (
                    ("pension_credit", "pension_credit", None),
                    ("housing_benefit", "housing_benefit", None),
                    ("housing_benefit_pension_age", "housing_benefit", pension_age_rules))},
        }
    return out


def run_coverage(arg):
    """What a dataset holds in each of ``years`` on the model the path runs use: spending and caseloads for the UK
    and for Great Britain, to set against DWP's tables.

    ``arg``: ``years``, ``september_cpi_history`` (for the additional pension), optional ``dataset`` and ``spec``, a
    path. With a path, its calendar growth and statutory inputs are set before the data load and the flat rates and
    the earnings-linked Pension Credit guarantee are the triple lock's on it, as in run_path's triple-lock run; the
    years before the horizon are the model's own on every path. ``demography``: the population treatment, as in the
    path runs (None: config.DEMOGRAPHY).
    """
    from policyengine_uk.utils.scenario import Scenario

    dataset, spec = arg.get("dataset"), arg.get("spec")
    years = sorted(int(y) for y in arg["years"])
    sep_cpi = {int(y): float(v) for y, v in arg["september_cpi_history"].items()}
    if spec is None:
        sim = _managed(dataset)
        path = None
    else:
        parameters = model_parameters()
        base = base_levels(parameters)
        _, earnings, rates = spec_rates(spec)
        levels = {name: rules.level_path(base[name], rates["triple_lock"], HORIZON) for name in base}
        pc_levels = pension_credit_levels(parameters, earnings, spec.get("rate_decimals", CENTRAL_RATE_DECIMALS))
        sim = _managed(dataset, scenario=Scenario(parameter_changes=scenario_changes(spec, parameters),
                                                  applied_before_data_load=True))
        set_flat_rates(sim, levels, pc_levels)
        sep_cpi = {**sep_cpi, **september_cpi(spec)}
        path = {"policy": "triple_lock", "statutory": {"cpi": spec["statutory_cpi"],
                                                       "earnings": spec["statutory_earnings"]}}
    treatment = arg.get("demography") or DEMOGRAPHY
    survey_age = np.asarray(sim.calculate("age", int(min(sim.dataset.years))).to_numpy(), dtype=float)
    pinned, data_year = pinned_inputs(sim, years, sep_cpi, treatment,
                                    retyped_level=arg.get("retyped_level", "kept"))
    pin(sim, pinned)  # as in the path runs
    held = held_pension_types(sim, pinned, years)
    additional_pension_followed(sim, pinned, years)
    accounting = state_pension_accounting(sim, pinned)
    readback = None
    if treatment != "legacy":
        from .demography import readback as population_readback

        readback = population_readback(sim, pinned.treatment, years)
    age = np.asarray(sim.calculate("age", years[0]).to_numpy(), dtype=float)
    by_year = {y: coverage_stats(sim, y) for y in years}
    # A small country component cannot be recovered by subtracting years or
    # UK/GB tables: withhold the whole linked country family when needed.
    country_suppressed = any(row["status"] != "available" for table in by_year.values()
                             for geo in ("uk", "gb") for row in table[geo]["state_pension_by_country"].values())
    if country_suppressed:
        for table in by_year.values():
            for geo in ("uk", "gb"):
                table[geo]["state_pension_by_country"] = {
                    name: {key: "withheld_family" if key == "status" else None for key in row}
                    for name, row in table[geo]["state_pension_by_country"].items()}
    return {
        "dataset": sim.triple_lock_provenance["runtime_dataset"],
        "model": sim.triple_lock_provenance,
        "path": path,
        "data_year": data_year,
        "demography": treatment,
        "ageing": ageing_record(pinned, readback),
        "state_pension_accounting": accounting,
        "by_year": by_year,
        "country_tables_withheld": country_suppressed,
        "held_pension_type_records": {y: held[y]["records"] for y in years},
        "max_age": float(age.max()),
        "survey_max_age": float(survey_age.max()),
        "records": {"households": int(len(sim.calculate("household_weight", years[0]))),
                    "people": int(len(age))},
    }


JOBS = {"path": run_path, "history": run_history, "coverage": run_coverage}


# ── Caching and isolation ────────────────────────────────────────────────


def file_hash(path):
    """sha256 of a file's bytes: provenance, so the results file goes stale on any edit."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _DropBareStrings(ast.NodeTransformer):
    """Remove docstrings and every other statement that is only a string, and the u prefix of string literals: none
    changes what the code computes."""

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)

    def visit_Constant(self, node):
        node.kind = None
        return node


# What in pyproject.toml decides the code a job runs: the dependencies and the Python version. The description,
# version and tool settings do not.
PYPROJECT_FIELDS = ("dependencies", "optional-dependencies", "requires-python")


def source_semantics(path):
    """sha256 of what a source file says, not how it is written.

    Python: the syntax tree (``ast.dump``, no line numbers) without comments,
    docstrings or other statements that are only a string, so an edit to prose
    alone keeps the hash and any change to code, names or values moves it.
    pyproject.toml: its dependencies, optional dependencies, Python version and
    build system (PYPROJECT_FIELDS); other TOML: the parsed document. Dropping docstrings is safe because no module the job
    key covers reads one at run time (tests/test_engine_pure.py checks).
    """
    path = Path(path)
    if path.suffix not in (".py", ".toml"):  # a data file: what it holds is its bytes
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix == ".toml":
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        if path.name == "pyproject.toml":
            doc = {k: doc.get("project", {}).get(k) for k in PYPROJECT_FIELDS} | {"build-system": doc.get("build-system")}
        canonical = json.dumps(doc, sort_keys=True, default=str)
    else:  # bytes, so the source is decoded as Python decodes it (coding cookie, byte-order mark)
        canonical = ast.dump(_DropBareStrings().visit(ast.parse(path.read_bytes(), filename=str(path))))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _engine_files(root=None, pyproject=None):
    here = Path(root) if root is not None else Path(__file__).resolve().parent
    return {**{name: here / name for name in ENGINE_FILES}, **ENGINE_DATA,
            "pyproject.toml": Path(pyproject) if pyproject is not None else REPO / "pyproject.toml"}


def engine_hashes(root=None, pyproject=None):
    """{file: sha256 of its bytes} for the engine files and pyproject.toml: the results file's provenance."""
    return {name: file_hash(path) for name, path in _engine_files(root, pyproject).items()}


def engine_semantics(root=None, pyproject=None):
    """{file: source_semantics} for the engine files and pyproject.toml: what a job's cache key holds for the code."""
    return {name: source_semantics(path) for name, path in _engine_files(root, pyproject).items()}


def package_versions():
    """The installed versions of TRACKED_PACKAGES, and Python's major.minor (a patch release changes no result, and
    nothing pins one: CI's 3.13 need not be the build's)."""
    return {**{name: importlib.metadata.version(name) for name in TRACKED_PACKAGES},
            "python": f"{sys.version_info.major}.{sys.version_info.minor}"}


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


def _job(inp, out):
    """Run one job from its input file into its output file, in the process jobs.run_jobs started for it."""
    from . import model_horizon

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
