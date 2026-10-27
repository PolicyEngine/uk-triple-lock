"""A released UK bundle manifest carrying one of d2011's pairs, as its policyengine.py release would carry it."""

from copy import deepcopy
import hashlib
import json

from triple_lock import datasets
from triple_lock.config import REPO

VERSION = "99.0.0"  # Fictional future release, never a production pin.
LOCAL_AREA_KEYS = ("path", "revision", "sha256", "manifest_sha256")
# A fictional 2.151.0 local-area cut, standing in for the binding pair's own while it is pending.
INVENTED_CUT = datasets.local_area_cut("invented_local_area.h5", "invented-local-area-cut", "c" * 64, "d" * 64,
                                       "2.151.0", "built_with")


def cut(name):
    """The pair's local-area cut: its pinned one, or the invented one while the binding cut is pending."""
    local = datasets.DATASETS[name]["local_area"]
    return deepcopy(local if all(local[key] is not None for key in LOCAL_AREA_KEYS) else INVENTED_CUT)


def regional_manifest(local, core="3.33.3"):
    """The fields of a local-area cut's own release manifest that the fill checks, as its build writes them.
    Synthetic: the real ones are metadata of a private repository."""
    return {"build": {"cut_tag": local["revision"],
                      "built_with_model_package": {"name": "policyengine-uk",
                                                   "version": local["built_with_model_version"]},
                      "built_with_core_package": {"name": "policyengine-core", "version": core}},
            "dataset_role": "non_default_local_area",
            "artifacts": {"microcosm_uk_2024_25_dense": {
                "kind": "microdata", "path": local["path"], "repo_id": local["repo_id"],
                "revision": local["revision"], "sha256": local["sha256"]}}}


def regional_certification(local, model_version):
    """policyengine.py #699's record of an accepted model mismatch between a pair and its local-area cut."""
    return {"compatibility_basis": "accepted_model_mismatch", "certified_for_model_version": model_version,
            "built_with_model_version": local["built_with_model_version"],
            "accepted_reason": "Synthetic fixture.", "area_receipts": "uncertified",
            "regional_manifest_uri": local["source_manifest_uri"], "regional_manifest_sha256": local["manifest_sha256"],
            "defaulted_inputs": [], "dropped_columns": [], "limitations": [], "evidence": []}


def released(name, local=None, version=VERSION):
    """(manifest, local, regional_raw): #715's candidate skeleton re-pointed at the pair ``name``'s pins, routing
    areas to the cut ``local`` (default: ``cut(name)``), whose manifest SHA-256 becomes the synthetic bytes'."""
    spec = datasets.DATASETS[name]
    certification = spec["bundle_certification"]
    local = deepcopy(local or cut(name))
    regional_raw = json.dumps(regional_manifest(local, certification["core_version"])).encode()
    local["manifest_sha256"] = hashlib.sha256(regional_raw).hexdigest()
    manifest = json.loads((REPO / "data/certification/d1983-candidate-bundle-manifest.json").read_text())
    release = manifest["data_releases"]["uk"]
    # Every field the release workflow rewrites for the carrier, as it writes them.
    manifest["bundle_version"] = manifest["policyengine_version"] = version
    manifest["packages"]["policyengine"].update(version=version, install_requirement=f"policyengine=={version}")
    manifest["citation"].update(title=f"PolicyEngine bundle {version}", version=version)
    for country, data_release in manifest["data_releases"].items():
        data_release.update(policyengine_version=version, bundle_id=f"{country}-{version}")
    core = certification["core_version"]
    manifest["packages"]["policyengine-core"].update(version=core, install_requirement=f"policyengine-core=={core}")
    release["certification"]["certified_for_core_version"] = certification["core_version"]
    release["model_package"].update(version=certification["model_version"], sha256=certification["model_wheel_sha256"])
    release["certification"]["certified_for_model_version"] = certification["model_version"]
    release["build_id"] = spec["build_id"]
    release["certified_data_artifact"].update(
        build_id=spec["build_id"], dataset=spec["logical_name"], sha256=spec["sha256"],
        uri=f"hf://{spec['repo_id']}/{spec['path']}@{spec['revision']}",
        data_package={"name": spec["data_package"], "version": spec["data_version"]})
    release["release_manifest_uri"] = spec["release_manifest"]["uri"]
    release["source_manifest_uri"] = spec["release_manifest"]["source_uri"]
    release["region_datasets"] = datasets.area_routed(local["path"])
    release["datasets"]["microcosm_uk_2024_25_dense"] = {key: local[key] for key in ("path", "repo_id", "revision",
                                                                                      "sha256")}
    release.update(regional_release_kind="local_area", regional_release_manifest_uri=local["release_manifest_uri"],
                   regional_source_manifest_uri=local["source_manifest_uri"])
    if local["model_basis"] == "accepted_model_mismatch":
        release["regional_source_manifest_sha256"] = local["manifest_sha256"]
        release["regional_certification"] = regional_certification(local, certification["model_version"])
    return manifest, local, regional_raw
