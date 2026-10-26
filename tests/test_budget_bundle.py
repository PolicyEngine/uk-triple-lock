"""The pending Budget release is never inferred from candidate metadata."""

from copy import deepcopy
import hashlib
import importlib.metadata
import json
from types import SimpleNamespace

import pytest

import released_pair
from scripts.fill_release_identities import BUNDLE_IDENTITIES, IDENTITIES
from triple_lock import certification, datasets, pipeline
from triple_lock.config import PRIMARY_DATASET, SENSITIVITY_DATASET

FALLBACK_DATASET = "microcosm_uk_2024_25@a133f37a"
PENDING = datasets.BINDING_BUNDLE_VERSION is None  # before the release-night fill


def test_binding_roles_and_the_preflight_read_no_model_or_data(monkeypatch):
    assert PRIMARY_DATASET == "microcosm_uk_2024_25@a6299504"
    assert datasets.D2011_PAIRS == (PRIMARY_DATASET, FALLBACK_DATASET)
    assert SENSITIVITY_DATASET == "enhanced_frs_2024_25@1.58.2"
    monkeypatch.setattr(datasets, "materialize", lambda *a, **kw: pytest.fail("no data"))
    if PENDING:
        monkeypatch.setattr(pipeline, "package_versions", lambda: pytest.fail("no model import"))
        with pytest.raises(pipeline.UncertifiedBundle, match="d2011.*pending"):
            pipeline.certified_bundle_preflight()
    else:  # filled: an install of any other carrier refuses before provenance
        monkeypatch.setattr(pipeline, "package_versions", lambda: {"policyengine": "0.0.0"})
        monkeypatch.setattr(datasets, "provenance", lambda *a: pytest.fail("refused before provenance"))
        with pytest.raises(pipeline.UncertifiedBundle, match="d2011"):
            pipeline.certified_bundle_preflight()


@pytest.mark.parametrize("primary", ["enhanced_frs_2024_25@1.58.2", "microcosm_uk_2024_25@5c6b3f68"])
def test_the_preflight_admits_only_d2011_s_pairs(monkeypatch, primary):
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", primary)
    monkeypatch.setattr(pipeline, "package_versions", lambda: pytest.fail("refused before any import"))
    with pytest.raises(pipeline.UncertifiedBundle, match="Microcosm a6299504"):
        pipeline.certified_bundle_preflight()


def test_the_fallback_preflight_reads_the_fallback_s_own_bundle(monkeypatch):
    """After the fallback commit moves the primary, the preflight checks #715's pair, not the 2.151.0 one."""
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", FALLBACK_DATASET)
    for key, value in (("bundle_version", "99.0.0"), ("manifest_sha256", "a" * 64),
                       ("certification_url", "https://example.invalid/pull/1"), ("certification_commit", "b" * 40)):
        monkeypatch.setitem(datasets.BUNDLE_715, key, value)
    pins = {"policyengine": "99.0.0", "policyengine-uk": "2.147.2", "policyengine-core": "3.33.3"}
    monkeypatch.setattr(pipeline, "package_versions", lambda: dict(pins))
    provenance = {"dataset": FALLBACK_DATASET, "certified": True}
    monkeypatch.setattr(datasets, "provenance", lambda name: dict(provenance) if name == FALLBACK_DATASET
                        else pytest.fail(f"provenance of {name}"))
    receipt = pipeline.certified_bundle_preflight(log=lambda _: None)
    assert receipt == {"certified_bundle": {"passed": True, "packages": pins, "primary": provenance}}
    monkeypatch.setattr(pipeline, "package_versions", lambda: {**pins, "policyengine-uk": "2.151.0"})
    with pytest.raises(pipeline.UncertifiedBundle):
        pipeline.certified_bundle_preflight(log=lambda _: None)


