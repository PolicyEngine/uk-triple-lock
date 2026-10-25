"""Bridge design, estimator and linked suppression checks without survey data."""

from copy import deepcopy
import contextlib
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts import run_model_v2_j_bridge as bridge
from triple_lock.engine import _keys_to_int


def test_frozen_bridge_uses_full_both_paths_and_original_forty_indices():
    specs = _keys_to_int(json.loads((Path(__file__).parents[1] / "data/pilot/d_macro_specs.json").read_text()))
    planned, sample, weights = bridge.design(specs, bridge.CERTIFIED)
    assert len(planned) == 42
    assert len({i for indices in sample.values() for i in indices}) == 40
    assert sum(map(len, sample.values())) == 40
    assert sum(weights.values()) + specs["identical_rates_probability"] == pytest.approx(1)
    assert all(job[1]["demography"] == "both" for _, job in planned)
    assert all(job[1]["dataset"] == bridge.CERTIFIED for _, job in planned)
    assert planned[-1][1][1]["years"] == [*range(2024, 2031), 2034, 2039]
    assert planned[0][1][1]["fiscal_output_years"] == [2034, 2039]


@pytest.mark.parametrize("uk,gb,expected", [(20, 10, True), (19, 10, False), (10, 10, True),
                                           (9, 0, False), (0, 0, True), (True, 0, False), (10, 20, False)])
def test_linked_support_includes_northern_ireland_complement(uk, gb, expected):
    assert bridge.linked_support(uk, gb) is expected


def fake_run(value):
    return {"saving_bn": {y: {"gross": value, "net": value, "gb": {"gross": value, "net": value}}
                          for y in bridge.YEARS},
            "saving_support_records_by_year": {y: {"uk": {"gross": 20, "net": 20, "offset": 20},
                                                    "gb": {"gross": 10, "net": 10, "offset": 10}}
                                               for y in bridge.YEARS}}


def test_partial_checkpoint_does_not_estimate_missing_draws():
    runs = {"central": fake_run(1), "draw_1": fake_run(2)}
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    assert len(result["central"]) == 8 and result["paired"] == []


def test_paired_estimator_uses_saved_stratum_mass_and_se_components():
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: .5})
    assert len(result["paired"]) == 8
    estimate = result["paired"][0]["estimate_bn"]
    assert estimate["mean"] == 1.5
    assert estimate["variance_path_sampling"] == .25
    assert estimate["variance_first_phase"] > 0


def test_one_small_complement_withholds_linked_measure_family():
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    runs["draw_2"]["saving_support_records_by_year"][2039]["uk"]["net"] = 19
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    for kind in ("central", "paired"):
        rows = result[kind]
        assert all(r["status"] == "withheld_family" for r in rows)
        assert all(r["value_bn" if kind == "central" else "estimate_bn"] is None for r in rows)


@pytest.mark.parametrize("offset", [None, 1, 9])
def test_small_or_missing_gross_net_offset_withholds_both_totals(offset):
    runs = {"central": fake_run(1), "draw_1": fake_run(2), "draw_2": fake_run(4)}
    runs["draw_2"]["saving_support_records_by_year"][2039]["gb"]["offset"] = offset
    result = bridge.saving_tables(runs, {1: [1, 2]}, {1: 1})
    assert all(row["status"] == "withheld_family" for rows in result.values() for row in rows)


