"""Archived-D full simulations for retained fiscal years; private arrays are discarded after aggregate support counts."""

import contextlib
import hashlib
import importlib.metadata
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache" / "pilot-d-source"
sys.path.insert(0, str(SOURCE / "src"))
import numpy as np
from triple_lock import engine
from triple_lock.pipeline import redact_records

assert Path(engine.__file__).resolve().is_relative_to(SOURCE)
MACRO_SPECS = ROOT / "data" / "pilot" / "d_macro_specs.json"
SPECS = engine._keys_to_int(json.loads(MACRO_SPECS.read_text()))
HEAD = "498d970123adff4e8f05908e17c7b366ba71a28c"
PRIMARY = "enhanced_frs_2024_25@1.56.16"
NEWER = "enhanced_frs_2024_25@1.57.4"
STORE = ROOT / ".cache" / "d-fiscal-full-reuse-support"
FIELDS = {"state_pension_flat_rate": ("basic_state_pension", "new_state_pension"),
          "additional_state_pension": ("additional_state_pension",),
          "pension_credit": ("pension_credit",), "housing_benefit": ("housing_benefit",),
          "council_tax_reduction": ("council_tax_benefit",), "universal_credit": ("universal_credit",),
          "income_tax": ("income_tax",)}
YEARS = (2034, 2039)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def support(values, scalar, context=""):
    count = int(np.count_nonzero(values))
    if 0 < count < 10:
        raise RuntimeError("A published fiscal cell has fewer than ten contributing households: " + context)
    return count


