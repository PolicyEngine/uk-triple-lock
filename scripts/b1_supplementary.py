"""B1: the supplementary runs registered after an independent review (docs/METHOD.md, B1, "Supplementary runs after
an independent review", 12 November 2026). Writes data/b1/supplementary.json.

Sensitivities (a) to (e) and diagnostics (f) to (j). None replaces the headline. Refits use the registered sampler
settings and record the convergence gate; a refit that misses it is marked and not quoted.

    PYTHONPATH=src python scripts/b1_supplementary.py
"""

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock import ts_obr_errors as C4
from triple_lock import v1_bands as V
from triple_lock.config import ERROR_CSV, HORIZON, STATUTORY_YEARS
from triple_lock.ts_backtest import H, statutory_outturns

BASIS_SEED = 20261120
PATH_SEED_OFFSETS = (0, 1000, 2000, 3000, 4000)  # 0 is the registered seed
P = B.PRIORS
PRIOR_RUNS = {
    "b_sigma_median_1.0": {"log_sigma_mu": float(np.log(1.0))},
    "b_sigma_median_2.5": {"log_sigma_mu": float(np.log(2.5))},
    "b_sigma_logsd_0.25": {"log_sigma_sd": 0.25},
    "b_sigma_logsd_1.0": {"log_sigma_sd": 1.0},
    "b_kappa_logsd_0.25": {"log_kappa_sd": 0.25},
    "b_kappa_logsd_1.0": {"log_kappa_sd": 1.0},
    "b_zeta_sd_0.25": {"zeta_sd": 0.25},
    "b_zeta_sd_1.0": {"zeta_sd": 1.0},
}
YEARS = tuple(str(y) for y in B.REPORT_YEARS)


def gross_report(gross, G):
    """Gross saving distribution and probabilities in the report years, from (paths, HORIZON) arrays."""
    out = {}
    for y in B.REPORT_YEARS:
        j = HORIZON.index(y)
        g = gross[:, j]
        out[str(y)] = {"gross_bn": B._stats(g), "probability": {"above_0": float(np.mean(G[:, j] > 0)),
                                                                 "above_5": float(np.mean(g > 5)),
                                                                 "above_10": float(np.mean(g > 10))}}
    return out


def fit_record(diag, theta):
    return {"gate_met": diag["gate_met"], "worst": diag["worst"], "rerun": diag["settings"]["rerun"],
            "draws_retained": int(len(theta)),
            "posterior": {k: {q: v[q] for q in ("p5", "p50", "p95")} for k, v in B.posterior_summary(theta).items()}}


# ── (a) Basis split ──────────────────────────────────────────────────────────


def calendar_outturns(path=ERROR_CSV):
    """Calendar-year outturns by (target year, variable) from the error file's ``outturn`` column, as decimals."""
    cal = {}
    for r in csv.DictReader(open(path)):
        if r["outturn"] not in ("", None):
            key = (int(r["target_year"]), r["variable"])
            value = float(r["outturn"])
            if key in cal and cal[key] != value:
                raise ValueError(f"two calendar outturns for {key}")
            cal[key] = value
    return cal


def calendar_cells(cells, cal, stat):
    """The F cells on the calendar basis: a_cal = a - (statutory - calendar outturn), lags rebuilt; ``keep`` marks
    the cells whose target year has a calendar outturn for both variables."""
    keep = np.array([all((int(t), k) in cal for k in V.VARIABLES) for t in cells["target"]])
    a = cells["a"].copy()
    for i, t in enumerate(cells["target"]):
        if keep[i]:
            a[i] -= 100 * (np.array(stat[int(t)]) - np.array([cal[(int(t), k)] for k in V.VARIABLES]))
        else:
            a[i] = 0.0
    by = {(int(v), int(h)): a[i] for i, (v, h) in enumerate(zip(cells["origin"], cells["h"]))}
    lag = np.array([by[(int(v), int(h) - 1)] if h > 1 else np.zeros(2) for v, h in zip(cells["origin"], cells["h"])])
    return {**cells, "a": a, "lag": lag}, keep


def basis_record(cal, stat):
    """b(t) = statutory input less calendar outturn, points, for every year from 2011 with both: (years, (n, 2))."""
    years = sorted(t for t in stat if t >= 2011 and all((t, k) in cal for k in V.VARIABLES))
    b = np.array([100 * (np.array(stat[t]) - np.array([cal[(t, k)] for k in V.VARIABLES])) for t in years])
    return years, b


