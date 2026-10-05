"""Publication must protect component differences and both survey entities."""

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from triple_lock import ageing_publication as AP, ageing_validation as AV


def snapshots(households=30, members=1):
    n = households * members
    membership = np.repeat(np.arange(households), members)
    row = {"person": {"age": np.full(n, 80), "type": np.full(n, 1), "asp": np.zeros(n),
                      "basic": np.ones(n), "weight": np.ones(n), "head": np.zeros(n, bool)},
           "household": {"weight": np.ones(households), "basic": np.full(households, members)},
           "age_cell": np.zeros(n, int), "country": np.full(n, "England"), "region": np.full(n, "London")}
    data = {mode: {year: copy.deepcopy(row) for year in (2024, 2025)} for mode in AV.RUN_MODES}
    return data, membership, np.ones(n, bool), np.ones(households, bool)


def test_large_union_cannot_hide_a_small_component_difference():
    data, membership, people, homes = snapshots()
    data["both"][2025]["person"]["age"] += 1
    data["both"][2025]["person"]["asp"][:4] = 123456789
    with pytest.raises(AP.PublicationBlocked) as error:
        AP.input_support(data, membership, people, homes)
    assert "123456789" not in str(error.value) and "4" not in str(error.value)


def test_many_people_in_fewer_than_ten_households_still_block_publication():
    data, membership, people, homes = snapshots(households=30, members=5)
    data["types"][2024]["person"]["type"][:25] = 2
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_large_northern_ireland_difference_cannot_mask_a_small_gb_difference():
    data, membership, people, homes = snapshots()
    people[10:] = False
    homes[10:] = False
    data["reweight"][2024]["person"]["weight"][5:] *= 2
    with pytest.raises(AP.PublicationBlocked, match="small record support"):
        AP.input_support(data, membership, people, homes)


def test_zero_differences_and_at_least_ten_on_both_entities_are_publishable():
    data, membership, people, homes = snapshots()
    data["both"][2025]["person"]["basic"][:10] *= 2
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["pair_year_checks"] == 20
    assert audit["withheld_families"] == {"age": False, "geography": False}
    assert "weight" not in str(audit)


def test_small_changes_within_a_large_published_cell_withhold_whole_family():
    data, membership, people, homes = snapshots()
    for mode in data.values():
        for row in mode.values():
            row["country"][10:] = "Wales"
            row["region"][10:] = "Cardiff"
    data["both"][2024]["person"]["basic"][5:15] *= 2
    audit = AP.input_support(data, membership, people, homes)
    assert audit["passed"] and audit["withheld_families"]["geography"]
    assert not audit["withheld_families"]["age"]


def result(status="available", records=20):
    row = {"status": "available", "records": 20, "state_pension_bn": 1}
    return {"coverage": {"triple_lock": {2024: {"GB": {**row, "status": status, "records": records},
                                               "by_age": {"80_plus": row.copy()}, "by_country": {"England": row.copy()},
                                               "by_region": {"London": row.copy()}}}}}


def test_suppressed_gb_coverage_cannot_be_bypassed_by_another_spending_table():
    plan = {"jobs": [1, 2]}
    audit = {"passed": True, "fiscal_function_sha256": AP.fiscal_function_sha256(),
             "plan_sha256": AP.plan_sha256(plan), "publication_guard_sha256": AP.engine.file_hash(AP.__file__),
             "withheld_families": {"age": False, "geography": False}}
    with pytest.raises(AP.PublicationBlocked, match="GB coverage"):
        AP.guard_results(plan, [result(), result("suppressed", None)], audit)


def test_guard_withholds_linked_family_before_summary_can_emit_any_table():
    plan = {"jobs": [1, 2]}
    audit = {"passed": True, "fiscal_function_sha256": AP.fiscal_function_sha256(),
             "plan_sha256": AP.plan_sha256(plan), "publication_guard_sha256": AP.engine.file_hash(AP.__file__),
             "withheld_families": {"age": True, "geography": False}}
    runs = [result(), result()]
    AP.guard_results(plan, runs, audit)
    for run in runs:
        table = run["coverage"]["triple_lock"][2024]
        assert table["by_age"]["80_plus"] == {"status": "withheld_family", "records": None, "state_pension_bn": None}
        assert table["GB"]["state_pension_bn"] == table["by_country"]["England"]["state_pension_bn"] == 1


def test_audit_from_a_different_fiscal_function_cannot_publish():
    with pytest.raises(AP.PublicationBlocked, match="another fiscal function"):
        AP.guard_results({"jobs": [1]}, [result()], {"passed": True, "fiscal_function_sha256": "old"})


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
