"""Check a policyengine.py release against d2011's pinned pair, then fill the identities only it can supply.

    .venv/bin/python scripts/fill_release_identities.py --pr N --release TAG [--target fallback] [--apply]
    .venv/bin/python scripts/fill_release_identities.py --pr N --manifest FILE [--target fallback]

The UK bundle manifest is read at the release tag (the release workflow's version commit rewrites it after the
certifying merge, so the merge commit's bytes are not the release's), or from ``--manifest FILE``, such as the
installed wheel's. Every identity datasets.py already pins is compared the way
``datasets._certified_by_installed_bundle`` will compare the installed release: carrier version, model and core
versions, model wheel SHA-256, build id, release and source manifest URIs, the certified artifact, region routing
(national to the pinned file; constituency and local authority to the local-area file) and the local-area cut.

The local-area cut's own release manifest is read at its tag on the Hub (``HUGGING_FACE_TOKEN``), or from
``--regional-manifest FILE``. Its build must name the cut's tag and have run the cut's model (2.151.0 for the
binding pair, whose bundle must carry no ``regional_certification``; 2.132.6 for the fallback, on #699's accepted
mismatch) on core 3.33.3, and its local-area artifact must be the file the bundle routes to. The fallback's cut is
pinned already; the binding cut's file, tag, SHA-256 and manifest SHA-256 come from the release and are filled.

With ``--release``, the certifying pull request must be merged, its merge commit must be in the tag, and the tag's
manifest must be, byte for byte, what the release workflow writes from the merge commit's: the carrier version
fields, each country's bundle id, the install requirements and the citation are rewritten and ``source`` is dropped;
nothing else changes. The release is then exactly what the certifying review merged. Any difference exits 1 before
anything is written.

``--apply`` (with ``--release`` only) writes the target's identities: carrier version, manifest SHA-256, certifying
pull request and merge commit, and for the binding target its local-area cut. The binding target also writes the
carrier pin in pyproject.toml and requirements-lock.txt and data/binding-bridge.json, the pending configuration
filled and marked ready. The fallback target writes only its datasets identities: its model pin, primary and bridge
endpoints move in their own reviewed commit. Every file is checked before any is written. Nothing is installed and
no data is loaded. Afterwards: re-resolve the lock for the new carrier, install it, rerun this with ``--manifest``
on the installed wheel's manifest, and run check_upstream(), both preflights and the bridge's --validate-only.
"""

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
REPOSITORY = "PolicyEngine/policyengine.py"
MANIFEST = "src/policyengine/data/bundle/manifest.json"
TARGETS = {"binding": ("microcosm_uk_2024_25@a6299504", "BINDING"),
           "fallback": ("microcosm_uk_2024_25@a133f37a", "FALLBACK")}
BUNDLE_IDENTITIES = ("BUNDLE_VERSION", "BUNDLE_MANIFEST_SHA256", "CERTIFICATION_URL", "CERTIFICATION_COMMIT")
LOCAL_AREA_IDENTITIES = ("LOCAL_AREA_PATH", "LOCAL_AREA_REVISION", "LOCAL_AREA_SHA256", "LOCAL_AREA_MANIFEST_SHA256")
IDENTITIES = {"BINDING": BUNDLE_IDENTITIES + LOCAL_AREA_IDENTITIES, "FALLBACK": BUNDLE_IDENTITIES}
LOCAL_AREA_ROLE = "non_default_local_area"


def github(path):
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def github_file(path, ref):
    """A file's exact bytes at a ref of policyengine.py."""
    return base64.b64decode(github(f"repos/{REPOSITORY}/contents/{path}?ref={ref}")["content"])


def hub_file(local):
    """The local-area cut's release manifest, at the cut's own tag."""
    from huggingface_hub import hf_hub_download
    from triple_lock.datasets import LOCAL_AREA_RELEASE_MANIFEST

    return Path(hf_hub_download(local["repo_id"], LOCAL_AREA_RELEASE_MANIFEST, revision=local["revision"],
                                repo_type=local["repo_type"], token=os.environ.get("HUGGING_FACE_TOKEN"))).read_bytes()


def local_area_entry(release, path):
    """The release's one datasets entry for the local-area file ({} unless exactly one names it)."""
    entries = [entry for entry in release.get("datasets", {}).values()
               if isinstance(entry, dict) and entry.get("path") == path]
    return entries[0] if len(entries) == 1 else {}


def released_local_area(release):
    """The local-area file the release routes constituency runs to, with its tag and SHA-256."""
    path = (release["region_datasets"].get("constituency") or {}).get("path_template")
    entry = local_area_entry(release, path)
    return {"LOCAL_AREA_PATH": path, "LOCAL_AREA_REVISION": entry.get("revision"),
            "LOCAL_AREA_SHA256": entry.get("sha256")}


