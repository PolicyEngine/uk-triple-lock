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


def test_provenance_records_the_installed_certified_bundle_and_dataset():
    """The recorded model version is the installed policyengine-uk (and its __version__, where a release has one)."""
    pytest.importorskip("policyengine_uk")
    import policyengine_uk

    p = datasets.provenance(PRIMARY_DATASET)
    installed = importlib.metadata.version("policyengine-uk")
    assert p["model_version"] == installed == engine.package_versions()["policyengine-uk"]
    assert p["model_version"] == getattr(policyengine_uk, "__version__", installed)
    assert p["core_version"] == importlib.metadata.version("policyengine-core")
    assert p["bundle_package"] == "policyengine"
    assert p["bundle_version"] == "6.2.6" == importlib.metadata.version("policyengine")
    assert p["model_version"] == "2.125.1" and p["core_version"] == "3.33.0"
    assert p["certified"] is True and p["certification_bundle"] == datasets.CERTIFIED_BUNDLE
    assert p["dataset"] == PRIMARY_DATASET and p["runtime_dataset"] == "enhanced_frs_2024_25"
    assert p["runtime_dataset_sha256"] == "5ba399ea5ab9a6c7d4e9aaf6c623080beb34d9ad5f330f6244dbad72b8d960b6"
    assert p["release_manifest"]["revision"] == "fdeba38517bd86067f34c0a5d8ed8923efb3b10a"
    assert p["data_version"] == "1.58.0" and p["data_built_with"] == "policyengine-uk 2.122.2"
    assert p["data_build_core_version"] == "3.32.13"


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
    assert datasets._certified_by_installed_bundle(spec, versions)
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
    assert "policyengine[uk]==6.2.6" in dependencies
    assert not [d for d in dependencies if d.startswith(("policyengine-uk==", "policyengine-core=="))]
    lock = (REPO / "requirements-lock.txt").read_text().splitlines()
    pins = {"policyengine": "6.2.6", "policyengine-uk": "2.125.1", "policyengine-core": "3.33.0"}
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
    assert uk_pins == {"policyengine-uk": "==2.125.1", "policyengine-core": "==3.33.0"}


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
