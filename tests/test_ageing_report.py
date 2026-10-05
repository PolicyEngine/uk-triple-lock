"""The public renderer fails closed and copies approved aggregate estimates."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ageing_report", ROOT / "scripts" / "report_ageing_validation.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def approved_fixture():
    """Synthetic aggregates used in memory only; never a published result file."""
    cell = {"status": "available", "records": 20, **{field: 1.0 for field in renderer.CELL_FIELDS}}
    tables = {str(y): {"GB": copy.deepcopy(cell), "by_age": {"80_84": copy.deepcopy(cell)},
                      "by_country": {"England": copy.deepcopy(cell)}, "by_region": {"LONDON": copy.deepcopy(cell)}}
              for y in range(2024, 2040)}
    contrast = {name: 12.345 for name in renderer.CONTRASTS}
    central = {metric: {str(y): copy.deepcopy(contrast) for y in renderer.FORECAST_YEARS}
               for metric in ("gross", "net")}
    expected = {metric: {str(y): {name: {"mean_bn": 42.123, "se_bn": 0.456} for name in renderer.CONTRASTS}
                        for y in renderer.FORECAST_YEARS} for metric in ("gross", "net")}
    audit = {"passed": True, "minimum_contributing_records": 10,
             "person_and_household_support_checked": True, "field_component_and_union_support_checked": True,
             "withheld_families": {"age": False, "geography": False}, "model_version": "2.90.2"}
    contexts = {field: 3.141 for field in ("basic_state_pension_bn", "new_state_pension_bn",
                "new_protected_payments_bn", "basic_recipients_m", "new_recipients_m")}
    checks = {"max_relative_cell_error": 1e-7, "eligible_components_identity_within_penny": True,
              "unchanged_type_additional_matches_original_within_penny": True,
              "positive_reports_below_model_pension_age_records": 40,
              "represented_topcoding_applied": True, "uncapped_age_fallback": False,
              "pinned_survey_flags": ["is_benunit_head"]}
    return {
        "publication_privacy_audit": audit, "minimum_contributing_records": 10,
        "complete_paired_design": True, "paired_sample": {"draws_by_stratum": {"1": list(range(40))}},
        "bundle": {"model_version": "2.90.2", "policyengine_version": "5.3.0", "bundle_id": "synthetic",
                   "certified_data_build_id": "synthetic"},
        "central_coverage": {mode: {policy: copy.deepcopy(tables) for policy in ("triple_lock", "burnham_2030")}
                             for mode in renderer.MODES},
        "suppression_policy": {"age_tables_withheld": False, "geography_tables_withheld": False},
        "central_four_way_saving_bn": central, "expected_four_way_saving_bn": expected,
        "coverage_comparisons": [{"year": y, "mode": mode, "metric": metric, "status": "available",
                                  "model_GB": 7.111, "benchmark_GB": 8.222, "difference": 99.333}
                                 for y in renderer.COVERAGE_YEARS for mode in renderer.MODES
                                 for metric in ("state_pension_bn", "recipients_m")],
        "dwp": {"source": "Synthetic source", "url": "https://example.org/synthetic", "sha256": "fixture",
                "years": {str(y): {"GB_plus_overseas_context": copy.deepcopy(contexts)}
                          for y in renderer.COVERAGE_YEARS},
                "unavailable": {field: "Synthetic unavailability" for field in
                                ("GB_by_type", "by_age", "by_geography", "after_2030")}},
        "checks": {"central": {"both": checks}}, "worker_execution": {"Enhanced_FRS_workers": 6,
                    "Microcosm_workers": 0, "persistent": True, "maximum_jobs_per_worker": 20},
        "dataset": "synthetic in-memory fixture", "calibration_year": 2024, "data_year": 2024,
        "generated_at": "synthetic", "source_results_sha256": "fixture",
        "provenance": {"engine_semantics": {"engine.py": "fixture"},
                       "validation_semantics": {"ons_npp_2024_uk_age_sex.csv": "fixture"}},
    }


@pytest.mark.parametrize("change", [None, {"passed": False}, {"passed": True}])
def test_requires_complete_passed_publication_audit(change):
    report = approved_fixture()
    report["publication_privacy_audit"] = change
    with pytest.raises(ValueError, match="audit|support"):
        renderer.validate_report(report)


def test_rejects_positive_cell_with_nine_contributors():
    report = approved_fixture()
    report["central_coverage"]["both"]["triple_lock"]["2024"]["by_age"]["80_84"]["records"] = 9
    with pytest.raises(ValueError, match="fewer"):
        renderer.validate_report(report)


def test_rejects_nonavailable_cell_with_nonnull_data():
    report = approved_fixture()
    report["central_coverage"]["legacy"]["burnham_2030"]["2025"]["GB"]["status"] = "suppressed"
    with pytest.raises(ValueError, match="still contains data"):
        renderer.validate_report(report)


def test_rejects_record_level_fields_even_with_a_passed_audit():
    report = approved_fixture()
    report["unrelated_metadata"] = {"household_weight": [1, 2, 3]}
    with pytest.raises(ValueError, match="record-level"):
        renderer.validate_report(report)


def test_zero_support_zero_cells_are_allowed():
    renderer.validate_cell({"status": "available", "records": 0,
                            **{field: 0 for field in renderer.CELL_FIELDS}}, minimum=10)


def test_withheld_family_prints_status_without_fallback_data():
    report = approved_fixture()
    report["suppression_policy"]["age_tables_withheld"] = True
    # Contributor suppression can be stricter than the cross-treatment audit.
    report["publication_privacy_audit"]["withheld_families"]["age"] = False
    for policies in report["central_coverage"].values():
        for tables in policies.values():
            for table in tables.values():
                table["by_age"] = {"80_84": {"status": "withheld_family", "records": None,
                                            **{field: None for field in renderer.CELL_FIELDS}}}
    output = renderer.render(report, "fixture", "synthetic.json")
    assert "**Withheld family:**" in output
    assert "| 2024–25 | 80_84 |" not in output


def test_family_suppression_cannot_weaken_the_cross_treatment_audit():
    report = approved_fixture()
    report["publication_privacy_audit"]["withheld_families"]["age"] = True
    with pytest.raises(ValueError, match="weakens"):
        renderer.validate_report(report)


def test_copies_provided_means_standard_errors_and_benchmark_differences():
    output = renderer.render(approved_fixture(), "fixture", "synthetic.json")
    assert "42.123 ± 0.456" in output
    assert "7.111 | 8.222 | 99.333" in output  # supplied difference, never recalculated
    assert "6 Enhanced FRS workers, 0 Microcosm workers" in output
    assert "not matched GB benchmarks" in output
    assert "| 2039–40 |" in output
    assert "legacy and frozen already share the integer-age pension-eligibility gate" in output
    assert "birthday inputs can also affect eligibility" in output


def test_failure_preserves_an_existing_output_file(tmp_path):
    input_path, output_path = tmp_path / "unapproved.json", tmp_path / "report.md"
    input_path.write_text(json.dumps({"publication_privacy_audit": {"passed": False}}))
    output_path.write_text("Existing report\n")
    with pytest.raises(ValueError, match="passed"):
        renderer.main([str(input_path), "-o", str(output_path)])
    assert output_path.read_text() == "Existing report\n"
