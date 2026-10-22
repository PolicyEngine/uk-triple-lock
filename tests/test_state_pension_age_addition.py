"""Version-aware State Pension accounting on small formula stubs, never survey data.

The stub mirrors #2340's annual age/type/report eligibility and its legislated
data-year exclusion. It deliberately has its own additional-pension formula:
the engine's explicit inputs must take precedence over that formula.
"""

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

pytest.importorskip("policyengine_uk")
from policyengine_uk.model_api import WEEKS_IN_YEAR  # noqa: E402

from triple_lock import demography, engine  # noqa: E402
from triple_lock.config import DEMOGRAPHY_MODES, HORIZON  # noqa: E402

DATA_YEAR = 2024
ADDITION = "state_pension_age_addition"
CAPS = {"BASIC": 176.45 * WEEKS_IN_YEAR, "NEW": 230.25 * WEEKS_IN_YEAR}


class Series:
    def __init__(self, values):
        self.values = np.asarray(values)
        self.weights = SimpleNamespace(values=np.ones(len(self.values)))

    def to_numpy(self):
        return self.values

    def sum(self):
        return self.values.sum()


class Parameters:
    def __init__(self, addition_amount=0.25, addition_age=80):
        pension = SimpleNamespace(
            basic_state_pension=SimpleNamespace(amount=lambda period: CAPS["BASIC"] / WEEKS_IN_YEAR),
            new_state_pension=SimpleNamespace(amount=lambda period: CAPS["NEW"] / WEEKS_IN_YEAR),
            age_addition=SimpleNamespace(amount=lambda period: addition_amount, age=lambda period: addition_age),
        )
        self.gov = SimpleNamespace(dwp=SimpleNamespace(state_pension=pension))

    def __call__(self, period):
        return self

    def get_child(self, path):
        values = {
            "gov.contrib.abolish_council_tax": False,
            "gov.contrib.abolish_state_pension": False,
            "gov.contrib.cec.state_pension_increase": 0,
            "gov.contrib.benefit_uprating.all": 0,
            "gov.contrib.benefit_uprating.non_sp": 0,
        }
        return lambda instant: values[path]


class Model:
    """One person per household/benefit unit, with optional #2340 formulas."""

    def __init__(self, profiles, addition=True, flat_factor=1.0):
        self.ages = np.array([row[0] for row in profiles], dtype=float)
        self.types = np.array([row[1] for row in profiles])
        self.reported = np.array([row[2] for row in profiles], dtype=float)
        self.dataset = SimpleNamespace(years=[DATA_YEAR])
        self.baseline = None
        self.flat_factor = flat_factor
        self.inputs = {}
        self.has_addition = addition
        variables = [*engine.STATE_PENSION_PARTS, "state_pension", "state_pension_reported", "age",
                     "is_SP_age", "state_pension_type", "person_weight", "household_weight", "country",
                     "pension_credit", "guarantee_credit", "savings_credit", "housing_benefit",
                     "housing_benefit_pension_age_regulations_apply", "council_tax_benefit", "universal_credit"]
        self.tax_benefit_system = SimpleNamespace(
            parameters=Parameters(),
            variables={name: SimpleNamespace(entity=SimpleNamespace(key="person"))
                       for name in [*variables, *([ADDITION] if addition else [])]},
        )
        self.populations = {entity: SimpleNamespace(project=lambda values: values, any=lambda values: values)
                            for entity in ("household", "benunit", "person")}

    def set_input(self, variable, year, values):
        self.inputs[variable, year] = np.asarray(values).copy()

    def array(self, variable, year):
        return self.calculate(variable, year).to_numpy()

    def split_reported(self):
        reported = self.array("state_pension_reported", DATA_YEAR)
        if not self.has_addition:
            return reported
        legislated = (self.baseline if self.baseline is not None else self).tax_benefit_system.parameters
        p = legislated(DATA_YEAR).gov.dwp.state_pension.age_addition
        receives = ((self.array("state_pension_type", DATA_YEAR) == "BASIC") &
                    (self.array("age", DATA_YEAR) >= p.age(DATA_YEAR)) & (reported > 0))
        return np.maximum(reported - receives * p.amount(DATA_YEAR) * WEEKS_IN_YEAR, 0)

    def calculate(self, variable, year, **kwargs):
        if (variable, year) in self.inputs:
            return Series(self.inputs[variable, year])
        if variable == "state_pension_reported":
            return Series(self.reported)
        if variable == "age":
            return Series(self.ages)
        if variable == "state_pension_type":
            return Series(self.types)
        if variable == "is_SP_age":
            return Series(self.array("age", year) >= 66)
        if variable in ("person_weight", "household_weight"):
            return Series(np.ones(len(self.ages)))
        if variable == "country":
            return Series(np.full(len(self.ages), "ENGLAND"))
        if variable in ("basic_state_pension", "new_state_pension"):
            kind = "BASIC" if variable == "basic_state_pension" else "NEW"
            factor = self.flat_factor if year != DATA_YEAR else 1
            return Series(np.where(self.array("state_pension_type", year) == kind,
                                   np.minimum(self.split_reported(), CAPS[kind]) * factor, 0))
        if variable == "additional_state_pension":
            # A new upstream uprating formula must still lose to set_input.
            return Series(np.full(len(self.ages), 999_999.0))
        if variable == ADDITION and self.has_addition:
            p = self.tax_benefit_system.parameters(year).gov.dwp.state_pension.age_addition
            entitled = ((self.array("state_pension_reported", DATA_YEAR) > 0) |
                        (self.array("basic_state_pension", year) +
                         self.array("additional_state_pension", year) > 0))
            return Series((self.array("state_pension_type", year) == "BASIC") *
                          (self.array("age", year) >= p.age(year)) * entitled * p.amount(year) * WEEKS_IN_YEAR)
        if variable == "state_pension":
            return Series(sum(self.array(name, year) for name in engine.state_pension_parts(self)))
        if variable in self.tax_benefit_system.variables:
            return Series(np.zeros(len(self.ages)))
        raise KeyError(variable)

    def map_result(self, values, source, target):
        return values


