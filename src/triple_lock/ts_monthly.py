"""Monthly bivariate model of the CPI index and average weekly earnings.

The triple lock is set by two statutory inputs measured over different windows:
the September CPI 12-month rate and May-July AWE total pay growth. The gap
between them and the gap between calendar-year CPI and earnings growth behave
differently from year to year, and the ratchet is paid when the lead passes
between earnings and the higher of CPI and 2.5%. ``trajectories.gap_statistics``
records both gaps' lag-1 correlations and reversal counts over stated windows
(and with April 2022's earnings leg as published or as suspended in law) in the
results file. This module models the months themselves and builds every annual
measure from the same simulated months:

* September CPI 12-month rate and May-July AWE 3-month-average growth (the
  statutory inputs), and
* calendar-year CPI and AWE total pay growth. The OBR forecasts calendar CPI and
  national-accounts average earnings, and PolicyEngine's economic assumptions
  use those forecasts; calendar AWE growth stands in for the latter when the
  draws are tilted to them.

Model: a VAR(p) on monthly log changes of the CPI index (ONS D7BT, not
seasonally adjusted) and the AWE total pay level (ONS KAB9, seasonally
adjusted), with an intercept and 11 month dummies, fitted by OLS on 2000-02
onwards; p is chosen by BIC, every candidate scored on the same rows (the
criterion table is returned). Shocks are Gaussian, resampled residual pairs, or
Student-t marginals (at least ts_methods.MIN_MARGINAL_DF degrees of freedom)
joined by a t-copula. Simulation can start with the CPI index already observed
for a month the AWE has not reached (as in September 2026: CPI to August, AWE to
July); that month's AWE shock is drawn from its Gaussian conditional
distribution given the observed CPI shock, under every shock kind (for the
t-copula this is an approximation to its own conditional).
"""

import csv
import hashlib
import re
from pathlib import Path

import numpy as np
from scipy import stats

from .config import REPO
from .ts_methods import fit_t_marginal

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


def fit(months, cpi, awe, lags=LAG_CANDIDATES, exclude_covid=True, lag_order=None):
    """OLS VAR on monthly log changes; lag order by BIC on a common sample.

    Every candidate order is scored on the same equations: months from
    ``max(lags)`` on whose own month and every lag up to ``max(lags)`` avoid the
    furlough months (with ``exclude_covid``). The chosen order is then refitted
    on every equation it can use. With ``exclude_covid`` the equations for
    furlough-era months (and months whose lags reach into them) are dropped from
    estimation and the shock pool.
    """
    x = np.column_stack([np.diff(np.log(cpi)), np.diff(np.log(awe))])
    mon = months[1:]
    pmax = max(lags)

    def keep(p, start):
        if not exclude_covid:
            return np.ones(len(x) - start, dtype=bool)
        return np.array([not any(mon[t - l] in COVID_MONTHS for l in range(0, p + 1)) for t in range(start, len(x))])

    common = keep(pmax, pmax)
    Y = x[pmax:][common]
    criterion = []
    for p in lags:
        X = _design(x, mon, p)[pmax - p:][common]
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        resid = Y - X @ beta
        sigma = resid.T @ resid / len(Y)
        bic = float(np.log(np.linalg.det(sigma)) + np.log(len(Y)) * beta.size / len(Y))
        criterion.append({"p": p, "n": int(len(Y)), "bic": round(bic, 4)})
    p = min(criterion, key=lambda c: c["bic"])["p"] if lag_order is None else lag_order
    if p not in lags:
        raise ValueError("lag_order must be in the criterion grid")
    k = keep(p, p)
    X = _design(x, mon, p)[k]
    beta, *_ = np.linalg.lstsq(X, x[p:][k], rcond=None)
    resid = x[p:][k] - X @ beta
    return {"p": p, "beta": beta, "resid": resid - resid.mean(axis=0), "x": x, "months": mon,
            "exclude_covid": exclude_covid, "criterion": criterion}


def _shocks(model, kind, n, steps, rng):
    """Shocks (n, steps, 2) and a description of their distribution."""
    resid = model["resid"]
    if kind == "gauss":
        sigma = resid.T @ resid / len(resid)
        return rng.multivariate_normal(np.zeros(2), sigma, size=(n, steps)), {}
    if kind == "boot":
        return resid[rng.integers(0, len(resid), size=(n, steps))], {"n_residuals": int(len(resid))}
    if kind == "tcop":
        marg = [fit_t_marginal(resid[:, j]) for j in range(2)]
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
        shocks = np.column_stack([stats.t.ppf(uu[:, j], marg[j][0], 0.0, marg[j][2])
                                  for j in range(2)]).reshape(n, steps, 2)
        return shocks, {"marginal_df": [round(m[0], 2) for m in marg], "copula_df": int(df),
                        "kendall_tau": round(float(tau), 3), "copula_rho": round(rho, 3)}
    raise ValueError(kind)


