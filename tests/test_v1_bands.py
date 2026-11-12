"""V1, the conditional volatility bands (docs/METHOD.md, "Conditional volatility bands (V1)"; data/v1/)."""

import csv
import json
import subprocess
import sys

import numpy as np
import pytest

from triple_lock import v1_bands as V
from triple_lock.config import ACTUALS_CSV, HORIZON, REPO

BANDS = json.loads((REPO / "data" / "v1" / "bands.json").read_text())
IDENTITY = json.loads((REPO / "data" / "v1" / "identity_check.json").read_text())
METHOD = (REPO / "docs" / "METHOD.md").read_text()
RESULTS = json.loads((REPO / "data" / "results.json").read_text())


def test_spec_follows_the_frozen_sections_and_is_named():
    head = METHOD.index("## Conditional volatility bands (V1)")
    assert head > METHOD.index("<!-- C4 frozen rule ends -->")
    assert BANDS["spec_commit"] == V.SPEC_COMMIT
    assert "not a calibrated forecast" in BANDS["label"] and "not output of the C2 or C4 models" in BANDS["label"]


def test_module_uses_neither_failed_model():
    src = (REPO / "src" / "triple_lock" / "v1_bands.py").read_text()
    for name in ("ts_obr_errors", "ts_monthly", "ts_uncertainty", "expected_value", "ts_backtest"):
        assert f"import {name}" not in src and f".{name} import" not in src


def test_statutory_series_match_the_committed_inputs():
    series, source = V.statutory_history()
    assert min(series) == 1997 and max(series) == 2025
    assert all(source[y].startswith("KAC3") for y in range(2001, 2026))
    assert all(source[y].startswith("national-accounts") for y in range(1997, 2001))
    with ACTUALS_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            y = int(row["determination_year"])
            if y in series:
                assert series[y][0] == pytest.approx(float(row["cpi_september_12m"]), abs=1e-12)
                assert series[y][1] == pytest.approx(float(row["awe_total_pay_may_jul_3m_yoy"]), abs=1e-12)
    assert series[2021][1] == pytest.approx(0.084)


def test_lag_pairs_and_exclusions():
    series, _ = V.statutory_history()
    a = V.estimate(series)
    b = V.estimate(series, V.EXCLUDED)
    assert len(a["pairs"]) == 28 and len(b["pairs"]) == 24
    assert not any(y in V.EXCLUDED for p in b["pairs"] for y in p)
    assert b["years"] == [y for y in range(1997, 2026) if y not in V.EXCLUDED]
    assert BANDS["settings"]["a"]["lag_pairs"] == 28 and BANDS["settings"]["b"]["lag_pairs"] == 24


def test_estimator_recovers_a_known_ar1():
    rng = np.random.default_rng(1)
    phi, L = np.array([0.6, -0.3]), np.array([[0.01, 0.0], [0.004, 0.008]])
    x = np.zeros((20_001, 2))
    for t in range(1, len(x)):
        x[t] = phi * x[t - 1] + L @ rng.standard_normal(2)
    est = V.estimate({1000 + t: tuple(x[t] + [0.02, 0.04]) for t in range(len(x))})
    assert est["phi"] == pytest.approx(phi, abs=0.02)
    assert est["sigma"] == pytest.approx(L @ L.T, rel=0.05, abs=1e-6)
    assert est["anchor"] == pytest.approx([0.02, 0.04], abs=1e-3)


def test_nonstationary_estimate_stops():
    with pytest.raises(ValueError, match="V1 stops"):
        V.estimate({2000 + t: (0.01 * 1.5**t, 0.01 * t) for t in range(10)})


def test_draws_are_seeded_antithetic_and_centred():
    z = V.normals()
    assert z.shape == (2 * V.N_HALF, len(HORIZON) - 1, 2)
    assert np.array_equal(z, V.normals())
    assert np.array_equal(z[: V.N_HALF], -z[V.N_HALF:])  # antithetic pairs: every mean is zero
    series, _ = V.statutory_history()
    st = V.paths(V.estimate(series), z)
    c = V.centre()
    assert np.array_equal(st[:, 0], np.broadcast_to(c[0], st[:, 0].shape))  # 2026 fixed at the published inputs
    assert np.abs(st.mean(axis=0) - c).max() < 1e-14  # no drift at any horizon
    assert np.allclose(st[: V.N_HALF] - c, -(st[V.N_HALF:] - c))  # symmetric about the centre


