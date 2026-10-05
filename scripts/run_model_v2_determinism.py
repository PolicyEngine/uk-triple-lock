"""Four serial, fresh Microcosm paths: archived D support and final-head determinism.

Run with the pinned Python environment and HUGGING_FACE_TOKEN already exported.
Every source tree is a git archive inside the assigned workspace. Each full
PolicyEngine path runs in a new interpreter with a cold demography cache.
The independent fiscal capture stays in that interpreter's memory; only
aggregate values, support counts and hashes leave it. No survey vectors or
single-record diagnostics are written or fingerprinted.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time

MICROCOSM = "populace_uk_2023"
D_LEGACY = "498d970123adff4e8f05908e17c7b366ba71a28c"
D_BOTH = "30318c4f9d1a5fdba290371dc5ab56bd1f064c0a"
MIN_RECORDS = 10
FIELDS = {"state_pension_flat_rate": ("basic_state_pension", "new_state_pension"),
          "additional_state_pension": ("additional_state_pension",),
          "pension_credit": ("pension_credit",), "housing_benefit": ("housing_benefit",)}


def fingerprint(value):
    """Lossless finite-float JSON fingerprint of selected aggregate fields."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 24):
            h.update(block)
    return h.hexdigest()


def source_fingerprint(source):
    """Hash all archived model Python sources and dependency declarations."""
    source = Path(source)
    paths = sorted((source / "src").rglob("*.py"))
    paths += [source / name for name in ("pyproject.toml", "requirements-lock.txt", "uv.lock")
              if (source / name).exists()]
    return fingerprint({str(path.relative_to(source)): digest(path) for path in paths})


