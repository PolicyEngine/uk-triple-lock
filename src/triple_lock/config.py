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
EXTRA_DISTRIBUTION_YEAR = 2030

TRIPLE_LOCK_FLOOR = 0.025
# No rule cuts the cash State Pension: a negative index gives a 0% uprating.
# (SSAA 1992 s150A requires an increase of at least earnings growth but does
# not require a cut when the index falls; the triple lock floors at 2.5%.)
ZERO_FLOOR = 0.0
# create_triple_lock.py rounds each year's rate to 3 dp; the central run
# applies the same rounding to every rule so that a rule and the triple lock
# are identical in years where they pick the same component.
CENTRAL_RATE_DECIMALS = 3

# The Prime Minister's conference speech (29 September 2026) keeps the triple
# lock for this Parliament and adjusts it from April 2030: "the state pension
# will continue to rise every year at least by prices or 2.5%. And it will
# hold its value relative to earnings over time". Every alternative here
# follows the triple lock up to April 2029 and switches from April 2030.
SWITCH_YEAR = 2030
POLICIES = {
    "triple_lock": {
        "label": "Triple lock (current policy)",
        "rule": "max(CPI, earnings, 2.5%)",
    },
    "burnham_2030": {
        "label": "Burnham plan",
        "rule": "at least max(CPI, 2.5%); never below an earnings link from 2029-30",
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
REPRESENTATIVE_RANKING_POLICY = "burnham_2030"
# Paths re-run through full PolicyEngine (gross and net), at these percentiles
# of the Burnham plan's gross cost.
REPRESENTATIVE_QUANTILES = [10, 25, 50, 75, 90]

# Sensitivity: drop vintages whose blocks target the 2022-23 inflation shock years.
EX_2022_23_TARGET_YEARS = (2022, 2023)

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
# Realised statutory inputs by year, for the backtest.
ACTUALS_CSV = REPO / "data" / "triple_lock_actual_inputs.csv"
# Growth years where the central path is PolicyEngine's long-run convergence,
# not the OBR's March 2026 forecast (which ends in 2030).
LATE_HORIZON_YEARS = (2031, 2032, 2033)
# Block length for the vintage bootstrap: spring vintages cover horizons 1-4.
BLOCK_HORIZON = 4

OUTPUT = REPO / "data" / "triple_lock_results.json"
DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "triple_lock_results.json"

METHOD_LIMITATIONS = [
    # Forecast
    "The law sets each rise from September CPI and May-July earnings; after April 2027 the "
    "OBR's calendar-year CPI and national-accounts earnings forecasts stand in for them.",
    "Growth for 2031-2033 is PolicyEngine's long-run path, above the OBR's long-term figures; "
    "with the OBR's figures the CPI link's 2034-35 saving is smaller.",
    "The forecast uncertainty range covers gross State Pension spending only and rests on 12 "
    "past OBR forecasts (1,584 distinct paths); backtests show it is too narrow to read as "
    "probabilities.",
    # Data
    "The survey is not aged forward, so from 2033-34 every pensioner is on the new State "
    "Pension.",
    "A pension change of a few pounds can make one survey household eligible for Housing "
    "Benefit, moving a year's net figure by up to a few hundred million pounds.",
    # Model
    "Every rule follows the triple lock to April 2029 and its own formula from April 2030. The "
    "Burnham plan is our reading of the speech, which gave no formula.",
    "Only the basic and new State Pension change; other benefit rates follow PolicyEngine's "
    "own uprating, with no behavioural response.",
    "Costs are in cash terms (nominal £), not adjusted for inflation.",
]
