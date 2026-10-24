"""Offline attestation of a ledger-qualified model, core and dataset artifact.

The committed wheel member manifests are extracted from archives whose SHA-256s
were checked against the qualification receipt and PyPI. They let preflight
check the installed payload without downloading wheels or opening survey data.
"""

import hashlib
import importlib.metadata
import json
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath

from .config import REPO

REQUIRED_GATES = (
    "installed_versions", "wheel_hashes", "core_compatibility", "data_access",
    "dataset_bytes", "supported_years", "budget_inputs", "reform_contract",
    "metrics_review", "reform_responsiveness", "replay",
)


class CertificationMismatch(RuntimeError):
    """Installed packages or the artifact pin differ from the qualified pair."""


def _relative(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise CertificationMismatch(f"Unsafe certification path: {name!r}")
    return Path(root).joinpath(*relative.parts)


def _document(root, name, expected):
    raw = _relative(root, name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise CertificationMismatch(f"Certification metadata SHA-256 mismatch: {name}")
    return json.loads(raw)


@lru_cache(maxsize=16384)
def _payload_hash(path, inode, size, mtime, ctime):
    # The stat tuple is part of the cache key: an installed file edited or
    # replaced after a successful preflight is checked again.
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_installed_wheel(name, pair_package, wheel_manifest, distribution):
    if (wheel_manifest.get("schema_version") != 1
            or wheel_manifest.get("package") != name
            or wheel_manifest.get("version") != pair_package["version"]
            or wheel_manifest.get("wheel", {}).get("sha256") != pair_package["wheel_sha256"]):
        raise CertificationMismatch(f"Wheel attestation differs from the receipt: {name}")
    installed = distribution(name)
    if installed.version != pair_package["version"]:
        raise CertificationMismatch(f"Installed version differs from the receipt: {name}")
    members = wheel_manifest["members"]
    if not members or any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in members.values()):
        raise CertificationMismatch(f"Invalid wheel member manifest: {name}")
    roots = set()
    for member, digest in members.items():
        relative = PurePosixPath(member)
        _relative(".", member)  # reject traversals before locating installed files
        if relative.parts[0].endswith(".data"):
            raise CertificationMismatch(f"Unsupported relocated wheel member: {member}")
        path = Path(installed.locate_file(member))
        info = path.stat()
        actual = _payload_hash(str(path.absolute()), info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if actual != digest:
            raise CertificationMismatch(f"Installed wheel payload SHA-256 mismatch: {name}: {member}")
        if len(relative.parts) > 1:
            roots.add(relative.parts[0])
    # Installers add bytecode and dist-info bookkeeping. An additional source
    # or data file in the importable package is not part of the qualified wheel.
    for package_root in roots:
        directory = Path(installed.locate_file(package_root))
        for path in directory.rglob("*"):
            relative = path.relative_to(directory)
            cached_bytecode = "__pycache__" in relative.parts and path.suffix == ".pyc"
            installer_metadata = (package_root.endswith(".dist-info") and len(relative.parts) == 1
                                  and path.name in {"RECORD", "INSTALLER", "REQUESTED", "direct_url.json"})
            if (path.is_file() or path.is_symlink()) and not (cached_bytecode or installer_metadata):
                member = str(PurePosixPath(package_root, *path.relative_to(directory).parts))
                if member not in members:
                    raise CertificationMismatch(f"Unexpected installed wheel payload: {name}: {member}")
    return wheel_manifest["wheel"]["sha256"]


def verify_bundle(certification, spec, versions, *, root=REPO, distribution=None):
    """Check receipt, exact pins and installed wheel payloads; never read records.

    ``certification`` pins the source sidecar path and digest. The sidecar pins
    the raw receipt and wheel member manifests, so all metadata is checked
    offline. ``spec`` is one dataset registry entry and ``versions`` is the
    output of ``datasets.model_versions``. Raises ``CertificationMismatch``
    on any missing evidence, unqualified receipt or mismatch.
    """
    distribution = distribution or importlib.metadata.distribution
    try:
        source = _document(root, certification["ledger_source_path"], certification["ledger_source_sha256"])
        receipt = _document(root, source["receipt_path"], source["receipt_sha256"])
        if source.get("schema_version") != 1 or not re.fullmatch(r"[0-9a-f]{40}", source["ledger_commit"]):
            raise CertificationMismatch("Invalid ledger source metadata")
        pair_id = receipt["pair_id"]
        expected_url = ("https://github.com/PolicyEngine/policyengine.py/blob/"
                        f"{source['ledger_commit']}/uk/{pair_id}/")
        if (source["pair_id"] != pair_id or not source["source_url"].startswith(expected_url)
                or not source["source_url"].endswith("/qualification_receipt.json")
                or receipt["harness"]["git_commit"] != source["candidate_commit"]):
            raise CertificationMismatch("Receipt differs from its ledger source")
        gates = receipt["gates"]
        if receipt.get("verdict") != "qualified":
            raise CertificationMismatch(f"Receipt is not a clean pass: {receipt.get('verdict')}")
        if (len({gate["gate_id"] for gate in gates}) != len(gates)
                or not set(REQUIRED_GATES).issubset(gate["gate_id"] for gate in gates)
                or any(gate["status"] != "pass" for gate in gates)):
            raise CertificationMismatch("Every mandatory qualification gate must pass")
        pair = receipt["pair"]
        if pair["country_id"] != "uk":
            raise CertificationMismatch("Receipt is not for the UK")
        data = pair["data"]
        for receipt_key, spec_key in (
            ("repo_id", "repo_id"), ("repo_type", "repo_type"), ("dataset", "logical_name"),
            ("dataset_path", "path"), ("dataset_revision", "revision"), ("dataset_sha256", "sha256"),
            ("data_package", "data_package"), ("release_version", "data_version"),
        ):
            if data[receipt_key] != spec[spec_key]:
                raise CertificationMismatch(f"Dataset pin differs from the receipt: {spec_key}")
        for receipt_key, manifest_key in (
            ("release_manifest_revision", "revision"), ("release_manifest_path", "path"),
            ("release_manifest_sha256", "sha256"),
        ):
            if data[receipt_key] != spec["release_manifest"][manifest_key]:
                raise CertificationMismatch(f"Data release manifest differs from the receipt: {manifest_key}")
        for key in ("bundle_package", "bundle_version", "model_version", "core_version"):
            if versions.get(key) != certification[key]:
                raise CertificationMismatch(f"Installed pin differs from certification: {key}")
        if distribution(certification["bundle_package"]).version != certification["bundle_version"]:
            raise CertificationMismatch("Installed policyengine client version differs from its pin")
        wheel_hashes = {}
        for role, name in (("model", "policyengine-uk"), ("core", "policyengine-core")):
            package = pair[role]
            if package["name"] != name or package["version"] != certification[f"{role}_version"]:
                raise CertificationMismatch(f"Package pin differs from the receipt: {name}")
            pinned_manifest = source["wheels"][name]
            manifest = _document(root, pinned_manifest["manifest_path"], pinned_manifest["manifest_sha256"])
            wheel_hashes[name] = _verify_installed_wheel(name, package, manifest, distribution)
        return {"pair_id": pair_id, "ledger_commit": source["ledger_commit"],
                "receipt_sha256": source["receipt_sha256"], "verdict": receipt["verdict"],
                "gates": {gate["gate_id"]: gate["status"] for gate in gates}, "wheel_hashes": wheel_hashes}
    except CertificationMismatch:
        raise
    except (OSError, ValueError, KeyError, TypeError, importlib.metadata.PackageNotFoundError) as error:
        raise CertificationMismatch(f"Missing or invalid certification evidence: {error}") from error


def verify_released_bundle_payloads(certification, *, root=REPO, distribution=None):
    """Attest installed model/core bytes for the exact released Budget bundle.

    This adds payload checks to the released-manifest route. It does not waive
    any gate or change the historical qualification-ledger verifier above.
    """
    distribution = distribution or importlib.metadata.distribution
    try:
        wheels = certification["wheels"]
        verified = {}
        for role, name in (("model", "policyengine-uk"), ("core", "policyengine-core")):
            pin = wheels[name]
            manifest = _document(root, pin["manifest_path"], pin["manifest_sha256"])
            package = {"version": certification[f"{role}_version"], "wheel_sha256": pin["wheel_sha256"]}
            verified[name] = _verify_installed_wheel(name, package, manifest, distribution)
        return verified
    except CertificationMismatch:
        raise
    except (OSError, ValueError, KeyError, TypeError, importlib.metadata.PackageNotFoundError) as error:
        raise CertificationMismatch(f"Missing or invalid released bundle payload: {error}") from error
