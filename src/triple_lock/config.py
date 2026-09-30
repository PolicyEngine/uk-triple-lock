"""Fixed choices for the triple lock analysis.

Everything a reader might want to check or change lives here: the two rules,
the horizon, the parameter paths the reform touches, the input files and the
method limitations the results file reports.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Fiscal years named by start year ("2027" = 2027-28). 2026-27 rates are set.
# Upratings from April 2027 to April 2039, so the final year is 2039-40, the
# year DWP's State Pension uprating analysis (29 September 2026) costs.
BASE_YEAR = 2026
HORIZON = list(range(2027, 2040))
FINAL_YEAR = HORIZON[-1]
# Household tables: five upratings after the switch, and the final year.
DISTRIBUTION_YEARS = [2034, FINAL_YEAR]
# Calendar-year growth each path sets in the model: 2027-2039. policyengine-uk
# uprates incomes and CPI-indexed thresholds in fiscal year y by calendar-year
# y growth, and benefit rates by calendar y-1 CPI, so 2039-40 needs 2039.
CALENDAR_YEARS = list(range(BASE_YEAR + 1, FINAL_YEAR + 1))
# Statutory inputs (September CPI, May-July AWE) that set the April 2027 to
# April 2039 rises: 2026-2038.
STATUTORY_YEARS = [y - 1 for y in HORIZON]

TRIPLE_LOCK_FLOOR = 0.025
# No rule cuts the cash State Pension: a negative index gives a 0% uprating.
# (SSAA 1992 s150A requires an increase of at least earnings growth but does
# not require a cut when the index falls; the triple lock floors at 2.5%.)
ZERO_FLOOR = 0.0
# create_triple_lock.py rounds each year's rate to 3 dp; every run applies the
# same rounding to both rules, so they are identical in years where they pick
# the same component.
CENTRAL_RATE_DECIMALS = 3

# The Prime Minister's conference speech (29 September 2026) keeps the triple
# lock for this Parliament and adjusts it from April 2030: "the state pension
# will continue to rise every year at least by prices or 2.5%. And it will
# hold its value relative to earnings over time". DWP's State Pension uprating
# analysis the same day defines it: from April 2030 the pension keeps its
# 2029-30 ratio to earnings, rising "at least inflation or 2.5% – and anything
# more that is needed to retain that value".
SWITCH_YEAR = 2030
POLICIES = {
    "triple_lock": {
        "label": "Triple lock (current policy)",
        "rule": "max(CPI, earnings, 2.5%)",
    },
    "burnham_2030": {
        "label": "Burnham plan",
        "rule": "from April 2030, at least max(CPI, 2.5%); never below an earnings link from 2029-30",
    },
}
BASELINE_POLICY = "triple_lock"
REFORM_POLICY = "burnham_2030"

# Only the flat-rate State Pension is triple-locked. These are the parameters
# the reform overwrites, year by year.
FLAT_RATE_PARAMETERS = {
    "new_state_pension": "gov.dwp.state_pension.new_state_pension.amount",
    "basic_state_pension": "gov.dwp.state_pension.basic_state_pension.amount",
}
# Growth series the model's own triple lock is built from
# (policyengine_uk/parameters/gov/dwp/state_pension/triple_lock/create_triple_lock.py).
OBR_GROWTH = "gov.economic_assumptions.yoy_growth.obr"
CPI_PARAMETER = f"{OBR_GROWTH}.consumer_price_index"
EARNINGS_PARAMETER = f"{OBR_GROWTH}.average_earnings"
MODEL_TRIPLE_LOCK_PARAMETER = "gov.economic_assumptions.yoy_growth.triple_lock"
# In law the additional State Pension is CPI-linked and neither rule changes
# it; policyengine-uk uprates it with the flat-rate ratio, so every reform run
# pins it to the unreformed run on the same path.
PINNED_VARIABLES = ["additional_state_pension"]

# Household-level variables used for the fiscal decomposition. Each is summed
# with household weights; the net figure is the change in gov_balance.
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
# Recorded in every run's totals, outside the net decomposition.
SPENDING_DETAIL = ["basic_state_pension", "new_state_pension"]

# Inputs.
DATA = REPO / "data"
RAW = DATA / "raw"
CENTRAL_FORECAST_CSV = DATA / "obr_central_forecast.csv"
ERROR_CSV = DATA / "obr_forecast_errors.csv"
# Paired gaps between the statutory inputs and the calendar-year measures
# (September CPI minus calendar CPI; May-July AWE minus OBR earnings) by year.
CROSSCHECK_CSV = DATA / "obr_outturn_crosscheck.csv"
# Realised statutory inputs by year.
ACTUALS_CSV = DATA / "triple_lock_actual_inputs.csv"
BENCHMARKS_CSV = DATA / "benchmarks.csv"
# Block length for the OBR forecast-error bootstrap (a backtest comparator):
# spring vintages cover horizons 1-4.
BLOCK_HORIZON = 4

# The April 2027 uprating is set by September 2026 CPI (published 21 October
# 2026) and May-July 2026 AWE total pay growth (published 15 September 2026).
# The earnings leg uses the published figure; the CPI leg uses the latest
# published CPI 12-month rate (August 2026) until September CPI is out.
STATUTORY_YEAR = 2026
AWE_CSV = RAW / "ons_kac3_awe_total_pay_3m_yoy.csv"
AWE_PERIOD = "2026 JUL"
AWE_URL = (
    "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/"
    "earningsandworkinghours/timeseries/kac3/lms"
)
CPI_CSV = RAW / "ons_d7g7_cpi_annual_rate.csv"
CPI_PERIOD = "2026 AUG"
CPI_URL = "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23"
CPI_Q3_PERIOD = "2026Q3"
# August-to-September changes in the CPI 12-month rate from this year on
# bound how far September 2026 CPI can plausibly move from August.
CPI_AUG_SEP_FIRST_YEAR = 1997

# Datasets. The bundle's certified default is the primary; Microcosm is a
# sensitivity (uncertified until its benefits-inclusive rebuild).
PRIMARY_DATASET = None  # the policyengine bundle's certified default (enhanced_frs_2024_25)
SENSITIVITY_DATASET = "populace_uk_2023"

# Outputs.
OUTPUT = DATA / "results.json"
DASHBOARD_COPY = REPO / "dashboard" / "public" / "data" / "results.json"
# Model jobs are cached here, keyed by their inputs and the engine's source,
# so an interrupted build resumes (git-ignored).
JOB_CACHE = REPO / ".cache" / "jobs"
