"""Net saving percentiles and threshold shares of the B1 forecast with the full runs' pooled net-to-gross ratio.

The full runs on a weighted sample of the paths (data/b1/full_runs.json, registered 18 November 2026) give a pooled
ratio of net to gross saving in 2039-40 of about 0.692, against the 0.683 of the stored runs that forecast.json
applies. This script applies the full runs' ratio to every path's rule-arithmetic gross saving in each year (an
assumption for years other than 2039-40, which the runs do not cover) and writes data/b1/net_full_ratio.json.
"""
import json
from pathlib import Path

import numpy as np

from triple_lock import b1_bayes as B
from triple_lock.config import HORIZON

ROOT = Path(__file__).resolve().parents[1]
QS = {"p5": 5, "p25": 25, "p50": 50, "p75": 75, "p95": 95}


def main():
    full = json.loads((ROOT / "data/b1/full_runs.json").read_text())
    ratio = full["estimates"]["supplementary_ratio_estimator"]["pooled_net_to_gross"]
    forecast = json.loads((ROOT / "data/b1/forecast.json").read_text())
    _, theta, _ = B.load_posterior(B.POSTERIOR)
    a = B.arithmetic(B.forward_inputs(theta), B.cash_context())
    out = {"note": __doc__.split("\n")[0], "ratio": ratio, "n_paths": int(len(a["gross_bn"])), "by_year": {}}
    for j, y in enumerate(HORIZON):
        g = a["gross_bn"][:, j]
        if not np.isfinite(g).all():
            g = g[np.isfinite(g)]
        stored = forecast["by_year"].get(str(y))
        if stored is not None:  # the regenerated paths must be the forecast's own
            assert abs(np.percentile(g, 50) - stored["gross_bn"]["p50"]) < 1e-6, y
        n = ratio * g
        out["by_year"][str(y)] = {"net_bn": {k: float(np.percentile(n, q)) for k, q in QS.items()},
                                  "probability": {f"above_{t}": float((n > t).mean()) for t in (0, 5, 10)}}
    (ROOT / "data/b1/net_full_ratio.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["by_year"]["2039"], indent=1), out["n_paths"])


if __name__ == "__main__":
    main()
