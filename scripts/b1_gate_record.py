"""B1: what turns on the reading of the convergence gate (docs/METHOD.md, B1 record of 12 November 2026). Writes
data/b1/gate_record.json.

The first fit, at commit 8c798a0, coded the spectral-radius bound as a wall inside NUTS and failed the gate on
divergent transitions. This runs the same forward step on those wall-coded draws (read from git history) and sets the
2039-40 and 2034-35 figures beside the fixed fit's.

    PYTHONPATH=src python scripts/b1_gate_record.py
"""

import io
import json
import subprocess

import numpy as np

from triple_lock import b1_bayes as B

WALL_COMMIT = "8c798a0213a59d435e4f77bfd4621e48a507925e"
WALL_PATH = "data/b1/posterior.npz"  # .npy format under its first name


def figures(theta, ctx):
    res, _, _ = B.forecast_summary(theta, ctx)
    return {str(y): {"gross_bn": res["by_year"][str(y)]["gross_bn"], "probability": res["by_year"][str(y)]["probability"]["gross"],
                     "monte_carlo_se": res["monte_carlo_se"][str(y)]} for y in B.REPORT_YEARS}, res["n_paths"]


def main():
    raw = subprocess.run(["git", "show", f"{WALL_COMMIT}:{WALL_PATH}"], cwd=B.REPO, capture_output=True, check=True).stdout
    wall = np.load(io.BytesIO(raw))
    wall_theta, _ = B.retained(wall)
    _, theta, _ = B.load_posterior()
    ctx = B.cash_context()
    a, na = figures(wall_theta, ctx)
    b, nb = figures(theta, ctx)
    out = {**B.provenance(), "wall_coded": {"commit": WALL_COMMIT, "draws": int(len(wall_theta)), "n_paths": na,
                                             "fit": "the rerun at target acceptance 0.99; 90 transitions flagged divergent",
                                             "posterior": B.posterior_summary(wall_theta), **a},
           "fixed": {"draws": int(len(theta)), "n_paths": nb, "posterior": B.posterior_summary(theta), **b},
           "difference_fixed_less_wall": {y: {k: b[y]["gross_bn"][k] - a[y]["gross_bn"][k] for k in b[y]["gross_bn"]}
                                          for y in b}}
    B.write(B.OUT / "gate_record.json", out)
    for y in b:
        print(y, "wall", {k: round(v, 3) for k, v in a[y]["gross_bn"].items()}, "fixed",
              {k: round(v, 3) for k, v in b[y]["gross_bn"].items()})


if __name__ == "__main__":
    main()
