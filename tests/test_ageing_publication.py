"""Publication must protect component differences and both survey entities."""

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from triple_lock import ageing_publication as AP, ageing_validation as AV


def snapshots(households=30, members=1):
    n = households * members
    membership = np.repeat(np.arange(households), members)
    row = {"person": {"age": np.full(n, 80), "state_pension_type": np.full(n, 1), "additional_state_pension": np.zeros(n),
                      "basic_state_pension": np.ones(n), "new_state_pension": np.zeros(n), "state_pension": np.ones(n),
                      "person_weight": np.ones(n), "is_household_head": np.zeros(n, bool)},
           "household": {"household_weight": np.ones(households), "basic_state_pension": np.full(households, members, dtype=float)},
           "normalised_person": {"basic_state_pension": np.ones(n), "new_state_pension": np.zeros(n), "additional_state_pension": np.zeros(n)},
           "normalised_household": {"basic_state_pension": np.full(households, members, dtype=float), "new_state_pension": np.zeros(households), "additional_state_pension": np.zeros(households)},
           "age_cell": np.zeros(n, int), "country": np.full(n, "England"), "region": np.full(n, "London")}
    data = {mode: {year: copy.deepcopy(row) for year in (2024, 2025)} for mode in AV.RUN_MODES}
    return data, membership, np.ones(n, bool), np.ones(households, bool)


def test_large_union_cannot_hide_a_small_component_difference():
    data, membership, people, homes = snapshots()
    data["both"][2025]["person"]["age"] += 1
    data["both"][2025]["person"]["additional_state_pension"][:4] = 123456789
    with pytest.raises(AP.PublicationBlocked) as error:
        AP.input_support(data, membership, people, homes)
    assert "123456789" not in str(error.value) and "4" not in str(error.value)


def test_many_people_in_fewer_than_ten_households_still_block_publication():
    data, membership, people, homes = snapshots(households=30, members=5)
    data["types"][2024]["person"]["state_pension_type"][:25] = 2
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_large_northern_ireland_difference_cannot_mask_a_small_gb_difference():
    data, membership, people, homes = snapshots()
    people[10:] = False
    homes[10:] = False
    data["reweight"][2024]["person"]["person_weight"][5:] *= 2
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_zero_differences_and_at_least_ten_on_both_entities_are_publishable():
    data, membership, people, homes = snapshots()
    data["both"][2025]["person"]["basic_state_pension"][:10] *= 2
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["pair_year_checks"] == 20
    assert audit["withheld_families"] == {"age": False, "geography": False}
    assert '"person_weight"' not in str(audit)


def test_small_changes_within_a_large_published_cell_withhold_whole_family():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        for row in mode.values():
            row["country"][10:] = "Wales"
            row["region"][10:] = "Cardiff"
    data["both"][2024]["person"]["basic_state_pension"][5:15] *= 2
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["withheld_families"]["geography"]
    assert not audit["withheld_families"]["age"]


def result(status="available", records=20, mode="legacy"):
    row = {"status": "available", "records": 20, "state_pension_bn": 1}
    table = {"GB": {**row, "status": status, "records": records},
             "by_age": {"80_plus": row.copy()}, "by_country": {"England": row.copy()}, "by_region": {"London": row.copy()}}
    return {"bundle": {"model_version": "2.90.2"}, "data_year": 2024, "dataset": "fixture", "mode": mode,
            "coverage": {policy: {year: copy.deepcopy(table) for year in range(2024, 2040)} for policy in AP.POLICIES}}


