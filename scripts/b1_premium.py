"""Descriptive statistics of the headline forecast's own paths, added 15 November 2026 after the seventh review round.

No refit, no new paths: the headline's 399,440 forward paths regenerated from data/b1/posterior.npy with the headline's
seed, exactly as scripts/b1_bayes.py draws them. Reports (1) how often each statutory input falls below zero and below
the record's lowest value, and (2) the triple-lock premium the paths imply over the Aprils from the switch to 2039: the
triple lock's rate less May-July earnings (both to 0.1 point), in points per year and as the cumulative log excess y,
against the gap G the adjusted rule removes. Writes data/b1/premium.json.
"""
import json
from pathlib import Path

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock import rules
from triple_lock import v1_bands as V
from triple_lock.config import CENTRAL_RATE_DECIMALS, HORIZON, SWITCH_YEAR, STATUTORY_YEARS

OUT = Path(__file__).resolve().parents[1] / "data" / "b1" / "premium.json"
RECORD_MIN_EARNINGS = -0.009  # May-July 2020, the record's lowest (data/triple_lock_actual_inputs.csv)


def main():
    _, theta, _ = B.load_posterior(B.POSTERIOR)
    inputs = B.forward_inputs(theta)
    fwd = inputs[:, 1:]  # 2027-2038 determination years
    cpi, earn = inputs[:, :, 0], inputs[:, :, 1]
    ra = V.rule_arithmetic(cpi, earn)
    tl = ra["tl"]
    earn_r = rules.round_rate(earn, CENTRAL_RATE_DECIMALS)
    from_switch = np.array([y >= SWITCH_YEAR for y in HORIZON])
    excess_pts = (tl - earn_r)[:, from_switch]  # rate points, every path
    ok = (earn_r[:, from_switch] > -0.5).all(axis=1)
    y = (np.log1p(tl[:, from_switch][ok]) - np.log1p(earn_r[:, from_switch][ok])).sum(axis=1)
    G = ra["G"][:, -1]
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
        "premium_points_per_year": {"mean": float(100 * excess_pts.mean()), "median_of_path_means": float(100 * np.median(excess_pts.mean(axis=1)))},
        "y_log_points_cumulative": {"mean": float(100 * y.mean()), "median": float(100 * np.median(y)),
                                    "paths_dropped_earnings_below_minus_50pct": int((~ok).sum())},
        "G_2039_log_points": {"mean": float(100 * G[ok].mean()), "median": float(100 * np.median(G[ok]))},
        "G_over_y": {"ratio_of_means": float(G[ok].mean() / y.mean()),
                     "median_path_ratio_where_y_positive": float(np.median(G[ok][y > 0] / y[y > 0]))},
        "years_in_premium": n_years,
        "budget_chart_5_1": chart,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