def basis_draws(n_draws, pairs, horizon, b, seed=BASIS_SEED):
    """Transitory basis terms (n_draws * 2 * pairs, horizon, 2) as decimals, in the order of B.deviations: for each
    posterior draw one Sigma_b ~ inverse-Wishart(n, sum b b'), then independent normal draws, negated on mirrors."""
    from scipy.stats import invwishart

    rng = np.random.default_rng(seed)
    S = b.T @ b
    sig = invwishart(df=len(b), scale=S).rvs(size=n_draws, random_state=rng)
    L = np.linalg.cholesky(sig)
    z = rng.standard_normal((n_draws, pairs, horizon, 2))
    x = np.einsum("dij,dphj->dphi", L, z)
    return np.concatenate([x, -x], axis=1).reshape(-1, horizon, 2) / 100, sig


def basis_split(cells, transitions, ctx, headline_median, log=print):
    cal, stat = calendar_outturns(), statutory_outturns()
    cc, keep = calendar_cells(cells, cal, stat)
    years, b = basis_record(cal, stat)
    draws, diag = B.fit(B.likelihood_data(cc, transitions, keep=keep), log=log)
    theta, _ = B.retained(draws)
    inputs = B.forward_inputs(theta)
    a1 = B.arithmetic(inputs, ctx)
    add, sig = basis_draws(len(theta), B.PAIRS, len(STATUTORY_YEARS) - 1, b)
    inputs2 = inputs.copy()
    inputs2[:, 1:] += add
    a2 = B.arithmetic(inputs2, ctx)
    del inputs, inputs2, add
    a1r, a2r = gross_report(a1["gross_bn"], a1["G"]), gross_report(a2["gross_bn"], a2["G"])
    sd = np.sqrt(np.stack([sig[:, 0, 0], sig[:, 1, 1]], axis=1))
    return {
        "cells_kept": int(keep.sum()), "cells_dropped_no_calendar_outturn": int((~keep).sum()),
        "fit": fit_record(diag, theta),
        "basis_years": years, "basis_points": {str(t): dict(zip(V.VARIABLES, map(float, x))) for t, x in zip(years, b)},
        "basis_sd_about_zero_points": dict(zip(V.VARIABLES, map(float, np.sqrt((b ** 2).mean(axis=0))))),
        "basis_mean_points": dict(zip(V.VARIABLES, map(float, b.mean(axis=0)))),
        "basis_lag1_autocorrelation": dict(zip(V.VARIABLES, (float(np.corrcoef(b[1:, k], b[:-1, k])[0, 1]) for k in (0, 1)))),
        "basis_correlation": float(np.corrcoef(b.T)[0, 1]),
        "basis_sd_posterior_points": {k: {"p5": float(np.percentile(sd[:, i], 5)), "p50": float(np.median(sd[:, i])),
                                          "p95": float(np.percentile(sd[:, i], 95))} for i, k in enumerate(V.VARIABLES)},
        "a1_calendar_errors_no_basis": a1r,
        "a2_calendar_errors_plus_basis": a2r,
        "headline_median_less_a1_median_2039_bn": float(headline_median - a1r["2039"]["gross_bn"]["p50"]),
        "a2_median_less_a1_median_2039_bn": float(a2r["2039"]["gross_bn"]["p50"] - a1r["2039"]["gross_bn"]["p50"]),
    }


# ── (c), (d): bounded inputs, real terms and share on the headline's paths ──


def headline_extras(inputs, out, ctx):
    ra = V.rule_arithmetic(inputs[:, :, 0], inputs[:, :, 1])
    ratio = ra["tl_index"] / ctx["central_tl_index"][None]
    real = ra["share"] * ctx["base"][None]
    clipped = np.maximum(inputs, 0.0)
    clipped[:, 0] = inputs[:, 0]  # 2026 is the published input
    oc = B.arithmetic(clipped, ctx)
    series, _ = V.statutory_history(B.OUTTURN_FIRST, B.RECORD_LAST)
    hist = np.array([series[y] for y in range(B.OUTTURN_FIRST, B.RECORD_LAST + 1)])
    fwd = inputs[:, 1:]
    by_year = {}
    for j, y in enumerate(HORIZON):
        by_year[str(y)] = {
            "real_gross_bn": B._stats(real[:, j]),
            "real_probability": {"above_5": float(np.mean(real[:, j] > 5)), "above_10": float(np.mean(real[:, j] > 10))},
            "share": B._stats(out["share"][:, j]),
            "tl_index_ratio": B._stats(ratio[:, j]),
            "cash_gross_bn": B._stats(out["gross_bn"][:, j]),
            "net_bn": B._stats(out["net_bn"][:, j]),
        }
    return {
        "d_real_terms_and_share": {
            "definition": "real_gross_bn = share(y) x B(y): the gross saving at the central path's levels, without "
                          "the factor I_path(y) / I_central(y) (tl_index_ratio)",
            "by_year": by_year},
        "c_bounded_inputs": {
            "definition": "every statutory input 2027-2038 below zero set to zero, both variables, on the headline's paths",
            "report": gross_report(oc["gross_bn"], oc["G"]),
            "share_of_path_years_below_zero": {k: float((fwd[:, :, i] < 0).mean()) for i, k in enumerate(V.VARIABLES)},
            "share_of_paths_with_any_cpi_year_below_zero": float((fwd[:, :, 0] < 0).any(axis=1).mean()),
            "history_years_below_zero_1989_2025": {k: int((hist[:, i] < 0).sum()) for i, k in enumerate(V.VARIABLES)},
            "history_years": int(len(hist)),
        },
    }


