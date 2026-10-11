"""Exact correspondence for a privacy-only migration of historical artifacts.

These independently reviewed hashes bind every retained JSON value. Original
raw hashes describe the historical artifacts, never the sanitized bytes or
the current model. No private values are retained in this proof.
"""

import hashlib
import json
from pathlib import Path


PROOF = "data/pilot/historical-publication-privacy-redaction.json"
REMOVED_FIELDS = frozenset(("largest_household", "concentration_by_year", "largest_record_bn",
                            "net_excluding_largest_record", "max_proportionality_error_gbp",
                            "max_additional_state_pension_gap_gbp", "max_identity_error_gbp",
                            "max_age", "survey_max_age"))
RESULTS_TARGETS = frozenset(("data/results.json", "dashboard/public/data/results.json"))
REVIEWED_ARTIFACTS = (
    {"targets": ["data/results.json", "dashboard/public/data/results.json"],
     "original_artifact_sha256": "e94cce9fe564c25d493bcef2f6f5489270801bfff8e8f930c3aed77c6fdd7f14",
     "sanitized_artifact_sha256": "2ef0a3c9a99072bc25586401eb6e79363e66cb91453d9d235ae0ed76e8e33f3d",
     "retained_content_sha256": "3a7407c93cbb9b37c52536e80d7b32e56143dcca84b4354dc6019eae7c583efd",
     "removed_field_counts": [{"field": "concentration_by_year", "occurrences": 5},
                              {"field": "largest_household", "occurrences": 5},
                              {"field": "largest_record_bn", "occurrences": 240},
                              {"field": "max_age", "occurrences": 2},
                              {"field": "max_proportionality_error_gbp", "occurrences": 9},
                              {"field": "net_excluding_largest_record", "occurrences": 240}]},
    {"targets": ["data/scenarios/obr_premium.json"],
     "original_artifact_sha256": "a56dca0f13a47d723f0f8e8f20325af26fde18c53762baa2f11b97d33fce6412",
     "sanitized_artifact_sha256": "7feacab04701d327da1f76a43a8c7313a45295722e75f776e1edd8e90292eb6e",
     "retained_content_sha256": "a545d3205dfda27574a703ae446f8c2f5a909a9892ae037b8b15eade12100a10",
     "removed_field_counts": [{"field": "concentration_by_year", "occurrences": 1},
                              {"field": "largest_household", "occurrences": 1},
                              {"field": "max_proportionality_error_gbp", "occurrences": 1}]},
    {"targets": ["data/pilot/model_v2_e.json"],
     "original_artifact_sha256": "ac3ad91ca4650108dab90b2dbaae92808a913160fd174371a01d5c875bd3ee7a",
     "sanitized_artifact_sha256": "c673c9ee6b82f60767e1ad5375e5daf24e0990cb01b472c5cc46fd1b8bb87584",
     "retained_content_sha256": "aed02d7069f723bd9bdd2fbeadc025e35057cd0455950bcc35de95eb92d90c38",
     "removed_field_counts": [{"field": "max_identity_error_gbp", "occurrences": 6}]},
)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def assert_diagnostics_absent(value):
    if isinstance(value, dict):
        if REMOVED_FIELDS.intersection(value):
            raise AssertionError("individual-record diagnostic reintroduced")
        for child in value.values():
            assert_diagnostics_absent(child)
    elif isinstance(value, list):
        for child in value:
            assert_diagnostics_absent(child)


