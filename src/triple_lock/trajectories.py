"""A few paths we fully understand, what the plan would have paid in past years, and the method backtests.

Every fiscal and household figure is a full PolicyEngine UK run (engine.py);
nothing is scaled from another run.

Future paths
------------
* ``central``: the central path (central.py): OBR March 2026 EFO to 2030, the
  OBR's long-term determinants after, April 2027 on the published inputs.
* ``random``: one draw picked uniformly at random (fixed seed) from the expected
  value's primary distribution.
* ``monthly_p50`` and ``monthly_p90``: draws from the expected value's primary
  distribution (expected_value.py: the monthly model shifted to the central
  path's calendar means, equal weights). For the median and 90th percentile of
  the 2039-40 Burnham gap (rule arithmetic on the weekly rate), the candidates
  are the draws within BAND of that probability; the path run is the candidate
  nearest their average path (each year and series standardised by its SD).

Each drawn path's ``selection`` says where its 2039-40 gap sits among the
primary distribution's 50,000 equally weighted draws: ``gap_percentile_2039``
(the weight below it plus half the weight tied with it) and
``larger_gap_pct_2039`` (the weight of draws whose gap is larger).

The same monthly model with Student-t copula and Gaussian shocks is summarised
in ``models`` but not run: those shocks put more weight on deflation, including
September CPI below -3%, which the published series has never reached (its
1989-2025 low is in ``gap_statistics``).

Past years
----------
What the Burnham plan would have paid had it started in an earlier April, on the
published September CPI and May-July earnings (ONS, latest vintage; April 2022's
earnings leg was suspended, so both rules use CPI that year). Counterfactual
flat rate = actual flat rate x (Burnham index / triple-lock replay index).
Fiscal and household effects for 2024-25 to 2026-27, the years the survey data
cover, come from full runs (engine.run_history), which keep each person's
survey-year share of the flat rate at actual law so every pension scales by
the level ratio.
"""

import csv
from pathlib import Path

import numpy as np

from . import engine, households, rules, ts_monthly
from .central import september_cpi_history
from .config import ACTUALS_CSV, BASE_YEAR, CALENDAR_YEARS, CENTRAL_RATE_DECIMALS, CPI_CSV, FINAL_YEAR, HORIZON, \
    STATUTORY_YEARS
from .ts_backtest import switches

QUANTILES = (0.5, 0.9)
RANDOM_SEED = 20261001  # picks the random path: one draw, uniformly, from the primary distribution
BAND = 0.025  # candidates: draws whose weighted CDF position is within 2.5 points of the quantile
MODEL_KINDS = {
    "boot": ("Monthly model, resampled residual shocks", True),
    "tcop": ("Monthly model, t-copula shocks", False),
    "gauss": ("Monthly model, Gaussian shocks", False),
}
DEFLATION_THRESHOLDS = {"-1%": -0.01, "-3%": -0.03}
HISTORY_YEARS = list(range(2011, BASE_YEAR + 1))  # April upratings with published inputs
HISTORY_SWITCH_YEARS = list(range(2012, BASE_YEAR + 1))
HISTORY_MODEL_YEARS = [2024, 2025, 2026]
SUSPENDED_EARNINGS_YEAR = 2022


# ── Future paths ─────────────────────────────────────────────────────────


def ordinal(n):
    """1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st..."""
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


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


def gap_position(gap, w, value):
    """Where ``value`` sits among weighted draws of the gap, in percent of the weight.

    ``percentile``: the weight below it plus half the weight tied with it (for a
    draw, its weighted_cdf_position x 100); ``larger``: the weight above it.
    """
    below, tied, above = (float(w[mask].sum()) for mask in (gap < value, gap == value, gap > value))
    total = float(w.sum())
    return {"percentile": 100 * (below + tied / 2) / total, "larger": 100 * above / total}


