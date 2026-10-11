"""The survey datasets every job runs on, each pinned to a revision and a SHA-256, and what a run records about them.

The policyengine.py 6.2.6 bundle certifies Enhanced FRS 1.58.0 with
policyengine-uk 2.125.1 and policyengine-core 3.33.0. ``materialize``
fetches a file from Hugging Face into one shared store, ``.cache/datasets``,
and checks its SHA-256 against the pin before every use, as the managed loader
did; the store keeps one copy of each file for every worker.

``provenance`` records certification only when the installed bundle, model,
core and pinned artifact all match that release. The original 1.56.16 pilot
pair and Microcosm paired sensitivity remain uncertified under this bundle.

``HUGGING_FACE_TOKEN`` must be set for a file that is not yet in the store (the
repositories are private).
"""

import contextlib
import hashlib
import importlib.metadata
import json
import os
import shutil
from pathlib import Path

from .config import PRIMARY_DATASET, REPO

STORE = REPO / ".cache" / "datasets"

CERTIFIED_BUNDLE = {
    "bundle_package": "policyengine", "bundle_version": "6.2.6",
    "bundle_id": "uk-6.2.6", "model_version": "2.125.1", "core_version": "3.33.0",
    "manifest_sha256": "8633ad814c9c85e53c7c513f69c4c7b1500a03cd2f6ef133d6e2ea8346b2db54",
    "certification_url": "https://github.com/PolicyEngine/policyengine.py/pull/555",
    "certification_commit": "37d25c423e9541b4ca86adbdd8687738b49ab8ec",
}
RELEASE_MANIFEST_1_58_0 = {
    "revision": "fdeba38517bd86067f34c0a5d8ed8923efb3b10a",
    "path": "releases/1.58.0/release_manifest.json",
    "sha256": "ddd63e1f7755ee358c4ede9050bfdde09f3a80f48a5c0d8ee9d1fb531e4a1a07",
    "uri": "https://huggingface.co/policyengine/policyengine-uk-data-private/resolve/"
           "fdeba38517bd86067f34c0a5d8ed8923efb3b10a/releases/1.58.0/release_manifest.json",
}

# Where policyengine-uk-data declares an Enhanced FRS release's calibration year: the builder calibrates the weights
# in that year and saves them back to the survey year (create_datasets.py), so it is the year static ageing anchors
# to (demography.annual_weights: weights in it and every earlier year are the dataset's own).
CALIBRATION_SOURCE = ("policyengine-uk-data {tag}, policyengine_uk_data/datasets/frs_release.py: CURRENT_FRS_RELEASE "
                      "(survey_year=2024, base_year=2024, calibration_year=2025)")

