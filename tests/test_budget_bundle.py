"""The pending Budget release is never inferred from candidate metadata."""

from copy import deepcopy
import hashlib
import importlib.metadata
import json
from types import SimpleNamespace

import pytest

from triple_lock import certification, datasets, pipeline
from triple_lock.config import PRIMARY_DATASET, REPO, SENSITIVITY_DATASET


def test_binding_roles_and_pending_preflight_do_not_read_model_or_data(monkeypatch):
    assert PRIMARY_DATASET == "microcosm_uk_2024_25@a133f37a"
    assert SENSITIVITY_DATASET == "enhanced_frs_2024_25@1.58.2"
    monkeypatch.setattr(datasets, "materialize", lambda *a, **kw: pytest.fail("no data"))
    monkeypatch.setattr(pipeline, "package_versions", lambda: pytest.fail("no model import"))
    with pytest.raises(pipeline.UncertifiedBundle, match="#715.*pending"):
        pipeline.certified_bundle_preflight()


@pytest.fixture
def released(tmp_path, monkeypatch):
    manifest = json.loads((REPO / "data/certification/d1983-candidate-bundle-manifest.json").read_text())
    version = "99.0.0"  # Fictional future release, never a production pin.
    release = manifest["data_releases"]["uk"]
    manifest["policyengine_version"] = version
    release["policyengine_version"] = version
    release["bundle_id"] = f"uk-{version}"
    cert = {**datasets.CERTIFIED_BUNDLE, "bundle_version": version, "bundle_id": f"uk-{version}"}
    spec = deepcopy(datasets.DATASETS[PRIMARY_DATASET])
    spec["bundle_certification"] = cert
    path = tmp_path / "manifest.json"
    distributions = {"policyengine": SimpleNamespace(version=version, locate_file=lambda _: path)}
    cert["wheels"] = {}
    for role, name in (("model", "policyengine-uk"), ("core", "policyengine-core")):
        package = name.replace("-", "_")
        package_version = cert[f"{role}_version"]
        member = f"{package}/fixture.py"
        payload = f"# Invented {name} {package_version} payload\n".encode()
        installed_path = tmp_path / "site-packages" / member
        installed_path.parent.mkdir(parents=True)
        installed_path.write_bytes(payload)
        wheel_sha256 = hashlib.sha256(f"Invented {name} wheel".encode()).hexdigest()
        member_manifest = {"schema_version": 1, "package": name, "version": package_version,
                           "wheel": {"sha256": wheel_sha256},
                           "members": {member: hashlib.sha256(payload).hexdigest()}}
        manifest_path = f"{role}-wheel.json"
        manifest_raw = json.dumps(member_manifest).encode()
        (tmp_path / manifest_path).write_bytes(manifest_raw)
        cert["wheels"][name] = {"manifest_path": manifest_path,
                                 "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                                 "wheel_sha256": wheel_sha256}
        distributions[name] = SimpleNamespace(
            version=package_version, locate_file=lambda member: tmp_path / "site-packages" / member)
    cert["model_wheel_sha256"] = cert["wheels"]["policyengine-uk"]["wheel_sha256"]
    release["model_package"]["sha256"] = cert["model_wheel_sha256"]
    monkeypatch.setattr(importlib.metadata, "distribution", distributions.__getitem__)
    # Exercise the production payload verifier on these authenticated tiny
    # fixtures; this unit suite must never traverse the actual installed wheels.
    verify_payloads = certification.verify_released_bundle_payloads
    monkeypatch.setattr(certification, "verify_released_bundle_payloads", lambda pin:
                        verify_payloads(pin, root=tmp_path, distribution=distributions.__getitem__))
    versions = {key: cert[key] for key in ("bundle_package", "bundle_version", "model_version", "core_version")}

    def write():
        raw = json.dumps(manifest).encode()
        path.write_bytes(raw)
        cert["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    write()
    return spec, versions, manifest, write, path


def test_exact_released_manifest_and_artifact_can_certify(released):
    spec, versions, _, _, _ = released
    assert datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("package", ["policyengine_uk", "policyengine_core"])
def test_released_bundle_rechecks_tampered_installed_payload(released, package):
    spec, versions, _, _, path = released
    assert datasets._certified_by_installed_bundle(spec, versions)
    payload = path.parent / "site-packages" / package / "fixture.py"
    payload.write_text("# Changed installed model/core code\n")
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64), ("revision", "other-cut"), ("path", "other.h5"),
    ("repo_id", "policyengine/other"), ("data_version", "other"), ("build_id", "other"),
])
def test_released_bundle_rejects_different_artifact_identity(released, field, value):
    spec, versions, _, _, _ = released
    spec[field] = value
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("location,key,value", [
    ("certification", "certified_for_core_version", "3.33.0"),
    ("model_package", "version", "2.153.4"),
    ("model_package", "sha256", "0" * 64),
    (None, "build_id", "other-cut"),
    (None, "source_manifest_uri", "hf://other"),
    (None, "release_manifest_uri", "https://example.com/other"),
    (None, "region_datasets", {"constituency": {"path_template": "dense.h5"}}),
])
def test_structural_pair_checks_even_with_authenticated_manifest(released, location, key, value):
    spec, versions, manifest, write, _ = released
    release = manifest["data_releases"]["uk"]
    (release[location] if location else release)[key] = value
    write()
    assert not datasets._certified_by_installed_bundle(spec, versions)


def test_changed_installed_manifest_is_rejected(released):
    spec, versions, _, _, path = released
    path.write_text("{}")
    assert not datasets._certified_by_installed_bundle(spec, versions)
