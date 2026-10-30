"""The scenarios-first interim file, the d2124 forecast vintages and the binding release's limitation wording.

pipeline.build(mean_paths=False), behind ``triple-lock-build --without-mean-paths --out PATH``, runs every job of the
full build except the paired mean paths and writes an interim file. These tests run no model and open no dataset.
"""

import copy
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import event, given, settings
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


@pytest.mark.parametrize("link, target, out", [
    ("L", "data/scenarios", "L/../results.json"),  # the OS follows L first: data/results.json
    ("S", "data/scenarios/sub", "S/../obr_premium.json"),  # data/scenarios/obr_premium.json
    ("D", "sub/inner", "D/../../copy.json"),  # the dashboard copy (by spelling alone, a file above the tree)
    ("L", "data/scenarios", "L/../scenarios/new.json"),  # a new file in the scenario directory
])
def test_the_interim_guard_follows_a_symbolic_link_before_a_dotdot(cli_build, publication, link, target, out):
    """'..' after a symbolic link climbs from where the link leads, as the OS resolves it, not from the link."""
    (publication / "data" / "scenarios" / "sub").mkdir()
    (publication / "sub" / "inner").mkdir(parents=True)
    (publication / link).symlink_to(publication / target, target_is_directory=True)
    with pytest.raises(SystemExit):
        cli.main([*INTERIM, "--out", str(publication) + "/" + out])
    with pytest.raises(SystemExit):
        cli.write_interim({"results": 5}, str(publication) + "/" + out)
    assert cli_build["build"] == []
    assert (publication / "data" / "results.json").read_text() == "results\n"
    assert (publication / "copy.json").read_text() == "copy\n"
    assert sorted(p.name for p in (publication / "data" / "scenarios").iterdir()) == ["obr_premium.json", "sub"]


@pytest.mark.parametrize("out", [".", "..", "data/..", "data/."])
def test_the_interim_guard_refuses_a_name_that_is_a_directory(cli_build, publication, out):
    with pytest.raises(SystemExit):
        cli.main([*INTERIM, "--out", str(publication / out) if out != "." else "."])
    assert cli_build["build"] == []


def test_the_interim_guard_refuses_an_alias_of_a_protected_file_that_does_not_exist(cli_build, publication, monkeypatch):
    """With the protected file (or its whole directory) absent there is no inode to compare; the folded spelling,
    case and Unicode normalisation alike, still names it."""
    (publication / "data" / "results.json").unlink()
    monkeypatch.setattr(cli, "DASHBOARD_COPY", publication / "Dash" / "Données" / "copy.json")  # composed é
    for out in ("data/RESULTS.json", "dash/Données/COPY.JSON", "DASH/DONNÉES/copy.json"):
        with pytest.raises(SystemExit):
            cli.main([*INTERIM, "--out", str(publication / out)])
    assert cli_build["build"] == []


def test_the_interim_write_refuses_a_directory_swapped_for_a_link_after_the_check(monkeypatch, publication):
    """The directory becomes a symbolic link to data/ between the last path check and the write: the write holds the
    directory it checked (O_NOFOLLOW), so it fails rather than writing data/results.json."""
    work = publication / "work"
    work.mkdir()
    real = cli.destination
    calls = []

    def destination(out):
        entry = real(out)
        calls.append(entry)
        if len(calls) == 2:  # write_interim's own lookup, after interim_refusal's
            work.rename(publication / "work-moved")
            work.symlink_to(publication / "data", target_is_directory=True)
        return entry

    monkeypatch.setattr(cli, "destination", destination)
    with pytest.raises(OSError):
        cli.write_interim({"results": 6}, work / "results.json")
    assert (publication / "data" / "results.json").read_text() == "results\n"
    assert not (publication / "work-moved" / "results.json").exists()


def test_the_interim_write_refuses_a_redirect_made_after_the_path_check(monkeypatch, publication):
    """work/ becomes a link to data/ after the path re-check passed: the handle check, by identity, refuses it."""
    work = publication / "work"
    work.mkdir()
    real = cli.interim_refusal

    def interim_refusal(out, hardlinks=True):
        refused = real(out, hardlinks=hardlinks)
        work.rename(publication / "work-moved")
        work.symlink_to(publication / "data", target_is_directory=True)
        return refused

    monkeypatch.setattr(cli, "interim_refusal", interim_refusal)
    with pytest.raises(SystemExit, match="must not write the results file"):
        cli.write_interim({"results": 7}, work / "results.json")
    assert (publication / "data" / "results.json").read_text() == "results\n"


