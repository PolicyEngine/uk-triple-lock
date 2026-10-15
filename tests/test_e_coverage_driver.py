"""Coverage-only recipe completeness, isolation and aggregate disclosure checks."""

import importlib.util
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("e_coverage_driver", SCRIPTS / "run_model_v2_e_coverage.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def design():
    helper = driver.shared_driver(SCRIPTS / "run_model_v2_e_pilot.py")
    specifications = {"central": {"id": "central"}, "september_cpi_history": {},
                      "paired": {i: {"stratum": 1 + i // 4, "times_drawn": 1, "spec": {"id": f"draw_{i}"}}
                                 for i in range(40)},
                      "paired_strata_probability": {i: .09 for i in range(1, 11)}, "identical_rates_probability": .1}
    return driver.plan(specifications, {"n": 50000, "seed": 41, "shocks": "boot"}, helper), helper


def test_six_complete_coverage_jobs_and_no_fiscal_path_jobs(tmp_path):
    planned, helper = design()
    assert len(planned["jobs"]) == 6
    assert {label[1] for label in planned["labels"]} == set(helper.TREATMENTS)
    for kind, argument in planned["jobs"]:
        assert kind == "coverage"
        assert argument["years"] == list(helper.COVERAGE_YEARS)
        assert argument["dataset"] == driver.PRIMARY
    outputs = [{"mode": mode} for _, mode in planned["labels"]]
    def fake_runner(jobs, **kwargs):
        assert jobs == planned["jobs"] and kwargs["cache"] == tmp_path and kwargs["workers"] == 3
        return outputs
    assert set(driver.execute(planned, fake_runner, 3, tmp_path)) == set(helper.TREATMENTS)
    with pytest.raises(ValueError, match="at most three"):
        driver.execute(planned, fake_runner, 4, tmp_path)
    with pytest.raises(ValueError):
        driver.execute(planned, lambda *args, **kwargs: outputs[:-1], 1, tmp_path)


def test_receipts_preserve_suppression_and_fail_on_missing_actual_support():
    coverage = {"both_full_new": {"by_year": {2039: {}}, "state_pension_country_contrast_support": {
        2039: {"ENGLAND": {"status": "suppressed", "records": None},
               "SCOTLAND": {"status": "available", "records": 10},
               "WALES": {"status": "available", "records": 0}}}}}
    countries = ("ENGLAND", "SCOTLAND", "WALES")
    rows = driver.support_receipts(coverage, countries)
    assert rows == [
        {"treatment": "both_full_new", "year": 2039, "country": "ENGLAND", "status": "suppressed", "contributing_records": None},
        {"treatment": "both_full_new", "year": 2039, "country": "SCOTLAND", "status": "available", "contributing_records": 10},
        {"treatment": "both_full_new", "year": 2039, "country": "WALES", "status": "available", "contributing_records": 0},
    ]
    coverage["both_full_new"]["state_pension_country_contrast_support"][2039]["SCOTLAND"]["records"] = 9
    assert driver.support_receipts(coverage, countries)[1]["contributing_records"] is None
    del coverage["both_full_new"]["state_pension_country_contrast_support"][2039]["SCOTLAND"]
    with pytest.raises(ValueError, match="actual model support"):
        driver.support_receipts(coverage, countries)


def test_source_hashes_include_scientific_python_and_dependency_declarations(tmp_path):
    (tmp_path / "src" / "triple_lock").mkdir(parents=True)
    scientific = tmp_path / "src" / "triple_lock" / "engine.py"
    scientific.write_text("engine = 1\n")
    for declaration in ("pyproject.toml", "requirements-lock.txt"):
        (tmp_path / declaration).write_text("pinned dependencies\n")
    before = driver.source_hashes(tmp_path)
    assert set(before) == {"src/triple_lock/engine.py", "pyproject.toml", "requirements-lock.txt"}
    scientific.write_text("engine = 2\n")
    assert driver.source_hashes(tmp_path)["src/triple_lock/engine.py"] != before["src/triple_lock/engine.py"]
