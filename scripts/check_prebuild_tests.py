"""Require a complete pytest report; allow only the documented pre-build failures."""

from pathlib import Path
import os
import sys
import xml.etree.ElementTree as ET

STALE_TESTS = {
    ("tests.test_results", "test_not_stale"),
    ("tests.test_results", "test_method_text_percentiles_match_the_past_years_check"),
    ("tests.test_scenarios", "test_not_stale"),
}


def check_report(path, *, allow_stale=False):
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases or any(suite.get("errors", "0") != "0" for suite in root.iter("testsuite")):
        raise ValueError("pytest did not complete without collection/runtime errors")
    if any(case.find("error") is not None for case in cases):
        raise ValueError("pytest reported a test error")
    failures = {(case.get("classname"), case.get("name")) for case in cases
                if case.find("failure") is not None}
    unexpected = failures - (STALE_TESTS if allow_stale else set())
    if unexpected:
        raise ValueError(f"unexpected test failures: {sorted(unexpected)}")
    return len(cases), sorted(failures)


if __name__ == "__main__":
    count, failures = check_report(Path(sys.argv[1]),
                                  allow_stale=os.environ.get("ALLOW_PREBUILD_STALE") == "true")
    print(f"Completed {count} tests; {len(failures)} documented pre-build stale-results failures.")
    for module, name in failures:
        print(f"  {module}::{name}")
