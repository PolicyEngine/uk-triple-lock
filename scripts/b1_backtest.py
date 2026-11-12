"""B1: the C2/C4 scores on pseudo-out-of-sample refits (docs/METHOD.md, B1, validation 3). Writes
data/b1/backtest.json.

For each of the thirteen complete origins the model is refitted without the data its hold-out forbids, and 5,000
four-year paths around the OBR forecast are scored exactly as C2 and C4 were (``ts_backtest.candidate_score``, C4's
summaries and limits, ratios to the first model's binding C2 scores). The scores are reported, not a gate.

    PYTHONPATH=src python scripts/b1_backtest.py
"""

import json

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock import ts_obr_errors as C4
from triple_lock.ts_backtest import (APRIL_2022_TREATMENTS, H, SUSPENDED_DETERMINATION_YEAR, candidate_score,
                                     statutory_outturns)

HOLD_OUTS = {
    "chronological": "primary: F cells with target year at most origin - 1 (what was known in spring of the origin year)",
    "target_year": "C4's: F cells dropped whose target year or lagged year lies in origin + 1 .. origin + 4",
}
SEED_OFFSET = {"chronological": 0, "target_year": 100_000}


def keep_cells(cells, origin, hold_out):
    if hold_out == "chronological":
        return cells["target"] <= origin - 1
    return ~B.touches(cells, range(origin + 1, origin + H + 1))


def origin_draws(theta, origin, forecast, n=C4.N_SCORE_DRAWS, path_seed_offset=0):
    rng = np.random.default_rng(origin + path_seed_offset)
    sub = theta[rng.choice(len(theta), n, replace=len(theta) < n)]  # with replacement only if fewer than n retained
    return forecast[None] + B.deviations(sub, 1, H, rng, delta_start=None, antithetic=False)


def refits(hold_out, record, cells, transitions, log=print):
    """The registered pseudo-out-of-sample refits: each origin's retained draws and its fit record."""
    thetas, fits = {}, {}
    for v in record["origins"]:
        keep = keep_cells(cells, v[0], hold_out)
        data = B.likelihood_data(cells, transitions, keep=keep)
        draws, diag = B.fit(data, warmup=B.REFIT_WARMUP, kept=B.REFIT_KEPT,
                            seed=B.MCMC_SEED + v[0] + SEED_OFFSET[hold_out], log=log)
        theta, _ = B.retained(draws)
        fits[v[1]] = {"error_cells": int(keep.sum()), "error_target_years": int(round(data["w_f"].sum())),
                      "draws_retained": int(len(theta)), "draws_outside_radius_bound": diag["draws_outside_radius_bound"],
                      "gate_met": diag["gate_met"], "worst": diag["worst"], "rerun": diag["settings"]["rerun"],
                      "posterior_median": {k: s["p50"] for k, s in B.posterior_summary(theta).items()}}
        log(f"B1 {hold_out} {v[1]}: {int(keep.sum())} cells, gate {diag['gate_met']}, {diag['worst']}")
        thetas[v[1]] = theta
    return thetas, fits


def score(hold_out, record, thetas, fits, path_seed_offset=0):
    """C2/C4 scores of the refits' four-year paths; ``path_seed_offset`` 0 is the registered path seed."""
    regime = (SUSPENDED_DETERMINATION_YEAR,)
    outturns = {"published": statutory_outturns(), "suspended": statutory_outturns(suspended_years=regime)}
    kept = record["origins"]
    chrono = [v for v in kept if sum(u[0] + H <= v[0] - 1 for u in kept) >= 2]  # test A's origins, as C2 and C4
    rows, failures = [], []
    for i, v in enumerate(kept):
        d0 = origin_draws(thetas[v[1]], v[0], record["forecast"][i], path_seed_offset=path_seed_offset)
        years = [v[0] + h for h in range(1, H + 1)]
        if not np.isfinite(d0).all():
            failures.append({"origin": v[1], "error": "non-finite draws"})
            continue
        for treatment in APRIL_2022_TREATMENTS:
            d = d0.copy()
            suspended = treatment == "suspended"
            if suspended:
                for j, year in enumerate(years):
                    if year in regime:
                        d[:, j, 1] = d[:, j, 0]
            y = np.array([outturns[treatment][yy] for yy in years])
            metrics = candidate_score(d, y, v[0], target_years=years, suspended_years=regime,
                                      exclude_legal_constants=suspended)
            metrics.update(C4.central_50(d, y, years, regime if suspended else ()))
            if not suspended:
                metrics["annual_gap_cells"] = H
            rows.append({"origin": v[1], "origin_year": v[0], "target_years": years, "chronological": v in chrono,
                         "treatment": treatment, **metrics})
    summaries = {}
    for test, origins in (("A", chrono), ("B", kept)):
        summaries[test] = {t: C4._summary([r for r in rows if r["treatment"] == t and (test == "B" or r["chronological"])],
                                          len(origins), t == "suspended") for t in APRIL_2022_TREATMENTS}
    result = {"variant": f"b1_{hold_out}", "n_draws": C4.N_SCORE_DRAWS,
              "origins": {"A": [v[1] for v in chrono], "B": [v[1] for v in kept]},
              "bias_convention": "forecast mean minus realised; positive = overprediction",
              "rows": rows, "failures": failures, "scores": summaries}
    verdict = C4.verdict(result)
    return {"hold_out": HOLD_OUTS[hold_out], "fits": fits,
            "all_refits_met_the_convergence_gate": all(f["gate_met"] for f in fits.values()),
            "c4_rule_would_pass": verdict["passes"], "c4_rule_failures": verdict["failures"],
            "checks_against_c2_c4_limits": verdict["checks"], **result}


def run(hold_out, record, cells, transitions, log=print):
    thetas, fits = refits(hold_out, record, cells, transitions, log)
    return score(hold_out, record, thetas, fits)


def main():
    record, cells, transitions = C4.load_record(), B.error_cells(), B.outturn_transitions()
    out = {**B.provenance(), "status": "reported, not a pass/fail gate (docs/METHOD.md, B1)", "limits": C4.LIMITS,
           "reference": "data/pilot/c2-binding/scores.json, monthly_var1_boot, suspended treatment",
           "refit": {"chains": B.CHAINS, "warmup": B.REFIT_WARMUP, "kept": B.REFIT_KEPT},
           "hold_outs": {k: run(k, record, cells, transitions) for k in HOLD_OUTS}}
    B.write(B.OUT / "backtest.json", out)
    for k, r in out["hold_outs"].items():
        print(k, "C4 rule would pass:", r["c4_rule_would_pass"], json.dumps(r["c4_rule_failures"], indent=1))


if __name__ == "__main__":
    main()
