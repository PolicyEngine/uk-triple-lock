"""The central path: the growth every model run starts from, and the inputs each April's rise uses.

Calendar-year growth (what the model's economic assumptions hold; it moves
earnings, benefit rates and thresholds in the model):

* 2027-2030: the OBR March 2026 EFO calendar-year CPI and average earnings
  (Tables 1.7 and 1.6), unrounded. policyengine-uk's own assumptions for these
  years are the same figures rounded to 0.1 point.
* 2031-2039: the OBR's long-term economic determinants (March 2026 EFO, dated
  28 May 2026), converted from fiscal to calendar years (calendar y = 1/4 of
  fiscal year y-1 to y plus 3/4 of fiscal year y to y+1). policyengine-uk's own
  long-run earnings path converges to 3.83%, the 2025 determinants' figure;
  the 2026 determinants have 3.75%, reached more slowly.
* 2026 is the model's own on every path (the OBR's March 2026 forecast, 2.3%
  CPI): it sets April 2027's benefit uprating in the model, where in law
  September 2026 CPI (published 21 October 2026) will.

Statutory inputs (what sets each April's State Pension rise: September CPI
and May-July AWE total pay growth the year before):

* 2026 (April 2027): published May-July 2026 AWE and August 2026 CPI, standing
  in for September CPI until it is published (``statutory_inputs``).
* 2027-2030: the EFO's September-quarter CPI and April-June earnings growth,
  the closest published proxies to the statutory timing.
* 2031-2038: the calendar-year path, as no quarterly forecast exists.
"""

import csv
import copy
import re

from .config import (
    AWE_CSV,
    AWE_PERIOD,
    AWE_URL,
    CALENDAR_YEARS,
    CENTRAL_FORECAST_CSV,
    CPI_AUG_SEP_FIRST_YEAR,
    CPI_CSV,
    CPI_PERIOD,
    CPI_Q3_PERIOD,
    ACTUALS_CSV,
    CPI_URL,
    SEPTEMBER_CPI_HISTORY_FROM,
    STATUTORY_YEAR,
    STATUTORY_YEARS,
    TRIPLE_LOCK_FLOOR,
)

EFO_YEARS = range(2027, 2031)  # calendar years the EFO forecasts
QUARTERLY_YEARS = range(2027, 2031)  # statutory years with EFO quarterly proxies
EFO_SOURCE = "OBR Economic and fiscal outlook, March 2026 (detailed forecast tables: economy, Tables 1.6 and 1.7)"
EFO_URL = "https://obr.uk/docs/d055fbf02d5b3g6jq8l2/efo-march-2026-detailed-forecast-tables-economy.xlsx"
LTED_SOURCE = "OBR Long-term economic determinants, March 2026 EFO (dated 28 May 2026)"
LTED_URL = "https://obr.uk/docs/dlm_uploads/Long-term-economic-determinants-March-2026-EFO.xlsx"
# The determinants file's note on its 'Triple lock' row (Growth rate assumptions sheet).
OBR_TRIPLE_LOCK_PREMIUM = 0.006
OBR_TRIPLE_LOCK_NOTE = "Average earnings growth plus 0.6 percentage points"


def long_run_earnings_variant(central, delta, first_year=2031):
    """Copy the calendar targets and move long-run earnings; shocks are unchanged.

    Statutory inputs are rebuilt from shifted monthly levels by the caller,
    rather than moved arithmetically by this function.
    """
    variant = copy.deepcopy(central)
    for y in variant['calendar']['earnings']:
        if y >= first_year:
            variant['calendar']['earnings'][y] += delta
    return variant


def obr_premium_comparator(central, april_years=range(2034, 2040)):
    """OBR triple-lock minus earnings, pp, with fiscal input year = April year - 1."""
    years = [y - 1 for y in april_years]
    return 100 * sum(central['obr_triple_lock_uprating'][y] - central['obr_earnings_fiscal'][y]
                     for y in years) / len(years)


def _rows(path=CENTRAL_FORECAST_CSV):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _series(rows, basis, variable, key=lambda p: int(p[:4])):
    return {key(r["period"]): float(r["value"]) for r in rows if r["basis"] == basis and r["variable"] == variable}


def fiscal_to_calendar(fiscal, year):
    """Calendar-year growth from fiscal-year growth (fiscal keys = start year): its Q1 falls in the earlier one."""
    return 0.25 * fiscal[year - 1] + 0.75 * fiscal[year]


def _ons_monthly(path):
    """{"YYYY MON": rate as a decimal} from an ONS time-series CSV download."""
    with path.open(newline="") as f:
        return {
            row[0]: float(row[1]) / 100
            for row in csv.reader(f)
            if len(row) >= 2 and re.fullmatch(r"\d{4} [A-Z]{3}", row[0])
        }


