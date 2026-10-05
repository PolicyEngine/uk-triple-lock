"""The paired estimator, privacy boundary and published benchmark definitions."""

import copy
import json
from types import SimpleNamespace

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


def test_zero_recipient_cells_publish_zeros_and_do_not_trigger_suppression():
    values = {name: np.zeros(4) for name in ("state_pension", "basic_state_pension", "new_state_pension", "additional_state_pension")}
    zero = AV.coverage_cell(values, np.ones(4), np.ones(4, bool))
    assert zero["status"] == "available"
    assert all(value == 0 for key, value in zero.items() if key != "status")
    values = {**values, "state_pension": np.ones(10), "basic_state_pension": np.ones(10),
              "new_state_pension": np.zeros(10), "additional_state_pension": np.zeros(10)}
    large = AV.coverage_cell(values, np.ones(10), np.ones(10, bool))
    assert AV.complementary_suppression({"zero": zero, "large": large})["large"] == large


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


def test_three_and_four_record_cells_cannot_be_recovered_as_a_seven_record_sum():
    def cell(n):
        values = {"state_pension": np.ones(n), "basic_state_pension": np.ones(n),
                  "new_state_pension": np.zeros(n), "additional_state_pension": np.zeros(n)}
        return AV.coverage_cell(values, np.ones(n), np.ones(n, bool))

    rows = AV.complementary_suppression({"three": cell(3), "four": cell(4), "large": cell(10), "zero": cell(0)})
    assert rows["large"]["status"] == "suppressed"
    assert rows["three"]["state_pension_bn"] is None and rows["four"]["state_pension_bn"] is None
    assert rows["zero"]["status"] == "available" and rows["zero"]["state_pension_bn"] == 0


def test_complementary_suppression_hides_ten_contributors_for_each_component():
    def cell(basic, new):
        amounts = np.r_[np.ones(basic), np.zeros(new)]
        values = {"state_pension": np.ones(basic + new), "basic_state_pension": amounts,
                  "new_state_pension": 1 - amounts, "additional_state_pension": np.zeros(basic + new)}
        return AV.coverage_cell(values, np.ones(basic + new), np.ones(basic + new, bool))

    rows = AV.complementary_suppression({"small": cell(3, 4), "basic": cell(10, 0), "new": cell(0, 10)})
    assert rows["basic"]["status"] == "suppressed" and rows["new"]["status"] == "suppressed"


def test_legacy_control_is_separate_from_the_factorial_interaction():
    runs = dict(zip(AV.MODES, [1, 2, 3, 7]))
    runs["legacy"] = -3
    result = AV.four_way(runs, lambda value: value)
    assert result["legacy"] == -3
    assert result["common_input_effect"] == 4
    assert result["interaction"] == 3


def test_central_plan_has_five_jobs_and_original_control(monkeypatch):
    monkeypatch.setattr(AV, "validation_semantics", lambda: {})
    plan = AV.validation_plan(central_only=True)
    assert len(plan["jobs"]) == 5
    assert [arg["demography"] for _, arg in plan["jobs"]] == list(AV.RUN_MODES)
    assert all("demography_years" not in arg for _, arg in plan["jobs"])


def test_explicit_calibration_year_enters_core_and_control_job_identity(monkeypatch):
    monkeypatch.setattr(AV, "validation_semantics", lambda: {})
    plan = AV.validation_plan(central_only=True, calibration_year=2025)
    assert plan["calibration_year"] == 2025
    assert all(arg["demography_calibration_year"] == 2025 for _, arg in plan["jobs"])


