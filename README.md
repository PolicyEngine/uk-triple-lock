# The Burnham plan and the State Pension triple lock

**Dashboard: https://uk-triple-lock.vercel.app/uk/triple-lock**

PolicyEngine UK analysis of the Prime Minister's plan to adjust the triple lock from April 2030, 2027-28 to 2039-40. Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled from another run.

In his speech to Labour's conference on 29 September 2026, Andy Burnham said he would keep the triple lock until 2030 and then "adjust" it: the State Pension would rise every year with prices or 2.5%, and "it will hold its value relative to earnings over time" (as the [BBC live page](https://www.bbc.co.uk/news/live/c6x2zrv774gvt?post=asset%3A7a078b64-1a5e-4ab2-995f-6afcb5daae5d#post) quotes him; `docs/sources.md` lists the posts). DWP's [State Pension uprating analysis](https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating) the same day describes it: from April 2030 the pension keeps "that record high value relative to earnings", rising "at least inflation or 2.5% – and anything more that is needed to retain that value". We read inflation as September CPI, earnings as May–July earnings and the record value as the 2029-30 level. Both rules here follow the triple lock to April 2029.

## What it reports

The dashboard builds up in steps:

1. **The triple lock**: September CPI, May–July earnings and 2.5% for each April since 2011, which one set the rise, and what the ratchet adds up to; the Burnham plan's rule, and what it would have paid had it started earlier.
2. **The OBR's central forecast**: the OBR's March 2026 forecast to 2030 and its long-term determinants after, through both rules.
3. **Another path**: a random path, and the middle and 90th-percentile paths, from a monthly model of prices and earnings whose calendar-year averages match the OBR forecast.
4. **One pensioner**: example pensioners under both rules on a path, with their income tax, Pension Credit, Housing Benefit, council tax reduction and Winter Fuel Payment.
5. **Everyone**: the full microsimulation on a path: gross and net saving, the account from one to the other, who loses, and poverty.
6. **Every path**: the expected saving, a weighted mean over a stratified sample of about 200 full runs (Enhanced FRS) with its Monte Carlo standard error; a paired subsample of about 40 of those paths on Microcosm as a dataset sensitivity; calibration sensitivities; DWP's £15bn and other published costings.

The Method tab has the engine's checks, the expected-value backtest, the forecast-distribution backtest, the datasets against DWP's spending and caseloads, and the limitations. `docs/METHOD.md` describes the method; `docs/RESULTS_SCHEMA.md` the results file; `docs/sources.md` the data.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-lock.txt   # the versions the results were built with
uv pip install --python .venv/bin/python --no-deps -e .
HUGGING_FACE_TOKEN=... .venv/bin/triple-lock-build   # the certified Enhanced FRS and Microcosm, via policyengine.py
HUGGING_FACE_TOKEN=... .venv/bin/triple-lock-build --scenario obr_premium   # one scenario run, to data/scenarios/
.venv/bin/python -m pytest -q

cd dashboard && bun install && bun run test && bun run dev
```

The build writes `data/results.json` and the dashboard's copy. Each model job runs in its own process and is cached in `.cache/jobs` under a hash of its inputs, what the engine's code computes (its syntax tree, so comments and docstrings don't count) and the package versions. An interrupted build resumes, and a change outside the engine, or to its prose, reruns nothing it has; the results file records the files' raw hashes, so it still needs rebuilding (from the cache) after any edit. So does every scenario run in `data/scenarios`: rerun each one (`--scenario NAME`, about 40 seconds) with every full rebuild, and `tests/test_scenarios.py` fails until you do. Stopping a build (Ctrl-C, SIGTERM or SIGHUP) stops its model processes, and a model process whose build is killed outright stops itself. The full build is about 250 model runs: roughly an hour and a half for the Enhanced FRS on three workers and three hours for the Microcosm subsample on two. The model is pinned through `policyengine==5.3.0` (policyengine-uk 2.90.2). Each Microcosm process needs about 35 GB of memory (`--sensitivity-workers` sets how many run at once; default 2). Run one build at a time: builds share the worker directories under `.cache/workers`.

Where policyengine-uk 2.90.2 departs from current law in ways that matter here, the engine sets the law under both rules (docs/METHOD.md): the State Pension age of 67 from 2028-29, the earnings-linked Pension Credit guarantee and the CPI-linked additional State Pension.
