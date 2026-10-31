"""Budget-wheel projection capabilities, using parameters and invented inputs only."""

import importlib.metadata
from types import SimpleNamespace

import pytest

pytest.importorskip("policyengine_uk")

import policyengine_uk.tax_benefit_system as tbs
from policyengine_uk.utils.scenario import Scenario

from triple_lock import engine, model_horizon

LAGGED_CPI = "gov.economic_assumptions.indices.obr.lagged_cpi"
SEPTEMBER_CPI = "gov.economic_assumptions.indices.september_cpi_uprating"
# The index gov.benefit_uprating_cpi names on each Budget wheel: #715's 2.147.2 predates #2557; d2011's binding
# 2.151.0 has it (and still lacks #2576 and #2340).
BENEFIT_INDEX = {"2.147.2": LAGGED_CPI, "2.151.0": SEPTEMBER_CPI}
DEPENDENT_PATHS = ["gov.dwp.pension_credit.guarantee_credit.minimum_guarantee.SINGLE",
                   "gov.dwp.pension_credit.guarantee_credit.minimum_guarantee.COUPLE",
                   "gov.dwp.pension_credit.savings_credit.threshold.SINGLE",
                   "gov.dwp.pension_credit.savings_credit.threshold.COUPLE",
                   *(f"gov.dwp.housing_benefit.allowances.{family}.{cohort}"
                     for family in ("single", "couple", "lone_parent")
                     for cohort in ("aged", "aged_from_cutoff"))]


def budget_wheel():
    version = importlib.metadata.version("policyengine-uk")
    if version not in BENEFIT_INDEX:
        pytest.skip(f"the Budget wheels are {sorted(BENEFIT_INDEX)}, not {version}")
    return version


def test_budget_wheel_exact_sources_and_absent_links():
    version = budget_wheel()
    model_horizon.check_upstream()
    parameters = engine.model_parameters()
    sc = parameters.gov.dwp.pension_credit.savings_credit
    assert "maximum" not in sc.children
    assert not callable(getattr(tbs, "project_savings_credit_threshold", None))
    assert not callable(getattr(tbs, "project_pension_age_allowances", None))
    assert parameters.gov.benefit_uprating_cpi.metadata["uprating"] == BENEFIT_INDEX[version]
    assert engine.AGE_ADDITION not in engine.state_pension_parts()


def test_the_guarantee_and_its_dependent_amounts_keep_the_lagged_calendar_cpi_projection():
    """On 2.147.2 through gov.benefit_uprating_cpi; on 2.151.0, where #2557 moved that index to September CPI, by
    naming lagged CPI themselves. So d1753's installed projection is the same on both wheels."""
    version = budget_wheel()
    parameters = engine.model_parameters()
    for path in DEPENDENT_PATHS:
        named = parameters.get_child(path).metadata["uprating"]
        assert named == ("gov.benefit_uprating_cpi" if version == "2.147.2" else LAGGED_CPI), path


@pytest.mark.parametrize("linked_threshold, linked_hb", [(False, False), (True, False), (False, True), (True, True)])
def test_maximum_alone_does_not_enable_linked_amounts(monkeypatch, linked_threshold, linked_hb):
    """A future maximum without #2576 must preserve installed CPI amounts."""
    monkeypatch.setattr(tbs, "project_savings_credit_threshold", (lambda p: p) if linked_threshold else None,
                        raising=False)
    monkeypatch.setattr(tbs, "project_pension_age_allowances", (lambda p: p) if linked_hb else None,
                        raising=False)
    maximum = SimpleNamespace(children={family: lambda _: 20.0 for family in ("SINGLE", "COUPLE")})
    sc = SimpleNamespace(children={"maximum": maximum}, maximum=maximum,
                         rate=SimpleNamespace(phase_in=lambda _: .6))
    system = SimpleNamespace(parameters=SimpleNamespace(gov=SimpleNamespace(dwp=SimpleNamespace(
        pension_credit=SimpleNamespace(savings_credit=sc)))), reset_parameter_caches=lambda: None)
    applied = []
    monkeypatch.setattr(Scenario, "from_reform", lambda changes: SimpleNamespace(
        simulation_modifier=lambda _: applied.append(changes)))
    guarantee = engine.PENSION_CREDIT_GUARANTEE["single"]
    engine.set_flat_rates(SimpleNamespace(tax_benefit_system=system), {}, {guarantee: {2030: 300.0}})
    changes = applied.pop()
    threshold = "gov.dwp.pension_credit.savings_credit.threshold.SINGLE"
    assert (threshold in changes) is linked_threshold
    if linked_threshold:
        assert next(iter(changes[threshold].values())) == pytest.approx(300 - 20 / .6)
    for kind in ("single", "lone_parent"):
        path = f"gov.dwp.housing_benefit.allowances.{kind}"
        assert (path + ".aged" in changes) is linked_hb
        assert (path + ".aged_from_cutoff" in changes) is linked_hb
        if linked_hb:
            assert next(iter(changes[path + ".aged"].values())) == 320
            assert next(iter(changes[path + ".aged_from_cutoff"].values())) == 300