@st.composite
def profiles(draw):
    ages = draw(st.lists(st.integers(18, 105), min_size=1, max_size=10))
    rows = []
    for age in ages:
        kind = draw(st.sampled_from(["BASIC", "NEW"])) if age >= 66 else "NONE"
        reported = draw(st.integers(0, 2_000_000)) / 100
        rows.append((age, kind, reported))
    return rows


def treatment(sim, years, mode, anchor=None):
    """Small population stand-in: held ages, and cohort types in the named modes."""
    out = demography.Population(age={y: sim.ages.copy() for y in years})
    out.survey_types = sim.types.copy()
    out.over_pension_age = {y: sim.ages >= 66 for y in years}
    out.types = {y: (np.where((sim.types == "BASIC") & (sim.ages < 90), "NEW", sim.types)
                     if mode in ("types", "both") and y >= 2034 else sim.types.copy()) for y in years}
    for name, by_year in out.items():
        for year, values in by_year.items():
            sim.set_input(name, year, values)
    return out


@settings(max_examples=80, deadline=None)
@given(profiles())
@example([(79, "BASIC", 12_000), (80, "BASIC", 12_000), (95, "NEW", 12_000),
          (80, "BASIC", 0), (80, "BASIC", 1), (55, "NONE", 12_000)])
def test_person_identity_and_age_type_report_rules_in_every_treatment(rows):
    """The fourth part replaces the included addition, including reports below it."""
    sep = {y: .02 for y in range(DATA_YEAR, max(HORIZON))}
    for mode in DEMOGRAPHY_MODES:
        with patch.object(demography, "population", treatment):
            pinned, _ = engine.pinned_inputs(Model(rows), HORIZON, sep, mode)
        sim = Model(rows)
        engine.pin(sim, pinned)
        payable = np.where(sim.ages >= 66, sim.reported, 0)
        np.testing.assert_allclose(sim.array("state_pension", DATA_YEAR), payable, rtol=0, atol=.01)
        assert engine.state_pension_accounting(sim, pinned)["max_identity_error_gbp"] <= .01
        eligible = (sim.types == "BASIC") & (sim.ages >= 80) & (payable > 0)
        expected = np.minimum(payable, eligible * .25 * WEEKS_IN_YEAR)
        np.testing.assert_array_equal(sim.array(ADDITION, DATA_YEAR), expected)
        needs_pin = np.any(eligible & (payable < .25 * WEEKS_IN_YEAR))
        assert (ADDITION in pinned) == needs_pin
        if needs_pin:
            assert set(pinned[ADDITION]) == {DATA_YEAR}