# d2011's binding pair and its fallback: each must certify once its own release identities are filled.
@pytest.fixture(params=[PRIMARY_DATASET, FALLBACK_DATASET])
def released(request, tmp_path, monkeypatch):
    # #715's a133f37a candidate skeleton, re-pointed at the pair and routed to its local-area cut (the binding's
    # invented one while its own is pending), whose manifest SHA-256 is a synthetic manifest's.
    manifest, local, _ = released_pair.released(request.param)
    version = released_pair.VERSION
    release = manifest["data_releases"]["uk"]
    spec = deepcopy(datasets.DATASETS[request.param])
    cert = {**spec["bundle_certification"], "bundle_version": version, "bundle_id": f"uk-{version}",
            "certification_url": "https://example.invalid/pull/9999", "certification_commit": "1" * 40}
    spec["bundle_certification"] = cert
    spec["local_area"] = local
    spec["region_datasets"] = datasets.area_routed(local["path"])
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
    # National only: the binding pair's constituency and local-authority runs must route to its local-area file.
    (None, "region_datasets", {"national": {"path_template": "microcosm_uk_2024_25.h5"}}),
])
def test_structural_pair_checks_even_with_authenticated_manifest(released, location, key, value):
    spec, versions, manifest, write, _ = released
    release = manifest["data_releases"]["uk"]
    (release[location] if location else release)[key] = value
    write()
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("binding,named,pin,certifies", [
    ("certified", "3.33.3", "3.33.3", True),  # #715's candidate: the certificate names the core
    ("bundle_pin", None, "3.33.3", True),     # policyengine.py's default since 6.11.0: it covers the bundle's pin
    (None, None, "3.33.3", True),             # certificates from before October 2026 follow the pin the same way
    ("certified", None, "3.33.3", False),
    ("certified", "3.33.0", "3.33.3", False),
    ("bundle_pin", "3.33.0", "3.33.3", False),
    ("bundle_pin", None, "3.33.0", False),
    ("open", None, "3.33.3", False),
])
def test_the_certified_core_follows_policyengine_pys_core_binding(released, binding, named, pin, certifies):
    spec, versions, manifest, write, _ = released
    certificate = manifest["data_releases"]["uk"]["certification"]
    for key, value in (("core_binding", binding), ("certified_for_core_version", named)):
        certificate.pop(key, None)
        if value is not None:
            certificate[key] = value
    manifest["packages"]["policyengine-core"]["version"] = pin
    write()
    assert datasets._certified_by_installed_bundle(spec, versions) is certifies


@pytest.mark.parametrize("key", released_pair.LOCAL_AREA_KEYS)
def test_a_pending_part_of_the_local_area_cut_certifies_nothing(released, key):
    spec, versions, _, _, _ = released
    assert datasets._certified_by_installed_bundle(spec, versions)
    spec["local_area"] = {**spec["local_area"], key: None}
    assert not datasets._certified_by_installed_bundle(spec, versions)


def test_a_pending_local_area_file_cannot_certify(released):
    spec, versions, manifest, write, _ = released
    pending = datasets.area_routed(None)
    spec["region_datasets"] = deepcopy(pending)
    assert not datasets._certified_by_installed_bundle(spec, versions)
    manifest["data_releases"]["uk"]["region_datasets"] = deepcopy(pending)
    write()
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("key,value", [("revision", "another-cut"), ("sha256", "0" * 64),
                                       ("repo_id", "policyengine/other")])
def test_another_local_area_cut_of_the_same_file_cannot_certify(released, key, value):
    """Every cut publishes microcosm_uk_2024_25_dense.h5: the pinned tag and bytes, not the name, identify it."""
    spec, versions, manifest, write, _ = released
    manifest["data_releases"]["uk"]["datasets"]["microcosm_uk_2024_25_dense"][key] = value
    write()
    assert not datasets._certified_by_installed_bundle(spec, versions)


def test_the_basis_of_the_area_routing_is_the_pair_s_own(released):
    """The binding pair carries no #699 mismatch record; the fallback needs exactly one."""
    spec, versions, manifest, write, _ = released
    release = manifest["data_releases"]["uk"]
    if spec["local_area"]["model_basis"] == "built_with":
        release["regional_certification"] = released_pair.regional_certification(spec["local_area"],
                                                                                  versions["model_version"])
    else:
        del release["regional_certification"]
    write()
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("key", ["certification_url", "certification_commit"])
def test_a_released_certificate_needs_its_certifying_pull_request(released, key):
    spec, versions, _, _, _ = released
    spec["bundle_certification"][key] = None
    assert not datasets._certified_by_installed_bundle(spec, versions)


