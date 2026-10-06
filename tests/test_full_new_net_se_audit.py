"""Portable validation of the aggregate kept/full-new precision evidence."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/pilot/full_new_net_se_audit.json"


def read(path):
    return json.loads(path.read_text())


def test_saved_path_audit_matches_published_estimates_and_pairing():
    audit = read(AUDIT)
    fiscal = read(ROOT / "data/pilot/model_v2_e.json")
    assert audit["checks"]["batch_count"] == audit["checks"]["unique_full_cache_keys"] == 41
    assert audit["checks"]["paired_distinct_indices"] == 40
    assert all(value is True for key, value in audit["checks"].items() if isinstance(value, bool))
    assert audit["draw_provenance"] == fiscal["provenance"]["draws"]
    assert len({r["cache_key"] for r in audit["cache_receipts"]}) == 41
    for path, expected in audit["input_files_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((ROOT / "scripts/audit_model_v2_full_new_net_se.py").read_bytes()).hexdigest() == audit["audit_script_sha256"]
    for row in audit["summary"]:
        for audit_name, treatment in (("kept", "both"), ("full_new", "both_full_new"),
                                      ("full_new_minus_kept", "retyped_level_upper_minus_kept")):
            published = next(r for r in fiscal["fiscal"]["paired"] if
                             (r["year"], r["geography"], r["measure"], r["treatment_or_contrast"]) ==
                             (row["year"], "UK", row["measure"], treatment))["estimate_bn"]
            for field, value in row[audit_name].items():
                assert value == pytest.approx(published[field], abs=1e-12, rel=0)
        a, b, c = (row[name]["se"] for name in ("kept", "full_new", "full_new_minus_kept"))
        assert row["estimator_correlation"] == pytest.approx((a*a+b*b-c*c)/(2*a*b), abs=1e-12, rel=0)


def test_path_aggregates_reproduce_net_stratified_precision_without_private_caches():
    audit = read(AUDIT)
    fiscal = read(ROOT / "data/pilot/model_v2_e.json")
    spec = importlib.util.spec_from_file_location("precision_audit", ROOT / "scripts/audit_model_v2_full_new_net_se.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    design = fiscal["provenance"]["paired_macro_draws"]
    indices = {int(h): rows for h, rows in design["indices_by_stratum"].items()}
    probabilities = {int(h): value for h, value in design["probability_by_stratum"].items()}
    expected_indices = {i for rows in indices.values() for i in rows}
    for year in (2034, 2039):
        rows = [row for row in audit["paths"] if row["year"] == year]
        assert len(rows) == 40
        assert {row["macro_path_index"] for row in rows} == expected_indices
        values = {row["macro_path_index"]: row["net_contrast_bn"] for row in rows}
        result, strata = module.estimate(values, indices, probabilities, audit["draw_provenance"]["n"])
        saved = next(row for row in audit["summary"] if row["year"] == year and row["measure"] == "net")
        assert result == pytest.approx(saved["full_new_minus_kept"], abs=1e-12, rel=0)
        assert {str(h): value for h, value in strata.items()} == pytest.approx(
            audit["net_contrast_path_variance_by_stratum"][str(year)], abs=1e-12, rel=0)
    # These are full-path aggregates. No survey diagnostics cross the boundary.
    text = AUDIT.read_text()
    assert '"household_id"' not in text and '"person_id"' not in text and '"weight"' not in text
