"""Check a policyengine.py release against d2011's pinned pair, then fill the identities only it can supply.

    .venv/bin/python scripts/fill_release_identities.py --pr N --release TAG [--target fallback] [--apply]

The UK bundle manifest is read at the release tag (the release workflow's version commit rewrites it after the
certifying merge, so the merge commit's bytes are not the release's), or from ``--manifest FILE``, such as the
installed wheel's. Every identity datasets.py already pins is compared the way
``datasets._certified_by_installed_bundle`` will compare the installed release: carrier version, model and core
versions, model wheel SHA-256, build id, release and source manifest URIs, the certified artifact, and region
routing (national to the pinned file; constituency and local authority to one local-area file). Any difference
exits 1 before anything is written.

``--apply`` writes the target's five ``datasets`` identities (carrier version, manifest SHA-256, certifying pull
request and merge commit, local-area file). For the binding target it also writes the carrier pin in
pyproject.toml and requirements-lock.txt and data/binding-bridge.json, the pending configuration filled and
marked ready. The fallback target writes only its datasets identities: its model pin, primary and bridge
endpoints move in their own reviewed commit. Nothing is installed and no data is loaded. The installed release
must still pass check_upstream(), both preflights and the bridge's --validate-only.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
REPOSITORY = "PolicyEngine/policyengine.py"
MANIFEST = "src/policyengine/data/bundle/manifest.json"
LOCAL_AREA_REGIONS = ("constituency", "local_authority")
TARGETS = {"binding": ("microcosm_uk_2024_25@a6299504", "BINDING"),
           "fallback": ("microcosm_uk_2024_25@a133f37a", "FALLBACK")}
IDENTITIES = ("BUNDLE_VERSION", "BUNDLE_MANIFEST_SHA256", "CERTIFICATION_URL", "CERTIFICATION_COMMIT",
              "LOCAL_AREA_PATH")


def github(path):
    return json.loads(subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout)


def checks(manifest, spec):
    """[(label, pinned, released)] for every identity the registry already pins."""
    from triple_lock.datasets import certified_core

    certification = spec["bundle_certification"]
    release = manifest["data_releases"]["uk"]
    artifact = release["certified_data_artifact"]
    version = manifest["policyengine_version"]
    regions = release["region_datasets"]
    local = {(regions.get(area) or {}).get("path_template") for area in LOCAL_AREA_REGIONS}
    return [
        ("UK release carrier version", version, release["policyengine_version"]),
        ("bundle id", f"uk-{version}", release["bundle_id"]),
        ("core version", certification["core_version"], manifest["packages"]["policyengine-core"]["version"]),
        ("core version certified for", certification["core_version"], certified_core(manifest)),
        ("model version", certification["model_version"], release["model_package"]["version"]),
        ("model version certified for", certification["model_version"],
         release["certification"]["certified_for_model_version"]),
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
        ("routed regions", ["constituency", "local_authority", "national"], sorted(regions)),
        ("national file", {"path_template": spec["path"]}, regions.get("national")),
        ("one local-area file for both area types", True, len(local) == 1 and bool(next(iter(local)))),
    ]


def identities(raw, manifest, pull_request):
    """The five values only the release supplies, from the manifest's exact bytes and the pull request. An unmerged
    pull request has no certifying commit (None), so its values can be printed but never applied."""
    regions = manifest["data_releases"]["uk"]["region_datasets"]
    return {"BUNDLE_VERSION": manifest["policyengine_version"],
            "BUNDLE_MANIFEST_SHA256": hashlib.sha256(raw).hexdigest(),
            "CERTIFICATION_URL": pull_request["html_url"],
            "CERTIFICATION_COMMIT": pull_request["merge_commit_sha"] if pull_request.get("merged_at") else None,
            "LOCAL_AREA_PATH": (regions.get("constituency") or {}).get("path_template")}


def _replace_once(text, pattern, replacement, where):
    text, count = re.subn(pattern, replacement, text, flags=re.M)
    if count != 1:
        raise ValueError(f"{where}: expected exactly one match for {pattern!r}")
    return text


def fill(root, prefix, values, reviewed_head):
    """Write the identities; the binding target also writes its carrier pins and the ready bridge configuration."""
    missing = [name for name in IDENTITIES if not values.get(name)]
    if missing:
        raise ValueError(f"the release does not supply {missing}: nothing is written")
    path = root / "src/triple_lock/datasets.py"
    text = path.read_text()
    for name in IDENTITIES:
        text = _replace_once(text, rf"^{prefix}_{name} = None$", f"{prefix}_{name} = {json.dumps(values[name])}",
                             path)
    path.write_text(text)
    if prefix != "BINDING":
        return
    version = values["BUNDLE_VERSION"]
    for path in (root / "pyproject.toml", root / "requirements-lock.txt"):
        path.write_text(_replace_once(path.read_text(), r'^(\s*"?policyengine==)[0-9][^",\s]*', rf"\g<1>{version}",
                                      path))
    configuration = json.loads((root / "data/binding-bridge.pending.json").read_text())
    for step, endpoint in (("model", "to"), ("data", "from"), ("data", "to")):
        packages = configuration["steps"][step][endpoint]["packages"]
        if packages["policyengine"] is not None:
            raise ValueError(f"the pending {step}/{endpoint} endpoint already names a carrier")
        packages["policyengine"] = version
    configuration["status"] = "ready"
    configuration["pending_release"].update(
        pull_request=values["CERTIFICATION_URL"], reviewed_head=reviewed_head, policyengine_version=version,
        bundle_manifest_sha256=values["BUNDLE_MANIFEST_SHA256"])
    (root / "data/binding-bridge.json").write_text(json.dumps(configuration, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pr", type=int, required=True, help="the merged policyengine.py PR certifying the pair")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--release", help="the policyengine.py release tag carrying it")
    source.add_argument("--manifest", type=Path, help="that release's manifest file, e.g. the installed wheel's")
    parser.add_argument("--target", choices=sorted(TARGETS), default="binding")
    parser.add_argument("--apply", action="store_true", help="write the identities once every check passes")
    args = parser.parse_args(argv)

    from triple_lock import datasets

    name, prefix = TARGETS[args.target]
    spec = datasets.DATASETS[name]
    if args.manifest:
        raw = args.manifest.read_bytes()
    else:
        raw = base64.b64decode(github(f"repos/{REPOSITORY}/contents/{MANIFEST}?ref={args.release}")["content"])
    manifest = json.loads(raw)
    if args.release and manifest["policyengine_version"] != args.release:
        raise SystemExit(f"release {args.release}'s manifest names policyengine {manifest['policyengine_version']}")
    rows = checks(manifest, spec)
    pull_request = github(f"repos/{REPOSITORY}/pulls/{args.pr}")
    values = identities(raw, manifest, pull_request)
    # Identities already filled (a rerun on the installed wheel's manifest) must equal what this release supplies.
    rows += [(f"filled {prefix}_{key}", getattr(datasets, f"{prefix}_{key}"), value) for key, value in values.items()
             if getattr(datasets, f"{prefix}_{key}") is not None]
    width = max(len(label) for label, _, _ in rows)
    for label, pinned, released in rows:
        print(f"{'ok  ' if pinned == released else 'FAIL'} {label:<{width}}  {json.dumps(released)}"
              + ("" if pinned == released else f"  (pinned {json.dumps(pinned)})"))
    release = manifest["data_releases"]["uk"]
    print(json.dumps({"dataset": name, **{f"{prefix}_{key}": value for key, value in values.items()},
                      "reviewed_head": pull_request["head"]["sha"],
                      **{key: release.get(key) for key in ("regional_release_kind", "regional_release_manifest_uri",
                                                           "regional_source_manifest_uri")}}, indent=2))
    if any(pinned != released for _, pinned, released in rows):
        print(f"refused: the release differs from the pinned {name} pair", file=sys.stderr)
        return 1
    if args.apply:
        if any(label.startswith("filled ") for label, _, _ in rows):
            raise SystemExit(f"{prefix} identities are already filled: rerun without --apply to check them")
        fill(ROOT, prefix, values, pull_request["head"]["sha"])
        print("applied: review the diff; install the release; run check_upstream(), both preflights and "
              "the bridge's --validate-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
