"""Exact historical privacy redaction and tamper checks, without model jobs."""

import json
from pathlib import Path
import shutil

import pytest

from historical_estimator_redaction import (PROOF, RECEIPT, TARGETS, canonical_digest, digest,
                                            verify_historical_estimator_redaction)


ROOT = Path(__file__).resolve().parents[1]


def copy_artifacts(destination):
    for relative in (*TARGETS, PROOF, RECEIPT):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_estimator_redaction_preserves_historical_fiscal_content_and_provenance():
    check = verify_historical_estimator_redaction(ROOT)
    assert check["passed"] and check["retained_fiscal_estimates_unchanged"]
    assert check["original_provenance_preserved"]
    assert not check["current_runtime_identity_claimed"]


def test_refreshing_metadata_cannot_admit_changed_fiscal_estimates(tmp_path):
    copy_artifacts(tmp_path)
    estimator = json.loads((tmp_path / TARGETS[0]).read_text())
    estimator["estimates"]["primary"]["gross"]["2034"]["mean"] += 1
    updated = (json.dumps(estimator, indent=2) + "\n").encode()
    for relative in TARGETS:
        (tmp_path / relative).write_bytes(updated)
    metadata = json.loads((tmp_path / PROOF).read_text())
    metadata["sanitized_artifact_sha256"] = digest(updated)
    metadata["retained_content_sha256"] = canonical_digest(estimator)
    (tmp_path / PROOF).write_text(json.dumps(metadata))
    with pytest.raises(AssertionError, match="estimator hash changed"):
        verify_historical_estimator_redaction(tmp_path)


def test_individual_record_families_cannot_be_reintroduced(tmp_path):
    copy_artifacts(tmp_path)
    estimator = json.loads((tmp_path / TARGETS[0]).read_text())
    estimator["estimates"]["primary"]["largest_record_bn"] = {"synthetic": {"mean": 1}}
    (tmp_path / TARGETS[0]).write_text(json.dumps(estimator))
    with pytest.raises(AssertionError, match="estimator bytes changed"):
        verify_historical_estimator_redaction(tmp_path)


def test_old_receipt_hash_cannot_be_relabelled_as_sanitized(tmp_path):
    copy_artifacts(tmp_path)
    receipt = json.loads((tmp_path / RECEIPT).read_text())
    receipt["files"]["historical_estimator.json"] = digest((tmp_path / TARGETS[0]).read_bytes())
    (tmp_path / RECEIPT).write_text(json.dumps(receipt))
    with pytest.raises(AssertionError, match="immutable historical receipt changed"):
        verify_historical_estimator_redaction(tmp_path)
