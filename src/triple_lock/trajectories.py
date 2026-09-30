"""Trajectory viewer data: the Burnham plan vs the triple lock on a few paths, each a full model run.

Every fiscal and household figure here comes from PolicyEngine UK runs on the
certified data; nothing is scaled from another run.

Horizon
-------
Upratings from April 2027 to April 2039, so the final year is 2039-40, the year
DWP's State Pension uprating analysis (29 September 2026) costs.
TRAJECTORY_HORIZON is this module's own: the main results (config.HORIZON) stop
at 2034-35, and the central path here reproduces them for 2027-28 to 2034-35.

Future paths
------------
* ``central``: the dashboard's central path (OBR March 2026 EFO to 2030,
  PolicyEngine's long-run path after, April 2027 on the published inputs).
* ``monthly_boot_p50`` and ``monthly_boot_p90``: draws from the monthly model
  of the CPI index and average weekly earnings (ts_monthly: a VAR on monthly log
  changes, lag order by BIC, shocks resampled from its residuals). It simulates
  the months from August 2026 to December 2039, so September CPI and May-July
  AWE (the statutory inputs) and the calendar-year measures come from the same
  months. N_DRAWS paths are entropy-tilted so the weighted mean of calendar CPI
  and earnings in each year 2027-2039 equals the central path. For the weighted
  median and 90th percentile of the 2039-40 Burnham gap (rule arithmetic on the
  weekly rate), the candidates are the draws within BAND of that probability;
  the path run is the candidate nearest their weighted centre (each year and
  series standardised by its weighted SD), among those with at least the
  candidates' median weight. The t-copula and Gaussian shock versions are
  reported (``models``) but not run: their tilted draws put more weight on
  deflation, including September CPI below -3%, which the published series has
  never reached (its 1989-2025 low is in ``gap_statistics``); ``models`` records
  the shares, and a test checks the choice against them.
* ``uncertainty_tab_p50`` and ``uncertainty_tab_p90``: the Uncertainty tab's
  representative paths (its draw to 2033, the central path after, since that
  tab's range stops at 2033), with unrounded rates as that tab computes them.

How a path enters the model
---------------------------
Its calendar-year CPI and earnings growth for 2027-2039 replace
``gov.economic_assumptions.yoy_growth.obr`` (RPI and CPIH move by the same
amount as CPI) in a Scenario applied before the data load. Each job first
extends policyengine-uk's derived series to 2042 (model_horizon: without it
benefit rates stop following the path after April 2029). Each run records,
and fails unless, in every year 2027-28 to 2039-40:

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
wealth (GDP per head, household interest income), self-employment income (mixed
income per head), rents, council tax and mortgage interest; from 2031 rents and
council tax also stay at their 2030 amounts, because the survey data are
extended only to 2030. Calendar 2026 growth, which sets April 2027's benefit
uprating, is the model's own on every path. ``not_moving`` records those series
for each path.

The State Pension flat rates are set from each rule applied to the path's
statutory inputs (September CPI, May-July AWE; rates to 3 dp, except the
Uncertainty tab's paths). The additional State Pension is pinned to the
unreformed model on the same path, so it follows the model's own triple lock on
the calendar measures, not CPI as in law; it is the same in both runs. A
Scenario simulation builds a second, default-path simulation as its
``baseline``; every run here drops it before calculating, so no variable
compares against it (employer NI incidence would), and records that employer
NI incidence is zero.

Past years
----------
What the Burnham plan would have paid had it started in an earlier April, on the
published September CPI and May-July earnings (ONS, latest vintage; April 2022's
earnings leg was suspended, so both rules use CPI that year). Counterfactual
flat rate = actual flat rate x (Burnham index / triple-lock replay index).
Fiscal and household effects for 2024-25 to 2026-27, the years the survey data
cover, come from full runs. policyengine-uk pays each person the share of the
flat rate their survey-year (2024-25) pension is of that year's flat rate; the
counterfactual runs keep that denominator at actual law (a formula override), so
every basic and new State Pension scales by the level ratio, which each run
checks person by person.

Run: ``python -m triple_lock.trajectories`` (needs managed-data access and a
clean git tree, or ``--allow-dirty``; each model run happens in its own process
and working directory).
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import rules
from .config import (
    ACTUALS_CSV,
    AWE_CSV,
    BASE_YEAR,
    CENTRAL_FORECAST_CSV,
    CENTRAL_RATE_DECIMALS,
    CPI_CSV,
    CROSSCHECK_CSV,
    ERROR_CSV,
    HORIZON as MAIN_HORIZON,
    MODEL_TRIPLE_LOCK_PARAMETER,
    OUTPUT,
    REPO,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)

TRAJECTORY_OUTPUT = REPO / "data" / "trajectory_results.json"
TRAJECTORY_DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "trajectory_results.json"
POLICIES = ["triple_lock", "burnham_2030"]

# April 2027 to April 2039 upratings: fiscal years 2027-28 to 2039-40.
TRAJECTORY_HORIZON = list(range(2027, 2040))
TRAJECTORY_FINAL_YEAR = TRAJECTORY_HORIZON[-1]
# Statutory inputs (September CPI, May-July AWE) that set each April's rise: 2026-2038.
STATUTORY_YEARS = [y - 1 for y in TRAJECTORY_HORIZON]
# Calendar-year growth each path sets in the model: 2027-2039. policyengine-uk
# uprates incomes and CPI-indexed thresholds in fiscal year y by calendar-year y
# growth, so 2039-40 needs calendar 2039.
CALENDAR_YEARS = list(range(BASE_YEAR + 1, TRAJECTORY_FINAL_YEAR + 1))
MONTHLY_YEARS = [BASE_YEAR, *CALENDAR_YEARS]  # what the monthly model builds: 2026-2039

N_DRAWS = 50_000
SEED = 20260929
QUANTILES = (0.5, 0.9)
BAND = 0.025  # candidates: draws whose weighted CDF position is within 2.5 points of the quantile
# (shock kind, label, whether its paths go through the model). Only the bootstrap
# model's paths are run: with the t-copula (marginal df bounded at 4) and
# Gaussian shocks the tilted draws put more weight on deflation, including
# September CPI below -3%, which the published series has never reached;
# ``models[...]["september_cpi_below"]`` records the shares and
# test_trajectories checks the choice against them.
MODEL_METHODS = {
    "monthly_boot": ("boot", "Monthly model", True),
    "monthly_tcop": ("tcop", "Monthly model, t-copula shocks", False),
    "monthly_gauss": ("gauss", "Monthly model, Gaussian shocks", False),
}
DEFLATION_THRESHOLDS = {"-1%": -0.01, "-3%": -0.03}
OBR = "gov.economic_assumptions.yoy_growth.obr"
MOVE_WITH_CPI = ["rpi", "cpih"]
BN = 1e9
HISTORY_YEARS = list(range(2011, BASE_YEAR + 1))  # April upratings with published inputs
HISTORY_SWITCH_YEARS = list(range(2012, BASE_YEAR + 1))
HISTORY_MODEL_YEARS = [2024, 2025, 2026]
SUSPENDED_EARNINGS_YEAR = 2022
FLAT_RATE = {
    "new_state_pension": "gov.dwp.state_pension.new_state_pension.amount",
    "basic_state_pension": "gov.dwp.state_pension.basic_state_pension.amount",
}
# Parameters whose growth each forward run checks against the path: (path, calendar series, lag in years).
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
HASHED = ["trajectories.py", "model_horizon.py", "ts_methods.py", "ts_monthly.py", "ts_backtest.py", "rules.py",
          "config.py", "pipeline.py", "breakdowns.py", "provenance.py", "var_check.py", "uncertainty.py"]


class PathNotFollowed(RuntimeError):
    """A model series did not follow the path in some year: the result would not be a run of that path."""


class SourceChanged(RuntimeError):
    """Code or inputs changed between the start of the build and a job or the end of the build."""


# ── Which input set each year's rise ─────────────────────────────────────


def rate_sources(cpi, earnings, rates, years, decimals=CENTRAL_RATE_DECIMALS):
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
            out["burnham_2030"][y] = "triple_lock"
            continue
        floor = max(c, TRIPLE_LOCK_FLOOR)
        floor = round(floor, decimals) if decimals is not None else floor
        if rates["burnham_2030"][y] > floor + 1e-12:
            out["burnham_2030"][y] = "earnings_path"
        else:
            out["burnham_2030"][y] = "cpi" if c >= TRIPLE_LOCK_FLOOR else "floor"
    return out


# ── Future paths ─────────────────────────────────────────────────────────


def weighted_quantile(x, w, q):
    order = np.argsort(x)
    cw = np.cumsum(w[order])
    return float(x[order][np.searchsorted(cw, q * cw[-1])])


def weighted_cdf_position(x, w):
    """Each draw's mid-point position in the weighted distribution of x, in (0, 1); ties share a position."""
    values, inverse = np.unique(x, return_inverse=True)
    tie_weight = np.bincount(inverse, weights=w)
    below = np.concatenate([[0.0], np.cumsum(tie_weight)[:-1]])
    return (below + tie_weight / 2)[inverse] / w.sum()