@pytest.mark.parametrize("name,bundle,prefix,model", [
    (PRIMARY_DATASET, "CERTIFIED_BUNDLE", "BINDING", "2.151.0"),
    # d2011's fallback is a133f37a with policyengine.py #699's area routing, not #715's national-only candidate.
    (FALLBACK_DATASET, "BUNDLE_715", "FALLBACK", "2.147.2"),
])
def test_each_d2011_pair_routes_areas_to_its_cut_and_is_wholly_pending_or_wholly_filled(name, bundle, prefix, model):
    spec = datasets.DATASETS[name]
    certification = spec["bundle_certification"]
    local = spec["local_area"]
    assert certification is getattr(datasets, bundle) and certification["model_version"] == model
    assert spec["region_datasets"] == datasets.area_routed(local["path"]) == {
        "national": {"path_template": spec["path"]},
        "constituency": {"path_template": local["path"]}, "local_authority": {"path_template": local["path"]}}
    filled = [getattr(datasets, f"{prefix}_{key}") is not None for key in IDENTITIES[prefix]]
    assert all(filled) or not any(filled)  # a half-filled pair is a broken fill
    assert (certification["bundle_version"], certification["manifest_sha256"], certification["certification_url"],
            certification["certification_commit"]) == tuple(getattr(datasets, f"{prefix}_{key}")
                                                             for key in BUNDLE_IDENTITIES)
    if not any(filled):
        versions = {**{key: certification[key] for key in ("bundle_package", "model_version", "core_version")},
                    "bundle_version": "99.0.0"}
        assert not datasets._certified_by_installed_bundle(spec, versions)


def test_the_local_area_cuts_are_pinned_on_their_bases():
    binding, fallback = datasets.BINDING_LOCAL_AREA, datasets.FALLBACK_LOCAL_AREA
    assert datasets.DATASETS[PRIMARY_DATASET]["local_area"] is binding
    assert datasets.DATASETS[FALLBACK_DATASET]["local_area"] is fallback
    assert (binding["path"], binding["revision"], binding["sha256"], binding["manifest_sha256"]) == (
        datasets.BINDING_LOCAL_AREA_PATH, datasets.BINDING_LOCAL_AREA_REVISION, datasets.BINDING_LOCAL_AREA_SHA256,
        datasets.BINDING_LOCAL_AREA_MANIFEST_SHA256)
    assert (binding["built_with_model_version"], binding["model_basis"]) == ("2.151.0", "built_with")
    # The 19 October dense cut, as its release manifest at the tag records it (61,723 bytes).
    assert fallback == {
        "path": "microcosm_uk_2024_25_dense.h5", "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "revision": "microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe",
        "sha256": "8e10e130d0260e0b52e2e29902f0502ebdff76a14a3e57d2c876bf4cd8db5872",
        "release_manifest_uri": "https://huggingface.co/datasets/policyengine/populace-uk-private/resolve/"
                                "microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe/releases/"
                                "microcosm-uk-2024-25-dense/release_manifest.json",
        "source_manifest_uri": "hf://dataset/policyengine/populace-uk-private@"
                               "microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe/releases/"
                               "microcosm-uk-2024-25-dense/release_manifest.json",
        "manifest_sha256": "b9dc7cae358b9c965935f83721508594f9fb56a35911ffb0f9216ecb6a799561",
        "built_with_model_version": "2.132.6", "model_basis": "accepted_model_mismatch"}


def test_the_fallback_keeps_its_own_model_and_release_manifest():
    fallback = datasets.DATASETS[FALLBACK_DATASET]
    assert (datasets.BUNDLE_715["model_version"], datasets.BUNDLE_715["core_version"]) == ("2.147.2", "3.33.3")
    assert datasets.BUNDLE_715["model_wheel_sha256"] == datasets.BUNDLE_715["wheels"]["policyengine-uk"]["wheel_sha256"]
    assert fallback["release_manifest"] == datasets.MICROCOSM_RELEASE_MANIFEST_A133
    assert fallback["build_id"] == fallback["revision"] == datasets.MICROCOSM_REVISION_A133


def test_changed_installed_manifest_is_rejected(released):
    spec, versions, _, _, path = released
    path.write_text("{}")
    assert not datasets._certified_by_installed_bundle(spec, versions)
