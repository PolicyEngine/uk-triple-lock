# The model-v2 rebuild: runbook

The one full rebuild of `data/results.json`, its dashboard copy and `data/scenarios/*.json` on model-v2 (#14 section 5): parts A, B and C integrated, every figure a full PolicyEngine UK run. The complete binding build has not run. Part J adds a separate pre-Budget rehearsal on the certified bundle, whose receipts and measured status are linked below. The integration pilot ran pieces of it (below), and this page says what the whole needs, in order, and what it waits for.

## What it waits for

| Gate | What it holds back | Until then |
|---|---|---|
| **d955 = (c), decided by Max on 5 October**: C2 scores April 2022 with its earnings leg suspended and excludes cells fixed by law | The [C2 rule](METHOD.md#model-v2-statutory-uncertainty-screen-pre-registration-c2) was committed and pushed at `65343e2ee43a359f056ce5a027739509d32ab49f` before implementation or scoring. The binding re-score waits for the post-Budget inputs. Only the original primary may get an expected value; its failure automatically takes (a), scenarios only. | Use the recorded `--uncertainty-ruling c` with the C2 handoff under either outcome. With no ruling, execution refuses and names d955. Mean-path scenarios run independently of adequacy. Any expected value is labelled model-conditional and shown beside the scenario envelope. |
| **d833, released**: Enhanced FRS 1.58.0 | The released uk-data batch includes the Pension Credit and pension-age Housing Benefit fixes. | The historical 1.56.16 pilot remains unchanged and uncertified. Fresh certified coverage is recorded separately; calibration accuracy is assessed from those full runs. |
| **d778, certified and released**: policyengine 6.2.6 | UK 2.125.1, core 3.33.0 and Enhanced FRS 1.58.0, verified against the released wheel and immutable HF manifest. [Certification evidence](pilot/J-certification.md). | The bundle gate is satisfied. Binding C2 still waits for the post-Budget inputs. Microcosm remains an uncertified sensitivity. |

Max has selected d955(c). The adapter reads the frozen C2 handoff and records its screen, pre-registration SHA, C1 failure and C2 outcome. It refuses a handoff whose frozen-section content SHA-256 differs from the committed binding; calculation heads remain provenance only. A C2 pass never promotes another form or averages forms. The d833/d778 bundle gate is satisfied by the verified 6.2.6 release. The binding C2 input gate remains; the historical uncertified pilot is preserved separately.

## Inputs to update first

Each is a commit before the build. The build refuses a dirty tree, and every input file is hashed into provenance.

1. **September 2026 CPI** (ONS D7G7, published 21 October 2026). It supplies April 2027's CPI leg and additional State Pension uprating. Published May–July earnings supply the earnings leg and the Pension Credit guarantee's next rise, subject to its no-cut rule.
   - Update `data/raw/ons_d7g7_cpi_annual_rate.csv` and `data/raw/ons_d7bt_cpi_index.csv` (the monthly index the models read).
   - Update the April 2027 row in `data/triple_lock_actual_inputs.csv` with the actual September 2026 CPI and published May–July 2026 AWE. Keep CPI consistent with the raw September monthly index, and AWE consistent with the raw May, June and July 2026 levels in `data/raw/ons_kab9_awe_total_pay.csv`; the binding guard checks those matches.
   - Set `config.CPI_PERIOD = "2026 SEP"`.
   - April 2027 is then the larger of September CPI and the published May–July AWE (`config.AWE_PERIOD`, already final).
2. **The Budget-day OBR means** (28 October 2026 forecast and its long-term determinants).
   - Update `data/obr_central_forecast.csv`: the EFO's calendar-year CPI and earnings and their fan-chart deciles, and the long-term determinants' fiscal-year CPI, earnings and triple-lock rows (`fiscal_year_lted`), which also set the OBR wedge (`trajectories.obr_premium_spec`). The expected value's draws are shifted to the new calendar means. Refresh the `q3_yoy` CPI and `q2_yoy` earnings rows for 2026–2030 from that same dated Budget forecast; the binding guard checks those quarterly proxies too.
   - For each 2026–2030 calendar and quarterly CPI/earnings mean, record the official `https://obr.uk/` source URL and explicit OBR Budget/EFO date in its `source`, `note` or `source_date`: `28 October 2026`, `28 Oct 2026` or `2026-10-28`. The binding guard checks the release identity, finite means and committed source bytes.
   - Do not substitute the March 2026 means for the binding C2 score or mix vintages. If the Budget forecast is delayed, the binding score and rebuild wait for it.
   - Update `data/obr_forecast_errors.csv` and the statutory outturns so every forecast origin made complete by the new releases is included. In particular, the current March 2022 vintage has only horizons 1–3: add its fourth-horizon CPI and earnings **forecast means**. Those mean rows are needed for C2 even if their calendar outturn/error fields remain unavailable; do not invent an outturn or error. Eligibility still requires all four statutory target years to be observed.
3. **Binding C2 re-score after 28 October, on those committed inputs.** The binding input set is September 2026 CPI, published May–July 2026 AWE and the OBR's 28 October 2026 Budget means, plus every newly complete forecast origin. Score April 2022 as the law applied it, with earnings equal to CPI in forecast draws and outturns. Exclude statistic cells fixed by that legal rule; this removes four construction-zero annual gap cells in test A. Terminal paths retain the suspended year in their compounded arithmetic. Published-earnings scores stay beside every C2 result as a sensitivity and never decide the gate.
   - If the original monthly VAR(1) bootstrap primary passes, `--uncertainty-ruling c` runs it; label its expected value **model-conditional** beside the **scenario envelope**. Alternatives that pass are reported individually, with no promotion or averaging.
   - If that primary fails, the same `--uncertainty-ruling c` command automatically takes **(a)**: omit expected value, retain the scenario envelope and record the failure and fallback. There is no later method choice.
   - Run the same post-build Python and dashboard checks under either outcome. The result contracts read the frozen C2 scores and past-years check from `uncertainty_screen.c2_scores`, including the published sensitivity; they do not require legacy `expected_value.backtest` or `expected_value.past_years_check`. If the primary fails, they check the recorded omission reason and scenario envelope, and skip only assertions about an expected value that is intentionally absent. Synthetic dashboard fixtures exercise both outcomes on every tab.
   - The adapter retains **(b)** as an explicit tested input for the original primary with its frozen-screen failure retained. It is not Max's selected rebuild route.

   A run on today's inputs is explicitly a **dry run**, not the binding score and not permission for a fiscal expected value. The adapter consumes the original-primary 160-slot design (161 unique full runs including its identical-rates check on the committed inputs). Replacement sampling can repeat indices after an input update; use the handoff's saved distinct counts. A passing binding score adds the exact 40-slot Microcosm-paired subsample. The original-primary ±0.5-point mean paths run independently of adequacy, with the same primary indices, innovations and zero-stratum mass; their extra baseline check may save nonzero. The scenario envelope carries the central path, OBR wedge, recorded historical last-decade replay (April 2017–2026, with its own model years) and those paired mean paths under either outcome. The historical replay retains its period label and is not treated as a future-horizon simulation or included in a common future-year range.
4. **Versions** (live check on the day):
   - Install the committed exact lock. Verify `policyengine==6.2.6`, `policyengine-uk==2.125.1` and `policyengine-core==3.33.0` against [PyPI](https://pypi.org/project/policyengine/6.2.6/), plus the Enhanced FRS 1.58.0 manifest at HF commit `fdeba38517bd86067f34c0a5d8ed8923efb3b10a`. Its SHA-256 is `5ba399ea5ab9a6c7d4e9aaf6c623080beb34d9ad5f330f6244dbad72b8d960b6`.
   - Per d778, use `policyengine[uk]==6.2.6`, the certified release after the uk-data batch. Relevant model changes since the 2.120.0 pilot are listed in [the upstream audit](pilot/J-upstream.md). Do not silently upgrade the bundle on rebuild day; a changed bundle needs a new verification and bridge.
   - **Housing Benefit Guarantee Credit passport: hard precondition.** The certified d778 bundle must pin **policyengine-uk 2.123.6 or later**, including [policyengine-uk #1927](https://github.com/PolicyEngine/policyengine-uk/pull/1927) (merged 8 October 2026 at `bd13f3d1`). The pilot pin, 2.120.0, passports on Guarantee Credit entitlement instead of receipt and overstates the kept net saving on paths where Burnham creates that entitlement. The current bundle includes this correction. Preserve the historical pilot records at 2.120.0 / 1.56.16; do not relabel them certified.
   - Before starting model jobs, `pipeline.housing_benefit_passport_preflight` behaviourally tests the installed model on synthetic pension-age single people entitled to Guarantee Credit: the non-claimant must face the ordinary HB means test, while the Pension Credit claimant must receive maximum HB. It also reverses `in_receipt_of_guarantee_credit` to verify that all three passport branches actually read receipt. Both calculations must preserve positive Guarantee Credit entitlement and the Pension Credit claim pattern, with finite monetary values, Boolean regulation flags and HB between zero and rent. The same checks validate saved preflight provenance. A failure names the failed checks and #1927 and stops the rebuild; a pass records the observations in `provenance.preflight`. This guards the full build, standalone scenarios and both step 3 ageing entry points (`python scripts/validate_ageing.py` and `python -m triple_lock.ageing_validation`). Paired and central-only ageing reports retain the full check in `provenance.preflight`; `--plan` and `--help` start no jobs. Ordinary pilot tests do not require the old pin to pass the guard.
   - On a move: update `pyproject.toml` and `requirements-lock.txt`, re-hash the guarded files (`model_horizon.UPSTREAM`; `check_upstream()` names the ones that changed, to read before re-hashing), and rerun the version bridge (part A's pilot, below).
   - The installed certified core is 3.33.0. The model/core/engine-port intermediate bridge holds the data fixed; it does not isolate core effects from model or port effects.
5. **The dataset** (d833, released).
   - The primary is `enhanced_frs_2024_25@1.58.0`, pinned to the immutable manifest revision above and hashed on materialization. The build-time model/core were 2.122.2 / 3.32.13; the release explicitly certifies runtime 2.125.1 / 3.33.0. Calibration year remains 2025.
   - For a new release, add its pin to `datasets.DATASETS`: revision, SHA-256, `built_with`, and `ageing_anchor` read from that release's `frs_release.py` (`calibration_year`). Then set `config.PRIMARY_DATASET`.
   - Run the coverage job on it first, and the gross-to-net and accounting checks, which fail a run on their own.
   - Check whether policyengine-uk-data#538 (the calibration-year weight level) is fixed in that release.

## Commands

From a clean checkout of the approved `model-v2` head, with the locked environment; PR #24 remains a draft until its separate decisions and review are complete:

```sh
uv venv .venv
uv pip install -r requirements-lock.txt
uv pip install --no-deps -e .
source .venv/bin/activate
export HUGGING_FACE_TOKEN=$(agent-secret get HUGGING_FACE_TOKEN_MAX)
# Private dataset bytes stay in .cache/datasets.
python -c "import psutil; m = psutil.virtual_memory(); print(m.available / 2**30, 'GiB free')"   # see Memory

# 1. Check the inputs before anything long.
python -m pytest -q                      # only the three stale-results tests may fail (below)

# 2. After 28 October, with the binding macro inputs committed and the
#    certified d778 bundle installed after d833's uk-data batch.
#    Check #1927's receipt passport before scoring; real builds also run this guard.
python -c 'from triple_lock.pipeline import housing_benefit_passport_preflight; housing_benefit_passport_preflight()'
python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2

# The same build command handles both C2 outcomes:
# primary passes: model-conditional expected value and scenario envelope;
# primary fails: automatic (a), scenario envelope only, with recorded reason.
triple-lock-build --workers 3 --sensitivity-workers 2 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2

# Standalone mean-path scenarios, with no adequacy gate:
triple-lock-build --mean-path-scenarios --workers 3 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2 --out .cache/mean-path-scenarios.json

# 3. The four-way ageing design, on the rebuilt file's paired draws (aggregates only, into .cache; see below).
python scripts/validate_ageing.py --plan
python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json
#    If the primary failed C2 and the build has no expected-value section,
#    run this central-only command instead of the paired design above:
python scripts/validate_ageing.py --central-only --workers 3 -o .cache/ageing_validation.json

# 4. Check the file before committing it.
python scripts/check_assumptions.py data/results.json
python -m pytest -q                      # now nothing may fail
cd dashboard && bun install && bun run test && bun run lint && bun run build
```

For the pre-Budget **dry run** only (draws and scoring, zero PolicyEngine jobs):

```sh
python -m triple_lock.ts_uncertainty --screen c2 --output out/uncertainty-c2-dry-run
```

Omitting `--binding` labels the handoff and scores as a dry run. Do not use that handoff for the binding rebuild. Commit the updated macro/model/data inputs before the binding score; commit its resulting handoff and score provenance before the full build.

`triple-lock-build` caches every job (`.cache/jobs`). An interrupted build resumes where it stopped, and the job key changes only with what a job computes.

Step 3 reads its paired draws from the file it is pointed at (`data/results.json` by default) and rebuilds each draw from the central path, failing if a draw no longer reproduces the inputs the file records. So it runs after the build, on the rebuilt file. Run on the committed file once the inputs have changed, it fails, by design. A passing C2 build records the Microcosm-paired subsample: per path, `times_drawn_sensitivity`; per stratum, `sensitivity_paths` and `probability`; and `draws.n`, `seed`, `shocks` and `form`. The validation reconstructs that recorded form. The original-primary design includes stratum zero explicitly, so its mass is counted once. The validation has six modes: `legacy`, `frozen`, `reweight`, `types`, `both`, and the `total` population-only control. Its `both` path runs share the build's cache entries (`ageing_validation.canonical`), so today's design adds the other five modes' central and 40 paired path runs (205) and six coverage jobs, whose years differ from the build's. The four-way factorial remains frozen/reweight/types/both; legacy and total are controls. A failed-primary build has no paired expected-value subsample, so use `--central-only`.

## Jobs, memory and time

Counts below use the committed original-primary design: 160 sample slots and one extra zero check, all distinct. C2 scoring and its dry run start **zero PolicyEngine jobs**. Mean-path scenarios do not wait for a passing screen. A primary pass reuses the 161 baseline runs for the expected value and adds 40 Microcosm runs; a primary failure still runs the 483 original-primary scenario jobs (baseline and two variants), without expected value or those 40 Microcosm runs. C2 never substitutes an alternative primary.

| Stage | Enhanced FRS jobs | Microcosm jobs |
|---|---|---|
| Central path | 1 | – |
| Coverage | 1 | 1 |
| Original-primary baseline, reused for expected value only if primary passes C2 | 161 | 40 if primary passes; 0 if it fails |
| Paired mean-path scenarios (independent of adequacy) | 322 | – |
| Trajectories: four future paths and four past-year cases | 8 | – |
| Scenario (OBR wedge) | 1 | – |
| **Build under c, primary passes C2** | **494** | **41** |
| **Build under c, primary fails C2 → automatic a** | **494** | **1** |
| Step 3 after primary passes: five other modes of central and 40 paired draws (205), plus six coverage jobs | 211 | – |
| Step 3 after primary fails, central only: five other central paths plus six coverage jobs | 11 | – |

For updated inputs let `U` be the handoff's original-primary `unique_full_runs` (including the extra check), and `V` the distinct indices in its 40-slot Microcosm subsample. The build has `3U + 11` Enhanced FRS jobs under either outcome; it has `V + 1` Microcosm jobs if the primary passes, or one if it fails. Step 3 adds `5(1 + V) + 6` Enhanced FRS jobs after a pass, or 11 after a failure. The standalone mean-path command has `3U` Enhanced FRS jobs (483 today). These are cold logical-job counts; exact cache hits and repeated indices can reduce new process executions.

The validation's complete design has 252 labels (246 path runs and six coverage jobs); 211 above is the additional work after reusing the build's 41 `both` paths. Repeated indices can further reduce unique cache jobs. Its central-only design has twelve labels before reusing the central `both` path. The separate part E evidence pilot also has 252 full-run labels, with different treatments including the full-new bound; it executes 41 six-treatment Enhanced FRS batches and six coverage jobs (47 process jobs), capped at three batch workers while at least 40 GiB is available and load is below about twice the CPU count. Otherwise reduce workers. That optimization shares pristine setup only: every treatment and policy has independent inputs and parameters, with full-horizon calculations in their original order. It does not change ordinary build or Microcosm jobs.

Part E publishes the ONS total-only control to address Vahid's population-total point. The comparison is `reweight_minus_ons_total`: the two controls' target totals can differ, so it is not a fixed-total estimate of the age/sex margins alone. A matched-total supplement is a possible follow-up; its runs and results are outside this closeout.

The corrected full-new support receipt also has a separate six-job coverage-only recipe, `scripts/run_model_v2_e_coverage.py`, at its own frozen head. This reruns all nine coverage years for each original E treatment and counts actual stored flat-rate changes, excluding already-full re-typed amounts. It records source/data/package hashes and all 162 country support receipts. When a complete `--coverage-results` artifact is supplied, the E driver validates it before starting any job and schedules only the **41 fiscal batches**, skipping the six obsolete coverage jobs. The assembled evidence still has **252 labels**: 246 fiscal labels at their original source and six fresh coverage labels at their separately recorded source. Without the replacement, the default remains 47 execution jobs and 252 labels. At most three Enhanced FRS coverage workers are permitted; allocate slots against other active jobs.

Once those full jobs and proofs are complete, select stored aggregates into a reviewable table with:

```sh
python scripts/render_model_v2_e_tables.py --input data/pilot/model_v2_e.json \
  --output docs/pilot/E-fiscal-tables.md
```

The renderer selects the saved aggregate tables and preserves linked suppression; it computes no mean, contrast or SE.

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

Part D ran pieces of this on the integrated branch (policyengine-uk 2.120.0, Enhanced FRS 1.56.16, the March 2026 OBR means). Its aggregate version bridge, integrated savings and GB-versus-DWP coverage are retained in [data/pilot](../data/pilot/), with calculation-commit/model tags and review verdicts in [MODEL_V2_PILOT.md](MODEL_V2_PILOT.md). They are a pilot on an uncertified data/model pair, not for quoting. The completed coverage audit is retained. The per-path national fiscal support audit was stopped before completion as a scope cut. Its historical national contributor counts do not certify subset complements or recoverable offsets. Part J checks exact support for linked gross/net offsets and the UK/GB and Housing Benefit complements before releasing its new bridge. D's retained figures are published unchanged, with **£1m (£0.001bn)** tolerance for independent full-run replays. Archived replays at D's calculation heads match gross to four decimal places and net within £0.0003bn; this is a float-tolerance check, not a claim of exact equality.

- Part A's version bridge, rerun on 2.120.0: coverage, the central path, the OBR wedge and fourteen expected-value draws on 1.56.16, and the central path and coverage on 1.57.4.
- The central path and the 40 Microcosm-paired draws under `legacy` and `both`, and coverage under `both`.
- The central path on Microcosm under `legacy` and `both`.

## Portable pre-build validation

The frozen C2 section is bound by its committed SHA-256; calculation heads are
provenance, and pilot source correspondence uses committed per-file hashes.
A normal depth-1 clone needs no private Git directory or historical commits for
its tests or C2 build. The annotated `c2-preregistration` tag preserves the
registration audit separately; see METHOD.md for dates and verification.

Run the complete suite in a fresh environment using the locked install above.
Before the gated rebuild, the three named stale-results tests remain failures.
CI runs the same complete suite and records its process exit code, every
selected/completed test identity, and its JUnit report.
Completion includes fixture teardown, final reporting and plugin cleanup,
including pytest's final cleanup after command-hook wrappers return. The
recorder publishes evidence only after that cleanup returns; a hard exit
during cleanup leaves no reusable completion record.
An explicit pytest exit remains an interruption even if it chooses code zero or one.
`scripts/check_prebuild_tests.py` requires complete execution and validates the
three documented stale assertions by identity and assertion reason; other
exceptions raised by those test functions still fail CI. These are the only
permitted exceptions for the draft `model-v2` PR. Main and ready PRs require exit
code zero and all tests to pass. Interruptions, collection errors, internal
errors, missing completion evidence and every other failure fail CI.
No history fetch is needed in the checkout workflow.

## Part J: pre-Budget rehearsal and post-Budget sequence

The rehearsal uses the certified bundle and today's committed inputs. Its numbers are not for quoting. It never writes `data/results.json`, its dashboard copy or scenario publication files. The C2 dry handoff remains `run_kind: dry_run` with `expected_value_authorized: false`; the rehearsal adapter retains the frozen ruling (c) checks and original-primary design. A passing diagnostic screen does not authorize a binding build.

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
vm_stat
python -m triple_lock.ts_uncertainty --screen c2 --output .cache/J-c2-dry-run
python scripts/run_model_v2_j_rehearsal.py --handoff .cache/J-c2-dry-run \
  --output-dir .cache/J-rehearsal --stage core --skip-microcosm-coverage --workers 3
# Run these after Enhanced FRS work finishes and memory is available.
python scripts/run_model_v2_j_rehearsal.py --handoff .cache/J-c2-dry-run \
  --output-dir .cache/J-rehearsal --stage coverage --workers 1
python scripts/run_model_v2_j_rehearsal.py --handoff .cache/J-c2-dry-run \
  --output-dir .cache/J-rehearsal --stage sample --workers 3 \
  --sample-runs 20 --microcosm-runs 2 --sensitivity-workers 1
```

Use no more than three Enhanced FRS workers or two Microcosm workers across all active jobs. The stages keep those datasets separate. Check `vm_stat` and available memory before admission; stop when host load exceeds twice the CPU count or memory becomes insufficient. The Part J first two-worker bridge attempt was stopped at load above 36 on the 18-CPU host; no fiscal aggregate completed. Numerical-library thread limits above prevent each worker opening a large thread pool. This is a host-admission failure, not a fiscal correction. Cold job times, cache hits, failures and full planning estimates are recorded separately by job type; unmeasured types keep their estimate unavailable.

The exact post-Budget order is:

1. Commit September CPI, published May–July earnings, the 28 October OBR forecast and every newly complete backtest origin, with the source bytes and release identities described above. Verify the certified lock, hashes and behavioural HB passport.
2. Run the **binding C2 re-score**, using `python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2`. The named launchd job `uk-triple-lock-c2` is intended to start this from **29 October 2026**. This workspace task does not install or change that host job. A read-only inspection on 11 October found no matching loaded label, so check its host schedule before relying on it; the binding-input guard remains mandatory even when launchd invokes the command. Commit the resulting binding handoff and scores before model jobs.
3. Run `triple-lock-build --workers 3 --sensitivity-workers 2 --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2` on the certified bundle. Primary pass permits only its model-conditional expected value beside the scenario envelope; primary failure automatically uses (a), scenarios only. Run the paired four-way validation after a pass, or `--central-only` after a failure. Check accounting, coverage, source/input/provenance bindings, full pytest and dashboard checks.
4. Obtain independent review of the rebuilt fiscal aggregates, C2 outcome, coverage and limitations, resolve findings and repeat to approval. Keep #24 OPEN and draft until the separately authorized review/merge decision.
5. After reviewed results are accepted, update the paper and dashboard together, including scenario-envelope wording and Pension Credit/HB/CTR coverage. Re-run their checks. Part J rehearsals and historical pilot figures do not supply publishable replacements.

The verified pins and release hashes are in [J-certification](pilot/J-certification.md), and the source changes are in [J-upstream](pilot/J-upstream.md). Measured timings and the numerical bridge are recorded only after the corresponding full jobs complete. Historical memory/runtime estimates above remain historical context.

The full build, standalone mean-path and single-scenario entry points, and real ageing validation enforce the exact certified carrier/model/core, primary pin and released-manifest certification before model jobs. Their provenance keeps that gate beside the behavioural Housing Benefit passport. Paired ageing additionally requires the source's exact certified packages, dataset SHA and manifests; the old pilot cannot supply that source. The version bridge verifies the retained pilot against its independently pinned historical content before reusing figures; an initially consistent but edited pilot is rejected, including under optimized Python.

Runtime planning uses only completed cold jobs. `planned_stage_wall_hours` adds the central path, OBR wedge and both dataset coverage jobs at their full serial latency, then divides the remaining sequential batches by the relevant worker caps. `ideal_parallel_wall_hours` is retained only as an explicitly optimistic comparison. Partial batches, contention, C2 scoring, input preparation and review/paper/dashboard work remain outside these model-runtime estimates. Missing job types leave both estimates unavailable. Ten synthetic runtime regressions passed; their invented times are test inputs, not rehearsal measurements.

Part J stopped early under the saturation rule on 11 October. Available memory was roughly 57–65 GiB, but one-minute load reached 252.84 on 18 CPUs, against the 36 admission limit. No full certified path/coverage job completed, no 20+2 sample completed, and no measured per-job wall times or defensible post-Budget runtime estimate exist. They remain **unavailable**, rather than being filled with historical estimates. [J-report](pilot/J-report.md) retains the exact old pilot figures and lists every missing certified output. The isolated driver plans 161 Enhanced FRS unique paths and 40 paired sensitivities; its planning receipt keeps unmeasured job types null. Regenerate the unauthorized dry-run C2 handoff after source/input changes: a retry correctly rejected its stale source fingerprint before model admission. Re-run the commands above on an unsaturated host to obtain the required timings and planning estimate.

The rehearsal's validation receipt records full-horizon/treatment invariants and timings only. It omits fiscal tables because independent-mode tables cannot certify small treatment contrasts. The ordinary four-way validation computes paired contrasts from independent full treatment jobs and keeps its report private under the workspace's `.cache/` or `out/`; public contrast publication requires a separate joint contributor/complement support audit. The historical part B report remains its own guarded record. The rehearsal requires exact certified packages/artifact and checks source/input/package/driver identity around every stage and checkpoint; it cannot publish a binding result.

The net/offset-support fix retains one policy's household programme arrays until the counterpart year is computed, then releases them. Support comes from accurately summed individual programme changes, avoiding cancellation residuals from completed balances; published fiscal totals are unchanged. Additional peak memory and runtime are unmeasured. Historical Microcosm memory timings do not establish the certified port's current requirements; start with one sensitivity worker and measure before using the two-worker maximum.

On resumption on 11 October, `vm_stat` was checked again and one-minute load was 333.82, then 349.96, later 220.12 on the same 18-CPU host. No new survey job was admitted. This remains a stopped rehearsal, with no certified bridge, GB coverage or measured runtime estimate. New publication writers also omit the top-ten concentration diagnostic until nonzero-contributor and recoverable-complement support can be established; cached ten-selected-record labels alone are insufficient.
