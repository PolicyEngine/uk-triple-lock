"""Checks against policyengine-uk itself, on hypothetical households and the parameter tree (no dataset).

They prove the mechanisms the engine relies on: overwriting the flat-rate
amounts moves the State Pension by exactly the ratio of the rules' levels; a
reform to the triple-lock flags moves nothing (the rate is built at load time);
our triple lock reproduces the model's own; and, with the horizon extension,
a growth path set before the parameters are processed reaches the model's
triple lock and lagged CPI to 2041.
"""

import numpy as np
import pytest

pytest.importorskip("policyengine_uk")

from policyengine_uk import CountryTaxBenefitSystem, Simulation  # noqa: E402

from triple_lock import engine, rules  # noqa: E402
from triple_lock.central import central_path, fiscal_to_calendar, statutory_inputs  # noqa: E402
from triple_lock.config import (  # noqa: E402
    BASE_YEAR,
    CALENDAR_YEARS,
    CENTRAL_RATE_DECIMALS,
    CPI_PARAMETER,
    EARNINGS_PARAMETER,
    FINAL_YEAR,
    FLAT_RATE_PARAMETERS,
    HORIZON,
    MODEL_TRIPLE_LOCK_PARAMETER,
)

YEARS = list(range(2027, 2035))  # the default parameters' own triple lock reaches 2034


@pytest.fixture(scope="module")
def parameters():
    return CountryTaxBenefitSystem().parameters


def situation(year):
    # One pensioner on each system; reported State Pension above either flat rate gives the full rate.
    return {
        "people": {
            "new_sp": {"age": {year: 70}, "state_pension_reported": {year: 30_000}},
            "basic_sp": {"age": {year: 90}, "state_pension_reported": {year: 30_000}},
        },
        "benunits": {"b": {"members": ["new_sp", "basic_sp"]}},
        "households": {"h": {"members": ["new_sp", "basic_sp"]}},
    }


def pensions(reform=None, year=YEARS[-1]):
    sim = Simulation(situation=situation(year), reform=reform)
    return {v: sim.calculate(v, year) for v in ["new_state_pension", "basic_state_pension"]}


def model_path(parameters):
    cpi, earnings = parameters.get_child(CPI_PARAMETER), parameters.get_child(EARNINGS_PARAMETER)
    return ({y - 1: float(cpi(f"{y - 1}-01-01")) for y in YEARS}, {y - 1: float(earnings(f"{y - 1}-01-01")) for y in YEARS})


def levels(parameters, policy, cpi, earnings):
    base = engine.base_levels(parameters)
    r = rules.uprating_path(policy, cpi, earnings, YEARS, decimals=CENTRAL_RATE_DECIMALS)
    return {name: rules.level_path(base[name], r, YEARS) for name in base}, r


def test_our_triple_lock_reproduces_the_models_own(parameters):
    cpi, earnings = model_path(parameters)
    lv, r = levels(parameters, "triple_lock", cpi, earnings)
    model_rate = parameters.get_child(MODEL_TRIPLE_LOCK_PARAMETER)
    for y in YEARS:
        assert float(model_rate(f"{y}-06-01")) == pytest.approx(r[y], abs=1e-12)
        for name, path in FLAT_RATE_PARAMETERS.items():
            assert float(parameters.get_child(path)(f"{y}-06-01")) == pytest.approx(lv[name][y], rel=engine.MODEL_AMOUNT_REL_TOL)


def test_reform_moves_flat_rate_pensions_by_the_level_ratio(parameters):
    """On a path where the ratchet bites, the Burnham plan's amounts move each pension by exactly its level ratio."""
    cpi = {y - 1: (0.05 if y == 2031 else 0.01) for y in YEARS}
    earnings = {y - 1: (0.00 if y == 2031 else 0.05) for y in YEARS}
    tl, r_tl = levels(parameters, "triple_lock", cpi, earnings)
    bp, r_bp = levels(parameters, "burnham_2030", cpi, earnings)
    base, reformed = pensions(engine.flat_rate_reform(tl)), pensions(engine.flat_rate_reform(bp))
    ratio = rules.cumulative_index(r_bp, YEARS)[YEARS[-1]] / rules.cumulative_index(r_tl, YEARS)[YEARS[-1]]
    assert ratio < 0.97  # material, not rounding
    assert base["new_state_pension"][0] > 0 and base["basic_state_pension"][1] > 0
    assert reformed["new_state_pension"][0] / base["new_state_pension"][0] == pytest.approx(ratio, rel=1e-6)
    assert reformed["basic_state_pension"][1] / base["basic_state_pension"][1] == pytest.approx(ratio, rel=1e-6)


def test_triple_lock_reform_equals_the_unreformed_model(parameters):
    cpi, earnings = model_path(parameters)
    tl, _ = levels(parameters, "triple_lock", cpi, earnings)
    base, reformed = pensions(), pensions(engine.flat_rate_reform(tl))
    for v in base:
        assert reformed[v] == pytest.approx(base[v], rel=1e-5)


def test_flag_reform_does_not_bite():
    """Why the engine overwrites amounts: the triple lock is built at load time."""
    flags_off = pensions({
        "gov.dwp.state_pension.triple_lock.include_earnings": {"2027-01-01.2034-12-31": False},
        "gov.dwp.state_pension.triple_lock.minimum_rate": {"2027-01-01.2034-12-31": 0.0},
    })
    assert flags_off["new_state_pension"] == pytest.approx(pensions()["new_state_pension"])