def checks(manifest, spec, local, regional_raw):
    """[(label, pinned, released)] for every identity the registry pins, and for the local-area cut ``local`` (the
    pinned cut, or for a pending binding cut the one the release names) against its own release manifest's bytes."""
    from triple_lock.datasets import _local_area_routed, area_routed, certified_core

    certification = spec["bundle_certification"]
    release = manifest["data_releases"]["uk"]
    artifact = release["certified_data_artifact"]
    version = manifest["policyengine_version"]
    model = certification["model_version"]
    entry = local_area_entry(release, local["path"])
    regional = json.loads(regional_raw)
    build = regional.get("build", {})
    cut_artifacts = [item for item in regional.get("artifacts", {}).values()
                     if isinstance(item, dict) and item.get("path") == local["path"]]
    certificate = release.get("regional_certification")
    if local["model_basis"] == "built_with":
        pinned_certificate = None  # both halves on the pair's own model
    else:  # policyengine.py #699's record of the reviewed mismatch
        pinned_certificate = {"compatibility_basis": local["model_basis"], "certified_for_model_version": model,
                              "built_with_model_version": local["built_with_model_version"],
                              "regional_manifest_uri": local["source_manifest_uri"],
                              "regional_manifest_sha256": local["manifest_sha256"], "area_receipts": "uncertified"}
        if isinstance(certificate, dict):
            certificate = {key: certificate.get(key) for key in pinned_certificate}
    return [
        ("UK release carrier version", version, release["policyengine_version"]),
        ("bundle id", f"uk-{version}", release["bundle_id"]),
        ("core version", certification["core_version"], manifest["packages"]["policyengine-core"]["version"]),
        ("core version certified for", certification["core_version"], certified_core(manifest)),
        ("model version", model, release["model_package"]["version"]),
        ("model version certified for", model, release["certification"]["certified_for_model_version"]),
        ("model wheel SHA-256", certification["model_wheel_sha256"], release["model_package"]["sha256"]),
        ("release build id", spec["build_id"], release["build_id"]),
        ("artifact build id", spec["build_id"], artifact["build_id"]),
        ("release manifest URI", spec["release_manifest"]["uri"], release["release_manifest_uri"]),
        ("source manifest URI", spec["release_manifest"]["source_uri"], release["source_manifest_uri"]),
        ("artifact dataset", spec["logical_name"], artifact["dataset"]),
        ("artifact SHA-256", spec["sha256"], artifact["sha256"]),
        ("artifact URI", f"hf://{spec['repo_id']}/{spec['path']}@{spec['revision']}", artifact["uri"]),
        ("artifact data package", {"name": spec["data_package"], "version": spec["data_version"]},
         artifact["data_package"]),
        # Exactly what the installed check compares: national to the pinned file, both area types to one file.
        ("region routing", area_routed(local["path"]), release["region_datasets"]),
        ("local-area datasets entry", {key: local[key] for key in ("repo_id", "repo_type", "revision", "sha256")},
         {key: entry.get(key, local["repo_type"] if key == "repo_type" else None)
          for key in ("repo_id", "repo_type", "revision", "sha256")}),
        ("regional release kind", "local_area", release.get("regional_release_kind")),
        ("regional release manifest URI", local["release_manifest_uri"], release.get("regional_release_manifest_uri")),
        ("regional source manifest URI", local["source_manifest_uri"], release.get("regional_source_manifest_uri")),
        ("regional source manifest SHA-256", local["manifest_sha256"],
         release.get("regional_source_manifest_sha256", None if pinned_certificate else local["manifest_sha256"])),
        ("regional certification", pinned_certificate, certificate),
        ("local-area release manifest SHA-256", local["manifest_sha256"], hashlib.sha256(regional_raw).hexdigest()),
        ("local-area cut tag", local["revision"], build.get("cut_tag")),
        ("local-area build model", local["built_with_model_version"],
         build.get("built_with_model_package", {}).get("version")),
        ("local-area build core", certification["core_version"],
         build.get("built_with_core_package", {}).get("version")),
        ("local-area dataset role", LOCAL_AREA_ROLE, regional.get("dataset_role")),
        ("local-area artifact", [{"kind": "microdata", "path": local["path"], "repo_id": local["repo_id"],
                                  "revision": local["revision"], "sha256": local["sha256"]}],
         [{key: item.get(key) for key in ("kind", "path", "repo_id", "revision", "sha256")}
          for item in cut_artifacts]),
        # The function provenance calls, so the script and the installed check cannot disagree.
        ("installed check routes to this cut", True, _local_area_routed(release, local, model)),
    ]


