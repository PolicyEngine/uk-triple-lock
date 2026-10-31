# The government's adjusted Triple Lock and the State Pension triple lock

**Dashboard: https://policyengine.org/uk/triple-lock**

PolicyEngine UK analysis of the government's adjusted Triple Lock, which replaces the triple lock from April 2030, 2027-28 to 2039-40. Every fiscal and household figure is a full PolicyEngine UK run; nothing is scaled from another run.

In his speech to Labour's conference on 29 September 2026, Andy Burnham said he would keep the triple lock until 2030 and then "adjust" it: the State Pension would rise every year with prices or 2.5%, and "it will hold its value relative to earnings over time" (as the [BBC live page](https://www.bbc.co.uk/news/live/c6x2zrv774gvt?post=asset%3A7a078b64-1a5e-4ab2-995f-6afcb5daae5d#post) quotes him; `docs/sources.md` lists the posts). DWP's [State Pension uprating analysis](https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating) the same day describes it: from April 2030 the pension keeps "that record high value relative to earnings", rising "at least inflation or 2.5% – and anything more that is needed to retain that value". We read inflation as September CPI, earnings as May–July earnings and the record value as the 2029-30 level. Both rules here follow the triple lock to April 2029. The [Budget](https://www.gov.uk/government/publications/budget-2026-document/budget-2026-html) on 28 October 2026 adopted the rule as the government's adjusted Triple Lock (paragraph 5.23 and Box 5.A): from April 2030 the State Pension rises "by the highest of 2.5%, inflation, or the amount required to maintain its value relative to earnings as reached in April 2029". Earlier releases here called it the Burnham plan; the results keep its id, `burnham_2030`.

## The post-Budget release (October 2026)

This is the binding release on the 28 October 2026 Budget's inputs. It shows **scenarios only, with no expected value**: the forecast model failed its registered test on past OBR forecasts, and the registered rule (ruling (c), with its automatic fallback to (a)) then drops the expected value and keeps the scenarios. Scored on 7 OBR forecasts, one a year from March 2016 to March 2022, the model expected earnings growth below 2.5% in 44.6% of the years tested, against 17.9% in practice: a bias of 0.267, beyond the limit of 0.25. That is the only check it failed; the outcome fell inside its range in 5 of 7 final years and 83% of annual checks. The central path follows the OBR's October 2026 forecast to 2030 (and the April 2031 rise), then its March 2026 long-term determinants, which the OBR says are not a forecast.

Later releases follow a [second registered rule, C3](docs/METHOD.md#forward-publication-rule-and-prospective-test-pre-registration-c3). They publish the model's average as a labelled model-conditional sensitivity, and a new test on outcomes nobody has yet seen decides only whether it may be called an estimate. That test can give no verdict before October 2034, because fewer years cannot separate a correct model from a wrong one. This release stays scenarios only.

What the adjusted Triple Lock saves against the triple lock in 2039-40 (Microcosm, cash terms, UK), on four scenarios that form a scenario envelope, not a probability interval:

| Scenario | Gross | Net of tax and benefits |
| --- | --- | --- |
| OBR central forecast | £0.5bn | £0.3bn |
| OBR long-term path (the triple lock pays 0.6 points above earnings from April 2032) | £10.9bn | £7.3bn |
| Earnings −0.5 points from 2031, average of 160 simulated draws | £11.4bn ± £0.5bn | £7.8bn ± £0.3bn |
| Earnings +0.5 points from 2031, average of 160 simulated draws | £11.9bn ± £0.5bn | £8.1bn ± £0.3bn |

The ± is the 95% Monte Carlo error. Prices and earnings swap the lead on the simulated paths, which is when the adjusted Triple Lock saves, so those paths save far more than the smooth central path.

**Data.** The figures use the certified bundle released in **policyengine.py 6.11.1** (policyengine-uk 2.151.0, policyengine-core 3.33.3): Microcosm's national cut `microcosm-uk-2024-25-national-20261025T091414Z-a6299504` as primary, with its local-area cut for constituency and local-authority runs. Without an expected value the build runs no paired sensitivity, so Enhanced FRS 1.58.2 runs only for the coverage check. Separate model and data bridge steps measure the move from the pre-Budget bundle; see [REBUILD.md](docs/REBUILD.md). This release replaces the provisional pre-Budget release of October 2026, on Enhanced FRS 1.58.0, and the expected saving it gave.

## What the dashboard shows

Five tabs, in order:

1. **Budget impact**: what the adjusted Triple Lock saves on each scenario, and how that compares with DWP's £15bn and other published costings.
2. **How the triple lock works**: what set each April's rise since 2011, how the rises add up, and what the adjusted Triple Lock would have paid had it started earlier.
3. **Forecast paths**: both rules on one path, by default the OBR central forecast, or one of three simulated model paths.
4. **Distributional impact**: the full microsimulation on a path (gross and net saving, households worse off, poverty, change by income decile and other groups) and four example pensioners.
5. **Methodology**: how we model it, what we use, our assumptions and the limitations.

`docs/METHOD.md` describes the method; `docs/RESULTS_SCHEMA.md` the results file; `docs/sources.md` the data.

## Reproduce

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-lock.txt   # the versions the results were built with
uv pip install --python .venv/bin/python --no-deps -e .
# fetches the pinned Enhanced FRS and Microcosm into .cache/datasets
.venv/bin/python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2
HUGGING_FACE_TOKEN=... .venv/bin/triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2
.venv/bin/python -m pytest -q

cd dashboard && bun install && bun run test && bun run dev
```

The build writes `data/results.json`, the dashboard's copy and every scenario run in `data/scenarios`. Each model job runs in its own process and is cached in `.cache/jobs` under a hash of its inputs, the engine's code and the package versions, so an interrupted build resumes; the results file records the files' raw hashes, so it needs rebuilding (from the cache) after any edit. A cold binding build is about 490 full runs, about a day on one machine with one worker. Run one build at a time: builds share the worker directories under `.cache/workers`. Job counts, memory limits, the binding post-Budget sequence and the certification checks are in [docs/REBUILD.md](docs/REBUILD.md).

Where policyengine-uk departs from current law in ways that matter here, the engine sets the law under both rules (docs/METHOD.md): the earnings-linked Pension Credit guarantee and the CPI-linked additional State Pension. The survey population is aged statically: ONS-projection weights after the data's calibration year, each record's age retained, and State Pension types by birth cohort, the same under both rules.