def test_model_horizon_extension_reaches_2041():
    """Built the way a Scenario applied before the data load builds its parameters (reset, change, process), with
    a CPI path the default does not have, every extended series follows it to 2041."""
    from triple_lock import model_horizon

    path = {y: 0.02 + 0.001 * (y - 2030) for y in range(2030, 2042)}
    with model_horizon.installed():
        system = CountryTaxBenefitSystem()
        system.reset_parameters()
        obr = system.parameters.gov.economic_assumptions.yoy_growth.obr
        for y, g in path.items():
            obr.consumer_price_index.update(period=f"year:{y}-01-01:1", value=g)
        system.process_parameters()
        p = system.parameters
        obr = p.gov.economic_assumptions.yoy_growth.obr
        for y in range(2031, 2042):
            assert obr.lagged_cpi(f"{y}-06-01") == pytest.approx(path[y - 1]), y
            assert obr.lagged_average_earnings(f"{y}-06-01") == pytest.approx(obr.average_earnings(f"{y - 1}-06-01")), y
            assert p.gov.economic_assumptions.yoy_growth.triple_lock(f"{y}-06-01") == round(
                max(obr.average_earnings(f"{y - 1}-06-01"), path[y - 1], 0.025), 3), y


def test_econ_changes_cover_every_calendar_year_and_move_rpi_with_cpi(parameters):
    spec = {"cpi": {y: 0.03 for y in CALENDAR_YEARS}, "earnings": {y: 0.04 for y in CALENDAR_YEARS}}
    changes = engine.econ_changes(spec, parameters)
    obr = parameters.gov.economic_assumptions.yoy_growth.obr
    for series in ("consumer_price_index", "average_earnings", "rpi", "cpih"):
        keys = changes[f"gov.economic_assumptions.yoy_growth.obr.{series}"]
        assert sorted(keys) == [f"year:{y}-01-01:1" for y in CALENDAR_YEARS]
    for y in CALENDAR_YEARS:
        moved = changes["gov.economic_assumptions.yoy_growth.obr.rpi"][f"year:{y}-01-01:1"] - float(obr.rpi(f"{y}-01-01"))
        assert moved == pytest.approx(0.03 - float(obr.consumer_price_index(f"{y}-01-01")))


def test_statutory_april_2027_inputs():
    """The April 2027 earnings leg is published May-July 2026 AWE; CPI is August 2026 until September is out."""
    s = statutory_inputs()
    assert s["earnings"] == pytest.approx(0.039)
    assert s["cpi"] == pytest.approx(0.031)
    # September CPI would need a larger jump from August than any since 1997 to set the rate
    assert s["cpi_rise_needed_to_set_triple_lock"] > s["largest_aug_to_sep_cpi_rise"]


def test_central_path_sources():
    c = central_path()
    assert sorted(c["calendar"]["cpi"]) == CALENDAR_YEARS
    assert c["statutory"]["earnings"][BASE_YEAR] == pytest.approx(0.039)
    assert {c["calendar_source"][y] for y in range(2027, 2031)} == {"efo_calendar"}
    assert {c["calendar_source"][y] for y in range(2031, FINAL_YEAR + 1)} == {"lted_converted"}
    # The conversion reproduces the OBR's own calendar-year figures to within 0.1 point where both exist.
    assert c["conversion_check_max_abs_error"] < 0.001
    assert fiscal_to_calendar({2030: 0.02, 2031: 0.04}, 2031) == pytest.approx(0.035)
    # On the central path the 2.5% floor sets the triple lock for April 2028-2031 (the OBR's own row says 2.5%).
    r = rules.uprating_path("triple_lock", c["statutory"]["cpi"], c["statutory"]["earnings"], HORIZON)
    assert all(r[y] == 0.025 for y in range(2028, 2032))
    assert all(c["obr_triple_lock_uprating"][y - 1] == pytest.approx(0.025) for y in range(2028, 2032))


def test_example_households_account_for_every_pound():
    """On a path where the plan bites, each example's change in net income is its State Pension change plus the
    changes in Pension Credit, Housing Benefit and council tax reduction, less the change in income tax; the
    renters' Housing Benefit and the Pension Credit recipient's top-up respond."""
    from triple_lock import households, model_horizon, trajectories

    spec = {k: v for k, v in trajectories.central_spec(central_path()).items() if k not in ("id", "label", "source")}
    spec["statutory_earnings"] = {**spec["statutory_earnings"], 2031: 0.0, 2032: 0.0}
    spec["statutory_cpi"] = {**spec["statutory_cpi"], 2031: 0.05}
    with model_horizon.installed():
        out = households.run_examples(spec)["results"]
    for example, r in out.items():
        tl, bp = r["triple_lock"], r["burnham_2030"]
        for y in HORIZON:
            d = {k: bp[k][y] - tl[k][y] for k in tl}
            explained = d["state_pension"] + d["pension_credit"] + d["housing_benefit"] + d["council_tax_reduction"] - d["income_tax"]
            assert d["net_income"] == pytest.approx(explained, abs=1.0), (example, y)
            if y < 2030:
                assert d["state_pension"] == 0
        assert r["burnham_2030"]["state_pension"][FINAL_YEAR] < r["triple_lock"]["state_pension"][FINAL_YEAR]
    assert out["social_renter"]["burnham_2030"]["housing_benefit"][FINAL_YEAR] > out["social_renter"]["triple_lock"]["housing_benefit"][FINAL_YEAR]
    assert out["basic_renter"]["burnham_2030"]["pension_credit"][FINAL_YEAR] > out["basic_renter"]["triple_lock"]["pension_credit"][FINAL_YEAR]