def test_float32_balance_residuals_cannot_authorize_one_household_offset():
    reference = {"basic_state_pension": np.full(40, 10000.05, dtype=np.float32),
                 "new_state_pension": np.zeros(40, dtype=np.float32),
                 "other_spending": np.full(40, 22800, dtype=np.float32),
                 "small_spending": np.full(40, .00003, dtype=np.float32)}
    reform = deepcopy(reference)
    reform["basic_state_pension"][:] = 9900
    reform["other_spending"][0] += 10
    flat = {name: {2039: source["basic_state_pension"].astype(float)}
            for name, source in (("triple_lock", reference), (bridge.engine.REFORM, reform))}
    balances = {name: {2039: -sum(v.astype(float) for v in source.values())}
                for name, source in (("triple_lock", reference), (bridge.engine.REFORM, reform))}
    gross = flat["triple_lock"][2039] - flat[bridge.engine.REFORM][2039]
    net = balances[bridge.engine.REFORM][2039] - balances["triple_lock"][2039]
    assert np.count_nonzero(gross - net) == 40  # cancellation noise would falsely authorize the table
    offset = bridge.engine.fiscal_offset_households(reference, reform, [])
    counts = bridge.engine.saving_support_counts(
        flat, {2039: bridge.engine.fiscal_net_households(reference, reform, [])},
        {"triple_lock": {2039: SimpleNamespace(weights=pd.Series(np.ones(40)))}},
        np.arange(40) < 20, [2039], {2039: offset})[2039]
    assert counts["uk"]["gross"] == 40 and counts["gb"]["gross"] == 20
    assert counts["uk"]["offset"] is counts["gb"]["offset"] is None
    run = fake_run(1)
    run["saving_support_records_by_year"] = {year: counts for year in bridge.YEARS}
    assert all(row["status"] == "withheld_family"
               for row in bridge.saving_tables({"central": run}, {1: [1, 2]}, {1: 1})["central"])


def coverage_table(uk_total=40, uk_older=20, gb_total=20, gb_older=10):
    return {geo: {"programme_support_records": {
        "housing_benefit": total, "housing_benefit_pension_age": older}}
        for geo, total, older in (("uk", uk_total, uk_older), ("gb", gb_total, gb_older))}


@pytest.mark.parametrize("counts", [(21, 20, 10, 10), (40, 20, 21, 20),
                                   (41, 20, 30, 10)])
def test_hb_family_rejects_small_subset_or_geographic_complement(counts):
    assert not bridge.hb_family_supported([coverage_table(*counts)])


def test_hb_family_closes_across_years():
    assert bridge.hb_family_supported([coverage_table(), coverage_table()])
    assert not bridge.hb_family_supported([coverage_table(), coverage_table(21, 20, 10, 10)])


def test_public_coverage_withholds_both_linked_hb_metrics(monkeypatch):
    tables = {2024: coverage_table(), 2025: coverage_table(21, 20, 10, 10)}
    for table in tables.values():
        for row in table.values():
            row["programme_support_records"].update(
                state_pension=20 if row is table["uk"] else 10,
                pension_credit=20 if row is table["uk"] else 10,
                council_tax_reduction=20 if row is table["uk"] else 10)
            row.update({metric: 1.0 for metric in bridge.METRICS})
    monkeypatch.setattr(bridge.dwp, "coverage_targets_by_year", lambda **kw: {})
    monkeypatch.setattr(bridge, "digest", lambda path: "synthetic-source")
    rows = bridge.coverage_tables({"by_year": tables})["rows"]
    hb = [r for r in rows if r["metric"].startswith("housing_benefit")]
    assert len(hb) == 4
    assert all(r["status"] == "withheld_family" and r["UK"] is None and r["GB"] is None
               and r["support_UK"] is None and r["support_GB"] is None for r in hb)
    assert all(r["status"] == "available" for r in rows if r not in hb)


def test_source_change_between_batches_is_rejected(monkeypatch):
    start = {"source": "original", "packages": {"policyengine-uk": "2.125.1"}}
    monkeypatch.setattr(bridge, "execution_snapshot", lambda: deepcopy(start))
    bridge.check_snapshot(start, "before batch")
    monkeypatch.setattr(bridge, "execution_snapshot", lambda: {**start, "source": "changed"})
    with pytest.raises(bridge.engine.SourceChanged, match="changed at after batch"):
        bridge.check_snapshot(start, "after batch")


