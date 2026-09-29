"""Synthetic checks on the VAR cross-check (no PolicyEngine, no ONS files)."""

import numpy as np
import pytest

from triple_lock.uncertainty import summarise_draws
from triple_lock.var_check import fit_var, select_lag, simulate, var_draws

GROWTH_YEARS = list(range(2026, 2034))
YEARS = [g + 1 for g in GROWTH_YEARS]


def synthetic_var(n=400, seed=0):
    """Known VAR(1): CPI shocks feed into next year's earnings growth."""
    rng = np.random.default_rng(seed)
    a = np.array([[0.5, 0.0], [0.4, 0.3]])
    c = np.array([0.01, 0.015])
    cov = np.array([[1e-4, 0.3e-4], [0.3e-4, 1e-4]])
    chol = np.linalg.cholesky(cov)
    x = np.zeros((n, 2))
    x[0] = [0.02, 0.03]
    for t in range(1, n):
        x[t] = c + a @ x[t - 1] + chol @ rng.standard_normal(2)
    return x, a, cov


def test_fit_recovers_coefficients():
    data, a, cov = synthetic_var(4000)
    _, lags, sigma, _ = fit_var(data, 1)
    assert lags[0] == pytest.approx(a, abs=0.05)
    assert sigma == pytest.approx(cov, rel=0.15)


def test_aic_prefers_true_lag_order_on_var1_data():
    data, _, _ = synthetic_var(2000)
    p, scores = select_lag(data)
    assert p == 1 and set(scores) == {1, 2}


def test_simulation_carries_cross_lag():
    """A CPI shock this year raises expected earnings growth next year."""
    lags = np.array([[[0.0, 0.0], [0.5, 0.0]]])
    sims = simulate(np.zeros(2), lags, np.eye(2) * 1e-10, [[0.0, 0.0]], 2, fixed_first=[0.1, 0.0], n_draws=10)
    assert sims[:, 1, 1] == pytest.approx(0.5 * sims[:, 0, 0], abs=1e-4)


def test_draws_are_calibrated_to_the_central_path():
    data, _, _ = synthetic_var(300)
    cc = {g: 0.02 for g in GROWTH_YEARS}
    ce = {g: 0.035 for g in GROWTH_YEARS}
    years = list(range(2026 - len(data), 2026))
    cpi, earn, info = var_draws(cc, ce, GROWTH_YEARS, data, years, n_draws=10_000)
    assert cpi.mean(axis=0) == pytest.approx(np.full(8, 0.02))
    assert earn.mean(axis=0) == pytest.approx(np.full(8, 0.035))
    # First growth year fixed, later years uncertain.
    assert cpi[:, 0].std() == pytest.approx(0) and cpi[:, -1].std() > 0.005
    assert info["lag_order"] in (1, 2) and -1 <= info["residual_correlation"] <= 1

    mc = summarise_draws(cpi, earn, YEARS, 200.0, 1.3)
    for q in mc["cost_of_triple_lock_vs"].values():
        assert q["basis"] == "gross" and 0 <= q["p10"] <= q["p50"] <= q["p90"]
    assert set(mc["prob_triple_lock_binds_on_floor"]) == {str(y) for y in YEARS}


def test_history_must_end_the_year_before_simulation():
    data, _, _ = synthetic_var(50)
    with pytest.raises(ValueError, match="history ends"):
        var_draws({g: 0.02 for g in GROWTH_YEARS}, {g: 0.03 for g in GROWTH_YEARS}, GROWTH_YEARS,
                  data, list(range(1970, 2020)), n_draws=10)
