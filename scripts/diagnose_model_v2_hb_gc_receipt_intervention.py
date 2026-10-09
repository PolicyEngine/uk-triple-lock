"""Compare fresh original paths with an HB Guarantee Credit receipt intervention.

This is an explicitly labelled model sensitivity, not a statutory conclusion.
It changes the three HB entitlement passport predicates together, in memory,
and preserves every savings-credit-only branch. No installed source is edited.
Survey arrays remain transient; linked aggregate families are disclosure gated.
"""

import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import psutil


SUPPORT_PATH = Path(__file__).with_name("diagnose_model_v2_gc_precision.py")
SUPPORT_SPEC = importlib.util.spec_from_file_location("hb_receipt_disclosure_helpers", SUPPORT_PATH)
SUPPORT = importlib.util.module_from_spec(SUPPORT_SPEC)
SUPPORT_SPEC.loader.exec_module(SUPPORT)
PATH_INDEX = 39769
HORIZON = list(range(2027, 2040))
ENDPOINTS = (2034, 2039)
REGISTRY_NAME = "h-item4-hb-gc-receipt-intervention.pid.json"
SLOT_NAME = "h-item4-hb-gc-receipt-intervention0"
REGISTRIES = (
    "full_new_net_se_diagnostic_validated.pid.json",
    "h-item4-gc-precision.pid.json",
    REGISTRY_NAME,
)
PASSPORT_MODULES = (
    "variables.gov.dwp.housing_benefit.applicable_income.housing_benefit_applicable_income",
    "variables.gov.dwp.housing_benefit.housing_benefit_assessable_capital",
    "variables.gov.dwp.housing_benefit.applicable_income.housing_benefit_tariff_income",
)
RELATED_FORMULA_FILES = (
    "variables/gov/dwp/pension_credit/guarantee_credit/in_receipt_of_guarantee_credit.py",
    "variables/gov/dwp/pension_credit/savings_credit/in_receipt_of_savings_credit_only.py",
    "variables/gov/dwp/pension_credit/savings_credit/savings_credit.py",
    "variables/gov/dwp/pension_credit/pension_credit.py",
    "variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_savings_credit_only_income.py",
    "variables/gov/dwp/housing_benefit/entitlement/housing_benefit_entitlement.py",
    "variables/gov/dwp/housing_benefit/housing_benefit_eligible.py",
    "variables/gov/dwp/housing_benefit/housing_benefit_pre_benefit_cap.py",
    "variables/gov/dwp/housing_benefit/housing_benefit.py",
)


def transformed_formula(source_bytes, variable_name):
    """Replace exactly one specified predicate; retain all other formula AST."""
    tree = ast.parse(source_bytes)
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == variable_name]
    if len(classes) != 1:
        raise RuntimeError("expected exactly one installed HB variable class")
    formulas = [node for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name == "formula"]
    if len(formulas) != 1:
        raise RuntimeError("expected exactly one installed HB formula")
    formula = deepcopy(formulas[0])
    expected = ast.parse('pension_age_regulations & (benunit("guarantee_credit", period) > 0)', mode="eval").body
    replacement = ast.parse('pension_age_regulations & benunit("in_receipt_of_guarantee_credit", period)', mode="eval").body
    matches = [node for node in ast.walk(formula) if isinstance(node, ast.Assign)
               and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
               and node.targets[0].id == "guarantee_credit"
               and ast.dump(node.value) == ast.dump(expected)]
    if len(matches) != 1:
        raise RuntimeError("installed HB passport predicate differs from the declared intervention")
    matches[0].value = replacement
    ast.fix_missing_locations(formula)
    return formula


def formula_ast_hash(formula):
    return hashlib.sha256(ast.dump(formula).encode()).hexdigest()


