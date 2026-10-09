"""Resume only the missing Microcosm cold repeat from a validated first receipt.

The imported worker and its execution fingerprint stay unchanged. This helper
never relabels a receipt or reuses its cache: the repeat gets its own fresh
archive, interpreter and cache. Run only after a new one-worker allocation.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import run_model_v2_determinism as driver

YEARS = list(range(2027, 2040))


def current_provenance(specification):
    from triple_lock import engine

    packages = engine.package_versions()
    if packages["policyengine-uk"] != "2.120.0" or packages["policyengine-core"] != "3.32.16":
        raise ValueError("the resume environment must retain the pilot's pinned model packages")
    full_spec = {**engine._keys_to_int(specification), "dataset": driver.MICROCOSM, "demography": "both"}
    return {"full_spec_sha256": driver.fingerprint(full_spec),
            "packages": packages, "package_sha256": driver.fingerprint(packages),
            "python": sys.version.split()[0],
            "engine_file_sha256": driver.digest(Path(engine.__file__)),
            "engine_semantics_sha256": driver.fingerprint(engine.engine_semantics())}


def validate_first_receipt(path, args, workspace, specification, data):
    path = Path(path).resolve()
    if not path.is_relative_to(workspace):
        raise ValueError("the completed first checkpoint must stay inside the assigned workspace")
    row = json.loads(path.read_text())
    expected = {"label": "current_first", "calculation_head": args.current_head,
                "dataset": driver.MICROCOSM, "treatment": "both", "passed": True,
                "cold_cache": True, "minimum_contributing_records": driver.MIN_RECORDS,
                "calculated_fiscal_years": YEARS, "fiscal_output_years": YEARS,
                "scientific_check_years": YEARS, "aggregate_fingerprint_years": YEARS,
                "dataset_sha256": driver.digest(data),
                "driver_sha256": driver.digest(Path(driver.__file__)),
                **current_provenance(specification)}
    for key, value in expected.items():
        if row.get(key) != value:
            raise ValueError(f"the completed first checkpoint does not match {key}")
    scientific = driver.committed_source_fingerprint(args.git_dir, args.current_head)
    head = subprocess.run(["/usr/bin/git", "--git-dir", str(args.git_dir.resolve()), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    if (row.get("source_sha256") != scientific
            or driver.committed_source_fingerprint(args.git_dir, head) != scientific
            or driver.source_fingerprint(workspace) != scientific):
        raise ValueError("the completed first checkpoint differs from the final scientific source")
    if row.get("aggregate_sha256") != driver.fingerprint(
            driver.selected_aggregates(row["aggregates"], YEARS)):
        raise ValueError("the completed first checkpoint has a changed aggregate fingerprint")
    driver.validate_support_counts(row["cells"])
    return row


def main(args):
    os.umask(0o077)
    workspace = Path.cwd().resolve()
    if not args.out.resolve().is_relative_to(workspace):
        raise ValueError("all outputs must stay inside the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.current_head):
        raise ValueError("--current-head must name the full final scientific commit SHA")
    sys.path.insert(0, str(workspace / "src"))
    from triple_lock import datasets

    data = datasets.materialize(driver.MICROCOSM, store=workspace / ".cache" / "datasets")
    specification = json.loads(args.specs.read_text())["central"]
    historical = driver.load_historical_receipts(args.reuse_historical_receipts, workspace)
    first = validate_first_receipt(args.first_receipt, args, workspace, specification, data)
    if args.validate_only:
        print("Completed first checkpoint matches source, inputs, packages and unchanged worker", flush=True)
        return
    store = workspace / ".cache" / "microcosm-check"
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.workers = 1
    with driver.cold_pool(1) as (pool, stop):
        future = pool.submit(driver.execute_mc_job, ("current_repeat", args.current_head, "both"),
                             args, workspace, data, store, specification, stop)
        repeat, resource = future.result()
    runs = [*historical, first, repeat]
    resources = [{"label": "current_first", **first["resources_before_actual_job"],
                  "reused_aggregate_receipt_sha256": driver.digest(args.first_receipt)}, resource]
    correspondence = driver.source_correspondence(args.git_dir, runs)
    driver.write_public(args.out, runs, resources, args.historical, correspondence, workers=1)
    print("Completed cold pair and final scientific-source correspondence passed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-dir", type=Path, default=driver.default_git_dir())
    parser.add_argument("--current-head", required=True)
    parser.add_argument("--first-receipt", type=Path, required=True)
    parser.add_argument("--reuse-historical-receipts", type=Path, nargs=2, required=True)
    parser.add_argument("--run-label", required=True, help="new label for the repeat's fresh archive")
    parser.add_argument("--minimum-available-gib", type=float, default=44.)
    parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
    parser.add_argument("--historical", type=Path, default=Path("data/pilot/microcosm_central.json"))
    parser.add_argument("--out", type=Path, default=Path("data/pilot/microcosm_support_and_determinism.json"))
    parser.add_argument("--validate-only", action="store_true")
    main(parser.parse_args())