def test_real_snapshot_hashes_committed_dependencies_without_requiring_uv_lock(monkeypatch):
    root = Path(__file__).parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setattr(bridge.pipeline, "git_state", lambda: {"git_revision": "fixed-test-revision"})
    monkeypatch.setattr(bridge.pipeline, "package_versions", lambda: {"test": "fixed-installed-version"})
    snapshot = bridge.execution_snapshot()  # real source/input reads and digest implementation
    for name in ("pyproject.toml", "requirements-lock.txt", bridge.PROOF,
                 "src/triple_lock/historical_publication.py"):
        assert snapshot["bridge_files"][name] == hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert ("uv.lock" in snapshot["bridge_files"]) is (root / "uv.lock").exists()
    assert snapshot["source_hashes"] and snapshot["input_hashes"] and snapshot["engine_hashes"]
    assert "historical_publication.py" in snapshot["source_hashes"]


def test_real_snapshot_rejects_dependency_lock_byte_drift_without_editing_repo(monkeypatch, tmp_path):
    root = Path(__file__).parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setattr(bridge.pipeline, "git_state", lambda: {"git_revision": "fixed-test-revision"})
    monkeypatch.setattr(bridge.pipeline, "package_versions", lambda: {"test": "fixed-installed-version"})
    original = bridge.execution_snapshot()
    # Copy only the real bridge's relative inputs, keeping the repository's
    # scientific inputs untouched. The real snapshot still hashes every byte.
    for name in original["bridge_files"]:
        source = Path(name)
        if source.is_absolute():
            continue
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    monkeypatch.chdir(tmp_path)
    bridge.check_snapshot(original, "unchanged copied dependency files")
    lock = tmp_path / "requirements-lock.txt"
    lock.write_bytes(lock.read_bytes() + b"\n# changed dependency lock\n")
    with pytest.raises(bridge.engine.SourceChanged, match="changed at dependency lock drift"):
        bridge.check_snapshot(original, "dependency lock drift")


def test_incompatible_resumed_receipt_is_rejected(tmp_path):
    receipt = tmp_path / "bridge.json"
    receipt.write_text(json.dumps({"provenance": {"execution_snapshot": {"source": "old"}}}))
    with pytest.raises(bridge.engine.SourceChanged, match="incompatible source provenance"):
        bridge.check_resume(receipt, {"source": "new"})
    bridge.check_resume(receipt, {"source": "old"})


def test_checkpoint_symlink_cannot_redirect_write_into_results(tmp_path):
    protected = tmp_path / "results.json"
    protected.write_text("binding result stays unchanged")
    destination = tmp_path / "bridge.json"
    (tmp_path / ".bridge.json.tmp").symlink_to(protected)
    bridge.atomic_receipt(destination, {"run_kind": "pre_budget_bridge"}, lambda: None)
    assert protected.read_text() == "binding result stays unchanged"
    assert json.loads(destination.read_text()) == {"run_kind": "pre_budget_bridge"}


def test_serialization_drift_keeps_previous_checkpoint(tmp_path):
    destination = tmp_path / "bridge.json"
    destination.write_text("previous checkpoint")

    def changed():
        raise bridge.engine.SourceChanged("changed during serialization")

    with pytest.raises(bridge.engine.SourceChanged, match="serialization"):
        bridge.atomic_receipt(destination, {"new": True}, changed)
    assert destination.read_text() == "previous checkpoint"
    assert list(tmp_path.glob(".bridge.json.*.tmp")) == []


@pytest.mark.parametrize("has_previous", [False, True])
def test_final_receipt_commit_drift_restores_previous_bytes_or_removes_new_receipt(tmp_path, monkeypatch, has_previous):
    destination = tmp_path / "bridge.json"
    previous = b'{"complete": false, "checkpoint": "valid previous bytes"}\n'
    if has_previous:
        destination.write_bytes(previous)
    protected = tmp_path / "results.json"
    protected.write_text("binding result stays unchanged")
    predictable = tmp_path / ".bridge.json.tmp"
    predictable.symlink_to(protected)
    frozen = {"dependency": "original"}
    checks = []
    replace = Path.replace
    replacements = []

    def drift_during_final_commit(temporary, target):
        if Path(target) == destination:
            replacements.append(temporary)
            if len(replacements) == 1:
                frozen["dependency"] = "changed during final replacement"
        return replace(temporary, target)

    def guard():
        checks.append(dict(frozen))
        if frozen["dependency"] != "original":
            raise bridge.engine.SourceChanged("dependency changed during final receipt commit")

    monkeypatch.setattr(Path, "replace", drift_during_final_commit)
    with pytest.raises(bridge.engine.SourceChanged, match="final receipt commit"):
        bridge.atomic_receipt(destination, {"complete": True}, guard)
    assert len(checks) == 2
    assert len(replacements) == (2 if has_previous else 1)
    if has_previous:
        assert destination.read_bytes() == previous
        assert destination.stat().st_mode & 0o777 == 0o600
    else:
        assert not destination.exists()
    assert protected.read_text() == "binding result stays unchanged"
    assert predictable.is_symlink()
    assert list(tmp_path.glob(".bridge.json.*.tmp")) == []


