"""The release-night fill checks every pinned identity and writes only what the release supplies."""

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

import pytest

from released_pair import INVENTED_CUT, VERSION, regional_certification, released
from scripts import binding_bridge
from scripts import fill_release_identities as fill
from triple_lock import datasets
from triple_lock.config import REPO

BINDING, FALLBACK = fill.TARGETS["binding"][0], fill.TARGETS["fallback"][0]
MERGED = {"html_url": "https://github.com/PolicyEngine/policyengine.py/pull/9999", "merged_at": "2026-10-26T23:00:00Z",
          "merge_commit_sha": "1" * 40, "head": {"sha": "2" * 40}}
OLD = "98.0.0"  # The fictional carrier the certifying merge's manifest names before the release's version commit.
ROUTED = "installed check routes to this cut"
REWRITE = "release manifest is the workflow's rewrite of the merge's"
# Real policyengine.py bundle manifests (a public repository), each at src/policyengine/data/bundle/manifest.json:
# two certifying merges and the releases cut from them.
UPSTREAM = Path(__file__).parent / "fixtures/policyengine-bundle-manifests"
UPSTREAM_SHA256 = {
    "pr-704-merge-13192b52.json": "461fe51f720501eda986d09e35d779a96269aeff203d4cda17f611ee357b0a73",  # 13192b524
    "release-6.11.0.json": "bccf23acde631aed4665757094c04f86e60993fb9d388e7dc958b90c876e5a80",
    "pr-555-merge-37d25c42.json": "e7f94bdd88818764e4112e1b6eb74a98d196683ec29ad0a552d38062e701fe8c",  # 37d25c423
    "release-6.2.6.json": "8633ad814c9c85e53c7c513f69c4c7b1500a03cd2f6ef133d6e2ea8346b2db54",
}


@pytest.fixture
def pending(monkeypatch):
    """datasets.py as it stands before any fill, whatever the tree holds: every release identity None."""
    for prefix, names in fill.IDENTITIES.items():
        for key in names:
            monkeypatch.setattr(datasets, f"{prefix}_{key}", None)
    monkeypatch.setitem(datasets.DATASETS[BINDING], "local_area",
                        datasets.local_area_cut(None, None, None, None, "2.151.0", "built_with"))


def failing(manifest, name, local, regional_raw):
    return [label for label, pinned, got in fill.checks(manifest, datasets.DATASETS[name], local, regional_raw)
            if pinned != got]


@pytest.mark.parametrize("name", [BINDING, FALLBACK])
def test_a_release_carrying_the_pinned_pair_passes_every_check(pending, name):
    manifest, local, regional_raw = released(name)
    assert failing(manifest, name, local, regional_raw) == []


@pytest.mark.parametrize("name", [BINDING, FALLBACK])
def test_a_bundle_pin_certificate_like_6_11_0s_passes(pending, name):
    manifest, local, regional_raw = released(name)
    certificate = manifest["data_releases"]["uk"]["certification"]
    del certificate["certified_for_core_version"]
    certificate["core_binding"] = "bundle_pin"
    assert failing(manifest, name, local, regional_raw) == []


