"""Time-series forecast distributions for annual UK CPI and earnings growth, and the tools shared with
the monthly model.

Three bivariate VAR variants share the same mean dynamics (OLS, lag order 1-2 by
AIC) and differ only in their shocks: Gaussian, resampled historical residual
pairs, or Student-t marginals (at least MIN_MARGINAL_DF degrees of freedom)
joined by a Student-t copula. Each returns draws of shape (n, steps, 2) = [cpi,
earnings] growth (decimals) for the ``steps`` years after the last row of
``data``. ``shift`` and ``tilt`` calibrate draws to a target mean path (the OBR
forecast); ``tilt`` is entropy tilting (Robertson, Tallman and Whiteman 2005),
which reweights draws instead of moving them. The scores are the proper scoring
rules the backtests use.

ts_backtest scores these annual methods and the monthly model (ts_monthly),
which draws the paths trajectories.py runs through PolicyEngine; ts_monthly uses
this module's t-marginal fit and ``tilt``.
"""

import numpy as np
from scipy import stats


# ── VAR mean dynamics (OLS, lag order by AIC over 1-2) ─────────────────────


def fit_var(data, p):
    y = data[p:]
    x = np.hstack([np.ones((len(y), 1))] + [data[p - l: len(data) - l] for l in range(1, p + 1)])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    intercept = beta[0]
    lags = np.stack([beta[1 + 2 * i: 3 + 2 * i].T for i in range(p)])
    return intercept, lags, resid


def select_lag(data, candidates=(1, 2)):
    skip = max(candidates)
    scores = {}
    for p in candidates:
        d = data[skip - p:]
        _, _, resid = fit_var(d, p)
        sigma = resid.T @ resid / len(resid)
        scores[p] = float(np.log(np.linalg.det(sigma)) + 2 * 2 * (1 + 2 * p) / len(resid))
    return min(scores, key=scores.get)


def simulate(intercept, lags, data, shocks):
    p = lags.shape[0]
    hist = np.repeat(data[-p:][None], shocks.shape[0], axis=0)
    out = np.empty_like(shocks)
    for t in range(shocks.shape[1]):
        mean = intercept + sum(hist[:, -1 - i] @ lags[i].T for i in range(p))
        out[:, t] = mean + shocks[:, t]
        hist = np.concatenate([hist[:, 1:], out[:, t][:, None]], axis=1)
    return out


def _setup(data):
    p = select_lag(data)
    c, a, resid = fit_var(data, p)
    return p, c, a, resid - resid.mean(axis=0)


def gauss_var(data, steps, n, seed):
    p, c, a, resid = _setup(data)
    sigma = resid.T @ resid / len(resid)
    shocks = np.random.default_rng(seed).multivariate_normal(np.zeros(2), sigma, size=(n, steps))
    return simulate(c, a, data, shocks), {"lag_order": p}


def boot_var(data, steps, n, seed):
    p, c, a, resid = _setup(data)
    idx = np.random.default_rng(seed).integers(0, len(resid), size=(n, steps))
    return simulate(c, a, data, resid[idx]), {"lag_order": p, "n_residuals": len(resid)}


COPULA_DF_GRID = (2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50)
# Lower bound on the degrees of freedom of a fitted Student-t marginal. Below 4
# a t has no finite fourth moment; the unbounded fit gave the monthly AWE shocks
# 2.7, whose tails produced implausible earnings and deflation years.
MIN_MARGINAL_DF = 4.0


def fit_t_marginal(x, min_df=MIN_MARGINAL_DF):
    """(df, 0, scale) of a zero-location Student-t fitted by maximum likelihood, df at least ``min_df``.

    When the unconstrained estimate is below the bound, df is fixed at the bound
    and the scale is refitted (the constrained maximum).
    """
    df, loc, scale = stats.t.fit(x, floc=0.0)
    if df < min_df:
        df, loc, scale = stats.t.fit(x, f0=min_df, floc=0.0)
    return float(df), float(loc), float(scale)


