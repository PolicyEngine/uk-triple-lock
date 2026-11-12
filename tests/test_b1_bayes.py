"""B1, the Bayesian forecast of the uprating inputs (docs/METHOD.md, B1; data/b1/)."""

import hashlib
import json

import numpy as np
import pytest

from triple_lock import b1_bayes as B
from triple_lock import ts_obr_errors as C4
from triple_lock import v1_bands as V
from triple_lock.config import HORIZON, REPO, STATUTORY_YEARS

OUT = REPO / "data" / "b1"
FIT = json.loads((OUT / "fit.json").read_text())
FORECAST = json.loads((OUT / "forecast.json").read_text())
VALIDATION = json.loads((OUT / "validation.json").read_text())
BACKTEST = json.loads((OUT / "backtest.json").read_text())
SENSITIVITY = json.loads((OUT / "sensitivity.json").read_text())
GATE_RECORD = json.loads((OUT / "gate_record.json").read_text())
METHOD = (REPO / "docs" / "METHOD.md").read_text()
RESULTS = json.loads((REPO / "data" / "results.json").read_text())


def same_up_to_rounding(a, b, rel=1e-9):
    if isinstance(a, dict):
        return set(a) == set(b) and all(same_up_to_rounding(a[k], b[k], rel) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same_up_to_rounding(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return b == pytest.approx(a, rel=rel, abs=1e-12)
    return a == b


# ── The specification and the ruling ─────────────────────────────────────────


def test_spec_is_outside_the_frozen_sections_and_records_the_ruling():
    head = METHOD.index("## Bayesian forecast of the uprating inputs (B1)")
    assert head > METHOD.index("## Conditional volatility bands (V1)") > METHOD.index("<!-- C4 frozen rule ends -->")
    section = METHOD[head:]
    assert '> "No - we need to make it a forecast we can stand behind"' in section
    assert '> "Not sensitivity - take a Bayesian approach"' in section
    assert "12 November 2026 at 14:23" in section
    assert "designed after the first model failed C2, the second failed C4 and V1" in section
    assert "not a pass/fail gate" in section and "The one hard gate is numerical" in section
    for f in (FIT, FORECAST, VALIDATION, BACKTEST, SENSITIVITY):
        assert f["spec_commit"] == B.SPEC_COMMIT and f["no_microsimulation"] is True
    assert "not tested, validated or calibrated" in FORECAST["label"]


def test_the_unmet_gate_and_its_fix_are_on_the_record():
    record = METHOD[METHOD.index("**Record of order and of the first fit, 12 November 2026"):]
    assert "74 transitions flagged divergent" in record and "gave 0 divergent transitions" in record
    assert "is Max's ruling" in record and B.SPEC_COMMIT in record
    wall, fixed = GATE_RECORD["wall_coded"], GATE_RECORD["fixed"]
    assert wall["commit"].startswith("8c798a0")
    for y in ("2034", "2039"):  # the reading of the gate does not move the answer beyond Monte Carlo error
        for q in ("p50", "p95"):
            se = max(fixed[y]["monte_carlo_se"][f"gross_{q}"], wall[y]["monte_carlo_se"][f"gross_{q}"])
            assert abs(GATE_RECORD["difference_fixed_less_wall"][y][q]) < 4 * se


def test_priors_are_the_specified_numbers():
    p = B.PRIORS
    assert p["phi_mu"] == (0.5, 0.1, 0.2, 0.5) and p["phi_sd"] == (0.25, 0.2, 0.2, 0.25)
    assert p["log_sigma_mu"] == pytest.approx(np.log(1.5)) and p["log_sigma_sd"] == 0.5
    assert (p["z_mu"], p["z_sd"], p["zeta_sd"], p["log_kappa_sd"]) == (0.4, 0.5, 0.5, 0.5)
    assert (p["nu_shape"], p["nu_rate"], p["nu_fixed"]) == (2.0, 0.1, 0.0)
    assert p["m_mu"] == (2.0, 4.0) and p["m_sd"] == (0.5, 1.0) and p["delta_sd"] == (0.25, 0.5)
    assert FIT["priors"] == json.loads(json.dumps(p))
    assert (B.CHAINS, B.WARMUP, B.KEPT, B.TARGET_ACCEPT, B.MCMC_SEED) == (4, 1500, 2500, 0.95, 20261112)
    assert B.GATE == {"rhat_max": 1.01, "ess_min": 1000, "divergences_max": 10} and B.RADIUS_MAX == 0.98


# ── Data: each year enters once ──────────────────────────────────────────────


def test_error_cells_are_the_record_and_each_target_year_weighs_one():
    cells = B.error_cells()
    assert len(cells["target"]) == 55 and sorted(set(cells["target"].tolist())) == list(range(2011, 2027))
    w = B.cell_weights(cells)
    for t in range(2011, 2027):
        assert w[cells["target"] == t].sum() == pytest.approx(1.0)
    rec = C4.load_record()  # the complete origins' errors are C4's statutory errors
    for i, v in enumerate(rec["years"]):
        for h in range(1, 5):
            sel = (cells["origin"] == v) & (cells["h"] == h)
            assert sel.sum() == 1
            assert cells["a"][sel][0] == pytest.approx(100 * rec["statutory"][i, h - 1], abs=1e-9)
            lag = 100 * rec["statutory"][i, h - 2] if h > 1 else np.zeros(2)
            assert cells["lag"][sel][0] == pytest.approx(lag, abs=1e-9)
    assert FIT["data"]["error_cells"] == 55 and FIT["data"]["error_target_years"] == 16


def test_outturn_block_stops_where_the_error_record_starts():
    data = B.likelihood_data()
    years = B.outturn_transitions()["year"]
    assert years[data["w_o"] > 0].tolist() == list(range(1990, 2011)) and data["w_o"].sum() == 21
    assert FIT["data"]["outturn_transition_years"] == list(range(1990, 2011))
    assert min(B.error_cells()["target"]) == 2011  # no year is in both blocks


def test_hold_outs_and_exclusions_drop_the_right_cells():
    cells = B.error_cells()
    hot = B.touches(cells, B.HOT_YEARS)
    for t, h, drop in zip(cells["target"], cells["h"], hot):
        assert drop == (t in B.HOT_YEARS or (h >= 2 and t - 1 in B.HOT_YEARS))
    assert (cells["target"][~hot] == 2024).sum() == 1  # only the one-year-ahead 2024 cell survives
    w = B.cell_weights(cells, ~hot)
    assert w[hot].sum() == 0 and w.sum() == pytest.approx(len(set(cells["target"][~hot].tolist())))
    d = B.demeaned(cells)
    for h in range(1, 5):
        assert d["a"][d["h"] == h].mean(axis=0) == pytest.approx([0, 0], abs=1e-12)
    assert (d["lag"][d["h"] == 1] == 0).all()


# ── Convergence ──────────────────────────────────────────────────────────────


def test_diagnostics_tell_good_chains_from_bad():
    rng = np.random.default_rng(0)
    good = rng.standard_normal((4, 2000, len(B.PARAMS)))
    d = B.diagnostics(good, 0)
    assert d["gate_met"] and d["worst"]["rhat"] < 1.01 and 6000 < d["worst"]["ess_bulk"] < 11000
    sticky = np.zeros_like(good)
    for t in range(1, good.shape[1]):
        sticky[:, t] = 0.95 * sticky[:, t - 1] + good[:, t]
    assert 100 < B.diagnostics(sticky, 0)["worst"]["ess_bulk"] < 600  # iid/39 in theory
    apart = good + np.arange(4)[:, None, None]
    assert B.diagnostics(apart, 0)["worst"]["rhat"] > 1.3 and not B.diagnostics(apart, 0)["gate_met"]
    assert not B.diagnostics(good, 11)["gate_met"]


def test_stored_posterior_meets_the_gate_on_the_chains_as_run():
    assert hashlib.sha256(B.POSTERIOR.read_bytes()).hexdigest() == FIT["posterior_sha256"] == FORECAST["posterior_sha256"]
    draws, theta, chain = B.load_posterior()
    assert draws.shape == (B.CHAINS, B.KEPT, len(B.PARAMS))
    conv = FIT["convergence"]
    again = B.diagnostics(draws, conv["worst"]["divergences"])
    assert again["gate_met"] and conv["gate_met"] and FIT["headline_permitted"]
    assert again["worst"]["rhat"] == pytest.approx(conv["worst"]["rhat"], rel=1e-6)
    assert again["worst"]["ess_bulk"] == pytest.approx(conv["worst"]["ess_bulk"], rel=1e-6)
    assert conv["worst"]["divergences"] <= 10 and not FIT["sampler"]["rerun"]
    assert len(theta) == FIT["radius_bound"]["draws_retained"] == draws.shape[0] * draws.shape[1] - FIT["radius_bound"]["draws_outside"]
    assert (B.spectral_radius(theta) < B.RADIUS_MAX).all() and len(chain) == len(theta)
    assert FORECAST["n_paths"] == len(theta) * 2 * B.PAIRS >= 100_000


def test_refit_agrees_with_the_stored_posterior():
    pytest.importorskip("numpyro")
    draws, diag = B.fit(B.likelihood_data(), log=lambda *_: None)
    assert diag["gate_met"]
    new, old = B.posterior_summary(B.retained(draws)[0]), FIT["posterior"]
    for k in old:  # NUTS is not bit-stable across platforms: agreement to a tenth of a posterior standard deviation
        assert abs(new[k]["p50"] - old[k]["p50"]) < 0.1 * old[k]["sd"], k


# ── The forward process ──────────────────────────────────────────────────────


def test_paths_are_centred_mirrored_and_shifted_only_from_2031():
    _, theta, _ = B.load_posterior()
    sub = theta[:50]
    x = B.forward_inputs(sub, pairs=10)
    c = V.centre()
    assert x.shape == (50 * 20, len(STATUTORY_YEARS), 2)
    assert (x[:, 0] == c[0]).all()  # 2026 is the published input on every path
    dev = (x - c[None]).reshape(50, 20, len(STATUTORY_YEARS), 2)
    assert dev[:, :10] == pytest.approx(-dev[:, 10:], abs=1e-12)  # mirror images within each draw
    assert np.abs(dev.mean(axis=1)).max() < 1e-12
    none = B.forward_inputs(sub, pairs=10, delta_sd=(0.0, 0.0))
    i31 = STATUTORY_YEARS.index(2031)
    assert (x[:, :i31] == none[:, :i31]).all() and not np.allclose(x[:, i31:], none[:, i31:])
    assert FORECAST["mean_input_deviation_max_abs_points"] < 1e-8
    assert FORECAST["long_run_shift"]["from_determination_year"] == 2031


def test_shocks_have_the_t_scale_and_the_process_its_persistence():
    theta = np.zeros((1, len(B.PARAMS)))
    p = {k: j for j, k in enumerate(B.PARAMS)}
    theta[0, p["phi_cc"]], theta[0, p["phi_ee"]], theta[0, p["phi_ec"]] = 0.5, 0.3, 0.2
    theta[0, p["log_sigma_c"]], theta[0, p["log_sigma_e"]], theta[0, p["z_rho"]] = np.log(1.0), np.log(2.0), np.arctanh(0.5)
    theta[0, p["nu_m2"]] = 8.0  # nu = 10
    u, Phi = B.shocks(theta, 200_000, 2, np.random.default_rng(1))
    cov = np.cov(u[0, :, 0].T)
    assert cov == pytest.approx(10 / 8 * np.array([[1.0, 1.0], [1.0, 4.0]]), rel=0.03)
    assert Phi[0] == pytest.approx(np.array([[0.5, 0.0], [0.2, 0.3]]))
    dev = 100 * B.deviations(theta, 200_000, 2, np.random.default_rng(1), antithetic=False)
    slope = np.linalg.lstsq(dev[:, 0], dev[:, 1], rcond=None)[0].T  # year 2 on year 1
    assert slope == pytest.approx(Phi[0], abs=0.02)
    wide = B.shocks(theta, 200_000, 1, np.random.default_rng(2), scale="O")[0]
    assert np.cov(wide[0, :, 0].T) == pytest.approx(cov, rel=0.05)  # kappa = 1, zeta = 0: the same scale


def test_prior_draws_respect_the_bound():
    t = B.prior_draws(2000)
    assert t.shape == (2000, len(B.PARAMS)) and (B.spectral_radius(t) < B.RADIUS_MAX).all()
    d = B.derived(t)
    assert np.median(d["sigma_c"]) == pytest.approx(1.5, rel=0.08) and np.median(d["rho_F"]) == pytest.approx(0.38, abs=0.05)
    assert d["nu"].min() > 2


# ── Cash: the identity, re-checked through B1's own functions ────────────────


def test_identity_reproduces_every_stored_run():
    ctx = B.cash_context(RESULTS)
    for pid, run in V.stored_runs(RESULTS).items():
        if pid == "obr_wedge":  # pays specified triple-lock rates; checked with the rates given in data/v1
            continue
        inputs = np.array([[run["statutory"][k][str(y - 1)] for k in V.VARIABLES] for y in HORIZON])[None]
        out = B.arithmetic(inputs, ctx)
        stored = np.array([run["saving_bn"][str(y)]["gross"] for y in HORIZON])
        assert np.abs(out["gross_bn"][0] - stored).max() < 1e-5, pid
    c = B.arithmetic(V.centre()[None], ctx)
    for j, y in enumerate(HORIZON):
        assert FORECAST["central_rule_arithmetic"][str(y)]["gross_bn"] == pytest.approx(c["gross_bn"][0, j], abs=1e-9)
    assert FORECAST["net_ratio"]["rho"] == pytest.approx(V.net_ratio(RESULTS)[0], abs=1e-12)


def test_summaries_are_ordered_and_consistent():
    rho = FORECAST["net_ratio"]["rho"]
    for y in map(str, HORIZON):
        row = FORECAST["by_year"][y]
        for k in ("G", "share", "gross_bn", "net_bn"):
            q = [row[k][f"p{p}"] for p in B.QUANTILES]
            assert q == sorted(q) and q[0] >= 0
        assert row["net_bn"]["p50"] == pytest.approx(rho * row["gross_bn"]["p50"])
        pr = row["probability"]
        assert 1 >= pr["gross"]["above_0"] >= pr["gross"]["above_5"] >= pr["gross"]["above_10"] >= 0
        assert pr["gross"]["above_5"] >= pr["net"]["above_5"] and pr["gross"]["above_10"] >= pr["net"]["above_10"]
        assert set(FORECAST["monte_carlo_se"][y]) >= {"gross_p5", "gross_p50", "gross_p95", "p_above_0", "p_gross_above_10"}
    for y in ("2034", "2039"):  # a positive saving is the complement of the rules paying the same
        assert FORECAST["by_year"][y]["probability"]["gross"]["above_0"] == pytest.approx(1 - FORECAST["pay_same_share"][y], abs=1e-12)
        assert len(FORECAST["by_chain"]) == B.CHAINS
        lo, hi = FORECAST["range_across_chains"][y]["gross_p50"]
        assert lo <= FORECAST["by_year"][y]["gross_bn"]["p50"] <= hi
        assert FORECAST["conditional_on_parameters"][y]["gross_median_bn"]["sd"] > 0


def test_committed_forecast_and_validation_regenerate_from_the_stored_draws():
    forecast, validation = B.build_forecast()
    assert same_up_to_rounding(json.loads(json.dumps(forecast, default=float)), FORECAST)
    assert same_up_to_rounding(json.loads(json.dumps(validation, default=float)), VALIDATION)


# ── Validation outputs ───────────────────────────────────────────────────────


def test_validation_reports_every_committed_check():
    stats = VALIDATION["replicated_error_records"]["statistics"]
    want = {"floor_share", "switches_per_path", "max_abs_error_points"}
    want |= {f"sd_{v}_h{h}" for v in V.VARIABLES for h in range(1, 5)} | {f"corr_h{h}" for h in range(1, 5)}
    assert set(stats) == want and VALIDATION["replicated_error_records"]["replications"] == 4000
    flagged = sorted(k for k, s in stats.items() if s["outside_central_98"])
    assert flagged == VALIDATION["replicated_error_records"]["outside_central_98"]
    assert VALIDATION["prior_predictive"]["draws"] == 10_000
    assert set(VALIDATION["prior_predictive"]["input_deviation_sd_points"]) == {"2027", "2030", "2038"}
    hist = VALIDATION["forward_paths_against_history"]["history_2001_2025"]
    assert hist["floor_share"] == pytest.approx(7 / 25) and hist["lead_changes_per_year"] == pytest.approx(8 / 24)


def test_backtest_uses_c4s_limits_and_reports_both_hold_outs():
    assert BACKTEST["limits"] == json.loads(json.dumps(C4.LIMITS)) and "not a pass/fail gate" in BACKTEST["status"]
    assert set(BACKTEST["hold_outs"]) == {"chronological", "target_year"}
    for r in BACKTEST["hold_outs"].values():
        assert len(r["fits"]) == 13 and len(r["origins"]["B"]) == 13 and len(r["origins"]["A"]) == 7
        assert r["n_draws"] == 5000 and not r["failures"]
        assert r["c4_rule_would_pass"] == (not r["c4_rule_failures"])
        assert {c["check"] for c in r["checks_against_c2_c4_limits"]} >= {"|floor_bias|", "annual_gap_coverage"}
    chrono = BACKTEST["hold_outs"]["chronological"]["fits"]
    assert chrono["June 2010 Budget forecast"]["error_cells"] == 0 and chrono["March 2011 EFO"]["error_cells"] == 0
    assert chrono["March 2022 EFO"]["error_target_years"] == 11  # target years 2011 to 2021


def test_sensitivity_runs_and_ranges():
    runs = SENSITIVITY["runs"]
    assert set(runs) == {f"S{i}" for i in range(1, 16)}
    assert {s for s, r in runs.items() if not r["refit"]} == {"S8", "S9", "S13"}
    quoted = {s: r["2039"]["gross_bn"]["p50"] for s, r in runs.items() if r.get("gate_met", True)}
    rng = SENSITIVITY["range_2039_gross_median_bn"]
    assert rng["all_S1_S15"] == pytest.approx([min(quoted.values()), max(quoted.values())])
    prior = [quoted[s] for s in ("S1", "S2", "S3", "S4", "S5", "S6", "S8", "S9") if s in quoted]
    assert rng["prior_sensitivity_S1_S6_S8_S9"] == pytest.approx([min(prior), max(prior)])
    assert SENSITIVITY["headline"]["2039"]["gross_bn"]["p50"] == pytest.approx(FORECAST["by_year"]["2039"]["gross_bn"]["p50"])
    assert runs["S7"]["error_cells"] == int((~B.touches(B.error_cells(), B.HOT_YEARS)).sum())
    assert runs["S11"]["outturn_transitions"] == 0 and runs["S12"]["error_cells"] == 0 and runs["S12"]["outturn_transitions"] == 36
    assert runs["S3"]["posterior"]["nu"]["p50"] == 30 and runs["S4"]["posterior"]["nu"]["p50"] == 3