def build_receipt_reform():
    """Build isolated override classes from installed formulas, without file writes."""
    from policyengine_core.reforms import Reform

    variables, bindings = [], {}
    for suffix in PASSPORT_MODULES:
        module = importlib.import_module(f"policyengine_uk.{suffix}")
        variable_name = suffix.rsplit(".", 1)[1]
        original_class = getattr(module, variable_name)
        source = Path(module.__file__).read_bytes()
        formula = transformed_formula(source, variable_name)
        namespace = dict(vars(module))
        executable = ast.fix_missing_locations(ast.Module(body=[formula], type_ignores=[]))
        exec(compile(executable, f"<hb-gc-receipt-intervention:{variable_name}>", "exec"), namespace)
        attributes = {name: value for name, value in original_class.__dict__.items()
                      if not name.startswith("__")}
        attributes.update(formula=namespace["formula"], __module__=__name__)
        override = type(variable_name, original_class.__bases__, attributes)
        variables.append(override)
        bindings[suffix.replace(".", "/") + ".py"] = {
            "installed_source_sha256": hashlib.sha256(source).hexdigest(),
            "intervention_formula_ast_sha256": formula_ast_hash(formula),
            "predicate": 'pension_age_regulations & benunit("in_receipt_of_guarantee_credit", period)',
            "replaced_predicate_count": 1,
        }

    class receipt_predicate_reform(Reform):
        def apply(self):
            for variable in variables:
                self.update_variable(variable)

    return receipt_predicate_reform, variables, bindings


def scoped_worker_admission(root, current_pid=None, pid_probe=None):
    """Use explicit task registries and scoped PID probes; never enumerate processes."""
    current_pid = os.getpid() if current_pid is None else current_pid
    pid_probe = SUPPORT.task_pid_is_alive if pid_probe is None else pid_probe
    active, own = {current_pid}, {current_pid}
    for registry_name in REGISTRIES:
        try:
            payload = json.loads((root / ".cache" / registry_name).read_text())
        except FileNotFoundError:
            continue
        except (PermissionError, json.JSONDecodeError):
            raise RuntimeError("task-owned worker registry unavailable") from None
        pid = payload.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise RuntimeError("task-owned worker registry has no valid PID")
        if pid != current_pid:
            try:
                if not pid_probe(pid):
                    continue
            except (PermissionError, psutil.AccessDenied):
                raise RuntimeError("scoped task PID liveness permission unavailable") from None
        active.add(pid)
        if registry_name == REGISTRY_NAME:
            own.add(pid)
    if len(own) > 1 or len(active) > 2:
        raise RuntimeError("task-registered diagnostic worker limit exceeded")
    return {
        "worker_admission_method": "current PID and three explicit task-owned registries; scoped PID existence",
        "checked_registry_paths": [f".cache/{name}" for name in REGISTRIES],
        "task_registered_workers": len(active), "own_workers": len(own),
        "maximum_task_registered_workers": 2, "maximum_own_workers": 1,
        "simulation_serialization": "receipt-intervention, precision and original-correct exclusive slots",
    }


def resource_snapshot(root, stage):
    vm_stat = subprocess.check_output(["vm_stat"], text=True)
    page_match = re.search(r"page size of (\d+) bytes", vm_stat)
    if page_match is None:
        raise RuntimeError("vm_stat page size unavailable")
    pages = []
    for name in ("Pages free", "Pages inactive", "Pages speculative"):
        match = re.search(rf"{name}:\s*(\d+)", vm_stat)
        if match is None:
            raise RuntimeError("vm_stat available-page count unavailable")
        pages.append(int(match[1]))
    snapshot = {
        "at": datetime.now(timezone.utc).isoformat(), "stage": stage,
        "cpu_count": os.cpu_count(), "load": list(os.getloadavg()),
        "available_gib": psutil.virtual_memory().available / 2**30,
        "vm_stat_available_gib": sum(pages) * int(page_match[1]) / 2**30,
        **scoped_worker_admission(root),
    }
    if min(snapshot["available_gib"], snapshot["vm_stat_available_gib"]) < 40:
        raise RuntimeError("less than 40 GiB available RAM")
    SUPPORT.emit(status="resource admission passed", **snapshot)
    return snapshot


