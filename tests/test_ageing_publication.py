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
             "audit_engine_semantics": provenance["engine_semantics"], "audit_validation_semantics": provenance["validation_semantics"],
             "years": list(range(2024, 2040)), "data_year": 2024, "model_version": "2.90.2", "bundle": runs[0]["bundle"],
             "dataset": "fixture", "calculation_head": plan["calculation_head"], "calibration_anchor": None,
             "calculation_provenance": {**provenance, "plan_sha256": AP.plan_sha256(plan), "fiscal_function_sha256": plan["fiscal_function_sha256"]},
             "pension_formula_sha256": AP.READ_PENSION_FORMULAS.copy(), "pair_year_checks": 160, "consecutive_year_checks": 75,
             "minimum_contributing_records": 10, "macro_path_support_proof": {"paths_checked": 1, "identical_state_pension_age_changes": True,
                "data_year_flat_rate_ceilings_unchanged": True, "positive_common_uprating_multipliers": True}}
    for flag in ("person_and_household_support_checked", "field_component_and_union_support_checked", "consecutive_year_support_checked",
                 "pension_recipient_and_type_changes_checked", "age_cell_changes_checked", "weights_beyond_common_factor_checked", "pinned_keys_checked"):
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
    ("fiscal_function_sha256", "old"), ("plan_sha256", "old"), ("publication_guard_sha256", "old"),
    ("audit_engine_semantics", {}), ("audit_validation_semantics", {}), ("years", [2024]), ("data_year", 2025),
    ("model_version", "2.118.0"), ("bundle", {}), ("pension_formula_sha256", {}), ("pair_year_checks", 150),
    ("consecutive_year_checks", 70), ("minimum_contributing_records", 9), ("macro_path_support_proof", {}),
    ("pinned_keys_checked", False), ("consecutive_year_support_checked", False),
    ("pension_recipient_and_type_changes_checked", False), ("age_cell_changes_checked", False),
    ("weights_beyond_common_factor_checked", False),
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
    monkeypatch.setattr(AP, "_checkout_provenance", lambda: provenance)
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
        AP.publish_cached(plan, output, execution_metadata=execution_metadata(plan))
    assert not output.exists()


def test_saved_json_labels_publish_with_exact_original_execution_metadata(monkeypatch, tmp_path):
    plan, runs, audit = publication_fixture()
    cached = iter(runs)
    monkeypatch.setattr(AP.engine, "cached", lambda *args, **kwargs: next(cached))
    monkeypatch.setattr(AP.AV, "summarise", lambda plan, runs: {"provenance": {"engine_semantics": plan["engine_semantics"]}})
    monkeypatch.setattr(AP, "REPO", tmp_path)
    monkeypatch.setattr(AP, "_checkout_provenance", lambda: plan["calculation_provenance"])
    output = tmp_path / "output.json"
    report = AP.publish_cached(plan, output, audit, execution_metadata(plan))
    assert output.exists() and report["calculation_head"] == plan["calculation_head"]
    assert report["publication_provenance"]["head"] == plan["calculation_head"]
    assert report["worker_execution"] == {"enhanced_frs_workers": 8, "microcosm_workers": 0}
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