def test_a_directory_swapped_for_a_link_gets_no_new_subdirectory_where_it_points(monkeypatch, publication):
    """work/ becomes a link to data/scenarios after the path check, and the destination's directories don't exist
    yet: the write fails without creating anything in the scenario directory (review delta3, finding 1)."""
    work = publication / "work"
    work.mkdir()
    real = cli.destination
    calls = []

    def destination(out):
        entry = real(out)
        calls.append(entry)
        if len(calls) == 2:  # write_interim's own lookup, after interim_refusal's
            work.rename(publication / "work-moved")
            work.symlink_to(publication / "data" / "scenarios", target_is_directory=True)
        return entry

    monkeypatch.setattr(cli, "destination", destination)
    with pytest.raises((OSError, SystemExit)):
        cli.write_interim({"results": 8}, work / "new" / "nested" / "out.json")
    scenarios = publication / "data" / "scenarios"
    assert sorted(p.relative_to(scenarios).as_posix() for p in scenarios.rglob("*")) == ["obr_premium.json"]
    assert list((publication / "work-moved").iterdir()) == []


def test_the_directory_walk_creates_missing_parts_but_none_in_the_scenarios(publication):
    scenarios = publication / "data" / "scenarios"
    created = []
    with pytest.raises(SystemExit, match="must not write the results file"):
        cli._open_directory(scenarios / "new" / "nested", created)
    assert created == [] and sorted(p.name for p in scenarios.iterdir()) == ["obr_premium.json"]
    handle = cli._open_directory(publication / "work" / "a" / "b", created)
    try:
        assert (publication / "work" / "a" / "b").is_dir()
        assert cli._identity(os.fstat(handle)) == cli._identity(os.stat(publication / "work" / "a" / "b"))
        assert [name for _, name, _ in created] == ["work", "a", "b"]
    finally:
        os.close(handle)
        cli._release(created, remove=True)
    assert not (publication / "work").exists()  # removed, deepest first
    (publication / "work").mkdir()
    (publication / "link").symlink_to(publication / "work", target_is_directory=True)
    with pytest.raises(OSError):  # O_NOFOLLOW: a component that is a link is never followed
        cli._open_directory(publication / "link" / "c", created := [])
    assert created == [] and not (publication / "work" / "c").exists()


def test_a_stream_that_fails_to_open_leaks_no_descriptor_or_temporary_file(monkeypatch, publication):
    """os.fdopen raising after the temporary file exists (review delta3, finding 2)."""
    work = publication / "work"
    work.mkdir()
    opened, real_open = [], os.open

    def recording_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fdopen(*args, **kwargs):
        raise OSError("injected fdopen failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", recording_open)
        patch.setattr(os, "fdopen", fdopen)
        with pytest.raises(OSError, match="injected fdopen failure"):
            cli.write_interim({"results": 9}, work / "out.json")
    assert opened
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert list(work.iterdir()) == []


def test_a_directory_moved_into_the_scenarios_during_the_rename_keeps_no_new_file(monkeypatch, publication):
    """The held directory moves into data/scenarios between the handle check and the rename: the check after the
    rename removes the new file and refuses (review delta3, finding 1)."""
    work = publication / "work"
    work.mkdir()
    scenarios = publication / "data" / "scenarios"
    real_rename = os.rename

    def rename(src, dst, *args, **kwargs):
        real_rename(src, dst, *args, **kwargs)
        if kwargs.get("src_dir_fd") is not None:  # write_interim's renameat
            real_rename(work, scenarios / "moved")

    with monkeypatch.context() as patch:
        patch.setattr(os, "rename", rename)
        with pytest.raises(SystemExit, match="must not write the results file"):
            cli.write_interim({"results": 10}, work / "out.json")
    assert sorted(p.relative_to(scenarios).as_posix() for p in scenarios.rglob("*")) == ["moved", "obr_premium.json"]
    assert (publication / "data" / "results.json").read_text() == "results\n"


