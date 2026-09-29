# UK triple lock: cost, distribution and uncertainty

**Dashboard: https://uk-triple-lock.vercel.app/uk/triple-lock**

PolicyEngine UK analysis of the State Pension triple lock and the Prime Minister's plan to adjust it from April 2030, over 2027-28 to 2034-35.

In his speech to Labour's conference on 29 September 2026, Andy Burnham said the triple lock will stay for this Parliament and that, from April 2030, the State Pension will "continue to rise every year at least by prices or 2.5%" and "hold its value relative to earnings over time" ([BBC](https://www.bbc.co.uk/news/live/c6x2zrv774gvt)). Every rule here follows the triple lock to April 2029 and applies its own uprating from April 2030:

- **Burnham plan** (our reading; the speech gave no formula): each April the pension rises by at least the higher of CPI and 2.5%, and it never falls below an earnings link started from its 2029-30 level. It keeps the 2.5% floor and the long-run earnings link, and drops the ratchet. A second reading, with the earnings path restored only at five-yearly reviews, is reported as a policy-definition sensitivity.
- **Double lock**: the higher of CPI and earnings.
- **Earnings link** and **CPI link**.

## What it reports

- **Budget impact**: the saving to the government from each rule, gross (State Pension spending) and net of Pension Credit, Housing Benefit, other benefits and income tax, on the central path. That path is published inputs for April 2027 (May–July 2026 AWE, August 2026 CPI), the OBR's March 2026 forecast to 2030, and PolicyEngine's long-run path for 2031–33.
- **Who's affected**: the change in household net income by income quintile, region, household type, tenure and age.
- **Uncertainty**: a block bootstrap of the OBR's past forecast errors for CPI and earnings, with the historical gaps to the statutory inputs (September CPI, May–July AWE), and a VAR cross-check. It gives a range for the gross State Pension cost. Net and household figures are central-path only. Backtests on past forecasts show the ranges are too narrow to read as probabilities.
- **Trajectories**: the Burnham plan against the triple lock on a few macro paths and on past years, every figure a full PolicyEngine UK run with the path applied to the whole model. The paths come from a monthly time-series model of the statutory inputs, backtested against the other methods. See `docs/TRAJECTORIES.md`.
- **Methodology**: the method, equations, limitations, backtests and sources.

The triple lock applies to the basic and new State Pension only. The additional State Pension is held at its baseline (CPI-linked) value in every scenario.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -e ".[uk,dev]"
.venv/bin/triple-lock-build        # needs the Enhanced FRS (data/enhanced_frs_2024_25.h5, private)
.venv/bin/python -m pytest -q

cd dashboard && bun install && bun run dev   # http://localhost:3000/uk/triple-lock
```

The pipeline writes `data/triple_lock_results.json` and the dashboard's copy. `docs/RESULTS_SCHEMA.md` describes the file, and `docs/sources.md` the data sources. The model is pinned through `policyengine==5.3.0` (policyengine-uk 2.90.2).
