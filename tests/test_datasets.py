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


def test_provenance_records_the_installed_model_and_that_it_is_uncertified():
    """The recorded model version is the installed policyengine-uk (and its __version__, where a release has one)."""
    pytest.importorskip("policyengine_uk")
    import policyengine_uk

    p = datasets.provenance(PRIMARY_DATASET)
    installed = importlib.metadata.version("policyengine-uk")
    assert p["model_version"] == installed == engine.package_versions()["policyengine-uk"]
    assert p["model_version"] == getattr(policyengine_uk, "__version__", installed)
    assert p["core_version"] == importlib.metadata.version("policyengine-core")
    assert p["certified"] is False and p["certification"].startswith("uncertified")
    assert p["dataset"] == PRIMARY_DATASET and p["runtime_dataset"] == "enhanced_frs_2024_25"
    assert p["runtime_dataset_sha256"] == datasets.DATASETS[PRIMARY_DATASET]["sha256"]


def test_the_pins_agree():
    """pyproject.toml and requirements-lock.txt pin the same policyengine-uk, and the environment has it."""
    import tomllib

    from triple_lock.config import REPO

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    pins = [d for d in pyproject["project"]["optional-dependencies"]["uk"] if d.startswith("policyengine-uk==")]
    lock = [line for line in (REPO / "requirements-lock.txt").read_text().splitlines()
            if line.startswith("policyengine-uk==")]
    assert len(pins) == 1 and lock == pins
    assert not [line for line in (REPO / "requirements-lock.txt").read_text().splitlines()
                if line.startswith("policyengine==")]
    with pytest.raises(importlib.metadata.PackageNotFoundError):  # policyengine.py would refuse 2.118.0
        importlib.metadata.version("policyengine")
    try:
        installed = importlib.metadata.version("policyengine-uk")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("policyengine-uk is not installed")
    assert pins == [f"policyengine-uk=={installed}"]