@pytest.mark.parametrize("name", [BINDING, FALLBACK])
@pytest.mark.parametrize("where,key,value,labels", [
    ("uk", "policyengine_version", "98.0.0", {"UK release carrier version"}),
    ("uk", "bundle_id", "uk-98.0.0", {"bundle id"}),
    ("core", "version", "3.33.0", {"core version", "core version certified for"}),
    ("certification", "certified_for_core_version", "3.33.0", {"core version certified for"}),
    ("model_package", "version", "2.153.4", {"model version"}),
    ("certification", "certified_for_model_version", "2.153.4", {"model version certified for"}),
    ("model_package", "sha256", "0" * 64, {"model wheel SHA-256"}),
    ("uk", "build_id", "other-cut", {"release build id"}),
    ("artifact", "build_id", "other-cut", {"artifact build id"}),
    ("uk", "release_manifest_uri", "https://example.com/other", {"release manifest URI"}),
    ("uk", "source_manifest_uri", "hf://other", {"source manifest URI"}),
    ("artifact", "dataset", "enhanced_frs_2024_25", {"artifact dataset"}),
    ("artifact", "sha256", "0" * 64, {"artifact SHA-256"}),
    ("artifact", "uri", "hf://policyengine/other/microcosm_uk_2024_25.h5@x", {"artifact URI"}),
    ("artifact", "data_package", {"name": "microcosm-data", "version": "0.2.0"}, {"artifact data package"}),
    # #715's national-only candidate routing, an area type left out or split, or an extra member, is not the pair.
    ("uk", "region_datasets", {"national": {"path_template": "microcosm_uk_2024_25.h5"}}, {"region routing"}),
    ("regions", "national", {"path_template": "other.h5"}, {"region routing"}),
    ("regions", "local_authority", {"path_template": "other_local_area.h5"}, {"region routing"}),
    ("regions", "constituency", {"path_template": ""}, {"region routing"}),
    ("regions", "constituency", {"path_template": "invented_local_area.h5", "extra": 1}, {"region routing"}),
    # The local-area cut as the bundle names it: the installed check refuses each one too.
    ("dense", "sha256", "0" * 64, {"local-area datasets entry", ROUTED}),
    ("dense", "revision", "other-cut", {"local-area datasets entry", ROUTED}),
    ("dense", "repo_id", "policyengine/other", {"local-area datasets entry", ROUTED}),
    ("dense", "repo_type", "model", {"local-area datasets entry", ROUTED}),
    ("uk", "regional_release_kind", "national", {"regional release kind", ROUTED}),
    ("uk", "regional_release_manifest_uri", "https://example.com/other", {"regional release manifest URI", ROUTED}),
    ("uk", "regional_source_manifest_uri", "hf://other", {"regional source manifest URI", ROUTED}),
    ("uk", "regional_source_manifest_sha256", "0" * 64, {"regional source manifest SHA-256", ROUTED}),
])
def test_each_pinned_identity_is_checked(pending, name, where, key, value, labels):
    manifest, local, regional_raw = released(name)
    release = manifest["data_releases"]["uk"]
    container = {"uk": release, "core": manifest["packages"]["policyengine-core"],
                 "certification": release["certification"], "model_package": release["model_package"],
                 "artifact": release["certified_data_artifact"], "regions": release["region_datasets"],
                 "dense": release["datasets"]["microcosm_uk_2024_25_dense"]}[where]
    container[key] = value
    assert labels <= set(failing(manifest, name, local, regional_raw))


@pytest.mark.parametrize("name", [BINDING, FALLBACK])
@pytest.mark.parametrize("change,label", [
    (lambda m: m["build"].update(cut_tag="other-cut"), "local-area cut tag"),
    (lambda m: m["build"]["built_with_model_package"].update(version="2.150.0"), "local-area build model"),
    (lambda m: m["build"]["built_with_core_package"].update(version="3.33.0"), "local-area build core"),
    (lambda m: m.update(dataset_role="default"), "local-area dataset role"),
    (lambda m: m["artifacts"]["microcosm_uk_2024_25_dense"].update(sha256="0" * 64), "local-area artifact"),
    (lambda m: m["artifacts"]["microcosm_uk_2024_25_dense"].update(kind="diagnostics"), "local-area artifact"),
    (lambda m: m["artifacts"].update(copy=dict(m["artifacts"]["microcosm_uk_2024_25_dense"])), "local-area artifact"),
])
def test_the_cut_s_own_release_manifest_is_checked(pending, name, change, label):
    """Each change also changes the bytes, so the pinned manifest SHA-256 refuses as well."""
    manifest, local, regional_raw = released(name)
    regional = json.loads(regional_raw)
    change(regional)
    assert {label, "local-area release manifest SHA-256"} <= set(
        failing(manifest, name, local, json.dumps(regional).encode()))


@pytest.mark.parametrize("name", [BINDING, FALLBACK])
def test_two_datasets_entries_for_the_local_area_file_refuse(pending, name):
    """The script and the installed check both refuse, even with both entries naming the pinned cut."""
    manifest, local, regional_raw = released(name)
    entries = manifest["data_releases"]["uk"]["datasets"]
    entries["duplicate_dense"] = dict(entries["microcosm_uk_2024_25_dense"])
    assert {"local-area datasets entry", ROUTED} <= set(failing(manifest, name, local, regional_raw))


def test_the_binding_pair_refuses_an_accepted_mismatch_block(pending):
    """Both halves of d2011's pair are on 2.151.0, so #699's mismatch record is not that pair."""
    manifest, local, regional_raw = released(BINDING)
    manifest["data_releases"]["uk"]["regional_certification"] = regional_certification(local, "2.151.0")
    assert {"regional certification", ROUTED} <= set(failing(manifest, BINDING, local, regional_raw))


