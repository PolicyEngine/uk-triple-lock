"""The engine's helpers on stubs and the parameter tree (no dataset)."""

import json

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine, pipeline, rules
from triple_lock.config import (BASE_YEAR, CENTRAL_RATE_DECIMALS, HORIZON, PENSION_CREDIT_GUARANTEE,
                               STATUTORY_PARAMETERS, STATUTORY_YEARS, SWITCH_YEAR, TRIPLE_LOCK_FLOOR)


class Series:
    def __init__(self, values):
        self.values = np.asarray(values)

    def to_numpy(self):
        return self.values


class StubSim:
    """Two people: A over State Pension age throughout; B over it until 2027, not from 2028 (the age rise). A is on
    the basic State Pension, B on the new, each reporting the data year's flat rate and a little more (£100 and £50 a
    year: the additional pension)."""

    WEEKLY = {"basic": 176.45, "new": 230.25}

    class dataset:
        years = [2024]

    class tax_benefit_system:
        class parameters:
            class gov:
                class dwp:
                    class state_pension:
                        class basic_state_pension:
                            amount = staticmethod(lambda period: StubSim.WEEKLY["basic"])

                        class new_state_pension:
                            amount = staticmethod(lambda period: StubSim.WEEKLY["new"])

    def calculate(self, variable, year):
        from policyengine_uk.model_api import WEEKS_IN_YEAR

        if variable == "state_pension_type":
            assert year == 2024
            return Series(["BASIC", "NEW"])
        if variable == "state_pension_reported":
            assert year == 2024
            return Series([self.WEEKLY["basic"] * WEEKS_IN_YEAR + 100, self.WEEKLY["new"] * WEEKS_IN_YEAR + 50])
        if variable == "is_SP_age":
            return Series([True, year < 2028])
        raise KeyError(variable)


def test_pinned_inputs_hold_types_mask_by_age_and_grow_the_additional_pension_by_cpi():
    sep = {2024: 0.017, 2025: 0.038, **{y: 0.02 for y in range(2026, 2040)}}
    sep[2030] = -0.01  # a negative September CPI never cuts the additional pension
    out, data_year = engine.pinned_inputs(StubSim(), [2027, 2028, 2031], sep, "legacy")
    assert data_year == 2024
    assert out["state_pension_type"][2027].tolist() == ["BASIC", "NEW"]
    assert out["state_pension_type"][2028].tolist() == ["BASIC", "NONE"]
    idx_2027 = 1.017 * 1.038 * 1.02  # upratings April 2025, 2026, 2027 (September 2024, 2025, 2026 CPI)
    assert out["additional_state_pension"][2027] == pytest.approx([100 * idx_2027, 50 * idx_2027])
    idx_2031 = idx_2027 * 1.02 * 1.02 * 1.02 * 1.0  # April 2028-30 at 2%, April 2031 floored at 0
    assert out["additional_state_pension"][2031] == pytest.approx([100 * idx_2031, 0.0])
    # The data year is pinned too: its types, its additional pension (uprating factor 1) and the reported pension
    # the run counts (both over State Pension age in 2024, so all of it).
    assert out["additional_state_pension"][2024] == pytest.approx([100, 50])
    assert out["state_pension_reported"][2024].tolist() == StubSim().calculate("state_pension_reported", 2024).values.tolist()


def test_the_additional_pension_follows_each_years_type_not_the_survey_years():
    """A person on the basic State Pension in the survey and on the new one in a later year (a cohort type) gets the
    part of their reported pension above the new flat rate, not the part above the basic one: else the band between
    the two flat rates would be paid twice (once inside the new State Pension, once as additional pension)."""
    from triple_lock.demography import pension_components

    from policyengine_uk.model_api import WEEKS_IN_YEAR

    caps = (StubSim.WEEKLY["basic"] * WEEKS_IN_YEAR, StubSim.WEEKLY["new"] * WEEKS_IN_YEAR)
    reported = np.array([caps[0] + 100, caps[1] + 50, 0.5 * caps[0]])
    survey = pension_components(reported, ["BASIC", "NEW", "BASIC"], *caps)
    moved = pension_components(reported, ["NEW", "NEW", "NEW"], *caps)
    assert survey[2] == pytest.approx([100, 50, 0])
    assert moved[2] == pytest.approx([0, 50, 0])  # the basic State Pensioner's £100 is inside the new flat rate
    for parts in (survey, moved):
        assert sum(parts) == pytest.approx(reported)  # the reported pension, whatever the type


