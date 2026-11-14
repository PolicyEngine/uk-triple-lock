"""B1: the appendix sensitivities T1 to T3 (docs/METHOD.md, B1, "Appendix sensitivities T1 to T3", registered
14 November 2026 before this file existed). Writes data/b1/appendix_sensitivities.json.

T1 refits the registered model with the spectral-radius bound imposed by a smooth change of variables; T2 transforms the
headline's forward paths with a soft lower bound on the inputs (no refit); T3 refits with a persistent log variance in
place of the Student-t shock. None replaces the headline or rewrites any other file in data/b1/. No PolicyEngine run.

    PYTHONPATH=src python scripts/b1_appendix_sensitivities.py [t1] [t2] [t3]
"""

import json
import sys

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock import v1_bands as V
from triple_lock.config import HORIZON, STATUTORY_YEARS

OUT = B.OUT / "appendix_sensitivities.json"
SPEC_COMMIT = "c78f161"
BOUNDS = {"zero": 0.0, "record_minimum": -0.01}  # T2's lower bounds, as decimals
T3_PHI_MAX, T3_S_SCALE = 0.95, 0.5
T3_FIRST, T3_LAST = 1990, 2026


def report(out):
    """Gross saving distribution and the shares of paths above the thresholds in the report years."""
    res = {}
    for y in B.REPORT_YEARS:
        j = HORIZON.index(y)
        g = out["gross_bn"][:, j]
        res[str(y)] = {"gross_bn": B._stats(g), "probability": {"above_0": float(np.mean(out["G"][:, j] > 0)),
                                                                 "above_5": float(np.mean(g > 5)),
                                                                 "above_10": float(np.mean(g > 10))}}
    return res


def pct(x, qs=(5, 25, 50, 75, 95)):
    return {f"p{q}": float(np.percentile(x, q)) for q in qs}


# ── T1: the bound by reparameterisation ──────────────────────────────────────


def _sqrt2(M, xp):
    """The symmetric square root of a 2 x 2 positive-definite matrix, in closed form."""
    s = xp.sqrt(M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0])
    return (M + s * xp.eye(2)) / xp.sqrt(M[0, 0] + M[1, 1] + 2 * s)


def phi_of(A4, xp=np):
    """R^4 onto the 2 x 2 matrices with spectral radius below RADIUS_MAX, in PARAMS order (cc, ce, ec, ee)."""
    A = A4.reshape(2, 2)
    P = xp.linalg.inv(_sqrt2(xp.eye(2) + A @ A.T, xp)) @ A
    G = xp.linalg.inv(xp.eye(2) - P @ P.T)
    R = _sqrt2(G, xp)
    return (B.RADIUS_MAX * R @ P @ xp.linalg.inv(R)).reshape(4)


def a_of(phi4):
    """The inverse map (numpy): Gamma from the Lyapunov equation, P, then A."""
    from scipy.linalg import solve_discrete_lyapunov

    Psi = np.asarray(phi4, dtype=float).reshape(2, 2) / B.RADIUS_MAX
    G = solve_discrete_lyapunov(Psi, np.eye(2))
    R = _sqrt2(G, np)
    P = np.linalg.inv(R) @ Psi @ R
    return (np.linalg.inv(_sqrt2(np.eye(2) - P @ P.T, np)) @ P).reshape(4)