def publication_fixture():
    provenance = AP._checkout_provenance()
    plan = {"jobs": [("ageing_path", {"demography": mode}) for mode in AV.RUN_MODES],
            "labels": [["central", mode] for mode in AV.RUN_MODES], "central_only": True,
            "engine_semantics": provenance["engine_semantics"], "validation_semantics": provenance["validation_semantics"],
            "calculation_head": provenance["head"], "calculation_provenance": provenance,
            "fiscal_function_sha256": AP.fiscal_function_sha256(), "source_sha256": "fixture", "packages": {}}
    runs = [result(mode=mode) for mode in AV.RUN_MODES]
    audit = {"passed": True, "fiscal_function_sha256": AP.fiscal_function_sha256(), "plan_sha256": AP.plan_sha256(plan),
             "publication_guard_sha256": AP.engine.file_hash(AP.__file__), "withheld_families": {"age": False, "geography": False},
             "publication_code_sha256": AP._publication_code_hashes(),
             "audit_engine_semantics": provenance["engine_semantics"], "audit_validation_semantics": provenance["validation_semantics"],
             "years": list(range(2024, 2040)), "data_year": 2024, "model_version": "2.90.2", "bundle": runs[0]["bundle"],
             "dataset": "fixture", "calculation_head": plan["calculation_head"], "calibration_anchor": None,
             "calculation_provenance": {**provenance, "plan_sha256": AP.plan_sha256(plan), "fiscal_function_sha256": plan["fiscal_function_sha256"]},
             "pension_formula_sha256": AP.READ_PENSION_FORMULAS.copy(), "pair_year_checks": 160, "consecutive_year_checks": 75,
             "all_year_pair_checks": 600, "treatment_contrast_year_checks": 1200,
             "exact_statistic_comparison_checks": 1960, "direct_mixed_treatment_year_pairs_checked": False,
             "calculation_source_head_verification": AP._head_source_verification(plan),
             "minimum_contributing_records": 10, "macro_path_support_proof": {"paths_checked": 1, "identical_state_pension_age_changes": True,
                "data_year_flat_rate_ceilings_unchanged": True, "positive_common_uprating_multipliers": True}}
    for flag in ("person_and_household_support_checked", "field_component_and_union_support_checked", "consecutive_year_support_checked",
                 "pension_recipient_and_type_changes_checked", "age_cell_changes_checked", "weights_beyond_common_factor_checked", "pinned_keys_checked",
                 "all_year_pairs_support_checked", "treatment_contrast_year_support_checked"):
        audit[flag] = True
    for flag in ("exact_published_cell_support_checked", "recipient_weighted_count_support_checked", "normalised_weighted_monetary_support_checked"):
        audit[flag] = True
    return plan, runs, audit


def test_suppressed_gb_coverage_cannot_be_bypassed_by_another_spending_table():
    plan, runs, audit = publication_fixture()
    runs[0] = result("suppressed", None)
    with pytest.raises(AP.PublicationBlocked, match="GB coverage"):
        AP.guard_results(plan, runs, audit)


def test_guard_withholds_linked_family_before_summary_can_emit_any_table():
    plan, runs, audit = publication_fixture()
    audit["withheld_families"]["age"] = True
    AP.guard_results(plan, runs, audit)
    for run in runs:
        table = run["coverage"]["triple_lock"][2024]
        assert table["by_age"]["80_plus"] == {"status": "withheld_family", "records": None, "state_pension_bn": None}
        assert table["GB"]["state_pension_bn"] == table["by_country"]["England"]["state_pension_bn"] == 1


@pytest.mark.parametrize("field,value", [
    ("fiscal_function_sha256", "old"), ("plan_sha256", "old"), ("publication_guard_sha256", "old"), ("publication_code_sha256", {}),
    ("audit_engine_semantics", {}), ("audit_validation_semantics", {}), ("years", [2024]), ("data_year", 2025),
    ("model_version", "2.118.0"), ("bundle", {}), ("pension_formula_sha256", {}), ("pair_year_checks", 150),
    ("consecutive_year_checks", 70), ("minimum_contributing_records", 9), ("macro_path_support_proof", {}),
    ("pinned_keys_checked", False), ("consecutive_year_support_checked", False),
    ("pension_recipient_and_type_changes_checked", False), ("age_cell_changes_checked", False),
    ("weights_beyond_common_factor_checked", False),
    ("all_year_pairs_support_checked", False), ("all_year_pair_checks", 599),
    ("treatment_contrast_year_support_checked", False), ("treatment_contrast_year_checks", 1199),
    ("calculation_source_head_verification", {}),
    ("exact_published_cell_support_checked", False), ("recipient_weighted_count_support_checked", False),
    ("normalised_weighted_monetary_support_checked", False), ("exact_statistic_comparison_checks", 1959),
    ("direct_mixed_treatment_year_pairs_checked", True),
])
def test_missing_or_stale_audit_binding_blocks_publication(field, value):
    plan, runs, audit = publication_fixture()
    audit[field] = value
    with pytest.raises(AP.PublicationBlocked):
        AP.guard_results(plan, runs, audit)