def burnham_gap(cpi, earnings, base_new_sp, decimals=CENTRAL_RATE_DECIMALS):
    """Full new State Pension, £/week in the final year: triple lock minus Burnham plan, per draw.

    ``cpi`` and ``earnings`` are (n, len(STATUTORY_YEARS)) statutory inputs for growth years 2026-2038.
    """
    level = {
        p: base_new_sp * np.prod(1 + rules.rates_matrix(p, cpi, earnings, TRAJECTORY_HORIZON, decimals), axis=1)
        for p in POLICIES
    }
    return level["triple_lock"] - level["burnham_2030"]


def select_draws(paths, weights, gap, quantiles=QUANTILES, band=BAND):
    """A representative draw near each weighted quantile of the gap.

    Candidates: draws whose weighted CDF position in the gap is within ``band`` of
    the quantile; of those with at least the candidates' median weight, the pick
    is the one nearest (mean squared distance, each year and series standardised
    by its weighted SD over all draws) to the candidates' weighted mean path.
    Raises if the band holds no draw.
    """
    n = len(paths)
    flat = paths.reshape(n, -1)
    mean = weights @ flat
    sd = np.sqrt(weights @ (flat - mean) ** 2)
    z = (flat - mean) / np.where(sd > 0, sd, 1.0)
    pos = weighted_cdf_position(gap, weights)
    picks = []
    for q in quantiles:
        target = weighted_quantile(gap, weights, q)
        cand = np.where(np.abs(pos - q) <= band)[0]
        if not len(cand):
            raise ValueError(f"no draw within {band} of the {q} quantile of the gap")
        wc = weights[cand]
        centre = wc @ z[cand] / wc.sum()
        eligible = cand[wc >= np.median(wc)]
        dist = ((z[eligible] - centre) ** 2).mean(axis=1)
        pick = int(eligible[np.argmin(dist)])
        picks.append({"quantile": q, "draw": pick, "quantile_gap_gbp_week": round(target, 2),
                      "gap_gbp_week": round(float(gap[pick]), 2), "cdf_position": round(float(pos[pick]), 4),
                      "band": band, "n_candidates": int(len(cand)),
                      "candidates_effective_sample": round(float(wc.sum() ** 2 / (wc ** 2).sum()), 1)})
    return picks


def switches_per_year(stat_cpi, stat_earnings, w=None):
    from .ts_backtest import switches

    s = switches(np.stack([stat_cpi, stat_earnings], axis=2))
    per_path = s / (stat_cpi.shape[1] - 1)
    return float(per_path.mean() if w is None else w @ per_path)


def model_summary(m, weights, tinfo, gap, info, label, runs_paths):
    """What the ``models`` block reports for one monthly-model variant."""
    stat_cpi = m["statutory_cpi"][:, :-1]  # Septembers 2026-2038
    stat_earn = m["statutory_earnings"][:, :-1]
    below = {}
    for name, threshold in DEFLATION_THRESHOLDS.items():
        hit = stat_cpi < threshold
        below[name] = {"path_years": round(float(weights @ hit.mean(axis=1)), 4),
                       "paths": round(float(weights @ hit.any(axis=1)), 4),
                       "path_years_unweighted": round(float(hit.mean()), 4)}
    return {
        "label": label,
        "runs_paths": runs_paths,
        **info,
        "n_draws": N_DRAWS,
        "tilt_effective_sample": round(tinfo["ess"]),
        "tilt_max_abs_mean_error": tinfo["max_abs_mean_error"],
        "gap_gbp_week": {f"p{int(100 * q)}": round(weighted_quantile(gap, weights, q), 2)
                         for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "gap_zero_share": round(float(weights @ (np.abs(gap) < 0.005)), 3),
        "gap_negative_share": round(float(weights @ (gap <= -0.005)), 3),
        "september_2026_cpi": {f"p{int(100 * q)}": round(weighted_quantile(m["statutory_cpi"][:, 0], weights, q), 4)
                               for q in (0.1, 0.5, 0.9)},
        "september_cpi_below": below,
        "september_cpi_years": [STATUTORY_YEARS[0], STATUTORY_YEARS[-1]],
        "may_july_earnings_range": {
            "min": round(float(stat_earn.min()), 4), "max": round(float(stat_earn.max()), 4),
            **{f"p{q}": round(float(np.percentile(stat_earn, q)), 4) for q in (1, 99)},
        },
        "switches_per_year": {
            "statutory_2026_2038": {"tilted": round(switches_per_year(stat_cpi, stat_earn, weights), 3),
                                    "untilted": round(switches_per_year(stat_cpi, stat_earn), 3)},
            "calendar_2027_2039": {
                "tilted": round(switches_per_year(m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:], weights), 3),
                "untilted": round(switches_per_year(m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:]), 3)},
        },
    }


