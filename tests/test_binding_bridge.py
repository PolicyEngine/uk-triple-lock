"""The pending two-step bridge is exercised with a stub engine only."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import binding_bridge
from scripts import run_model_v2_j_bridge as bridge
from triple_lock.engine import _keys_to_int


ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / "data/binding-bridge.pending.json"


def ready_configuration():
    config = json.loads(PENDING.read_text())
    config["status"] = "ready"
    new_packages = {"policyengine": "9.0.0", "policyengine-uk": "3.0.0", "policyengine-core": "4.0.0"}
    config["steps"]["model"]["to"]["packages"] = dict(new_packages)
    config["steps"]["data"]["from"]["packages"] = dict(new_packages)
    config["steps"]["data"]["to"]["packages"] = dict(new_packages)
    config["steps"]["data"]["to"]["dataset"]["sha256"] = "b" * 64
    return config


def dataset_provenance(endpoint):
    packages = endpoint["packages"]
    return {"dataset": endpoint["dataset"]["name"],
            "runtime_dataset_sha256": endpoint["dataset"]["sha256"],
            "bundle_version": packages["policyengine"], "model_version": packages["policyengine-uk"],
            "core_version": packages["policyengine-core"], "certified": True}


def fake_run(value):
    return {"saving_bn": {y: {"gross": value, "net": value - .5,
                               "gb": {"gross": value, "net": value - .5}} for y in bridge.YEARS},
            "saving_support_records_by_year": {
                y: {geo: {measure: count for measure in ("gross", "net", "offset")}
                    for geo, count in (("uk", 20), ("gb", 10))} for y in bridge.YEARS}}


def fake_coverage(value):
    return {"rows": [{"year": 2024, "metric": "state_pension_bn", "unit": "£bn", "status": "available",
                      "UK": value, "GB": value - .5}]}


def test_pending_bundle_cannot_be_run():
    with pytest.raises(ValueError, match="bundle is pending"):
        binding_bridge.validate_configuration(json.loads(PENDING.read_text()))


@pytest.mark.parametrize("part,endpoint,field,value,message", [
    ("model", "to", "dataset", {"name": "enhanced_frs_2024_25@1.58.2", "sha256": "b" * 64}, "hold dataset"),
    ("data", "to", "packages", {"policyengine": "10.0.0", "policyengine-uk": "3.0.0", "policyengine-core": "4.0.0"}, "hold the model"),
    ("data", "from", "dataset", {"name": "enhanced_frs_2024_25@1.58.1", "sha256": "c" * 64}, "must chain"),
])
def test_each_step_changes_only_its_claim_and_the_steps_chain(part, endpoint, field, value, message):
    configuration = ready_configuration()
    binding_bridge.validate_configuration(configuration)
    configuration["steps"][part][endpoint][field] = value
    with pytest.raises(ValueError, match=message):
        binding_bridge.validate_configuration(configuration)


@pytest.mark.parametrize("package", binding_bridge.PACKAGES)
def test_declared_package_pins_must_match_the_actual_runtime(package):
    endpoint = ready_configuration()["steps"]["model"]["to"]
    actual = dict(endpoint["packages"])
    actual[package] = "wrong"
    with pytest.raises(ValueError, match="runtime from/to does not match"):
        binding_bridge.validate_runtime(endpoint, actual, dataset_provenance(endpoint))


@pytest.mark.parametrize("field,value", [("dataset", "enhanced_frs_2024_25@1.58.2"),
                                        ("runtime_dataset_sha256", "0" * 64), ("model_version", "wrong")])
def test_declared_dataset_and_model_pins_must_match_provenance(field, value):
    endpoint = ready_configuration()["steps"]["model"]["to"]
    actual = dataset_provenance(endpoint)
    actual[field] = value
    with pytest.raises(ValueError, match="does not match"):
        binding_bridge.validate_runtime(endpoint, endpoint["packages"], actual)


@pytest.fixture
def stub_engine(monkeypatch, tmp_path):
    """Run the real entry point, frozen design and receipt comparisons only."""
    monkeypatch.chdir(tmp_path)
    for name in ("d_macro_specs.json", "model_v2_e.json", "cold-source-binding.json"):
        target = tmp_path / "data/pilot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / "data/pilot" / name).read_bytes())
    config = ready_configuration()
    specs_raw = Path("data/pilot/d_macro_specs.json").read_bytes()
    specs = _keys_to_int(json.loads(specs_raw))
    planned, sample, weights = bridge.design(specs, config["steps"]["model"]["from"]["dataset"]["name"])
    design = {"indices_by_stratum": sample, "probabilities_by_stratum": weights,
              "n_first_phase": 50000, "seed": 20260929, "zero_probability": specs["identical_rates_probability"]}
    baseline_endpoint = config["steps"]["model"]["from"]
    baseline = {"complete": True, "quote_eligible": False,
                "provenance": {"packages": baseline_endpoint["packages"],
                               "dataset": dataset_provenance(baseline_endpoint),
                               "engine_hashes": {"stub-engine": "old"},
                               "specs_sha256": hashlib.sha256(specs_raw).hexdigest()},
                "paired_macro_design": design,
                "fiscal": bridge.saving_tables({name: fake_run(2) for name, _ in planned if name != "coverage"},
                                                sample, weights),
                "coverage": fake_coverage(2)}
    baseline_path = Path("data/pilot/baseline.json")
    baseline_path.write_text(json.dumps(baseline))
    config["baseline_receipt"]["sha256"] = bridge.digest(baseline_path)
    Path("data/binding-bridge.json").write_text(json.dumps(config))
    installed = {"endpoint": config["steps"]["model"]["to"]}
    calls, preflights = [], []

    def snapshot():
        files = [Path("data/pilot") / name for name in ("d_macro_specs.json", "model_v2_e.json", "cold-source-binding.json")]
        return {"git_revision": "stub-revision", "engine_hashes": {"stub-engine": "new"},
                "packages": deepcopy(installed["endpoint"]["packages"]),
                "bridge_files": {str(path): bridge.digest(path) for path in files}}

    def run_batch(batch, workers, cache, **kwargs):
        calls.extend(deepcopy(batch))
        value = 5 if installed["endpoint"]["dataset"]["name"].endswith("1.58.2") else 3
        return [fake_run(value) if kind == "path" else fake_coverage(value) for _, (kind, arg) in batch]

    def preflight():
        preflights.append(True)
        return {"passed": True}

    monkeypatch.setattr(bridge, "execution_snapshot", snapshot)
    monkeypatch.setattr(bridge.datasets, "provenance", lambda name: dataset_provenance(installed["endpoint"]))
    monkeypatch.setattr(bridge.pipeline, "housing_benefit_passport_preflight", preflight)
    monkeypatch.setattr(bridge, "memory_check", lambda **kwargs: {})
    monkeypatch.setattr(bridge.engine, "cached", lambda *args, **kwargs: None)
    monkeypatch.setattr(bridge, "run_batch", run_batch)
    monkeypatch.setattr(bridge, "coverage_tables", lambda run: run)
    return config, installed, calls, preflights


def run_step(step, source, output):
    args = bridge.argument_parser().parse_args([
        "--config", "data/binding-bridge.json", "--step", step,
        "--from-receipt", str(source), "--workers", "3", "--out", str(output)])
    bridge.main(args)
    return json.loads(Path(output).read_text())


def test_stub_engine_runs_separate_model_and_data_steps_on_the_same_paired_design(stub_engine):
    config, installed, calls, preflights = stub_engine
    model = run_step("model", "data/pilot/baseline.json", "data/pilot/model.json")
    model_jobs = deepcopy(calls)
    calls.clear()
    installed["endpoint"] = config["steps"]["data"]["to"]
    data = run_step("data", "data/pilot/model.json", "data/pilot/data.json")
    assert len(model_jobs) == len(calls) == 42
    assert all(arg["dataset"].endswith("1.58.0") for _, (_, arg) in model_jobs)
    assert all(arg["dataset"].endswith("1.58.2") for _, (_, arg) in calls)
    assert preflights == [True, True]
    assert model["complete"] is data["complete"] is True
    assert model["quote_eligible"] is data["quote_eligible"] is False
    assert model["bridge"]["declared_pins"] == config["steps"]["model"]["to"] == config["steps"]["data"]["from"]
    assert data["bridge"]["from_receipt"]["sha256"] == bridge.digest("data/pilot/model.json")
    assert model["paired_macro_design"] == data["paired_macro_design"]
    for receipt, difference in ((model, 1), (data, 2)):
        assert len(receipt["comparison"]["central"]) == len(receipt["comparison"]["paired"]) == 8
        assert receipt["comparison"]["central"][0]["difference_bn"] == pytest.approx(difference)
        assert receipt["comparison"]["paired"][0]["difference_bn"] == pytest.approx(difference * .99214)
        assert receipt["comparison"]["coverage"][0]["difference"]["UK"] == difference
        assert receipt["comparison"]["paired"][0]["difference_se"] is None
        assert "se" in receipt["comparison"]["paired"][0]["from"]


def test_data_step_refuses_a_separate_from_receipt_even_with_matching_pins(stub_engine):
    config, installed, calls, preflights = stub_engine
    model = run_step("model", "data/pilot/baseline.json", "data/pilot/model.json")
    model["bridge"]["endpoint"] = "from"
    Path("data/pilot/model.json").write_text(json.dumps(model))
    installed["endpoint"] = config["steps"]["data"]["to"]
    calls.clear()
    with pytest.raises(ValueError, match="must reuse the model/to receipt"):
        run_step("data", "data/pilot/model.json", "data/pilot/data.json")
    assert calls == [] and preflights == [True]


def test_data_step_refuses_changed_engine_sources(stub_engine):
    config, installed, calls, preflights = stub_engine
    model = run_step("model", "data/pilot/baseline.json", "data/pilot/model.json")
    model["provenance"]["engine_hashes"] = {"stub-engine": "changed"}
    Path("data/pilot/model.json").write_text(json.dumps(model))
    installed["endpoint"] = config["steps"]["data"]["to"]
    calls.clear()
    with pytest.raises(ValueError, match="hold engine sources fixed"):
        run_step("data", "data/pilot/model.json", "data/pilot/data.json")
    assert calls == [] and preflights == [True]


@pytest.mark.parametrize("tamper", ["package", "dataset", "receipt_bytes", "design"])
def test_source_receipt_tampering_is_refused_before_preflight_or_jobs(stub_engine, tamper):
    _, _, calls, preflights = stub_engine
    source = Path("data/pilot/baseline.json")
    receipt = json.loads(source.read_text())
    if tamper == "package":
        receipt["provenance"]["packages"]["policyengine-uk"] = "wrong"
    elif tamper == "dataset":
        receipt["provenance"]["dataset"]["runtime_dataset_sha256"] = "0" * 64
    elif tamper == "design":
        receipt["paired_macro_design"]["seed"] += 1
    else:
        receipt["fiscal"]["central"][0]["value_bn"] += 1
    source.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        run_step("model", source, "data/pilot/model.json")
    assert calls == [] and preflights == []


def test_runtime_pin_mismatch_is_refused_before_preflight_or_jobs(stub_engine):
    _, installed, calls, preflights = stub_engine
    installed["endpoint"] = deepcopy(installed["endpoint"])
    installed["endpoint"]["packages"]["policyengine-uk"] = "wrong"
    with pytest.raises(ValueError, match="runtime from/to does not match"):
        run_step("model", "data/pilot/baseline.json", "data/pilot/model.json")
    assert calls == [] and preflights == []


def test_historical_receipts_and_reviewed_recipe_remain_byte_identical():
    config = json.loads(PENDING.read_text())
    assert bridge.digest(ROOT / config["baseline_receipt"]["path"]) == config["baseline_receipt"]["sha256"]
    assert bridge.digest(ROOT / "data/pilot/J-bridge-model-step.json") == "e0576b897c81852b8961cd03538c46159e0bc16b8db9ba5ee50ea49a46c292b7"
    recipe = json.loads((ROOT / "data/pilot/d_macro_specs.json").read_bytes())
    assert hashlib.sha256(bridge.engine._canonical(recipe).encode()).hexdigest() == bridge.REVIEWED_RECIPE_SHA256


def test_real_historical_baseline_matches_the_declared_from_pins_and_frozen_design():
    configuration = ready_configuration()
    raw = (ROOT / configuration["baseline_receipt"]["path"]).read_bytes()
    specs_raw = (ROOT / "data/pilot/d_macro_specs.json").read_bytes()
    specs = _keys_to_int(json.loads(specs_raw))
    _, sample, weights = bridge.design(specs, configuration["steps"]["model"]["from"]["dataset"]["name"])
    paired_design = {"indices_by_stratum": sample, "probabilities_by_stratum": weights,
                     "n_first_phase": 50000, "seed": 20260929,
                     "zero_probability": specs["identical_rates_probability"]}
    binding_bridge.validate_source_receipt(configuration, "model", json.loads(raw), raw, paired_design,
                                          hashlib.sha256(specs_raw).hexdigest())


def test_final_data_endpoint_requires_certification(stub_engine, monkeypatch):
    config, installed, calls, preflights = stub_engine
    run_step("model", "data/pilot/baseline.json", "data/pilot/model.json")
    installed["endpoint"] = config["steps"]["data"]["to"]
    calls.clear()
    monkeypatch.setattr(bridge.datasets, "provenance", lambda name: {
        **dataset_provenance(installed["endpoint"]), "certified": False})
    with pytest.raises(ValueError, match="exact dataset certification"):
        run_step("data", "data/pilot/model.json", "data/pilot/data.json")
    assert calls == [] and preflights == [True]


def test_comparison_preserves_suppression():
    before = {"fiscal": {kind: [{"geography": "UK", "year": 2039, "measure": "gross", "status": "available",
                                ("value_bn" if kind == "central" else "estimate_bn"): 2 if kind == "central" else {"mean": 2}}]
                          for kind in ("central", "paired")},
              "coverage": fake_coverage(2), "paired_macro_design": {}}
    after = deepcopy(before)
    for kind in ("central", "paired"):
        after["fiscal"][kind][0]["status"] = "withheld_family"
    after["coverage"]["rows"][0]["status"] = "withheld_family"
    comparison = binding_bridge.compare(before, after)
    for kind in ("central", "paired"):
        assert comparison[kind][0]["from"] is comparison[kind][0]["to"] is comparison[kind][0]["difference_bn"] is None
    assert comparison["coverage"][0]["difference"] == {"UK": None, "GB": None}


def test_bridge_launch_refusal_keeps_host_saturated_and_its_decisions(monkeypatch, tmp_path):
    reading = {"available_gib": 39.0, "load_1m": 0.0, "cpu_count": 18}
    monkeypatch.setattr(bridge.host, "measure", lambda: dict(reading))

    def launch(jobs, *, admission, stop, **kwargs):
        admission("path", {}, tmp_path, stop)
        pytest.fail("refused bridge job was admitted")

    monkeypatch.setattr(bridge.jobs, "run_jobs", launch)
    with pytest.raises(bridge.host.HostSaturated) as error:
        bridge.run_batch([("central", ("path", {}))], 1, tmp_path / "cache", monitor_interval=10)
    decision = error.value.host_admissions[0]
    assert error.value.host_admission == decision
    assert decision["available_gib"] == 39.0 and decision["minimum_available_gib"] == 40
    assert decision["admitted"] is False
