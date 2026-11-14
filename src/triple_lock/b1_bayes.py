"""B1: a Bayesian forecast of the State Pension uprating inputs (docs/METHOD.md, "Bayesian forecast of the uprating
inputs (B1)").

A Bayesian VAR(1) with Student-t shocks for the deviation of September CPI and May-July earnings growth from a forecast
path, fitted to the OBR's forecast-error record (target years 2011 on) and the statutory outturns before it (1989 to
2010), each year entering once. The specification was committed and pushed before this module existed (SPEC_COMMIT).
B1 was designed after the first model failed C2, the second failed C4 and V1's results were seen; its headline stands
on Max's ruling of 12 November 2026, not on a test.

Only ``fit`` needs NumPyro and JAX. Everything after the fit is numpy on the committed posterior draws:

    python -m triple_lock.b1_bayes --output data/b1

rewrites ``forecast.json`` and ``validation.json`` from ``data/b1/posterior.npy``. The fit, the pseudo-out-of-sample
scores and the sensitivity runs are ``scripts/b1_fit.py``, ``scripts/b1_backtest.py`` and ``scripts/b1_sensitivity.py``.
No PolicyEngine run or survey data enters anything here.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from . import v1_bands as V
from .config import ACTUALS_CSV, AWE_CSV, CPI_CSV, ERROR_CSV, HORIZON, REPO, STATUTORY_YEARS
from .ts_backtest import H, load_forecasts, statutory_outturns, switches

SPEC_COMMIT = "de576a54c8b83d075cd1905352fd55cfdc4b29df"
OUT = REPO / "data" / "b1"
POSTERIOR = OUT / "posterior.npy"
PARAMS = ("phi_cc", "phi_ce", "phi_ec", "phi_ee", "log_sigma_c", "log_sigma_e", "z_rho", "zeta", "log_kappa_c",
          "log_kappa_e", "nu_m2", "m_c", "m_e")
MCMC_SEED = 20261112
PREDICTIVE_SEED = 20261113
CHAINS, WARMUP, KEPT, TARGET_ACCEPT = 4, 1500, 2500, 0.95
REFIT_WARMUP, REFIT_KEPT = 1000, 1500  # the pseudo-out-of-sample refits
RERUN_WARMUP, RERUN_TARGET_ACCEPT = 3000, 0.99
GATE = {"rhat_max": 1.01, "ess_min": 1000, "divergences_max": 10}
RADIUS_MAX = 0.98
OUTTURN_FIRST, OUTTURN_LAST, RECORD_LAST = 1989, 2010, 2025
HOT_YEARS = (2021, 2022, 2023)
PAIRS = 20  # antithetic pairs per posterior draw: 10,000 draws x 40 paths = 400,000
N_BATCHES = 40
DELTA_FROM = 2031
QUANTILES = (5, 25, 50, 75, 95)
SE_QUANTILES = (5, 50, 95)
THRESHOLDS_BN = (0, 5, 10)
REPORT_YEARS = (2034, 2039)
N_PRIOR = 10_000
N_REPLICATIONS = 4000
N_CONDITIONAL, CONDITIONAL_PAIRS = 1000, 1000
LABEL = ("B1: posterior predictive forecast under the stated model and priors (docs/METHOD.md, B1). Designed after C2 "
         "and C4 failed and V1 was seen; not tested, validated or calibrated; headline on Max's ruling of 12 November "
         "2026")

# The priors of the specification, in percentage points. ``phi`` is in PARAMS order: cc, ce (CPI on lagged
# earnings), ec (earnings on lagged CPI), ee.
PRIORS = {
    "phi_mu": (0.5, 0.1, 0.2, 0.5), "phi_sd": (0.25, 0.2, 0.2, 0.25),
    "log_sigma_mu": float(np.log(1.5)), "log_sigma_sd": 0.5,
    "z_mu": 0.4, "z_sd": 0.5, "zeta_sd": 0.5, "log_kappa_sd": 0.5,
    "nu_shape": 2.0, "nu_rate": 0.1, "nu_fixed": 0.0,
    "m_mu": (2.0, 4.0), "m_sd": (0.5, 1.0),
    "delta_sd": (0.25, 0.5),  # CPI shift; real earnings shift
}


# ── Data ─────────────────────────────────────────────────────────────────────


def error_cells(error_csv=ERROR_CSV, actuals_csv=ACTUALS_CSV):
    """Every spring-origin cell (v, h), h = 1..4, with a statutory outturn: the forecast-error record, in points.

    Returns arrays over cells: ``origin``, ``h``, ``target``, ``a`` (n, 2) = statutory outturn less the OBR's
    calendar-year forecast, and ``lag`` (n, 2) = the same origin's error one year earlier (zero at h = 1).
    """
    forecasts, _ = load_forecasts(Path(error_csv))
    outturn = statutory_outturns(actuals_csv)
    rows = []
    for (v, label), f in sorted(forecasts.items()):
        if not label.startswith(("March ", "June 2010 ")):
            continue
        prev = np.zeros(2)
        for h in range(1, H + 1):
            if v + h not in outturn or any((k, h) not in f for k in V.VARIABLES):
                break
            a = 100 * (np.array(outturn[v + h]) - np.array([f[(k, h)] for k in V.VARIABLES]))
            rows.append((v, h, v + h, a, prev))
            prev = a
    return {"origin": np.array([r[0] for r in rows]), "h": np.array([r[1] for r in rows]),
            "target": np.array([r[2] for r in rows]), "a": np.array([r[3] for r in rows]),
            "lag": np.array([r[4] for r in rows])}


def cell_weights(cells, keep=None, full_weight=False):
    """1/n(T) for every kept cell, n(T) the number of kept cells with its target year; zero for dropped cells."""
    keep = np.ones(len(cells["target"]), dtype=bool) if keep is None else np.asarray(keep, dtype=bool)
    w = np.zeros(len(keep))
    for t in np.unique(cells["target"][keep]):
        sel = keep & (cells["target"] == t)
        w[sel] = 1.0 if full_weight else 1.0 / sel.sum()
    return w


def touches(cells, years):
    """Cells whose target year, or whose lagged year, is in ``years``."""
    years = set(years)
    t, h = cells["target"], cells["h"]
    return np.array([(tt in years) or (hh >= 2 and tt - 1 in years) for tt, hh in zip(t, h)])


def demeaned(cells):
    """The cells with each variable's mean error at each horizon removed, and the lags rebuilt (sensitivity S15)."""
    a = cells["a"].copy()
    for h in range(1, H + 1):
        a[cells["h"] == h] -= a[cells["h"] == h].mean(axis=0)
    by = {(int(v), int(h)): a[i] for i, (v, h) in enumerate(zip(cells["origin"], cells["h"]))}
    lag = np.array([by[(int(v), int(h) - 1)] if h > 1 else np.zeros(2) for v, h in zip(cells["origin"], cells["h"])])
    return {**cells, "a": a, "lag": lag}


