"""The release-night fill checks every pinned identity and writes only what the release supplies."""

from copy import deepcopy
import hashlib
import json
import shutil

import pytest

from scripts import binding_bridge
from scripts import fill_release_identities as fill
from triple_lock import datasets
from triple_lock.config import REPO

VERSION = "99.0.0"  # Fictional future release, never a production pin.
LOCAL_AREA = "invented_local_area.h5"
MERGED = {"html_url": "https://github.com/PolicyEngine/policyengine.py/pull/9999", "merged_at": "2026-10-26T23:00:00Z",
          "merge_commit_sha": "1" * 40, "head": {"sha": "2" * 40}}


def released_manifest(name):
    """#715's candidate skeleton, re-pointed at the named pair's pins as its release would carry them."""
    spec = datasets.DATASETS[name]
    certification = spec["bundle_certification"]
    manifest = json.loads((REPO / "data/certification/d1983-candidate-bundle-manifest.json").read_text())
    release = manifest["data_releases"]["uk"]
    manifest["policyengine_version"] = release["policyengine_version"] = VERSION
    release["bundle_id"] = f"uk-{VERSION}"
    manifest["packages"]["policyengine-core"]["version"] = certification["core_version"]
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
    release["region_datasets"] = datasets.area_routed(LOCAL_AREA)
    return manifest


def failing(manifest, name):
    return [label for label, pinned, released in fill.checks(manifest, datasets.DATASETS[name]) if pinned != released]


@pytest.mark.parametrize("target", sorted(fill.TARGETS))
def test_a_release_carrying_the_pinned_pair_passes_every_check(target):
    name, _ = fill.TARGETS[target]
    assert failing(released_manifest(name), name) == []


@pytest.mark.parametrize("target", sorted(fill.TARGETS))
def test_a_bundle_pin_certificate_like_6_11_0s_passes(target):
    name, _ = fill.TARGETS[target]
    manifest = released_manifest(name)
    certificate = manifest["data_releases"]["uk"]["certification"]
    del certificate["certified_for_core_version"]
    certificate["core_binding"] = "bundle_pin"
    assert failing(manifest, name) == []


@pytest.mark.parametrize("target", sorted(fill.TARGETS))
@pytest.mark.parametrize("where,key,value,label", [
    ("uk", "policyengine_version", "98.0.0", "UK release carrier version"),
    ("uk", "bundle_id", "uk-98.0.0", "bundle id"),
    ("core", "version", "3.33.0", "core version"),
    ("certification", "certified_for_core_version", "3.33.0", "core version certified for"),
    ("model_package", "version", "2.153.4", "model version"),
    ("certification", "certified_for_model_version", "2.153.4", "model version certified for"),
    ("model_package", "sha256", "0" * 64, "model wheel SHA-256"),
    ("uk", "build_id", "other-cut", "release build id"),
    ("artifact", "build_id", "other-cut", "artifact build id"),
    ("uk", "release_manifest_uri", "https://example.com/other", "release manifest URI"),
    ("uk", "source_manifest_uri", "hf://other", "source manifest URI"),
    ("artifact", "dataset", "enhanced_frs_2024_25", "artifact dataset"),
    ("artifact", "sha256", "0" * 64, "artifact SHA-256"),
    ("artifact", "uri", "hf://policyengine/other/microcosm_uk_2024_25.h5@x", "artifact URI"),
    ("artifact", "data_package", {"name": "microcosm-data", "version": "0.2.0"}, "artifact data package"),
    # #715's national-only candidate routing, or an area type left out, is not d2011's pair.
    ("uk", "region_datasets", {"national": {"path_template": "microcosm_uk_2024_25.h5"}}, "routed regions"),
    ("regions", "national", {"path_template": "other.h5"}, "national file"),
    ("regions", "local_authority", {"path_template": "other_local_area.h5"}, "one local-area file for both area types"),
    ("regions", "constituency", {"path_template": ""}, "one local-area file for both area types"),
])
def test_each_pinned_identity_is_checked(target, where, key, value, label):
    name, _ = fill.TARGETS[target]
    manifest = released_manifest(name)
    release = manifest["data_releases"]["uk"]
    container = {"uk": release, "core": manifest["packages"]["policyengine-core"],
                 "certification": release["certification"], "model_package": release["model_package"],
                 "artifact": release["certified_data_artifact"], "regions": release["region_datasets"]}[where]
    container[key] = value
    assert label in failing(manifest, name)


def test_identities_come_from_the_exact_bytes_and_the_merge():
    manifest = released_manifest(fill.TARGETS["binding"][0])
    raw = json.dumps(manifest).encode()
    assert fill.identities(raw, manifest, MERGED) == {
        "BUNDLE_VERSION": VERSION, "BUNDLE_MANIFEST_SHA256": hashlib.sha256(raw).hexdigest(),
        "CERTIFICATION_URL": MERGED["html_url"], "CERTIFICATION_COMMIT": MERGED["merge_commit_sha"],
        "LOCAL_AREA_PATH": LOCAL_AREA}
    candidate = {**MERGED, "merged_at": None}
    assert fill.identities(raw, manifest, candidate)["CERTIFICATION_COMMIT"] is None


