"""How often the C3 test passes on simulated outcomes (docs/METHOD.md, C3).

Model draws and arithmetic only: no outturn, no C3 target, no microsimulation and no fiscal figure. Each simulated
outcome is one path of a stated truth, scored against the model's own distribution for the same years. Real origins
differ from one another, so these rates describe the test's shape, not its exact behaviour.

    PYTHONPATH=src python scripts/c3_operating_characteristics.py
"""

import json
from pathlib import Path

import numpy as np

from triple_lock.central import central_path
from triple_lock.ts_backtest import gap_pct, switches, wilson_band
from triple_lock.ts_methods import tilt_moments
from triple_lock.ts_uncertainty import PRIMARY_FORM, future_draws

OUTPUT = Path(__file__).resolve().parent.parent / "docs/uncertainty/c3-operating-characteristics.json"
FIRST_YEAR = 2026  # future_draws starts at this determination year
OUTCOME_YEARS = (4, 8, 12)  # determination years 2027-2030, 2027-2034 and 2027-2038
N_OUTCOMES = 20_000
SEED = 20261031
FLOOR = 0.025
LIMITS = {"annual_coverage": (0.5, 1.0), "terminal_coverage": (0.5, 1.0), "gap_bias_pp": 1.5, "switch_bias": 1.0,
          "floor_bias": 0.25}


def windows(k):
    """Column slices of every four-year window among k outcome years, one for each origin with all four untouched."""
    return [slice(i, i + 4) for i in range(k - 3)]


def band(x):
    """The central 80% interval ts_methods.interval_hit uses for equal-weight draws x."""
    s, c = np.sort(x), np.cumsum(np.full(len(x), 1 / len(x)))
    return s[np.searchsorted(c, 0.1)], s[min(np.searchsorted(c, 0.9), len(x) - 1)]


def statistics(cpi, earnings, truth_cpi, truth_earnings):
    """Each simulated outcome's test statistics, as ts_backtest.candidate_score defines them.

    Forecast and truth both have shape (paths, years); truth rows are the simulated outcomes.
    """
    gap, truth_gap = 100 * (earnings - cpi), 100 * (truth_earnings - truth_cpi)
    bands = np.array([band(gap[:, j]) for j in range(gap.shape[1])]).T
    forecast, truth = np.stack([cpi, earnings], axis=2), np.stack([truth_cpi, truth_earnings], axis=2)
    switch_bias, terminal_hits = [], []
    for w in windows(cpi.shape[1]):
        switch_bias.append(switches(forecast[:, w]).mean() - switches(truth[:, w]))
        low, high = band(gap_pct(forecast[:, w], decimals=None)["burnham_2030"])
        realised = gap_pct(truth[:, w], decimals=None)["burnham_2030"]
        terminal_hits.append((realised >= low) & (realised <= high))
    return {
        "annual_coverage": ((truth_gap >= bands[0]) & (truth_gap <= bands[1])).mean(axis=1),
        "gap_bias": gap.mean() - truth_gap.mean(axis=1),
        "floor_bias": (earnings < FLOOR).mean() - (truth_earnings < FLOOR).mean(axis=1),
        "switch_bias": np.mean(switch_bias, axis=0),
        "terminal_hits": np.array(terminal_hits),
    }


def pass_rates(cpi, earnings, truth_cpi, truth_earnings):
    """Share of simulated outcomes passing each check, and all of them, on the columns given."""
    s = statistics(cpi, earnings, truth_cpi, truth_earnings)
    hits, n = s["terminal_hits"].sum(axis=0), s["terminal_hits"].shape[0]
    wilson = np.array([wilson_band(h, n)[0] <= 0.8 <= wilson_band(h, n)[1] for h in range(n + 1)])[hits]
    low, high = LIMITS["annual_coverage"]
    checks = {
        "annual_coverage": (s["annual_coverage"] >= low) & (s["annual_coverage"] <= high),
        "terminal_coverage": (hits / n >= LIMITS["terminal_coverage"][0]) & wilson,
        "gap_bias": np.abs(s["gap_bias"]) <= LIMITS["gap_bias_pp"],
        "switch_bias": np.abs(s["switch_bias"]) <= LIMITS["switch_bias"],
        "floor_bias": np.abs(s["floor_bias"]) <= LIMITS["floor_bias"],
    }
    rates = {name: round(float(ok.mean()), 3) for name, ok in checks.items()}
    rates["all"] = round(float(np.logical_and.reduce(list(checks.values())).mean()), 3)
    return rates


def truths(cpi, earnings, rng):
    """{name: (cpi rows, earnings rows)}, each N_OUTCOMES simulated outcomes for every horizon year."""
    n = len(cpi)
    pick = rng.integers(n, size=N_OUTCOMES)
    share = (earnings < FLOOR).mean(axis=1)
    out = {"model is right": (cpi[pick], earnings[pick])}
    for name, ratio in (("true floor rate is 3/4 of the model's", 0.75), ("true floor rate is 1/2 of the model's", 0.5)):
        weights, _ = tilt_moments((share - ratio * share.mean())[:, None], scale=np.array([1e-3]))
        tilted = rng.choice(n, N_OUTCOMES, p=weights / weights.sum())
        out[name] = (cpi[tilted], earnings[tilted])
    for name, shift in (("true earnings growth is 1pp higher", 0.01), ("true earnings growth is 1pp lower", -0.01)):
        out[name] = (cpi[pick], earnings[pick] + shift)
    mean_c, mean_e = cpi.mean(axis=0), earnings.mean(axis=0)
    for name, scale in (("true spread is 3/2 of the model's", 1.5), ("true spread is 2/3 of the model's", 2 / 3)):
        out[name] = (mean_c + scale * (cpi[pick] - mean_c), mean_e + scale * (earnings[pick] - mean_e))
    return out


def main():
    d = future_draws(PRIMARY_FORM, central_path())
    cpi, earnings = d["stat_cpi"][:, 1:], d["stat_earnings"][:, 1:]  # determination years 2027-2038
    simulated = truths(cpi, earnings, np.random.default_rng(SEED))
    result = {
        "form": PRIMARY_FORM, "first_outcome_year": FIRST_YEAR + 1, "simulated_outcomes": N_OUTCOMES, "seed": SEED,
        "note": "The model's own distribution for each year, scored once a year; real origins differ.",
        "pass_rates": {name: {str(k): pass_rates(cpi[:, :k], earnings[:, :k], c[:, :k], e[:, :k])
                              for k in OUTCOME_YEARS}
                       for name, (c, e) in simulated.items()},
    }
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    for name, by_years in result["pass_rates"].items():
        print(f"{name:40s}", {k: v["all"] for k, v in by_years.items()})


if __name__ == "__main__":
    main()
