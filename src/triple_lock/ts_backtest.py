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


def statutory_outturns(path=None, suspend_2022=False):
    """{growth year: (September CPI, May-July AWE)} from the published inputs file.

    ``suspend_2022`` sets the April 2022 uprating's earnings input to its CPI, as the law did.
    """
    from .config import ACTUALS_CSV

    with Path(path or ACTUALS_CSV).open(newline="") as f:
        out = {int(r["determination_year"]): (float(r["cpi_september_12m"]), float(r["awe_total_pay_may_jul_3m_yoy"]))
               for r in csv.DictReader(f) if r["cpi_september_12m"] and r["awe_total_pay_may_jul_3m_yoy"]}
    if suspend_2022:
        c = out[SUSPENDED_DETERMINATION_YEAR][0]
        out[SUSPENDED_DETERMINATION_YEAR] = (c, c)
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