def forward_specs(central_cpi, central_earnings, base_new_sp, main_results):
    """Every future trajectory, plus the monthly-model diagnostics.

    ``central_cpi``/``central_earnings``: {calendar year: growth} for 2026-2039,
    2026 holding the April 2027 statutory inputs. Each spec carries calendar
    growth for 2027-2039 (the model's economic assumptions) and statutory
    inputs for 2026-2038 (the rule).
    """
    from . import ts_monthly
    from .ts_methods import tilt

    target = np.array([[central_cpi[y], central_earnings[y]] for y in CALENDAR_YEARS])
    specs = [{
        "id": "central",
        "label": "Central forecast",
        "source": "The dashboard's central path: OBR March 2026 forecast to 2030, PolicyEngine's long-run path "
                  "after; its calendar values also serve as the statutory inputs (April 2027: published inputs)",
        "rate_decimals": CENTRAL_RATE_DECIMALS,
        "cpi": {y: central_cpi[y] for y in CALENDAR_YEARS},
        "earnings": {y: central_earnings[y] for y in CALENDAR_YEARS},
        "statutory_cpi": {y: central_cpi[y] for y in STATUTORY_YEARS},
        "statutory_earnings": {y: central_earnings[y] for y in STATUTORY_YEARS},
    }]
    models = {}
    for method, (kind, label, run_paths) in MODEL_METHODS.items():
        m, info = ts_monthly.paths(MONTHLY_YEARS, N_DRAWS, SEED, kind)
        cal = np.stack([m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:]], axis=2)
        weights, tinfo = tilt(cal, target)
        stat_cpi, stat_earn = m["statutory_cpi"][:, :-1], m["statutory_earnings"][:, :-1]
        gap = burnham_gap(stat_cpi, stat_earn, base_new_sp)
        models[method] = model_summary(m, weights, tinfo, gap, info, label, run_paths)
        if not run_paths:
            continue
        picks = select_draws(np.stack([stat_cpi, stat_earn], axis=2), weights, gap)
        models[method]["selections"] = picks
        for pick in picks:
            p, d = int(100 * pick["quantile"]), pick["draw"]
            specs.append({
                "id": f"{method}_p{p}",
                "label": f"{label}: {'middle' if p == 50 else f'{p}th percentile'}",
                "source": (f"Draw {d:,} of {N_DRAWS:,}: of the draws whose 2039-40 Burnham gap is near the model's "
                           f"weighted {p}th percentile (£{pick['quantile_gap_gbp_week']:.2f} a week), the one closest "
                           "to their average path"),
                "selection": pick,
                "rate_decimals": CENTRAL_RATE_DECIMALS,
                "cpi": {y: float(m["calendar_cpi"][d, j + 1]) for j, y in enumerate(CALENDAR_YEARS)},
                "earnings": {y: float(m["calendar_earnings"][d, j + 1]) for j, y in enumerate(CALENDAR_YEARS)},
                "statutory_cpi": {y: float(stat_cpi[d, j]) for j, y in enumerate(STATUTORY_YEARS)},
                "statutory_earnings": {y: float(stat_earn[d, j]) for j, y in enumerate(STATUTORY_YEARS)},
            })
    for q in ("p50", "p90"):
        rep = main_results["uncertainty"]["representative_paths"][q]
        last = max(int(k) for k in rep["cpi"])

        def extend(series, central, years):
            return {y: float(rep[series][str(y)]) if y <= last else float(central[y]) for y in years}

        specs.append({
            "id": f"uncertainty_tab_{q}",
            "label": f"Uncertainty tab: {'middle' if q == 'p50' else '90th percentile'} path",
            "source": (f"The Uncertainty tab's representative {q} path (draw {rep['draw']} of its block bootstrap of "
                       f"OBR forecast errors and statutory gaps) to {last}, the central path after; here applied to "
                       "the whole model. Rates are unrounded, as on that tab"),
            "rate_decimals": None,
            "uncertainty_tab_last_year": last,
            "cpi": extend("cpi", central_cpi, CALENDAR_YEARS),
            "earnings": extend("earnings", central_earnings, CALENDAR_YEARS),
            "statutory_cpi": extend("cpi", central_cpi, STATUTORY_YEARS),
            "statutory_earnings": extend("earnings", central_earnings, STATUTORY_YEARS),
        })
    return specs, models


def _econ_changes(spec, parameters):
    obr = parameters.get_child(OBR)
    cpi_node = obr.get_child("consumer_price_index")
    changes = {
        f"{OBR}.consumer_price_index": {f"year:{y}-01-01:1": float(spec["cpi"][y]) for y in CALENDAR_YEARS},
        f"{OBR}.average_earnings": {f"year:{y}-01-01:1": float(spec["earnings"][y]) for y in CALENDAR_YEARS},
    }
    for series in MOVE_WITH_CPI:
        node = obr.get_child(series)
        changes[f"{OBR}.{series}"] = {
            f"year:{y}-01-01:1": float(node(f"{y}-01-01")) + float(spec["cpi"][y]) - float(cpi_node(f"{y}-01-01"))
            for y in CALENDAR_YEARS
        }
    return changes


def _totals(sim, years):
    from .pipeline import FISCAL_COMPONENTS

    out = {}
    for y in years:
        t = {name: sum(float(sim.calculate(v, y, map_to="household").sum()) for v in vs) / BN
             for name, vs in FISCAL_COMPONENTS.items()}
        t["gov_balance"] = float(sim.calculate("gov_balance", y, map_to="household").sum()) / BN
        t["household_net_income"] = float(sim.calculate("household_net_income", y).sum()) / BN
        out[y] = t
    return out