def outturn_transitions(first=OUTTURN_FIRST, last=RECORD_LAST):
    """Statutory inputs in points for the transitions (t - 1, t), t = first + 1 .. last: ``year``, ``cur``, ``lag``."""
    series, source = V.statutory_history(first, last)
    years = np.arange(first + 1, last + 1)
    cur = 100 * np.array([series[y] for y in years])
    lag = 100 * np.array([series[y - 1] for y in years])
    return {"year": years, "cur": cur, "lag": lag, "source": source}


def likelihood_data(cells=None, transitions=None, *, keep=None, full_weight=False, outturn_first=OUTTURN_FIRST,
                    outturn_last=OUTTURN_LAST, use_errors=True, use_outturns=True):
    """The arrays the likelihood reads; a dropped cell or transition keeps its place with weight zero, so every fit
    has the same shapes."""
    cells = error_cells() if cells is None else cells
    transitions = outturn_transitions() if transitions is None else transitions
    w_f = cell_weights(cells, keep, full_weight) if use_errors else np.zeros(len(cells["target"]))
    y = transitions["year"]
    w_o = ((y - 1 >= outturn_first) & (y <= outturn_last)).astype(float) if use_outturns else np.zeros(len(y))
    return {"a": cells["a"], "a_lag": cells["lag"], "w_f": w_f, "s": transitions["cur"], "s_lag": transitions["lag"],
            "w_o": w_o}


# ── The fit (NumPyro) ────────────────────────────────────────────────────────


def _model(a, a_lag, w_f, s, s_lag, w_o, hp):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    phi = numpyro.sample("phi", dist.Normal(hp["phi_mu"], hp["phi_sd"]).to_event(1))
    log_sigma = numpyro.sample("log_sigma", dist.Normal(hp["log_sigma_mu"], hp["log_sigma_sd"]).expand([2]).to_event(1))
    z_rho = numpyro.sample("z_rho", dist.Normal(hp["z_mu"], hp["z_sd"]))
    zeta = numpyro.sample("zeta", dist.Normal(0.0, hp["zeta_sd"]))
    log_kappa = numpyro.sample("log_kappa", dist.Normal(0.0, hp["log_kappa_sd"]).expand([2]).to_event(1))
    nu_m2 = numpyro.sample("nu_m2", dist.Gamma(hp["nu_shape"], hp["nu_rate"]))
    m = numpyro.sample("m", dist.Normal(hp["m_mu"], hp["m_sd"]).to_event(1))

    # The spectral-radius bound is not coded here. As a wall of zero density it made NUTS flag every trajectory that
    # crossed it as divergent (docs/METHOD.md, B1 record of 12 November 2026); the sampler runs on the posterior
    # without the bound and ``retained`` discards the draws outside it, which targets the same truncated posterior.
    Phi = phi.reshape(2, 2)
    nu = jnp.where(hp["nu_fixed"] > 0, hp["nu_fixed"], 2.0 + nu_m2)

    def tril(log_sd, z):
        sd, rho = jnp.exp(log_sd), jnp.tanh(z)
        return jnp.array([[sd[0], 0.0], [rho * sd[1], sd[1] * jnp.sqrt(1 - rho * rho)]])

    r_f = a - a_lag @ Phi.T
    r_o = (s - m) - (s_lag - m) @ Phi.T
    numpyro.factor("errors", (w_f * dist.MultivariateStudentT(nu, jnp.zeros(2), tril(log_sigma, z_rho)).log_prob(r_f)).sum())
    numpyro.factor("outturns", (w_o * dist.MultivariateStudentT(nu, jnp.zeros(2), tril(log_sigma + log_kappa, z_rho + zeta)).log_prob(r_o)).sum())