def published_vector_family(rows, positive_weights):
    """Suppress all linked monetary/count cells if any support/complement is small.

    Inputs are full-model weighted household contribution vectors, retained only
    transiently. Every row's named stages are linked, as are additive rows and
    both policies. No unsafe numeric aggregate is returned or written.
    """
    positive_weights = np.asarray(positive_weights, dtype=bool)
    total_records = int(np.count_nonzero(positive_weights))
    safe = SUPPORT.supported_count(total_records)
    aggregates = {}
    for name, stages in rows.items():
        aggregates[name] = {}
        for stage, vector in stages.items():
            vector = np.asarray(vector, dtype=np.float64)
            if vector.shape != positive_weights.shape or not np.isfinite(vector).all():
                raise RuntimeError("invalid transient fiscal contribution vector")
            support = int(np.count_nonzero((vector != 0) & positive_weights))
            complement = total_records - support
            safe = safe and all(SUPPORT.supported_count(n) for n in (support, complement))
            aggregates[name][stage] = {
                "support_records": support, "support_complement_records": complement,
                "bn": float(vector[positive_weights].sum() / SUPPORT.BN),
            }
    if not safe:
        aggregates = {name: {stage: {
            "support_records": None, "support_complement_records": None, "bn": None,
        } for stage in stages} for name, stages in rows.items()}
    return {
        "numeric_family_status": "available" if safe else "withheld_linked_family",
        "positive_weight_household_records": total_records if safe else None,
        "rows": aggregates,
    }


def assert_alignment(original, intervention):
    """Assert IDs, cohorts and weights only in memory; return no identifying values."""
    for name in ("household_ids", "household_weights", "person_ids", "age", "pension_type"):
        if not np.array_equal(original[name], intervention[name]):
            raise RuntimeError("original and intervention household/cohort alignment differs")


def variant_key(binding, variant):
    payload = {"kind": "hb_gc_receipt_predicate_sensitivity", "variant": variant, **binding}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def capture_fiscal_arrays(simulation, year, engine):
    def array(variable, map_to=None):
        return np.asarray(simulation.calculate(variable, year, map_to=map_to).to_numpy()).copy()

    weights = np.asarray(simulation.calculate("household_net_income", year).weights.to_numpy(), dtype=np.float64).copy()
    tax, spending = engine.fiscal_variables(simulation.tax_benefit_system.parameters, year)
    balance = sum(array(v, "household").astype(np.float64) for v in tax) - sum(
        array(v, "household").astype(np.float64) for v in spending
    )
    return {
        "household_ids": array("household_id"), "household_weights": weights,
        "person_ids": array("person_id"), "age": array("age"),
        "pension_type": array("state_pension_type"),
        "gov_balance": balance * weights,
        "housing_benefit": array("housing_benefit", "household").astype(np.float64) * weights,
    }


def run_full_variant(engine, template, specification, variant, reform, variables, root, admissions):
    """Run every original year with independent policy clones and transient arrays."""
    original_clone, original_totals = engine._clone_path_template, engine.totals
    policies, contributions = [], []

    def build_clone(pristine):
        clone = original_clone(pristine)
        if variant == "receipt_predicate":
            clone.apply_reform(reform)
            for variable in variables:
                installed = clone.tax_benefit_system.get_variable(variable.__name__)
                if not all(function is variable.formula for function in installed.formulas.values()):
                    raise RuntimeError("receipt override was not installed in the independent clone")
        return clone

    def captured_totals(simulation, years):
        if list(years) != HORIZON:
            raise RuntimeError("the full original fiscal horizon must be calculated")
        totals = {}
        for year in years:
            totals.update(original_totals(simulation, [year]))
            SUPPORT.emit(status="fiscal totals completed", variant=variant, year=year, policy_position=len(policies))
        policies.append({year: capture_fiscal_arrays(simulation, year, engine) for year in ENDPOINTS})
        return totals

    engine._clone_path_template, engine.totals = build_clone, captured_totals
    try:
        admissions.append(resource_snapshot(root, f"immediate full 13-year {variant} path"))
        result = engine.run_path(specification, _support_callback=contributions.append, _template=template)
    finally:
        engine._clone_path_template, engine.totals = original_clone, original_totals
    if len(policies) != 2 or len(contributions) != 1:
        raise RuntimeError("full path did not supply two policies and one paired contribution set")
    return result, policies, contributions.pop()