def _set_flat_rates(sim, levels):
    from policyengine_uk.utils.scenario import Scenario

    from .pipeline import flat_rate_reform

    Scenario.from_reform(flat_rate_reform(levels)).simulation_modifier(sim)
    sim.tax_benefit_system.reset_parameter_caches()


def _pin(sim, pinned):
    for v, by_year in pinned.items():
        for y, values in by_year.items():
            sim.set_input(v, y, values)


def _unweighted_total(sim, variable, year):
    """Sum over the variable's own entity, unweighted: its growth is the uprating applied, whatever the weights do."""
    return float(np.asarray(sim.calculate(variable, year).values, dtype=float).sum())


def _growth(level, years):
    return {y: level[y] / level[y - 1] - 1 if level[y - 1] else None for y in years}


def path_following(sim, calendar):
    """Growth of model series the path must drive, in every horizon year, against what the path says.

    ``calendar``: {"cpi"|"earnings": {calendar year: growth}} for 2026-2039 as the
    model received them. Raises PathNotFollowed if any series misses.
    """
    p = sim.tax_benefit_system.parameters
    years = [BASE_YEAR, *TRAJECTORY_HORIZON]
    out, failures = {}, []

    def record(name, growth, expected, tol, **extra):
        err = max(abs(growth[y] - expected[y]) for y in TRAJECTORY_HORIZON)
        out[name] = {**extra, "growth": growth, "expected": expected, "max_abs_error": err}
        if not err <= tol:
            failures.append(f"{name}: off by {err:.2e}")

    for name, (path, series, lag) in PATH_PARAMETERS.items():
        level = {y: float(p.get_child(path)(f"{y}-06-01")) for y in years}
        record(name, _growth(level, TRAJECTORY_HORIZON), {y: calendar[series][y - lag] for y in TRAJECTORY_HORIZON},
               PATH_GROWTH_TOL, parameter=path,
               follows=f"calendar {'CPI' if series == 'cpi' else 'earnings'} growth "
                       f"{'the year before' if lag else 'the same year'}")
    employment = {y: _unweighted_total(sim, "employment_income_before_lsr", y) for y in years}
    record("employment_income", _growth(employment, TRAJECTORY_HORIZON),
           {y: calendar["earnings"][y] for y in TRAJECTORY_HORIZON}, PATH_GROWTH_TOL,
           variable="employment_income_before_lsr", follows="calendar earnings growth the same year (unweighted total)")
    model_tl = {y: float(p.get_child(MODEL_TRIPLE_LOCK_PARAMETER)(f"{y}-06-01")) for y in TRAJECTORY_HORIZON}
    expected_tl = {y: round(max(calendar["earnings"][y - 1], calendar["cpi"][y - 1], TRIPLE_LOCK_FLOOR), 3)
                   for y in TRAJECTORY_HORIZON}
    tl_err = max(abs(model_tl[y] - expected_tl[y]) for y in TRAJECTORY_HORIZON)
    out["model_triple_lock"] = {"parameter": MODEL_TRIPLE_LOCK_PARAMETER, "rate": model_tl, "expected": expected_tl,
                                "max_abs_error": tl_err}
    if not tl_err <= 1e-12:
        failures.append(f"model_triple_lock: off by {tl_err:.2e}")
    nsp = {y: float(p.get_child(FLAT_RATE["new_state_pension"])(f"{y}-06-01")) for y in years}
    expected_nsp = rules.level_path(nsp[BASE_YEAR], model_tl, TRAJECTORY_HORIZON)
    nsp_err = max(abs(nsp[y] / expected_nsp[y] - 1) for y in TRAJECTORY_HORIZON)
    out["model_new_state_pension"] = {"weekly": nsp, "expected": expected_nsp, "max_rel_error": nsp_err}
    if not nsp_err <= MODEL_AMOUNT_REL_TOL:
        failures.append(f"model_new_state_pension: off by {nsp_err:.2e}")
    if failures:
        raise PathNotFollowed("; ".join(failures))
    return out