def test_a_directory_moved_into_the_scenarios_before_a_mkdir_leaves_nothing_there(monkeypatch, publication):
    """work/ moves into data/scenarios after the walk checked it and before it makes work/new: the next check refuses,
    and the write removes the directory it made (review delta4, finding 1)."""
    work = publication / "work"
    work.mkdir()
    scenarios = publication / "data" / "scenarios"
    real, moved = cli._under_scenarios, []

    def under_scenarios(directory):
        found = real(directory)
        if not moved:
            moved.append(work.rename(scenarios / "moved"))
        return found

    monkeypatch.setattr(cli, "_under_scenarios", under_scenarios)
    with pytest.raises(SystemExit, match="must not write the results file"):
        cli.write_interim({"results": 11}, work / "new" / "nested" / "out.json")
    assert sorted(p.relative_to(scenarios).as_posix() for p in scenarios.rglob("*")) == ["moved", "obr_premium.json"]


def test_a_refused_write_removes_the_directories_it_made(monkeypatch, publication):
    monkeypatch.setattr(cli, "_handle_refusal", lambda directory, name: "refused for the test")
    with pytest.raises(SystemExit, match="refused for the test"):
        cli.write_interim({"results": 12}, publication / "work" / "new" / "out.json")
    assert not (publication / "work").exists()
    (publication / "kept").mkdir()
    with pytest.raises(SystemExit, match="refused for the test"):
        cli.write_interim({"results": 12}, publication / "kept" / "out.json")
    assert (publication / "kept").is_dir()  # it removes only what it made


def test_a_failed_write_removes_no_directory_another_process_put_in_its_place(monkeypatch, publication):
    """Between the mkdir and the cleanup, another process swaps work/new for its own empty directory: the cleanup
    leaves that directory, and with it work/."""
    work = publication / "work"

    def refusal(directory, name):
        (work / "theirs").mkdir()  # made while work/new exists, so the two never share an identity
        (work / "new").rmdir()
        (work / "theirs").rename(work / "new")
        return "refused for the test"

    monkeypatch.setattr(cli, "_handle_refusal", refusal)
    with pytest.raises(SystemExit, match="refused for the test"):
        cli.write_interim({"results": 13}, work / "new" / "out.json")
    assert (work / "new").is_dir() and list((work / "new").iterdir()) == []


