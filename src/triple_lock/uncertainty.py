"""Monte Carlo over OBR forecast errors for CPI and earnings growth.

Method
------
Each draw adds a historical *vintage* of OBR forecast errors to the central
growth path. Resampling whole vintages (a block bootstrap by forecast year)
keeps two features a parametric draw would lose: the CPI and earnings errors
of one forecast are strongly correlated (about 0.8), and errors in the same
vintage persist across horizons.

The central path is the March 2026 EFO, so calendar growth year ``g`` sits at
forecast horizon ``g - 2026``:

* horizon 0 (2026, which sets the April 2027 uprating) uses the published
  May-July AWE and August CPI; September CPI, not yet published, is drawn by
  resampling historical August-to-September changes (the main run);
* horizons 1..H (H = 4, the spring vintages' coverage) take the errors of
  one sampled vintage;
* horizons beyond H are filled by further independently sampled vintages,
  using each one's longest-horizon errors (horizons 2..H), so long horizons
  carry long-horizon error variance (restarting the second block at horizon
  1 would give 5-7-year horizons the smaller variance of 1-3-year ones). The within-draw persistence of errors
  is broken at each join.

Only vintages that cover every horizon 1..H (H = 4) are retained.

Cost approximation
------------------
Flat-rate State Pension spending is proportional to the flat-rate level (the
formula is ``share x amount``), so spending under any path is
``S_central x I(path) / I_TL,central`` where ``S_central`` is PolicyEngine's
final-year basic + new State Pension spend under the triple lock on the
central forecast and ``I`` is the cumulative uprating index. The cost of the
triple lock relative to an alternative in the final year is then

    S_central x (I_TL(draw) - I_alt(draw)) / I_TL,central

This uses each draw's own triple-lock path as the base, which is what the
difference in spending is. (``S x (I_TL / I_alt - 1)`` would instead price the
gap on the alternative's spending level.) The pipeline validates it against
full PolicyEngine runs on the representative p10/p50/p90 paths.
"""

import csv
from pathlib import Path

import numpy as np

from .config import (
    ALTERNATIVES,
    BLOCK_HORIZON,
    FAN_QUANTILES,
    MC_SEED,
    N_DRAWS,
    POLICIES,
    QUANTILES,
    REPRESENTATIVE_RANKING_POLICY,
)
from .rules import floor_binds, rule_rate, zero_floor_binds

VARIABLES = ("cpi", "earnings")
REQUIRED_COLUMNS = {
    "year_forecast_made",
    "forecast_vintage",
    "horizon_years",
    "variable",
    "forecast",
    "outturn",
    "error",
}


# ── Loading ──────────────────────────────────────────────────────────────


def load_forecast_errors(path):
    """Read the error CSV into {(year_made, vintage): {(variable, horizon): error}}.

    Rates must be decimals (0.021 = 2.1%), as the file documents. Every row
    must be a CPI or earnings error with a value; anything else raises.
    Duplicate rows within a vintage are averaged.
    """
    path = Path(path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path} has no rows")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    grouped = {}
    for n, row in enumerate(rows, start=2):
        variable = row["variable"].strip().lower()
        if variable not in VARIABLES:
            raise ValueError(f"{path} line {n}: unknown variable {row['variable']!r}")
        if abs(float(row["forecast"])) > 1:
            raise ValueError(f"{path} line {n}: forecast {row['forecast']} is not a decimal rate")
        vintage = (int(row["year_forecast_made"]), row["forecast_vintage"].strip())
        key = (variable, int(row["horizon_years"]))
        grouped.setdefault(vintage, {}).setdefault(key, []).append(float(row["error"]))
    return {
        vintage: {key: float(np.mean(values)) for key, values in errors.items()}
        for vintage, errors in grouped.items()
    }


