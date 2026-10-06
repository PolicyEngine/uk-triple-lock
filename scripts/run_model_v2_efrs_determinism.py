"""One cold Enhanced FRS central/both pair at the final scientific head.

Checks the central/both path twice in fresh interpreters and git archives.
Fiscal quantities are
fully calculated in all 13 forecast years, then the 2034/2039 aggregates
are selected for fingerprints. All engine scientific checks are retained.
Run only within an allocation of one or two free Enhanced FRS worker slots.
Authentication is supplied through HUGGING_FACE_TOKEN, never an argument.
"""

import argparse
from concurrent.futures import as_completed
import json
import os
from pathlib import Path
import re
import sys

from run_model_v2_determinism import (
    archive_source, cold_pool, compare_runs, default_git_dir, digest, resource_receipt, run_checked_child,
    source_correspondence, worker,
)

PRIMARY = "enhanced_frs_2024_25@1.56.16"
TARGET_YEARS = [2034, 2039]


def plan(specifications):
    return [{"case": "central_both", "label": f"central_both_{repeat}", "repeat": repeat,
             "treatment": "both", "specification": specifications["central"]}
            for repeat in ("first", "repeat")]


def comparison_table(runs):
    grouped = {}
    for run in runs:
        grouped.setdefault(run["case"], []).append(run)
    return {case: compare_runs(*pair) for case, pair in grouped.items() if len(pair) == 2}


def write_public(output, runs, resources, specs, workers=1, correspondence=None):
    comparisons = comparison_table(runs)
    complete = len(runs) == 2 and {row.get("label") for row in runs} == {
        "central_both_first", "central_both_repeat"}
    passed = (set(comparisons) == {"central_both"}
              and comparisons["central_both"]["passed"]
              and correspondence and correspondence["passed"])
    value = {
        "status": ("passed" if passed else "failed")
                  if complete else "in progress",
        "complete": complete, "certified": False, "quote_eligible": False,
        "warning": "pilot on an uncertified data/model pair; not for quoting",
        "minimum_contributing_records": 10, "dataset": PRIMARY,
        "data_built_with": "policyengine-uk 2.89.2", "policyengine_uk": "2.120.0",
        "specifications_sha256": digest(specs),
        "runs": [{key: value for key, value in row.items() if key != "aggregates"} for row in runs],
        "comparisons": comparisons,
        "final_head_scientific_source_correspondence": correspondence,
        "execution_driver_sha256": digest(Path(__file__)),
        "resources_before_each_job": resources,
        "execution": "two full PolicyEngine central/both paths; fresh interpreter and cold "
                     "demography cache for every run",
        "maximum_enhanced_frs_workers": workers,
        "fiscal_output_years": list(range(2027, 2040)),
        "calculated_fiscal_years": list(range(2027, 2040)),
        "aggregate_fingerprint_years": TARGET_YEARS,
        "scientific_check_years": list(range(2027, 2040)),
        "scope": "aggregate fingerprints and contributor counts only; complete PolicyEngine "
                 "fiscal outputs and scientific checks for all 13 years; reporting years selected afterward",
    }
    from triple_lock.pipeline import redact_records

    redact_records(value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    if complete and value["status"] != "passed":
        raise RuntimeError("the final-head Enhanced FRS cold pair or source correspondence failed")


def execute_job(row, args, workspace, data, store, stop=None):
    """One fresh process; the coordinator's pool only controls admission."""
    resources = {"label": row["label"], **resource_receipt()}
    if resources["available_bytes"] < args.minimum_available_gib * 2**30:
        raise RuntimeError("available host RAM is below the Enhanced FRS headroom requirement")
    source = archive_source(workspace, args.git_dir.resolve(), args.head,
                            f"efrs-{args.run_label}-{row['label']}")
    data_store = source / ".cache" / "datasets"
    data_store.mkdir(parents=True, mode=0o700)
    os.link(data, data_store / data.name)
    configuration = {**row, "head": args.head, "source": str(source), "dataset": PRIMARY,
                     "cold_cache": not (source / ".cache" / "demography").exists(),
                     "fingerprint_years": TARGET_YEARS,
                     "minimum_available_gib": args.minimum_available_gib}
    input_file = store / f"{args.run_label}-{row['label']}.input.json"
    aggregate_file = store / f"{args.run_label}-{row['label']}.aggregate.json"
    input_file.write_text(json.dumps(configuration))
    private_log = store / f"{args.run_label}-{row['label']}.private.log"
    print(f"Starting full Enhanced FRS {row['label']} at {args.head}; allocation {args.workers}", flush=True)
    code = run_checked_child(
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(input_file), str(aggregate_file)],
        workspace, source, private_log, stop)
    if code:
        raise RuntimeError(f"Enhanced FRS path failed; private diagnostics retained in {private_log.name}")
    safe = json.loads(aggregate_file.read_text())
    safe.update(case=row["case"], repeat=row["repeat"])
    print(f"Completed full Enhanced FRS {row['label']}; aggregate support passed", flush=True)
    return safe, resources


def main(args):
    os.umask(0o077)
    workspace = Path.cwd().resolve()
    if not args.out.resolve().is_relative_to(workspace):
        raise ValueError("all outputs must stay inside the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.head):
        raise ValueError("--head must name the full final engine commit SHA")
    sys.path.insert(0, str(workspace / "src"))
    from triple_lock import datasets

    data = datasets.materialize(PRIMARY, store=workspace / ".cache" / "datasets")
    specifications = json.loads(args.specs.read_text())
    store = workspace / ".cache" / "efrs-determinism"
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.workers not in (1, 2):
        raise ValueError("the cold-check allocation is one or two Enhanced FRS workers")
    rows = plan(specifications)
    order = {row["label"]: i for i, row in enumerate(rows)}
    runs, resources = [], []
    # Admit only one wave at a time, so an exception cannot leave queued
    # simulations starting after a failed check. Every subprocess keeps its
    # own source directory and cache, including both members of each pair.
    with cold_pool(args.workers) as (pool, stop):
        for offset in range(0, len(rows), args.workers):
            futures = [pool.submit(execute_job, row, args, workspace, data, store, stop)
                       for row in rows[offset:offset + args.workers]]
            for future in as_completed(futures):
                safe, resource = future.result()
                runs.append(safe)
                resources.append(resource)
                runs.sort(key=lambda row: order[row["label"]])
                resources.sort(key=lambda row: order[row["label"]])
                correspondence = (source_correspondence(args.git_dir.resolve(), runs, "central_both_")
                                  if len(runs) == 2 else None)
                write_public(args.out, runs, resources, args.specs, args.workers, correspondence)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(json.loads(Path(sys.argv[2]).read_text()), Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--git-dir", type=Path, default=default_git_dir())
        parser.add_argument("--head", required=True)
        parser.add_argument("--run-label", default="final")
        parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
        parser.add_argument("--minimum-available-gib", type=float, default=12.)
        parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
        parser.add_argument("--out", type=Path, default=Path("data/pilot/efrs_determinism.json"))
        main(parser.parse_args())
