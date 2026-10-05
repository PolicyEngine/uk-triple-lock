"""The expected saving from the Burnham plan: a calibrated distribution of paths and a stratified sample of full runs.

Why an expected value
---------------------
The triple lock takes a maximum each year, and the Burnham plan pays at least
max(CPI, 2.5%) but otherwise only what keeps the pension on its 2029-30 earnings
path. The saving comes from years when the higher of CPI and 2.5% runs ahead of
earnings: the triple lock keeps that gain for good, while the Burnham plan's
level waits for earnings to catch up. A single central path, on which earnings
lead from 2031, gives almost none. The expected saving is a weighted mean of
the saving over paths, each saving a full model run.

1. Draws
--------
``N_DRAWS`` paths of the monthly model (ts_monthly: a VAR on monthly log
changes of the CPI index and AWE, residual-bootstrap shocks), August 2026 to
December 2039. Every annual measure, the statutory inputs (September CPI,
May-July AWE) and the calendar-year ones, comes from the same simulated months.

2. Calibration
--------------
* Means: the smoothest monthly drift path that makes the draws' mean calendar
  CPI and earnings growth equal the central path in every year 2027-2039
  (``ts_monthly.shift_to_calendar_means``). Every draw moves by the same
  amount, so the shocks and their dependence are the model's own. (Entropy
  tilting to the same means, the earlier approach, keeps about 1,000 of 50,000
  draws' worth of weight: the model's own means sit far from the OBR's.)
* Dynamics: entropy tilting (minimal change in weights) so that, jointly with
  the means, the expected per-path variance of the statutory real-wage gap
  (May-July AWE minus September CPI, 2026-2038) and the expected rate at which
  the lead passes between the two inputs match history.
* Not targeted: the share of years in which both inputs are below 2.5%. The
  OBR's central forecast itself has earnings below 2.5% from 2027 to 2030, so
  matching history's lower share would fight the means. It is reported.

The history window and the treatment of 2020-21 (furlough-era earnings) set
the dynamics targets; every combination is solved and reported. The primary
is chosen on the expected-value backtest (``ev_backtest``) and the past-years
check: the drift shift alone (the OBR's means, the model's own dynamics). In
the backtest, tilting to the dynamics of the history before each origin made
the expected gap more biased, not less, and the past-years check puts the
realised 2012-start gap at the 55th percentile of the untilted model fitted
before 2011 but the 93rd of the tilted one. The dynamics tilts are
sensitivities, computed from the same full runs by reweighting.

3. Full runs
------------
The draws with identical rates under both rules in every year have a saving of
exactly zero (both runs get the same inputs); they form their own stratum and
one of them is run to confirm it. The rest are split into ``N_STRATA`` strata
of equal probability on the 2039-40 gap in the full new State Pension (rule
arithmetic on the weekly rate), paths are allocated across strata in
proportion to probability x the gap's spread in the stratum (Neyman), with at
least ``MIN_PER_STRATUM``, and drawn within each stratum with probability
proportional to weight (with replacement). Each is a full model run of both
rules (engine.run_path). The estimate for any output is sum_h W_h x its mean
over stratum h's runs. Its Monte Carlo variance adds path sampling
sum_h W_h^2 s_h^2 / n_h and first phase
sum_h W_h [s_h^2 + (m_h-m)^2] / N_DRAWS, including the zero stratum.
Both components are reported separately and do not measure model uncertainty.
Microcosm runs a paired subsample (the first
paths drawn in each stratum), so the dataset difference is estimated from
paired runs.
"""

import numpy as np

from . import rules, ts_monthly
from .config import (
    SENSITIVITY_DATASET,
    BASE_YEAR,
    CALENDAR_YEARS,
    CENTRAL_RATE_DECIMALS,
    FINAL_YEAR,
    HORIZON,
    STATUTORY_YEARS,
    SWITCH_YEAR,
    TRIPLE_LOCK_FLOOR,
)
from .central import september_cpi_history
from .ts_backtest import switches
from .ts_methods import TiltError, tilt_moments