class AgingStubSim(StubSim):
    """StubSim with ages (held at the survey year's, or one year older each year) and the load's declaration of how
    it treated the population (as _managed sets it), or none."""

    def __init__(self, aged=False, declared=engine.LOADED_POPULATION):
        self.aged = aged
        if declared is not None:
            self.triple_lock_population = dict(declared)

    def calculate(self, variable, year):
        if variable == "age":
            return Series(np.array([70.0, 66.0]) + (year - 2024 if self.aged else 0))
        return super().calculate(variable, year)


def test_population_treatment_records_the_load_and_checks_what_it_can():
    """What run_path records in fixed_inputs.population: the load's declaration of weights and ages, checked against
    what the run pins and the ages the model computes, and the pension type rule pinned_inputs followed."""
    years = [2027, 2028, 2031]
    sep = {y: 0.02 for y in range(2024, 2040)}
    pinned, data_year = engine.pinned_inputs(StubSim(), years, sep, "legacy")
    today = {"weights": "survey", "ages": "survey_year", "pension_types": "survey_year"}
    assert engine.population_treatment(AgingStubSim(), pinned, data_year, years) == today
    # No declaration from the load: a simulation built some other way cannot say what it did to the survey.
    with pytest.raises(engine.PathNotFollowed, match="did not declare"):
        engine.population_treatment(AgingStubSim(declared=None), pinned, data_year, years)
    # A change made inside the dataset is recorded as the code that made it declares it.
    raked = {"weights": "ons_projection", "ages": "adjusted"}
    assert engine.population_treatment(AgingStubSim(declared=raked), pinned, data_year, years) == {
        **raked, "pension_types": "survey_year"}
    # What the run itself does is checked against the declaration.
    assert engine.population_treatment(AgingStubSim(aged=True), pinned, data_year, years)["ages"] == "aged_forward"
    with pytest.raises(engine.PathNotFollowed, match="weights"):
        engine.population_treatment(AgingStubSim(), {**pinned, "household_weight": {y: [1.0] for y in years}},
                                    data_year, years)
    with pytest.raises(engine.PathNotFollowed, match="ages differ"):
        engine.population_treatment(AgingStubSim(), {**pinned, "age": {y: [85.0, 66.0] for y in years}},
                                    data_year, years)
    unpinned = {k: v for k, v in pinned.items() if k != "state_pension_type"}
    assert engine.population_treatment(AgingStubSim(), unpinned, data_year, years)["pension_types"] == "model"


def test_pinned_inputs_refuse_an_unknown_treatment():
    with pytest.raises(ValueError, match="unknown demography treatment"):
        engine.pinned_inputs(StubSim(), [2027], {y: 0.02 for y in range(2024, 2040)}, "aged")


def test_september_cpi_joins_published_history_and_the_path_at_published_precision():
    spec = {"september_cpi_history": {"2024": 0.017, "2025": 0.038},
            "statutory_cpi": {2026: 0.03144, 2027: 0.0201}}
    got = engine.september_cpi(spec)
    assert got == {2024: 0.017, 2025: 0.038, 2026: 0.031, 2027: 0.02}


@pytest.fixture(scope="module")
def parameters():
    pytest.importorskip("policyengine_uk")
    from policyengine_uk import CountryTaxBenefitSystem

    return CountryTaxBenefitSystem().parameters


def test_pension_credit_guarantee_rises_with_earnings_and_is_never_cut(parameters):
    earnings = {y - 1: (-0.02 if y == 2031 else 0.03) for y in HORIZON}
    levels = engine.pension_credit_levels(parameters, earnings)
    for path in PENSION_CREDIT_GUARANTEE.values():
        base = float(parameters.get_child(path)(f"{BASE_YEAR}-06-01"))
        lv = levels[path]
        assert lv[HORIZON[0]] == pytest.approx(base * 1.03)
        assert lv[2031] == pytest.approx(lv[2030])  # a fall in earnings leaves it unchanged
        assert all(lv[y] >= lv[y - 1] for y in HORIZON[1:])


