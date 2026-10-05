# The model-v2 rebuild: runbook

The one full rebuild of `data/results.json`, its dashboard copy and `data/scenarios/*.json` on model-v2 (#14 section 5): parts A, B and C integrated, every figure a full PolicyEngine UK run. Nothing here has been run as a whole. The integration pilot ran pieces of it (below), and this page says what the whole needs, in order, and what it waits for.

## What it waits for

| Gate | What it holds back | Until then |
|---|---|---|
| **d955**: how to present the saving, as no macro model passes C1's pre-registered screen (`docs/UNCERTAINTY_PILOT.md`) | The expected-value section: the headline expected saving, its SEs, the dynamics range, the mean-path sensitivity and the Microcosm paired difference. `expected_value.build(run=True)` refuses, by design (C1's gate). It refuses a form that failed the screen, and it refuses the legacy 200-slot design even for a form that passed. | `triple-lock-build` stops at the expected-value stage. Everything before it (central, coverage) is cached and kept. |
| **d833**: the uk-data fixes land as **one** data release on Max's go | The dataset: Pension Credit take-up fill and capital (#510, #513), pension-age Housing Benefit calibration (#490), and with them the Pension Credit and Housing Benefit offsets | The pin stays at Enhanced FRS 1.56.16, and the coverage rows keep showing the gaps to DWP (Pension Credit claims about +30%, pension-age Housing Benefit about +70%). |
| **d778**: a policyengine.py release that certifies the policyengine-uk pin with that data | `provenance.model.certified` | Every run records `certified: false` and why (`datasets.UNCERTIFIED`). This doesn't block the build. |

So the rebuild can start once d955 is decided and its expected-value adapter is in. d833 decides which data it runs on. d778 only changes a provenance flag.

## Inputs to update first

Each is a commit before the build. The build refuses a dirty tree, and every input file is hashed into provenance.

1. **September 2026 CPI** (ONS D7G7, published 21 October 2026). It sets the April 2027 uprating, and the additional pension's and the Pension Credit guarantee's next rise.
   - Update `data/raw/ons_d7g7_cpi_annual_rate.csv` and `data/raw/ons_d7bt_cpi_index.csv` (the monthly index the models read).
   - Set `config.CPI_PERIOD = "2026 SEP"`.
   - April 2027 is then the larger of September CPI and the published May–July AWE (`config.AWE_PERIOD`, already final).
2. **The post-Budget OBR means** (Autumn Budget, expected 28 October 2026: the November Economic and Fiscal Outlook and its long-term determinants).
   - Update `data/obr_central_forecast.csv`: the EFO's calendar-year CPI and earnings and their fan-chart deciles, and the long-term determinants' fiscal-year CPI, earnings and triple-lock rows (`fiscal_year_lted`), which also set the OBR wedge (`trajectories.obr_premium_spec`). The expected value's draws are shifted to the new calendar means.
   - If the Budget is later than the date the rebuild must run, record that the March 2026 means were used. Don't mix vintages.
3. **The uncertainty screen on those inputs.** Re-run C1's frozen screen first (`python -m triple_lock.ts_uncertainty --output out/uncertainty`, see `docs/UNCERTAINTY_PILOT.md`), then apply d955's ruling:
   - **(a)** A scenario envelope: no expected-value section. This needs pipeline and dashboard work to drop it.
   - **(b)** The current model, labelled as model-conditional and failing the backtest.
   - **(c)** A new pre-registered screen.

   Any ruling that keeps an expected value needs the C1 adapter. It runs the passing form's 160-slot design (161 unique full runs with the identical-rates check) and, only if the original primary passes, its paired ±0.5-point earnings mean paths (161 each). It replaces the disabled 200-slot route in `expected_value.build`.