@settings(max_examples=60, deadline=None)
@given(rows=profiles(), cpi=st.lists(st.floats(-.1, .2, allow_nan=False, allow_infinity=False),
                                   min_size=max(HORIZON) - DATA_YEAR,
                                   max_size=max(HORIZON) - DATA_YEAR),
       factor=st.floats(.5, 1.5, allow_nan=False, allow_infinity=False))
def test_age_addition_is_equal_under_both_rules_on_every_path_and_year(rows, cpi, factor):
    """Path CPI and any flat-rate change leave the addition and its saving at zero."""
    sep = dict(zip(range(DATA_YEAR, max(HORIZON)), cpi, strict=True))
    for mode in DEMOGRAPHY_MODES:
        with patch.object(demography, "population", treatment):
            pinned, _ = engine.pinned_inputs(Model(rows), HORIZON, sep, mode)
        baseline, policy = Model(rows), Model(rows, flat_factor=factor)
        engine.pin(baseline, pinned)
        engine.pin(policy, pinned)
        for year in HORIZON:
            left, right = baseline.array(ADDITION, year), policy.array(ADDITION, year)
            assert left.tobytes() == right.tobytes()
            assert (left - right).sum() == 0
        assert engine.additional_pension_followed(baseline, pinned, HORIZON) <= .01
        assert engine.additional_pension_followed(policy, pinned, HORIZON) <= .01


@settings(max_examples=100, deadline=None)
@given(rows=profiles(), cpi=st.floats(-.1, .2, allow_nan=False, allow_infinity=False))
def test_missing_variable_preserves_previous_pinned_arrays_byte_for_byte(rows, cpi):
    """Independent copy of the previous accounting, including operation order."""
    sim = Model(rows, addition=False)
    sep = {y: cpi for y in range(DATA_YEAR, max(HORIZON))}
    pinned, _ = engine.pinned_inputs(sim, HORIZON, sep, "legacy")
    payable = np.where(sim.ages >= 66, sim.reported, 0.0)
    expected = {"state_pension_reported": {DATA_YEAR: payable},
                "state_pension_type": {}, "additional_state_pension": {}}
    index = 1.0
    for year in range(DATA_YEAR, max(HORIZON) + 1):
        if year > DATA_YEAR:
            index *= 1 + max(sep[year - 1], 0.0)
        if year in (DATA_YEAR, *HORIZON):
            kind = np.where(sim.ages >= 66, sim.types, "NONE")
            basic = np.where(kind == "BASIC", np.minimum(payable, CAPS["BASIC"]), 0)
            new = np.where(kind == "NEW", np.minimum(payable, CAPS["NEW"]), 0)
            additional = np.where(kind != "NONE", np.maximum(payable - basic - new, 0), 0)
            expected["state_pension_type"][year] = kind
            expected["additional_state_pension"][year] = additional * index * (sim.ages >= 66)
    assert set(pinned) == set(expected)
    for variable, by_year in expected.items():
        assert set(pinned[variable]) == set(by_year)
        for year, values in by_year.items():
            actual = pinned[variable][year]
            assert actual.dtype == values.dtype
            assert actual.tobytes() == values.tobytes(), (variable, year)
    assert engine.state_pension_parts(sim) == engine.STATE_PENSION_PARTS
    engine.pin(sim, pinned)
    assert engine.state_pension_accounting(sim, pinned)["max_identity_error_gbp"] <= .01


def test_exclusion_uses_legislated_data_year_age_addition_parameters():
    sim = Model([(80, "BASIC", 12_000), (79, "BASIC", 12_000), (80, "NEW", 12_000)])
    sim.baseline = Model([(80, "BASIC", 12_000)] * 3)
    legislated = sim.baseline.tax_benefit_system.parameters.gov.dwp.state_pension.age_addition
    legislated.amount = lambda year: .25 if year == DATA_YEAR else .75
    legislated.age = lambda year: 80 if year == DATA_YEAR else 79
    sim.tax_benefit_system.parameters = Parameters(addition_amount=.5, addition_age=79)
    pinned, _ = engine.pinned_inputs(sim, [2027], {y: 0 for y in range(2024, 2027)}, "legacy")
    expected = [12_000 - .25 * WEEKS_IN_YEAR - CAPS["BASIC"],
                12_000 - CAPS["BASIC"], max(12_000 - CAPS["NEW"], 0)]
    np.testing.assert_allclose(pinned["additional_state_pension"][DATA_YEAR], expected, rtol=0, atol=1e-10)


