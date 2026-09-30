"""The two rules: examples and properties that hold for every input (no PolicyEngine needed)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine, rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, HORIZON, POLICIES, SWITCH_YEAR, TRIPLE_LOCK_FLOOR

rates = st.floats(min_value=-0.03, max_value=0.12, allow_nan=False)
paths = st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON))
STEP = 10 ** -CENTRAL_RATE_DECIMALS


def split(pairs):
    return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])


@pytest.mark.parametrize("cpi, earnings, expected", [
    (0.030, 0.040, 0.040),
    (0.050, 0.020, 0.050),
    (0.010, 0.020, 0.025),
    (-0.010, -0.005, 0.025),
])
def test_triple_lock_rate(cpi, earnings, expected):
    assert rules.rates_matrix("triple_lock", cpi, earnings)[0, 0] == pytest.approx(expected)


def test_unknown_policy_raises():
    with pytest.raises(ValueError):
        rules.rates_matrix("double_lock", 0.02, 0.03)


def test_uprating_uses_previous_year_growth():
    """Uprating in April y reads growth in y-1, as create_triple_lock does."""
    path = rules.uprating_path("triple_lock", {2026: 0.01, 2027: 0.05}, {2026: 0.03, 2027: 0.00}, [2027, 2028])
    assert path == {2027: 0.03, 2028: 0.05}


def test_levels_compound():
    r = {2027: 0.10, 2028: 0.10}
    assert rules.cumulative_index(r, [2027, 2028]) == pytest.approx({2027: 1.1, 2028: 1.21})
    assert rules.level_path(200.0, r, [2027, 2028]) == pytest.approx({2027: 220.0, 2028: 242.0})


def test_floor_binds_only_when_both_below_floor():
    assert rules.floor_binds(0.02, 0.024)
    assert not rules.floor_binds(0.02, 0.025)
    assert not rules.floor_binds(0.03, 0.01)


def test_burnham_keeps_the_floor_but_not_the_ratchet():
    years = [2030, 2031, 2032]
    cpi, earn = np.array([0.01, 0.01, 0.01]), np.array([0.01, 0.06, 0.06])
    tl = rules.rates_matrix("triple_lock", cpi, earn, years)[0]
    b = rules.rates_matrix("burnham_2030", cpi, earn, years)[0]
    assert tl == pytest.approx([0.025, 0.06, 0.06])
    assert b[0] == pytest.approx(0.025)
    assert b[1] == pytest.approx(max(0.025, 1.01 * 1.06 / 1.025 - 1)) and b[1] < tl[1]
    assert b[2] == pytest.approx(0.06)  # back on the earnings path, it follows earnings
    assert rules.rates_matrix("burnham_2030", cpi, np.zeros(3), years)[0] == pytest.approx([0.025] * 3)


def test_switch_year_is_a_parameter():
    cpi, earn = np.array([0.03, 0.01]), np.array([0.01, 0.05])
    late = rules.rates_matrix("burnham_2030", cpi, earn, [2012, 2013], switch_year=2030)[0]
    early = rules.rates_matrix("burnham_2030", cpi, earn, [2012, 2013], switch_year=2012)[0]
    assert late == pytest.approx([0.03, 0.05])  # triple lock throughout
    assert early[1] < 0.05  # from 2012 the plan only restores the earnings path


# ── Properties for all inputs ───────────────────────────────────────────


@settings(max_examples=300, deadline=None)
@given(paths)
def test_burnham_plan_invariants(pairs):
    """Triple lock before the switch; at least max(CPI, 2.5%) after; level never below its earnings path;
    above the triple lock only by rounding (at most 0.1pp in a year); never a cash cut."""
    cpi, earnings = split(pairs)
    tl = rules.rates_matrix("triple_lock", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    assert (tl >= TRIPLE_LOCK_FLOOR - 1e-12).all() and (bp >= 0).all()
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            assert bp[j] == tl[j]
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS)
        assert bp[j] >= floor - 1e-12
        level *= 1 + bp[j]
        assert level >= anchor * (1 - 1e-12)
        assert bp[j] <= tl[j] + STEP + 1e-12


@settings(max_examples=300, deadline=None)
@given(paths)
def test_burnham_plan_is_the_smallest_rate_meeting_both_guarantees(pairs):
    """Each post-switch rate is on the 3 dp grid, meets both guarantees, and 0.1 point less would break one."""
    cpi, earnings = split(pairs)
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS)
        assert abs(bp[j] / STEP - round(bp[j] / STEP)) < 1e-6, "not a 3 dp rate"
        assert bp[j] >= floor - 1e-12 and level * (1 + bp[j]) >= anchor * (1 - 1e-12)
        lower = bp[j] - STEP
        assert lower < floor - 1e-12 or level * (1 + lower) < anchor * (1 - 1e-12), "a smaller rate would do"
        level *= 1 + bp[j]


@settings(max_examples=200, deadline=None)
@given(paths)
def test_burnham_level_never_exceeds_the_triple_lock_unrounded(pairs):
    """Without rounding the plan's level is at most the triple lock's in every year (the saving is never negative)."""
    cpi, earnings = split(pairs)
    tl = np.cumprod(1 + rules.rates_matrix("triple_lock", cpi, earnings, HORIZON)[0])
    bp = np.cumprod(1 + rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON)[0])
    assert (bp <= tl * (1 + 1e-12)).all()


@settings(max_examples=200, deadline=None)
@given(paths)
def test_vectorised_rates_equal_one_path_at_a_time(pairs):
    """Differential: the (n, years) array path gives each draw what the single-path call gives it."""
    cpi, earnings = split(pairs)
    C = np.stack([cpi, cpi * 0.5, earnings])
    E = np.stack([earnings, earnings + 0.01, cpi])
    for p in POLICIES:
        full = rules.rates_matrix(p, C, E, HORIZON, CENTRAL_RATE_DECIMALS)
        for i in range(3):
            assert np.array_equal(full[i], rules.rates_matrix(p, C[i], E[i], HORIZON, CENTRAL_RATE_DECIMALS)[0])


@settings(max_examples=300, deadline=None)
@given(paths, st.sampled_from([CENTRAL_RATE_DECIMALS, None]))
def test_rate_sources_name_the_binding_input(pairs, decimals):
    cpi = {y - 1: p[0] for y, p in zip(HORIZON, pairs)}
    earnings = {y - 1: p[1] for y, p in zip(HORIZON, pairs)}
    r = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals) for p in POLICIES}
    src = engine.rate_sources(cpi, earnings, r, HORIZON, decimals)
    for y in HORIZON:
        c, e = cpi[y - 1], earnings[y - 1]
        chosen = {"earnings": e, "cpi": c, "floor": TRIPLE_LOCK_FLOOR}[src["triple_lock"][y]]
        assert chosen == max(c, e, TRIPLE_LOCK_FLOOR)
        if y < SWITCH_YEAR:
            assert src["burnham_2030"][y] == "triple_lock"
        else:
            floor = max(c, TRIPLE_LOCK_FLOOR)
            floor = round(floor, decimals) if decimals is not None else floor
            assert (src["burnham_2030"][y] == "earnings_path") == (r["burnham_2030"][y] > floor + 1e-12)