def comparison_tables(native_arrays, intervention_arrays, native_contributions, intervention_contributions, year):
    native_tl, native_bp = (native_arrays[0][year], native_arrays[1][year])
    variant_tl, variant_bp = (intervention_arrays[0][year], intervention_arrays[1][year])
    for first, second in ((native_tl, native_bp), (native_tl, variant_tl), (native_bp, variant_bp)):
        assert_alignment(first, second)
    positive = native_tl["household_weights"] > 0
    saving_rows = {}
    for measure in ("gross", "net"):
        original = native_contributions[year][measure]
        intervention = intervention_contributions[year][measure]
        saving_rows[measure] = {
            "original": original, "receipt_predicate": intervention, "effect": intervention - original,
        }
    effects = {}
    for policy, first, second in (("triple_lock", native_tl, variant_tl), ("burnham_2030", native_bp, variant_bp)):
        total = second["gov_balance"] - first["gov_balance"]
        hb = -(second["housing_benefit"] - first["housing_benefit"])
        effects[f"{policy}_gov_balance"] = {"effect": total}
        effects[f"{policy}_housing_benefit_gov_balance_component"] = {"effect": hb}
        effects[f"{policy}_other_fiscal_components"] = {"effect": total - hb}
    for component in ("gov_balance", "housing_benefit_gov_balance_component", "other_fiscal_components"):
        effects[f"net_saving_{component}"] = {"effect": (
            effects[f"burnham_2030_{component}"]["effect"] - effects[f"triple_lock_{component}"]["effect"]
        )}
    if not np.allclose(effects["net_saving_gov_balance"]["effect"], saving_rows["net"]["effect"], rtol=0, atol=1e-5):
        raise RuntimeError("paired fiscal contribution identity differs")
    return {
        "saving_comparison": published_vector_family(saving_rows, positive),
        "housing_benefit_and_other_fiscal_intervention_changes": published_vector_family(effects, positive),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--specs", default=Path("data/pilot/d_macro_specs.json"), type=Path)
    parser.add_argument("--fiscal", default=Path("data/pilot/model_v2_e.json"), type=Path)
    parser.add_argument("--treatment", choices=("both", "both_full_new"), default="both")
    parser.add_argument("--out", default=Path("data/pilot/hb_gc_receipt_intervention.json"), type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        SUPPORT.emit(
            status="planned; no model run", path_index=PATH_INDEX, treatment=args.treatment,
            full_path_count=2, independent_policy_calculations=4, fiscal_years=HORIZON,
            original_then_intervention=True, changed_hb_predicates=3, savings_credit_only_branches="preserved",
            registry=f".cache/{REGISTRY_NAME}", slot=SLOT_NAME,
            additional_serial_slots=["h-item4-gc-precision0", "source/h-item4-efrs-correct0"],
            maximum_own_workers=1, output=str(args.out),
            cache_namespace=".cache/h-item4-hb-gc-receipt-intervention/<variant-key>",
            launcher_log=".cache/h-item4-hb-gc-receipt-intervention.log",
        )
        return
    root, source = Path.cwd().resolve(), args.source.resolve()
    cache = (args.cache or source / ".cache/jobs-pilot-e").resolve()
    public = args.out.resolve()
    for path in (source, cache, public, args.specs.resolve(), args.fiscal.resolve()):
        if not path.is_relative_to(root):
            raise RuntimeError("all inputs and outputs must be inside the assigned workspace")
    if public.exists() or not os.environ.get("HUGGING_FACE_TOKEN"):
        raise RuntimeError("output must be new and the launcher must supply the HF token")
    os.umask(0o077)
    admissions = [resource_snapshot(root, "before model imports")]
    sys.path.insert(0, str(source / "src"))
    from triple_lock import engine, jobs, model_horizon

    if not Path(engine.__file__).resolve().is_relative_to(source) or list(engine.HORIZON) != HORIZON:
        raise RuntimeError("incorrect frozen source or horizon")
    if list(engine.POLICIES) != ["triple_lock", "burnham_2030"]:
        raise RuntimeError("unexpected policy order")
    macro = json.loads(args.specs.read_text())["paired"][str(PATH_INDEX)]["spec"]
    cache_file, record = SUPPORT.original_cache_record(cache, macro)
    if engine.engine_semantics() != record["engine"] or engine.package_versions() != record["packages"]:
        raise RuntimeError("original source semantics or packages differ")
    if engine.job_key(record["kind"], record["arg"], record["engine"], record["packages"]) != record["key"]:
        raise RuntimeError("original cache key does not match its input")
    specification = engine._keys_to_int(record["arg"])["specs"][args.treatment]
    retyped = "kept" if args.treatment == "both" else "full_new"
    if specification["demography"] != "both" or specification["retyped_level"] != retyped:
        raise RuntimeError("the original treatment differs")
    recipe_hash, helper_hash = SUPPORT.file_sha256(__file__), SUPPORT.file_sha256(SUPPORT_PATH)
    source_hashes, cache_hash = engine.engine_hashes(), SUPPORT.file_sha256(cache_file)
    input_hashes = {str(path.resolve().relative_to(root)): SUPPORT.file_sha256(path) for path in (args.specs, args.fiscal)}
    reform, variables, formula_bindings = build_receipt_reform()
    package_root = Path(importlib.util.find_spec("policyengine_uk").origin).parent
    formula_hashes = {name: SUPPORT.file_sha256(package_root / name) for name in RELATED_FORMULA_FILES}
    formula_hashes.update({name: binding["installed_source_sha256"] for name, binding in formula_bindings.items()})
    binding = {
        "audit_script_sha256": recipe_hash, "disclosure_helper_sha256": helper_hash,
        "source_files_sha256": source_hashes, "engine_semantics": record["engine"], "packages": record["packages"],
        "original_cache_record_sha256": cache_hash, "original_batch_cache_key": record["key"],
        "input_files_sha256": input_hashes, "installed_formula_source_sha256": formula_hashes,
        "intervention_formulas": formula_bindings, "path_index": PATH_INDEX, "treatment": args.treatment,
        "specification_sha256": hashlib.sha256(engine._canonical(specification).encode()).hexdigest(),
    }
    keys = {variant: variant_key(binding, variant) for variant in ("original", "receipt_predicate")}
    namespace = root / ".cache/h-item4-hb-gc-receipt-intervention" / keys["receipt_predicate"][:24]
    registry = root / ".cache" / REGISTRY_NAME
    original_managed = engine._managed

    def guarded_managed(*positional, **keywords):
        admissions.append(resource_snapshot(root, "immediate dataset load"))
        return original_managed(*positional, **keywords)

    engine._managed = guarded_managed
    try:
        with (
            jobs.slot_lock(root / ".cache/workers" / SLOT_NAME, timeout=0),
            jobs.slot_lock(root / ".cache/workers/h-item4-gc-precision0", timeout=0),
            jobs.slot_lock(source / ".cache/workers/h-item4-efrs-correct0", timeout=0),
            model_horizon.installed(),
        ):
            SUPPORT.write_json(registry, {"pid": os.getpid(), "status": "admitted", "variant_keys": keys, "admissions": admissions})
            template = engine._prepare_path_template(specification)
            native, native_arrays, native_contributions = run_full_variant(
                engine, template, specification, "original", reform, variables, root, admissions
            )
            for year in ENDPOINTS:
                for measure in ("gross", "net"):
                    if abs(native["saving_bn"][year][measure] - record["result"][args.treatment]["saving_bn"][str(year)][measure]) > 0.001:
                        raise RuntimeError("fresh original endpoint does not replay within £1 million")
            intervention, intervention_arrays, intervention_contributions = run_full_variant(
                engine, template, specification, "receipt_predicate", reform, variables, root, admissions
            )
    finally:
        engine._managed = original_managed
    tables = {}
    for year in ENDPOINTS:
        for result, contribution in ((native, native_contributions), (intervention, intervention_contributions)):
            for measure in ("gross", "net"):
                if abs(float(contribution[year][measure].sum() / SUPPORT.BN) - result["saving_bn"][year][measure]) > 1e-6:
                    raise RuntimeError("household contributions differ from full model totals")
        tables[str(year)] = comparison_tables(native_arrays, intervention_arrays, native_contributions, intervention_contributions, year)
    del native, intervention, native_arrays, intervention_arrays, native_contributions, intervention_contributions, template
    if engine.engine_hashes() != source_hashes or engine.engine_semantics() != record["engine"]:
        raise RuntimeError("frozen source changed during the sensitivity")
    if engine.package_versions() != record["packages"] or SUPPORT.file_sha256(__file__) != recipe_hash or SUPPORT.file_sha256(SUPPORT_PATH) != helper_hash:
        raise RuntimeError("recipe, disclosure helper or packages changed during the sensitivity")
    if SUPPORT.file_sha256(cache_file) != cache_hash or any(SUPPORT.file_sha256(root / name) != digest for name, digest in input_hashes.items()):
        raise RuntimeError("original cache or input changed during the sensitivity")
    if any(SUPPORT.file_sha256(package_root / name) != digest for name, digest in formula_hashes.items()):
        raise RuntimeError("installed formula source changed during the sensitivity")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "status": "two fresh full paths; receipt-predicate model sensitivity",
        "full_path_count": 2, "independent_policy_calculations": 4, "fiscal_years_calculated": HORIZON,
        "minimum_records": 10, "original_replay_within_absolute_one_million_pounds": True,
        "binding": binding, "variant_keys": keys, "admissions": admissions, "comparisons": tables,
        "source_head_provenance": json.loads(args.fiscal.read_text())["provenance"]["calculation_head"],
        "method": (
            "One original treatment and macro path, two fresh full thirteen-year paths, each with independent "
            "policy clones of one pristine setup. The intervention replaces only the three Housing Benefit "
            "pension-age positive-entitlement passport predicates with pension-age actual Guarantee Credit "
            "receipt predicates; savings-credit-only branches remain unchanged and are recomputed normally. "
            "Fresh original and intervention household contributions supply all paired supports and complements. "
            "Household/person identity, age, pension type and weights are compared only in memory. Every linked "
            "count and monetary family is withheld together if any support or complement has one to nine "
            "records. HB effects have government-balance sign; other fiscal effects are the residual after HB. "
            "No survey identifier, weight, individual amount or unsafe numeric aggregate is written. This is "
            "an intervention sensitivity, not a statutory conclusion or a numerical-precision correction."
        ),
    }
    SUPPORT.write_json(namespace / "disclosure-checked-comparison.json", payload)
    SUPPORT.write_json(public, payload)
    SUPPORT.write_json(registry, {"pid": os.getpid(), "status": "completed", "variant_keys": keys, "receipt_sha256": SUPPORT.file_sha256(public)})
    SUPPORT.emit(status="receipt intervention completed", receipt=str(public.relative_to(root)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exception:
        SUPPORT.emit(status="receipt intervention stopped; private inputs withheld", error_type=type(exception).__name__)
        raise SystemExit(1) from None
