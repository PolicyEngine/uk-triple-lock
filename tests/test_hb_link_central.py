"""The published HB sensitivity contains only supported UK fiscal aggregates."""

import json
import math
from pathlib import Path

import pytest


def test_committed_central_result_is_an_aggregate_only_available_family():
    root = Path(__file__).resolve().parents[1]
    result = json.loads((root / "data/diagnostics/hb_link_central.json").read_text())
    assert set(result) == {"status", "disclosure_status", "geography", "path", "method", "unit",
                           "bundle_version", "model_version", "dataset_version", "uk_saving_bn"}
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
    assert rows["2039"]["net"]["linked_minus_current"] == pytest.approx(0.0013907970021625603)
    assert max(rows, key=lambda year: rows[year]["net"]["linked_minus_current"]) == "2037"
