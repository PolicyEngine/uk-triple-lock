"""Backtests of the forecast-distribution methods against realised CPI and earnings.

Both backtests take each OBR forecast as an origin and score the four years it
targets. Every method is fitted on data dated before the origin; the data are
today's revised ONS and OBR figures, not those available at the time, and the
model design (the monthly model's lag grid, its furlough exclusion, the shock
distributions) was chosen with the whole sample in view.

Calendar backtest (``run_backtest``): the calendar-year measures the OBR forecasts
---------------------------------------------------------------------------------
Test A (chronological): origins are the OBR spring forecasts with at least two
earlier forecasts whose four target years were all published, March 2016 to March
2021. At origin v:

* the VAR methods (ts_methods) are fitted on annual history to v-1 (calendar CPI
  and OBR-definition earnings), simulate years v..v+4 and are calibrated to the
  OBR forecast for v+1..v+4 by shifting or entropy tilting;
* the block bootstrap adds the errors of those earlier forecasts to the OBR
  forecast, de-meaned by their mean (the construction an earlier version of this
  dashboard used, without the statutory gaps) and raw (not calibrated), one path per earlier forecast;
* ``iid_normal``: independent normal errors per series and horizon, with the SD of
  the same earlier errors;
* ``obr_point``: the OBR forecast with no uncertainty.

Test B: all 12 forecasts from the June 2010 Budget to March 2021; the block
bootstrap uses every other forecast (leave-one-out, so it sees later forecasts'
errors). Test C: the VAR methods alone, uncalibrated, origins 2000-2021, scored
on ONS history. Dependence ablations (calendar backtest only): each VAR's
shifted draws with years shuffled across draws (``+no_autocorrelation``:
marginals and same-year co-movement kept) and with the earnings paths shuffled
against CPI (``+no_comovement``).

Tests A and B score against the OBR outturns the forecasts target. Scores, on
the 8-vector of 2 series x 4 years in pp (lower is better unless noted):

* ``energy``: energy score, the multivariate generalisation of CRPS (itself the
  quantile loss integrated over all quantile levels); weakly sensitive to
  dependence.
* ``vs_serial``, ``vs_cross``, ``vs_crosslag``: variogram score (p = 0.5) over
  pairs of the same series in different years (autoregression), the two series
  in the same year (co-movement) and the two series in different years.
* ``path_inside_80``: share of origins whose realised 8-vector is inside the
  forecast's central 80% by band depth (multivariate PIT >= 0.2; 80% if
  calibrated; null for a single-path forecast); ``crps`` and ``inside_80`` are
  the per-value versions.
* ``cum_cpi_crps``, ``cum_earnings_crps``: CRPS of 4-year cumulative growth, whose
  spread depends on the autocorrelation.
* For the gap between the triple lock and each alternative after four upratings
  (% of the triple-lock level, the alternative starting at the first uprating):
  CRPS and whether the outcome fell inside the 10-90% interval. With fewer than
  10 draws (the block bootstrap has 2-7 at the chronological origins) that
  interval is the draws' min-max range; ``min_draws``/``max_draws`` record it.

Statutory backtest (``run_statutory_backtest``): what the triple lock uses
--------------------------------------------------------------------------
Tests A and B only, scored on the published September CPI and May-July AWE
total pay growth. The monthly models (ts_monthly) build those inputs from
simulated months, tilted on the calendar measures to the OBR forecast,
shifted to it (``monthly_boot+shift``: the drift shift the paths and the
expected value use) or neither (``monthly_boot+raw``); the annual VAR's draws are used as statutory
inputs directly or with resampled historical statutory gaps added; the block
bootstrap adds the historical statutory gaps of the same years. Every score is computed twice, for
the two treatments of April 2022 (determination year 2021): the published
May-July 2021 earnings growth, and earnings equal to CPI, as the law set it
when the earnings leg was suspended.
"""

import csv
from pathlib import Path

import numpy as np

from .config import CENTRAL_RATE_DECIMALS, ERROR_CSV
from .rules import rates_matrix
from .ts_methods import (
    METHODS,
    band_depth_prerank,
    crps,
    energy_score,
    interval_hit,
    resample,
    shift,
    shuffle_series,
    shuffle_years,
    tilt,
    variogram_score,
)
from .history_data import error_blocks, gap_blocks, history, load_forecast_errors, load_statutory_gaps