# name -> where the file is and what it must hash to. "certified" names the policyengine.py bundles that certified
# the file (for other policyengine-uk versions), "built_with" the policyengine-uk version its data build ran,
# "ageing_anchor" the year static ageing anchors its weights to (the data build's calibration year where it has one).
DATASETS = {
    "enhanced_frs_2024_25@1.58.0": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.58.0",
        "sha256": "5ba399ea5ab9a6c7d4e9aaf6c623080beb34d9ad5f330f6244dbad72b8d960b6",
        "data_package": "policyengine-uk-data", "data_version": "1.58.0",
        "built_with": "policyengine-uk 2.122.2",
        "build_core_version": "3.32.13",
        "data_build_fingerprint": "sha256:c094d7006fdd81df220090284212f16bbffb15624643bc442c4bb3e1b1e5dac8",
        "certified": ["policyengine.py 6.2.6 (uk-6.2.6, policyengine-uk 2.125.1, policyengine-core 3.33.0)"],
        "bundle_certification": CERTIFIED_BUNDLE,
        "release_manifest": RELEASE_MANIFEST_1_58_0,
        "ageing_anchor": {"year": 2025, "calibration_year": 2025, "source": CALIBRATION_SOURCE.format(tag="1.58.0")},
    },
    "enhanced_frs_2024_25@1.56.16": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.56.16",
        "sha256": "e433e532b17bd8ce76030156285816e33d44e93edabd2204adbef71d19a68712",
        "data_package": "policyengine-uk-data", "data_version": "1.56.16",
        "built_with": "policyengine-uk 2.89.2",
        "certified": ["policyengine.py 5.3.0 (uk-5.3.0, policyengine-uk 2.90.2)",
                      "policyengine.py 6.2.1 (uk-6.2.1, policyengine-uk 2.102.3)"],
        "ageing_anchor": {"year": 2025, "calibration_year": 2025, "source": CALIBRATION_SOURCE.format(tag="1.56.16")},
    },
    "enhanced_frs_2024_25@1.57.4": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.57.4",
        "sha256": "03fe15e40a4c7333498d1eac50a87e1ec2aec730782881e0f1812bc2aa8e68d4",
        "data_package": "policyengine-uk-data", "data_version": "1.57.4",
        "built_with": "policyengine-uk 2.93.0",
        "certified": [],
        "ageing_anchor": {"year": 2025, "calibration_year": 2025, "source": CALIBRATION_SOURCE.format(tag="1.57.4")},
    },
    "populace_uk_2023": {
        "logical_name": "populace_uk_2023",
        "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "path": "populace_uk_2023.h5", "revision": "populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z",
        "sha256": "f17306ccb2aad7ff0130be3589b560afb2e2a12a943570911cd0c77f07934833",
        "data_package": "populace-data", "data_version": "populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z",
        "built_with": None,
        "certified": ["policyengine.py 5.3.0 and 6.2.1 dataset overlay (uncertified sensitivity)"],
        # No published calibration year: its data year is 2023, before the ONS 2024-based projection starts.
        "ageing_anchor": {"year": 2024, "calibration_year": None,
                          "source": "no published calibration year; the data year (2023) precedes the ONS 2024-based "
                                    "projection, so the anchor is its first fiscal year, 2024-25"},
    },
}
UNCERTIFIED = "uncertified: this dataset and installed bundle/model/core do not match the certified 6.2.6 UK artifact"


class DatasetMismatch(RuntimeError):
    """A dataset file does not hash to its pin."""


def resolve(dataset=None):
    """The registry name a job's ``dataset`` argument means: None is the primary dataset."""
    name = dataset or PRIMARY_DATASET
    if name not in DATASETS:
        raise KeyError(f"unknown dataset {name!r}: one of {sorted(DATASETS)}")
    return name


def uri(name):
    d = DATASETS[resolve(name)]
    return f"hf://{d['repo_id']}/{d['path']}@{d['revision']}"