def input_digest(sim):
    """One hash of supplied data inputs; neither inputs nor per-record hashes are returned."""
    digest = hashlib.sha256()
    for variable, branch, period in sorted(sim._user_input_keys, key=lambda key: tuple(map(str, key))):
        value = sim.get_holder(variable)._memory_storage.get(period, branch)
        if value is not None:
            array = np.asarray(value)
            digest.update(str((variable, branch, period, array.dtype.str, array.shape)).encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


def parameter_snapshot(sim):
    paths = {*engine.FLAT_RATE_PARAMETERS.values(), *engine.PENSION_CREDIT_GUARANTEE.values(),
             *(entry[0] for entry in engine.PATH_PARAMETERS.values())}
    return {(path, year): float(sim.tax_benefit_system.parameters.get_child(path)(f"{year}-06-01"))
            for path in sorted(paths) for year in (engine.BASE_YEAR, *engine.HORIZON)}


def validate_clone(pristine, sim):
    """Check real parameter/input isolation without releasing private arrays."""
    assert sim.tax_benefit_system is not pristine.tax_benefit_system
    assert sim.tax_benefit_system.parameters is not pristine.tax_benefit_system.parameters
    assert sim._user_input_keys == pristine._user_input_keys and sim._user_input_keys is not pristine._user_input_keys
    assert sim._user_input_contexts == pristine._user_input_contexts and sim._user_input_contexts is not pristine._user_input_contexts
    assert all(sim.populations[name] is not pristine.populations[name] for name in sim.populations)
    count = 0
    for variable, branch, period in pristine._user_input_keys:
        left = pristine.get_holder(variable)._memory_storage.get(period, branch)
        right = sim.get_holder(variable)._memory_storage.get(period, branch)
        if left is not None:
            assert right is not None and not np.shares_memory(left, right)
            assert np.array_equal(left, right, equal_nan=np.asarray(left).dtype.kind in "fc")
            count += 1
    before = input_digest(sim)
    sim.input_variables = list(sim.input_variables)
    sim._invalidate_all_caches()
    assert sim.invalidated_caches is not pristine.invalidated_caches
    assert input_digest(sim) == before == input_digest(pristine)
    path = engine.FLAT_RATE_PARAMETERS["new_state_pension"]
    probe = sim.tax_benefit_system.parameters.get_child(path)
    original = pristine.tax_benefit_system.parameters.get_child(path)
    assert probe is not original
    value = float(probe("2034-06-01"))
    original_value = float(original("2034-06-01"))
    history = [entry.clone() for entry in probe.values_list]
    probe.update(period="year:2034:1", value=value + 1)
    sim.tax_benefit_system.reset_parameter_caches()
    assert float(original("2034-06-01")) == original_value
    probe.values_list = history
    sim.tax_benefit_system.reset_parameter_caches()
    return count


def run_original_path(spec):
    """Original full archived-D call order, with independent pristine policy clones."""
    original_managed = engine._managed
    pristine = None
    pristine_inputs, pristine_parameters = None, None
    clone_checks = {}
    started = time.monotonic()

    def managed(dataset=None, **kwargs):
        nonlocal pristine, pristine_inputs, pristine_parameters
        if pristine is None:
            sim = original_managed(dataset, **kwargs)
            pristine = sim.clone()
            pristine.baseline = None
            pristine.tax_benefit_system.simulation = pristine
            pristine_inputs, pristine_parameters = input_digest(pristine), parameter_snapshot(pristine)
            print(f"D full audit {spec['demography']}: pristine loaded; {time.monotonic() - started:.1f}s",
                  file=sys.__stdout__, flush=True)
            return sim
        sim = pristine.clone()
        sim.baseline = None
        sim.tax_benefit_system.simulation = sim
        policy = list(engine.POLICIES)[len(clone_checks)]
        clone_checks[policy] = validate_clone(pristine, sim)
        print(f"D full audit {spec['demography']}: {policy} independent pristine clone; "
              f"{time.monotonic() - started:.1f}s", file=sys.__stdout__, flush=True)
        return sim

    engine._managed = managed
    try:
        result = engine.run_path(spec)
        assert input_digest(pristine) == pristine_inputs
        assert parameter_snapshot(pristine) == pristine_parameters
        result['checks'].update({'pristine_policy_clone_inputs_checked': clone_checks,
                                 'pristine_template_unmutated': True,
                                 'full_fiscal_calculation_years': list(engine.HORIZON)})
        print(f"D full audit {spec['demography']}: all original full-year outputs complete; "
              f"{time.monotonic() - started:.1f}s", file=sys.__stdout__, flush=True)
        return result
    finally:
        engine._managed = original_managed


def worker(job, conn):
    """No arrays are ever written; only trusted in-memory IPC returns private snapshots to this coordinator."""
    os.umask(0o077)
    label = job["label"]
    private_log = STORE / f"{label}-{job['treatment']}.private.log"
    snapshots = {}
    original = engine.totals

    def captured_totals(sim, years):
        result = original(sim, years)
        policy = list(engine.POLICIES)[len(snapshots)]
        snapshots[policy] = {}
        for year in years:
            tax, spending = engine.fiscal_variables(sim.tax_benefit_system.parameters, year)
            gb = engine.gb_mask(sim, year)
            weighted = {}
            for variable in (*tax, *spending, "household_net_income"):
                series = sim.calculate(variable, year, map_to="household")
                weighted[variable] = (np.asarray(series.values, dtype=np.float64)
                                      * np.asarray(series.weights.values, dtype=np.float64))
            government = sum((weighted[v] for v in tax), np.zeros(len(gb))) \
                - sum((weighted[v] for v in spending), np.zeros(len(gb)))
            fields = {name: sum((weighted[v] for v in variables), np.zeros(len(gb)))
                      for name, variables in FIELDS.items()}
            values = {"gov_balance": government, "household_net_income": weighted["household_net_income"], **fields}
            for geo, mask in (("uk", np.ones(len(gb), dtype=bool)), ("gb", gb)):
                expected = result[year] if geo == "uk" else result[year]["gb"]
                for name, value in values.items():
                    if abs(float(value[mask].sum()) / 1e9 - expected[name]) > 1e-7:
                        raise RuntimeError("Independent fiscal snapshot does not match the full-model aggregate")
            snapshots[policy][str(year)] = {"gb": gb, "values": values}
        return result

    engine.totals = captured_totals
    try:
        with private_log.open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = run_original_path({**job["spec"], "dataset": job["dataset"], "demography": job["treatment"]})
            redact_records(result)
            result.pop("largest_household", None)
            result.pop("concentration_by_year", None)
            cells = {}
            changes = {}
            withheld = []
            minimum = None
            for year in map(str, YEARS):
                baseline = snapshots["triple_lock"][year]
                reform = snapshots["burnham_2030"][year]
                assert np.array_equal(baseline["gb"], reform["gb"])
                changes[year] = {
                    "gross": baseline["values"]["state_pension_flat_rate"] - reform["values"]["state_pension_flat_rate"],
                    "net": reform["values"]["gov_balance"] - baseline["values"]["gov_balance"],
                    "household_income": reform["values"]["household_net_income"] - baseline["values"]["household_net_income"],
                    **{field: reform["values"][field] - baseline["values"][field]
                       for field in FIELDS if field not in ("state_pension_flat_rate", "additional_state_pension")
                       and label in ("central", "newer_central")},
                }
                cells[year] = {}
                for geo, mask in (("uk", np.ones(len(baseline["gb"]), dtype=bool)), ("gb", baseline["gb"])):
                    counts = {"policies": {}, "saving": {}}
                    for policy, snapshot in snapshots.items():
                        counts["policies"][policy] = {}
                        for field, amounts in snapshot[year]["values"].items():
                            aggregate = float(amounts[mask].sum()) / 1e9
                            n = support(amounts[mask], aggregate, f"{year}/{geo}/{policy}/{field}")
                            counts["policies"][policy][field] = n
                            if aggregate:
                                minimum = n if minimum is None else min(minimum, n)
                    for measure, amounts in changes[year].items():
                        if geo == "gb" and measure not in ("gross", "net", "household_income"):
                            continue  # Retained GB fiscal tables publish gross/net, not these component changes.
                        aggregate = float(amounts[mask].sum()) / 1e9
                        if measure not in ("gross", "net", "household_income") and 0 < np.count_nonzero(amounts[mask]) < 10:
                            withheld.append({"year": int(year), "geography": geo, "measure": measure})
                            continue
                        n = support(amounts[mask], aggregate, f"{year}/{geo}/saving/{measure}")
                        counts["saving"][measure] = n
                        if aggregate:
                            minimum = n if minimum is None else min(minimum, n)
                        if measure in ("gross", "net"):
                            scalar = result["saving_bn"][int(year)]
                            expected = scalar[measure] if geo == "uk" else scalar["gb"][measure]
                            if abs(aggregate - expected) > 1e-7:
                                raise RuntimeError("Independent policy saving differs from the model's aggregate")
                    cells[year][geo] = counts
            aggregates = {
                "saving_bn": {str(year): {geo: {measure: result["saving_bn"][year][measure]
                                                     if geo == "uk" else result["saving_bn"][year]["gb"][measure]
                                               for measure in ("gross", "net")}
                                           for geo in ("uk", "gb")} for year in YEARS},
                "totals_bn": {policy: {str(year): {geo: {field: result["totals_bn"][policy][year][field]
                                                               if geo == "uk" else result["totals_bn"][policy][year]["gb"][field]
                                                         for field in FIELDS}
                                               for geo in ("uk", "gb")} for year in YEARS}
                              for policy in engine.POLICIES},
            }
            safe = {"label": label, "treatment": job["treatment"], "dataset": job["dataset"],
                    "dataset_sha256": result["model"]["runtime_dataset_sha256"],
                    "fiscal_output_years": list(YEARS), "macro_and_input_years": list(engine.HORIZON),
                    "withheld_component_changes": withheld,
                    "checks": result["checks"],
                    "full_spec_sha256": canonical_hash({**job["spec"], "dataset": job["dataset"],
                                                         "demography": job["treatment"]}),
                    "passed": True, "minimum_contributing_records": 10,
                    "minimum_observed_positive_cell_contributors": minimum, "cells": cells, "aggregates": aggregates}
        # Private arrays are sent only on an anonymous local pipe; no result file, cache or log holds them.
        conn.send({"safe": safe, "private": {"policy": snapshots, "saving": changes}})
    except BaseException as error:
        with private_log.open("a") as log:
            traceback.print_exc(file=log)
        conn.send({"error": type(error).__name__, "private_diagnostic": private_log.name})
    finally:
        conn.close()


def execute(job):
    print(f"starting D fiscal support {job['label']} {job['treatment']}", flush=True)
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(job, child))
    process.start()
    child.close()
    value = parent.recv()
    parent.close()
    process.join()
    if "error" in value:
        raise RuntimeError(f"D support job failed safely: {value['error']}; {value['private_diagnostic']}")
    if job["label"] == "central":
        (STORE / f"central-{job['treatment']}.aggregate.json").write_text(
            json.dumps(value["safe"], indent=2, allow_nan=False) + "\n")
    print(f"completed D fiscal support {job['label']} {job['treatment']}", flush=True)
    return value