def run_forward(spec):
    """Full model runs of one future path: unreformed, triple lock and Burnham plan."""
    from policyengine.tax_benefit_models.uk import managed_microsimulation
    from policyengine_uk.utils.scenario import Scenario

    from .breakdowns import BREAKDOWNS, breakdown, household_frame, households_affected
    from .pipeline import PINNED_VARIABLES, base_levels, household_groups

    final = TRAJECTORY_FINAL_YEAR
    reference = managed_microsimulation()
    reference.baseline = None
    parameters = reference.tax_benefit_system.parameters
    bundle = reference.policyengine_bundle
    base = base_levels(parameters)
    changes = _econ_changes(spec, parameters)
    model_2026 = {s: float(parameters.get_child(f"{OBR}.{name}")(f"{BASE_YEAR}-01-01"))
                  for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))}
    del reference

    cpi = {y: float(spec["statutory_cpi"][y]) for y in STATUTORY_YEARS}
    earnings = {y: float(spec["statutory_earnings"][y]) for y in STATUTORY_YEARS}
    decimals = spec["rate_decimals"]
    rates = {p: rules.uprating_path(p, cpi, earnings, TRAJECTORY_HORIZON, decimals=decimals) for p in POLICIES}
    levels = {p: {name: rules.level_path(base[name], rates[p], TRAJECTORY_HORIZON) for name in base} for p in POLICIES}

    def build():
        sim = managed_microsimulation(scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))
        sim.baseline = None  # the scenario's default-path comparator; nothing may compare against it
        return sim

    unreformed = build()
    p = unreformed.tax_benefit_system.parameters
    applied_growth = {
        s: {y: float(p.get_child(f"{OBR}.{name}")(f"{y}-01-01")) for y in [BASE_YEAR, *CALENDAR_YEARS]}
        for s, name in (("cpi", "consumer_price_index"), ("earnings", "average_earnings"))
    }
    calendar = {s: {BASE_YEAR: model_2026[s], **{y: float(spec[s][y]) for y in CALENDAR_YEARS}}
                for s in ("cpi", "earnings")}
    following = path_following(unreformed, calendar)
    other_series = {}
    for group, variables in (("not_moving", NOT_MOVING), ("also_moving", ALSO_MOVING)):
        other_series[group] = {
            v: _growth({y: _unweighted_total(unreformed, v, y) for y in [BASE_YEAR, *TRAJECTORY_HORIZON]},
                       TRAJECTORY_HORIZON)
            for v in variables
        }
    pinned = {v: {y: unreformed.calculate(v, y).to_numpy() for y in TRAJECTORY_HORIZON} for v in PINNED_VARIABLES}
    del unreformed

    totals, income, groups, applied_weekly, hh, flat, employer_ni = {}, {}, None, {}, {}, {}, {}
    yearly_income, household_ids = {}, None
    for policy in POLICIES:
        sim = build()
        _set_flat_rates(sim, levels[policy])
        _pin(sim, pinned)
        totals[policy] = _totals(sim, TRAJECTORY_HORIZON)
        income[policy] = sim.calculate("household_net_income", final)
        yearly_income[policy] = {y: sim.calculate("household_net_income", y) for y in TRAJECTORY_HORIZON}
        hh[policy] = {v: sim.calculate(v, final, map_to="household").to_numpy()
                      for v in ("household_id", *LARGEST_HOUSEHOLD_VARIABLES)}
        flat[policy] = {y: {n: sim.calculate(n, y).to_numpy().astype(float) for n in FLAT_RATE}
                        for y in TRAJECTORY_HORIZON}
        employer_ni[policy] = float(sim.calculate("employer_ni_fixed_employer_cost_change", final, map_to="household").sum()) / BN
        if groups is None:
            groups = household_groups(sim, final)
            household_ids = sim.calculate("household_id", final).to_numpy()
        applied_weekly[policy] = {y: float(sim.tax_benefit_system.parameters.get_child(FLAT_RATE["new_state_pension"])(
            f"{y}-06-01")) for y in TRAJECTORY_HORIZON}
        del sim

    # Every flat-rate pension scales by the ratio of the two rules' amounts (no data-year denominator moves).
    proportionality = max(
        float(np.abs(flat["burnham_2030"][y][n] - flat["triple_lock"][y][n]
                     * levels["burnham_2030"][n][y] / levels["triple_lock"][n][y]).max())
        for y in TRAJECTORY_HORIZON for n in FLAT_RATE
    )
    if not proportionality <= PROPORTIONALITY_TOL_GBP:
        raise PathNotFollowed(f"flat-rate pensions are not proportional to the flat rates: off by £{proportionality:.4f}")
    if any(abs(v) > 1e-12 for v in employer_ni.values()):
        raise PathNotFollowed(f"employer NI incidence is not zero: {employer_ni}")

    # For every year, the single household record that moves that year's net figure most.
    concentration = {}
    for y in TRAJECTORY_HORIZON:
        w_y = yearly_income["triple_lock"][y].weights.to_numpy()
        contrib = (yearly_income["burnham_2030"][y].to_numpy() - yearly_income["triple_lock"][y].to_numpy()) * w_y / BN
        k = int(np.argmax(np.abs(contrib)))
        total = float(contrib.sum())
        concentration[y] = {"household_id": int(household_ids[k]), "weight": float(w_y[k]),
                            "contribution_bn": float(contrib[k]),
                            "share_of_income_change": float(contrib[k] / total) if total else 0.0}

    tl, bp = totals["triple_lock"], totals["burnham_2030"]
    change = income["burnham_2030"] - income["triple_lock"]
    frame = household_frame(change, income["triple_lock"], groups)
    # The single household record that moves the final-year net figure most:
    # arithmetic on this run's own output (a decomposition), not an estimate.
    weight = income["triple_lock"].weights.to_numpy()
    contribution = change.to_numpy() * weight / BN
    i = int(np.argmax(np.abs(contribution)))
    net_final = float(contribution.sum())
    flat_hh = {pol: hh[pol]["basic_state_pension"] + hh[pol]["new_state_pension"] for pol in POLICIES}
    largest = {
        "household_id": int(hh["triple_lock"]["household_id"][i]),
        "weight": float(weight[i]),
        "income_change_gbp": float(change.to_numpy()[i]),
        "contribution_bn": float(contribution[i]),
        "share_of_income_change": float(contribution[i] / net_final) if net_final else 0.0,
        "income_change_excluding_bn": float(net_final - contribution[i]),
        "gross_contribution_bn": float((flat_hh["triple_lock"][i] - flat_hh["burnham_2030"][i]) * weight[i] / BN),
        "change_gbp": {v: float(hh["burnham_2030"][v][i] - hh["triple_lock"][v][i])
                       for v in ("housing_benefit", "pension_credit", "state_pension")},
        "amounts_gbp": {pol: {v: float(hh[pol][v][i]) for v in ("housing_benefit", "pension_credit", "state_pension")}
                        for pol in POLICIES},
        "median_weight": float(np.median(weight)),
    }
    return {
        "rate_decimals": decimals,
        "statutory": {"cpi": cpi, "earnings": earnings},
        "calendar": {s: {y: float(spec[s][y]) for y in CALENDAR_YEARS} for s in ("cpi", "earnings")},
        "applied_growth": applied_growth,
        "path_following": following,
        **other_series,
        "rates": rates,
        "rate_sources": rate_sources(cpi, earnings, rates, TRAJECTORY_HORIZON, decimals),
        "weekly": levels,
        "applied_new_state_pension": applied_weekly,
        "saving_bn": {
            y: {
                "gross": tl[y]["state_pension_flat_rate"] - bp[y]["state_pension_flat_rate"],
                "net": bp[y]["gov_balance"] - tl[y]["gov_balance"],
                "household_income_change": bp[y]["household_net_income"] - tl[y]["household_net_income"],
                "components": {k: bp[y][k] - tl[y][k] for k in tl[y] if k not in ("gov_balance", "household_net_income")},
            }
            for y in TRAJECTORY_HORIZON
        },
        "totals_bn": totals,
        "by_decile": breakdown(frame, *BREAKDOWNS["by_decile"]),
        "households_affected": households_affected(change),
        "largest_household": largest,
        "concentration_by_year": concentration,
        "checks": {"max_proportionality_error_gbp": proportionality, "employer_ni_incidence_bn": employer_ni},
        "bundle": {k: bundle[k] for k in ("bundle_id", "policyengine_version", "model_version", "runtime_dataset",
                                           "runtime_dataset_uri", "certified_data_build_id")},
    }


# ── Past years ───────────────────────────────────────────────────────────


