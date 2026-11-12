"""V1: results conditional on stated volatility assumptions (docs/METHOD.md, "Conditional volatility bands (V1)").

A sensitivity, not a calibrated forecast and not a registration: if September CPI and May-July earnings growth vary
around the OBR central path as they varied over a stated span of past years, the rules' gap is distributed as this
module computes. It uses neither the first model (C2) nor the second (C4); it reads only ``rules`` and ``central``, the
committed ONS series and the stored central run. No PolicyEngine run or survey data enters anything here.

    python -m triple_lock.v1_bands --output data/v1

writes ``bands.json``.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from . import rules
from .central import _ons_monthly, central_path
from .config import AWE_CSV, CENTRAL_RATE_DECIMALS, CPI_CSV, HORIZON, REPO, STATUTORY_YEARS
from .history_data import history

SPEC_COMMIT = "fcf1609f673f488958fd6343288a3eaa499b0d4b"
FIRST_YEAR, LAST_YEAR = 1997, 2025
FIRST_KAC3_YEAR = 2001
EXCLUDED = (2021, 2022, 2023)
SETTINGS = {
    "a": {"label": "1997-2025", "excluded": ()},
    "b": {"label": "1997-2025 without 2021-23", "excluded": EXCLUDED},
}
SEED = 20261112
N_HALF = 5_000  # antithetic pairs: 10,000 paths
QUANTILES = (5, 25, 50, 75, 95)
PAY_SAME_YEARS = (2034, 2039)
HIST_BIN_BN = 0.5
VARIABLES = ("cpi", "earnings")
RESULTS = REPO / "data" / "results.json"
EMULATOR_CHECK = REPO / "data" / "c4" / "emulator_check.json"
LABEL = ("conditional on stated volatility assumptions (V1): a sensitivity, not a calibrated forecast; "
         "not output of the C2 or C4 models; Max's ruling on its use in the paper is pending")


def statutory_history(first=FIRST_YEAR, last=LAST_YEAR):
    """{year: (September CPI, May-July earnings growth)} as decimals, and each year's earnings source.

    September CPI is D7G7's September row. Earnings are KAC3's July row (May-July total pay growth) from 2001; for the
    years before, which KAC3 does not cover, national-accounts wages and salaries per employee on the OBR's definition
    (``history_data.history``), a smoother calendar-year measure.
    """
    cpi = _ons_monthly(CPI_CSV)
    awe = _ons_monthly(AWE_CSV)
    na_years, na = history(first_year=first, last_year=min(last, FIRST_KAC3_YEAR - 1))
    na_earn = dict(zip(na_years, na[:, 1]))
    out, source = {}, {}
    for y in range(first, last + 1):
        if y >= FIRST_KAC3_YEAR:
            e, source[y] = awe[f"{y} JUL"], "KAC3 May-July"
        else:
            e, source[y] = float(na_earn[y]), "national-accounts wages and salaries per employee (OBR definition)"
        out[y] = (cpi[f"{y} SEP"], e)
    return out, source


def estimate(series, excluded=()):
    """Anchor m, AR(1) coefficient phi through the origin and innovation covariance Sigma, per the V1 spec.

    ``series``: {year: (cpi, earnings)}. Lag pairs with either year excluded are dropped.
    """
    years = [y for y in sorted(series) if y not in excluded]
    x = np.array([series[y] for y in years])
    m = x.mean(axis=0)
    dev = {y: np.array(series[y]) - m for y in years}
    pairs = [(y - 1, y) for y in years if y - 1 in dev]
    lag = np.array([dev[a] for a, _ in pairs])
    cur = np.array([dev[b] for _, b in pairs])
    phi = (lag * cur).sum(axis=0) / (lag**2).sum(axis=0)
    u = cur - phi * lag
    sigma = np.cov(u, rowvar=False, ddof=1)
    if np.any(np.abs(phi) >= 1):
        raise ValueError(f"V1 stops: |phi| >= 1 ({phi}); a changed model needs a new dated section")
    return {"years": years, "anchor": m, "phi": phi, "sigma": sigma, "pairs": pairs}


def normals(n_half=N_HALF, seed=SEED, n_years=len(STATUTORY_YEARS) - 1):
    """Standard normal pairs (2 n_half, n_years, 2): n_half draws and their negatives."""
    z = np.random.default_rng(seed).standard_normal((n_half, n_years, 2))
    return np.concatenate([z, -z])


def deviations(est, z):
    """epsilon (n, years after 2026, 2): epsilon(2026) = 0, epsilon(t) = diag(phi) epsilon(t-1) + L z(t)."""
    L = np.linalg.cholesky(est["sigma"])
    eps = np.zeros(z.shape)
    prev = np.zeros((z.shape[0], 2))
    for j in range(z.shape[1]):
        prev = est["phi"] * prev + z[:, j] @ L.T
        eps[:, j] = prev
    return eps


def centre(central=None):
    """The OBR central path's statutory inputs (STATUTORY_YEARS, 2): 2026 published, then the central path."""
    central = central_path() if central is None else central
    return np.array([[central["statutory"][v][y] for v in VARIABLES] for y in STATUTORY_YEARS])


