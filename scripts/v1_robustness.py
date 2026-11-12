"""Robustness of V1 (docs/METHOD.md, "Conditional volatility bands (V1)", Changes of 12 November 2026).

Not part of the V1 specification: each run below changes one stated assumption and reports the final year's gross
saving, so the paper can say how far its two settings move. Every run uses V1's own estimator, draws, centre, rule
arithmetic and cash identity (``triple_lock.v1_bands``), the same 400,000 paths, and no PolicyEngine run.

* the innovation correlation set to 0 and to 0.8, holding the innovation standard deviations and persistence;
* no persistence (phi = 0), holding the innovations' covariance;
* the span starting in 2001, the first year of May-July earnings growth (KAC3), so no national-accounts year enters;
* setting (b) also without 2020;
* a VAR(1) with cross-lags in place of the two separate AR(1)s;
* innovations resampled from the estimated residuals (demeaned, rows kept together) in place of normal draws;
* the innovation covariance taken about zero rather than about the residuals' mean (``np.cov`` demeans them).

It also records what the paper's comparison with the scenarios and the second model rests on: how often the CPI and
earnings lead passes between them (``ts_backtest.switches``) on V1's paths, on V1's paths without persistence and on
the first model's paths behind the earnings scenarios (regenerated with that model's code and seed, as
``scripts/v1_identity_check.py`` does; V1 itself does not import it); the year-to-year correlation of each set's
statutory inputs; V1's statutory input standard deviation by year; and the OBR's forecast errors, calendar-year
(``data/obr_forecast_error_summary.csv``) and statutory (spring forecasts against September CPI and May-July earnings
growth).

    PYTHONPATH=src python scripts/v1_robustness.py
"""

import csv
import json
from pathlib import Path

import numpy as np

from triple_lock import v1_bands as V
from triple_lock.central import central_path, long_run_earnings_variant
from triple_lock.config import ACTUALS_CSV, ERROR_CSV, HORIZON
from triple_lock.ts_backtest import switches

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "v1" / "robustness.json"
SUMMARY_CSV = ROOT / "data" / "obr_forecast_error_summary.csv"
RESAMPLE_SEED = 20261113
WITHOUT_2020 = (2020, *V.EXCLUDED)
QS = (5, 50, 95)


def final_year(st, base, central, rho, ca):
    """Final-year gross quantiles, mean share and mean CPI-earnings lead switches for statutory inputs ``st``."""
    ra = V.rule_arithmetic(st[:, :, 0], st[:, :, 1])
    gross = V.gross_bn(ra["share"], ra["tl_index"], ca["tl_index"], base)[:, -1]
    return {"gross_bn": {f"p{q}": float(np.percentile(gross, q)) for q in QS},
            "share_mean": float(ra["share"][:, -1].mean()), "share_p50": float(np.median(ra["share"][:, -1])),
            "lead_switches_mean": float(switches(st).mean())}


def var_deviations(A, sigma, z):
    """epsilon(t) = A epsilon(t-1) + L z(t), epsilon(2026) = 0, with 2026 prepended."""
    L = np.linalg.cholesky(sigma)
    eps = np.zeros((z.shape[0], z.shape[1] + 1, 2))
    for j in range(z.shape[1]):
        eps[:, j + 1] = eps[:, j] @ A.T + z[:, j] @ L.T
    return eps


def resampled_deviations(phi, u, n_paths, n_years, seed=RESAMPLE_SEED):
    """epsilon(t) = diag(phi) epsilon(t-1) + u*, u* drawn with replacement from the demeaned residual rows."""
    u = u - u.mean(axis=0)
    idx = np.random.default_rng(seed).integers(0, len(u), size=(n_paths, n_years))
    eps = np.zeros((n_paths, n_years + 1, 2))
    for j in range(n_years):
        eps[:, j + 1] = phi * eps[:, j] + u[idx[:, j]]
    return eps


def residuals(est, series):
    lag = np.array([np.array(series[a]) - est["anchor"] for a, _ in est["pairs"]])
    cur = np.array([np.array(series[b]) - est["anchor"] for _, b in est["pairs"]])
    return lag, cur


def var1(est, series):
    """Least squares through the origin of each deviation on both lagged deviations, over V1's lag pairs."""
    lag, cur = residuals(est, series)
    A = np.linalg.lstsq(lag, cur, rcond=None)[0].T
    u = cur - lag @ A.T
    if np.max(np.abs(np.linalg.eigvals(A))) >= 1:
        raise ValueError("VAR(1) not stationary")
    return A, np.cov(u, rowvar=False, ddof=1)


def year_to_year_correlation(st):
    """Mean over consecutive determination years from 2027 of the across-path correlation of each input with itself
    a year earlier."""
    out = {}
    for i, v in enumerate(V.VARIABLES):
        x = st[:, 1:, i]
        out[v] = float(np.mean([np.corrcoef(x[:, j - 1], x[:, j])[0, 1] for j in range(1, x.shape[1])]))
    return out