def test_cli_requires_calibration_before_starting_any_model(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("no model preparation before calibration is explicit")

    monkeypatch.setattr(AV, "validation_plan", forbidden)
    with pytest.raises(SystemExit) as error:
        AV.main(["--persistent-workers", "--workers", "4"])
    assert error.value.code == 2
    assert "require --calibration-year" in capsys.readouterr().err


def test_linked_suppression_withholds_whole_families_across_modes_years_policies_and_paths():
    def cell(status="available", records=20):
        return {"status": status, "records": records, "recipients_m": 0.2, "state_pension_bn": 1.0}

    def table():
        return {"GB": cell(), "by_age": {"80_plus": cell(), "zero": cell(records=0)},
                "by_country": {"England": cell()}, "by_region": {"London": cell()}}

    grouped = {path: {mode: {"coverage": {policy: {year: table() for year in (2024, 2025)}
                                        for policy in ("triple_lock", "burnham")}}
                     for mode in AV.RUN_MODES} for path in ("central", "draw_1")}
    grouped["central"]["both"]["coverage"]["triple_lock"][2024]["by_age"]["80_plus"] = cell("suppressed", None)
    grouped["draw_1"]["types"]["coverage"]["burnham"][2025]["by_country"]["England"] = cell("suppressed", None)
    grouped["draw_1"]["legacy"]["coverage"]["burnham"][2025]["GB"] = cell(records=7)
    suppression = AV.withhold_linked_coverage(grouped)
    assert suppression["age_tables_withheld"] and suppression["geography_tables_withheld"]
    for runs in grouped.values():
        for run in runs.values():
            for policy in run["coverage"].values():
                for rows in policy.values():
                    for name in ("by_age", "by_country", "by_region"):
                        for row in rows[name].values():
                            assert row["status"] == "withheld_family"
                            assert all(value is None for key, value in row.items() if key != "status")
    assert grouped["central"]["legacy"]["coverage"]["burnham"][2025]["GB"]["state_pension_bn"] == 1
    assert grouped["draw_1"]["legacy"]["coverage"]["burnham"][2025]["GB"]["state_pension_bn"] is None
    assert AV.withhold_linked_coverage(grouped) == suppression  # Repeated publication cannot undo the family guard.


def test_unaffected_family_remains_available():
    cell = {"status": "available", "records": 10, "state_pension_bn": 1}
    table = {"GB": cell.copy(), "by_age": {"a": cell.copy()},
             "by_country": {"England": {"status": "suppressed", "records": None, "state_pension_bn": None}},
             "by_region": {"London": cell.copy()}}
    grouped = {"central": {"both": {"coverage": {"triple_lock": {2025: table}}}}}
    suppression = AV.withhold_linked_coverage(grouped)
    assert not suppression["age_tables_withheld"] and suppression["geography_tables_withheld"]
    assert table["by_age"]["a"]["state_pension_bn"] == table["GB"]["state_pension_bn"] == 1


def test_country_region_overlap_cannot_reveal_suppressed_cells():
    regions = np.array(["LONDON"] * 20 + ["SCOTLAND"] * 3 + ["WALES"] * 4 + ["NORTHERN_IRELAND"] * 10)
    n = len(regions)
    arrays = {"region": regions, "age": np.full(n, 80), "person_weight": np.ones(n),
              "state_pension": np.ones(n), "basic_state_pension": np.ones(n),
              "new_state_pension": np.zeros(n), "additional_state_pension": np.zeros(n)}

    class Sim:
        def calculate(self, variable, year, map_to=None):
            return SimpleNamespace(to_numpy=lambda: arrays[variable])

    tables = AV.pension_coverage(Sim(), [2026])[2026]
    assert tables["GB"]["records"] == 27  # Northern Ireland is excluded.
    assert tables["GB"]["recipients_m"] == pytest.approx(27e-6)
    assert all(row["status"] == "suppressed" for row in tables["by_country"].values())
    assert all(tables["by_region"][name]["status"] == "suppressed" for name in ("LONDON", "SCOTLAND", "WALES"))
    assert tables["by_region"]["NORTH_EAST"]["records"] == 0
    assert tables["by_age"]["under_60"]["records"] == 0


def test_summary_preserves_paired_interaction_common_inputs_and_multiplicities(monkeypatch):
    monkeypatch.setattr(AV, "dwp_forecasts", lambda: {"years": {}})
    plan = {"labels": [], "sample": {1: [3, 3, 7]}, "W": {1: 0.8}, "W0": 0.2,
            "central_only": False, "source": "fixture", "source_sha256": "fixture",
            "validation_semantics": {}, "engine_semantics": {}, "packages": {}}
    results = []
    for path, base in (("central", 1), ("draw_3", 10), ("draw_7", 20)):
        values = {"legacy": 0.6 * base, "frozen": base, "reweight": 1.1 * base,
                  "types": 1.2 * base, "both": 1.8 * base}
        for mode in AV.RUN_MODES:
            plan["labels"].append((path, mode))
            value = values[mode]
            results.append({"saving_bn": {y: {key: value for key in ("gross", "net", "household_income_change")} for y in AV.HORIZON},
                            "totals_bn": {"triple_lock": {y: {key: value for key in ("state_pension", "basic_state_pension", "new_state_pension")} for y in AV.HORIZON}},
                            "coverage": {"triple_lock": {}}, "bundle": {"model_version": "test"},
                            "checks": {}, "dataset": "test", "data_year": 2024, "geography": "GB",
                            "largest_household": {"household_id": 123, "weight": 456}})
    report = AV.summarise(plan, results)
    assert report["central_four_way_saving_bn"]["gross"][2027]["common_input_effect"] == pytest.approx(0.4)
    contrasts = report["expected_four_way_saving_bn"]["gross"][2027]
    assert contrasts["interaction"]["mean_bn"] == pytest.approx(0.8 * np.mean([5, 5, 10]))
    assert contrasts["interaction"]["se_bn"] == pytest.approx(0.8 * np.std([5, 5, 10], ddof=1) / np.sqrt(3))
    assert contrasts["common_input_effect"]["mean_bn"] == pytest.approx(0.8 * np.mean([4, 4, 8]))
    public = json.dumps(report)
    assert "household_id" not in public and "largest_household" not in public and '"weight"' not in public


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
