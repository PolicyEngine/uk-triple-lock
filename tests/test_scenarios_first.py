"""The scenarios-first interim file, the d2124 forecast vintages and the binding release's limitation wording.

pipeline.build(mean_paths=False), behind ``triple-lock-build --without-mean-paths --out PATH``, runs every job of the
full build except the paired mean paths and writes an interim file. These tests run no model and open no dataset.
"""

import copy
import json
import sys
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import cli, config, pipeline
from triple_lock.rules import round_rate
from triple_lock.ts_uncertainty import PRIMARY_FORM

BINDING_HANDOFF = config.REPO / "data" / "pilot" / "c2-binding" / "handoff.json"


@pytest.fixture
def binding_manifest():
    return json.loads(BINDING_HANDOFF.read_text())


def passing(manifest):
    manifest = copy.deepcopy(manifest)
    manifest["c2_outcome"]["forms"][PRIMARY_FORM]["passes"] = True
    manifest["c2_outcome"]["forms"][PRIMARY_FORM]["failures"] = []
    return manifest


def test_the_binding_handoff_allows_a_scenarios_first_file(binding_manifest):
    provenance = pipeline.scenarios_first_ruling(binding_manifest)
    assert provenance["requested_ruling"] == "c" and provenance["effective_ruling"] == "a"
    assert provenance["fallback_reason"].startswith("Original primary failed the frozen C2 statutory screen")


def test_a_passing_primary_refuses_a_scenarios_first_file(binding_manifest):
    with pytest.raises(SystemExit, match="passed, so the file has an expected value"):
        pipeline.scenarios_first_ruling(passing(binding_manifest))


@pytest.mark.parametrize("ruling,pre_budget", [("b", False), ("a", True), ("c", True)])
def test_build_refuses_a_scenarios_first_file_that_could_have_an_expected_value(monkeypatch, ruling, pre_budget):
    monkeypatch.setattr(pipeline, "snapshot", lambda: pytest.fail("refused before the build starts"))
    with pytest.raises(SystemExit, match="scenarios-first file needs"):
        pipeline.build(uncertainty_ruling=ruling, pre_budget=pre_budget, mean_paths=False, log=lambda _: None)


class Reached(Exception):
    pass


@pytest.fixture
def stubbed_build(monkeypatch, binding_manifest):
    """pipeline.build up to the expected-value route, with no model, dataset or job."""
    calls = {"jobs": []}
    handoff = {"manifest": binding_manifest}
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline.expected_value, "_handoff", lambda *a, **kw: ("binding", handoff["manifest"]))
    monkeypatch.setattr(pipeline, "certified_bundle_preflight", lambda **kw: {})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda **kw: {})
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", SimpleNamespace(system=SimpleNamespace(parameters=None)))
    monkeypatch.setattr(pipeline.engine, "base_levels", lambda parameters: {"new_state_pension": 241.3,
                                                                            "basic_state_pension": 184.9})

    def run_jobs(batch, **kwargs):
        calls["jobs"].append([kind for kind, _ in batch])
        return [{"model": {}} for _ in batch]

    def expected_value_build(*args, **kwargs):
        calls["expected_value"] = kwargs
        raise Reached

    monkeypatch.setattr(pipeline.jobs, "run_jobs", run_jobs)
    monkeypatch.setattr(pipeline.expected_value, "build", expected_value_build)
    return calls, handoff


@pytest.mark.parametrize("mean_paths", [False, True])
def test_build_passes_the_mean_path_choice_to_the_expected_value_route(stubbed_build, mean_paths):
    calls, _ = stubbed_build
    with pytest.raises(Reached):
        pipeline.build(uncertainty_ruling="c", uncertainty_handoff="binding", mean_paths=mean_paths,
                       log=lambda _: None)
    assert calls["expected_value"]["mean_paths"] is mean_paths
    # The same jobs run before it either way: the central path, then both coverage runs.
    assert calls["jobs"] == [["path"], ["coverage", "coverage"]]


def test_build_refuses_a_scenarios_first_file_before_any_job_if_the_primary_passed(stubbed_build, binding_manifest):
    calls, handoff = stubbed_build
    handoff["manifest"] = passing(binding_manifest)
    with pytest.raises(SystemExit, match="passed, so the file has an expected value"):
        pipeline.build(uncertainty_ruling="c", uncertainty_handoff="binding", mean_paths=False, log=lambda _: None)
    assert calls["jobs"] == []


@pytest.fixture
def cli_build(monkeypatch):
    calls = {"build": [], "write": []}
    monkeypatch.setattr(pipeline, "build", lambda **kwargs: (calls["build"].append(kwargs) or {"results": 1},
                                                             {"obr_premium": {}}))
    monkeypatch.setattr(pipeline, "write", lambda results, paths: calls["write"].append(list(paths)))
    return calls


def test_cli_writes_only_the_interim_file(cli_build, tmp_path):
    out = tmp_path / "scenarios-first.json"
    assert cli.main(["--workers", "1", "--uncertainty-ruling", "c", "--uncertainty-handoff", "out/uncertainty-c2",
                     "--without-mean-paths", "--out", str(out)]) == 0
    assert cli_build["build"][0]["mean_paths"] is False
    assert cli_build["write"] == [[out]]  # not the results file, its dashboard copy or a scenario file