def test_macro_reuse_proof_accepts_negative_cpi_floor_but_rejects_nonfinite_or_age_changes(monkeypatch):
    cap = SimpleNamespace(amount=lambda year: 1)
    parameters = SimpleNamespace(gov=SimpleNamespace(dwp=SimpleNamespace(
        state_pension=SimpleNamespace(basic_state_pension=cap, new_state_pension=cap))))
    monkeypatch.setattr(AP.engine, "base_levels", lambda parameters: {"basic_state_pension": 1, "new_state_pension": 2})
    monkeypatch.setattr(AP.engine, "scenario_changes", lambda spec, parameters: spec["changes"])
    monkeypatch.setattr(AP.engine, "september_cpi", lambda spec: {year: spec["cpi"] for year in range(2024, 2040)})
    monkeypatch.setattr(AP.engine, "spec_rates", lambda spec: (None, None, {
        policy: {year: .025 for year in AP.HORIZON} for policy in AP.POLICIES}))
    spec = {"demography_calibration_year": 2024, "changes": copy.deepcopy(AP.STATE_PENSION_AGE_CHANGES), "cpi": -2}
    plan = {"labels": [("central", "both"), ("draw_1", "both")],
            "jobs": [("ageing_path", spec), ("ageing_path", copy.deepcopy(spec))], "calibration_year": 2024}
    proof = AP._path_proof(plan, parameters, 2024, range(2024, 2040))
    assert proof["paths_checked"] == 2 and proof["positive_common_uprating_multipliers"]
    plan["jobs"][1][1]["cpi"] = np.nan
    with pytest.raises(AP.PublicationBlocked, match="finite and positive"):
        AP._path_proof(plan, parameters, 2024, range(2024, 2040))


    plan["jobs"][1][1]["cpi"] = .02
    plan["jobs"][1][1]["changes"]["gov.dwp.state_pension.basic_state_pension.amount"] = {"year:2024-01-01:1": 2}
    with pytest.raises(AP.PublicationBlocked, match="data-year ceilings"):
        AP._path_proof(plan, parameters, 2024, range(2024, 2040))


def test_adjacent_year_type_change_is_protected_even_when_treatments_agree():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        mode[2025]["person"]["state_pension_type"][:4] = 2
    with pytest.raises(AP.PublicationBlocked, match="year difference"):
        AP.input_support(data, membership, people, homes)


def test_common_weight_growth_and_component_uprating_do_not_create_false_support():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        mode[2025]["person"]["person_weight"] *= 1.0072
        mode[2025]["household"]["household_weight"] *= 1.0072
        mode[2025]["person"]["basic_state_pension"] *= 1.05
    audit = AP.input_support(data, membership, people, homes)
    assert audit["consecutive_year_support_checked"] and audit["consecutive_year_checks"] == 5


def test_common_weight_factor_cannot_mask_five_distorted_households():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        mode[2025]["person"]["person_weight"] *= 1.0072
        mode[2025]["household"]["household_weight"] *= 1.0072
        mode[2025]["person"]["person_weight"][:5] *= 1.1
        mode[2025]["household"]["household_weight"][:5] *= 1.1
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_age_cell_household_support_comes_only_from_changed_members_in_the_cell():
    data, membership, people, homes = snapshots(households=40, members=10)
    a_cell = (membership < 5) | (np.arange(len(membership)) % 10 == 0)
    changed = (membership < 5) | (np.arange(len(membership)) % 10 == 1)
    for mode in data.values():
        for row in mode.values():
            row["age_cell"] = np.where(a_cell, 0, 5)
            row["person"]["age"] = np.where(a_cell, 55, 85)
    for row in data["both"].values():
        row["person"]["basic_state_pension"][changed] *= 2
        row["normalised_person"]["basic_state_pension"][changed] *= 2
        row["household"]["basic_state_pension"] += np.bincount(membership, weights=changed)
        row["normalised_household"]["basic_state_pension"] = row["household"]["basic_state_pension"].copy()
    assert AP.input_support(data, membership, people, homes)["withheld_families"]["age"]