N_DRAWS = 50_000
SEED = 20260929
KIND = "boot"
MONTHLY_YEARS = [BASE_YEAR, *CALENDAR_YEARS]  # what the monthly model builds: 2026-2039
HISTORY_WINDOWS = {"2001_2025": (2001, 2025), "2010_2025": (2010, 2025)}
TREATMENTS = {
    "covid_excluded": "determination years 2020 and 2021 left out (furlough-era earnings, the months the monthly "
                      "model's fit also leaves out)",
    "suspended": "2021 earnings set to 2021 CPI, as the law set the April 2022 uprating when it suspended the "
                 "earnings leg",
    "published": "the published figures in every year",
}
DYNAMICS = ("gap_variance", "switch_rate")
DIAGNOSTICS = ("gap_variance", "switch_rate", "floor_share")
# Tolerances for the tilt, in each target's units: 1bp of growth; 0.01 pp^2; 0.001 switches a year.
SCALE = {"mean": 1e-4, "gap_variance": 0.01, "switch_rate": 0.001, "floor_share": 0.001}
TILT_TOL = 1e-6
MIN_ESS = 500
# Chosen on the expected-value backtest and the past-years check (see ``choice``).
PRIMARY = "means_shift"
N_STRATA = 10
N_PATHS = 200
N_PATHS_SENSITIVITY = 40
MIN_PER_STRATUM = 2
SAMPLE_SEED = 20260930
BACKTEST_DRAWS = 5000
BACKTEST_H = 4
PAST_START = 2011  # determination year of the first counterfactual Burnham rise (April 2012)


# ── Draws and moments ────────────────────────────────────────────────────


def moments(stat_cpi, stat_earnings):
    """Per-path statistics of the statutory inputs, arrays (n,).

    gap_variance: variance (ddof 1) over the path's years of May-July AWE minus
    September CPI, in pp^2; switch_rate: times the lead passes between them, per
    pair of consecutive years (ts_backtest.switches); floor_share: share of years
    in which both are below 2.5%.
    """
    gap = 100 * (stat_earnings - stat_cpi)
    L = stat_cpi.shape[1]
    return {
        "gap_variance": np.var(gap, axis=1, ddof=1),
        "switch_rate": switches(np.stack([stat_cpi, stat_earnings], axis=2)) / (L - 1),
        "floor_share": np.mean(np.maximum(stat_cpi, stat_earnings) < TRIPLE_LOCK_FLOOR, axis=1),
    }


def statutory_history(first, last, treatment):
    """(years, September CPI, May-July AWE growth) from the monthly ONS data the model is fitted on."""
    months, cpi, awe, _ = ts_monthly.levels()
    years = list(range(first, last + 1))
    m = ts_monthly.annual_measures(months, cpi[None], awe[None], years)
    c, e = m["statutory_cpi"][0].copy(), m["statutory_earnings"][0].copy()
    if treatment == "suspended" and 2021 in years:
        e[years.index(2021)] = c[years.index(2021)]
    if treatment == "covid_excluded":
        keep = [i for i, y in enumerate(years) if y not in (2020, 2021)]
        years, c, e = [years[i] for i in keep], c[keep], e[keep]
    elif treatment not in TREATMENTS:
        raise ValueError(treatment)
    return years, c, e


def history_targets(first, last, treatment):
    """The dynamics statistics of the statutory history in a window, as the per-path statistics define them.

    The switch rate counts lead changes between consecutive years only: where
    years are left out (covid_excluded), the series is split at the hole.
    """
    years, c, e = statutory_history(first, last, treatment)
    stats = {k: float(v[0]) for k, v in moments(c[None], e[None]).items()}
    cuts = [0] + [i for i in range(1, len(years)) if years[i] != years[i - 1] + 1] + [len(years)]
    n_switch = n_pairs = 0
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a >= 2:
            n_switch += int(switches(np.stack([c[a:b], e[a:b]], axis=1)[None])[0])
            n_pairs += b - a - 1
    stats["switch_rate"] = n_switch / n_pairs
    return {"years": [years[0], years[-1]], "n_years": len(years), "consecutive_pairs": n_pairs, **stats}


def draws(central, n=N_DRAWS, seed=SEED, kind=KIND):
    """Monthly-model draws, unshifted and shifted to the central path's calendar means (same shocks)."""
    target = {y: (central["calendar"]["cpi"][y], central["calendar"]["earnings"][y]) for y in CALENDAR_YEARS}
    out = {}
    for name, cal_target in (("raw", None), ("shifted", target)):
        m, info = ts_monthly.paths(MONTHLY_YEARS, n, seed, kind, calendar_target=cal_target, lag_order=1)
        out[name] = {
            "stat_cpi": m["statutory_cpi"][:, :-1],  # Septembers 2026-2038
            "stat_earnings": m["statutory_earnings"][:, :-1],  # May-July 2026-2038
            "calendar": np.stack([m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:]], axis=2),  # 2027-2039
            "info": info,
        }
    out["target"] = np.array([target[y] for y in CALENDAR_YEARS])
    return out


