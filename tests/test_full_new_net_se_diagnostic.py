"""Validate the published full-run diagnostic without private caches or data."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "data/pilot/full_new_net_se_diagnostic_validated.json"


@pytest.fixture(scope="module")
def receipt():
    return json.loads(RECEIPT.read_text())


def test_diagnostic_binds_its_public_inputs_recipe_and_original_path(receipt):
    # The publication-only map rename preserves the frozen run receipt bytes.
    raw = RECEIPT.read_bytes()
    original = raw.split(b',\n  "publication_schema":', 1)[0].replace(
        b'"aggregate_components":', b'"components_bn":'
    ) + b'}\n'
    assert hashlib.sha256(original).hexdigest() == receipt["publication_schema"]["original_receipt_sha256"]
    assert receipt["audit_script_sha256"] == hashlib.sha256(
        (ROOT / "scripts/diagnose_model_v2_full_new_housing_benefit.py").read_bytes()
    ).hexdigest()
    assert set(receipt["input_files_sha256"]) == {
        "data/pilot/d_macro_specs.json", "data/pilot/model_v2_e.json"
    }
    for relative, expected in receipt["input_files_sha256"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected
    audit = json.loads((ROOT / "data/pilot/full_new_net_se_audit.json").read_text())
    matches = [row for row in audit["cache_receipts"]
               if row["path"] == f"draw_{receipt['path_index']}"]
    assert len(matches) == 1
    assert receipt["original_batch_cache_key"] == matches[0]["cache_key"]
    fiscal = json.loads((ROOT / "data/pilot/model_v2_e.json").read_text())
    assert receipt["engine_semantics"] == fiscal["provenance"]["engine_semantics"]
    assert receipt["packages"] == fiscal["provenance"]["packages"]
    package = Path(importlib.metadata.distribution("policyengine-uk").locate_file("policyengine_uk"))
    assert len(receipt["policyengine_formula_source_sha256"]) == 7
    for relative, expected in receipt["policyengine_formula_source_sha256"].items():
        assert hashlib.sha256((package / relative).read_bytes()).hexdigest() == expected
    assert receipt["admission"]["maximum_workers"] == 1
    assert receipt["admission"]["available_gib"] >= 40
    assert receipt["admission"]["vm_stat_available_gib"] >= 40


def test_full_diagnostic_replays_the_original_public_endpoint_aggregates(receipt):
    audit = json.loads((ROOT / "data/pilot/full_new_net_se_audit.json").read_text())
    paths = {row["year"]: row for row in audit["paths"]
             if row["macro_path_index"] == receipt["path_index"]}
    assert set(paths) == {2034, 2039}
    runs = {run["treatment"]: run for run in receipt["runs"]}
    assert set(runs) == {"both", "both_full_new"}
    for treatment, run in runs.items():
        assert run["full_horizon"] == list(range(2027, 2040))
        assert set(run["saving_replay"]) == {"2034", "2039"}
        column = "kept_bn" if treatment == "both" else "full_new_bn"
        for year, comparisons in run["saving_replay"].items():
            for measure in ("gross", "net"):
                row = comparisons[measure]
                assert row["cached_bn"] == paths[int(year)][column][measure]
                assert row["replay_bn"] == pytest.approx(row["cached_bn"], abs=.001, rel=0)
                assert row["difference_bn"] == pytest.approx(
                    row["replay_bn"] - row["cached_bn"], abs=1e-12, rel=0
                )


def test_diagnostic_publishes_only_supported_linked_aggregate_families(receipt):
    assert receipt["minimum_records"] == 10
    raw = RECEIPT.read_text()
    assert "/Users/" not in raw

    def check_keys(value):
        if isinstance(value, dict):
            assert not set(value).intersection({"person_id", "household_id", "weights", "amounts_gbp"})
            for child in value.values():
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)

    def check_aggregate(group):
        count = group["records"]
        assert count is None or count == 0 or count >= 10
        if group["status"] == "withheld_family":
            assert count is None
            return
        for cell in group["aggregate_components"].values():
            if cell.get("status") == "withheld_family":
                assert cell["support_records"] is None
                assert all(cell[key] is None for key in ("triple_lock", "burnham_2030", "change"))
                continue
            for key in ("triple_lock", "burnham_2030", "change"):
                support = cell["support_records"][key]
                assert support == 0 or support >= 10
                if cell[key] != 0:
                    assert support >= 10
            assert cell["change"] == pytest.approx(
                cell["burnham_2030"] - cell["triple_lock"], abs=1e-8, rel=0
            )

    check_keys(receipt)
    for run in receipt["runs"]:
        assert set(run["housing_benefit_passport_groups"]) == {"2034", "2039"}
        for diagnostic in run["housing_benefit_passport_groups"].values():
            national = diagnostic["national_components"]
            check_aggregate(national)
            groups = diagnostic["passport_groups"]
            assert set(groups) == {
                "passport_both", "passport_triple_lock_only", "passport_burnham_only", "passport_neither"
            }
            for group in groups.values():
                check_aggregate(group)
            if any(group["status"] == "withheld_family" for group in groups.values()):
                assert all(group["status"] == "withheld_family" for group in groups.values())
            else:
                assert sum(group["records"] for group in groups.values()) == national["records"]
                for variable, cell in national["aggregate_components"].items():
                    withheld = [group["aggregate_components"][variable].get("status") == "withheld_family"
                                for group in groups.values()]
                    assert not any(withheld) or all(withheld)
                    if not any(withheld) and cell.get("status") != "withheld_family":
                        for key in ("triple_lock", "burnham_2030", "change"):
                            assert sum(group["aggregate_components"][variable][key] for group in groups.values()) == pytest.approx(
                                cell[key], abs=1e-8, rel=0
                            )
            buckets = diagnostic["passport_flip_guarantee_credit_amount_buckets_records"]
            if any(count is None for count in buckets.values()):
                assert all(count is None for count in buckets.values())
            else:
                assert all(count == 0 or count >= 10 for count in buckets.values())
                if all(group["status"] == "available" for group in groups.values()):
                    assert sum(buckets.values()) == (
                        groups["passport_triple_lock_only"]["records"] + groups["passport_burnham_only"]["records"]
                    )