def history_inputs(path=ACTUALS_CSV):
    """{year: cpi}, {year: earnings} for April upratings 2011-2026, earnings suspended in 2022."""
    with Path(path).open(newline="") as f:
        rows = {int(r["uprating_april"]): r for r in csv.DictReader(f)}
    cpi = {y: float(rows[y]["cpi_september_12m"]) for y in HISTORY_YEARS}
    earnings = {y: float(rows[y]["awe_total_pay_may_jul_3m_yoy"]) for y in HISTORY_YEARS}
    earnings[SUSPENDED_EARNINGS_YEAR] = cpi[SUSPENDED_EARNINGS_YEAR]
    return cpi, earnings


def history_counterfactual(switch_year, cpi, earnings):
    """Rates and the Burnham / triple-lock level ratio had the plan started in April ``switch_year``."""
    c = np.array([cpi[y] for y in HISTORY_YEARS])
    e = np.array([earnings[y] for y in HISTORY_YEARS])
    tl = rules.rates_matrix("triple_lock", c, e)[0]
    previous = rules.SWITCH_YEAR
    rules.SWITCH_YEAR = switch_year
    try:
        bp = rules.rates_matrix("burnham_2030", c, e, HISTORY_YEARS)[0]
    finally:
        rules.SWITCH_YEAR = previous
    ratio = np.cumprod(1 + bp) / np.cumprod(1 + tl)
    return {
        "triple_lock_rate": dict(zip(HISTORY_YEARS, tl.tolist())),
        "burnham_rate": dict(zip(HISTORY_YEARS, bp.tolist())),
        "level_ratio": dict(zip(HISTORY_YEARS, ratio.tolist())),
    }


def history_groups(cpi, earnings):
    """Switch years grouped by identical counterfactual paths."""
    groups = []
    for s in HISTORY_SWITCH_YEARS:
        cf = history_counterfactual(s, cpi, earnings)
        ratio = np.array(list(cf["level_ratio"].values()))
        for g in groups:
            if np.allclose(g["_ratio"], ratio, rtol=0, atol=1e-12):
                g["switch_years"].append(s)
                break
        else:
            groups.append({"switch_years": [s], **cf, "_ratio": ratio})
    for g in groups:
        g["changes_anything"] = bool(np.abs(g.pop("_ratio") - 1).max() > 1e-12)
    return groups


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


def run_history(switch_year):
    """Full model runs for 2024-25..2026-27: actual law vs flat rates had the plan started in ``switch_year``."""
    from policyengine.tax_benefit_models.uk import managed_microsimulation

    from .pipeline import PINNED_VARIABLES

    cpi, earnings = history_inputs()
    cf = history_counterfactual(switch_year, cpi, earnings)
    base = managed_microsimulation()
    base.baseline = None
    p = base.tax_benefit_system.parameters
    data_year = int(min(base.dataset.years))
    actual = {n: {y: float(p.get_child(path)(f"{y}-06-01")) for y in HISTORY_MODEL_YEARS} for n, path in FLAT_RATE.items()}
    denominators = {n: float(p.get_child(path)(f"{data_year}-06-01")) for n, path in FLAT_RATE.items()}
    levels = {n: {y: actual[n][y] * cf["level_ratio"][y] for y in HISTORY_MODEL_YEARS} for n in FLAT_RATE}
    pinned = {v: {y: base.calculate(v, y).to_numpy() for y in HISTORY_MODEL_YEARS} for v in PINNED_VARIABLES}
    base_totals = _totals(base, HISTORY_MODEL_YEARS)
    base_flat = {y: {n: base.calculate(n, y).to_numpy().astype(float) for n in FLAT_RATE} for y in HISTORY_MODEL_YEARS}
    last = HISTORY_MODEL_YEARS[-1]
    base_income = base.calculate("household_net_income", last).to_numpy()
    weight = base.calculate("household_weight", last).to_numpy()
    del base
    sim = managed_microsimulation()
    sim.baseline = None
    if int(min(sim.dataset.years)) != data_year:
        raise RuntimeError("the counterfactual simulation has a different survey year")
    sim.apply_reform(actual_law_denominators(denominators, data_year))
    _set_flat_rates(sim, levels)
    _pin(sim, pinned)
    applied = {y: float(sim.tax_benefit_system.parameters.get_child(FLAT_RATE["new_state_pension"])(f"{y}-06-01"))
               for y in HISTORY_MODEL_YEARS}
    totals = _totals(sim, HISTORY_MODEL_YEARS)
    proportionality = max(
        float(np.abs(sim.calculate(n, y).to_numpy().astype(float) - base_flat[y][n] * cf["level_ratio"][y]).max())
        for y in HISTORY_MODEL_YEARS for n in FLAT_RATE
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
                "gross": base_totals[y]["state_pension_flat_rate"] - totals[y]["state_pension_flat_rate"],
                "net": totals[y]["gov_balance"] - base_totals[y]["gov_balance"],
                "components": {k: totals[y][k] - base_totals[y][k] for k in base_totals[y]
                               if k not in ("gov_balance", "household_net_income")},
            }
            for y in HISTORY_MODEL_YEARS
        },
        "households_losing_pct": float(100 * (weight * (change < -1)).sum() / weight.sum()),
    }


# ── Observed gap statistics ──────────────────────────────────────────────


def _gap_stats(cpi, earnings, years, what):
    g = np.array([earnings[y] - cpi[y] for y in years])
    from .ts_backtest import switches

    n = int(switches(np.stack([np.array([cpi[y] for y in years]), np.array([earnings[y] for y in years])],
                              axis=1)[None])[0])
    return {"series": what, "years": [years[0], years[-1]], "lag1_correlation": round(float(np.corrcoef(g[1:], g[:-1])[0, 1]), 3),
            "switches": n, "pairs": len(years) - 1, "switches_per_year": round(n / (len(years) - 1), 3)}