def _tilt(d, mean_target, dyn_targets, keys):
    """Weights matching the calendar means (if given) and the named dynamics targets; raises TiltError."""
    n = len(d["stat_cpi"])
    cols, scale = [], []
    if mean_target is not None:
        cols.append((d["calendar"] - mean_target[None]).reshape(n, -1))
        scale += [SCALE["mean"]] * cols[-1].shape[1]
    mom = moments(d["stat_cpi"], d["stat_earnings"])
    for k in keys:
        cols.append((mom[k] - dyn_targets[k])[:, None])
        scale.append(SCALE[k])
    if not cols:
        return np.full(n, 1 / n), {"ess": float(n), "max_abs_mean_error": 0.0}
    return tilt_moments(np.hstack(cols), scale=np.array(scale), tol=TILT_TOL)


def calibrations(d, targets):
    """Every calibration: {name: (draw set, weights, info)}.

    ``targets``: {(window, treatment): history_targets(...)}. Raw draws: the
    model as fitted, and entropy tilting to the central means. Shifted draws:
    the drift shift alone, and with each window and treatment's dynamics
    targets (and, as a sensitivity, the floor share too).
    """
    out = {}

    def add(name, set_name, mean_target, dyn, keys, extra):
        try:
            w, info = _tilt(d[set_name], mean_target, dyn, keys)
        except TiltError as e:
            out[name] = {"draws": set_name, "weights": None, "error": str(e), **extra}
            return
        mom = moments(d[set_name]["stat_cpi"], d[set_name]["stat_earnings"])
        out[name] = {"draws": set_name, "weights": w, "ess": round(info["ess"], 1),
                     "achieved": {k: float(w @ mom[k]) for k in DIAGNOSTICS},
                     "targeted": list(keys) + (["calendar_means"] if mean_target is not None else []),
                     "ess_below_minimum": bool(info["ess"] < MIN_ESS), **extra}

    add("model", "raw", None, None, (), {"description": "the monthly model as fitted, equal weights"})
    add("means_tilt", "raw", d["target"], None, (),
        {"description": "entropy tilting to the central path's calendar means (the earlier approach)"})
    add("means_shift", "shifted", None, None, (),
        {"description": "the smoothest monthly drift path matching the central path's calendar means, equal weights"})
    for (window, treatment), t in targets.items():
        tag = f"{window}.{treatment}"
        add(f"shift_dynamics.{tag}", "shifted", d["target"], t, DYNAMICS,
            {"description": "the drift shift, then entropy tilting to the means and the history's gap variance and "
                            "lead-switch rate", "window": window, "treatment": treatment, "targets": t})
        add(f"shift_dynamics_floor.{tag}", "shifted", d["target"], t, DYNAMICS + ("floor_share",),
            {"description": "as shift_dynamics, also matching the history's share of years below 2.5% (a "
                            "sensitivity: it fights the OBR's forecast of earnings below 2.5% to 2030)",
             "window": window, "treatment": treatment, "targets": t})
    return out


# ── Rule arithmetic on draws ─────────────────────────────────────────────


def rule_levels(stat_cpi, stat_earnings, base_weekly, decimals=CENTRAL_RATE_DECIMALS):
    """Weekly full new State Pension under each rule, (n, len(HORIZON)), and the rates."""
    rates = {p: rules.rates_matrix(p, stat_cpi, stat_earnings, HORIZON, decimals) for p in ("triple_lock", "burnham_2030")}
    levels = {p: base_weekly * np.cumprod(1 + r, axis=1) for p, r in rates.items()}
    return levels, rates


def gap_summary(d, w, base_weekly):
    """Weighted distribution of the 2039-40 weekly gap and the rates' premium over earnings."""
    levels, rates = rule_levels(d["stat_cpi"], d["stat_earnings"], base_weekly)
    gap = levels["triple_lock"][:, -1] - levels["burnham_2030"][:, -1]
    identical = np.all(rates["triple_lock"] == rates["burnham_2030"], axis=1)
    order = np.argsort(gap)
    cw = np.cumsum(w[order])
    q = {f"p{int(100 * p)}": round(float(gap[order][np.searchsorted(cw, p * cw[-1])]), 2)
         for p in (0.1, 0.25, 0.5, 0.75, 0.9)}
    late = [j for j, y in enumerate(HORIZON) if y >= 2034]  # after the OBR's long-term premium is fully in
    premium = {p: float(w @ (r[:, late] - d["stat_earnings"][:, late]).mean(axis=1)) for p, r in rates.items()}
    return {
        "mean_gap_gbp_week": round(float(w @ gap), 3),
        "gap_gbp_week": q,
        "identical_share": round(float(w @ identical), 4),
        "mean_rate_minus_earnings_2034_2039": {p: round(v, 5) for p, v in premium.items()},
    }


# ── Expected-value backtest ──────────────────────────────────────────────


