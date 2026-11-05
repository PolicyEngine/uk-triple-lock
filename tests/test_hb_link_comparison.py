"""Sensitivity-driver invariants without loading a survey."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    "compare_hb_link", Path(__file__).resolve().parents[1] / "scripts/compare_hb_link.py")
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def parameters(values):
    return SimpleNamespace(get_child=lambda path: lambda _: values[path])


def test_whole_cpi_alternative_covers_both_hb_cohorts_and_thresholds():
    paths = [*comparison.HB_PATHS.values(),
             *(p + "_from_cutoff" for p in comparison.HB_PATHS.values()),
             *comparison.SC_PATHS.values()]
    values = {path: 200 + i for i, path in enumerate(paths)}
    model = SimpleNamespace(get_child=lambda path: (
        lambda date: {2026: 100., 2027: 103.1, 2028: 106.193}[int(date[:4])])
        if path == "gov.benefit_uprating_cpi" else lambda _: values[path])
    result = comparison.cpi_levels(model, 2026, [2027, 2028])
    assert set(result) == set(paths)
    for path in paths:
        assert result[path] == pytest.approx({2027: values[path] * 1.031,
                                             2028: values[path] * 1.06193})


@pytest.mark.parametrize("path_index", [1.031, 1.08])
def test_cpi_builder_reads_processed_path_at_amount_application_and_restores(path_index):
    """The default 3.5% model tree cannot supply a path's alternative levels."""
    paths = [*comparison.HB_PATHS.values(),
             *(p + "_from_cutoff" for p in comparison.HB_PATHS.values()),
             *comparison.SC_PATHS.values()]
    calls = []
    original_builder = lambda *args: {"guarantee": {2027: 300}}
    original_setter = lambda simulation, levels, extra=None: calls.append(extra)
    engine = SimpleNamespace(pension_credit_levels=original_builder,
                             set_flat_rates=original_setter, BASE_YEAR=2026, HORIZON=[2027])
    def model(index):
        return SimpleNamespace(get_child=lambda path: (
            lambda date: 1. if int(date[:4]) == 2026 else index)
            if path == "gov.benefit_uprating_cpi" else lambda _: 200.)
    applied = SimpleNamespace(tax_benefit_system=SimpleNamespace(parameters=model(path_index)))
    with pytest.raises(RuntimeError, match="restore after interruption"):
        with comparison.experimental_builder(engine, True, {}, method="cpi"):
            assert engine.pension_credit_levels is original_builder
            guarantees = engine.pension_credit_levels(model(1.035), {}, 3)
            engine.set_flat_rates(applied, {}, guarantees)
            assert calls[0]["guarantee"] == {2027: 300}
            for path in paths:
                assert calls[0][path][2027] == pytest.approx(200 * path_index)
            raise RuntimeError("restore after interruption")
    assert engine.set_flat_rates is original_setter
    assert engine.pension_credit_levels is original_builder


def test_link_grows_only_retained_component_by_nonnegative_statutory_cpi():
    guarantee_paths = {"single": "g.single", "couple": "g.couple"}
    values = {"g.single": 100, "g.couple": 150,
              **dict(zip(comparison.HB_PATHS.values(), (120, 180, 125)))}
    guarantees = {"g.single": {2027: 110, 2028: 121},
                  "g.couple": {2027: 165, 2028: 181.5}}
    result = comparison.linked_levels(parameters(values), guarantees, guarantee_paths,
                                      2026, [2027, 2028], {2026: 0.1, 2027: -0.2})
    assert result[comparison.HB_PATHS["single"]] == {2027: 132, 2028: 143}
    assert result[comparison.HB_PATHS["couple"]] == {2027: 198, 2028: 214.5}
    assert result[comparison.HB_PATHS["lone_parent"]] == {2027: 137.5, 2028: 148.5}
    assert not any("savings_credit" in path for path in result)


