"""Shared staleness check for the stored source hashes (tests/test_results.py, tests/test_scenarios.py).

A stored run is stale when a source it was built from changed or went away. A module added to the package since the
build cannot have shaped the stored figures unless a module the build did use imports it, so an added ``.py`` file
that no stored module imports leaves the run current. Anything else added (a non-module key) is stale.
"""

import ast
from pathlib import Path

from triple_lock.config import REPO

PACKAGE = REPO / "src" / "triple_lock"


def imported_modules(path):
    """Names of sibling modules that ``path`` imports (relative or as ``triple_lock.x``), at any depth in the file."""
    names = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1 and node.module is None:  # from . import x, y
                names.update(a.name for a in node.names)
            elif node.level == 1:  # from .x import y
                names.add(node.module.split(".")[0])
            elif node.level == 0 and node.module and node.module.split(".")[0] == "triple_lock":
                parts = node.module.split(".")
                names.update([parts[1]] if len(parts) > 1 else [a.name for a in node.names])
        elif isinstance(node, ast.Import):
            for a in node.names:
                parts = a.name.split(".")
                if parts[0] == "triple_lock" and len(parts) > 1:
                    names.add(parts[1])
    return names


def assert_sources_current(stored, now, message, package=PACKAGE):
    """Fail with ``message`` unless every stored source is unchanged and present, every source added since is a
    module, and no stored module imports an added one."""
    assert {k: now.get(k) for k in stored} == stored, message
    added = sorted(set(now) - set(stored))
    assert all(k.endswith(".py") for k in added), f"{message}\nadded non-module sources: {added}"
    stems = {k[:-3] for k in added}
    importers = {k: sorted(imported_modules(package / k) & stems) for k in stored if k.endswith(".py")}
    importers = {k: v for k, v in importers.items() if v}
    assert not importers, f"{message}\nstored modules import added ones: {importers}"
