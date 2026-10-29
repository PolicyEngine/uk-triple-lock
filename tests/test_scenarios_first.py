"""The scenarios-first interim file, the d2124 forecast vintages and the binding release's limitation wording.

pipeline.build(mean_paths=False), behind ``triple-lock-build --without-mean-paths --out PATH``, runs every job of the
full build except the paired mean paths and writes an interim file. These tests run no model and open no dataset.
"""

import copy
import json
import os
import re
import sys
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import cli, config, pipeline
from triple_lock.rules import round_rate, triple_lock_source
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


INTERIM = ["--workers", "1", "--uncertainty-ruling", "c", "--uncertainty-handoff", "out/uncertainty-c2", "--without-mean-paths"]


def test_cli_writes_only_the_interim_file(cli_build, tmp_path):
    out = tmp_path / "scenarios-first.json"
    assert cli.main([*INTERIM, "--out", str(out)]) == 0
    assert cli_build["build"][0]["mean_paths"] is False
    assert cli_build["write"] == []  # not the results file, its dashboard copy or a scenario file
    assert json.loads(out.read_text()) == {"results": 1}


def test_the_interim_file_has_pipeline_write_s_text(tmp_path):
    results = {"b": [1.5, 2], "a": {"x": None}}
    cli.write_interim(results, tmp_path / "interim.json")
    pipeline.write(results, [tmp_path / "written.json"])
    assert (tmp_path / "interim.json").read_bytes() == (tmp_path / "written.json").read_bytes()


def test_cli_refuses_an_interim_destination_with_a_second_name(cli_build, tmp_path):
    published = tmp_path / "results.json"
    published.write_text("published\n")
    alias = tmp_path / "interim.json"
    os.link(published, alias)  # an ignored file that is really the results file
    with pytest.raises(SystemExit):
        cli.main([*INTERIM, "--out", str(alias)])
    assert cli_build["build"] == [] and published.read_text() == "published\n"


@pytest.fixture
def publication(monkeypatch, tmp_path):
    """A scratch results file, dashboard copy and scenario directory in place of the repository's."""
    data = tmp_path / "data"
    (data / "scenarios").mkdir(parents=True)
    (data / "scenarios" / "obr_premium.json").write_text("scenario\n")
    (data / "results.json").write_text("results\n")
    (tmp_path / "copy.json").write_text("copy\n")
    monkeypatch.setattr(cli, "OUTPUT", data / "results.json")
    monkeypatch.setattr(cli, "DASHBOARD_COPY", tmp_path / "copy.json")
    monkeypatch.setattr(cli, "SCENARIO_DIR", data / "scenarios")
    return tmp_path


def _case_insensitive(directory):
    probe = directory / "Case-Probe"
    probe.write_text("")
    try:
        return (directory / "case-probe").exists()
    finally:
        probe.unlink()


@pytest.mark.parametrize("alias", ["data/RESULTS.JSON", "DATA/results.json", "data/SCENARIOS/nested/interim.json",
                                   "data/Scenarios/obr_premium.json", "data/scenarios/../scenarios/x.json"])
def test_the_interim_guard_compares_paths_by_identity_not_spelling(cli_build, publication, alias):
    if alias != "data/scenarios/../scenarios/x.json" and not _case_insensitive(publication):
        pytest.skip("a case-sensitive volume has no case aliases")
    with pytest.raises(SystemExit):
        cli.main([*INTERIM, "--out", str(publication / alias)])
    assert cli_build["build"] == []
    assert (publication / "data" / "results.json").read_text() == "results\n"


def test_the_interim_guard_refuses_a_symlinked_entry_or_directory(cli_build, publication):
    outside = publication / "outside.json"
    outside.write_text("outside\n")
    entry = publication / "data" / "scenarios" / "linked.json"
    entry.symlink_to(outside)  # resolves outside the scenario directory, but the write would replace the entry
    to_scenarios = publication / "to-scenarios"
    to_scenarios.symlink_to(publication / "data" / "scenarios", target_is_directory=True)
    plain_link = publication / "plain-link.json"
    plain_link.symlink_to(outside)
    for out in (entry, to_scenarios / "interim.json", plain_link):
        with pytest.raises(SystemExit):
            cli.main([*INTERIM, "--out", str(out)])
    assert cli_build["build"] == [] and entry.is_symlink() and outside.read_text() == "outside\n"