def error_blocks(errors_by_vintage, block_horizon=BLOCK_HORIZON, exclude_target_years=()):
    """Complete vintages as an array (n_vintages, H, 2) of [cpi, earnings] errors.

    H = ``block_horizon``. Vintages without every horizon 1..H for both
    variables are not blocks and are left out (the most recent EFOs, whose
    later horizons have no outturn yet). ``exclude_target_years`` drops whole
    vintages whose horizons 1..H target any of those years (the block is kept
    intact rather than patched).
    """
    if block_horizon < 2:
        raise ValueError("block horizon must be at least 2")
    horizons = range(1, block_horizon + 1)
    excluded = set(exclude_target_years)
    kept = sorted(
        v
        for v, errors in errors_by_vintage.items()
        if all((var, h) in errors for var in VARIABLES for h in horizons)
        and not excluded & {v[0] + h for h in horizons}
    )
    if len(kept) < 2:
        raise ValueError("fewer than two complete vintages")
    blocks = np.array(
        [[[errors_by_vintage[v][(var, h)] for var in VARIABLES] for h in horizons] for v in kept]
    )
    return blocks, kept


def load_statutory_gaps(path):
    """{year: (cpi_gap, earnings_gap)}: statutory input minus calendar-year proxy.

    CPI: September 12-month rate minus the OBR calendar-year outturn.
    Earnings: May-July AWE total pay growth (KAC3) minus the OBR earnings
    outturn, or the OBR-definition rebuild from latest ONS data where the
    database has no outturn yet. Years missing either gap are left out.
    """
    path = Path(path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    gaps = {}
    for row in rows:
        obr_earnings = row["earnings_obr_outturn"] or row["earnings_obr_def_rebuilt_latest_ons"]
        needed = [row["cpi_ons_d7g7_september"], row["cpi_obr_outturn"], row["awe_kac3_may_jul"], obr_earnings]
        if not all(needed):
            continue
        gaps[int(row["year"])] = (
            float(row["cpi_ons_d7g7_september"]) - float(row["cpi_obr_outturn"]),
            float(row["awe_kac3_may_jul"]) - float(obr_earnings),
        )
    if not gaps:
        raise ValueError(f"{path} has no complete statutory-gap years")
    return gaps


def gap_blocks(kept, gaps, block_horizon=BLOCK_HORIZON):
    """Statutory gaps aligned with :func:`error_blocks`, (n_vintages, H, 2).

    Cell (v, h) holds the gaps for vintage v's horizon-h target year, so a
    draw that picks a vintage's forecast errors also picks the gaps of the
    same years: the CPI and earnings gaps keep their joint and serial pattern
    and their comovement with the forecast errors. The gaps are de-meaned by
    horizon (across vintages), as the forecast errors are, so they widen the
    draws without moving their mean in any year. This removes the gaps'
    historical average, including May-July AWE running about 0.3pp a year
    above OBR earnings.
    Raises if a target year has no gap.
    """
    missing = sorted({v[0] + h for v in kept for h in range(1, block_horizon + 1)} - set(gaps))
    if missing:
        raise KeyError(f"no statutory gap for target years {missing}")
    out = np.array(
        [[gaps[v[0] + h] for h in range(1, block_horizon + 1)] for v in kept], dtype=float
    )
    return out - out.mean(axis=0, keepdims=True)


def n_distinct_paths(n_vintages, n_horizons, block_horizon=BLOCK_HORIZON):
    """Distinct error paths the block bootstrap can produce."""
    n_blocks = 1 + max(b for b, _ in horizon_error_schedule(n_horizons, block_horizon))
    return n_vintages**n_blocks


# ── Simulation ───────────────────────────────────────────────────────────


def horizon_error_schedule(n_horizons, block_horizon):
    """For horizons 1..n: (block number, horizon within that block's vintage).

    Block 0 covers horizons 1..H directly. Later blocks each cover up to H-1
    horizons using their vintage's horizons 2..H; a final partial block takes
    that vintage's longest horizons.
    """
    schedule = [(0, h) for h in range(1, min(n_horizons, block_horizon) + 1)]
    remaining = n_horizons - len(schedule)
    block = 0
    while remaining > 0:
        block += 1
        length = min(remaining, block_horizon - 1)
        start = block_horizon - length + 1
        schedule.extend((block, h) for h in range(start, block_horizon + 1))
        remaining -= length
    return schedule


def simulate_growth_paths(
    central_cpi,
    central_earnings,
    growth_years,
    forecast_year,
    blocks,
    n_draws=N_DRAWS,
    seed=MC_SEED,
    demean=False,
    gaps=None,
    first_year_cpi_shocks=None,
):
    """Draws of CPI and earnings growth, each (n_draws, len(growth_years)).

    ``central_*`` map calendar year to growth. ``blocks`` is the output of
    :func:`error_blocks`. ``demean`` removes each horizon's mean historical
    error first, centring the draws on the OBR forecast.
    ``gaps`` (from :func:`gap_blocks`, same shape as ``blocks``) is added to
    the errors cell by cell, turning proxy errors into statutory-input errors.
    ``first_year_cpi_shocks`` (historical August-to-September changes in the
    CPI 12-month rate) is resampled onto the forecast-year CPI, whose
    earnings leg is published but whose September CPI is not yet; without it
    the forecast year is fixed.
    """
    blocks = np.asarray(blocks, dtype=float)
    if demean:
        blocks = blocks - blocks.mean(axis=0, keepdims=True)
    if gaps is not None:
        if np.shape(gaps) != blocks.shape:
            raise ValueError("gaps must have the same shape as blocks")
        blocks = blocks + np.asarray(gaps, dtype=float)
    n_vintages, block_horizon, _ = blocks.shape
    horizons = [g - forecast_year for g in growth_years]
    if min(horizons) < 0 or max(horizons) < 1:
        raise ValueError(f"growth years {growth_years} must run from the forecast year {forecast_year} forward")
    schedule = horizon_error_schedule(max(horizons), block_horizon)
    n_blocks = 1 + max(b for b, _ in schedule)

    rng = np.random.default_rng(seed)
    picks = rng.integers(0, n_vintages, size=(n_draws, n_blocks))

    cpi = np.empty((n_draws, len(growth_years)))
    earnings = np.empty((n_draws, len(growth_years)))
    for j, (year, h) in enumerate(zip(growth_years, horizons)):
        if h == 0:
            # The forecast year sets the April 2027 uprating: earnings are
            # published; September CPI is drawn around August if shocks given.
            err = np.zeros((n_draws, 2))
            if first_year_cpi_shocks is not None:
                shocks = np.asarray(first_year_cpi_shocks, dtype=float)
                err[:, 0] = np.random.default_rng(seed + 2).choice(shocks, size=n_draws)
        else:
            block, vintage_h = schedule[h - 1]
            err = blocks[picks[:, block], vintage_h - 1, :]
        cpi[:, j] = central_cpi[year] + err[:, 0]
        earnings[:, j] = central_earnings[year] + err[:, 1]
    return cpi, earnings


def mean_error_by_horizon(blocks):
    """{variable: {horizon: mean error}} over the vintages in ``blocks``."""
    means = np.asarray(blocks).mean(axis=0)
    return {
        var: {str(h + 1): float(means[h, k]) for h in range(means.shape[0])}
        for k, var in enumerate(VARIABLES)
    }


def bias_label(blocks):
    """Plain description of the mean historical error carried by raw draws."""
    means = mean_error_by_horizon(blocks)

    def describe(var, under, over):
        values = [100 * v for v in means[var].values()]
        lo, hi = min(values), max(values)
        direction = under if lo > 0 else over if hi < 0 else "mixed-sign mean error"
        return f"{var.upper() if var == 'cpi' else var} {direction} {lo:+.2f} to {hi:+.2f}pp"

    return (
        "includes the OBR's historical forecast bias (mean outturn minus forecast, "
        "horizons 1-4): "
        + describe("cpi", "under-forecast", "over-forecast")
        + "; "
        + describe("earnings", "under-forecast", "over-forecast")
    )


def indices_from_growth(cpi, earnings):
    """Per-policy uprating rates and cumulative index, arrays (n_draws, n_years).

    Column j of the growth arrays is the growth that sets uprating year j.
    """
    rates = {p: rule_rate(p, cpi, earnings) for p in POLICIES}
    index = {p: np.cumprod(1 + r, axis=1) for p, r in rates.items()}
    return rates, index


def _percentiles(values, qs):
    return {f"p{q}": float(np.percentile(values, q)) for q in qs}


def run_monte_carlo(
    central_cpi,
    central_earnings,
    uprating_years,
    forecast_year,
    blocks,
    final_year_spend_bn,
    central_final_index,
    n_draws=N_DRAWS,
    seed=MC_SEED,
    demean=False,
    gaps=None,
    first_year_cpi_shocks=None,
):
    """Monte Carlo summary in the results-file ``uncertainty`` shape.

    ``final_year_spend_bn`` is baseline (triple lock, central) basic + new
    State Pension spend in the final uprating year; ``central_final_index``
    the triple-lock cumulative index behind it.
    """
    growth_years = [y - 1 for y in uprating_years]
    cpi, earnings = simulate_growth_paths(
        central_cpi, central_earnings, growth_years, forecast_year, blocks,
        n_draws=n_draws, seed=seed, demean=demean, gaps=gaps,
        first_year_cpi_shocks=first_year_cpi_shocks,
    )
    return summarise_draws(cpi, earnings, uprating_years, final_year_spend_bn, central_final_index)


def summarise_draws(cpi, earnings, uprating_years, final_year_spend_bn, central_final_index):
    """Cost percentiles, fan, floor probability and representative paths for any draws.

    ``cpi`` and ``earnings`` are (n_draws, n_years) growth arrays whose column
    j sets uprating year ``uprating_years[j]``.
    """
    growth_years = [y - 1 for y in uprating_years]
    n_draws = cpi.shape[0]
    rates, index = indices_from_growth(cpi, earnings)
    spend_per_index = final_year_spend_bn / central_final_index
    zero_floor = {p: zero_floor_binds(p, cpi, earnings) for p in ALTERNATIVES}
    any_zero = np.logical_or.reduce([z.any(axis=1) for z in zero_floor.values()])

    cost = {
        alt: spend_per_index * (index["triple_lock"][:, -1] - index[alt][:, -1])
        for alt in ALTERNATIVES
    }
    summary = {
        alt: {**_percentiles(c, QUANTILES), "mean": float(c.mean()), "basis": "gross"}
        for alt, c in cost.items()
    }
    fan = {
        p: {
            str(y): _percentiles(index[p][:, j], FAN_QUANTILES)
            for j, y in enumerate(uprating_years)
        }
        for p in POLICIES
    }
    summary_pct = {
        alt: {
            **_percentiles(100 * c / final_year_spend_bn, QUANTILES),
            "basis": "gross, % of final-year basic + new State Pension spend under the central triple lock",
        }
        for alt, c in cost.items()
    }
    binds = floor_binds(cpi, earnings)
    prob_floor = {str(y): float(binds[:, j].mean()) for j, y in enumerate(uprating_years)}

    ranking = cost[REPRESENTATIVE_RANKING_POLICY]
    representative = {}
    for q in FAN_QUANTILES:
        target = np.percentile(ranking, q)
        i = int(np.argmin(np.abs(ranking - target)))
        representative[f"p{q}"] = {
            "draw": i,
            "ranked_on": f"final-year cost of triple lock vs {REPRESENTATIVE_RANKING_POLICY}",
            "approx_cost_of_triple_lock_vs_bn": {alt: float(cost[alt][i]) for alt in ALTERNATIVES},
            "cpi": {str(g): float(cpi[i, j]) for j, g in enumerate(growth_years)},
            "earnings": {str(g): float(earnings[i, j]) for j, g in enumerate(growth_years)},
            "keys": "cpi/earnings keyed by growth (calendar) year; uprating keyed by fiscal year it sets",
            "uprating": {
                p: {str(y): float(rates[p][i, j]) for j, y in enumerate(uprating_years)}
                for p in POLICIES
            },
        }

    return {
        "n_draws": int(n_draws),
        "cost_of_triple_lock_vs": summary,
        "cost_of_triple_lock_vs_pct_of_spend": summary_pct,
        "zero_floor": {
            "share_of_draws_any_rule": float(any_zero.mean()),
            "share_of_draws_by_rule": {p: float(z.any(axis=1).mean()) for p, z in zero_floor.items()},
            "note": "share of draws in which a rule's index is negative in at least one "
            "year, so the no-cash-cut floor (0%) sets its uprating",
        },
        "fan": fan,
        "prob_triple_lock_binds_on_floor": prob_floor,
        "representative_paths": representative,
        "distinct_paths": int(len(np.unique(np.round(np.c_[cpi, earnings], 10), axis=0))),
    }
