"""Does V1's cash identity reproduce every stored microsimulation result? Writes data/v1/identity_check.json.

V1 (docs/METHOD.md, "Conditional volatility bands (V1)") reads gross saving off rule arithmetic:
gross = share x B x (path triple-lock level / central triple-lock level), with the levels from ``rules.rates_matrix``
at 0.1-point rounding, not from the runs. This checks that identity, through V1's own functions:

* on the five stored single-path runs: the rule-arithmetic weekly levels against the stored ones, and the gross saving
  against the stored one (the OBR long-term path pays specified triple-lock rates, so its stored rates are given);
* on the stored earnings scenarios: their draws are regenerated with the scenarios' own code and seed (this script
  imports the first model's sampler for that alone; V1 itself does not), the identity is applied to every sampled
  path, and the stratified means are compared with the stored means of the microsimulation runs.

No PolicyEngine run.

    PYTHONPATH=src python scripts/v1_identity_check.py
"""

import json
from pathlib import Path

import numpy as np

from triple_lock import ts_uncertainty as U
from triple_lock import v1_bands as V
from triple_lock.central import central_path, long_run_earnings_variant
from triple_lock.config import HORIZON

ROOT = Path(__file__).resolve().parents[1]
N_SCENARIO_DRAWS = 50_000


def inputs(run):
    return (np.array([run["statutory"]["cpi"][str(y - 1)] for y in HORIZON]),
            np.array([run["statutory"]["earnings"][str(y - 1)] for y in HORIZON]))


def single_paths(R):
    runs = V.stored_runs(R)
    base = V.base_bn(runs["central"])
    w0 = R["base_year_weekly"]["new_state_pension"]
    ca = V.rule_arithmetic(*(a[None] for a in inputs(runs["central"])))
    out = {}
    for pid, p in runs.items():
        cpi, earn = inputs(p)
        if pid == "obr_wedge":
            given = np.array([p["rates"]["triple_lock"][str(y)] if p["rate_sources"]["triple_lock"][str(y)] == "specified"
                              else np.nan for y in HORIZON])
            from triple_lock import rules
            from triple_lock.config import CENTRAL_RATE_DECIMALS
            tl = rules.rates_matrix("triple_lock", cpi, earn, HORIZON, CENTRAL_RATE_DECIMALS,
                                    specified={"triple_lock": given})
            bp = rules.rates_matrix("burnham_2030", cpi, earn, HORIZON, CENTRAL_RATE_DECIMALS)
            G = np.cumsum(np.log1p(tl) - np.log1p(bp), axis=1)
            ra = {"tl": tl, "bp": bp, "share": -np.expm1(-G), "tl_index": np.cumprod(1 + tl, axis=1)}
        else:
            ra = V.rule_arithmetic(cpi[None], earn[None])
        wk = {k: np.array([p["weekly"][k]["new_state_pension"][str(y)] for y in HORIZON])
              for k in ("triple_lock", "burnham_2030")}
        gross = np.array([p["saving_bn"][str(y)]["gross"] for y in HORIZON])
        em = V.gross_bn(ra["share"][0], ra["tl_index"][0], ca["tl_index"][0], base)
        out[pid] = {"max_abs_weekly_error_gbp": float(max(np.abs(w0 * ra["tl_index"][0] - wk["triple_lock"]).max(),
                                                          np.abs(w0 * np.cumprod(1 + ra["bp"][0]) - wk["burnham_2030"]).max())),
                    "max_abs_gross_error_bn": float(np.abs(em - gross).max()),
                    "rates_given": pid == "obr_wedge"}
    return out


def scenarios(R):
    runs = V.stored_runs(R)
    base = V.base_bn(runs["central"])
    ca = V.rule_arithmetic(*(a[None] for a in inputs(runs["central"])))
    cen = central_path()
    d0 = U.future_draws(U.PRIMARY_FORM, cen, N_SCENARIO_DRAWS)
    design = U.sample_design(d0, n_runs=160, include_zero=True)
    out = {}
    for sid, sc in R["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"].items():
        dv = U.future_draws(U.PRIMARY_FORM, long_run_earnings_variant(cen, sc["calendar_earnings_delta"],
                                                                      sc["from_year"]), N_SCENARIO_DRAWS)
        ra = V.rule_arithmetic(dv["stat_cpi"], dv["stat_earnings"])
        g = V.gross_bn(ra["share"], ra["tl_index"], ca["tl_index"], base)
        stored = sc["scenario_path_set"]["gross"]
        err = []
        for j, y in enumerate(HORIZON):
            est = sum(design["stratum_weights"][int(k)] * np.mean(g[idx, j]) for k, idx in design["sample"].items())
            err.append(est - stored[str(y)]["mean"])
        out[sid] = {"max_abs_stratified_mean_error_bn": float(np.abs(err).max()),
                    "final_year_stored_bn": stored[str(HORIZON[-1])]["mean"],
                    "final_year_error_bn": float(err[-1])}
    return out


def main():
    R = json.loads((ROOT / "data" / "results.json").read_text())
    out = {"identity": "gross = share x B x (path TL level / central TL level), levels from rules.rates_matrix",
           "no_microsimulation": True,
           "single_path_runs": single_paths(R),
           "earnings_scenarios_stratified_means": scenarios(R)}
    path = ROOT / "data" / "v1" / "identity_check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