@given(gap=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
       cpi=st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False))
def test_linked_allowance_never_below_guarantee(gap, cpi):
    guarantees = {"g": {2027: 200, 2028: 210}}
    values = {"g": 150, **{path: 150 + gap for path in comparison.HB_PATHS.values()}}
    result = comparison.linked_levels(parameters(values), guarantees,
                                      {"single": "g", "couple": "g"}, 2026,
                                      [2027, 2028], {2026: cpi, 2027: cpi})
    assert all(amount >= guarantees["g"][year]
               for levels in result.values() for year, amount in levels.items())


def test_negative_base_component_rejected():
    values = {"g": 200, **{path: 199 for path in comparison.HB_PATHS.values()}}
    with pytest.raises(ValueError, match="below its guarantee"):
        comparison.linked_levels(parameters(values), {"g": {2027: 210}},
                                 {"single": "g", "couple": "g"}, 2026, [2027], {2026: 0})


def test_joint_linked_alternative_covers_both_hb_cohorts_and_both_thresholds():
    guarantees = {"single": "g.single", "couple": "g.couple"}
    values = {"g.single": 100., "g.couple": 150.,
              **dict(zip(comparison.HB_PATHS.values(), (120., 180., 125.))),
              comparison.SC_PATHS["single"]: 80., comparison.SC_PATHS["couple"]: 120.}
    levels = {"g.single": {2027: 110., 2028: 121.},
              "g.couple": {2027: 165., 2028: 181.5}}
    fake_engine = SimpleNamespace(PENSION_CREDIT_GUARANTEE=guarantees, BASE_YEAR=2026,
                                  HORIZON=[2027, 2028], september_cpi=lambda _: {2026: .1, 2027: -.2})
    result = comparison.experimental_levels(fake_engine, parameters(values), levels, {}, "linked")
    assert len(result) == 8
    assert result[comparison.HB_PATHS["single"]] == {2027: 132., 2028: 143.}
    assert result[comparison.HB_PATHS["single"] + "_from_cutoff"] == levels["g.single"]
    assert result[comparison.HB_PATHS["couple"] + "_from_cutoff"] == levels["g.couple"]
    assert result[comparison.HB_PATHS["lone_parent"] + "_from_cutoff"] == levels["g.single"]
    assert result[comparison.SC_PATHS["single"]] == pytest.approx({2027: 88., 2028: 99.})
    assert result[comparison.SC_PATHS["couple"]] == pytest.approx({2027: 132., 2028: 148.5})


def test_builder_restored_even_after_exception():
    original = lambda *_: None
    engine = SimpleNamespace(pension_credit_levels=original)
    with pytest.raises(RuntimeError):
        with comparison.experimental_builder(engine, True, {}):
            assert engine.pension_credit_levels is not original
            raise RuntimeError("synthetic interruption")
    assert engine.pension_credit_levels is original


def contributions(net):
    return {2039: {"gross": np.ones(40), "net": np.asarray(net)}}


@pytest.mark.parametrize("support", [1, 9, 31, 39])
def test_small_effect_support_or_complement_suppresses_whole_family(support):
    current = contributions(np.ones(40))
    linked = contributions(np.ones(40) + (np.arange(40) < support))
    result = comparison.public_comparison(current, linked, {2039: np.ones(40, dtype=bool)})
    assert result["disclosure_status"] == "withheld_linked_family"
    assert all(value is None for measures in result["uk_saving_bn"].values()
               for cells in measures.values() for value in cells.values())


