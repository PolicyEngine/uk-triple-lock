# The Burnham plan and the State Pension triple lock

**Dashboard: https://uk-triple-lock.vercel.app/uk/triple-lock**

PolicyEngine UK analysis of the Prime Minister's plan to adjust the triple lock from April 2030, 2027-28 to 2039-40. Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled from another run.

In his speech to Labour's conference on 29 September 2026, Andy Burnham said the triple lock will stay for this Parliament and that, from April 2030, the State Pension will "continue to rise every year at least by prices or 2.5%" and "hold its value relative to earnings over time" ([BBC](https://www.bbc.co.uk/news/live/c6x2zrv774gvt)). DWP's [State Pension uprating analysis](https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating) the same day defines it: the pension keeps its 2029-30 value relative to earnings, rising "at least inflation or 2.5% – and anything more that is needed to retain that value". Both rules here follow the triple lock to April 2029.

## What it reports

The dashboard builds up in steps:

1. **The triple lock**: September CPI, May–July earnings and 2.5% for each April since 2011, which one set the rise, and what the ratchet adds up to; the Burnham plan's rule, and what it would have paid had it started earlier.
2. **The OBR's central forecast**: the OBR's March 2026 forecast to 2030 and its long-term determinants after, through both rules.
3. **Another path**: a random path, and the middle and 90th-percentile paths, from a monthly model of prices and earnings whose paths average out to the OBR forecast.
4. **One pensioner**: example pensioners under both rules on a path, with their income tax, Pension Credit, Housing Benefit and council tax reduction.
5. **Everyone**: the full microsimulation on a path: gross and net saving, the account from one to the other, who loses, and poverty.
6. **Every path**: the expected saving, a weighted mean over a stratified sample of about 200 full runs (Enhanced FRS) with its Monte Carlo standard error; the same paths on Microcosm as a paired dataset sensitivity; calibration sensitivities; DWP's £15bn and other published costings.

The Method tab has the engine's checks, the expected-value backtest, the forecast-distribution backtest, the datasets against DWP's spending and caseloads, and the limitations. `docs/METHOD.md` describes the method; `docs/RESULTS_SCHEMA.md` the results file; `docs/sources.md` the data.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -e ".[uk,dev]"
HUGGING_FACE_TOKEN=... .venv/bin/triple-lock-build   # the certified Enhanced FRS and Microcosm, via policyengine.py
.venv/bin/python -m pytest -q

cd dashboard && bun install && bun run test && bun run dev
```

The build writes `data/results.json` and the dashboard's copy. Each model job runs in its own process and is cached in `.cache/jobs` under a hash of its inputs, the engine's source and the package versions, so an interrupted build resumes and a change outside the engine reruns nothing it has. The full build is about 250 model runs: roughly an hour and a half for the Enhanced FRS on three workers and three hours for the Microcosm subsample on two. The model is pinned through `policyengine==5.3.0` (policyengine-uk 2.90.2).
