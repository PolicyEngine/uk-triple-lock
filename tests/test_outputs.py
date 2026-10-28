"""Synthetic checks on the output builders (no PolicyEngine run)."""

from hypothesis import given, settings, strategies as st
import microdf as mdf
import numpy as np
import pytest

from triple_lock.breakdowns import (
    BREAKDOWNS,
    age_band,
    all_breakdowns,
    decile_groups,
    household_type,
    households_affected,
    largest_household_contribution,
    map_labels,
    TENURE_GROUPS,
)
from triple_lock.engine import flat_rate_reform

N = 600


def test_reform_sets_every_year_explicitly():
    reform = flat_rate_reform({"new_state_pension": {2027: 250.0, 2028: 256.0}})
    assert reform == {
        "gov.dwp.state_pension.new_state_pension.amount": {
            "2027-01-01.2027-12-31": 250.0,
            "2028-01-01.2028-12-31": 256.0,
        }
    }


@pytest.fixture
def synthetic():
    rng = np.random.default_rng(3)
    weights = rng.uniform(100, 2_000, N)
    base = mdf.MicroSeries(rng.uniform(5_000, 90_000, N), weights=weights)
    reform = mdf.MicroSeries(base.to_numpy() - rng.uniform(0, 800, N), weights=weights)
    decile, quintile = decile_groups(np.r_[-1, rng.integers(1, 11, N - 1)])
    groups = {
        "decile": decile,
        "quintile": quintile,
        "region": rng.choice(["LONDON", "WALES", "NORTH_EAST", "NORTH_WEST", "YORKSHIRE",
                              "EAST_MIDLANDS", "WEST_MIDLANDS", "EAST_OF_ENGLAND", "SOUTH_EAST",
                              "SOUTH_WEST", "SCOTLAND", "NORTHERN_IRELAND"], N),
        "tenure": map_labels(rng.choice(list(TENURE_GROUPS), N), TENURE_GROUPS, "tenure"),
        "hh_type": household_type(
            np.r_[1, 2, 2, 1, 2, rng.integers(1, 3, N - 5)],
            np.r_[1, 2, 1, 0, 0, rng.integers(0, 2, N - 5)],
            np.r_[0, 0, 0, 1, 0, rng.integers(0, 2, N - 5)],
        ),
        "age_band": age_band(np.r_[30, 70, 80, rng.uniform(18, 80, N - 3)]),
    }
    return reform - base, base, groups


def test_every_breakdown_sums_to_the_total_change(synthetic):
    change, base, groups = synthetic
    out = all_breakdowns(change, base, groups)
    total_bn = float(change.sum()) / 1e9
    for key in BREAKDOWNS:
        rows = out[key]
        assert sum(r["total_bn"] for r in rows) == pytest.approx(total_bn, abs=0.001 * len(rows))
        assert sum(r["share_of_households_pct"] for r in rows) == pytest.approx(100, abs=0.05)
        assert {"label", "mean_change_gbp", "pct_income_change", "total_bn", "share_of_households_pct"} <= set(rows[0])


def test_weighted_totals_match_microdf(synthetic):
    change, base, groups = synthetic
    frame = mdf.MicroDataFrame({"change": change.to_numpy(), "g": groups["region"]}, weights=base.weights.to_numpy())
    rows = {r["region"]: r for r in all_breakdowns(change, base, groups)["by_region"]}
    for region, total in frame.groupby("g").change.sum().items():
        assert rows[region]["total_bn"] == pytest.approx(total / 1e9, abs=5e-4)
    affected = households_affected(change)
    assert affected["losing_pct"] == pytest.approx(100 * float((change < -1).mean()), abs=0.01)


def test_quintile_means_are_weighted_averages_of_decile_means(synthetic):
    change, base, groups = synthetic
    out = all_breakdowns(change, base, groups)
    deciles, quintiles = out["by_decile"], out["by_quintile"]
    assert [q["quintile"] for q in quintiles] == [1, 2, 3, 4, 5]
    for q in quintiles:
        lo, hi = deciles[2 * q["quintile"] - 2], deciles[2 * q["quintile"] - 1]
        w_lo, w_hi = lo["share_of_households_pct"], hi["share_of_households_pct"]
        expected = (lo["mean_change_gbp"] * w_lo + hi["mean_change_gbp"] * w_hi) / (w_lo + w_hi)
        assert q["mean_change_gbp"] == pytest.approx(expected, abs=0.05)


def test_negative_income_decile_goes_to_decile_one_and_bad_values_raise():
    decile, quintile = decile_groups(np.array([-1, 1, 10]))
    assert decile.tolist() == [1, 1, 10] and quintile.tolist() == [1, 1, 5]
    with pytest.raises(ValueError):
        decile_groups(np.array([0, 11]))


def test_unmapped_labels_and_empty_groups_raise(synthetic):
    change, base, groups = synthetic
    with pytest.raises(KeyError):
        map_labels(np.array(["OWNED_OUTRIGHT", "SQUAT"]), TENURE_GROUPS, "tenure")
    groups = {**groups, "tenure": np.full(N, "owner_outright")}
    with pytest.raises(KeyError, match="no households"):
        all_breakdowns(change, base, groups)
    with pytest.raises(ValueError):
        household_type(np.array([0]), np.array([0]), np.array([1]))


def test_no_losers_reports_zero():
    """A rule identical to the triple lock that year has no losers; gainers are still counted."""
    gain = mdf.MicroSeries(np.array([5.0, 0.0]), weights=np.array([1.0, 1.0]))
    assert households_affected(gain) == {"losing_pct": 0.0, "mean_loss_gbp": 0.0,
                                         "gaining_pct": 50.0, "mean_gain_gbp": 5.0}


