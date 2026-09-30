"""Benchmark resolution and validation, and the DWP workbook parser (no PolicyEngine needed)."""

import csv

import pytest

from triple_lock import benchmarks, dwp


def test_resolve_follows_string_keys_integer_keys_and_list_indices():
    data = {"a": [{"b": {2039: 1.5, "2034": 2.5}}]}
    assert benchmarks.resolve(data, "a.0.b.2039") == 1.5
    assert benchmarks.resolve(data, "a.0.b.2034") == 2.5
    with pytest.raises((KeyError, IndexError)):
        benchmarks.resolve(data, "a.1.b.2039")


def _write(tmp_path, rows):
    p = tmp_path / "b.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=benchmarks.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return p


ROW = {"id": "x", "publisher": "P", "title": "T", "date": "2026-01-01", "url": "https://example.org", "figure_text": "F",
       "comparison": "C", "our_metric": "a.b", "like_for_like": "no", "note": "N", "verified": "true"}


@pytest.mark.parametrize("change", [{"url": "http://example.org"}, {"like_for_like": "maybe"}, {"verified": "yes"},
                                    {"note": " "}, {"our_metric": "a.missing"}])
def test_load_benchmarks_refuses_a_bad_row(tmp_path, change):
    with pytest.raises((ValueError, KeyError)):
        benchmarks.load_benchmarks({"a": {"b": 1.0}}, _write(tmp_path, [{**ROW, **change}]))


def test_load_benchmarks_refuses_a_non_numeric_target(tmp_path):
    with pytest.raises(ValueError):
        benchmarks.load_benchmarks({"a": {"b": "text"}}, _write(tmp_path, [ROW]))


def test_the_committed_benchmarks_point_at_results_paths_the_build_makes():
    with benchmarks.BENCHMARKS_CSV.open(newline="") as f:
        metrics = [r["our_metric"] for r in csv.DictReader(f)]
    roots = {"expected_value", "trajectories", "central"}
    assert all(m.split(".")[0] in roots for m in metrics)


def test_dwp_coverage_values_are_pinned_and_consistent():
    """The 2026-27 values read from DWP's Spring Forecast 2026 tables (£bn; caseloads in millions)."""
    v = dwp.coverage_targets()["values"]
    expected = {"state_pension_total": 154.175, "state_pension_abroad": 5.905, "state_pension_basic": 66.150,
                "state_pension_new": 64.812, "state_pension_caseload": 13.220, "state_pension_caseload_abroad": 1.068,
                "pension_credit": 6.055, "pension_credit_caseload": 1.312, "housing_benefit_capped": 11.643,
                "housing_benefit_la_funded": 0.831, "housing_benefit_pension_age": 7.269}
    for k, x in expected.items():
        assert v[k] == pytest.approx(x, abs=0.001), k
    assert v["state_pension_in_gb"] == pytest.approx(v["state_pension_total"] - v["state_pension_abroad"])
    assert v["state_pension_caseload_in_gb"] == pytest.approx(v["state_pension_caseload"] - v["state_pension_caseload_abroad"])
    assert v["state_pension_flat_rate"] == pytest.approx(v["state_pension_basic"] + v["state_pension_new"])
    assert v["housing_benefit"] == pytest.approx(v["housing_benefit_capped"] + v["housing_benefit_la_funded"])


def test_coverage_rows_map_the_model_to_dwp():
    """pipeline.coverage puts each model total beside its DWP figure, in the stated units."""
    from triple_lock.pipeline import coverage

    run = {"dataset": "d", "state_pension_bn": 140.0, "basic_state_pension_bn": 70.0, "new_state_pension_bn": 50.0,
           "state_pension_recipients": 12.0e6, "pension_credit_bn": 6.0, "pension_credit_benefit_units": 1.3e6,
           "housing_benefit_bn": 12.0, "housing_benefit_pensioner_benefit_units_bn": 7.0, "max_age": 80.0,
           "people": 68e6, "max_household_weight": 1e5, "records": {}, "pension_type_people": {},
           "state_pension_age_people": 12e6}
    cov = coverage({"primary": run, "sensitivity": {**run, "state_pension_bn": 150.0}})
    rows = {r["key"]: r for r in cov["rows"]}
    t = dwp.coverage_targets()["values"]
    assert rows["state_pension_bn"]["dwp"] == t["state_pension_in_gb"] and rows["state_pension_bn"]["primary"] == 140.0
    assert rows["state_pension_bn"]["sensitivity"] == 150.0
    assert rows["flat_rate_bn"]["primary"] == 120.0 and rows["flat_rate_bn"]["dwp"] == t["state_pension_flat_rate"]
    assert rows["state_pension_recipients_m"]["primary"] == 12.0  # millions
    assert "max_household_weight" not in cov["datasets"]["primary"]  # a survey record's weight is never published
    assert rows["pension_credit_claims_m"]["primary"] == 1.3
    assert rows["housing_benefit_pension_age_bn"]["dwp"] == t["housing_benefit_pension_age"]
