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
    assert result["identical_rates_check"]["largest_abs_saving_bn"] == 0
    assert not {"expected_value", "estimates", "paired_difference", "saving_bn"} & result.keys()


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


@pytest.mark.parametrize("memory,load", [(7, 0), (100, 9)])
def test_host_saturation_stops_before_run(monkeypatch, memory, load):
    rehearsal = driver()
    snapshot = {"available_gib": memory, "load_1m": load, "cpu_count": 4, "vm_stat": "synthetic admission snapshot"}
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: snapshot)
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda *args, **kw: pytest.fail("saturated host must start no job"))
    report = {"host_checks": [], "timings": [], "batches": []}
    runner = rehearsal.TimedJobs(report, lambda: None)
    with pytest.raises(RuntimeError, match="host memory or load"):
        runner([("path", {})], workers=1)
    assert report["host_checks"] == [snapshot]  # main's failure checkpoint retains the rejected admission evidence
    assert report["timings"] == []


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
    original_write = pipeline.write

    def changed_during_serialization(report, paths):
        original_write(report, paths)
        packages["policyengine-core"] = "3.33.1"

    monkeypatch.setattr(pipeline, "write", changed_during_serialization)
    with pytest.raises(rehearsal.engine.SourceChanged):
        rehearsal.main(["--handoff", str(tmp_path / "unused"), "--stage", "validation",
                        "--output-dir", str(destination)])
    assert not (destination / "validation-receipt.json").exists()
    assert not (destination / ".validation-receipt.tmp").exists()


def test_rehearsal_post_checkpoint_drift_restores_previous_receipt(tmp_path, monkeypatch):
    rehearsal = driver()
    _, _, packages, destination = mock_driver_main(rehearsal, tmp_path, monkeypatch)
    destination.mkdir(parents=True)
    previous = b'{"status": "previous valid receipt"}\n'
    (destination / "validation-receipt.json").write_bytes(previous)
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
    assert not (destination / ".validation-receipt.tmp").exists()


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
