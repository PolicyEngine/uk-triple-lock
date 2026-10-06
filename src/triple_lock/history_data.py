"""Historical data the backtests and calibration read: OBR forecast errors, statutory gaps, annual ONS series.

* ``load_forecast_errors`` / ``error_blocks``: OBR forecast errors for calendar
  CPI and average earnings by vintage and horizon (data/obr_forecast_errors.csv,
  from the OBR Historical official forecasts database, Spring 2026). The
  backtests use them for the OBR forecast-error bootstrap, a comparator.
* ``load_statutory_gaps`` / ``gap_blocks``: statutory input minus calendar-year
  measure by year (data/obr_outturn_crosscheck.csv).
* ``history``: annual calendar CPI (ONS D7G7, calendar-year average of the
  12-month rate) and average earnings growth on the OBR's definition, national
  accounts wages and salaries per employee, (DTWM - ROYK) / (MGRZ - MGRQ).
"""

import csv
import re
from pathlib import Path

import numpy as np

from .config import BLOCK_HORIZON, RAW

VARIABLES = ("cpi", "earnings")
REQUIRED_COLUMNS = {"year_forecast_made", "forecast_vintage", "horizon_years", "variable", "forecast", "outturn",
                    "error"}
ONS_GEN = "https://www.ons.gov.uk/generator?format=csv&uri="
SERIES = {
    "D7G7": (RAW / "ons_d7g7_cpi_annual_rate.csv", ONS_GEN + "/economy/inflationandpriceindices/timeseries/d7g7/mm23"),
    "DTWM": (RAW / "ons_dtwm_compensation_of_employees.csv", ONS_GEN + "/economy/grossdomesticproductgdp/timeseries/dtwm/ukea"),
    "ROYK": (RAW / "ons_royk_employers_social_contributions.csv", ONS_GEN + "/economy/grossdomesticproductgdp/timeseries/royk/ukea"),
    "MGRZ": (RAW / "ons_mgrz_employment_16plus.csv", ONS_GEN + "/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/mgrz/lms"),
    "MGRQ": (RAW / "ons_mgrq_self_employed_16plus.csv", ONS_GEN + "/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/mgrq/lms"),
}
FIRST_YEAR = 1989
LAST_YEAR = 2025


def load_forecast_errors(path):
    """Read observed calendar errors, retaining forecast-only rows for other readers.

    Rates must be finite decimals (0.021 = 2.1%). A valid forecast row with
    both outturn and error blank has no calendar observation yet and is ignored
    here; C2 can still use its mean once the statutory outturn is complete.
    A partially filled observation, malformed forecast or unknown variable
    raises. Duplicate observed rows within a vintage are averaged unchanged.
    """
    path = Path(path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path} has no rows")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    grouped = {}
    for n, row in enumerate(rows, start=2):
        if any(row[key] is None for key in REQUIRED_COLUMNS):
            raise ValueError(f"{path} line {n}: incomplete CSV row")
        variable = row["variable"].strip().lower()
        if variable not in VARIABLES:
            raise ValueError(f"{path} line {n}: unknown variable {row['variable']!r}")
        forecast = float(row["forecast"])
        if not np.isfinite(forecast) or abs(forecast) > 1:
            raise ValueError(f"{path} line {n}: forecast {row['forecast']} is not a finite decimal rate")
        vintage = (int(row["year_forecast_made"]), row["forecast_vintage"].strip())
        horizon = int(row["horizon_years"])
        if not vintage[1] or horizon < 1:
            raise ValueError(f"{path} line {n}: forecast vintage and positive horizon required")
        outturn, error = row["outturn"].strip(), row["error"].strip()
        if bool(outturn) != bool(error):
            raise ValueError(f"{path} line {n}: outturn and error must both be present or both blank")
        if not outturn:
            continue
        observed, residual = float(outturn), float(error)
        if not np.isfinite(observed) or abs(observed) > 1 or not np.isfinite(residual):
            raise ValueError(f"{path} line {n}: outturn and error must be finite decimal rates")
        key = (variable, horizon)
        grouped.setdefault(vintage, {}).setdefault(key, []).append(residual)
    return {vintage: {key: float(np.mean(values)) for key, values in errors.items()}
            for vintage, errors in grouped.items()}


