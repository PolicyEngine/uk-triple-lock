"""Trajectory viewer data: the Burnham plan vs the triple lock on a few paths, each a full model run.

Every fiscal and household figure here comes from PolicyEngine UK runs on the
certified data; nothing is scaled from another run.

Future paths (April 2027 to April 2034 upratings)
-------------------------------------------------
* ``central``: the dashboard's central path (OBR March 2026 EFO to 2030,
  PolicyEngine's long-run path after).
* A monthly time-series model of the CPI index and average weekly earnings
  (ts_monthly: a VAR on monthly log changes with Student-t marginal shocks
  joined by a t-copula; the Gaussian-shock version is reported but not run). They simulate the months from August
  2026, so September CPI and May-July AWE (the statutory inputs) and the
  calendar-year measures all come from the same months, and September 2026 CPI
  is uncertain. The best-scoring methods in the statutory backtest
  (ts_backtest.run_statutory_backtest). 20,000 paths, entropy-tilted so the
  weighted mean of calendar CPI and earnings in each year equals the central
  path. The most typical draw near the weighted median and 90th
  percentile of the 2034-35 Burnham gap (rule arithmetic on the weekly rate) is
  run through the model.
* The Uncertainty tab's own representative p50 and p90 paths.

How a path enters the model: its calendar-year CPI and earnings growth for
2027-2033 replace ``gov.economic_assumptions.yoy_growth.obr`` (RPI and CPIH move
with CPI) in a Scenario applied before the data load, so every uprated parameter
and microdata income follows it. The State Pension flat rates are set from each
rule applied to the path's statutory inputs (September CPI, May-July AWE; 3 dp
rates), and the additional State Pension is pinned to the unreformed model on
the same path. The central path and the Uncertainty tab's paths have no separate
statutory series: their values serve as both.

Past years
----------
What the Burnham plan would have paid had it started in an earlier April, on the
published September CPI and May-July earnings (ONS, latest vintage; April 2022's
earnings leg was suspended, so both rules use CPI that year). Counterfactual
level = actual level x (Burnham index / triple-lock replay index). Fiscal and
household effects for 2024-25 to 2026-27, the years the survey data cover, come
from full runs.

Run: ``python -m triple_lock.trajectories`` (needs managed-data access; each
model run happens in its own process and working directory).
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
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
    ERROR_CSV,
    FINAL_YEAR,
    HORIZON,
    OUTPUT,
    REPO,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)

TRAJECTORY_OUTPUT = REPO / "data" / "trajectory_results.json"
TRAJECTORY_DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "trajectory_results.json"
# Diagnostics: write the results only to this path (never the committed files).
OUTPUT_ENV = "TRIPLE_LOCK_TRAJECTORY_OUTPUT"
POLICIES = ["triple_lock", "burnham_2030"]
GROWTH_YEARS = [y - 1 for y in HORIZON[1:]]  # 2027-2033: set April 2028..April 2034
N_DRAWS = 20_000
SEED = 20260929
QUANTILES = (0.5, 0.9)
NEAR_GBP = 0.10  # a draw is "near" a quantile within 10p a week
# (shock kind, label, whether its paths go through the model). Only the t-copula
# model's paths are run: the Gaussian model's 90th-percentile draws include
# September CPI rates far below anything since 1989 (-3% and lower).
MODEL_METHODS = {
    "monthly_tcop": ("tcop", "Monthly model", True),
    "monthly_gauss": ("gauss", "Monthly model, Gaussian shocks", False),
}
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
HASHED = ["trajectories.py", "ts_methods.py", "ts_monthly.py", "ts_backtest.py", "rules.py", "config.py",
          "pipeline.py", "var_check.py", "uncertainty.py"]


# ── Which input set each year's rise ─────────────────────────────────────


def rate_sources(cpi, earnings, rates, years):
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
        floor = round(max(c, TRIPLE_LOCK_FLOOR), CENTRAL_RATE_DECIMALS)
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


def burnham_gap(cpi, earnings, base_new_sp):
    """Full new State Pension, £/week in the final year: triple lock minus Burnham plan, per draw.

    ``cpi`` and ``earnings`` are (n, 8) statutory inputs for growth years 2026-2033.
    """
    level = {
        p: base_new_sp * np.prod(1 + rules.rates_matrix(p, cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS), axis=1)
        for p in POLICIES
    }
    return level["triple_lock"] - level["burnham_2030"]


def select_draws(paths, weights, gap, quantiles=QUANTILES):
    """The most typical draw near each weighted quantile of the gap.

    Candidates: draws within NEAR_GBP of the quantile with at least the median
    weight. The pick is the candidate closest (squared distance over years and
    series) to the candidates' weighted mean path.
    """
    picks = []
    for q in quantiles:
        target = weighted_quantile(gap, weights, q)
        cand = np.where(np.abs(gap - target) < NEAR_GBP)[0]
        cand = cand[weights[cand] >= np.median(weights)]
        centre = (weights[cand][:, None, None] * paths[cand]).sum(0) / weights[cand].sum()
        pick = int(cand[np.argmin(((paths[cand] - centre) ** 2).sum(axis=(1, 2)))])
        picks.append({"quantile": q, "draw": pick, "quantile_gap_gbp_week": round(target, 2),
                      "gap_gbp_week": round(float(gap[pick]), 2), "n_candidates": int(len(cand))})
    return picks


def forward_specs(central_cpi, central_earnings, statutory, base_new_sp, main_results):
    """Every future trajectory: calendar growth (keyed 2027-2033) for the economic assumptions and
    statutory inputs (keyed 2026-2033) for the rule; plus model diagnostics."""
    from . import ts_monthly
    from .ts_methods import tilt

    target = np.array([[central_cpi[y], central_earnings[y]] for y in GROWTH_YEARS])
    specs = [{
        "id": "central",
        "label": "Central forecast",
        "source": "The dashboard's central path: OBR March 2026 forecast to 2030, PolicyEngine's long-run path "
                  "after; its calendar values also serve as the statutory inputs (April 2027: published inputs)",
        "cpi": {y: central_cpi[y] for y in GROWTH_YEARS},
        "earnings": {y: central_earnings[y] for y in GROWTH_YEARS},
    }]
    models = {}
    years = [BASE_YEAR, *GROWTH_YEARS]
    for method, (kind, label, run_paths) in MODEL_METHODS.items():
        m, info = ts_monthly.paths(years, N_DRAWS, SEED, kind)
        cal = np.stack([m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:]], axis=2)
        weights, tinfo = tilt(cal, target)
        gap = burnham_gap(m["statutory_cpi"], m["statutory_earnings"], base_new_sp)
        models[method] = {
            "label": label,
            **info,
            "tilt_effective_sample": round(tinfo["ess"]),
            "gap_gbp_week": {f"p{int(100 * q)}": round(weighted_quantile(gap, weights, q), 2)
                             for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
            "gap_zero_share": round(float(weights @ (np.abs(gap) < 0.005)), 3),
            "gap_negative_share": round(float(weights @ (gap <= -0.005)), 3),
            "september_2026_cpi": {f"p{int(100 * q)}": round(weighted_quantile(m["statutory_cpi"][:, 0], weights, q), 4)
                                   for q in (0.1, 0.5, 0.9)},
        }
        if not run_paths:
            continue
        stat = np.stack([m["statutory_cpi"], m["statutory_earnings"]], axis=2)
        for pick in select_draws(stat, weights, gap):
            p, d = int(100 * pick["quantile"]), pick["draw"]
            specs.append({
                "id": f"{method}_p{p}",
                "label": f"{label}: {'middle' if p == 50 else f'{p}th percentile'}",
                "source": (f"Draw {d} of {N_DRAWS:,}: the most typical draw whose 2034-35 Burnham gap is near the "
                           f"model's weighted {p}th percentile (£{pick['quantile_gap_gbp_week']:.2f} a week)"),
                "selection": pick,
                "cpi": {y: float(m["calendar_cpi"][d, j + 1]) for j, y in enumerate(GROWTH_YEARS)},
                "earnings": {y: float(m["calendar_earnings"][d, j + 1]) for j, y in enumerate(GROWTH_YEARS)},
                "statutory_cpi": {y: float(m["statutory_cpi"][d, j]) for j, y in enumerate(years)},
                "statutory_earnings": {y: float(m["statutory_earnings"][d, j]) for j, y in enumerate(years)},
            })
    for q in ("p50", "p90"):
        rep = main_results["uncertainty"]["representative_paths"][q]
        specs.append({
            "id": f"uncertainty_tab_{q}",
            "label": f"Uncertainty tab: {'middle' if q == 'p50' else '90th percentile'} path",
            "source": (f"The Uncertainty tab's representative {q} path (draw {rep['draw']} of its block bootstrap of "
                       "OBR forecast errors and statutory gaps), here applied to the whole model"),
            "cpi": {y: rep["cpi"][str(y)] for y in GROWTH_YEARS},
            "earnings": {y: rep["earnings"][str(y)] for y in GROWTH_YEARS},
        })
    return specs, models


def _econ_changes(spec, parameters):
    obr = parameters.get_child(OBR)
    cpi_node = obr.get_child("consumer_price_index")
    changes = {
        f"{OBR}.consumer_price_index": {f"year:{y}-01-01:1": float(spec["cpi"][y]) for y in GROWTH_YEARS},
        f"{OBR}.average_earnings": {f"year:{y}-01-01:1": float(spec["earnings"][y]) for y in GROWTH_YEARS},
    }
    for series in MOVE_WITH_CPI:
        node = obr.get_child(series)
        changes[f"{OBR}.{series}"] = {
            f"year:{y}-01-01:1": float(node(f"{y}-01-01")) + float(spec["cpi"][y]) - float(cpi_node(f"{y}-01-01"))
            for y in GROWTH_YEARS
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


def run_forward(spec):
    """Full model runs of one future path: unreformed, triple lock and Burnham plan."""
    from policyengine_uk.utils.scenario import Scenario

    from .breakdowns import BREAKDOWNS, breakdown, household_frame, households_affected
    from .pipeline import PINNED_VARIABLES, base_levels, household_groups, managed_microsimulation, statutory_inputs

    reference = managed_microsimulation()
    parameters = reference.tax_benefit_system.parameters
    bundle = reference.policyengine_bundle
    base = base_levels(parameters)
    changes = _econ_changes(spec, parameters)
    del reference

    if "statutory_cpi" in spec:
        cpi = {y: float(v) for y, v in spec["statutory_cpi"].items()}
        earnings = {y: float(v) for y, v in spec["statutory_earnings"].items()}
    else:
        stat = statutory_inputs()
        cpi = {BASE_YEAR: stat["cpi"], **{y: float(spec["cpi"][y]) for y in GROWTH_YEARS}}
        earnings = {BASE_YEAR: stat["earnings"], **{y: float(spec["earnings"][y]) for y in GROWTH_YEARS}}
    rates = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS) for p in POLICIES}
    levels = {p: {name: rules.level_path(base[name], rates[p], HORIZON) for name in base} for p in POLICIES}

    def build():
        return managed_microsimulation(scenario=Scenario(parameter_changes=changes, applied_before_data_load=True))

    unreformed = build()
    p = unreformed.tax_benefit_system.parameters
    applied_growth = {
        "cpi": {y: float(p.get_child(f"{OBR}.consumer_price_index")(f"{y}-01-01")) for y in GROWTH_YEARS},
        "earnings": {y: float(p.get_child(f"{OBR}.average_earnings")(f"{y}-01-01")) for y in GROWTH_YEARS},
    }
    pinned = {v: {y: unreformed.calculate(v, y).to_numpy() for y in HORIZON} for v in PINNED_VARIABLES}
    del unreformed

    totals, income, groups, applied_weekly, hh = {}, {}, None, {}, {}
    for policy in POLICIES:
        sim = build()
        _set_flat_rates(sim, levels[policy])
        _pin(sim, pinned)
        totals[policy] = _totals(sim, HORIZON)
        income[policy] = sim.calculate("household_net_income", FINAL_YEAR)
        hh[policy] = {v: sim.calculate(v, FINAL_YEAR, map_to="household").to_numpy()
                      for v in ("household_id", "housing_benefit", "pension_credit", "state_pension")}
        if groups is None:
            groups = household_groups(sim, FINAL_YEAR)
        applied_weekly[policy] = {y: float(sim.tax_benefit_system.parameters.get_child(FLAT_RATE["new_state_pension"])(
            f"{y}-06-01")) for y in HORIZON}
        del sim

    tl, bp = totals["triple_lock"], totals["burnham_2030"]
    change = income["burnham_2030"] - income["triple_lock"]
    frame = household_frame(change, income["triple_lock"], groups)
    # The single household record that moves the final-year net figure most:
    # arithmetic on this run's own output (a decomposition), not an estimate.
    weight = income["triple_lock"].weights.to_numpy()
    contribution = change.to_numpy() * weight / BN
    i = int(np.argmax(np.abs(contribution)))
    net_final = float(contribution.sum())
    largest = {
        "household_id": int(hh["triple_lock"]["household_id"][i]),
        "weight": float(weight[i]),
        "income_change_gbp": float(change.to_numpy()[i]),
        "contribution_bn": float(contribution[i]),
        "share_of_income_change": float(contribution[i] / net_final) if net_final else 0.0,
        "income_change_excluding_bn": float(net_final - contribution[i]),
        "change_gbp": {v: float(hh["burnham_2030"][v][i] - hh["triple_lock"][v][i])
                       for v in ("housing_benefit", "pension_credit", "state_pension")},
        "median_weight": float(np.median(weight)),
    }
    return {
        "statutory": {"cpi": cpi, "earnings": earnings},
        "calendar": {"cpi": {y: float(spec["cpi"][y]) for y in GROWTH_YEARS},
                     "earnings": {y: float(spec["earnings"][y]) for y in GROWTH_YEARS}},
        "applied_growth": applied_growth,
        "rates": rates,
        "rate_sources": rate_sources(cpi, earnings, rates, HORIZON),
        "weekly": levels,
        "applied_new_state_pension": applied_weekly,
        "saving_bn": {
            y: {
                "gross": tl[y]["state_pension_flat_rate"] - bp[y]["state_pension_flat_rate"],
                "net": bp[y]["gov_balance"] - tl[y]["gov_balance"],
                "household_income_change": bp[y]["household_net_income"] - tl[y]["household_net_income"],
                "components": {k: bp[y][k] - tl[y][k] for k in tl[y] if k not in ("gov_balance", "household_net_income")},
            }
            for y in HORIZON
        },
        "totals_bn": totals,
        "by_decile": breakdown(frame, *BREAKDOWNS["by_decile"]),
        "households_affected": households_affected(change),
        "largest_household": largest,
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


def run_history(switch_year):
    """Full model runs for 2024-25..2026-27: actual law vs flat rates had the plan started in ``switch_year``."""
    from .pipeline import PINNED_VARIABLES, managed_microsimulation

    cpi, earnings = history_inputs()
    cf = history_counterfactual(switch_year, cpi, earnings)
    base = managed_microsimulation()
    p = base.tax_benefit_system.parameters
    actual = {n: {y: float(p.get_child(path)(f"{y}-06-01")) for y in HISTORY_MODEL_YEARS} for n, path in FLAT_RATE.items()}
    levels = {n: {y: actual[n][y] * cf["level_ratio"][y] for y in HISTORY_MODEL_YEARS} for n in FLAT_RATE}
    pinned = {v: {y: base.calculate(v, y).to_numpy() for y in HISTORY_MODEL_YEARS} for v in PINNED_VARIABLES}
    base_totals = _totals(base, HISTORY_MODEL_YEARS)
    last = HISTORY_MODEL_YEARS[-1]
    base_income = base.calculate("household_net_income", last).to_numpy()
    weight = base.calculate("household_weight", last).to_numpy()
    del base
    sim = managed_microsimulation()
    _set_flat_rates(sim, levels)
    _pin(sim, pinned)
    applied = {y: float(sim.tax_benefit_system.parameters.get_child(FLAT_RATE["new_state_pension"])(f"{y}-06-01"))
               for y in HISTORY_MODEL_YEARS}
    totals = _totals(sim, HISTORY_MODEL_YEARS)
    change = sim.calculate("household_net_income", last).to_numpy() - base_income
    return {
        "actual_weekly": actual,
        "counterfactual_weekly": levels,
        "applied_new_state_pension": applied,
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


# ── Orchestration ────────────────────────────────────────────────────────


def _run_isolated(kind, arg, workdir):
    """Run one model job in its own process and working directory (the dataset lands in ./data)."""
    workdir.mkdir(parents=True, exist_ok=True)
    inp, out = workdir / "input.json", workdir / "output.json"
    inp.write_text(json.dumps(arg, default=float))
    result = subprocess.run(
        [sys.executable, "-m", "triple_lock.trajectories", "--job", kind, str(inp), str(out)],
        cwd=workdir, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    if result.returncode != 0:
        raise RuntimeError(f"{kind} job failed in {workdir}:\n{result.stderr[-4000:]}")
    return json.loads(out.read_text())


def _keys_to_int(d):
    return {int(k) if isinstance(k, str) and k.isdigit() else k: _keys_to_int(v) if isinstance(v, dict) else v
            for k, v in d.items()}


def build(workers=6, log=print):
    from . import provenance
    from .pipeline import base_levels, central_path, dataset_override, managed_microsimulation, statutory_inputs
    from .ts_backtest import run_backtest, run_statutory_backtest
    from .var_check import SERIES

    main_results = json.loads(OUTPUT.read_text())
    reference = managed_microsimulation()
    parameters = reference.tax_benefit_system.parameters
    bundle = reference.policyengine_bundle
    central_cpi, central_earnings, _ = central_path(parameters)
    statutory = statutory_inputs()
    statutory["model_cpi"] = float(parameters.get_child(f"{OBR}.consumer_price_index")(f"{BASE_YEAR}-01-01"))
    statutory["model_earnings"] = float(parameters.get_child(f"{OBR}.average_earnings")(f"{BASE_YEAR}-01-01"))
    base_new_sp = base_levels(parameters)["new_state_pension"]
    del reference

    log("Selecting future paths")
    specs, models = forward_specs(central_cpi, central_earnings, statutory, base_new_sp, main_results)
    cpi_h, earnings_h = history_inputs()
    groups = history_groups(cpi_h, earnings_h)

    log(f"Running {len(specs)} future paths and {sum(g['changes_anything'] for g in groups)} past-year cases")
    with tempfile.TemporaryDirectory(prefix="trajectories-") as tmp, ThreadPoolExecutor(workers) as pool:
        forward = {s["id"]: pool.submit(_run_isolated, "forward", s, Path(tmp) / s["id"]) for s in specs}
        past = {g["switch_years"][0]: pool.submit(_run_isolated, "history", g["switch_years"][0],
                                                   Path(tmp) / f"history_{g['switch_years'][0]}")
                for g in groups if g["changes_anything"]}
        forward = {k: _keys_to_int(f.result()) for k, f in forward.items()}
        past = {k: _keys_to_int(f.result()) for k, f in past.items()}
    log("Backtests of the forecast-distribution methods")
    backtest = {"statutory": run_statutory_backtest(), "calendar": run_backtest()}

    trajectories = []
    for s in specs:
        r = forward[s["id"]]
        trajectories.append({key: s[key] for key in ("id", "label", "source") if key in s}
                            | ({"selection": s["selection"]} if "selection" in s else {})
                            | {k: v for k, v in r.items() if k != "bundle"})
    for g in groups:
        g["model_years"] = past.get(g["switch_years"][0])

    from .config import CROSSCHECK_CSV
    from .ts_monthly import AWE_LEVEL_CSV, CPI_INDEX_CSV

    input_hashes = {str(p.relative_to(REPO)): provenance.file_hash(p)
                    for p in [OUTPUT, ACTUALS_CSV, ERROR_CSV, AWE_CSV, CPI_CSV, CENTRAL_FORECAST_CSV, CROSSCHECK_CSV,
                              CPI_INDEX_CSV, AWE_LEVEL_CSV, *(path for path, _ in SERIES.values())]}
    prov = provenance.build_provenance(bundle, input_hashes)
    prov["source_hashes"] = trajectory_source_hashes()
    override = dataset_override()
    if override is not None:
        prov["dataset_override"] = {"path": str(override), "sha256": provenance.file_hash(override)}
    prov["packages"]["scipy"] = __import__("importlib.metadata").metadata.version("scipy")
    return {
        "provenance": prov,
        "horizon": HORIZON,
        "switch_year": SWITCH_YEAR,
        "policies": {p: main_results["policies"][p] for p in POLICIES},
        "method": {
            "summary": "Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled.",
            "macro_path": "CPI and earnings growth for 2027-2033 replace the model's economic assumptions before the "
                          "data load (RPI and CPIH move with CPI), so every uprated benefit rate, threshold and "
                          "microdata income follows the path. The path's CPI and earnings also set the April "
                          "upratings (statutory gaps at zero); April 2027 uses the published 3.9% earnings and "
                          "August 2026 CPI.",
            "state_pension": "Flat-rate amounts from each rule, 3 dp rates; additional State Pension pinned to the "
                             "unreformed model on the same path.",
            "percentile_labels": "Middle and 90th-percentile paths are ranked on the 2034-35 gap in the weekly rate "
                                 "(rule arithmetic), not on cost; a few paths are not a distribution.",
        },
        "models": models,
        "trajectories": trajectories,
        "history": {
            "years": HISTORY_YEARS,
            "model_years": HISTORY_MODEL_YEARS,
            "cpi": cpi_h,
            "earnings": earnings_h,
            "suspended_earnings_year": SUSPENDED_EARNINGS_YEAR,
            "actual_weekly": {n: {y: float(parameters.get_child(path)(f"{y}-06-01"))
                                  for y in HISTORY_YEARS if y >= (2016 if n == "new_state_pension" else 2011)}
                              for n, path in FLAT_RATE.items()},
            "note": "September CPI and May-July earnings, latest ONS vintage; April 2022's earnings leg was "
                    "suspended, so both rules use CPI that year. Counterfactual level = actual level x "
                    "(Burnham index / triple-lock replay index).",
            "groups": groups,
        },
        "backtest": backtest,
    }


def trajectory_source_hashes():
    from .provenance import file_hash

    here = Path(__file__).resolve().parent
    hashes = {name: file_hash(here / name) for name in HASHED}
    hashes["pyproject.toml"] = file_hash(REPO / "pyproject.toml")
    return hashes


def output_paths():
    """The committed results and dashboard copy, or only ``TRIPLE_LOCK_TRAJECTORY_OUTPUT`` when set.

    A run on an alternative dataset (``TRIPLE_LOCK_DATASET``) must name its own output.
    """
    from .pipeline import DATASET_ENV

    override = os.environ.get(OUTPUT_ENV)
    if override:
        return (Path(override),)
    if os.environ.get(DATASET_ENV):
        raise ValueError(f"{DATASET_ENV} is set: set {OUTPUT_ENV} too, so the committed results are not overwritten")
    return (TRAJECTORY_OUTPUT, TRAJECTORY_DASHBOARD_COPY)


def write(results, paths=(TRAJECTORY_OUTPUT, TRAJECTORY_DASHBOARD_COPY)):
    text = json.dumps(results, indent=1, default=float) + "\n"
    for path in paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        print(f"Trajectory results written to {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Full-model trajectories: the Burnham plan vs the triple lock")
    parser.add_argument("--job", nargs=3, metavar=("KIND", "INPUT", "OUTPUT"), help=argparse.SUPPRESS)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    if args.job:
        kind, inp, out = args.job
        arg = json.loads(Path(inp).read_text())
        if kind == "forward":
            for key in ("cpi", "earnings", "statutory_cpi", "statutory_earnings"):
                if key in arg:
                    arg[key] = {int(k): v for k, v in arg[key].items()}
            result = run_forward(arg)
        else:
            result = run_history(int(arg))
        Path(out).write_text(json.dumps(result, default=float))
        return 0
    paths = output_paths()
    write(build(workers=args.workers), paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
