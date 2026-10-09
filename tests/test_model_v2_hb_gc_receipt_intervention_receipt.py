"""Portable checks for the full-run HB receipt-predicate sensitivity."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "data/pilot/hb_gc_receipt_intervention.json"


@pytest.fixture(scope="module")
def receipt():
    return json.loads(RECEIPT.read_text())


def test_hb_receipt_sensitivity_binds_public_inputs_and_installed_predicates(receipt):
    binding = receipt["binding"]
    for key, relative in (
        ("audit_script_sha256", "scripts/diagnose_model_v2_hb_gc_receipt_intervention.py"),
        ("disclosure_helper_sha256", "scripts/diagnose_model_v2_gc_precision.py"),
    ):
        assert binding[key] == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    for relative, digest in binding["input_files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    fiscal = json.loads((ROOT / "data/pilot/model_v2_e.json").read_text())
    assert binding["engine_semantics"] == fiscal["provenance"]["engine_semantics"]
    assert binding["packages"] == fiscal["provenance"]["packages"]
    audit = json.loads((ROOT / "data/pilot/full_new_net_se_audit.json").read_text())
    original = next(row for row in audit["cache_receipts"]
                    if row["path"] == f"draw_{binding['path_index']}")
    assert binding["original_batch_cache_key"] == original["cache_key"]
    assert binding["original_cache_record_sha256"] == original["aggregate_cache_sha256"]
    package = Path(importlib.metadata.distribution("policyengine-uk").locate_file("policyengine_uk"))
    assert len(binding["installed_formula_source_sha256"]) == 12
    for relative, digest in binding["installed_formula_source_sha256"].items():
        assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == digest
    assert len(binding["intervention_formulas"]) == 3
    for relative, formula in binding["intervention_formulas"].items():
        assert formula["installed_source_sha256"] == binding["installed_formula_source_sha256"][relative]
        assert formula["replaced_predicate_count"] == 1
        assert formula["predicate"] == 'pension_age_regulations & benunit("in_receipt_of_guarantee_credit", period)'
    assert set(receipt["variant_keys"]) == {"original", "receipt_predicate"}
    assert len(set(receipt["variant_keys"].values())) == 2
    for variant, digest in receipt["variant_keys"].items():
        payload = {"kind": "hb_gc_receipt_predicate_sensitivity", "variant": variant, **binding}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(canonical.encode()).hexdigest() == digest


def test_hb_receipt_sensitivity_runs_both_full_paths_and_replays_original_endpoints(receipt):
    assert receipt["full_path_count"] == 2
    assert receipt["independent_policy_calculations"] == 4
    assert receipt["fiscal_years_calculated"] == list(range(2027, 2040))
    assert receipt["original_replay_within_absolute_one_million_pounds"] is True
    assert receipt["binding"]["treatment"] == "both"
    assert receipt["binding"]["path_index"] == 39769
    assert set(receipt["comparisons"]) == {"2034", "2039"}
    validated = json.loads((ROOT / "data/pilot/full_new_net_se_diagnostic_validated.json").read_text())
    original = next(run for run in validated["runs"] if run["treatment"] == "both")
    for year, comparison in receipt["comparisons"].items():
        saving = comparison["saving_comparison"]
        if saving["numeric_family_status"] == "available":
            for measure in ("gross", "net"):
                rows = saving["rows"][measure]
                assert rows["original"]["bn"] == pytest.approx(
                    original["saving_replay"][year][measure]["cached_bn"], abs=.001, rel=0)
                assert rows["effect"]["bn"] == pytest.approx(
                    rows["receipt_predicate"]["bn"] - rows["original"]["bn"], abs=1e-8, rel=0)
    assert len(receipt["admissions"]) == 4
    for admission in receipt["admissions"]:
        assert admission["available_gib"] >= 40
        assert admission["vm_stat_available_gib"] >= 40
        assert admission["own_workers"] == admission["maximum_own_workers"] == 1
        assert admission["task_registered_workers"] <= 2


def test_hb_receipt_sensitivity_publishes_supported_linked_fiscal_effects(receipt):
    assert receipt["minimum_records"] == 10
    assert "/Users/" not in RECEIPT.read_text()
    for comparison in receipt["comparisons"].values():
        for family in comparison.values():
            if family["numeric_family_status"] == "withheld_linked_family":
                assert family["positive_weight_household_records"] is None
                assert all(value is None for stages in family["rows"].values()
                           for cell in stages.values() for value in cell.values())
                continue
            total = family["positive_weight_household_records"]
            assert total >= 10
            for stages in family["rows"].values():
                for cell in stages.values():
                    for key in ("support_records", "support_complement_records"):
                        assert cell[key] == 0 or cell[key] >= 10
                    assert cell["support_records"] + cell["support_complement_records"] == total
                    if cell["bn"] != 0:
                        assert cell["support_records"] >= 10
        family = comparison["housing_benefit_and_other_fiscal_intervention_changes"]
        if family["numeric_family_status"] == "available":
            rows = family["rows"]
            for policy in ("triple_lock", "burnham_2030", "net_saving"):
                assert rows[f"{policy}_gov_balance"]["effect"]["bn"] == pytest.approx(
                    rows[f"{policy}_housing_benefit_gov_balance_component"]["effect"]["bn"]
                    + rows[f"{policy}_other_fiscal_components"]["effect"]["bn"], abs=1e-8, rel=0)
            for component in ("gov_balance", "housing_benefit_gov_balance_component", "other_fiscal_components"):
                assert rows[f"net_saving_{component}"]["effect"]["bn"] == pytest.approx(
                    rows[f"burnham_2030_{component}"]["effect"]["bn"]
                    - rows[f"triple_lock_{component}"]["effect"]["bn"], abs=1e-8, rel=0)
            saving = comparison["saving_comparison"]
            if saving["numeric_family_status"] == "available":
                assert rows["net_saving_gov_balance"]["effect"]["bn"] == pytest.approx(
                    saving["rows"]["net"]["effect"]["bn"], abs=1e-8, rel=0)
