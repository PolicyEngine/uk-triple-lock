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
