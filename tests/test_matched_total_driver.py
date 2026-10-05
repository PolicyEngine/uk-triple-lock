"""Matched-total design, model-read population receipts and exact reference guards."""

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("matched_total_driver", SCRIPTS / "run_model_v2_matched_total.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def design():
    specs = {"central": {"id": "central"}, "september_cpi_history": {},
             "paired": {i: {"stratum": 1 + i // 4, "times_drawn": 1, "spec": {"id": f"draw_{i}"}}
                        for i in range(40)},
             "paired_strata_probability": {i: .09 for i in range(1, 11)}, "identical_rates_probability": .1}
    return driver.plan(specs, {"n": 50000, "seed": 41, "shocks": "boot"},
                       driver.shared_driver(SCRIPTS / "run_model_v2_e_pilot.py"))


def grouped_runs(planned):
    def result(mode):
        targets = {year: float(year + 1000) for year in range(2027, 2040)}
        return {"saving_bn": {2034: {"gross": 1., "net": 2.}, 2039: {"gross": 3., "net": 4.}},
                "totals_bn": {"triple_lock": {2034: {"state_pension_flat_rate": 5.}},
                              "burnham_2030": {2034: {"state_pension_flat_rate": 6.}}},
                "rates": {"triple_lock": [1.]}, "statutory": {"cpi": [2.]},
                "fixed_inputs": {"ageing": {"weights_unchanged_through_anchor": True,
                                              "target_population_people_by_year": targets},
                                 "held_pension_type_records": {year: {"BASIC": 100, "NEW": 100, "NONE": 100}
                                                               for year in targets},
                                 "held_pension_type_people": {year: {"BASIC": target / 2, "NEW": target / 2, "NONE": 0.}
                                                              for year, target in targets.items()}}}
    return {label: {mode: result(mode) for mode in driver.TREATMENTS} for label in planned["labels"]}


def test_supplement_has_41_full_three_mode_batches_and_no_coverage():
    planned = design()
    assert len(planned["execution_jobs"]) == len(planned["labels"]) == 41
    assert sum(map(len, planned["sample"].values())) == 40
    assert sum(planned["probabilities"].values()) + planned["identical_rates_probability"] == pytest.approx(1)
    assert planned["labels"][0] == "central" and planned["labels"][-1] == "draw_39"
    for kind, argument in planned["execution_jobs"]:
        assert kind == "treatment_paths" and argument["contrasts"] == driver.CONTRASTS
        assert set(argument["specs"]) == set(driver.TREATMENTS)
        assert all(spec["dataset"] == driver.PRIMARY and spec["demography"] == mode
                   and spec["retyped_level"] == "kept" and spec["fiscal_output_years"] == [2034, 2039]
                   for mode, spec in argument["specs"].items())
    original = driver.shared_driver(SCRIPTS / "run_model_v2_e_pilot.py")
    matched = driver.shared_driver(SCRIPTS / "run_model_v2_e_pilot.py", matched=True)
    assert len(original.TREATMENTS) == 6 and len(matched.TREATMENTS) == 3
    assert "total" in original.TREATMENTS and "total_matched" not in original.TREATMENTS


def test_execution_checks_worker_limit_and_every_independent_result(tmp_path):
    planned = design()
    grouped = grouped_runs(planned)
    def fake(jobs, **kwargs):
        assert jobs == planned["execution_jobs"] and kwargs["workers"] == 2 and kwargs["cache"] == tmp_path
        return list(grouped.values())
    assert driver.execute(planned, fake, 2, tmp_path) == grouped
    with pytest.raises(ValueError, match="at most two"):
        driver.execute(planned, fake, 3, tmp_path)
    with pytest.raises(ValueError, match="three treatment"):
        driver.execute(planned, lambda *args, **kwargs: [{"frozen": {}}] * 41, 1, tmp_path)


def test_population_receipt_checks_all_years_and_only_publishes_selected_aggregates():
    grouped = grouped_runs(design())
    receipt = driver.population_receipts(grouped)
    assert receipt["status"] == "passed" and len(receipt["rows"]) == 82
    assert {row["year"] for row in receipt["rows"]} == {2034, 2039}
    assert all(row["target_people"] == row["model_people"]["reweight"] == row["model_people"]["total_matched"]
               for row in receipt["rows"])
    # A missed unpublished year also fails the whole check.
    grouped["central"]["total_matched"]["fixed_inputs"]["held_pension_type_people"][2028]["BASIC"] += 1
    with pytest.raises(ValueError, match="shared matched-total target"):
        driver.population_receipts(grouped)
    grouped = grouped_runs(design())
    grouped["central"]["total_matched"]["fixed_inputs"]["held_pension_type_records"][2034] = {"BASIC": 9}
    with pytest.raises(ValueError, match="ten-record"):
        driver.population_receipts(grouped)


def test_exact_reference_proof_does_not_reuse_outputs_and_refuses_one_changed_cell(tmp_path):
    planned = design()
    grouped = grouped_runs(planned)
    reference = {"provenance": {"calculation_head": "a" * 40, "engine_semantics": {"engine": "old"},
                                 "packages": {"policyengine-uk": "2.120.0"}}}
    saved = deepcopy(grouped)
    def cached(kind, arg, **kwargs):
        assert kind == "treatment_paths" and "total" in arg["specs"]
        assert kwargs == {"engine": reference["provenance"]["engine_semantics"],
                          "packages": reference["provenance"]["packages"], "cache": tmp_path}
        return saved[arg["specs"]["frozen"]["id"]]
    engine = SimpleNamespace(cached=cached)
    proof = driver.check_reference(planned, grouped, reference, tmp_path, engine)
    assert proof["status"] == "passed" and proof["matched_runs"] == 82
    assert all(set(row) == {"path", "treatment", "exact_aggregate_match"} for row in proof["rows"])
    grouped["draw_39"]["reweight"]["saving_bn"][2039]["net"] += .000001
    with pytest.raises(ValueError, match="aggregates differ"):
        driver.check_reference(planned, grouped, reference, tmp_path, engine)
    with pytest.raises(ValueError, match="reference E batch is missing"):
        driver.check_reference(planned, grouped_runs(planned), reference, tmp_path,
                               SimpleNamespace(cached=lambda *args, **kwargs: None))