def test_successful_receipt_commit_checks_provenance_before_and_after_replacement(tmp_path):
    destination = tmp_path / "bridge.json"
    observed = []
    bridge.atomic_receipt(destination, {"complete": True},
                          lambda: observed.append(destination.exists()))
    assert observed == [False, True]
    assert json.loads(destination.read_text()) == {"complete": True}
    assert destination.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".bridge.json.*.tmp")) == []


def test_reviewed_recipe_redaction_preserves_exact_pilot_design():
    root = Path(__file__).parents[1]
    path = root / "data/pilot/d_macro_specs.json"
    pilot = json.loads((root / "data/pilot/model_v2_e.json").read_text())
    raw = path.read_bytes()
    specs = _keys_to_int(json.loads(raw))
    binding = json.loads((root / "data/pilot/cold-source-binding.json").read_bytes())
    _, sample, weights = bridge.design(specs, bridge.CERTIFIED)
    bridge.verify_pilot_recipe(raw, pilot, sample, weights, binding)
    altered = deepcopy(sample)
    stratum = next(iter(altered))
    altered[stratum][0] += 1
    with pytest.raises(ValueError, match="differ from the pilot"):
        bridge.verify_pilot_recipe(raw, pilot, altered, weights, binding)

    changed_recipe = json.loads(raw)
    changed_recipe["central"]["cpi"][next(iter(changed_recipe["central"]["cpi"]))] = .5
    with pytest.raises(ValueError, match="recipe differs"):
        bridge.verify_pilot_recipe(json.dumps(changed_recipe).encode(), pilot, sample, weights, binding)


class ReachedSyntheticBatch(Exception):
    pass


def stub_bridge_main(monkeypatch):
    """Keep the real snapshot and input checks; stop before any engine job."""
    root = Path(__file__).parents[1]
    monkeypatch.chdir(root)
    packages = {"policyengine": "6.2.6", "policyengine-uk": "2.125.1", "policyengine-core": "3.33.0"}
    monkeypatch.setattr(bridge.pipeline, "git_state", lambda: {"git_revision": "fixed-test-revision"})
    monkeypatch.setattr(bridge.pipeline, "package_versions", lambda: packages.copy())
    monkeypatch.setattr(bridge.datasets, "provenance", lambda dataset: {"certified": True, "dataset": dataset})
    monkeypatch.setattr(bridge, "memory_check", lambda **kw: {})
    monkeypatch.setattr(bridge.engine, "cached", lambda *a, **kw: None)
    preflights, batches = [], []

    def preflight():
        preflights.append(True)
        return {}

    def batch(rows, *a, **kw):
        batches.extend(rows)
        raise ReachedSyntheticBatch()

    monkeypatch.setattr(bridge.pipeline, "housing_benefit_passport_preflight", preflight)
    monkeypatch.setattr(bridge, "run_batch", batch)
    output = root / ".cache/J-synthetic-input-binding-no-output.json"
    assert not output.exists()
    return SimpleNamespace(out=output, workers=1, pair="certified", max_load_per_cpu=None), preflights, batches


