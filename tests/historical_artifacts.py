"""The historical pilot publication, by its exact pinned bytes, whether or not it is still the committed file.

``triple_lock.historical_publication`` pins the sanitized bytes of the historical (uncertified pilot) results, their
dashboard copy and the OBR-premium scenario. A certified rebuild replaces those committed files with new bytes, which
are a new input with their own identity and cannot satisfy the pins. The proof of the historical publication still
has to hold, so the bytes it binds are archived here (gzip, decompressed byte for byte) and the proof runs on a tree
holding them. CI checks out at depth 1, so the archive cannot come from Git history.

While the committed file *is* the historical file, everything here reads the committed bytes, and the archive must
equal them: the proof is exactly as strong either way.
"""

import gzip
import json
import shutil
from pathlib import Path

from triple_lock.historical_publication import PROOF, REVIEWED_ARTIFACTS, digest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tests" / "fixtures" / "historical-publication"
# Each reviewed target a rebuild replaces, and its archived copy. data/pilot/model_v2_e.json is never rebuilt.
ARCHIVED = {
    "data/results.json": "results.json.gz",
    "dashboard/public/data/results.json": "results.json.gz",
    "data/scenarios/obr_premium.json": "obr_premium.json.gz",
}
RESULTS = "data/results.json"


def pinned_sha256(relative):
    return next(a["sanitized_artifact_sha256"] for a in REVIEWED_ARTIFACTS if relative in a["targets"])


def committed_is_historical(relative=RESULTS):
    """True while the committed target is still the historical publication's exact bytes."""
    return digest((ROOT / relative).read_bytes()) == pinned_sha256(relative)


def historical_bytes(relative):
    """The exact historical bytes of a reviewed target: the committed file while it is the historical one, else the
    archived copy. Either way the bytes must hash to the independently reviewed pin."""
    if relative not in ARCHIVED or committed_is_historical(relative):
        content = (ROOT / relative).read_bytes()
    else:
        content = gzip.decompress((ARCHIVE / ARCHIVED[relative]).read_bytes())
    if digest(content) != pinned_sha256(relative):
        raise AssertionError(f"archived historical {relative} does not match its reviewed pin")
    return content


def historical_results():
    """The historical pilot results (with its expected value and Microcosm-paired draws), parsed."""
    return json.loads(historical_bytes(RESULTS))


def historical_tree(destination):
    """A repository-shaped tree with the publication proof and every reviewed target at its historical bytes."""
    destination = Path(destination)
    for artifact in REVIEWED_ARTIFACTS:
        for relative in artifact["targets"]:
            path = destination / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(historical_bytes(relative))
    proof = destination / PROOF
    proof.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / PROOF, proof)
    return destination


def historical_root(tmp_path):
    """The repository itself while it still holds the historical publication, else a tree under ``tmp_path``."""
    if all(committed_is_historical(relative) for relative in ARCHIVED):
        return ROOT
    return historical_tree(Path(tmp_path) / "historical-publication")
