"""Provenance for a pipeline run.

Records what produced a results file: the repository revision, the
policyengine.py release bundle that certifies the model and data, the
versions of every package that affects the numbers, and hashes of the
source and input files that define the calculation.

The bundle is policyengine.py's own certification record — it is the
authority on which policyengine-uk version and which data build were
used, so this module reads it rather than inspecting policyengine-uk
directly. Everything here is required: a missing package, file or git
checkout raises rather than being recorded as unknown.
"""

import copy
import hashlib
import importlib.metadata
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Packages whose version can move a result. policyengine-uk is included
# because the bundle certifies it, not because the project pins it.
TRACKED_PACKAGES = [
    "policyengine",
    "policyengine-uk",
    "policyengine-core",
    "microdf-python",
    "numpy",
]

# Source files that define the calculation. A change to any of them makes a
# committed results file stale; the pin test compares these hashes.
HASHED_SOURCES = [
    "config.py",
    "rules.py",
    "uncertainty.py",
    "var_check.py",
    "breakdowns.py",
    "benchmarks.py",
    "pipeline.py",
    "provenance.py",
    "cli.py",
]

# Repository files that define the environment the calculation runs in.
HASHED_REPO_FILES = ["pyproject.toml"]

# Bundle fields worth recording. `runtime_dataset_source` is deliberately
# excluded: it is a machine-local cache path.
BUNDLE_FIELDS = [
    "bundle_id",
    "policyengine_version",
    "model_package",
    "model_version",
    "default_dataset",
    "runtime_dataset",
    "runtime_dataset_uri",
    "certified_data_build_id",
    "certified_data_artifact_sha256",
    "data_build_model_version",
    "compatibility_basis",
    "certified_by",
]

# Fields that change on every run even when code, model and data are
# identical. The regression test drops them before comparing.
VOLATILE_FIELDS = ["generated_at", "git_revision", "git_dirty"]


def _git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _package_versions():
    return {name: importlib.metadata.version(name) for name in TRACKED_PACKAGES}


def file_hash(path):
    """SHA-256 of a file; raises if it does not exist."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    """SHA-256 of the calculation sources and the environment definition."""
    here = Path(__file__).resolve().parent
    repo = here.parents[1]
    hashes = {name: file_hash(here / name) for name in HASHED_SOURCES}
    hashes.update({name: file_hash(repo / name) for name in HASHED_REPO_FILES})
    return hashes


def build_provenance(bundle, input_hashes):
    """Assemble the provenance block for a results file.

    ``bundle`` is ``sim.policyengine_bundle`` from a managed simulation;
    ``input_hashes`` maps repository paths of input data files to SHA-256.
    """
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_revision": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "packages": _package_versions(),
        "source_hashes": source_hashes(),
        "input_hashes": dict(input_hashes),
        "dataset": {
            "name": bundle["runtime_dataset"],
            "uri": bundle["runtime_dataset_uri"],
            "data_build": bundle["certified_data_build_id"],
        },
        "release_bundle": {field: bundle[field] for field in BUNDLE_FIELDS},
    }


def strip_volatile(results):
    """Copy of ``results`` without the run-to-run varying provenance fields."""
    stripped = copy.deepcopy(results)
    for field in VOLATILE_FIELDS:
        del stripped["provenance"][field]
    return stripped