N_DRAWS = 5000
H = 4
GAP_ALTERNATIVES = ["burnham_2030"]
LONG_ORIGINS = range(2000, 2022)
# The April 2022 uprating (determination year 2021): its earnings leg was suspended in law.
SUSPENDED_DETERMINATION_YEAR = 2021
APRIL_2022_TREATMENTS = ("published", "suspended")


def load_forecasts(path=ERROR_CSV):
    forecasts, outturns = {}, {}
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            v = (int(r["year_forecast_made"]), r["forecast_vintage"].strip())
            k = (r["variable"].strip().lower(), int(r["horizon_years"]))
            forecasts.setdefault(v, {})[k] = float(r["forecast"])
            if r["outturn"].strip():
                outturns.setdefault(v, {})[k] = float(r["outturn"])
    return forecasts, outturns


def gap_pct(paths, decimals=CENTRAL_RATE_DECIMALS):
    """% gap between the triple lock and each alternative after the paths' upratings.

    The inputs and rates are rounded as in the fiscal runs (rules.round_rate, 0.1 point), so the backtests score the
    same policy arithmetic as the expected saving; ``decimals=None`` gives the unrounded gap.
    """
    cpi, earnings = paths[:, :, 0], paths[:, :, 1]
    level = {p: np.prod(1 + rates_matrix(p, cpi, earnings, decimals=decimals), axis=1)
             for p in ["triple_lock", *GAP_ALTERNATIVES]}
    return {a: 100 * (level["triple_lock"] - level[a]) / level["triple_lock"] for a in GAP_ALTERNATIVES}


