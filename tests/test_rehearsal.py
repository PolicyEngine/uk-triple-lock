"""Publication boundaries and real frozen-C2 validation; synthetic engine only."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from triple_lock import expected_value as EV, pipeline, ts_uncertainty as TU
from test_uncertainty_adapter import artifact, backtest, base_artifact, fake_engine  # noqa: F401


def dry_artifact(artifact, monkeypatch):
    central, output, manifest = artifact
    scores = backtest()
    scores.update(scoring_head="f" * 40, input_hashes=TU.handoff_input_hashes(), origins={"B": [2010, 2011]})
    outcome = TU.adequacy(scores, screen="c2")
    binding_inputs = {"ready": False, "complete_origins": scores["origins"]["B"]}
    manifest.update(TU.c2_metadata(scores, outcome, binding_inputs, binding=False))
    for data in manifest["forms"].values():
        data.update(fiscal_eligible=False, diagnostic_only=True)
    (output / "handoff.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(TU, "binding_input_provenance", lambda **kw: binding_inputs)
    return central, output, manifest


def test_rehearsal_executes_bounded_primary_and_exact_paired_specs(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    calls = []
    result = EV.rehearsal_sample(central, output, runner=fake_engine(calls), log=lambda _: None)
    assert [len(jobs) for jobs, _ in calls] == [20, 2]
    assert [kwargs["workers"] for _, kwargs in calls] == [3, 2]
    efrs = {spec["id"]: spec for _, spec in calls[0][0]}
    for _, spec in calls[1][0]:
        assert {k: v for k, v in spec.items() if k != "dataset"} == efrs[spec["id"]]
    assert result["provenance"]["full_design_unique_runs"] == 161
    assert result["provenance"]["requested_ruling"] == "c"
    assert result["provenance"]["form"] == TU.PRIMARY_FORM
    assert result["provenance"]["run_kind"] == "rehearsal"
    assert not result["expected_value_authorized"]
    assert not result["quote_eligible"]
    assert result["identical_rates_check"] == {"performed": True, "passed": True}
    assert result["completed_job_counts"] == {"primary": 20, "sensitivity": 2}
    assert result["invariants"] == {"all_engine_jobs_completed": True, "requested_job_counts_returned": True}
    assert not {"expected_value", "estimates", "paired_difference", "saving_bn"} & result.keys()


def test_rehearsal_sample_receipt_omits_raw_engine_diagnostics_and_extrema(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    synthetic = fake_engine([])

    def diagnostic_engine(requested, **kwargs):
        runs = synthetic(requested, **kwargs)
        for run in runs:
            run.update(
                checks={"max_proportionality_error_gbp": 0.00123456789012345,
                        "max_additional_state_pension_gap_gbp": 0.00098765432109876,
                        "employer_ni_incidence_bn": {"triple_lock": 0.0, "burnham_2030": 0.0},
                        "future_record_diagnostic": {"person_value": 987654321.125}},
                model={"future_private_value": 123456789.875},
                fixed_inputs={"calculated_fiscal_years": list(EV.HORIZON), "private_person_value": 765432198.125},
                concentration_top10_by_year={2039: {"records": 10, "contribution_bn": 987654321.625}},
            )
        return runs

    receipt = EV.rehearsal_sample(central, output, runner=diagnostic_engine, log=lambda _: None)
    assert set(receipt) == {"rehearsal", "run_kind", "quote_eligible", "expected_value_authorized",
                            "provenance", "indices", "sensitivity_indices", "completed_job_counts",
                            "invariants", "identical_rates_check"}
    serialized = json.dumps(receipt)
    for private_value in ("max_proportionality_error_gbp", "max_additional_state_pension_gap_gbp",
                          "employer_ni_incidence_bn", "future_record_diagnostic", "future_private_value",
                          "private_person_value", "concentration_top10_by_year", "987654321.625",
                          "0.00123456789012345", "0.00098765432109876",
                          "987654321.125", "123456789.875", "765432198.125"):
        assert private_value not in serialized


def test_rehearsal_sample_preserves_identical_rates_validation(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    with pytest.raises(AssertionError, match="identical rates"):
        EV.rehearsal_sample(central, output, runner=fake_engine([], broken_zero=True), log=lambda _: None)


def test_rehearsal_sample_marks_unsampled_identical_rates_check_unperformed(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    receipt = EV.rehearsal_sample(central, output, n_runs=1, n_sensitivity=1,
                                  runner=fake_engine([]), log=lambda _: None)
    assert receipt["completed_job_counts"] == {"primary": 1, "sensitivity": 1}
    assert receipt["identical_rates_check"] == {"performed": False, "passed": False}


def test_rehearsal_sample_preserves_engine_cardinality_failure(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    with pytest.raises(ValueError, match="wrong number of path results"):
        EV.rehearsal_sample(central, output, runner=lambda requested, **kwargs: [], log=lambda _: None)


def test_rehearsal_sample_preserves_underlying_engine_failure(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)

    def invalid_engine(*args, **kwargs):
        raise AssertionError("synthetic full-run validation failed")

    with pytest.raises(AssertionError, match="full-run validation failed"):
        EV.rehearsal_sample(central, output, runner=invalid_engine, log=lambda _: None)


def test_binding_build_still_refuses_dry_handoff_before_jobs(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    with pytest.raises(ValueError, match="dry-run handoff cannot authorize"):
        EV.build(central, 1., uncertainty_ruling="c", handoff_path=output,
                 runner=lambda *args, **kw: pytest.fail("no binding job may run"))


@pytest.mark.parametrize("mutation,match", [
    (lambda manifest: manifest.update(rule_sha="0" * 40), "rule SHA"),
    (lambda manifest: manifest["forms"][TU.PRIMARY_FORM].update(fiscal_eligible=True), "primary-only"),
    (lambda manifest: manifest.update(expected_value_authorized=True), "authorization"),
    (lambda manifest: manifest["score_table"].update(scoring_head="0" * 40), "score table"),
])
def test_rehearsal_retains_full_handoff_validation(artifact, monkeypatch, mutation, match):
    central, output, manifest = dry_artifact(artifact, monkeypatch)
    mutation(manifest)
    (output / "handoff.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=match):
        EV.rehearsal_sample(central, output, runner=lambda *args, **kw: pytest.fail("no job may run"))


def test_rehearsal_refuses_binding_handoff(artifact, monkeypatch):
    central, output, manifest = dry_artifact(artifact, monkeypatch)
    inputs = {"ready": False, "complete_origins": manifest["score_table"]["origins"]["B"]}
    manifest.update(TU.c2_metadata(manifest["score_table"], manifest["c2_outcome"], inputs, binding=True))
    for form, metadata in manifest["forms"].items():
        metadata["fiscal_eligible"] = form == TU.PRIMARY_FORM
    (output / "handoff.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="rehearsal requires a dry C2 handoff"):
        EV.rehearsal_design(central, output)


def test_rehearsal_receipt_cannot_be_reused_as_c2_authorization(artifact, monkeypatch):
    central, output, _ = dry_artifact(artifact, monkeypatch)
    receipt = EV.rehearsal_sample(central, output, n_runs=2, n_sensitivity=0,
                                  runner=fake_engine([]), log=lambda _: None)
    with pytest.raises(ValueError):
        TU.validate_c2_handoff(receipt["provenance"])


@pytest.mark.parametrize("runs,sensitivity", [(0, 0), (21, 0), (20, 3), (1, 2)])
def test_rehearsal_cannot_expand_into_a_full_build(runs, sensitivity):
    with pytest.raises(ValueError, match="rehearsal permits"):
        EV.rehearsal_design({}, None, n_runs=runs, n_sensitivity=sensitivity)


@pytest.mark.parametrize("relative", ["data/results.json", "dashboard/public/data/results.json",
                                       ".cache/J-rehearsal/results.json", ".cache/J-rehearsal/nested/results.json",
                                       ".cache/other/receipt.json"])
def test_rehearsal_never_writes_results_or_other_directory(tmp_path, monkeypatch, relative):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    destination = tmp_path / relative
    safe = tmp_path / ".cache/J-rehearsal/receipt.json"
    receipt = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    with pytest.raises(ValueError, match="rehearsal cannot produce"):
        pipeline.write(receipt, [safe, destination])
    assert not safe.exists()  # all destinations checked before the first write
    assert not destination.exists()


def test_rehearsal_symlink_and_nested_marker_cannot_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    directory = tmp_path / ".cache/J-rehearsal"
    directory.mkdir(parents=True)
    publication = tmp_path / "data"
    publication.mkdir()
    (directory / "escape").symlink_to(publication, target_is_directory=True)
    receipt = {"provenance": {"run_kind": "rehearsal"}, "rehearsal_output_dir": ".cache/J-rehearsal"}
    with pytest.raises(ValueError):
        pipeline.write(receipt, [directory / "escape/receipt.json"])
    assert not (publication / "receipt.json").exists()
    with pytest.raises(ValueError):
        pipeline.write({"provenance": {"run_kind": "rehearsal"}}, [publication / "results.json"])
    (directory / "receipt-alias.json").symlink_to(directory / "results.json")
    with pytest.raises(ValueError):
        pipeline.write(receipt, [directory / "receipt-alias.json"])
    assert not (directory / "results.json").exists()


def test_rehearsal_safe_receipt_and_binding_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    safe = tmp_path / ".cache/J-rehearsal/receipt.json"
    receipt = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    pipeline.write(receipt, [safe])
    assert json.loads(safe.read_text()) == receipt
    binding = tmp_path / "data/results.json"
    pipeline.write({"run_kind": "binding"}, [binding])
    assert json.loads(binding.read_text()) == {"run_kind": "binding"}


def test_shared_rehearsal_writer_rejects_publication_hardlink_before_any_write(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    publication = tmp_path / "data/results.json"
    publication.parent.mkdir()
    original = b'{"preserved_publication": true}\n'
    publication.write_bytes(original)
    destination = tmp_path / ".cache/J-rehearsal/receipt.json"
    destination.parent.mkdir(parents=True)
    destination.hardlink_to(publication)
    safe = destination.with_name("first-receipt.json")
    receipt = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    with pytest.raises(ValueError, match="multiply linked destination"):
        pipeline.write(receipt, [safe, destination])
    assert publication.read_bytes() == destination.read_bytes() == original
    assert publication.stat().st_nlink == 2
    assert not safe.exists()


def test_shared_rehearsal_writer_atomically_replaces_with_owner_only_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    destination = tmp_path / ".cache/J-rehearsal/receipt.json"
    destination.parent.mkdir(parents=True)
    previous = b'{"previous_receipt": true}\n'
    destination.write_bytes(previous)
    publication = tmp_path / "data/results.json"
    publication.parent.mkdir()
    original = b'{"preserved_publication": true}\n'
    publication.write_bytes(original)
    predictable = destination.with_name(".receipt.json.tmp")
    predictable.symlink_to(publication)
    receipt = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    real_replace = Path.replace
    replacements = []

    def checked_replace(source, target):
        if target == destination:
            replacements.append(source)
            assert source != destination and source != predictable
            assert destination.read_bytes() == previous
            assert json.loads(source.read_text()) == receipt
            assert source.stat().st_mode & 0o777 == 0o600
            assert source.stat().st_nlink == 1
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", checked_replace)
    pipeline.write(receipt, [destination])
    assert len(replacements) == 1
    assert json.loads(destination.read_text()) == receipt
    assert destination.stat().st_mode & 0o777 == 0o600
    assert publication.read_bytes() == original and predictable.is_symlink()
    assert list(destination.parent.glob(".receipt.json.*.tmp")) == []


def test_shared_rehearsal_writer_rechecks_late_hardlink_and_removes_temporary_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    publication = tmp_path / "data/results.json"
    publication.parent.mkdir()
    original = b'{"preserved_publication": true}\n'
    publication.write_bytes(original)
    destination = tmp_path / ".cache/J-rehearsal/receipt.json"
    receipt = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    real_sync = pipeline.os.fsync

    def link_after_temporary_write(descriptor):
        real_sync(descriptor)
        destination.hardlink_to(publication)

    monkeypatch.setattr(pipeline.os, "fsync", link_after_temporary_write)
    with pytest.raises(ValueError, match="multiply linked destination"):
        pipeline.write(receipt, [destination])
    assert publication.read_bytes() == destination.read_bytes() == original
    assert list(destination.parent.glob(".receipt.json.*.tmp")) == []


def driver():
    path = Path(__file__).parents[1] / "scripts/run_model_v2_j_rehearsal.py"
    spec = importlib.util.spec_from_file_location("j_rehearsal_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_planning_estimate_excludes_warm_jobs_and_preserves_gate_counts():
    rehearsal = driver()
    timings = [{"dataset": dataset, "kind": kind, "wall_seconds": 30., "cache": "cold", "status": "completed"}
               for dataset, kinds in (("efrs", ("path", "coverage", "history")), ("microcosm", ("path", "coverage")))
               for kind in kinds]
    timings.append({"dataset": "efrs", "kind": "path", "wall_seconds": 1000., "cache": "warm", "status": "completed"})
    estimate = rehearsal.planning_estimate(timings, 161, 40, 3, 2)
    assert estimate["measured_types"]["efrs.path"]["mean_wall_seconds"] == 30
    outcomes = estimate["post_Budget_build_plus_validation"]
    assert sum(outcomes["primary_passes"]["enhanced_frs_jobs"].values()) == 705
    assert sum(outcomes["primary_fails"]["enhanced_frs_jobs"].values()) == 505
    assert sum(outcomes["primary_passes"]["microcosm_jobs"].values()) == 41
    assert sum(outcomes["primary_fails"]["microcosm_jobs"].values()) == 1
    assert "planning estimate" in estimate["label"]


# Four CPUs: the default limit is 6 x 4 = 24 (twice the CPUs, 8, was the old cutoff).
@pytest.mark.parametrize("memory,load", [(7, 0), (100, 25)])
def test_host_saturation_stops_before_run(monkeypatch, memory, load):
    monkeypatch.delenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", raising=False)
    rehearsal = driver()
    snapshot = {"available_gib": memory, "load_1m": load, "cpu_count": 4, "vm_stat": "synthetic admission snapshot"}
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: snapshot)
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda *args, **kw: pytest.fail("saturated host must start no job"))
    report = {"host_checks": [], "timings": [], "batches": []}
    runner = rehearsal.TimedJobs(report, lambda: None)
    with pytest.raises(rehearsal.host.HostSaturated, match="host memory or load") as error:
        runner([("path", {})], workers=1)
    # main's failure checkpoint retains the rejected admission evidence and the limits that rejected it
    assert report["host_checks"] == [{**snapshot, "minimum_available_gib": 40, "max_load_per_cpu": 6.0,
                                      "load_limit": 24.0, "admitted": False}]
    assert error.value.host_admissions == report["host_checks"]
    assert report["timings"] == []
    assert runner.stop.is_set()


@pytest.mark.parametrize("warm_jobs", [0, 1, 2])
def test_rehearsal_microcosm_floor_counts_concurrent_uncached_jobs(monkeypatch, warm_jobs):
    rehearsal = driver()
    monkeypatch.setattr(rehearsal.engine, "engine_semantics", lambda: {})
    monkeypatch.setattr(rehearsal.engine, "package_versions", lambda: {})
    monkeypatch.setattr(rehearsal.engine, "cached", lambda kind, arg, *a: {} if arg["i"] < warm_jobs else None)
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda requested, **kwargs: ["cached or stub"] * len(requested))
    snapshot = {"available_gib": 40 * max(1, 2 - warm_jobs), "load_1m": 0, "cpu_count": 4}

    def measure():
        assert warm_jobs < 2, "a completely cached batch starts no model process"
        return snapshot

    monkeypatch.setattr(rehearsal, "host_snapshot", measure)
    report = {"host_checks": [], "timings": [], "batches": []}
    work = [("path", {"dataset": rehearsal.SENSITIVITY_DATASET, "i": i}) for i in range(2)]
    assert rehearsal.TimedJobs(report, lambda: None)(work, workers=2) == ["cached or stub"] * 2
    if warm_jobs < 2:
        assert report["host_checks"][0]["minimum_available_gib"] == 40 * (2 - warm_jobs)
    else:
        assert not report["host_checks"]


@pytest.mark.parametrize("load", [8.01, 9, 16, 24])
def test_load_between_two_and_six_times_the_cpus_admits_before_and_after_the_slot(tmp_path, monkeypatch, load):
    """Load above the old cutoff (8 on four CPUs) but within the default limit (24) starts the job."""
    monkeypatch.delenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", raising=False)
    rehearsal = driver()
    snapshot = {"available_gib": 100, "load_1m": load, "cpu_count": 4, "vm_stat": "synthetic busy host"}
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: dict(snapshot))
    for namespace in (rehearsal.engine, rehearsal.jobs):
        monkeypatch.setattr(namespace, "engine_semantics", lambda: {})
        monkeypatch.setattr(namespace, "package_versions", lambda: {})
        monkeypatch.setattr(namespace, "cached", lambda *a, **kw: None)
    monkeypatch.setattr(rehearsal.jobs, "kill_children", lambda *a, **kw: pytest.fail("an admitted host is not stopped"))

    def scheduler(requested, *, admission, stop, **kw):
        admission("path", {}, tmp_path, stop)  # the after-slot recheck
        return ["synthetic result"]

    monkeypatch.setattr(rehearsal.jobs, "run_jobs", scheduler)
    report = {"host_checks": [], "timings": [], "batches": []}
    runner = rehearsal.TimedJobs(report, lambda: None)
    assert runner([("path", {})], workers=1) == ["synthetic result"]
    limits = {"minimum_available_gib": 40, "max_load_per_cpu": 6.0, "load_limit": 24.0, "admitted": True}
    assert report["host_checks"] == [{**snapshot, **limits},
                                     {**snapshot, **limits, "phase": "after_slot_acquisition"}]
    assert not runner.stop.is_set()


def test_a_configured_limit_reaches_every_rehearsal_check(monkeypatch):
    monkeypatch.setenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", "100")  # the runner's own value wins
    rehearsal = driver()
    snapshot = {"available_gib": 100, "load_1m": 9, "cpu_count": 4, "vm_stat": "synthetic"}
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: snapshot)
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda *args, **kw: pytest.fail("refused host must start no job"))
    report = {"host_checks": [], "timings": [], "batches": []}
    runner = rehearsal.TimedJobs(report, lambda: None, max_load_per_cpu=2)
    with pytest.raises(RuntimeError, match=r"limit 8 = 2 x 4 CPUs"):
        runner([("path", {})], workers=1)
    assert report["host_checks"][0]["load_limit"] == 8 and report["host_checks"][0]["admitted"] is False


@pytest.mark.parametrize("memory,load", [(100, 25), (39, 0)])
def test_rehearsal_post_slot_saturation_stops_queued_jobs_and_retains_safe_receipt(tmp_path, monkeypatch, memory, load):
    monkeypatch.delenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", raising=False)
    rehearsal = driver()
    healthy = {"available_gib": 100, "load_1m": 0, "cpu_count": 4, "vm_stat": "before slot wait"}
    saturated = {"available_gib": memory, "load_1m": load, "cpu_count": 4, "vm_stat": "after slot acquisition"}
    snapshots = iter([healthy, saturated, saturated])
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: next(snapshots))
    monkeypatch.setattr(rehearsal.engine, "engine_semantics", lambda: {})
    monkeypatch.setattr(rehearsal.engine, "package_versions", lambda: {})
    monkeypatch.setattr(rehearsal.engine, "cached", lambda *args, **kw: None)
    monkeypatch.setattr(rehearsal.jobs, "engine_semantics", lambda: {})
    monkeypatch.setattr(rehearsal.jobs, "package_versions", lambda: {})
    monkeypatch.setattr(rehearsal.jobs, "cached", lambda *args, **kw: None)
    monkeypatch.setattr(rehearsal.jobs, "WORKDIRS", tmp_path / "workers")
    monkeypatch.setattr(rehearsal.jobs, "_run_isolated", lambda *args: pytest.fail("post-slot saturation must launch no model"))
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    killed = []

    def kill_shared(stop):
        killed.append(stop)
        stop.set()
        return 0

    monkeypatch.setattr(rehearsal.jobs, "kill_children", kill_shared)
    report = {"rehearsal": True, "quote_eligible": False, "expected_value_authorized": False,
              "rehearsal_output_dir": ".cache/J-rehearsal", "host_checks": [], "timings": [], "batches": []}
    receipt = tmp_path / ".cache/J-rehearsal/admission-receipt.json"
    runner = rehearsal.TimedJobs(report, lambda: pipeline.write(report, [receipt]))
    real_scheduler = rehearsal.jobs.run_jobs
    calls = []

    def temporary_scheduler(requested, **kwargs):
        calls.append(kwargs)
        return real_scheduler(requested, cache=tmp_path / "job-cache", **kwargs)

    monkeypatch.setattr(rehearsal.jobs, "run_jobs", temporary_scheduler)
    with pytest.raises(rehearsal.host.HostSaturated, match="failed") as error:
        runner([("path", {"i": index}) for index in range(4)], workers=2, log=lambda _: None)
    assert error.value.host_admissions
    assert all(decision["admitted"] is False and decision["available_gib"] == memory
               and decision["load_1m"] == load for decision in error.value.host_admissions)
    assert calls[0]["stop"] is runner.stop
    assert killed and all(stop is runner.stop for stop in killed)
    assert runner.stop.is_set()
    saved = json.loads(receipt.read_text())
    assert any(check.get("phase") == "after_slot_acquisition" and check["vm_stat"] == "after slot acquisition"
               and check["load_limit"] == 24 and check["admitted"] is False for check in saved["host_checks"])
    assert saved["timings"] == []
    assert saved["batches"] == []
    assert saved["expected_value_authorized"] is False
    assert not (tmp_path / "data/results.json").exists()
    # A later stage cannot resume an event that the host admission revoked.
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: healthy)
    with pytest.raises(rehearsal.jobs.Aborted, match="stopped before another model batch"):
        runner([("path", {"i": 5})], workers=1)
    assert len(calls) == 1


def unsafe_validation_results(rehearsal, case):
    """Individually adequate cells can leave a one-record contrast or nine-record complement."""
    modes = list(rehearsal.AV.RUN_MODES)
    paths = [{"fixed_inputs": {"demography": mode, "calculated_fiscal_years": list(rehearsal.HORIZON)},
              "saving_bn": {2039: {"gross": 12.3456789 + (0.00000987 if mode == "both" else 0),
                                    "net": 9.87654321, "gb": {"gross": 10.000001}}},
              "saving_support_records_by_year": {2039: {"uk": {"gross": 19, "net": 19},
                                                        "gb": {"gross": 10, "net": 10}}},
              "treatment_contrast_support": {"both_minus_frozen": 1 if case == "contrast" else 10}}
             for mode in modes]
    coverage = [{"demography": mode, "by_year": {2039: {"uk": {"records": 19, "state_pension_bn": 11.987654},
                                                          "gb": {"records": 10, "state_pension_bn": 10.987653}}}}
                for mode in modes]
    return modes, paths + coverage


@pytest.mark.parametrize("case", ["contrast", "geography_complement"])
def test_validation_receipt_never_exposes_small_contrast_or_geography(case):
    rehearsal = driver()
    modes, results = unsafe_validation_results(rehearsal, case)
    receipt = rehearsal.validation_receipt(modes, results)
    assert receipt["fiscal_tables_omitted"] is True
    assert receipt["invariants"] == {"requested_treatments_used": True, "full_horizon_paths": True,
                                     "all_engine_jobs_completed": True}
    # Exact allowlist: no amount or contributing-count field may be copied,
    # even when every individual saving support count is at least ten.
    assert set(receipt) == {"rehearsal", "quote_eligible", "status", "method", "modes", "path_jobs",
                            "coverage_jobs", "invariants", "fiscal_tables_omitted"}
    encoded = json.dumps(receipt)
    for raw_field in ("saving_bn", "state_pension_bn", "records", "contrast_support", "12.3456789", "11.987654"):
        assert raw_field not in encoded


def mock_driver_main(rehearsal, tmp_path, monkeypatch):
    modes, results = unsafe_validation_results(rehearsal, "contrast")
    monkeypatch.setattr(rehearsal, "REPO", tmp_path)
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline, "check_unchanged", lambda *args: None)
    packages = dict(rehearsal.CERTIFIED_PACKAGES)
    monkeypatch.setattr(pipeline, "package_versions", lambda: dict(packages))
    monkeypatch.setattr(rehearsal.datasets, "provenance", lambda dataset: {"dataset": dataset, "certified": True})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: {"passed": True})
    monkeypatch.setattr(rehearsal.central, "central_path", lambda: {})
    monkeypatch.setattr(rehearsal.engine, "base_levels", lambda parameters: {"new_state_pension": 1})
    monkeypatch.setattr(rehearsal.EV, "rehearsal_design", lambda *args, **kwargs: {
        "indices": [], "sensitivity_indices": [],
        "provenance": {"full_design_unique_runs": 161, "full_design_paired_runs": 40}})
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", SimpleNamespace(system=SimpleNamespace(parameters=None)))
    plan = {"validation": [("path", {})] * len(modes) + [("coverage", {})] * len(modes),
            "validation_modes": modes, "scenario_ids": [], "history_switch_years": [], "historical_model_years": []}
    monkeypatch.setattr(rehearsal, "core_plan", lambda *args: plan)
    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: lambda *args, **kwargs: results)
    monkeypatch.setattr(rehearsal.AV, "summarise", lambda *args: pytest.fail("rehearsal must not render fiscal tables"))
    monkeypatch.setenv("VECLIB_MAXIMUM_THREADS", "1")
    destination = tmp_path / ".cache/J-rehearsal"
    return modes, results, packages, destination


def test_validation_driver_writes_only_invariants_without_calling_fiscal_renderer(tmp_path, monkeypatch):
    rehearsal = driver()
    modes, results, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    assert rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                           "--output-dir", str(destination)]) == 0
    receipt = json.loads((destination / "validation-receipt.json").read_text())
    assert receipt["validation"]["fiscal_tables_omitted"] is True
    assert receipt["validation"]["path_jobs"] == len(modes)
    assert receipt["numeric_threads"]["VECLIB_MAXIMUM_THREADS"] == "1"
    assert receipt["provenance"]["packages"] == packages
    assert receipt["provenance"]["dataset"]["certified"] is True
    assert len(receipt["provenance"]["driver_sha256"]) == 64
    assert "12.3456789" not in json.dumps(receipt)
    assert not (tmp_path / "data/results.json").exists()


@pytest.mark.parametrize("stage", ["central", "coverage", "scenarios"])
def test_core_stage_writer_omits_unproven_top10_and_all_raw_engine_results(tmp_path, monkeypatch, stage):
    """Ten selected records do not prove ten nonzero contributing records."""
    rehearsal = driver()
    _, _, _, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    plan = {stage: [("coverage" if stage == "coverage" else "path", {})],
            "validation_modes": [], "scenario_ids": [], "history_switch_years": [], "historical_model_years": []}
    monkeypatch.setattr(rehearsal, "core_plan", lambda *args: plan)
    runs = [{"saving_bn": {2039: {"net": 987654321.625}},
             "concentration_top10_by_year": {2039: {"records": 10, "contribution_bn": 987654321.625,
                                                     "share_of_income_change": 1.0}},
             "by_year": {2039: {"private_survey_value": 123456789.875}}}]
    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: lambda *args, **kwargs: runs)
    assert rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", stage,
                           "--skip-microcosm-coverage", "--output-dir", str(destination)]) == 0
    encoded = (destination / f"{stage}-receipt.json").read_text()
    receipt = json.loads(encoded)
    assert receipt["status"] == "completed" and receipt["completed_stages"] == [stage]
    for private_field in ("concentration_top10_by_year", "saving_bn", "private_survey_value",
                          "987654321.625", "123456789.875"):
        assert private_field not in encoded
    assert not (tmp_path / "data/results.json").exists()


@pytest.mark.parametrize("flag,environment,expected,source", [
    ([], None, 6.0, "default"), ([], "4", 4.0, "environment"), (["--max-load-per-cpu", "10"], "4", 10.0, "flag")])
def test_rehearsal_resolves_and_records_the_load_limit_it_applies(tmp_path, monkeypatch, flag, environment,
                                                                   expected, source):
    rehearsal = driver()
    modes, results, _, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    if environment is None:
        monkeypatch.delenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", raising=False)
    else:
        monkeypatch.setenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", environment)
    runners = []
    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: runners.append(args) or (lambda *a, **kw: results))
    assert rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                           "--output-dir", str(destination), *flag]) == 0
    assert len(runners) == 1 and runners[0][3] == expected
    receipt = json.loads((destination / "validation-receipt.json").read_text())
    assert receipt["host_admission"] == {"max_load_per_cpu": expected, "source": source,
                                         "environment_variable": "TRIPLE_LOCK_MAX_LOAD_PER_CPU"}


@pytest.mark.parametrize("flag,environment", [([], "0"), ([], "-3"), (["--max-load-per-cpu", "nan"], None)])
def test_rehearsal_refuses_a_malformed_load_limit_before_planning(tmp_path, monkeypatch, flag, environment):
    rehearsal = driver()
    _, _, _, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    if environment is None:
        monkeypatch.delenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", raising=False)
    else:
        monkeypatch.setenv("TRIPLE_LOCK_MAX_LOAD_PER_CPU", environment)
    monkeypatch.setattr(pipeline, "snapshot", lambda: pytest.fail("a malformed limit stops before planning"))
    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: pytest.fail("a malformed limit starts no runner"))
    with pytest.raises(ValueError, match="TRIPLE_LOCK_MAX_LOAD_PER_CPU"):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination), *flag])
    assert not destination.exists()


@pytest.mark.parametrize("package", ["policyengine", "policyengine-uk", "policyengine-core"])
def test_rehearsal_rejects_other_bundle_versions_before_preflight_or_jobs(tmp_path, monkeypatch, package):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    packages[package] = "wrong-version"
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: pytest.fail("wrong bundle starts no model"))
    monkeypatch.setattr(EV, "rehearsal_design", lambda *args, **kw: pytest.fail("wrong bundle starts no design"))
    with pytest.raises(ValueError, match="exact certified"):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--output-dir", str(destination)])
    assert not destination.exists()


def test_rehearsal_rejects_uncertified_primary_before_jobs(tmp_path, monkeypatch):
    rehearsal = driver()
    _, _, _, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    monkeypatch.setattr(rehearsal.datasets, "provenance", lambda dataset: {"certified": False})
    monkeypatch.setattr(EV, "rehearsal_design", lambda *args, **kw: pytest.fail("uncertified artifact starts no design"))
    with pytest.raises(ValueError, match="certified primary dataset"):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--output-dir", str(destination)])


@pytest.mark.parametrize("change", ["package", "driver", "certification", "numeric_threads"])
def test_rehearsal_detects_environment_drift_alongside_source_check(tmp_path, monkeypatch, change):
    rehearsal = driver()
    _, _, packages, _ = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    synthetic_driver = tmp_path / "synthetic_driver.py"
    synthetic_driver.write_text("before")
    monkeypatch.setattr(rehearsal, "__file__", str(synthetic_driver))
    environment = rehearsal.certified_environment()
    checks = []
    monkeypatch.setattr(pipeline, "check_unchanged", lambda start, where: checks.append(where))
    if change == "package":
        packages["numpy"] = "changed-dependency"
    elif change == "driver":
        synthetic_driver.write_text("after")
    elif change == "certification":
        monkeypatch.setattr(rehearsal.datasets, "provenance", lambda dataset: {"dataset": dataset, "certified": False})
    else:
        monkeypatch.setenv("VECLIB_MAXIMUM_THREADS", "2")
    with pytest.raises(rehearsal.engine.SourceChanged, match="packages, dataset certification, driver or numeric threads"):
        rehearsal.check_execution({}, environment, "after synthetic stage")
    assert checks == ["after synthetic stage"]


def test_rehearsal_stage_package_drift_never_writes_completed_validation(tmp_path, monkeypatch):
    rehearsal = driver()
    _, results, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)

    def changed_batch(*args, **kwargs):
        packages["policyengine-uk"] = "2.125.2"
        return results

    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: changed_batch)
    with pytest.raises(rehearsal.engine.SourceChanged):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination)])
    retained = json.loads((destination / "validation-receipt.json").read_text())
    assert retained["status"] == "running"
    assert "validation" not in retained


def test_rehearsal_checkpoint_drift_stops_before_atomic_receipt_commit(tmp_path, monkeypatch):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    original_serialize = rehearsal.serialized_receipt

    def changed_during_serialization(report):
        payload = original_serialize(report)
        packages["policyengine-core"] = "3.33.1"
        return payload

    monkeypatch.setattr(rehearsal, "serialized_receipt", changed_during_serialization)
    with pytest.raises(rehearsal.engine.SourceChanged):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination)])
    assert not (destination / "validation-receipt.json").exists()
    assert not (destination / ".validation-receipt.tmp").exists()


def test_rehearsal_internal_temp_symlink_and_drift_preserve_valid_bytes(tmp_path, monkeypatch):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    destination.mkdir(parents=True)
    previous = b'{"status": "valid previous receipt", "preserve": true}\n'
    receipt = destination / "validation-receipt.json"
    receipt.write_bytes(previous)
    predictable = destination / ".validation-receipt.tmp"
    predictable.symlink_to(receipt)
    original_serialize = rehearsal.serialized_receipt

    def changed_during_serialization(report):
        payload = original_serialize(report)
        packages["policyengine-core"] = "3.33.1"
        return payload

    monkeypatch.setattr(rehearsal, "serialized_receipt", changed_during_serialization)
    with pytest.raises(rehearsal.engine.SourceChanged):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination)])
    assert receipt.read_bytes() == previous
    assert predictable.is_symlink()
    assert list(destination.glob(".validation-receipt.json.*.tmp")) == []


def test_rehearsal_private_temporary_receipt_retains_destination_guard(tmp_path, monkeypatch):
    rehearsal = driver()
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    report = {"rehearsal": True, "rehearsal_output_dir": ".cache/J-rehearsal"}
    with pytest.raises(ValueError, match="rehearsal cannot produce"):
        rehearsal.private_temporary_receipt(report, tmp_path / "data/results.json", b"invalid")
    safe = tmp_path / ".cache/J-rehearsal/receipt.json"
    temporary = rehearsal.private_temporary_receipt(report, safe, b"safe")
    assert temporary.read_bytes() == b"safe"
    assert temporary.stat().st_mode & 0o777 == 0o600
    assert temporary.name.startswith(".receipt.json.")
    assert temporary != safe
    temporary.unlink()


def test_rehearsal_post_checkpoint_drift_restores_previous_receipt(tmp_path, monkeypatch):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    destination.mkdir(parents=True)
    previous = b'{"status": "previous valid receipt"}\n'
    (destination / "validation-receipt.json").write_bytes(previous)
    predictable = destination / ".validation-receipt.tmp"
    predictable.symlink_to(destination / "validation-receipt.json")
    original_check = rehearsal.check_execution

    def changed_after_commit(start, environment, where):
        if where == "after receipt checkpoint":
            packages["numpy"] = "changed-after-commit"
        return original_check(start, environment, where)

    monkeypatch.setattr(rehearsal, "check_execution", changed_after_commit)
    with pytest.raises(rehearsal.engine.SourceChanged):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination)])
    assert (destination / "validation-receipt.json").read_bytes() == previous
    assert predictable.is_symlink()
    assert list(destination.glob(".validation-receipt.json.*.tmp")) == []


def test_rehearsal_plan_records_certification_without_model_jobs(tmp_path, monkeypatch, capsys):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda: pytest.fail("plan starts no model"))
    monkeypatch.setattr(rehearsal, "TimedJobs", lambda *args: pytest.fail("plan starts no runner"))
    assert rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation", "--plan",
                           "--output-dir", str(destination)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "planned"
    assert report["provenance"]["packages"] == packages
    assert report["provenance"]["dataset"]["certified"] is True
    assert not destination.exists()
