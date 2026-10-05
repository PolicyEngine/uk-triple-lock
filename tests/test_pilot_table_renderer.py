"""The fiscal renderer selects recorded aggregates and preserves disclosure gates."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "pilot_table_renderer", Path(__file__).resolve().parents[1] / "scripts/render_model_v2_e_tables.py"
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.fixture
def aggregates():
    metadata = {"treatment_or_contrast": "both", "year": 2034, "geography": "UK", "measure": "gross", "status": "available"}
    return {
        "provenance": {"calculation_head": "a" * 40, "minimum_contributing_records": 10},
        "fiscal": {
            "central": [{**metadata, "value_bn": 12.345678}],
            "paired": [{**metadata, "estimate_bn": {"mean": 45.678901, "se": 9.8765432,
                                                   "se_path_sampling": 0.000000023456789,
                                                   "se_first_phase": 0.12345678}}],
            "suppression": {"minimum_records": 10, "whole_family_withheld": {"gross": False, "net": False}},
        },
        "historical_part_d": {"calculation_head": "b" * 40, "rows": [
            {"year": 2034, "geo": "uk", "measure": "gross", "central_2.120.0_both": 23.456789,
             "expected_2.120.0_both": {"mean": 34.56789, "se": 8.7654321,
                                     "se_path_sampling": 7.654321, "se_first_phase": 6.54321}},
        ]},
    }


def test_selects_recorded_means_ses_and_contrasts_without_recalculation(aggregates):
    contrast = {"treatment_or_contrast": "combined_effect", "year": 2034, "geography": "UK", "measure": "gross", "status": "available"}
    aggregates["fiscal"]["central"].append({**contrast, "value_bn": 91.234567})
    aggregates["fiscal"]["paired"].append({**contrast, "estimate_bn": {"mean": 82.345678, "se": 73.456789,
                                                                      "se_path_sampling": 64.56789, "se_first_phase": 55.6789}})
    aggregates["private_extra"] = {"record_id": "DO_NOT_RENDER", "weight": 123456789123456789}
    aggregates["fixed_inputs"] = {
        "total": {"model_population_people_by_year": {"2034": 71234567.8912345, "2039": None}},
        "both": {"model_population_people_by_year": {2034: 70123456.7891234, 2039: 72345678.9123456}},
    }
    result = renderer.render(aggregates)
    assert "| E both, kept | 12.345678 | unavailable | 45.678901; 9.8765432; 2.3456789e-08; 0.12345678 |" in result
    assert "| D retained both | 23.456789 | unavailable | 34.56789; 8.7654321; 7.654321; 6.54321 |" in result
    assert "| Both minus frozen | 91.234567 | unavailable | 82.345678; 73.456789; 64.56789; 55.6789 |" in result
    assert "| E total only | 71234567.8912345 | withheld |" in result
    assert "| E both, kept | 70123456.7891234 | 72345678.9123456 |" in result
    assert "DO_NOT_RENDER" not in result
    assert "123456789123456789" not in result


def test_nulls_and_linked_suppression_stay_withheld(aggregates):
    nulls = deepcopy(aggregates)
    nulls["fiscal"]["central"][0]["value_bn"] = None
    nulls["fiscal"]["paired"][0]["estimate_bn"] = None
    assert "| E both, kept | withheld | unavailable | withheld | unavailable |" in renderer.render(nulls)
    for suppression in (
        {"whole_family_withheld": {"gross": True}},
        {"treatment_level_family_withheld": {"gross": True}},
        {"contrast_family_withheld": {"combined_effect": {"gross": True}}},
    ):
        suppressed = deepcopy(aggregates)
        suppressed["fiscal"]["suppression"].update(suppression)
        result = renderer.render(suppressed)
        assert "| E both, kept | withheld | unavailable | withheld | unavailable |" in result
        assert "12.345678" not in result
        assert "45.678901" not in result


def test_refuses_plans_duplicate_cells_and_missing_disclosure_rule(aggregates):
    with pytest.raises(ValueError, match="completed fiscal aggregates"):
        renderer.render({"status": "planned; no PolicyEngine runs started"})
    duplicate = deepcopy(aggregates)
    duplicate["fiscal"]["central"].append(duplicate["fiscal"]["central"][0])
    with pytest.raises(ValueError, match="duplicate aggregate"):
        renderer.render(duplicate)
    aggregates["fiscal"]["suppression"]["minimum_records"] = 9
    with pytest.raises(ValueError, match="ten-record"):
        renderer.render(aggregates)
