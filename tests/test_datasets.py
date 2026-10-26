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


def binding_release_installed():
    """Whether the installed carrier is the binding release datasets.py pins (never while it is pending)."""
    return (datasets.BINDING_BUNDLE_VERSION is not None
            and datasets.model_versions()["bundle_version"] == datasets.BINDING_BUNDLE_VERSION)


def test_provenance_records_the_exact_pair_and_certifies_only_its_installed_release():
    """Pending, or filled but not yet installed: nothing certifies. Filled and installed (CI installs the lock),
    the release must certify the pinned pair: the fill's pins and the installed bytes agree."""
    pytest.importorskip("policyengine_uk")
    p = datasets.provenance(PRIMARY_DATASET)
    installed = binding_release_installed()
    assert p["model_version"] == "2.151.0" == engine.package_versions()["policyengine-uk"]
    assert p["core_version"] == "3.33.3"
    assert p["bundle_version"] == importlib.metadata.version("policyengine")
    assert p["certified"] is installed
    if installed:
        assert p["certification"] == f"policyengine.py {datasets.BINDING_BUNDLE_VERSION} UK bundle certification"
        assert p["certification_bundle"] == datasets.CERTIFIED_BUNDLE
    else:
        assert "d2011" in p["certification"] and "certification_bundle" not in p
    assert p["runtime_dataset"] == "microcosm_uk_2024_25"
    assert p["runtime_dataset_sha256"] == "b96a8cd625b645a409c063b1de5158532708a2f0d3c3897a794a8fb0bbd5064e"
    assert p["dataset"] == "microcosm_uk_2024_25@a6299504"
    assert p["release_manifest"] == datasets.MICROCOSM_RELEASE_MANIFEST
    assert p["data_version"] == "0.1.0"
    assert p["data_build_id"] == datasets.MICROCOSM_REVISION
    assert p["ageing_anchor"]["year"] == p["ageing_anchor"]["calibration_year"] == 2025


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
    assert datasets._certified_by_installed_bundle(spec, versions) is binding_release_installed()
    assert not datasets._certified_by_installed_bundle({**spec, "sha256": "0" * 64}, versions)
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text("{}")
    class ChangedDistribution:
        def locate_file(self, name):
            return bad_manifest
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: ChangedDistribution())
    assert not datasets._certified_by_installed_bundle(spec, versions)


def lock_pins():
    from packaging.utils import canonicalize_name

    from triple_lock.config import REPO

    lines = (REPO / "requirements-lock.txt").read_text().splitlines()
    return {canonicalize_name(name): version for name, version in
            (line.split("==", 1) for line in lines if "==" in line and not line.startswith("#"))}


def test_the_pins_agree():
    """The project pins the carrier (the preparatory one while the release is pending, the release once filled), the
    pair's model and core; all three installed versions match the lock."""
    import tomllib

    from packaging.requirements import Requirement

    from triple_lock.config import REPO

    carrier = datasets.BINDING_BUNDLE_VERSION or datasets.PREPARATORY_CARRIER
    pins = {"policyengine": carrier, "policyengine-uk": "2.151.0", "policyengine-core": "3.33.3"}
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["optional-dependencies"]["uk"]
    assert {f"{package}=={version}" for package, version in pins.items()} <= set(dependencies)
    assert not any(d.startswith("policyengine[uk]") for d in dependencies)
    assert {package: lock_pins().get(package) for package in pins} == pins
    try:
        installed = {package: importlib.metadata.version(package) for package in pins}
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("certified policyengine UK bundle is not installed")
    if datasets.BINDING_BUNDLE_VERSION is not None and installed["policyengine"] != carrier:
        pytest.skip(f"the filled carrier {carrier} is not installed yet: re-resolve and install the lock")
    assert installed == pins
    bundled = [Requirement(r) for r in importlib.metadata.requires("policyengine") or []]
    uk_extra = {r.name: r.specifier for r in bundled
                if r.marker and r.marker.evaluate({"extra": "uk"}) and r.name in pins}
    if datasets.BINDING_BUNDLE_VERSION is None:
        # The preparatory carrier's extra pins its previous model: installing it would conflict with the pair's.
        assert {name: str(specifier) for name, specifier in uk_extra.items()} != {
            "policyengine-uk": "==2.151.0", "policyengine-core": "==3.33.3"}
    else:
        # The release carries the pair, so whatever its extra pins must admit the pair's model and core.
        assert all(specifier.contains(pins[name]) for name, specifier in uk_extra.items())


def test_the_lock_satisfies_the_installed_carrier_s_own_requirements():
    """The fill bumps only the carrier pin; a re-resolved lock (docs/REBUILD.md) must still satisfy what that
    carrier requires outside its extras."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    pins = lock_pins()
    try:
        installed = importlib.metadata.version("policyengine")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("policyengine is not installed")
    if installed != pins.get("policyengine"):
        pytest.skip(f"installed policyengine {installed} is not the lock's")
    unmet = [str(r) for r in map(Requirement, importlib.metadata.requires("policyengine") or [])
             if (r.marker is None or r.marker.evaluate({"extra": ""}))
             and canonicalize_name(r.name) in pins
             and not r.specifier.contains(pins[canonicalize_name(r.name)], prereleases=True)]
    assert unmet == []


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


@pytest.mark.parametrize("name", sorted(datasets.DATASETS))
def test_a_declared_calibration_year_is_the_ageing_anchor(name):
    """The rake never moves calibrated weights: where a build has a calibration year, static ageing anchors there."""
    anchor = datasets.ageing_anchor(name)
    if anchor["calibration_year"] is not None:
        assert anchor["year"] == anchor["calibration_year"]
    assert anchor["year"] >= 2024 and anchor["source"]
