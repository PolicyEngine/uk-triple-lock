"""Synthetic checks on the output builders (no PolicyEngine run)."""

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
from triple_lock.pipeline import composition_effect, cost_vs_baseline, flat_rate_reform

N = 600


def test_reform_sets_every_year_explicitly():
    reform = flat_rate_reform({"new_state_pension": {2027: 250.0, 2028: 256.0}})
    assert reform == {
        "gov.dwp.state_pension.new_state_pension.amount": {
            "2027-01-01.2027-12-31": 250.0,
            "2028-01-01.2028-12-31": 256.0,
        }
    }


def _totals(sp, balance, hni):
    base = {k: 0.0 for k in [
        "additional_state_pension", "pension_credit", "housing_benefit", "universal_credit",
        "council_tax_reduction", "winter_fuel_payment", "income_tax",
    ]}
    return {**base, "state_pension_flat_rate": sp, "gov_balance": balance, "household_net_income": hni}


def test_cost_signs():
    baseline = {2034: _totals(160.0, -100.0, 2000.0)}
    reform = {2034: _totals(150.0, -94.0, 1994.0)}
    cost = cost_vs_baseline(reform, baseline, [2034])
    assert cost["gross"]["2034"] == -10.0
    assert cost["net"]["2034"] == -6.0
    assert cost["change_in_household_net_income"]["2034"] == -6.0


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


def test_no_losers_raises():
    gain = mdf.MicroSeries(np.array([5.0, 0.0]), weights=np.array([1.0, 1.0]))
    with pytest.raises(ValueError):
        households_affected(gain)


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


def test_composition_effect():
    years = [2027, 2028]
    uprating = {
        "triple_lock": {2027: 0.10, 2028: 0.10},
        "double_lock": {2027: 0.10, 2028: 0.10},
        "earnings_link": {2027: 0.10, 2028: 0.0},
        "cpi_link": {2027: 0.0, 2028: 0.0},
    }
    # Spend per index point: 100 in 2027 (110 / 1.1), 110 in 2028 (133.1 / 1.21).
    totals = {2027: {"state_pension_flat_rate": 110.0}, 2028: {"state_pension_flat_rate": 133.1}}
    costs = {alt: {"gross": {}} for alt in ["double_lock", "earnings_link", "cpi_link"]}
    out = composition_effect(totals, uprating, costs, years)
    assert out["difference_pct_by_year"] == {"2027": 0.0, "2028": 10.0}
    assert out["difference_pct"] == 10.0
    assert out["gross_fixed_composition"]["cpi_link"]["2028"] == pytest.approx(-100 * (1.21 - 1.0))
    assert out["gross_fixed_composition"]["double_lock"]["2028"] == 0.0