def as_released(merged, version):
    """The manifest the release workflow writes for ``version`` from the certifying merge's ``merged``, as at
    policyengine.py 6.11.0: .github/bump_version.py's sync_bundle_versions (the carrier version fields, each country's
    bundle id), then scripts/generate_bundle_artifacts.py's normalized_manifest (each package's install requirement,
    the citation, no ``source``). Nothing else is rewritten. None where sync_bundle_versions or normalized_manifest
    would fail on ``merged``'s structure; the workflow's validation and pre-versioning checks are not replayed, since
    the tag must equal this rewrite in any case."""
    if not (isinstance(merged, dict) and {"bundle_version", "policyengine_version", "packages"} <= merged.keys()):
        return None
    released = deepcopy(merged)
    try:
        released["bundle_version"] = released["policyengine_version"] = version
        released["packages"]["policyengine"]["version"] = version
        for country, data_release in released.get("data_releases", {}).items():
            if isinstance(data_release, dict):
                data_release.update(policyengine_version=version, bundle_id=f"{country}-{version}")
        for package in released["packages"].values():
            package["install_requirement"] = (f"{package['name']}=={package['version']}"
                                              + (f"; {package['markers']}" if package.get("markers") else ""))
    except (AttributeError, KeyError, TypeError):
        return None
    released.pop("source", None)
    released["citation"] = {"title": f"PolicyEngine bundle {version}", "version": version, "type": "software-bundle",
                            "publisher": "PolicyEngine"}
    return released


def manifest_text(manifest):
    """The bytes the release workflow writes for a manifest."""
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def certifying_checks(pull_request, tag, raw):
    """[(label, pinned, released)]: the pull request merged, into this tag, whose manifest bytes ``raw`` are exactly
    what the release workflow writes from the merge's."""
    commit = pull_request.get("merge_commit_sha") if pull_request.get("merged_at") else None
    rows = [("certifying pull request merged", True, commit is not None)]
    if commit is None:
        return rows
    status = github(f"repos/{REPOSITORY}/compare/{commit}...{tag}")["status"]
    expected = as_released(json.loads(github_file(MANIFEST, commit)), json.loads(raw)["policyengine_version"])
    return rows + [
        ("merge commit is in the release", True, status in ("ahead", "identical")),
        ("release manifest is the workflow's rewrite of the merge's", True,
         expected is not None and manifest_text(expected) == raw),
    ]


def identities(raw, manifest, pull_request, prefix, regional_raw):
    """The values only the release supplies, from the manifest's exact bytes, the pull request and (binding) the
    local-area cut it names. An unmerged pull request has no certifying commit (None), so its values can be
    printed but never applied."""
    values = {"BUNDLE_VERSION": manifest["policyengine_version"],
              "BUNDLE_MANIFEST_SHA256": hashlib.sha256(raw).hexdigest(),
              "CERTIFICATION_URL": pull_request["html_url"],
              "CERTIFICATION_COMMIT": pull_request["merge_commit_sha"] if pull_request.get("merged_at") else None}
    if prefix == "BINDING":
        values.update(released_local_area(manifest["data_releases"]["uk"]),
                      LOCAL_AREA_MANIFEST_SHA256=hashlib.sha256(regional_raw).hexdigest())
    return values


def _replace_once(text, pattern, replacement, where):
    """``replacement`` is a function of the match, so no value is read as a template."""
    text, count = re.subn(pattern, replacement, text, flags=re.M)
    if count != 1:
        raise ValueError(f"{where}: expected exactly one match for {pattern!r}: nothing is written")
    return text