4. **Versions** (live check on the day):
   - `pip index versions policyengine-uk` and `policyengine-core`.
   - Move to a newer release only if every change since the pin is a bug fix. If one changes methodology, stay and record it.
   - On a move: update `pyproject.toml` and `requirements-lock.txt`, re-hash the guarded files (`model_horizon.UPSTREAM`; `check_upstream()` names the ones that changed, to read before re-hashing), and rerun the version bridge (part A's pilot, below).
   - policyengine-core 3.32.17 (5 October 2026: uprating and cloned-storage fixes) is not yet taken.
5. **The dataset** (d833).
   - For a new release, add its pin to `datasets.DATASETS`: revision, SHA-256, `built_with`, and `ageing_anchor` read from that release's `frs_release.py` (`calibration_year`). Then set `config.PRIMARY_DATASET`.
   - Run the coverage job on it first, and the gross-to-net and accounting checks, which fail a run on their own.
   - Check whether policyengine-uk-data#538 (the calibration-year weight level) is fixed in that release.

## Commands

From a clean checkout of the merged branch, with the locked environment:

```sh
uv venv .venv && uv pip install -r requirements-lock.txt && uv pip install --no-deps -e .
export HUGGING_FACE_TOKEN=...            # the datasets are private; the store is .cache/datasets
python -c "import psutil; m = psutil.virtual_memory(); print(m.available / 2**30, 'GiB free')"   # see Memory

# 1. Check the inputs before anything long.
python -m pytest -q                      # only the three stale-results tests may fail (below)
python scripts/validate_ageing.py --plan # 210 jobs: the paired draws come from data/results.json

# 2. The build (results file, dashboard copy and every scenario).
triple-lock-build --workers 4 --sensitivity-workers 2

# 3. The four-way ageing design on the rebuilt file's paired draws (aggregates only, into .cache).
python scripts/validate_ageing.py --workers 4 -o .cache/ageing_validation.json

# 4. Check the file before committing it.
python scripts/check_assumptions.py data/results.json
python -m pytest -q                      # now nothing may fail
cd dashboard && bun install && bun run test && bun run lint && bun run build
```

`triple-lock-build` caches every job (`.cache/jobs`). An interrupted build resumes where it stopped, and the job key changes only with what a job computes. Step 3's `both` runs share the build's cache entries, so it adds only the other treatments.

## Jobs, memory and time

Job counts as the code stands. The expected value depends on d955: the C1 adapter's 161 unique runs, plus 322 if the original primary passes and its mean paths run.

| Stage | Enhanced FRS jobs | Microcosm jobs |
|---|---|---|
| Central path | 1 | – |
| Coverage | 1 | 1 |
| Expected value (C1 design) | 161 (+322 mean paths) | 40 (the paired subsample) |
| Trajectories: four future paths and four past-year cases | 8 | – |
| Scenario (OBR wedge) | 1 | – |
| **Build** | **172** (494) | **41** |
| Four-way design (step 3): the other four treatments of central and 40 paired draws, and five coverage jobs | 169 | – |

Memory, measured in the integration pilot on policyengine-uk 2.120.0:

- an Enhanced FRS path job peaks at about 6 GB under the model-v2 treatment;
- a Microcosm job needs about 32 GB (31.8 GB measured on 2.118.0);
- the CLI's defaults are 3 and 2 workers. Never run more than two Microcosm processes.

Check free RAM before starting. In every stage the build runs its Microcosm jobs after its Enhanced FRS jobs, so the peak is two Microcosm processes, about 64 GB. The four-way design starts no Microcosm process.

Time, from the pilot's measured job times:

- an Enhanced FRS path job takes about 2.5 minutes of wall time with six running together;
- a Microcosm path job takes about 20 minutes.

| | Without mean paths | With mean paths |
|---|---|---|
| Enhanced FRS part of the build (4 workers) | about 2 hours | about 5 hours |
| Microcosm part (2 workers) | about 7 hours | about 7 hours |
| Four-way design (4 workers) | about 1.5 hours | about 1.5 hours |
| **Total** | **about 10 to 11 hours** | **about 13 to 14 hours** |

Both are within #14's estimate of 8 to 16 hours.

## What the rebuilt file must show (checked by the tests)

- `test_results.py::test_not_stale`, `test_scenarios.py::test_not_stale` and `test_method_text_percentiles_match_the_past_years_check` fail until the rebuild, and pass after it. They are the only tests allowed to fail before it.
- Every run's `fixed_inputs.population` is `{"weights": "ons_projection", "ages": "adjusted", "pension_types": "cohort"}`, and the assumptions strip is worded from it (`pipeline._population_item`).
- Every run passes, or it would have failed: the data-year State Pension identity (`fixed_inputs.state_pension_accounting`), the additional pension under both rules, the population readback, the ONS targets to 1e-6 (`fixed_inputs.ageing`), gross to net, path following, and the GB masks.
- The coverage rows set Great Britain against DWP to 2030-31, and State Pension by age is published or withheld whole.
- No single-record diagnostic, only `concentration_top10_by_year`. The dashboard shows the single-record panel as unavailable. Wording it from the ten-record measure is dashboard work, not part of this runbook.

## After the rebuild

- The paper's step 4 drops "which policyengine-uk requires" (#14).
- Refresh `data/scenarios/obr_premium.json` (the build does).
- Re-measure the Pension Credit and Housing Benefit offsets on the released data (d833), and the State Pension, Pension Credit and Housing Benefit bridge against the pilot (below).
- Watch the float32 model check in late years.

## The integration pilot this rests on

Part D ran pieces of this on the integrated branch (policyengine-uk 2.120.0, Enhanced FRS 1.56.16, the March 2026 OBR means). The figures are aggregates and are not committed; the pilot folder and the PR hold them.

- Part A's version bridge, rerun on 2.120.0: coverage, the central path, the OBR wedge and fourteen expected-value draws on 1.56.16, and the central path and coverage on 1.57.4.
- The central path and the 40 Microcosm-paired draws under `legacy` and `both`, and coverage under `both`.
- The central path on Microcosm under `legacy` and `both`.