def test_scenario_changes_carry_the_path_and_its_statutory_inputs(parameters):
    """The calendar growth and every statutory input (at its observation date, the year before its April), and
    nothing on the State Pension age: the model's own, by date of birth (the scalar paths are gone upstream)."""
    from triple_lock.config import CALENDAR_YEARS

    spec = {"cpi": {y: 0.02 for y in CALENDAR_YEARS}, "earnings": {y: 0.035 for y in CALENDAR_YEARS},
            "statutory_cpi": {y: 0.021 + y / 1e6 for y in STATUTORY_YEARS},
            "statutory_earnings": {y: 0.036 + y / 1e6 for y in STATUTORY_YEARS}}
    changes = engine.scenario_changes(spec, parameters)
    assert "gov.economic_assumptions.yoy_growth.obr.average_earnings" in changes
    assert not [path for path in changes if path.startswith("gov.dwp.state_pension.age")]
    for series, (path, month_day) in STATUTORY_PARAMETERS.items():
        assert changes[path] == {f"year:{y}-{month_day}:1": spec[f"statutory_{series}"][y] for y in STATUTORY_YEARS}
    assert STATUTORY_YEARS == [y - 1 for y in HORIZON]


def test_the_builds_own_outputs_do_not_make_the_tree_dirty():
    assert {":!data/results.json", ":!dashboard/public/data/results.json", ":!data/scenarios/*.json"} <= set(pipeline.OUTPUT_PATHS)
    state = pipeline.git_state()
    assert set(state) == {"git_revision", "git_dirty"} and len(state["git_revision"]) == 40


# ── Survey records stay out of the published file ─────────────────────

RECORD = {"household_id": 8566, "weight": 40285.6, "median_weight": 700.0, "income_change_gbp": 7866.0,
          "contribution_bn": 0.317, "share_of_income_change": -10.8, "income_change_excluding_bn": -0.35,
          "gross_contribution_bn": 0.006, "change_gbp": {"housing_benefit": 7800.0},
          "amounts_gbp": {"triple_lock": {"state_pension": 12000.0}}}


def test_redact_records_keeps_only_contributions_wherever_they_sit():
    run = {"largest_household": dict(RECORD),
           "concentration_by_year": {"2033": {k: RECORD[k] for k in ("household_id", "weight", "contribution_bn",
                                                                      "share_of_income_change")}},
           "saving_bn": {"2033": {"net": 0.03}}}
    results = pipeline.redact_records({"central": {"run": run}, "trajectories": {"paths": [json_copy(run)]}})
    for r in (results["central"]["run"], results["trajectories"]["paths"][0]):
        assert r["largest_household"] == {"contribution_bn": 0.317, "share_of_income_change": -10.8,
                                          "income_change_excluding_bn": -0.35}
        assert r["concentration_by_year"] == {"2033": {"contribution_bn": 0.317, "share_of_income_change": -10.8}}
        assert r["saving_bn"] == {"2033": {"net": 0.03}}


def json_copy(x):
    return json.loads(json.dumps(x))


leaf = st.one_of(st.integers(), st.floats(allow_nan=False), st.text(max_size=3))
record = st.fixed_dictionaries({}, optional={k: st.floats(allow_nan=False) for k in RECORD})
tree = st.recursive(
    leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.sampled_from(["a", "b", "run", "paths"]), children, max_size=3),
        st.fixed_dictionaries({"largest_household": record}),
        st.fixed_dictionaries({"concentration_by_year": st.dictionaries(st.sampled_from(["2033", "2039"]), record,
                                                                        max_size=2)}),
    ),
    max_leaves=12,
)