def paths(est, z, central=None):
    """Statutory inputs (n, STATUTORY_YEARS, 2): the centre plus the deviations, with 2026 fixed."""
    c = centre(central)
    eps = np.concatenate([np.zeros((z.shape[0], 1, 2)), deviations(est, z)], axis=1)
    return c[None] + eps


def rule_arithmetic(stat_cpi, stat_earnings):
    """Rates of both rules for the Aprils in HORIZON at the published 0.1-point rounding; G, share, TL index, same."""
    tl = rules.rates_matrix("triple_lock", stat_cpi, stat_earnings, HORIZON, CENTRAL_RATE_DECIMALS)
    bp = rules.rates_matrix("burnham_2030", stat_cpi, stat_earnings, HORIZON, CENTRAL_RATE_DECIMALS)
    G = np.cumsum(np.log1p(tl) - np.log1p(bp), axis=1)
    return {"tl": tl, "bp": bp, "G": G, "share": -np.expm1(-G), "tl_index": np.cumprod(1 + tl, axis=1),
            "same": np.cumprod(tl == bp, axis=1).astype(bool)}


def central_run(results=None):
    results = json.loads(RESULTS.read_text()) if results is None else results
    return results["scenario_envelope"]["central"]["run"]


def base_bn(run):
    """B(y): the central run's basic and new State Pension spending under the triple lock, £bn, by HORIZON year."""
    return np.array([run["totals_bn"]["triple_lock"][str(y)]["state_pension_flat_rate"] for y in HORIZON])


def gross_bn(share, tl_index, central_tl_index, base):
    """The exact identity: gross = share x B x (path TL level / central TL level)."""
    return share * base * tl_index / central_tl_index


def stored_runs(results):
    """The five stored single-path runs: the trajectories' paths and the OBR long-term path."""
    runs = {p["id"]: p for p in results["trajectories"]["paths"]}
    runs["obr_wedge"] = results["scenario_envelope"]["obr_wedge"]["run"]
    return runs


def net_ratio(results):
    """rho: least squares through the origin of net on gross over every stored path-year with a gap."""
    g, n = [], []
    for p in stored_runs(results).values():
        for y in map(str, HORIZON):
            tl, bp = (p["weekly"][k]["new_state_pension"][y] for k in ("triple_lock", "burnham_2030"))
            if tl - bp <= 1e-9 * tl:
                continue
            g.append(p["saving_bn"][y]["gross"])
            n.append(p["saving_bn"][y]["net"])
    g, n = np.array(g), np.array(n)
    return float(g @ n / (g @ g)), len(g), float(g.max())


def summary(x):
    return {"mean": float(np.mean(x)), **{f"p{q}": float(np.percentile(x, q)) for q in QUANTILES}}


