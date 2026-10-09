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
    # Stopping the per-path national audit was a scope cut, not anyone's ruling.
    assert "ruling" not in audit["scope"] and "Max" not in audit["scope"]
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
        "coverage_gb_dwp": {"coverage"}, "integrated": {"national"},
        "version_bridge": {"coverage", "national"}, "microcosm_central": {"national"},
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
    if "national" in receipts:
        national = receipts["national"]
        assert national["status"] == "passed" and national["complete"] is True
        assert "stopped" in national["per_path_national_audit"]
        assert "No completed paired-path audit is claimed" in national["scope"]
        for text in (national["scope"], national["per_path_national_audit"]):
            assert "ruling" not in text and "Max" not in text
        assert national["independent_full_run_comparison"] == {
            "absolute_tolerance_bn": 0.001, "relative_tolerance": 0, "retained_numbers_changed": False,
        }
        runs = {row["label"]: row for row in national["runs"]}
        assert set(runs) == {"efrs_legacy", "efrs_both", "d_legacy", "d_both"}
        prefix = "d" if name == "microcosm_central" else "efrs"
        for treatment in ("legacy", "both"):
            row = runs[f"{prefix}_{treatment}"]
            assert row["passed"] is True
            assert row["calculation_head"] == (value["treatments"][treatment]["calculation_head"]
                                               if prefix == "d" else value["provenance"]["calculation_head"])
            assert row["dataset_sha256"] == value["provenance"]["dataset_sha256"]
            assert row["calculated_fiscal_years"] == list(range(2027, 2040))
            assert set(row["cells"]) == {"2034", "2039"}
            counts = [count for geographies in row["cells"].values()
                      for cell in geographies.values() for count in cell.values() if count > 0]
            assert row["minimum_observed_positive_cell_contributors"] == min(counts)
            assert min(counts) >= 9977
            for key in ("source_receipt_sha256", "full_spec_sha256"):
                assert re.fullmatch(r"[0-9a-f]{64}", row[key])
        replay = audit["retained_replay_comparison"]
        assert replay["comparison"] == "independent full runs with absolute float tolerance"
        assert replay["absolute_tolerance_bn"] == 0.001 and replay["relative_tolerance"] == 0
        assert replay["retained_numbers_changed"] is False
        assert replay["numeric_differences_published"] is False
        assert replay["all_compared_cells_within_tolerance"] is True
        assert replay["cells"] and all(row["within_tolerance"] is True for row in replay["cells"])


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


def binder():
    return runpy.run_path(str(ROOT / "scripts" / "bind_model_v2_d_support.py"))


def synthetic_national_receipt():
    return {"runs": [{**synthetic_fiscal_run("efrs_legacy"), "label": "efrs_legacy"},
                     {**synthetic_fiscal_run("efrs_both", 10), "label": "efrs_both"}]}


def synthetic_integrated_rows(receipt):
    runs = {row["label"]: row for row in receipt["runs"]}
    return [{"year": year, "geo": geo, "measure": measure,
             **{f"central_2.120.0_{treatment}":
                runs[f"efrs_{treatment}"]["aggregates"]["saving_bn"][str(year)][geo][measure]
                for treatment in ("legacy", "both")}}
            for year in (2034, 2039) for geo in ("uk", "gb") for measure in ("gross", "net")]


@pytest.mark.parametrize("difference,passed", [(0, True), (0.0003, True), (0.000999, True),
                                                (0.001001, False), (1, False), (float("nan"), False)])
def test_integrated_replay_uses_absolute_one_million_tolerance(difference, passed):
    compare = binder()["retained_fiscal_comparison"]
    receipt = synthetic_national_receipt()
    rows = synthetic_integrated_rows(receipt)
    rows[0]["central_2.120.0_legacy"] += difference
    result = compare("integrated", {"rows": rows}, receipt)
    assert result["all_compared_cells_within_tolerance"] is passed
    assert sum(not row["within_tolerance"] for row in result["cells"]) == (0 if passed else 1)
    assert result["absolute_tolerance_bn"] == 0.001 and result["relative_tolerance"] == 0
    assert result["retained_numbers_changed"] is False
    assert result["numeric_differences_published"] is False
    assert all(set(row) == {"year", "geography", "measure", "treatment", "within_tolerance"}
               for row in result["cells"])


def test_independent_full_run_tolerance_never_grows_with_the_fiscal_total():
    compare = binder()["retained_fiscal_comparison"]
    receipt = synthetic_national_receipt()
    rows = synthetic_integrated_rows(receipt)
    receipt["runs"][0]["aggregates"]["saving_bn"]["2034"]["uk"]["gross"] = 1e8
    rows[0]["central_2.120.0_legacy"] = 1e8 + 0.01
    assert compare("integrated", {"rows": rows}, receipt)["all_compared_cells_within_tolerance"] is False


def test_bridge_compares_only_available_central_replays_without_a_paired_audit():
    receipt = synthetic_national_receipt()
    central = receipt["runs"][0]
    rows = [{"figure": f"Central path: {measure} saving {year}-{str(year + 1)[-2:]}",
             "2.120.0": central["aggregates"]["saving_bn"][str(year)]["uk"][measure],
             "2.120.0_1.57.4": -1}
            for year in (2034, 2039) for measure in ("gross", "net")]
    compare = binder()["retained_fiscal_comparison"]
    result = compare("version_bridge", {"rows": rows, "draws": [{"draw": 11}]}, receipt)
    assert result["all_compared_cells_within_tolerance"] is True
    assert len(result["cells"]) == 4
    assert all(row["column"] == "2.120.0" for row in result["cells"])
    assert "without additional replays" in result["scope"]


def test_empty_fiscal_comparison_does_not_pass_vacuously():
    compare = binder()["retained_fiscal_comparison"]
    assert compare("integrated", {"rows": []}, synthetic_national_receipt())["all_compared_cells_within_tolerance"] is False


def test_national_support_rejects_small_positive_cells_and_shortened_runs(tmp_path):
    select = binder()["national_run"]
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    row = {
        "passed": True, "treatment": "legacy", "dataset": "synthetic",
        "calculation_head": "c" * 40,
        "dataset_sha256": "a" * 64, "full_spec_sha256": "b" * 64,
        "calculated_fiscal_years": list(range(2027, 2040)),
        "cells": {str(year): {geo: {"saving": {"gross": 10, "net": 10}}
                              for geo in ("uk", "gb")} for year in (2034, 2039)},
        "aggregates": synthetic_fiscal_run("test")["aggregates"],
    }
    assert select(row, receipt, label="test", head="c" * 40)["minimum_observed_positive_cell_contributors"] == 10
    row["cells"]["2039"]["gb"]["saving"]["net"] = 9
    with pytest.raises(ValueError, match="fewer than ten"):
        select(row, receipt, label="test", head="c" * 40)
    row["cells"]["2039"]["gb"]["saving"]["net"] = 0
    with pytest.raises(ValueError, match="fewer than ten"):
        select(row, receipt, label="test", head="c" * 40)
    row["cells"]["2039"]["gb"]["saving"]["net"] = 10
    row["calculated_fiscal_years"] = [2034, 2039]
    with pytest.raises(ValueError, match="full thirteen-year"):
        select(row, receipt, label="test", head="c" * 40)
