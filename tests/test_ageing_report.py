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
             "all_year_pairs_support_checked": True, "all_year_pair_checks": 600,
             "treatment_contrast_year_support_checked": True, "treatment_contrast_year_checks": 1200,
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
    report = {
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
                    "Microcosm_workers": 0, "persistent": True, "maximum_jobs_per_worker": 20,
                    "initial_cached_jobs": 0, "planned_jobs": 205, "completed_jobs": 205,
                    "execution_log_sha256": "5" * 64},
        "integration_evidence": {"legacy_matches_committed_central": True, "opt_in_engine_run_passed": True,
            "record_diagnostics_suppressed": True, "persistent_matches_isolated": True,
            "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation),
            "preceding_mode": "legacy", "full_model_verification_jobs": 5,
            "integration_file_sha256": "6" * 64, "equivalence_file_sha256": "7" * 64},
        "dataset": "synthetic in-memory fixture", "calibration_year": 2025, "data_year": 2024,
        "generated_at": "synthetic", "source_results_sha256": "fixture",
        "provenance": {"engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation)},
        "plan_sha256": "e" * 64, "fiscal_function_sha256": "f" * 64,
        "calculation_head": "1" * 40,
        "calculation_provenance": {"head": "1" * 40, "dirty": False,
                                   "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation)},
        "publication_provenance": {"head": "2" * 40, "dirty": True,
                                   "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation),
                                   "publication_code_sha256": {"ageing_publication.py": "0" * 64,
                                       "publish_ageing_validation.py": "4" * 64,
                                       "report_ageing_validation.py": renderer.hashlib.sha256(Path(renderer.__file__).read_bytes()).hexdigest()}},
        "calibration_anchor": {"source_calibration_year": 2025, "source_data_tag": "1.56.16",
            "source_commit": "12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3", "runtime_anchor_year": 2025,
            "runtime_restores_builder_calibration": False, "verified_artifact_calibration_manifest": False,
            "source_url": "https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57",
            "weights_basis": "Native runtime 2025 weights; builder calibration preservation unverified"},
    }
    audit.update({"audit_validation_semantics": copy.deepcopy(validation),
                  "bundle": copy.deepcopy(report["bundle"]), "data_year": report["data_year"],
                  "dataset": report["dataset"], "pinned_keys_checked": True,
                  "calculation_head": report["calculation_head"],
                  "calculation_provenance": {**copy.deepcopy(report["calculation_provenance"]),
                                             "plan_sha256": report["plan_sha256"],
                                             "fiscal_function_sha256": report["fiscal_function_sha256"]},
                  "publication_provenance": copy.deepcopy(report["publication_provenance"]),
                  "publication_code_sha256": copy.deepcopy(report["publication_provenance"]["publication_code_sha256"]),
                  "calibration_anchor": copy.deepcopy(report["calibration_anchor"]),
                  "calculation_source_head_verification": {"verified": True, "head": report["calculation_head"],
                      "engine_semantics": copy.deepcopy(runtime), "validation_semantics": copy.deepcopy(validation),
                      "files_checked": len(set(runtime) | set(validation))}})
    return report


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
    assert "8 Enhanced FRS slots, 0 Microcosm workers" in output
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
    *( ("publication_privacy_audit", field) for field in (
        "audit_validation_semantics", "bundle", "data_year", "dataset", "pinned_keys_checked",
        "calculation_head", "calculation_provenance", "publication_provenance", "calibration_anchor")),
    ("publication_privacy_audit", "calculation_provenance", "plan_sha256"),
    ("publication_privacy_audit", "calculation_provenance", "fiscal_function_sha256"),
    ("publication_privacy_audit", "publication_code_sha256"),
    *( ("publication_privacy_audit", field) for field in (
        "all_year_pairs_support_checked", "all_year_pair_checks", "treatment_contrast_year_support_checked",
        "treatment_contrast_year_checks", "calculation_source_head_verification")),
    *( ("publication_privacy_audit", "calculation_source_head_verification", field) for field in (
        "verified", "head", "engine_semantics", "validation_semantics", "files_checked")),
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
    *( ("worker_execution", field) for field in (
        "initial_cached_jobs", "planned_jobs", "completed_jobs", "execution_log_sha256")),
    ("integration_evidence",),
    *( ("integration_evidence", field) for field in (
        "legacy_matches_committed_central", "opt_in_engine_run_passed", "record_diagnostics_suppressed",
        "persistent_matches_isolated", "engine_semantics", "validation_semantics", "preceding_mode",
        "full_model_verification_jobs", "integration_file_sha256", "equivalence_file_sha256")),
    ("calibration_anchor",),
    *( ("calibration_anchor", field) for field in (
        "source_calibration_year", "runtime_anchor_year", "source_commit", "source_data_tag", "source_url",
        "weights_basis", "runtime_restores_builder_calibration", "verified_artifact_calibration_manifest")),
])
def test_required_publication_binding_field_cannot_be_omitted(path):
    report = approved_fixture()
    change_field(report, path, remove=True)
    if path in (("plan_sha256",), ("fiscal_function_sha256",)):
        report["publication_privacy_audit"]["calculation_provenance"].pop(path[0])
    elif path in (("publication_provenance",), ("calibration_anchor",)):
        report["publication_privacy_audit"].pop(path[0])
    with pytest.raises(ValueError):
        renderer.validate_report(report)


