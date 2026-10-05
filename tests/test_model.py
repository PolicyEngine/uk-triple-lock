"""Checks against policyengine-uk itself, on hypothetical households and the parameter tree (no dataset).

They prove the mechanisms the engine relies on: overwriting the flat-rate
amounts moves the State Pension by exactly the ratio of the rules' levels; a
reform to the triple-lock flags moves nothing (the rate is built at load time);
our triple lock reproduces the model's own from its statutory inputs, which a
path's inputs set before the parameters are processed replace; the State
Pension age follows the Pensions Act timetable by date of birth; and a growth
path reaches every derived series to the final year.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

pytest.importorskip("policyengine_uk")

from policyengine_uk import CountryTaxBenefitSystem, Simulation  # noqa: E402

from triple_lock import engine, rules  # noqa: E402
from triple_lock.central import central_path, fiscal_to_calendar, statutory_inputs  # noqa: E402
from triple_lock.config import (  # noqa: E402
    BASE_YEAR,
    CALENDAR_YEARS,
    CENTRAL_RATE_DECIMALS,
    FINAL_YEAR,
    FLAT_RATE_PARAMETERS,
    HORIZON,
    MODEL_TRIPLE_LOCK_PARAMETER,
    STATUTORY_PARAMETERS,
    STATUTORY_YEARS,
)

YEARS = HORIZON  # policyengine-uk 2.118.0 builds its own triple lock to 2074


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
    """The model's own statutory inputs (published, then calendar growth plus the OBR's forecast gap)."""
    read = {s: parameters.get_child(path) for s, (path, _) in STATUTORY_PARAMETERS.items()}
    month_day = {s: md for s, (_, md) in STATUTORY_PARAMETERS.items()}
    return tuple({y - 1: float(read[s](f"{y - 1}-{month_day[s]}")) for y in YEARS} for s in ("cpi", "earnings"))


def levels(parameters, policy, cpi, earnings):
    base = engine.base_levels(parameters)
    r = rules.uprating_path(policy, cpi, earnings, YEARS, decimals=CENTRAL_RATE_DECIMALS)
    return {name: rules.level_path(base[name], r, YEARS) for name in base}, r


def test_our_triple_lock_reproduces_the_models_own(parameters):
    """From its statutory inputs (#1939), in every year of the horizon: April 2027 is 3.9%, from the published
    May-July 2026 AWE (provisional: the 15 September first estimate until the October release)."""
    cpi, earnings = model_path(parameters)
    assert earnings[2026] == pytest.approx(0.039)
    lv, r = levels(parameters, "triple_lock", cpi, earnings)
    model_rate = parameters.get_child(MODEL_TRIPLE_LOCK_PARAMETER)
    assert float(model_rate("2027-06-01")) == pytest.approx(0.039, abs=1e-12)
    for y in YEARS:
        assert float(model_rate(f"{y}-06-01")) == pytest.approx(r[y], abs=1e-12)
        assert float(model_rate(f"{y}-06-01")) == engine.model_triple_lock_rate(earnings[y - 1], cpi[y - 1])
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


def processed(changes, install=True):
    """The parameter tree built the way a Scenario applied before the data load builds it: reset, change, process."""
    from triple_lock import model_horizon

    def build():
        system = CountryTaxBenefitSystem()
        system.reset_parameters()
        for path, values in changes.items():
            node = system.parameters.get_child(path)
            for period, value in values.items():
                node.update(period=period, value=value)
        system.process_parameters()
        return system.parameters

    if not install:
        return build()
    with model_horizon.installed():
        return build()


def test_every_derived_series_follows_a_path_to_the_final_year():
    """With a calendar path the default does not have, set before processing, lagged CPI and earnings, the
    statutory inputs (calendar growth after the OBR's forecast gaps end in 2031), the model's triple lock and the
    private pension uprating (the one extension model_horizon still makes) follow it to the final year."""
    obr = "gov.economic_assumptions.yoy_growth.obr"
    cpi = {y: 0.02 + 0.001 * (y - 2030) for y in range(2026, FINAL_YEAR + 2)}
    earnings = {y: 0.03 + 0.0005 * (y - 2030) for y in range(2026, FINAL_YEAR + 2)}
    p = processed({f"{obr}.consumer_price_index": {f"year:{y}-01-01:1": v for y, v in cpi.items()},
                   f"{obr}.average_earnings": {f"year:{y}-01-01:1": v for y, v in earnings.items()}})
    g = p.gov.economic_assumptions
    rpi = g.yoy_growth.obr.rpi
    for y in range(2032, FINAL_YEAR + 1):
        assert g.yoy_growth.obr.lagged_cpi(f"{y}-06-01") == pytest.approx(cpi[y - 1]), y
        assert g.yoy_growth.obr.lagged_average_earnings(f"{y}-06-01") == pytest.approx(earnings[y - 1]), y
        for s, (path, month_day) in STATUTORY_PARAMETERS.items():
            assert p.get_child(path)(f"{y - 1}-{month_day}") == pytest.approx((cpi if s == "cpi" else earnings)[y - 1])
        assert g.yoy_growth.triple_lock(f"{y}-06-01") == engine.model_triple_lock_rate(earnings[y - 1], cpi[y - 1]), y
        assert g.yoy_growth.obr.private_pension_index(f"{y}-06-01") == pytest.approx(min(rpi(f"{y - 1}-06-01"), 0.05))
        index = g.indices.obr.private_pension_index
        assert index(f"{y}-06-01") / index(f"{y - 1}-06-01") - 1 == pytest.approx(
            g.yoy_growth.obr.private_pension_index(f"{y}-06-01"), abs=2e-4), y


def test_a_path_sets_the_models_statutory_inputs_and_so_its_triple_lock():
    """engine.statutory_changes replaces the published figure and the forecast (calendar growth plus the forecast
    gap) in every year it covers, and the model's triple lock is built from them; a calendar change alone moves the
    forecast inputs one for one, the gap kept."""
    obr = "gov.economic_assumptions.yoy_growth.obr"
    spec = {"statutory_cpi": {y: 0.0105 + 0.002 * (y - 2026) for y in STATUTORY_YEARS},
            "statutory_earnings": {y: 0.0441 - 0.0015 * (y - 2026) for y in STATUTORY_YEARS}}
    p = processed(engine.statutory_changes(spec))
    for y in HORIZON:
        for s, (path, month_day) in STATUTORY_PARAMETERS.items():
            assert p.get_child(path)(f"{y - 1}-{month_day}") == spec[f"statutory_{s}"][y - 1]
        assert p.get_child(MODEL_TRIPLE_LOCK_PARAMETER)(f"{y}-06-01") == engine.model_triple_lock_rate(
            spec["statutory_earnings"][y - 1], spec["statutory_cpi"][y - 1]), y
    default = processed({})
    shifted = processed({f"{obr}.consumer_price_index": {"year:2028-01-01:1": float(
        default.get_child(f"{obr}.consumer_price_index")("2028-01-01")) + 0.01}})
    path = STATUTORY_PARAMETERS["cpi"][0]
    assert shifted.get_child(path)("2028-09-01") == pytest.approx(default.get_child(path)("2028-09-01") + 0.01)
    assert shifted.get_child(path)("2025-09-01") == default.get_child(path)("2025-09-01")  # published: unmoved


# Pensions Act 1995 Sch 4 para 1 as amended (2014 s.26): State Pension age in months by date of birth, for the
# cohorts a survey age of 60 to 80 can reach in 2026-2039. (Women born 6 April 1950 to 5 October 1954 follow the
# day tables, and are left out.)
def statutory_age_months(birth_month, male):
    """``birth_month``: months since January of year 0 on the grid whose months start on the 6th."""
    def month(y, m):  # the grid month starting on the 6th of month m
        return 12 * y + m - 1
    if male and birth_month < month(1953, 12):
        return 780
    if birth_month < month(1954, 10):
        return None
    if birth_month < month(1960, 4):
        return 792
    if birth_month < month(1961, 3):
        return 793 + int(birth_month - month(1960, 4))  # 66 years and 1 to 11 months
    if birth_month < month(1977, 4):
        return 804
    return None


@pytest.mark.parametrize("year", [2026, 2027, 2028, 2033, FINAL_YEAR])
def test_state_pension_age_follows_the_timetable_by_date_of_birth(year):
    """Synthetic checks around the rise to 67 (#21): a person of a given whole age and months past their birthday at
    6 October has the State Pension age the Act gives their date of birth (to within a day), and is over it exactly
    when the months since it are not negative. With survey ages held, the survey's 66-year-olds are partly over it in
    2026-27 and 2027-28, and below it from 2028-29."""
    cases = [(age, months, male) for age in (60, 64, 65, 66, 67, 70, 75, 80)
             for months in (0.5, 2.5, 5.5, 6.5, 9.5, 11.5) for male in (False, True)]
    people = {f"p{i}": {"age": {year: age}, "months_since_last_birthday": {year: months}, "is_male": {year: male}}
              for i, (age, months, male) in enumerate(cases)}
    sim = Simulation(situation={"people": people,
                                "benunits": {f"b{i}": {"members": [p]} for i, p in enumerate(people)},
                                "households": {f"h{i}": {"members": [p]} for i, p in enumerate(people)}})
    spa = sim.calculate("state_pension_age", year)
    over = sim.calculate("is_SP_age", year)
    checked = 0
    for i, (age, months, male) in enumerate(cases):
        birth = 12 * year + 9 - (12 * age + months)  # 6 October of the fiscal year, less the exact age
        expected = statutory_age_months(birth, male)
        if expected is None:
            continue
        checked += 1
        assert 12 * float(spa[i]) == pytest.approx(expected, abs=1 / 28), (year, age, months, male)
        assert bool(over[i]) == (12 * age + months >= expected), (year, age, months, male)
    assert checked >= 40
    sixty_six = [bool(over[i]) for i, (age, _, _) in enumerate(cases) if age == 66]
    sixty_seven = [bool(over[i]) for i, (age, _, _) in enumerate(cases) if age == 67]
    assert all(sixty_seven)
    assert (0 < sum(sixty_six) < len(sixty_six)) if year in (2026, 2027) else not any(sixty_six)


def test_no_reform_uses_the_removed_state_pension_age_parameters():
    """The scalar ages the engine used to set (gov.dwp.state_pension.age.male / female) are gone upstream: a reform
    naming them fails with directions, and the engine's scenario names none."""
    from policyengine_uk.utils.scenario import Scenario

    with pytest.raises(Exception, match="age_by_birth_date"):
        Scenario.from_reform({"gov.dwp.state_pension.age.female": {"2028-01-01.2028-12-31": 67}}).simulation_modifier(
            Simulation(situation=situation(2028)))
    spec = {k: v for k, v in trajectories_central().items() if k not in ("id", "label", "source")}
    assert not [p for p in engine.scenario_changes(spec, CountryTaxBenefitSystem().parameters)
                if p.startswith("gov.dwp.state_pension.age")]


def trajectories_central():
    from triple_lock import trajectories

    return trajectories.central_spec(central_path())


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
    changes in Pension Credit, Housing Benefit, council tax reduction and Winter Fuel Payment (means-tested above
    an income threshold), less the change in income tax; the
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
            explained = (d["state_pension"] + d["pension_credit"] + d["housing_benefit"] + d["council_tax_reduction"]
                         + d["winter_fuel_payment"] - d["income_tax"])
            assert d["net_income"] == pytest.approx(explained, abs=1.0), (example, y)
            if y < 2030:
                assert d["state_pension"] == 0
        assert r["burnham_2030"]["state_pension"][FINAL_YEAR] < r["triple_lock"]["state_pension"][FINAL_YEAR]
    assert out["social_renter"]["burnham_2030"]["housing_benefit"][FINAL_YEAR] > out["social_renter"]["triple_lock"]["housing_benefit"][FINAL_YEAR]
    assert out["basic_renter"]["burnham_2030"]["pension_credit"][FINAL_YEAR] > out["basic_renter"]["triple_lock"]["pension_credit"][FINAL_YEAR]
    # On the guarantee under both rules (the basic State Pension is below it), the pensioner comes out exactly even:
    # Pension Credit tops the lower pension back up, and council tax reduction disregards a guarantee credit
    # recipient's whole income (policyengine-uk 2.104.2; SI 2012/2885 Sch 1 para 13), so it does not move.
    on_guarantee = out["basic_renter"]
    for y in HORIZON:
        assert on_guarantee["triple_lock"]["pension_credit"][y] > 0 and on_guarantee["burnham_2030"]["pension_credit"][y] > 0
        assert on_guarantee["burnham_2030"]["net_income"][y] == pytest.approx(on_guarantee["triple_lock"]["net_income"][y],
                                                                             abs=0.01), y
        assert on_guarantee["burnham_2030"]["council_tax_reduction"][y] == pytest.approx(
            on_guarantee["triple_lock"]["council_tax_reduction"][y], abs=0.01), y


TAKE_UP = ("claims_all_entitled_benefits", "would_claim_housing_benefit", "would_claim_council_tax_reduction",
           "would_claim_pc")


def test_examples_claim_in_full_without_take_up_inputs():
    """No example reports a benefit or sets a take-up flag, so policyengine-uk takes each to claim in full, and the
    renters' Housing Benefit is a new pension-age claim (SI 2014/1230 reg 6A(4)). Any reported CTC, WTC, UC, HB,
    JSA, IS or ESA amount would switch claims_all_entitled_benefits off for the whole simulation."""
    from triple_lock import households

    index = households.cpi_index({y: 0.02 for y in CALENDAR_YEARS})
    for example, e in households.EXAMPLES.items():
        s = households.situation(example, index)
        inputs = set(s["people"]["pensioner"]) | set(s["benunits"]["benunit"]) | set(s["households"]["household"])
        assert {i for i in inputs if i.endswith("_reported")} == {"state_pension_reported"}, example
        assert not inputs & {*TAKE_UP, "would_claim_uc"}, example
        sim = Simulation(situation=s)
        for flag in TAKE_UP:
            assert sim.calculate(flag, FINAL_YEAR).all(), (example, flag)
        if e["rent_weekly"]:
            assert sim.calculate("housing_benefit_eligible", FINAL_YEAR).all(), example
            assert sim.calculate("housing_benefit", FINAL_YEAR).sum() > 0, example


@settings(max_examples=20, deadline=None, derandomize=True)
@given(age=st.integers(67, 100), partner_age=st.one_of(st.none(), st.integers(67, 100)),
       rent_weekly=st.integers(0, 400), council_tax=st.integers(0, 4_000), private_pension=st.integers(0, 30_000),
       tenure=st.sampled_from(["RENT_FROM_COUNCIL", "RENT_FROM_HA", "RENT_PRIVATELY", "OWNED_OUTRIGHT"]))
def test_continuing_award_inputs_change_nothing_for_pensioners(age, partner_age, rent_weekly, council_tax,
                                                              private_pension, tenure):
    """Differential: for a family whose adults are all over State Pension age, every output the examples report is
    the same with or without the continuing-award inputs they needed before policyengine-uk 2.102.5 (reported
    Housing Benefit, claims_all_entitled_benefits and no Universal Credit claim)."""
    from triple_lock import households

    year = 2027
    people = {"p": age} | ({"q": partner_age} if partner_age else {})

    def run(continuing_award):
        # As in the examples: the full flat rate and no additional State Pension.
        persons = {name: {"age": {year: a}, "state_pension_reported": {year: 1_000_000},
                          "additional_state_pension": {year: 0.0},
                          "private_pension_income": {year: private_pension if name == "p" else 0}}
                   for name, a in people.items()}
        benunit = {"members": list(people)}
        if continuing_award:
            persons["p"]["housing_benefit_reported"] = {year: 1.0}
            benunit |= {"claims_all_entitled_benefits": {year: True}, "would_claim_uc": {year: False}}
        sim = Simulation(situation={
            "people": persons,
            "benunits": {"b": benunit},
            "households": {"h": {"members": list(people), "rent": {year: rent_weekly * households.WEEKS},
                                 "council_tax": {year: council_tax}, "tenure_type": {year: tenure}}},
        })
        return {v: float(sim.calculate(v, year).sum()) for vs in households.OUTPUTS.values() for v in vs}

    assert run(True) == run(False)


def test_model_horizon_changes_only_the_private_pension_uprating():
    """Differential: with the extension installed, every parameter of the processed tree equals the unextended
    model's on every date to the final year, except the private pension uprating (and its index), which upstream
    stops at 2034. Calendar-dated parameters (preserve_calendar_dates) are among them."""
    from policyengine_core.parameters import Parameter

    def leaves(parameters):
        # In traversal order: get_descendants can reach two parameter objects under one name.
        return [p for p in parameters.get_descendants() if isinstance(p, Parameter)]

    upstream = leaves(processed({}, install=False))
    extended = leaves(processed({}))
    assert [p.name for p in upstream] == [p.name for p in extended]
    assert any((p.metadata or {}).get("preserve_calendar_dates") for p in upstream)
    dates = [f"{y}-{md}" for y in range(2015, FINAL_YEAR + 1) for md in ("01-01", "04-30", "06-01", "09-01")]

    def same(x, y):
        if np.all(np.asarray(x == y)):
            return True
        try:
            return bool(np.isnan(x) and np.isnan(y))
        except TypeError:  # strings and booleans
            return False

    differ = {a.name for a, b in zip(upstream, extended) for d in dates if not same(a(d), b(d))}
    assert differ == {"gov.economic_assumptions.yoy_growth.obr.private_pension_index",
                      "gov.economic_assumptions.indices.obr.private_pension_index"}, sorted(differ)[:10]
    early = [(a.name, d) for a, b in zip(upstream, extended) for d in dates if d < "2035" and not same(a(d), b(d))]
    assert not early, early[:10]
