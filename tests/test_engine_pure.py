"""The engine's helpers on stubs and the parameter tree (no dataset)."""

import numpy as np
import pytest

from triple_lock import engine, pipeline
from triple_lock.config import BASE_YEAR, HORIZON, PENSION_CREDIT_GUARANTEE, STATE_PENSION_AGE_CHANGES


class Series:
    def __init__(self, values):
        self.values = np.asarray(values)

    def to_numpy(self):
        return self.values


class StubSim:
    """Two people: A over State Pension age throughout; B over it until 2027, not from 2028 (the age rise)."""

    class dataset:
        years = [2024]

    def calculate(self, variable, year):
        if variable == "state_pension_type":
            assert year == 2024
            return Series(["BASIC", "NEW"])
        if variable == "additional_state_pension":
            assert year == 2024
            return Series([100.0, 50.0])
        if variable == "is_SP_age":
            return Series([True, year < 2028])
        raise KeyError(variable)


def test_pinned_inputs_hold_types_mask_by_age_and_grow_the_additional_pension_by_cpi():
    sep = {2024: 0.017, 2025: 0.038, **{y: 0.02 for y in range(2026, 2040)}}
    sep[2030] = -0.01  # a negative September CPI never cuts the additional pension
    out, data_year = engine.pinned_inputs(StubSim(), [2027, 2028, 2031], sep)
    assert data_year == 2024
    assert out["state_pension_type"][2027].tolist() == ["BASIC", "NEW"]
    assert out["state_pension_type"][2028].tolist() == ["BASIC", "NONE"]
    idx_2027 = 1.017 * 1.038 * 1.02  # upratings April 2025, 2026, 2027 (September 2024, 2025, 2026 CPI)
    assert out["additional_state_pension"][2027] == pytest.approx([100 * idx_2027, 50 * idx_2027])
    idx_2031 = idx_2027 * 1.02 * 1.02 * 1.02 * 1.0  # April 2028-30 at 2%, April 2031 floored at 0
    assert out["additional_state_pension"][2031] == pytest.approx([100 * idx_2031, 0.0])


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


def test_scenario_changes_carry_the_path_and_the_state_pension_age(parameters):
    from triple_lock.config import CALENDAR_YEARS

    spec = {"cpi": {y: 0.02 for y in CALENDAR_YEARS}, "earnings": {y: 0.035 for y in CALENDAR_YEARS}}
    changes = engine.scenario_changes(spec, parameters)
    for path, change in STATE_PENSION_AGE_CHANGES.items():
        assert changes[path] == change
    assert "gov.economic_assumptions.yoy_growth.obr.average_earnings" in changes


def test_the_builds_own_outputs_do_not_make_the_tree_dirty():
    assert ":!data/results.json" in pipeline.OUTPUT_PATHS and ":!dashboard/public/data/results.json" in pipeline.OUTPUT_PATHS
    state = pipeline.git_state()
    assert set(state) == {"git_revision", "git_dirty"} and len(state["git_revision"]) == 40