def test_cli_full_build_keeps_its_mean_paths_and_outputs(cli_build):
    assert cli.main(["--uncertainty-ruling", "c"]) == 0
    assert cli_build["build"][0]["mean_paths"] is True
    assert cli_build["write"][0] == [config.OUTPUT, config.DASHBOARD_COPY]
    assert cli_build["write"][1] == [config.SCENARIO_DIR / "obr_premium.json"]


@pytest.mark.parametrize("arguments", [
    ["--without-mean-paths"],
    ["--without-mean-paths", "--out", str(config.OUTPUT)],
    ["--without-mean-paths", "--out", str(config.DASHBOARD_COPY)],
    ["--without-mean-paths", "--out", str(config.SCENARIO_DIR / "interim.json")],
    ["--without-mean-paths", "--out", "x.json", "--scenario", "obr_premium"],
    ["--without-mean-paths", "--out", "x.json", "--mean-path-scenarios"],
    ["--without-mean-paths", "--out", "x.json", "--pre-budget", "--uncertainty-ruling", "a"],
])
def test_cli_refuses_an_interim_file_that_could_replace_a_publication_output(cli_build, arguments):
    with pytest.raises(SystemExit):
        cli.main(["--uncertainty-ruling", "c", *arguments])
    assert cli_build["build"] == [] and cli_build["write"] == []


def test_the_scenarios_first_label_names_what_the_file_omits():
    label = pipeline.scenarios_first_label()
    assert label["interim"] is True
    assert label["omits"] == ["mean_path_scenarios", "scenario_envelope.paired_earnings_mean_paths"]
    assert "--uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2" in label["complete_build"]


# d2124: the October 2026 EFO to 2030, the March 2026 long-term determinants after.

def test_forecast_vintages_split_the_central_path_at_the_end_of_the_forecast():
    vintages = pipeline.forecast_vintages()
    assert vintages["decision"] == "d2124"
    assert vintages["forecast"]["calendar_years"] == [2026, 2030]
    assert vintages["forecast"]["april_rises"] == [2028, 2031]
    assert vintages["long_term"]["calendar_years"] == [2031, 2039]
    assert vintages["long_term"]["april_rises"] == [2032, 2039]
    assert "28 October 2026" in vintages["forecast"]["title"]
    assert "March 2026" in vintages["long_term"]["title"]


def test_forecast_vintages_refuse_a_path_that_switches_back():
    central = copy.deepcopy(pipeline.central_module.central_path())
    central["calendar_source"][2033] = "efo_calendar"
    with pytest.raises(pipeline.MissingFigure, match="one forecast vintage then another"):
        pipeline.forecast_vintages(central)


def test_the_binding_limitations_name_both_vintages_and_the_new_name():
    wording = pipeline.method_limitations()
    text = " ".join(wording)
    assert "Burnham" not in text
    assert "The adjusted Triple Lock from April 2030" in text
    (vintage,) = [w for w in wording if w.startswith("The central path follows the OBR's October 2026")]
    assert "calendar years 2026-2030" in vintage and "to April 2031" in vintage
    assert "March 2026 long-term economic determinants" in vintage and "2031 and later" in vintage
    # dashboard/src/components/MethodTab.jsx LIMIT_ROWS shows its short line only when these are present.
    for needed in ("long-term projection", "October 2026", "March 2026"):
        assert needed in vintage
    assert sum("Pension Credit guarantee's rises" in w for w in wording) == 1


def test_the_guarantee_limitation_quotes_the_central_path_s_inputs():
    central = pipeline.central_module.central_path()
    (guarantee,) = [w for w in pipeline.method_limitations() if "Pension Credit guarantee's rises" in w]
    earnings, cpi = (round_rate(central["statutory"][k][2027]) for k in ("earnings", "cpi"))
    assert f"({earnings:.1%} in 2027, for April 2028)" in guarantee
    assert f"September CPI ({cpi:.1%}) sets April 2028's State Pension rise" in guarantee
    assert "from April 2028 to April 2031" in guarantee


rate = st.floats(min_value=-0.02, max_value=0.12, allow_nan=False, allow_infinity=False)


@settings(max_examples=150, deadline=None)
@given(cpi=rate, earnings=rate)
def test_the_guarantee_limitation_says_cpi_sets_the_rise_exactly_when_it_does(cpi, earnings):
    central = copy.deepcopy(pipeline.central_module.central_path())
    central["statutory"]["cpi"][2027], central["statutory"]["earnings"][2027] = cpi, earnings
    (guarantee,) = [w for w in pipeline.method_limitations(central) if "Pension Credit guarantee's rises" in w]
    cpi_sets_it = round_rate(cpi) > max(round_rate(earnings), config.TRIPLE_LOCK_FLOOR)
    assert ("September CPI" in guarantee) is cpi_sets_it
    assert f"({round_rate(earnings):.1%} in 2027" in guarantee