def score(draws, outcome, weights=None, seed=0):
    """Scores of draws (n, H, 2) for the realised (H, 2), both decimals."""
    x = 100 * draws.reshape(len(draws), -1)
    y = 100 * outcome.reshape(-1)
    equal = x if weights is None else 100 * resample(draws, weights, N_DRAWS, seed).reshape(N_DRAWS, -1)
    d = x.shape[1]
    serial = [(i, j) for i in range(d) for j in range(i + 1, d) if i % 2 == j % 2]
    cross = [(i, i + 1) for i in range(0, d, 2)]
    crosslag = [(i, j) for i in range(d) for j in range(i + 1, d) if i % 2 != j % 2 and i // 2 != j // 2]
    cum = 100 * (np.prod(1 + draws, axis=1) - 1)
    cum_y = 100 * (np.prod(1 + outcome, axis=0) - 1)
    out = {
        "energy": energy_score(equal, y, seed),
        "vs_serial": variogram_score(equal, y, pairs=serial),
        "vs_cross": variogram_score(equal, y, pairs=cross),
        "vs_crosslag": variogram_score(equal, y, pairs=crosslag),
        "path_pit": band_depth_prerank(equal, y) if len(equal) > 1 else None,
        "n_draws": int(len(draws)),
        "crps": float(np.mean([crps(x[:, j], y[j], weights) for j in range(d)])),
        "inside_80": float(np.mean([interval_hit(x[:, j], y[j], w=weights) for j in range(d)])),
        "cum_cpi_crps": crps(cum[:, 0], cum_y[0], weights),
        "cum_earnings_crps": crps(cum[:, 1], cum_y[1], weights),
    }
    g, gy = gap_pct(draws), gap_pct(outcome[None])
    for a in GAP_ALTERNATIVES:
        out[f"{a}_crps"] = crps(g[a], gy[a][0], weights)
        out[f"{a}_inside"] = interval_hit(g[a], gy[a][0], w=weights)
        out[f"{a}_realised"] = float(gy[a][0])
    return out


def origin_draws(v, forecasts, blocks, training, hist_years, hist, seed):
    fc = np.array([[forecasts[v][(var, h)] for var in ("cpi", "earnings")] for h in range(1, H + 1)])
    data = hist[[i for i, y in enumerate(hist_years) if y <= v[0] - 1]]
    out = {}
    for name, method in METHODS.items():
        paths, _ = method(data, H + 1, N_DRAWS, seed)
        paths = paths[:, 1:]
        shifted = shift(paths, fc)
        out[f"{name}+shift"] = (shifted, None)
        out[f"{name}+tilt"] = (paths, tilt(paths, fc)[0])
        out[f"{name}+shift+no_autocorrelation"] = (shuffle_years(shifted, seed), None)
        out[f"{name}+shift+no_comovement"] = (shuffle_series(shifted, seed), None)
    err = blocks[training]
    out["block_bootstrap_demeaned"] = (fc[None] + err - err.mean(axis=0, keepdims=True), None)
    out["block_bootstrap_raw"] = (fc[None] + err, None)
    sd = err.std(axis=0, ddof=1)
    out["iid_normal"] = (fc[None] + np.random.default_rng(seed).standard_normal((N_DRAWS, H, 2)) * sd[None], None)
    out["obr_point"] = (fc[None], None)
    return out


def _summary(rows):
    methods = list(dict.fromkeys(r["method"] for r in rows))
    table = {}
    for m in methods:
        rs = [r for r in rows if r["method"] == m]
        pits = [r["path_pit"] for r in rs]
        table[m] = {
            "n_origins": len(rs),
            "min_draws": min(r["n_draws"] for r in rs),
            "max_draws": max(r["n_draws"] for r in rs),
            "energy": round(float(np.mean([r["energy"] for r in rs])), 3),
            **{k: round(float(np.mean([r[k] for r in rs])), 3)
               for k in ("vs_serial", "vs_cross", "vs_crosslag", "cum_cpi_crps", "cum_earnings_crps")},
            "path_inside_80_pct": (None if None in pits else round(100 * float(np.mean([p >= 0.2 for p in pits])), 1)),
            "path_pits": None if None in pits else [round(p, 2) for p in pits],
            "crps_pp": round(float(np.mean([r["crps"] for r in rs])), 3),
            "inside_80_pct": round(100 * float(np.mean([r["inside_80"] for r in rs])), 1),
            **{f"{a}_crps_pp": round(float(np.mean([r[f"{a}_crps"] for r in rs])), 3) for a in GAP_ALTERNATIVES},
            **{f"{a}_inside": int(sum(r[f"{a}_inside"] for r in rs)) for a in GAP_ALTERNATIVES},
            "burnham_2030_inside_by_origin": [bool(r["burnham_2030_inside"]) for r in rs],
        }
    return table


def run_backtest():
    forecasts, outturns = load_forecasts()
    blocks, kept = error_blocks(load_forecast_errors(ERROR_CSV))
    hist_years, hist = history(first_year=1989, last_year=2025)
    hist_years = list(hist_years)

    def rolling(v):
        return [j for j, u in enumerate(kept) if u[0] + H <= v[0] - 1]

    def leave_one_out(v):
        return [j for j, u in enumerate(kept) if u != v]

    def test(origins, training_fn):
        rows = []
        for v in origins:
            y = np.array([[outturns[v][(var, h)] for var in ("cpi", "earnings")] for h in range(1, H + 1)])
            draws = origin_draws(v, forecasts, blocks, training_fn(v), hist_years, hist, seed=v[0])
            for method, (d, w) in draws.items():
                rows.append({"origin": v[1], "method": method, **score(d, y, w, seed=v[0])})
        return rows

    rows_a = test([v for v in kept if len(rolling(v)) >= 2], rolling)
    rows_b = test(kept, leave_one_out)
    rows_c = []
    for t in LONG_ORIGINS:
        data = hist[[i for i, y in enumerate(hist_years) if y <= t - 1]]
        y = hist[[hist_years.index(t + h) for h in range(1, H + 1)]]
        for name, method in METHODS.items():
            paths, _ = method(data, H + 1, N_DRAWS, t)
            paths = paths[:, 1:]
            for variant, p in ((name, paths), (f"{name}+no_autocorrelation", shuffle_years(paths, t)),
                               (f"{name}+no_comovement", shuffle_series(paths, t))):
                rows_c.append({"origin": str(t), "method": variant, **score(p, y, None, t)})
    origins_a = list(dict.fromkeys(r["origin"] for r in rows_a))
    return {
        "chronological": {"origins": origins_a, "methods": _summary(rows_a)},
        "all_origins_leave_one_out": {"origins": [v[1] for v in kept], "methods": _summary(rows_b)},
        "var_uncalibrated_long": {"origins": [str(t) for t in LONG_ORIGINS], "methods": _summary(rows_c)},
        "realised_gap_pct": {r["origin"]: {a: round(r[f"{a}_realised"], 2) for a in GAP_ALTERNATIVES}
                             for r in rows_b if r["method"] == "obr_point"},
    }


# ── Backtest on the statutory inputs (what the triple lock actually uses) ───


def statutory_outturns(path=None, suspend_2022=False, suspended_years=None):
    """{growth year: (September CPI, May-July AWE)} from the published inputs file.

    ``suspend_2022`` sets the April 2022 uprating's earnings input to its CPI, as the law did.
    """
    from .config import ACTUALS_CSV

    with Path(path or ACTUALS_CSV).open(newline="") as f:
        out = {int(r["determination_year"]): (float(r["cpi_september_12m"]), float(r["awe_total_pay_may_jul_3m_yoy"]))
               for r in csv.DictReader(f) if r["cpi_september_12m"] and r["awe_total_pay_may_jul_3m_yoy"]}
    regime = (SUSPENDED_DETERMINATION_YEAR,) if suspend_2022 and suspended_years is None else (suspended_years or ())
    for year in regime:
        if year in out:
            c = out[year][0]
            out[year] = (c, c)
    return out


def statutory_gap_history(last_year):
    """{year: (Sep CPI - calendar CPI, May-July AWE - OBR-definition earnings)} to ``last_year``, from ONS data."""
    from . import ts_monthly as TM

    months, cpi, awe, _ = TM.levels((last_year, 12))
    years = list(range(2001, last_year + 1))
    stat = TM.annual_measures(months, cpi[None], awe[None], years)
    hist_years, hist = history(first_year=2001, last_year=last_year)
    cal = {y: hist[i] for i, y in enumerate(hist_years)}
    return {y: (float(stat["statutory_cpi"][0, j] - cal[y][0]), float(stat["statutory_earnings"][0, j] - cal[y][1]))
            for j, y in enumerate(years)}


def switches(paths):
    """Times the lead passes between CPI and earnings across consecutive years, per path.

    A year in which they are equal keeps the previous lead, so it is not a switch.
    """
    s = np.sign(paths[:, :, 1] - paths[:, :, 0])
    for t in range(1, s.shape[1]):
        s[:, t] = np.where(s[:, t] == 0, s[:, t - 1], s[:, t])
    return np.sum((s[:, 1:] != s[:, :-1]) & (s[:, :-1] != 0), axis=1)


def statutory_origin_draws(v, forecasts, blocks, kept, training, seed):
    """Draws of the statutory inputs (n, H, 2) for v's target years, with weights, for every method."""
    from . import ts_monthly as TM
    from .config import CROSSCHECK_CSV

    fc = np.array([[forecasts[v][(var, h)] for var in ("cpi", "earnings")] for h in range(1, H + 1)])
    years = [v[0] + h for h in range(1, H + 1)]
    out = {}
    # Monthly models: statutory inputs built from simulated months, tilted on the calendar measures.
    for kind in ("gauss", "boot", "tcop"):
        m, _ = TM.paths(years, N_DRAWS, seed, kind, end_obs=(v[0] - 1, 12))
        stat = np.stack([m["statutory_cpi"], m["statutory_earnings"]], axis=2)
        cal = np.stack([m["calendar_cpi"], m["calendar_earnings"]], axis=2)
        out[f"monthly_{kind}+tilt"] = (stat, tilt(cal, fc)[0])
        if kind == "boot":
            out["monthly_boot+raw"] = (stat, None)
            # The calibration the paths and the expected value use: the drift shifted to the forecast's means.
            ms, _ = TM.paths(years, N_DRAWS, seed, kind, end_obs=(v[0] - 1, 12),
                             calendar_target={y: tuple(fc[j]) for j, y in enumerate(years)})
            out["monthly_boot+shift"] = (np.stack([ms["statutory_cpi"], ms["statutory_earnings"]], axis=2), None)
    # Annual VAR on the calendar measures: statutory = calendar (the gap at zero), and with gap blocks.
    hist_years, hist = history(first_year=1989, last_year=v[0] - 1)
    paths, _ = METHODS["boot_var"](hist, H + 1, N_DRAWS, seed)
    paths = paths[:, 1:]
    w = tilt(paths, fc)[0]
    out["annual_boot_var+tilt+no_gaps"] = (paths, w)
    gaps = statutory_gap_history(v[0] - 1)
    starts = [y for y in gaps if all(y + k in gaps for k in range(H))]
    gb = np.array([[gaps[y + k] for k in range(H)] for y in starts])
    gb = gb - gb.mean(axis=0, keepdims=True)
    pick = np.random.default_rng(seed + 7).integers(0, len(gb), size=N_DRAWS)
    out["annual_boot_var+tilt+gap_blocks"] = (paths + gb[pick], w)
    # The OBR forecast-error bootstrap: past forecasts' errors plus the same years' statutory gaps, de-meaned.
    kept_t = [kept[j] for j in training]
    err = blocks[training] - blocks[training].mean(axis=0, keepdims=True)
    err = err + gap_blocks(kept_t, load_statutory_gaps(CROSSCHECK_CSV), H)
    out["block_bootstrap_statutory"] = (fc[None] + err, None)
    sd = err.std(axis=0, ddof=1)
    out["iid_normal"] = (fc[None] + np.random.default_rng(seed).standard_normal((N_DRAWS, H, 2)) * sd[None], None)
    out["obr_point"] = (fc[None], None)
    return out


def run_statutory_backtest():
    """Both tests, each scored under both treatments of April 2022 (the draws are the same)."""
    forecasts, _ = load_forecasts()
    blocks, kept = error_blocks(load_forecast_errors(ERROR_CSV))
    outturns = {t: statutory_outturns(suspend_2022=t == "suspended") for t in APRIL_2022_TREATMENTS}

    def rolling(v):
        return [j for j, u in enumerate(kept) if u[0] + H <= v[0] - 1]

    def leave_one_out(v):
        return [j for j, u in enumerate(kept) if u != v]

    def test(origins, training_fn):
        rows = {t: [] for t in APRIL_2022_TREATMENTS}
        for v in origins:
            draws = statutory_origin_draws(v, forecasts, blocks, kept, training_fn(v), v[0])
            for t in APRIL_2022_TREATMENTS:
                y = np.array([outturns[t][v[0] + h] for h in range(1, H + 1)])
                real_switches = int(switches(y[None])[0])
                for method, (d, w) in draws.items():
                    s = switches(d)
                    wt = np.full(len(d), 1 / len(d)) if w is None else w
                    rows[t].append({"origin": v[1], "method": method, **score(d, y, w, seed=v[0]),
                                    "switches_expected": float(wt @ s), "switches_realised": real_switches})
        return rows

    def summary(rows):
        table = _summary(rows)
        for m in table:
            rs = [r for r in rows if r["method"] == m]
            table[m]["switches_expected"] = round(float(np.mean([r["switches_expected"] for r in rs])), 2)
            table[m]["switches_realised"] = round(float(np.mean([r["switches_realised"] for r in rs])), 2)
        return table

    chrono = [v for v in kept if len(rolling(v)) >= 2]
    rows_a, rows_b = test(chrono, rolling), test(kept, leave_one_out)
    c21, e21 = statutory_outturns()[SUSPENDED_DETERMINATION_YEAR]
    descriptions = {
        "published": f"April 2022 scored on the published May-July 2021 earnings growth ({100 * e21:.1f}%)",
        "suspended": f"April 2022 scored with earnings equal to September 2021 CPI ({100 * c21:.1f}%), as the law "
                     "set it when the earnings leg was suspended",
    }
    return {
        "target": "September CPI 12-month rate and May-July AWE total pay growth (published, latest vintage)",
        "treatments": {
            t: {
                "description": descriptions[t],
                "april_2022_inputs": {"cpi": c21, "earnings": e21 if t == "published" else c21},
                "chronological": {"origins": [v[1] for v in chrono], "methods": summary(rows_a[t])},
                "all_origins_leave_one_out": {"origins": [v[1] for v in kept], "methods": summary(rows_b[t])},
                "realised_gap_pct": {r["origin"]: {a: round(r[f"{a}_realised"], 2) for a in GAP_ALTERNATIVES}
                                     for r in rows_b[t] if r["method"] == "obr_point"},
            }
            for t in APRIL_2022_TREATMENTS
        },
        # The April upratings each origin's four target years set (determination year + 1).
        "origin_april_upratings": {v[1]: [v[0] + h + 1 for h in range(1, H + 1)] for v in kept},
    }


# Model-v2 C1: fixed candidate screen (docs/METHOD.md, pre-registration).
def candidate_score(draws, outcome, seed=0, *, target_years=None, suspended_years=(),
                    exclude_legal_constants=False):
    """Joint statutory scores, in pp for growth and fractions for floor frequency.

    Bias always means forecast mean minus realised value. The terminal policy
    gap uses the existing unrounded backtest convention (plan starts at year 1).
    """
    if exclude_legal_constants and (target_years is None or len(target_years) != len(outcome)):
        raise ValueError("C2 legal exclusions require the determination years")
    active = np.ones(len(outcome), dtype=bool)
    if exclude_legal_constants:
        active = np.array([year not in set(suspended_years) for year in target_years])
        draws, outcome = np.array(draws, copy=True), np.array(outcome, copy=True)
        draws[:, ~active, 1] = draws[:, ~active, 0]
        outcome[~active, 1] = outcome[~active, 0]
    gaps = 100 * (draws[:, :, 1] - draws[:, :, 0])
    observed_gap = 100 * (outcome[:, 1] - outcome[:, 0])
    sw, sy = switches(draws), float(switches(outcome[None])[0])
    floor = (draws[:, :, 1] < 0.025).mean(axis=1)
    fy = float((outcome[:, 1] < 0.025).mean())
    terminal = gap_pct(draws, decimals=None)['burnham_2030']
    ty = float(gap_pct(outcome[None], decimals=None)['burnham_2030'][0])
    x, y = 100 * draws.reshape(len(draws), -1), 100 * outcome.reshape(-1)
    result = {
        'gap_crps': float(np.mean([crps(gaps[:, j], observed_gap[j]) for j in np.flatnonzero(active)])) if active.any() else None,
        'switch_crps': crps(sw, sy), 'floor_crps': crps(floor, fy),
        'energy': energy_score(x, y, seed), 'variogram': variogram_score(x, y),
        'gap_bias_pp': float(gaps[:, active].mean() - observed_gap[active].mean()) if active.any() else None,
        'switch_bias': float(sw.mean() - sy), 'floor_bias': float(floor.mean() - fy),
        'terminal_bias_pp': float(terminal.mean() - ty),
        'annual_gap_coverage': float(np.mean([interval_hit(gaps[:, j], observed_gap[j])
                                              for j in np.flatnonzero(active)])) if active.any() else None,
        'terminal_coverage': float(interval_hit(terminal, ty)),
        'predicted_switches': float(sw.mean()), 'realised_switches': sy,
        'predicted_floor_frequency': float(floor.mean()), 'realised_floor_frequency': fy,
        'predicted_terminal_gap_pct': float(terminal.mean()), 'realised_terminal_gap_pct': ty,
    }
    if exclude_legal_constants:
        # This is a legal-rule mask, never a test of coincidentally equal data.
        result['annual_gap_cells'] = int(active.sum())
        result['annual_gap_excluded_cells'] = int((~active).sum())
        fixed = []
        if not active.any():
            fixed.extend(('gap_crps', 'gap_bias_pp', 'annual_gap_coverage',
                          'terminal_bias_pp', 'terminal_coverage',
                          'predicted_terminal_gap_pct', 'realised_terminal_gap_pct'))
        if active.sum() <= 1:
            # With at most one unsuspended lead there cannot be a lead reversal.
            fixed.extend(('switch_crps', 'switch_bias', 'predicted_switches', 'realised_switches'))
        for name in fixed:
            result[name] = None
        result['legal_fixed_statistics'] = fixed
    return result


def mean_with_overlap_se(values, max_lag=3):
    """Independent and Newey–West SEs, lag 3 for overlapping four-year origins.

    Both are descriptive with this small sample; no independent-origin claim is
    attached to the HAC number. Covariances use n as denominator, with n/(n-1)
    finite-sample correction to the long-run variance.
    """
    x = np.asarray(values, float)
    n = len(x)
    if n < 2:
        raise ValueError('at least two origins are required')
    z = x - x.mean()
    long_run = float(z @ z / n)
    for lag in range(1, min(max_lag, n - 1) + 1):
        long_run += 2 * (1 - lag / (max_lag + 1)) * float(z[lag:] @ z[:-lag] / n)
    return {'mean': float(x.mean()), 'se_independent': float(x.std(ddof=1) / np.sqrt(n)),
            'se_overlap_hac': float(np.sqrt(max(0, long_run) / (n - 1)))}


def wilson_band(hits, n, z=1.959963984540054):
    """Descriptive binomial band; does not correct overlapping-origin dependence."""
    p, z2 = hits / n, z * z
    mid = (p + z2 / (2 * n)) / (1 + z2 / n)
    radius = z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return [float(mid - radius), float(mid + radius)]


def complete_statutory_origins(forecasts, outturns):
    """Spring origins with all four forecast means and statutory outcomes available.

    Annual calendar outturns/errors need not yet exist: they are not what C2
    scores. Forecast rows with blank outturn/error are still usable means.
    """
    return sorted(v for v, means in forecasts.items()
                  if (v[1].startswith(('March ', 'June 2010 '))
                      and all((variable, h) in means and np.isfinite(means[variable, h])
                              for variable in ('cpi', 'earnings') for h in range(1, H + 1))
                      and all(v[0] + h in outturns for h in range(1, H + 1))))


def weighted_mean_with_overlap_se(values, cell_counts, max_lag=3):
    """Pool annual cells equally; report origin-cluster SEs with their counts.

    The influence series is n*w_i*(x_i - pooled_mean), for normalized cell
    weights w_i. C1's independent and Bartlett-lag-3 conventions then apply.
    """
    x, counts = np.asarray(values, float), np.asarray(cell_counts, float)
    total = counts.sum()
    if len(x) < 2 or total <= 0:
        raise ValueError('at least two scored origins and one annual cell are required')
    mean = float(counts @ x / total)
    influence = len(x) * counts / total * (x - mean)
    se = mean_with_overlap_se(influence, max_lag)
    se.update(mean=mean, n_cells=int(total), n_scored_origins=len(x))
    return se


def run_candidate_backtest(n=N_DRAWS, log=print, *, screen="c1", suspended_years=None):
    """Score all C1 forms on the existing A/B origins, with no post-origin training.

    Unlike the older forecast-error bootstrap, none of these five candidates
    uses a leave-one-out error pool. A is the pre-existing chronological subset
    of B, so its candidate forecasts are identical and can be reused.
    """
    from .ts_uncertainty import CANDIDATES, candidate_paths
    from .ts_methods import pit

    if screen not in ('c1', 'c2'):
        raise ValueError('screen must be c1 or c2')
    regime = tuple((SUSPENDED_DETERMINATION_YEAR,) if suspended_years is None else suspended_years)
    forecasts, _ = load_forecasts()
    published = statutory_outturns()
    if screen == 'c2':
        kept = complete_statutory_origins(forecasts, published)
    else:
        _, kept = error_blocks(load_forecast_errors(ERROR_CSV))
    chrono = [v for v in kept if sum(u[0] + H <= v[0] - 1 for u in kept) >= 2]
    outturns = {'published': published, 'suspended': statutory_outturns(suspended_years=regime)}
    rows, failures = [], []
    for v in kept:
        years = [v[0] + h for h in range(1, H + 1)]
        target = {y: tuple(forecasts[v][(var, h)] for var in ('cpi', 'earnings'))
                  for h, y in enumerate(years, start=1)}
        for form in CANDIDATES:
            log(f'Backtest {v[1]} {form}')
            try:
                m, info = candidate_paths(form, years, n, v[0], end_obs=(v[0] - 1, 12), calendar_target=target)
                draws = np.stack([m['statutory_cpi'], m['statutory_earnings']], axis=2)
                if not np.isfinite(draws).all():
                    raise ValueError('non-finite statutory draws')
                for treatment in APRIL_2022_TREATMENTS:
                    d = draws.copy()
                    if treatment == 'suspended':
                        for j, year in enumerate(years):
                            if year in regime:
                                d[:, j, 1] = d[:, j, 0]
                    y = np.array([outturns[treatment][yy] for yy in years])
                    metrics = candidate_score(d, y, v[0], target_years=years, suspended_years=regime,
                                              exclude_legal_constants=screen == 'c2' and treatment == 'suspended')
                    if not all(np.isfinite(x) for x in metrics.values() if isinstance(x, (int, float))):
                        raise ValueError('non-finite scores')
                    rows.append({'origin': v[1], 'origin_year': v[0], 'target_years': years,
                                 'chronological': v in chrono, 'form': form, 'treatment': treatment,
                                 'model': info, **metrics})
            except (ValueError, np.linalg.LinAlgError, FloatingPointError) as e:
                failures.append({'origin': v[1], 'form': form, 'error': str(e)})
    summaries = {}
    for test, origins in (('A', chrono), ('B', kept)):
        summaries[test] = {}
        for treatment in APRIL_2022_TREATMENTS:
            summaries[test][treatment] = {}
            for form in CANDIDATES:
                selected = [r for r in rows if r['form'] == form and r['treatment'] == treatment
                            and (test == 'B' or r['chronological'])]
                summary = {'n_origins': len(selected), 'expected_origins': len(origins)}
                if len(selected) >= 2:
                    metadata = ('origin', 'origin_year', 'target_years', 'chronological', 'form',
                                'treatment', 'model', 'annual_gap_cells', 'annual_gap_excluded_cells',
                                'legal_fixed_statistics')
                    fields = [k for k in selected[0] if k not in metadata]
                    for k in fields:
                        eligible = [r for r in selected if r[k] is not None]
                        if not eligible:
                            summary[k] = {'mean': None, 'n_scored_origins': 0, 'excluded_by_law': True}
                        elif len(eligible) == 1:
                            summary[k] = {'mean': eligible[0][k], 'n_scored_origins': 1,
                                          'se_independent': None, 'se_overlap_hac': None}
                        elif screen == 'c2' and treatment == 'suspended' and k in (
                                'gap_crps', 'gap_bias_pp', 'annual_gap_coverage'):
                            summary[k] = weighted_mean_with_overlap_se(
                                [r[k] for r in eligible], [r['annual_gap_cells'] for r in eligible])
                        else:
                            summary[k] = mean_with_overlap_se([r[k] for r in eligible])
                    terminal = [r for r in selected if r['terminal_coverage'] is not None]
                    hits = int(sum(r['terminal_coverage'] for r in terminal))
                    summary['terminal_coverage']['hits'] = hits
                    if terminal:
                        summary['terminal_coverage']['wilson95_independent'] = wilson_band(hits, len(terminal))
                    if screen == 'c2':
                        summary['annual_gap_cells'] = sum(r.get('annual_gap_cells', H) for r in selected)
                        summary['annual_gap_excluded_cells'] = sum(r.get('annual_gap_excluded_cells', 0) for r in selected)
                        summary['terminal_scored_origins'] = len(terminal)
                        summary['terminal_excluded_origins'] = len(selected) - len(terminal)
                summaries[test][treatment][form] = summary
    # Past-years check is uncalibrated: no fifteen-year OBR forecast at 2011.
    past, years = {}, list(range(2011, 2026))
    for form in CANDIDATES:
        log(f'Past-years check {form}')
        try:
            m, _ = candidate_paths(form, years, n, 2011, end_obs=(2010, 12))
            raw = np.stack([m['statutory_cpi'], m['statutory_earnings']], axis=2)
            if not np.isfinite(raw).all():
                raise ValueError('non-finite past-years statutory draws')
            past[form] = {}
            for treatment in APRIL_2022_TREATMENTS:
                d = raw.copy()
                if treatment == 'suspended':
                    for j, year in enumerate(years):
                        if year in regime:
                            d[:, j, 1] = d[:, j, 0]
                g = gap_pct(d, decimals=None)['burnham_2030']
                y = np.array([outturns[treatment][yy] for yy in years])
                realised = float(gap_pct(y[None], decimals=None)['burnham_2030'][0])
                if not np.isfinite(g).all() or not np.isfinite(realised):
                    raise ValueError('non-finite past-years policy gaps')
                past[form][treatment] = {'realised_gap_pct': realised,
                                         'realised_percentile': 100 * pit(g, realised),
                                         'mean_gap_pct': float(g.mean()),
                                         'p10_p50_p90': np.quantile(g, [0.1, 0.5, 0.9]).tolist()}
        except (ValueError, np.linalg.LinAlgError, FloatingPointError) as e:
            past[form] = {'error': str(e)}
    result = {'n_draws': n, 'origins': {'A': [v[1] for v in chrono], 'B': [v[1] for v in kept]},
            'bias_convention': 'forecast mean minus realised; positive = overprediction',
            'vintage_note': 'Latest revised ONS/OBR inputs; model design saw the full sample; origins overlap.',
            'suspension': 'Applied to both forecasts and outturns for determination year 2021.',
            'rows': rows, 'failures': failures, 'scores': summaries, 'past_years': past}
    if screen == 'c2':
        result.update(screen='c2', suspended_determination_years=list(regime),
                      suspension=f'Applied to both forecasts and outturns for determination years {list(regime)}.',
                      exclusion='Statistics fixed by the suspended-earnings legal rule; annual cells equally weighted.')
    return result
