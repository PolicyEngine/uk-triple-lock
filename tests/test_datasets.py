"""The pinned datasets and the provenance every run records (no model run, no download)."""

import hashlib
import importlib.metadata
import re

import pytest

from triple_lock import datasets, engine
from triple_lock.config import PRIMARY_DATASET, SENSITIVITY_DATASET


def test_every_dataset_is_pinned_to_a_revision_and_a_sha256():
    assert PRIMARY_DATASET in datasets.DATASETS and SENSITIVITY_DATASET in datasets.DATASETS
    for name, d in datasets.DATASETS.items():
        assert re.fullmatch(r"[0-9a-f]{64}", d["sha256"]), name
        assert d["revision"] and d["repo_id"].startswith("policyengine/"), name
        assert datasets.uri(name) == f"hf://{d['repo_id']}/{d['path']}@{d['revision']}"
    assert datasets.resolve(None) == PRIMARY_DATASET
    with pytest.raises(KeyError):
        datasets.resolve("enhanced_frs_2099")


def _fake(content):
    def download(spec, directory):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / spec["path"]
        path.write_bytes(content)
        return path
    return download


def test_materialize_fetches_once_and_checks_the_hash(tmp_path, monkeypatch):
    content = b"not really an h5 file"
    pinned = {**datasets.DATASETS[PRIMARY_DATASET], "sha256": hashlib.sha256(content).hexdigest()}
    monkeypatch.setitem(datasets.DATASETS, PRIMARY_DATASET, pinned)
    calls = []

    def download(spec, directory):
        calls.append(spec["revision"])
        return _fake(content)(spec, directory)

    path = datasets.materialize(None, store=tmp_path, download=download)
    assert path.read_bytes() == content and path.parent == tmp_path
    assert datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=download) == path
    assert calls == [pinned["revision"]]  # the second call reuses the verified file
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".download-")]


def test_materialize_refuses_a_file_that_does_not_match_its_pin(tmp_path):
    with pytest.raises(datasets.DatasetMismatch, match="wrong SHA-256"):
        datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=_fake(b"something else"))
    assert not datasets.local_path(PRIMARY_DATASET, tmp_path).exists()
    # A file already in the store that has changed is not used either.
    path = datasets.local_path(PRIMARY_DATASET, tmp_path)
    path.write_bytes(b"tampered")
    with pytest.raises(datasets.DatasetMismatch, match="does not hash to the pin"):
        datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=_fake(b"unused"))


def test_provenance_records_pending_exact_candidate_without_claiming_certification():
    pytest.importorskip("policyengine_uk")
    p = datasets.provenance(PRIMARY_DATASET)
    assert p["model_version"] == "2.151.0" == engine.package_versions()["policyengine-uk"]
    assert p["core_version"] == "3.33.3"
    assert p["bundle_version"] == importlib.metadata.version("policyengine")
    assert p["certified"] is False and "d2011" in p["certification"]
    assert "certification_bundle" not in p
    assert p["runtime_dataset"] == "microcosm_uk_2024_25"
    assert p["runtime_dataset_sha256"] == "b96a8cd625b645a409c063b1de5158532708a2f0d3c3897a794a8fb0bbd5064e"
    assert p["dataset"] == "microcosm_uk_2024_25@a6299504"
    assert p["release_manifest"] == datasets.MICROCOSM_RELEASE_MANIFEST
    assert p["data_version"] == "0.1.0"
    assert p["data_build_id"] == datasets.MICROCOSM_REVISION
    assert p["ageing_anchor"]["calibration_year"] is None


@pytest.mark.parametrize("name", ["enhanced_frs_2024_25@1.56.16", SENSITIVITY_DATASET])
def test_historical_pilot_and_microcosm_are_uncertified_under_this_bundle(name):
    pytest.importorskip("policyengine_uk")
    p = datasets.provenance(name)
    assert p["certified"] is False and p["certification"].startswith("uncertified")
    assert "certification_bundle" not in p


@pytest.mark.parametrize("changed", [
    {"model_version": "2.120.0"}, {"core_version": "3.32.16"},
    {"bundle_version": None}, {"bundle_version": "6.2.5"},
])
def test_certification_requires_the_exact_installed_bundle_model_and_core(monkeypatch, changed):
    versions = {key: datasets.CERTIFIED_BUNDLE[key]
                for key in ("bundle_package", "bundle_version", "model_version", "core_version")}
    monkeypatch.setattr(datasets, "model_versions", lambda: {**versions, **changed})
    assert datasets.provenance(PRIMARY_DATASET)["certified"] is False


def test_certification_rejects_different_artifact_bytes_and_changed_bundle_manifest(monkeypatch, tmp_path):
    pytest.importorskip("policyengine_uk")
    spec = datasets.DATASETS[PRIMARY_DATASET]
    versions = datasets.model_versions()
    assert not datasets._certified_by_installed_bundle(spec, versions)
    assert not datasets._certified_by_installed_bundle({**spec, "sha256": "0" * 64}, versions)
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text("{}")
    class ChangedDistribution:
        def locate_file(self, name):
            return bad_manifest
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: ChangedDistribution())
    assert not datasets._certified_by_installed_bundle(spec, versions)


def test_the_pins_agree():
    """The project pins the certified carrier; its UK-extra pins and all three installed versions match the lock."""
    import tomllib

    from triple_lock.config import REPO

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["optional-dependencies"]["uk"]
    assert "policyengine==6.10.1" in dependencies
    assert "policyengine-uk==2.151.0" in dependencies
    assert "policyengine-core==3.33.3" in dependencies
    assert not any(d.startswith("policyengine[uk]") for d in dependencies)
    lock = (REPO / "requirements-lock.txt").read_text().splitlines()
    pins = {"policyengine": "6.10.1", "policyengine-uk": "2.151.0", "policyengine-core": "3.33.3"}
    for package, version in pins.items():
        assert f"{package}=={version}" in lock
    try:
        installed = {package: importlib.metadata.version(package) for package in pins}
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("certified policyengine UK bundle is not installed")
    assert installed == pins
    from packaging.requirements import Requirement
    bundled = [Requirement(r) for r in importlib.metadata.requires("policyengine")]
    uk_pins = {r.name: str(r.specifier) for r in bundled
               if r.marker and r.marker.evaluate({"extra": "uk"}) and r.name in pins}
    assert uk_pins != {"policyengine-uk": "==2.151.0", "policyengine-core": "==3.33.3"}
    # The released extra differs: installing it would conflict with the candidate model pin.


def test_materialize_hashes_each_file_once_per_process(tmp_path, monkeypatch):
    """A job loads its dataset three or four times: the file is hashed once while unchanged, and again once it
    changes (here, replaced by a file that no longer matches, which fails)."""
    content = b"pinned bytes"
    pinned = {**datasets.DATASETS[PRIMARY_DATASET], "sha256": hashlib.sha256(content).hexdigest()}
    monkeypatch.setitem(datasets.DATASETS, PRIMARY_DATASET, pinned)
    calls = []
    real = datasets.sha256_file
    monkeypatch.setattr(datasets, "sha256_file", lambda p, *a: calls.append(p) or real(p, *a))
    path = datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=_fake(content))
    hashed = len(calls)
    for _ in range(3):
        assert datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=_fake(content)) == path
    assert len(calls) == hashed
    path.write_bytes(b"changed bytes!")  # a different size: a new stamp
    with pytest.raises(datasets.DatasetMismatch):
        datasets.materialize(PRIMARY_DATASET, store=tmp_path, download=_fake(content))