@pytest.mark.parametrize("name", ["d_macro_specs.json", "model_v2_e.json", "cold-source-binding.json"])
def test_input_read_race_restored_after_parse_is_rejected_before_preflight(monkeypatch, name):
    args, preflights, batches = stub_bridge_main(monkeypatch)
    target = Path("data/pilot") / name
    raw = target.read_bytes()
    changed = json.loads(raw)
    if name == "d_macro_specs.json":
        changed["central"]["cpi"][next(iter(changed["central"]["cpi"]))] = .5
    elif name == "model_v2_e.json":
        changed["fiscal"]["central"][0]["value_bn"] += 1
    else:
        changed["input_redactions"]["data/pilot/d_macro_specs.json"]["sanitized_specs_sha256"] = "0" * 64
    changed_bytes = json.dumps(changed).encode()
    real_read = Path.read_bytes
    reads = []

    def changing_read(path):
        if path.resolve() == target.resolve():
            reads.append(True)
            # Initial snapshot sees the real bytes. Only the parser's read
            # sees changed bytes; every later read sees the restored file.
            if len(reads) == 2:
                return changed_bytes
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", changing_read)
    with pytest.raises(bridge.engine.SourceChanged, match="differs from its initial execution snapshot"):
        bridge.main(args)
    assert len(reads) == 2 and preflights == [] and batches == []
    assert real_read(target) == raw and not args.out.exists()


def test_main_plans_and_validates_from_the_same_single_read_inputs(monkeypatch):
    args, preflights, batches = stub_bridge_main(monkeypatch)
    captured = {}
    read_snapshot_bytes = bridge.read_snapshot_bytes
    verify_pilot_recipe = bridge.verify_pilot_recipe
    verify_historical_publication = bridge.verify_historical_publication_redaction

    def capture(path, snapshot):
        assert str(path) not in captured
        captured[str(path)] = read_snapshot_bytes(path, snapshot)
        return captured[str(path)]

    def verify(raw, pilot, sample, weights, binding):
        assert raw is captured["data/pilot/d_macro_specs.json"]
        assert pilot == json.loads(captured["data/pilot/model_v2_e.json"])
        assert binding == json.loads(captured["data/pilot/cold-source-binding.json"])
        return verify_pilot_recipe(raw, pilot, sample, weights, binding)

    def verify_publication(repo, *, supplied_bytes, targets):
        name = "data/pilot/model_v2_e.json"
        assert targets == {name}
        assert supplied_bytes[name] is captured[name]
        return verify_historical_publication(repo, supplied_bytes=supplied_bytes, targets=targets)

    monkeypatch.setattr(bridge, "read_snapshot_bytes", capture)
    monkeypatch.setattr(bridge, "verify_pilot_recipe", verify)
    monkeypatch.setattr(bridge, "verify_historical_publication_redaction", verify_publication)
    with pytest.raises(ReachedSyntheticBatch):
        bridge.main(args)
    assert set(captured) == {"data/pilot/d_macro_specs.json", "data/pilot/model_v2_e.json",
                             "data/pilot/cold-source-binding.json"}
    assert preflights == [True] and len(batches) == 1
    central = _keys_to_int(json.loads(captured["data/pilot/d_macro_specs.json"]))["central"]
    name, (kind, argument) = batches[0]
    assert name == "central" and kind == "path"
    assert all(argument[key] == value for key, value in central.items())
    assert argument["dataset"] == bridge.CERTIFIED and argument["demography"] == "both"
    assert not args.out.exists()


@pytest.mark.parametrize("flag,environment,expected,source", [
    (None, None, 6.0, "default"), (None, "4", 4.0, "environment"), (10.0, "4", 10.0, "flag")])