def _model_t1(a, a_lag, w_f, s, s_lag, w_o, hp):
    import jax
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    A = numpyro.sample("A", dist.ImproperUniform(dist.constraints.real_vector, (), (4,)))
    phi = phi_of(A, jnp)
    logdet = jnp.linalg.slogdet(jax.jacfwd(lambda x: phi_of(x, jnp))(A))[1]
    numpyro.factor("phi_prior", dist.Normal(hp["phi_mu"], hp["phi_sd"]).log_prob(phi).sum() + logdet)
    numpyro.deterministic("phi", phi)
    log_sigma = numpyro.sample("log_sigma", dist.Normal(hp["log_sigma_mu"], hp["log_sigma_sd"]).expand([2]).to_event(1))
    z_rho = numpyro.sample("z_rho", dist.Normal(hp["z_mu"], hp["z_sd"]))
    zeta = numpyro.sample("zeta", dist.Normal(0.0, hp["zeta_sd"]))
    log_kappa = numpyro.sample("log_kappa", dist.Normal(0.0, hp["log_kappa_sd"]).expand([2]).to_event(1))
    nu_m2 = numpyro.sample("nu_m2", dist.Gamma(hp["nu_shape"], hp["nu_rate"]))
    m = numpyro.sample("m", dist.Normal(hp["m_mu"], hp["m_sd"]).to_event(1))
    Phi = phi.reshape(2, 2)
    nu = 2.0 + nu_m2

    def tril(log_sd, z):
        sd, rho = jnp.exp(log_sd), jnp.tanh(z)
        return jnp.array([[sd[0], 0.0], [rho * sd[1], sd[1] * jnp.sqrt(1 - rho * rho)]])

    r_f = a - a_lag @ Phi.T
    r_o = (s - m) - (s_lag - m) @ Phi.T
    numpyro.factor("errors", (w_f * dist.MultivariateStudentT(nu, jnp.zeros(2), tril(log_sigma, z_rho)).log_prob(r_f)).sum())
    numpyro.factor("outturns", (w_o * dist.MultivariateStudentT(nu, jnp.zeros(2), tril(log_sigma + log_kappa, z_rho + zeta)).log_prob(r_o)).sum())


def _run(model, data, init, *, warmup, kept, target_accept, seed=B.MCMC_SEED, extra=()):
    import os

    os.environ.setdefault("XLA_FLAGS", "--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1")
    import jax
    import jax.numpy as jnp
    from numpyro.infer import MCMC, NUTS, init_to_value

    jax.config.update("jax_enable_x64", True)
    kernel = NUTS(model, target_accept_prob=target_accept,
                  init_strategy=init_to_value(values={k: jnp.asarray(v) for k, v in init.items()}))
    mcmc = MCMC(kernel, num_warmup=warmup, num_samples=kept, num_chains=B.CHAINS, chain_method="sequential",
                progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), **{k: jnp.asarray(v, dtype=jnp.float64) for k, v in data.items()},
             hp=B._hyper(B.PRIORS), extra_fields=("diverging",))
    s = {k: np.asarray(v) for k, v in mcmc.get_samples(group_by_chain=True).items()}
    draws = np.concatenate([s["phi"], s["log_sigma"], s["z_rho"][..., None], s["zeta"][..., None], s["log_kappa"],
                            s["nu_m2"][..., None], s["m"]], axis=-1)
    return draws, int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum()), {k: s[k] for k in extra}


def _init_t1():
    P = B.PRIORS
    return {"A": a_of(P["phi_mu"]), "log_sigma": np.full(2, P["log_sigma_mu"]), "z_rho": P["z_mu"], "zeta": 0.0,
            "log_kappa": np.zeros(2), "nu_m2": 20.0, "m": np.array(P["m_mu"])}


