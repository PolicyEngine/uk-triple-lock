"""Committed pilot evidence contains aggregates only, with explicit provenance."""

import copy
import hashlib
import json
import math
import re
import runpy
from pathlib import Path

import pytest

from triple_lock.pipeline import redact_records

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "pilot"
# Matches the record fields forbidden by the approved ageing report, and also
# excludes single-record contributions which the ordinary results allow.
PRIVATE_FIELDS = {
    "id", "ids", "weight", "amount", "amounts",
    "household_id", "household_ids", "person_id", "person_ids", "benunit_id", "benunit_ids",
    "household_weight", "person_weight", "benunit_weight", "weights", "base_weights",
    "record_id", "record_ids", "record_weight", "record_weights", "record_amount", "record_amounts",
    "pinned_inputs", "private_inputs", "largest_household", "concentration_by_year",
    "gross_contribution_bn", "contribution_bn", "income_change_excluding_bn", "share_of_income_change",
}


def assert_aggregate_only(value):
    if isinstance(value, dict):
        assert not PRIVATE_FIELDS.intersection(value), "Pilot contains a record-level field"
        assert not any(isinstance(value.get(key), list) for key in ("age", "ages", "population_records")), \
            "Pilot contains a record-level demographic array"
        if value.get("passed") is True and isinstance(value.get("cells"), dict):
            # Fiscal support receipts store household contributor counts in
            # their cells. A signed aggregate can cancel to zero, so the
            # exception is zero contributors, not merely a zero scalar sum.
            def check_counts(node):
                if isinstance(node, dict):
                    for child in node.values():
                        check_counts(child)
                else:
                    assert isinstance(node, int) and not isinstance(node, bool)
                    assert node == 0 or node >= 10, "Fiscal support cell has fewer than ten contributors"
            check_counts(value["cells"])
        if value.get("status") in ("available", "suppressed", "withheld_family") and "records" in value:
            if value["status"] == "available":
                records = value["records"]
                assert isinstance(records, int) and not isinstance(records, bool) and records >= 0
                # A zero cell can be published; every positive cell needs at
                # least ten contributors. Status/records are metadata.
                amounts = [v for k, v in value.items() if k.endswith(("_bn", "_m"))]
                assert all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in amounts)
                assert not any(amounts) or records >= 10, "Pilot cell has fewer than ten contributors"
            else:
                assert all(v is None for k, v in value.items() if k != "status"), \
                    "Suppressed pilot cell still has data"
        for child in value.values():
            assert_aggregate_only(child)
    elif isinstance(value, list):
        for child in value:
            assert_aggregate_only(child)
    elif isinstance(value, float):
        assert math.isfinite(value), "Pilot contains a nonfinite number"


def test_committed_pilot_files_carry_no_record_level_field():
    files = sorted(PILOT.glob("*.json"))
    assert files, "The 2.120.0 pilot evidence must be committed"
    for file in files:
        value = json.loads(file.read_text())
        assert_aggregate_only(value)
        assert redact_records(copy.deepcopy(value)) == value, f"Record redaction changes {file.name}"


@pytest.mark.parametrize("name", ("version_bridge", "integrated", "coverage_gb_dwp", "microcosm_central"))
def test_original_d_pilot_carries_version_commit_and_uncertified_warning(name):
    value = json.loads((PILOT / f"{name}.json").read_text())
    provenance = value["provenance"]
    assert provenance["policyengine_uk"] == "2.120.0"
    assert provenance["policyengine_core"] == "3.32.16"
    assert provenance["certified"] is False and provenance["quote_eligible"] is False
    assert "not for quoting" in provenance["status"]
    assert provenance["minimum_contributing_records"] == 10
    assert re.fullmatch(r"[0-9a-f]{40}", provenance["calculation_head"])
    for key in ("source_sha256", "dataset_sha256"):
        assert re.fullmatch(r"[0-9a-f]{64}", provenance[key])


def test_microcosm_both_does_not_take_the_earlier_failed_runs_head():
    value = json.loads((PILOT / "microcosm_central.json").read_text())
    assert value["treatments"]["legacy"]["calculation_head"].startswith("498d970")
    assert value["treatments"]["both"]["calculation_head"].startswith("30318c4")