def treatment_contrasts(legacy, both):
    counts = {}
    minimum = None
    for year in legacy["saving"]:
        gb = legacy["policy"]["triple_lock"][year]["gb"]
        assert np.array_equal(gb, both["policy"]["triple_lock"][year]["gb"])
        counts[year] = {}
        for geo, mask in (("uk", np.ones(len(gb), dtype=bool)), ("gb", gb)):
            out = {"saving": {}, "policies": {}}
            for measure in legacy["saving"][year]:
                if measure not in ("gross", "net", "household_income"):
                    continue  # No component treatment contrasts are retained in D's integrated table.
                delta = both["saving"][year][measure] - legacy["saving"][year][measure]
                n = support(delta[mask], float(delta[mask].sum()), f"{year}/{geo}/treatment/saving/{measure}")
                out["saving"][measure] = n
                if np.any(delta[mask]):
                    minimum = n if minimum is None else min(minimum, n)
            for policy in engine.POLICIES:
                out["policies"][policy] = {}
                for field in legacy["policy"][policy][year]["values"]:
                    delta = both["policy"][policy][year]["values"][field] \
                        - legacy["policy"][policy][year]["values"][field]
                    n = support(delta[mask], float(delta[mask].sum()), f"{year}/{geo}/treatment/{policy}/{field}")
                    out["policies"][policy][field] = n
                    if np.any(delta[mask]):
                        minimum = n if minimum is None else min(minimum, n)
            counts[year][geo] = out
    return {"passed": True, "minimum_contributing_records": 10,
            "minimum_observed_positive_cell_contributors": minimum, "cells": counts}