def ev_backtest(n=BACKTEST_DRAWS):
    """Chronological test of each calibration's expected Burnham gap against what happened.

    Origins: the OBR spring forecasts 2010-2021 whose four target years have
    outturns (ts_backtest's). At each, the monthly model is fitted on data to the
    December before; the four target years' statutory inputs are simulated; the
    calibrations use that forecast's calendar CPI and earnings as the means and
    the statutory history 2001 to the year before (furlough years left out) as the
    dynamics targets. The Burnham plan starts at the first of the four upratings
    and the gap is in % of the triple-lock level after the fourth. Scored against
    the published inputs under both treatments of April 2022. ``obr_point`` is the
    forecast itself as a single path (calendar values as statutory inputs).
    """
    from .history_data import error_blocks, load_forecast_errors
    from .config import ERROR_CSV
    from .ts_backtest import APRIL_2022_TREATMENTS, gap_pct, load_forecasts, statutory_outturns

    forecasts, _ = load_forecasts()
    _, kept = error_blocks(load_forecast_errors(ERROR_CSV))
    outturns = {t: statutory_outturns(suspend_2022=t == "suspended") for t in APRIL_2022_TREATMENTS}
    rows = []
    for v in kept:
        years = [v[0] + h for h in range(1, BACKTEST_H + 1)]
        fc = np.array([[forecasts[v][(var, h)] for var in ("cpi", "earnings")] for h in range(1, BACKTEST_H + 1)])
        target = {y: tuple(fc[j]) for j, y in enumerate(years)}
        sets = {}
        for name, cal_target in (("raw", None), ("shifted", target)):
            m, _ = ts_monthly.paths(years, n, v[0], KIND, end_obs=(v[0] - 1, 12), calendar_target=cal_target)
            sets[name] = {"stat_cpi": m["statutory_cpi"], "stat_earnings": m["statutory_earnings"],
                          "calendar": np.stack([m["calendar_cpi"], m["calendar_earnings"]], axis=2)}
        dyn = history_targets(2001, v[0] - 1, "covid_excluded")
        cal = {
            "model": ("raw", None, ()),
            "means_tilt": ("raw", fc, ()),
            "means_shift": ("shifted", None, ()),
            "shift_dynamics": ("shifted", fc, DYNAMICS),
        }
        preds = {}
        for name, (set_name, mt, keys) in cal.items():
            d = sets[set_name]
            try:
                w, info = _tilt(d, mt, dyn, keys)
            except TiltError as e:
                preds[name] = {"error": str(e)}
                continue
            paths = np.stack([d["stat_cpi"], d["stat_earnings"]], axis=2)
            g = gap_pct(paths)["burnham_2030"]
            preds[name] = {"gap_pct": float(w @ g), "switches": float(w @ switches(paths)), "ess": float(info["ess"])}
        g = gap_pct(fc[None])["burnham_2030"]
        preds["obr_point"] = {"gap_pct": float(g[0]), "switches": float(switches(fc[None])[0]), "ess": 1.0}
        for t in APRIL_2022_TREATMENTS:
            y = np.array([outturns[t][yy] for yy in years])
            realised = {"gap_pct": float(gap_pct(y[None])["burnham_2030"][0]), "switches": int(switches(y[None])[0])}
            rows.append({"origin": v[1], "treatment": t, "realised": realised, "predicted": preds})
    summary = {}
    for t in APRIL_2022_TREATMENTS:
        rs = [r for r in rows if r["treatment"] == t]
        summary[t] = {}
        for name in rs[0]["predicted"]:
            ok = [r for r in rs if "gap_pct" in r["predicted"][name]]
            err = np.array([r["predicted"][name]["gap_pct"] - r["realised"]["gap_pct"] for r in ok])
            sw = np.array([r["predicted"][name]["switches"] - r["realised"]["switches"] for r in ok])
            summary[t][name] = {
                "n_origins": len(ok),
                "mean_predicted_gap_pct": round(float(np.mean([r["predicted"][name]["gap_pct"] for r in ok])), 3),
                "mean_realised_gap_pct": round(float(np.mean([r["realised"]["gap_pct"] for r in ok])), 3),
                "bias_pct_points": round(float(err.mean()), 3),
                "bias_se_independent": round(float(err.std(ddof=1) / np.sqrt(len(err))), 3),
                "mean_abs_error": round(float(np.abs(err).mean()), 3),
                "switch_bias": round(float(sw.mean()), 3),
                "min_ess": round(min(r["predicted"][name]["ess"] for r in ok), 1),
            }
    return {
        "origins": [v[1] for v in kept],
        "horizon_years": BACKTEST_H,
        "draws": n,
        "bias_sign_convention": "predicted minus realised; positive means overprediction",
        "note": "Origins overlap (consecutive forecasts share three of four target years), so the standard errors, "
                "computed as if the origins were independent, understate the uncertainty; twelve origins are few. "
                "The data are today's revised ONS and OBR figures, and the model design was chosen with the whole "
                "sample in view.",
        "rows": rows,
        "summary": summary,
    }


