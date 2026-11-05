"""Require completed pytest execution; allow only identified stale assertions."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from _pytest.junitxml import bin_xml_escape, mangle_test_address


STALE_REASONS = {
    ("tests.test_results", "test_not_stale"): re.compile(
        r"AssertionError: (?:sources|inputs) changed since the build: rebuild(?:\n|$)"),
    ("tests.test_results", "test_method_text_percentiles_match_the_past_years_check"): re.compile(
        r"AssertionError: method text percentiles differ from the historical past-years check: rebuild(?:\n|$)"),
    ("tests.test_results", "test_assumptions_block_is_current"): re.compile(
        r"AssertionError: assumptions changed since the build: rebuild(?:\n|$)"),
    ("tests.test_scenarios", "test_not_stale"): re.compile(
        r"AssertionError: [a-z0-9_]+: (?:sources|inputs|engine) changed since the run: rerun it(?:\n|$)"),
}


def allow_prebudget_stale(results, *, event_name, base_ref):
    """Permit the finite stale-output exceptions only for a provisional release's PR into main."""
    if event_name != "pull_request" or base_ref != "main" or not isinstance(results, dict):
        return False
    release, screen = results.get("release"), results.get("uncertainty_screen")
    return (isinstance(release, dict) and isinstance(screen, dict)
            and release.get("stage") == "pre-budget" and release.get("provisional") is True
            and screen.get("run_kind") == "dry_run" and screen.get("expected_value_authorized") is False)


def check_report(path, *, pytest_exit_code, completion_path, allow_stale=False):
    allowed_codes = {0, 1} if allow_stale else {0}
    if pytest_exit_code not in allowed_codes:
        raise ValueError(f"pytest did not finish successfully: exit code {pytest_exit_code}")
    completion = json.loads(Path(completion_path).read_text())
    selected = completion.get("selected")
    completed = completion.get("completed_nodeids")
    if (not isinstance(selected, int) or isinstance(selected, bool) or selected <= 0
            or not isinstance(completed, list) or len(completed) != selected
            or any(not isinstance(nodeid, str) or not nodeid for nodeid in completed)
            or len(set(completed)) != selected
            or completion.get("exit_code") != pytest_exit_code
            or completion.get("interrupted") is not False
            or completion.get("complete") is not True):
        raise ValueError("pytest did not complete every selected test")
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    suites = list(root.iter("testsuite"))
    if len(cases) != selected or not suites:
        raise ValueError("JUnit report does not cover every selected test")
    prefix = completion.get("junit_prefix")
    if prefix is not None and not isinstance(prefix, str):
        raise ValueError("invalid JUnit prefix in the completion record")
    expected_cases = []
    for nodeid in completed:
        # Use the installed, pinned pytest formatter, including parametrized IDs.
        names = mangle_test_address(nodeid)
        classnames = ([prefix] if prefix else []) + names[:-1]
        expected_cases.append((".".join(classnames), bin_xml_escape(names[-1])))
    if Counter(expected_cases) != Counter((case.get("classname"), case.get("name")) for case in cases):
        raise ValueError("JUnit identities differ from the completed test identities")
    for suite in suites:
        direct_cases = suite.findall("testcase")
        counters = {
            "tests": len(direct_cases),
            "failures": sum(case.find("failure") is not None for case in direct_cases),
            "errors": sum(case.find("error") is not None for case in direct_cases),
            "skipped": sum(case.find("skipped") is not None for case in direct_cases),
        }
        if any(suite.get(key) != str(value) for key, value in counters.items()):
            raise ValueError("JUnit counters do not match the reported test cases")
    failures = []
    for case in cases:
        identity = (case.get("classname"), case.get("name"))
        if not all(identity) or case.find("error") is not None:
            raise ValueError("pytest reported an unnamed/incomplete case or a test error")
        failure = case.find("failure")
        if failure is None:
            continue
        reason = STALE_REASONS.get(identity)
        if (not allow_stale or reason is None
                or reason.match(failure.get("message", "")) is None):
            raise ValueError(f"unexpected test failure: {identity}")
        failures.append(identity)
    if (pytest_exit_code == 1) != bool(failures):
        raise ValueError("pytest exit code does not match the reported failures")
    return len(cases), sorted(failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--pytest-exit-code", type=int, required=True)
    parser.add_argument("--completion-report", type=Path, required=True)
    parser.add_argument("--results", type=Path, default=Path(__file__).resolve().parents[1] / "data/results.json")
    args = parser.parse_args()
    allow_stale = allow_prebudget_stale(
        json.loads(args.results.read_text()), event_name=os.environ.get("GITHUB_EVENT_NAME"),
        base_ref=os.environ.get("GITHUB_BASE_REF"))
    count, failures = check_report(
        args.report, pytest_exit_code=args.pytest_exit_code,
        completion_path=args.completion_report,
        allow_stale=allow_stale)
    print(f"Completed {count} tests; {len(failures)} documented pre-build stale-results failures.")
    for module, name in failures:
        print(f"  {module}::{name}")