def simulate(model, months, cpi, awe, end, n, seed, kind="boot", extra_cpi=()):
    """Monthly level paths from the month after ``months[-1]`` to ``end``.

    ``extra_cpi``: [((year, month), level), ...] CPI observations for the first
    simulated months (AWE not yet published); the CPI change is fixed at the
    observation and the AWE shock is drawn given the implied CPI shock (Gaussian
    conditional on the residual covariance).
    Returns future months, arrays (n, S) of CPI and AWE levels, and the shock description.
    """
    rng = np.random.default_rng(seed)
    future = list(month_range(months[-1], end))[1:]
    S = len(future)
    p, beta = model["p"], model["beta"]
    shocks, shock_info = _shocks(model, kind, n, S, rng)
    resid = model["resid"]
    sigma = resid.T @ resid / len(resid)
    hist = np.repeat(model["x"][-p:][None], n, axis=0)  # (n, p, 2)
    lc = np.full(n, np.log(cpi[-1]))
    la = np.full(n, np.log(awe[-1]))
    fixed = dict(extra_cpi)
    out_c, out_a = np.empty((n, S)), np.empty((n, S))
    prev_cpi_level = cpi[-1]
    innovations = hashlib.sha256()
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
        innovations.update(np.ascontiguousarray(step - mean).tobytes())
        lc, la = lc + step[:, 0], la + step[:, 1]
        out_c[:, t], out_a[:, t] = np.exp(lc), np.exp(la)
        hist = np.concatenate([hist[:, 1:], step[:, None]], axis=1)
    shock_info["innovation_sha256"] = innovations.hexdigest()
    return future, out_c, out_a, shock_info


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


SHIFT_TOL = 1e-12  # on the mean calendar growth
SHIFT_ITERATIONS = 20


def _calendar_growth(logs, idx, years):
    """Mean over draws of calendar-year growth of the average level, and the pieces its Jacobian needs."""
    g, parts = [], []
    for y in years:
        this = np.exp(logs[:, [idx[(y, m)] for m in range(1, 13)]])
        prev = np.exp(logs[:, [idx[(y - 1, m)] for m in range(1, 13)]])
        ratio = this.mean(axis=1) / prev.mean(axis=1)
        g.append(ratio.mean() - 1)
        parts.append((this, prev, ratio))
    return np.array(g), parts