def gap_statistics():
    """Observed year-to-year behaviour of the earnings-CPI gap, on stated windows and data."""
    from . import ts_monthly
    from .ts_backtest import statutory_outturns
    from .var_check import history

    out = {}
    determination = list(range(HISTORY_YEARS[0] - 1, HISTORY_YEARS[-1]))  # 2010-2025: April 2011-2026
    for treatment in ("published", "suspended"):
        o = statutory_outturns(suspend_2022=treatment == "suspended")
        out[f"statutory_upratings_{HISTORY_YEARS[0]}_{HISTORY_YEARS[-1]}_{treatment}_2022"] = _gap_stats(
            {y: o[y][0] for y in determination}, {y: o[y][1] for y in determination}, determination,
            f"September CPI and May-July AWE setting the April {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]} upratings "
            f"(published inputs file; April 2022 earnings {treatment})")
    for first in (determination[0], 1989):
        hy, h = history(first_year=first, last_year=determination[-1])
        cal_cpi = {int(y): float(h[i, 0]) for i, y in enumerate(hy)}
        cal_earn = {int(y): float(h[i, 1]) for i, y in enumerate(hy)}
        out[f"calendar_{first}_{determination[-1]}"] = _gap_stats(
            cal_cpi, cal_earn, sorted(cal_cpi), "calendar-year CPI and OBR-definition average earnings")
    months, cpi, awe, _ = ts_monthly.levels()
    years = list(range(2001, determination[-1] + 1))
    m = ts_monthly.annual_measures(months, cpi[None], awe[None], years)
    out[f"monthly_statutory_{years[0]}_{years[-1]}"] = _gap_stats(
        dict(zip(years, m["statutory_cpi"][0])), dict(zip(years, m["statutory_earnings"][0])), years,
        "September CPI and May-July AWE built from the monthly data the monthly model is fitted on (raw 2021 earnings)")
    with CPI_CSV.open(newline="") as f:
        rows = [r for r in csv.reader(f) if len(r) > 1 and r[0].endswith(" SEP") and r[0][:4].isdigit()]
    sep = {int(r[0][:4]): float(r[1]) / 100 for r in rows if 1989 <= int(r[0][:4]) <= determination[-1]}
    low = min(sep, key=sep.get)
    out["lowest_september_cpi"] = {"years": [min(sep), max(sep)], "year": low, "rate": sep[low],
                                   "source": "ONS D7G7, CPI 12-month rate"}
    return out


# ── Provenance ───────────────────────────────────────────────────────────


def trajectory_source_hashes():
    from .provenance import file_hash

    here = Path(__file__).resolve().parent
    hashes = {name: file_hash(here / name) for name in HASHED}
    hashes["pyproject.toml"] = file_hash(REPO / "pyproject.toml")
    return hashes


def input_files():
    from .ts_monthly import AWE_LEVEL_CSV, CPI_INDEX_CSV
    from .var_check import SERIES

    return [OUTPUT, ACTUALS_CSV, ERROR_CSV, AWE_CSV, CPI_CSV, CENTRAL_FORECAST_CSV, CROSSCHECK_CSV,
            CPI_INDEX_CSV, AWE_LEVEL_CSV, *(path for path, _ in SERIES.values())]


