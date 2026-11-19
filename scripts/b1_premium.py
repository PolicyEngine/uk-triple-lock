"""Descriptive statistics of the headline forecast's own paths, added 15 November 2026 after the seventh review round.

No refit, no new paths: the headline's 399,440 forward paths regenerated from data/b1/posterior.npy with the headline's
seed, exactly as scripts/b1_bayes.py draws them. Reports (1) how often each statutory input falls below zero and below
the record's lowest value, and (2) the triple-lock premium the paths imply over the Aprils from the switch to 2039: the
triple lock's rate less May-July earnings (both to 0.1 point), in points per year and as the cumulative log excess y,
against the gap G the adjusted rule removes, with the share of the mean excess from years of falling pay and from
Aprils 2037-39, and (16 November) the same on the soft-bounded paths of T2 at the record minimum. Writes
data/b1/premium.json.
"""
import importlib.util
import json
from pathlib import Path

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock import rules
from triple_lock import v1_bands as V
from triple_lock.config import CENTRAL_RATE_DECIMALS, HORIZON, SWITCH_YEAR, STATUTORY_YEARS

OUT = Path(__file__).resolve().parents[1] / "data" / "b1" / "premium.json"
RECORD_MIN_EARNINGS = -0.009  # May-July 2020, the record's lowest (data/triple_lock_actual_inputs.csv)


def soft_inputs(inputs, recentre=False):
    """The headline's paths with the soft lower bound at the record's minimum, median-centred, as T2 in
    scripts/b1_appendix_sensitivities.py (no refit)."""
    spec = importlib.util.spec_from_file_location("b1_app", Path(__file__).with_name("b1_appendix_sensitivities.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c, L = V.centre(), mod.BOUNDS["record_minimum"]
    x = mod.soft_bound(inputs, c, L)
    if recentre:
        x = mod.recentred(x, c, L)
    return x[:, :, 0], x[:, :, 1]


def premium_stats(cpi, earn, from_switch):
    """Premium, cumulative excess y and gap G over the Aprils from the switch, on paths whose earnings stay above -50%."""
    ra = V.rule_arithmetic(cpi, earn)
    tl = ra["tl"]
    earn_r = rules.round_rate(earn, CENTRAL_RATE_DECIMALS)
    ok = (earn_r[:, from_switch] > -0.5).all(axis=1)
    ex = (tl - earn_r)[:, from_switch][ok]  # rate points
    logex = np.log1p(tl[:, from_switch][ok]) - np.log1p(earn_r[:, from_switch][ok])
    y = logex.sum(axis=1)
    G = ra["G"][:, -1][ok]
    neg = earn[:, from_switch][ok] < 0
    years = np.array(HORIZON)[from_switch]
    late = years >= 2037
    return {
        "paths_used": int(ok.sum()), "paths_dropped_earnings_below_minus_50pct": int((~ok).sum()),
        "premium_points_per_year": {"mean": float(100 * ex.mean()), "median_of_path_means": float(100 * np.median(ex.mean(axis=1)))},
        "y_log_points_cumulative": {"mean": float(100 * y.mean()), "median": float(100 * np.median(y))},
        "G_2039_log_points": {"mean": float(100 * G.mean()), "median": float(100 * np.median(G))},
        "G_over_y": {"ratio_of_means": float(G.mean() / y.mean()),
                     "median_path_ratio_where_y_positive": float(np.median(G[y > 0] / y[y > 0]))},
        "share_of_mean_y_from_path_years_with_earnings_below_zero": float(logex[neg].sum() / logex.sum()),
        "share_of_mean_y_from_aprils_2037_on": float(logex[:, late].sum() / logex.sum()),
        "G_over_y_more": {"ratio_of_medians": float(np.median(G) / np.median(y)),
                          "path_ratio_quartiles": [float(q) for q in np.quantile(G[y > 0] / y[y > 0], [0.25, 0.5, 0.75])]},
        "remaining_excess_x_final_log_points": {"median": float(100 * np.median(y - G)), "mean": float(100 * (y - G).mean()),
                                                "share_of_paths_above_5": float(((y - G) > 0.05).mean())},
        "by_april": {str(yr): _by_year(logex[:, : k + 1].sum(axis=1), ra["G"][:, HORIZON.index(yr)][ok])
                     for k, yr in enumerate(years)},
    }


def _by_year(y, G):
    pos = y > 0
    return {"ratio_of_means": float(G.mean() / y.mean()), "ratio_of_medians": float(np.median(G) / np.median(y)),
            "median_of_path_ratios": float(np.median(G[pos] / y[pos])), "median_x_log_points": float(100 * np.median(y - G))}


def main():
    _, theta, _ = B.load_posterior(B.POSTERIOR)
    inputs = B.forward_inputs(theta)
    fwd = inputs[:, 1:]  # 2027-2038 determination years
    cpi, earn = inputs[:, :, 0], inputs[:, :, 1]
    ra = V.rule_arithmetic(cpi, earn)
    from_switch = np.array([y >= SWITCH_YEAR for y in HORIZON])
    base = premium_stats(cpi, earn, from_switch)
    n_years = int(from_switch.sum())
    # Budget Chart 5.1's 2039-40 share saved, on all State Pension spending, restated on basic and new spending with the
    # central run's additional State Pension (CPI-uprated under both rules), as paper/paperdata.chart_share_flat does.
    import csv
    ch = {int(r["fiscal_year_start"]): (float(r["triple_lock_pct_gdp"]), float(r["adjusted_pct_gdp"]))
          for r in csv.DictReader((OUT.parents[1] / "benchmarks" / "budget_2026_chart_5_1.csv").open())}
    tot = json.loads(V.RESULTS.read_text())["scenario_envelope"]["central"]["run"]["totals_bn"]["triple_lock"]
    chart = {}
    for yr in (2034, 2039):
        t = tot[str(yr)]
        flat = (1 - ch[yr][1] / ch[yr][0]) * (t["state_pension_flat_rate"] + t["additional_state_pension"]) / t["state_pension_flat_rate"]
        chart[str(yr)] = {"chart_share_flat": flat, "share_of_paths_saving_a_larger_share": float((ra["share"][:, HORIZON.index(yr)] > flat).mean())}
    out = {
        "note": __doc__.split("\n")[0], "n_paths": int(len(inputs)), "posterior_sha256": __import__("hashlib").sha256(B.POSTERIOR.read_bytes()).hexdigest(),
        "seed": B.PREDICTIVE_SEED, "aprils": [y_ for y_, f in zip(HORIZON, from_switch) if f],
        "share_of_path_years_below_zero": {"cpi": float((fwd[:, :, 0] < 0).mean()), "earnings": float((fwd[:, :, 1] < 0).mean())},
        "share_of_path_years_earnings_below_record_min": float((fwd[:, :, 1] < RECORD_MIN_EARNINGS).mean()),
        "record_min_earnings": RECORD_MIN_EARNINGS,
        "share_of_paths_with_any_earnings_year_below_zero": float((fwd[:, :, 1] < 0).any(axis=1).mean()),
        **base,
        "soft_bound_record_minimum": premium_stats(*soft_inputs(inputs), from_switch),
        "soft_bound_record_minimum_recentred": premium_stats(*soft_inputs(inputs, recentre=True), from_switch),
        "years_in_premium": n_years,
        "budget_chart_5_1": chart,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