def t1(ctx, log=print):
    data = B.likelihood_data()
    stored, theta0, _ = B.load_posterior()
    # The map and its inverse agree on the stored draws.
    sub = theta0[:: max(1, len(theta0) // 500), :4]
    roundtrip = float(max(np.abs(phi_of(a_of(p)) - p).max() for p in sub))

    # Check (i): the priors alone through the same map against prior_draws (the registered priors with the bound by
    # rejection).
    prior_data = {**data, "w_f": np.zeros_like(data["w_f"]), "w_o": np.zeros_like(data["w_o"])}
    pd_, pdiv, _ = _run(_model_t1, prior_data, _init_t1(), warmup=B.WARMUP, kept=B.KEPT, target_accept=B.TARGET_ACCEPT,
                        seed=B.MCMC_SEED + 1)
    pt = pd_.reshape(-1, pd_.shape[-1])
    ref = B.prior_draws(n=100_000, seed=B.PREDICTIVE_SEED + 11)
    pdiag = B.diagnostics(pd_, pdiv)
    prior_check = {"divergences": pdiv, "worst": pdiag["worst"], "parameters": {}}
    cols = {k: j for j, k in enumerate(B.PARAMS[:4])}
    series = {**{k: (pt[:, j], ref[:, j]) for k, j in cols.items()},
              "spectral_radius": (B.spectral_radius(pt), B.spectral_radius(ref))}
    for k, (x, r) in series.items():
        ess = pdiag["parameters"][k]["ess_bulk"] if k in cols else min(pdiag["parameters"][c]["ess_bulk"] for c in cols)
        prior_check["parameters"][k] = {"reparameterised": pct(x), "rejection": pct(r), "sd_rejection": float(r.std()),
                                        "ess_bulk": float(ess),
                                        "max_abs_quantile_gap_in_sd": float(max(abs(pct(x)[q] - pct(r)[q]) for q in pct(x)) / r.std())}
    prior_check["max_abs_quantile_gap_in_sd"] = max(v["max_abs_quantile_gap_in_sd"] for v in prior_check["parameters"].values())
    prior_check["passed"] = bool(prior_check["max_abs_quantile_gap_in_sd"] < 0.1)
    log(f"T1 prior check: gap {prior_check['max_abs_quantile_gap_in_sd']:.3f} sd, divergences {pdiv}")

    # The fit, with the gate as written and its one rerun.
    draws, div, _ = _run(_model_t1, data, _init_t1(), warmup=B.WARMUP, kept=B.KEPT, target_accept=B.TARGET_ACCEPT)
    diag = B.diagnostics(draws, div)
    settings = {"warmup": B.WARMUP, "kept": B.KEPT, "target_accept": B.TARGET_ACCEPT, "rerun": False}
    if not diag["gate_met"]:
        log(f"T1 gate unmet ({diag['worst']}); rerun")
        first = diag
        draws, div, _ = _run(_model_t1, data, _init_t1(), warmup=B.RERUN_WARMUP, kept=B.KEPT,
                             target_accept=B.RERUN_TARGET_ACCEPT)
        diag = B.diagnostics(draws, div)
        diag["first_attempt"] = {"worst": first["worst"], "gate_met": first["gate_met"]}
        settings.update(warmup=B.RERUN_WARMUP, target_accept=B.RERUN_TARGET_ACCEPT, rerun=True)
    theta = draws.reshape(-1, draws.shape[-1])
    outside = int((B.spectral_radius(theta) >= B.RADIUS_MAX).sum())
    log(f"T1 fit: {diag['worst']}, gate met {diag['gate_met']}, outside {outside}")

    # Check (ii): the posterior against the committed draws, in units of the committed posterior's standard deviation
    # and of the Monte Carlo error of a median (1.2533 sd / sqrt(ess), both fits).
    post_check = {"parameters": {}}
    sdiag = B.diagnostics(stored, 0)["parameters"]
    for j, k in enumerate(B.PARAMS):
        x, r = theta[:, j], theta0[:, j]
        mc = 1.2533 * r.std() * np.sqrt(1 / diag["parameters"][k]["ess_bulk"] + 1 / sdiag[k]["ess_bulk"])
        post_check["parameters"][k] = {"reparameterised": pct(x), "committed": pct(r),
                                       "median_gap_in_mc_se": float(abs(np.median(x) - np.median(r)) / mc),
                                       "max_abs_quantile_gap_in_sd": float(max(abs(pct(x)[q] - pct(r)[q]) for q in pct(x)) / r.std())}
    post_check["max_median_gap_in_mc_se"] = max(v["median_gap_in_mc_se"] for v in post_check["parameters"].values())
    post_check["max_abs_quantile_gap_in_sd"] = max(v["max_abs_quantile_gap_in_sd"] for v in post_check["parameters"].values())
    post_check["passed"] = bool(post_check["max_abs_quantile_gap_in_sd"] < 0.1)
    log(f"T1 posterior check: {post_check['max_abs_quantile_gap_in_sd']:.3f} sd, {post_check['max_median_gap_in_mc_se']:.2f} MC se")

    res = {"label": "T1: the registered model with the spectral-radius bound by reparameterisation",
           "map_roundtrip_max_abs_error": roundtrip, "prior_check": prior_check, "posterior_check": post_check,
           "convergence": {"worst": diag["worst"], "gate": diag["gate"], "gate_met_as_written": diag["gate_met"],
                           **({"first_attempt": diag["first_attempt"]} if "first_attempt" in diag else {})},
           "settings": {**settings, "chains": B.CHAINS, "seed": B.MCMC_SEED},
           "draws": int(len(theta)), "draws_outside_radius_bound": outside,
           "posterior": {k: {q: v[q] for q in ("p5", "p50", "p95")} for k, v in B.posterior_summary(theta).items()}}
    if prior_check["passed"] and post_check["passed"]:
        fc, _, out = B.forecast_summary(theta, ctx, n_batches=B.N_BATCHES)
        res["forecast"] = report(out)
        res["monte_carlo_se"] = {y: fc["monte_carlo_se"][y] for y in map(str, B.REPORT_YEARS)}
        res["n_paths"] = fc["n_paths"]
    else:
        res["forecast"] = None
        res["status"] = "failed its coding checks; no forecast"
    return res


# ── T2: a soft lower bound on the inputs, forward only ───────────────────────


def soft_bound(inputs, centre, L):
    """x = f + eps where eps >= 0; x = L + (f - L) exp(eps / (f - L)) where eps < 0. Year 0 (2026) is fixed."""
    f = centre[None]
    eps = inputs - f
    span = f - L
    if (span[:, 1:] <= 0).any():
        raise ValueError("the centre must lie above the bound")
    low = L + span * np.exp(np.minimum(eps, 0.0) / span)
    x = np.where(eps >= 0, inputs, low)
    x[:, 0] = inputs[:, 0]
    return x


def recentred(x, centre, L):
    """(x - L) divided in each year by its average over paths relative to (f - L): the centre is the mean again."""
    f = centre[None]
    factor = (x - L).mean(axis=0, keepdims=True) / (f - L)
    y = L + (x - L) / factor
    y[:, 0] = x[:, 0]
    return y


def t2(ctx, log=print):
    _, theta, _ = B.load_posterior()
    inputs = B.forward_inputs(theta)
    c = V.centre()
    base = B.arithmetic(inputs, ctx)
    res = {"label": "T2: soft lower bound on the forward statutory inputs; the headline's draws and shocks; no refit",
           "headline_recomputed": report(base),
           "headline_share_path_years_below_zero": dict(zip(V.VARIABLES, map(float, (inputs[:, 1:] < 0).mean(axis=(0, 1))))),
           "headline_earnings_below_floor_share": B.forward_against_history(inputs)["forward_2027_2038"]["floor_share"],
           "runs": {}}
    for name, L in BOUNDS.items():
        x = soft_bound(inputs, c, L)
        for variant, paths in (("median_centred", x), ("mean_centred", recentred(x, c, L))):
            out = B.arithmetic(paths, ctx)
            shift = 100 * (paths[:, 1:].mean(axis=0) - c[1:])
            res["runs"][f"{name}_{variant}"] = {
                "bound_points": 100 * L, "variant": variant, **report(out),
                "mean_shift_points": {"mean_over_years": dict(zip(V.VARIABLES, map(float, shift.mean(axis=0)))),
                                      "max_over_years": dict(zip(V.VARIABLES, map(float, shift.max(axis=0))))},
                "share_path_years_below_zero": dict(zip(V.VARIABLES, map(float, (paths[:, 1:] < 0).mean(axis=(0, 1))))),
                "lowest_input_points": dict(zip(V.VARIABLES, map(float, 100 * paths[:, 1:].min(axis=(0, 1))))),
                "earnings_below_floor_share": B.forward_against_history(paths)["forward_2027_2038"]["floor_share"]}
            log(f"T2 {name} {variant}: median {res['runs'][f'{name}_{variant}']['2039']['gross_bn']['p50']:.2f}")
            del out
    return res


# ── T3: a persistent log variance in place of the Student-t shock ────────────


def _model_t3(a, a_lag, w_f, s, s_lag, w_o, hp, idx_f, idx_o, n_years):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    phi = numpyro.sample("phi", dist.Normal(hp["phi_mu"], hp["phi_sd"]).to_event(1))
    log_sigma = numpyro.sample("log_sigma", dist.Normal(hp["log_sigma_mu"], hp["log_sigma_sd"]).expand([2]).to_event(1))
    z_rho = numpyro.sample("z_rho", dist.Normal(hp["z_mu"], hp["z_sd"]))
    zeta = numpyro.sample("zeta", dist.Normal(0.0, hp["zeta_sd"]))
    log_kappa = numpyro.sample("log_kappa", dist.Normal(0.0, hp["log_kappa_sd"]).expand([2]).to_event(1))
    m = numpyro.sample("m", dist.Normal(hp["m_mu"], hp["m_sd"]).to_event(1))
    phi_h = numpyro.sample("phi_h", dist.Uniform(0.0, T3_PHI_MAX))
    s_h = numpyro.sample("s_h", dist.HalfNormal(T3_S_SCALE))
    eta = numpyro.sample("eta", dist.Normal(0.0, 1.0).expand([n_years]).to_event(1))
    # Non-centred: h(first) = s eta / sqrt(1 - phi_h^2), h(t) = phi_h h(t - 1) + s eta(t).
    from jax import lax

    h0 = s_h * eta[0] / jnp.sqrt(1 - phi_h**2)
    _, rest = lax.scan(lambda prev, e: ((phi_h * prev + s_h * e,) * 2), h0, eta[1:])
    h = numpyro.deterministic("h", jnp.concatenate([h0[None], rest]))
    Phi = phi.reshape(2, 2)

    def tril(log_sd, z):
        sd, rho = jnp.exp(log_sd), jnp.tanh(z)
        return jnp.array([[sd[0], 0.0], [rho * sd[1], sd[1] * jnp.sqrt(1 - rho * rho)]])

    def logp(r, L, hh):  # a bivariate normal with scale matrix exp(h) L L'
        zs = jnp.linalg.solve(L, r.T).T * jnp.exp(-hh / 2)[:, None]
        return -0.5 * (zs**2).sum(axis=1) - jnp.log(L[0, 0] * L[1, 1]) - hh - jnp.log(2 * jnp.pi)

    r_f = a - a_lag @ Phi.T
    r_o = (s - m) - (s_lag - m) @ Phi.T
    numpyro.factor("errors", (w_f * logp(r_f, tril(log_sigma, z_rho), h[idx_f])).sum())
    numpyro.factor("outturns", (w_o * logp(r_o, tril(log_sigma + log_kappa, z_rho + zeta), h[idx_o])).sum())


def t3(ctx, log=print):
    import jax.numpy as jnp

    cells, trans = B.error_cells(), B.outturn_transitions()
    data = B.likelihood_data(cells, trans)
    n_years = T3_LAST - T3_FIRST + 1
    idx_f = np.asarray(cells["target"]) - T3_FIRST
    idx_o = np.clip(np.asarray(trans["year"]) - T3_FIRST, 0, n_years - 1)  # weight zero beyond 2010
    if idx_f.min() < 0 or idx_f.max() >= n_years or (data["w_o"][np.asarray(trans["year"]) > B.OUTTURN_LAST] != 0).any():
        raise ValueError("T3's years do not match the records")
    P = B.PRIORS
    init = {"phi": np.array(P["phi_mu"]), "log_sigma": np.full(2, P["log_sigma_mu"]), "z_rho": P["z_mu"], "zeta": 0.0,
            "log_kappa": np.zeros(2), "m": np.array(P["m_mu"]), "phi_h": 0.5, "s_h": 0.5, "eta": np.zeros(n_years)}

    def model(a, a_lag, w_f, s, s_lag, w_o, hp):
        return _model_t3(a, a_lag, w_f, s, s_lag, w_o, hp, jnp.asarray(idx_f), jnp.asarray(idx_o), n_years)

    def run(warmup, accept):
        import jax
        from numpyro.infer import MCMC, NUTS, init_to_value

        jax.config.update("jax_enable_x64", True)
        kernel = NUTS(model, target_accept_prob=accept,
                      init_strategy=init_to_value(values={k: jnp.asarray(v) for k, v in init.items()}))
        mcmc = MCMC(kernel, num_warmup=warmup, num_samples=B.KEPT, num_chains=B.CHAINS, chain_method="sequential",
                    progress_bar=False)
        mcmc.run(jax.random.PRNGKey(B.MCMC_SEED), **{k: jnp.asarray(v, dtype=jnp.float64) for k, v in data.items()},
                 hp=B._hyper(P), extra_fields=("diverging",))
        s = {k: np.asarray(v) for k, v in mcmc.get_samples(group_by_chain=True).items()}
        return s, int(np.asarray(mcmc.get_extra_fields()["diverging"]).sum())

    def diag_of(s, div):
        # The gate's statistics on every sampled parameter and on the last state h(2026), which the forecast starts from.
        cols = {"phi_cc": s["phi"][..., 0], "phi_ce": s["phi"][..., 1], "phi_ec": s["phi"][..., 2], "phi_ee": s["phi"][..., 3],
                "log_sigma_c": s["log_sigma"][..., 0], "log_sigma_e": s["log_sigma"][..., 1], "z_rho": s["z_rho"],
                "zeta": s["zeta"], "log_kappa_c": s["log_kappa"][..., 0], "log_kappa_e": s["log_kappa"][..., 1],
                "m_c": s["m"][..., 0], "m_e": s["m"][..., 1], "phi_h": s["phi_h"], "s_h": s["s_h"], "h_last": s["h"][..., -1]}
        out = {}
        for k, x in cols.items():
            xs = B._split(x)
            folded = np.abs(xs - np.median(xs))
            q05, q95 = np.quantile(xs, [0.05, 0.95])
            out[k] = {"rhat": max(B._rhat(B._rank_normal(xs)), B._rhat(B._rank_normal(folded))),
                      "ess_bulk": B._ess(B._rank_normal(xs)),
                      "ess_tail": min(B._ess((xs <= q05).astype(float)), B._ess((xs <= q95).astype(float)))}
        worst = {"rhat": max(v["rhat"] for v in out.values()), "ess_bulk": min(v["ess_bulk"] for v in out.values()),
                 "ess_tail": min(v["ess_tail"] for v in out.values()), "divergences": div}
        met = (worst["rhat"] <= B.GATE["rhat_max"] and min(worst["ess_bulk"], worst["ess_tail"]) >= B.GATE["ess_min"]
               and div <= B.GATE["divergences_max"])
        return {"worst": worst, "gate": B.GATE, "gate_met_as_written": bool(met)}

    s, div = run(B.WARMUP, B.TARGET_ACCEPT)
    diag = diag_of(s, div)
    settings = {"warmup": B.WARMUP, "target_accept": B.TARGET_ACCEPT, "rerun": False}
    if not diag["gate_met_as_written"]:
        log(f"T3 gate unmet ({diag['worst']}); rerun")
        first = diag
        s, div = run(B.RERUN_WARMUP, B.RERUN_TARGET_ACCEPT)
        diag = {**diag_of(s, div), "first_attempt": first}
        settings.update(warmup=B.RERUN_WARMUP, target_accept=B.RERUN_TARGET_ACCEPT, rerun=True)
    log(f"T3 fit: {diag['worst']}, gate met {diag['gate_met_as_written']}")

    flat = {k: v.reshape((-1,) + v.shape[2:]) for k, v in s.items()}
    n = len(flat["phi_h"])
    theta = np.column_stack([flat["phi"], flat["log_sigma"], flat["z_rho"], flat["zeta"], flat["log_kappa"],
                             np.full(n, 28.0), flat["m"]])  # nu is unused forward: the shocks below are normal
    keep = B.spectral_radius(theta) < B.RADIUS_MAX
    theta, phi_h, s_h, h_last = theta[keep], flat["phi_h"][keep], flat["s_h"][keep], flat["h"][keep, -1]

    # Forward: normal shocks with scale exp(h(t)) Sigma_F, h continuing from each draw's h(2026); mirror images share h.
    rng = np.random.default_rng(B.PREDICTIVE_SEED)
    horizon = len(STATUTORY_YEARS) - 1
    Phi, L, _ = B.unpack(theta)
    d = len(theta)
    z = rng.standard_normal((d, B.PAIRS, horizon, 2))
    eta = rng.standard_normal((d, B.PAIRS, horizon))
    h = np.empty((d, B.PAIRS, horizon))
    prev = np.broadcast_to(h_last[:, None], (d, B.PAIRS))
    for t in range(horizon):
        prev = phi_h[:, None] * prev + s_h[:, None] * eta[:, :, t]
        h[:, :, t] = prev
    u = np.exp(h / 2)[..., None] * np.einsum("dij,dphj->dphi", L, z)
    eps = np.empty_like(u)
    prev = np.zeros((d, B.PAIRS, 2))
    for t in range(horizon):
        prev = np.einsum("dij,dpj->dpi", Phi, prev) + u[:, :, t]
        eps[:, :, t] = prev
    start = STATUTORY_YEARS.index(B.DELTA_FROM) - 1
    dc = rng.normal(0.0, 1.0, (d, B.PAIRS)) * P["delta_sd"][0]
    dr = rng.normal(0.0, 1.0, (d, B.PAIRS)) * P["delta_sd"][1]
    eps[:, :, start:, 0] += dc[:, :, None]
    eps[:, :, start:, 1] += (dc + dr)[:, :, None]
    eps = np.concatenate([eps, -eps], axis=1).reshape(-1, horizon, 2) / 100
    c = V.centre()
    inputs = c[None] + np.concatenate([np.zeros((len(eps), 1, 2)), eps], axis=1)
    out = B.arithmetic(inputs, ctx)
    years = list(range(T3_FIRST, T3_LAST + 1))
    hm = np.median(flat["h"][keep], axis=0)
    return {"label": "T3: normal shocks with a first-order autoregressive log variance over 1990 to 2026, fitted",
            "convergence": diag, "settings": {**settings, "kept": B.KEPT, "chains": B.CHAINS, "seed": B.MCMC_SEED},
            "draws": int(n), "draws_outside_radius_bound": int((~keep).sum()), "n_paths": int(len(inputs)),
            "posterior": {"phi_h": pct(phi_h, (5, 50, 95)), "s_h": pct(s_h, (5, 50, 95)),
                          "h_2026": pct(h_last, (5, 50, 95)),
                          "phi_cc": pct(theta[:, 0], (5, 50, 95)), "phi_ee": pct(theta[:, 3], (5, 50, 95)),
                          "sigma_c": pct(np.exp(theta[:, 4]), (5, 50, 95)), "sigma_e": pct(np.exp(theta[:, 5]), (5, 50, 95)),
                          "sd_multiplier_median_by_year": {str(y): float(np.exp(v / 2)) for y, v in zip(years, hm)}},
            "input_deviation_sd_points": {str(y): dict(zip(V.VARIABLES, map(float, 100 * inputs[:, i].std(axis=0))))
                                          for i, y in enumerate(STATUTORY_YEARS) if y in (2027, 2030, 2038)},
            **report(out)}


def main():
    which = set(sys.argv[1:]) or {"t1", "t2"}
    ctx = B.cash_context()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    res.update({**B.provenance(), "spec": "docs/METHOD.md, B1, Appendix sensitivities T1 to T3 (14 November 2026)",
                "spec_commit": SPEC_COMMIT,
                "label": "Appendix sensitivities of B1, registered after every B1 result was seen; none replaces the headline",
                "posterior_sha256": __import__("hashlib").sha256(B.POSTERIOR.read_bytes()).hexdigest()})
    for k, f in (("t1", t1), ("t2", t2), ("t3", t3)):
        if k in which:
            res[k] = f(ctx)
            B.write(OUT, res)
    return res


if __name__ == "__main__":
    main()
