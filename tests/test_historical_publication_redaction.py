"""Privacy-only correspondence, preserved fiscal inputs, and provenance isolation."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from copy import deepcopy

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


def synthetic_custom_expected_value():
    """Two macro paths with aggregate fiscal outputs; no survey or model."""
    paths = [{"stratum": 1, "times_drawn": 1, "times_drawn_sensitivity": 1,
              "outputs": {"primary": {"gross": {"2039": gross}, "net": {"2039": net}},
                          "sensitivity": {"gross": {"2039": gross + 1}, "net": {"2039": net + .5}}}}
             for gross, net in ((1., .75), (3., 2.25))]
    return {"primary": "synthetic", "draws": {"n": 100},
            "strata": [{"stratum": 1, "probability": 1.}], "paths": paths,
            "estimates": {dataset: {key: {"2039": {"mean": 0.}}
                                    for key in ("gross", "net")}
                          for dataset in ("primary", "sensitivity")},
            "sensitivities": {}, "paired_difference": {key: {"2039": {"mean": 0.}}
                                                        for key in ("gross", "net")}}


def assert_shared_diagnostics_absent(value):
    from triple_lock.pipeline import RECORD_FIELDS

    if isinstance(value, dict):
        assert not set(value) & RECORD_FIELDS
        for child in value.values():
            assert_shared_diagnostics_absent(child)
    elif isinstance(value, list):
        for child in value:
            assert_shared_diagnostics_absent(child)


def test_custom_historical_estimator_recursively_redacts_families_and_preserves_fiscal_input(tmp_path):
    from triple_lock import expected_value as EV
    from triple_lock.pipeline import RECORD_FIELDS
    from triple_lock.ts_uncertainty import write_historical_estimator

    clean = synthetic_custom_expected_value()
    expected = EV.reestimate_published(clean)
    custom = deepcopy(clean)
    sentinel = 987654321.625
    # A key-shaped year series previously reached the generic estimator.
    # All current prohibited families must be removed before reconstruction.
    for field in RECORD_FIELDS:
        for dataset, outputs in custom["estimates"].items():
            outputs[field] = {"2039": {"mean": sentinel}}
            for path in custom["paths"]:
                path["outputs"][dataset][field] = {"2039": sentinel}
        custom["paired_difference"][field] = {"2039": {"mean": sentinel}}
    custom["primary"] = {"name": "synthetic", "nested_metadata": [
        {"deeper": {field: {"private": sentinel} for field in RECORD_FIELDS}},
        {"safe_label": "preserved"},
    ]}
    original = deepcopy(custom)
    recomputed = EV.reestimate_published(custom)
    assert custom == original
    assert_shared_diagnostics_absent(recomputed)
    assert recomputed["estimates"] == expected["estimates"]
    assert recomputed["paired_difference"] == expected["paired_difference"]
    assert recomputed["historical_primary"]["nested_metadata"][1] == {"safe_label": "preserved"}
    source = tmp_path / "custom-results.json"
    source_bytes = (json.dumps({"expected_value": custom}) + "\n").encode()
    source.write_bytes(source_bytes)
    output = tmp_path / "estimator-output"
    written = write_historical_estimator(output, published_path=source)
    published_bytes = (output / "historical_estimator.json").read_bytes()
    assert_shared_diagnostics_absent(written)
    assert_shared_diagnostics_absent(json.loads(published_bytes))
    assert str(sentinel).encode() not in published_bytes
    assert written["published_results_sha256"] == digest(source_bytes)
    assert written["estimates"] == expected["estimates"]
    assert written["paired_difference"] == expected["paired_difference"]
    assert source.read_bytes() == source_bytes


def test_custom_historical_writer_redacts_nested_estimator_result_before_serializing(tmp_path, monkeypatch):
    from triple_lock import expected_value as EV
    from triple_lock.pipeline import RECORD_FIELDS
    from triple_lock.ts_uncertainty import write_historical_estimator

    source = tmp_path / "custom-results.json"
    source_bytes = b'{"expected_value": {"synthetic": true}}\n'
    source.write_bytes(source_bytes)
    reconstructed = {"estimates": {"primary": {"gross": {2039: {"mean": 2.}}}},
                     "future_metadata": [{"nested": {field: {"private": 987654321.625}
                                                      for field in RECORD_FIELDS}}]}
    monkeypatch.setattr(EV, "reestimate_published", lambda value: reconstructed)
    output = tmp_path / "estimator-output"
    written = write_historical_estimator(output, published_path=source)
    content = (output / "historical_estimator.json").read_bytes()
    assert_shared_diagnostics_absent(written)
    assert_shared_diagnostics_absent(json.loads(content))
    assert written["estimates"]["primary"]["gross"][2039]["mean"] == 2.
    assert written["published_results_sha256"] == digest(source_bytes)
    assert b"987654321.625" not in content
