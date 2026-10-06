"""Portable checks for the published original-path GC/HB diagnostic."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "data/pilot/gc_precision_diagnostic.json"


@pytest.fixture(scope="module")
def receipt():
    return json.loads(RECEIPT.read_text())


def test_gc_diagnostic_is_bound_to_the_public_recipe_inputs_and_original_path(receipt):
    assert receipt["audit_script_sha256"] == hashlib.sha256(
        (ROOT / "scripts/diagnose_model_v2_gc_precision.py").read_bytes()
    ).hexdigest()
    for relative, expected in receipt["input_files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    fiscal = json.loads((ROOT / "data/pilot/model_v2_e.json").read_text())
    assert receipt["engine_semantics"] == fiscal["provenance"]["engine_semantics"]
    assert receipt["packages"] == fiscal["provenance"]["packages"]
    audit = json.loads((ROOT / "data/pilot/full_new_net_se_audit.json").read_text())
    original = next(row for row in audit["cache_receipts"]
                    if row["path"] == f"draw_{receipt['path_index']}")
    assert receipt["original_batch_cache_key"] == original["cache_key"]
    assert receipt["original_cache_record_sha256"] == original["aggregate_cache_sha256"]
    package = Path(importlib.metadata.distribution("policyengine-uk").locate_file("policyengine_uk"))
    assert len(receipt["policyengine_formula_source_sha256"]) == 11
    for relative, expected in receipt["policyengine_formula_source_sha256"].items():
        assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == expected


def test_gc_diagnostic_replays_the_full_original_horizon_and_published_endpoints(receipt):
    assert receipt["full_path_count"] == 1
    assert receipt["fiscal_years_calculated"] == list(range(2027, 2040))
    assert set(receipt["saving_replay"]) == {"2034", "2039"}
    validated = json.loads((ROOT / "data/pilot/full_new_net_se_diagnostic_validated.json").read_text())
    original = next(run for run in validated["runs"] if run["treatment"] == receipt["treatment"])
    assert receipt["path_index"] == validated["path_index"]
    assert receipt["replay_absolute_tolerance_bn"] == .001
    for year, replay in receipt["saving_replay"].items():
        assert replay["replay_within_absolute_tolerance"] is True
        for measure in ("gross", "net"):
            cell = replay[measure]
            if replay["numeric_family_status"] == "available":
                assert cell["cached_bn"] == original["saving_replay"][year][measure]["cached_bn"]
                assert cell["replay_bn"] == pytest.approx(cell["cached_bn"], abs=.001, rel=0)
                assert cell["difference_bn"] == pytest.approx(
                    cell["replay_bn"] - cell["cached_bn"], abs=1e-12, rel=0)
            else:
                assert all(value is None for value in cell.values())
    assert len(receipt["admissions"]) >= 3
    for admission in receipt["admissions"]:
        assert admission["available_gib"] >= 40
        assert admission["vm_stat_available_gib"] >= 40
        assert admission["maximum_precision_workers"] == 1
        assert admission["precision_workers"] == 1
        assert admission["task_registered_diagnostic_workers"] <= 2
        assert set(admission["checked_registry_paths"]) == {
            ".cache/full_new_net_se_diagnostic_validated.pid.json",
            ".cache/h-item4-gc-precision.pid.json",
        }


def test_gc_diagnostic_publishes_supported_counts_and_linked_money_only(receipt):
    assert receipt["minimum_records"] == 10
    assert "/Users/" not in RECEIPT.read_text()

    def walk(value, count_family=False):
        if isinstance(value, dict):
            assert not set(value).intersection({"person_id", "household_id", "weights", "amounts_gbp"})
            if value.get("status") == "withheld_linked_family":
                assert value["support_records"] is None
                assert value["support_complement_records"] is None
                assert all(value[key] is None for key in ("triple_lock_bn", "burnham_2030_bn", "change_bn"))
            if value.get("status") == "available" and "support_records" in value:
                for policy, support in value["support_records"].items():
                    amount = value[f"{policy}_bn"]
                    if amount != 0:
                        assert support >= 10
            for key, child in value.items():
                walk(child, count_family or key == "records" or key.endswith("_records"))
        elif isinstance(value, list):
            for child in value:
                walk(child, count_family)
        elif count_family and isinstance(value, int) and not isinstance(value, bool):
            assert value == 0 or value >= 10

    walk(receipt)
    for diagnostic in receipt["diagnostics"].values():
        for table in (value for value in diagnostic.values()
                      if isinstance(value, dict) and "groups" in value):
            if table["count_family_status"] == "withheld_linked_family":
                assert table["records"] is None
                assert all(group["records"] is None and group["complement_records"] is None
                           for group in table["groups"].values())
            else:
                assert sum(group["records"] for group in table["groups"].values()) == table["records"]
            for variable, total in table["total_components"].items():
                cells = [group["components"][variable] for group in table["groups"].values()]
                if total["status"] == "withheld_linked_family":
                    assert all(cell["status"] == "withheld_linked_family" for cell in cells)
                else:
                    assert all(cell["status"] == "available" for cell in cells)
                    for key in total:
                        if key.endswith("_bn"):
                            assert sum(cell[key] for cell in cells) == pytest.approx(total[key], abs=1e-8, rel=0)
