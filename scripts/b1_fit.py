"""B1: the registered fit (docs/METHOD.md, B1). Writes data/b1/posterior.npy and data/b1/fit.json.

NumPyro's NUTS sampler on the joint posterior; the convergence gate of the specification is applied, with its one
rerun. Everything downstream (``python -m triple_lock.b1_bayes``) reads the stored draws with numpy alone.

    PYTHONPATH=src python scripts/b1_fit.py
"""

import json

import numpy as np

from triple_lock import b1_bayes as B


def main():
    import jax
    import numpyro

    cells, transitions = B.error_cells(), B.outturn_transitions()
    data = B.likelihood_data(cells, transitions)
    draws, diag = B.fit(data)
    theta, _ = B.retained(draws)
    sha = B.save_posterior(draws)
    out = {**B.provenance(), "posterior_sha256": sha, "parameters": list(B.PARAMS), "priors": B.PRIORS,
           "sampler": {"numpyro": numpyro.__version__, "jax": jax.__version__, **diag["settings"]},
           "convergence": {k: v for k, v in diag.items() if k != "settings"},
           "radius_bound": {"bound": B.RADIUS_MAX, "draws_as_run": diag["n_draws"],
                            "draws_outside": diag["draws_outside_radius_bound"], "draws_retained": diag["draws_retained"],
                            "how": "NUTS on the posterior without the bound; draws outside it discarded"},
           "headline_permitted": diag["gate_met"],
           "share_of_draws_with_spectral_radius_above_0.95": float((B.spectral_radius(theta) > 0.95).mean()),
           "posterior": B.posterior_summary(theta),
           "data": {"error_cells": int((data["w_f"] > 0).sum()), "error_target_years": int(round(data["w_f"].sum())),
                    "error_cells_by_target_year": {str(int(t)): int((cells["target"] == t).sum())
                                                   for t in np.unique(cells["target"])},
                    "error_origins": sorted({int(v) for v in cells["origin"]}),
                    "outturn_transitions": int(data["w_o"].sum()),
                    "outturn_transition_years": [int(y) for y, w in zip(transitions["year"], data["w_o"]) if w],
                    "outturn_earnings_source": {str(y): transitions["source"][y]
                                                for y in range(B.OUTTURN_FIRST, B.OUTTURN_LAST + 1)}}}
    B.write(B.OUT / "fit.json", out)
    print(json.dumps({"gate_met": diag["gate_met"], "worst": diag["worst"], "sha": sha}, indent=1))
    print(json.dumps({k: [round(v["p5"], 3), round(v["p50"], 3), round(v["p95"], 3)] for k, v in out["posterior"].items()}))


if __name__ == "__main__":
    main()