def test_the_interim_write_refuses_a_destination_that_became_a_symlink_during_the_build(monkeypatch, tmp_path):
    out, outside = tmp_path / "interim.json", tmp_path / "outside.json"
    outside.write_text("outside\n")

    def build(**kwargs):
        out.symlink_to(outside)
        return {"results": 3}, {}

    monkeypatch.setattr(pipeline, "build", build)
    with pytest.raises(SystemExit, match="symbolic link"):
        cli.main([*INTERIM, "--out", str(out)])
    assert out.is_symlink() and outside.read_text() == "outside\n"


def test_the_interim_write_refuses_a_destination_that_became_the_results_file_during_the_build(monkeypatch, publication):
    out = publication / "interim.json"

    def build(**kwargs):
        os.link(publication / "data" / "results.json", out)  # the destination is now the results file's inode
        return {"results": 4}, {}

    monkeypatch.setattr(pipeline, "build", build)
    with pytest.raises(SystemExit, match="must not write the results file"):
        cli.main([*INTERIM, "--out", str(out)])
    assert (publication / "data" / "results.json").read_text() == "results\n"


def test_the_interim_write_leaves_a_link_made_during_the_build_alone(monkeypatch, tmp_path):
    out = tmp_path / "interim.json"
    out.write_text("old\n")
    other = tmp_path / "other.json"

    def build(**kwargs):
        os.link(out, other)  # someone links the destination while the build runs
        return {"results": 2}, {}

    monkeypatch.setattr(pipeline, "build", build)
    assert cli.main([*INTERIM, "--out", str(out)]) == 0
    assert other.read_text() == "old\n" and json.loads(out.read_text()) == {"results": 2}


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
    ["--without-mean-paths", "--out", str(config.SCENARIO_DIR / "nested" / "interim.json")],
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


def test_forecast_vintage_titles_name_the_month_the_dashboard_shows():
    # dashboard/src/lib/dataHelpers.js getForecastVintages takes the first "Month YYYY" in each title.
    month_year = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})\b")
    vintages = pipeline.forecast_vintages()
    assert month_year.search(vintages["forecast"]["title"]).group(0) == "October 2026"
    assert month_year.search(vintages["long_term"]["title"]).group(0) == "March 2026"


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


@pytest.mark.parametrize("cpi,earnings,says", [(0.034, 0.034, True), (0.034, 0.035, False), (0.025, 0.02, False),
                                               (0.026, 0.026, True), (0.025, 0.025, False)])
def test_the_guarantee_limitation_counts_a_tie_above_the_floor_as_cpi(cpi, earnings, says):
    central = copy.deepcopy(pipeline.central_module.central_path())
    central["statutory"]["cpi"][2027], central["statutory"]["earnings"][2027] = cpi, earnings
    (guarantee,) = [w for w in pipeline.method_limitations(central) if "Pension Credit guarantee's rises" in w]
    assert ("September CPI" in guarantee) is says


@settings(max_examples=150, deadline=None)
@given(cpi=rate, earnings=rate)
def test_the_guarantee_limitation_says_cpi_sets_the_rise_exactly_when_it_does(cpi, earnings):
    central = copy.deepcopy(pipeline.central_module.central_path())
    central["statutory"]["cpi"][2027], central["statutory"]["earnings"][2027] = cpi, earnings
    (guarantee,) = [w for w in pipeline.method_limitations(central) if "Pension Credit guarantee's rises" in w]
    # The rule's own label: CPI above the floor that ties or beats earnings (the review's tie case included).
    cpi_sets_it = round_rate(cpi) > config.TRIPLE_LOCK_FLOOR and round_rate(cpi) >= round_rate(earnings)
    assert ("September CPI" in guarantee) is cpi_sets_it
    assert cpi_sets_it is (triple_lock_source(round_rate(cpi), round_rate(earnings)) == "cpi")
    assert f"({round_rate(earnings):.1%} in 2027" in guarantee