def past_years_check(n=BACKTEST_DRAWS):
    """Where the realised gap had the plan started in April 2012 falls in the model's distribution fitted before it.

    The model is fitted on data to December 2010 and simulates the statutory
    inputs for 2011-2025 (the April 2012-2026 rises); no OBR forecast covers those
    fifteen years, so the calibrations are the model alone and the model tilted
    to the 2001-2010 dynamics. Realised: the published inputs with April 2022's
    earnings leg suspended, as the law did.
    """
    from .ts_backtest import gap_pct, statutory_outturns

    years = list(range(PAST_START, 2026))
    m, _ = ts_monthly.paths(years, n, PAST_START, KIND, end_obs=(PAST_START - 1, 12))
    d = {"stat_cpi": m["statutory_cpi"], "stat_earnings": m["statutory_earnings"],
         "calendar": np.stack([m["calendar_cpi"], m["calendar_earnings"]], axis=2)}
    paths = np.stack([d["stat_cpi"], d["stat_earnings"]], axis=2)
    g = gap_pct(paths)["burnham_2030"]
    o = statutory_outturns(suspend_2022=True)
    y = np.array([o[yy] for yy in years])
    realised = float(gap_pct(y[None])["burnham_2030"][0])
    dyn = history_targets(2001, PAST_START - 1, "published")
    out = {"years": [years[0], years[-1]], "realised_gap_pct": round(realised, 3), "dynamics_targets": dyn}
    for name, keys in (("model", ()), ("dynamics", DYNAMICS)):
        try:
            w, info = _tilt(d, None, dyn, keys)
        except TiltError as e:
            out[name] = {"error": str(e)}
            continue
        order = np.argsort(g)
        cw = np.cumsum(w[order])
        out[name] = {"mean_gap_pct": round(float(w @ g), 3),
                     "realised_percentile": round(float(100 * w[g <= realised].sum()), 1),
                     "p10_p50_p90": [round(float(g[order][np.searchsorted(cw, p * cw[-1])]), 3) for p in (0.1, 0.5, 0.9)],
                     "ess": round(float(info["ess"]), 1)}
    return out


# ── Stratified sample ────────────────────────────────────────────────────


def stratify(w, gap, identical, n_strata=N_STRATA):
    """Stratum per draw: 0 for identical rates (a saving of exactly zero), 1..n_strata of equal probability on the gap."""
    strata = np.zeros(len(w), dtype=int)
    rest = np.where(~identical)[0]
    if len(rest) == 0:
        return strata
    order = rest[np.argsort(gap[rest], kind="stable")]
    cw = np.cumsum(w[order]) / w[order].sum()
    strata[order] = np.minimum((cw * n_strata - 1e-12).astype(int), n_strata - 1) + 1
    return strata


def allocate(w, gap, strata, n_paths=N_PATHS, min_per=MIN_PER_STRATUM, include_zero=False):
    """Paths per stratum 1..K: Neyman allocation on the gap's weighted spread, at least ``min_per``, summing to n_paths."""
    ks = sorted(set(strata if include_zero else strata[strata > 0]))
    if min_per < 2:
        raise ValueError('at least two runs per sampled stratum are required')
    if not ks:
        return {}
    if n_paths < len(ks) * min_per:
        raise ValueError('sample budget is smaller than the stratum minimums')
    W = np.array([w[strata == k].sum() for k in ks])
    sd = []
    for k in ks:
        wk = w[strata == k] / w[strata == k].sum()
        gk = gap[strata == k]
        sd.append(np.sqrt(wk @ (gk - wk @ gk) ** 2))
    score = W * np.maximum(np.array(sd), 1e-9)
    alloc = np.maximum(min_per, np.floor(n_paths * score / score.sum())).astype(int)
    while alloc.sum() < n_paths:  # hand out the remainder to the largest shortfalls
        alloc[np.argmax(n_paths * score / score.sum() - alloc)] += 1
    while alloc.sum() > n_paths:
        alloc[np.argmax(np.where(alloc > min_per, alloc - n_paths * score / score.sum(), -np.inf))] -= 1
    return {int(k): int(a) for k, a in zip(ks, alloc)}


