# The Burnham plan and the State Pension triple lock

**Dashboard: https://policyengine.org/uk/triple-lock**

PolicyEngine UK analysis of the Prime Minister's plan to adjust the triple lock from April 2030, 2027-28 to 2039-40. Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled from another run.

In his speech to Labour's conference on 29 September 2026, Andy Burnham said he would keep the triple lock until 2030 and then "adjust" it: the State Pension would rise every year with prices or 2.5%, and "it will hold its value relative to earnings over time" (as the [BBC live page](https://www.bbc.co.uk/news/live/c6x2zrv774gvt?post=asset%3A7a078b64-1a5e-4ab2-995f-6afcb5daae5d#post) quotes him; `docs/sources.md` lists the posts). DWP's [State Pension uprating analysis](https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating) the same day describes it: from April 2030 the pension keeps "that record high value relative to earnings", rising "at least inflation or 2.5% – and anything more that is needed to retain that value". We read inflation as September CPI, earnings as May–July earnings and the record value as the 2029-30 level. Both rules here follow the triple lock to April 2029.

## The pre-Budget release (October 2026)

This is a **provisional, model-conditional** release ahead of the 28 October 2026 Budget, under the recorded uncertainty ruling (c). The forecast model passes its test on past OBR forecasts in a dry run on today's inputs (4 of 6 final years and 80% of annual checks inside its range); the binding test runs on the Budget's inputs, and a new release follows. Inputs are the OBR's March 2026 forecast, with August 2026 CPI standing in for September's for April 2027.

Headline, 2039-40 (Enhanced FRS, cash terms, UK): a **provisional, model-conditional expected saving of £11.1bn gross and £7.9bn net of tax and benefits**, the probability-weighted average over 50,000 simulated paths of prices and earnings centred on the OBR's forecast, estimated from 160 full runs (Monte Carlo error about ±£0.1bn).

**Data.** The published figures use the certified bundle, **policyengine.py 6.2.6** (policyengine-uk 2.125.1, policyengine-core 3.33.0) with **Enhanced FRS 1.58.0**. The same 40 paths are also run on **Microcosm's UK release** (`microcosm_uk_2024_25`, tag `microcosm-uk-2024-25-national-20261002T230158Z-5c6b3f68`, uncertified under this bundle) as a paired cross-check: Microcosm minus Enhanced FRS is +£1.12bn gross and +£0.49bn net in 2039-40. The cross-check is in `data/results.json` but not on the dashboard. This is the historical pre-Budget bundle. The binding rebuild will use d2011's pair, released in **policyengine.py 6.11.1** (policyengine-uk 2.151.0, policyengine-core 3.33.3): Microcosm's national cut `microcosm-uk-2024-25-national-20261025T091414Z-a6299504` as primary, with its local-area cut for constituency and local-authority runs, and **Enhanced FRS 1.58.2** as the paired sensitivity. Separate model and data bridge steps run before coverage and the fiscal run; see [REBUILD.md](docs/REBUILD.md).

## What the dashboard shows

Five tabs, in order:

1. **Budget impact**: the expected saving and its spread across paths, the saving each year, and how it compares with fixed scenarios, DWP's £15bn and other published costings.
2. **How the triple lock works**: what set each April's rise since 2011, how the rises add up, and what the Burnham plan would have paid had it started earlier.
3. **Forecast paths**: both rules on one path, by default the OBR central forecast, or a simulated example, typical (median) or high-saving (90th percentile) path.
4. **Distributional impact**: the full microsimulation on a path (gross and net saving, households worse off, poverty, change by income decile and other groups) and four example pensioners.
5. **Methodology**: how we model it, what we use, our assumptions and the limitations.

`docs/METHOD.md` describes the method; `docs/RESULTS_SCHEMA.md` the results file; `docs/sources.md` the data.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-lock.txt   # the versions the results were built with
uv pip install --python .venv/bin/python --no-deps -e .
# fetches the pinned Enhanced FRS and Microcosm into .cache/datasets
HUGGING_FACE_TOKEN=... .venv/bin/triple-lock-build --pre-budget --uncertainty-ruling c --workers 2 --sensitivity-workers 1
.venv/bin/python -m pytest -q

cd dashboard && bun install && bun run test && bun run dev
```

The build writes `data/results.json`, the dashboard's copy and every scenario run in `data/scenarios`. Each model job runs in its own process and is cached in `.cache/jobs` under a hash of its inputs, the engine's code and the package versions, so an interrupted build resumes; the results file records the files' raw hashes, so it needs rebuilding (from the cache) after any edit. A cold pre-Budget build is about 535 full runs, several hours on one machine with two workers. Run one build at a time: builds share the worker directories under `.cache/workers`. Job counts, memory limits, the binding post-Budget sequence and the certification checks are in [docs/REBUILD.md](docs/REBUILD.md).

Where policyengine-uk departs from current law in ways that matter here, the engine sets the law under both rules (docs/METHOD.md): the earnings-linked Pension Credit guarantee and the CPI-linked additional State Pension. The survey population is aged statically: ONS-projection weights after the data's calibration year, ages above the survey's top code of 80 spread using ONS single-age shares, and State Pension types by birth cohort, the same under both rules.

The live quoted sensitivity range uses only reweightings with `included_in_quoted_range: true` (at least 100 effective runs): **£8.3–12.4bn gross (£5.9–8.8bn net)** in 2039-40. Six more reweightings are excluded. Historical results bytes and their provenance are retained until the binding rebuild; REBUILD documents the exact expected stale-results assertions.