@pytest.mark.parametrize("stage", ["current", "linked", "linked_minus_current"])
@pytest.mark.parametrize("support", [1, 9, 31, 39])
def test_recoverable_offset_support_or_complement_suppresses_whole_family(stage, support):
    small = (np.arange(40) < support).astype(float)
    narrow_offset = {"gross": np.ones(40), "net": np.ones(40) + small}
    broad_offset = {"gross": np.full(40, 3), "net": np.full(40, 5)}
    if stage == "current":
        current, linked = narrow_offset, broad_offset
    elif stage == "linked":
        current, linked = broad_offset, narrow_offset
    else:
        current = {"gross": np.ones(40), "net": np.full(40, 2)}
        linked = {"gross": np.full(40, 2), "net": np.full(40, 3) + small}
    # All published gross/net levels and their sensitivity effects have full
    # support. Only the offset recoverable by subtracting cells is unsafe.
    for measure in ("gross", "net"):
        assert np.count_nonzero(current[measure]) == 40
        assert np.count_nonzero(linked[measure]) == 40
        assert np.count_nonzero(linked[measure] - current[measure]) == 40
    result = comparison.public_comparison({2039: current}, {2039: linked},
                                          {2039: np.ones(40, dtype=bool)})
    assert result["disclosure_status"] == "withheld_linked_family"
    assert all(value is None for measures in result["uk_saving_bn"].values()
               for cells in measures.values() for value in cells.values())


def test_supported_full_run_comparison_exposes_only_aggregate_amounts():
    result = comparison.public_comparison(contributions(np.ones(40)),
        contributions(np.r_[np.full(20, 2), np.ones(20)]), {2039: np.ones(40, dtype=bool)})
    assert result["disclosure_status"] == "available"
    assert result["uk_saving_bn"][2039]["net"] == {
        "current": 40e-9, "linked": 60e-9, "linked_minus_current": 20e-9}
    text = json.dumps(result)
    assert all(key not in text for key in ("household_id", "weight", "records", "single_record"))


def test_zero_weight_records_cannot_supply_support():
    result = comparison.public_comparison(contributions(np.ones(40)), contributions(np.ones(40)),
                                          {2039: np.arange(40) < 3})
    assert result["disclosure_status"] == "withheld_linked_family"


def test_alignment_fingerprint_hashes_equivalent_object_values_not_addresses():
    first = np.asarray(["".join(("BAS", "IC")), "".join(("NE", "W"))], dtype=object)
    second = np.asarray(["".join(("BA", "SIC")), "".join(("N", "EW"))], dtype=object)
    assert comparison.alignment_digest([first]) == comparison.alignment_digest([second])
    second[0] = "NONE"
    assert comparison.alignment_digest([first]) != comparison.alignment_digest([second])


@pytest.fixture(scope="module")
def processed_system():
    pytest.importorskip("policyengine_uk")
    from policyengine_uk import CountryTaxBenefitSystem

    return CountryTaxBenefitSystem()


def test_cpi_alternative_overrides_all_refreshed_dependents(processed_system):
    from policyengine_uk import tax_benefit_system as tbs

    if not all(callable(getattr(tbs, builder, None)) for builder in (
            "project_pension_age_allowances", "project_savings_credit_threshold")):
        pytest.skip("the installed model has no #2576 linked HB/Savings Credit projection builders")
    from triple_lock import engine

    system = processed_system.clone()
    proxy = SimpleNamespace(tax_benefit_system=system)
    earnings = {year: .08 for year in engine.STATUTORY_YEARS}
    guarantees = engine.pension_credit_levels(system.parameters, earnings)
    alternative = comparison.cpi_levels(system.parameters, engine.BASE_YEAR, engine.HORIZON)
    engine.set_flat_rates(proxy, {}, {**guarantees, **alternative})
    for path, levels in {**guarantees, **alternative}.items():
        for year, value in levels.items():
            assert float(system.parameters.get_child(path)(f"{year}-06-01")) == pytest.approx(value, abs=1e-9)


@pytest.mark.parametrize("existing_derived_projection", [False, True])
@settings(max_examples=8, deadline=None)
@given(earnings=st.lists(st.floats(min_value=-0.1, max_value=0.2,
                                allow_nan=False, allow_infinity=False), min_size=13, max_size=13),
       cpi=st.lists(st.floats(min_value=-0.1, max_value=0.2,
                           allow_nan=False, allow_infinity=False), min_size=13, max_size=13))