def error_blocks(errors_by_vintage, block_horizon=BLOCK_HORIZON, exclude_target_years=()):
    """Complete vintages as an array (n_vintages, H, 2) of [cpi, earnings] errors, and their keys.

    Vintages without every horizon 1..H for both variables are left out (the
    most recent EFOs, whose later horizons have no outturn yet).
    ``exclude_target_years`` drops whole vintages whose horizons 1..H target
    any of those years.
    """
    if block_horizon < 2:
        raise ValueError("block horizon must be at least 2")
    horizons = range(1, block_horizon + 1)
    excluded = set(exclude_target_years)
    kept = sorted(
        v for v, errors in errors_by_vintage.items()
        if all((var, h) in errors for var in VARIABLES for h in horizons) and not excluded & {v[0] + h for h in horizons}
    )
    if len(kept) < 2:
        raise ValueError("fewer than two complete vintages")
    blocks = np.array([[[errors_by_vintage[v][(var, h)] for var in VARIABLES] for h in horizons] for v in kept])
    return blocks, kept


def load_statutory_gaps(path):
    """{year: (cpi_gap, earnings_gap)}: statutory input minus calendar-year measure.

    CPI: September 12-month rate minus the OBR calendar-year outturn.
    Earnings: May-July AWE total pay growth (KAC3) minus the OBR earnings
    outturn, or the OBR-definition rebuild from latest ONS data where the
    database has no outturn yet. Years missing either gap are left out.
    """
    path = Path(path)
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    gaps = {}
    for row in rows:
        obr_earnings = row["earnings_obr_outturn"] or row["earnings_obr_def_rebuilt_latest_ons"]
        needed = [row["cpi_ons_d7g7_september"], row["cpi_obr_outturn"], row["awe_kac3_may_jul"], obr_earnings]
        if not all(needed):
            continue
        gaps[int(row["year"])] = (float(row["cpi_ons_d7g7_september"]) - float(row["cpi_obr_outturn"]),
                                  float(row["awe_kac3_may_jul"]) - float(obr_earnings))
    if not gaps:
        raise ValueError(f"{path} has no complete statutory-gap years")
    return gaps


def gap_blocks(kept, gaps, block_horizon=BLOCK_HORIZON):
    """Statutory gaps aligned with :func:`error_blocks`, (n_vintages, H, 2), de-meaned by horizon.

    Cell (v, h) holds the gaps for vintage v's horizon-h target year, so a draw
    that picks a vintage's forecast errors also picks the gaps of the same
    years. Raises if a target year has no gap.
    """
    missing = sorted({v[0] + h for v in kept for h in range(1, block_horizon + 1)} - set(gaps))
    if missing:
        raise KeyError(f"no statutory gap for target years {missing}")
    out = np.array([[gaps[v[0] + h] for h in range(1, block_horizon + 1)] for v in kept], dtype=float)
    return out - out.mean(axis=0, keepdims=True)


def read_ons_annual(path):
    """{year: value} from an ONS generator CSV (annual rows only)."""
    out = {}
    with Path(path).open(newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and re.fullmatch(r"\d{4}", row[0].strip()):
                out[int(row[0])] = float(row[1])
    return out


def history(first_year=FIRST_YEAR, last_year=LAST_YEAR):
    """(years, array (T, 2) of [cpi, earnings] growth as decimals), first..last year.

    Every series must cover every year needed; a gap raises KeyError.
    """
    s = {k: read_ons_annual(path) for k, (path, _) in SERIES.items()}
    years = list(range(first_year, last_year + 1))

    def earnings_level(y):
        return (s["DTWM"][y] - s["ROYK"][y]) / (s["MGRZ"][y] - s["MGRQ"][y])

    data = np.array([[s["D7G7"][y] / 100, earnings_level(y) / earnings_level(y - 1) - 1] for y in years])
    return years, data