@settings(max_examples=200, deadline=None)
@given(tree)
def test_no_record_field_survives_redaction(obj):
    out = pipeline.redact_records(json_copy(obj))

    def check(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "largest_household" and isinstance(v, dict):
                    assert set(v) <= set(pipeline.RECORD_FIELDS[k])
                elif k == "concentration_by_year" and isinstance(v, dict):
                    assert all(set(c) <= set(pipeline.RECORD_FIELDS[k]) for c in v.values())
                else:
                    check(v)
        elif isinstance(x, list):
            for v in x:
                check(v)

    check(out)


# ── One rounding for the statutory inputs ──────────────────────────────

half_grid = st.integers(-30, 120).map(lambda k: (k + 0.5) / 1000)
rate = st.one_of(half_grid, st.floats(min_value=-0.03, max_value=0.12, allow_nan=False))
statutory = st.lists(rate, min_size=len(HORIZON), max_size=len(HORIZON)).map(
    lambda v: {y - 1: x for y, x in zip(HORIZON, v)})


def rule_input(x):
    """The input the triple lock paid when it alone set the rise: its rate with the other input far below."""
    return float(rules.rates_matrix("triple_lock", x, -0.5, decimals=CENTRAL_RATE_DECIMALS)[0, 0])


@settings(max_examples=300, deadline=None)
@given(statutory, statutory)
def test_the_fixed_inputs_see_the_statutory_inputs_the_rules_see(cpi, earnings):
    """Differential, half-grid values included: the additional pension's September CPI and the Pension Credit
    guarantee's rise use exactly the 0.1-point inputs the State Pension rules use (with Python's round() they would
    differ by 0.1 point on 84 of 151 half-grid values)."""
    sep = engine.september_cpi({"september_cpi_history": {2024: 0.017}, "statutory_cpi": cpi})
    growth = engine.guarantee_growth(earnings)
    for y in HORIZON:
        assert sep[y - 1] == rules.round_rate(cpi[y - 1])
        assert growth[y] == max(rules.round_rate(earnings[y - 1]), 0.0)
        if cpi[y - 1] > 0.03:
            assert sep[y - 1] == pytest.approx(rule_input(cpi[y - 1]), abs=1e-15)
        if earnings[y - 1] > 0.03:
            assert growth[y] == pytest.approx(rule_input(earnings[y - 1]), abs=1e-15)


class StubParameters:
    def __init__(self, levels):
        self.levels = levels

    def get_child(self, path):
        return lambda instant: self.levels[path]


@settings(max_examples=200, deadline=None)
@given(statutory)
def test_pension_credit_levels_compound_the_rounded_earnings_and_never_fall(earnings):
    base = {path: 200.0 + i for i, path in enumerate(PENSION_CREDIT_GUARANTEE.values())}
    levels = engine.pension_credit_levels(StubParameters(base), earnings)
    growth = engine.guarantee_growth(earnings)
    for path, lv in levels.items():
        expected = base[path]
        for y in HORIZON:
            expected *= 1 + growth[y]
            assert lv[y] == pytest.approx(expected, rel=1e-12)
            assert lv[y] >= (lv[y - 1] if y > HORIZON[0] else base[path])


def test_the_model_check_rounds_as_policyengine_uk_does():
    """The one rounding besides rules.round_rate: engine.model_triple_lock_rate reproduces the model's own triple lock
    to check it, rounding each statutory input as policyengine-uk 2.118.0 does (halves away from zero on the shortest
    decimal), numpy scalars included. The two roundings differ only on exact half-grid inputs."""
    assert engine.model_triple_lock_rate(0.0245, 0.02) == 0.025  # numpy's halves-to-even gives 0.024
    assert rules.round_rate(0.0245) == 0.024
    assert engine.model_triple_lock_rate(np.float64(0.0355), np.float64(0.02)) == 0.036 == rules.round_rate(0.0355)
    assert engine.published_precision(-0.0005) == -0.001
    assert engine.model_triple_lock_rate(0.01, -0.02) == TRIPLE_LOCK_FLOOR


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(rate, rate), min_size=len(HORIZON), max_size=len(HORIZON)))
def test_model_triple_lock_rate_matches_policyengine_uks_rule(pairs):
    """Differential against the upstream rule (policyengine-uk 2.118.0's create_triple_lock: each input rounded as
    read_uprating_years rounds it, then uprating_rates under current law), half-grid statutory inputs included: the
    path-following check expects exactly what the model computes."""
    pytest.importorskip("policyengine_uk")
    from policyengine_uk.parameters.gov.dwp.state_pension.triple_lock import create_triple_lock as tl

    years = {y: tl.UpratingYear(earnings=tl.round_to_published_precision(e), cpi=tl.round_to_published_precision(c),
                                minimum_rate=TRIPLE_LOCK_FLOOR) for y, (e, c) in zip(HORIZON, pairs)}
    model = tl.uprating_rates(years)
    for y, (e, c) in zip(HORIZON, pairs):
        assert model[y] == engine.model_triple_lock_rate(e, c), y


grid = st.integers(-20, 110).map(lambda k: k / 1000)  # statutory inputs as ONS publishes them, to 0.1 point


