"""Installed-model identities after the engine's amount setter; no survey data."""

import importlib.util
import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

from hypothesis import example, given, settings, strategies as st
import pytest


pytest.importorskip("policyengine_uk")

from triple_lock import engine, rules  # noqa: E402


import policyengine_uk.tax_benefit_system as tbs

pytestmark = pytest.mark.skipif(
    not callable(getattr(tbs, "project_savings_credit_threshold", None))
    or not callable(getattr(tbs, "project_pension_age_allowances", None)),
    reason="the installed model has no #2576 linked SC/HB projection builders")


SPEC = importlib.util.spec_from_file_location(
    "pension_credit_upstream", Path(__file__).resolve().parents[1] / "scripts/check_pension_credit_upstream.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


@pytest.fixture(scope="module")
def parameters():
    return engine.model_parameters()


@pytest.fixture(scope="module")
def processed_path(parameters):
    """Process a real central Scenario before loading one invented household.

    The standalone CLI separately checks three complete pre-load macro
    Scenarios. Here each generated guarantee path deliberately diverges from
    this processed tree, testing the engine's subsequent amount override.
    """
    return check.build(check.specifications()["central"], parameters)


nonnegative = st.lists(st.one_of(
    st.sampled_from([0.0, 0.0005, 0.0245, 0.0325, 0.0805]),
    st.floats(min_value=0, max_value=0.2, allow_nan=False, allow_infinity=False)),
    min_size=len(check.YEARS), max_size=len(check.YEARS))


@settings(max_examples=12, deadline=None)
@given(earnings=nonnegative)
@example(earnings=[0.0805] * 14)
@example(earnings=[0.0] * 14)
def test_derived_identities_for_every_year_both_rules_and_nonnegative_paths(parameters, processed_path, earnings):
    """Earnings ties expose the installed/engine rounding difference (#2576).

    Both rules must use the same guarantee and its dependent amounts, even
    when their State Pension rates differ. Include the explicit 2040 boundary
    beyond the engine's final fiscal year, without changing the frozen horizon.
    """
    spec = check.specifications()["central"]
    spec.update(statutory_earnings=dict(zip((year - 1 for year in check.YEARS), earnings)),
                earnings=dict(zip(engine.CALENDAR_YEARS, earnings)))
    guarantees = check.guarantees(parameters, spec)
    _, _, rates = engine.spec_rates(spec)
    previous = None
    for policy in engine.POLICIES:
        sim = SimpleNamespace(tax_benefit_system=processed_path.tax_benefit_system.clone())
        flat = {kind: rules.level_path(base, rates[policy], engine.HORIZON)
                for kind, base in engine.base_levels(parameters).items()}
        engine.set_flat_rates(sim, flat, guarantees)
        p = sim.tax_benefit_system.parameters
        applied = {}
        for year in check.YEARS:
            at = f"{year}-06-01"
            applied[year] = {}
            pc = p.gov.dwp.pension_credit
            for family, path in engine.PENSION_CREDIT_GUARANTEE.items():
                guarantee = float(p.get_child(path)(at))
                applied[year][family] = guarantee
                assert guarantee == pytest.approx(guarantees[path][year], abs=1e-9)
                maximum = float(pc.savings_credit.maximum.children[family.upper()](at))
                threshold = float(pc.savings_credit.threshold.children[family.upper()](at))
                assert (guarantee - threshold) * pc.savings_credit.rate.phase_in(at) == pytest.approx(maximum, abs=1e-9)
            for kind, family in check.FAMILIES.items():
                guarantee = applied[year][family]
                maximum = float(pc.savings_credit.maximum.children[family.upper()](at))
                for cohort in ("aged", "aged_from_cutoff"):
                    allowance = float(p.get_child(f"gov.dwp.housing_benefit.allowances.{kind}.{cohort}")(at))
                    assert allowance == pytest.approx(guarantee + (maximum if cohort == "aged" else 0), abs=1e-9)
                    assert allowance >= guarantee
        if previous is not None:
            assert applied == previous
        previous = applied


def test_explicit_sensitivity_amounts_win_per_year(parameters):
    spec = check.specifications()["high_earnings"]
    sim = check.build(spec, parameters)
    guarantees = check.guarantees(parameters, spec)
    hb = "gov.dwp.housing_benefit.allowances.single.aged"
    threshold = "gov.dwp.pension_credit.savings_credit.threshold.SINGLE"
    engine.set_flat_rates(sim, {}, {**guarantees, hb: {2028: 777}, threshold: {2029: 123}})
    p = sim.tax_benefit_system.parameters
    assert p.get_child(hb)("2028-06-01") == 777
    assert p.get_child(threshold)("2029-06-01") == 123
    for year in (2027, 2030, 2040):
        at = f"{year}-06-01"
        guarantee = p.get_child(engine.PENSION_CREDIT_GUARANTEE["single"])(at)
        maximum = p.gov.dwp.pension_credit.savings_credit.maximum.SINGLE(at)
        assert p.get_child(hb)(at) == pytest.approx(guarantee + maximum, abs=1e-9)
        assert p.get_child(threshold)(at) == pytest.approx(guarantee - maximum / 0.6, abs=1e-9)
