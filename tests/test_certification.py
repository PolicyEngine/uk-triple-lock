"""Offline ledger and installed-wheel attestation using invented payloads only."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from triple_lock import certification


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    pair_id, ledger, candidate = "a" * 64, "b" * 40, "c" * 40
    spec = {"logical_name": "enhanced_frs_2024_25", "repo_id": "policyengine/example-private",
            "repo_type": "model", "path": "example.h5", "revision": "1.2.3", "sha256": "d" * 64,
            "data_package": "policyengine-uk-data", "data_version": "1.2.3",
            "release_manifest": {"revision": "e" * 40, "path": "release.json", "sha256": "f" * 64}}
    pair = {"country_id": "uk", "data": {
        "dataset": spec["logical_name"], "repo_id": spec["repo_id"], "repo_type": "model",
        "dataset_path": spec["path"], "dataset_revision": spec["revision"], "dataset_sha256": spec["sha256"],
        "data_package": spec["data_package"], "release_version": spec["data_version"],
        "release_manifest_revision": spec["release_manifest"]["revision"],
        "release_manifest_path": spec["release_manifest"]["path"],
        "release_manifest_sha256": spec["release_manifest"]["sha256"],
    }}
    source = {"schema_version": 1, "ledger_commit": ledger, "pair_id": pair_id,
              "candidate_commit": candidate,
              "source_url": f"https://github.com/PolicyEngine/policyengine.py/blob/{ledger}/uk/{pair_id}/qualification_receipt.json",
              "receipt_path": "data/certification/receipt.json", "wheels": {}}
    distributions = {"policyengine": SimpleNamespace(version="6.10.2")}
    for role, name, version in (("model", "policyengine-uk", "2.153.4"), ("core", "policyengine-core", "3.33.3")):
        package = name.replace("-", "_")
        members = {f"{package}/__init__.py": b"VERSION = 'invented fixture'\n",
                   f"{package}/parameters/example.yaml": b"value: 123\n",
                   f"{package}-{version}.dist-info/METADATA": f"Name: {name}\nVersion: {version}\n".encode()}
        for member, raw in members.items():
            path = tmp_path / "site-packages" / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        wheel_hash = hashlib.sha256(f"invented {name} wheel".encode()).hexdigest()
        pair[role] = {"name": name, "version": version, "wheel_sha256": wheel_hash}
        manifest_path = f"data/certification/{role}.json"
        manifest = {"schema_version": 1, "package": name, "version": version,
                    "wheel": {"sha256": wheel_hash},
                    "members": {member: hashlib.sha256(raw).hexdigest() for member, raw in members.items()}}
        source["wheels"][name] = {"manifest_path": manifest_path,
                                  "manifest_sha256": _write(tmp_path / manifest_path, manifest)}
        distributions[name] = SimpleNamespace(version=version, locate_file=lambda path: tmp_path / "site-packages" / path)
    receipt = {"pair_id": pair_id, "pair": pair, "harness": {"git_commit": candidate},
               "verdict": "qualified", "gates": [{"gate_id": gate, "status": "pass"}
                                                     for gate in certification.REQUIRED_GATES]}
    cert = {"bundle_package": "policyengine", "bundle_version": "6.10.2", "model_version": "2.153.4",
            "core_version": "3.33.3", "ledger_source_path": "data/certification/source.json"}
    versions = {key: cert[key] for key in ("bundle_package", "bundle_version", "model_version", "core_version")}

    def save():
        source["receipt_sha256"] = _write(tmp_path / source["receipt_path"], receipt)
        cert["ledger_source_sha256"] = _write(tmp_path / cert["ledger_source_path"], source)

    def verify():
        return certification.verify_bundle(cert, spec, versions, root=tmp_path, distribution=distributions.__getitem__)

    save()
    return SimpleNamespace(root=tmp_path, cert=cert, spec=spec, source=source, receipt=receipt,
                           versions=versions, distributions=distributions, save=save, verify=verify)


def test_exact_qualified_pair_and_authenticated_installed_payload_pass_offline(bundle):
    result = bundle.verify()
    assert result["verdict"] == "qualified"
    assert result["gates"] == {gate: "pass" for gate in certification.REQUIRED_GATES}
    assert result["wheel_hashes"] == {package["name"]: package["wheel_sha256"]
                                     for package in (bundle.receipt["pair"]["model"], bundle.receipt["pair"]["core"])}
    assert not list(bundle.root.rglob("*.h5"))


@pytest.mark.parametrize("verdict", ["needs_review", "rejected", "incomplete", "accepted"])
def test_only_a_clean_qualified_receipt_is_accepted(bundle, verdict):
    bundle.receipt["verdict"] = verdict
    bundle.save()
    with pytest.raises(certification.CertificationMismatch, match="not a clean pass"):
        bundle.verify()


@pytest.mark.parametrize("gate_change", ["fail", "needs_review", "unavailable", "error", "missing", "duplicate"])
def test_every_mandatory_gate_must_pass_exactly_once(bundle, gate_change):
    if gate_change == "missing":
        bundle.receipt["gates"].pop()
    elif gate_change == "duplicate":
        bundle.receipt["gates"].append(bundle.receipt["gates"][0].copy())
    else:
        bundle.receipt["gates"][0]["status"] = gate_change
    bundle.save()
    with pytest.raises(certification.CertificationMismatch, match="mandatory qualification gate"):
        bundle.verify()


@pytest.mark.parametrize("target", ["receipt", "source", "wheel_manifest"])
def test_committed_metadata_must_retain_its_pinned_bytes(bundle, target):
    path = {"receipt": bundle.source["receipt_path"], "source": bundle.cert["ledger_source_path"],
            "wheel_manifest": bundle.source["wheels"]["policyengine-uk"]["manifest_path"]}[target]
    with (bundle.root / path).open("ab") as file:
        file.write(b" ")
    with pytest.raises(certification.CertificationMismatch, match="metadata SHA-256 mismatch"):
        bundle.verify()


@pytest.mark.parametrize("key", ["revision", "sha256", "repo_id", "path", "data_version"])
def test_dataset_pin_must_match_the_receipt(bundle, key):
    bundle.spec[key] = "wrong"
    with pytest.raises(certification.CertificationMismatch, match="Dataset pin differs"):
        bundle.verify()


def test_dataset_release_manifest_is_immutable(bundle):
    bundle.spec["release_manifest"]["revision"] = "0" * 40
    with pytest.raises(certification.CertificationMismatch, match="release manifest differs"):
        bundle.verify()


def test_installed_payload_edit_after_a_success_is_rechecked(bundle):
    bundle.verify()
    path = bundle.root / "site-packages/policyengine_uk/parameters/example.yaml"
    path.write_bytes(b"value: 456\n")  # same size; the stat cache must still notice
    with pytest.raises(certification.CertificationMismatch, match="payload SHA-256 mismatch"):
        bundle.verify()


def test_installed_metadata_version_and_additional_importable_payload_are_checked(bundle):
    bundle.distributions["policyengine-core"].version = "0.0.0"
    with pytest.raises(certification.CertificationMismatch, match="Installed version differs"):
        bundle.verify()
    bundle.distributions["policyengine-core"].version = "3.33.3"
    added = bundle.root / "site-packages/policyengine_core/unqualified.py"
    added.write_text("raise RuntimeError('not from the wheel')\n")
    with pytest.raises(certification.CertificationMismatch, match="Unexpected installed wheel payload"):
        bundle.verify()


def test_installer_generated_bytecode_is_allowed(bundle):
    bytecode = bundle.root / "site-packages/policyengine_core/__pycache__/example.cpython-313.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"invented bytecode")
    assert bundle.verify()["verdict"] == "qualified"


def test_additional_sourceless_module_is_not_installer_bytecode(bundle):
    bytecode = bundle.root / "site-packages/policyengine_core/unqualified.pyc"
    bytecode.write_bytes(b"not from the wheel")
    with pytest.raises(certification.CertificationMismatch, match="Unexpected installed wheel payload"):
        bundle.verify()


def test_unqualified_added_distribution_metadata_is_rejected(bundle):
    metadata = bundle.root / "site-packages/policyengine_core-3.33.3.dist-info/entry_points.txt"
    metadata.write_text("[console_scripts]\nunqualified = example:main\n")
    with pytest.raises(certification.CertificationMismatch, match="Unexpected installed wheel payload"):
        bundle.verify()


def test_installer_bookkeeping_is_allowed(bundle):
    directory = bundle.root / "site-packages/policyengine_core-3.33.3.dist-info"
    for name in ("RECORD", "INSTALLER", "REQUESTED", "direct_url.json"):
        (directory / name).write_text("generated by the installer")
    assert bundle.verify()["verdict"] == "qualified"


def test_receipt_harness_must_be_the_candidate_in_the_immutable_ledger_source(bundle):
    bundle.receipt["harness"]["git_commit"] = "0" * 40
    bundle.save()
    with pytest.raises(certification.CertificationMismatch, match="differs from its ledger source"):
        bundle.verify()
