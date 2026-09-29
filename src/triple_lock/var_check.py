"""Cross-check on the forecast-error bootstrap: a bivariate VAR on UK history.

Method
------
1. Annual CPI inflation (ONS D7G7, calendar-year average of the 12-month
   rate) and average earnings growth on the OBR's definition, national
   accounts wages and salaries per employee, (DTWM - ROYK) / (MGRZ - MGRQ),
   the same measure the central forecast and the error data use.
2. A VAR(p) with intercept, p in {1, 2}, estimated by OLS equation by
   equation on the common sample and chosen by AIC
   (ln|Sigma| + 2k/T, k = number of estimated coefficients).
3. Paths are simulated from the fitted VAR with Gaussian shocks drawn from
   the residual covariance. The lagged cross-terms carry dynamics such as a
   CPI shock followed by faster earnings growth (2022 into 2023-24).
   Simulation starts from the observed history (1989-2025); the first growth year (2026,
   mostly already published) is fixed at the OBR central value, as in the
   main method, and later years evolve from it.
4. Each year's draws are mean-shifted so their mean equals the OBR central
   forecast ("calibrated to the OBR on average"), which keeps the VAR's
   variance and co-movement but not its own long-run means.

Implemented with numpy (no statsmodels dependency).
"""

import csv
import re
from pathlib import Path

import numpy as np

from .config import REPO

RAW = REPO / "data" / "raw"
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
LAG_CANDIDATES = (1, 2)
VAR_SEED = 20260930


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

    data = np.array(
        [[s["D7G7"][y] / 100, earnings_level(y) / earnings_level(y - 1) - 1] for y in years]
    )
    return years, data


def fit_var(data, p, skip=0):
    """OLS VAR(p) with intercept. Returns (intercept (2,), lags (p, 2, 2), Sigma, T).

    ``skip`` drops leading observations so different lag orders share a sample.
    """
    y = data[max(p, skip):]
    x = np.hstack(
        [np.ones((len(y), 1))]
        + [data[max(p, skip) - lag: len(data) - lag] for lag in range(1, p + 1)]
    )
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    sigma = resid.T @ resid / len(y)
    lags = np.stack([beta[1 + 2 * i: 3 + 2 * i].T for i in range(p)])
    return beta[0], lags, sigma, len(y)


def aic(sigma, t, p, n=2):
    return float(np.log(np.linalg.det(sigma)) + 2 * n * (1 + n * p) / t)


def select_lag(data, candidates=LAG_CANDIDATES):
    skip = max(candidates)
    scores = {p: aic(*fit_var(data, p, skip)[2:], p) for p in candidates}
    return min(scores, key=scores.get), scores


def companion_max_eigenvalue(lags):
    p = lags.shape[0]
    top = np.hstack(list(lags))
    bottom = np.hstack([np.eye(2 * (p - 1)), np.zeros((2 * (p - 1), 2))]) if p > 1 else np.zeros((0, 2))
    return float(max(abs(np.linalg.eigvals(np.vstack([top, bottom])))))


def simulate(intercept, lags, sigma, last_obs, n_years, fixed_first, n_draws, seed=VAR_SEED):
    """(n_draws, n_years, 2) simulated growth. ``last_obs`` is (p, 2), oldest first.

    The first simulated year is set to ``fixed_first`` ([cpi, earnings]).
    """
    rng = np.random.default_rng(seed)
    p = lags.shape[0]
    chol = np.linalg.cholesky(sigma)
    hist = np.repeat(np.asarray(last_obs, float)[None], n_draws, axis=0)
    out = np.empty((n_draws, n_years, 2))
    for t in range(n_years):
        mean = intercept + sum(hist[:, -1 - i] @ lags[i].T for i in range(p))
        value = mean + rng.standard_normal((n_draws, 2)) @ chol.T
        if t == 0:
            value = np.broadcast_to(np.asarray(fixed_first, float), value.shape).copy()
        out[:, t] = value
        hist = np.concatenate([hist[:, 1:], value[:, None]], axis=1)
    return out


def var_draws(central_cpi, central_earnings, growth_years, data, years, n_draws, seed=VAR_SEED):
    """Mean-calibrated VAR draws: (cpi, earnings) arrays and a description dict.

    ``data`` is (T, 2) history of [cpi, earnings] for ``years``, ending the
    year before ``growth_years[0]``.
    """
    if len(years) != len(data):
        raise ValueError("years and data differ in length")
    if years[-1] != growth_years[0] - 1:
        raise ValueError(f"history ends {years[-1]}, simulation starts {growth_years[0]}")
    p, scores = select_lag(data)
    intercept, lags, sigma, t = fit_var(data, p)
    first = growth_years[0]
    sims = simulate(
        intercept, lags, sigma, data[-p:], len(growth_years),
        fixed_first=(central_cpi[first], central_earnings[first]),
        n_draws=n_draws, seed=seed,
    )
    central = np.array([[central_cpi[g], central_earnings[g]] for g in growth_years])
    sims = sims - sims.mean(axis=0, keepdims=True) + central[None]
    sd = np.sqrt(np.diag(sigma))
    info = {
        "lag_order": int(p),
        "aic": {str(k): round(v, 4) for k, v in scores.items()},
        "sample_years": [int(years[0]), int(years[-1])],
        "n_obs": int(t),
        "residual_sd": {"cpi": round(float(sd[0]), 5), "earnings": round(float(sd[1]), 5)},
        "residual_correlation": round(float(sigma[0, 1] / (sd[0] * sd[1])), 3),
        "coefficients": {
            "intercept": [round(float(v), 5) for v in intercept],
            "lags": [[[round(float(v), 4) for v in row] for row in lag] for lag in lags],
            "order": "rows: [cpi, earnings] equations; columns: [cpi, earnings] lagged",
        },
        "max_companion_eigenvalue": round(companion_max_eigenvalue(lags), 4),
    }
    return sims[:, :, 0], sims[:, :, 1], info

