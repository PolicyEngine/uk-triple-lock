"""A completed full cold path survives interrupted repeat coordinators."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("resume_determinism", SCRIPTS / "resume_model_v2_determinism.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def checkpoint(tmp_path, monkeypatch):
    driver = helper.driver
    data = tmp_path / "synthetic.h5"
    data.write_bytes(b"no survey records: input fingerprint fixture")
    provenance = {"full_spec_sha256": "spec", "package_sha256": "packages",
                  "packages": {"policyengine-uk": "2.120.0", "policyengine-core": "3.32.16"},
                  "python": "version", "engine_file_sha256": "engine", "engine_semantics_sha256": "semantics"}
    monkeypatch.setattr(helper, "current_provenance", lambda specification: provenance)
    monkeypatch.setattr(driver, "committed_source_fingerprint", lambda *args: "scientific")
    monkeypatch.setattr(driver, "source_fingerprint", lambda *args: "scientific")
    monkeypatch.setattr(helper.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="d" * 40))
    aggregates = {"saving_bn": {str(year): {"uk": {"net": 1.}, "gb": {"net": .9}} for year in helper.YEARS},
                  "totals_bn": {}}
    row = {"label": "current_first", "calculation_head": "f" * 40, "dataset": driver.MICROCOSM,
           "treatment": "both", "passed": True, "cold_cache": True,
           "minimum_contributing_records": 10, "calculated_fiscal_years": helper.YEARS,
           "fiscal_output_years": helper.YEARS, "scientific_check_years": helper.YEARS,
           "aggregate_fingerprint_years": helper.YEARS, "dataset_sha256": driver.digest(data),
           "driver_sha256": driver.digest(Path(driver.__file__)), "source_sha256": "scientific",
           "aggregates": aggregates, "aggregate_sha256": driver.fingerprint(aggregates),
           "cells": {"2039": {"uk": {"saving": {"net": 20}}, "gb": {"saving": {"net": 10}}}},
           "resources_before_actual_job": {"available_bytes": 2**40}, **provenance}
    first = tmp_path / "first.json"
    first.write_text(json.dumps(row))
    args = SimpleNamespace(current_head="f" * 40, git_dir=tmp_path / ".git-e")
    return first, args, data, row


def test_completed_first_is_reused_without_relabelling_or_changing_its_quantities(checkpoint, tmp_path):
    first, args, data, row = checkpoint
    assert helper.validate_first_receipt(first, args, tmp_path, {}, data) == row


@pytest.mark.parametrize("field", (
    "label", "calculation_head", "dataset", "treatment", "passed", "cold_cache",
    "minimum_contributing_records", "calculated_fiscal_years", "fiscal_output_years",
    "scientific_check_years", "aggregate_fingerprint_years", "dataset_sha256", "driver_sha256",
    "full_spec_sha256", "package_sha256", "packages", "python", "engine_file_sha256", "engine_semantics_sha256",
))
def test_resume_rejects_changed_inputs_packages_worker_or_incomplete_first(checkpoint, tmp_path, field):
    first, args, data, row = checkpoint
    row[field] = "changed"
    first.write_text(json.dumps(row))
    with pytest.raises(ValueError, match=field):
        helper.validate_first_receipt(first, args, tmp_path, {}, data)


def test_resume_rejects_modified_quantities_even_with_passed_flags(checkpoint, tmp_path):
    first, args, data, row = checkpoint
    row["aggregates"]["saving_bn"]["2039"]["uk"]["net"] = 2.
    first.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="aggregate fingerprint"):
        helper.validate_first_receipt(first, args, tmp_path, {}, data)


@pytest.mark.parametrize("changed_source", ("committed", "worktree", "receipt"))
def test_resume_rejects_changed_final_scientific_source(checkpoint, tmp_path, monkeypatch, changed_source):
    first, args, data, row = checkpoint
    if changed_source == "committed":
        monkeypatch.setattr(helper.driver, "committed_source_fingerprint",
                            lambda git_dir, head: "scientific" if head == args.current_head else "changed")
    elif changed_source == "worktree":
        monkeypatch.setattr(helper.driver, "source_fingerprint", lambda *args: "changed")
    else:
        row["source_sha256"] = "changed"
        first.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="final scientific source"):
        helper.validate_first_receipt(first, args, tmp_path, {}, data)


def test_resume_invokes_only_missing_repeat_with_the_unchanged_worker_and_a_fresh_archive(
        checkpoint, tmp_path, monkeypatch):
    from triple_lock import datasets

    first, args, data, row = checkpoint
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / "specs.json"
    specs.write_text('{"central":{}}')
    args = SimpleNamespace(**vars(args), first_receipt=first, specs=specs, validate_only=False,
                           reuse_historical_receipts=[], run_label="retry", minimum_available_gib=44.,
                           historical=tmp_path / "retained.json", out=tmp_path / "public.json")
    monkeypatch.setattr(datasets, "materialize", lambda *args, **kwargs: data)
    historical = [{"label": "d_legacy"}, {"label": "d_both"}]
    monkeypatch.setattr(helper.driver, "load_historical_receipts", lambda *args: historical)
    monkeypatch.setattr(helper.driver, "resource_receipt", lambda: {"available_bytes": 2**40})
    configurations, writes = [], []

    def archive(workspace, git_dir, head, label):
        source = workspace / label
        source.mkdir()
        return source

    def child(command, workspace, source, private_log, stop):
        assert command[1] == str(Path(helper.driver.__file__).resolve())
        assert command[2] == "--worker"
        configuration = json.loads(Path(command[-2]).read_text())
        configurations.append(configuration)
        Path(command[-1]).write_text(json.dumps({"label": "current_repeat"}))
        return 0

    monkeypatch.setattr(helper.driver, "archive_source", archive)
    monkeypatch.setattr(helper.driver, "run_checked_child", child)
    monkeypatch.setattr(helper.driver, "source_correspondence", lambda *args: {"passed": True})
    monkeypatch.setattr(helper.driver, "write_public", lambda out, runs, *args, **kwargs: writes.append(runs))
    helper.main(args)
    assert len(configurations) == 1
    assert configurations[0]["label"] == "current_repeat"
    assert configurations[0]["cold_cache"] and configurations[0]["honour_current_head_control"] is False
    assert "fiscal_output_years" not in configurations[0]
    assert [run["label"] for run in writes[0]] == ["d_legacy", "d_both", "current_first", "current_repeat"]
    assert writes[0][2] == row
    assert args.workers == 1


def test_validation_only_never_admits_a_model_worker(checkpoint, tmp_path, monkeypatch):
    from triple_lock import datasets

    first, args, data, row = checkpoint
    monkeypatch.chdir(tmp_path)
    specs = tmp_path / "specs.json"
    specs.write_text('{"central":{}}')
    args = SimpleNamespace(**vars(args), first_receipt=first, specs=specs, validate_only=True,
                           reuse_historical_receipts=[], out=tmp_path / "public.json")
    monkeypatch.setattr(datasets, "materialize", lambda *args, **kwargs: data)
    monkeypatch.setattr(helper.driver, "load_historical_receipts", lambda *args: [])
    monkeypatch.setattr(helper.driver, "cold_pool", lambda *args: pytest.fail("validation admitted a model worker"))
    helper.main(args)
    assert not args.out.exists()
