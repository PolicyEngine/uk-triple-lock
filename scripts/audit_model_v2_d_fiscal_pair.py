"""Precompute an original D macro-draw pair into an atomic aggregate-only checkpoint.

Run only when an Enhanced FRS slot is free. The serial support coordinator
reads these checkpoints without changing its calculation recipe or outputs.
"""

import argparse
import json
import os
from pathlib import Path

import audit_model_v2_d_fiscal as audit


def main(index):
    os.umask(0o077)
    audit.STORE.mkdir(parents=True, exist_ok=True)
    calibration = json.loads((audit.STORE / "calibration.aggregate.json").read_text())
    assert all(calibration["treatments"][name]["passed"] for name in ("legacy", "both"))
    spec = audit.SPECS["paired"][index]["spec"]
    label = f"draw_{index}"
    path = audit.STORE / f"{label}.aggregate.json"
    driver = audit.digest(Path(audit.__file__))
    if path.exists():
        assert json.loads(path.read_text())["driver_sha256"] == driver
        print(f"Existing aggregate support checkpoint retained: {label}")
        return
    legacy = audit.execute({"label": label, "spec": spec, "dataset": audit.PRIMARY, "treatment": "legacy"})
    both = audit.execute({"label": label, "spec": spec, "dataset": audit.PRIMARY, "treatment": "both"})
    contrast = audit.treatment_contrasts(legacy["private"], both["private"])
    pair = {"label": label, "driver_sha256": driver, "legacy": legacy["safe"], "both": both["safe"],
            "both_minus_legacy_support": contrast}
    del legacy, both
    temporary = path.with_suffix(f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(audit.redact_records(pair), indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
    print(f"Atomic aggregate support checkpoint complete: {label}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draw", type=int, required=True, help="An original paired macro-draw index, never a survey ID")
    main(parser.parse_args().draw)