_SAMPLERS = {}


def _sampler(warmup, kept, target_accept):
    import os

    os.environ.setdefault("XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1")
    import jax
    import numpyro
    from numpyro.infer import MCMC, NUTS, init_to_value

    jax.config.update("jax_enable_x64", True)
    key = (warmup, kept, target_accept)
    if key not in _SAMPLERS:
        import jax.numpy as jnp

        init = {"phi": jnp.array(PRIORS["phi_mu"]), "log_sigma": jnp.full(2, PRIORS["log_sigma_mu"]),
                "z_rho": jnp.array(PRIORS["z_mu"]), "zeta": jnp.array(0.0), "log_kappa": jnp.zeros(2),
                "nu_m2": jnp.array(20.0), "m": jnp.array(PRIORS["m_mu"])}
        kernel = NUTS(_model, target_accept_prob=target_accept, init_strategy=init_to_value(values=init))
        _SAMPLERS[key] = MCMC(kernel, num_warmup=warmup, num_samples=kept, num_chains=CHAINS,
                              chain_method="sequential", progress_bar=False)
    return _SAMPLERS[key]


def _hyper(priors):
    import jax.numpy as jnp

    return {k: jnp.asarray(v, dtype=jnp.float64) for k, v in priors.items() if k != "delta_sd"}


def sample(data, priors=None, *, warmup=WARMUP, kept=KEPT, target_accept=TARGET_ACCEPT, seed=MCMC_SEED):
    """One NUTS run on the posterior without the spectral-radius bound. Returns the chains as run, draws (chains,
    kept, len(PARAMS)), and the number of divergent transitions."""
    import jax
    import jax.numpy as jnp

    priors = {**PRIORS, **(priors or {})}
    mcmc = _sampler(warmup, kept, target_accept)
    mcmc.run(jax.random.PRNGKey(seed), **{k: jnp.asarray(v, dtype=jnp.float64) for k, v in data.items()},
             hp=_hyper(priors), extra_fields=("diverging",))
    s = {k: np.asarray(v) for k, v in mcmc.get_samples(group_by_chain=True).items()}
    draws = np.concatenate([s["phi"], s["log_sigma"], s["z_rho"][..., None], s["zeta"][..., None], s["log_kappa"],
                            s["nu_m2"][..., None], s["m"]], axis=-1)
    return draws, int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum())


def fit(data, priors=None, *, warmup=WARMUP, kept=KEPT, seed=MCMC_SEED, log=print):
    """The registered fit with its convergence gate: one rerun at the stricter settings if the gate is unmet.

    Returns the chains as run. The gate is evaluated on them, all draws and all divergences; ``retained`` then
    discards the draws outside the spectral-radius bound, and their number is recorded.
    """
    draws, div = sample(data, priors, warmup=warmup, kept=kept, seed=seed)
    diag = diagnostics(draws, div)
    settings = {"warmup": warmup, "kept": kept, "target_accept": TARGET_ACCEPT, "rerun": False}
    if not diag["gate_met"]:
        log(f"B1 gate unmet ({diag['worst']}); rerun at target acceptance {RERUN_TARGET_ACCEPT}")
        first = diag
        draws, div = sample(data, priors, warmup=RERUN_WARMUP, kept=kept, target_accept=RERUN_TARGET_ACCEPT, seed=seed)
        diag = diagnostics(draws, div)
        diag["first_attempt"] = first
        settings.update(warmup=RERUN_WARMUP, target_accept=RERUN_TARGET_ACCEPT, rerun=True)
    outside = int((spectral_radius(draws.reshape(-1, draws.shape[-1])) >= RADIUS_MAX).sum())
    return draws, {**diag, "draws_outside_radius_bound": outside, "draws_retained": diag["n_draws"] - outside,
                   "settings": {**settings, "chains": CHAINS, "seed": seed}}


def retained(draws):
    """The draws inside the spectral-radius bound, (D, 13), and each one's chain."""
    theta = draws.reshape(-1, draws.shape[-1])
    chain = np.repeat(np.arange(draws.shape[0]), draws.shape[1])
    keep = spectral_radius(theta) < RADIUS_MAX
    return theta[keep], chain[keep]


# ── Convergence diagnostics (Vehtari et al. 2021), numpy only ────────────────


def _split(x):
    n = x.shape[1] // 2
    return np.concatenate([x[:, :n], x[:, n:2 * n]])


def _rank_normal(x):
    from scipy.stats import norm, rankdata

    r = rankdata(x, method="average").reshape(x.shape)
    return norm.ppf((r - 0.375) / (x.size + 0.25))