def statutory_inputs(awe_csv=AWE_CSV, cpi_csv=CPI_CSV, forecast_csv=CENTRAL_FORECAST_CSV):
    """Inputs for the April 2027 rise on the statutory timing.

    Earnings: published May-July 2026 AWE total pay growth (ONS KAC3, July 2026
    value). CPI: the latest published CPI 12-month rate (ONS D7G7, August 2026),
    standing in for September 2026 CPI until it is published. Also reports how
    far September CPI would have to move from August to change the triple lock
    rate, against the largest historical move.
    """
    earnings = _ons_monthly(awe_csv)[AWE_PERIOD]
    cpi_monthly = _ons_monthly(cpi_csv)
    cpi = cpi_monthly[CPI_PERIOD]
    q3 = [r for r in _rows(forecast_csv)
          if r["variable"] == "cpi" and r["basis"] == "q3_yoy" and r["period"] == CPI_Q3_PERIOD]
    if len(q3) != 1:
        raise KeyError(f"{forecast_csv} must have exactly one cpi q3_yoy {CPI_Q3_PERIOD} row")
    last = int(CPI_PERIOD[:4])
    moves = [cpi_monthly[f"{y} SEP"] - cpi_monthly[f"{y} AUG"] for y in range(CPI_AUG_SEP_FIRST_YEAR, last)]
    return {
        "growth_year": STATUTORY_YEAR,
        "earnings": earnings,
        "earnings_source": f"ONS AWE whole-economy total pay, 3-month average y/y (KAC3), {AWE_PERIOD}",
        "earnings_url": AWE_URL,
        "cpi": cpi,
        "cpi_source": f"ONS CPI 12-month rate (D7G7), {CPI_PERIOD}: latest published month, "
        "standing in for September 2026 CPI (published 21 October 2026)",
        "cpi_url": CPI_URL,
        "obr_q3_cpi_forecast": float(q3[0]["value"]),
        "cpi_rise_needed_to_set_triple_lock": round(max(earnings, TRIPLE_LOCK_FLOOR) - cpi, 4),
        "largest_aug_to_sep_cpi_rise": round(max(moves), 4),
        "aug_to_sep_years": [CPI_AUG_SEP_FIRST_YEAR, last - 1],
        "aug_to_sep_changes": [round(m, 4) for m in moves],
    }


def september_cpi_history(path=ACTUALS_CSV):
    """{determination year: published September CPI 12-month rate}, for the additional pension's uprating to 2026."""
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    out = {int(r["determination_year"]): float(r["cpi_september_12m"]) for r in rows
           if r["cpi_september_12m"] and int(r["determination_year"]) >= SEPTEMBER_CPI_HISTORY_FROM
           and int(r["determination_year"]) < STATUTORY_YEAR}
    missing = sorted(set(range(SEPTEMBER_CPI_HISTORY_FROM, STATUTORY_YEAR)) - set(out))
    if missing:
        raise KeyError(f"{path} lacks September CPI for {missing}")
    return out


def central_path(forecast_csv=CENTRAL_FORECAST_CSV):
    """The central path: calendar growth 2027-2039, statutory inputs 2026-2038, and where each value comes from."""
    rows = _rows(forecast_csv)
    efo = {v: _series(rows, "calendar_year", v, int) for v in ("cpi", "earnings")}
    lted = {v: _series(rows, "fiscal_year_lted", v) for v in ("cpi", "earnings", "triple_lock_uprating")}
    quarterly = {"cpi": _series(rows, "q3_yoy", "cpi"), "earnings": _series(rows, "q2_yoy", "earnings")}
    calendar, calendar_source = {"cpi": {}, "earnings": {}}, {}
    for y in CALENDAR_YEARS:
        if y in EFO_YEARS:
            for v in calendar:
                calendar[v][y] = efo[v][y]
            calendar_source[y] = "efo_calendar"
        else:
            for v in calendar:
                calendar[v][y] = fiscal_to_calendar(lted[v], y)
            calendar_source[y] = "lted_converted"
    april_2027 = statutory_inputs(forecast_csv=forecast_csv)
    statutory, statutory_source = {"cpi": {}, "earnings": {}}, {}
    for y in STATUTORY_YEARS:
        if y == STATUTORY_YEAR:
            statutory["cpi"][y], statutory["earnings"][y] = april_2027["cpi"], april_2027["earnings"]
            statutory_source[y] = "published"
        elif y in QUARTERLY_YEARS:
            statutory["cpi"][y], statutory["earnings"][y] = quarterly["cpi"][y], quarterly["earnings"][y]
            statutory_source[y] = "efo_quarterly"
        else:
            statutory["cpi"][y], statutory["earnings"][y] = calendar["cpi"][y], calendar["earnings"][y]
            statutory_source[y] = "calendar"
    conversion_check = max(abs(fiscal_to_calendar(lted[v], y) - efo[v][y]) for v in efo for y in EFO_YEARS)
    return {
        "calendar": calendar,
        "statutory": statutory,
        "calendar_source": calendar_source,
        "statutory_source": statutory_source,
        "april_2027_inputs": april_2027,
        # OBR's own long-term 'Triple lock' uprating, by the fiscal year of its inputs (paid the next April).
        "obr_triple_lock_uprating": {y: v for y, v in lted["triple_lock_uprating"].items() if y >= STATUTORY_YEAR},
        "obr_earnings_fiscal": {y: v for y, v in lted["earnings"].items() if y >= STATUTORY_YEAR},
        "conversion_check_max_abs_error": conversion_check,
        "sources": {
            "efo_calendar": {"title": EFO_SOURCE, "url": EFO_URL,
                             "what": "calendar-year CPI and average earnings growth"},
            "lted_converted": {"title": LTED_SOURCE, "url": LTED_URL,
                               "what": "fiscal-year CPI and average earnings growth, converted to calendar years "
                                       "(1/4 of the earlier fiscal year, 3/4 of the later); beyond 2030-31 a "
                                       "long-term projection, not a forecast"},
            "efo_quarterly": {"title": EFO_SOURCE, "url": EFO_URL,
                              "what": "September-quarter CPI and April-June earnings growth on a year earlier"},
            "published": {"title": "ONS", "url": AWE_URL, "what": "May-July 2026 AWE and August 2026 CPI"},
            "calendar": {"title": LTED_SOURCE, "url": LTED_URL, "what": "the calendar-year path"},
        },
    }