def calibrate_central(safe):
    """Refuse the abbreviated workload unless retained fiscal aggregates are exact."""
    full_path = ROOT / ".cache" / "d-fiscal-support" / "central.aggregate.json"
    full = json.loads(full_path.read_text())[safe["treatment"]]
    assert safe["dataset_sha256"] == full["dataset_sha256"]
    assert safe["full_spec_sha256"] == full["full_spec_sha256"]
    assert safe["aggregates"]["saving_bn"] == full["aggregates"]["saving_bn"], \
        "Selected-output savings differ from the original full-output simulation"
    count = 8
    for policy, years in full["aggregates"]["totals_bn"].items():
        for geo, fields in years["2039"].items():
            for field, expected in fields.items():
                assert safe["aggregates"]["totals_bn"][policy]["2039"][geo][field] == expected, \
                    "Selected-output policy total differs from the original full-output simulation"
                count += 1
    path = STORE / "calibration.aggregate.json"
    receipt = json.loads(path.read_text()) if path.exists() else {
        "full_output_recipe": "scripts/audit_model_v2_d_fiscal_full.py",
        "full_output_recipe_sha256": digest(ROOT / "scripts" / "audit_model_v2_d_fiscal_full.py"),
        "full_output_receipt_sha256": digest(full_path),
        "calculation_head": HEAD,
        "changed_workload": "The original archived-D full run_path call order and all thirteen fiscal years "
                            "are evaluated. Each policy is an independent pristine same-path simulation clone. "
                            "Only the published aggregate support receipt is selected to 2034 and 2039.",
        "treatments": {},
    }
    receipt["treatments"][safe["treatment"]] = {"passed": True, "comparison": "exact Python scalar equality",
                                               "aggregate_cells_checked": count,
                                               "dataset_sha256": safe["dataset_sha256"],
                                               "full_spec_sha256": safe["full_spec_sha256"]}
    path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")


