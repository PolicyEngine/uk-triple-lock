"""The paired estimator, privacy boundary and published benchmark definitions."""

import copy
import json

import numpy as np
import pytest
from hypothesis import given, strategies as st

from triple_lock import ageing_validation as AV


def source_results():
    return json.loads(AV.SOURCE_RESULTS.read_text())


def test_paired_indices_match_the_committed_microcosm_runs():
    sample, W, W0, paths = AV.paired_sample(source_results())
    expected = {2948, 5040, 5584, 5649, 8160, 8937, 9699, 9747, 14271, 15420,
                15441, 15584, 16751, 16833, 17294, 17633, 18436, 19383, 19540, 21053,
                21930, 22769, 22780, 24220, 26418, 29401, 29899, 30625, 32795, 35926,
                37304, 38904, 39173, 39769, 40067, 43346, 44184, 46653, 47111, 48963}
    assert set(paths) == expected
    assert sum(map(len, sample.values())) == 40
    assert [len(sample[k]) for k in sorted(sample)] == [5, 3, 2, 2, 2, 2, 2, 3, 4, 15]
    assert sum(W.values()) + W0 == pytest.approx(1)


def test_paired_design_preserves_repeated_draws():
    source = source_results()
    paths = [p for p in source["expected_value"]["paths"] if p.get("times_drawn_sensitivity") and p["stratum"] == 1]
    paths[0]["times_drawn_sensitivity"] = 2
    paths[1]["times_drawn_sensitivity"] = 0
    sample, _, _, by_draw = AV.paired_sample(source)
    assert sample[1].count(paths[0]["draw"]) == 2
    assert paths[1]["draw"] not in by_draw


def test_paired_design_rejects_an_incomplete_or_inconsistent_source():
    source = source_results()
    next(p for p in source["expected_value"]["paths"] if p.get("times_drawn_sensitivity"))["times_drawn_sensitivity"] = 0
    with pytest.raises(ValueError, match="stratum"):
        AV.paired_sample(source)


@given(st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False),
       st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False),
       st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False),
       st.floats(-1e4, 1e4, allow_nan=False, allow_infinity=False))
def test_four_way_interaction_is_reported_for_each_paired_run(frozen, weights, types, both):
    result = AV.four_way(dict(zip(AV.MODES, [frozen, weights, types, both])), lambda r: r)
    assert result["combined_effect"] == pytest.approx(
        result["reweight_effect"] + result["types_effect"] + result["interaction"], abs=1e-8)


def test_four_way_interaction_cannot_be_replaced_with_two_isolated_effects():
    result = AV.four_way(dict(zip(AV.MODES, [1, 2, 3, 7])), lambda r: r)
    assert result["reweight_effect"] == 1
    assert result["types_effect"] == 2
    assert result["combined_effect"] == 6
    assert result["interaction"] == 3


def test_small_coverage_cells_are_suppressed_without_record_values_or_weights():
    values = {"state_pension": np.ones(9), "basic_state_pension": np.ones(9),
              "new_state_pension": np.zeros(9), "additional_state_pension": np.zeros(9)}
    row = AV.coverage_cell(values, np.arange(1, 10), np.ones(9, bool))
    assert row["status"] == "suppressed"
    assert all(value is None for key, value in row.items() if key != "status")
    assert "weight" not in json.dumps(row)


def test_nonzero_components_with_fewer_than_ten_records_are_suppressed():
    values = {"state_pension": np.ones(12), "basic_state_pension": np.r_[np.ones(9), np.zeros(3)],
              "new_state_pension": np.r_[np.zeros(9), np.ones(3)], "additional_state_pension": np.zeros(12)}
    row = AV.coverage_cell(values, np.full(12, 10_000), np.ones(12, bool))
    assert row["status"] == "suppressed"
    assert row["recipients_m"] is None
    assert row["state_pension_bn"] is None
    assert row["basic_state_pension_bn"] is None
    assert row["new_state_pension_bn"] is None
    assert row["basic_recipients_m"] is None
    assert row["additional_state_pension_bn"] is None


def test_suppressed_component_cannot_be_recovered_by_subtraction():
    values = {"state_pension": np.ones(20), "basic_state_pension": np.r_[np.ones(2), np.zeros(18)],
              "new_state_pension": np.r_[np.zeros(2), np.ones(18)], "additional_state_pension": np.zeros(20)}
    row = AV.coverage_cell(values, np.full(20, 10_000), np.ones(20, bool))
    assert row["status"] == "suppressed"
    assert all(value is None for key, value in row.items() if key != "status")


def test_marginal_total_cannot_reveal_one_suppressed_cell():
    rows = {"a": {"status": "suppressed", "records": None, "recipients_m": None},
            "b": {"status": "available", "records": 10, "recipients_m": 0.1},
            "c": {"status": "available", "records": 20, "recipients_m": 0.2}}
    public = AV.complementary_suppression(rows)
    assert public["a"]["recipients_m"] is None and public["b"]["recipients_m"] is None
    assert public["c"]["recipients_m"] == 0.2


def test_coverage_uses_the_models_own_person_outputs():
    values = {"state_pension": np.arange(10, 22), "basic_state_pension": np.zeros(12),
              "new_state_pension": np.arange(10, 22), "additional_state_pension": np.zeros(12)}
    weights = np.arange(100, 112)
    row = AV.coverage_cell(values, weights, np.ones(12, bool))
    assert row["state_pension_bn"] == pytest.approx(float(weights @ values["state_pension"]) / 1e9)
    assert row["new_recipients_m"] == pytest.approx(float(weights.sum()) / 1e6)


def test_dwp_forecasts_use_only_published_gb_totals_without_allocating_overseas_by_type():
    source = AV.dwp_forecasts()
    assert set(source["years"]) == set(range(2024, 2031))
    base = source["years"][2026]
    assert base["GB"]["state_pension_bn"] == pytest.approx(154.17454328758753 - 5.905244519444378)
    assert base["GB"]["recipients_m"] == pytest.approx(13.220 - 1.068)
    assert base["GB_plus_overseas_context"]["basic_state_pension_bn"] == pytest.approx(66.15000309800662)
    assert base["GB_plus_overseas_context"]["new_state_pension_bn"] == pytest.approx(64.81189966321676)
    assert base["GB_plus_overseas_context"]["basic_recipients_m"] == pytest.approx(7.666)
    assert base["GB_plus_overseas_context"]["new_recipients_m"] == pytest.approx(5.527)
    assert set(base["GB"]) == {"state_pension_bn", "recipients_m"}
    assert {"GB_by_type", "by_age", "by_geography", "after_2030"} == set(source["unavailable"])


def test_paired_design_refuses_missing_probability_mass():
    source = copy.deepcopy(source_results())
    source["expected_value"]["strata"][0]["probability"] = 0
    with pytest.raises(ValueError, match="probabilities"):
        AV.paired_sample(source)