# ── (e) Gap spread, post hoc ─────────────────────────────────────────────────


def gap_spread(theta, n=B.N_REPLICATIONS, seed=B.PREDICTIVE_SEED + 3):
    """The registered replications of validation 2(a), same draws and seed; the earnings-less-CPI error spread."""
    years, forecast, errors = B.complete_record()
    sub = theta[(np.arange(n) * len(theta)) // n]
    first, last = int(years.min()) + 1, int(years.max()) + H
    u, Phi = B.shocks(sub, 1, last - first + 1, np.random.default_rng(seed))
    u = u[:, 0]
    e = np.zeros((n, len(years), H, 2))
    for i, v in enumerate(years):
        prev = np.zeros((n, 2))
        for h in range(H):
            prev = np.einsum("dij,dj->di", Phi, prev) + u[:, v + h + 1 - first]
            e[:, i, h] = prev
    out = {}
    for h in range(H):
        real = float((errors[:, h, 1] - errors[:, h, 0]).std(ddof=1))
        rep = (e[:, :, h, 1] - e[:, :, h, 0]).std(axis=1, ddof=1)
        out[f"h{h + 1}"] = {"realised": real, "replicated_p1": float(np.percentile(rep, 1)),
                            "replicated_p50": float(np.median(rep)), "replicated_p99": float(np.percentile(rep, 99)),
                            "share_at_or_above_realised": float(np.mean(rep >= real)),
                            "outside_central_98": bool(real < np.percentile(rep, 1) or real > np.percentile(rep, 99))}
    return {"label": "post hoc: suggested by the review after the registered checks were seen", "replications": n,
            "cells": int(errors.shape[0] * H), "statistic": "sd across complete-origin cells of earnings error less CPI error",
            "by_horizon": out}


# ── (f) Path seeds in the backtest ───────────────────────────────────────────


def backtest_seeds(cells, transitions, log=print):
    spec = importlib.util.spec_from_file_location("b1_backtest", Path(__file__).with_name("b1_backtest.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    record = C4.load_record()
    out = {}
    for hold_out in bt.HOLD_OUTS:
        thetas, fits = bt.refits(hold_out, record, cells, transitions, log=lambda *a: None)
        rows = []
        for off in PATH_SEED_OFFSETS:
            res = bt.score(hold_out, record, thetas, fits, path_seed_offset=off)
            fb = [c for c in res["checks_against_c2_c4_limits"] if c["test"] == "A" and c["check"] == "|floor_bias|"]
            rows.append({"path_seed_offset": off, "test_a_floor_bias": fb[0]["value"] if fb else None,
                         "c4_rule_would_pass": res["c4_rule_would_pass"], "c4_rule_failures": res["c4_rule_failures"]})
            log(f"(f) {hold_out} offset {off}: floor bias {rows[-1]['test_a_floor_bias']:.4f} pass {res['c4_rule_would_pass']}")
        out[hold_out] = {"all_refits_met_the_convergence_gate": all(f["gate_met"] for f in fits.values()),
                         "by_path_seed": rows, "floor_bias_range": [min(r["test_a_floor_bias"] for r in rows),
                                                                     max(r["test_a_floor_bias"] for r in rows)],
                         "seeds_passing": sum(r["c4_rule_would_pass"] for r in rows)}
    return out


# ── (i), (j) ─────────────────────────────────────────────────────────────────


def level_misses(cells):
    out = {}
    for name, lo, hi in (("origins_2010_2016", 2010, 2016), ("origins_2017_2022", 2017, 2022)):
        sel = (cells["origin"] >= lo) & (cells["origin"] <= hi)
        out[name] = {f"h{h}": {"n": int((sel & (cells["h"] == h)).sum()),
                               **dict(zip(V.VARIABLES, map(float, cells["a"][sel & (cells["h"] == h)].mean(axis=0)))),
                               "earnings_negative": int((cells["a"][sel & (cells["h"] == h), 1] < 0).sum())}
                     for h in range(1, H + 1)}
    return out


def residual_correlation(cells, theta):
    w = B.cell_weights(cells)

    def corr(Phi):
        r = cells["a"] - cells["lag"] @ Phi.T
        m = (w[:, None] * r).sum(axis=0) / w.sum()
        c = (w[:, None, None] * np.einsum("ni,nj->nij", r - m, r - m)).sum(axis=0)
        return float(c[0, 1] / np.sqrt(c[0, 0] * c[1, 1]))

    def corr0(Phi):  # about zero, as the likelihood's location
        r = cells["a"] - cells["lag"] @ Phi.T
        c = (w[:, None, None] * np.einsum("ni,nj->nij", r, r)).sum(axis=0)
        return float(c[0, 1] / np.sqrt(c[0, 0] * c[1, 1]))

    Phi_all, _, _ = B.unpack(theta)
    med = np.median(theta, axis=0)
    Pm = B.unpack(med[None])[0][0]
    sub = Phi_all[:: max(1, len(theta) // 1000)]
    c0 = np.array([corr0(p) for p in sub])
    return {"at_posterior_median_phi": {"about_mean": corr(Pm), "about_zero": corr0(Pm)},
            "about_zero_over_posterior_draws": {"p5": float(np.percentile(c0, 5)), "p50": float(np.median(c0)),
                                                "p95": float(np.percentile(c0, 95))},
            "rho_F_posterior_median": float(np.median(np.tanh(theta[:, B.PARAMS.index("z_rho")]))),
            "rho_F_prior_median": float(np.tanh(P["z_mu"]))}


def main():
    cells, transitions = B.error_cells(), B.outturn_transitions()
    _, theta, _ = B.load_posterior()
    ctx = B.cash_context()
    log = lambda *a: print(*a, flush=True)  # noqa: E731
    inputs = B.forward_inputs(theta)
    out_h = B.arithmetic(inputs, ctx)
    head = gross_report(out_h["gross_bn"], out_h["G"])
    out = {**B.provenance(), "spec": "docs/METHOD.md, B1, Supplementary runs after an independent review",
           "status": "sensitivities and diagnostics; none replaces the headline", "headline": head}
    out.update(headline_extras(inputs, out_h, ctx))
    del inputs, out_h
    log("(c)", out["c_bounded_inputs"]["report"]["2039"])
    out["e_gap_spread_post_hoc"] = gap_spread(theta)
    log("(e) done")

    out["a_basis_split"] = basis_split(cells, transitions, ctx, head["2039"]["gross_bn"]["p50"], log=log)
    log("(a)", out["a_basis_split"]["a1_calendar_errors_no_basis"]["2039"], out["a_basis_split"]["a2_calendar_errors_plus_basis"]["2039"])

    out["b_prior_runs"] = {}
    for k, pr in PRIOR_RUNS.items():
        draws, diag = B.fit(B.likelihood_data(cells, transitions), pr, log=log)
        th, _ = B.retained(draws)
        o = B.arithmetic(B.forward_inputs(th), ctx)
        out["b_prior_runs"][k] = {"priors_changed": pr, **fit_record(diag, th), **gross_report(o["gross_bn"], o["G"])}
        log("(b)", k, diag["gate_met"], out["b_prior_runs"][k]["2039"]["gross_bn"]["p50"])
    meds = [r["2039"]["gross_bn"]["p50"] for r in out["b_prior_runs"].values() if r["gate_met"]]
    out["b_range_2039_gross_median_bn"] = [min(meds), max(meds)]

    o = B.arithmetic(B.forward_inputs(theta, delta_sd=tuple(4 * x for x in P["delta_sd"])), ctx)
    out["g_delta_times_4"] = gross_report(o["gross_bn"], o["G"])
    del o

    out["h_horizons"] = {}
    for name, keep in (("h1_only", cells["h"] == 1), ("h2plus_only", cells["h"] >= 2)):
        draws, diag = B.fit(B.likelihood_data(cells, transitions, keep=keep), log=log)
        th, _ = B.retained(draws)
        o = B.arithmetic(B.forward_inputs(th), ctx)
        out["h_horizons"][name] = {"cells": int(keep.sum()), **fit_record(diag, th), **gross_report(o["gross_bn"], o["G"])}
        log("(h)", name, out["h_horizons"][name]["2039"]["gross_bn"]["p50"])

    out["i_level_misses_points"] = level_misses(cells)
    out["j_residual_correlation"] = residual_correlation(cells, theta)
    out["f_backtest_path_seeds"] = backtest_seeds(cells, transitions, log=log)
    B.write(B.OUT / "supplementary.json", out)
    log("written")


if __name__ == "__main__":
    main()
