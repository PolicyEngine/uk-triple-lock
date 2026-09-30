"""Trajectory selection and the past-years counterfactual (no PolicyEngine needed)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import rules
from triple_lock import trajectories as T


def test_weighted_cdf_position_gives_ties_one_position():
    x = np.array([1.0, 2.0, 2.0, 3.0])
    assert T.weighted_cdf_position(x, np.ones(4)).tolist() == [0.125, 0.5, 0.5, 0.875]


def test_gap_position_counts_ties_half_and_the_rest_above():
    gap = np.array([0.0, 0.0, 1.0, 2.0, 2.0, 3.0])
    w = np.array([1.0, 1.0, 2.0, 1.0, 1.0, 2.0])
    assert T.gap_position(gap, w, 2.0) == {"percentile": 100 * (4 + 1) / 8, "larger": 100 * 2 / 8}
    assert T.gap_position(gap, w, 0.0) == {"percentile": 100 * 1 / 8, "larger": 100 * 6 / 8}
    assert T.gap_position(gap, w, 5.0) == {"percentile": 100.0, "larger": 0.0}  # above every draw
    assert T.position_fields(gap, w, 1.0) == {"gap_percentile_2039": 37.5, "larger_gap_pct_2039": 50.0,
                                              "draws_compared": 6}


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 10_000), st.integers(2, 120), st.floats(1e-6, 1e6), st.booleans())
def test_gap_position_invariants(seed, n, scale, ties):
    """For every draw: the percentile is its weighted CDF position (two implementations agree); below + tied + above
    is all the weight; the result is bounded, ignores the weights' scale and never falls as the gap rises."""
    rng = np.random.default_rng(seed)
    gap = rng.normal(size=n)
    if ties:
        gap = np.round(gap, 1)  # many exact ties
        gap[: n // 4] = 0.0  # and an exact-zero mass, as identical rates give
    w = rng.uniform(0.1, 2.0, size=n)
    cdf = T.weighted_cdf_position(gap, w)
    previous = -1.0
    for i in np.argsort(gap, kind="stable"):
        pos = T.gap_position(gap, w, gap[i])
        tied = 100 * w[gap == gap[i]].sum() / w.sum()
        assert pos["percentile"] == pytest.approx(100 * cdf[i], abs=1e-9)
        assert pos["percentile"] + tied / 2 + pos["larger"] == pytest.approx(100.0, abs=1e-9)
        assert 0 <= pos["percentile"] <= 100 and 0 <= pos["larger"] <= 100
        assert T.gap_position(gap, w * scale, gap[i])["percentile"] == pytest.approx(pos["percentile"], abs=1e-9)
        assert pos["percentile"] >= previous - 1e-9
        previous = pos["percentile"]


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 10_000), st.floats(1e-3, 1e3))
def test_select_draws_picks_inside_the_band_and_ignores_units(seed, scale):
    rng = np.random.default_rng(seed)
    paths = rng.normal(size=(4000, 3, 2))
    weights = rng.uniform(0.5, 1.5, size=4000)
    weights /= weights.sum()
    gap = paths[:, :, 1].sum(axis=1) + 0.1 * rng.normal(size=4000)
    picks = T.select_draws(paths, weights, gap)
    pos = T.weighted_cdf_position(gap, weights)
    for pick in picks:
        assert abs(pos[pick["draw"]] - pick["quantile"]) <= T.BAND
    rescaled = paths.copy()
    rescaled[:, :, 0] *= scale  # standardised distance: a series' units cannot change the pick
    assert [p["draw"] for p in T.select_draws(rescaled, weights, gap)] == [p["draw"] for p in picks]


def test_select_draws_refuses_an_empty_band():
    with pytest.raises(ValueError):
        T.select_draws(np.zeros((2, 1, 2)), np.array([0.5, 0.5]), np.array([0.0, 1.0]), quantiles=(0.5,), band=0.1)


def test_history_counterfactual_starts_at_its_switch_year():
    cpi, earnings = T.history_inputs()
    for s in (2012, 2019, 2026):
        cf = T.history_counterfactual(s, cpi, earnings)
        for y in T.HISTORY_YEARS:
            if y < s:
                assert cf["burnham_rate"][y] == cf["triple_lock_rate"][y]
                assert cf["level_ratio"][y] == pytest.approx(1.0)
        ratio = np.array(list(cf["level_ratio"].values()))
        assert (ratio <= 1 + 1e-12).all()  # the plan never pays more than the triple lock
        assert np.all(np.diff(ratio) <= 1e-12)  # and the gap never closes over these years


def test_history_counterfactual_reproduces_the_level_ratio_from_the_rates():
    cpi, earnings = T.history_inputs()
    cf = T.history_counterfactual(2012, cpi, earnings)
    c = np.array([cpi[y] for y in T.HISTORY_YEARS])
    e = np.array([earnings[y] for y in T.HISTORY_YEARS])
    tl = rules.rates_matrix("triple_lock", c, e)[0]
    assert list(cf["triple_lock_rate"].values()) == tl.tolist()
    assert cf["level_ratio"][2026] == pytest.approx(np.prod(1 + np.array(list(cf["burnham_rate"].values()))) / np.prod(1 + tl))


def test_history_groups_cover_every_switch_year_once():
    cpi, earnings = T.history_inputs()
    groups = T.history_groups(cpi, earnings)
    years = [y for g in groups for y in g["switch_years"]]
    assert sorted(years) == T.HISTORY_SWITCH_YEARS
    assert groups[0]["switch_years"][0] == 2012  # the benchmarks read groups.0 as the 2012 start


def test_april_2022_earnings_are_suspended_in_the_replay():
    cpi, earnings = T.history_inputs()
    assert earnings[T.SUSPENDED_EARNINGS_YEAR] == cpi[T.SUSPENDED_EARNINGS_YEAR]


def test_ordinal():
    assert [T.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 55, 93, 101, 111)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "55th", "93rd", "101st", "111th"]


def test_the_2012_group_changes_something():
    cpi, earnings = T.history_inputs()
    g = T.history_groups(cpi, earnings)[0]
    assert 2012 in g["switch_years"] and g["changes_anything"] is True