def input_hashes():
    from .provenance import file_hash

    return {str(Path(p).relative_to(REPO)): file_hash(p) for p in input_files()}


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def snapshot():
    """What the build is about to run: revision, dirty flag, source and input hashes, time."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_revision": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "source_hashes": trajectory_source_hashes(),
        "input_hashes": input_hashes(),
    }


def check_unchanged(start, where):
    now = {"source_hashes": trajectory_source_hashes(), "input_hashes": input_hashes()}
    changed = [k for block in now for k in now[block] if start[block].get(k) != now[block][k]]
    if changed:
        raise SourceChanged(f"{changed} changed between the start of the build and {where}")


# ── Orchestration ────────────────────────────────────────────────────────


def _run_isolated(kind, arg, workdir, start):
    """Run one model job in its own process and working directory (the dataset lands in ./data)."""
    workdir.mkdir(parents=True, exist_ok=True)
    inp, out = workdir / "input.json", workdir / "output.json"
    inp.write_text(json.dumps({"arg": arg, "source_hashes": start["source_hashes"],
                               "input_hashes": start["input_hashes"]}, default=float))
    result = subprocess.run(
        [sys.executable, "-m", "triple_lock.trajectories", "--job", kind, str(inp), str(out)],
        cwd=workdir, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    if result.returncode != 0:
        raise RuntimeError(f"{kind} job failed in {workdir}:\n{result.stderr[-4000:]}")
    return json.loads(out.read_text())


def _keys_to_int(d):
    return {int(k) if isinstance(k, str) and k.lstrip("-").isdigit() else k: _keys_to_int(v) if isinstance(v, dict) else v
            for k, v in d.items()}


def method_text(models):
    path_model = next(m for m, (_, _, run) in MODEL_METHODS.items() if run)
    return {
        "summary": "Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled.",
        "horizon": f"Upratings April {TRAJECTORY_HORIZON[0]} to April {TRAJECTORY_FINAL_YEAR}, so the final year is "
                   f"{TRAJECTORY_FINAL_YEAR}-{str(TRAJECTORY_FINAL_YEAR + 1)[2:]}. The main results stop at "
                   f"{MAIN_HORIZON[-1]}-{str(MAIN_HORIZON[-1] + 1)[2:]}; the central path reproduces them to then.",
        "macro_path": (
            f"Each path's calendar-year CPI and earnings growth for {CALENDAR_YEARS[0]}-{CALENDAR_YEARS[-1]} replace the "
            "model's economic assumptions before the data load (RPI and CPIH move by the same amount as CPI), with "
            "policyengine-uk's derived series extended to 2042 first. Each run checks, for every year, that benefit "
            "rates uprated by CPI (the Pension Credit guarantee among them) grow by the path's CPI the year before, "
            "CPI-indexed thresholds by its CPI the same year, employment income by its earnings the same year, and "
            "the model's own triple lock by the path's calendar measures. Also moving: survey amounts uprated by "
            "CPI and private pension income (RPI the year before, capped at 5%). Not moving: dividend, property and "
            "savings income and wealth, self-employment income, rents, council tax and mortgage interest; from 2031 "
            "rents and council tax stay at their 2030 amounts (the survey data are extended to 2030). Calendar 2026 "
            "growth, which sets April 2027's benefit uprating, is the model's own on every path."
        ),
        "statutory_inputs": (
            "The State Pension rises come from each rule applied to the path's statutory inputs (September CPI, "
            "May-July AWE). April 2027 uses the published May-July 2026 earnings on every path; its September CPI "
            "is August 2026 CPI on the central and Uncertainty tab paths and simulated on the monthly-model paths. "
            "The central path's later statutory inputs equal its calendar values; the monthly model builds both "
            "from the same simulated months; the Uncertainty tab's paths carry its statutory draws to 2033."
        ),
        "state_pension": (
            "Flat-rate amounts from each rule, rates to 3 dp (unrounded on the Uncertainty tab's paths, as on that "
            "tab). The additional State Pension is pinned to the unreformed model on the same path, so it follows the "
            "model's own triple lock on the calendar measures, not CPI as in law; it is the same in both runs."
        ),
        "path_model": (
            f"The monthly-model paths use {models[path_model]['label'].lower()} with shocks resampled from its "
            "residuals. The t-copula and Gaussian versions put more weight on deflation, including September CPI "
            "below -3%, which the published series has never reached; models.*.september_cpi_below records the "
            "tilted shares."
        ),
        "percentile_labels": f"Middle and 90th-percentile paths are ranked on the {TRAJECTORY_FINAL_YEAR}-"
                             f"{str(TRAJECTORY_FINAL_YEAR + 1)[2:]} gap in the weekly rate (rule arithmetic), not on "
                             "cost; a few paths are not a distribution.",
    }


def build(workers=3, allow_dirty=False, log=print):
    from policyengine.tax_benefit_models.uk import managed_microsimulation

    from . import model_horizon, provenance
    from .pipeline import base_levels, central_path
    from .ts_backtest import run_backtest, run_statutory_backtest

    start = snapshot()
    if start["git_dirty"] and not allow_dirty:
        raise SystemExit("The git tree is dirty: commit first, or pass --allow-dirty (the file will say so).")
    main_results = json.loads(OUTPUT.read_text())
    reference = managed_microsimulation()
    reference.baseline = None
    parameters = reference.tax_benefit_system.parameters
    bundle = reference.policyengine_bundle
    # Growth years 2026-2039, April 2027's inputs substituted.
    central_cpi, central_earnings, _ = central_path(parameters, [*TRAJECTORY_HORIZON, TRAJECTORY_FINAL_YEAR + 1])
    base_new_sp = base_levels(parameters)["new_state_pension"]
    actual_weekly = {n: {y: float(parameters.get_child(path)(f"{y}-06-01"))
                         for y in HISTORY_YEARS if y >= (2016 if n == "new_state_pension" else 2011)}
                     for n, path in FLAT_RATE.items()}
    bsp = {y: float(parameters.get_child(FLAT_RATE["basic_state_pension"])(f"{y}-06-01"))
           for y in [HISTORY_YEARS[0] - 1, *HISTORY_YEARS]}
    actual_rise = {y: round(bsp[y] / bsp[y - 1] - 1, 3) for y in HISTORY_YEARS}
    del reference

    log("Selecting future paths")
    specs, models = forward_specs(central_cpi, central_earnings, base_new_sp, main_results)
    cpi_h, earnings_h = history_inputs()
    groups = history_groups(cpi_h, earnings_h)

    log(f"Running {len(specs)} future paths and {sum(g['changes_anything'] for g in groups)} past-year cases")
    with tempfile.TemporaryDirectory(prefix="trajectories-") as tmp, ThreadPoolExecutor(workers) as pool:
        forward = {s["id"]: pool.submit(_run_isolated, "forward", s, Path(tmp) / s["id"], start) for s in specs}
        past = {g["switch_years"][0]: pool.submit(_run_isolated, "history", g["switch_years"][0],
                                                   Path(tmp) / f"history_{g['switch_years'][0]}", start)
                for g in groups if g["changes_anything"]}
        forward = {k: _keys_to_int(f.result()) for k, f in forward.items()}
        past = {k: _keys_to_int(f.result()) for k, f in past.items()}
    log("Backtests of the forecast-distribution methods")
    backtest = {"statutory": run_statutory_backtest(), "calendar": run_backtest()}

    trajectories = []
    for s in specs:
        r = forward[s["id"]]
        trajectories.append({key: s[key] for key in ("id", "label", "source") if key in s}
                            | {key: s[key] for key in ("selection", "uncertainty_tab_last_year") if key in s}
                            | {k: v for k, v in r.items() if k != "bundle"})
    for g in groups:
        g["model_years"] = past.get(g["switch_years"][0])

    check_unchanged(start, "the end of the build")
    prov = provenance.build_provenance(bundle, start["input_hashes"])
    prov.update({k: start[k] for k in ("generated_at", "git_revision", "git_dirty", "source_hashes")})
    prov["packages"]["scipy"] = __import__("importlib.metadata").metadata.version("scipy")
    prov["snapshot"] = "revision, dirty flag and hashes taken when the build started; rechecked at its end"
    return {
        "provenance": prov,
        "horizon": TRAJECTORY_HORIZON,
        "main_horizon": MAIN_HORIZON,
        "switch_year": SWITCH_YEAR,
        "policies": {p: main_results["policies"][p] for p in POLICIES},
        "method": method_text(models) | {"model_horizon": model_horizon.extensions()},
        "models": models,
        "gap_statistics": gap_statistics(),
        "trajectories": trajectories,
        "history": {
            "years": HISTORY_YEARS,
            "model_years": HISTORY_MODEL_YEARS,
            "cpi": cpi_h,
            "earnings": earnings_h,
            "suspended_earnings_year": SUSPENDED_EARNINGS_YEAR,
            "actual_weekly": actual_weekly,
            "actual_rise": actual_rise,
            "actual_rise_note": "Rise actually paid each April: the model's basic State Pension amounts, rounded to "
                                "0.1 point.",
            "note": "September CPI and May-July earnings, latest ONS vintage; April 2022's earnings leg was "
                    "suspended, so both rules use CPI that year. Counterfactual flat rate = actual flat rate x "
                    "(Burnham index / triple-lock replay index); each person's pension scales by that ratio.",
            "groups": groups,
        },
        "backtest": backtest,
    }


def write(results, paths=(TRAJECTORY_OUTPUT, TRAJECTORY_DASHBOARD_COPY)):
    text = json.dumps(results, indent=1, default=float, allow_nan=False) + "\n"
    for path in paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        print(f"Trajectory results written to {path}")


def _job(kind, inp, out):
    from . import model_horizon

    payload = json.loads(Path(inp).read_text())
    check_unchanged(payload, f"the start of this {kind} job")
    # Before any simulation: every series the path drives must reach the final year.
    model_horizon.install()
    arg = payload["arg"]
    if kind == "forward":
        for key in ("cpi", "earnings", "statutory_cpi", "statutory_earnings"):
            arg[key] = {int(k): v for k, v in arg[key].items()}
        result = run_forward(arg)
    else:
        result = run_history(int(arg))
    Path(out).write_text(json.dumps(result, default=float, allow_nan=False))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Full-model trajectories: the Burnham plan vs the triple lock")
    parser.add_argument("--job", nargs=3, metavar=("KIND", "INPUT", "OUTPUT"), help=argparse.SUPPRESS)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--allow-dirty", action="store_true", help="run from a tree with uncommitted changes")
    args = parser.parse_args(argv)
    if args.job:
        _job(*args.job)
        return 0
    write(build(workers=args.workers, allow_dirty=args.allow_dirty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
