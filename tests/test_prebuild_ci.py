"""The pre-build gate must reject incomplete or unrelated real pytest failures."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("prebuild_ci", ROOT / "scripts/check_prebuild_tests.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def run_pytest(directory, modules):
    """Run only tiny isolated probe modules with the real completion plugin."""
    package = directory / "tests"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for name, source in modules.items():
        (package / name).write_text(textwrap.dedent(source))
    report = directory / "report.xml"
    completion = directory / "completion.json"
    environment = dict(os.environ)
    environment.pop("GIT_DIR", None)
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    environment.update(PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "scripts.pytest_completion",
         f"--completion-report={completion}", f"--junitxml={report}", "tests"],
        cwd=directory, env=environment, capture_output=True, text=True, timeout=180,
    )
    assert report.exists() and completion.exists(), result.stdout + result.stderr
    return SimpleNamespace(report=report, completion=completion, returncode=result.returncode,
                           output=result.stdout + result.stderr)


def check(probe, *, allow_stale=False, exit_code=None):
    return ci.check_report(probe.report, completion_path=probe.completion,
                           pytest_exit_code=probe.returncode if exit_code is None else exit_code,
                           allow_stale=allow_stale)


@pytest.fixture(scope="module")
def passing_probe(tmp_path_factory):
    probe = run_pytest(tmp_path_factory.mktemp("ci-complete"), {
        "test_complete.py": """
            import pytest
            def test_pass():
                assert True
            @pytest.mark.skip(reason="a completed setup skip")
            def test_skip():
                assert False
        """,
    })
    assert probe.returncode == 0, probe.output
    return probe


@pytest.fixture(scope="module")
def stale_probe(tmp_path_factory):
    probe = run_pytest(tmp_path_factory.mktemp("ci-known-stale"), {
        "test_results.py": """
            def test_not_stale():
                assert False, "sources changed since the build: rebuild"
            def test_method_text_percentiles_match_the_past_years_check():
                assert False, "method text percentiles differ from the historical past-years check: rebuild"
            def test_another_check():
                assert True
        """,
        "test_scenarios.py": """
            def test_not_stale():
                assert False, "central: engine changed since the run: rerun it"
        """,
    })
    assert probe.returncode == 1, probe.output
    return probe


@pytest.mark.parametrize("allow_stale", (False, True))
def test_ci_accepts_complete_real_pytest_pass_and_setup_skip(passing_probe, allow_stale):
    completion = json.loads(passing_probe.completion.read_text())
    assert completion["selected"] == 2
    assert completion["complete"] is True
    assert set(completion["completed_nodeids"]) == {
        "tests/test_complete.py::test_pass", "tests/test_complete.py::test_skip"}
    assert check(passing_probe, allow_stale=allow_stale) == (2, [])


def test_ci_allows_all_three_documented_stale_assertions(stale_probe):
    assert json.loads(stale_probe.completion.read_text())["complete"] is True
    assert check(stale_probe, allow_stale=True) == (4, sorted(ci.STALE_REASONS))


def test_ci_is_strict_when_prebuild_exception_is_not_enabled(stale_probe):
    with pytest.raises(ValueError):
        check(stale_probe)


@pytest.mark.parametrize("body", (
    'raise RuntimeError("unrelated call-phase runtime error")',
    'assert False, "unrelated assertion under an allowed test name"',
    'assert False, "sources changed since the build: rebuild for a different reason"',
))
def test_ci_rejects_unrelated_call_failures_under_allowlisted_identity(tmp_path, body):
    probe = run_pytest(tmp_path, {"test_results.py": f"def test_not_stale():\n    {body}\n"})
    assert probe.returncode == 1, probe.output
    case = ET.parse(probe.report).getroot().find(".//testcase")
    assert (case.get("classname"), case.get("name")) == ("tests.test_results", "test_not_stale")
    assert case.find("failure") is not None and case.find("error") is None
    with pytest.raises(ValueError, match="unexpected test failure"):
        check(probe, allow_stale=True)


def test_ci_rejects_known_stale_text_under_an_unlisted_test_identity(tmp_path):
    probe = run_pytest(tmp_path, {"test_uncertainty.py": """
        def test_reproducibility():
            assert False, "sources changed since the build: rebuild"
    """})
    assert probe.returncode == 1, probe.output
    with pytest.raises(ValueError, match="unexpected test failure"):
        check(probe, allow_stale=True)


@pytest.mark.parametrize("exit_code", (0, 1, 2))
def test_ci_rejects_partial_real_pytest_execution_even_with_zero_or_one_exit(tmp_path, exit_code):
    probe = run_pytest(tmp_path, {"test_partial.py": f"""
        import pytest
        def test_first():
            assert True
        def test_second():
            pytest.exit("deliberately incomplete probe", returncode={exit_code})
        def test_third():
            assert False, "this failure must not disappear from the gate"
    """})
    assert probe.returncode == exit_code, probe.output
    completion = json.loads(probe.completion.read_text())
    assert completion["selected"] == 3
    assert completion["completed_nodeids"] == ["tests/test_partial.py::test_first"]
    assert completion["complete"] is False
    for allow_stale in (False, True):
        with pytest.raises(ValueError):
            check(probe, allow_stale=allow_stale)


def test_ci_rejects_real_keyboard_interrupt_with_partial_junit(tmp_path):
    probe = run_pytest(tmp_path, {"test_partial.py": """
        def test_first():
            assert True
        def test_second():
            raise KeyboardInterrupt
        def test_third():
            assert False, "this failure must not disappear from the gate"
    """})
    assert probe.returncode == 2, probe.output
    completion = json.loads(probe.completion.read_text())
    assert completion["selected"] == 3
    assert completion["completed_nodeids"] == ["tests/test_partial.py::test_first"]
    assert completion["complete"] is False
    for allow_stale in (False, True):
        with pytest.raises(ValueError):
            check(probe, allow_stale=allow_stale)


def test_ci_rejects_real_collection_errors(tmp_path):
    probe = run_pytest(tmp_path, {"test_results.py": "import unavailable_ci_probe_module\n"})
    assert probe.returncode == 2, probe.output
    assert ET.parse(probe.report).getroot().find(".//error") is not None
    assert json.loads(probe.completion.read_text())["complete"] is False
    for allow_stale in (False, True):
        with pytest.raises(ValueError):
            check(probe, allow_stale=allow_stale)


def test_ci_rejects_real_setup_errors_under_allowlisted_identity(tmp_path):
    probe = run_pytest(tmp_path, {"test_results.py": """
        import pytest
        @pytest.fixture
        def broken_setup():
            raise RuntimeError("unrelated setup error")
        def test_not_stale(broken_setup):
            assert False, "sources changed since the build: rebuild"
    """})
    assert probe.returncode == 1, probe.output
    assert ET.parse(probe.report).getroot().find(".//error") is not None
    with pytest.raises(ValueError, match="test error"):
        check(probe, allow_stale=True)


def test_ci_rejects_real_teardown_error_after_an_allowlisted_stale_assertion(tmp_path):
    probe = run_pytest(tmp_path, {"test_results.py": """
        import pytest
        @pytest.fixture
        def broken_teardown():
            yield
            raise RuntimeError("unrelated teardown error")
        def test_not_stale(broken_teardown):
            assert False, "sources changed since the build: rebuild"
    """})
    assert probe.returncode == 1, probe.output
    assert ET.parse(probe.report).getroot().find(".//error") is not None
    # The test did execute, so an error must be rejected independently of the
    # completion record and the allowed call-phase assertion.
    assert json.loads(probe.completion.read_text())["complete"] is True
    with pytest.raises(ValueError):
        check(probe, allow_stale=True)


@pytest.fixture
def copied_probe(tmp_path, passing_probe):
    report = tmp_path / "report.xml"
    completion = tmp_path / "completion.json"
    shutil.copyfile(passing_probe.report, report)
    shutil.copyfile(passing_probe.completion, completion)
    return SimpleNamespace(report=report, completion=completion, returncode=0)


def test_ci_requires_a_completion_record(copied_probe):
    copied_probe.completion.unlink()
    with pytest.raises(FileNotFoundError):
        check(copied_probe, allow_stale=True)


@pytest.mark.parametrize("mutation", ("invalid_json", "not_complete", "selected_mismatch",
                                     "boolean_selected", "duplicate_nodes", "exit_mismatch"))
def test_ci_rejects_malformed_or_inconsistent_completion_records(copied_probe, mutation):
    if mutation == "invalid_json":
        copied_probe.completion.write_text("{invalid json")
    else:
        record = json.loads(copied_probe.completion.read_text())
        if mutation == "not_complete":
            record["complete"] = False
        elif mutation == "selected_mismatch":
            record["selected"] = 3
        elif mutation == "boolean_selected":
            record["selected"] = True
        elif mutation == "duplicate_nodes":
            record["completed_nodeids"] = [record["completed_nodeids"][0]] * 2
        elif mutation == "exit_mismatch":
            record["exit_code"] = 1
        copied_probe.completion.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        check(copied_probe, allow_stale=True)


@pytest.mark.parametrize("mutation", ("invalid_xml", "missing_case", "unnamed_case",
                                     "tests", "failures", "errors", "skipped"))
def test_ci_rejects_malformed_or_inconsistent_junit_reports(copied_probe, mutation):
    if mutation == "invalid_xml":
        copied_probe.report.write_text("<testsuites><broken>")
    else:
        tree = ET.parse(copied_probe.report)
        suite = tree.getroot().find(".//testsuite")
        if mutation == "missing_case":
            suite.remove(suite.find("testcase"))
        elif mutation == "unnamed_case":
            suite.find("testcase").attrib.pop("name")
        else:
            suite.set(mutation, str(int(suite.get(mutation)) + 1))
        tree.write(copied_probe.report)
    with pytest.raises((ValueError, ET.ParseError)):
        check(copied_probe, allow_stale=True)


@pytest.mark.parametrize("exit_code", (2, 3, 4, 5))
def test_ci_rejects_interruption_internal_usage_and_no_tests_exits(passing_probe, exit_code):
    with pytest.raises(ValueError, match="exit code"):
        check(passing_probe, allow_stale=True, exit_code=exit_code)


def test_ci_rejects_failure_exit_without_failures(copied_probe):
    record = json.loads(copied_probe.completion.read_text())
    record["exit_code"] = 1
    copied_probe.completion.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="exit code does not match"):
        check(copied_probe, allow_stale=True, exit_code=1)


def test_ci_rejects_success_exit_with_reported_failures(tmp_path, stale_probe):
    report = tmp_path / "report.xml"
    completion = tmp_path / "completion.json"
    shutil.copyfile(stale_probe.report, report)
    record = json.loads(stale_probe.completion.read_text())
    record["exit_code"] = 0
    completion.write_text(json.dumps(record))
    probe = SimpleNamespace(report=report, completion=completion, returncode=0)
    with pytest.raises(ValueError, match="exit code does not match"):
        check(probe, allow_stale=True)