def test_main_resolves_and_records_the_load_limit_it_applies(monkeypatch, flag, environment, expected, source):
    args, preflights, batches = stub_bridge_main(monkeypatch)
    args.max_load_per_cpu = flag
    if environment is None:
        monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
    else:
        monkeypatch.setenv(bridge.host.MAX_LOAD_PER_CPU_ENV, environment)
    calls, captured = [], {}
    reading = {"available_gib": 57.0, "load_1m": 66.11, "cpu_count": 18, "minimum_available_gib": 40,
               "max_load_per_cpu": expected, "load_limit": expected * 18, "admitted": True}

    def memory_check(**kw):
        calls.append(("host", kw))
        return dict(reading)

    def batch(rows, workers, cache, **kw):
        calls.append(("batch", kw))
        return [fake_run(1)]

    def receipt(destination, public, guard):
        captured.update(deepcopy(public))
        raise ReachedSyntheticBatch()

    monkeypatch.setattr(bridge, "memory_check", memory_check)
    monkeypatch.setattr(bridge, "run_batch", batch)
    monkeypatch.setattr(bridge, "atomic_receipt", receipt)
    with pytest.raises(ReachedSyntheticBatch):
        bridge.main(args)
    assert calls == [("host", {"max_load_per_cpu": expected}), ("batch", {"max_load_per_cpu": expected})]
    assert captured["provenance"]["host_admission"] == {
        "max_load_per_cpu": expected, "source": source,
        "environment_variable": "TRIPLE_LOCK_MAX_LOAD_PER_CPU", "minimum_available_gib": 40,
        "running_minimum_available_gib": bridge.RUNNING_MINIMUM_GIB}
    assert captured["timings"][0]["host_before"] == reading
    assert not args.out.exists()


@pytest.mark.parametrize("flag,environment", [(None, "0"), (None, "nan"), (-1.0, None)])
def test_main_refuses_a_malformed_load_limit_before_preflight_or_jobs(monkeypatch, flag, environment):
    args, preflights, batches = stub_bridge_main(monkeypatch)
    args.max_load_per_cpu = flag
    if environment is None:
        monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
    else:
        monkeypatch.setenv(bridge.host.MAX_LOAD_PER_CPU_ENV, environment)
    with pytest.raises(ValueError, match="TRIPLE_LOCK_MAX_LOAD_PER_CPU"):
        bridge.main(args)
    assert preflights == [] and batches == [] and not args.out.exists()


@pytest.mark.parametrize("memory,load,admitted", [
    (57, 36.01, True), (57, 66.11, True), (57, 108, True), (57, 108.01, False), (57, 252.84, False),
    (39.99, 0, False), (40, 0, True)])
def test_memory_check_keeps_40_gib_and_admits_up_to_six_loads_per_cpu(monkeypatch, memory, load, admitted):
    """18 CPUs: the old cutoff was 36; the default limit is 108. The 40 GiB floor is unchanged."""
    monkeypatch.delenv(bridge.host.MAX_LOAD_PER_CPU_ENV, raising=False)
    monkeypatch.setattr(bridge.host, "measure", lambda: {"available_gib": memory, "load_1m": load, "cpu_count": 18})
    if admitted:
        assert bridge.memory_check() == {"available_gib": memory, "load_1m": load, "cpu_count": 18,
                                         "minimum_available_gib": 40, "max_load_per_cpu": 6.0,
                                         "load_limit": 108.0, "admitted": True}
    else:
        with pytest.raises(RuntimeError, match="Host saturated: .*bridge stops before new jobs"):
            bridge.memory_check()


def test_preexisting_pilot_fiscal_tamper_is_rejected_even_with_matching_snapshot(monkeypatch):
    """Current-file consistency cannot authorize changed historical figures."""
    args, preflights, batches = stub_bridge_main(monkeypatch)
    target = Path("data/pilot/model_v2_e.json")
    real_read = Path.read_bytes
    original = real_read(target)
    changed = json.loads(original)
    changed["fiscal"]["central"][0]["value_bn"] += 1
    changed_bytes = json.dumps(changed).encode()

    def preexisting_change(path):
        return changed_bytes if path.resolve() == target.resolve() else real_read(path)

    # Both the initial snapshot and parser see identical tampered bytes;
    # only the immutable reviewed historical identity rejects the change.
    monkeypatch.setattr(Path, "read_bytes", preexisting_change)
    snapshot = bridge.execution_snapshot()
    assert snapshot["bridge_files"][str(target)] == hashlib.sha256(changed_bytes).hexdigest()
    assert bridge.read_snapshot_bytes(target, snapshot) == changed_bytes
    with pytest.raises(AssertionError, match="sanitized artifact bytes changed"):
        bridge.main(args)
    assert preflights == [] and batches == [] and not args.out.exists()
    assert real_read(target) == original