@pytest.mark.parametrize("key,value", [
    ("compatibility_basis", "built_with"), ("certified_for_model_version", "2.151.0"),
    ("built_with_model_version", "2.151.0"), ("regional_manifest_uri", "hf://other"),
    ("regional_manifest_sha256", "0" * 64), ("area_receipts", "certified"), (None, None),
])
def test_the_fallback_needs_699_s_exact_mismatch_record(pending, key, value):
    manifest, local, regional_raw = released(FALLBACK)
    release = manifest["data_releases"]["uk"]
    if key is None:
        del release["regional_certification"]
    else:
        release["regional_certification"][key] = value
    assert {"regional certification", ROUTED} <= set(failing(manifest, FALLBACK, local, regional_raw))


def test_the_fallback_needs_the_regional_manifest_digest(pending):
    manifest, local, regional_raw = released(FALLBACK)
    del manifest["data_releases"]["uk"]["regional_source_manifest_sha256"]
    assert {"regional source manifest SHA-256", ROUTED} <= set(failing(manifest, FALLBACK, local, regional_raw))


@pytest.mark.parametrize("digest", [True, False])
def test_the_binding_digest_is_compared_where_the_release_records_it(pending, digest):
    """A 6.11.0-shaped release has no regional_source_manifest_sha256; #699's schema adds it."""
    manifest, local, regional_raw = released(BINDING)
    if digest:
        manifest["data_releases"]["uk"]["regional_source_manifest_sha256"] = local["manifest_sha256"]
    assert failing(manifest, BINDING, local, regional_raw) == []
    if digest:
        manifest["data_releases"]["uk"]["regional_source_manifest_sha256"] = "0" * 64
        assert {"regional source manifest SHA-256", ROUTED} <= set(failing(manifest, BINDING, local, regional_raw))


def test_identities_come_from_the_exact_bytes_the_merge_and_the_cut(pending):
    manifest, local, regional_raw = released(BINDING)
    raw = json.dumps(manifest).encode()
    assert fill.identities(raw, manifest, MERGED, "BINDING", regional_raw) == {
        "BUNDLE_VERSION": VERSION, "BUNDLE_MANIFEST_SHA256": hashlib.sha256(raw).hexdigest(),
        "CERTIFICATION_URL": MERGED["html_url"], "CERTIFICATION_COMMIT": MERGED["merge_commit_sha"],
        "LOCAL_AREA_PATH": local["path"], "LOCAL_AREA_REVISION": local["revision"],
        "LOCAL_AREA_SHA256": local["sha256"], "LOCAL_AREA_MANIFEST_SHA256": hashlib.sha256(regional_raw).hexdigest()}
    assert set(fill.identities(raw, manifest, MERGED, "FALLBACK", regional_raw)) == set(fill.BUNDLE_IDENTITIES)
    candidate = {**MERGED, "merged_at": None}
    assert fill.identities(raw, manifest, candidate, "BINDING", regional_raw)["CERTIFICATION_COMMIT"] is None


def written(manifest):
    """A manifest's bytes as the release workflow writes them (json.dumps, indent 2, sorted keys, final newline)."""
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def as_merged(manifest):
    """The manifest as the certifying merge left it, before the release workflow's version commit: each field that
    commit rewrites names the carrier OLD. Written out field by field, not derived from fill.as_released."""
    merged = deepcopy(manifest)
    merged["bundle_version"] = merged["policyengine_version"] = OLD
    merged["packages"]["policyengine"].update(version=OLD, install_requirement=f"policyengine=={OLD}")
    merged["citation"].update(title=f"PolicyEngine bundle {OLD}", version=OLD)
    for country, data_release in merged["data_releases"].items():
        data_release.update(policyengine_version=OLD, bundle_id=f"{country}-{OLD}")
    return merged


