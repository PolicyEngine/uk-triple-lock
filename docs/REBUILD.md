# The binding rebuild: runbook

The pre-Budget release is committed on **main**: policyengine.py 6.2.6 / UK 2.125.1 / core 3.33.0 / Enhanced FRS 1.58.0, publicized in Vahid's post as provisional and model-conditional under ruling (c). The 29 October binding rebuild uses **different data**: Max ruled **d1983 = B** on 24 October, making policyengine.py's national Microcosm UK Budget pair primary, with **Enhanced FRS 1.58.2** as paired sensitivity. Bridge step (b) measures that data-family change. No binding fiscal result has run here.

## What it waits for

| Gate | What it holds back | Until then |
|---|---|---|
| **d1983 = B: policyengine.py #715** | The exact released carrier manifest for national Microcosm cut `microcosm-uk-2024-25-national-20261023T075039Z-a133f37a`, UK 2.147.2 / core 3.33.3 | #715 remains a draft stacked on #704. Its attribution is scheduled for 24 October 22:00Z–25 October 10:00Z, then review. Preflight fails closed while carrier version and released-manifest digest are unset. |
| **Binding inputs**: AWE on 20 October, September CPI on 21 October, OBR forecast on 28 October | Commit official source bytes and release identities before a fresh binding C2 handoff | A pre-Budget/dry-run file never authorizes the binding build. |
| **d955 = (c)** | Only a passing original primary may get a model-conditional expected value, beside the scenario envelope | C2's frozen rule remains unchanged; primary failure automatically takes (a), scenarios only. No alternative form is promoted. |

## Pending #715 bundle and two-step bridge