def _rhat(x):
    n = x.shape[1]
    w = x.var(axis=1, ddof=1).mean()
    b = n * x.mean(axis=1).var(ddof=1)
    return float(np.sqrt(((n - 1) / n * w + b / n) / w)) if w > 0 else float("nan")


def _ess(x):
    m, n = x.shape
    c = x - x.mean(axis=1, keepdims=True)
    f = np.fft.rfft(c, 2 * n, axis=1)
    acov = np.fft.irfft(f * np.conj(f), 2 * n, axis=1)[:, :n] / n
    w = (acov[:, 0] * n / (n - 1)).mean()
    var_plus = w * (n - 1) / n + (x.mean(axis=1).var(ddof=1) if m > 1 else 0.0)
    if not var_plus > 0:
        return float("nan")
    rho = 1 - (w - acov.mean(axis=0)) / var_plus
    rho[0] = 1.0
    pairs = rho[: 2 * (n // 2)].reshape(-1, 2).sum(axis=1)  # Geyer's initial positive, monotone sequence
    stop = np.flatnonzero(pairs <= 0)
    pairs = pairs[: stop[0]] if len(stop) else pairs
    pairs = np.minimum.accumulate(pairs)
    tau = max(-1 + 2 * pairs.sum(), 1 / np.log10(m * n))
    return float(m * n / tau)


def diagnostics(draws, divergences):
    """Rank-normalised split R-hat, bulk and tail effective sample sizes per parameter, and the gate."""
    out = {}
    for j, name in enumerate(PARAMS):
        x = _split(draws[:, :, j])
        folded = np.abs(x - np.median(x))
        q05, q95 = np.quantile(x, [0.05, 0.95])
        out[name] = {"rhat": max(_rhat(_rank_normal(x)), _rhat(_rank_normal(folded))),
                     "ess_bulk": _ess(_rank_normal(x)),
                     "ess_tail": min(_ess((x <= q05).astype(float)), _ess((x <= q95).astype(float)))}
    worst = {"rhat": max(v["rhat"] for v in out.values()), "ess_bulk": min(v["ess_bulk"] for v in out.values()),
             "ess_tail": min(v["ess_tail"] for v in out.values()), "divergences": int(divergences)}
    met = (worst["rhat"] <= GATE["rhat_max"] and worst["ess_bulk"] >= GATE["ess_min"]
           and worst["ess_tail"] >= GATE["ess_min"] and divergences <= GATE["divergences_max"])
    return {"parameters": out, "worst": worst, "gate": GATE, "gate_met": bool(met), "n_draws": int(draws.shape[0] * draws.shape[1])}


# ── Parameters and paths (numpy) ─────────────────────────────────────────────


def unpack(theta, scale="F", nu_fixed=0.0):
    """Phi (D, 2, 2), the lower Cholesky factor of the shock scale (D, 2, 2) and nu (D,) from draws (D, 13).

    ``scale``: "F" the forecast-error scale (the forward process), "O" the outturn block's.
    """
    theta = np.atleast_2d(theta)
    p = {k: theta[:, j] for j, k in enumerate(PARAMS)}
    Phi = np.stack([np.stack([p["phi_cc"], p["phi_ce"]], axis=-1), np.stack([p["phi_ec"], p["phi_ee"]], axis=-1)], axis=1)
    k = scale == "O"
    sc = np.exp(p["log_sigma_c"] + k * p["log_kappa_c"])
    se = np.exp(p["log_sigma_e"] + k * p["log_kappa_e"])
    rho = np.tanh(p["z_rho"] + k * p["zeta"])
    L = np.zeros((len(theta), 2, 2))
    L[:, 0, 0], L[:, 1, 0], L[:, 1, 1] = sc, rho * se, se * np.sqrt(1 - rho**2)
    nu = np.full(len(theta), float(nu_fixed)) if nu_fixed > 0 else 2.0 + p["nu_m2"]
    return Phi, L, nu


def spectral_radius(theta):
    Phi, _, _ = unpack(theta)
    return np.abs(np.linalg.eigvals(Phi)).max(axis=1)


def derived(theta, nu_fixed=0.0):
    """The parameters a reader wants: persistence, scales, correlations, degrees of freedom."""
    theta = np.atleast_2d(theta)
    p = {k: theta[:, j] for j, k in enumerate(PARAMS)}
    return {**{k: p[k] for k in ("phi_cc", "phi_ce", "phi_ec", "phi_ee", "m_c", "m_e")},
            "sigma_c": np.exp(p["log_sigma_c"]), "sigma_e": np.exp(p["log_sigma_e"]), "rho_F": np.tanh(p["z_rho"]),
            "rho_O": np.tanh(p["z_rho"] + p["zeta"]), "kappa_c": np.exp(p["log_kappa_c"]),
            "kappa_e": np.exp(p["log_kappa_e"]),
            "nu": np.full(len(theta), float(nu_fixed)) if nu_fixed > 0 else 2.0 + p["nu_m2"], "spectral_radius": spectral_radius(theta)}


def shocks(theta, pairs, horizon, rng, *, scale="F", nu_fixed=0.0, cluster=False):
    """Student-t shocks u (D, pairs, horizon, 2) in points: normal draws times the root of a common yearly w."""
    Phi, L, nu = unpack(theta, scale, nu_fixed)
    d = len(Phi)
    z = rng.standard_normal((d, pairs, horizon, 2))
    w = nu[:, None, None] / rng.chisquare(np.broadcast_to(nu[:, None, None], (d, pairs, horizon)))
    if cluster:  # sensitivity S13: a year repeats the previous year's w with probability one half
        repeat = rng.random((d, pairs, horizon)) < 0.5
        for t in range(1, horizon):
            w[:, :, t] = np.where(repeat[:, :, t], w[:, :, t - 1], w[:, :, t])
    return np.sqrt(w)[..., None] * np.einsum("dij,dphj->dphi", L, z), Phi


def deviations(theta, pairs, horizon, rng, *, delta_sd=PRIORS["delta_sd"], delta_start=None, antithetic=True, **kw):
    """Deviations from the centre (paths, horizon, 2) as decimals, paths grouped by posterior draw.

    epsilon(0) = 0, epsilon(t) = Phi epsilon(t-1) + u(t); from index ``delta_start`` a constant level shift is added
    (CPI: delta_c; earnings: delta_c + delta_r). With ``antithetic`` every path has its mirror image (shocks and
    shifts negated, the same w), so each draw's mean deviation is exactly zero.
    """
    u, Phi = shocks(theta, pairs, horizon, rng, **kw)
    eps = np.empty_like(u)
    prev = np.zeros(u.shape[:2] + (2,))
    for t in range(horizon):
        prev = np.einsum("dij,dpj->dpi", Phi, prev) + u[:, :, t]
        eps[:, :, t] = prev
    if delta_start is not None:
        dc = rng.normal(0.0, 1.0, u.shape[:2]) * delta_sd[0]
        dr = rng.normal(0.0, 1.0, u.shape[:2]) * delta_sd[1]
        eps[:, :, delta_start:, 0] += dc[:, :, None]
        eps[:, :, delta_start:, 1] += (dc + dr)[:, :, None]
    if antithetic:
        eps = np.concatenate([eps, -eps], axis=1)
    return eps.reshape(-1, horizon, 2) / 100


def forward_inputs(theta, pairs=PAIRS, seed=PREDICTIVE_SEED, central=None, **kw):
    """Statutory inputs (paths, STATUTORY_YEARS, 2): the OBR centre, 2026 fixed, plus the deviations from 2027."""
    c = V.centre(central)
    kw.setdefault("delta_start", STATUTORY_YEARS.index(DELTA_FROM) - 1)
    dev = deviations(theta, pairs, len(STATUTORY_YEARS) - 1, np.random.default_rng(seed), **kw)
    return c[None] + np.concatenate([np.zeros((len(dev), 1, 2)), dev], axis=1)


def prior_draws(n=N_PRIOR, seed=PREDICTIVE_SEED + 1, priors=None):
    """Draws (n, 13) from the priors alone, the spectral-radius bound applied by rejection."""
    pr = {**PRIORS, **(priors or {})}
    rng = np.random.default_rng(seed)
    out = np.empty((0, len(PARAMS)))
    while len(out) < n:
        k = 2 * n
        t = np.column_stack([
            rng.normal(pr["phi_mu"], pr["phi_sd"], (k, 4)), rng.normal(pr["log_sigma_mu"], pr["log_sigma_sd"], (k, 2)),
            rng.normal(pr["z_mu"], pr["z_sd"], k), rng.normal(0, pr["zeta_sd"], k),
            rng.normal(0, pr["log_kappa_sd"], (k, 2)), rng.gamma(pr["nu_shape"], 1 / pr["nu_rate"], k),
            rng.normal(pr["m_mu"], pr["m_sd"], (k, 2))])
        out = np.concatenate([out, t[spectral_radius(t) < RADIUS_MAX]])
    return out[:n]


# ── Rule arithmetic, cash and summaries ──────────────────────────────────────


def cash_context(results=None, central=None):
    """What the identity needs from the stored central run: B(y), the central triple-lock index, rho and its error."""
    results = json.loads(V.RESULTS.read_text()) if results is None else results
    c = V.centre(central)
    ca = V.rule_arithmetic(c[None, :, 0], c[None, :, 1])
    rho, n_rho, max_gross = V.net_ratio(results)
    loo = json.loads(V.EMULATOR_CHECK.read_text())["net_over_gross_leave_one_path_out"]
    return {"base": V.base_bn(V.central_run(results)), "central_tl_index": ca["tl_index"], "central_G": ca["G"][0],
            "rho": rho, "rho_path_years": n_rho, "max_stored_gross_bn": max_gross,
            "rho_loo_mean_abs_error_pct": loo["mean_abs_error_pct"], "rho_loo_max_abs_error_pct": loo["max_abs_error_pct"]}


def arithmetic(inputs, ctx):
    """G, share, gross and net (paths, HORIZON) for statutory inputs (paths, STATUTORY_YEARS, 2)."""
    ra = V.rule_arithmetic(inputs[:, :, 0], inputs[:, :, 1])
    gross = V.gross_bn(ra["share"], ra["tl_index"], ctx["central_tl_index"], ctx["base"])
    return {"G": ra["G"], "share": ra["share"], "gross_bn": gross, "net_bn": ctx["rho"] * gross, "same": ra["same"]}


def _stats(x):
    return {"mean": float(np.mean(x)), **{f"p{q}": float(np.percentile(x, q)) for q in QUANTILES}}


def _probabilities(gross, net, G):
    return {"gross": {"above_0": float(np.mean(G > 0)), **{f"above_{t}": float(np.mean(gross > t)) for t in THRESHOLDS_BN[1:]}},
            "net": {"above_0": float(np.mean(G > 0)), **{f"above_{t}": float(np.mean(net > t)) for t in THRESHOLDS_BN[1:]}}}


def year_summary(out, j):
    """One fiscal year's distribution: G, share, gross, net and the probabilities above the thresholds."""
    return {**{k: _stats(out[k][:, j]) for k in ("G", "share", "gross_bn", "net_bn")},
            "probability": _probabilities(out["gross_bn"][:, j], out["net_bn"][:, j], out["G"][:, j])}


def headline_vector(out, j):
    """The figures whose precision is reported, for column j: gross percentiles and the probabilities."""
    g, n, G = out["gross_bn"][:, j], out["net_bn"][:, j], out["G"][:, j]
    v = {f"gross_p{q}": float(np.percentile(g, q)) for q in SE_QUANTILES}
    v.update({"p_above_0": float(np.mean(G > 0)), "p_gross_above_5": float(np.mean(g > 5)),
              "p_gross_above_10": float(np.mean(g > 10)), "p_net_above_5": float(np.mean(n > 5)),
              "p_net_above_10": float(np.mean(n > 10))})
    return v


def batch_se(out, paths_per_draw, n_draws, n_batches=N_BATCHES):
    """Batch-means Monte Carlo standard errors: batches of whole posterior draws, in order, with all their paths
    (equal batches when the draws divide evenly, otherwise sizes differing by at most one draw)."""
    edges = [int(e[0]) * paths_per_draw for e in np.array_split(np.arange(n_draws), n_batches)] + [n_draws * paths_per_draw]
    se = {}
    for y in HORIZON:
        j = HORIZON.index(y)
        rows = [headline_vector({k: v[edges[b]:edges[b + 1]] for k, v in out.items()}, j) for b in range(n_batches)]
        se[str(y)] = {k: float(np.std([r[k] for r in rows], ddof=1) / np.sqrt(n_batches)) for k in rows[0]}
    return se


def forecast_summary(theta, ctx, *, pairs=PAIRS, seed=PREDICTIVE_SEED, n_batches=N_BATCHES, chain=None, **kw):
    """The distribution by year for draws ``theta`` (D, 13), with Monte Carlo standard errors; ``chain`` (D,) gives
    each draw's chain for the per-chain figures."""
    inputs = forward_inputs(theta, pairs, seed, **kw)
    out = arithmetic(inputs, ctx)
    j39 = HORIZON.index(2039)
    res = {"n_paths": int(len(inputs)), "n_draws": int(len(theta)), "paths_per_draw": 2 * pairs,
           "by_year": {str(y): year_summary(out, j) for j, y in enumerate(HORIZON)},
           "pay_same_share": {str(y): float(out["same"][:, HORIZON.index(y)].mean()) for y in REPORT_YEARS},
           "gross_2039_max_bn": float(out["gross_bn"][:, j39].max()),
           "share_gross_above_max_stored": {str(y): float((out["gross_bn"][:, j] > ctx["max_stored_gross_bn"]).mean())
                                            for j, y in enumerate(HORIZON)},
           "input_deviation_sd_points": {str(y): dict(zip(V.VARIABLES, map(float, 100 * inputs[:, i].std(axis=0))))
                                         for i, y in enumerate(STATUTORY_YEARS) if i},
           "mean_input_deviation_max_abs_points": float(100 * np.abs(inputs.mean(axis=0) - V.centre()).max())}
    if n_batches:
        res["monte_carlo_se"] = batch_se(out, 2 * pairs, len(theta), n_batches)
    if chain is not None:
        of_path = np.repeat(chain, 2 * pairs)
        rows = [{str(y): headline_vector({k: v[of_path == c] for k, v in out.items()}, HORIZON.index(y))
                 for y in REPORT_YEARS} for c in np.unique(chain)]
        res["by_chain"] = rows
        res["range_across_chains"] = {y: {k: [min(r[y][k] for r in rows), max(r[y][k] for r in rows)]
                                          for k in rows[0][y]} for y in rows[0]}
    return res, inputs, out


def conditional_on_parameters(theta, ctx, n=N_CONDITIONAL, pairs=CONDITIONAL_PAIRS, seed=PREDICTIVE_SEED + 2):
    """For n draws evenly spaced through the retained draws (about every tenth), the median saving and P(> £10bn)
    given that draw's parameters: how much of the spread is uncertainty about the parameters."""
    sub = theta[(np.arange(n) * len(theta)) // n]
    rows = {y: [] for y in REPORT_YEARS}
    for start in range(0, n, 100):
        block = sub[start:start + 100]
        out = arithmetic(forward_inputs(block, pairs, seed + start), ctx)
        for y in REPORT_YEARS:
            g = out["gross_bn"][:, HORIZON.index(y)].reshape(len(block), 2 * pairs)
            rows[y].extend(zip(np.median(g, axis=1), (g > 10).mean(axis=1)))
    res = {"draws": n, "paths_per_draw": 2 * pairs}
    for y in REPORT_YEARS:
        med, p10 = map(np.array, zip(*rows[y]))
        res[str(y)] = {name: {"mean": float(x.mean()), "sd": float(x.std(ddof=1)), "p5": float(np.percentile(x, 5)),
                              "p95": float(np.percentile(x, 95))}
                       for name, x in (("gross_median_bn", med), ("p_gross_above_10", p10))}
    return res


# ── Validation: prior and posterior predictive checks ────────────────────────


def record_statistics(inputs, errors):
    """Statistics of one (replicated or realised) record of the complete origins: inputs and errors (n, 4, 2)."""
    out = {"floor_share": float((inputs[:, :, 1] < 0.025).mean()), "switches_per_path": float(switches(inputs).mean()),
           "max_abs_error_points": float(np.abs(errors).max())}
    for h in range(H):
        for k, name in enumerate(V.VARIABLES):
            out[f"sd_{name}_h{h + 1}"] = float(errors[:, h, k].std(ddof=1))
        out[f"corr_h{h + 1}"] = float(np.corrcoef(errors[:, h, 0], errors[:, h, 1])[0, 1])
    return out


def complete_record():
    """The thirteen complete origins: years, forecasts (n, 4, 2) as decimals and errors (n, 4, 2) in points."""
    from .ts_obr_errors import load_record

    rec = load_record()
    return rec["years"], rec["forecast"], 100 * rec["statutory"]


def replicated_records(theta, n=N_REPLICATIONS, seed=PREDICTIVE_SEED + 3):
    """Posterior predictive replications of the complete origins' record, origins sharing target-year shocks."""
    years, forecast, errors = complete_record()
    sub = theta[(np.arange(n) * len(theta)) // n]
    first, last = int(years.min()) + 1, int(years.max()) + H
    u, Phi = shocks(sub, 1, last - first + 1, np.random.default_rng(seed))
    u = u[:, 0]
    reps = []
    e = np.zeros((n, len(years), H, 2))
    for i, v in enumerate(years):
        prev = np.zeros((n, 2))
        for h in range(H):
            prev = np.einsum("dij,dj->di", Phi, prev) + u[:, v + h + 1 - first]
            e[:, i, h] = prev
    for d in range(n):
        reps.append(record_statistics(forecast + e[d] / 100, e[d]))
    realised = record_statistics(forecast + errors / 100, errors)
    out = {}
    for k, obs in realised.items():
        x = np.array([r[k] for r in reps])
        p_hi = float(np.mean(x >= obs))
        out[k] = {"realised": obs, "replicated_mean": float(x.mean()), "replicated_p1": float(np.percentile(x, 1)),
                  "replicated_p5": float(np.percentile(x, 5)), "replicated_p50": float(np.percentile(x, 50)),
                  "replicated_p95": float(np.percentile(x, 95)), "replicated_p99": float(np.percentile(x, 99)),
                  "share_at_or_above_realised": p_hi, "share_at_or_below_realised": float(np.mean(x <= obs)),
                  "outside_central_98": bool(obs < np.percentile(x, 1) or obs > np.percentile(x, 99))}
    return {"replications": n, "origins": [int(y) for y in years], "statistics": out,
            "outside_central_98": sorted(k for k, v in out.items() if v["outside_central_98"])}


def path_statistics(inputs):
    """Descriptive statistics of statutory input paths (paths, years, 2): floor share, lead changes, correlation."""
    x = inputs - inputs.mean(axis=1, keepdims=True)
    within = (x[:, :, 0] * x[:, :, 1]).sum(axis=1) / np.sqrt((x[:, :, 0] ** 2).sum(axis=1) * (x[:, :, 1] ** 2).sum(axis=1))
    return {"floor_share": float((inputs[:, :, 1] < 0.025).mean()),
            "lead_changes_per_year": float(switches(inputs).mean() / (inputs.shape[1] - 1)),
            "correlation_within_path_mean": float(np.nanmean(within))}


def forward_against_history(inputs):
    series, _ = V.statutory_history(OUTTURN_FIRST, RECORD_LAST)
    hist = np.array([series[y] for y in range(2001, RECORD_LAST + 1)])[None]
    dev = inputs[:, 1:] - V.centre()[None, 1:]
    return {"forward_2027_2038": {**path_statistics(inputs[:, 1:]),
                                  "deviation_correlation_pooled": float(np.corrcoef(dev[:, :, 0].ravel(), dev[:, :, 1].ravel())[0, 1])},
            "forward_2026_2038_lead_changes_per_year": float(switches(inputs).mean() / (inputs.shape[1] - 1)),
            "history_2001_2025": path_statistics(hist),
            "note": "descriptive: the forward centre differs from the past (earnings 2.1% to 3.6%, CPI near 2%)"}


def prior_predictive(ctx):
    theta = prior_draws()
    res, inputs, _ = forecast_summary(theta, ctx, seed=PREDICTIVE_SEED + 4, n_batches=0)
    keep = {str(y): res["by_year"][str(y)]["gross_bn"] | {"probability": res["by_year"][str(y)]["probability"]["gross"]}
            for y in REPORT_YEARS}
    return {"draws": len(theta), "n_paths": res["n_paths"], "gross_bn": keep,
            "input_deviation_sd_points": {str(y): res["input_deviation_sd_points"][str(y)] for y in (2027, 2030, 2038)},
            "parameters": {k: {"p5": float(np.percentile(v, 5)), "p50": float(np.percentile(v, 50)),
                               "p95": float(np.percentile(v, 95))} for k, v in derived(theta).items()}}


# ── Stored posterior ─────────────────────────────────────────────────────────


def save_posterior(draws, path=POSTERIOR):
    """The chains as run (chains, kept, 13), before the spectral-radius bound, as float64 in numpy's .npy format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        np.save(f, np.ascontiguousarray(draws, dtype="<f8"))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_posterior(path=POSTERIOR):
    """The chains as run, the retained draws (D, 13) and each retained draw's chain."""
    with Path(path).open("rb") as f:
        draws = np.load(f)
    return (draws, *retained(draws))


def posterior_summary(theta, nu_fixed=0.0):
    return {k: {"mean": float(v.mean()), "sd": float(v.std(ddof=1)), "p5": float(np.percentile(v, 5)),
                "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95))}
            for k, v in derived(theta, nu_fixed).items()}


def provenance():
    return {"label": LABEL, "spec": "docs/METHOD.md, Bayesian forecast of the uprating inputs (B1)",
            "spec_commit": SPEC_COMMIT, "no_microsimulation": True, "numpy_version": np.__version__,
            "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (CPI_CSV, AWE_CSV, ERROR_CSV, ACTUALS_CSV, V.RESULTS, V.EMULATOR_CHECK)}}


def build_forecast(posterior=POSTERIOR):
    draws, theta, chain = load_posterior(posterior)
    ctx = cash_context()
    res, inputs, _ = forecast_summary(theta, ctx, chain=chain)
    forecast = {**provenance(), "posterior_sha256": hashlib.sha256(Path(posterior).read_bytes()).hexdigest(),
                "seed": PREDICTIVE_SEED, "antithetic": True, "draws_as_run": int(draws.shape[0] * draws.shape[1]),
                "draws_outside_radius_bound": int(draws.shape[0] * draws.shape[1] - len(theta)),
                "years": {str(y): f"{y}-{str(y + 1)[2:]}" for y in HORIZON},
                "units": "G in log points (fraction); share as a fraction; gross and net in £bn, UK, cash",
                "centre": {str(y): dict(zip(V.VARIABLES, map(float, c))) for y, c in zip(STATUTORY_YEARS, V.centre())},
                "central_rule_arithmetic": {str(y): {"G": float(ctx["central_G"][j]),
                                                      "gross_bn": float(-np.expm1(-ctx["central_G"][j]) * ctx["base"][j])}
                                            for j, y in enumerate(HORIZON)},
                "net_ratio": {k: ctx[k] for k in ("rho", "rho_path_years", "max_stored_gross_bn",
                                                  "rho_loo_mean_abs_error_pct", "rho_loo_max_abs_error_pct")},
                "long_run_shift": {"from_determination_year": DELTA_FROM, "sd_points": dict(zip(("cpi", "real_earnings"), PRIORS["delta_sd"]))},
                "mc_se_batches": N_BATCHES, **res,
                "conditional_on_parameters": conditional_on_parameters(theta, ctx)}
    validation = {**provenance(), "posterior_sha256": forecast["posterior_sha256"],
                  "prior_predictive": prior_predictive(ctx),
                  "posterior_for_comparison": {
                      "gross_bn": {str(y): forecast["by_year"][str(y)]["gross_bn"] | {"probability": forecast["by_year"][str(y)]["probability"]["gross"]}
                                   for y in REPORT_YEARS},
                      "input_deviation_sd_points": {str(y): forecast["input_deviation_sd_points"][str(y)] for y in (2027, 2030, 2038)}},
                  "replicated_error_records": replicated_records(theta),
                  "forward_paths_against_history": forward_against_history(inputs)}
    return forecast, validation


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True, default=float) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    forecast, validation = build_forecast()
    write(args.output / "forecast.json", forecast)
    write(args.output / "validation.json", validation)
    for y in REPORT_YEARS:
        s = forecast["by_year"][str(y)]
        print(y, "gross", {k: round(v, 2) for k, v in s["gross_bn"].items()}, "net p50", round(s["net_bn"]["p50"], 2),
              s["probability"]["gross"])


if __name__ == "__main__":
    main()
