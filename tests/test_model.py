"""Checks against policyengine-uk itself, on hypothetical households (no dataset).

These prove the reform mechanism: overwriting the flat-rate amounts moves
the State Pension by exactly the ratio of uprating indices, while a reform
to the triple-lock flags would move nothing.
"""

import pytest

pytest.importorskip("policyengine_uk")

from policyengine_uk import CountryTaxBenefitSystem, Simulation  # noqa: E402

from triple_lock.config import FINAL_YEAR, HORIZON  # noqa: E402
from triple_lock.pipeline import (  # noqa: E402
    central_path,
    model_uprating,
    statutory_inputs,
    uprating_paths,
    check_baseline_reproduction,
    reform_for_rates,
)
from triple_lock.rules import cumulative_index  # noqa: E402


@pytest.fixture(scope="module")
def parameters():
    return CountryTaxBenefitSystem().parameters


@pytest.fixture(scope="module")
def uprating(parameters):
    return model_uprating(parameters)


def situation(year):
    # One pensioner on each system. Reported State Pension above either flat
    # rate means each receives the full flat rate (share = 1).
    return {
        "people": {
            "new_sp": {"age": {year: 70}, "state_pension_reported": {year: 30_000}},
            "basic_sp": {"age": {year: 90}, "state_pension_reported": {year: 30_000}},
        },
        "benunits": {"b": {"members": ["new_sp", "basic_sp"]}},
        "households": {"h": {"members": ["new_sp", "basic_sp"]}},
    }


def pensions(reform=None, year=FINAL_YEAR):
    sim = Simulation(situation=situation(year), reform=reform)
    return {
        v: sim.calculate(v, year)
        for v in ["new_state_pension", "basic_state_pension", "additional_state_pension"]
    }


def test_our_triple_lock_path_reproduces_the_model(parameters, uprating):
    check_baseline_reproduction(parameters, uprating["triple_lock"])


def test_alternatives_never_exceed_the_triple_lock(uprating):
    for policy in ["double_lock", "earnings_link", "cpi_link"]:
        for y in HORIZON:
            assert uprating[policy][y] <= uprating["triple_lock"][y]


def test_reform_moves_flat_rate_pension_by_index_ratio(parameters, uprating):
    baseline = pensions()
    reform, _ = reform_for_rates(parameters, uprating["cpi_link"])
    reformed = pensions(reform)
    ratio = (
        cumulative_index(uprating["cpi_link"], HORIZON)[FINAL_YEAR]
        / cumulative_index(uprating["triple_lock"], HORIZON)[FINAL_YEAR]
    )
    assert ratio < 0.97  # the reform is material, not a rounding change
    new_person, basic_person = 0, 1
    assert baseline["new_state_pension"][new_person] > 0
    assert baseline["basic_state_pension"][basic_person] > 0
    assert reformed["new_state_pension"][new_person] / baseline["new_state_pension"][new_person] == pytest.approx(ratio, rel=1e-5)
    assert reformed["basic_state_pension"][basic_person] / baseline["basic_state_pension"][basic_person] == pytest.approx(ratio, rel=1e-5)


def test_triple_lock_reform_equals_unreformed_baseline(parameters, uprating):
    baseline = pensions()
    reform, _ = reform_for_rates(parameters, uprating["triple_lock"])
    reformed = pensions(reform)
    for v in ["new_state_pension", "basic_state_pension"]:
        assert reformed[v] == pytest.approx(baseline[v], rel=1e-5)


def test_flag_reform_does_not_bite():
    """Why the pipeline overwrites amounts: the triple lock is built at load time."""
    baseline = pensions()
    flags_off = pensions(
        {
            "gov.dwp.state_pension.triple_lock.include_earnings": {"2027-01-01.2034-12-31": False},
            "gov.dwp.state_pension.triple_lock.minimum_rate": {"2027-01-01.2034-12-31": 0.0},
        }
    )
    assert flags_off["new_state_pension"] == pytest.approx(baseline["new_state_pension"])


def test_statutory_april_2027_inputs(parameters):
    """The April 2027 earnings leg is published May-July 2026 AWE, not PE's 3.4%."""
    s = statutory_inputs()
    assert s["earnings"] == pytest.approx(0.039)
    assert 0.0 < s["cpi"] < 0.05
    cpi, earnings, stat = central_path(parameters)
    assert earnings[2026] == pytest.approx(0.039) and stat["model_earnings"] == pytest.approx(0.034)
    assert uprating_paths(cpi, earnings)["triple_lock"][2027] == pytest.approx(0.039)
    # Later years are untouched.
    assert model_uprating(parameters)["triple_lock"][2028] == uprating_paths(cpi, earnings)["triple_lock"][2028]
