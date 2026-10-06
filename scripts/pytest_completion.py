"""Record selected/completed test identities independently of pytest's JUnit XML."""

import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption("--completion-report", help="Write the CI execution completion record")


def pytest_configure(config):
    config._prebuild_completed_nodeids = []


def pytest_runtest_logreport(report):
    # A call report proves execution; a setup skip/failure completes a case too.
    if report.when == "call" or report.when == "setup" and (report.skipped or report.failed):
        _active_config._prebuild_completed_nodeids.append(report.nodeid)


def pytest_sessionstart(session):
    global _active_config
    _active_config = session.config


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption("--completion-report")
    if destination is None:
        return
    completed = session.config._prebuild_completed_nodeids
    selected = session.testscollected
    record = {
        "selected": selected, "completed_nodeids": completed,
        "exit_code": int(exitstatus),
        "junit_prefix": session.config.option.junitprefix,
        "complete": int(exitstatus) in (0, 1) and selected > 0
        and len(completed) == selected and len(set(completed)) == selected,
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
