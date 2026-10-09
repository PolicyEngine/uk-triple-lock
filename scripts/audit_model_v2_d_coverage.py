"""Fresh full archived-D coverage runs with aggregate-only support receipts."""

import contextlib
import gc
import hashlib
import importlib.metadata
import json
import os
import subprocess
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
HEAD = "498d970123adff4e8f05908e17c7b366ba71a28c"
MACRO_SPECS = ROOT / "data" / "pilot" / "d_macro_specs.json"
SPECS = engine._keys_to_int(json.loads(MACRO_SPECS.read_text()))
ORIGINAL = json.loads((ROOT / "data" / "pilot" / "coverage_gb_dwp.json").read_text())["model"]
OUT = ROOT / "data" / "pilot"
YEARS = [2026, 2027, 2028, 2029, 2030, 2034, 2039]
original_coverage_stats = engine.coverage_stats


def hashed(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array(sim, variable, year):
    return np.asarray(sim.calculate(variable, year).to_numpy())


def audited_stats(sim, year):
    out = original_coverage_stats(sim, year)
    gb = {entity: engine.gb_mask(sim, year, entity) for entity in ("person", "benunit", "household")}
    sp_age = array(sim, "is_SP_age", year).astype(bool)
    pensioner_unit = sim.map_result(sp_age.astype(float), "person", "benunit") > 0
    pa_rules = array(sim, "housing_benefit_pension_age_regulations_apply", year).astype(bool)
    types = array(sim, "state_pension_type", year).astype(str)
    variables = {
        "state_pension_bn": "state_pension", "basic_state_pension_bn": "basic_state_pension",
        "new_state_pension_bn": "new_state_pension", "additional_state_pension_bn": "additional_state_pension",
        "state_pension_recipients": "state_pension", "pension_credit_bn": "pension_credit",
        "guarantee_credit_bn": "guarantee_credit", "savings_credit_bn": "savings_credit",
        "pension_credit_benefit_units": "pension_credit", "housing_benefit_bn": "housing_benefit",
        "housing_benefit_benefit_units": "housing_benefit", "housing_benefit_pension_age_bn": "housing_benefit",
        "housing_benefit_pension_age_benefit_units": "housing_benefit",
        "housing_benefit_pensioner_benefit_units_bn": "housing_benefit",
        "council_tax_reduction_bn": "council_tax_benefit", "universal_credit_bn": "universal_credit",
    }
    arrays = {v: array(sim, v, year) for v in set(variables.values())}
    for geo in ("uk", "gb"):
        def within(entity):
            return gb[entity] if geo == "gb" else np.ones_like(gb[entity], dtype=bool)

        counts = {}
        for field, variable in variables.items():
            entity = sim.tax_benefit_system.variables[variable].entity.key
            mask = within(entity) & (arrays[variable] > 0)
            if field.startswith("housing_benefit_pension_age"):
                mask &= pa_rules
            elif field == "housing_benefit_pensioner_benefit_units_bn":
                mask &= pensioner_unit
            counts[field] = int(mask.sum())
        counts["state_pension_age_people"] = int((within("person") & sp_age).sum())
        counts["people"] = int(within("person").sum())
        counts["pension_type_people"] = {kind: int((within("person") & (types == kind)).sum())
                                         for kind in out[geo]["pension_type_people"]}
        out[geo]["contributor_support"] = counts
    return out


engine.coverage_stats = audited_stats


def validate(table):
    checked = 0
    minimum_positive = None
    for by_geo in table.values():
        for cell in by_geo.values():
            for metric, support in cell["contributor_support"].items():
                values = cell[metric] if isinstance(support, dict) else {metric: cell[metric]}
                counts = support if isinstance(support, dict) else {metric: support}
                for name, count in counts.items():
                    value = values[name]
                    if value != 0:
                        if count < 10:
                            raise RuntimeError("Aggregate support audit found a nonzero cell below ten records")
                        minimum_positive = count if minimum_positive is None else min(minimum_positive, count)
                    elif count == 0:
                        pass
                    checked += 1
    return {"passed": True, "minimum_contributing_records": 10,
            "minimum_observed_positive_cell_contributors": minimum_positive, "metrics_checked": checked}


def same_retained_both(table):
    wanted = ORIGINAL
    for year, by_geo in table.items():
        for geo, row in by_geo.items():
            comparable = {key: value for key, value in row.items()
                          if key not in ("contributor_support", "households_by_country")}
            if comparable != wanted[year][geo]:
                return False
    return True


def run(dataset, treatment):
    label = f"{dataset}-{treatment}"
    arg = {"years": YEARS, "september_cpi_history": SPECS["september_cpi_history"],
           "spec": SPECS["central"], "dataset": dataset, "demography": treatment}
    private = ROOT / ".cache" / f"d-support-{label}.private.log"
    print(f"starting archived D coverage {label}", flush=True)
    try:
        with private.open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            result = engine.run_coverage(arg)
            table = {str(y): {geo: {key: value for key, value in row.items() if key != "households_by_country"}
                             for geo, row in geographies.items()}
                     for y, geographies in result["by_year"].items()}
            proof = validate(table)
    except BaseException:
        with private.open("a") as log:
            traceback.print_exc(file=log)
        print(f"archived D coverage failed; private diagnostics retained at {private.name}", flush=True)
        raise SystemExit(1) from None
    same = same_retained_both(table) if treatment == "both" else None
    receipt = {"dataset": dataset, "policyengine_uk": importlib.metadata.version("policyengine-uk"),
               "policyengine_core": importlib.metadata.version("policyengine-core"),
               "calculation_head": HEAD, "treatment": treatment, "years": YEARS,
               "coverage": table, "support_audit": proof, "matches_retained_D_both_exactly": same,
               "dataset_sha256": result["model"]["runtime_dataset_sha256"]}
    OUT.mkdir(parents=True, exist_ok=True)
    part = ROOT / ".cache" / f"d-support-{label}.aggregate.json"
    part.write_text(json.dumps(redact_records(receipt), indent=2, allow_nan=False) + "\n")
    print(f"completed archived D coverage {label}; support passed; retained comparison={same}", flush=True)
    gc.collect()
    return receipt


def main():
    todo = [("enhanced_frs_2024_25@1.56.16", "legacy"), ("enhanced_frs_2024_25@1.56.16", "both"),
            ("enhanced_frs_2024_25@1.57.4", "legacy")]
    runs = []
    for dataset, treatment in todo:
        subprocess.run([sys.executable, str(Path(__file__)), "--single", dataset, treatment], check=True)
        runs.append(json.loads((ROOT / ".cache" / f"d-support-{dataset}-{treatment}.aggregate.json").read_text()))
        receipt = {
            "status": "coverage support audited; fiscal-path and Microcosm support pending",
            "certified": False, "quote_eligible": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "calculation_head": HEAD,
            "policyengine_uk": importlib.metadata.version("policyengine-uk"),
            "policyengine_core": importlib.metadata.version("policyengine-core"),
            "driver_sha256": hashed(Path(__file__)),
            "archived_engine_sha256": hashed(SOURCE / "src" / "triple_lock" / "engine.py"),
            "macro_specs_sha256": hashed(MACRO_SPECS),
            "minimum_contributing_records": 10,
            "scope": "Positive contributor counts for each coverage programme aggregate in UK and GB, "
                     "central triple-lock path, all retained D coverage years; no record identifiers, weights or amounts. "
                     "This does not audit fiscal-path treatment differences or Microcosm.",
            "runs": runs,
        }
        (OUT / "d_support_audit.json").write_text(json.dumps(redact_records(receipt), indent=2, allow_nan=False) + "\n")
    print("all archived D coverage support runs completed", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--single":
        run(sys.argv[2], sys.argv[3])
    else:
        main()