def run_setting(key, series, z, central, base, rho):
    est = estimate(series, SETTINGS[key]["excluded"])
    st = paths(est, z, central)
    ra = rule_arithmetic(st[:, :, 0], st[:, :, 1])
    c = centre(central)
    ca = rule_arithmetic(c[None, :, 0], c[None, :, 1])
    gross = gross_bn(ra["share"], ra["tl_index"], ca["tl_index"], base)
    net = rho * gross
    j39 = HORIZON.index(2039)
    edges = np.arange(0, np.ceil(gross[:, j39].max() / HIST_BIN_BN) * HIST_BIN_BN + HIST_BIN_BN, HIST_BIN_BN)
    counts, _ = np.histogram(gross[:, j39], bins=edges)
    return {
        "label": SETTINGS[key]["label"],
        "excluded_years": list(SETTINGS[key]["excluded"]),
        "retained_years": est["years"],
        "lag_pairs": len(est["pairs"]),
        "anchor": dict(zip(VARIABLES, map(float, est["anchor"]))),
        "phi": dict(zip(VARIABLES, map(float, est["phi"]))),
        "innovation_sd": dict(zip(VARIABLES, map(float, np.sqrt(np.diag(est["sigma"]))))),
        "innovation_correlation": float(est["sigma"][0, 1] / np.sqrt(est["sigma"][0, 0] * est["sigma"][1, 1])),
        "sigma": est["sigma"].tolist(),
        "statutory_input_sd_2038": dict(zip(VARIABLES, map(float, st[:, -1].std(axis=0)))),
        "by_year": {str(y): {"G": summary(ra["G"][:, j]), "share": summary(ra["share"][:, j]),
                             "gross_bn": summary(gross[:, j]), "net_bn": summary(net[:, j])}
                    for j, y in enumerate(HORIZON)},
        "pay_same_share": {str(y): float(ra["same"][:, HORIZON.index(y)].mean()) for y in PAY_SAME_YEARS},
        "gross_2039_histogram": {"bin_bn": HIST_BIN_BN, "edges_bn": edges.tolist(), "counts": counts.tolist()},
    }


def build(results=None, central=None):
    results = json.loads(RESULTS.read_text()) if results is None else results
    central = central_path() if central is None else central
    series, source = statutory_history()
    run = central_run(results)
    base = base_bn(run)
    rho, n_rho, max_gross = net_ratio(results)
    loo = json.loads(EMULATOR_CHECK.read_text())["net_over_gross_leave_one_path_out"]
    z = normals()
    c = centre(central)
    ca = rule_arithmetic(c[None, :, 0], c[None, :, 1])
    return {
        "label": LABEL,
        "spec": "docs/METHOD.md, Conditional volatility bands (V1)",
        "spec_commit": SPEC_COMMIT,
        "no_microsimulation": True,
        "numpy_version": np.__version__,
        "n_paths": 2 * N_HALF,
        "seed": SEED,
        "antithetic": True,
        "years": {str(y): f"{y}-{str(y + 1)[2:]}" for y in HORIZON},
        "units": "G in log points (fraction); share as a fraction; gross and net in £bn, UK, cash",
        "series": {str(y): {"cpi": series[y][0], "earnings": series[y][1], "earnings_source": source[y]}
                   for y in sorted(series)},
        "centre": {str(y): dict(zip(VARIABLES, map(float, c[i]))) for i, y in enumerate(STATUTORY_YEARS)},
        "central_rule_arithmetic": {str(y): {"G": float(ca["G"][0, j]),
                                              "gross_bn": float(ca["share"][0, j] * base[j])}
                                    for j, y in enumerate(HORIZON)},
        "base_bn": {str(y): float(b) for y, b in zip(HORIZON, base)},
        "net_ratio": {"rho": rho, "path_years": n_rho, "max_stored_gross_bn": max_gross,
                      "leave_one_path_out_mean_abs_error_pct": loo["mean_abs_error_pct"],
                      "leave_one_path_out_max_abs_error_pct": loo["max_abs_error_pct"]},
        "input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (CPI_CSV, AWE_CSV, RESULTS, EMULATOR_CHECK)},
        "settings": {k: run_setting(k, series, z, central, base, rho) for k in SETTINGS},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=REPO / "data" / "v1")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    out = build()
    (args.output / "bands.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for k, s in out["settings"].items():
        y = s["by_year"]["2039"]
        print(k, s["label"], "phi", s["phi"], "sd", s["innovation_sd"], "corr", round(s["innovation_correlation"], 3))
        print("  2039 gross", {q: round(v, 2) for q, v in y["gross_bn"].items()},
              "net", {q: round(v, 2) for q, v in y["net_bn"].items()}, "same", s["pay_same_share"])


if __name__ == "__main__":
    main()
