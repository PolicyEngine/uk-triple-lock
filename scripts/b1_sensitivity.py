"""B1: the sensitivity runs S1 to S15 (docs/METHOD.md, B1, validation 4). Writes data/b1/sensitivity.json.

Each run changes one thing. Runs that change the posterior refit with the registered sampler settings; S8, S9 and S13
change only the forward step and reuse the stored posterior. Every run draws 400,000 paths with the forecast's seed.

    PYTHONPATH=src python scripts/b1_sensitivity.py
"""

import json

import numpy as np

from triple_lock import b1_bayes as B

P = B.PRIORS
RUNS = {
    "S1": {"label": "persistence looser: Phi prior standard deviations doubled",
           "priors": {"phi_sd": tuple(2 * x for x in P["phi_sd"])}},
    "S2": {"label": "persistence tighter: Phi prior standard deviations halved",
           "priors": {"phi_sd": tuple(x / 2 for x in P["phi_sd"])}},
    "S3": {"label": "thin tails: nu fixed at 30", "priors": {"nu_fixed": 30.0}},
    "S4": {"label": "fat tails: nu fixed at 3", "priors": {"nu_fixed": 3.0}},
    "S5": {"label": "low correlation: atanh rho_F ~ N(0, 0.25^2)", "priors": {"z_mu": 0.0, "z_sd": 0.25}},
    "S6": {"label": "high correlation: atanh rho_F ~ N(atanh 0.8, 0.25^2)",
           "priors": {"z_mu": float(np.arctanh(0.8)), "z_sd": 0.25}},
    "S7": {"label": "without 2021-23: F cells dropped whose target or lagged year is 2021, 2022 or 2023",
           "data": "drop_hot"},
    "S8": {"label": "no long-run level uncertainty: delta = 0", "forward": {"delta_sd": (0.0, 0.0)}},
    "S9": {"label": "long-run level standard deviations doubled",
           "forward": {"delta_sd": tuple(2 * x for x in P["delta_sd"])}},
    "S10": {"label": "outturn block from 1997", "data": "outturn_1997"},
    "S11": {"label": "forecast-error record alone", "data": "errors_only"},
    "S12": {"label": "outturn record alone, 1989-2025, forward scale Sigma_O", "data": "outturns_only",
            "forward": {"scale": "O"}},
    "S13": {"label": "clustered volatility forward: w(t) repeats w(t-1) with probability one half",
            "forward": {"cluster": True}},
    "S14": {"label": "every F cell at weight one", "data": "full_weight"},
    "S15": {"label": "errors de-meaned by variable and horizon", "data": "demeaned"},
}
PRIOR_RUNS = ("S1", "S2", "S3", "S4", "S5", "S6", "S8", "S9")


def data_for(kind, cells, transitions):
    if kind == "drop_hot":
        return B.likelihood_data(cells, transitions, keep=~B.touches(cells, B.HOT_YEARS))
    if kind == "outturn_1997":
        return B.likelihood_data(cells, transitions, outturn_first=1997)
    if kind == "errors_only":
        return B.likelihood_data(cells, transitions, use_outturns=False)
    if kind == "outturns_only":
        return B.likelihood_data(cells, transitions, use_errors=False, outturn_last=B.RECORD_LAST)
    if kind == "full_weight":
        return B.likelihood_data(cells, transitions, full_weight=True)
    if kind == "demeaned":
        return B.likelihood_data(B.demeaned(cells), transitions)
    raise ValueError(kind)


def report(res):
    return {str(y): {"gross_bn": res["by_year"][str(y)]["gross_bn"], "net_bn": res["by_year"][str(y)]["net_bn"],
                     "probability": res["by_year"][str(y)]["probability"],
                     "monte_carlo_se": res["monte_carlo_se"][str(y)]} for y in B.REPORT_YEARS}


def main():
    cells, transitions = B.error_cells(), B.outturn_transitions()
    _, main_theta = B.load_posterior()
    ctx = B.cash_context()
    base, _, _ = B.forecast_summary(main_theta, ctx)
    out = {**B.provenance(), "headline": report(base), "runs": {}}
    for sid, run in RUNS.items():
        forward = dict(run.get("forward", {}))
        entry = {"label": run["label"], "refit": "priors" in run or "data" in run}
        theta = main_theta
        if entry["refit"]:
            data = data_for(run["data"], cells, transitions) if "data" in run else B.likelihood_data(cells, transitions)
            draws, diag = B.fit(data, run.get("priors"))
            theta = draws.reshape(-1, draws.shape[-1])
            entry.update(gate_met=diag["gate_met"], worst=diag["worst"], rerun=diag["settings"]["rerun"],
                         error_cells=int((data["w_f"] > 0).sum()), error_weight=float(data["w_f"].sum()),
                         outturn_transitions=int(data["w_o"].sum()), posterior=B.posterior_summary(theta))
            if run.get("priors", {}).get("nu_fixed"):
                forward["nu_fixed"] = run["priors"]["nu_fixed"]
        res, _, _ = B.forecast_summary(theta, ctx, **forward)
        entry.update(report(res))
        out["runs"][sid] = entry
        print(sid, run["label"], "| 2039 gross p5/p50/p95",
              [round(entry["2039"]["gross_bn"][k], 2) for k in ("p5", "p50", "p95")],
              "gate", entry.get("gate_met", "n/a"), flush=True)
    med = {s: r["2039"]["gross_bn"]["p50"] for s, r in out["runs"].items() if r.get("gate_met", True)}
    out["not_quoted_gate_unmet"] = sorted(s for s, r in out["runs"].items() if not r.get("gate_met", True))
    out["range_2039_gross_median_bn"] = {
        "prior_sensitivity_S1_S6_S8_S9": [min(med[s] for s in PRIOR_RUNS if s in med), max(med[s] for s in PRIOR_RUNS if s in med)],
        "all_S1_S15": [min(med.values()), max(med.values())],
        "lowest": min(med, key=med.get), "highest": max(med, key=med.get)}
    B.write(B.OUT / "sensitivity.json", out)
    print(json.dumps(out["range_2039_gross_median_bn"], indent=1))


if __name__ == "__main__":
    main()