def test_zero_volatility_gives_the_central_path():
    est = {"phi": np.array([0.5, 0.5]), "sigma": np.eye(2) * 1e-30}
    st = V.paths(est, V.normals(n_half=10))
    ra = V.rule_arithmetic(st[:, :, 0], st[:, :, 1])
    c = V.centre()
    ca = V.rule_arithmetic(c[None, :, 0], c[None, :, 1])
    assert np.allclose(ra["G"], ca["G"])
    assert BANDS["central_rule_arithmetic"]["2039"]["gross_bn"] == pytest.approx(
        RESULTS["scenario_envelope"]["central"]["run"]["saving_bn"]["2039"]["gross"], abs=1e-4)


def test_rule_arithmetic_bounds():
    series, _ = V.statutory_history()
    st = V.paths(V.estimate(series), V.normals(n_half=500))
    ra = V.rule_arithmetic(st[:, :, 0], st[:, :, 1])
    assert (ra["G"] >= -1e-15).all() and (ra["share"] < 1).all()
    assert (np.diff(ra["G"], axis=1) >= -1e-12).all()  # the gap never closes (both rates at least 2.5%)
    assert (ra["G"][ra["same"]] == 0).all()


def test_identity_reproduces_every_stored_run():
    for pid, r in IDENTITY["single_path_runs"].items():
        assert r["max_abs_weekly_error_gbp"] == 0, pid
        assert r["max_abs_gross_error_bn"] < 1e-4, pid
    for sid, r in IDENTITY["earnings_scenarios_stratified_means"].items():
        assert r["max_abs_stratified_mean_error_bn"] < 1e-4, sid
    sys.path.insert(0, str(REPO / "scripts"))
    import v1_identity_check as X
    assert X.single_paths(RESULTS) == IDENTITY["single_path_runs"]


def test_net_ratio_matches_the_emulator_check():
    rho, n, top = V.net_ratio(RESULTS)
    assert n == 40 and BANDS["net_ratio"]["rho"] == pytest.approx(rho, abs=1e-12)
    slopes = json.loads(V.EMULATOR_CHECK.read_text())["net_over_gross_leave_one_path_out"]["slope_by_left_out_path"]
    assert min(slopes.values()) - 1e-3 < rho < max(slopes.values()) + 1e-3
    assert BANDS["net_ratio"]["max_stored_gross_bn"] == pytest.approx(top)


def test_summaries_are_ordered_and_consistent():
    for k, s in BANDS["settings"].items():
        for y, row in s["by_year"].items():
            for measure, d in row.items():
                q = [d[f"p{p}"] for p in V.QUANTILES]
                assert q == sorted(q), (k, y, measure)
            assert row["net_bn"]["p50"] == pytest.approx(BANDS["net_ratio"]["rho"] * row["gross_bn"]["p50"])
        h = s["gross_2039_histogram"]
        assert sum(h["counts"]) == BANDS["n_paths"] and len(h["edges_bn"]) == len(h["counts"]) + 1
        assert 0 <= s["pay_same_share"]["2039"] <= s["pay_same_share"]["2034"] <= 1
    # Setting (b) drops the 2021-23 years, so its innovations are smaller.
    a, b = BANDS["settings"]["a"], BANDS["settings"]["b"]
    assert all(b["innovation_sd"][v] < a["innovation_sd"][v] for v in V.VARIABLES)


def test_committed_bands_regenerate():
    assert json.loads(json.dumps(V.build(), sort_keys=True)) == BANDS


def test_cli_writes_one_file(tmp_path):
    out = subprocess.run([sys.executable, "-m", "triple_lock.v1_bands", "--output", str(tmp_path)], capture_output=True,
                         text=True, cwd=REPO, env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stderr
    assert [p.name for p in tmp_path.iterdir()] == ["bands.json"]