def upstream(name):
    raw = (UPSTREAM / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == UPSTREAM_SHA256[name]
    return raw


@pytest.mark.parametrize("merge,release,version", [("pr-704-merge-13192b52.json", "release-6.11.0.json", "6.11.0"),
                                                   ("pr-555-merge-37d25c42.json", "release-6.2.6.json", "6.2.6")])
def test_the_replayed_workflow_writes_each_real_release_s_exact_bytes(merge, release, version):
    """Differential: the script's replay against what policyengine.py's own release workflow wrote."""
    assert fill.manifest_text(fill.as_released(json.loads(upstream(merge)), version)) == upstream(release)


def test_a_real_certifier_whose_manifest_is_not_the_release_s_is_refused():
    """#555 (6.2.6's certifier) is an ancestor of 6.11.0, but 6.11.0's manifest is not its rewrite."""
    merged = json.loads(upstream("pr-555-merge-37d25c42.json"))
    assert fill.manifest_text(fill.as_released(merged, "6.11.0")) != upstream("release-6.11.0.json")


def test_a_real_release_with_an_old_version_source_uri_is_refused():
    """The review's input: a source URI naming the old carrier in the merge and the new one in the release passed
    the earlier string replacement. The workflow never rewrites a source URI, so it must be the merge's exactly."""
    merged = json.loads(upstream("pr-704-merge-13192b52.json"))
    release = json.loads(upstream("release-6.11.0.json"))
    assert fill.manifest_text(fill.as_released(merged, "6.11.0")) == written(release)
    merged["data_releases"]["us"]["source_manifest_uri"] = "hf://dataset/example/data@6.10.2/release_manifest.json"
    release["data_releases"]["us"]["source_manifest_uri"] = "hf://dataset/example/data@6.11.0/release_manifest.json"
    assert fill.manifest_text(fill.as_released(merged, "6.11.0")) != written(release)


NON_ASCII = "caf\u00e9 \u00a3 \u4e2d \U0001f600"


def test_non_ascii_text_is_written_escaped_as_the_workflow_writes_it():
    """json.dumps escapes non-ASCII by default, upstream and here, whether the merge's bytes were escaped or UTF-8."""
    release = json.loads(upstream("release-6.11.0.json"))
    release["data_releases"]["uk"]["note"] = NON_ASCII
    for ensure_ascii in (True, False):
        merged = json.loads(upstream("pr-704-merge-13192b52.json"))
        merged["data_releases"]["uk"]["note"] = NON_ASCII
        merged = json.loads(json.dumps(merged, ensure_ascii=ensure_ascii).encode("utf-8"))
        assert fill.manifest_text(fill.as_released(merged, "6.11.0")) == written(release)
    assert b"\\u00e9" in written(release) and NON_ASCII.encode("utf-8") not in written(release)


@pytest.mark.parametrize("entry", [None, "retired", ["uk"]])
def test_a_non_dict_data_release_is_left_as_the_workflow_leaves_it(pending, entry):
    """sync_bundle_versions rewrites only the dict entries of data_releases."""
    manifest = released(BINDING)[0]
    manifest["data_releases"]["xx"] = entry
    merged = as_merged({**manifest, "data_releases": {k: v for k, v in manifest["data_releases"].items() if k != "xx"}})
    merged["data_releases"]["xx"] = deepcopy(entry)
    assert fill.manifest_text(fill.as_released(merged, VERSION)) == written(manifest)


def test_the_synthetic_release_is_the_workflow_s_rewrite_of_its_merge(pending):
    for name in (BINDING, FALLBACK):
        manifest = released(name)[0]
        assert manifest["policyengine_version"] == VERSION and as_merged(manifest)["policyengine_version"] == OLD
        assert fill.manifest_text(fill.as_released(as_merged(manifest), VERSION)) == written(manifest)
        assert fill.manifest_text(fill.as_released(manifest, VERSION)) == written(manifest)
        # The workflow derives the whole citation and drops ``source``, whatever the merge wrote there.
        merged = as_merged(manifest)
        merged["citation"]["doi"], merged["source"] = "10.5281/zenodo.1", {"pull_request": 9999}
        assert fill.manifest_text(fill.as_released(merged, VERSION)) == written(manifest)


@pytest.mark.parametrize("in_merge,in_release", [
    (lambda m: m["data_releases"]["uk"]["certified_data_artifact"].update(sha256="0" * 64), None),
    (lambda m: m["data_releases"]["uk"].update(extra=None), None),
    (lambda m: m["data_releases"]["uk"]["region_datasets"].pop("constituency"), None),
    (lambda m: m["data_releases"]["uk"]["certification"].update(core_binding=1), None),
    (lambda m: m.update(schema_version=str(m["schema_version"])), None),
    (lambda m: m["packages"]["policyengine-uk"].update(version=OLD), None),
    (lambda m: m["packages"]["policyengine"].update(markers="python_version >= '3.13'"), None),
    # Strings naming the carrier outside the rewritten fields: old in the merge, new in the release.
    (lambda m: m["data_releases"]["uk"].update(source_manifest_uri=f"hf://dataset/example@{OLD}/manifest.json"),
     lambda m: m["data_releases"]["uk"].update(source_manifest_uri=f"hf://dataset/example@{VERSION}/manifest.json")),
    (lambda m: m["data_releases"]["us"].update(release_manifest_uri=f"https://example.com/{OLD}/manifest.json"),
     lambda m: m["data_releases"]["us"].update(release_manifest_uri=f"https://example.com/{VERSION}/manifest.json")),
    # Values Python compares equal whose bytes differ: the merge wrote 1, the release true.
    (lambda m: m["data_releases"]["uk"].update(flag=1), lambda m: m["data_releases"]["uk"].update(flag=True)),
])
def test_the_release_may_differ_from_the_merge_only_in_the_rewritten_fields(pending, in_merge, in_release):
    manifest = released(BINDING)[0]
    merged = as_merged(manifest)
    in_merge(merged)
    if in_release:
        in_release(manifest)
    assert fill.manifest_text(fill.as_released(merged, VERSION)) != written(manifest)


def test_the_workflow_derives_every_package_s_install_requirement(pending):
    """normalized_manifest rewrites each package's requirement from its name, version and markers."""
    manifest = released(BINDING)[0]
    markers = "python_version >= '3.13'"
    manifest["packages"]["policyengine-us"].update(markers=markers,
                                                   install_requirement=f"policyengine-us==2.2.1; {markers}")
    merged = as_merged(manifest)
    merged["packages"]["policyengine-us"]["install_requirement"] = "policyengine-us"
    merged["packages"]["policyengine-uk"]["install_requirement"] = "policyengine-uk>=2"
    assert fill.manifest_text(fill.as_released(merged, VERSION)) == written(manifest)


@pytest.mark.parametrize("field", ["bundle_version", "policyengine_version", "packages"])
def test_a_merge_missing_a_field_the_version_commit_needs_is_no_release(pending, field):
    """sync_bundle_versions exits 1 without bundle_version, policyengine_version or packages."""
    merged = as_merged(released(BINDING)[0])
    del merged[field]
    assert fill.as_released(merged, VERSION) is None


@pytest.mark.parametrize("merged", [None, [], {"policyengine_version": "6.2.6", "data_releases": {}},
                                    {"bundle_version": OLD, "policyengine_version": OLD, "packages": {}},
                                    {"bundle_version": OLD, "policyengine_version": OLD,
                                     "packages": {"policyengine": {"version": OLD}}}])
def test_a_merge_manifest_the_workflow_cannot_rewrite_is_no_release(merged):
    assert fill.as_released(merged, VERSION) is None


def hub(manifest, merged=None, status="ahead", pull_request=MERGED, tag_bytes=written):
    """gh api, answering only the reads a --release run should make: the manifest at the tag (as ``tag_bytes``
    writes it) and at the merge commit, the pull request, and the merge commit's comparison with the tag. Any other
    read fails."""
    merged = as_merged(manifest) if merged is None else merged
    encode = lambda raw: {"content": base64.b64encode(raw).decode()}
    commit = pull_request["merge_commit_sha"]
    answers = {f"repos/{fill.REPOSITORY}/contents/{fill.MANIFEST}?ref={VERSION}": encode(tag_bytes(manifest)),
               f"repos/{fill.REPOSITORY}/contents/{fill.MANIFEST}?ref={commit}": encode(written(merged)),
               f"repos/{fill.REPOSITORY}/pulls/9999": pull_request,
               f"repos/{fill.REPOSITORY}/compare/{commit}...{VERSION}": {"status": status}}
    return answers.__getitem__


@pytest.mark.parametrize("pull_request,status,merged,refusal", [
    (MERGED, "ahead", None, None),
    (MERGED, "identical", None, None),
    ({**MERGED, "merged_at": None}, "ahead", None, "certifying pull request merged"),
    (MERGED, "diverged", None, "merge commit is in the release"),
    (MERGED, "behind", None, "merge commit is in the release"),
    # A certifier that is an ancestor of the tag but whose manifest is not the release's (like 6.2.6's #555).
    (MERGED, "ahead", {"policyengine_version": "6.2.6", "data_releases": {}}, REWRITE),
])
def test_the_certifying_pull_request_merged_into_the_tag_with_its_manifest(pending, monkeypatch, pull_request, status,
                                                                         merged, refusal):
    manifest = released(BINDING)[0]
    monkeypatch.setattr(fill, "github", hub(manifest, merged, status, pull_request))
    failures = [label for label, pinned, got in fill.certifying_checks(pull_request, VERSION, written(manifest))
                if pinned != got]
    assert failures == ([refusal] if refusal else [])


@pytest.mark.parametrize("merge_value,release_value", [
    (f"hf://dataset/example@{OLD}/manifest.json", f"hf://dataset/example@{VERSION}/manifest.json"),
    (1, True),  # equal in Python, not in the bytes
])
def test_the_certifying_check_compares_the_tag_s_bytes(pending, monkeypatch, merge_value, release_value):
    manifest = released(BINDING)[0]
    merged = as_merged(manifest)
    merged["data_releases"]["uk"]["source_manifest_uri"] = merge_value
    manifest["data_releases"]["uk"]["source_manifest_uri"] = release_value
    monkeypatch.setattr(fill, "github", hub(manifest, merged))
    failures = [label for label, pinned, got in fill.certifying_checks(MERGED, VERSION, written(manifest))
                if pinned != got]
    assert failures == [REWRITE]


# Tags equal to the rewrite in content but not in bytes.
REFORMATTED = [lambda m: json.dumps(m).encode(), lambda m: written(m)[:-1],
               lambda m: json.dumps(m, indent=2, sort_keys=False).encode() + b"\n",
               lambda m: (json.dumps(m, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()]


@pytest.mark.parametrize("tag_bytes", REFORMATTED)
def test_the_certifying_check_refuses_a_tag_reformatted_from_the_rewrite(pending, monkeypatch, tag_bytes):
    manifest = released(BINDING)[0]
    manifest["data_releases"]["uk"]["note"] = NON_ASCII
    merged = as_merged(manifest)
    assert json.loads(tag_bytes(manifest)) == fill.as_released(merged, VERSION)
    assert tag_bytes(manifest) != written(manifest)
    monkeypatch.setattr(fill, "github", hub(manifest, merged))
    failures = [label for label, pinned, got in fill.certifying_checks(MERGED, VERSION, tag_bytes(manifest))
                if pinned != got]
    assert failures == [REWRITE]


def reset(root):
    """Copy the files the fill writes, with every release identity and the carrier back at their pending values."""
    for relative in ("src/triple_lock/datasets.py", "pyproject.toml", "requirements-lock.txt",
                     "data/binding-bridge.pending.json"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, root / relative)
    path = root / "src/triple_lock/datasets.py"
    text = path.read_text()
    for prefix, names in fill.IDENTITIES.items():
        for key in names:
            text, count = re.subn(rf"^{prefix}_{key} = .*$", f"{prefix}_{key} = None", text, flags=re.M)
            assert count == 1
    path.write_text(text)
    for path in (root / "pyproject.toml", root / "requirements-lock.txt"):
        text, count = re.subn(r'^(\s*"?policyengine==)[0-9][^",\s]*', rf"\g<1>{datasets.PREPARATORY_CARRIER}",
                              path.read_text(), flags=re.M)
        assert count == 1
        path.write_text(text)
    return root


@pytest.fixture
def tree(tmp_path):
    """A pending copy of the tree, so the real one is never touched and its fill state does not matter."""
    return reset(tmp_path / "tree")


def values(prefix="BINDING"):
    manifest, _, regional_raw = released(BINDING)
    return fill.identities(json.dumps(manifest).encode(), manifest, MERGED, prefix, regional_raw)


def assignments(text, prefix):
    return {name: line.split(" = ", 1)[1] for line in text.splitlines()
            for name in fill.IDENTITIES[prefix] if line.startswith(f"{prefix}_{name} = ")}


def files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_the_binding_fill_writes_every_pin_and_a_ready_bridge(pending, tree):
    filled = values()
    fill.fill(tree, "BINDING", filled, MERGED["head"]["sha"])
    text = (tree / "src/triple_lock/datasets.py").read_text()
    assert assignments(text, "BINDING") == {name: json.dumps(filled[name]) for name in fill.IDENTITIES["BINDING"]}
    assert set(assignments(text, "FALLBACK").values()) == {"None"}
    assert f'"policyengine=={VERSION}",' in (tree / "pyproject.toml").read_text()
    assert f"\npolicyengine=={VERSION}\n" in (tree / "requirements-lock.txt").read_text()
    pending_bridge = json.loads((REPO / "data/binding-bridge.pending.json").read_text())
    assert json.loads((tree / "data/binding-bridge.pending.json").read_text()) == pending_bridge
    ready = json.loads((tree / "data/binding-bridge.json").read_text())
    binding_bridge.validate_configuration(ready)
    assert ready["pending_release"] == {**pending_bridge["pending_release"], "pull_request": MERGED["html_url"],
                                        "reviewed_head": MERGED["head"]["sha"], "policyengine_version": VERSION,
                                        "bundle_manifest_sha256": filled["BUNDLE_MANIFEST_SHA256"]}
    # Only the three carrier pins and the status change: model, core and dataset pins stay exactly as reviewed.
    expected = deepcopy(pending_bridge)
    expected["status"] = "ready"
    expected["pending_release"] = ready["pending_release"]
    for step, endpoint in (("model", "to"), ("data", "from"), ("data", "to")):
        expected["steps"][step][endpoint]["packages"]["policyengine"] = VERSION
    assert ready == expected


def test_the_fallback_fill_writes_only_its_own_identities(pending, tree):
    before = files(tree)
    fill.fill(tree, "FALLBACK", values("FALLBACK"), MERGED["head"]["sha"])
    text = (tree / "src/triple_lock/datasets.py").read_text()
    assert "None" not in set(assignments(text, "FALLBACK").values())
    assert set(assignments(text, "BINDING").values()) == {"None"}
    assert {path for path, raw in files(tree).items() if before.get(path) != raw} == {"src/triple_lock/datasets.py"}


def test_a_value_is_written_as_itself_never_as_a_template(pending, tree):
    """A backslash in a value is not a regex back-reference."""
    url = r"https://github.com/PolicyEngine/policyengine.py/pull/9999\1\g<0>"
    fill.fill(tree, "BINDING", {**values(), "CERTIFICATION_URL": url}, MERGED["head"]["sha"])
    assert f"BINDING_CERTIFICATION_URL = {json.dumps(url)}\n" in (tree / "src/triple_lock/datasets.py").read_text()


@pytest.mark.parametrize("missing", ["CERTIFICATION_COMMIT", "LOCAL_AREA_REVISION", "LOCAL_AREA_MANIFEST_SHA256"])
def test_a_value_the_release_does_not_supply_writes_nothing(pending, tree, missing):
    before = files(tree)
    with pytest.raises(ValueError, match=missing):
        fill.fill(tree, "BINDING", {**values(), missing: None}, MERGED["head"]["sha"])
    assert files(tree) == before


@pytest.mark.parametrize("break_tree", [
    # A pending endpoint that already names a carrier, found after datasets.py and both pins were built.
    lambda root: (root / "data/binding-bridge.pending.json").write_text(
        (root / "data/binding-bridge.pending.json").read_text().replace('"policyengine": null', '"policyengine": "1"', 1)),
    # No exact carrier pin to replace, found after datasets.py was built.
    lambda root: (root / "pyproject.toml").write_text(
        (root / "pyproject.toml").read_text().replace("policyengine==", "policyengine>=")),
])
def test_a_refusal_found_late_still_writes_nothing(pending, tree, break_tree):
    break_tree(tree)
    before = files(tree)
    with pytest.raises(ValueError, match="nothing is written"):
        fill.fill(tree, "BINDING", values(), MERGED["head"]["sha"])
    assert files(tree) == before


def run_release(monkeypatch, tree, manifest, regional_raw, *arguments, merged=None, tag_bytes=written):
    """main() in --release mode against the fake GitHub and Hub; the Hub read must be at the cut's own tag."""
    monkeypatch.setattr(fill, "github", hub(manifest, merged, tag_bytes=tag_bytes))
    monkeypatch.setattr(fill, "ROOT", tree)
    cut_tag = json.loads(regional_raw)["build"]["cut_tag"]
    monkeypatch.setattr(fill, "hub_file", lambda local: regional_raw if local["revision"] == cut_tag
                        else pytest.fail(f"read the cut's manifest at {local['revision']}"))
    return fill.main(["--pr", "9999", "--release", VERSION, *arguments])


def test_the_release_path_reads_the_tag_and_applies_the_binding_pair(pending, tree, monkeypatch):
    manifest, local, regional_raw = released(BINDING)
    assert run_release(monkeypatch, tree, manifest, regional_raw, "--apply") == 0
    filled = assignments((tree / "src/triple_lock/datasets.py").read_text(), "BINDING")
    assert filled["LOCAL_AREA_REVISION"] == json.dumps(local["revision"])
    assert filled["LOCAL_AREA_MANIFEST_SHA256"] == json.dumps(local["manifest_sha256"])
    assert filled["CERTIFICATION_COMMIT"] == json.dumps(MERGED["merge_commit_sha"])
    assert (tree / "data/binding-bridge.json").exists()


def test_the_release_path_applies_the_pinned_fallback_cut(pending, tree, monkeypatch):
    manifest, local, regional_raw = released(FALLBACK)
    monkeypatch.setitem(datasets.DATASETS[FALLBACK], "local_area", local)
    assert run_release(monkeypatch, tree, manifest, regional_raw, "--target", "fallback", "--apply") == 0
    assert "None" not in assignments((tree / "src/triple_lock/datasets.py").read_text(), "FALLBACK").values()
    assert not (tree / "data/binding-bridge.json").exists()


def test_the_release_path_refuses_a_tag_naming_another_carrier(pending, monkeypatch):
    manifest = released(BINDING, version="98.5.0")[0]
    monkeypatch.setattr(fill, "github", lambda path: {"content": base64.b64encode(json.dumps(manifest).encode())})
    with pytest.raises(SystemExit, match="names policyengine 98.5.0"):
        fill.main(["--pr", "9999", "--release", VERSION])


@pytest.mark.parametrize("change", [
    lambda manifest: manifest["data_releases"]["uk"]["certified_data_artifact"].update(sha256="0" * 64),
    lambda manifest: manifest["data_releases"]["uk"].update(regional_certification={"compatibility_basis": "x"}),
])
def test_main_refuses_a_differing_release_before_writing(pending, tree, monkeypatch, capsys, change):
    manifest, _, regional_raw = released(BINDING)
    change(manifest)
    before = files(tree)
    assert run_release(monkeypatch, tree, manifest, regional_raw, "--apply") == 1
    assert files(tree) == before
    assert "refused" in capsys.readouterr().err


def test_main_refuses_a_release_that_is_not_the_certifying_merge(pending, tree, monkeypatch, capsys):
    manifest, _, regional_raw = released(BINDING)
    merged = as_merged(manifest)
    merged["data_releases"]["uk"]["certified_data_artifact"]["sha256"] = "0" * 64
    before = files(tree)
    assert run_release(monkeypatch, tree, manifest, regional_raw, "--apply", merged=merged) == 1
    assert files(tree) == before
    assert f"FAIL {REWRITE}" in capsys.readouterr().out


@pytest.mark.parametrize("tag_bytes", REFORMATTED)
def test_main_compares_the_tag_s_own_bytes(pending, tree, monkeypatch, capsys, tag_bytes):
    """The tag's bytes, not a re-serialization of them, must be the workflow's."""
    manifest, _, regional_raw = released(BINDING)
    manifest["data_releases"]["uk"]["note"] = NON_ASCII
    before = files(tree)
    assert run_release(monkeypatch, tree, manifest, regional_raw, "--apply", tag_bytes=tag_bytes) == 1
    assert files(tree) == before
    assert f"FAIL {REWRITE}" in capsys.readouterr().out
    assert run_release(monkeypatch, tree, manifest, regional_raw) == 0


def test_the_binding_pair_refuses_a_local_area_cut_built_on_another_model(pending, tree, monkeypatch, capsys):
    """The review's failing input: a6299504 released with a cut shaped like the 19 October one (built on 2.132.6)."""
    other = datasets.local_area_cut(INVENTED_CUT["path"], "dense-cut-built-on-2.132.6", "e" * 64, None, "2.132.6",
                                    "built_with")
    manifest, _, regional_raw = released(BINDING, local=other)
    assert run_release(monkeypatch, tree, manifest, regional_raw) == 1
    assert "FAIL local-area build model" in capsys.readouterr().out
    manifest["data_releases"]["uk"]["regional_certification"] = regional_certification(other, "2.151.0")
    assert run_release(monkeypatch, tree, manifest, regional_raw) == 1
    assert "FAIL regional certification" in capsys.readouterr().out


def test_apply_needs_the_release_path(pending, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(released(BINDING)[0]))
    with pytest.raises(SystemExit) as refusal:
        fill.main(["--pr", "9999", "--manifest", str(path), "--apply"])
    assert refusal.value.code == 2


def test_a_rerun_checks_the_identities_already_filled(pending, tmp_path, monkeypatch, capsys):
    manifest, local, regional_raw = released(BINDING)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    regional = tmp_path / "regional.json"
    regional.write_bytes(regional_raw)
    filled = fill.identities(path.read_bytes(), manifest, MERGED, "BINDING", regional_raw)
    monkeypatch.setattr(fill, "github", {f"repos/{fill.REPOSITORY}/pulls/9999": MERGED}.__getitem__)
    for key, value in filled.items():
        monkeypatch.setattr(datasets, f"BINDING_{key}", value)
    monkeypatch.setitem(datasets.DATASETS[BINDING], "local_area", local)
    arguments = ["--pr", "9999", "--manifest", str(path), "--regional-manifest", str(regional)]
    assert fill.main(arguments) == 0
    assert capsys.readouterr().out.count("ok   filled BINDING_") == len(fill.IDENTITIES["BINDING"])
    # Installed bytes that differ from the pinned digest refuse.
    path.write_text(json.dumps(manifest, indent=1))
    assert fill.main(arguments) == 1
    assert "FAIL filled BINDING_BUNDLE_MANIFEST_SHA256" in capsys.readouterr().out
