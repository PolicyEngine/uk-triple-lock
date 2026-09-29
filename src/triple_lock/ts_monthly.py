"""Monthly bivariate model of the CPI index and average weekly earnings.

The triple lock is set by two statutory inputs measured over different windows:
the September CPI 12-month rate and May-July AWE total pay growth. Their gap
reverses sign far more often than calendar-year CPI and earnings growth do
(2011-2026: year-to-year correlation -0.30, against +0.42 for the calendar
measures), and the ratchet is paid on those reversals. Annual models of the
calendar measures cannot see this. This module models the months themselves
and builds every annual measure from the same simulated months:

* September CPI 12-month rate and May-July AWE 3-month-average growth (the
  statutory inputs), and
* calendar-year CPI and AWE growth (what the OBR forecasts and PolicyEngine's
  economic assumptions use).

Model: a VAR(p) on monthly log changes of the CPI index (ONS D7BT, not
seasonally adjusted) and the AWE total pay level (ONS KAB9, seasonally
adjusted), with an intercept and 11 month dummies, fitted by OLS on 2000-02
onwards; p is chosen by BIC. Shocks are Gaussian, resampled residual pairs, or
Student-t marginals with a t-copula, as in ts_methods. Simulation can start
with the CPI index already observed for a month the AWE has not reached (as in
September 2026: CPI to August, AWE to July); that month's AWE shock is drawn
from its distribution given the observed CPI shock.
"""

import csv
import re
from pathlib import Path

import numpy as np
from scipy import stats

from .config import REPO

RAW = REPO / "data" / "raw"
CPI_INDEX_CSV = RAW / "ons_d7bt_cpi_index.csv"
AWE_LEVEL_CSV = RAW / "ons_kab9_awe_total_pay.csv"
FIRST = (2000, 1)
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
LAG_CANDIDATES = (1, 2, 3, 6, 12, 13)
# Furlough-era months whose AWE changes are composition effects, not wage shocks
# (the April 2022 earnings leg was suspended for this reason). Excluded from the
# fit and the shock pool by default; ``exclude_covid=False`` keeps them.
COVID_MONTHS = set()
_y, _m = 2020, 3
while (_y, _m) <= (2021, 9):
    COVID_MONTHS.add((_y, _m))
    _m += 1
    if _m > 12:
        _y, _m = _y + 1, 1


def read_monthly(path):
    """{(year, month): value} from an ONS generator CSV."""
    out = {}
    with Path(path).open(newline="") as f:
        for row in csv.reader(f):
            m = re.fullmatch(r"(\d{4}) ([A-Z]{3})", row[0].strip()) if row else None
            if m and len(row) > 1 and row[1].strip():
                out[(int(m.group(1)), MONTHS.index(m.group(2)) + 1)] = float(row[1])
    return out