@pytest.mark.parametrize("name", ("version_bridge", "integrated", "coverage_gb_dwp", "microcosm_central"))
def test_original_d_pilot_is_bound_to_a_passed_minimum_cell_support_receipt(name):
    value = json.loads((PILOT / f"{name}.json").read_text())
    audit = value["provenance"]["support_audit"]
    assert audit["status"] == "passed", "Retained D programmes need archived-source support before publication"
    assert audit["minimum_contributing_records"] >= 10
    assert audit["family"] == name, "Receipt binding must name the evidence family"
    receipts = {}
    for binding in audit["receipts"]:
        receipt = (ROOT / binding["receipt"]).resolve()
        assert receipt.is_relative_to(PILOT.resolve()), "Support receipt must be committed in data/pilot"
        assert hashlib.sha256(receipt.read_bytes()).hexdigest() == binding["sha256"]
        content = json.loads(receipt.read_text())
        assert_aggregate_only(content)
        assert binding["role"] not in receipts, "Duplicate receipt role"
        receipts[binding["role"]] = content
    required = {
        "coverage_gb_dwp": {"coverage"}, "integrated": {"fiscal"},
        "version_bridge": {"coverage", "fiscal"}, "microcosm_central": {"microcosm"},
    }[name]
    assert set(receipts) == required, "Receipt does not cover this evidence family"
    if "coverage" in receipts:
        coverage = receipts["coverage"]
        assert coverage["calculation_head"] == value["provenance"]["calculation_head"]
        expected = {("enhanced_frs_2024_25@1.56.16", "both")}
        if name == "version_bridge":
            expected = {("enhanced_frs_2024_25@1.56.16", "legacy"),
                        ("enhanced_frs_2024_25@1.57.4", "legacy")}
        runs = {(r["dataset"], r["treatment"]): r for r in coverage["runs"]}
        assert expected.issubset(runs)
        for key in expected:
            row = runs[key]
            assert row["support_audit"]["passed"] is True
            assert row["support_audit"]["minimum_observed_positive_cell_contributors"] >= 10
            assert set(row["years"]) == {2026, 2027, 2028, 2029, 2030, 2034, 2039}
    if "fiscal" in receipts:
        fiscal = receipts["fiscal"]
        assert fiscal["status"] == "passed" and fiscal["complete"] is True
        assert fiscal["calculation_head"] == value["provenance"]["calculation_head"]
        assert fiscal["fiscal_output_years"] == [2034, 2039]
        assert fiscal["macro_and_input_years"] == list(range(2027, 2040))
        assert fiscal["calibration"]["treatments"]["legacy"]["passed"] is True
        assert fiscal["calibration"]["treatments"]["both"]["passed"] is True
        replay = audit["retained_replay_comparison"]
        assert replay["comparison"] == "exact Python scalar equality"
        assert replay["numeric_differences_published"] is False
        assert replay["cells"] and all(isinstance(row["exact"], bool) for row in replay["cells"])
        reference = PILOT / "d_fiscal_full_central_reference.json"
        assert fiscal["calibration"]["full_output_receipt_sha256"] == hashlib.sha256(reference.read_bytes()).hexdigest()
        expected_specs = json.loads((PILOT / "d_macro_specs.json").read_text())
        paired = {f"draw_{index}" for index in expected_specs["paired"]} | {"central"}
        pairs = {p["label"]: p for p in fiscal["pairs"]}
        assert set(pairs) == paired and len(pairs) == 41
        for pair in pairs.values():
            assert pair["both_minus_legacy_support"]["passed"] is True
            spec = expected_specs["central"] if pair["label"] == "central" else \
                expected_specs["paired"][pair["label"].removeprefix("draw_")]["spec"]
            for treatment in ("legacy", "both"):
                row = pair[treatment]
                assert row["passed"] is True and row["treatment"] == treatment
                assert row["dataset_sha256"] == value["provenance"]["dataset_sha256"]
                assert set(row["cells"]) == {"2034", "2039"}
                assert row["macro_and_input_years"] == list(range(2027, 2040))
                assert row["checks"]["full_fiscal_calculation_years"] == list(range(2027, 2040))
                full_spec = {**spec, "dataset": row["dataset"], "demography": treatment}
                expected_hash = hashlib.sha256(json.dumps(full_spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                assert row["full_spec_sha256"] == expected_hash
        if name == "version_bridge":
            supported = {int(label.removeprefix("draw_")) for label in pairs if label != "central"}
            supported.update(int(row["label"].removeprefix("bridge_draw_"))
                             for row in fiscal["extra_legacy"] if row["label"].startswith("bridge_draw_"))
            assert {row["draw"] for row in value["draws"]}.issubset(supported)
            assert {"newer_central", "obr_premium"}.issubset({r["label"] for r in fiscal["extra_legacy"]})
    if "microcosm" in receipts:
        assert receipts["microcosm"]["complete"] is True, "Bind only the stable complete Microcosm receipt"
        runs = {row["label"]: row for row in receipts["microcosm"]["runs"]}
        for treatment in ("legacy", "both"):
            row = runs[f"d_{treatment}"]
            assert row["passed"] is True
            assert row["calculation_head"] == value["treatments"][treatment]["calculation_head"]
            assert row["dataset_sha256"] == value["provenance"]["dataset_sha256"]
            assert set(row["cells"]) == {str(y) for y in range(2027, 2040)}


@pytest.mark.parametrize("field", sorted(PRIVATE_FIELDS))
def test_pilot_privacy_guard_rejects_nested_record_fields(field):
    with pytest.raises(AssertionError, match="record-level"):
        assert_aggregate_only({"metadata": [{field: None}]})


def test_pilot_privacy_guard_rejects_small_and_incompletely_suppressed_cells():
    with pytest.raises(AssertionError, match="fewer than ten"):
        assert_aggregate_only({"status": "available", "records": 9, "state_pension_bn": 1.0})
    with pytest.raises(AssertionError, match="still has data"):
        assert_aggregate_only({"status": "suppressed", "records": None, "state_pension_bn": 1.0})
    assert_aggregate_only({"status": "available", "records": 0, "state_pension_bn": 0.0})
    with pytest.raises(AssertionError, match="fewer than ten"):
        assert_aggregate_only({"passed": True, "cells": {"2039": {"GB": {"net": 9}}}})


def test_part_b_record_is_explicitly_labelled_as_2_90_2():
    old = json.loads((ROOT / "data" / "ageing_validation.json").read_text())
    assert "policyengine-uk 2.90.2" in old["record_label"]
    assert old["bundle"]["model_version"] == "2.90.2"
    assert "Historical record: policyengine-uk 2.90.2" in (ROOT / "docs" / "AGEING_PILOT_RESULTS.md").read_text()


def synthetic_fiscal_run(label, offset=0):
    return {"label": label, "aggregates": {"saving_bn": {
        str(year): {geo: {measure: float(offset + year + position)
                         for position, measure in enumerate(("gross", "net"))}
                    for geo in ("uk", "gb")}
        for year in (2034, 2039)
    }}}


def test_integrated_replay_flags_identify_a_changed_cell_without_publishing_a_delta():
    compare = runpy.run_path(str(ROOT / "scripts" / "bind_model_v2_d_support.py"))["retained_fiscal_equality"]
    pair = {"label": "central", "legacy": synthetic_fiscal_run("central"),
            "both": synthetic_fiscal_run("central", 10)}
    fiscal = {"pairs": [pair], "extra_legacy": []}
    rows = []
    for year in (2034, 2039):
        for geo in ("uk", "gb"):
            for measure in ("gross", "net"):
                rows.append({"year": year, "geo": geo, "measure": measure,
                             **{f"central_2.120.0_{treatment}": pair[treatment]["aggregates"]["saving_bn"][str(year)][geo][measure]
                                for treatment in ("legacy", "both")}})
    assert compare("integrated", {"rows": rows}, fiscal)["all_compared_cells_exact"] is True
    rows[0]["central_2.120.0_legacy"] += 1
    result = compare("integrated", {"rows": rows}, fiscal)
    assert result["all_compared_cells_exact"] is False
    assert sum(not row["exact"] for row in result["cells"]) == 1
    assert result["numeric_differences_published"] is False
    assert all(set(row) == {"year", "geography", "measure", "treatment", "exact"} for row in result["cells"])


def test_bridge_replay_flags_use_both_paired_and_extra_macro_paths():
    compare = runpy.run_path(str(ROOT / "scripts" / "bind_model_v2_d_support.py"))["retained_fiscal_equality"]
    central, newer = synthetic_fiscal_run("central"), synthetic_fiscal_run("newer_central", 10)
    paired, extra = synthetic_fiscal_run("draw_10", 20), synthetic_fiscal_run("bridge_draw_11", 30)
    fiscal = {"pairs": [{"label": "central", "legacy": central}, {"label": "draw_10", "legacy": paired}],
              "extra_legacy": [newer, extra]}
    rows = [{"figure": f"Central path: {measure} saving {year}-{str(year + 1)[-2:]}",
             "2.120.0": central["aggregates"]["saving_bn"][str(year)]["uk"][measure],
             "2.120.0_1.57.4": newer["aggregates"]["saving_bn"][str(year)]["uk"][measure]}
            for year in (2034, 2039) for measure in ("gross", "net")]
    draws = [{"draw": index, **{f"{measure}_{year}_2.120.0": run["aggregates"]["saving_bn"][str(year)]["uk"][measure]
                               for year in (2034, 2039) for measure in ("gross", "net")}}
             for index, run in ((10, paired), (11, extra))]
    assert compare("version_bridge", {"rows": rows, "draws": draws}, fiscal)["all_compared_cells_exact"] is True
    draws[1]["net_2039_2.120.0"] += 1
    result = compare("version_bridge", {"rows": rows, "draws": draws}, fiscal)
    failures = [row for row in result["cells"] if not row["exact"]]
    assert failures == [{"macro_draw": 11, "year": 2039, "geography": "uk", "measure": "net", "exact": False}]
    assert result["numeric_differences_published"] is False