def stub_scheduler(monkeypatch, tmp_path):
    """Exercise the actual scheduler without a model, package probe or child."""
    launched = []
    monkeypatch.setattr(bridge.jobs, "WORKDIRS", tmp_path / "workers")
    monkeypatch.setattr(bridge.jobs, "engine_semantics", lambda: {"synthetic": "scheduler"})
    monkeypatch.setattr(bridge.jobs, "package_versions", lambda: {})
    monkeypatch.setattr(bridge.jobs, "cached", lambda *a, **kw: None)
    monkeypatch.setattr(bridge.jobs, "_run_isolated", lambda *a: launched.append(a) or {"safe": True})
    return launched


def test_saturation_cancels_worker_held_in_slot_until_release(monkeypatch, tmp_path):
    """A slot released after monitor exit cannot admit its waiting worker."""
    launched = stub_scheduler(monkeypatch, tmp_path)
    waiting, release, saturated, stopped = (threading.Event() for _ in range(4))
    shared_stops, errors = [], []

    @contextlib.contextmanager
    def held_slot(workdir, *a, stop=None, **kw):
        waiting.set()
        assert release.wait(10)
        yield  # deliberately model a release racing cancellation's lock check

    def memory_check(max_load_per_cpu=None, minimum_gib=40):
        if saturated.is_set():
            raise RuntimeError("Host saturated")
        return {"available_gib": 80, "load_1m": 0}

    kill_children = bridge.jobs.kill_children

    def kill_with_shared_stop(stop=None, **kw):
        shared_stops.append(stop)
        result = kill_children(stop, **kw)
        stopped.set()
        return result

    def run():
        try:
            bridge.run_batch([("central", ("path", {"synthetic": True}))], 1,
                             tmp_path / "cache", monitor_interval=.01)
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(bridge.jobs, "slot_lock", held_slot)
    monkeypatch.setattr(bridge.jobs, "kill_children", kill_with_shared_stop)
    monkeypatch.setattr(bridge, "memory_check", memory_check)
    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert waiting.wait(10)
        saturated.set()
        assert stopped.wait(10)
        assert len(shared_stops) == 1 and shared_stops[0] is not None and shared_stops[0].is_set()
        release.set()
        worker.join(10)
        assert not worker.is_alive()
        assert len(errors) == 1 and "host saturation" in str(errors[0])
        assert launched == []
    finally:
        release.set()
        worker.join(10)


def test_bridge_rechecks_host_inside_acquired_slot_before_launch(monkeypatch, tmp_path):
    launched = stub_scheduler(monkeypatch, tmp_path)
    inside_slot, host_checks, shared_stops = [], [], []

    @contextlib.contextmanager
    def acquired_slot(*a, **kw):
        inside_slot.append(True)
        try:
            yield
        finally:
            inside_slot.clear()

    def memory_check(max_load_per_cpu=None, minimum_gib=40):
        host_checks.append(bool(inside_slot))
        assert inside_slot
        raise RuntimeError("Host became saturated while waiting for a slot")

    kill_children = bridge.jobs.kill_children

    def kill_with_shared_stop(stop=None, **kw):
        shared_stops.append(stop)
        return kill_children(stop, **kw)

    monkeypatch.setattr(bridge.jobs, "slot_lock", acquired_slot)
    monkeypatch.setattr(bridge.jobs, "kill_children", kill_with_shared_stop)
    monkeypatch.setattr(bridge, "memory_check", memory_check)
    with pytest.raises(RuntimeError, match="host saturation"):
        bridge.run_batch([("central", ("path", {"synthetic": True}))], 1,
                         tmp_path / "cache", monitor_interval=10)
    assert host_checks == [True] and launched == []
    assert len(shared_stops) == 1 and shared_stops[0].is_set()
