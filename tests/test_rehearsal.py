"""Publication boundaries and real frozen-C2 validation; synthetic engine only."""

import importlib.util
import json
from pathlib import Path

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
    monkeypatch.setattr(rehearsal, "host_snapshot", lambda **kw: {"available_gib": memory, "load_1m": load, "cpu_count": 4})
    monkeypatch.setattr(rehearsal.jobs, "run_jobs", lambda *args, **kw: pytest.fail("saturated host must start no job"))
    runner = rehearsal.TimedJobs({"host_checks": [], "timings": [], "batches": []}, lambda: None)
    with pytest.raises(RuntimeError, match="host memory or load"):
        runner([("path", {})], workers=1)
