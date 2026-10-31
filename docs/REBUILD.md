# The binding rebuild: runbook

The pre-Budget release used policyengine.py 6.2.6 / UK 2.125.1 / core 3.33.0 / Enhanced FRS 1.58.0, publicized in Vahid's post as provisional and model-conditional under ruling (c). The binding rebuild of 29-30 October uses **different data**: Max ruled **d1983 = B** on 24 October, making policyengine.py's national Microcosm UK Budget pair primary, with **Enhanced FRS 1.58.2** as paired sensitivity. Bridge step (b) measures that data-family change. The rebuild finished on 30 October: the primary failed C2 ([C2_BINDING.md](C2_BINDING.md)), so the build took the automatic fallback to (a), ran no paired sensitivity and wrote scenarios only.

## What it waits for

| Gate | What it holds back | Until then |
|---|---|---|
| **d2011 = A: the 2.151.0 pair (microcosm#1396)** | The exact released carrier manifest for national Microcosm cut `microcosm-uk-2024-25-national-20261025T091414Z-a6299504` and its local-area cut, UK 2.151.0 / core 3.33.3 | Released: policyengine.py **6.11.1** (tag `b14ee554`, 27 October 01:30Z), certified by [#720](https://github.com/PolicyEngine/policyengine.py/pull/720) (merge `610ebc42` of reviewed head `99a3e48b`), before d2011's Tuesday 27 October 18:00Z deadline, so its fallback to #715's `a133f37a` / UK 2.147.2 pair was not taken. The eight `datasets.BINDING_*` identities are filled from the tag; preflight certifies only that exact release. |
| **Binding inputs**: AWE on 20 October, September CPI on 21 October, OBR forecast on 28 October | Committed in `593c355cd75d28d50a2bac732e078c1294873b84`, before scoring | Official bytes, release dates, hashes and extraction cells are in [sources](sources.md) and [the extraction record](c2-input-extraction.txt). |
| **d955 = (c): binding C2 failed** | The rebuild automatically takes **(a), scenarios only; no expected value** | The original primary fails test A suspended floor bias: 0.267 exceeds the unchanged 0.25 limit. Passing alternatives are not promoted. [Every check and sensitivity](C2_BINDING.md). |

## Binding C2 verdict: 28 October 2026

The binding run uses `--screen c2 --binding`, the unchanged pre-registered rule
`65343e2ee43a359f056ce5a027739509d32ab49f`, and all 13 complete spring
statutory origins, one a year, including March 2022. Its primary failure automatically selects ruling
**(a)**. The rebuild must omit the expected value and retain the scenario
envelope; there is no further model-selection decision. The committed handoff is
`data/pilot/c2-binding/handoff.json`; [C2_BINDING.md](C2_BINDING.md) records the
scores and provenance. No fiscal rebuild was run for this re-score.

All `fiscal_year_lted` rows and the March long-term workbook remain unchanged.
C2 scores do not read those rows or central-path values after 2030. Future
handoff scenario specs do use the preserved March long-term path; whether a
fiscal rebuild may use it awaits Max's **d2124**, independently of C2's verdict.

## d2011 bundle and two-step bridge

Max ruled **d2011 = A** on 25 October: the binding primary is the certified 2.151.0 national and local-area pair built at [microcosm#1396](https://github.com/PolicyEngine/microcosm/pull/1396) (`67ee2ddf3`). d1983 = B's reason (Microcosm, clean data) holds for it. Its identities, known before the release:

| Identity | Pin |
|---|---|
| UK model/core | `policyengine-uk==2.151.0`, `policyengine-core==3.33.3` (microcosm#1396's `uv.lock`) |
| UK wheel SHA-256 | `5722f55aca3eb88e1a228e95e1a57e3bd70a4d530a5a000991565ebd8955ce35` (`data/certification/d2011-model-wheel.json`) |
| Dataset registry name | `microcosm_uk_2024_25@a6299504` |
| HF repository / revision / path | `policyengine/populace-uk-private` / `microcosm-uk-2024-25-national-20261025T091414Z-a6299504` / `microcosm_uk_2024_25.h5` |
| Dataset SHA-256 | `b96a8cd625b645a409c063b1de5158532708a2f0d3c3897a794a8fb0bbd5064e`, the staged attempt `uk-frs-calibration-attempt-20261025T091414Z-a6299504` |
| Data release manifest | `releases/microcosm-uk-2024-25-national/release_manifest.json` at that revision (`datasets.MICROCOSM_RELEASE_MANIFEST`) |
| Region routing | national to the national file; constituency and local authority to the local-area cut's file, with the bundle's `regional_*` fields naming that cut's release manifest and no `regional_certification` (both halves are on 2.151.0) |
| Filled from the 6.11.1 release (`datasets.BINDING_*`) | carrier `6.11.1`, manifest SHA-256 `ab60903b390e7a765ea6558ec5e2d8fa5aede06b6f735fbf4e4c96109ffd1617`, certifying pull request #720 and merge commit `610ebc42586b7358c41afe4fabec7c67adf17205`, and the 2.151.0 local-area cut: file `microcosm_uk_2024_25_dense.h5`, tag `microcosm-uk-2024-25-dense-20261026T105309Z-c9df4b86`, SHA-256 `cb3712f25b76109ad27b7b0cdf5dee78c55d3b7f55ce7bf207ef1a191da2ae9a` and release manifest SHA-256 `30be47545efd2aa320e30f8d04240cf345aec105fa1d788334770bc4e17c583e` |
| Core coverage | the certificate's core by policyengine.py's rule (`datasets.certified_core`), made stricter: the named `certified_for_core_version` under `core_binding` `certified`, which must equal the bundle's core pin; else the pin (`bundle_pin`, 6.11.0's default), which a named core must equal |

The revision exists on the Hub with the pinned file (LFS SHA-256 and its 342,348,841 bytes checked on 26 October); materialization still verifies the bytes before every use, and the release must name the same artifact. The lock uses the released base carrier `policyengine==6.11.1` without `[uk]`, plus explicit UK 2.151.0/core 3.33.3. The engine constructs `policyengine_uk` directly and loads its own verified artifact. Publication preflight certifies only the exact authenticated release. d1727's Enhanced FRS qualification-ledger route is superseded as the primary; its fail-closed code, [status receipt](../data/certification/d1727-qualification-status.json) and [2.153.4 audit](d1727-upstream.md) stay as history.

**Fallback (not taken).** The pair shipped in 6.11.1 before d2011's deadline, so this fallback was not used; it stays documented, and its identities stay pending. d2011's fallback was #715's `microcosm_uk_2024_25@a133f37a` / UK 2.147.2 pair served with [policyengine.py #699](https://github.com/PolicyEngine/policyengine.py/pull/699)'s area routing: a133f37a's national file, with constituency and local-authority runs routed to the 19 October dense local-area cut `microcosm-uk-2024-25-dense-20261019T000432Z-ee5c2dbe` (built on 2.132.6) on an accepted model mismatch. #715's reviewed candidate head `e02d41bceab57756373b2dc3bcf78635b856ec81` routes national only, so it does not certify the fallback by itself. Its local-area cut is pinned now (`datasets.FALLBACK_LOCAL_AREA`: file `microcosm_uk_2024_25_dense.h5`, SHA-256 `8e10e130…`, release manifest SHA-256 `b9dc7cae…`), and the release must carry #699's `regional_certification` for exactly that mismatch (2.147.2 certified, 2.132.6 built, area receipts uncertified) and `regional_source_manifest_sha256`. Its bundle identities stay pending in `datasets.FALLBACK_*`. If d2011 falls back, fill them with `HUGGING_FACE_TOKEN=… .venv/bin/python scripts/fill_release_identities.py --target fallback --pr <PR> --release <tag> --apply`. Then, in one reviewed commit, move these to the fallback: `config.PRIMARY_DATASET` (the preflight reads the bundle of whichever of `datasets.D2011_PAIRS` it names, here `datasets.BUNDLE_715`); the model pin to `policyengine-uk==2.147.2` and the carrier pin in `pyproject.toml` and `requirements-lock.txt`, with the lock re-resolved as in step 1; CI's install comment; the bridge endpoints and dataset in `data/binding-bridge.pending.json`, and its ready copy; and the d2011 wording in METHOD.md and this runbook. Its [2.125.1-to-2.147.2 audit](d1983-upstream.md) applies.

1. Done for 6.11.1 on 27 October (`--pr 720 --release 6.11.1`): all 32 checks passed at the tag, and all 37 on the installed wheel. After the pair is released, run `HUGGING_FACE_TOKEN=… .venv/bin/python scripts/fill_release_identities.py --pr <certifying PR> --release <tag>`. It reads the UK bundle manifest at the release tag (the release workflow's version commit rewrites it after the certifying merge, so the merge commit's bytes are not the release's) and compares every identity above with it, the revision included. It reads the local-area cut's own release manifest at the cut's tag (or `--regional-manifest FILE`): the cut's build must name that tag, have run UK 2.151.0 on core 3.33.3, and publish the file the bundle routes to, with the bundle's `datasets` entry, regional URIs and any `regional_source_manifest_sha256` matching; a `regional_certification` block refuses. It requires the certifying pull request to be merged, its merge commit to be in the tag, and the tag's manifest to be, byte for byte, what the release workflow writes from the manifest at that commit: it rewrites the carrier version fields, each country's bundle id, the install requirements and the citation, drops `source`, and changes nothing else. It prints the eight `datasets.BINDING_*` values: carrier version, manifest SHA-256, certifying pull request and merge commit, and the local-area cut's file, tag, SHA-256 and release manifest SHA-256. Any difference refuses. With `--apply` (only with `--release`) it checks every file it writes before writing any, then writes those, the carrier version in both dependency files and the ready `data/binding-bridge.json` of step 4. Do not change the model/core/data pins merely to fit a carrier.
   Then re-resolve the lock for the new carrier, keeping every other pin as a preference: save the four comment lines at the top of `requirements-lock.txt`, run `uv pip compile pyproject.toml --extra uk --extra dev --python-version 3.13 --no-header --no-annotate --upgrade-package policyengine -o requirements-lock.txt`, and put the comment lines back. At the preparatory carrier this reproduces all 86 pins exactly. Name any pin other than `policyengine` that moves in the commit; `test_the_lock_satisfies_the_installed_carrier_s_own_requirements` checks the installed carrier's requirements against the lock. After installing the lock, rerun the script without `--apply`, with `--manifest` on the installed wheel's `policyengine/data/bundle/manifest.json`: it then also checks each filled identity, so the installed bytes must hash to the pinned digest, as the preflight in step 3 requires. With the release installed, `tests/test_datasets.py` and `tests/test_budget_bundle.py` require provenance to certify the filled pair.
2. Keep the [2.147.2-to-2.151.0 source audit](d2011-upstream.md) (on top of the [2.125.1-to-2.147.2 audit](d1983-upstream.md)), `check_upstream()` and the parameter/small-household checks passing. UK 2.151.0 adds #2557: benefit uprating follows the previous September's CPI and `path_following` takes its September branch. It lacks #2576 (earnings-linked guarantee/derived HB and Savings Credit, first 2.151.2), and #2340 remains unmerged. Additional pension still takes the engine's path-specific explicit CPI pin. Age-addition handling takes the absent-variable branch.
3. Run certification and the behavioural HB receipt-passport preflight below before survey jobs. Synthetic checks never certify the fiscal result.
4. `--apply` in step 1 writes this; check it by hand. It copies `data/binding-bridge.pending.json` to `data/binding-bridge.json`, fills the released carrier version in the three new endpoint package maps and `pending_release.policyengine_version`, fills `pending_release.pull_request`, `reviewed_head` and `bundle_manifest_sha256`, and sets status `ready`. Commit it. Keep historical baseline pins/SHA, UK/core pins and both artifact hashes fixed. Pending `--validate-only` honestly refuses without launching jobs.
5. Run **(a), model step**: 6.2.6 / UK 2.125.1 / core 3.33.0 → UK 2.151.0 / core 3.33.3, holding **Enhanced FRS 1.58.0** fixed. The new intermediate pair is uncertified. Run **(b), data step**: **Enhanced FRS 1.58.0 → Microcosm a6299504**, holding the same installed packages and engine sources fixed. Only that final endpoint must have released certification. Each endpoint runs the complete central/coverage/frozen forty-path design. Data/from must reuse exactly model/to's receipt; no dataset-family equality is assumed.
6. Review fresh accounting and GB/DWP coverage before feeding a regenerated binding C2 handoff to the full fiscal build. The primary/sensitivity config change alters its input hash: regenerate it through C2, and preserve every historical handoff/receipt byte.

**Microcosm's anchor year.** Both Microcosm cuts anchor static ageing at 2025, their calibration year (#40). Each build solves its household weights at 2025 and writes them at the 2024 data year divided by policyengine-uk's own projection factor (1.0072), so the model's 2025 weights are the solved ones (`build_record.json`'s export readback `weight_year`; microcosm's `weight_year.py`, microcosm#796 A19). a133f37a's entry had said it declared no calibration year.

**d1753 on this bundle.** UK 2.151.0 has neither Savings Credit `maximum` nor either linked projection builder. Tests also cover a `maximum`-present/builders-absent system defensively. Keep its installed **CPI** HB allowances and Savings Credit thresholds as headline. Since #2557 moved `gov.benefit_uprating_cpi` to September CPI, those amounts name `gov.economic_assumptions.indices.obr.lagged_cpi` themselves, so they keep the lagged calendar-CPI projection they had on 2.147.2. The engine still applies the statutory earnings-linked guarantee. Gate linked derivation on the actual builders, not merely on `maximum`. The separate foreground comparison below runs the installed-CPI and explicitly guarantee-linked conventions as complete central pairs of the triple lock and the adjusted Triple Lock; it does not change the default.

```sh
# Main session foreground only, after authenticating and installing the released lock.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
.venv/bin/python -c 'from triple_lock.model_horizon import check_upstream; check_upstream()'
.venv/bin/python -c 'from triple_lock.pipeline import certified_bundle_preflight, housing_benefit_passport_preflight; certified_bundle_preflight(); housing_benefit_passport_preflight()'

# Zero jobs: authenticate ready config, historical source receipt and paired design.
.venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step model \
  --from-receipt data/pilot/J-bridge-certified.json --workers 1 \
  --out data/pilot/binding-bridge-model.json --validate-only

# Both steps rerun from their job cache after a host refusal (scripts/resume_after_host_refusal.py).
# heavy_run.sh stops any command tree whose summed footprint passes HEAVY_CAP_MB (default 20480 MB):
# raise it for each Microcosm run. These ran at 49152 MB on 27 October; the data step's peak tree footprint, coordinator
# included, was 16.7 GiB at one Microcosm worker (data/pilot/binding-bridge-data.json, timings).
# (a) Model step on Enhanced FRS 1.58.0; intermediate remains uncertified.
HEAVY_CALLER=uk-triple-lock .venv/bin/python scripts/resume_after_host_refusal.py \
  --log .cache/resume/d2011-bridge-model.jsonl -- ~/reviews/us-hub/scripts/heavy_run.sh d2011-bridge-model \
  .venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step model \
  --from-receipt data/pilot/J-bridge-certified.json --workers 1 --out data/pilot/binding-bridge-model.json
# (b) Cross-family data step on exactly the same UK2.151.0/core3.33.3 environment.
HEAVY_CALLER=uk-triple-lock HEAVY_CAP_MB=49152 .venv/bin/python scripts/resume_after_host_refusal.py \
  --log .cache/resume/d2011-bridge-data.jsonl -- ~/reviews/us-hub/scripts/heavy_run.sh d2011-bridge-data \
  .venv/bin/python scripts/run_model_v2_j_bridge.py --config data/binding-bridge.json --step data \
  --from-receipt data/pilot/binding-bridge-model.json --workers 1 --out data/pilot/binding-bridge-data.json
# Send Fleet ops the data step's measured memory: per batch, timings[].memory_observed.

# d1753: installed CPI headline versus guarantee-linked HB/Savings Credit alternative.
# Two central-path Microcosm pairs in one process, one at a time (each run is freed before the next).
HEAVY_CALLER=uk-triple-lock HEAVY_CAP_MB=49152 ~/reviews/us-hub/scripts/heavy_run.sh d1983-hb-sc-linked \
  .venv/bin/python scripts/compare_hb_link.py --method linked --execute \
  --output .cache/d1983-hb-sc-linked-comparison.json

# Coverage check: verifies source/row completeness and prints fresh GB/DWP ratios.
# Review those ratios and accounting; no arbitrary numeric threshold certifies coverage.
.venv/bin/python - <<'PY_CHECK'
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

The current State Pension guard audit is [d2011-upstream](d2011-upstream.md), on top of [d1983-upstream](d1983-upstream.md). #36's parameter-consistency and age-addition preparation remains documented in [d1727-upstream](d1727-upstream.md) and its retained receipts; its 2.153.4 linked-projection findings do not describe 2.147.2 or 2.151.0.

## Inputs to update first

Each is a commit before the build. The build refuses a dirty tree, and every input file is hashed into provenance.

1. **AWE (20 October) and September 2026 CPI (21 October).** Refresh the May–July AWE levels (KAB9), published rate (KAC3), and their release metadata from the 20 October vintage. Set `ts_monthly.BINDING_AWE_RELEASE_DATE` to that authenticated release date; retain the pre-Budget release's September vintage in its historical provenance. September CPI is ONS D7G7, published 21 October 2026. It supplies April 2027's CPI leg and additional State Pension uprating. Published May–July earnings supply the earnings leg and the Pension Credit guarantee's next rise, subject to its no-cut rule.
   - Update `data/raw/ons_d7g7_cpi_annual_rate.csv` and `data/raw/ons_d7bt_cpi_index.csv` (the monthly index the models read).
   - Update the April 2027 row in `data/triple_lock_actual_inputs.csv` with the actual September 2026 CPI and published May–July 2026 AWE. Keep CPI consistent with the raw September monthly index, and AWE consistent with the raw May, June and July 2026 levels in `data/raw/ons_kab9_awe_total_pay.csv`; the binding guard checks those matches.
   - Set `config.CPI_PERIOD = "2026 SEP"`.
   - April 2027 is then the larger of September CPI and the published May–July AWE (`config.AWE_PERIOD`).
2. **The Budget-day OBR means** (28 October 2026 forecast).
   - Done in the input commit above: `data/obr_central_forecast.csv` now holds the October EFO's calendar-year CPI and earnings, CPI fan-chart deciles (Chart C2.4), and `q3_yoy` CPI and `q2_yoy` earnings for 2026–2030. October long-term determinants were not published when the source files were collected. Leave every `fiscal_year_lted` row and `data/raw/Long-term-economic-determinants-March-2026-EFO.xlsx` unchanged; do not substitute, extrapolate or relabel. Their fiscal-rebuild use awaits d2124. The binding guard requires the calendar and quarterly means only; C2 scoring does not read the long-term rows.
   - For each 2026–2030 calendar and quarterly CPI/earnings mean, record the official `https://obr.uk/` source URL and explicit OBR Budget/EFO date in its `source`, `note` or `source_date`: `28 October 2026`, `28 Oct 2026` or `2026-10-28`. The binding guard checks the release identity, finite means and committed source bytes.
   - Do not substitute the March 2026 means for the binding C2 score or mix vintages. If the Budget forecast is delayed, the binding score and rebuild wait for it.
   - Update `data/obr_forecast_errors.csv` and the statutory outturns so every spring forecast origin made complete by the new releases is included. In particular, the current March 2022 vintage has only horizons 1–3: add its fourth-horizon CPI and earnings **forecast means**. Those mean rows are needed for C2 even if their calendar outturn/error fields remain unavailable; do not invent an outturn or error. Eligibility still requires all four statutory target years to be observed.
3. **Binding C2 re-score after 28 October, on those committed inputs.** The binding input set is September 2026 CPI, published May–July 2026 AWE and the OBR's 28 October 2026 Budget means, plus every newly complete spring forecast origin. Score April 2022 as the law applied it, with earnings equal to CPI in forecast draws and outturns. Exclude statistic cells fixed by that legal rule; this removes four construction-zero annual gap cells in test A. Terminal paths retain the suspended year in their compounded arithmetic. Published-earnings scores stay beside every C2 result as a sensitivity and never decide the gate.
   - If the original monthly VAR(1) bootstrap primary passes, `--uncertainty-ruling c` runs it; label its expected value **model-conditional** beside the **scenario envelope**. Alternatives that pass are reported individually, with no promotion or averaging.
   - If that primary fails, the same `--uncertainty-ruling c` command automatically takes **(a)**: omit expected value, retain the scenario envelope and record the failure and fallback. There is no later method choice.
   - Run the same post-build Python and dashboard checks under either outcome. The result contracts read the frozen C2 scores and past-years check from `uncertainty_screen.c2_scores`, including the published sensitivity; they do not require legacy `expected_value.backtest` or `expected_value.past_years_check`. If the primary fails, they check the recorded omission reason and scenario envelope, and skip only assertions about an expected value that is intentionally absent. Synthetic dashboard fixtures exercise both outcomes on every tab.
   - The adapter retains **(b)** as an explicit tested input for the original primary with its frozen-screen failure retained. It is not Max's selected rebuild route.

   A run on today's inputs is explicitly a **dry run**, not the binding score and not permission for a fiscal expected value. The adapter consumes the original-primary 160-slot design (161 unique full runs on the dry run's inputs and 160 on the binding inputs, including its identical-rates check). Replacement sampling can repeat indices after an input update; use the handoff's saved distinct counts. A passing binding score adds the exact frozen 40-slot paired subsample on Enhanced FRS 1.58.2; only the dataset role changes. The original-primary ±0.5-point mean paths run independently of adequacy, with the same primary indices, innovations and zero-stratum mass; their extra baseline check may save nonzero. The scenario envelope carries the central path, OBR wedge, recorded historical last-decade replay (April 2017–2026, with its own model years) and those paired mean paths under either outcome. The historical replay retains its period label and is not treated as a future-horizon simulation or included in a common future-year range.
4. **Versions and dataset**: with d2011's release filled (6.11.1), complete the two-step bridge above. The installed packages, primary artifact and released certification must match exactly. Run the final coverage and accounting checks before the binding run. The behavioural Housing Benefit Guarantee Credit passport must still pass: the non-claimant faces the ordinary means test, the claimant receives maximum HB, and reversed receipt flags exercise all three branches. Every publication entry point runs this guard before fiscal jobs.

## Commands

Start from `main`, with the newly released d2011 carrier lock and bridge changes reviewed on the rebuild branch. The lock pins the released carrier, policyengine.py 6.11.1, with UK 2.151.0/core 3.33.3:

Set `HEAVY_CALLER=uk-triple-lock` before every command run through `heavy_run.sh`, `lockrun.sh` or `heavy_queue.zsh`. The caller identity gives this repository access to the Fleet ops reservation [below](#part-j-pre-budget-rehearsal-and-post-budget-sequence).

```sh
git fetch origin main
git switch -c rebuild-budget-2026 origin/main  # not rebuild/…: a branch named rebuild exists
# Complete the bridge and input-update sections above on this branch.
# Commit each step and open a draft PR into main at the first commit.
# The following install uses the newly authenticated d2011 lock.
uv venv .venv --python 3.13
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python --no-deps -e .
source .venv/bin/activate
export HEAVY_CALLER=uk-triple-lock
export HUGGING_FACE_TOKEN=$(agent-secret get HUGGING_FACE_TOKEN_MAX)
# Private dataset bytes stay in .cache/datasets.
python -c "import psutil; m = psutil.virtual_memory(); print(m.available / 2**30, 'GiB free')"   # see Memory

# 1. Check the inputs before anything long.
python -m pytest -q                           # only the documented stale-results assertions may fail (below)

# 2. After 28 October, with the binding macro inputs committed and the
#    released d2011 bundle installed, both bridge steps and coverage reviewed.
#    Check #1927's receipt passport before scoring; real builds also run this guard.
python -c 'from triple_lock.pipeline import housing_benefit_passport_preflight; housing_benefit_passport_preflight()'
python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2

# The same build command handles both C2 outcomes:
# primary passes: model-conditional expected value and scenario envelope;
# primary fails: automatic (a), scenario envelope only, with recorded reason.
# Run it under heavy_run.sh with the one-worker Microcosm ceiling, rerunning from cache after a host refusal
# (each of its ~491 Microcosm jobs is admitted only with 40 GiB available; see Jobs, memory and time).
# HEAVY_CAP_MB is about twice the bridge data step's peak tree footprint (16.7 GiB at one Microcosm worker).
HEAVY_CAP_MB=32768 python scripts/resume_after_host_refusal.py --log .cache/resume/build.jsonl -- \
  ~/reviews/us-hub/scripts/heavy_run.sh triple-lock-build \
  triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2

# Scenarios first (the explainer's ask; Max: "Yes, scenarios first", 28 October 2026). With the binding handoff's
# primary failed, every run of the full build except the paired mean paths (about 11 Microcosm jobs and the
# Enhanced FRS coverage job of ~492) goes into an interim file; nothing else is written. The full build
# then reuses those jobs from the cache: the job key is kind, arguments, engine semantics and packages, so the
# interim and final figures come from the same runs. It needs only the handoff's manifest, so the committed
# data/pilot/c2-binding works before out/uncertainty-c2 (whose draw arrays the mean paths need) is regenerated.
# The build refuses it if the primary passed C2 or with --pre-budget. Commit the interim file before the
# full build, which refuses an uncommitted tree.
HEAVY_CAP_MB=32768 python scripts/resume_after_host_refusal.py --log .cache/resume/scenarios-first.jsonl -- \
  ~/reviews/us-hub/scripts/heavy_run.sh triple-lock-build \
  triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c \
  --uncertainty-handoff data/pilot/c2-binding --without-mean-paths --out data/interim/scenarios-first.json

# Standalone mean-path scenarios, with no adequacy gate:
triple-lock-build --mean-path-scenarios --workers 1 --uncertainty-ruling c \
  --uncertainty-handoff out/uncertainty-c2 --out .cache/mean-path-scenarios.json

# 3. The four-way ageing design, on the rebuilt file's paired draws (aggregates only, into .cache; see below).
python scripts/validate_ageing.py --plan
HEAVY_CAP_MB=32768 python scripts/resume_after_host_refusal.py --log .cache/resume/ageing.jsonl -- \
  ~/reviews/us-hub/scripts/heavy_run.sh triple-lock-ageing \
  python scripts/validate_ageing.py --workers 1 -o .cache/ageing_validation.json
#    If the primary failed C2 and the build has no expected-value section,
#    run this central-only command instead of the paired design above:
python scripts/validate_ageing.py --central-only --workers 1 -o .cache/ageing_validation.json

# 4. Check the file before committing it.
python scripts/check_assumptions.py data/results.json
python -m pytest -q                           # now nothing may fail
(cd dashboard && bun install --frozen-lockfile && bun run test --maxWorkers=4 && bun run lint && bun run build)
```

The lock has no `pytest-xdist`, so the suite runs serially (about 24 minutes in CI).

For the pre-Budget **dry run** only (draws and scoring, zero PolicyEngine jobs):

```sh
python -m triple_lock.ts_uncertainty --screen c2 --output out/uncertainty-c2-dry-run
```

Omitting `--binding` labels the handoff and scores as a dry run. Do not use that handoff for the binding rebuild. Commit the updated macro/model/data inputs before the binding score; commit its resulting handoff and score provenance before the full build.

`triple-lock-build` caches every job (`.cache/jobs`). An interrupted build resumes where it stopped, and the job key changes only with what a job computes.

Step 3 reads its paired draws from the file it is pointed at (`data/results.json` by default) and rebuilds each draw from the central path, failing if a draw no longer reproduces the inputs the file records. So it runs after the build, on the rebuilt file. Run on the committed file once the inputs have changed, it fails, by design. A passing d1983 C2 build records the Enhanced-FRS-paired subsample (the frozen handoff retains its historical “Microcosm-paired” wording): per path, `times_drawn_sensitivity`; per stratum, `sensitivity_paths` and `probability`; and `draws.n`, `seed`, `shocks` and `form`. The validation reconstructs that recorded form. The original-primary design includes stratum zero explicitly, so its mass is counted once. The validation has six modes: `legacy`, `frozen`, `reweight`, `types`, `both`, and the `total` population-only control. Its `both` path runs share the build's cache entries (`ageing_validation.canonical`), so today's design adds the other five modes' central and 40 paired path runs (205) and six coverage jobs, whose years differ from the build's. The four-way factorial remains frozen/reweight/types/both; legacy and total are controls. A failed-primary build has no paired expected-value subsample, so use `--central-only`.

## Interim pre-Budget release (before the binding rebuild)

This section describes the historical certified pre-Budget release, reproduced only at its original source and lock. Its 6.2.6 / 1.58.0 Enhanced FRS primary and earlier Microcosm sensitivity remain as published under Max's recorded ruling (c). The current binding source selects different datasets and must use the d2011 sequence above. Its expected value is **provisional and model-conditional**: the original primary passes the registered C2 dry run on current inputs (4 of 6 terminal years, 80% annual coverage), with the full paired Microcosm cross-check. The binding test follows the Budget inputs; failure removes the expected value. A scenarios-only interim release may use (a). The obsolete public pre-Budget (b) route is refused.

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

The dataset roles have changed. Counts below use the binding handoff's original-primary design: 160 sample slots and one extra zero check, which give 160 distinct full runs (`unique_full_runs` in `data/pilot/c2-binding/handoff.json`). C2 scoring starts **zero PolicyEngine jobs**; mean-path scenarios do not wait for adequacy. Only the sensitivity dataset changes for its exact forty paired slots.

| Stage | Microcosm primary jobs | Enhanced FRS 1.58.2 sensitivity jobs |
|---|---:|---:|
| Central path | 1 | 0 |
| Coverage | 1 | 1 |
| Original-primary baseline, reused for expected value only after C2 pass | 160 | 40 after pass; 0 after failure |
| Paired mean-path scenarios | 320 | 0 |
| Four trajectories and four past-year cases | 8 | 0 |
| OBR wedge | 1 | 0 |
| **Build under c, primary passes C2** | **491** | **41** |
| **Build under c, primary fails → automatic a** | **491** | **1** |
| Ageing validation after pass, reusing the build's both paths | 211 | 0 |
| Ageing validation after failure, central only | 11 | 0 |

For updated inputs let `U` be original-primary `unique_full_runs` (including the extra check), and `V` the distinct indices in the frozen 40-slot sensitivity. The binding build has `3U + 11` **Microcosm** jobs under either C2 outcome; Enhanced FRS adds `V + 1` after a pass, or one after failure. Validation adds `5(1 + V) + 6` Microcosm jobs after pass, or 11 after failure. Standalone mean-path scenarios have `3U` Microcosm jobs. Cache hits and replacement-draw duplicates reduce process launches.

**Runtime at one Microcosm worker.** The binding data step ([receipt](../data/pilot/binding-bridge-data.json), `timings`) ran on 27 October on Microcosm a6299504 with policyengine-uk 2.151.0 and one worker. Its 41 cold path jobs took 192–259 s each (median 213 s), and its coverage job 72 s. Its peaks were a tree footprint of 16.7 GiB, a job footprint of 16.3 GiB and job resident memory of 17.6 GiB. At the median, one worker runs the build's 491 Microcosm jobs in about **29 hours**, and the validation's 211 after a pass in about **12.5 hours** more. That is an estimate: not every build job is a data-step path job, as the mean-path variants, trajectories and OBR wedge show. The earlier **84-hour** figure came from the 12 October rehearsal's two cold jobs (556 s and 672 s, mean 614 s), on an earlier cut and model. Fleet ops kept the build at one Microcosm worker on 27 October. A second needs 80 GiB available at a batch start (and each slot refill 40 GiB beyond what the other running job may still allocate of its 40 GiB), and the host did not reach that in the Budget windows.

**Capacity estimate for Fleet ops, derived without survey jobs.** The old reservation assumed 3 Enhanced FRS plus 2 Microcosm workers. Keeping role caps of 3 primary plus 2 sensitivity would now mean **3 Microcosm plus 2 Enhanced FRS** workers. Across concurrent work, filling all five reserved slots at the historical per-worker peaks (31.8 GB and 6 GB) gives **107.4 GB**, versus the old **81.6 GB**: **25.8 GB / 31.6% more**. These are reservation-wide sums. The frozen `expected_value.build` schedules primary and sensitivity phases sequentially: its three-primary/two-sensitivity worker estimate is `max(3 × 31.8, 2 × 6)` = **95.4 GB**, excluding coordinator/other-process memory. At the documented one-primary/one-sensitivity caps, that phase maximum is **31.8 GB**. These are historical-peak extrapolations. For a6299504 and 2.151.0, the 27 October bridge measured only the data step's path and coverage jobs, at one worker (a 16.7 GiB peak tree footprint; see the runtime paragraph above). Other job kinds (the build's mean-path variants, trajectories and OBR wedge, and ageing validation), concurrent Microcosm workers and the net-support fix's incremental cost remain unmeasured. Code admission requires **120 GiB available** for three concurrent cold Microcosm jobs (40 GiB each), compared with 80 GiB for two. Start the main session at **`--workers 1 --sensitivity-workers 1`**, with a 40 GiB admission floor, and have Fleet ops review capacity before increasing it. The bridge likewise caps Microcosm endpoints at two, uses Microcosm slots and scales its before-batch floor to 40 GiB per concurrent Microcosm job; each slot keeps 40 GiB for the one job it admits beyond what the batch's other admitted Microcosm jobs may still allocate, and its monitor keeps 8 GiB while the batch runs ([Host admission](#host-admission-memory-floors-and-the-load-limit)).

The historical rehearsal timings at the end of this runbook used the opposite data roles and an earlier cut; they do not forecast the binding runtime. The capacity estimate ran no survey or Microcosm simulation of its own; the runtime paragraph's measurements come from the bridge receipt.

The validation's complete design has 252 labels (246 path runs and six coverage jobs); 211 above is the additional work after reusing the build's 41 `both` paths. Repeated indices can further reduce unique cache jobs. Its central-only design has twelve labels before reusing the central `both` path. The separate part E evidence pilot also has 252 full-run labels, with different treatments including the full-new bound; it executed 41 six-treatment Enhanced FRS batches and six coverage jobs (47 process jobs), capped at three batch workers while at least 40 GiB was available and load was below about twice the CPU count, the operator rule at the time. Its driver has no host check of its own; the current limits are in [Host admission](#host-admission-memory-floors-and-the-load-limit). That optimization shares pristine setup only: every treatment and policy has independent inputs and parameters, with full-horizon calculations in their original order. It does not change ordinary build or Microcosm jobs.

Part E publishes the ONS total-only control to address Vahid's population-total point. The comparison is `reweight_minus_ons_total`: the two controls' target totals can differ, so it is not a fixed-total estimate of the age/sex margins alone. A matched-total supplement is a possible follow-up; its runs and results are outside this closeout.

The corrected full-new support receipt also has a separate six-job coverage-only recipe, `scripts/run_model_v2_e_coverage.py`, at its own frozen head. This reruns all nine coverage years for each original E treatment and counts actual stored flat-rate changes, excluding already-full re-typed amounts. It records source/data/package hashes and all 162 country support receipts. When a complete `--coverage-results` artifact is supplied, the E driver validates it before starting any job and schedules only the **41 fiscal batches**, skipping the six obsolete coverage jobs. The assembled evidence still has **252 labels**: 246 fiscal labels at their original source and six fresh coverage labels at their separately recorded source. Without the replacement, the default remains 47 execution jobs and 252 labels. At most three Enhanced FRS coverage workers are permitted; allocate slots against other active jobs.

Once those full jobs and proofs are complete, select stored aggregates into a reviewable table with:

```sh
python scripts/render_model_v2_e_tables.py --input data/pilot/model_v2_e.json \
  --output docs/pilot/E-fiscal-tables.md
```

The renderer selects the saved aggregate tables and preserves linked suppression; it computes no mean, contrast or SE.

**Binding-run guards (Vahid's review items 2–4).** Default to **one Microcosm primary worker** (`--workers 1`) and one Enhanced FRS sensitivity worker until measured current-cut peak memory supports more. Historical peaks were about 6 GB for Enhanced FRS and 31.8 GB for Microcosm; the latter predates the net-support changes. The 27 October bridge measured peak tree footprints of 8.7 GiB on Enhanced FRS 1.58.0 (model step) and 16.7 GiB on Microcosm a6299504 (data step), one worker each. The 12 October rehearsal ran two cold Microcosm paths sequentially (556 s and 675 s) but measured **no worker peak memory**. Sources: `~/.claude/scheduled-jobs/uk-triple-lock-rehearsal/state/logs/rehearsal-sample-1-1791792698.log` and the rehearsal worktree's `.cache/J-rehearsal/sample-receipt.json`; available-memory snapshots are host headroom.

`jobs.py` applies `host.assess` before uncached batches (40 GiB; 40 GiB × `min(workers, uncached Microcosm jobs)` for Microcosm) and after each slot acquisition (40 GiB beyond what the batch's other admitted Microcosm jobs may still allocate of their 40 GiB, recorded as `outstanding_reservations_gib`), with load limit `TRIPLE_LOCK_MAX_LOAD_PER_CPU` × CPUs (default 6). Job cache records and `provenance.model.host_admission` retain decisions; `host_admission_cache_hit` marks reuse without a launch. Fiscal cache keys are unchanged; explicit Part J callbacks and runners retain their own guards.

The **historical pre-Budget release** pins KAB9 and KAC3 to **15 September 2026**, before October revisions. Reproducing that release uses those archived bytes; [sources](sources.md) gives the download and rounding-interval rules. The **binding rebuild** instead uses the authenticated **20 October 2026** release described in Inputs to update first: both source files, their release metadata and `ts_monthly.BINDING_AWE_RELEASE_DATE` have been updated together before binding C2 scoring. The loader checks and records that required October vintage. A moved Budget requires one edit to `ts_uncertainty.C2_BUDGET_DATE`; source-date matching and diagnostics derive from it.

### Host admission: memory floors and the load limit

The Part J runners, `scripts/run_model_v2_j_bridge.py` and `scripts/run_model_v2_j_rehearsal.py`, admit a model job through one shared rule (`triple_lock.host`). They refuse when available memory is below the runner's floor, or when one-minute load is above `TRIPLE_LOCK_MAX_LOAD_PER_CPU` × logical CPUs. A reading that is not a finite number also refuses. They check before each batch, again inside each acquired worker slot, and every five seconds while jobs run; a refusal stops the running children and starts nothing new. A job the refusal stops counts as not run, not as failed: `kill_children` marks each job process it finds still running before it signals it, and `jobs._run_isolated` counts a marked job ended by SIGTERM or SIGKILL as not run. Any other exit is the job's own failure, including a kill the build did not send that is only classified after the build began stopping, so such a run is never retried as a refusal. The bridge's five-second check reads only the host. Its memory observer runs on a separate thread, so a slow or failed observation never delays or stops a check. If the check itself cannot read the host, the bridge stops the batch and fails with that error; it is not a host refusal, so it is never rerun as one. Nor is a batch that fails for its own reason, such as a corrupt cache record found before any job runs, while the check finds the host saturated: only the scheduler's report of its jobs is passed on as a refusal.

Every reading is host-wide available memory (`psutil`). It already excludes what the run's running jobs hold, but not what a job admitted a moment ago is about to load. So a floor reserves room only for memory still to come:
- before a batch, 40 GiB for each cold job;
- in a slot, 40 GiB for the job it admits, plus, for each other admitted Microcosm job, its 40 GiB less what its process holds now (`jobs.ColdReservations`; all 40 GiB while that process has not started or cannot be read). Each job's memory is read again after the host reading and credited at the smaller reading; if that leaves more than 1 GiB (`jobs.RECHECK_GIB`) further outstanding, because a job freed memory in between, the host is checked again;
- while the batch's own jobs run, only the host's 8 GiB safety floor.

Slots admit one at a time, from the host reading to the registered reservation, so two slots cannot admit on the same headroom. The fiscal build's scheduler (`jobs.run_jobs`) uses the same reservations. Until 25 October the bridge applied its batch floor in each slot and in the monitor, counting its own resident jobs against room reserved for them. On the host at 23:55Z on 24 October (54.5 GiB available, load 86), that would have stopped a one-worker Microcosm data step once its worker loaded (about 25 GiB left, below 40). With two Microcosm workers, the second slot would have needed 80 GiB with the first job resident. The first correction kept 40 GiB per slot. The 25 October review showed two slots could then each read the same 60 GiB, left after other work grew past the batch's 80 GiB gate, and admit two 40 GiB jobs. The reservations close that. `tests/test_bridge_memory.py` states the rules as properties:
- on the real gate, scheduler and monitor, a batch completes exactly when its gate, each admission and the running floor pass;
- for any interleaving of admissions, loading, finishes and changes in other work, a slot admits exactly when available memory covers its floor beyond what the running jobs may still allocate. So each admission leaves room for every admitted job to reach its budget;
- for running jobs whose memory rises or falls during an admission, a slot that admits had, at the deciding host reading, its floor beyond what they could still allocate then, less at most 1 GiB.

| Runner | Memory floor | Load limit |
|---|---|---|
| Bridge | 40 GiB per concurrent Microcosm job before a batch (otherwise 40 GiB); 40 GiB in each slot beyond the other admitted Microcosm jobs' outstanding reservations; 8 GiB while jobs run | per-CPU limit × CPUs |
| Rehearsal | 40 GiB before an Enhanced FRS batch and in each slot; 40 GiB × `min(workers, uncached Microcosm jobs)` before a Microcosm batch; 8 GiB while a job runs | per-CPU limit × CPUs |

The per-CPU limit defaults to **6**, the threshold Subfleet's own guard uses for background work: **108 on this 18-CPU host**. Set `TRIPLE_LOCK_MAX_LOAD_PER_CPU` to change it, or pass `--max-load-per-cpu` to either runner (the flag wins). A blank variable means the default. A zero, negative or non-finite value stops the runner at startup, before planning or any job. It is never read as "no limit".

The memory floor protects the host and the run. On a shared host, load measures contention, not danger. Fleet ops measured this host on 11 October: with about 90 sessions, one-minute load sat at 150–350 for much of the day. The old cutoff of twice the CPU count (36) stopped Part J with 57–65 GiB still free. A load of 66.11 now passes. Readings of 220–350 still refuse, so the post-Budget run also relies on the Fleet ops reservation [below](#part-j-pre-budget-rehearsal-and-post-budget-sequence).

New receipts written by the current runners record the limits they applied:
- the bridge in `provenance.host_admission` (including `running_minimum_available_gib`) and in each batch's `timings[].host_before`;
- the rehearsal in `host_admission` and in each `host_checks` entry.

The entries are `minimum_available_gib`, `max_load_per_cpu`, `load_limit` and `admitted`.

The bridge also measures memory while each batch runs, in `timings[].memory_observed`:
- `minimum_available_gib`, the lowest host reading of the safety check, which runs every `interval_seconds` (5) and reads only the host (`samples` counts its readings);
- from the separate observer, whose readings each start `interval_seconds` after the previous one finished (a slow reading lengthens its own cycle, never the safety check's): `observations` and the fields below, plus `observation_errors` and `first_observation_error` when the process table cannot be read, and `footprint_errors` and `first_footprint_error` when `footprint` fails, times out (10 seconds) or exits non-zero (that observation still records resident memory, with null footprint fields);
- `maximum_jobs_rss_gib`, the largest summed resident memory of its job processes, and `maximum_coordinator_rss_gib`, its own;
- `maximum_tree_footprint_gib`, the largest macOS `phys_footprint` summed over itself and its job processes, which is what `heavy_run.sh` counts against `HEAVY_CAP_MB`;
- `peak_job_footprint_gib`, the largest kernel lifetime footprint peak (`phys_footprint_peak`) of any job process, as of the last sample;
- `peak_finished_job_rss_gib`, the kernel's high-water resident memory of the largest job process finished so far in the run (`getrusage`).

Resident memory excludes compressed and swapped pages, so under memory pressure it understates a job's footprint; the footprint fields count them (they are null off macOS). A slot credits each running job with its resident memory. For compressed and swapped pages that errs safe: a smaller reading leaves a larger reservation. For pages a job shares with other processes it does not: they count as held, though copying them later adds physical memory that resident size does not show. On 25 October a process importing the locked model and its libraries measured 0.252 GiB resident against a 0.225 GiB footprint; the binding data step records both measures for a loaded worker. The reservations have three further limits. On macOS `psutil` 6.1.1 reports available memory as inactive plus free pages, so a running job's own inactive pages can count as available while its resident memory is also credited as held; with one Microcosm worker, as the reservation sets, no other job in the batch is credited at all. Reservations are per process: a build and a bridge running at once could each admit a job on the same headroom, so the runbook never overlaps them. The historical rehearsal runner keeps its original admission (40 GiB in each slot, no reservations), because its receipts record its source; reproduce its Microcosm stages with one worker. The binding data step at one worker is the first measurement of a Microcosm worker on a6299504 / 2.151.0. Read its peak before raising `--workers` for the build, and re-set `HEAVY_CAP_MB` to at least 1.3 × the measured tree footprint (Fleet ops' rule: a ceiling trip closes heavy slot 2 for everyone for an hour). The limit is operational. It is in no job's cache key, recipe hash or execution snapshot, so changing it reruns nothing.

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
- **Vintage mix: resolved by d2124 (A, 28 October 2026).** The rebuild uses the October 2026 EFO to 2030 and the March 2026 long-term determinants after it, labelled on every figure, and reruns the post-2030 parts when the October determinants land. `tests/test_model.py::test_central_path_sources` states this as an intended exception:
  - it checks the fiscal-to-calendar conversion against the March 2026 EFO's own calendar figures (Tables 1.6 and 1.7 in the committed workbook), the determinants' vintage, to within 0.001;
  - it requires `conversion_check_max_abs_error`, which now compares the March determinants with the October calendar rows (0.01455), to exceed 0.001, so the test fails when the October determinants land and the exception must go;
  - on the October path, forecast September 2027 CPI (3.382%) sets April 2028's rise, the 2.5% floor sets April 2029–2031, and the March determinants' own 'Triple lock' row still reads 2.5% for all four. The OBR wedge therefore pays that row only from April 2032 and the central path's rates before it (`trajectories.obr_premium_spec`, `tests/test_obr_wedge.py`).
  `central.py`, `config.py` and `obr_central_forecast.csv` are unchanged: the binding handoff fingerprints them.
- **Calendar 2026 growth: October, set in the rebuild.** `central.py` leaves 2026 calendar growth at the installed model's (policyengine-uk 2.151.0) on every path, while the October EFO's 2026 row (CPI 3.1128%, average earnings 3.733%) is committed but unread, because `EFO_YEARS` starts in 2027. d2124's "October EFO to 2030" and the no-mix rule above cover 2026 too, and the Budget dashboard uses the October 2026 figures. Before any fiscal run, the rebuild sets 2026 calendar CPI and earnings from that row in `engine.py`, extends the path-following checks to 2026, and records the source. The C2 verdict does not depend on it. The change stays outside `central.py`, `config.py` and the forecast CSV so the binding handoff remains valid; if that proves impossible, the handoff is regenerated under the unchanged rule and the change is disclosed.
- **Pension Credit guarantee input.** The guarantee's next rise follows the path's statutory earnings: for 2027–2030, the EFO's April–June average earnings growth (OBR's national-accounts measure, the same proxy as the triple lock's earnings leg). The Budget dashboard's policyengine-uk run on the October forecast uses its own May–July AWE projection instead (3.027% for 2027 against 3.296% here). The triple lock rises agree; the guarantee's April 2028 rise does not. The rebuild discloses this in METHOD and the limitations.
- Every run's `fixed_inputs.population` is `{"weights": "ons_projection", "ages": "survey_year", "pension_types": "cohort"}` on the Microcosm primary, whose ages need no adjusting (`"ages": "adjusted"` on the Enhanced FRS, whose top-coded tail gets represented ages), and the assumptions strip is worded from it (`pipeline._population_item`).
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
For this C2 task's handoff report, the addendum permitted the exact named stale-results assertions and the d2124 vintage-mix assertion, which now passes as the intended exception above. That task exception never expanded CI's allowlist.
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
stale-assertion exceptions accepted by CI on PRs into `main` while the committed file explicitly remains a provisional pre-Budget dry run with no binding authorization. Ready PRs use the same finite allowlist; main remains strict. The d2124 vintage mix is not an allowlisted stale assertion: `test_central_path_sources` states it as an intended, labelled exception and passes. Once a binding file replaces the retained fiscal results, exit code zero and all tests passing are required. Interruptions, collection errors, internal
errors, missing completion evidence and every other failure fail CI.
No history fetch is needed in the checkout workflow.

## Part J: pre-Budget rehearsal and post-Budget sequence

The historical rehearsal used the pre-Budget 6.2.6 / 1.58.0 certified bundle. Reproducing that historical run uses that exact lock; the binding run uses d2011's pair instead. The commands in this subsection reproduce the historical rehearsal at its original source and lock; the current foreground commands above control the binding rebuild. Its numbers are not for quoting. It never writes `data/results.json`, its dashboard copy or scenario publication files. The C2 dry handoff remains `run_kind: dry_run` with `expected_value_authorized: false`; the rehearsal adapter retains the frozen ruling (c) checks and original-primary design. A passing diagnostic screen does not authorize a binding build.

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

The post-Budget rebuild runs inside the Fleet ops capacity reservation **`triple-lock-rebuild-2026-10`**, window **2026-10-29T00:00Z to 2026-11-04T00:00Z** (Fleet ops moved the end from 2 November on 25 October, for the one-worker Microcosm runtime). While it holds, Fleet ops' session cap drops to **12**, and only its holder, `uk-triple-lock`, passes `reservation.py allowed`. `python3 ~/reviews/fleet-ops/tools/reservation.py status` shows whether it is in force. Fleet ops found load can stay above 36 even at that cap, which is why the runners use the shared limit above.

The exact post-Budget order is:

0. If the inputs and the certified environment are ready before 29 October, start the hold early, so it is in force before the step 3 model jobs:

   ```sh
   python3 ~/reviews/fleet-ops/tools/reservation.py ready triple-lock-rebuild-2026-10
   ```

   A `ready` mark brings the start forward only; it cannot extend the window past 4 November.
1. Branch from `origin/main` and open a new draft PR into `main` at the first commit. With d2011's release filled (6.11.1), complete the upstream re-hash, passport preflight, model bridge, data bridge and coverage review above. Commit AWE (20 October), September CPI (21 October), the OBR forecast (28 October) and newly complete backtest origins with official source bytes and release identities. Recheck the certified lock and guards after those changes.
2. Run the **binding C2 re-score**, using `python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2`. It is not a separate launchd label. It is the `uk-triple-lock-c2` step inside the loaded launchd job `com.maxghenis.triple-lock-2027`, which runs daily at 08:35. From **29 October 2026**, or the day after a moved Budget, that job dispatches the step as a Subfleet hard-tier build in this repository. It does so once its `budget-check` step has ended DONE or WAITING_ON_MAX. The step stops at the C2 verdict; it does not run the fiscal rebuild. The binding-input guard remains mandatory when the job invokes the command. Commit the resulting binding handoff and scores before model jobs.
3. Run `triple-lock-build --workers 1 --sensitivity-workers 1 --uncertainty-ruling c --uncertainty-handoff out/uncertainty-c2` on the certified bundle. Primary pass permits only its model-conditional expected value beside the scenario envelope; primary failure automatically uses (a), scenarios only. Run the paired four-way validation after a pass, or `--central-only` after a failure. Check accounting, coverage, source/input/provenance bindings, full pytest and dashboard checks.
4. Obtain independent review of the rebuilt fiscal aggregates, C2 outcome, coverage and limitations, resolve findings and repeat to approval. Keep the new rebuild PR draft until independent review approves; mark it ready and leave merging to the reviewer.
5. After reviewed results are accepted, update the paper and dashboard together, including scenario-envelope wording and Pension Credit/HB/CTR coverage. Re-run their checks. Part J rehearsals and historical pilot figures do not supply publishable replacements.
6. Once the rebuild and its review in step 4 are finished, release the reservation so the fleet comes back early:

   ```sh
   python3 ~/reviews/fleet-ops/tools/reservation.py release triple-lock-rebuild-2026-10
   ```

   Otherwise Fleet ops' session cap stays at 12 until 2026-11-04T00:00Z.

The two bridge steps and the HB/Savings Credit pair run earlier, in their own protected single-worker reservation **`uk-tl-bridge-2026-10-27`**, Tuesday 27 October 07:00Z to 18:00Z. Start each step only if it can finish by 18:00Z, when the Budget final regeneration begins. Never mark this one `ready`: it would overlap the Budget reservations. Release it when the steps finish:

```sh
python3 ~/reviews/fleet-ops/tools/reservation.py release uk-tl-bridge-2026-10-27
```

The historical pre-Budget pins and release hashes are in [J-certification](pilot/J-certification.md), and the source changes are in [J-upstream](pilot/J-upstream.md). The version bridge and all three rehearsal stages subsequently completed at execution head `b31137e`. The [completed verification receipt](../data/pilot/J-completed-verification.json) binds the completed artifacts; the [model-step bridge](../data/pilot/J-bridge-model-step.json), [certified bridge](../data/pilot/J-bridge-certified.json) and [GB coverage against DWP](../data/pilot/J-coverage-gb-dwp.json) retain only the permitted aggregate publications. They are **pre-Budget and not for quoting**. [MODEL_V2_PILOT](MODEL_V2_PILOT.md) records the numerical bridge and coverage interpretation. Rehearsal fiscal values remain private. Historical memory/runtime estimates above remain historical context.

The full build, standalone mean-path and single-scenario entry points, and real ageing validation enforce the exact certified client/model/core, primary pin and applicable certification evidence before model jobs. For the historical bundle that evidence is its released carrier manifest; the binding route requires the exact released carrier manifest of d2011's pair and its Microcosm artifact. The old d1727 qualification-ledger route remains closed and historical. Their provenance keeps that gate beside the behavioural Housing Benefit passport. Paired ageing additionally requires the source's exact certified packages, dataset SHA and manifests; the old pilot cannot supply that source. The version bridge verifies the retained pilot against its independently pinned historical content before reusing figures; an initially consistent but edited pilot is rejected, including under optimized Python.

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
