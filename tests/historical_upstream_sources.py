"""Bind retained pilot formula receipts to genuine archived upstream bytes.

The certified installed model has changed. These stdlib-only checks read a
hash-bound excerpt archive of policyengine-uk 2.120.0; they neither import nor
extract it, and make no claim about the current runtime's formula identity.
"""

import hashlib
from pathlib import Path
import tarfile
import tomllib


PILOT_MODEL_VERSION = "2.120.0"
SOURCE_COMMIT = "b5b092312df7aa56a4e89c4b9b7c133507dea114"
ARCHIVE_PATH = "tests/fixtures/policyengine-uk-2.120.0-receipt-sources.tar.gz"
# Independent of mutable archive metadata and retained receipt digests.
ARCHIVE_SHA256 = "7d23f6322bded418302424f9eaa79a9527a1dcfcd7c1df101c7947662b4fa672"


def historical_upstream_files(repo, model_version):
    """Read the precise historical source without depending on installed UK."""
    assert model_version == PILOT_MODEL_VERSION, "formula archive is only for the 2.120.0 pilot model"
    archive = (repo / ARCHIVE_PATH).resolve()
    assert archive.is_relative_to(repo.resolve()), "historical upstream archive leaves repository"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA256, \
        "historical upstream archive bytes changed"
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        assert all(member.isfile() and not Path(member.name).is_absolute()
                   and ".." not in Path(member.name).parts for member in members), \
            "invalid historical upstream archive member"
        assert len({member.name for member in members}) == len(members), \
            "duplicate historical upstream archive member"
        files = {member.name: tar.extractfile(member).read() for member in members}
    metadata = tomllib.loads(files["pyproject.toml"].decode())["project"]
    assert metadata["name"] == "policyengine-uk" and metadata["version"] == model_version, \
        "historical upstream package metadata differs from the receipt"
    return files


def verify_historical_formula_sources(repo, packages, formulas):
    """Verify the receipt's unchanged hashes against its original model source."""
    version = packages["policyengine-uk"]
    files = historical_upstream_files(repo, version)
    for relative, expected in formulas.items():
        assert relative.startswith("variables/") and relative.endswith(".py"), \
            "historical formula path must name an upstream variable source"
        source = files[f"policyengine_uk/{relative}"]
        assert hashlib.sha256(source).hexdigest() == expected, \
            f"historical upstream formula differs from its retained receipt: {relative}"
    return {"passed": True, "model_version": version, "source_commit": SOURCE_COMMIT,
            "archive_path": ARCHIVE_PATH, "archive_sha256": ARCHIVE_SHA256,
            "formula_count": len(formulas), "current_runtime_identity_claimed": False}