def tcop_var(data, steps, n, seed):
    """VAR mean dynamics; Student-t marginal shocks joined by a Student-t copula."""
    p, c, a, resid = _setup(data)
    marg = [fit_t_marginal(resid[:, j]) for j in range(2)]
    tau = stats.kendalltau(resid[:, 0], resid[:, 1]).statistic
    rho = float(np.clip(np.sin(np.pi * tau / 2), -0.99, 0.99))
    R = np.array([[1, rho], [rho, 1]])
    u = stats.rankdata(resid, axis=0) / (len(resid) + 1)

    def loglik(df):
        z = stats.t.ppf(u, df)
        return float(np.sum(stats.multivariate_t(loc=[0, 0], shape=R, df=df).logpdf(z) - stats.t.logpdf(z, df).sum(axis=1)))

    df = max(COPULA_DF_GRID, key=loglik)
    rng = np.random.default_rng(seed)
    z = stats.multivariate_t(loc=[0, 0], shape=R, df=df).rvs(size=n * steps, random_state=rng).reshape(-1, 2)
    uu = stats.t.cdf(z, df)
    shocks = np.column_stack([stats.t.ppf(uu[:, j], marg[j][0], 0.0, marg[j][2]) for j in range(2)])
    info = {"lag_order": p, "copula_df": int(df), "kendall_tau": round(float(tau), 3), "copula_rho": round(rho, 3),
            "marginal_df": [round(float(m[0]), 2) for m in marg]}
    return simulate(c, a, data, shocks.reshape(n, steps, 2)), info


METHODS = {"gauss_var": gauss_var, "boot_var": boot_var, "tcop_var": tcop_var}


# ── Calibration to a target mean path ────────────────────────────────────


def shift(paths, target):
    return paths - paths.mean(axis=0, keepdims=True) + target[None]


TILT_TOL = 1e-10


class TiltError(RuntimeError):
    """Entropy tilting did not reach the target means (e.g. a target outside the draws' range)."""


def tilt_moments(G, iters=200, tol=TILT_TOL, scale=None):
    """Entropy-tilting weights: minimal KL change from equal weights so every column of ``G`` has weighted mean 0.

    ``G`` (n, k) holds each draw's moment functions minus their targets. The
    weights are w_i proportional to exp(G_i . lambda), with lambda minimising the
    log of the sum of those terms (the dual problem, solved by Newton steps with
    a backtracking line search). ``scale`` (k,) expresses each column's
    tolerance in its own units (default 1). Raises TiltError when the largest
    scaled weighted-mean error is above ``tol`` after ``iters`` steps (a target
    outside the draws' range), instead of returning weights that miss it.
    """
    G = np.asarray(G, dtype=float)
    scale = np.ones(G.shape[1]) if scale is None else np.asarray(scale, dtype=float)
    g = G / scale[None]
    lam = np.zeros(g.shape[1])

    def objective(l):
        s = g @ l
        m = s.max()
        return m + np.log(np.exp(s - m).sum()), s

    for _ in range(iters):
        f0, s = objective(lam)
        w = np.exp(s - s.max())
        w /= w.sum()
        grad = w @ g
        if np.abs(grad).max() < 1e-12:
            break
        h = (g * w[:, None]).T @ g - np.outer(grad, grad)
        step = np.linalg.solve(h + 1e-12 * np.eye(len(lam)), grad)
        t = 1.0
        while t > 1e-8 and objective(lam - t * step)[0] > f0 - 1e-4 * t * grad @ step:
            t /= 2
        lam = lam - t * step
    _, s = objective(lam)
    w = np.exp(s - s.max())
    w /= w.sum()
    err = np.abs(w @ g)
    info = {"max_abs_mean_error": float(err.max()), "ess": float(1 / (w ** 2).sum())}
    if not info["max_abs_mean_error"] <= tol:
        raise TiltError(f"tilting missed a target by {info['max_abs_mean_error']:.3g} (in its scale units; "
                        f"effective sample {info['ess']:.1f})")
    return w, info


def tilt(paths, target, iters=200, tol=TILT_TOL):
    """Entropy-tilting weights so each (year, series) weighted mean of ``paths`` equals ``target``."""
    return tilt_moments((paths - target[None]).reshape(len(paths), -1), iters, tol)


def resample(paths, w, m, seed):
    """Equal-weight sample of m paths drawn in proportion to w."""
    idx = np.random.default_rng(seed).choice(len(paths), size=m, p=w)
    return paths[idx]


# ── Proper scores ───────────────────────────────────────────────────────