def verify_historical_publication_redaction(repo, *, supplied_bytes=None, targets=None):
    """Verify known sanitized targets against independently pinned content.

    A caller may supply a target's already-read immutable bytes. That exact
    buffer is verified without rereading the target, avoiding a parse/hash race.
    """
    repo = Path(repo).resolve()
    supplied_bytes = supplied_bytes or {}
    reviewed_targets = {relative for artifact in REVIEWED_ARTIFACTS for relative in artifact["targets"]}
    targets = reviewed_targets if targets is None else set(targets)
    if not targets or not targets <= reviewed_targets:
        raise AssertionError("unreviewed historical artifact target")
    if not set(supplied_bytes) <= targets:
        raise AssertionError("unreviewed supplied artifact")
    proof_path = (repo / PROOF).resolve()
    if not proof_path.is_relative_to(repo):
        raise AssertionError("publication proof leaves repository")
    metadata = json.loads(proof_path.read_bytes())
    if metadata["transform"] != "omit_licensed_record_diagnostics_v1":
        raise AssertionError("privacy transform changed")
    if metadata["removed_field_names"] != sorted(REMOVED_FIELDS):
        raise AssertionError("privacy removal scope changed")
    if metadata["artifacts"] != list(REVIEWED_ARTIFACTS):
        raise AssertionError("reviewed artifact correspondence changed")
    if metadata["model_jobs"] != 0:
        raise AssertionError("privacy migration is not a model run")
    if metadata["original_provenance_preserved"] is not True:
        raise AssertionError("historical provenance relabelled")
    if metadata["every_retained_value_unchanged"] is not True:
        raise AssertionError("retained values relabelled")
    for artifact in REVIEWED_ARTIFACTS:
        contents = []
        for relative in artifact["targets"]:
            if relative not in targets:
                continue
            path = (repo / relative).resolve()
            if not path.is_relative_to(repo):
                raise AssertionError("historical artifact leaves repository")
            content = supplied_bytes[relative] if relative in supplied_bytes else path.read_bytes()
            if not isinstance(content, bytes):
                raise AssertionError("historical artifact buffer must be immutable bytes")
            if digest(content) != artifact["sanitized_artifact_sha256"]:
                raise AssertionError("sanitized artifact bytes changed")
            retained = json.loads(content)
            if canonical_digest(retained) != artifact["retained_content_sha256"]:
                raise AssertionError("retained content changed")
            assert_diagnostics_absent(retained)
            contents.append(content)
        if contents and not all(content == contents[0] for content in contents):
            raise AssertionError("historical publication copies differ")
    return {"passed": True, "every_retained_value_unchanged": True,
            "original_provenance_preserved": True, "current_runtime_identity_claimed": False}


def verify_historical_public_input(repo, relative, historical_sha256):
    """Accept only the exact reviewed privacy transform of a saved input."""
    artifact = next((item for item in REVIEWED_ARTIFACTS if relative in item["targets"]), None)
    if artifact is None:
        raise AssertionError("unreviewed historical public input")
    if historical_sha256 != artifact["original_artifact_sha256"]:
        raise AssertionError("historical input provenance changed")
    verify_historical_publication_redaction(repo, targets={relative})
    return {"historical_artifact_sha256": historical_sha256,
            "sanitized_artifact_sha256": artifact["sanitized_artifact_sha256"],
            "historical_raw_hash_is_provenance_only": True, "every_retained_value_unchanged": True}


def historical_results_source_sha256(path, content, repo):
    """Alias historical identity only for a verified known repository target.

    Custom inputs retain their actual byte hash, even if they happen to be a
    copy of the sanitized historical results. They cannot borrow provenance.
    """
    repo = Path(repo).resolve()
    path = Path(path).absolute()
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError:
        return digest(content)
    if relative not in RESULTS_TARGETS:
        return digest(content)
    if not path.resolve().is_relative_to(repo):
        raise AssertionError("historical results source leaves repository")
    if digest(content) != REVIEWED_ARTIFACTS[0]["sanitized_artifact_sha256"]:
        # A subsequent full build is a new input with its own byte identity.
        # It cannot inherit the historical migration's original hash.
        return digest(content)
    verify_historical_publication_redaction(repo, supplied_bytes={relative: content}, targets={relative})
    return REVIEWED_ARTIFACTS[0]["original_artifact_sha256"]