def draw_sample(w, strata, alloc, seed=SAMPLE_SEED):
    """{stratum: [draw index, ...]}: with replacement, probability proportional to weight within the stratum."""
    rng = np.random.default_rng(seed)
    out = {}
    for k, n_k in alloc.items():
        idx = np.where(strata == k)[0]
        p = w[idx] / w[idx].sum()
        out[int(k)] = [int(i) for i in rng.choice(idx, size=n_k, replace=True, p=p)]
    return out


def stratified_estimate(values_by_stratum, W, n_draws=N_DRAWS):
    """Mean, path-sampling and first-phase SEs, with their combined 95% MC band.

    Omitted strata contribute known-zero outcomes, including their
    between-stratum first-phase variance. W must contain all their masses, or
    the missing probability mass is interpreted as known-zero. For importance
    reweightings this is a plug-in approximation, conditional on fitted weights.
    """
    if n_draws <= 0:
        raise ValueError('n_draws must be positive')
    if any(w < 0 for w in W.values()) or sum(W.values()) > 1 + 1e-9:
        raise ValueError('stratum weights must be nonnegative probability masses')
    est, var = 0.0, 0.0
    stats = {}
    for k, vals in values_by_stratum.items():
        vals = np.asarray(vals, dtype=float)
        if len(vals) < 2:
            raise ValueError(f"stratum {k} has fewer than two runs")
        est += W[k] * vals.mean()
        var += W[k] ** 2 * vals.var(ddof=1) / len(vals)
        stats[k] = (float(vals.mean()), float(vals.var(ddof=1)))
    first = sum(W[k] * (s2 + (m - est) ** 2) for k, (m, s2) in stats.items())
    zero_mass = 1 - sum(W[k] for k in stats)
    first = (first + max(0, zero_mass) * est ** 2) / n_draws
    se = float(np.sqrt(var + first))
    return {'mean': float(est), 'se': se, 'se_path_sampling': float(np.sqrt(var)),
            'se_first_phase': float(np.sqrt(first)), 'variance_path_sampling': float(var),
            'variance_first_phase': float(first), 'plus_minus_95': 1.96 * se,
            'mc_interval_95': [float(est - 1.96 * se), float(est + 1.96 * se)]}


def stratified_mean(values_by_stratum, W, n_draws=N_DRAWS):
    """Backward-compatible tuple interface, now including first-phase variance."""
    estimate = stratified_estimate(values_by_stratum, W, n_draws)
    return estimate['mean'], estimate['se']


def path_spec(d, i, dataset=None):
    """The engine spec for draw ``i`` of a draw set."""
    return {
        "id": f"draw_{i}",
        "rate_decimals": CENTRAL_RATE_DECIMALS,
        "cpi": {y: float(d["calendar"][i, j, 0]) for j, y in enumerate(CALENDAR_YEARS)},
        "earnings": {y: float(d["calendar"][i, j, 1]) for j, y in enumerate(CALENDAR_YEARS)},
        "statutory_cpi": {y: float(d["stat_cpi"][i, j]) for j, y in enumerate(STATUTORY_YEARS)},
        "statutory_earnings": {y: float(d["stat_earnings"][i, j]) for j, y in enumerate(STATUTORY_YEARS)},
        "september_cpi_history": september_cpi_history(),
        **({"dataset": dataset} if dataset else {}),
    }


# ── Assembly ─────────────────────────────────────────────────────────────


OUTPUTS = ("gross", "net")


def _outputs(result):
    """{output: {year: value}} from one path's run, incl. components and households losing."""
    out = {o: {y: result["saving_bn"][y][o] for y in HORIZON} for o in OUTPUTS}
    out["gross_share_flat_rate_spending_pct"] = {
        y: 100 * result["saving_bn"][y]["gross"] / result["totals_bn"]["triple_lock"][y]["state_pension_flat_rate"]
        for y in HORIZON}
    comps = result["saving_bn"][HORIZON[0]]["components"]
    for c in comps:
        out[f"component.{c}"] = {y: result["saving_bn"][y]["components"][c] for y in HORIZON}
    out["households_losing_pct"] = {y: result["households_affected"][y]["losing_pct"] for y in HORIZON}
    # The single survey record that moves each year's household-income change most, and by how much (£bn;
    # positive: it gains, which the net saving loses).
    out["largest_record_bn"] = {y: result["concentration_by_year"][y]["contribution_bn"] for y in HORIZON}
    # The net saving without that record: its income change is all State Pension, benefits and tax, so the
    # government's balance moves by minus it.
    out["net_excluding_largest_record"] = {y: result["saving_bn"][y]["net"] + result["concentration_by_year"][y]["contribution_bn"]
                                           for y in HORIZON}
    return out


