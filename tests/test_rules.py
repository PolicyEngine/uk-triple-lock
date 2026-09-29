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


def test_alternatives_follow_the_triple_lock_until_2030():
    from triple_lock.rules import uprating_path
    years = list(range(2027, 2035))
    cpi = {y - 1: 0.02 for y in years}
    earn = {y - 1: 0.04 for y in years}
    for policy in ["cpi_link", "prices_or_floor", "burnham_2030", "earnings_link"]:
        path = uprating_path(policy, cpi, earn, years)
        assert all(path[y] == pytest.approx(0.04) for y in years if y < 2030)
    assert all(uprating_path("cpi_link", cpi, earn, years)[y] == pytest.approx(0.02) for y in years if y >= 2030)


def test_burnham_rule_keeps_the_floor_but_not_the_ratchet():
    from triple_lock.rules import rates_matrix
    years = [2030, 2031, 2032]
    # earnings 1% (floor 2.5% binds), then 6%: the triple lock pays 2.5% then 6%;
    # Burnham pays 2.5% then only what restores the earnings path.
    cpi = np.array([0.01, 0.01, 0.01])
    earn = np.array([0.01, 0.06, 0.06])
    tl = rates_matrix("triple_lock", cpi, earn, years)[0]
    b = rates_matrix("burnham_2030", cpi, earn, years)[0]
    assert tl == pytest.approx([0.025, 0.06, 0.06])
    assert b[0] == pytest.approx(0.025)
    level = 1.025
    anchor = 1.01 * 1.06
    assert b[1] == pytest.approx(max(0.025, anchor / level - 1))
    assert b[1] < tl[1]
    # Once back on the earnings path it follows earnings.
    assert b[2] == pytest.approx(0.06)
    # With earnings below 2.5% throughout it is the prices-or-2.5% rule.
    low = np.array([0.0, 0.0, 0.0])
    assert rates_matrix("burnham_2030", cpi, low, years)[0] == pytest.approx(
        rates_matrix("prices_or_floor", cpi, low, years)[0]
    )