def fill(root, prefix, values, reviewed_head):
    """Write the identities; the binding target also writes its carrier pins and the ready bridge configuration.
    Every file is built and checked first, so a refusal writes nothing."""
    missing = [name for name in IDENTITIES[prefix] if not values.get(name)]
    if missing:
        raise ValueError(f"the release does not supply {missing}: nothing is written")
    path = root / "src/triple_lock/datasets.py"
    text = path.read_text()
    for name in IDENTITIES[prefix]:
        assignment = f"{prefix}_{name} = {json.dumps(values[name])}"
        text = _replace_once(text, rf"^{prefix}_{name} = None$", lambda _, line=assignment: line, path)
    writes = {path: text}
    if prefix == "BINDING":
        version = values["BUNDLE_VERSION"]
        for path in (root / "pyproject.toml", root / "requirements-lock.txt"):
            writes[path] = _replace_once(path.read_text(), r'^(\s*"?policyengine==)[0-9][^",\s]*',
                                         lambda match: match.group(1) + version, path)
        configuration = json.loads((root / "data/binding-bridge.pending.json").read_text())
        for step, endpoint in (("model", "to"), ("data", "from"), ("data", "to")):
            packages = configuration["steps"][step][endpoint]["packages"]
            if packages["policyengine"] is not None:
                raise ValueError(f"the pending {step}/{endpoint} endpoint already names a carrier: nothing is written")
            packages["policyengine"] = version
        configuration["status"] = "ready"
        configuration["pending_release"].update(
            pull_request=values["CERTIFICATION_URL"], reviewed_head=reviewed_head, policyengine_version=version,
            bundle_manifest_sha256=values["BUNDLE_MANIFEST_SHA256"])
        writes[root / "data/binding-bridge.json"] = json.dumps(configuration, indent=2) + "\n"
    for path, text in writes.items():
        path.write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pr", type=int, required=True, help="the merged policyengine.py PR certifying the pair")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release", help="the policyengine.py release tag carrying it")
    source.add_argument("--manifest", type=Path, help="that release's manifest file, e.g. the installed wheel's")
    parser.add_argument("--regional-manifest", type=Path,
                        help="the local-area cut's release_manifest.json (default: read it at the cut's tag)")
    parser.add_argument("--target", choices=sorted(TARGETS), default="binding")
    parser.add_argument("--apply", action="store_true",
                        help="with --release: write the identities once every check passes")
    args = parser.parse_args(argv)
    if args.apply and not args.release:
        parser.error("--apply needs --release: only the tag's checks authenticate what it writes")

    from triple_lock import datasets

    name, prefix = TARGETS[args.target]
    spec = datasets.DATASETS[name]
    raw = args.manifest.read_bytes() if args.manifest else github_file(MANIFEST, args.release)
    manifest = json.loads(raw)
    if args.release and manifest["policyengine_version"] != args.release:
        raise SystemExit(f"release {args.release}'s manifest names policyengine {manifest['policyengine_version']}")
    local = spec["local_area"]
    if any(local[key] is None for key in ("path", "revision", "sha256", "manifest_sha256")):
        # The binding cut, pending: check the one the release names, with its release manifest's digest.
        supplied = released_local_area(manifest["data_releases"]["uk"])
        local = datasets.local_area_cut(supplied["LOCAL_AREA_PATH"], supplied["LOCAL_AREA_REVISION"],
                                        supplied["LOCAL_AREA_SHA256"], None, local["built_with_model_version"],
                                        local["model_basis"])
        if local["revision"] is None and not args.regional_manifest:
            raise SystemExit("refused: the release names no single local-area datasets entry to read the cut from")
    regional_raw = args.regional_manifest.read_bytes() if args.regional_manifest else hub_file(local)
    if local["manifest_sha256"] is None:
        local["manifest_sha256"] = hashlib.sha256(regional_raw).hexdigest()
    rows = checks(manifest, spec, local, regional_raw)
    pull_request = github(f"repos/{REPOSITORY}/pulls/{args.pr}")
    if args.release:
        rows += certifying_checks(pull_request, args.release, raw)
    values = identities(raw, manifest, pull_request, prefix, regional_raw)
    # Identities already filled (a rerun on the installed wheel's manifest) must equal what this release supplies.
    rows += [(f"filled {prefix}_{key}", getattr(datasets, f"{prefix}_{key}"), value) for key, value in values.items()
             if getattr(datasets, f"{prefix}_{key}") is not None]
    width = max(len(label) for label, _, _ in rows)
    for label, pinned, released in rows:
        print(f"{'ok  ' if pinned == released else 'FAIL'} {label:<{width}}  {json.dumps(released)}"
              + ("" if pinned == released else f"  (pinned {json.dumps(pinned)})"))
    print(json.dumps({"dataset": name, **{f"{prefix}_{key}": value for key, value in values.items()},
                      "reviewed_head": pull_request["head"]["sha"]}, indent=2))
    if any(pinned != released for _, pinned, released in rows):
        print(f"refused: the release differs from the pinned {name} pair", file=sys.stderr)
        return 1
    if args.apply:
        if any(label.startswith("filled ") for label, _, _ in rows):
            raise SystemExit(f"{prefix} identities are already filled: rerun without --apply to check them")
        fill(ROOT, prefix, values, pull_request["head"]["sha"])
        print("applied: review the diff; re-resolve requirements-lock.txt for the new carrier (docs/REBUILD.md); "
              "install it; rerun this with --manifest on the installed wheel's manifest; run check_upstream(), "
              "both preflights and the bridge's --validate-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