def committed_source_fingerprint(git_dir, head):
    """The same source hash from immutable git blobs, excluding doc-only edits."""
    command = ["git", "--git-dir", str(Path(git_dir).resolve())]
    names = subprocess.run([*command, "ls-tree", "-r", "--name-only", "-z", head],
                           check=True, capture_output=True).stdout.decode().split("\0")
    selected = [name for name in names if (name.startswith("src/") and name.endswith(".py"))
                or name in ("pyproject.toml", "requirements-lock.txt", "uv.lock")]
    archive = subprocess.run([*command, "archive", head, *selected], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        contents = {member.name: hashlib.sha256(tar.extractfile(member).read()).hexdigest()
                    for member in tar.getmembers() if member.isfile()}
    return fingerprint(contents)


def source_correspondence(git_dir, runs):
    head = subprocess.run(["git", "--git-dir", str(Path(git_dir).resolve()), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    current_hash = committed_source_fingerprint(git_dir, head)
    current = [row for row in runs if row["label"].startswith("current")]
    matching = {row["label"]: row["source_sha256"] == current_hash for row in current}
    return {"branch_head_at_check": head, "scientific_source_sha256": current_hash,
            "executed_calculation_heads": sorted({row["calculation_head"] for row in current}),
            "matching_executed_sources": matching,
            "passed": len(current) == 2 and all(matching.values()),
            "scope": "all src Python files, pyproject.toml, requirements-lock.txt and optional uv.lock; "
                     "actual calculation commits remain unchanged"}


def load_historical_receipts(paths, workspace):
    """Reuse completed aggregate-only support audits without rerunning D."""
    expected = {"d_legacy": D_LEGACY, "d_both": D_BOTH}
    rows = []
    for path in paths:
        path = Path(path).resolve()
        if not path.is_relative_to(workspace):
            raise ValueError("reused audit receipts must stay inside the assigned workspace")
        row = json.loads(path.read_text())
        if (row.get("label") not in expected or row.get("calculation_head") != expected[row["label"]]
                or row.get("dataset") != MICROCOSM or row.get("passed") is not True
                or row.get("minimum_contributing_records") != MIN_RECORDS or row.get("cold_cache") is not True):
            raise ValueError("the reused audit is not a passed cold original-D Microcosm run")
        if row["aggregate_sha256"] != fingerprint(selected_aggregates(
                row["aggregates"], row.get("aggregate_fingerprint_years", range(2027, 2040)))):
            raise ValueError("a reused audit aggregate fingerprint does not match its quantities")
        if row["source_sha256"] != committed_source_fingerprint(workspace / ".git-e", row["calculation_head"]):
            raise ValueError("a reused audit source fingerprint does not match its recorded commit")
        rows.append(row)
    if len(rows) != 2 or {row["label"] for row in rows} != set(expected):
        raise ValueError("reuse requires exactly the legacy and both original-D support receipts")
    return sorted(rows, key=lambda row: row["label"] != "d_legacy")


def selected_aggregates(aggregates, years):
    """Select fingerprint years only after the full fiscal run has completed."""
    return {"saving_bn": {str(year): aggregates["saving_bn"][str(year)] for year in years},
            "totals_bn": {policy: {str(year): values[str(year)] for year in years}
                          for policy, values in aggregates["totals_bn"].items()}}


def supported_cell(contributors, aggregate):
    """A positive fiscal cell must have at least ten contributing households."""
    if (0 < contributors < MIN_RECORDS) or (aggregate != 0 and contributors < MIN_RECORDS):
        raise RuntimeError("a nonzero aggregate fails the ten-household disclosure floor")
    return {"status": "available", "records": contributors, "amount_bn": aggregate}


def compare_runs(first, second):
    keys = ("aggregate_sha256", "calculation_head", "source_sha256", "engine_semantics_sha256", "engine_file_sha256", "package_sha256",
            "dataset_sha256", "full_spec_sha256")
    matches = {key: first[key] == second[key] for key in keys}
    matches["fresh_cold_runs"] = first["cold_cache"] is True and second["cold_cache"] is True
    return {"passed": all(matches.values()), "bit_identical_aggregates": matches["aggregate_sha256"],
            "matching_hashes": matches}


def current_configuration(configuration):
    """Optionally pause the current-head pair until a final source is committed.

    An already-running archive audit may finish its two historical paths while
    the final engine is prepared. The explicit workspace control file records
    the eventual full SHA; it cannot alter either historical source tree.
    """
    if not configuration["label"].startswith("current") or configuration.get("honour_current_head_control") is False:
        return configuration
    workspace = Path.cwd().resolve()
    control = workspace / ".cache" / "microcosm-check" / "current-head-control.json"
    while control.exists():
        ruling = json.loads(control.read_text())
        if not ruling.get("paused", False):
            break
        parent = os.environ.get("TRIPLE_LOCK_PARENT_PID")
        if parent:
            os.kill(int(parent), 0)
        time.sleep(10)
    else:
        return configuration
    head = ruling["head"]
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("the current-head control must record a full commit SHA")
    if head == configuration["head"]:
        return configuration
    old_source = Path(configuration["source"])
    source = archive_source(workspace, workspace / ".git-e", head,
                            old_source.name + "-controlled-final")
    target_store = source / ".cache" / "datasets"
    target_store.mkdir(parents=True, mode=0o700)
    for data in (old_source / ".cache" / "datasets").glob("*.h5"):
        os.link(data, target_store / data.name)
    return {**configuration, "head": head, "source": str(source),
            "cold_cache": not (source / ".cache" / "demography").exists()}


def worker(configuration, output):
    """Fresh interpreter; private weighted arrays are never returned or saved."""
    os.umask(0o077)
    driver_digest = digest(Path(__file__))
    configuration = current_configuration(configuration)
    if not configuration["cold_cache"]:
        raise RuntimeError("determinism checks require a fresh cold demography cache")
    actual_resources = resource_receipt()
    if actual_resources["available_bytes"] < configuration.get("minimum_available_gib", 44) * 2**30:
        raise RuntimeError("available host RAM is below the Microcosm headroom requirement")
    source = Path(configuration["source"]).resolve()
    sys.path.insert(0, str(source / "src"))
    import numpy as np
    from triple_lock import engine, jobs, pipeline

    jobs.watch_parent()

    if not Path(engine.__file__).resolve().is_relative_to(source):
        raise RuntimeError("worker imported an engine outside its immutable source archive")
    packages = engine.package_versions()
    if packages["policyengine-uk"] != "2.120.0" or packages["policyengine-core"] != "3.32.16":
        raise RuntimeError("Microcosm checks require policyengine-uk 2.120.0 and policyengine-core 3.32.16")
    snapshots = {}
    original = engine.totals

    def captured_totals(sim, years):
        totals = original(sim, years)
        policy = list(engine.POLICIES)[len(snapshots)]
        snapshots[policy] = {}
        for year in years:
            tax, spending = engine.fiscal_variables(sim.tax_benefit_system.parameters, year)
            gb = engine.gb_mask(sim, year)
            weighted = {}
            for variable in (*tax, *spending, "household_net_income"):
                series = sim.calculate(variable, year, map_to="household")
                weighted[variable] = np.asarray(series.values, dtype=np.float64) * np.asarray(
                    series.weights.values, dtype=np.float64)
            government = sum((weighted[v] for v in tax), np.zeros(len(gb))) - sum(
                (weighted[v] for v in spending), np.zeros(len(gb)))
            values = {name: sum((weighted[v] for v in variables), np.zeros(len(gb)))
                      for name, variables in FIELDS.items()}
            values.update(gov_balance=government, household_net_income=weighted["household_net_income"])
            for geography, mask in (("uk", np.ones(len(gb), dtype=bool)), ("gb", gb)):
                reported = totals[year] if geography == "uk" else totals[year]["gb"]
                for field, amounts in values.items():
                    if abs(float(amounts[mask].sum()) / 1e9 - reported[field]) > 1e-7:
                        raise RuntimeError("independent household fiscal capture differs from the engine aggregate")
            snapshots[policy][year] = {"gb": gb, "values": values}
        return totals

    engine.totals = captured_totals
    specification = engine._keys_to_int(configuration["specification"])
    dataset = configuration.get("dataset", MICROCOSM)
    full_spec = {**specification, "dataset": dataset, "demography": configuration["treatment"]}
    if "fiscal_output_years" in configuration:
        full_spec["fiscal_output_years"] = configuration["fiscal_output_years"]
    result = engine.run_path(full_spec)
    cells, aggregate_totals, aggregate_saving = {}, {}, {}
    minimum = None
    for year in full_spec.get("fiscal_output_years", engine.HORIZON):
        baseline = snapshots["triple_lock"][year]
        reform = snapshots["burnham_2030"][year]
        if not np.array_equal(baseline["gb"], reform["gb"]):
            raise RuntimeError("policy runs changed the household geography")
        changes = {"gross": baseline["values"]["state_pension_flat_rate"] - reform["values"]["state_pension_flat_rate"],
                   "net": reform["values"]["gov_balance"] - baseline["values"]["gov_balance"]}
        cells[str(year)] = {}
        aggregate_saving[str(year)] = {}
        for geography, mask in (("uk", np.ones(len(baseline["gb"]), dtype=bool)), ("gb", baseline["gb"])):
            policy_cells, saving_cells = {}, {}
            for policy in engine.POLICIES:
                policy_cells[policy] = {}
                aggregate_totals.setdefault(policy, {}).setdefault(str(year), {})[geography] = {}
                for field, amounts in snapshots[policy][year]["values"].items():
                    reported = result["totals_bn"][policy][year]
                    scalar = float(reported[field] if geography == "uk" else reported["gb"][field])
                    count = int(np.count_nonzero(amounts[mask]))
                    policy_cells[policy][field] = supported_cell(count, scalar)
                    aggregate_totals[policy][str(year)][geography][field] = scalar
                    if scalar != 0:
                        minimum = count if minimum is None else min(minimum, count)
            aggregate_saving[str(year)][geography] = {}
            for measure, amounts in changes.items():
                reported = result["saving_bn"][year]
                scalar = float(reported[measure] if geography == "uk" else reported["gb"][measure])
                if abs(float(amounts[mask].sum()) / 1e9 - scalar) > 1e-7:
                    raise RuntimeError("independent policy saving differs from the full engine aggregate")
                count = int(np.count_nonzero(amounts[mask]))
                saving_cells[measure] = supported_cell(count, scalar)
                aggregate_saving[str(year)][geography][measure] = scalar
                if scalar != 0:
                    minimum = count if minimum is None else min(minimum, count)
            cells[str(year)][geography] = {"policies": policy_cells, "saving": saving_cells}
    # Fiscal balances and savings may be signed. Their support receipt reports
    # counts separately; ordinary positive coverage_cell validation does not
    # apply to these signed fiscal quantities.
    support_counts = {year: {geo: {section: {name: ({field: cell["records"] for field, cell in value.items()}
        if section == "policies" else value["records"]) for name, value in sections.items()}
        for section, sections in geographies.items()} for geo, geographies in row.items()}
        for year, row in cells.items()}
    aggregates = {"saving_bn": aggregate_saving, "totals_bn": aggregate_totals}
    fingerprint_years = configuration.get("fingerprint_years", list(full_spec.get("fiscal_output_years", engine.HORIZON)))
    safe = {"label": configuration["label"], "calculation_head": configuration["head"],
            "treatment": configuration["treatment"], "dataset": dataset,
            "dataset_sha256": result["model"]["runtime_dataset_sha256"],
            "packages": packages, "python": sys.version.split()[0], "passed": True,
            "minimum_contributing_records": MIN_RECORDS,
            "minimum_observed_positive_cell_contributors": minimum,
            "cells": support_counts, "aggregates": aggregates,
            "aggregate_sha256": fingerprint(selected_aggregates(aggregates, fingerprint_years)),
            "aggregate_fingerprint_years": fingerprint_years,
            "full_spec_sha256": fingerprint(full_spec), "package_sha256": fingerprint(packages),
            "engine_semantics_sha256": fingerprint(engine.engine_semantics()),
            "engine_file_sha256": digest(Path(engine.__file__)),
            "source_sha256": source_fingerprint(source),
            "driver_sha256": driver_digest,
            "resources_before_actual_job": actual_resources,
            "scientific_check_years": list(engine.HORIZON),
            "calculated_fiscal_years": list(engine.HORIZON),
            "fiscal_output_years": list(full_spec.get("fiscal_output_years", engine.HORIZON)),
            "cold_cache": not (source / ".cache" / "demography").exists()}
    # Coldness is checked before starting the worker; that worker can now have
    # created its new cache. Preserve the coordinator's actual pre-run receipt.
    safe["cold_cache"] = configuration["cold_cache"]
    pipeline.redact_records(safe)
    output.write_text(json.dumps(safe, indent=2, allow_nan=False) + "\n")


def archive_source(workspace, git_dir, head, label):
    source = workspace / ".cache" / "microcosm-check" / f"source-{label}-{head[:7]}"
    if source.exists():
        raise RuntimeError("a cold-check source directory already exists; use a new --run-label")
    source.mkdir(parents=True, mode=0o700)
    archive = subprocess.run(["git", "--git-dir", str(git_dir), "archive", head],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(source, filter="data")
    return source


def resource_receipt():
    import psutil

    memory = psutil.virtual_memory()
    checks = {}
    for command in (("vm_stat",), ("top", "-l", "1", "-n", "0")):
        try:
            completed = subprocess.run(command, capture_output=True, text=True)
            checks[command[0]] = {"exit_code": completed.returncode,
                                  "available": completed.returncode == 0}
        except OSError as error:
            checks[command[0]] = {"exit_code": None, "available": False, "reason": type(error).__name__}
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_bytes": memory.total, "available_bytes": memory.available,
            "logical_cpus": os.cpu_count(), "load_average": list(os.getloadavg()),
            "requested_command_checks": checks}


def write_public(output, runs, resources, historical, correspondence=None, workers=1):
    current = [row for row in runs if row["label"].startswith("current")]
    determinism = compare_runs(*current) if len(current) == 2 else None
    old = json.loads(historical.read_text())
    comparisons = {row["label"]: {"rerun_matches_retained_D_2034_2039": all(
        row["aggregates"]["saving_bn"][str(year)] == old[row["treatment"]]["saving_bn"][str(year)]
        for year in (2034, 2039))} for row in runs if row["label"].startswith("d_")}
    if len(current) == 2:
        comparisons["current_vs_D_both"] = {
            "aggregate_values_changed": current[0]["aggregate_sha256"] != next(
                row["aggregate_sha256"] for row in runs if row["label"].startswith("d_both")),
            "interpretation": "comparison of fresh full-run aggregates; no assumption of unchanged fiscal values"}
    # Replayed quantities are used for exact comparisons in memory. Publishing
    # a second table alongside the retained D table could expose a cross-run
    # numerical difference whose linked support was not measured. Counts and
    # opaque aggregate fingerprints provide the audit without that difference.
    public_runs = [{key: value for key, value in row.items() if key != "aggregates"} for row in runs]
    final_passed = bool(determinism and determinism["passed"] and correspondence and correspondence["passed"])
    value = {"status": ("passed" if final_passed else "failed") if len(runs) == 4 else "in progress",
             "complete": len(runs) == 4, "certified": False, "quote_eligible": False,
             "warning": "pilot on an uncertified data/model pair; not for quoting",
             "minimum_contributing_records": MIN_RECORDS, "runs": public_runs, "resources_before_each_job": resources,
             "determinism": determinism, "comparisons": comparisons,
             "final_head_scientific_source_correspondence": correspondence,
             "retained_D_source_sha256": digest(historical),
             "execution": "four full PolicyEngine UK central path audits, including any explicitly reused "
                          "validated historical audits; fresh interpreter and cold cache for every executed path",
             "maximum_microcosm_workers": workers,
             "scope": "gross/net savings and independent fiscal totals for UK/GB in every forecast year; "
                      "fingerprints cover aggregate quantities only; no survey record is saved or fingerprinted"}
    output.parent.mkdir(parents=True, exist_ok=True)
    from triple_lock.pipeline import redact_records

    redact_records(value)
    output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    if len(runs) == 4 and not determinism["passed"]:
        raise RuntimeError("fresh current-head Microcosm aggregate fingerprints differ")
    if len(runs) == 4 and not (correspondence and correspondence["passed"]):
        raise RuntimeError("the branch scientific sources no longer match the executed cold checks")


def execute_mc_job(plan, args, workspace, data, store, specification):
    label, head, treatment = plan
    resources = {"label": label, **resource_receipt()}
    if resources["available_bytes"] < args.minimum_available_gib * 2**30:
        raise RuntimeError("available host RAM is below the Microcosm headroom requirement")
    source = archive_source(workspace, args.git_dir.resolve(), head, f"{args.run_label}-{label}")
    dataset_store = source / ".cache" / "datasets"
    dataset_store.mkdir(parents=True, mode=0o700)
    os.link(data, dataset_store / data.name)
    cold = not (source / ".cache" / "demography").exists()
    configuration = {"label": label, "head": head, "treatment": treatment, "source": str(source),
                     "specification": specification, "cold_cache": cold,
                     "honour_current_head_control": False,
                     "minimum_available_gib": args.minimum_available_gib}
    input_file = store / f"{args.run_label}-{label}.input.json"
    aggregate_file = store / f"{args.run_label}-{label}.aggregate.json"
    input_file.write_text(json.dumps(configuration))
    private_log = store / f"{args.run_label}-{label}.private.log"
    print(f"Starting full Microcosm {label} at {head}; allocation {args.workers}", flush=True)
    with private_log.open("w") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker",
                                    str(input_file), str(aggregate_file)], stdout=log, stderr=log,
                                   start_new_session=True,
                                   env={**os.environ, "PYTHONPATH": str(source / "src"),
                                        "TRIPLE_LOCK_PARENT_PID": str(os.getpid()),
                                        "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        code = process.wait()
    if code:
        raise RuntimeError(f"Microcosm full path failed; private diagnostics retained in {private_log.name}")
    print(f"Completed full Microcosm {label}; aggregate support passed", flush=True)
    return json.loads(aggregate_file.read_text()), resources


def check_parallel_admission(workers, reuse_historical, resources):
    if workers not in (1, 2):
        raise ValueError("the Microcosm allocation is one or two workers")
    if workers == 2:
        if not reuse_historical:
            raise ValueError("two-worker execution requires validated historical receipts")
        if resources["available_bytes"] < 80 * 2**30:
            raise RuntimeError("two Microcosm workers require at least 80 GiB available RAM")


def main(args):
    os.umask(0o077)
    workspace = Path.cwd().resolve()
    if not args.out.resolve().is_relative_to(workspace):
        raise ValueError("all outputs must stay inside the assigned workspace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.current_head):
        raise ValueError("--current-head must be the full archived commit SHA")
    # Materialise once into the shared store. Authentication stays in the
    # environment and is never written into a configuration, receipt or log.
    sys.path.insert(0, str(workspace / "src"))
    from triple_lock import datasets

    data = datasets.materialize(MICROCOSM, store=workspace / ".cache" / "datasets")
    specifications = json.loads(args.specs.read_text())["central"]
    store = workspace / ".cache" / "microcosm-check"
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    current_plans = (("current_first", args.current_head, "both"), ("current_repeat", args.current_head, "both"))
    plans = current_plans if args.reuse_historical_receipts else (
        ("d_legacy", D_LEGACY, "legacy"), ("d_both", D_BOTH, "both"), *current_plans)
    runs = load_historical_receipts(args.reuse_historical_receipts, workspace) if args.reuse_historical_receipts else []
    admission = resource_receipt()
    check_parallel_admission(args.workers, bool(args.reuse_historical_receipts), admission)
    resources = [{"label": "allocation_admission", **admission}]
    order = {plan[0]: i for i, plan in enumerate(plans)}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(plans), args.workers):
            futures = [pool.submit(execute_mc_job, plan, args, workspace, data, store, specifications)
                       for plan in plans[offset:offset + args.workers]]
            for future in as_completed(futures):
                row, resource = future.result()
                runs.append(row)
                resources.append(resource)
                historical_rows = [row for row in runs if row["label"].startswith("d_")]
                current_rows = sorted((row for row in runs if row["label"].startswith("current")),
                                      key=lambda row: order[row["label"]])
                runs = historical_rows + current_rows
                correspondence = source_correspondence(args.git_dir.resolve(), runs) if len(runs) == 4 else None
                write_public(args.out, runs, resources, args.historical, correspondence, args.workers)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(json.loads(Path(sys.argv[2]).read_text()), Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--git-dir", type=Path, default=Path(".git-e"))
        parser.add_argument("--current-head", required=True)
        parser.add_argument("--run-label", default="final")
        parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
        parser.add_argument("--reuse-historical-receipts", type=Path, nargs=2,
                            help="two completed original-D aggregate-only receipts; run only the new current pair")
        parser.add_argument("--minimum-available-gib", type=float, default=44.)
        parser.add_argument("--specs", type=Path, default=Path(
            "/Users/maxghenis/reviews/uk-triple-lock-2026-09-29/model-v2-integrate/specs.json"))
        parser.add_argument("--historical", type=Path, default=Path(
            "/Users/maxghenis/reviews/uk-triple-lock-2026-09-29/model-v2-integrate/microcosm.json"))
        parser.add_argument("--out", type=Path, default=Path("data/pilot/microcosm_support_and_determinism.json"))
        main(parser.parse_args())