@settings(max_examples=300, deadline=None)
@given(st.lists(st.tuples(grid, grid), min_size=len(HORIZON), max_size=len(HORIZON)))
def test_the_burnham_plan_matches_policyengine_uks_earnings_path_guarantee(pairs):
    """Differential: two implementations of the same rule agree. policyengine-uk 2.118.0 expresses the plan as the
    triple lock to April 2029 and then, from the switch, no earnings element (max(CPI, 2.5%)) with its
    earnings_path_guarantee (the pension kept on an earnings path anchored at its level before the guarantee first
    applies, the top-up rounded up); rules.rates_matrix("burnham_2030") is ours. On inputs at published precision
    both roundings leave the inputs alone."""
    pytest.importorskip("policyengine_uk")
    from policyengine_uk.parameters.gov.dwp.state_pension.triple_lock import create_triple_lock as tl

    years = {y: tl.UpratingYear(earnings=e, cpi=c, minimum_rate=TRIPLE_LOCK_FLOOR, include_earnings=y < SWITCH_YEAR,
                                earnings_path_guarantee=y >= SWITCH_YEAR)
             for y, (e, c) in zip(HORIZON, pairs)}
    upstream = tl.uprating_rates(years)
    cpi = {y - 1: c for y, (_, c) in zip(HORIZON, pairs)}
    earnings = {y - 1: e for y, (e, _) in zip(HORIZON, pairs)}
    ours = rules.uprating_path("burnham_2030", cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS)
    for y in HORIZON:
        assert ours[y] == pytest.approx(upstream[y], abs=1e-12), (y, ours, upstream)


# ── The pension types the model uses ───────────────────────────────────


class ModelStub:
    """A simulation that stores set_input values and returns them, optionally garbled, as the model's types."""

    def __init__(self, garble=None, weights=(1.0, 2.0, 4.0)):
        self.inputs, self.garble, self.weights = {}, garble, np.array(weights)

    def set_input(self, variable, year, values):
        self.inputs[(variable, year)] = np.asarray(values)

    def calculate(self, variable, year):
        if variable == "person_weight":
            return Series(self.weights)
        values = self.inputs[(variable, year)]
        return Series(self.garble(values) if self.garble else values)


PINNED = {"state_pension_type": {2027: np.array(["BASIC", "NEW", "NONE"]), 2028: np.array(["BASIC", "NONE", "NONE"])}}


def test_held_pension_types_are_counted_from_the_model():
    sim = ModelStub()
    engine.pin(sim, PINNED)
    held = engine.held_pension_types(sim, PINNED, [2027, 2028])
    assert held[2027] == {"records": {"BASIC": 1, "NEW": 1, "NONE": 1}, "people": {"BASIC": 1.0, "NEW": 2.0, "NONE": 4.0}}
    assert held[2028] == {"records": {"BASIC": 1, "NEW": 0, "NONE": 2}, "people": {"BASIC": 1.0, "NEW": 0.0, "NONE": 6.0}}


@pytest.mark.parametrize("garble, message", [
    (lambda v: np.where(v == "NEW", "BASIC", v), "not the held one"),   # the model uses another type
    (lambda v: v[:-1], "pinned array"),
    (lambda v: np.where(v == "NONE", "OTHER", v), "not the held one"),
])
def test_held_pension_types_fail_the_run_when_the_model_uses_other_types(garble, message):
    sim = ModelStub(garble)
    engine.pin(sim, PINNED)
    with pytest.raises(engine.PathNotFollowed, match=message):
        engine.held_pension_types(sim, PINNED, [2027])


def test_held_pension_types_reject_a_type_outside_the_three():
    pinned = {"state_pension_type": {2027: np.array(["BASIC", "OTHER", "NONE"])}}
    sim = ModelStub()
    engine.pin(sim, pinned)
    with pytest.raises(engine.PathNotFollowed, match="unknown"):
        engine.held_pension_types(sim, pinned, [2027])


# ── The fiscal decomposition: policyengine-uk's own tax and spending lists ──


class ParameterStub:
    """Parameters at a date, by path: the three switches fiscal_variables mirrors."""

    def __init__(self, **values):
        self.values = {"gov.contrib.abolish_council_tax": False, "gov.contrib.abolish_state_pension": False,
                       "gov.contrib.cec.state_pension_increase": 0, **values}

    def get_child(self, path):
        return lambda instant: self.values[path]


