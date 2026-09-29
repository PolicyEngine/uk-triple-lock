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
# No rule cuts the cash State Pension: a negative index gives a 0% uprating.
# (SSAA 1992 s150A requires an increase of at least earnings growth but does
# not require a cut when the index falls; the triple lock floors at 2.5%.)
ZERO_FLOOR = 0.0
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

# Sensitivities: drop vintages whose blocks target the 2022-23 inflation
# shock years; add noise for the OBR-earnings vs May-July AWE gap (SD of the
# gap 2010-2024, docs/sources.md).
EX_2022_23_TARGET_YEARS = (2022, 2023)
AWE_GAP_SD = 0.014

# Quarterly proxies closer to the statutory timing (September CPI, May-July
# AWE) from the March 2026 EFO; used only for an analytic timing sensitivity.
CENTRAL_FORECAST_CSV = REPO / "data" / "obr_central_forecast.csv"
QUARTERLY_GROWTH_YEARS = range(2027, 2031)

# The April 2027 uprating is set by September 2026 CPI (published 21 October
# 2026) and May-July 2026 AWE total pay growth (published 15 September 2026).
# The earnings leg uses the published figure; the CPI leg uses the latest
# published CPI 12-month rate (August 2026) until September CPI is out. These
# replace the calendar-year 2026 growth rates PolicyEngine uses (3.4% earnings).
STATUTORY_YEAR = 2026
AWE_CSV = REPO / "data" / "raw" / "ons_kac3_awe_total_pay_3m_yoy.csv"
AWE_PERIOD = "2026 JUL"
AWE_URL = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
    "earningsandworkinghours/timeseries/kac3/lms"
)
CPI_CSV = REPO / "data" / "raw" / "ons_d7g7_cpi_annual_rate.csv"
CPI_PERIOD = "2026 AUG"
CPI_URL = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23"
CPI_Q3_PERIOD = "2026Q3"
# August-to-September changes in the CPI 12-month rate from this year on
# bound how far September 2026 CPI can plausibly move from August.
CPI_AUG_SEP_FIRST_YEAR = 1997
# Paired gaps between the statutory inputs and the calendar-year proxies
# (September CPI minus calendar CPI; May-July AWE minus OBR earnings) by year.
CROSSCHECK_CSV = REPO / "data" / "obr_outturn_crosscheck.csv"
# Block length for the vintage bootstrap: spring vintages cover horizons 1-4.
BLOCK_HORIZON = 4

OUTPUT = REPO / "data" / "triple_lock_results.json"
DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "triple_lock_results.json"

METHOD_LIMITATIONS = [
    "The model's triple lock rate for year y is max(OBR calendar-year CPI growth "
    "in y-1, OBR calendar-year average earnings growth in y-1, 2.5%). The statutory "
    "uprating uses September CPI and May-July AWE total pay; the calendar-year "
    "measures are a proxy. In particular the April 2027 rate (3.4%) comes from the "
    "OBR's March 2026 forecast of 2026 earnings growth; here it is replaced by published "
    "May-July 2026 AWE total pay growth (ONS KAC3, 3.9%) for the earnings leg and the latest "
    "published CPI 12-month rate (August 2026, 3.1%) for the CPI leg until September 2026 "
    "CPI is published on 21 October 2026. September CPI would have to exceed 3.9% to change "
    "the triple lock rate, a larger August-to-September move than any since 1997; it does "
    "set the CPI link's and double lock's April 2027 rates. Later years use the "
    "calendar-year proxies.",
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
    "advances a year each year, so by 2032-33 every pensioner is modelled as on the new "
    "State Pension. This raises flat-rate spending per point of the uprating index by "
    "about a tenth between 2027-28 and 2034-35, and the gross cost of every rule scales "
    "with it: later-year costs are overstated by that much relative to a fixed 2027-28 "
    "pensioner composition (central.composition_effect). The uncertainty costs are also "
    "given as % of final-year flat-rate spending, which this does not affect.",
    "No behavioural response (saving, labour supply, retirement timing) and no "
    "change in Pension Credit take-up beyond PolicyEngine's static entitlement "
    "model. Net costs include income tax, Pension Credit, Housing Benefit, "
    "Universal Credit, Council Tax Reduction and Winter Fuel Payment interactions, "
    "but not indirect taxes on the resulting change in spending.",
    "Earnings growth is the OBR's national-accounts average earnings (wages and "
    "salaries per employee), not the May-July AWE total pay growth the triple lock "
    "uses; the gap has an SD of about 1.4pp a year (2010-2024), and September CPI "
    "differs from calendar-year CPI by an SD of about 0.5pp. The headline Monte Carlo "
    "is therefore a distribution for the calendar-year proxies, conditional on the "
    "proxies tracking the statutory inputs. uncertainty.sensitivity_statutory_gaps adds "
    "each drawn target year's historical pair of gaps (de-meaned), keeping their joint, "
    "serial and forecast-error comovement; sensitivity_awe_gap adds independent "
    "N(0, 1.4pp) earnings noise instead.",
    "Growth for 2031-2033 (setting the April 2032-2034 upratings) is PolicyEngine's "
    "convergence path to its long-run assumptions (earnings 3.3-3.7%), above the "
    "OBR's long-term determinants (fiscal-year earnings 2.8-3.4%); later-year "
    "costs of CPI-linking are correspondingly larger.",
    "The forecast-error Monte Carlo prices the final-year gross cost by linear "
    "scaling of PolicyEngine's spending with the uprating index; representative "
    "paths are re-run in full PolicyEngine to check it. Historical errors come from "
    "12 complete vintages, and each path joins two vintage blocks, so the draws "
    "resample only 144 distinct macro paths (uncertainty.error_source.n_distinct_paths): "
    "percentiles are summaries of that small set, not precise probabilities. The VAR "
    "cross-check gives a materially different range (uncertainty.var_cross_check).",
    "The uncertainty results are gross only. The macro draws move the basic and new "
    "State Pension; every other benefit rate, earnings and incomes, and the "
    "CPI-linked additional State Pension stay on the central path. The net figures "
    "on the representative paths (uncertainty.representative_path_runs) are "
    "therefore pension-only conditional simulations, not a distribution of net cost.",
    "Net costs inherit PolicyEngine's means-tested eligibility cliffs: a small pension "
    "change can switch a single heavily weighted survey household onto Housing Benefit, "
    "moving a year's net figure by several hundred £m. cost_vs_triple_lock_bn[policy] "
    "reports the largest single household each year and net_excluding_largest_household.",
    "No rule cuts the cash State Pension: a negative CPI or earnings index gives 0% "
    "(uncertainty.zero_floor reports how often this binds).",
    "Costs are in nominal £ in each fiscal year, not deflated.",
]
