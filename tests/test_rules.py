"""Synthetic checks on the uprating rules (no PolicyEngine needed)."""

import numpy as np
import pytest

from triple_lock.rules import (
    cumulative_index,
    floor_binds,
    zero_floor_binds,
    level_path,
    rule_rate,
    uprating_path,
)


@pytest.mark.parametrize(
    "cpi, earnings, expected",
    [
        # (triple_lock, double_lock, earnings_link, cpi_link)
        (0.030, 0.040, (0.040, 0.040, 0.040, 0.030)),
        (0.050, 0.020, (0.050, 0.050, 0.020, 0.050)),
        (0.010, 0.020, (0.025, 0.020, 0.020, 0.010)),
        # No cash cuts: negative indices give 0%.
        (-0.010, -0.005, (0.025, 0.0, 0.0, 0.0)),
        (-0.010, 0.030, (0.030, 0.030, 0.030, 0.0)),
    ],
)
def test_rule_rates(cpi, earnings, expected):
    policies = ["triple_lock", "double_lock", "earnings_link", "cpi_link"]
    got = tuple(rule_rate(p, cpi, earnings) for p in policies)
    assert got == pytest.approx(expected)


def test_triple_lock_is_never_below_any_alternative():
    rng = np.random.default_rng(0)
    cpi, earnings = rng.normal(0.02, 0.02, (2, 1000))
    tl = rule_rate("triple_lock", cpi, earnings)
    for p in ["double_lock", "earnings_link", "cpi_link"]:
        assert (tl >= rule_rate(p, cpi, earnings)).all()


def test_unknown_policy_raises():
    with pytest.raises(ValueError):
        rule_rate("quadruple_lock", 0.02, 0.03)


def test_uprating_uses_previous_year_growth():
    """Uprating in year y reads growth in y-1, as create_triple_lock does."""
    cpi = {2026: 0.01, 2027: 0.05}
    earnings = {2026: 0.03, 2027: 0.00}
    path = uprating_path("double_lock", cpi, earnings, [2027, 2028])
    assert path == {2027: 0.03, 2028: 0.05}


def test_rounding_matches_model_convention():
    path = uprating_path("earnings_link", {2031: 0.02}, {2031: 0.0332}, [2032], decimals=3)
    assert path[2032] == 0.033


def test_levels_compound():
    rates = {2027: 0.10, 2028: 0.10}
    assert cumulative_index(rates, [2027, 2028]) == pytest.approx({2027: 1.1, 2028: 1.21})
    assert level_path(200.0, rates, [2027, 2028]) == pytest.approx({2027: 220.0, 2028: 242.0})


def test_floor_binds_only_when_both_below_floor():
    assert floor_binds(0.02, 0.024)
    assert not floor_binds(0.02, 0.025)
    assert not floor_binds(0.03, 0.01)


def test_zero_floor_holds_on_arrays():
    rng = np.random.default_rng(5)
    cpi, earnings = rng.normal(0.0, 0.03, (2, 2000))
    for p in ["triple_lock", "double_lock", "earnings_link", "cpi_link"]:
        assert (rule_rate(p, cpi, earnings) >= 0).all()
    assert zero_floor_binds("cpi_link", -0.01, 0.02)
    assert not zero_floor_binds("double_lock", -0.01, 0.02)