@pytest.mark.parametrize("path,value", [
    (("publication_privacy_audit", "plan_sha256"), "9" * 64),
    (("publication_privacy_audit", "fiscal_function_sha256"), "9" * 64),
    (("publication_privacy_audit", "publication_guard_sha256"), "short"),
    (("publication_privacy_audit", "audit_engine_semantics", "engine.py"), "9" * 64),
    (("publication_privacy_audit", "audit_validation_semantics", "ageing_validation.py"), "9" * 64),
    (("publication_privacy_audit", "bundle", "bundle_id"), "stale"),
    (("publication_privacy_audit", "data_year"), 2025),
    (("publication_privacy_audit", "dataset"), "stale"),
    (("publication_privacy_audit", "pinned_keys_checked"), False),
    (("publication_privacy_audit", "calculation_head"), "9" * 40),
    (("publication_privacy_audit", "calculation_provenance", "head"), "9" * 40),
    (("publication_privacy_audit", "all_year_pairs_support_checked"), False),
    (("publication_privacy_audit", "all_year_pair_checks"), 599),
    (("publication_privacy_audit", "treatment_contrast_year_support_checked"), False),
    (("publication_privacy_audit", "treatment_contrast_year_checks"), 1199),
    (("publication_privacy_audit", "calculation_source_head_verification", "verified"), False),
    (("publication_privacy_audit", "calculation_source_head_verification", "head"), "9" * 40),
    (("publication_privacy_audit", "calculation_source_head_verification", "files_checked"), 3),
    (("publication_privacy_audit", "calculation_source_head_verification", "files_checked"), True),
    (("publication_privacy_audit", "calculation_source_head_verification", "engine_semantics", "engine.py"), "9" * 64),
    (("publication_privacy_audit", "calculation_source_head_verification", "validation_semantics", "ageing_validation.py"), "9" * 64),
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
    (("worker_execution", "Microcosm_workers"), 1),
    (("worker_execution", "Microcosm_workers"), 2),
    (("worker_execution", "Microcosm_workers"), -1),
    (("worker_execution", "Microcosm_workers"), False),
    (("worker_execution", "initial_cached_jobs"), -1),
    (("worker_execution", "initial_cached_jobs"), 206),
    (("worker_execution", "initial_cached_jobs"), False),
    (("worker_execution", "planned_jobs"), 204),
    (("worker_execution", "completed_jobs"), 204),
    (("worker_execution", "execution_log_sha256"), "short"),
    *( (("integration_evidence", field), False) for field in (
        "legacy_matches_committed_central", "opt_in_engine_run_passed", "record_diagnostics_suppressed",
        "persistent_matches_isolated")),
    (("integration_evidence", "engine_semantics", "engine.py"), "9" * 64),
    (("integration_evidence", "validation_semantics", "ageing_validation.py"), "9" * 64),
    (("integration_evidence", "preceding_mode"), "both"),
    (("integration_evidence", "full_model_verification_jobs"), 4),
    (("integration_evidence", "integration_file_sha256"), "short"),
    (("integration_evidence", "equivalence_file_sha256"), "short"),
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
    report["publication_privacy_audit"]["bundle"]["model_version"] = "2.118.0"
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


def test_frozen_cli_authoritative_nested_metadata_can_be_rendered():
    report = approved_fixture()
    for name in ("publication_provenance", "calibration_anchor", "plan_sha256", "fiscal_function_sha256"):
        del report[name]
    output = renderer.render(report, "fixture", "synthetic.json")
    assert "| Publication head | " + "2" * 40 in output
    assert "native runtime 2025 weights" in output
    assert "| Publication-audited plan SHA-256 | " + "e" * 64 in output
    # Normalisation is local to the renderer; the approved payload is unchanged.
    assert "publication_provenance" not in report
    assert "plan_sha256" not in report


@pytest.mark.parametrize("path,value", [
    (("publication_privacy_audit", "publication_provenance", "head"), "3" * 40),
    (("publication_privacy_audit", "publication_provenance", "dirty"), False),
    (("publication_privacy_audit", "publication_provenance", "engine_semantics", "engine.py"), "3" * 64),
    (("publication_privacy_audit", "calibration_anchor", "runtime_anchor_year"), 2024),
    (("publication_privacy_audit", "calibration_anchor", "runtime_restores_builder_calibration"), True),
    (("publication_privacy_audit", "calculation_provenance", "plan_sha256"), "3" * 64),
    (("publication_privacy_audit", "calculation_provenance", "fiscal_function_sha256"), "3" * 64),
])
def test_conflicting_nested_and_top_level_metadata_is_rejected(path, value):
    report = approved_fixture()
    change_field(report, path, value)
    with pytest.raises(ValueError, match="conflicts"):
        renderer.render(report, "fixture", "synthetic.json")


@pytest.mark.parametrize("path,value", [
    (("publication_privacy_audit", "publication_provenance", "head"), None),
    (("publication_privacy_audit", "publication_provenance", "dirty"), "false"),
    (("publication_privacy_audit", "calibration_anchor", "runtime_anchor_year"), 2024),
    (("publication_privacy_audit", "calculation_provenance", "plan_sha256"), "3" * 64),
])
def test_nested_compatibility_does_not_weaken_any_binding(path, value):
    report = approved_fixture()
    for name in ("publication_provenance", "calibration_anchor", "plan_sha256", "fiscal_function_sha256"):
        del report[name]
    change_field(report, path, value)
    with pytest.raises(ValueError):
        renderer.render(report, "fixture", "synthetic.json")


def test_publication_head_requires_all_forty_characters_even_if_both_copies_match():
    report = approved_fixture()
    report["publication_provenance"]["head"] = "2" * 7
    report["publication_privacy_audit"]["publication_provenance"]["head"] = "2" * 7
    with pytest.raises(ValueError, match="forty"):
        renderer.render(report, "fixture", "synthetic.json")


@pytest.mark.parametrize("name", ("ageing_publication.py", "publish_ageing_validation.py", "report_ageing_validation.py"))
def test_actual_publication_code_hash_cannot_be_omitted(name):
    report = approved_fixture()
    for provenance in (report["publication_provenance"], report["publication_privacy_audit"]["publication_provenance"]):
        del provenance["publication_code_sha256"][name]
    with pytest.raises(ValueError, match="source hashes"):
        renderer.validate_report(report)


@pytest.mark.parametrize("name,digest,match", [
    ("ageing_publication.py", "9" * 64, "module and guard"),
    ("publish_ageing_validation.py", "short", "SHA-256"),
    ("report_ageing_validation.py", "9" * 64, "differs from this script"),
])
def test_actual_publication_code_hash_bindings_are_enforced(name, digest, match):
    report = approved_fixture()
    for provenance in (report["publication_provenance"], report["publication_privacy_audit"]["publication_provenance"]):
        provenance["publication_code_sha256"][name] = digest
    report["publication_privacy_audit"]["publication_code_sha256"][name] = digest
    with pytest.raises(ValueError, match=match):
        renderer.validate_report(report)


@pytest.mark.parametrize("name", ("ageing_publication.py", "publish_ageing_validation.py", "report_ageing_validation.py"))
def test_audit_requires_every_actual_publication_code_hash(name):
    report = approved_fixture()
    del report["publication_privacy_audit"]["publication_code_sha256"][name]
    with pytest.raises(ValueError, match="source hashes"):
        renderer.validate_report(report)


@pytest.mark.parametrize("name", ("ageing_publication.py", "publish_ageing_validation.py", "report_ageing_validation.py"))
def test_publication_code_hashes_cannot_differ_from_audited_map(name):
    report = approved_fixture()
    report["publication_privacy_audit"]["publication_code_sha256"][name] = "9" * 64
    with pytest.raises(ValueError, match="authoritative audit"):
        renderer.validate_report(report)


def test_requested_worker_slot_fields_are_supported():
    report = approved_fixture()
    worker = report["worker_execution"]
    worker["requested_enhanced_frs_workers"] = worker.pop("Enhanced_FRS_workers")
    worker["requested_microcosm_workers"] = worker.pop("Microcosm_workers")
    assert renderer.worker_counts(report) == (8, 0)


def test_source_head_verification_display_does_not_assert_the_driver_dirty_literal():
    output = renderer.render(approved_fixture(), "fixture", "synthetic.json")
    assert "| Calculation source files verified against head | True |" in output
    assert "Not measured by the pilot driver; source-map files verified separately" in output
    assert "| Calculation tree dirty | False |" not in output
    assert "Great Britain, nominal £bn" in output


def test_execution_and_integration_display_copies_file_backed_evidence():
    output = renderer.render(approved_fixture(), "fixture", "synthetic.json")
    assert "0 initially cached of 205 planned jobs; 205 newly complete" in output
    assert "| Full-model verification jobs | 5 |" in output
    assert "| Integration file SHA-256 | " + "6" * 64 in output
    assert "| Worker-equivalence file SHA-256 | " + "7" * 64 in output
    assert "one preceding legacy job" in output
    assert "does not enumerate every nonlinear programme-state contrast" in output


def test_completed_cached_jobs_are_allowed_when_the_design_is_complete():
    report = approved_fixture()
    report["worker_execution"]["initial_cached_jobs"] = 5
    report["worker_execution"]["completed_jobs"] = 200
    renderer.validate_report(report)
