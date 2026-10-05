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
    runtime = {"engine.py": "a" * 64, "demography.py": "b" * 64}
    validation = {"ageing_validation.py": "c" * 64, "demography.py": "b" * 64,
                  "ons_npp_2024_uk_age_sex.csv": "d" * 64}
    audit = {"passed": True, "minimum_contributing_records": 10,
             "person_and_household_support_checked": True, "field_component_and_union_support_checked": True,
             "withheld_families": {"age": False, "geography": False}, "model_version": "2.90.2",
             "years": list(range(2024, 2040)), "pair_year_checks": 160,
             "consecutive_year_checks": 75, "consecutive_year_support_checked": True,
             "pension_recipient_and_type_changes_checked": True, "age_cell_changes_checked": True,
             "weights_beyond_common_factor_checked": True,
             "plan_sha256": "e" * 64, "fiscal_function_sha256": "f" * 64,
             "publication_guard_sha256": "0" * 64,
             "audit_engine_semantics": copy.deepcopy(runtime),
             "pension_formula_sha256": copy.deepcopy(renderer.READ_PENSION_FORMULAS),
             "macro_path_support_proof": {"paths_checked": 41,
                 "identical_state_pension_age_changes": True, "data_year_flat_rate_ceilings_unchanged": True,
                 "positive_common_uprating_multipliers": True}}
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
        "checks": {path: {mode: copy.deepcopy(checks) for mode in renderer.MODES}
                   for path in ("central", *(f"draw_{index}" for index in range(40)))},
        "worker_execution": {"Enhanced_FRS_workers": 8,
                    "Microcosm_workers": 0, "persistent": True, "maximum_jobs_per_worker": 20},
        "dataset": "synthetic in-memory fixture", "calibration_year": 2025, "data_year": 2024,
        "generated_at": "synthetic", "source_results_sha256": "fixture",
        "provenance": {"engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation)},
        "plan_sha256": "e" * 64, "fiscal_function_sha256": "f" * 64,
        "calculation_head": "1" * 40,
        "calculation_provenance": {"head": "1" * 40, "dirty": False,
                                   "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation)},
        "publication_provenance": {"head": "2" * 40, "dirty": True,
                                   "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation)},
        "calibration_anchor": {"source_calibration_year": 2025, "source_data_tag": "1.56.16",
            "source_commit": "12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3", "runtime_anchor_year": 2025,
            "runtime_restores_builder_calibration": False, "verified_artifact_calibration_manifest": False,
            "source_url": "https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57",
            "weights_basis": "Native runtime 2025 weights; builder calibration preservation unverified"},
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
    assert "8 Enhanced FRS workers, 0 Microcosm workers" in output
    assert "not matched GB benchmarks" in output
    assert "| 2039–40 |" in output
    assert "legacy and frozen already share the integer-age pension-eligibility gate" in output
    assert "birthday inputs can also affect eligibility" in output
    assert "native runtime 2025 weights" in output
    assert "builder calibration preservation unverified" in output
    assert "| Publication head | " + "2" * 40 in output


def test_failure_preserves_an_existing_output_file(tmp_path):
    input_path, output_path = tmp_path / "unapproved.json", tmp_path / "report.md"
    input_path.write_text(json.dumps({"publication_privacy_audit": {"passed": False}}))
    output_path.write_text("Existing report\n")
    with pytest.raises(ValueError, match="passed"):
        renderer.main([str(input_path), "-o", str(output_path)])
    assert output_path.read_text() == "Existing report\n"


def change_field(report, path, value=None, remove=False):
    parent = report
    for name in path[:-1]:
        parent = parent[name]
    if remove:
        parent.pop(path[-1])
    else:
        parent[path[-1]] = value


@pytest.mark.parametrize("path", [
    ("publication_privacy_audit", "plan_sha256"),
    ("publication_privacy_audit", "fiscal_function_sha256"),
    ("publication_privacy_audit", "publication_guard_sha256"),
    ("publication_privacy_audit", "audit_engine_semantics"),
    ("publication_privacy_audit", "model_version"),
    ("publication_privacy_audit", "pension_formula_sha256"),
    ("publication_privacy_audit", "years"),
    ("publication_privacy_audit", "pair_year_checks"),
    *( ("publication_privacy_audit", field) for field in (
        "consecutive_year_checks", "consecutive_year_support_checked", "pension_recipient_and_type_changes_checked",
        "age_cell_changes_checked", "weights_beyond_common_factor_checked")),
    ("publication_privacy_audit", "macro_path_support_proof"),
    *( ("publication_privacy_audit", "macro_path_support_proof", field) for field in (
        "paths_checked", "identical_state_pension_age_changes",
        "data_year_flat_rate_ceilings_unchanged", "positive_common_uprating_multipliers")),
    ("plan_sha256",), ("fiscal_function_sha256",),
    ("provenance", "engine_semantics"), ("provenance", "validation_semantics"),
    ("calculation_head",), ("calculation_provenance",), ("publication_provenance",),
    *( (name, field) for name in ("calculation_provenance", "publication_provenance")
       for field in ("head", "dirty", "engine_semantics", "validation_semantics")),
    ("worker_execution", "Enhanced_FRS_workers"), ("worker_execution", "Microcosm_workers"),
    ("calibration_anchor",),
    *( ("calibration_anchor", field) for field in (
        "source_calibration_year", "runtime_anchor_year", "source_commit", "source_data_tag", "source_url",
        "weights_basis", "runtime_restores_builder_calibration", "verified_artifact_calibration_manifest")),
])
def test_required_publication_binding_field_cannot_be_omitted(path):
    report = approved_fixture()
    change_field(report, path, remove=True)
    with pytest.raises(ValueError):
        renderer.validate_report(report)


@pytest.mark.parametrize("path,value", [
    (("publication_privacy_audit", "plan_sha256"), "9" * 64),
    (("publication_privacy_audit", "fiscal_function_sha256"), "9" * 64),
    (("publication_privacy_audit", "publication_guard_sha256"), "short"),
    (("publication_privacy_audit", "audit_engine_semantics", "engine.py"), "9" * 64),
    (("provenance", "validation_semantics", "demography.py"), "9" * 64),
    (("publication_privacy_audit", "model_version"), "2.118.0"),
    (("publication_privacy_audit", "pension_formula_sha256", "basic_state_pension"), "9" * 64),
    (("publication_privacy_audit", "years"), list(range(2025, 2040))),
    (("publication_privacy_audit", "years"), [*range(2024, 2040), 2039]),
    (("publication_privacy_audit", "pair_year_checks"), 159),
    (("publication_privacy_audit", "pair_year_checks"), True),
    (("publication_privacy_audit", "consecutive_year_checks"), 74),
    (("publication_privacy_audit", "consecutive_year_checks"), True),
    *( (("publication_privacy_audit", field), False) for field in (
        "consecutive_year_support_checked", "pension_recipient_and_type_changes_checked",
        "age_cell_changes_checked", "weights_beyond_common_factor_checked")),
    (("publication_privacy_audit", "macro_path_support_proof", "paths_checked"), 40),
    (("publication_privacy_audit", "macro_path_support_proof", "identical_state_pension_age_changes"), False),
    (("publication_privacy_audit", "macro_path_support_proof", "positive_common_uprating_multipliers"), "true"),
    (("calculation_head",), "missing"),
    (("calculation_provenance", "head"), "9" * 40),
    (("calculation_provenance", "engine_semantics", "engine.py"), "9" * 64),
    (("calculation_provenance", "validation_semantics", "ageing_validation.py"), "9" * 64),
    (("publication_provenance", "head"), ""),
    (("publication_provenance", "dirty"), "false"),
    (("publication_provenance", "engine_semantics", "demography.py"), "9" * 64),
    (("worker_execution", "Enhanced_FRS_workers"), True),
    (("worker_execution", "Enhanced_FRS_workers"), 0),
    (("worker_execution", "Enhanced_FRS_workers"), -1),
    (("worker_execution", "Microcosm_workers"), 3),
    (("worker_execution", "Microcosm_workers"), -1),
    (("worker_execution", "Microcosm_workers"), False),
    (("calibration_anchor", "runtime_anchor_year"), 2024),
    (("calibration_anchor", "verified_artifact_calibration_manifest"), "false"),
    (("calibration_anchor", "source_url"), "https://github.com/PolicyEngine/policyengine-uk-data/blob/main/frs_release.py"),
])
def test_stale_or_invalid_publication_binding_is_rejected(path, value):
    report = approved_fixture()
    change_field(report, path, value)
    with pytest.raises(ValueError):
        renderer.validate_report(report)


def test_does_not_reuse_support_proof_for_an_upgraded_bundle():
    report = approved_fixture()
    report["bundle"]["model_version"] = report["publication_privacy_audit"]["model_version"] = "2.118.0"
    with pytest.raises(ValueError, match="formula proof"):
        renderer.validate_report(report)


def test_missing_path_or_treatment_checks_are_rejected():
    for key in ("draw_39", "both"):
        report = approved_fixture()
        if key.startswith("draw"):
            del report["checks"][key]
        else:
            del report["checks"]["central"][key]
        with pytest.raises(ValueError, match="every distinct"):
            renderer.validate_report(report)


def test_conflicting_worker_count_spellings_are_rejected():
    report = approved_fixture()
    report["worker_execution"]["enhanced_frs_workers"] = 7
    with pytest.raises(ValueError, match="disagrees"):
        renderer.validate_report(report)


def test_worker_count_lowercase_spelling_is_supported():
    report = approved_fixture()
    worker = report["worker_execution"]
    worker["enhanced_frs_workers"] = worker.pop("Enhanced_FRS_workers")
    worker["microcosm_workers"] = worker.pop("Microcosm_workers")
    assert renderer.worker_counts(report) == (8, 0)
