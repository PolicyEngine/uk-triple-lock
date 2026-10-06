"""Synthetic intervention, binding and disclosure tests; no model simulations."""

import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    "hb_gc_receipt_intervention",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_model_v2_hb_gc_receipt_intervention.py",
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_all_three_installed_predicates_change_and_all_other_ast_is_preserved():
    package = Path(importlib.util.find_spec("policyengine_uk").origin).parent
    original_predicate = ast.parse('pension_age_regulations & (benunit("guarantee_credit", period) > 0)', mode="eval").body
    for suffix in diagnostic.PASSPORT_MODULES:
        variable_name = suffix.rsplit(".", 1)[1]
        source = (package / (suffix.replace(".", "/") + ".py")).read_bytes()
        tree = ast.parse(source)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == variable_name)
        original = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "formula")
        changed = diagnostic.transformed_formula(source, variable_name)
        restored = deepcopy(changed)
        replacement = next(node for node in ast.walk(restored) if isinstance(node, ast.Assign)
                           and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "guarantee_credit")
        replacement.value = deepcopy(original_predicate)
        assert ast.dump(restored) == ast.dump(original)
        assert any(isinstance(node, ast.Constant) and node.value == "in_receipt_of_guarantee_credit" for node in ast.walk(changed))
        assert any(isinstance(node, ast.Constant) and node.value == "in_receipt_of_savings_credit_only" for node in ast.walk(changed))


def test_predicate_change_reads_receipt_and_retains_pension_age_gate():
    source = b'''class example(Variable):
    def formula(benunit, period, parameters):
        pension_age_regulations = benunit("pension_age", period)
        guarantee_credit = pension_age_regulations & (benunit("guarantee_credit", period) > 0)
        return guarantee_credit
'''
    formula = diagnostic.transformed_formula(source, "example")
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[formula], type_ignores=[])), "<synthetic>", "exec"), namespace)
    values = {"pension_age": True, "guarantee_credit": 1, "in_receipt_of_guarantee_credit": False}
    assert namespace["formula"](lambda name, _: values[name], 2039, None) is False
    values["in_receipt_of_guarantee_credit"] = True
    assert namespace["formula"](lambda name, _: values[name], 2039, None) is True
    values["pension_age"] = False
    assert namespace["formula"](lambda name, _: values[name], 2039, None) is False


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_predicates_fail_closed(count):
    assignments = '\n'.join('        guarantee_credit = pension_age_regulations & (benunit("guarantee_credit", period) > 0)' for _ in range(count))
    source = f'class example(Variable):\n    def formula(benunit, period, parameters):\n{assignments}\n        return 0\n'
    with pytest.raises(RuntimeError, match="predicate differs"):
        diagnostic.transformed_formula(source.encode(), "example")


def test_small_effect_suppresses_original_intervention_and_all_linked_rows():
    rows = {
        "gross": {"original": np.ones(40), "receipt_predicate": np.ones(40), "effect": np.zeros(40)},
        "net": {"original": np.ones(40), "receipt_predicate": np.ones(40), "effect": np.r_[np.ones(3), np.zeros(37)]},
    }
    result = diagnostic.published_vector_family(rows, np.ones(40, dtype=bool))
    assert result["numeric_family_status"] == "withheld_linked_family"
    assert all(cell["bn"] is cell["support_records"] is cell["support_complement_records"] is None
               for row in result["rows"].values() for cell in row.values())


def test_small_complement_withholds_otherwise_supported_effect():
    result = diagnostic.published_vector_family({"net": {"effect": np.r_[np.ones(31), np.zeros(9)]}}, np.ones(40, dtype=bool))
    assert result["numeric_family_status"] == "withheld_linked_family"
    assert result["rows"]["net"]["effect"]["bn"] is None


@settings(deadline=None)
@given(size=st.integers(min_value=1, max_value=100), support=st.integers(min_value=0, max_value=100))
def test_every_published_support_and_complement_is_zero_or_ten(size, support):
    vector = (np.arange(size) < support).astype(float)
    result = diagnostic.published_vector_family({"effect": {"effect": vector}}, np.ones(size, dtype=bool))
    for row in result["rows"].values():
        for cell in row.values():
            for key in ("support_records", "support_complement_records"):
                assert cell[key] is None or cell[key] == 0 or cell[key] >= 10


def test_zero_weight_records_do_not_supply_disclosure_support():
    result = diagnostic.published_vector_family({"effect": {"effect": np.ones(40)}}, np.arange(40) < 3)
    assert result["numeric_family_status"] == "withheld_linked_family"


