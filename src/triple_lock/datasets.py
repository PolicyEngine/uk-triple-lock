"""Pinned data for the binding Microcosm primary and Enhanced FRS sensitivity.

d2011 = A (Max, 25 October 2026): the binding primary is the 2.151.0 national
and local-area pair built at microcosm#1396, Microcosm a6299504 / UK 2.151.0 /
core 3.33.3. Its carrier release is pending: provenance fails closed until its
released version, installed manifest digest, certifying pull request and
commit, and local-area cut are pinned below. #715's a133f37a / UK 2.147.2
pair, d1983's first binding pair, is d2011's fallback with policyengine.py
#699's area routing to the 19 October local-area cut, which is pinned already;
its bundle identities are pending the same way.
Historical Enhanced FRS and Microcosm artifacts retain their original pins.
Materialization checks the exact artifact SHA-256 before every use (cached
while unchanged), with one shared copy in .cache/datasets per artifact.
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

HISTORICAL_BUNDLE_6_2_6 = {
    "bundle_package": "policyengine", "bundle_version": "6.2.6",
    "bundle_id": "uk-6.2.6", "model_version": "2.125.1", "core_version": "3.33.0",
    "manifest_sha256": "8633ad814c9c85e53c7c513f69c4c7b1500a03cd2f6ef133d6e2ea8346b2db54",
    "certification_url": "https://github.com/PolicyEngine/policyengine.py/pull/555",
    "certification_commit": "37d25c423e9541b4ca86adbdd8687738b49ab8ec",
}
# #715's pair, d1983's first binding pair, is d2011's fallback if the 2.151.0 pair is not certified by Tue 27 Oct
# 18:00Z: a133f37a's national file with policyengine.py #699's area routing (the 19 Oct dense local-area cut
# microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe, built on 2.132.6, on an accepted model mismatch; pinned in
# FALLBACK_LOCAL_AREA below). #715's candidate head e02d41bc routes national only, and its 6.10.1 is NOT the release.
# Unknown until a fallback release: its version and installed manifest digest, and the pull request and commit that
# certify it. Each fails closed while None.
FALLBACK_BUNDLE_VERSION = None
FALLBACK_BUNDLE_MANIFEST_SHA256 = None
FALLBACK_CERTIFICATION_URL = None
FALLBACK_CERTIFICATION_COMMIT = None
BUNDLE_715 = {
    "bundle_package": "policyengine", "bundle_version": FALLBACK_BUNDLE_VERSION,
    "bundle_id": f"uk-{FALLBACK_BUNDLE_VERSION}", "model_version": "2.147.2", "core_version": "3.33.3",
    "manifest_path": "policyengine/data/bundle/manifest.json",
    "manifest_sha256": FALLBACK_BUNDLE_MANIFEST_SHA256,
    "model_wheel_sha256": "4b48ab1008b00610abc38192927ac9d4bb22037b6bbd9578926c2899e639f972",
    "wheels": {
        "policyengine-uk": {
            "manifest_path": "data/certification/d1983-model-wheel.json",
            "manifest_sha256": "de8eef1d683041e535abff7257d61c9bd4b32440027e3f09c399e57181c43f62",
            "wheel_sha256": "4b48ab1008b00610abc38192927ac9d4bb22037b6bbd9578926c2899e639f972",
        },
        "policyengine-core": {
            "manifest_path": "data/certification/d1983-core-wheel.json",
            "manifest_sha256": "dfbd18d2553e84b0e302ea22a637d4b66b6214623be7ec67874fbbe5fac42867",
            "wheel_sha256": "5847d9938412095fe9848c2ce535838a7dc8fac9238d8fd9e6c9d0a0648e0888",
        },
    },
    "certification_url": FALLBACK_CERTIFICATION_URL,
    "certification_commit": FALLBACK_CERTIFICATION_COMMIT,
}


def microcosm_release_manifest(revision):
    """Where a Microcosm UK national release tag keeps its release manifest."""
    return {
        "revision": revision,
        "path": "releases/microcosm-uk-2024-25-national/release_manifest.json",
        "uri": f"https://huggingface.co/datasets/policyengine/populace-uk-private/resolve/{revision}/"
               "releases/microcosm-uk-2024-25-national/release_manifest.json",
        "source_uri": f"hf://dataset/policyengine/populace-uk-private@{revision}/"
                      "releases/microcosm-uk-2024-25-national/release_manifest.json",
    }


LOCAL_AREA_REPO = "policyengine/populace-uk-private"
LOCAL_AREA_RELEASE_MANIFEST = "releases/microcosm-uk-2024-25-dense/release_manifest.json"


def local_area_cut(path, revision, sha256, manifest_sha256, built_with_model_version, model_basis):
    """The local-area cut a d2011 pair's constituency and local-authority runs load: its file, release tag and
    SHA-256; where the bundle names its release manifest, and the SHA-256 of those bytes; the model its build ran;
    and the basis on which the bundle routes to it. "built_with": the cut's build ran the pair's own model, so the
    bundle carries no regional_certification. "accepted_model_mismatch": policyengine.py #699's
    regional_certification records the reviewed mismatch. Any pending (None) part certifies nothing."""
    uri = lambda form: None if revision is None else form.format(repo=LOCAL_AREA_REPO, revision=revision,
                                                                 manifest=LOCAL_AREA_RELEASE_MANIFEST)
    return {"path": path, "repo_id": LOCAL_AREA_REPO, "repo_type": "dataset", "revision": revision, "sha256": sha256,
            "release_manifest_uri": uri("https://huggingface.co/datasets/{repo}/resolve/{revision}/{manifest}"),
            "source_manifest_uri": uri("hf://dataset/{repo}@{revision}/{manifest}"),
            "manifest_sha256": manifest_sha256, "built_with_model_version": built_with_model_version,
            "model_basis": model_basis}


def area_routed(local_area_path):
    """A UK Budget release's region routing: the national file serves national runs, and policyengine.py routes
    constituency and local-authority runs to the local-area file (provenance/certification.py:
    LOCAL_AREA_REGION_TYPES["uk"]). A pending (None) file certifies nothing."""
    return {"national": {"path_template": "microcosm_uk_2024_25.h5"},
            "constituency": {"path_template": local_area_path},
            "local_authority": {"path_template": local_area_path}}


MICROCOSM_REVISION_A133 = "microcosm-uk-2024-25-national-20261023T075039Z-a133f37a"
MICROCOSM_RELEASE_MANIFEST_A133 = microcosm_release_manifest(MICROCOSM_REVISION_A133)
# The release manifest at the cut's tag is 61,723 bytes; its build (built_with_model_package 2.132.6, core 3.33.3)
# names the tag as its cut_tag. policyengine.py 6.11.0 and #699's Budget route both route to this file.
FALLBACK_LOCAL_AREA = local_area_cut(
    "microcosm_uk_2024_25_dense.h5", "microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe",
    "8e10e130d0260e0b52e2e29902f0502ebdff76a14a3e57d2c876bf4cd8db5872",
    "b9dc7cae358b9c965935f83721508594f9fb56a35911ffb0f9216ecb6a799561", "2.132.6", "accepted_model_mismatch")
FALLBACK_REGION_DATASETS = area_routed(FALLBACK_LOCAL_AREA["path"])

# d2011's pair. Unknown until the policyengine.py release that carries it: that release's version and installed
# manifest digest, the pull request and commit that certify it, and the 2.151.0 local-area cut its constituency and
# local-authority runs load (file, release tag, SHA-256, and the SHA-256 of the cut's release manifest). Each fails
# closed while None; scripts/fill_release_identities.py fills them from the release.
BINDING_BUNDLE_VERSION = None
BINDING_BUNDLE_MANIFEST_SHA256 = None
BINDING_CERTIFICATION_URL = None
BINDING_CERTIFICATION_COMMIT = None
BINDING_LOCAL_AREA_PATH = None
BINDING_LOCAL_AREA_REVISION = None
BINDING_LOCAL_AREA_SHA256 = None
BINDING_LOCAL_AREA_MANIFEST_SHA256 = None
# The base carrier the preparatory lock installs while BINDING_BUNDLE_VERSION is pending (its [uk] extra pins its own
# previous model, so the lock omits it); the fill replaces it with the release in pyproject.toml and the lock.
PREPARATORY_CARRIER = "6.10.1"
CERTIFIED_BUNDLE = {
    "bundle_package": "policyengine", "bundle_version": BINDING_BUNDLE_VERSION,
    "bundle_id": f"uk-{BINDING_BUNDLE_VERSION}", "model_version": "2.151.0", "core_version": "3.33.3",
    "manifest_path": "policyengine/data/bundle/manifest.json",
    "manifest_sha256": BINDING_BUNDLE_MANIFEST_SHA256,
    "model_wheel_sha256": "5722f55aca3eb88e1a228e95e1a57e3bd70a4d530a5a000991565ebd8955ce35",
    "wheels": {
        "policyengine-uk": {
            "manifest_path": "data/certification/d2011-model-wheel.json",
            "manifest_sha256": "a67bd0a5afad28def6327f3cb2f056ef54c5e5da31eb03f4003d58d7ca5edc25",
            "wheel_sha256": "5722f55aca3eb88e1a228e95e1a57e3bd70a4d530a5a000991565ebd8955ce35",
        },
        "policyengine-core": {
            "manifest_path": "data/certification/d1983-core-wheel.json",
            "manifest_sha256": "dfbd18d2553e84b0e302ea22a637d4b66b6214623be7ec67874fbbe5fac42867",
            "wheel_sha256": "5847d9938412095fe9848c2ce535838a7dc8fac9238d8fd9e6c9d0a0648e0888",
        },
    },
    "certification_url": BINDING_CERTIFICATION_URL,
    "certification_commit": BINDING_CERTIFICATION_COMMIT,
}
# d2011's pairs, binding first: the only primaries certified_bundle_preflight admits. The fallback becomes the
# primary only in its own reviewed commit (docs/REBUILD.md, "Fallback").
D2011_PAIRS = ("microcosm_uk_2024_25@a6299504", "microcosm_uk_2024_25@a133f37a")
# The national's release tag, from the staged attempt uk-frs-calibration-attempt-20261025T091414Z-a6299504
# (staged_manifest.json: git_commit 67ee2ddf3, clean). The tag exists on the Hub with the pinned file (checked 26
# October: LFS SHA-256 b96a8cd6..., 342,348,841 bytes); materialization still verifies the bytes before every use, and
# the bundle must name the same artifact URI.
MICROCOSM_REVISION = "microcosm-uk-2024-25-national-20261025T091414Z-a6299504"
MICROCOSM_RELEASE_MANIFEST = microcosm_release_manifest(MICROCOSM_REVISION)
BINDING_LOCAL_AREA = local_area_cut(BINDING_LOCAL_AREA_PATH, BINDING_LOCAL_AREA_REVISION, BINDING_LOCAL_AREA_SHA256,
                                    BINDING_LOCAL_AREA_MANIFEST_SHA256, "2.151.0", "built_with")
BINDING_REGION_DATASETS = area_routed(BINDING_LOCAL_AREA_PATH)
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
    # SHA-256 of the staged attempt's file (staged_manifest.json and the Hub's LFS object, 342,348,841 bytes).
    "microcosm_uk_2024_25@a6299504": {
        "logical_name": "microcosm_uk_2024_25",
        "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "path": "microcosm_uk_2024_25.h5", "revision": MICROCOSM_REVISION,
        "sha256": "b96a8cd625b645a409c063b1de5158532708a2f0d3c3897a794a8fb0bbd5064e",
        "data_package": "microcosm-data", "data_version": "0.1.0",  # packages/microcosm-data at 67ee2ddf3
        "built_with": "policyengine-uk 2.151.0 (policyengine-core 3.33.3)",
        "build_id": MICROCOSM_REVISION,
        "certified": [],  # pending release; producer gates are not released bundle certification.
        "bundle_certification": CERTIFIED_BUNDLE,
        "release_manifest": MICROCOSM_RELEASE_MANIFEST,
        "region_datasets": BINDING_REGION_DATASETS,
        "local_area": BINDING_LOCAL_AREA,
        # Solved at 2025 and written divided by the model's 2024-to-2025 projection, as a133f37a's are.
        "ageing_anchor": {"year": 2025, "calibration_year": 2025,
                          "source": "uk-frs-calibration-attempt-20261025T091414Z-a6299504: build_record.json "
                                    "uk_national_export_readback weight_year (dataset_year 2024, solve_year 2025, "
                                    "engine_projection_factor 1.0072); calibration_diagnostics.json dates all 1,268 "
                                    "targets 2025"},
    },
    "microcosm_uk_2024_25@a133f37a": {
        "logical_name": "microcosm_uk_2024_25",
        "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "path": "microcosm_uk_2024_25.h5", "revision": MICROCOSM_REVISION_A133,
        "sha256": "64f83900ca3a1242fb017585234844ce89f743d32e41cd2b6558057777f914aa",
        "data_package": "microcosm-data", "data_version": "0.1.0",
        "built_with": "policyengine-uk 2.147.2 (policyengine-core 3.33.3)",
        "build_id": MICROCOSM_REVISION_A133,
        "certified": [],  # #715 is draft; producer gates are not released bundle certification.
        "bundle_certification": BUNDLE_715,
        "release_manifest": MICROCOSM_RELEASE_MANIFEST_A133,
        "region_datasets": FALLBACK_REGION_DATASETS,
        "local_area": FALLBACK_LOCAL_AREA,
        # The build solves its household weights at 2025 and writes them divided by policyengine-uk's own
        # 2024-to-2025 projection of household_weight, so the model's 2025 weights are the solved ones
        # (microcosm weight_year.py, microcosm#796 A19). The Enhanced FRS's 2025 weights are instead its calibrated
        # ones times 0.9956 (policyengine-uk-data#538; METHOD.md, "The Enhanced FRS calibration year's level").
        "ageing_anchor": {"year": 2025, "calibration_year": 2025,
                          "source": "microcosm-uk-2024-25-national-20261023T075039Z-a133f37a: build_record.json "
                                    "uk_national_export_readback weight_year (dataset_year 2024, solve_year 2025, "
                                    "engine_projection_factor 1.0072); calibration_diagnostics.json dates all 1,259 "
                                    "targets 2025"},
    },
    "enhanced_frs_2024_25@1.58.2": {
        "logical_name": "enhanced_frs_2024_25",
        "repo_id": "policyengine/policyengine-uk-data-private", "repo_type": "model",
        "path": "enhanced_frs_2024_25.h5", "revision": "1.58.2",
        "sha256": "40804ba2540458cb6f3c476d29d3bb4bc88d9ac6b401fa285ed6e4232a55aa52",
        "data_package": "policyengine-uk-data", "data_version": "1.58.2",
        "built_with": None, "certified": [],
        "release_manifest": {
            "revision": "a14737cd9499e1059cbec579ddf9aec3b3667ed1",
            "path": "releases/1.58.2/release_manifest.json",
            "sha256": "6867e8a7bd8be6110816527191b2348f712c4ba2502886696142506bb59fbbff",
            "uri": "https://huggingface.co/policyengine/policyengine-uk-data-private/resolve/"
                   "a14737cd9499e1059cbec579ddf9aec3b3667ed1/releases/1.58.2/release_manifest.json",
        },
        "ageing_anchor": {"year": 2025, "calibration_year": 2025,
                          "source": CALIBRATION_SOURCE.format(tag="1.58.2")},
    },
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
        "bundle_certification": HISTORICAL_BUNDLE_6_2_6,
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
    # Microcosm's UK national release (PolicyEngine/microcosm 64c460b), the paired dataset sensitivity. Built and
    # declared compatible with policyengine-uk 2.100.0 only, so uncertified under this bundle.
    "microcosm_uk_2024_25": {
        "logical_name": "microcosm_uk_2024_25",
        "repo_id": "policyengine/populace-uk-private", "repo_type": "dataset",
        "path": "microcosm_uk_2024_25.h5", "revision": "microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68",
        "sha256": "aa31bdf67c977927ea2b325567d1cf7a79d94381239bc79918a0a0fc9c9588af",
        "data_package": "microcosm-data", "data_version": "microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68",
        "built_with": "policyengine-uk 2.100.0 (policyengine-core 3.32.5)",
        "certified": [],
        # Every one of its 1,168 calibration targets is for 2025 (releases/microcosm-uk-2024-25-national/
        # calibration_diagnostics.json), the Enhanced FRS's calibration year.
        "ageing_anchor": {"year": 2025, "calibration_year": 2025,
                          "source": "microcosm-uk-2024-25-national release, calibration_diagnostics.json: all 1,168 "
                                    "targets have period 2025"},
    },
}
UNCERTIFIED = ("uncertified: the exact released policyengine.py bundle/model/core and artifact are required; "
               "the release carrying d2011's binding Microcosm UK Budget pair is pending")


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


def certified_core(manifest):
    """The core a UK bundle's certificate covers, by policyengine.py's rule (provenance/manifest.py
    DataCertification; provenance/receipt.py _certificate_fields), made stricter where that rule would fall back to
    the pin. core_binding "certified" must name the core in certified_for_core_version, and the bundle's core pin
    must equal it; "bundle_pin" (or no binding, before October 2026) covers the bundle's core pin, and a named core
    must equal it. None for anything else (an unnamed "certified" core, a named core off the pin, an unknown
    binding), which certifies nothing."""
    certificate = manifest["data_releases"]["uk"]["certification"]
    pin = manifest["packages"]["policyengine-core"]["version"]
    binding, named = certificate.get("core_binding"), certificate.get("certified_for_core_version")
    if binding == "certified":
        return named if named == pin else None
    if binding in (None, "bundle_pin"):
        return named or pin if named in (None, pin) else None
    return None


def _local_area_routed(release, local, model_version):
    """Whether a release routes areas to exactly the pinned local-area cut, on the pinned basis. Fails closed while
    any part of the cut is pending."""
    if any(local[key] is None for key in ("path", "revision", "sha256", "manifest_sha256")):
        return False
    entries = [entry for entry in release["datasets"].values()
               if isinstance(entry, dict) and entry.get("path") == local["path"]]
    if (len(entries) != 1
            or any(entries[0].get(key) != local[key] for key in ("repo_id", "revision", "sha256"))
            or entries[0].get("repo_type", local["repo_type"]) != local["repo_type"]
            or release.get("regional_release_kind") != "local_area"
            or release.get("regional_release_manifest_uri") != local["release_manifest_uri"]
            or release.get("regional_source_manifest_uri") != local["source_manifest_uri"]
            or release.get("regional_source_manifest_sha256", local["manifest_sha256"]) != local["manifest_sha256"]):
        return False
    regional = release.get("regional_certification")
    if local["model_basis"] == "built_with":
        # Both halves on the pair's own model: an accepted mismatch is not this pair.
        return regional is None and local["built_with_model_version"] == model_version
    return (local["model_basis"] == "accepted_model_mismatch" and isinstance(regional, dict)
            and release.get("regional_source_manifest_sha256") == local["manifest_sha256"]
            and regional.get("compatibility_basis") == "accepted_model_mismatch"
            and regional.get("certified_for_model_version") == model_version
            and regional.get("built_with_model_version") == local["built_with_model_version"]
            and regional.get("regional_manifest_uri") == local["source_manifest_uri"]
            and regional.get("regional_manifest_sha256") == local["manifest_sha256"]
            and regional.get("area_receipts") == "uncertified")


def _certified_by_installed_bundle(spec, versions):
    """Fail closed unless released-manifest or ledger evidence certifies the exact pair. A released-manifest
    certificate also needs the pull request and commit that certify it, and a pair with a local-area cut needs that
    exact cut."""
    certification = spec.get("bundle_certification")
    regions = spec.get("region_datasets", {"national": {"path_template": spec["path"]}})
    if not all(isinstance(template, dict) and template.get("path_template") for template in regions.values()):
        return False  # a pending file (BINDING_LOCAL_AREA_PATH) certifies nothing
    if (certification is None or not certification.get("bundle_version")
            or not certification.get("manifest_sha256") and "ledger_source_path" not in certification
            or "ledger_source_path" not in certification
            and not (certification.get("certification_url") and certification.get("certification_commit"))
            or any(versions.get(key) != certification[key]
                                    for key in ("bundle_package", "bundle_version", "model_version", "core_version"))):
        return False
    if "ledger_source_path" in certification:
        from .certification import CertificationMismatch, verify_bundle

        try:
            verify_bundle(certification, spec, versions)
            return True
        except CertificationMismatch:
            return False
    try:
        path = importlib.metadata.distribution("policyengine").locate_file(certification.get("manifest_path", "policyengine/data/bundle/manifest.json"))
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != certification["manifest_sha256"]:
            return False
        manifest = json.loads(raw)
        release = manifest["data_releases"]["uk"]
        artifact = release["certified_data_artifact"]
        if "model_wheel_sha256" in certification:
            if (manifest["policyengine_version"] != versions["bundle_version"]
                    or release["policyengine_version"] != versions["bundle_version"]
                    or manifest["packages"]["policyengine-core"]["version"] != versions["core_version"]
                    or certified_core(manifest) != versions["core_version"]
                    or release["model_package"]["version"] != versions["model_version"]
                    or release["model_package"]["sha256"] != certification["model_wheel_sha256"]
                    or release["build_id"] != spec["build_id"]
                    or artifact["build_id"] != spec["build_id"]
                    or release["release_manifest_uri"] != spec["release_manifest"]["uri"]
                    or release["source_manifest_uri"] != spec["release_manifest"]["source_uri"]
                    or release["region_datasets"] != regions
                    or "local_area" in spec
                    and not _local_area_routed(release, spec["local_area"], versions["model_version"])):
                return False
        matches = (release["bundle_id"] == certification["bundle_id"]
                and release["certification"]["certified_for_model_version"] == versions["model_version"]
                and artifact["dataset"] == spec["logical_name"]
                and artifact["sha256"] == spec["sha256"]
                and artifact["uri"] == f"hf://{spec['repo_id']}/{spec['path']}@{spec['revision']}"
                and artifact["data_package"] == {"name": spec["data_package"], "version": spec["data_version"]})
        if not matches:
            return False
        if "wheels" in certification:
            from .certification import CertificationMismatch, verify_released_bundle_payloads

            try:
                verify_released_bundle_payloads(certification)
            except CertificationMismatch:
                return False
        return True
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
        "certification": (("policyengine.py UK qualification-ledger receipt" if "ledger_source_path" in
                           d["bundle_certification"] else f"policyengine.py {d['bundle_certification']['bundle_version']} UK bundle certification")
                          if certified else UNCERTIFIED),
        **({"certification_bundle": dict(d["bundle_certification"])} if certified else {}),
        **({"release_manifest": dict(d["release_manifest"])} if "release_manifest" in d else {}),
        "runtime_dataset": d["logical_name"],
        "dataset": name,
        "runtime_dataset_uri": uri(name),
        "runtime_dataset_sha256": d["sha256"],
        "data_package": d["data_package"],
        "data_version": d["data_version"],
        "data_built_with": d["built_with"],
        **({"data_build_id": d["build_id"]} if "build_id" in d else {}),
        **({"data_build_core_version": d["build_core_version"],
            "data_build_fingerprint": d["data_build_fingerprint"]} if "build_core_version" in d else {}),
        "data_certified_elsewhere": list(d["certified"]),
        "ageing_anchor": dict(d["ageing_anchor"]),
    }