The reviewed [#715 head](https://github.com/PolicyEngine/policyengine.py/pull/715) is `e02d41bceab57756373b2dc3bcf78635b856ec81`. Check that head again before completing the pins; if its cut/model changes, re-read the new manifest and audit, and if it closes, stop. Its exact identities are:

| Identity | Pin |
|---|---|
| UK model/core | `policyengine-uk==2.147.2`, `policyengine-core==3.33.3` |
| UK wheel SHA-256 | `4b48ab1008b00610abc38192927ac9d4bb22037b6bbd9578926c2899e639f972` |
| Dataset registry name | `microcosm_uk_2024_25@a133f37a`, national only |
| HF repository / revision / path | `policyengine/populace-uk-private` / `microcosm-uk-2024-25-national-20261023T075039Z-a133f37a` / `microcosm_uk_2024_25.h5` |
| Dataset SHA-256 | `64f83900ca3a1242fb017585234844ce89f743d32e41cd2b6558057777f914aa` |
| Data release manifest | `https://huggingface.co/datasets/policyengine/populace-uk-private/resolve/microcosm-uk-2024-25-national-20261023T075039Z-a133f37a/releases/microcosm-uk-2024-25-national/release_manifest.json` |
| Source manifest URI | `hf://dataset/policyengine/populace-uk-private@microcosm-uk-2024-25-national-20261023T075039Z-a133f37a/releases/microcosm-uk-2024-25-national/release_manifest.json` |
| Released carrier manifest | Future `policyengine` release's `src/policyengine/data/bundle/manifest.json`; carrier version and digest intentionally unset |

The draft manifest still labels itself 6.10.1, but the already released 6.10.1 wheel carries the previous UK cut and cannot certify this one. The preparatory lock uses the base carrier without `[uk]`, plus explicit UK 2.147.2/core 3.33.3. The engine constructs `policyengine_uk` directly and loads its own verified artifact; the released carrier's `[uk]` extra would impose the previous model. Publication preflight remains closed until the exact #715 release is authenticated. d1727's Enhanced FRS qualification-ledger route is superseded as the primary; its fail-closed code, [status receipt](../data/certification/d1727-qualification-status.json) and [2.153.4 audit](d1727-upstream.md) stay as history.

1. After #715 is reviewed and released, set `datasets.BINDING_BUNDLE_VERSION` and `datasets.BINDING_BUNDLE_MANIFEST_SHA256` from the future released carrier, and the carrier version in both dependency files. Do not change the model/core/data pins merely to fit a carrier. Confirm that the released manifest exactly matches every identity above.
2. Keep the current [2.125.1-to-2.147.2 source audit](d1983-upstream.md), `check_upstream()` and the parameter/small-household checks passing. UK 2.147.2 includes #2019, #2507–2509, #1913, #2336, #2458, #1831, #2518 and #2516. It lacks #2557 (September-CPI benefit uprating, first 2.148.2) and #2576 (earnings-linked guarantee/derived HB and Savings Credit, first 2.151.2); #2340 remains unmerged. Additional pension still takes the engine's path-specific explicit CPI pin. Age-addition handling takes the absent-variable branch.
3. Run certification and the behavioural HB receipt-passport preflight below before survey jobs. Synthetic checks never certify the fiscal result.
4. Copy `data/binding-bridge.pending.json` to `data/binding-bridge.json`. Fill the released carrier version in the three new endpoint package maps and `pending_release.policyengine_version`, fill `pending_release.bundle_manifest_sha256`, set status `ready`, and commit it. Keep historical baseline pins/SHA, UK/core pins and both artifact hashes fixed. Pending `--validate-only` honestly refuses #715 without launching jobs.
5. Run **(a), model step**: 6.2.6 / UK 2.125.1 / core 3.33.0 → UK 2.147.2 / core 3.33.3, holding **Enhanced FRS 1.58.0** fixed. The new intermediate pair is uncertified. Run **(b), data step**: **Enhanced FRS 1.58.0 → Microcosm a133f37a**, holding the same installed packages and engine sources fixed. Only that final endpoint must have released certification. Each endpoint runs the complete central/coverage/frozen forty-path design. Data/from must reuse exactly model/to's receipt; no dataset-family equality is assumed.
6. Review fresh accounting and GB/DWP coverage before feeding a regenerated binding C2 handoff to the full fiscal build. The primary/sensitivity config change alters its input hash: regenerate it through C2, and preserve every historical handoff/receipt byte.

**d1753 on this bundle.** UK 2.147.2 has neither Savings Credit `maximum` nor either linked projection builder. Tests also cover a `maximum`-present/builders-absent system defensively. Keep its installed **CPI** HB allowances and Savings Credit thresholds as headline. Their `gov.benefit_uprating_cpi` parameter names `gov.economic_assumptions.indices.obr.lagged_cpi` in its uprating metadata, so it follows lagged calendar CPI; #2557's September-CPI construction is absent. The engine still applies the statutory earnings-linked guarantee. Gate linked derivation on the actual builders, not merely on `maximum`. The separate foreground comparison below runs the installed-CPI and explicitly guarantee-linked conventions as complete central triple-lock/Burnham pairs; it does not change the default.

```sh
# Main session foreground only, after authenticating and installing the released lock.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
.venv/bin/python -c 'from triple_lock.model_horizon import check_upstream; check_upstream()'
.venv/bin/python -c 'from triple_lock.pipeline import certified_bundle_preflight, housing_benefit_passport_preflight; certified_bundle_preflight(); housing_benefit_passport_preflight()'

# Zero jobs: authenticate ready config, historical source receipt and paired design.
.venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step model \
  --from-receipt data/pilot/J-bridge-certified.json --workers 1 \
  --out data/pilot/binding-bridge-model.json --validate-only

# (a) Model step on Enhanced FRS 1.58.0; intermediate remains uncertified.
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh d1983-bridge-model \
  .venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step model \
  --from-receipt data/pilot/J-bridge-certified.json --workers 1 --out data/pilot/binding-bridge-model.json
# (b) Cross-family data step on exactly the same UK2.147.2/core3.33.3 environment.
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh d1983-bridge-data \
  .venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step data \
  --from-receipt data/pilot/binding-bridge-model.json --workers 1 --out data/pilot/binding-bridge-data.json

# d1753: installed CPI headline versus guarantee-linked HB/Savings Credit alternative.
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh d1983-hb-sc-linked \
  .venv/bin/python scripts/compare_hb_link.py --method linked --execute \
  --output .cache/d1983-hb-sc-linked-comparison.json

# Coverage check: verifies source/row completeness and prints fresh GB/DWP ratios.
# Review those ratios and accounting; no arbitrary numeric threshold certifies coverage.
python - <<'PY_CHECK'
import json
import math
from pathlib import Path
from scripts.run_model_v2_j_bridge import COVERAGE_YEARS, METRICS, digest
from triple_lock import dwp
r = json.loads(Path("data/pilot/binding-bridge-data.json").read_text())
assert r["complete"] and r["bridge"]["step"] == "data"
assert r["provenance"]["dataset"]["certified"] is True
coverage = r["coverage"]
assert coverage["source_sha256"] == digest(dwp.TABLES)
rows = coverage["rows"]
assert len(rows) == len(COVERAGE_YEARS) * len(METRICS)
assert {(x["year"], x["metric"]) for x in rows} == {(y, m) for y in COVERAGE_YEARS for m in METRICS}
targets = dwp.coverage_targets_by_year(years=list(range(2024, 2031)))
for x in rows:
    target, scale = METRICS[x["metric"]][1:]
    benchmark = targets[x["year"]]["values"][target] * scale if target and x["year"] in targets else None
    assert x["DWP_GB"] == benchmark
    if x["status"] == "available":
        assert all(math.isfinite(x[g]) for g in ("UK", "GB"))
        assert x["GB_over_DWP"] == (x["GB"] / benchmark if benchmark else None)
    else:
        assert x["status"] == "withheld_family" and x["UK"] is x["GB"] is x["GB_over_DWP"] is None
    print(x["year"], x["metric"], x["status"], "GB/DWP:", x["GB_over_DWP"])
PY_CHECK
```

<a id="pending-state-pension-patches"></a>

The current State Pension guard audit is [d1983-upstream](d1983-upstream.md). #36's parameter-consistency and age-addition preparation remains documented in [d1727-upstream](d1727-upstream.md) and its retained receipts; its 2.153.4 linked-projection findings do not describe 2.147.2.

## Inputs to update first

Each is a commit before the build. The build refuses a dirty tree, and every input file is hashed into provenance.

1. **AWE (20 October) and September 2026 CPI (21 October).** Refresh the May–July AWE levels (KAB9), published rate (KAC3), and their release metadata from the 20 October vintage. Set `ts_monthly.BINDING_AWE_RELEASE_DATE` to that authenticated release date; retain the pre-Budget release's September vintage in its historical provenance. September CPI is ONS D7G7, published 21 October 2026. It supplies April 2027's CPI leg and additional State Pension uprating. Published May–July earnings supply the earnings leg and the Pension Credit guarantee's next rise, subject to its no-cut rule.
   - Update `data/raw/ons_d7g7_cpi_annual_rate.csv` and `data/raw/ons_d7bt_cpi_index.csv` (the monthly index the models read).
   - Update the April 2027 row in `data/triple_lock_actual_inputs.csv` with the actual September 2026 CPI and published May–July 2026 AWE. Keep CPI consistent with the raw September monthly index, and AWE consistent with the raw May, June and July 2026 levels in `data/raw/ons_kab9_awe_total_pay.csv`; the binding guard checks those matches.
   - Set `config.CPI_PERIOD = "2026 SEP"`.
   - April 2027 is then the larger of September CPI and the published May–July AWE (`config.AWE_PERIOD`).
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

   A run on today's inputs is explicitly a **dry run**, not the binding score and not permission for a fiscal expected value. The adapter consumes the original-primary 160-slot design (161 unique full runs including its identical-rates check on the committed inputs). Replacement sampling can repeat indices after an input update; use the handoff's saved distinct counts. A passing binding score adds the exact frozen 40-slot paired subsample on Enhanced FRS 1.58.2; only the dataset role changes. The original-primary ±0.5-point mean paths run independently of adequacy, with the same primary indices, innovations and zero-stratum mass; their extra baseline check may save nonzero. The scenario envelope carries the central path, OBR wedge, recorded historical last-decade replay (April 2017–2026, with its own model years) and those paired mean paths under either outcome. The historical replay retains its period label and is not treated as a future-horizon simulation or included in a common future-year range.
4. **Versions and dataset**: complete the pending #715 release and two-step bridge above. The installed packages, primary artifact and released certification must match exactly. Run the final coverage and accounting checks before the binding run. The behavioural Housing Benefit Guarantee Credit passport must still pass: the non-claimant faces the ordinary means test, the claimant receives maximum HB, and reversed receipt flags exercise all three branches. Every publication entry point runs this guard before fiscal jobs.

## Commands

Start from `main`, with the newly released #715 carrier lock and bridge changes reviewed on the rebuild branch. The preparatory lock pins its UK 2.147.2/core 3.33.3 candidate and remains uncertified until that release exists:

Set `HEAVY_CALLER=uk-triple-lock` before every command run through `heavy_run.sh`, `lockrun.sh` or `heavy_queue.zsh`. The caller identity gives this repository access to the Fleet ops reservation [below](#part-j-pre-budget-rehearsal-and-post-budget-sequence).

```sh
git fetch origin main
git switch -c rebuild/budget-2026 origin/main
# Complete the pending-bundle and input-update sections above on this branch.
# Commit each step and open a draft PR into main at the first commit.
# The following install uses the newly authenticated #715 lock.
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
source .venv/bin/activate
export HEAVY_CALLER=uk-triple-lock
export HUGGING_FACE_TOKEN=$(agent-secret get HUGGING_FACE_TOKEN_MAX)
# Private dataset bytes stay in .cache/datasets.
python -c "import psutil; m = psutil.virtual_memory(); print(m.available / 2**30, 'GiB free')"   # see Memory

# 1. Check the inputs before anything long.
python -m pytest -n 4 -q                      # only the documented stale-results assertions may fail (below)

# 2. After 28 October, with the binding macro inputs committed and the
#    released #715 bundle installed, both bridge steps and coverage reviewed.
#    Check #1927's receipt passport before scoring; real builds also run this guard.
python -c 'from triple_lock.pipeline import housing_benefit_passport_preflight; housing_benefit_passport_preflight()'
python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2

# The same build command handles both C2 outcomes:
# primary passes: model-conditional expected value and scenario envelope;
# primary fails: automatic (a), scenario envelope only, with recorded reason.
triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2

# Standalone mean-path scenarios, with no adequacy gate:
triple-lock-build --mean-path-scenarios --workers 1 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2 --out .cache/mean-path-scenarios.json

# 3. The four-way ageing design, on the rebuilt file's paired draws (aggregates only, into .cache; see below).
python scripts/validate_ageing.py --plan
python scripts/validate_ageing.py --workers 1 -o .cache/ageing_validation.json
#    If the primary failed C2 and the build has no expected-value section,
#    run this central-only command instead of the paired design above:
python scripts/validate_ageing.py --central-only --workers 1 -o .cache/ageing_validation.json

# 4. Check the file before committing it.
python scripts/check_assumptions.py data/results.json
python -m pytest -n 4 -q                      # now nothing may fail
(cd dashboard && bun install --frozen-lockfile && bun run test --maxWorkers=4 && bun run lint && bun run build)
```

For the pre-Budget **dry run** only (draws and scoring, zero PolicyEngine jobs):

```sh
python -m triple_lock.ts_uncertainty --screen c2 --output out/uncertainty-c2-dry-run
```

Omitting `--binding` labels the handoff and scores as a dry run. Do not use that handoff for the binding rebuild. Commit the updated macro/model/data inputs before the binding score; commit its resulting handoff and score provenance before the full build.

`triple-lock-build` caches every job (`.cache/jobs`). An interrupted build resumes where it stopped, and the job key changes only with what a job computes.

Step 3 reads its paired draws from the file it is pointed at (`data/results.json` by default) and rebuilds each draw from the central path, failing if a draw no longer reproduces the inputs the file records. So it runs after the build, on the rebuilt file. Run on the committed file once the inputs have changed, it fails, by design. A passing d1983 C2 build records the Enhanced-FRS-paired subsample (the frozen handoff retains its historical “Microcosm-paired” wording): per path, `times_drawn_sensitivity`; per stratum, `sensitivity_paths` and `probability`; and `draws.n`, `seed`, `shocks` and `form`. The validation reconstructs that recorded form. The original-primary design includes stratum zero explicitly, so its mass is counted once. The validation has six modes: `legacy`, `frozen`, `reweight`, `types`, `both`, and the `total` population-only control. Its `both` path runs share the build's cache entries (`ageing_validation.canonical`), so today's design adds the other five modes' central and 40 paired path runs (205) and six coverage jobs, whose years differ from the build's. The four-way factorial remains frozen/reweight/types/both; legacy and total are controls. A failed-primary build has no paired expected-value subsample, so use `--central-only`.

## Interim pre-Budget release (before the binding rebuild)

This section describes the historical certified pre-Budget release, reproduced only at its original source and lock. Its 6.2.6 / 1.58.0 Enhanced FRS primary and earlier Microcosm sensitivity remain as published under Max's recorded ruling (c). The current binding source selects different datasets and must use the #715 sequence above. Its expected value is **provisional and model-conditional**: the original primary passes the registered C2 dry run on current inputs (4 of 6 terminal years, 80% annual coverage), with the full paired Microcosm cross-check. The binding test follows the Budget inputs; failure removes the expected value. A scenarios-only interim release may use (a). The obsolete public pre-Budget (b) route is refused.

```sh
# From a clean checkout of the reviewed head, venv as above, Enhanced FRS 1.58.0 and Microcosm in .cache/datasets.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python -c 'from triple_lock.pipeline import certified_bundle_preflight as p; p()'
python -c 'from triple_lock.pipeline import housing_benefit_passport_preflight as p; p()'
python -m pytest -n 4 -q                      # only the documented stale-results assertions may fail
triple-lock-build --pre-budget --uncertainty-ruling c --workers 2 --sensitivity-workers 1   # or a: scenarios only
python scripts/validate_ageing.py --central-only --workers 3 -o .cache/ageing_validation.json
python scripts/check_assumptions.py data/results.json
python -m pytest -n 4 -q                      # now nothing may fail
(cd dashboard && bun install --frozen-lockfile && bun run test --maxWorkers=4 && bun run lint && bun run build)
```

- `--pre-budget` requires `--uncertainty-ruling a` or `c`, and takes no `--uncertainty-handoff`. It also refuses once `config.CPI_PERIOD` is no longer `2026 AUG` or the central path no longer uses the OBR's March 2026 EFO: by then the binding route applies.
- The file carries a top-level `release` block (`stage: "pre-budget"`, `interim: true`, `execution_ruling`, the OBR March 2026 forecast, April 2027's provisional August 2026 CPI leg, what happens to the expected value and `recorded_ruling: "c"`; see RESULTS_SCHEMA.md). `uncertainty_ruling` and the mean-path provenance say the file is an interim release under the recorded ruling (c).
- Under (a), `expected_value_omission.reason` says the expected value is "withheld pending the post-Budget binding score", and the dashboard's scenario envelope says it waits for the Budget inputs.
- Under (c), the build first validates every C2 integrity field (rule SHA and frozen section, current handoff input hashes, score hashes, C1 disclosure, dry-run kind, authorization and fiscal eligibility). It then runs the primary through the model-conditional route on the handoff it generates, then checks that the primary's path design and specs and both mean-path specs are byte-identical to the committed C2 dry run's (`pipeline.check_dry_run_design`), and refuses if they differ or if the dry run's primary fails C2. The file records the dry run's C2 provenance (`run_kind: "dry_run"`, `expected_value_authorized: false`) in `uncertainty_ruling` and `uncertainty_screen`, with `provisional: true`; `release.provisional`, `release.c2_dry_run` and `release.expected_value` say the expected value is provisional under ruling (c). The paired Microcosm cross-check runs in full (40 paired runs). Because it runs through the (b) route, `expected_value` also keeps the legacy `backtest` and `past_years_check` diagnostics.
- The dashboard shows a pre-Budget banner while `release.stage` is `pre-budget`.
- A provisional (c) build includes 40 paired Microcosm runs; `--sensitivity-workers` controls their concurrency and defaults to one at the CLI and pipeline entry point. Per the instruction to keep `expected_value.py` unchanged, its `build` and `rehearsal_sample` internal defaults remain two; public callers pass one explicitly. Changing those two signatures is deferred until that source edit is authorized. Host admission scales its batch floor to the number of concurrent uncached Microcosm jobs.
- After the Budget, the binding route in [Inputs to update first](#inputs-to-update-first) and [Commands](#commands) replaces this file: commit the new inputs, run the binding C2 score, then `triple-lock-build --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2`. That build writes no `release` block, so the banner goes. Forecast wording follows the file's release/central metadata.

## Jobs, memory and time

The dataset roles have changed. Counts below use the committed original-primary design: 160 sample slots and one extra zero check, all distinct. C2 scoring starts **zero PolicyEngine jobs**; mean-path scenarios do not wait for adequacy. Only the sensitivity dataset changes for its exact forty paired slots.

| Stage | Microcosm primary jobs | Enhanced FRS 1.58.2 sensitivity jobs |
|---|---:|---:|
| Central path | 1 | 0 |
| Coverage | 1 | 1 |
| Original-primary baseline, reused for expected value only after C2 pass | 161 | 40 after pass; 0 after failure |
| Paired mean-path scenarios | 322 | 0 |
| Four trajectories and four past-year cases | 8 | 0 |
| OBR wedge | 1 | 0 |
| **Build under c, primary passes C2** | **494** | **41** |
| **Build under c, primary fails → automatic a** | **494** | **1** |
| Ageing validation after pass, reusing the build's both paths | 211 | 0 |
| Ageing validation after failure, central only | 11 | 0 |

For updated inputs let `U` be original-primary `unique_full_runs` (including the extra check), and `V` the distinct indices in the frozen 40-slot sensitivity. The binding build has `3U + 11` **Microcosm** jobs under either C2 outcome; Enhanced FRS adds `V + 1` after a pass, or one after failure. Validation adds `5(1 + V) + 6` Microcosm jobs after pass, or 11 after failure. Standalone mean-path scenarios have `3U` Microcosm jobs. Cache hits and replacement-draw duplicates reduce process launches.

**Capacity estimate for Fleet ops, derived without survey jobs.** The old reservation assumed 3 Enhanced FRS plus 2 Microcosm workers. Keeping role caps of 3 primary plus 2 sensitivity would now mean **3 Microcosm plus 2 Enhanced FRS** workers. Across concurrent work, filling all five reserved slots at the historical per-worker peaks (31.8 GB and 6 GB) gives **107.4 GB**, versus the old **81.6 GB**: **25.8 GB / 31.6% more**. These are reservation-wide sums. The frozen `expected_value.build` schedules primary and sensitivity phases sequentially: its three-primary/two-sensitivity worker estimate is `max(3 × 31.8, 2 × 6)` = **95.4 GB**, excluding coordinator/other-process memory. At the documented one-primary/one-sensitivity caps, that phase maximum is **31.8 GB**. These are historical-peak extrapolations, not measurements of a133f37a/2.147.2; the fresh-cut peak and net-support-array cost are unmeasured. Code admission requires **120 GiB available** for three concurrent cold Microcosm jobs (40 GiB each), compared with 80 GiB for two. Start the main session at **`--workers 1 --sensitivity-workers 1`**, with a 40 GiB admission floor, and have Fleet ops review capacity before increasing it. The bridge likewise caps Microcosm endpoints at two, uses Microcosm slots and scales its batch/monitor floor to 40 GiB per concurrent Microcosm job.

The historical rehearsal timings at the end of this runbook used the opposite data roles and an earlier cut; they do not forecast the binding runtime. No current survey or Microcosm simulation was run for this preparation.

The validation's complete design has 252 labels (246 path runs and six coverage jobs); 211 above is the additional work after reusing the build's 41 `both` paths. Repeated indices can further reduce unique cache jobs. Its central-only design has twelve labels before reusing the central `both` path. The separate part E evidence pilot also has 252 full-run labels, with different treatments including the full-new bound; it executed 41 six-treatment Enhanced FRS batches and six coverage jobs (47 process jobs), capped at three batch workers while at least 40 GiB was available and load was below about twice the CPU count, the operator rule at the time. Its driver has no host check of its own; the current limits are in [Host admission](#host-admission-memory-floors-and-the-load-limit). That optimization shares pristine setup only: every treatment and policy has independent inputs and parameters, with full-horizon calculations in their original order. It does not change ordinary build or Microcosm jobs.

Part E publishes the ONS total-only control to address Vahid's population-total point. The comparison is `reweight_minus_ons_total`: the two controls' target totals can differ, so it is not a fixed-total estimate of the age/sex margins alone. A matched-total supplement is a possible follow-up; its runs and results are outside this closeout.

The corrected full-new support receipt also has a separate six-job coverage-only recipe, `scripts/run_model_v2_e_coverage.py`, at its own frozen head. This reruns all nine coverage years for each original E treatment and counts actual stored flat-rate changes, excluding already-full re-typed amounts. It records source/data/package hashes and all 162 country support receipts. When a complete `--coverage-results` artifact is supplied, the E driver validates it before starting any job and schedules only the **41 fiscal batches**, skipping the six obsolete coverage jobs. The assembled evidence still has **252 labels**: 246 fiscal labels at their original source and six fresh coverage labels at their separately recorded source. Without the replacement, the default remains 47 execution jobs and 252 labels. At most three Enhanced FRS coverage workers are permitted; allocate slots against other active jobs.

Once those full jobs and proofs are complete, select stored aggregates into a reviewable table with:

```sh
python scripts/render_model_v2_e_tables.py --input data/pilot/model_v2_e.json \
  --output docs/pilot/E-fiscal-tables.md
```

The renderer selects the saved aggregate tables and preserves linked suppression; it computes no mean, contrast or SE.

**Binding-run guards (Vahid's review items 2–4).** Default to **one Microcosm primary worker** (`--workers 1`) and one Enhanced FRS sensitivity worker until measured current-cut peak memory supports more. Historical peaks were about 6 GB for Enhanced FRS and 31.8 GB for Microcosm; the latter predates the net-support changes. The 12 October rehearsal ran two cold Microcosm paths sequentially (556 s and 675 s) but measured **no worker peak memory**. Sources: `~/.claude/scheduled-jobs/uk-triple-lock-rehearsal/state/logs/rehearsal-sample-1-1791792698.log` and the rehearsal worktree's `.cache/J-rehearsal/sample-receipt.json`; available-memory snapshots are host headroom.

`jobs.py` applies `host.assess` before uncached batches (40 GiB; 40 GiB × `min(workers, uncached Microcosm jobs)` for Microcosm) and after each slot acquisition (40 GiB), with load limit `TRIPLE_LOCK_MAX_LOAD_PER_CPU` × CPUs (default 6). Job cache records and `provenance.model.host_admission` retain decisions; `host_admission_cache_hit` marks reuse without a launch. Fiscal cache keys are unchanged; explicit Part J callbacks and runners retain their own guards.

The **historical pre-Budget release** pins KAB9 and KAC3 to **15 September 2026**, before October revisions. Reproducing that release uses those archived bytes; [sources](sources.md) gives the download and rounding-interval rules. The **binding rebuild** instead uses the authenticated **20 October 2026** release described in Inputs to update first: replace both source files and their release metadata together, and update `ts_monthly.BINDING_AWE_RELEASE_DATE` before re-scoring C2. The loader must check and record that required October vintage. A moved Budget requires one edit to `ts_uncertainty.C2_BUDGET_DATE`; source-date matching and diagnostics derive from it.

### Host admission: memory floors and the load limit

The Part J runners, `scripts/run_model_v2_j_bridge.py` and `scripts/run_model_v2_j_rehearsal.py`, admit a model job through one shared rule (`triple_lock.host`). They refuse when available memory is below the runner's floor, or when one-minute load is above `TRIPLE_LOCK_MAX_LOAD_PER_CPU` × logical CPUs. A reading that is not a finite number also refuses. They check before each batch, again inside each acquired worker slot, and every five seconds while jobs run; a refusal stops the running children and starts nothing new.

| Runner | Memory floor (unchanged) | Load limit |
|---|---|---|
| Bridge | 40 GiB per concurrent Microcosm job before a batch, in each slot and in the monitor; otherwise 40 GiB | per-CPU limit × CPUs |
| Rehearsal | 40 GiB before an Enhanced FRS batch and in each slot; 40 GiB × `min(workers, uncached Microcosm jobs)` before a Microcosm batch; 8 GiB while a job runs | per-CPU limit × CPUs |

The per-CPU limit defaults to **6**, the threshold Subfleet's own guard uses for background work: **108 on this 18-CPU host**. Set `TRIPLE_LOCK_MAX_LOAD_PER_CPU` to change it, or pass `--max-load-per-cpu` to either runner (the flag wins). A blank variable means the default. A zero, negative or non-finite value stops the runner at startup, before planning or any job. It is never read as "no limit".

The memory floor protects the host and the run. On a shared host, load measures contention, not danger. Fleet ops measured this host on 11 October: with about 90 sessions, one-minute load sat at 150–350 for much of the day. The old cutoff of twice the CPU count (36) stopped Part J with 57–65 GiB still free. A load of 66.11 now passes. Readings of 220–350 still refuse, so the post-Budget run also relies on the Fleet ops reservation [below](#part-j-pre-budget-rehearsal-and-post-budget-sequence).

New receipts written by the current runners record the limits they applied:
- the bridge in `provenance.host_admission` and in each batch's `timings[].host_before`;
- the rehearsal in `host_admission` and in each `host_checks` entry.

The entries are `minimum_available_gib`, `max_load_per_cpu`, `load_limit` and `admitted`. The limit is operational. It is in no job's cache key, recipe hash or execution snapshot, so changing it reruns nothing.

The full build (`triple-lock-build`), standalone scenarios and `scripts/validate_ageing.py` use the default scheduler admission described in the binding-run guards above.

Historical planning times, from part D's measured job times; these have not been remeasured for the final-head ordinary build:

- part D measured about 2.5 minutes per Enhanced FRS path with six running together; this is a historical measurement, not authorization for more than three current workers;
- a Microcosm path job takes about 20 minutes.

| Historical planning estimate | Omitting mean paths | Including mean paths |
|---|---|---|
| Enhanced FRS part of the build (3 workers) | about 2 hours | about 5 hours |
| Microcosm part (2 workers) | about 7 hours | about 7 hours |
| Four-way design (3 workers) | about 1.5 hours | about 1.5 hours |
| **Total** | **about 10 to 11 hours** | **about 13 to 14 hours** |

These historical estimates were within #14's 8-to-16-hour allowance. The current full-build CLI includes the mean-path scenarios; the first column is historical planning context, not a CLI switch. The completed Part J rehearsal now supplies the model-runtime planning estimates [below](#part-j-pre-budget-rehearsal-and-post-budget-sequence). The binding post-Budget build itself remains unmeasured; the historical allowance is not a measured full-build duration.

## What the rebuilt file must show (checked by the tests)

- `tests/test_results.py::test_not_stale` and `tests/test_scenarios.py::test_not_stale` report changed source/input hashes until the binding rebuild. The previously documented `test_method_text_percentiles_match_the_past_years_check` is also allowlisted for its exact stale-percentiles assertion, though it currently passes.
- This hardening additionally expects `tests/test_results.py::test_assumptions_block_is_current` to fail with **"assumptions changed since the build: rebuild"**. No complete fiscal job cache is available in this assigned workspace. `results.json`, its dashboard copy and scenario files remain byte-identical; their provenance continues to describe the historical build. The live `assumptions(results)` paths item now excludes six unsupported reweightings and quotes **£8.3–12.4bn gross (£5.9–8.8bn net)**. The dashboard replaces the stale stored paths text using the corrected helper. The binding rebuild must regenerate the entire file through the build, including all provenance; never hand-edit results/provenance hashes.
- Every run's `fixed_inputs.population` is `{"weights": "ons_projection", "ages": "adjusted", "pension_types": "cohort"}`, and the assumptions strip is worded from it (`pipeline._population_item`).
- Every run passes, or it would have failed: the data-year State Pension identity (`fixed_inputs.state_pension_accounting`), the additional pension under both rules, the population readback, the ONS targets to 1e-6 (`fixed_inputs.ageing`), gross to net, the independent government/household-income level and change identities, path following, and the GB masks.
- The coverage rows set Great Britain against DWP to 2030-31, and State Pension by age is published or withheld whole.
- No single-record or top-ten concentration diagnostics are published. Selecting ten records does not establish ten nonzero contributors or safe complements. The dashboard keeps these diagnostic panels unavailable.

## After the rebuild

- The paper's step 4 drops "which policyengine-uk requires" (#14).
- Refresh `data/scenarios/obr_premium.json` (the build does).
- Re-measure the Pension Credit and Housing Benefit offsets on the binding inputs. The completed pre-Budget version bridge and certified coverage are recorded in [MODEL_V2_PILOT](MODEL_V2_PILOT.md); they do not replace the post-Budget checks.
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
Before the gated rebuild, only the exact named stale-results assertions above may fail.
CI runs the same complete suite and records its process exit code, every
selected/completed test identity, and its JUnit report.
Completion includes fixture teardown, final reporting and plugin cleanup,
including pytest's final cleanup after command-hook wrappers return. The
recorder publishes evidence only after that cleanup returns; a hard exit
during cleanup leaves no reusable completion record.
An explicit pytest exit remains an interruption even if it chooses code zero or one.
`scripts/check_prebuild_tests.py` requires complete execution and validates the
documented stale assertions by identity and assertion reason; other
exceptions raised by those test functions still fail CI. These are the only
permitted exceptions on PRs into `main` while the committed file explicitly remains a provisional pre-Budget dry run with no binding authorization. Ready PRs use the same finite allowlist; main remains strict. Once a binding file replaces it, exit code zero and all tests passing are required. Interruptions, collection errors, internal
errors, missing completion evidence and every other failure fail CI.
No history fetch is needed in the checkout workflow.

## Part J: pre-Budget rehearsal and post-Budget sequence

The historical rehearsal used the pre-Budget 6.2.6 / 1.58.0 certified bundle. Reproducing that historical run uses that exact lock; the pending binding run uses d1983/#715 instead. The commands in this subsection reproduce the historical rehearsal at its original source and lock; the current foreground commands above control the binding rebuild. Its numbers are not for quoting. It never writes `data/results.json`, its dashboard copy or scenario publication files. The C2 dry handoff remains `run_kind: dry_run` with `expected_value_authorized: false`; the rehearsal adapter retains the frozen ruling (c) checks and original-primary design. A passing diagnostic screen does not authorize a binding build.

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
# Optional: the load limit per CPU (default 6; see Host admission). Memory floors are fixed.
# export TRIPLE_LOCK_MAX_LOAD_PER_CPU=6
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

Use no more than three Enhanced FRS workers or two Microcosm workers across all active jobs. The stages keep those datasets separate. Check `vm_stat` and available memory before admission. The runners stop when memory falls below their floor or load exceeds the [shared limit](#host-admission-memory-floors-and-the-load-limit), 6 × CPUs by default. The Part J first two-worker bridge attempt was stopped under the old rule, at load above 36 (twice the CPU count) on the 18-CPU host; no fiscal aggregate completed. Numerical-library thread limits above prevent each worker opening a large thread pool. This is a host-admission failure, not a fiscal correction. Completed cold job times and planning estimates are recorded below, separately from cache hits and failed attempts. The stopped attempts supply no model timing.

The post-Budget rebuild runs inside the Fleet ops capacity reservation **`triple-lock-rebuild-2026-10`**, window **2026-10-29T00:00Z to 2026-11-02T00:00Z**. While it holds, Fleet ops' session cap drops to **12**, and only its holder, `uk-triple-lock`, passes `reservation.py allowed`. `python3 ~/reviews/fleet-ops/tools/reservation.py status` shows whether it is in force. Fleet ops found load can stay above 36 even at that cap, which is why the runners use the shared limit above.

The exact post-Budget order is:

0. If the inputs and the certified environment are ready before 29 October, start the hold early, so it is in force before the step 3 model jobs:

   ```sh
   python3 ~/reviews/fleet-ops/tools/reservation.py ready triple-lock-rebuild-2026-10
   ```

   A `ready` mark brings the start forward only; it cannot extend the window past 2 November.
1. Branch from `origin/main` and open a new draft PR into `main` at the first commit. Complete the pending #715 release, upstream re-hash, passport preflight, model bridge, data bridge and coverage review above. Commit AWE (20 October), September CPI (21 October), the OBR forecast (28 October) and newly complete backtest origins with official source bytes and release identities. Recheck the certified lock and guards after those changes.
2. Run the **binding C2 re-score**, using `python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2`. It is not a separate launchd label. It is the `uk-triple-lock-c2` step inside the loaded launchd job `com.maxghenis.triple-lock-2027`, which runs daily at 08:35. From **29 October 2026**, or the day after a moved Budget, that job dispatches the step as a Subfleet hard-tier build in this repository. It does so once its `budget-check` step has ended DONE or WAITING_ON_MAX. The step stops at the C2 verdict; it does not run the fiscal rebuild. The binding-input guard remains mandatory when the job invokes the command. Commit the resulting binding handoff and scores before model jobs.
3. Run `triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2` on the certified bundle. Primary pass permits only its model-conditional expected value beside the scenario envelope; primary failure automatically uses (a), scenarios only. Run the paired four-way validation after a pass, or `--central-only` after a failure. Check accounting, coverage, source/input/provenance bindings, full pytest and dashboard checks.
4. Obtain independent review of the rebuilt fiscal aggregates, C2 outcome, coverage and limitations, resolve findings and repeat to approval. Keep the new rebuild PR draft until independent review approves; mark it ready and leave merging to the reviewer.
5. After reviewed results are accepted, update the paper and dashboard together, including scenario-envelope wording and Pension Credit/HB/CTR coverage. Re-run their checks. Part J rehearsals and historical pilot figures do not supply publishable replacements.
6. Once the rebuild and its review in step 4 are finished, release the reservation so the fleet comes back early:

   ```sh
   python3 ~/reviews/fleet-ops/tools/reservation.py release triple-lock-rebuild-2026-10
   ```

   Otherwise Fleet ops' session cap stays at 12 until 2026-11-02T00:00Z.

The historical pre-Budget pins and release hashes are in [J-certification](pilot/J-certification.md), and the source changes are in [J-upstream](pilot/J-upstream.md). The version bridge and all three rehearsal stages subsequently completed at execution head `b31137e`. The [completed verification receipt](../data/pilot/J-completed-verification.json) binds the completed artifacts; the [model-step bridge](../data/pilot/J-bridge-model-step.json), [certified bridge](../data/pilot/J-bridge-certified.json) and [GB coverage against DWP](../data/pilot/J-coverage-gb-dwp.json) retain only the permitted aggregate publications. They are **pre-Budget and not for quoting**. [MODEL_V2_PILOT](MODEL_V2_PILOT.md) records the numerical bridge and coverage interpretation. Rehearsal fiscal values remain private. Historical memory/runtime estimates above remain historical context.

The full build, standalone mean-path and single-scenario entry points, and real ageing validation enforce the exact certified client/model/core, primary pin and applicable certification evidence before model jobs. For the historical bundle that evidence is its released carrier manifest; the d1983 route requires #715's exact released carrier manifest and Microcosm artifact. The old d1727 qualification-ledger route remains closed and historical. Their provenance keeps that gate beside the behavioural Housing Benefit passport. Paired ageing additionally requires the source's exact certified packages, dataset SHA and manifests; the old pilot cannot supply that source. The version bridge verifies the retained pilot against its independently pinned historical content before reusing figures; an initially consistent but edited pilot is rejected, including under optimized Python.

The successful unattended steps had these measured wrapper wall times. These are elapsed times for the complete step, including its own setup and cache handling; they are separate from the cold-job means used for planning. Attempts stopped by host admission have nonzero return codes and are excluded.

| Completed step | Wrapper wall time |
|---|---:|
| C2 dry run (zero PolicyEngine jobs) | 106 seconds (1 min 46 sec) |
| Model/core/port bridge, data held at 1.56.16 | 318 seconds (5 min 18 sec) |
| Certified bridge, data 1.58.0 | 312 seconds (5 min 12 sec) |
| Rehearsal `core` | 431 seconds (7 min 11 sec) |
| Rehearsal `coverage` | 171 seconds (2 min 51 sec) |
| Rehearsal `sample` (20 Enhanced FRS + 2 Microcosm paths) | 1,862 seconds (31 min 2 sec) |

Only the completed cold jobs in the certified rehearsal's `core`, `coverage` and `sample` receipts contribute to these per-job measurements. Bridge jobs, warm cache hits and stopped attempts are excluded. In those historical receipts Microcosm was an uncertified sensitivity on the historical certified runtime; d1983 reverses the roles.

These completed runs used the frozen `b31137e` admission rule (load at most 36 on 18 CPUs). Their original receipts record host readings but predate the newer explicit admission fields and default limit of 108 above. The imported runtime receipt retains safe per-job timing rows and their source-receipt hashes.

| Dataset and job type | Completed cold jobs | Mean wall seconds | Observed range, seconds |
|---|---:|---:|---:|
| Enhanced FRS path | 30 | 83.923 | 56.064–95.353 |
| Enhanced FRS coverage | 6 | 21.429 | 16.212–23.798 |
| Enhanced FRS history | 4 | 22.673 | 18.300–24.380 |
| Microcosm coverage | 1 | 158.557 | 158.557 (one job) |
| Microcosm path | 2 | 614.010 | 555.865–672.155 |

The [runtime-planning receipt](../data/pilot/J-runtime-planning.json) applies the committed `planning_estimate` method to those completed cold-job means, with the dry handoff's `U = 161` unique Enhanced FRS runs and `V = 40` paired Microcosm indices. The following are **historical planning estimates for the former Enhanced-FRS-primary build plus step 3 validation**. They do not estimate the new Microcosm-primary rebuild. Updated binding inputs can change `U` and `V`.

| Worker caps (Enhanced FRS + Microcosm) | Primary passes C2: model-runtime estimate | Primary fails C2: model-runtime estimate |
|---|---:|---:|
| 3 + 1, matching the measured Microcosm cap | 12.32 hours | 3.94 hours |
| 3 + 2, projected | 8.91 hours | 3.94 hours |

`planned_stage_wall_hours` adds the central path, OBR wedge and both dataset coverage jobs at their full serial latency, then divides the remaining sequential batches by the relevant worker caps. The 3 + 2 row projects concurrency: the rehearsal measured only one Microcosm worker and provides no memory proof for two simultaneous certified-runtime Microcosm jobs. That historical one-sensitivity-worker advice is now one **primary** Microcosm worker; measure peak memory before adding another.

`ideal_parallel_wall_hours` divides even serial jobs by the worker caps and is retained only as an explicitly optimistic comparison: at 3 + 2 it is 8.85 hours after a C2 pass and 3.88 hours after a failure. Input preparation, C2 scoring, review, paper/dashboard work, scheduling, partial worker batches, cache reuse and contention remain outside these model-runtime estimates. Ten synthetic runtime regressions test the method; their invented times are not rehearsal measurements.

The earlier 11 October attempts stopped under the saturation rule: available memory was roughly 57–65 GiB, but one-minute load reached 252.84 on 18 CPUs, against the then admission limit of 36 (twice the CPU count). That reading would still exceed today's default limit of 108. [J-report](pilot/J-report.md) preserves that historical incomplete checkpoint. The later completed receipts supersede its missing-output status; they do not turn the dry C2 handoff into a binding score or the rehearsal into a publishable rebuild. Regenerate the unauthorized dry-run C2 handoff after source/input changes: an earlier retry correctly rejected its stale source fingerprint before model admission.

The rehearsal's validation receipt records full-horizon/treatment invariants and timings only. It omits fiscal tables because independent-mode tables cannot certify small treatment contrasts. The ordinary four-way validation computes paired contrasts from independent full treatment jobs and keeps its report private under the workspace's `.cache/` or `out/`; public contrast publication requires a separate joint contributor/complement support audit. The historical part B report remains its own guarded record. The rehearsal requires exact certified packages/artifact and checks source/input/package/driver identity around every stage and checkpoint; it cannot publish a binding result.

The net/offset-support fix retains one policy's household programme arrays until the counterpart year is computed, then releases them. Support comes from accurately summed individual programme changes, avoiding cancellation residuals from completed balances; published fiscal totals are unchanged. The completed timings include this implementation, but its incremental peak memory and runtime cost are not isolated. Historical Microcosm memory measurements do not establish the certified port's current requirements; the rehearsal measured one sensitivity worker, so measure available memory before using the two-worker maximum.

On the earlier 11 October resumption, `vm_stat` was checked again and one-minute load was 333.82, then 349.96, later 220.12 on the same 18-CPU host. No survey job was admitted in those attempts. The successful unattended runs reported above completed later at `b31137e`, with all receipt checks retained. New publication writers omit the top-ten concentration diagnostic until nonzero-contributor and recoverable-complement support can be established; cached ten-selected-record labels alone are insufficient.