def test_a_walk_that_fails_to_record_a_directory_leaks_no_descriptor(monkeypatch, publication):
    """os.dup fails after the walk made and opened work/: the walk closes every handle it opened, the new one too."""
    opened, made, real_open, real_mkdir, real_dup = [], [], os.open, os.mkdir, os.dup

    def recording_open(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def mkdir(*args, **kwargs):
        real_mkdir(*args, **kwargs)
        made.append(args[0])

    def dup(descriptor):  # the ancestry check dups too; fail only the record of a new directory
        if made:
            raise OSError("injected dup failure")
        return real_dup(descriptor)

    created = []
    with monkeypatch.context() as patch:
        patch.setattr(os, "open", recording_open)
        patch.setattr(os, "mkdir", mkdir)
        patch.setattr(os, "dup", dup)
        with pytest.raises(OSError, match="injected dup failure"):
            cli._open_directory(publication / "work" / "a", created)
    assert made == ["work"] and created == []
    for descriptor in opened:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_a_failing_check_after_the_rename_keeps_no_file(monkeypatch, publication):
    """The check after the rename raises (an ancestor turned unreadable): the write fails closed and removes the file
    it renamed into place (review delta4, finding 2)."""
    work = publication / "work"
    work.mkdir()
    renamed, real_rename, real_check = [], os.rename, cli._under_scenarios

    def rename(*args, **kwargs):
        real_rename(*args, **kwargs)
        renamed.append(True)

    def under_scenarios(directory):
        if renamed:
            raise PermissionError("injected: an ancestor is unreadable")
        return real_check(directory)

    monkeypatch.setattr(cli, "_under_scenarios", under_scenarios)
    with monkeypatch.context() as patch:
        patch.setattr(os, "rename", rename)
        with pytest.raises(PermissionError, match="injected"):
            cli.write_interim({"results": 13}, work / "out.json")
    assert renamed and list(work.iterdir()) == []


def test_the_handle_check_reads_identities_not_paths(publication):
    data, scenarios = publication / "data", publication / "data" / "scenarios"
    (scenarios / "sub").mkdir()
    (publication / "work").mkdir()
    (publication / "work" / "link.json").symlink_to(publication / "copy.json")
    cases = [(data, "results.json", True), (scenarios / "sub", "x.json", True), (scenarios, "x.json", True),
             (publication, "copy.json", True), (publication / "work", "link.json", True),
             (publication / "work", "x.json", False), (publication, "results.json", False)]
    if _case_insensitive(publication):
        cases.append((data, "RESULTS.JSON", True))
    for folder, name, refused in cases:
        handle = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            assert bool(cli._handle_refusal(handle, name)) is refused, (folder, name)
        finally:
            os.close(handle)


@pytest.mark.parametrize("flag", ["--scenario", "--mean-path-scenarios"])
def test_scenario_writes_refuse_the_results_file_by_identity_or_alias(monkeypatch, publication, flag):
    """--scenario and --mean-path-scenarios may write the scenario directory, never the results file or its copy:
    compared by identity, folded spelling and the OS's resolution of a link before '..'."""
    written = []
    monkeypatch.setattr(pipeline, "write", lambda results, paths: written.append(list(paths)))
    monkeypatch.setattr(pipeline, "scenario", lambda *a, **k: {"scenario": 1})
    monkeypatch.setattr(pipeline, "mean_path_scenarios", lambda **k: {"mean_paths": 1})
    (publication / "L").symlink_to(publication / "data" / "scenarios", target_is_directory=True)
    (publication / "to-results.json").symlink_to(publication / "data" / "results.json")
    outs = ["L/../results.json", "to-results.json", "data/results.json", "copy.json"]
    if _case_insensitive(publication):
        outs += ["data/RESULTS.JSON", "COPY.json"]
    for out in outs:
        arguments = [flag, *(["obr_premium"] if flag == "--scenario" else []), "--out", str(publication) + "/" + out]
        with pytest.raises(SystemExit):
            cli.main(arguments)
    assert written == []
    arguments = [flag, *(["obr_premium"] if flag == "--scenario" else []), "--out", str(publication / "data" / "scenarios" / "ok.json")]
    assert cli.main(arguments) == 0 and written == [[publication / "data" / "scenarios" / "ok.json"]]


SEGMENTS = ["data", "scenarios", "sub", "work", "L", "D", "S", "W", "..", ".", "DATA", "Scenarios"]
NAMES = ["results.json", "RESULTS.JSON", "obr_premium.json", "copy.json", "COPY.JSON", "x.json", "L", "..", "sub"]


@settings(max_examples=150, deadline=None, derandomize=True)
@given(segments=st.lists(st.sampled_from(SEGMENTS), max_size=5), name=st.sampled_from(NAMES))
def test_no_interim_out_path_changes_a_publication_output(segments, name):
    """For any --out spelled through links, '..', '.' and case aliases: the write is refused or fails, or it writes
    a file that is not the results file, its dashboard copy or anything under the scenario directory, and every
    publication output and link is left as it was."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
        root = Path(os.path.realpath(tmp))
        data = root / "data"
        (data / "scenarios" / "sub").mkdir(parents=True)
        (root / "work").mkdir()
        before = {data / "results.json": "results\n", root / "copy.json": "copy\n",
                  data / "scenarios" / "obr_premium.json": "scenario\n"}
        for path, text in before.items():
            path.write_text(text)
        links = {"L": data / "scenarios", "D": data, "S": data / "scenarios" / "sub", "W": root / "work"}
        for link, target in links.items():
            (root / link).symlink_to(target, target_is_directory=True)
        mp.setattr(cli, "OUTPUT", data / "results.json")
        mp.setattr(cli, "DASHBOARD_COPY", root / "copy.json")
        mp.setattr(cli, "SCENARIO_DIR", data / "scenarios")
        out = "/".join([str(root), *segments, name])
        try:
            cli.write_interim({"results": 8}, out)
            wrote = True
        except (SystemExit, OSError):
            wrote = False
        event(f"written: {wrote}")
        for path, text in before.items():
            assert path.read_text() == text, (out, path)
        for link, target in links.items():
            assert (root / link).is_symlink() and os.readlink(root / link) == str(target), (out, link)
        found = sorted(str(p.relative_to(data / "scenarios")) for p in (data / "scenarios").rglob("*"))
        assert found == ["obr_premium.json", "sub"], (out, found)
        if wrote:
            written = Path(os.path.realpath(out))
            assert json.loads(written.read_text()) == {"results": 8}, out


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


@pytest.mark.parametrize("omitted, reason", [("c2", "the model failed its frozen statutory screen (C2)"),
                                              ("ruling", "the d955 ruling publishes scenarios only")])
def test_a_file_without_an_expected_value_never_describes_one(omitted, reason):
    wording = pipeline.method_limitations(omitted=omitted)
    # dashboard/src/components/MethodTab.jsx moves any line naming an expected value to the box for the estimate
    # the file omits; the model's note describes the example paths the file does give.
    assert not [w for w in wording if re.search("expected value", w, re.I)]
    (model,) = [w for w in wording if "rests on one statistical model" in w or "rest on one statistical model" in w]
    assert model.startswith("The simulated example paths rest on one statistical model")
    assert f"no probability weight: {reason}, so the file gives no average across its paths." in model
    # The LIMIT_ROWS line for this note shows only when its fit period is present.
    assert "2000-2026" in model
    assert len(wording) == len(pipeline.method_limitations())


def test_a_file_with_an_expected_value_keeps_its_model_note():
    (model,) = [w for w in pipeline.method_limitations() if "one statistical model" in w]
    assert model == next(w for w in pipeline.METHOD_LIMITATIONS if w.startswith("The expected value rests"))


BINDING_VINTAGES = (
    "The central path follows the OBR's October 2026 Economic and fiscal outlook for calendar years 2026-2030 and the "
    "inputs to every April rise to April 2031. Later years follow the OBR's March 2026 long-term economic "
    "determinants (dated 28 May 2026), because the OBR published no October 2026 set with that outlook, and the OBR "
    "describes its long-term projection as not a forecast. When the OBR publishes the October set, a rebuild "
    "replaces every figure for 2031 and later.")
BINDING_NOTE = ("The OBR published no October 2026 long-term economic determinants with its 28 October 2026 outlook, "
                "so the years after the forecast follow the March 2026 set; a rebuild replaces them once the October "
                "set is out.")


def test_the_binding_vintage_wording_is_the_text_it_replaced():
    """Read from the sources, the binding path's line and note are word for word what 8b6b31b hard-coded."""
    (vintage,) = [w for w in pipeline.method_limitations() if w.startswith("The central path follows")]
    assert vintage == BINDING_VINTAGES
    assert pipeline.forecast_vintages()["note"] == BINDING_NOTE


def _march(central):
    for key in ("efo_calendar", "efo_quarterly"):
        central["sources"][key]["title"] = "OBR Economic and fiscal outlook, March 2026 (detailed forecast tables)"
    return central


def test_a_march_path_names_march_and_no_older_set():
    """A path on the March 2026 outlook throughout (a historical reconstruction) says nothing of October and gives
    no reason for an older long-term set, since it uses none (review delta3, finding 3)."""
    march = _march(copy.deepcopy(pipeline.central_module.central_path()))
    assert pipeline.forecast_vintages(march)["note"] is None
    (vintage,) = [w for w in pipeline.method_limitations(march) if w.startswith("The central path follows")]
    assert vintage.startswith("The central path follows the OBR's March 2026 Economic and fiscal outlook")
    assert "October" not in vintage and "because" not in vintage and "rebuild" not in vintage
    assert vintage.endswith("long-term economic determinants (dated 28 May 2026), and the OBR describes its "
                            "long-term projection as not a forecast.")


@pytest.mark.parametrize("forecast, long_term, older", [
    ("October 2026", "March 2026", True), ("March 2026", "March 2026", False), ("November 2025", "March 2025", True),
    ("March 2026", "October 2026", False), ("October 2026", "March 2027", False), ("January 2027", "December 2026", True),
    (None, "March 2026", False), ("October 2026", None, False)])
def test_the_vintage_wording_follows_the_months_the_sources_name(forecast, long_term, older):
    central = copy.deepcopy(pipeline.central_module.central_path())
    for key in ("efo_calendar", "efo_quarterly"):
        central["sources"][key]["title"] = f"OBR Economic and fiscal outlook, {forecast or 'undated'}"
    central["sources"]["lted_converted"]["title"] = f"OBR Long-term economic determinants, {long_term or 'undated'}"
    note = pipeline.forecast_vintages(central)["note"]
    (vintage,) = [w for w in pipeline.method_limitations(central) if w.startswith("The central path follows")]
    assert (note is not None) is older
    assert ("because the OBR published no" in vintage) is older and ("a rebuild replaces" in vintage) is older
    for month in (forecast, long_term):
        if month:
            assert month in vintage
    if older:
        assert f"no {forecast} long-term economic determinants with its {forecast} outlook" in note
        assert f"once the {forecast.split()[0]} set is out" in note and f"follow the {long_term} set" in note
    for absent in {"October 2026", "March 2026"} - {forecast, long_term}:
        assert absent not in vintage + (note or "")


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