def estimates(sample, results, W, n_draws=N_DRAWS):
    """Stratified estimates by output and year; ``results`` maps draw index to its run.

    The identical-rates stratum is left out: every output there is exactly zero.
    """
    per = {k: [_outputs(results[i]) for i in idx] for k, idx in sample.items()}
    keys = next(iter(per.values()))[0].keys()
    out = {}
    for key in keys:
        out[key] = {}
        for y in HORIZON:
            out[key][y] = stratified_estimate({k: [o[key][y] for o in outs] for k, outs in per.items()}, W, n_draws)
    return out


def reweighted(sample, results, W_primary, w_primary, w_other):
    """Estimates under another calibration of the same draws, from the same runs: sum_h W_h mean_h(r y), r = w'/w.

    ``effective_runs``: the sum over strata of (sum r)^2 / sum r^2 among the runs
    drawn, a guide to how far the plug-in standard error can be trusted (with few
    effective runs the +-1.96 SE interval is too narrow).
    """
    out = {"effective_runs": 0.0}
    for k, idx in sample.items():
        r = np.array([w_other[i] / w_primary[i] for i in idx])
        out["effective_runs"] += float(r.sum() ** 2 / (r ** 2).sum()) if r.sum() > 0 else 0.0
    out['included_in_quoted_range'] = out['effective_runs'] >= 100
    out['uncertainty_note'] = ('Plug-in SE conditional on estimated calibration weights; '
                               'under 100 effective runs is excluded from any quoted range.')
    for key in OUTPUTS:
        out[key] = {}
        for y in HORIZON:
            vals = {k: [results[i]["saving_bn"][y][key] * w_other[i] / w_primary[i] for i in idx]
                    for k, idx in sample.items()}
            out[key][y] = stratified_estimate(vals, W_primary, len(w_primary))
    return out