def crps(x, y, w=None):
    """Ensemble CRPS of draws x (n,) for outcome y, optionally weighted."""
    x = np.asarray(x, float)
    w = np.full(len(x), 1 / len(x)) if w is None else np.asarray(w, float) / np.sum(w)
    o = np.argsort(x)
    xs, ws = x[o], w[o]
    c = np.cumsum(ws)
    e_xx = 2 * np.sum(ws * xs * (2 * c - ws - 1))
    return float(np.sum(w * np.abs(x - y)) - 0.5 * e_xx)


def energy_score(X, y, seed=0):
    """Energy score of equal-weight draws X (n, d) for outcome y (d,)."""
    X = np.asarray(X, float)
    first = np.linalg.norm(X - y[None], axis=1).mean()
    perm = np.random.default_rng(seed).permutation(len(X))
    second = np.linalg.norm(X - X[perm], axis=1).mean()
    return float(first - 0.5 * second)


def interval_hit(x, y, lo=0.1, hi=0.9, w=None):
    """Whether y lies in the weighted [lo, hi] quantile interval of draws x.

    With few draws the interval is coarse: for fewer than 1 / lo draws it is the
    draws' [min, max] range, whatever ``lo`` and ``hi`` say.
    """
    x = np.asarray(x, float)
    w = np.full(len(x), 1 / len(x)) if w is None else np.asarray(w, float) / np.sum(w)
    o = np.argsort(x)
    c = np.cumsum(w[o])
    a, b = x[o][np.searchsorted(c, lo)], x[o][min(np.searchsorted(c, hi), len(x) - 1)]
    return bool(a <= y <= b)


def pit(x, y, w=None):
    w = np.full(len(x), 1 / len(x)) if w is None else np.asarray(w, float) / np.sum(w)
    return float(np.sum(w * (np.asarray(x) < y)) + 0.5 * np.sum(w * (np.asarray(x) == y)))


# ── Dependence-sensitive scores ─────────────────────────────────────────


def variogram_score(X, y, p=0.5, pairs=None):
    """Variogram score of order p (Scheuerer and Hamill 2015) for draws X (n, d), outcome y (d,).

    Sums over pairs (i, j) of (|y_i - y_j|^p - E|X_i - X_j|^p)^2, so it scores
    the forecast's dependence between components, which the energy score barely
    rewards. ``pairs`` restricts the sum (e.g. same series across years).
    """
    X = np.asarray(X, float)
    d = X.shape[1]
    if pairs is None:
        pairs = [(i, j) for i in range(d) for j in range(i + 1, d)]
    total = 0.0
    for i, j in pairs:
        total += (abs(y[i] - y[j]) ** p - np.mean(np.abs(X[:, i] - X[:, j]) ** p)) ** 2
    return float(total)


def band_depth_prerank(X, y):
    """Multivariate PIT of y among draws X (Thorarinsdottir et al. 2016, band-depth pre-rank).

    Pools the draws and the outcome, ranks each component, gives each vector the
    band depth mean_i (m + 1 - r_i)(r_i - 1), and returns the outcome's depth rank
    as a fraction in (0, 1]: near 0 = the outcome is less central than almost every
    draw (the forecast is too narrow or off-centre as a whole path).

    Undefined for a single draw (every pooled vector then has depth 0), so it
    raises; a point forecast has no multivariate rank.
    """
    X = np.asarray(X, float)
    if len(X) < 2:
        raise ValueError("band-depth pre-rank needs at least two draws")
    Z = np.vstack([X, np.asarray(y, float)[None]])
    m1 = len(Z)
    ranks = np.argsort(np.argsort(Z, axis=0, kind="stable"), axis=0, kind="stable") + 1
    depth = ((m1 - ranks) * (ranks - 1)).mean(axis=1)
    obs = depth[-1]
    below, ties = np.sum(depth[:-1] < obs), np.sum(depth[:-1] == obs)
    return float((below + 0.5 * ties + 0.5) / m1)


def shuffle_years(paths, seed):
    """Permute each year's (cpi, earnings) pairs across draws: marginals and same-year co-movement kept,
    autoregression destroyed."""
    rng = np.random.default_rng(seed)
    out = paths.copy()
    for t in range(paths.shape[1]):
        out[:, t] = paths[rng.permutation(len(paths)), t]
    return out


def shuffle_series(paths, seed):
    """Permute earnings paths across draws: each series' own dynamics kept, co-movement destroyed."""
    out = paths.copy()
    out[:, :, 1] = paths[np.random.default_rng(seed).permutation(len(paths)), :, 1]
    return out
