"""Record selected/completed test identities independently of pytest's JUnit XML."""

import json
from pathlib import Path

import pytest


_active_config = None


def pytest_addoption(parser, pluginmanager):
    parser.addoption("--completion-report", help="Write the CI execution completion record")
    config = None

    def before_hook(hook_name, hook_impls, kwargs):
        nonlocal config
        if hook_name == "pytest_cmdline_main":
            config = kwargs["config"]
            _initialize_completion(config)

    def after_hook(outcome, hook_name, hook_impls, kwargs):
        if config is None:
            return
        error = outcome.exception
        if error is not None and (
            isinstance(error, (KeyboardInterrupt, pytest.exit.Exception))
            or hook_name in ("pytest_sessionfinish", "pytest_unconfigure", "pytest_cmdline_main")
        ):
            config._prebuild_interrupted = True
        if hook_name == "pytest_sessionfinish" and error is None:
            config._prebuild_session_finished = True
        if hook_name == "pytest_cmdline_main":
            # Observe the entire command, outside all hook wrappers and the
            # final cleanup callbacks, before certifying completion.
            if error is None:
                config._prebuild_exit_code = int(outcome.get_result())
            try:
                _write_completion(config)
            finally:
                undo()

    undo = pluginmanager.add_hookcall_monitoring(before_hook, after_hook)


def _initialize_completion(config):
    global _active_config
    _active_config = config
    config._prebuild_executed_nodeids = set()
    config._prebuild_completed_nodeids = []
    config._prebuild_interrupted = False
    config._prebuild_session = None
    config._prebuild_session_finished = False
    config._prebuild_exit_code = None
    destination = config.getoption("--completion-report")
    if destination is not None:
        # An early exit must not leave a previous run's completion evidence.
        Path(destination).unlink(missing_ok=True)


def pytest_runtest_logreport(report):
    # A terminal call/setup outcome is necessary, but fixture teardown must
    # also return before the case is counted as completed.
    if report.when == "call" or report.when == "setup" and (report.skipped or report.failed):
        _active_config._prebuild_executed_nodeids.add(report.nodeid)
    if report.when == "teardown" and report.nodeid in _active_config._prebuild_executed_nodeids:
        _active_config._prebuild_completed_nodeids.append(report.nodeid)


def pytest_sessionstart(session):
    session.config._prebuild_session = session


def pytest_keyboard_interrupt(excinfo):
    # Pytest also invokes this hook for explicit pytest.exit(0/1).
    if _active_config is not None:
        _active_config._prebuild_interrupted = True


def _write_completion(config):
    destination = config.getoption("--completion-report")
    if destination is None:
        return
    session = config._prebuild_session
    completed = config._prebuild_completed_nodeids
    selected = session.testscollected if session is not None else 0
    exit_code = config._prebuild_exit_code
    if exit_code is None and session is not None:
        exit_code = int(session.exitstatus)
    record = {
        "selected": selected, "completed_nodeids": completed,
        "exit_code": exit_code,
        "junit_prefix": config.option.junitprefix,
        "interrupted": config._prebuild_interrupted,
        "complete": config._prebuild_session_finished
        and not config._prebuild_interrupted and exit_code in (0, 1) and selected > 0
        and len(completed) == selected and len(set(completed)) == selected,
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")