@pytest.fixture
def tree(tmp_path):
    """A copy of the files the fill writes, so the real tree is never touched."""
    for relative in ("src/triple_lock/datasets.py", "pyproject.toml", "requirements-lock.txt",
                     "data/binding-bridge.pending.json"):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, tmp_path / relative)
    return tmp_path


def values():
    manifest = released_manifest(fill.TARGETS["binding"][0])
    return fill.identities(json.dumps(manifest).encode(), manifest, MERGED)


def assignments(text, prefix):
    return {name: line.split(" = ", 1)[1] for line in text.splitlines()
            for name in fill.IDENTITIES if line.startswith(f"{prefix}_{name} = ")}


def test_the_binding_fill_writes_every_pin_and_a_ready_bridge(tree):
    filled = values()
    fill.fill(tree, "BINDING", filled, MERGED["head"]["sha"])
    text = (tree / "src/triple_lock/datasets.py").read_text()
    assert assignments(text, "BINDING") == {name: json.dumps(filled[name]) for name in fill.IDENTITIES}
    assert set(assignments(text, "FALLBACK").values()) == {"None"}
    assert f'"policyengine=={VERSION}",' in (tree / "pyproject.toml").read_text()
    assert f"\npolicyengine=={VERSION}\n" in (tree / "requirements-lock.txt").read_text()
    pending = json.loads((REPO / "data/binding-bridge.pending.json").read_text())
    assert json.loads((tree / "data/binding-bridge.pending.json").read_text()) == pending
    ready = json.loads((tree / "data/binding-bridge.json").read_text())
    binding_bridge.validate_configuration(ready)
    assert ready["pending_release"] == {**pending["pending_release"], "pull_request": MERGED["html_url"],
                                        "reviewed_head": MERGED["head"]["sha"], "policyengine_version": VERSION,
                                        "bundle_manifest_sha256": filled["BUNDLE_MANIFEST_SHA256"]}
    # Only the three carrier pins and the status change: model, core and dataset pins stay exactly as reviewed.
    expected = deepcopy(pending)
    expected["status"] = "ready"
    expected["pending_release"] = ready["pending_release"]
    for step, endpoint in (("model", "to"), ("data", "from"), ("data", "to")):
        expected["steps"][step][endpoint]["packages"]["policyengine"] = VERSION
    assert ready == expected


def test_the_fallback_fill_writes_only_its_own_identities(tree):
    before = {path: path.read_bytes() for path in tree.rglob("*") if path.is_file()}
    fill.fill(tree, "FALLBACK", values(), MERGED["head"]["sha"])
    text = (tree / "src/triple_lock/datasets.py").read_text()
    assert set(assignments(text, "FALLBACK").values()) != {"None"}
    assert set(assignments(text, "BINDING").values()) == {"None"}
    changed = {path.relative_to(tree).as_posix() for path in tree.rglob("*")
               if path.is_file() and before.get(path) != path.read_bytes()}
    assert changed == {"src/triple_lock/datasets.py"}


@pytest.mark.parametrize("missing", ["CERTIFICATION_COMMIT", "LOCAL_AREA_PATH"])
def test_a_value_the_release_does_not_supply_writes_nothing(tree, missing):
    before = {path: path.read_bytes() for path in tree.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match=missing):
        fill.fill(tree, "BINDING", {**values(), missing: None}, MERGED["head"]["sha"])
    assert {path: path.read_bytes() for path in tree.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("change,code", [(None, 0), ("artifact SHA-256", 1)])
def test_main_refuses_a_differing_release_before_writing(tree, tmp_path, monkeypatch, change, code):
    manifest = released_manifest(fill.TARGETS["binding"][0])
    if change:
        manifest["data_releases"]["uk"]["certified_data_artifact"]["sha256"] = "0" * 64
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(fill, "github", lambda _: MERGED)
    monkeypatch.setattr(fill, "ROOT", tree)
    assert fill.main(["--pr", "9999", "--manifest", str(path), "--apply"]) == code
    assert (tree / "data/binding-bridge.json").exists() is (code == 0)


def test_a_rerun_checks_the_identities_already_filled(tmp_path, monkeypatch, capsys):
    manifest = released_manifest(fill.TARGETS["binding"][0])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    filled = fill.identities(path.read_bytes(), manifest, MERGED)
    monkeypatch.setattr(fill, "github", lambda _: MERGED)
    for key, value in filled.items():
        monkeypatch.setattr(datasets, f"BINDING_{key}", value)
    assert fill.main(["--pr", "9999", "--manifest", str(path)]) == 0
    assert capsys.readouterr().out.count("ok   filled BINDING_") == len(fill.IDENTITIES)
    with pytest.raises(SystemExit, match="already filled"):
        fill.main(["--pr", "9999", "--manifest", str(path), "--apply"])
    # Installed bytes that differ from the pinned digest refuse.
    path.write_text(json.dumps(manifest, indent=1))
    assert fill.main(["--pr", "9999", "--manifest", str(path)]) == 1
    assert "FAIL filled BINDING_BUNDLE_MANIFEST_SHA256" in capsys.readouterr().out