def month_range(start, end):
    y, m = start
    while (y, m) <= end:
        yield (y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def levels(end=None):
    """Aligned monthly levels: months, cpi (T,), awe (T,), plus CPI months beyond the last AWE month."""
    cpi, awe = read_monthly(CPI_INDEX_CSV), read_monthly(AWE_LEVEL_CSV)
    last_awe = max(awe) if end is None else min(max(awe), end)
    months = list(month_range(FIRST, last_awe))
    extra_cpi = [(k, cpi[k]) for k in sorted(cpi) if k > last_awe and (end is None or k <= end)]
    return months, np.array([cpi[k] for k in months]), np.array([awe[k] for k in months]), extra_cpi


def _design(x, months, p):
    """Regressors for rows p.. of x (T, 2): intercept, 11 month dummies, p lags."""
    T = len(x)
    rows = []
    for t in range(p, T):
        dummies = np.zeros(11)
        if months[t][1] > 1:
            dummies[months[t][1] - 2] = 1
        rows.append(np.concatenate([[1.0], dummies, *[x[t - l] for l in range(1, p + 1)]]))
    return np.array(rows)


def fit(months, cpi, awe, lags=LAG_CANDIDATES, exclude_covid=True):
    """OLS VAR on monthly log changes; lag order by BIC on a common sample.

    With ``exclude_covid`` the equations for furlough-era months (and months
    whose lags reach into them) are dropped from estimation and the shock pool.
    """
    x = np.column_stack([np.diff(np.log(cpi)), np.diff(np.log(awe))])
    mon = months[1:]
    pmax = max(lags)

    def keep(p, start):
        if not exclude_covid:
            return np.ones(len(x) - start, dtype=bool)
        return np.array([not any(mon[t - l] in COVID_MONTHS for l in range(0, p + 1)) for t in range(start, len(x))])

    best = None
    for p in lags:
        k = keep(p, pmax)
        X = _design(x, mon, p)[pmax - p:][k]
        Y = x[pmax:][k]
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        resid = Y - X @ beta
        sigma = resid.T @ resid / len(Y)
        bic = np.log(np.linalg.det(sigma)) + np.log(len(Y)) * beta.size / len(Y)
        if best is None or bic < best[0]:
            best = (bic, p)
    p = best[1]
    k = keep(p, p)
    X = _design(x, mon, p)[k]
    beta, *_ = np.linalg.lstsq(X, x[p:][k], rcond=None)
    resid = x[p:][k] - X @ beta
    return {"p": p, "beta": beta, "resid": resid - resid.mean(axis=0), "x": x, "months": mon,
            "exclude_covid": exclude_covid}


def _shocks(model, kind, n, steps, rng):
    resid = model["resid"]
    if kind == "gauss":
        sigma = resid.T @ resid / len(resid)
        return rng.multivariate_normal(np.zeros(2), sigma, size=(n, steps))
    if kind == "boot":
        return resid[rng.integers(0, len(resid), size=(n, steps))]
    if kind == "tcop":
        marg = [stats.t.fit(resid[:, j], floc=0.0) for j in range(2)]
        tau = stats.kendalltau(resid[:, 0], resid[:, 1]).statistic
        rho = float(np.clip(np.sin(np.pi * tau / 2), -0.99, 0.99))
        R = np.array([[1, rho], [rho, 1]])
        u = stats.rankdata(resid, axis=0) / (len(resid) + 1)

        def loglik(df):
            z = stats.t.ppf(u, df)
            return float(np.sum(stats.multivariate_t(loc=[0, 0], shape=R, df=df).logpdf(z)
                                - stats.t.logpdf(z, df).sum(axis=1)))

        df = max((3, 4, 5, 6, 8, 10, 15, 20, 30, 50), key=loglik)
        z = stats.multivariate_t(loc=[0, 0], shape=R, df=df).rvs(size=n * steps, random_state=rng).reshape(-1, 2)
        uu = stats.t.cdf(z, df)
        return np.column_stack([stats.t.ppf(uu[:, j], marg[j][0], 0.0, marg[j][2])
                                for j in range(2)]).reshape(n, steps, 2)
    raise ValueError(kind)


def simulate(model, months, cpi, awe, end, n, seed, kind="boot", extra_cpi=()):
    """Monthly level paths from the month after ``months[-1]`` to ``end``.

    ``extra_cpi``: [((year, month), level), ...] CPI observations for the first
    simulated months (AWE not yet published); the CPI change is fixed at the
    observation and the AWE shock is drawn given the implied CPI shock (Gaussian
    conditional on the residual covariance).
    Returns future months and arrays (n, S) of CPI and AWE levels.
    """
    rng = np.random.default_rng(seed)
    future = list(month_range(months[-1], end))[1:]
    S = len(future)
    p, beta = model["p"], model["beta"]
    shocks = _shocks(model, kind, n, S, rng)
    resid = model["resid"]
    sigma = resid.T @ resid / len(resid)
    hist = np.repeat(model["x"][-p:][None], n, axis=0)  # (n, p, 2)
    lc = np.full(n, np.log(cpi[-1]))
    la = np.full(n, np.log(awe[-1]))
    fixed = dict(extra_cpi)
    out_c, out_a = np.empty((n, S)), np.empty((n, S))
    prev_cpi_level = cpi[-1]
    for t, mo in enumerate(future):
        dummies = np.zeros(11)
        if mo[1] > 1:
            dummies[mo[1] - 2] = 1
        X = np.concatenate([np.ones((n, 1)), np.repeat(dummies[None], n, 0), *[hist[:, -l] for l in range(1, p + 1)]], axis=1)
        mean = X @ beta
        step = mean + shocks[:, t]
        if mo in fixed:
            observed = np.log(fixed[mo]) - np.log(prev_cpi_level)
            e_c = observed - mean[:, 0]
            cond_sd = np.sqrt(sigma[1, 1] - sigma[0, 1] ** 2 / sigma[0, 0])
            step[:, 0] = observed
            step[:, 1] = mean[:, 1] + sigma[0, 1] / sigma[0, 0] * e_c + cond_sd * rng.standard_normal(n)
            prev_cpi_level = fixed[mo]
        lc, la = lc + step[:, 0], la + step[:, 1]
        out_c[:, t], out_a[:, t] = np.exp(lc), np.exp(la)
        hist = np.concatenate([hist[:, 1:], step[:, None]], axis=1)
    return future, out_c, out_a


def annual_measures(months, cpi, awe, years):
    """From monthly level arrays (n, T) over ``months``: dict of (n, len(years)) growth arrays.

    statutory_cpi: September 12-month rate; statutory_earnings: May-July average
    over the previous May-July; calendar_cpi / calendar_earnings: calendar-year
    average over the previous year's.
    """
    idx = {m: i for i, m in enumerate(months)}

    def avg(arr, ms):
        return np.mean([arr[:, idx[m]] for m in ms], axis=0)

    out = {k: [] for k in ("statutory_cpi", "statutory_earnings", "calendar_cpi", "calendar_earnings")}
    for y in years:
        out["statutory_cpi"].append(cpi[:, idx[(y, 9)]] / cpi[:, idx[(y - 1, 9)]] - 1)
        out["statutory_earnings"].append(avg(awe, [(y, 5), (y, 6), (y, 7)]) / avg(awe, [(y - 1, 5), (y - 1, 6), (y - 1, 7)]) - 1)
        cal, prev = [(y, m) for m in range(1, 13)], [(y - 1, m) for m in range(1, 13)]
        out["calendar_cpi"].append(avg(cpi, cal) / avg(cpi, prev) - 1)
        out["calendar_earnings"].append(avg(awe, cal) / avg(awe, prev) - 1)
    return {k: np.column_stack(v) for k, v in out.items()}


def paths(years, n, seed, kind="boot", end_obs=None, exclude_covid=True):
    """Simulated annual measures for ``years`` from data to ``end_obs`` (default: all published data).

    Historical months are pasted in front of the simulated ones, so measures
    that straddle the data (e.g. September 2026 CPI over September 2025) use
    observed values where they exist.
    """
    months, cpi, awe, extra = levels(end_obs)
    model = fit(months, cpi, awe, exclude_covid=exclude_covid)
    end = (max(years), 12)
    future, sc, sa = simulate(model, months, cpi, awe, end, n, seed, kind, extra)
    all_months = months + future
    C = np.concatenate([np.repeat(cpi[None], n, 0), sc], axis=1)
    A = np.concatenate([np.repeat(awe[None], n, 0), sa], axis=1)
    return annual_measures(all_months, C, A, years), {"lag_order": model["p"], "n_months": len(model["resid"]),
                                                      "shocks": kind, "exclude_covid": exclude_covid}
