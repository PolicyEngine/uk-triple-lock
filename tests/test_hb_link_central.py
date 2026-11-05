"""The published HB and Savings Credit sensitivities contain only supported UK fiscal aggregates."""

import json
import math
from pathlib import Path

import pytest


@pytest.mark.parametrize("filename,method,final_delta,peak_year", [
    ("hb_link_central.json", "HB component convention", 0.0013907970021625603, "2037"),
    ("sc_threshold_central.json", "Savings Credit maximum convention", -0.007016908492634394, "2039"),
])
def test_committed_central_result_is_an_aggregate_only_available_family(filename, method, final_delta, peak_year):
    root = Path(__file__).resolve().parents[1]
    result = json.loads((root / "data/diagnostics" / filename).read_text())
    assert set(result) == {"status", "disclosure_status", "geography", "path", "method", "unit",
                           "bundle_version", "model_version", "dataset_version", "uk_saving_bn"}
    assert result["method"] == method
    assert result["status"] == "completed"
    assert result["disclosure_status"] == "available"
    assert result["geography"] == "UK" and result["path"] == "central"
    assert result["unit"] == "GBP billion"
    assert (result["bundle_version"], result["model_version"], result["dataset_version"]) == (
        "6.2.6", "2.125.1", "1.58.0")
    rows = result["uk_saving_bn"]
    assert set(rows) == {str(year) for year in range(2027, 2040)}
    for measures in rows.values():
        assert set(measures) == {"gross", "net"}
        for cells in measures.values():
            assert set(cells) == {"current", "linked", "linked_minus_current"}
            assert all(type(value) in (int, float) and math.isfinite(value) for value in cells.values())
            assert cells["linked_minus_current"] == pytest.approx(cells["linked"] - cells["current"], abs=1e-12)
        assert measures["gross"]["linked_minus_current"] == 0
    assert rows["2039"]["net"]["linked_minus_current"] == pytest.approx(final_delta)
    assert max(rows, key=lambda year: abs(rows[year]["net"]["linked_minus_current"])) == peak_year


def test_sensitivities_share_the_same_current_method_baseline():
    root = Path(__file__).resolve().parents[1] / "data/diagnostics"
    hb, sc = [json.loads((root / filename).read_text())["uk_saving_bn"]
              for filename in ("hb_link_central.json", "sc_threshold_central.json")]
    for year in hb:
        for measure in ("gross", "net"):
            assert hb[year][measure]["current"] == sc[year][measure]["current"]