def test_fiscal_variables_are_policyengine_uks_lists_with_their_conditionals():
    pytest.importorskip("policyengine_uk")
    from policyengine_uk.variables.gov.gov_spending import GOV_SPENDING_VARIABLES
    from policyengine_uk.variables.gov.gov_tax import GOV_TAX_VARIABLES

    tax, spending = engine.fiscal_variables(ParameterStub(), 2030)
    assert tax == list(GOV_TAX_VARIABLES)
    assert "state_pension" not in spending and set(engine.STATE_PENSION_PARTS) <= set(spending)
    assert set(spending) == set(GOV_SPENDING_VARIABLES) - {"state_pension"} | set(engine.STATE_PENSION_PARTS)
    tax, spending = engine.fiscal_variables(ParameterStub(**{"gov.contrib.abolish_council_tax": True}), 2030)
    assert not {"council_tax", "high_value_council_tax_surcharge"} & set(tax) and "council_tax_benefit" not in spending
    for switch, value in (("gov.contrib.abolish_state_pension", True), ("gov.contrib.cec.state_pension_increase", 0.01)):
        with pytest.raises(engine.NotDecomposable):
            engine.fiscal_variables(ParameterStub(**{switch: value}), 2030)
    # Every named group's variables are counted, each in exactly one group.
    tax, spending = engine.fiscal_variables(ParameterStub(), 2030)
    grouped = [v for vs in engine.FISCAL_GROUPS.values() for v in vs]
    assert len(grouped) == len(set(grouped)) and set(grouped) <= set(tax) | set(spending)
    assert engine.tax_groups(tax) == {"income_tax", "other_tax"}


@settings(max_examples=200, deadline=None)
@given(st.data())
def test_the_components_add_up_to_the_change_in_gov_balance(data):
    """For any changes in the listed variables, the groups (taxes added, spending subtracted) are the change in
    gov_balance taken as its tax less its spending: saving_components never misses it."""
    pytest.importorskip("policyengine_uk")
    tax, spending = engine.fiscal_variables(ParameterStub(), 2030)
    amount = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False)

    def run(values, model_noise=0.0):
        t = engine.fiscal_groups(values, tax, spending)
        t["gov_balance"] = engine.net_from_components(engine.fiscal_groups(values, tax, spending), tax)
        t["gov_balance_model"] = t["gov_balance"] + model_noise
        return {**t, "variables": values, "tax_variables": sorted(tax)}

    base = {v: data.draw(amount) for v in [*tax, *spending]}
    policy = {v: base[v] + data.draw(amount) for v in base}
    out = engine.saving_components(run(policy), run(base))
    net = sum(policy[v] - base[v] for v in tax) - sum(policy[v] - base[v] for v in spending)
    assert abs(out["decomposition_residual"]) <= engine.FISCAL_IDENTITY_TOL_BN
    assert engine.net_from_components(out["components"], tax) == pytest.approx(net, abs=1e-9)
    assert sum(out["components_by_variable"].values()) == pytest.approx(
        sum(policy.values()) - sum(base.values()), abs=1e-9)


def test_saving_components_refuses_a_model_its_parts_do_not_explain():
    pytest.importorskip("policyengine_uk")
    tax, spending = engine.fiscal_variables(ParameterStub(), 2030)
    values = {v: 1.0 for v in [*tax, *spending]}

    def run(model_noise):
        t = engine.fiscal_groups(values, tax, spending)
        t["gov_balance"] = engine.net_from_components(engine.fiscal_groups(values, tax, spending), tax)
        t["gov_balance_model"] = t["gov_balance"] + model_noise
        return {**t, "variables": values, "tax_variables": sorted(tax)}

    engine.saving_components(run(5e-6), run(0.0))  # float32 noise: within FISCAL_MODEL_TOL_BN
    with pytest.raises(engine.NotDecomposable, match="float32"):
        engine.saving_components(run(0.012), run(0.0))  # the old £0.012bn residual would fail
    broken = run(0.0)
    broken["income_tax"] += 0.5  # a group that no longer matches gov_balance
    with pytest.raises(engine.NotDecomposable, match="miss"):
        engine.saving_components(broken, run(0.0))