def shift_to_calendar_means(months, cpi, awe, years, target, first_month):
    """Add the smoothest path of monthly drift, from ``first_month`` on, that makes the draws' mean
    calendar-year growth equal ``target`` in every year of ``years``.

    ``cpi``, ``awe``: level arrays (n, T) over ``months``; ``target``: (len(years), 2)
    calendar CPI and earnings growth. Every draw gets the same drift d_t added
    to its log change into month t (so a draw's level moves by the cumulated
    drift), which leaves each draw's shocks and the dependence of the monthly
    changes as the model made them: only the mean path moves. The drift path
    minimises the sum of squared month-to-month changes in d (starting from 0
    before ``first_month``) subject to the targets: Gauss-Newton steps on the
    exact mean growth, each solving the linearised equality-constrained least
    squares. A drift constant within each year would oscillate from year to
    year instead (a calendar average depends on the drift in two years), and the
    oscillation would put spurious reversals into the statutory measures.
    Returns the shifted levels and the drift path (monthly log points).
    """
    idx = {m: i for i, m in enumerate(months)}
    t0 = idx[first_month]
    last = idx[(max(years), 12)]
    k = last - t0 + 1  # drift unknowns: months first_month .. December of the last year
    # Smoothness: squared differences, including the step from 0 into the first month.
    D = np.eye(k) - np.eye(k, k=-1)
    H = D.T @ D
    out, drift = [], np.zeros((k, 2))
    for s_i, series in enumerate((cpi, awe)):
        base = np.log(series)
        d = np.zeros(k)
        for _ in range(SHIFT_ITERATIONS):
            logs = base.copy()
            logs[:, t0:last + 1] += np.cumsum(d)[None]
            logs[:, last + 1:] += d.sum()
            g, parts = _calendar_growth(logs, idx, years)
            resid = target[:, s_i] - g
            if np.abs(resid).max() <= SHIFT_TOL:
                break
            # Jacobian: d_t raises every month from t on, so d(growth_y)/d(d_t) = mean_i[ratio_i *
            # (share of year y's average from months >= t - share of year y-1's average from months >= t)].
            J = np.zeros((len(years), k))
            for j, (y, (this, prev, ratio)) in enumerate(zip(years, parts)):
                for which, arr, sign in ((y, this, 1.0), (y - 1, prev, -1.0)):
                    cols = [idx[(which, m)] for m in range(1, 13)]
                    tail = np.cumsum(arr[:, ::-1], axis=1)[:, ::-1] / arr.sum(axis=1, keepdims=True)  # share from month m on
                    for m, col in enumerate(cols):
                        if col < t0:
                            continue
                        # d at unknown u = col - t0 raises months col.. ; its share of this year's average is tail[:, m]
                        J[j, col - t0] += sign * float((ratio * tail[:, m]).mean())
                    # drifts before this year's first month raise the whole year equally (share 1)
                    first = cols[0]
                    if first > t0:
                        J[j, :first - t0] += sign * float(ratio.mean())
            # Minimise (d + x)' H (d + x) subject to J x = resid: KKT system.
            kkt = np.block([[2 * H, J.T], [J, np.zeros((len(years), len(years)))]])
            rhs = np.concatenate([-2 * H @ d, resid])
            x = np.linalg.solve(kkt, rhs)[:k]
            d = d + x
        else:
            raise ValueError(f"drift did not reach the targets: largest miss {np.abs(resid).max():.2e}")
        logs = base.copy()
        logs[:, t0:last + 1] += np.cumsum(d)[None]
        logs[:, last + 1:] += d.sum()
        out.append(np.exp(logs))
        drift[:, s_i] = d
    return out[0], out[1], [months[t0 + u] for u in range(k)], drift


def paths(years, n, seed, kind="boot", end_obs=None, exclude_covid=True, calendar_target=None, lag_order=None):
    """Simulated annual measures for ``years`` from data to ``end_obs`` (default: all published data).

    Historical months are pasted in front of the simulated ones, so measures
    that straddle the data (e.g. September 2026 CPI over September 2025) use
    observed values where they exist. ``calendar_target`` {year: (cpi, earnings)}
    adds the smoothest monthly drift path, from the first month in which neither
    series is observed (September 2026 with data to August 2026 CPI and July 2026
    AWE), that makes the draws' mean calendar growth equal it
    (``shift_to_calendar_means``); every annual measure, statutory ones
    included, is built from the shifted months.
    """
    months, cpi, awe, extra = levels(end_obs)
    model = fit(months, cpi, awe, exclude_covid=exclude_covid, lag_order=lag_order)
    end = (max(years), 12)
    future, sc, sa, shock_info = simulate(model, months, cpi, awe, end, n, seed, kind, extra)
    all_months = months + future
    C = np.concatenate([np.repeat(cpi[None], n, 0), sc], axis=1)
    A = np.concatenate([np.repeat(awe[None], n, 0), sa], axis=1)
    info = {"lag_order": model["p"], "lag_criterion": model["criterion"], "n_months": len(model["resid"]),
            "last_observed_month": list(months[-1]),
            "shocks": kind, "shock_distribution": shock_info, "exclude_covid": exclude_covid}
    if calendar_target is not None:
        shift_years = sorted(calendar_target)
        if shift_years[0] <= months[-1][0]:
            raise ValueError("calendar_target must start after the last observed year")
        target = np.array([calendar_target[y] for y in shift_years])
        first = future[len(extra)]  # the first month in which neither series is observed
        C, A, drift_months, drift = shift_to_calendar_means(all_months, C, A, shift_years, target, first)
        info["drift"] = {"first_month": list(drift_months[0]), "last_month": list(drift_months[-1]),
                         "annualised_pp_by_year": {
                             y: {s: round(float(1200 * drift[[i for i, mo in enumerate(drift_months) if mo[0] == y], j].mean()), 3)
                                 for j, s in enumerate(("cpi", "earnings"))}
                             for y in sorted({mo[0] for mo in drift_months})}}
    return annual_measures(all_months, C, A, years), info
