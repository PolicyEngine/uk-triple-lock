"""Assemble a complete D support receipt from aggregate-only checkpoints; run no model."""

import importlib.metadata
import json
import sys
from pathlib import Path

import audit_model_v2_d_fiscal as audit


def load_checkpoint(label, driver):
    value = json.loads((audit.STORE / f"{label}.aggregate.json").read_text())
    assert value["driver_sha256"] == driver, "Checkpoint belongs to another calculation recipe"
    return value


def main():
    # write_receipt records the execution environment. Require the original
    # one so a pure assembly cannot silently replace its provenance.
    assert sys.version.split()[0] == "3.13.9"
    assert importlib.metadata.version("policyengine-uk") == "2.120.0"
    assert importlib.metadata.version("policyengine-core") == "3.32.16"
    driver = audit.digest(Path(audit.__file__))
    labels = ["central", *(f"draw_{index}" for index in sorted(audit.SPECS["paired"]))]
    pairs = [load_checkpoint(label, driver) for label in labels]
    extras = {**audit.SPECS["ev"], **audit.SPECS["concentrated"]}
    singles = [load_checkpoint(f"bridge_draw_{index}", driver)
               for index in sorted(extras) if index not in audit.SPECS["paired"]]
    published = json.loads((audit.ROOT / "data" / "pilot" / "d_fiscal_support_audit.json").read_text())
    auxiliary = {row["label"]: row for row in published.get("extra_legacy", [])}
    for label in ("newer_central", "obr_premium"):
        path = audit.STORE / f"{label}.aggregate.json"
        if path.exists():
            row = load_checkpoint(label, driver)
        else:
            assert published["driver_sha256"] == driver
            row = auxiliary[label]
        assert row["passed"] is True
        singles.append(row)
    audit.write_receipt(pairs, singles, complete=True)
    print("Complete D support receipt assembled from aggregate-only checkpoints; no model run")


if __name__ == "__main__":
    main()
