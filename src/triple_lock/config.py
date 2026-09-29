"""Fixed choices for the triple lock analysis.

Everything a reader might want to check or change lives here: the policy
set, the horizon, the parameter paths the reform touches, and the method
limitations the results file reports.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Fiscal years named by start year ("2027" = 2027-28). The alternative rule
# applies from the April 2027 uprating; 2026-27 rates are already set.
BASE_YEAR = 2026
HORIZON = list(range(2027, 2035))
FINAL_YEAR = HORIZON[-1]
# Distributional tables are reported for the final horizon year (schema
# fields) and additionally for the end of this Parliament's forecast window.
EXTRA_DISTRIBUTION_YEAR = 2029

TRIPLE_LOCK_FLOOR = 0.025
# create_triple_lock.py rounds each year's rate to 3 dp; the central run
# applies the same rounding to every rule so that a rule and the triple lock
# are identical in years where they pick the same component.
CENTRAL_RATE_DECIMALS = 3

POLICIES = {
    "triple_lock": {
        "label": "Triple lock (current policy)",
        "rule": "max(CPI, earnings, 2.5%)",
    },
    "double_lock": {"label": "Double lock", "rule": "max(CPI, earnings)"},
    "earnings_link": {"label": "Earnings link", "rule": "earnings"},
    "cpi_link": {"label": "CPI link", "rule": "CPI"},
}
BASELINE_POLICY = "triple_lock"
ALTERNATIVES = [p for p in POLICIES if p != BASELINE_POLICY]

# Only the flat-rate State Pension is triple-locked. These are the parameters
# the reform overwrites, year by year.
FLAT_RATE_PARAMETERS = {
    "new_state_pension": "gov.dwp.state_pension.new_state_pension.amount",
    "basic_state_pension": "gov.dwp.state_pension.basic_state_pension.amount",
}
# Growth series the model's own triple lock is built from
# (policyengine_uk/parameters/gov/dwp/state_pension/triple_lock/create_triple_lock.py).
CPI_PARAMETER = "gov.economic_assumptions.yoy_growth.obr.consumer_price_index"
EARNINGS_PARAMETER = "gov.economic_assumptions.yoy_growth.obr.average_earnings"
MODEL_TRIPLE_LOCK_PARAMETER = "gov.economic_assumptions.yoy_growth.triple_lock"

FORECAST_SOURCE = (
    "PolicyEngine UK economic assumptions (gov.economic_assumptions.yoy_growth.obr): "
    "OBR March 2026 EFO for 2026-2030 (CPI Table 1.7, average earnings Table 1.6); "
    "for 2031+ PolicyEngine's convergence to OBR long-run assumptions "
    "(CPI 2%, earnings ramping to 3.83%)"
)
FORECAST_SOURCE_URL = (
    "https://obr.uk/docs/d055fbf02d5b3g6jq8l2/"
    "efo-march-2026-detailed-forecast-tables-economy.xlsx"
)

# Household-level variables used for the fiscal decomposition. Each is summed
# with household weights; the net cost is the change in gov_balance.
FISCAL_COMPONENTS = {
    "state_pension_flat_rate": ["basic_state_pension", "new_state_pension"],
    "additional_state_pension": ["additional_state_pension"],
    "pension_credit": ["pension_credit"],
    "housing_benefit": ["housing_benefit"],
    "universal_credit": ["universal_credit"],
    "council_tax_reduction": ["council_tax_benefit"],
    "winter_fuel_payment": ["winter_fuel_allowance"],
    "income_tax": ["income_tax"],
}

# Uncertainty.
ERROR_CSV = REPO / "data" / "obr_forecast_errors.csv"
N_DRAWS = 20_000
MC_SEED = 20260929
QUANTILES = [5, 10, 25, 50, 75, 90, 95]
FAN_QUANTILES = [10, 50, 90]
# Representative paths are chosen on the final-year cost of the triple lock
# against this alternative (the widest gap, so the ranking is most informative).
REPRESENTATIVE_RANKING_POLICY = "cpi_link"

# Sensitivities: drop vintages whose blocks target the pandemic and energy
# shock years; add noise for the OBR-earnings vs May-July AWE gap (SD of the
# gap 2010-2024, docs/sources.md).
EX_COVID_TARGET_YEARS = range(2020, 2024)
AWE_GAP_SD = 0.014

# Quarterly proxies closer to the statutory timing (September CPI, May-July
# AWE) from the March 2026 EFO; used only for an analytic timing sensitivity.
CENTRAL_FORECAST_CSV = REPO / "data" / "obr_central_forecast.csv"
QUARTERLY_GROWTH_YEARS = range(2026, 2031)
# Block length for the vintage bootstrap: spring vintages cover horizons 1-4.
BLOCK_HORIZON = 4

OUTPUT = REPO / "data" / "triple_lock_results.json"
DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "triple_lock_results.json"

METHOD_LIMITATIONS = [
    "The model's triple lock rate for year y is max(OBR calendar-year CPI growth "
    "in y-1, OBR calendar-year average earnings growth in y-1, 2.5%). The statutory "
    "uprating uses September CPI and May-July AWE total pay; the calendar-year "
    "measures are a proxy. In particular the April 2027 rate (3.4%) comes from the "
    "OBR's March 2026 forecast of 2026 earnings growth, although May-July 2026 AWE "
    "growth has since been published.",
    "Every rule is applied from the April 2027 uprating and compounds on the "
    "2026-27 rates (new State Pension £241.30, basic £184.90 a week). Weekly "
    "amounts are not rounded to 5p.",
    "Only the basic and new State Pension are uprated under each rule. The "
    "additional State Pension (and new State Pension protected payments) is held "
    "at its baseline value in every scenario: PolicyEngine uprates it with the "
    "flat-rate amount, so it would otherwise move with the reform although in law "
    "it is CPI-linked. Pension Credit, Housing Benefit and other rates follow "
    "PolicyEngine's own uprating and are identical across scenarios.",
    "The Enhanced FRS population is not aged forward beyond the survey: person ages "
    "are held at their data values while the basic/new State Pension cohort cut-off "
    "advances a year each year, so by 2033 every pensioner is modelled as on the new "
    "State Pension. Total spending levels in the early 2030s are therefore "
    "approximate; costs are driven by the gap between uprating indices and are much "
    "less sensitive to this.",
    "No behavioural response (saving, labour supply, retirement timing) and no "
    "change in Pension Credit take-up beyond PolicyEngine's static entitlement "
    "model. Net costs include income tax, Pension Credit, Housing Benefit, "
    "Universal Credit, Council Tax Reduction and Winter Fuel Payment interactions, "
    "but not indirect taxes on the resulting change in spending.",
    "Earnings growth is the OBR's national-accounts average earnings (wages and "
    "salaries per employee), not the May-July AWE total pay growth the triple lock "
    "uses; the gap has an SD of about 1.4pp a year (2010-2024). The forecast-error "
    "Monte Carlo covers OBR-measure errors only; a sensitivity adds N(0, 1.4pp) "
    "noise to earnings.",
    "Growth for 2031-2033 (setting the April 2032-2034 upratings) is PolicyEngine's "
    "convergence path to its long-run assumptions (earnings 3.3-3.7%), above the "
    "OBR's long-term determinants (fiscal-year earnings 2.8-3.4%); later-year "
    "costs of CPI-linking are correspondingly larger.",
    "The forecast-error Monte Carlo prices the final-year gross cost by linear "
    "scaling of PolicyEngine's spending with the uprating index; representative "
    "paths are re-run in full PolicyEngine to check it. Historical errors come from "
    "about a dozen vintages, so tail percentiles rest on few distinct blocks.",
    "Net costs inherit PolicyEngine's means-tested eligibility cliffs. Small "
    "pension changes can switch a single heavily weighted survey household onto "
    "Housing Benefit: one record weighted ~40,000 adds about £0.3bn to every "
    "alternative's 2029-30 net figure (and to the CPI link's in 2030-31 and 2031-32), "
    "and another weighted ~80,000 moves the CPI link's 2034-35 net by about £0.4bn. "
    "cost_vs_triple_lock_bn[policy].largest_single_household reports this each year.",
    "Costs are in nominal £ in each fiscal year, not deflated.",
]
