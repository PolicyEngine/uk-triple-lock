import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "prebuild_ci", Path(__file__).parents[1] / "scripts/check_prebuild_tests.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize("failure,accepted", [("", True),
    ('<testcase classname="tests.test_results" name="test_not_stale"><failure/></testcase>', True),
    ('<testcase classname="tests.test_uncertainty" name="test_reproducibility"><failure/></testcase>', False),
    ('<testcase classname="tests.test_results" name="test_not_stale"><error/></testcase>', False)])
def test_ci_allows_only_documented_stale_assertions(tmp_path, failure, accepted):
    report = tmp_path / "report.xml"
    report.write_text('<testsuites><testsuite errors="0"><testcase classname="tests.test_model" '
                      'name="test_model"/>' + failure + '</testsuite></testsuites>')
    if accepted:
        ci.check_report(report)
    else:
        with pytest.raises(ValueError):
            ci.check_report(report)


def test_ci_rejects_empty_or_incomplete_collection(tmp_path):
    report = tmp_path / "report.xml"
    for text in ('<testsuites/>', '<testsuites><testsuite errors="1"><testcase/></testsuite></testsuites>'):
        report.write_text(text)
        with pytest.raises(ValueError):
            ci.check_report(report)