def test_age_addition_fingerprints_reject_a_changed_person_in_one_year():
    rows = [(80, "BASIC", 12_000), (79, "BASIC", 12_000), (95, "NEW", 12_000)]
    years = [2027, 2039]
    pinned, _ = engine.pinned_inputs(Model(rows), years,
                                    {y: .02 for y in range(DATA_YEAR, max(years))}, "legacy")
    baseline, policy = Model(rows), Model(rows, flat_factor=.95)
    engine.pin(baseline, pinned)
    engine.pin(policy, pinned)
    reference = engine.age_addition_fingerprints(baseline, years)
    assert set(reference) == set(years)
    assert engine.age_addition_fingerprints(policy, years, reference) == reference
    changed = policy.array(ADDITION, years[-1]).copy()
    changed[0] += .01
    policy.set_input(ADDITION, years[-1], changed)
    with pytest.raises(engine.PathNotFollowed, match="age addition differs"):
        engine.age_addition_fingerprints(policy, years, reference)


def test_age_addition_fingerprints_skip_unavailable_variable():
    sim = Model([(80, "BASIC", 12_000)], addition=False)
    with patch.object(sim, "calculate", side_effect=AssertionError("unavailable variable calculated")):
        assert engine.age_addition_fingerprints(sim, HORIZON) == {}
        assert engine.age_addition_fingerprints(sim, HORIZON, {}) == {}


@pytest.mark.parametrize("present", [False, True])
def test_fiscal_components_and_coverage_include_only_the_available_parts(present):
    from triple_lock import households

    sim = Model([(80, "BASIC", 12_000)] * 12, addition=present)
    pinned, _ = engine.pinned_inputs(sim, [2027], {y: .02 for y in range(2024, 2027)}, "legacy")
    engine.pin(sim, pinned)
    tax, spending = engine.fiscal_variables(sim.tax_benefit_system.parameters, 2027, sim)
    assert (ADDITION in spending) is present
    values = dict.fromkeys([*tax, *spending], 0.0)
    if present:
        values[ADDITION] = 1.25
    grouped = engine.fiscal_groups(values, tax, spending)
    assert sum(grouped.values()) == (1.25 if present else 0)
    assert engine.net_from_components(grouped, tax) == (-1.25 if present else 0)
    # The independent household-income bridge must cancel the same pension
    # parts that government spending counts, including the conditional fourth.
    amounts = {"household_market_income": 7, "pension_contributions": .5, ADDITION: 1.25}
    with patch.object(engine, "_household_total", lambda _, name, year: amounts.get(name, 0)):
        assert engine.household_income_bridge(sim, 2027, tax, spending) == pytest.approx(6.5)
    if present:
        assert grouped[ADDITION] == 1.25

        def totals(amounts):
            result = engine.fiscal_groups(amounts, tax, spending)
            result["gov_balance"] = engine.net_from_components(result, tax)
            return {**result, "variables": amounts, "tax_variables": sorted(tax),
                    "gov_balance_model": result["gov_balance"]}

        changed = {**values, "basic_state_pension": -.4, "new_state_pension": -.6}
        saving = engine.saving_components(totals(changed), totals(values))
        assert saving["components"][ADDITION] == 0
        assert saving["components_by_variable"][ADDITION] == 0
        assert saving["decomposition_residual"] == pytest.approx(0, abs=1e-12)
    outputs = households.outputs(sim)
    assert (ADDITION in outputs["state_pension"]) is present
    assert (ADDITION in outputs) is present
    if not present:
        assert outputs == households.OUTPUTS
    stats = engine.coverage_stats(sim, 2027)
    for geo in ("uk", "gb"):
        result = stats[geo]
        assert (f"{ADDITION}_bn" in result) is present
        parts = sum(result[f"{name}_bn"] for name in engine.state_pension_parts(sim))
        assert result["state_pension_bn"] == pytest.approx(parts, abs=1e-12)
        age_row = result["state_pension_by_age"]["80_84"]
        assert (f"{ADDITION}_bn" in age_row) is present
        if present:
            expected = 12 * .25 * WEEKS_IN_YEAR / 1e9
            assert result[f"{ADDITION}_bn"] == pytest.approx(expected)
            assert age_row[f"{ADDITION}_bn"] == pytest.approx(expected)
