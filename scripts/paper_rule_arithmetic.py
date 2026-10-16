"""Rule arithmetic on every simulated path, for the working paper (no PolicyEngine run).

The expected saving is built from 160 full PolicyEngine UK runs, but several
questions the paper answers need only the two rules applied to the simulated
inputs, on all 50,000 paths:

* the gap the rules open in the full new State Pension in each year (the
  final-year gross saving is that gap times a constant fixed by the population,
  so the gap gives exact gross figures for other path sets);
* how the model's paths behave against history: how often the lead passes
  between CPI and earnings, the spread and persistence of the gap between them,
  and how often both are below the 2.5% floor;
* the same for the other versions of the price-and-earnings model that pass the
  test on past forecasts, and for the paired scenarios that move earnings growth
  0.5 points a year from 2031.

The draws are regenerated with the same code, seed and shocks as the expected
saving (``ts_uncertainty.future_draws``); the script checks that the primary
draws reproduce the results file's gap distribution and shock hash before it
writes anything. It writes one block, ``paper_rule_arithmetic``, into
``data/results.json``. After any rebuild of the results file (for example the
post-Budget binding run), rerun it:

    PYTHONPATH=src .venv/bin/python scripts/paper_rule_arithmetic.py
"""

import json
from pathlib import Path

import numpy as np

from triple_lock import expected_value as EV
from triple_lock import ts_uncertainty as U
from triple_lock.central import long_run_earnings_variant
from triple_lock.config import HORIZON
from triple_lock.rules import round_rate
from triple_lock.ts_backtest import switches

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results.json"
FLOOR = 0.025
# Statutory input years whose values set the April 2030 to April 2039 rises (the plan's years).
DYN_FIRST, DYN_LAST = 2029, 2038
INPUT_YEARS = [y - 1 for y in HORIZON]  # Septembers / May-July 2026-2038 set the April 2027-2039 rises


def dynamics(c, e):
    """Path behaviour over the plan's input years, averaged over the paths (equal weights).

    switch_rate: lead changes between CPI and earnings per pair of consecutive years (as the calibrations count
    them); switch_rate_floor: the same between the higher of CPI and the floor and earnings, the comparison the two
    rules make; gap_variance: variance of earnings minus CPI within a path, points squared; lag1_correlation: the
    year-to-year correlation of that gap, pooled over paths after removing each year's average across paths (the
    common drift towards the OBR forecast); floor_share: share of years in which both are below 2.5%."""
    j = [INPUT_YEARS.index(y) for y in range(DYN_FIRST, DYN_LAST + 1)]
    c, e = c[:, j], e[:, j]
    L = c.shape[1]
    m = EV.moments(c, e)
    floor_c = np.maximum(c, FLOOR)
    sw_floor = switches(np.stack([floor_c, e], axis=2)) / (L - 1)
    g = 100 * (e - c)
    d = g - g.mean(axis=0, keepdims=True)
    lag1 = float(np.sum(d[:, 1:] * d[:, :-1]) / np.sqrt(np.sum(d[:, 1:] ** 2) * np.sum(d[:, :-1] ** 2)))
    return {"input_years": [DYN_FIRST, DYN_LAST],
            "switch_rate": round(float(m["switch_rate"].mean()), 4),
            "switch_rate_floor": round(float(sw_floor.mean()), 4),
            "gap_variance": round(float(m["gap_variance"].mean()), 4),
            "lag1_correlation": round(lag1, 4),
            "floor_share": round(float(m["floor_share"].mean()), 4)}


def gaps(d, base_weekly):
    """Mean and percentiles of the weekly gap (triple lock minus plan) by April year, and the identical share."""
    levels, rates = EV.rule_levels(d["stat_cpi"], d["stat_earnings"], base_weekly)
    gap = levels["triple_lock"] - levels["burnham_2030"]
    out = {"mean_gap_gbp_week": {}, "gap_quantiles_gbp_week": {}}
    for j, y in enumerate(HORIZON):
        out["mean_gap_gbp_week"][str(y)] = round(float(gap[:, j].mean()), 4)
        out["gap_quantiles_gbp_week"][str(y)] = {f"p{int(100 * q)}": round(float(np.quantile(gap[:, j], q)), 4)
                                                  for q in (0.1, 0.25, 0.5, 0.75, 0.9)}
    out["identical_share"] = round(float(np.all(rates["triple_lock"] == rates["burnham_2030"], axis=1).mean()), 4)
    return out, rates


def below_earnings_share(d, rates):
    """Share of path-years, April 2031 to the final April, in which the plan's rise is below earnings growth."""
    e = round_rate(d["stat_earnings"])
    j = [i for i, y in enumerate(HORIZON) if y >= 2031]
    return round(float(np.mean(rates["burnham_2030"][:, j] < e[:, j] - 1e-9)), 4)