def test_record_moving_between_age_cells_requires_support_in_both_cells():
    data, membership, people, homes = snapshots()
    for row in data["both"].values():
        row["person"]["age"][:10] += 5
        row["age_cell"][:5] = 1
        row["age_cell"][5:10] = 2
    assert AP.input_support(data, membership, people, homes)["withheld_families"]["age"]


def test_unrecognised_pinned_input_cannot_be_silently_omitted():
    with pytest.raises(AP.PublicationBlocked, match="every pinned input"):
        AP._assert_audited_pins(None, {"new_eligibility_input": {}}, [], AP.INPUTS)


def test_full_managed_bundle_metadata_is_reduced_to_the_fiscal_job_contract():
    public = {"bundle_id": "uk-5.3.0", "policyengine_version": "5.3.0", "model_version": "2.90.2",
              "runtime_dataset": "enhanced_frs_2024_25", "certified_data_build_id": "policyengine-uk-data-1.56.16"}
    full = {**public, "installed_packages": {"extra": "1"}, "dataset_local_path": "/private/data.h5"}
    assert AP.canonical_bundle(full) == public


def test_managed_loading_is_confined_to_cache_and_restores_working_directory(monkeypatch, tmp_path):
    from pathlib import Path
    plan, _, _ = publication_fixture()
    provenance = AP._checkout_provenance()
    verified = AP._head_source_verification(plan)
    monkeypatch.setattr(AP, "_checkout_provenance", lambda: provenance)
    monkeypatch.setattr(AP, "_head_source_verification", lambda plan: verified)
    monkeypatch.setattr(AP, "REPO", tmp_path)
    previous = Path.cwd()
    def collect(plan):
        assert Path.cwd() == tmp_path / ".cache" / "ageing-publication-model"
        return {"passed": True}
    monkeypatch.setattr(AP, "_collect_input_support", collect)
    assert AP.collect_input_support(plan)["passed"] and Path.cwd() == previous


def execution_metadata(plan):
    return {"calculation_head": plan["calculation_head"], "calculation_provenance": plan["calculation_provenance"],
            "provenance": {"engine_semantics": plan["engine_semantics"], "validation_semantics": plan["validation_semantics"]},
            "source_results_sha256": plan["source_sha256"], "calibration_anchor": plan.get("calibration_anchor"),
            "worker_execution": {"enhanced_frs_workers": 8, "microcosm_workers": 0}, "host_before_runs": {"logical_cpus": 18}}


def test_missing_cache_never_loads_managed_model_or_writes_output(monkeypatch, tmp_path):
    plan, _, _ = publication_fixture()
    monkeypatch.setattr(AP.engine, "cached", lambda *args, **kwargs: None)
    monkeypatch.setattr(AP, "collect_input_support", lambda *args: pytest.fail("missing cached fiscal jobs must not start a model"))
    output = tmp_path / "output.json"
    with pytest.raises(AP.PublicationBlocked, match="completed full-model"):
        AP.publish_cached(plan, output, execution_metadata=execution_metadata(plan), execution_log="private.log", integration_files=("first.json", "second.json"), execution_driver="driver.py")
    assert not output.exists()


def test_saved_json_labels_publish_with_exact_original_execution_metadata(monkeypatch, tmp_path):
    plan, runs, audit = publication_fixture()
    cached = iter(runs)
    monkeypatch.setattr(AP.engine, "cached", lambda *args, **kwargs: next(cached))
    monkeypatch.setattr(AP.AV, "summarise", lambda plan, runs: {"provenance": {"engine_semantics": plan["engine_semantics"]}})
    verified = AP._head_source_verification(plan)
    monkeypatch.setattr(AP, "_head_source_verification", lambda plan: verified)
    monkeypatch.setattr(AP, "REPO", tmp_path)
    published = {**plan["calculation_provenance"], "head": "a" * 40}
    monkeypatch.setattr(AP, "_checkout_provenance", lambda: published)
    monkeypatch.setattr(AP, "_execution_log_metadata", lambda *args: {"initial_cached_jobs": 0, "planned_jobs": 5, "completed_jobs": 5, "execution_log_sha256": "b" * 64})
    monkeypatch.setattr(AP, "_integration_file_evidence", lambda *args: {"persistent_matches_isolated": True})
    monkeypatch.setattr(AP, "_execution_driver_metadata", lambda *args: {"execution_driver_verified": True})
    output = tmp_path / "output.json"
    report = AP.publish_cached(plan, output, audit, execution_metadata(plan), "private.log", ("first.json", "second.json"), "driver.py")
    assert output.exists() and report["calculation_head"] == plan["calculation_head"]
    assert report["publication_provenance"]["head"] == "a" * 40 != plan["calculation_head"]
    assert report["worker_execution"]["requested_enhanced_frs_workers"] == 8
    assert report["worker_execution"]["requested_microcosm_workers"] == 0
    assert report["plan_sha256"] == audit["plan_sha256"]


