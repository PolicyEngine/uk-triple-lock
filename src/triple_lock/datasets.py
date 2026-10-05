"""The survey datasets every job runs on, each pinned to a revision and a SHA-256, and what a run records about them.

Until model-v2 the engine loaded its data through policyengine.py's managed
loader, whose release bundle certified one policyengine-uk version with one
data build. No policyengine.py release yet pins a policyengine-uk carrying the
pensioner fixes this analysis needs (6.2.1 pins 2.102.3, and refuses to import
beside a later one: its data certification raises), so the engine pins
policyengine-uk directly and loads the same files itself. ``materialize``
fetches a file from Hugging Face into one shared store, ``.cache/datasets``,
and checks its SHA-256 against the pin before every use, as the managed loader
did; the store keeps one copy of each file for every worker.

The combination is not certified: no policyengine.py bundle pairs these files
with the installed policyengine-uk. ``provenance`` records that, with the
installed model and core versions, in every run, and the results file carries
it.

``HUGGING_FACE_TOKEN`` must be set for a file that is not yet in the store (the
repositories are private).
"""

import contextlib
import hashlib
import importlib.metadata
import os
import shutil
from pathlib import Path

from .config import PRIMARY_DATASET, REPO

STORE = REPO / ".cache" / "datasets"

# name -> where the file is and what it must hash to. "certified" names the policyengine.py bundles that certified
# the file (for other policyengine-uk versions), "built_with" the policyengine-uk version its data build ran.
DATASETS = {
    "enhanced_frs_2024_25@1.56.16": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.56.16",
        "sha256": "e433e532b17bd8ce76030156285816e33d44e93edabd2204adbef71d19a68712",
        "data_package": "policyengine-uk-data", "data_version": "1.56.16",
        "built_with": "policyengine-uk 2.89.2",
        "certified": ["policyengine.py 5.3.0 (uk-5.3.0, policyengine-uk 2.90.2)",
                      "policyengine.py 6.2.1 (uk-6.2.1, policyengine-uk 2.102.3)"],
    },
    "enhanced_frs_2024_25@1.57.4": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.57.4",
        "sha256": "03fe15e40a4c7333498d1eac50a87e1ec2aec730782881e0f1812bc2aa8e68d4",
        "data_package": "policyengine-uk-data", "data_version": "1.57.4",
        "built_with": "policyengine-uk 2.93.0",
        "certified": [],
    },
    "populace_uk_2023": {
        "logical_name": "populace_uk_2023",
        "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "path": "populace_uk_2023.h5", "revision": "populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z",
        "sha256": "f17306ccb2aad7ff0130be3589b560afb2e2a12a943570911cd0c77f07934833",
        "data_package": "populace-data", "data_version": "populace-uk-2023-dd68c73-4aa4b14-20260619T023711Z",
        "built_with": None,
        "certified": ["policyengine.py 5.3.0 and 6.2.1 dataset overlay (uncertified sensitivity)"],
    },
}
UNCERTIFIED = ("uncertified: policyengine-uk is pinned directly, because no policyengine.py release bundle yet carries "
               "a version with the pensioner fixes this analysis needs (policyengine.py 6.2.1 pins 2.102.3); no "
               "bundle certifies this dataset with the installed policyengine-uk")


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
    return {"model_package": "policyengine-uk", "model_version": importlib.metadata.version("policyengine-uk"),
            "core_version": importlib.metadata.version("policyengine-core")}


def provenance(name=None):
    """What a run records about its model and data: the installed versions, the dataset's pin, and that the pair is
    uncertified."""
    name = resolve(name)
    d = DATASETS[name]
    return {
        **model_versions(),
        "certified": False,
        "certification": UNCERTIFIED,
        "runtime_dataset": d["logical_name"],
        "dataset": name,
        "runtime_dataset_uri": uri(name),
        "runtime_dataset_sha256": d["sha256"],
        "data_package": d["data_package"],
        "data_version": d["data_version"],
        "data_built_with": d["built_with"],
        "data_certified_elsewhere": list(d["certified"]),
    }