def test_budget_guarantee_override_leaves_installed_dependent_projections():
    budget_wheel()
    from policyengine_uk import CountryTaxBenefitSystem

    system = CountryTaxBenefitSystem()
    paths = ["gov.dwp.pension_credit.savings_credit.threshold.SINGLE",
             "gov.dwp.pension_credit.savings_credit.threshold.COUPLE",
             *(f"gov.dwp.housing_benefit.allowances.{family}.{cohort}"
               for family in ("single", "couple", "lone_parent")
               for cohort in ("aged", "aged_from_cutoff"))]
    before = {path: {year: system.parameters.get_child(path)(f"{year}-06-01")
                     for year in engine.HORIZON} for path in paths}
    guarantees = engine.pension_credit_levels(system.parameters, {year: .08 for year in engine.STATUTORY_YEARS})
    engine.set_flat_rates(SimpleNamespace(tax_benefit_system=system), {}, guarantees)
    for path, years in before.items():
        for year, value in years.items():
            assert system.parameters.get_child(path)(f"{year}-06-01") == value


def test_budget_benefit_path_check_follows_the_index_the_wheel_names(monkeypatch):
    """2.147.2: the previous calendar year's CPI. 2.151.0 (#2557): the previous September's CPI, to 0.1 point,
    never cut."""
    version = budget_wheel()
    from policyengine_uk import Simulation
    from triple_lock import central, trajectories

    spec = trajectories.central_spec(central.central_path())
    parameters = engine.model_parameters()
    # The public path starts in 2027. run_path sets 2026 from the forecast
    # file (base_year_growth) for the first benefit uprating's one-year lag.
    calendar = engine.path_calendar(spec)
    simulation = Simulation(situation={
        "people": {"person": {"age": {2026: 70}}},
        "benunits": {"unit": {"members": ["person"]}},
        "households": {"household": {"members": ["person"]}},
    }, scenario=Scenario(parameter_changes=engine.scenario_changes(spec, parameters),
                         applied_before_data_load=True))
    employment = {engine.BASE_YEAR: 100.0}
    for year in engine.HORIZON:
        employment[year] = employment[year - 1] * (1 + spec["earnings"][year])
    monkeypatch.setattr(engine, "_unweighted_total", lambda sim, variable, year: employment[year])
    result = engine.path_following(simulation,
        calendar,
        {"cpi": spec["statutory_cpi"], "earnings": spec["statutory_earnings"]})
    benefit = result["benefit_uprating_cpi"]
    if version == "2.147.2":
        assert benefit["expected"] == {year: calendar["cpi"][year - 1] for year in engine.HORIZON}
        assert "calendar CPI growth the year before" in benefit["follows"]
    else:
        assert benefit["expected"] == {year: max(engine.published_precision(spec["statutory_cpi"][year - 1]), 0.0)
                                       for year in engine.HORIZON}
        assert benefit["follows"].startswith("September CPI the year before")
    assert benefit["max_abs_error"] <= engine.PATH_GROWTH_TOL