def write_receipt(pairs, singles, complete=False):
    value = {"status": "passed" if complete else "in progress", "complete": complete,
             "certified": False, "quote_eligible": False, "generated_at": datetime.now(timezone.utc).isoformat(),
             "calculation_head": HEAD, "policyengine_uk": importlib.metadata.version("policyengine-uk"),
             "policyengine_core": importlib.metadata.version("policyengine-core"), "python": sys.version.split()[0],
             "driver_sha256": digest(Path(__file__)),
             "archived_engine_sha256": digest(SOURCE / "src" / "triple_lock" / "engine.py"),
             "macro_specs_sha256": digest(MACRO_SPECS), "minimum_contributing_records": 10,
             "execution": "One fresh spawned Python process per full path; one Enhanced FRS worker maximum. "
                          "Each policy is an independent clone of a pristine same-path data-input template.",
             "scope": "Full fiscal policy cells and policy savings for retained fiscal years 2034 and 2039, UK and GB, plus exact "
                      "same-year both-minus-legacy contrasts for central and all forty original paired draws. "
                      "Private weighted household vectors travel over an anonymous pipe and are discarded. "
                      "Every original full-year fiscal, poverty, income and distribution calculation follows the archived "
                      "run_path call order. Retained bridge component changes are checked for UK only. "
                      "No unpublished GB component changes, cross-year contrasts or Microcosm support are claimed.",
             "fiscal_output_years": list(YEARS), "macro_and_input_years": list(engine.HORIZON),
             "calibration": json.loads((STORE / "calibration.aggregate.json").read_text()),
             "pairs": pairs, "extra_legacy": singles}
    (ROOT / "data" / "pilot" / "d_fiscal_support_audit.json").write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    os.umask(0o077)
    STORE.mkdir(parents=True, exist_ok=True)
    pairs, singles = [], []
    plans = [("central", SPECS["central"]),
             *((f"draw_{index}", entry["spec"]) for index, entry in sorted(SPECS["paired"].items()))]
    for label, spec in plans:
        saved = STORE / f"{label}.aggregate.json"
        if saved.exists():
            pair = json.loads(saved.read_text())
            assert pair["driver_sha256"] == digest(Path(__file__))
        else:
            legacy = execute({"label": label, "spec": spec, "dataset": PRIMARY, "treatment": "legacy"})
            if label == "central":
                calibrate_central(legacy["safe"])
            both = execute({"label": label, "spec": spec, "dataset": PRIMARY, "treatment": "both"})
            if label == "central":
                calibrate_central(both["safe"])
            contrast = treatment_contrasts(legacy["private"], both["private"])
            pair = {"label": label, "driver_sha256": digest(Path(__file__)),
                    "legacy": legacy["safe"], "both": both["safe"], "both_minus_legacy_support": contrast}
            del legacy, both
            saved.write_text(json.dumps(pair, indent=2, allow_nan=False) + "\n")
        pairs.append(pair)
        write_receipt(pairs, singles)
    extras = {**SPECS["ev"], **SPECS["concentrated"]}
    for index, entry in sorted(extras.items()):
        if index in SPECS["paired"]:
            continue
        label = f"bridge_draw_{index}"
        saved = STORE / f"{label}.aggregate.json"
        if saved.exists():
            safe = json.loads(saved.read_text())
            assert safe["driver_sha256"] == digest(Path(__file__))
        else:
            result = execute({"label": label, "spec": entry["spec"], "dataset": PRIMARY, "treatment": "legacy"})
            safe = {**result["safe"], "driver_sha256": digest(Path(__file__))}
            del result
            saved.write_text(json.dumps(safe, indent=2, allow_nan=False) + "\n")
        singles.append(safe)
        write_receipt(pairs, singles)
    # The newer-data central fiscal column is part of the original D bridge too.
    result = execute({"label": "newer_central", "spec": SPECS["central"], "dataset": NEWER, "treatment": "legacy"})
    singles.append(result["safe"])
    del result
    result = execute({"label": "obr_premium", "spec": SPECS["obr_premium"], "dataset": PRIMARY, "treatment": "legacy"})
    singles.append(result["safe"])
    del result
    write_receipt(pairs, singles, complete=True)
    print("all retained D Enhanced FRS fiscal support paths complete", flush=True)


if __name__ == "__main__":
    main()