def test_the_job_key_records_python_as_major_minor():
    """A patch release changes no result and nothing pins one, so the key (and test_not_stale) holds Python's
    major.minor only: the full version would fail whenever CI's patch differs from the build's."""
    import re
    import sys

    assert re.fullmatch(r"\d+\.\d+", engine.package_versions()["python"])
    assert engine.package_versions()["python"] == f"{sys.version_info.major}.{sys.version_info.minor}"
def test_treatment_contrast_counts_suppresses_small_and_detects_changes():
    from triple_lock.engine import treatment_contrast_counts
    import numpy as np

    def row(values):
        return {2039: {"gross": np.array(values, dtype=float), "net": np.array(values, dtype=float),
                       "gb": np.array([True] * 10 + [False] * 2)}}
    reference = row([1] * 12)
    same = row([1] * 12)
    all_changed = row([2] * 12)
    one_changed = row([2] + [1] * 11)
    contrasts = {"difference": {"alternative": 1, "reference": -1}}
    count = lambda alternative: treatment_contrast_counts(
        {"reference": reference, "alternative": alternative}, contrasts)[2039]
    assert count(same)["gb"]["difference"] == {"gross": 0, "net": 0}
    assert count(all_changed)["gb"]["difference"] == {"gross": 10, "net": 10}
    assert count(all_changed)["uk"]["difference"] == {"gross": 12, "net": 12}
    assert count(one_changed)["gb"]["difference"] == {"gross": None, "net": None}


def test_treatment_contrast_counts_rejects_changed_geography_order():
    from triple_lock.engine import treatment_contrast_counts
    import numpy as np
    import pytest

    a = {2039: {"gross": np.ones(10), "net": np.ones(10), "gb": np.ones(10, dtype=bool)}}
    b = {2039: {"gross": np.ones(10), "net": np.ones(10), "gb": np.zeros(10, dtype=bool)}}
    with pytest.raises(ValueError, match="geography ordering"):
        treatment_contrast_counts({"a": a, "b": b}, {"difference": {"a": 1, "b": -1}})


def test_treatment_batch_reuses_only_pristine_setup_and_discards_private_arrays(monkeypatch):
    specification = {"dataset": "enhanced_frs_2024_25@1.56.16", "cpi": {2034: .02},
                     "earnings": {2034: .03}, "statutory_cpi": {2033: .02},
                     "statutory_earnings": {2033: .03}}
    template, preparations, calls = object(), [], []
    monkeypatch.setattr(engine, "_prepare_path_template", lambda spec: preparations.append(spec) or template)

    def run(spec, _support_callback=None, _template=None):
        assert _template is template
        calls.append(spec["demography"])
        changed = spec["demography"] == "both"
        _support_callback({2034: {"gross": np.full(12, float(changed)),
                                  "net": np.full(12, 2. * changed), "gb": np.ones(12, dtype=bool)}})
        return {"saving_bn": {2034: {"gross": float(changed)}},
                "largest_household": {}, "concentration_by_year": {}, "concentration_top10_by_year": {}}

    monkeypatch.setattr(engine, "run_path", run)
    result = engine.run_treatment_paths({
        "specs": {mode: {**specification, "demography": mode} for mode in ("frozen", "both")},
        "contrasts": {"difference": {"both": 1, "frozen": -1}}})
    assert len(preparations) == 1 and calls == ["frozen", "both"]
    for aggregate in result.values():
        assert set(aggregate) == {"saving_bn", "treatment_contrast_support_records_by_year"}
        assert aggregate["treatment_contrast_support_records_by_year"][2034]["gb"]["difference"] == {
            "gross": 12, "net": 12}


@pytest.mark.parametrize("changed", ("earnings", "dataset"))
def test_treatment_batch_refuses_changed_macro_or_dataset_before_loading(monkeypatch, changed):
    specification = {"dataset": "enhanced_frs_2024_25@1.56.16", "cpi": {2034: .02},
                     "earnings": {2034: .03}, "statutory_cpi": {2033: .02},
                     "statutory_earnings": {2033: .03}}
    alternative = {**specification, changed: {2034: .04} if changed == "earnings"
                   else "enhanced_frs_2024_25@1.57.4"}
    monkeypatch.setattr(engine, "_prepare_path_template", lambda *args: pytest.fail("must not load data"))
    with pytest.raises(ValueError, match="share one dataset and macro Scenario"):
        engine.run_treatment_paths({"specs": {"frozen": specification, "both": alternative}, "contrasts": {}})
