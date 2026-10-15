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


def test_dwp_tables_by_year():
    """Every year to 2030-31 reads, the first is the 2026-27 reader's, and the pension-age Housing Benefit caseload is
    there (thousands -> millions)."""
    by_year = dwp.coverage_targets_by_year()
    assert sorted(by_year) == dwp.TABLE_YEARS == list(range(2026, 2031))
    assert by_year[2026]["values"] == dwp.coverage_targets()["values"]
    assert [by_year[y]["year"] for y in dwp.TABLE_YEARS] == ["2026/27", "2027/28", "2028/29", "2029/30", "2030/31"]
    assert by_year[2026]["values"]["housing_benefit_caseload_pension_age"] == pytest.approx(1.082, abs=0.001)
    assert by_year[2030]["values"]["state_pension_flat_rate"] > by_year[2026]["values"]["state_pension_flat_rate"]


def _stats(scale=1.0, gb_share=0.97):
    uk = {"state_pension_bn": 140.0, "basic_state_pension_bn": 70.0, "new_state_pension_bn": 50.0,
          "additional_state_pension_bn": 20.0, "state_pension_recipients": 12.0e6, "state_pension_age_people": 12e6,
          "pension_type_people": {"BASIC": 7e6, "NEW": 5e6, "NONE": 56e6}, "pension_credit_bn": 6.0,
          "guarantee_credit_bn": 5.0, "savings_credit_bn": 1.0, "pension_credit_benefit_units": 1.3e6,
          "housing_benefit_bn": 12.0, "housing_benefit_benefit_units": 2.0e6, "housing_benefit_pension_age_bn": 7.0,
          "housing_benefit_pension_age_benefit_units": 1.1e6, "housing_benefit_pensioner_benefit_units_bn": 7.2,
          "council_tax_reduction_bn": 2.0, "universal_credit_bn": 80.0, "people": 68e6}
    uk = {k: (v * scale if isinstance(v, float) else v) for k, v in uk.items()}
    gb = {k: (v * gb_share if isinstance(v, float) else v) for k, v in uk.items()}
    uk["households_by_country"] = {"ENGLAND": 25e6, "NORTHERN_IRELAND": 0.8e6, "SCOTLAND": 2.5e6, "WALES": 1.4e6}
    gb["households_by_country"] = None
    return {"uk": uk, "gb": gb}


def test_coverage_rows_map_the_model_to_dwp():
    """pipeline.coverage puts each model total, UK and GB, beside its DWP figure in the stated units, in 2026-27 and
    in every year a coverage job ran; years past DWP's tables have no DWP figure."""
    from triple_lock.pipeline import COVERAGE_YEARS, coverage

    def run(scale):
        return {"dataset": "d", "model": {"model_version": "x"}, "max_age": 80.0,
                "records": {"households": 3, "people": 5}, "path": None, "data_year": 2024,
                "by_year": {y: _stats(scale * (1 + 0.03 * (y - 2026))) for y in COVERAGE_YEARS}}

    cov = coverage({"primary": run(1.0), "sensitivity": run(150 / 140)})
    rows = {r["key"]: r for r in cov["rows"]}
    t = dwp.coverage_targets()["values"]
    assert rows["state_pension_bn"]["dwp"] == t["state_pension_in_gb"] and rows["state_pension_bn"]["primary"] == 140.0
    assert rows["state_pension_bn"]["primary_gb"] == pytest.approx(140.0 * 0.97)
    assert rows["state_pension_bn"]["primary_gb_over_dwp"] == pytest.approx(140.0 * 0.97 / t["state_pension_in_gb"])
    assert rows["state_pension_bn"]["sensitivity"] == pytest.approx(150.0)
    assert rows["flat_rate_bn"]["primary"] == 120.0 and rows["flat_rate_bn"]["dwp"] == t["state_pension_flat_rate"]
    assert rows["state_pension_recipients_m"]["primary"] == 12.0  # millions
    assert rows["pension_credit_claims_m"]["primary"] == 1.3
    assert rows["housing_benefit_pension_age_bn"]["dwp"] == t["housing_benefit_pension_age"]
    assert rows["housing_benefit_pension_age_claims_m"]["primary"] == pytest.approx(1.1)
    assert not {"max_household_weight", "weight"} & set(cov["datasets"]["primary"])  # no survey record's weight
    assert sorted(cov["by_year"]) == COVERAGE_YEARS and cov["rows"] == cov["by_year"][2026]["rows"]
    later = {r["key"]: r for r in cov["by_year"][2030]["rows"]}
    assert cov["by_year"][2030]["dwp_year"] == "2030/31"
    assert later["pension_credit_bn"]["dwp"] == dwp.coverage_targets_by_year()[2030]["values"]["pension_credit"]
    assert later["pension_credit_bn"]["primary"] == pytest.approx(6.0 * 1.12)
    for y in (2034, 2039):
        assert cov["by_year"][y]["dwp_year"] is None
        assert all(r["dwp"] is None and "primary_gb_over_dwp" not in r for r in cov["by_year"][y]["rows"])


def test_coverage_fails_on_households_of_unknown_country():
    """Great Britain is England, Scotland and Wales, so a dataset with households of unknown country would leave them
    out of the comparison with DWP: the build fails instead (neither dataset has any)."""
    from triple_lock.pipeline import COVERAGE_YEARS, coverage

    stats = _stats()
    stats["uk"]["households_by_country"] = {"ENGLAND": 10.0, "UNKNOWN": 1.0}
    run = {"dataset": "d", "model": {}, "max_age": 80.0, "records": {}, "path": None, "data_year": 2024,
           "by_year": {y: stats for y in COVERAGE_YEARS}}
    with pytest.raises(ValueError, match="unknown country"):
        coverage({"primary": run})


def test_coverage_fails_without_the_country_record():
    """A coverage block that does not say which country its households are in cannot show none is unknown."""
    from triple_lock.pipeline import COVERAGE_YEARS, coverage

    stats = _stats()
    del stats["uk"]["households_by_country"]
    run = {"dataset": "d", "model": {}, "max_age": 80.0, "records": {}, "path": None, "data_year": 2024,
           "by_year": {y: stats for y in COVERAGE_YEARS}}
    with pytest.raises(ValueError, match="which country"):
        coverage({"primary": run})