def test_mismatched_execution_head_or_worker_counts_cannot_publish():
    plan, _, _ = publication_fixture()
    metadata = execution_metadata(plan)
    metadata["calculation_head"] = "a" * 40
    with pytest.raises(AP.PublicationBlocked, match="execution head"):
        AP._execution_metadata(plan, metadata)

    metadata = execution_metadata(plan)
    metadata["worker_execution"]["microcosm_workers"] = 1
    with pytest.raises(AP.PublicationBlocked, match="zero Microcosm"):
        AP._execution_metadata(plan, metadata)


def test_swapped_treatment_payload_is_rejected_despite_complete_years():
    plan, runs, audit = publication_fixture()
    runs[0], runs[1] = runs[1], runs[0]
    with pytest.raises(AP.PublicationBlocked, match="publication jobs differ"):
        AP.guard_results(plan, runs, audit)


def test_one_policy_missing_a_year_is_not_hidden_by_other_years_in_the_union():
    plan, runs, audit = publication_fixture()
    del runs[0]["coverage"]["burnham_2030"][2025]
    with pytest.raises(AP.PublicationBlocked, match="every result year"):
        AP.guard_results(plan, runs, audit)


@pytest.mark.parametrize("categorical", [False, True])
def test_changing_treatment_contrast_cannot_hide_small_overlap_of_large_changes(categorical):
    data, membership, people, homes = snapshots()
    for year, count in ((2024, 20), (2025, 15)):
        row = data["types"][year]
        if categorical:
            row["person"]["state_pension_type"][:count] = 2
        else:
            row["person"]["basic_state_pension"][:count] = 2
            row["normalised_person"]["basic_state_pension"][:count] = 2
            row["household"]["basic_state_pension"][:count] = 2
            row["normalised_household"]["basic_state_pension"][:count] = 2
    for mode in data.values():
        row = mode[2025]
        if categorical:
            row["person"]["state_pension_type"][15:] = 0
        else:
            row["person"]["basic_state_pension"][15:] = 0
            row["normalised_person"]["basic_state_pension"][15:] = 0
            row["household"]["basic_state_pension"][15:] = 0
            row["normalised_household"]["basic_state_pension"][15:] = 0
    # Same-year contrasts have 20/15 contributors; changes within each
    # treatment have 15. Their changing contrast exposes only five.
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_nonadjacent_year_reversal_cannot_leave_five_contributors():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        mode[2026] = copy.deepcopy(mode[2024])
        mode[2025]["person"]["state_pension_type"][:20] = 2
        mode[2026]["person"]["state_pension_type"][:5] = 2
    # Adjacent changes affect twenty and fifteen, but endpoints affect five.
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_normalised_protected_payment_recipient_change_is_audited():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        row = mode[2025]
        row["person"]["additional_state_pension"][:5] = 1
        row["normalised_person"]["additional_state_pension"][:5] = 1
        row["normalised_household"]["additional_state_pension"][:5] = 1
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_changing_contrast_with_small_cell_support_withholds_family():
    data, membership, people, homes = snapshots(households=60)
    for mode in data.values():
        for row in mode.values():
            row["age_cell"][30:] = 1
    for year, count in ((2024, 40), (2025, 30)):
        row = data["types"][year]
        # Twenty vs fifteen affected contributors in each age cell.
        changed = np.r_[np.arange(count // 2), np.arange(30, 30 + count // 2)]
        row["person"]["state_pension_type"][changed] = 2
    for mode in data.values():
        mode[2025]["person"]["state_pension_type"][np.r_[15:30, 45:60]] = 0
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["withheld_families"]["age"]
    assert audit["treatment_contrast_year_checks"] == 10 and audit["all_year_pair_checks"] == 5


def test_calculation_head_verifies_semantics_without_trusting_dirty_flag(monkeypatch):
    plan, _, _ = publication_fixture()
    actual_git = AP._git
    def wrong_tree(*args):
        if args[0] == "show" and args[1].endswith(":src/triple_lock/config.py"):
            return b"CHANGED_CALCULATION = True\n"
        return actual_git(*args)
    monkeypatch.setattr(AP, "_git", wrong_tree)
    plan["calculation_provenance"]["dirty"] = False
    with pytest.raises(AP.PublicationBlocked, match="does not match its git head"):
        AP._verify_plan_sources(plan)


@pytest.mark.parametrize("mutation", ["head", "dirty", "engine", "validation", "fiscal"])
def test_saved_source_metadata_is_checked_before_publication(mutation):
    plan, _, _ = publication_fixture()
    if mutation == "head":
        plan["calculation_head"] = "bad"
    elif mutation == "dirty":
        plan["calculation_provenance"]["dirty"] = "false"
    elif mutation in ("engine", "validation"):
        plan[f"{mutation}_semantics"] = {}
    else:
        plan["fiscal_function_sha256"] = "old"
    with pytest.raises(AP.PublicationBlocked):
        AP._verify_plan_sources(plan)


def test_execution_log_counts_are_observed_and_incomplete_logs_are_rejected(monkeypatch, tmp_path):
    import json
    plan, _, _ = publication_fixture()
    monkeypatch.setattr(AP, "REPO", tmp_path)
    path = tmp_path / ".cache" / "execution.log"
    path.parent.mkdir()
    first = {"calculation_head": plan["calculation_head"], "Enhanced_FRS_workers": 8, "Microcosm_workers": 0}
    text = json.dumps(first) + "\n1 of 5 jobs cached; running 4 on 8 workers\n"
    text += "".join(f"ageing_path job done ({i}/4) in 1s\n" for i in range(1, 5))
    text += "Wrote complete private aggregate execution report to private.json\n"
    path.write_text(text)
    evidence = AP._execution_log_metadata(plan, {"requested_enhanced_frs_workers": 8}, path)
    assert evidence["initial_cached_jobs"] == 1 and evidence["completed_jobs"] == 4 and evidence["planned_jobs"] == 5
    path.write_text(text.replace("ageing_path job done (4/4) in 1s\n", ""))
    with pytest.raises(AP.PublicationBlocked, match="incomplete"):
        AP._execution_log_metadata(plan, {"requested_enhanced_frs_workers": 8}, path)


def test_integration_evidence_is_derived_from_original_files_and_binds_source(monkeypatch, tmp_path):
    import hashlib
    import json
    plan, _, _ = publication_fixture()
    plan["calibration_year"] = 2025
    plan["labels"].append(["draw_1", "legacy"])
    first = {"legacy_matches_committed_central": True, "max_legacy_saving_difference_bn": 0,
             "opt_in_engine_run_passed": True, "opt_in_demography": "both", "record_diagnostics_suppressed": True,
             "source_semantics": plan["engine_semantics"], "packages": plan["packages"]}
    second = {"identical": True, "preceding_path": "draw_1", "compared_path": "central", "mode": "both", "calibration_year": 2025,
              "engine_semantics": plan["engine_semantics"], "validation_semantics": plan["validation_semantics"]}
    monkeypatch.setattr(AP, "REPO", tmp_path)
    folder = tmp_path / ".cache"
    folder.mkdir()
    a, b = folder / "integration.json", folder / "equivalence.json"
    a.write_text(json.dumps(first))
    b.write_text(json.dumps(second))
    evidence = AP._integration_file_evidence(plan, a, b)
    assert evidence["persistent_matches_isolated"] and evidence["full_model_verification_jobs"] == 5
    assert evidence["construction_provenance"] == {"preceding_mode": "verified_calculation_source", "full_model_verification_jobs": "by_construction"}
    assert evidence["integration_file_sha256"] == hashlib.sha256(a.read_bytes()).hexdigest()
    second["validation_semantics"] = {}
    b.write_text(json.dumps(second))
    with pytest.raises(AP.PublicationBlocked, match="integration evidence"):
        AP._integration_file_evidence(plan, a, b)


def test_missing_original_log_or_control_files_cannot_produce_an_approved_report(monkeypatch, tmp_path):
    monkeypatch.setattr(AP.engine, "cached", lambda *args, **kwargs: pytest.fail("missing proof must fail before model-cache reads"))
    for log, files, driver in ((None, ("a", "b"), "driver"), ("log", None, "driver"), ("log", ("a",), "driver"), ("log", ("a", "b"), None)):
        with pytest.raises(AP.PublicationBlocked, match="complete private execution log"):
            AP.publish_cached({}, tmp_path / "report.json", execution_log=log, integration_files=files, execution_driver=driver)


def test_nonrecipients_in_other_treatment_cells_cannot_inflate_exact_statistic_support():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        for row in mode.values():
            for name in ("basic_state_pension", "state_pension"):
                row["person"][name][:10] = 0
            row["normalised_person"]["basic_state_pension"][:10] = 0
            row["household"]["basic_state_pension"][:10] = 0
            row["normalised_household"]["basic_state_pension"][:10] = 0
    for row in data["both"].values():
        row["age_cell"][:10] = 1
        row["person"]["age"][:10] = 85
        for name in ("basic_state_pension", "state_pension"):
            row["person"][name][:10] = 1
            row["person"][name][10:15] = 2
        row["normalised_person"]["basic_state_pension"][:10] = 1
        row["normalised_person"]["basic_state_pension"][10:15] = 2
        row["household"]["basic_state_pension"][:10] = 1
        row["household"]["basic_state_pension"][10:15] = 2
        row["normalised_household"]["basic_state_pension"] = row["household"]["basic_state_pension"].copy()
    # Global masks have fifteen contributors. Ten enter the other cell, where
    # they cannot inflate the five true monetary contributors in this cell.
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["withheld_families"]["age"]
    assert audit["exact_statistic_comparison_checks"] == 35
    assert audit["consecutive_year_checks"] == 5


@pytest.mark.parametrize("weighted", [False, True])
def test_four_snapshot_contributors_apply_each_snapshot_cell_before_subtraction(weighted):
    values = [np.zeros(30), np.ones(30), np.zeros(30), np.full(30, 2.0)]
    values[0][10:15] = values[1][10:15] = values[2][10:15] = 1
    indicators = [np.ones(30, bool), np.r_[np.zeros(10, bool), np.ones(20, bool)],
                  np.ones(30, bool), np.r_[np.zeros(10, bool), np.ones(20, bool)]]
    # The ten changing values excluded from B's cell contribute zero. Only
    # the five changing recipient or monetary entries inside the cell count.
    for index in (1, 3):
        values[index][15:] = 0
    vectors = [{"statistic": (value, weighted)} for value in values]
    mask, = AP._published_statistic_masks(vectors, indicators, (1, 1, 1, 1))
    assert int(mask.sum()) == 5


def test_published_recipient_support_excludes_zero_amount_weight_changes():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        for row in mode.values():
            for name in ("basic_state_pension", "state_pension"):
                row["person"][name][5:15] = 0
            row["normalised_person"]["basic_state_pension"][5:15] = 0
            row["household"]["basic_state_pension"][5:15] = 0
            row["normalised_household"]["basic_state_pension"][5:15] = 0
    for row in data["both"].values():
        row["person"]["person_weight"][:15] *= 2
        row["household"]["household_weight"][:15] *= 2
    # The old weight mask has fifteen members; only five receive pensions.
    with pytest.raises(AP.PublicationBlocked):
        AP.input_support(data, membership, people, homes)


def test_execution_driver_hash_is_measured_and_cannot_be_self_declared(monkeypatch, tmp_path):
    import hashlib
    monkeypatch.setattr(AP, "REPO", tmp_path)
    path = tmp_path / ".cache" / "driver.py"
    path.parent.mkdir()
    path.write_text("original_driver = True\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert AP._execution_driver_metadata({"execution_driver_sha256": digest}, path) == {
        "execution_driver_sha256": digest, "execution_driver_verified": True}
    path.write_text("modified_driver = True\n")
    with pytest.raises(AP.PublicationBlocked, match="saved producer hash"):
        AP._execution_driver_metadata({"execution_driver_sha256": digest}, path)