def history():
    """The same statistics for the statutory history in each window the calibrations use, and 2001-2010."""
    out = {}
    windows = {"2001_2025": (2001, 2025), "2010_2025": (2010, 2025), "2001_2010": (2001, 2010)}
    for name, (a, b) in windows.items():
        for t in ("suspended", "published", "covid_excluded"):
            if name == "2001_2010" and t != "published":
                continue
            years, c, e = EV.statutory_history(a, b, t)
            tgt = EV.history_targets(a, b, t)
            g = 100 * (e - c)
            contiguous = [i for i in range(1, len(years)) if years[i] == years[i - 1] + 1]
            lag1 = float(np.corrcoef(g[contiguous], g[[i - 1 for i in contiguous]])[0, 1])
            cuts = [0] + [i for i in range(1, len(years)) if years[i] != years[i - 1] + 1] + [len(years)]
            n_sw = n_pairs = 0
            fc = np.maximum(c, FLOOR)
            for lo, hi in zip(cuts[:-1], cuts[1:]):
                if hi - lo >= 2:
                    n_sw += int(switches(np.stack([fc[lo:hi], e[lo:hi]], axis=1)[None])[0])
                    n_pairs += hi - lo - 1
            out[f"{name}.{t}"] = {"years": tgt["years"], "n_years": tgt["n_years"],
                                  "switch_rate": round(tgt["switch_rate"], 4),
                                  "switch_rate_floor": round(n_sw / n_pairs, 4),
                                  "gap_variance": round(tgt["gap_variance"], 4),
                                  "lag1_correlation": round(lag1, 4),
                                  "floor_share": round(tgt["floor_share"], 4)}
    return out


def main():
    R = json.loads(RESULTS.read_text())
    base = R["base_year_weekly"]["new_state_pension"]
    central = U.central_path()
    passing = R["uncertainty_screen"]["c2_outcome"]["passing_forms"]
    primary = R["expected_value"]["draws"]["form"]
    n = R["expected_value"]["draws"]["n"]
    seed = R["expected_value"]["draws"]["seed"]
    forms = {}
    for form in dict.fromkeys([primary, *passing]):
        d = U.future_draws(form, central, n, seed)
        g, rates = gaps(d, base)
        forms[form] = {**g, "dynamics": dynamics(d["stat_cpi"], d["stat_earnings"]),
                       "plan_rise_below_earnings_share": below_earnings_share(d, rates),
                       "innovation_sha256": d["info"]["shock_distribution"]["innovation_sha256"]}
        if form == primary:
            stored = R["expected_value"]["gap_by_calibration"]["means_shift"]["mean_gap_gbp_week"]
            got = forms[form]["mean_gap_gbp_week"][str(HORIZON[-1])]
            assert abs(got - stored) < 5e-4, (got, stored)
            assert (forms[form]["innovation_sha256"]
                    == R["expected_value"]["draws"]["model"]["shock_distribution"]["innovation_sha256"])
            prim = d
    variants = {}
    for sid, sc in R["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"].items():
        delta, first = sc["calendar_earnings_delta"], sc["from_year"]
        d = U.future_draws(primary, long_run_earnings_variant(central, delta, first), n, seed)
        assert d["info"]["shock_distribution"]["innovation_sha256"] == forms[primary]["innovation_sha256"]
        g, rates = gaps(d, base)
        variants[sid] = {"calendar_earnings_delta": delta, "from_year": first, **g,
                         "dynamics": dynamics(d["stat_cpi"], d["stat_earnings"])}
    R["paper_rule_arithmetic"] = {
        "description": "The two rules applied to every simulated path (no PolicyEngine run): gaps in the full new "
                       "State Pension, path behaviour against history, the passing model versions and the paired "
                       "earnings scenarios. Written by scripts/paper_rule_arithmetic.py.",
        "n_draws": n, "seed": seed, "primary_form": primary,
        "base_weekly_new_state_pension": base,
        "forms": forms, "earnings_variants": variants, "history": history(),
    }
    # The pipeline's own format (indent 1), to the results file and the dashboard's copy of it.
    text = json.dumps(R, indent=1, default=float, allow_nan=False) + "\n"
    for target in (RESULTS, ROOT / "dashboard" / "public" / "data" / "results.json"):
        target.write_text(text)
    print(json.dumps({k: {"gap": v["mean_gap_gbp_week"][str(HORIZON[-1])], **v["dynamics"],
                          "below": v["plan_rise_below_earnings_share"]} for k, v in forms.items()}, indent=1))
    print(json.dumps({k: {"gap": v["mean_gap_gbp_week"], **v["dynamics"]} for k, v in variants.items()}, indent=1))
    print(json.dumps(R["paper_rule_arithmetic"]["history"], indent=1))


if __name__ == "__main__":
    main()
