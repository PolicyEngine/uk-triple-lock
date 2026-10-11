"""Certified publication gate, using package metadata and synthetic receipts only."""

from copy import deepcopy
import importlib.metadata
import sys
from types import SimpleNamespace

import pytest

from triple_lock import datasets, pipeline


PINS = {"policyengine": "6.2.6", "policyengine-uk": "2.125.1", "policyengine-core": "3.33.0"}
PRIMARY = "enhanced_frs_2024_25@1.58.0"


@pytest.fixture
def certified(monkeypatch):
    provenance = {"dataset": PRIMARY, "certified": True,
                  "runtime_dataset_sha256": datasets.DATASETS[PRIMARY]["sha256"],
                  "certification_bundle": dict(datasets.CERTIFIED_BUNDLE),
                  "release_manifest": dict(datasets.RELEASE_MANIFEST_1_58_0)}
    versions = dict(PINS)
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", PRIMARY)
    monkeypatch.setattr(pipeline, "package_versions", lambda: dict(versions))
    monkeypatch.setattr(datasets, "provenance", lambda name: deepcopy(provenance))
    monkeypatch.setattr(datasets, "materialize", lambda *a, **kw: pytest.fail("preflight reads no survey bytes"))
    return versions, provenance


def test_certified_preflight_records_verified_bundle_without_loading_model(certified, monkeypatch):
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    _, provenance = certified
    receipt = pipeline.certified_bundle_preflight(log=lambda _: None)
    assert receipt == {"certified_bundle": {"passed": True, "packages": PINS, "primary": provenance}}
    assert receipt["certified_bundle"]["primary"]["certified"] is True
    assert receipt["certified_bundle"]["primary"]["runtime_dataset_sha256"] == datasets.DATASETS[PRIMARY]["sha256"]


@pytest.mark.parametrize("package", PINS)
@pytest.mark.parametrize("version", [None, "uncertified-version"])
def test_certified_preflight_refuses_wrong_or_missing_runtime_version(certified, package, version):
    versions, _ = certified
    if version is None:
        versions.pop(package)
    else:
        versions[package] = version
    with pytest.raises(pipeline.UncertifiedBundle, match="fiscal rebuild requires the certified"):
        pipeline.certified_bundle_preflight(log=lambda _: pytest.fail("no pass log"))


@pytest.mark.parametrize("primary", ["enhanced_frs_2024_25@1.56.16", "populace_uk_2023"])
def test_certified_preflight_refuses_other_primary_before_provenance(certified, monkeypatch, primary):
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", primary)
    monkeypatch.setattr(datasets, "provenance", lambda *a: pytest.fail("wrong primary is refused first"))
    with pytest.raises(pipeline.UncertifiedBundle, match="enhanced_frs_2024_25@1.58.0"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


@pytest.mark.parametrize("certification", [False, None, 1, "true"])
def test_certified_preflight_requires_true_manifest_certification(certified, certification):
    _, provenance = certified
    provenance["certified"] = certification
    with pytest.raises(pipeline.UncertifiedBundle, match="released manifest"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


def test_certified_preflight_refuses_mismatched_provenance_primary(certified):
    _, provenance = certified
    provenance["dataset"] = "enhanced_frs_2024_25@1.56.16"
    with pytest.raises(pipeline.UncertifiedBundle):
        pipeline.certified_bundle_preflight(log=lambda _: None)


def test_certified_preflight_refuses_tampered_installed_release_manifest(tmp_path, monkeypatch):
    """Exercise the real dataset certification helper, without a model import or dataset load."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    versions = {key: datasets.CERTIFIED_BUNDLE[key]
                for key in ("bundle_package", "bundle_version", "model_version", "core_version")}
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", PRIMARY)
    monkeypatch.setattr(pipeline, "package_versions", lambda: dict(PINS))
    monkeypatch.setattr(datasets, "model_versions", lambda: dict(versions))
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: SimpleNamespace(locate_file=lambda path: manifest))
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    monkeypatch.setattr(datasets, "materialize", lambda *a, **kw: pytest.fail("preflight reads no survey bytes"))
    assert datasets.provenance(PRIMARY)["certified"] is False
    with pytest.raises(pipeline.UncertifiedBundle, match="released manifest"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


@pytest.mark.parametrize("entrypoint", ["build", "mean_path_scenarios"])
def test_publication_entrypoint_refuses_uncertified_bundle_before_model_or_jobs(certified, monkeypatch, entrypoint):
    versions, _ = certified
    versions["policyengine-uk"] = "2.123.6"  # receipt-passport capable, but outside the certified bundle
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(pipeline.expected_value, "_handoff", lambda *a, **kw: ("synthetic-binding", {}))
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda *a, **kw: pytest.fail("no model preflight"))
    monkeypatch.setattr(pipeline.jobs, "run_jobs", lambda *a, **kw: pytest.fail("no model jobs"))
    monkeypatch.setattr(pipeline.expected_value, "build_mean_path_scenarios", lambda *a, **kw: pytest.fail("no scenarios"))
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    with pytest.raises(pipeline.UncertifiedBundle):
        getattr(pipeline, entrypoint)(uncertainty_ruling="c", log=lambda _: None)


def test_standalone_mean_paths_record_certification_beside_passport(certified, monkeypatch):
    _, provenance = certified
    passport = {"housing_benefit_guarantee_credit_passport": {"keyed_on": "receipt"}}
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda **kw: passport)
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(pipeline.engine, "base_levels", lambda parameters: {"new_state_pension": 1.})
    monkeypatch.setattr(pipeline.engine, "engine_hashes", lambda: {})
    monkeypatch.setattr(pipeline, "check_unchanged", lambda *a: None)
    monkeypatch.setattr(pipeline.expected_value, "build_mean_path_scenarios", lambda *a, **kw: {"provenance": {}})
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", SimpleNamespace(system=SimpleNamespace(parameters={})))
    result = pipeline.mean_path_scenarios(uncertainty_ruling="c", log=lambda _: None)
    assert result["provenance"]["preflight"] == {
        **passport, "certified_bundle": {"passed": True, "packages": PINS, "primary": provenance}}
