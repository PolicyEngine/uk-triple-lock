"""Fresh archived-D paths, aggregate support only; arrays travel over an anonymous pipe and are discarded."""

import contextlib
import hashlib
import importlib.metadata
import json
import multiprocessing as mp
import os
import sys
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
STORE = ROOT / ".cache" / "d-fiscal-support"
FIELDS = {"state_pension_flat_rate": ("basic_state_pension", "new_state_pension"),
          "additional_state_pension": ("additional_state_pension",),
          "pension_credit": ("pension_credit",), "housing_benefit": ("housing_benefit",)}
YEARS = (2034, 2039)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def support(values, scalar):
    count = int(np.count_nonzero(values))
    if scalar != 0 and count < 10:
        raise RuntimeError("A positive published fiscal cell has fewer than ten contributing households")
    return count


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
            result = engine.run_path({**job["spec"], "dataset": job["dataset"], "demography": job["treatment"]})
            redact_records(result)
            result.pop("largest_household", None)
            result.pop("concentration_by_year", None)
            cells = {}
            changes = {}
            minimum = None
            for year in map(str, engine.HORIZON):
                baseline = snapshots["triple_lock"][year]
                reform = snapshots["burnham_2030"][year]
                assert np.array_equal(baseline["gb"], reform["gb"])
                changes[year] = {
                    "gross": baseline["values"]["state_pension_flat_rate"] - reform["values"]["state_pension_flat_rate"],
                    "net": reform["values"]["gov_balance"] - baseline["values"]["gov_balance"],
                    "household_income": reform["values"]["household_net_income"] - baseline["values"]["household_net_income"],
                }
                cells[year] = {}
                for geo, mask in (("uk", np.ones(len(baseline["gb"]), dtype=bool)), ("gb", baseline["gb"])):
                    counts = {"policies": {}, "saving": {}}
                    for policy, snapshot in snapshots.items():
                        counts["policies"][policy] = {}
                        for field, amounts in snapshot[year]["values"].items():
                            aggregate = float(amounts[mask].sum()) / 1e9
                            n = support(amounts[mask], aggregate)
                            counts["policies"][policy][field] = n
                            if aggregate:
                                minimum = n if minimum is None else min(minimum, n)
                    for measure, amounts in changes[year].items():
                        aggregate = float(amounts[mask].sum()) / 1e9
                        n = support(amounts[mask], aggregate)
                        counts["saving"][measure] = n
                        if aggregate:
                            minimum = n if minimum is None else min(minimum, n)
                        if measure != "household_income":
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
                                               for geo in ("uk", "gb")} for year in (2030, 2039)}
                              for policy in engine.POLICIES},
            }
            safe = {"label": label, "treatment": job["treatment"], "dataset": job["dataset"],
                    "dataset_sha256": result["model"]["runtime_dataset_sha256"],
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
                delta = both["saving"][year][measure] - legacy["saving"][year][measure]
                n = support(delta[mask], float(delta[mask].sum()))
                out["saving"][measure] = n
                if np.any(delta[mask]):
                    minimum = n if minimum is None else min(minimum, n)
            for policy in engine.POLICIES:
                out["policies"][policy] = {}
                for field in legacy["policy"][policy][year]["values"]:
                    delta = both["policy"][policy][year]["values"][field] \
                        - legacy["policy"][policy][year]["values"][field]
                    n = support(delta[mask], float(delta[mask].sum()))
                    out["policies"][policy][field] = n
                    if np.any(delta[mask]):
                        minimum = n if minimum is None else min(minimum, n)
            counts[year][geo] = out
    return {"passed": True, "minimum_contributing_records": 10,
            "minimum_observed_positive_cell_contributors": minimum, "cells": counts}


def write_receipt(pairs, singles, complete=False):
    value = {"status": "passed" if complete else "in progress", "complete": complete,
             "certified": False, "quote_eligible": False, "generated_at": datetime.now(timezone.utc).isoformat(),
             "calculation_head": HEAD, "policyengine_uk": importlib.metadata.version("policyengine-uk"),
             "policyengine_core": importlib.metadata.version("policyengine-core"), "python": sys.version.split()[0],
             "driver_sha256": digest(Path(__file__)),
             "archived_engine_sha256": digest(SOURCE / "src" / "triple_lock" / "engine.py"),
             "macro_specs_sha256": digest(MACRO_SPECS), "minimum_contributing_records": 10,
             "execution": "One fresh spawned Python process per full path; one Enhanced FRS worker maximum",
             "scope": "Full fiscal policy cells and policy savings for all forecast years, UK and GB, plus exact "
                      "same-year both-minus-legacy contrasts for central and all forty original paired draws. "
                      "Private weighted household vectors travel over an anonymous pipe and are discarded. "
                      "No cross-year contrasts or Microcosm support are claimed.",
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
            both = execute({"label": label, "spec": spec, "dataset": PRIMARY, "treatment": "both"})
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