def sha256_file(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def local_path(name, store=STORE):
    d = DATASETS[resolve(name)]
    return Path(store) / f"{Path(d['path']).stem}-{d['revision']}{Path(d['path']).suffix}"


@contextlib.contextmanager
def _locked(path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# Files this process has hashed, by (path, inode, size, modification time): a job loads its dataset three or four
# times, and Microcosm's file is 1.3 GB. Any change to the file changes the key, so it is hashed again.
_verified = set()


def _stamp(path):
    st = Path(path).stat()
    return (str(Path(path).resolve()), st.st_ino, st.st_size, st.st_mtime_ns)


def materialize(name=None, store=STORE, download=None):
    """The local file for a dataset, fetched into ``store`` if absent; raises DatasetMismatch unless it hashes to its
    pin (hashed once per process while the file is unchanged). ``download(spec, directory)`` returns a downloaded
    file's path (default: huggingface_hub)."""
    name = resolve(name)
    spec = DATASETS[name]
    path = local_path(name, store)
    if path.is_file() and (_stamp(path), spec["sha256"]) in _verified:
        return path
    with _locked(path.with_name(f".{path.name}.lock")):  # one download per file, whichever worker asks first
        if not path.is_file():
            tmp = Path(store) / f".download-{path.stem}-{os.getpid()}"
            try:
                got = (download or _hf_download)(spec, tmp)
                if sha256_file(got) != spec["sha256"]:
                    raise DatasetMismatch(f"{uri(name)} downloaded with the wrong SHA-256")
                shutil.move(got, path)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        stamp = _stamp(path)
        if sha256_file(path) != spec["sha256"]:
            raise DatasetMismatch(f"{path} does not hash to the pin for {name} ({spec['sha256'][:12]}...): delete it "
                                  "to fetch it again")
        _verified.add((stamp, spec["sha256"]))
    return path


def _hf_download(spec, directory):
    from huggingface_hub import hf_hub_download

    return Path(hf_hub_download(spec["repo_id"], spec["path"], revision=spec["revision"], repo_type=spec["repo_type"],
                                token=os.environ.get("HUGGING_FACE_TOKEN"), local_dir=directory))


def model_versions():
    """The installed model and core versions, as their distributions report them (policyengine_uk 2.118.0 has no
    ``__version__`` attribute; a release that adds one must agree, tests/test_engine_pure.py checks)."""
    try:
        bundle_version = importlib.metadata.version("policyengine")
    except importlib.metadata.PackageNotFoundError:  # isolated historical pilot environment
        bundle_version = None
    return {"model_package": "policyengine-uk", "model_version": importlib.metadata.version("policyengine-uk"),
            "core_version": importlib.metadata.version("policyengine-core"),
            "bundle_package": "policyengine", "bundle_version": bundle_version}


def _certified_by_installed_bundle(spec, versions):
    """Fail closed unless the installed released manifest certifies these exact dataset bytes and versions."""
    certification = spec.get("bundle_certification")
    if certification is None or any(versions.get(key) != certification[key]
                                    for key in ("bundle_package", "bundle_version", "model_version", "core_version")):
        return False
    try:
        path = importlib.metadata.distribution("policyengine").locate_file("policyengine/data/bundle/manifest.json")
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != certification["manifest_sha256"]:
            return False
        manifest = json.loads(raw)
        release = manifest["data_releases"]["uk"]
        artifact = release["certified_data_artifact"]
        return (release["bundle_id"] == certification["bundle_id"]
                and release["certification"]["certified_for_model_version"] == versions["model_version"]
                and artifact["dataset"] == spec["logical_name"]
                and artifact["sha256"] == spec["sha256"]
                and artifact["uri"] == f"hf://{spec['repo_id']}/{spec['path']}@{spec['revision']}"
                and artifact["data_package"] == {"name": spec["data_package"], "version": spec["data_version"]})
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError, KeyError, TypeError):
        return False


def ageing_anchor(name=None):
    """{year, calibration_year, source}: the year static ageing anchors a dataset's weights to (demography)."""
    return dict(DATASETS[resolve(name)]["ageing_anchor"])


def provenance(name=None):
    """Installed versions, pinned dataset bytes and whether the released UK bundle certifies this exact pair."""
    name = resolve(name)
    d = DATASETS[name]
    versions = model_versions()
    certified = _certified_by_installed_bundle(d, versions)
    return {
        **versions,
        "certified": certified,
        "certification": ("policyengine.py 6.2.6 UK bundle certification (#555)" if certified else UNCERTIFIED),
        **({"certification_bundle": dict(d["bundle_certification"])} if certified else {}),
        **({"release_manifest": dict(d["release_manifest"])} if "release_manifest" in d else {}),
        "runtime_dataset": d["logical_name"],
        "dataset": name,
        "runtime_dataset_uri": uri(name),
        "runtime_dataset_sha256": d["sha256"],
        "data_package": d["data_package"],
        "data_version": d["data_version"],
        "data_built_with": d["built_with"],
        **({"data_build_core_version": d["build_core_version"],
            "data_build_fingerprint": d["data_build_fingerprint"]} if "build_core_version" in d else {}),
        "data_certified_elsewhere": list(d["certified"]),
        "ageing_anchor": dict(d["ageing_anchor"]),
    }