def build(central, base_weekly, log=print, n_paths=N_PATHS, n_sensitivity=N_PATHS_SENSITIVITY,
          sensitivity_dataset=SENSITIVITY_DATASET, workers=3, sensitivity_workers=2, run=True,
          adequacy_report=None):
    """The expected-value section: calibration, backtest, sample, full runs (cached) and estimates.

    ``run=False`` stops after choosing the sample and returns the job lists
    for diagnostics only. Fiscal execution requires a passing original primary;
    alternative forms use their own C1 handoff designs. Without a supplied
    report the frozen screen is rerun on the current committed inputs.
    """
    if run:
        from .ts_uncertainty import PRIMARY_FORM, adequacy
        if adequacy_report is None:
            from .ts_backtest import run_candidate_backtest
            adequacy_report = adequacy(run_candidate_backtest(log=log))
        if PRIMARY_FORM not in adequacy_report['passing_forms']:
            raise ValueError('C1 adequacy gate failed for the original primary: no fiscal runs authorized; '
                             'use passing alternative forms\' own uncertainty handoff if any')

    d = draws(central)
    targets = {(wn, t): history_targets(*HISTORY_WINDOWS[wn], t) for wn in HISTORY_WINDOWS for t in TREATMENTS}
    cals = calibrations(d, targets)
    prim = cals[PRIMARY]
    w = prim["weights"]
    ds = d[prim["draws"]]
    levels, rates = rule_levels(ds["stat_cpi"], ds["stat_earnings"], base_weekly)
    gap = levels["triple_lock"][:, -1] - levels["burnham_2030"][:, -1]
    identical = np.all(rates["triple_lock"] == rates["burnham_2030"], axis=1)
    strata = stratify(w, gap, identical)
    alloc = allocate(w, gap, strata, n_paths)
    sample = draw_sample(w, strata, alloc)
    W = {k: float(w[strata == k].sum()) for k in alloc}
    W0 = float(w[strata == 0].sum())
    sub_alloc = {k: max(MIN_PER_STRATUM, int(round(n_sensitivity * alloc[k] / n_paths))) for k in alloc}
    sub = {k: sample[k][:sub_alloc[k]] for k in alloc}
    unique = sorted({i for idx in sample.values() for i in idx})
    unique_sub = sorted({i for idx in sub.values() for i in idx})
    zero_draw = int(np.argmax(np.where(identical, w, -1))) if identical.any() else None
    primary_jobs = [("path", path_spec(ds, i)) for i in unique]
    if zero_draw is not None:
        primary_jobs.append(("path", path_spec(ds, zero_draw)))
    sensitivity_jobs = [("path", path_spec(ds, i, sensitivity_dataset)) for i in unique_sub]
    if not run:
        return {"primary_jobs": primary_jobs, "sensitivity_jobs": sensitivity_jobs, "alloc": alloc,
                "sub_alloc": sub_alloc, "W": W, "W0": W0,
                "fiscal_eligible": False, "diagnostic_only": True}

    from . import engine

    log(f"Expected value: {len(unique)} paths on the primary dataset, {len(unique_sub)} on {sensitivity_dataset}")
    primary_runs = engine.run_jobs(primary_jobs, workers=workers, slot_prefix="efrs", log=log)
    runs = dict(zip(unique, primary_runs[:len(unique)]))
    zero_check = None
    if zero_draw is not None:
        z = primary_runs[-1]
        worst = max(abs(z["saving_bn"][y][o]) for y in HORIZON for o in ("gross", "net", "household_income_change"))
        if worst != 0.0:
            raise AssertionError(f"identical rates gave a non-zero saving ({worst})")
        zero_check = {"draw": zero_draw, "largest_abs_saving_bn": worst}
    sens_runs = dict(zip(unique_sub, engine.run_jobs(sensitivity_jobs, workers=sensitivity_workers,
                                                     slot_prefix="microcosm", log=log)))

    est_primary = estimates(sample, runs, W)
    est_sens = estimates(sub, sens_runs, W)
    diff = {}
    for key in OUTPUTS:
        diff[key] = {}
        for y in HORIZON:
            vals = {k: [sens_runs[i]["saving_bn"][y][key] - runs[i]["saving_bn"][y][key] for i in idx]
                    for k, idx in sub.items()}
            diff[key][y] = stratified_estimate(vals, W, len(w))
    sensitivities = {}
    for name, c in cals.items():
        if name == PRIMARY or c["draws"] != prim["draws"] or c["weights"] is None:
            continue
        sensitivities[name] = {"ess": c["ess"], **reweighted(sample, runs, W, w, c["weights"])}
    counts = {i: sum(idx.count(i) for idx in sample.values()) for i in unique}
    sub_counts = {i: sum(idx.count(i) for idx in sub.values()) for i in unique_sub}
    stratum_of = {i: k for k, idx in sample.items() for i in idx}
    paths = []
    for i in unique:
        r = runs[i]
        rec = {
            "draw": i, "stratum": stratum_of[i], "times_drawn": counts[i], "weight": float(w[i]),
            "gap_2039_gbp_week": float(gap[i]),
            "statutory": {"cpi": r["statutory"]["cpi"], "earnings": r["statutory"]["earnings"]},
            "rates": r["rates"],
            "outputs": {"primary": _outputs(r)},
            "weight_ratio": {name: float(c["weights"][i] / w[i]) for name, c in cals.items()
                             if name != PRIMARY and c["draws"] == prim["draws"] and c["weights"] is not None},
        }
        if i in sens_runs:
            s_ = sens_runs[i]
            rec["times_drawn_sensitivity"] = sub_counts[i]
            rec["outputs"]["sensitivity"] = _outputs(s_)
        paths.append(rec)
    strata_table = []
    for k in sorted(alloc):
        g_k = gap[strata == k]
        wk = w[strata == k]
        strata_table.append({"stratum": k, "probability": W[k], "gap_range_gbp_week": [float(g_k.min()), float(g_k.max())],
                             "mean_gap_gbp_week": float(wk @ g_k / wk.sum()), "paths": alloc[k],
                             "unique_paths": len(set(sample[k])), "sensitivity_paths": sub_alloc[k]})
    return {
        "method": __doc__,
        "draws": {"n": N_DRAWS, "seed": SEED, "shocks": KIND, "model": ds["info"]},
        "history_targets": {f"{wn}.{t}": v for (wn, t), v in targets.items()},
        "treatments": TREATMENTS,
        "calibrations": {name: {k: v for k, v in c.items() if k != "weights"} for name, c in cals.items()},
        "gap_by_calibration": {name: gap_summary(d[c["draws"]], c["weights"], base_weekly)
                               for name, c in cals.items() if c["weights"] is not None},
        "primary": PRIMARY,
        "adequacy": adequacy_report,
        "uncertainty_reporting": {
            "monte_carlo": "path sampling plus first phase; both components and ±1.96 total SE for every year",
            "model_and_mean_path": "separate scenario envelope; not a probability interval",
            "dynamics_range_rule": "exclude reweightings with fewer than 100 effective full runs",
        },
        "backtest": ev_backtest(),
        "past_years_check": past_years_check(),
        "strata": strata_table,
        "identical_rates": {"probability": W0, "check_run": zero_check},
        "datasets": {"primary": runs[unique[0]]["dataset"], "sensitivity": sensitivity_dataset},
        "estimates": {"primary": est_primary, "sensitivity": est_sens},
        "paired_difference": diff,
        "sensitivities": sensitivities,
        "paths": paths,
    }