def test_applied_sensitivity_overrides_processed_forecast_for_every_path_year(
        processed_system, existing_derived_projection, earnings, cpi):
    """A sensitivity invariant, independent of any claim about statutory links.

    The second case emulates a builder that already wrote future HB levels
    while processing parameters. Both cases receive the same subsequent
    per-path amount override, as engine.run_path does; neither loads data.
    """
    from triple_lock import engine

    system = processed_system.clone()
    proxy = SimpleNamespace(tax_benefit_system=system)
    if existing_derived_projection:
        engine.set_flat_rates(proxy, {}, {
            path: {year: 9999.0 for year in engine.HORIZON}
            for path in comparison.HB_PATHS.values()})
    parameters = system.parameters
    spec = {"statutory_earnings": dict(zip(engine.STATUTORY_YEARS, earnings)),
            "statutory_cpi": dict(zip(engine.STATUTORY_YEARS, cpi)),
            "september_cpi_history": {}}
    original_builder = engine.pension_credit_levels
    ordinary = original_builder(parameters, spec["statutory_earnings"])
    with comparison.experimental_builder(engine, True, spec):
        levels = engine.pension_credit_levels(parameters, spec["statutory_earnings"],
                                               engine.CENTRAL_RATE_DECIMALS)
    assert engine.pension_credit_levels is original_builder
    assert set(ordinary) == set(engine.PENSION_CREDIT_GUARANTEE.values())
    assert set(levels) == set(ordinary) | set(comparison.HB_PATHS.values())
    engine.set_flat_rates(proxy, {}, levels)
    for family, path in comparison.HB_PATHS.items():
        guarantee = engine.PENSION_CREDIT_GUARANTEE["couple" if family == "couple" else "single"]
        for year in engine.HORIZON:
            applied_hb = float(parameters.get_child(path)(f"{year}-06-01"))
            applied_guarantee = float(parameters.get_child(guarantee)(f"{year}-06-01"))
            assert applied_hb == pytest.approx(levels[path][year], abs=1e-9)
            assert applied_hb >= applied_guarantee


def test_plan_never_imports_or_runs_model(monkeypatch, capsys):
    import builtins
    original = builtins.__import__

    def safe_import(name, *args, **kwargs):
        if name.startswith(("triple_lock", "policyengine")):
            pytest.fail("plan must not import the engine or a model")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", safe_import)
    assert comparison.main([]) == 0
    assert "no model loaded" in capsys.readouterr().out


def test_output_restricted_to_workspace_cache(tmp_path):
    with pytest.raises(ValueError, match="inside the assigned workspace"):
        comparison.write_receipt(tmp_path / "public.json", {})


def test_host_refusal_writes_receipt_before_loading_parameters_or_data(monkeypatch):
    from triple_lock import central, engine, host, jobs

    def forbidden(*_, **__):
        pytest.fail("a refused run must not construct model parameters or load survey data")

    error = host.HostSaturated("synthetic host refusal")
    error.host_admission = {"admitted": False}

    def refused(*_):
        raise error

    receipts = []
    monkeypatch.setenv("HEAVY_CALLER", "uk-triple-lock")
    monkeypatch.setattr(jobs, "host_admission", refused)
    monkeypatch.setattr(central, "central_path", forbidden)
    monkeypatch.setattr(engine, "model_parameters", forbidden)
    monkeypatch.setattr(engine, "_managed", forbidden)
    monkeypatch.setattr(comparison, "write_receipt", lambda _, receipt: receipts.append(receipt))
    assert comparison.main(["--execute"]) == 75
    assert receipts[0]["status"] == "refused"
    assert receipts[0]["refusal"] == {"admitted": False}
    assert "comparison" not in receipts[0]
