"""Time-series methods: calibration, scores and the monthly model (no PolicyEngine needed)."""

import numpy as np
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from triple_lock import ts_monthly
from triple_lock.ts_backtest import switches
from triple_lock.ts_methods import (
    MIN_MARGINAL_DF,
    TiltError,
    band_depth_prerank,
    crps,
    fit_t_marginal,
    interval_hit,
    tilt,
    tilt_moments,
    variogram_score,
)


# ── Entropy tilting ─────────────────────────────────────────────────────


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000), st.floats(-0.5, 0.5), st.floats(-0.5, 0.5))
def test_tilt_matches_target_means(seed, shift_c, shift_e):
    rng = np.random.default_rng(seed)
    paths = rng.normal(0.02, 0.015, size=(3000, 3, 2))
    target = paths.mean(axis=0) + np.array([shift_c, shift_e]) * paths.std(axis=0)
    w, info = tilt(paths, target)
    assert np.all(w >= 0) and abs(w.sum() - 1) < 1e-9
    assert np.allclose(np.tensordot(w, paths, axes=1), target, atol=1e-8)
    assert 1 <= info["ess"] <= len(paths) + 1e-6


@settings(max_examples=40, deadline=None)
@example(seed=283, mean_shift=0.0, var_ratio=0.7, unit=0.6875)
@example(seed=108, mean_shift=0.0, var_ratio=0.7, unit=0.21875)
@given(st.integers(0, 10_000), st.floats(-0.4, 0.4), st.floats(0.7, 1.3), st.floats(1e-3, 1e3))
def test_moment_tilt_hits_every_target_whatever_the_scale(seed, mean_shift, var_ratio, unit):
    """Non-negative weights summing to one; each moment's weighted mean equals its target; the solution does not
    depend on the units a moment is expressed in."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(5000, 4))
    moments = np.column_stack([x.mean(axis=1), x.var(axis=1, ddof=1)])
    target = np.array([mean_shift * moments[:, 0].std(), var_ratio * moments[:, 1].mean()])
    G = moments - target[None]
    w, info = tilt_moments(G, scale=np.array([1e-3, 1e-3]), tol=1e-6)
    assert np.all(w >= 0) and abs(w.sum() - 1) < 1e-12
    assert np.allclose(w @ moments, target, atol=1e-8)
    w2, _ = tilt_moments(G * np.array([1.0, unit]), scale=np.array([1e-3, 1e-3 * unit]), tol=1e-6)
    assert np.allclose(w, w2, atol=1e-9)


def test_tilt_is_identity_at_the_sample_mean():
    paths = np.random.default_rng(0).normal(size=(500, 2, 2))
    w, info = tilt(paths, paths.mean(axis=0))
    assert np.allclose(w, 1 / 500) and info["ess"] == pytest.approx(500)


def test_tilt_raises_when_the_target_is_out_of_reach():
    paths = np.random.default_rng(1).uniform(0, 1, size=(400, 2, 2))
    with pytest.raises(TiltError):
        tilt(paths, np.full((2, 2), 2.0))


# ── Scores ──────────────────────────────────────────────────────────────


def test_crps_matches_the_normal_closed_form():
    x = np.random.default_rng(1).standard_normal(200_000)
    assert crps(x, 0.0) == pytest.approx(2 / np.sqrt(2 * np.pi) - 1 / np.sqrt(np.pi), abs=0.003)


def test_variogram_score_prefers_the_true_dependence():
    rng = np.random.default_rng(2)
    L = np.linalg.cholesky(np.array([[1, 0.9], [0.9, 1]]))
    right, wrong = [], []
    for _ in range(200):
        y = L @ rng.standard_normal(2)
        right.append(variogram_score(rng.standard_normal((2000, 2)) @ L.T, y))
        wrong.append(variogram_score(rng.standard_normal((2000, 2)), y))
    assert np.mean(right) < 0.5 * np.mean(wrong)


def test_band_depth_pit_is_uniform_for_a_calibrated_forecast():
    rng = np.random.default_rng(3)
    pits = [band_depth_prerank(rng.standard_normal((400, 4)), rng.standard_normal(4)) for _ in range(600)]
    assert abs(np.mean(pits) - 0.5) < 0.05
    assert abs(np.mean(np.array(pits) < 0.2) - 0.2) < 0.05


def test_band_depth_pit_is_undefined_for_a_point_forecast():
    with pytest.raises(ValueError):
        band_depth_prerank(np.zeros((1, 4)), np.ones(4))


@settings(max_examples=100, deadline=None)
@given(st.integers(0, 10_000), st.floats(0.01, 1000))
def test_interval_hit_ignores_the_scale_of_the_weights(seed, scale):
    rng = np.random.default_rng(seed)
    x, w, y = rng.normal(size=50), rng.uniform(0.1, 1, size=50), rng.normal()
    assert interval_hit(x, y, w=w * scale) == interval_hit(x, y, w=w / w.sum())


def test_switches_do_not_count_a_tie_as_a_reversal():
    tie = np.array([[[0.02, 0.03], [0.02, 0.02], [0.02, 0.04]]])
    flip = np.array([[[0.02, 0.03], [0.03, 0.02], [0.02, 0.04]]])
    assert switches(tie)[0] == 0 and switches(flip)[0] == 2


# ── The monthly model ───────────────────────────────────────────────────


def test_bic_compares_every_lag_order_on_the_same_rows():
    months, cpi, awe, _ = ts_monthly.levels()
    model = ts_monthly.fit(months, cpi, awe)
    crit = model["criterion"]
    assert len({c["n"] for c in crit}) == 1
    assert model["p"] == min(crit, key=lambda c: c["bic"])["p"]


def test_t_marginals_are_bounded():
    heavy = np.random.default_rng(4).standard_t(1.5, size=3000)
    assert fit_t_marginal(heavy)[0] == pytest.approx(MIN_MARGINAL_DF)
    light = np.random.default_rng(5).standard_t(12, size=20000)
    assert fit_t_marginal(light)[0] > MIN_MARGINAL_DF


def test_paths_are_reproducible():
    a, _ = ts_monthly.paths([2026, 2027, 2028], 200, 7)
    b, _ = ts_monthly.paths([2026, 2027, 2028], 200, 7)
    assert all(np.array_equal(a[k], b[k]) for k in a)


@settings(max_examples=12, deadline=None)
@given(st.integers(0, 1000), st.floats(0.0, 0.05), st.floats(0.0, 0.05))
def test_drift_shift_hits_the_calendar_means_and_keeps_every_draws_deviation(seed, cpi_target, earn_target):
    """After the shift the mean calendar growth equals the target in every year, and the observed May-July 2026
    earnings are the same on every draw."""
    years = [2026, 2027, 2028, 2029]
    target = {y: (cpi_target, earn_target) for y in years[1:]}
    raw, _ = ts_monthly.paths(years, 300, seed)
    shifted, info = ts_monthly.paths(years, 300, seed, calendar_target=target)
    for j, y in enumerate(years[1:], start=1):
        assert shifted["calendar_cpi"][:, j].mean() == pytest.approx(cpi_target, abs=1e-11)
        assert shifted["calendar_earnings"][:, j].mean() == pytest.approx(earn_target, abs=1e-11)
    # September 2026 CPI is simulated from the observed August 2026; the shift starts from September 2026,
    # and May-July 2026 earnings are observed, so they are the same on every draw in both sets.
    assert np.allclose(shifted["statutory_earnings"][:, 0], raw["statutory_earnings"][:, 0])
    assert np.ptp(raw["statutory_earnings"][:, 0]) == 0
    assert info["drift"]["first_month"] == [2026, 9]


def test_drift_shift_moves_every_draw_by_the_same_amount():
    years = [2026, 2027, 2028]
    months, cpi, awe, extra = ts_monthly.levels()
    model = ts_monthly.fit(months, cpi, awe)
    future, sc, sa, _ = ts_monthly.simulate(model, months, cpi, awe, (2028, 12), 50, 3, "boot", extra)
    all_months = months + future
    C = np.concatenate([np.repeat(cpi[None], 50, 0), sc], axis=1)
    A = np.concatenate([np.repeat(awe[None], 50, 0), sa], axis=1)
    C2, A2, drift_months, drift = ts_monthly.shift_to_calendar_means(
        all_months, C, A, years[1:], np.array([[0.02, 0.03], [0.02, 0.035]]), future[len(extra)])
    moved = np.log(C2) - np.log(C)
    assert np.allclose(moved, moved[:1], atol=1e-12)  # the same shift on every draw
    assert np.allclose(moved[:, : len(months) + len(extra)], 0)  # observed CPI months untouched
    moved_a = np.log(A2) - np.log(A)
    assert np.allclose(moved_a, moved_a[:1], atol=1e-12)  # earnings too: the same shift on every draw
    assert np.allclose(moved_a[:, : len(months)], 0)  # observed AWE months untouched
    # So each draw's deviation from the cross-draw mean log level is unchanged, month by month.
    dev = lambda X: np.log(X) - np.log(X).mean(axis=0, keepdims=True)
    assert np.allclose(dev(C2), dev(C), atol=1e-12) and np.allclose(dev(A2), dev(A), atol=1e-12)
