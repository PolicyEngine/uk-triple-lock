"""The shared staleness helper (tests/source_freshness.py) catches a changed, a removed and an imported new module."""

import re

import pytest

from source_freshness import assert_sources_current, imported_modules

MESSAGE = "sources changed since the build: rebuild"
STORED = {"a.py": "1", "b.py": "2", "pyproject.toml": "3"}


@pytest.fixture
def package(tmp_path):
    (tmp_path / "a.py").write_text("from .b import x\n")
    (tmp_path / "b.py").write_text("import numpy\n")
    (tmp_path / "new.py").write_text("from .a import y\n")
    return tmp_path


def fails(stored, now, package):
    with pytest.raises(AssertionError) as e:
        assert_sources_current(stored, now, MESSAGE, package)
    # scripts/check_prebuild_tests.py allows this failure only when the message matches its pattern.
    assert re.match(r"(?:sources|inputs) changed since the build: rebuild(?:\n|$)", str(e.value))


def test_unchanged_and_an_unimported_new_module_pass(package):
    assert_sources_current(STORED, dict(STORED), MESSAGE, package)
    assert_sources_current(STORED, {**STORED, "new.py": "4"}, MESSAGE, package)


def test_changed_module_fails(package):
    fails(STORED, {**STORED, "b.py": "changed"}, package)


def test_removed_module_fails(package):
    fails(STORED, {k: v for k, v in STORED.items() if k != "b.py"}, package)


def test_new_module_imported_by_a_stored_one_fails(package):
    (package / "b.py").write_text("def f():\n    from . import new\n")
    fails(STORED, {**STORED, "new.py": "4"}, package)
    (package / "b.py").write_text("from triple_lock.new import z\n")
    fails(STORED, {**STORED, "new.py": "4"}, package)


def test_added_non_module_fails(package):
    fails(STORED, {**STORED, "setup.cfg": "4"}, package)


def test_import_forms(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("from . import a, b\nfrom .c import d\nfrom triple_lock.e import f\nfrom triple_lock import g\n"
                 "import triple_lock.h\nimport os\n")
    assert imported_modules(p) == {"a", "b", "c", "e", "g", "h"}
