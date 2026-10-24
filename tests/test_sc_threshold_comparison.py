"""Savings Credit sensitivity properties and applied parameters; no survey loads."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest

from triple_lock import engine


SPEC = importlib.util.spec_from_file_location(
    "sc_threshold_comparison", Path(__file__).resolve().parents[1] / "scripts/compare_hb_link.py")
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def base_parameters():
    values = {engine.PENSION_CREDIT_GUARANTEE["single"]: 238,
              engine.PENSION_CREDIT_GUARANTEE["couple"]: 363.25,
              comparison.SC_PATHS["single"]: 208.07,
              comparison.SC_PATHS["couple"]: 329.75}
    return SimpleNamespace(get_child=lambda path: lambda _: values[path])


growth = st.lists(st.one_of(st.sampled_from([0, 0.0005, 0.0015, 0.0025, 0.0315]),
                           st.floats(min_value=0, max_value=0.2, allow_nan=False, allow_infinity=False)),
                  min_size=13, max_size=13)


@settings(max_examples=80, deadline=None)
@given(earnings=growth, cpi=growth)
def test_implied_maximum_grows_by_exact_rounded_nonnegative_cpi(earnings, cpi):
    parameters = base_parameters()
    spec = {"statutory_earnings": dict(zip(engine.STATUTORY_YEARS, earnings)),
            "statutory_cpi": dict(zip(engine.STATUTORY_YEARS, cpi)), "september_cpi_history": {}}
    guarantees = engine.pension_credit_levels(parameters, spec["statutory_earnings"])
    levels = comparison.experimental_levels(engine, parameters, guarantees, spec, "sc-threshold")
    assert set(levels) == set(comparison.SC_PATHS.values())
    assert not set(levels) & set(comparison.HB_PATHS.values())
    for family, base_maximum in (("single", 17.96), ("couple", 20.10)):
        previous_maximum = base_maximum
        for year, raw_cpi in zip(engine.HORIZON, cpi):
            guarantee = guarantees[engine.PENSION_CREDIT_GUARANTEE[family]][year]
            threshold = levels[comparison.SC_PATHS[family]][year]
            implied_maximum = 0.6 * (guarantee - threshold)
            rounded_cpi = float(engine.rules.round_rate(raw_cpi, engine.CENTRAL_RATE_DECIMALS))
            assert implied_maximum >= 0
            assert implied_maximum == pytest.approx(previous_maximum * (1 + rounded_cpi), rel=1e-10, abs=1e-10)
            assert implied_maximum / previous_maximum - 1 == pytest.approx(rounded_cpi, abs=1e-10)
            if implied_maximum > 0:
                assert threshold < guarantee
            previous_maximum = implied_maximum


@pytest.mark.parametrize("guarantee,threshold,expected", [
    (238, 208.07, 17.96), (363.25, 329.75, 20.10), (100.025, 100, 0.02), (238, 238, 0)])
def test_base_maximum_rounds_decimal_pennies_half_up(guarantee, threshold, expected):
    assert comparison.rounded_savings_credit_maximum(guarantee, threshold) == expected


def test_negative_base_maximum_is_rejected():
    with pytest.raises(ValueError, match="above its guarantee"):
        comparison.rounded_savings_credit_maximum(238, 239)


def test_negative_cpi_does_not_cut_the_projected_maximum():
    parameters = base_parameters()
    earnings = {year: 0 for year in engine.STATUTORY_YEARS}
    guarantees = engine.pension_credit_levels(parameters, earnings)
    levels = comparison.savings_credit_threshold_levels(
        parameters, guarantees, engine.PENSION_CREDIT_GUARANTEE, engine.BASE_YEAR, engine.HORIZON,
        {year: -0.1 for year in engine.STATUTORY_YEARS})
    for family, maximum in (("single", 17.96), ("couple", 20.10)):
        for year in engine.HORIZON:
            g = guarantees[engine.PENSION_CREDIT_GUARANTEE[family]][year]
            assert 0.6 * (g - levels[comparison.SC_PATHS[family]][year]) == pytest.approx(maximum)


@pytest.fixture(scope="module")
def processed_system():
    pytest.importorskip("policyengine_uk")
    from policyengine_uk import CountryTaxBenefitSystem

    return CountryTaxBenefitSystem()


def central_spec():
    from triple_lock import central, trajectories

    return trajectories.central_spec(central.central_path())


@pytest.mark.parametrize("existing_projection", [False, True])
def test_applied_sc_thresholds_follow_formula_and_leave_hb_unchanged(processed_system, existing_projection):
    import json

    system = processed_system.clone()
    proxy = SimpleNamespace(tax_benefit_system=system)
    if existing_projection:
        engine.set_flat_rates(proxy, {}, {path: {year: 9999 for year in engine.HORIZON}
                                         for path in comparison.SC_PATHS.values()})
    parameters = system.parameters
    spec = central_spec()
    # Compare with the ordinary current engine after its guarantee override:
    # that override now also keeps both pension-age HB cohorts consistent.
    engine.set_flat_rates(proxy, {}, engine.pension_credit_levels(parameters, spec["statutory_earnings"]))
    before_hb = {path: {year: float(parameters.get_child(path)(f"{year}-06-01")) for year in engine.HORIZON}
                 for path in comparison.HB_PATHS.values()}
    original = engine.pension_credit_levels
    with comparison.experimental_builder(engine, True, spec, method="sc-threshold"):
        levels = engine.pension_credit_levels(parameters, spec["statutory_earnings"], engine.CENTRAL_RATE_DECIMALS)
    assert engine.pension_credit_levels is original
    assert set(levels) == set(engine.PENSION_CREDIT_GUARANTEE.values()) | set(comparison.SC_PATHS.values())
    engine.set_flat_rates(proxy, {}, levels)
    comparison.check_applied_levels(engine, parameters, engine.HORIZON, spec, "sc-threshold")
    # Cross-check against the separately committed parameter-only calculation.
    root = Path(__file__).resolve().parents[1]
    central = json.loads((root / "data/diagnostics/pension_age_allowances.json").read_text())["paths"][0]
    for family, path in comparison.SC_PATHS.items():
        assert parameters.get_child(path)("2039-06-01") == pytest.approx(
            central["parameters"][f"savings_threshold_{family}"]["component_option_weekly"], abs=1e-9)
    for path, years in before_hb.items():
        for year, amount in years.items():
            assert float(parameters.get_child(path)(f"{year}-06-01")) == amount


@pytest.mark.parametrize("family,year", [("single", 2027), ("couple", 2039)])
def test_runtime_readback_rejects_an_unapplied_threshold(processed_system, family, year):
    system = processed_system.clone()
    proxy = SimpleNamespace(tax_benefit_system=system)
    spec = central_spec()
    guarantees = engine.pension_credit_levels(system.parameters, spec["statutory_earnings"])
    levels = comparison.experimental_levels(engine, system.parameters, guarantees, spec, "sc-threshold")
    engine.set_flat_rates(proxy, {}, {**guarantees, **levels})
    comparison.check_applied_levels(engine, system.parameters, engine.HORIZON, spec, "sc-threshold")
    path = comparison.SC_PATHS[family]
    engine.set_flat_rates(proxy, {}, {path: {year: levels[path][year] + 1}})
    with pytest.raises(engine.PathNotFollowed, match=f"Savings Credit threshold was not applied in {year}"):
        comparison.check_applied_levels(engine, system.parameters, engine.HORIZON, spec, "sc-threshold")


def test_sc_builder_restores_the_engine_after_interruption():
    original = lambda *_: None
    stub = SimpleNamespace(pension_credit_levels=original)
    with pytest.raises(RuntimeError):
        with comparison.experimental_builder(stub, True, {}, method="sc-threshold"):
            raise RuntimeError("synthetic interruption")
    assert stub.pension_credit_levels is original


def test_sc_plan_does_not_import_or_run_a_model(monkeypatch, capsys):
    import builtins

    original = builtins.__import__

    def no_model(name, *args, **kwargs):
        if name.startswith(("triple_lock", "policyengine")):
            pytest.fail("the plan must not import or run a model")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_model)
    assert comparison.main(["--method", "sc-threshold"]) == 0
    assert "sc-threshold" in capsys.readouterr().out


def test_sc_flag_routes_fresh_pairs_and_uses_a_separate_private_receipt(monkeypatch):
    from triple_lock import jobs

    calls, receipts = [], []

    def fake_variant(_engine, spec, enabled, fingerprints, positive, method="hb"):
        calls.append((enabled, method))
        positive.update({year: np.ones(40, dtype=bool) for year in engine.HORIZON})
        net = np.r_[np.full(20, 2), np.ones(20)] if enabled else np.ones(40)
        return {year: {"gross": np.ones(40), "net": net} for year in engine.HORIZON}, {"synthetic": True}

    def forbidden(*_, **__):
        pytest.fail("a routing test must not execute a survey simulation")

    monkeypatch.setenv("HEAVY_CALLER", "uk-triple-lock")
    monkeypatch.setattr(jobs, "host_admission", lambda *_: {"admitted": True})
    monkeypatch.setattr(engine, "run_path", forbidden)
    monkeypatch.setattr(comparison, "run_variant", fake_variant)
    monkeypatch.setattr(comparison, "write_receipt", lambda path, payload: receipts.append((path, payload)))
    assert comparison.main(["--execute", "--method", "sc-threshold"]) == 0
    assert calls == [(False, "hb"), (True, "sc-threshold")]
    path, receipt = receipts[0]
    assert path.name == "sc-threshold-comparison.json"
    assert receipt["method"] == "sc-threshold" and receipt["status"] == "completed"
    assert receipt["housing_benefit_allowances"] == "unchanged"
    assert receipt["comparison"]["disclosure_status"] == "available"
    assert receipt["cached_results_reused"] is False and receipt["full_pair_count"] == 2