def test_variant_keys_bind_variant_and_formula_content():
    binding = {"source_files_sha256": {"engine.py": "a"}, "intervention_formulas": {"predicate": "receipt"}}
    native = diagnostic.variant_key(binding, "original")
    intervention = diagnostic.variant_key(binding, "receipt_predicate")
    assert native != intervention
    changed = {**binding, "intervention_formulas": {"predicate": "other"}}
    assert intervention != diagnostic.variant_key(changed, "receipt_predicate")


@pytest.mark.parametrize("name", ["household_ids", "household_weights", "person_ids", "age", "pension_type"])
def test_household_and_cohort_misalignment_fails_closed(name):
    first = {field: np.array([1, 2]) for field in ("household_ids", "household_weights", "person_ids", "age", "pension_type")}
    second = {field: value.copy() for field, value in first.items()}
    second[name][0] = 3
    with pytest.raises(RuntimeError, match="alignment differs"):
        diagnostic.assert_alignment(first, second)


def registry(root, name, pid):
    (root / ".cache").mkdir(exist_ok=True)
    (root / ".cache" / name).write_text(json.dumps({"pid": pid}))


def test_owned_registry_guard_ignores_dead_and_deduplicates_self(tmp_path):
    registry(tmp_path, diagnostic.REGISTRIES[0], 101)
    registry(tmp_path, diagnostic.REGISTRY_NAME, 103)
    result = diagnostic.scoped_worker_admission(tmp_path, current_pid=103, pid_probe=lambda _: False)
    assert result["task_registered_workers"] == result["own_workers"] == 1


def test_owned_registry_guard_rejects_another_live_intervention(tmp_path):
    registry(tmp_path, diagnostic.REGISTRY_NAME, 101)
    with pytest.raises(RuntimeError, match="worker limit"):
        diagnostic.scoped_worker_admission(tmp_path, current_pid=103, pid_probe=lambda _: True)


def test_owned_registry_guard_fails_closed_on_denied_scope(tmp_path):
    registry(tmp_path, diagnostic.REGISTRIES[0], 101)

    def denied(_):
        raise PermissionError("synthetic denial")

    with pytest.raises(RuntimeError, match="permission unavailable"):
        diagnostic.scoped_worker_admission(tmp_path, current_pid=103, pid_probe=denied)


def test_resource_guard_uses_no_process_enumeration(tmp_path, monkeypatch):
    def forbidden(*_, **__):
        pytest.fail("global process enumeration is prohibited")

    monkeypatch.setattr(diagnostic.psutil, "process_iter", forbidden)
    monkeypatch.setattr(diagnostic.psutil, "virtual_memory", lambda: SimpleNamespace(available=50 * 2**30))
    monkeypatch.setattr(diagnostic.subprocess, "check_output", lambda *_, **__: (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free: 3276800.\nPages inactive: 0.\nPages speculative: 0.\n"
    ))
    monkeypatch.setattr(diagnostic.SUPPORT, "emit", lambda **_: None)
    result = diagnostic.resource_snapshot(tmp_path, "synthetic admission")
    assert result["task_registered_workers"] == 1


def test_fresh_variant_installs_reform_in_independent_clones_and_calculates_all_years(monkeypatch):
    reform = object()
    applied, calculated = [], []
    formula = lambda: None
    variable = type("example", (), {"formula": formula})

    class Clone:
        def __init__(self):
            self.tax_benefit_system = SimpleNamespace(get_variable=lambda _: SimpleNamespace(formulas={"start": formula}))

        def apply_reform(self, value):
            assert value is reform
            applied.append(self)

    def original_totals(_, years):
        calculated.extend(years)
        return {year: {} for year in years}

    engine = SimpleNamespace(_clone_path_template=lambda _: Clone(), totals=original_totals)

    def run_path(specification, _support_callback, _template):
        engine._clone_path_template(_template)  # independent unreformed setup clone
        for _ in range(2):
            engine.totals(engine._clone_path_template(_template), diagnostic.HORIZON)
        _support_callback({})
        return {}

    engine.run_path = run_path
    monkeypatch.setattr(diagnostic, "resource_snapshot", lambda *_: {})
    monkeypatch.setattr(diagnostic, "capture_fiscal_arrays", lambda *_: {})
    monkeypatch.setattr(diagnostic.SUPPORT, "emit", lambda **_: None)
    _, policies, _ = diagnostic.run_full_variant(engine, {}, {}, "receipt_predicate", reform, [variable], Path.cwd(), [])
    assert len({id(clone) for clone in applied}) == 3
    assert calculated == diagnostic.HORIZON * 2
    assert len(policies) == 2
    assert engine.totals is original_totals
