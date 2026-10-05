# The model-v2 rebuild: runbook

The one full rebuild of `data/results.json`, its dashboard copy and `data/scenarios/*.json` on model-v2 (#14 section 5): parts A, B and C integrated, every figure a full PolicyEngine UK run. Nothing here has been run as a whole. The integration pilot ran pieces of it (below), and this page says what the whole needs, in order, and what it waits for.

## What it waits for

| Gate | What it holds back | Until then |
|---|---|---|
| **d955**: how to present the saving, as no macro model passes C1's pre-registered screen (`docs/UNCERTAINTY_PILOT.md`) | Expected-value presentation and execution require an explicit recorded `--uncertainty-ruling a|b|c`. With no ruling, `expected_value.build(run=True)` refuses and names d955. Mean-path scenarios can run independently of adequacy, with presentation pending d955. | `triple-lock-build` refuses a missing ruling at entry, before central or coverage jobs start. Standalone mean-path scenarios remain runnable, with presentation pending d955. |
| **d833**: the uk-data fixes land as **one** data release on Max's go | The dataset: Pension Credit take-up fill and capital (#510, #513), pension-age Housing Benefit calibration (#490), and with them the Pension Credit and Housing Benefit offsets | The pin stays at Enhanced FRS 1.56.16, and the coverage rows keep showing the gaps to DWP (historical part D Pension Credit claims +30–63%, pension-age Housing Benefit +71–86%; see the committed pilot coverage table, pending its support audit). |
| **d778**: a policyengine.py release that certifies the policyengine-uk pin with that data | `provenance.model.certified` | Every run records `certified: false` and why (`datasets.UNCERTIFIED`). This doesn't block the build. |

The adapter is implemented. The full rebuild requires Max's d955 ruling; passing the flag records that ruling and does not make the decision for him. d833 decides which data it runs on. d778 only changes a provenance flag.

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
   - **(a)** `--uncertainty-ruling a`: skip the expected-value stage and omit its section from results; the dashboard shows the central figure and paired scenarios.
   - **(b)** `--uncertainty-ruling b`: run the original primary, explicitly labelled model-conditional, with its frozen-screen failure retained.
   - **(c)** `--uncertainty-ruling c`: rerun the screen using the suspended April 2022 treatment only; run its selected form only if it passes. The recorded ruling is the input authorizing this changed screen, not a retrospective claim that C1 passed.

   The adapter consumes `ts_uncertainty`'s chosen-form 160-slot design (161 unique original-primary full runs including its identical-rates check on the committed inputs). Counts for updated or alternative designs follow their saved distinct indices; replacement sampling can repeat a draw. It also runs an exact 40-slot Microcosm-paired subsample. The original-primary ±0.5-point mean paths are scenarios and run independently of C1 adequacy. Each uses the same primary indices, innovations and zero-stratum mass; its extra baseline check may save nonzero. The original-primary baseline is reused under (b), or separately run under (a) and when (c) chooses another form.
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

From a clean checkout of the approved `model-v2` head, with the locked environment; PR #24 remains a draft until its separate decisions and review are complete:

```sh
uv venv .venv && uv pip install -r requirements-lock.txt && uv pip install --no-deps -e .
export HUGGING_FACE_TOKEN=...            # the datasets are private; the store is .cache/datasets
python -c "import psutil; m = psutil.virtual_memory(); print(m.available / 2**30, 'GiB free')"   # see Memory

# 1. Check the inputs before anything long.
python -m pytest -q                      # only the three stale-results tests may fail (below)

# 2. The build (results file, dashboard copy and every scenario).
triple-lock-build --workers 3 --sensitivity-workers 2 --uncertainty-ruling <a|b|c>

# Standalone mean-path scenarios, with no adequacy gate:
triple-lock-build --mean-path-scenarios --workers 3 --out .cache/mean-path-scenarios.json
# Add --uncertainty-ruling only after Max records d955; otherwise presentation stays pending.

# 3. The four-way ageing design, on the rebuilt file's paired draws (aggregates only, into .cache; see below).
python scripts/validate_ageing.py --plan
python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json
#    With no expected-value section (d955's scenario envelope), the central path alone:
python scripts/validate_ageing.py --central-only --workers 3 -o .cache/ageing_validation.json

# 4. Check the file before committing it.
python scripts/check_assumptions.py data/results.json
python -m pytest -q                      # now nothing may fail
cd dashboard && bun install && bun run test && bun run lint && bun run build
```

`triple-lock-build` caches every job (`.cache/jobs`). An interrupted build resumes where it stopped, and the job key changes only with what a job computes.

Step 3 reads its paired draws from the file it is pointed at (`data/results.json` by default) and rebuilds each draw from the central path, failing if a draw no longer reproduces the inputs the file records. So it runs after the build, on the rebuilt file. Run on the committed file once the inputs have changed, it fails, by design. It needs the rebuilt expected value to record a Microcosm-paired subsample as the committed file does: per path, `times_drawn_sensitivity`; per stratum, `sensitivity_paths` and `probability`; and the draws' `n`, `seed` and `shocks`. The C1 adapter writes those, plus the selected `draws.form`; step 3 reconstructs that form rather than assuming VAR(1). The C1 original-primary design includes stratum zero explicitly, so its mass is counted once. The validation now has six modes: `legacy`, `frozen`, `reweight`, `types`, `both`, and the `total` population-only control. Its `both` path runs share the build's cache entries (`ageing_validation.canonical`), so it adds the other five modes' central and 40 paired path runs (205) and six coverage jobs, whose years differ from the build's. The four-way factorial remains frozen/reweight/types/both; legacy and total are controls.

## Jobs, memory and time

Counts below use the committed original-primary design: 160 sample slots and one extra zero check, all distinct. Mean-path scenarios do not wait for a passing screen. Under (a), skip the expected value and its 40 Microcosm jobs but run the 483 original-primary scenario jobs (baseline plus two variants). Under (b), reuse that baseline as the expected-value run. Under (c), a different selected passing form adds its own saved unique-run count beside those 483 scenario jobs.

| Stage | Enhanced FRS jobs | Microcosm jobs |
|---|---|---|
| Central path | 1 | – |
| Coverage | 1 | 1 |
| Expected value (b, original C1 design) | 161 | 40 (the paired subsample) |
| Paired mean-path scenarios (independent of adequacy) | 322 (plus 161 baseline under a or nonprimary c) | – |
| Trajectories: four future paths and four past-year cases | 8 | – |
| Scenario (OBR wedge) | 1 | – |
| **Build under b** | **494** | **41** |
| **Build under a** | **494** | **1** |
| Four-way factorial plus controls (step 3): the other five modes of central and 40 paired draws (205), and six coverage jobs | 211 | – |
| Step 3 under a, central only: five other central paths plus six coverage jobs | 11 | – |

The validation's complete design has 252 labels (246 path runs and six coverage jobs); 211 above is the additional work after reusing the build's 41 `both` paths. Repeated indices can further reduce unique cache jobs. Its central-only design has twelve labels before reusing the central `both` path. The separate part E evidence pilot also has 252 full-run labels, with different treatments including the full-new bound; it executes 41 six-treatment Enhanced FRS batches and six coverage jobs (47 process jobs), capped at two batch workers. That optimization shares pristine setup only: every treatment and policy has independent inputs and parameters, with full-horizon calculations in their original order. It does not change ordinary build or Microcosm jobs.

The separately versioned matched-total evidence supplement adds 123 full path-run labels in 41 three-treatment batches (frozen/reweight/total_matched), without coverage jobs. Its one population target is the sum of the same age/sex anchored targets, so the age-structure contrast holds that target fixed; the original `total` still measures ONS aggregate growth. Both model-read populations must hit their shared target in every calculated year. Combining the supplement with E requires an exact aggregate reproduction of all 41 frozen and 41 reweight reference runs. The recipe never runs a missing reference job. Ordinary step-3 defaults/counts remain six modes; the additional control is opt-in.

Once those full jobs and proofs are complete, select stored aggregates into a reviewable table with:

```sh
python scripts/render_model_v2_e_tables.py --input data/pilot/model_v2_e.json \
  --matched-input data/pilot/model_v2_matched_total.json --output out/E-fiscal-tables.md
```

The renderer checks the reference proof, retains both calculation heads, and preserves linked suppression; it computes no mean, contrast or SE.

Memory, measured in the integration pilot on policyengine-uk 2.120.0:

- an Enhanced FRS path job peaks at about 6 GB under the model-v2 treatment;
- a Microcosm job needs about 32 GB (31.8 GB measured on 2.118.0);
- the CLI's defaults are 3 and 2 workers. Never run more than two Microcosm processes.

Check free RAM before starting. In every stage the build runs its Microcosm jobs after its Enhanced FRS jobs, so the peak is two Microcosm processes, about 64 GB. The four-way design starts no Microcosm process.

Historical planning times, from part D's measured job times; these have not been remeasured for the final-head ordinary build:

- part D measured about 2.5 minutes per Enhanced FRS path with six running together; this is a historical measurement, not authorization for more than three current workers;
- a Microcosm path job takes about 20 minutes.

| Historical planning estimate | Omitting mean paths | Including mean paths |
|---|---|---|
| Enhanced FRS part of the build (3 workers) | about 2 hours | about 5 hours |
| Microcosm part (2 workers) | about 7 hours | about 7 hours |
| Four-way design (3 workers) | about 1.5 hours | about 1.5 hours |
| **Total** | **about 10 to 11 hours** | **about 13 to 14 hours** |

These historical estimates were within #14's 8-to-16-hour allowance. The current full-build CLI includes the mean-path scenarios; the first column is historical planning context, not a CLI switch. Final-head runtime is unverified; measure it under the current worker/RAM limits before relying on that allowance.

## What the rebuilt file must show (checked by the tests)

- `test_results.py::test_not_stale`, `test_scenarios.py::test_not_stale` and `test_method_text_percentiles_match_the_past_years_check` fail until the rebuild, and pass after it. They are the only tests allowed to fail before it.
- Every run's `fixed_inputs.population` is `{"weights": "ons_projection", "ages": "adjusted", "pension_types": "cohort"}`, and the assumptions strip is worded from it (`pipeline._population_item`).
- Every run passes, or it would have failed: the data-year State Pension identity (`fixed_inputs.state_pension_accounting`), the additional pension under both rules, the population readback, the ONS targets to 1e-6 (`fixed_inputs.ageing`), gross to net, the independent government/household-income level and change identities, path following, and the GB masks.
- The coverage rows set Great Britain against DWP to 2030-31, and State Pension by age is published or withheld whole.
- No single-record diagnostic, only `concentration_top10_by_year`. The dashboard shows the single-record panel as unavailable. Wording it from the ten-record measure is dashboard work, not part of this runbook.

## After the rebuild

- The paper's step 4 drops "which policyengine-uk requires" (#14).
- Refresh `data/scenarios/obr_premium.json` (the build does).
- Re-measure the Pension Credit and Housing Benefit offsets on the released data (d833), and the State Pension, Pension Credit and Housing Benefit bridge against the pilot (below).
- Watch the float32 model check in late years.

## The integration pilot this rests on

Part D ran pieces of this on the integrated branch (policyengine-uk 2.120.0, Enhanced FRS 1.56.16, the March 2026 OBR means). Its aggregate version bridge, integrated savings and GB-versus-DWP coverage are committed in [data/pilot](../data/pilot/), with calculation-commit/model tags and review verdicts in [MODEL_V2_PILOT.md](MODEL_V2_PILOT.md). They are a pilot on an uncertified data/model pair, not for quoting. The retained part D programme support audit is pending: the saved summaries omit Pension Credit/Housing Benefit contributing-record counts, so archived-source support receipts are required before publication.

- Part A's version bridge, rerun on 2.120.0: coverage, the central path, the OBR wedge and fourteen expected-value draws on 1.56.16, and the central path and coverage on 1.57.4.
- The central path and the 40 Microcosm-paired draws under `legacy` and `both`, and coverage under `both`.
- The central path on Microcosm under `legacy` and `both`.
