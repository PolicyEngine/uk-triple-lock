"""Historical upstream integrity checks, without importing PolicyEngine."""

import json
from pathlib import Path

import pytest

from historical_upstream_sources import (
    ARCHIVE_PATH,
    historical_upstream_files,
    verify_historical_formula_sources,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("filename", (
    "full_new_net_se_diagnostic_validated.json",
    "gc_precision_diagnostic.json",
    "hb_gc_receipt_intervention.json",
))
def test_retained_receipt_formula_hashes_match_genuine_pilot_sources(filename, monkeypatch):
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "distribution", lambda *args: pytest.fail(
        "historical verification must not consult the installed certified model"))
    receipt = json.loads((ROOT / "data/pilot" / filename).read_text())
    binding = receipt.get("binding", receipt)
    formulas = binding.get("policyengine_formula_source_sha256", binding.get("installed_formula_source_sha256"))
    proof = verify_historical_formula_sources(ROOT, binding["packages"], formulas)
    assert proof["passed"] and proof["model_version"] == "2.120.0"
    assert proof["current_runtime_identity_claimed"] is False
    assert proof["formula_count"] == len(formulas)


def test_modified_upstream_archive_is_rejected(tmp_path):
    target = tmp_path / ARCHIVE_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / ARCHIVE_PATH).read_bytes() + b"tampered")
    with pytest.raises(AssertionError, match="historical upstream archive bytes changed"):
        historical_upstream_files(tmp_path, "2.120.0")


def test_certified_version_cannot_be_verified_by_the_pilot_archive():
    with pytest.raises(AssertionError, match="only for the 2.120.0 pilot"):
        historical_upstream_files(ROOT, "2.125.1")


def test_modified_retained_formula_hash_is_rejected():
    receipt = json.loads((ROOT / "data/pilot/gc_precision_diagnostic.json").read_text())
    formulas = dict(receipt["policyengine_formula_source_sha256"])
    formulas[next(iter(formulas))] = "0" * 64
    with pytest.raises(AssertionError, match="historical upstream formula differs"):
        verify_historical_formula_sources(ROOT, receipt["packages"], formulas)