def position_fields(gap, w, value):
    """The selection fields that place a path's 2039-40 gap among the primary calibration's draws."""
    pos = gap_position(gap, w, value)
    return {"gap_percentile_2039": round(pos["percentile"], 2), "larger_gap_pct_2039": round(pos["larger"], 2),
            "draws_compared": int(len(gap))}


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
    s = switches(np.stack([stat_cpi, stat_earnings], axis=2)) / (stat_cpi.shape[1] - 1)
    return float(s.mean() if w is None else w @ s)


def model_summary(d, w, gap, info, label, runs_paths):
    """What the ``models`` block reports for one monthly-model variant."""
    stat_cpi, stat_earn = d["stat_cpi"], d["stat_earnings"]
    below = {}
    for name, threshold in DEFLATION_THRESHOLDS.items():
        hit = stat_cpi < threshold
        below[name] = {"path_years": round(float(w @ hit.mean(axis=1)), 4), "paths": round(float(w @ hit.any(axis=1)), 4)}
    return {
        "label": label,
        "runs_paths": runs_paths,
        **info,
        "gap_gbp_week": {f"p{int(100 * q)}": round(weighted_quantile(gap, w, q), 2) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
        "gap_zero_share": round(float(w @ (np.abs(gap) < 0.005)), 3),
        "september_2026_cpi": {f"p{int(100 * q)}": round(weighted_quantile(stat_cpi[:, 0], w, q), 4)
                               for q in (0.1, 0.5, 0.9)},
        "september_cpi_below": below,
        "september_cpi_years": [STATUTORY_YEARS[0], STATUTORY_YEARS[-1]],
        "may_july_earnings_range": {"min": round(float(stat_earn.min()), 4), "max": round(float(stat_earn.max()), 4),
                                    **{f"p{q}": round(float(np.percentile(stat_earn, q)), 4) for q in (1, 99)}},
        "switches_per_year": switches_per_year(stat_cpi, stat_earn, w),
    }


def central_spec(central):
    return {
        "id": "central",
        "label": "Central forecast",
        "source": "OBR March 2026 forecast to 2030 and the OBR's long-term determinants after; April 2027 on the "
                  "published inputs, September-quarter CPI and April-June earnings for the next four Aprils",
        "rate_decimals": CENTRAL_RATE_DECIMALS,
        "cpi": {y: central["calendar"]["cpi"][y] for y in CALENDAR_YEARS},
        "earnings": {y: central["calendar"]["earnings"][y] for y in CALENDAR_YEARS},
        "statutory_cpi": {y: central["statutory"]["cpi"][y] for y in STATUTORY_YEARS},
        "statutory_earnings": {y: central["statutory"]["earnings"][y] for y in STATUTORY_YEARS},
        "september_cpi_history": september_cpi_history(),
    }


def forward_specs(central, base_weekly, shifted=None):
    """The future paths to run, and the monthly-model summaries.

    ``shifted``: the expected value's shifted resampled-residual draws (computed
    here if None); the t-copula and Gaussian variants are drawn with the same
    shift and summarised only.
    """
    from . import expected_value as EV

    target = {y: (central["calendar"]["cpi"][y], central["calendar"]["earnings"][y]) for y in CALENDAR_YEARS}
    specs, models = [central_spec(central)], {}
    for kind, (label, run_paths) in MODEL_KINDS.items():
        if kind == EV.KIND and shifted is not None:
            d = shifted
        else:
            m, info = ts_monthly.paths(EV.MONTHLY_YEARS, EV.N_DRAWS, EV.SEED, kind, calendar_target=target)
            d = {"stat_cpi": m["statutory_cpi"][:, :-1], "stat_earnings": m["statutory_earnings"][:, :-1],
                 "calendar": np.stack([m["calendar_cpi"][:, 1:], m["calendar_earnings"][:, 1:]], axis=2), "info": info}
        # Equal weights: for the resampled-residual draws (EV.KIND) these are the expected value's primary
        # calibration (EV.PRIMARY, the drift shift alone), the same 50,000 draws with the same weights.
        w = np.full(len(d["stat_cpi"]), 1 / len(d["stat_cpi"]))
        levels, _ = EV.rule_levels(d["stat_cpi"], d["stat_earnings"], base_weekly)
        gap = levels["triple_lock"][:, -1] - levels["burnham_2030"][:, -1]
        models[kind] = model_summary(d, w, gap, d["info"], label, run_paths)
        if not run_paths:
            continue
        picks = select_draws(np.stack([d["stat_cpi"], d["stat_earnings"]], axis=2), w, gap)
        models[kind]["selections"] = picks
        i = int(np.random.default_rng(RANDOM_SEED).integers(len(w)))
        spec = EV.path_spec(d, i)
        spec.update({"id": "random", "label": "A random path",
                     "source": f"Draw {i:,} of {EV.N_DRAWS:,}, picked at random (seed {RANDOM_SEED}); its 2039-40 gap "
                               f"is £{gap[i]:.2f} a week, at the distribution's "
                               f"{ordinal(round(100 * weighted_cdf_position(gap, w)[i]))} percentile",
                     "selection": {"draw": i, "seed": RANDOM_SEED, "gap_gbp_week": round(float(gap[i]), 2),
                                   "cdf_position": round(float(weighted_cdf_position(gap, w)[i]), 4),
                                   **position_fields(gap, w, gap[i])}})
        specs.append(spec)
        for pick in picks:
            p, i = int(100 * pick["quantile"]), pick["draw"]
            spec = EV.path_spec(d, i)
            spec.update({
                "id": f"monthly_p{p}",
                "label": f"Monthly model: {'middle' if p == 50 else f'{p}th percentile'}",
                "source": (f"Draw {i:,} of {EV.N_DRAWS:,}: of the draws whose 2039-40 Burnham gap is near the "
                           f"distribution's {p}th percentile (£{pick['quantile_gap_gbp_week']:.2f} a week), the one "
                           "closest to their average path"),
                "selection": {**pick, **position_fields(gap, w, gap[i])},
            })
            specs.append(spec)
    return specs, models


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
    bp = rules.rates_matrix("burnham_2030", c, e, HISTORY_YEARS, switch_year=switch_year)[0]
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


def triple_lock_history(cpi, earnings):
    """The triple lock on the published inputs, April 2011-2026: which input set each rise, and the indices.

    ``earnings`` has April 2022's earnings leg suspended (equal to CPI), as the
    law did; the earnings index uses the published figure every year.
    """
    from .ts_backtest import statutory_outturns

    published = statutory_outturns()
    c = np.array([cpi[y] for y in HISTORY_YEARS])
    e = np.array([earnings[y] for y in HISTORY_YEARS])
    e_pub = np.array([published[y - 1][1] for y in HISTORY_YEARS])
    tl = rules.rates_matrix("triple_lock", c, e)[0]
    binding = {}
    for j, y in enumerate(HISTORY_YEARS):
        # The floor when it alone would have set the rise (ties included); otherwise the larger of the two inputs,
        # CPI when they tie (as in April 2022, when the earnings leg was suspended).
        if max(c[j], e[j]) <= rules.TRIPLE_LOCK_FLOOR:
            binding[y] = "floor"
        else:
            binding[y] = "earnings" if e[j] > c[j] else "cpi"
    return {
        "years": HISTORY_YEARS,
        "rate": dict(zip(HISTORY_YEARS, tl.tolist())),
        "binding": binding,
        "earnings_published": dict(zip(HISTORY_YEARS, e_pub.tolist())),
        "index": {
            "triple_lock": dict(zip(HISTORY_YEARS, np.cumprod(1 + tl).tolist())),
            "cpi": dict(zip(HISTORY_YEARS, np.cumprod(1 + c).tolist())),
            "earnings": dict(zip(HISTORY_YEARS, np.cumprod(1 + e_pub).tolist())),
            "floor": dict(zip(HISTORY_YEARS, np.cumprod(np.full(len(tl), rules.TRIPLE_LOCK_FLOOR) + 1).tolist())),
        },
        "note": f"Indices: 1 before the April {HISTORY_YEARS[0]} rise. The triple lock here is the rule replayed on the "
                "latest published inputs, with April 2022's earnings leg suspended as in law; the earnings index uses "
                "the published May-July growth every year. binding names the floor whenever neither input exceeds 2.5%, and CPI "
                "when the two inputs tie.",
    }


def history_job(group):
    return ("history", {"years": HISTORY_MODEL_YEARS,
                        "level_ratio": {y: group["level_ratio"][y] for y in HISTORY_MODEL_YEARS},
                        "september_cpi_history": september_cpi_history()})


# ── Observed gap statistics ──────────────────────────────────────────────


def _gap_stats(cpi, earnings, years, what):
    g = np.array([earnings[y] - cpi[y] for y in years])
    n = int(switches(np.stack([np.array([cpi[y] for y in years]), np.array([earnings[y] for y in years])],
                              axis=1)[None])[0])
    return {"series": what, "years": [years[0], years[-1]], "lag1_correlation": round(float(np.corrcoef(g[1:], g[:-1])[0, 1]), 3),
            "switches": n, "pairs": len(years) - 1, "switches_per_year": round(n / (len(years) - 1), 3)}


def gap_statistics():
    """Observed year-to-year behaviour of the earnings-CPI gap, on stated windows and data."""
    from .history_data import history
    from .ts_backtest import statutory_outturns

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


# ── Build ────────────────────────────────────────────────────────────────


def build(central, base_levels, actual_weekly, shifted=None, workers=3, log=print):
    """The trajectories section: future paths and past years (full runs, cached), gap statistics, backtests."""
    from .ts_backtest import run_backtest, run_statutory_backtest

    specs, models = forward_specs(central, base_levels["new_state_pension"], shifted)
    cpi_h, earnings_h = history_inputs()
    groups = history_groups(cpi_h, earnings_h)
    changing = [g for g in groups if g["changes_anything"]]
    log(f"Trajectories: {len(specs)} future paths, {len(changing)} past-year cases")
    results = engine.run_jobs([("path", {k: v for k, v in s.items() if k not in ("id", "label", "source", "selection")})
                               for s in specs] + [history_job(g) for g in changing], workers=workers,
                              slot_prefix="efrs", log=log)
    forward, past = results[:len(specs)], results[len(specs):]
    log("Example households on each path")
    trajectories = []
    for s, r in zip(specs, forward):
        arg = {k: v for k, v in s.items() if k not in ("id", "label", "source", "selection")}
        trajectories.append({k: s[k] for k in ("id", "label", "source", "selection") if k in s}
                            | {k: v for k, v in r.items() if k != "bundle"}
                            | {"households": households.run(arg)})
    for g, r in zip(changing, past):
        g["model_years"] = r
    for g in groups:
        g.setdefault("model_years", None)
    bsp = actual_weekly["basic_state_pension"]
    log("Backtests of the forecast-distribution methods")
    return {
        "models": models,
        "gap_statistics": gap_statistics(),
        "paths": trajectories,
        "history": {
            "years": HISTORY_YEARS,
            "model_years": HISTORY_MODEL_YEARS,
            "cpi": cpi_h,
            "earnings": earnings_h,
            "suspended_earnings_year": SUSPENDED_EARNINGS_YEAR,
            "actual_weekly": actual_weekly,
            "actual_rise": {y: round(bsp[y] / bsp[y - 1] - 1, 3) for y in HISTORY_YEARS},
            "actual_rise_note": "Rise actually paid each April: the model's basic State Pension amounts, rounded to "
                                "0.1 point.",
            "note": "September CPI and May-July earnings, latest ONS vintage; April 2022's earnings leg was "
                    "suspended, so both rules use CPI that year. Counterfactual flat rate = actual flat rate x "
                    "(Burnham index / triple-lock replay index); each person's pension scales by that ratio.",
            "groups": groups,
            "triple_lock": triple_lock_history(cpi_h, earnings_h),
        },
        "backtest": {"statutory": run_statutory_backtest(), "calendar": run_backtest()},
    }
