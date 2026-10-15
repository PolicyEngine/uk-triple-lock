"""Verify the exact diagnostic-only redaction without retaining private values.

The original receipt remains immutable historical provenance. The retained
content digest was captured from its original estimator after removing only
the four named individual-record families, and is pinned independently of
the mutable redaction metadata.
"""

import hashlib
import json


TARGETS = ("docs/uncertainty/historical_estimator.json", "data/pilot/c2-dry-run/historical_estimator.json")
PROOF = "data/pilot/historical-estimator-privacy-redaction.json"
RECEIPT = "data/pilot/c2-dry-run-receipt.json"
ORIGINAL_SHA256 = "92fbe2984ccac839fe9ae88c35f317b51dcea27e74076e0c6a92010286a84c69"
SANITIZED_SHA256 = "4d0e77e8f4f19847992754ed43b2fc50a98108a9a8e65dbe75cc47eb023c637d"
RETAINED_CONTENT_SHA256 = "942905869d2b85c9907023811664592b9429c8a0a0703a46b00b936123f45401"
RECEIPT_SHA256 = "8c08fc93e830f687ef85c37da4c0c40a686949048f61ce0e378d536e4cb3ce17"
REMOVED_PATHS = [["estimates", dataset, key] for dataset in ("primary", "sensitivity")
                 for key in ("largest_record_bn", "net_excluding_largest_record")]


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def verify_historical_estimator_redaction(repo):
    """Bind sanitized public artifacts to the unchanged historical receipt."""
    metadata = json.loads((repo / PROOF).read_text())
    assert metadata["transform"] == "remove_historical_single_record_estimators_v1", "redaction transform changed"
    assert metadata["removed_paths"] == REMOVED_PATHS, "redaction scope changed"
    assert metadata["targets"] == list(TARGETS), "redaction targets changed"
    assert metadata["original_artifact_sha256"] == ORIGINAL_SHA256, "historical estimator hash changed"
    assert metadata["sanitized_artifact_sha256"] == SANITIZED_SHA256, "sanitized estimator hash changed"
    assert metadata["retained_content_sha256"] == RETAINED_CONTENT_SHA256, "retained estimator content changed"
    assert metadata["historical_receipt"] == RECEIPT, "historical receipt path changed"
    receipt_bytes = (repo / RECEIPT).read_bytes()
    assert digest(receipt_bytes) == metadata["historical_receipt_sha256"] == RECEIPT_SHA256, \
        "immutable historical receipt changed"
    receipt = json.loads(receipt_bytes)
    assert receipt["files"]["historical_estimator.json"] == ORIGINAL_SHA256, "original artifact provenance changed"
    assert metadata["original_source_bindings"] == {
        name: receipt["bindings"]["input_hashes"][name] for name in ("expected_value.py", "ts_uncertainty.py")}, \
        "original source provenance changed"
    for relative in TARGETS:
        target = (repo / relative).resolve()
        assert target.is_relative_to(repo.resolve()), "sanitized estimator leaves repository"
        content = target.read_bytes()
        assert digest(content) == SANITIZED_SHA256, "sanitized estimator bytes changed"
        estimator = json.loads(content)
        assert canonical_digest(estimator) == RETAINED_CONTENT_SHA256, "retained estimator content changed"
        for _, dataset, key in REMOVED_PATHS:
            assert key not in estimator["estimates"][dataset], "individual-record estimator reintroduced"
    return {"passed": True, "original_provenance_preserved": True,
            "retained_fiscal_estimates_unchanged": True, "current_runtime_identity_claimed": False}
