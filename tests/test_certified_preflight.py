"""Certified publication gate, using package metadata and synthetic receipts only."""

from copy import deepcopy
import importlib.metadata
import json
import os
import sys
from types import SimpleNamespace

import pytest

from triple_lock import datasets, pipeline


PINS = {"policyengine": "99.0.0", "policyengine-uk": "2.151.0", "policyengine-core": "3.33.3"}
PRIMARY = "microcosm_uk_2024_25@a6299504"


@pytest.fixture
def certified(monkeypatch):
    # A fictional released carrier, whatever the production pins hold.
    monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, "bundle_version", PINS["policyengine"])
    monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, "manifest_sha256", "a" * 64)
    monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, "certification_url", "https://example.invalid/pull/1")
    monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, "certification_commit", "b" * 40)
    provenance = {"dataset": PRIMARY, "certified": True,
                  "runtime_dataset_sha256": datasets.DATASETS[PRIMARY]["sha256"],
                  "certification_bundle": dict(datasets.CERTIFIED_BUNDLE),
                  "release_manifest": dict(datasets.MICROCOSM_RELEASE_MANIFEST)}
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
    with pytest.raises(pipeline.UncertifiedBundle, match="Microcosm a6299504"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


@pytest.mark.parametrize("certification", [False, None, 1, "true"])
def test_certified_preflight_requires_true_manifest_certification(certified, certification):
    _, provenance = certified
    provenance["certified"] = certification
    with pytest.raises(pipeline.UncertifiedBundle, match="d2011|released manifest"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


def test_certified_preflight_refuses_mismatched_provenance_primary(certified):
    _, provenance = certified
    provenance["dataset"] = "enhanced_frs_2024_25@1.56.16"
    with pytest.raises(pipeline.UncertifiedBundle):
        pipeline.certified_bundle_preflight(log=lambda _: None)


@pytest.mark.parametrize("field", ["certification_url", "certification_commit"])
def test_certified_preflight_refuses_a_release_without_its_certifying_pull_request(certified, monkeypatch, field):
    monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, field, None)
    monkeypatch.setattr(datasets, "provenance", lambda *a: pytest.fail("an unnamed certifier is refused first"))
    with pytest.raises(pipeline.UncertifiedBundle, match="certifying pull"):
        pipeline.certified_bundle_preflight(log=lambda _: pytest.fail("no pass log"))


def test_certified_preflight_refuses_tampered_installed_release_manifest(tmp_path, monkeypatch):
    """Exercise the real dataset certification helper, without a model import or dataset load. The carrier's pinned
    identities and installed versions match, pending or filled alike, so the preflight reaches provenance: once the
    pair is filled the tampered manifest bytes refuse there, and while its local-area cut is pending the cut does."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    for key, value in (("bundle_version", PINS["policyengine"]), ("manifest_sha256", "a" * 64),
                       ("certification_url", "https://example.invalid/pull/1"), ("certification_commit", "b" * 40)):
        monkeypatch.setitem(datasets.CERTIFIED_BUNDLE, key, value)
    versions = {key: datasets.CERTIFIED_BUNDLE[key]
                for key in ("bundle_package", "bundle_version", "model_version", "core_version")}
    monkeypatch.setattr(pipeline, "PRIMARY_DATASET", PRIMARY)
    monkeypatch.setattr(pipeline, "package_versions", lambda: dict(PINS))
    monkeypatch.setattr(datasets, "model_versions", lambda: dict(versions))
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: SimpleNamespace(locate_file=lambda path: manifest))
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    monkeypatch.setattr(datasets, "materialize", lambda *a, **kw: pytest.fail("preflight reads no survey bytes"))
    assert datasets.provenance(PRIMARY)["certified"] is False
    with pytest.raises(pipeline.UncertifiedBundle, match="installed released manifest does not certify the pinned pair"):
        pipeline.certified_bundle_preflight(log=lambda _: None)


@pytest.mark.parametrize("entrypoint", ["build", "mean_path_scenarios", "scenario"])
def test_publication_entrypoint_refuses_uncertified_bundle_before_model_or_jobs(certified, monkeypatch, entrypoint):
    versions, _ = certified
    versions["policyengine-uk"] = "2.123.6"  # receipt-passport capable, but outside the certified bundle
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(pipeline.expected_value, "_handoff", lambda *a, **kw: ("synthetic-binding", {}))
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda *a, **kw: pytest.fail("no model preflight"))
    monkeypatch.setattr(pipeline.jobs, "run_jobs", lambda *a, **kw: pytest.fail("no model jobs"))
    monkeypatch.setattr(pipeline, "run_scenarios", lambda *a, **kw: pytest.fail("no scenarios"))
    monkeypatch.setattr(pipeline.expected_value, "build_mean_path_scenarios", lambda *a, **kw: pytest.fail("no scenarios"))
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    with pytest.raises(pipeline.UncertifiedBundle):
        if entrypoint == "scenario":
            pipeline.scenario("obr_premium", log=lambda _: None)
        else:
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


def test_standalone_scenario_records_certification_beside_passport(certified, monkeypatch):
    _, provenance = certified
    passport = {"housing_benefit_guarantee_credit_passport": {"keyed_on": "receipt"}}
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda **kw: passport)
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(pipeline, "run_scenarios", lambda central, names, **kw: {
        names[0]: ({"id": names[0], "label": "Synthetic OBR wedge", "source": "synthetic", "specified_rates": {}},
                   {"model": {"dataset": provenance}, "synthetic": True})})
    monkeypatch.setattr(pipeline, "check_unchanged", lambda *a: None)
    monkeypatch.setattr(pipeline.engine, "engine_hashes", lambda: {})
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    result = pipeline.scenario("obr_premium", log=lambda _: None)
    assert result["provenance"]["preflight"] == {
        **passport, "certified_bundle": {"passed": True, "packages": PINS, "primary": provenance}}
    assert result["provenance"]["datasets"]["primary"] == provenance
    assert result["run"] == {"synthetic": True}


def ageing_setup(certified, tmp_path, monkeypatch, *, central_only=False):
    from triple_lock import ageing_validation as AV

    _, provenance = certified
    plan = {"jobs": [("path", {})], "modes": ["both"], "sample": {}, "W": {}, "W0": 1.,
            "central_only": central_only, "dataset": PRIMARY,
            "source_provenance": {"model": deepcopy(provenance), "datasets": {"primary": PRIMARY},
                                  "packages": dict(PINS)}}
    monkeypatch.setattr(AV, "REPO", tmp_path)
    monkeypatch.setattr(AV, "validation_plan", lambda *a: plan)
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: {"synthetic_passport": {"passed": True}})
    from triple_lock import jobs
    monkeypatch.setattr(jobs, "run_jobs", lambda *a, **kw: [{"synthetic": True}])
    monkeypatch.setattr(AV, "summarise", lambda *a: {
        "fixed_inputs": {"both": {"state_pension_accounting": {"max_identity_error_gbp": 0.0123456789}}},
        "synthetic_aggregate": True})
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    output = tmp_path / ".cache" / "ageing.json"
    output.parent.mkdir()
    return AV, plan, output, provenance


@pytest.mark.parametrize("central_only", [False, True])
def test_ageing_reports_require_certification_keep_receipt_and_redact_diagnostics(certified, tmp_path, monkeypatch, central_only):
    AV, plan, output, provenance = ageing_setup(certified, tmp_path, monkeypatch, central_only=central_only)
    if central_only:
        plan["source_provenance"] = {}  # the preliminary central path needs no rebuilt source
    argv = ["-o", str(output)] + (["--central-only"] if central_only else [])
    assert AV.main(argv) == 0
    receipt = json.loads(output.read_text())
    assert receipt["provenance"]["preflight"]["certified_bundle"]["primary"] == provenance
    assert receipt["provenance"]["preflight"]["synthetic_passport"]["passed"] is True
    assert "max_identity_error_gbp" not in output.read_text()
    assert "0.0123456789" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600
    assert list(output.parent.glob(".ageing.json.*.tmp")) == []


@pytest.mark.parametrize("central_only", [False, True])
def test_ageing_rejects_uncertified_runtime_before_passport_or_jobs(certified, tmp_path, monkeypatch, central_only):
    AV, _, output, _ = ageing_setup(certified, tmp_path, monkeypatch, central_only=central_only)
    versions, _ = certified
    versions["policyengine-core"] = "3.32.13"
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: pytest.fail("no model preflight"))
    from triple_lock import jobs
    monkeypatch.setattr(jobs, "run_jobs", lambda *a, **kw: pytest.fail("no survey jobs"))
    argv = ["-o", str(output)] + (["--central-only"] if central_only else [])
    with pytest.raises(pipeline.UncertifiedBundle):
        AV.main(argv)
    assert not output.exists()


@pytest.mark.parametrize("field,value", [("certified", False), ("certified", 1), ("model_version", "2.120.0"),
                                        ("core_version", "3.32.13"), ("bundle_version", "6.2.5"),
                                        ("runtime_dataset_sha256", "0" * 64), ("data_version", "1.56.16"),
                                        ("certification_bundle", {}), ("release_manifest", {})])
def test_ageing_paired_source_rejects_other_certification_before_model_jobs(certified, tmp_path, monkeypatch, field, value):
    AV, plan, output, _ = ageing_setup(certified, tmp_path, monkeypatch)
    plan["source_provenance"]["model"][field] = value
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: pytest.fail("no model preflight"))
    from triple_lock import jobs
    monkeypatch.setattr(jobs, "run_jobs", lambda *a, **kw: pytest.fail("no survey jobs"))
    with pytest.raises(pipeline.UncertifiedBundle, match="source-results rebuilt"):
        AV.main(["-o", str(output)])
    assert not output.exists()


@pytest.mark.parametrize("changed", ["missing_provenance", "dataset_reference", "primary_dataset", "packages"])
def test_ageing_paired_source_refuses_inconsistent_rebuild_provenance(certified, tmp_path, monkeypatch, changed):
    AV, plan, output, _ = ageing_setup(certified, tmp_path, monkeypatch)
    if changed == "missing_provenance":
        plan.pop("source_provenance")
    elif changed == "dataset_reference":
        plan["source_provenance"]["datasets"]["primary"] = "enhanced_frs_2024_25@1.56.16"
    elif changed == "primary_dataset":
        plan["dataset"] = "populace_uk_2023"
    else:
        plan["source_provenance"]["packages"]["policyengine"] = "6.2.5"
    with pytest.raises(pipeline.UncertifiedBundle, match="source-results rebuilt"):
        AV.main(["-o", str(output)])
    assert not output.exists()


def test_ageing_plan_does_not_check_certification_or_write_output(certified, tmp_path, monkeypatch):
    AV, _, output, _ = ageing_setup(certified, tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "certified_bundle_preflight", lambda: pytest.fail("plan starts no preflight"))
    assert AV.main(["--plan", "-o", str(tmp_path / "data/results.json")]) == 0
    assert not output.exists()
    assert not (tmp_path / "data/results.json").exists()


@pytest.mark.parametrize("target", ["publication", "results", "private_results", "symlink", "hardlink", "cache_alias"])
def test_ageing_rejects_publication_and_alias_destinations_before_model_jobs(certified, tmp_path, monkeypatch, target):
    AV, _, output, _ = ageing_setup(certified, tmp_path, monkeypatch, central_only=True)
    publication = tmp_path / "data"
    publication.mkdir()
    if target == "publication":
        output = publication / "ageing.json"
    elif target == "results":
        output = publication / "results.json"
    elif target == "private_results":
        output = output.parent / "results.json"
    elif target == "symlink":
        output.symlink_to(publication / "results.json")
    elif target == "hardlink":
        original = publication / "results.json"
        original.write_text("preserve publication")
        os.link(original, output)
    else:
        output.parent.rmdir()
        output.parent.symlink_to(publication, target_is_directory=True)
    monkeypatch.setattr(pipeline, "certified_bundle_preflight", lambda: pytest.fail("invalid output starts no preflight"))
    with pytest.raises(ValueError, match="private workspace"):
        AV.main(["--central-only", "-o", str(output)])
    if target == "hardlink":
        assert original.read_text() == "preserve publication"


def test_ageing_atomic_writer_uses_exclusive_private_temporary_file(tmp_path, monkeypatch):
    from triple_lock import ageing_validation as AV

    monkeypatch.setattr(AV, "REPO", tmp_path)
    destination = tmp_path / ".cache" / "ageing.json"
    destination.parent.mkdir()
    destination.write_text("previous receipt")
    destination.chmod(0o644)
    publication = tmp_path / "data/results.json"
    publication.parent.mkdir()
    publication.write_text("preserve publication")
    predictable = destination.parent / ".ageing.json.tmp"
    predictable.symlink_to(publication)
    AV.write_private_report({"synthetic": True}, destination)
    assert json.loads(destination.read_text()) == {"synthetic": True}
    assert destination.stat().st_mode & 0o777 == 0o600
    assert publication.read_text() == "preserve publication"
    assert predictable.is_symlink()
    assert list(destination.parent.glob(".ageing.json.*.tmp")) == []