def obr_errors():
    """Calendar-year errors (the committed summary) and statutory errors of the spring forecasts, horizons 1-5."""
    with SUMMARY_CSV.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["sample"] in ("spring_vintages", "all_vintages")]
    cal = {}
    for r in rows:
        if r["sd_error"]:
            cal.setdefault(r["sample"], {}).setdefault(r["variable"], {})[r["horizon_years"]] = {
                "n": int(r["n"]), "sd": float(r["sd_error"]),
                "corr_cpi_earnings": float(r["corr_cpi_earnings_error"]) if r["corr_cpi_earnings_error"] else None}
    with ACTUALS_CSV.open(newline="") as f:
        stat = {int(r["determination_year"]): (float(r["cpi_september_12m"]), float(r["awe_total_pay_may_jul_3m_yoy"]))
                for r in csv.DictReader(f)}
    fc = {}
    with ERROR_CSV.open(newline="") as f:
        for r in csv.DictReader(f):
            fc[(r["forecast_vintage"], int(r["target_year"]), int(r["horizon_years"]), r["variable"])] = float(r["forecast"])
    statutory = {}
    for h in range(1, 6):
        pairs = [(stat[t][0] - fc[(v, t, h, "cpi")], stat[t][1] - fc[(v, t, h, "earnings")])
                 for (v, t, hh, var) in fc if hh == h and var == "cpi" and (v, t, h, "earnings") in fc and t in stat]
        if len(pairs) < 3:
            continue
        e = np.array(pairs)
        statutory[str(h)] = {"n": len(e), "sd": dict(zip(V.VARIABLES, map(float, e.std(axis=0, ddof=1)))),
                             "corr_cpi_earnings": float(np.corrcoef(e.T)[0, 1])}
    return {"calendar_year_summary": {"source": "data/obr_forecast_error_summary.csv",
                                      "measure": "calendar-year CPI inflation and average earnings growth, OBR "
                                                 "forecast against calendar-year outturn", **cal},
            "statutory_spring": {"source": "data/obr_forecast_errors.csv forecasts against data/triple_lock_actual_inputs.csv",
                                 "measure": "September CPI and May-July earnings growth (latest vintage) less the "
                                            "spring forecast's calendar-year figure for the same year",
                                 "by_horizon": statutory}}


def build():
    results = json.loads(V.RESULTS.read_text())
    central = central_path()
    series, _ = V.statutory_history()
    base = V.base_bn(V.central_run(results))
    rho = V.net_ratio(results)[0]
    c = V.centre(central)
    ca = V.rule_arithmetic(c[None, :, 0], c[None, :, 1])
    z = V.normals()
    fy = lambda st: final_year(st, base, central, rho, ca)  # noqa: E731
    excluded = {"a": (), "b": V.EXCLUDED}
    runs, input_sd, persistence = {}, {}, {}
    for k, exc in excluded.items():
        est = V.estimate(series, exc)
        sd = np.sqrt(np.diag(est["sigma"]))
        st = V.paths(est, z, central)
        input_sd[k] = {v: [float(x) for x in st[:, 1:, i].std(axis=0)] for i, v in enumerate(V.VARIABLES)}
        persistence[k] = year_to_year_correlation(st)
        r = {"registered_setting": fy(st)}
        for rho_u in (0.0, 0.8):
            s = np.diag(sd) @ np.array([[1, rho_u], [rho_u, 1]]) @ np.diag(sd)
            r[f"innovation_correlation_{rho_u}"] = fy(V.paths({**est, "sigma": s}, z, central))
        st0 = V.paths({**est, "phi": np.zeros(2)}, z, central)
        r["phi_0"] = fy(st0)
        persistence[f"{k}_phi_0"] = year_to_year_correlation(st0)
        r["from_2001"] = fy(V.paths(V.estimate({y: s for y, s in series.items() if y >= V.FIRST_KAC3_YEAR}, exc), z,
                                    central))
        A, s_var = var1(est, series)
        r["var1_cross_lags"] = {**fy(c[None] + var_deviations(A, s_var, z)), "A": A.tolist()}
        lag, cur = residuals(est, series)
        u = cur - est["phi"] * lag
        r["sigma_not_demeaned"] = fy(V.paths({**est, "sigma": u.T @ u / (len(u) - 1)}, z, central))
        r["resampled_residuals"] = fy(c[None] + resampled_deviations(est["phi"], u, len(z), z.shape[1]))
        if k == "b":
            r["without_2020"] = fy(V.paths(V.estimate(series, WITHOUT_2020), z, central))
        runs[k] = r
    # The first model's paths behind the two earnings scenarios (as scripts/v1_identity_check.py regenerates them).
    from triple_lock import ts_uncertainty as U

    scen = {}
    for sid, sc in results["scenario_envelope"]["paired_earnings_mean_paths"]["scenarios"].items():
        dv = U.future_draws(U.PRIMARY_FORM, long_run_earnings_variant(central, sc["calendar_earnings_delta"],
                                                                      sc["from_year"]), 50_000)
        st = np.stack([dv["stat_cpi"], dv["stat_earnings"]], axis=2)
        scen[sid] = {"lead_switches_mean": float(switches(st).mean()), "year_to_year_correlation":
                     year_to_year_correlation(st)}
        del dv, st
    return {"label": V.LABEL, "not_the_specification": "robustness runs; each changes one stated V1 assumption",
            "n_paths": int(len(z)), "seed": V.SEED, "resample_seed": RESAMPLE_SEED, "final_year": HORIZON[-1],
            "runs": runs, "statutory_input_sd_by_year": {"years": list(range(2027, 2039)), **input_sd},
            "year_to_year_correlation": persistence, "first_model_earnings_scenarios": scen,
            "obr_forecast_errors": obr_errors()}


def main():
    out = build()
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for k, r in out["runs"].items():
        for name, v in r.items():
            print(k, name, {q: round(x, 2) for q, x in v["gross_bn"].items()}, "share mean", round(100 * v["share_mean"], 2),
                  "p50", round(100 * v["share_p50"], 2), "switches", round(v["lead_switches_mean"], 2))
    print(json.dumps({k: out[k] for k in ("year_to_year_correlation", "first_model_earnings_scenarios")}, indent=1))
    print(json.dumps(out["obr_forecast_errors"]["statutory_spring"]["by_horizon"], indent=1))


if __name__ == "__main__":
    main()
