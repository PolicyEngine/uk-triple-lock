"""Privacy-only correspondence, preserved fiscal inputs, and provenance isolation."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from triple_lock.historical_publication import (
    PROOF, REMOVED_FIELDS, REVIEWED_ARTIFACTS, canonical_digest, digest,
    historical_results_source_sha256, verify_historical_public_input,
    verify_historical_publication_redaction,
)


ROOT = Path(__file__).resolve().parents[1]
TARGETS = tuple(relative for artifact in REVIEWED_ARTIFACTS for relative in artifact["targets"])


def copy_artifacts(destination):
    for relative in (*TARGETS, PROOF):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, path)


def test_exact_redaction_is_independently_bound_and_preserves_historical_identity():
    check = verify_historical_publication_redaction(ROOT)
    assert check["passed"] and check["every_retained_value_unchanged"]
    assert check["original_provenance_preserved"] and not check["current_runtime_identity_claimed"]
    for artifact in REVIEWED_ARTIFACTS:
        for relative in artifact["targets"]:
            result = verify_historical_public_input(ROOT, relative, artifact["original_artifact_sha256"])
            assert result["historical_raw_hash_is_provenance_only"]
            assert result["every_retained_value_unchanged"]


def test_metadata_refresh_cannot_authorize_changed_retained_fiscal_values(tmp_path):
    copy_artifacts(tmp_path)
    artifact = REVIEWED_ARTIFACTS[0]
    retained = json.loads((tmp_path / artifact["targets"][0]).read_bytes())
    retained["central"]["run"]["saving_bn"]["2039"]["gross"] += 1
    changed = (json.dumps(retained, indent=2) + "\n").encode()
    for relative in artifact["targets"]:
        (tmp_path / relative).write_bytes(changed)
    metadata = json.loads((tmp_path / PROOF).read_bytes())
    metadata["artifacts"][0].update(sanitized_artifact_sha256=digest(changed),
                                     retained_content_sha256=canonical_digest(retained))
    (tmp_path / PROOF).write_text(json.dumps(metadata))
    with pytest.raises(AssertionError, match="reviewed artifact correspondence changed"):
        verify_historical_publication_redaction(tmp_path)
    assert historical_results_source_sha256(tmp_path / artifact["targets"][0], changed, tmp_path) == digest(changed)
    assert digest(changed) != artifact["original_artifact_sha256"]


@pytest.mark.parametrize("field", sorted(REMOVED_FIELDS))
def test_nested_individual_diagnostics_cannot_reappear(tmp_path, field):
    copy_artifacts(tmp_path)
    path = tmp_path / TARGETS[0]
    retained = json.loads(path.read_bytes())
    retained["injected_private_diagnostic"] = [{field: 1}]
    path.write_text(json.dumps(retained))
    with pytest.raises(AssertionError, match="sanitized artifact bytes changed"):
        verify_historical_publication_redaction(tmp_path)


def test_original_hash_cannot_be_relabelled_as_the_sanitized_hash():
    artifact = REVIEWED_ARTIFACTS[-1]
    with pytest.raises(AssertionError, match="historical input provenance changed"):
        verify_historical_public_input(ROOT, artifact["targets"][0], artifact["sanitized_artifact_sha256"])


def test_historical_pilot_input_correspondence_does_not_depend_on_a_later_results_build(tmp_path):
    copy_artifacts(tmp_path)
    for relative in (*REVIEWED_ARTIFACTS[0]["targets"], *REVIEWED_ARTIFACTS[1]["targets"]):
        (tmp_path / relative).write_text('{"synthetic_later_build": true}\n')
    artifact = REVIEWED_ARTIFACTS[-1]
    check = verify_historical_public_input(tmp_path, artifact["targets"][0], artifact["original_artifact_sha256"])
    assert check["every_retained_value_unchanged"]


def test_later_repository_results_use_actual_source_identity(tmp_path):
    copy_artifacts(tmp_path)
    path = tmp_path / TARGETS[0]
    content = b'{"synthetic_later_build": true}\n'
    path.write_bytes(content)
    assert historical_results_source_sha256(path, content, tmp_path) == digest(content)
    assert digest(content) != REVIEWED_ARTIFACTS[0]["original_artifact_sha256"]


def test_known_sanitized_source_cannot_borrow_history_from_tampered_proof(tmp_path):
    copy_artifacts(tmp_path)
    content = (tmp_path / TARGETS[0]).read_bytes()
    metadata = json.loads((tmp_path / PROOF).read_bytes())
    metadata["artifacts"][0]["original_artifact_sha256"] = "0" * 64
    (tmp_path / PROOF).write_text(json.dumps(metadata))
    with pytest.raises(AssertionError, match="reviewed artifact correspondence changed"):
        historical_results_source_sha256(tmp_path / TARGETS[0], content, tmp_path)


def test_custom_copy_keeps_its_actual_hash_instead_of_borrowing_historical_provenance(tmp_path):
    content = (ROOT / TARGETS[0]).read_bytes()
    custom = tmp_path / "custom-results.json"
    custom.write_bytes(content)
    assert historical_results_source_sha256(custom, content, ROOT) == digest(content)
    assert digest(content) != REVIEWED_ARTIFACTS[0]["original_artifact_sha256"]


def test_historical_writer_parses_and_verifies_the_same_single_read_buffer(tmp_path, monkeypatch):
    from triple_lock.ts_uncertainty import write_historical_estimator

    source = ROOT / TARGETS[0]
    read_bytes = Path.read_bytes
    source_reads = []

    def once(path):
        if path == source:
            source_reads.append(path)
            assert len(source_reads) == 1, "historical source was reread"
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", once)
    result = write_historical_estimator(tmp_path)
    assert source_reads == [source]
    assert result["published_results_sha256"] == REVIEWED_ARTIFACTS[0]["original_artifact_sha256"]
    expected = json.loads((ROOT / "docs/uncertainty/historical_estimator.json").read_text())
    assert result["published_results_sha256"] == expected["published_results_sha256"]
    assert result["n_draws"] == expected["n_draws"]


def test_known_source_cannot_escape_repository_through_symlink(tmp_path):
    copy_artifacts(tmp_path)
    source = tmp_path / TARGETS[0]
    outside = tmp_path.parent / f"{tmp_path.name}-external.json"
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(AssertionError, match="leaves repository"):
        historical_results_source_sha256(source, outside.read_bytes(), tmp_path)


@pytest.mark.parametrize("optimization", ["flag", "environment"])
@pytest.mark.parametrize("tamper,expected", [
    ("fiscal", "sanitized artifact bytes changed"),
    ("proof", "reviewed artifact correspondence changed"),
])
def test_optimized_python_still_rejects_historical_fiscal_or_proof_tampering(tmp_path, optimization, tamper, expected):
    relative = REVIEWED_ARTIFACTS[-1]["targets"][0]
    for name in (relative, PROOF):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    target = tmp_path / (relative if tamper == "fiscal" else PROOF)
    changed = json.loads(target.read_bytes())
    if tamper == "fiscal":
        changed["fiscal"]["central"][0]["value_bn"] += 1
    else:
        changed["artifacts"][-1]["retained_content_sha256"] = "0" * 64
    target.write_text(json.dumps(changed))
    # Load only the stdlib verifier. Neither package initialization nor a
    # PolicyEngine import is needed to exercise optimized production guards.
    script = """
import runpy
import sys
from pathlib import Path
if sys.flags.optimize < 1:
    raise RuntimeError("test subprocess must run with optimization")
module = runpy.run_path(sys.argv[1])
repo = Path(sys.argv[2])
relative = sys.argv[3]
module["verify_historical_publication_redaction"](
    repo, supplied_bytes={relative: (repo / relative).read_bytes()}, targets={relative})
"""
    environment = dict(os.environ)
    environment.pop("PYTHONOPTIMIZE", None)
    options = ["-O"] if optimization == "flag" else []
    if optimization == "environment":
        environment["PYTHONOPTIMIZE"] = "2"
    result = subprocess.run(
        [sys.executable, *options, "-c", script, str(ROOT / "src/triple_lock/historical_publication.py"),
         str(tmp_path), relative],
        capture_output=True, text=True, env=environment, check=False, timeout=60,
    )
    assert result.returncode != 0
    assert f"AssertionError: {expected}" in result.stderr