def test_losers_and_gainers_are_counted_apart_at_one_pound():
    """£1 or less either way is neither; the means are each group's own weighted mean, both positive."""
    change = mdf.MicroSeries(np.array([-30.0, -10.0, -1.0, 0.5, 1.0, 1.02, 20.0]),
                             weights=np.array([1.0, 3.0, 5.0, 5.0, 5.0, 1.0, 1.0]))
    assert households_affected(change) == {"losing_pct": 19.05, "mean_loss_gbp": 15.0,
                                           "gaining_pct": 9.52, "mean_gain_gbp": 10.51}
    nobody = mdf.MicroSeries(np.array([-1.0, 0.0, 1.0]), weights=np.array([1.0, 1.0, 1.0]))
    assert households_affected(nobody) == {"losing_pct": 0.0, "mean_loss_gbp": 0.0,
                                           "gaining_pct": 0.0, "mean_gain_gbp": 0.0}


def test_zero_weight_households_are_in_no_group():
    """A group whose households all have zero weight is empty, not a division by zero."""
    gainer = mdf.MicroSeries(np.array([-10.0, 5.0]), weights=np.array([1.0, 0.0]))
    assert households_affected(gainer) == {"losing_pct": 100.0, "mean_loss_gbp": 10.0,
                                           "gaining_pct": 0.0, "mean_gain_gbp": 0.0}
    loser = mdf.MicroSeries(np.array([-10.0, 5.0]), weights=np.array([0.0, 1.0]))
    assert households_affected(loser) == {"losing_pct": 0.0, "mean_loss_gbp": 0.0,
                                          "gaining_pct": 100.0, "mean_gain_gbp": 5.0}


def _affected_reference(values, weights):
    """households_affected's definition in plain numpy, unrounded: the differential check's second path."""
    out = {}
    for mask, share, mean, sign in ((values < -1, "losing_pct", "mean_loss_gbp", -1),
                                    (values > 1, "gaining_pct", "mean_gain_gbp", 1)):
        weighted = weights[mask].sum() > 0
        out[share] = 100 * weights[mask].sum() / weights.sum() if weighted else 0.0
        out[mean] = sign * (weights[mask] * values[mask]).sum() / weights[mask].sum() if weighted else 0.0
    return out


@st.composite
def weighted_changes(draw):
    n = draw(st.integers(min_value=1, max_value=60))
    values = draw(st.lists(st.one_of(st.floats(min_value=-5_000, max_value=5_000, allow_nan=False),
                                     st.sampled_from([-1.0, 1.0, 0.0])), min_size=n, max_size=n))
    # Zero weights are allowed (Microcosm keeps zero-weight records); the total stays positive.
    weights = draw(st.lists(st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=10_000)), min_size=n, max_size=n)
                   .filter(lambda w: sum(w) > 0))
    return np.array(values), np.array(weights)


@settings(max_examples=400, deadline=None)
@given(weighted_changes())
def test_households_affected_properties(case):
    """For every input, zero weights included: the numpy reference agrees to rounding; the shares are disjoint and
    within [0, 100]; each group's mean is 0 exactly when the group has no weight and otherwise at least the £1
    threshold."""
    values, weights = case
    got = households_affected(mdf.MicroSeries(values, weights=weights))
    assert set(got) == {"losing_pct", "mean_loss_gbp", "gaining_pct", "mean_gain_gbp"}
    for key, expected in _affected_reference(values, weights).items():
        assert got[key] == pytest.approx(expected, abs=0.0051), key
    assert 0 <= got["losing_pct"] <= 100 and 0 <= got["gaining_pct"] <= 100
    assert got["losing_pct"] + got["gaining_pct"] <= 100.01
    for mask, mean in ((values < -1, "mean_loss_gbp"), (values > 1, "mean_gain_gbp")):
        assert (got[mean] == 0.0) if weights[mask].sum() == 0 else (got[mean] >= 1.0)


@settings(max_examples=300, deadline=None)
@given(weighted_changes(), st.floats(min_value=0.5, max_value=1_000))
def test_households_affected_symmetries(case, scale):
    """Negating every change swaps losers and gainers exactly; scaling every weight changes nothing beyond
    rounding."""
    values, weights = case
    got = households_affected(mdf.MicroSeries(values, weights=weights))
    flipped = households_affected(mdf.MicroSeries(-values, weights=weights))
    assert flipped == {"losing_pct": got["gaining_pct"], "mean_loss_gbp": got["mean_gain_gbp"],
                       "gaining_pct": got["losing_pct"], "mean_gain_gbp": got["mean_loss_gbp"]}
    scaled = households_affected(mdf.MicroSeries(values, weights=weights * scale))
    for key, value in got.items():
        assert scaled[key] == pytest.approx(value, abs=0.0101), key


def test_household_types():
    types = household_type(np.array([1, 2, 2, 2, 1]), np.array([1, 2, 1, 0, 0]), np.array([0, 0, 0, 2, 0]))
    assert types.tolist() == [
        "single_pensioner", "pensioner_couple", "mixed_age",
        "working_age_with_children", "working_age_no_children",
    ]


def test_largest_household_contribution():
    change = mdf.MicroSeries(np.array([-10.0, 6_900.0]), weights=np.array([10.0, 40_000.0]))
    out = largest_household_contribution(change)
    assert out["household_weight"] == 40_000.0
    assert out["income_change_gbp"] == 6_900.0
