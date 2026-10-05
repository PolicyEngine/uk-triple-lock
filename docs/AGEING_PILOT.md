# Static ageing pilot: model v2 part B

**Status: complete current-bundle pilot; part C gates pending.** The 205 full-model treatment jobs are complete and the publication privacy audit passed. The execution requested eight Enhanced FRS slots and zero Microcosm workers. The completed log records 0 initially cached of 205 planned jobs and 205 newly completed jobs. Actual aggregate results appear below and in [AGEING_PILOT_RESULTS.md](AGEING_PILOT_RESULTS.md). The committed dashboard results have not been rebuilt. Ageing remains opt-in; the published pipeline retains `legacy` until part C explicitly enables the combined treatment.

Draft PR: [#23](https://github.com/PolicyEngine/uk-triple-lock/pull/23). Target: `main`, to be retargeted onto part A's `model-v2`. The final delivery records the pushed head. Merge status: pending acceptance gates; merge nothing from this pilot.

## Design and provenance

The pilot uses policyengine 5.3.0 / policyengine-uk **2.90.2** and its certified Enhanced FRS. This fallback was selected while part A was unavailable at the fresh pilot's start around 04:22 UTC on 5 October 2026. Part A's [draft PR #24](https://github.com/PolicyEngine/uk-triple-lock/pull/24) was created at 04:44:26 UTC and now supplies the upgraded branch for part C's rebase. The current pilot tests the static method, not the absolute spending level of policyengine-uk 2.118.0. [METHOD.md](METHOD.md) describes the implemented inputs; [AGEING_RULE_AUDIT.md](AGEING_RULE_AUDIT.md) records programme and legal-cutoff checks.

The population input is [ONS's 2024-based UK principal projection](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationprojections/datasets/z1zippedpopulationprojectionsdatafilesuk), using the same public UK zip as policyengine-uk-data. It covers mid-years 2024–2041 by sex and single age, with ages 105–109 and 110+ combined into 105+. The committed CSV is public OGL data; its SHA-256 is `df91f70d81232225fe5516842390f3de3b2d5e6279b6a762cb28bcf63378229f`. The [provenance manifest](../data/ons_npp_2024_uk_age_sex.provenance.json) records live-download mode, source/workbook hashes and URLs. [ONS_PROJECTION.md](ONS_PROJECTION.md) documents extraction.

Fiscal-year population is `0.75 × mid-y + 0.25 × mid-(y+1)`, representing the October midpoint. Household targets apply those fiscal ONS growth factors to the anchor-year survey margins, rather than imposing raw ONS population levels. Sex-specific cells are five-year bands through 55–59, single ages 60–79, then 80–84, 85–89 and 90+. Bounded minimum-relative-entropy calibration permits ratios 0.2–5 relative to anchor weights and fails when targets are infeasible or not reached to 1e-6 relative. Person and benefit-unit weights follow their household weight.

The pilot explicitly anchors **2025**, the calibration year declared by the [exact data 1.56.16 source](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57). The API requires an explicit anchor or verified dataset metadata. These are **runtime-native 2025 weights**, which remain unchanged at the anchor; this does not establish preserved DWP benefit calibration. The builder materializes calibrated 2025 weights back to 2024 using a different factor from the runtime's forward uprating. The private artifact build manifest was gated. [CALIBRATION_ANCHOR.md](CALIBRATION_ANCHOR.md) records the bundle mapping, public source proof and materialization mismatch. Raked forecasts replace later native weights, which this runtime produces through population uprating. Part C must verify certified calibrated-period incomes and weights and measure the effect of age/type changes on benefit outcomes.

For top-coded data, a deterministic hash ordering assigns age-80 records represented ages 80–105 using sex-specific ONS shares and weighted midpoints. The weighted 80+ population is preserved and other ages stay unchanged. If any original age exceeds 80, the uncapped-data guard retains all original ages rather than spreading genuine age-80 records into another older tail. The report checks must identify whether top-code representation occurred and which supplied head flags were retained.

Represented ages and within-year birthday draws remain fixed across years. A record represents a person of that age in each year's contemporaneous cohort; it is not a surviving individual aged forward. Synthetic birth dates are inferred at 6 October each fiscal year. Model-eligible men born before 6 April 1951 and women born before 6 April 1953 receive `BASIC`, those born on or after the cutoff receive `NEW`, and those below model pensionable age receive `NONE`. Birthday inputs follow the upstream 2.118.0 draw when available. The separate synthetic upstream differential validates the mechanism; it does not replace full population runs on the pilot bundle.

Weights, represented ages and birthday draws are cached privately per dataset, anchor and treatment. One implementation deviation is that annual type arrays are rebuilt deterministically from those cached inputs and the upstream pension-age result once per path, then shared by baseline and both pension rules; they are not persisted across paths. This preserves upstream eligibility readback and policy equality, but does not implement the requested cross-path type cache. Part C can add that cache with an explicit model/eligibility fingerprint.

For recomputed types, the original reported State Pension is repartitioned against the selected type's data-year flat-rate ceiling. The nonnegative excess is additional pension; on `NEW` records it represents protected payments, including inherited amounts already reported. The excess follows September CPI and is identical under the triple lock, plan and baseline for a given path. The model does not simulate contribution histories or newly acquired protected entitlements. Below pensionable age, payable components remain zero.

The eligible data-year components identity passes to the penny, and unchanged-type additional pension is checked against the original model amount. An aggregate audit identified **40 records** with positive reported pension below the installed model's pensionable age. Their reported total cannot equal zero payable components. The all-record identity gate is therefore pending: part C must report and resolve verified misreporting or model eligibility defects through the proper data/model build, without creating payment below pensionable age to force equality.

## Planned treatments and results

The 205 jobs comprise five treatments for the central path and five for each of the exact 40 committed Microcosm-paired expected-value draws, all run on Enhanced FRS. Stratum probabilities are retained, and all 40 draws are distinct in this pilot. The API also supports selection multiplicities. Every treatment is a full model run of both pension rules with common baseline inputs; no fiscal result is scaled.

All pilot spending, gross/net savings and household-income effects, including the four-way contrasts, cover **Great Britain**, excluding Northern Ireland by the household-region mask. Coverage uses the same GB scope. The ONS raking input covers the UK, while these outcome aggregates cover GB. Pilot legacy results must not be compared directly with the committed dashboard's UK headline.

| Treatment | Age/birthday representation | Annual weights | Pension type/additional base |
| --- | --- | --- | --- |
| `legacy` | Original survey inputs | Native | Existing engine pins |
| `frozen` | Common represented ages and birthday draw | Native | Survey type and original additional amount |
| `reweight` | Common representation | Raked | Survey type and original additional amount |
| `types` | Common representation | Native | Contemporaneous cohort and repartitioned residual |
| `both` | Common representation | Raked | Contemporaneous cohort and repartitioned residual |

The core factorial interaction is `both − reweight − types + frozen`. The separate common-input effect is `frozen − legacy`. Both treatments already apply the same integer-age eligibility gate and zero additional pension below that age on 2.90.2. Their difference on this bundle therefore measures represented ages and any head/claimant changes from resolving age ties. The completed regression check confirms that central GB **State Pension totals** under `legacy` and `frozen` match in every year; net fiscal effects can differ, as the common-input contrasts show. On a newer bundle, birthday inputs can also affect eligibility, so the general contrast does not claim to isolate age representation alone. Both contrasts are computed within each path before stratified averaging. Expected-value uncertainty here is paired path-sampling uncertainty, not total model uncertainty.

**Four-way saving table (GB, £bn): publication-approved full-model output.** Expected entries show mean ± path-sampling SE. All values are copied from the final approved aggregate JSON. The generated [results report](AGEING_PILOT_RESULTS.md) contains all thirteen annual paths and spending/coverage tables.

| Sample | Fiscal year | Metric | Legacy | Frozen | Reweight | Types | Both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Central | 2034–35 | Gross saving | 0.529 | 0.529 | 0.614 | 0.570 | 0.658 | 0.003 | 0.000 |
| Central | 2034–35 | Net saving | 0.355 | 0.354 | 0.410 | 0.383 | 0.442 | 0.002 | -0.001 |
| Central | 2039–40 | Gross saving | 0.641 | 0.641 | 0.778 | 0.705 | 0.854 | 0.013 | 0.000 |
| Central | 2039–40 | Net saving | 0.419 | 0.419 | 0.506 | 0.468 | 0.566 | 0.011 | 0.000 |
| Paired expected value | 2034–35 | Gross saving ± SE | 2.527 ± 0.275 | 2.527 ± 0.275 | 2.935 ± 0.319 | 2.723 ± 0.296 | 3.147 ± 0.342 | 0.015 ± 0.002 | 0.000 ± 0.000 |
| Paired expected value | 2034–35 | Net saving ± SE | 1.644 ± 0.180 | 1.640 ± 0.180 | 1.895 ± 0.208 | 1.787 ± 0.195 | 2.055 ± 0.224 | 0.012 ± 0.001 | -0.005 ± 0.001 |
| Paired expected value | 2039–40 | Gross saving ± SE | 8.042 ± 0.057 | 8.042 ± 0.057 | 9.765 ± 0.070 | 8.842 ± 0.063 | 10.723 ± 0.077 | 0.158 ± 0.001 | 0.000 ± 0.000 |
| Paired expected value | 2039–40 | Net saving ± SE | 5.130 ± 0.090 | 5.130 ± 0.089 | 6.165 ± 0.136 | 5.708 ± 0.091 | 6.858 ± 0.137 | 0.115 ± 0.002 | 0.000 ± 0.001 |

The tables describe the completed current-bundle runs; remaining calibration and model gates keep absolute levels provisional.

On this bundle, the combined treatment increases **2039–40 GB expected gross savings from £8.042bn under frozen inputs to £10.723bn**, and net savings from **£5.130bn to £6.858bn**. The interactions are positive: £0.158bn gross and £0.115bn net. The central combined path remains much smaller, at £0.854bn gross and £0.566bn net, which supports using the full paired expected-value design. A substantial coverage gap remains: combined-treatment GB State Pension spending is £129.152bn against DWP's £148.269bn in 2026–27, and £149.556bn against £174.065bn in 2030–31. These observed GB results retain the calibration and model limitations below and must not be compared directly with the dashboard's UK headline.

## Published benchmarks and coverage

[DWP's Spring Forecast 2026 workbook](https://assets.publishing.service.gov.uk/media/69dcdc8c6b695d635c34dcc4/outturn-and-forecast-tables-spring-forecast-2026.xlsx), published on its [2026 tables page](https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2026), was read directly from the committed copy. A live publisher download matched that copy byte for byte: SHA-256 `11a591e4a2144ed6a686be6a9ded4e5d5b3b8d4887bd57c1ff0632bd251009de`.

The workbook's coverage is GB plus overseas, excluding Northern Ireland. Its separate overseas rows allow matched **all-type GB totals** by subtraction. Spending is nominal £bn and caseload is millions, converted from the workbook's £million and thousands. All five model treatments have completed. Selected comparisons appear below; the generated results report contains every covered year.

**The 2024–25 row is backward-raked from the 2025 anchor.** Weights remain unchanged at 2025, while raking changes native 2024 data-year weights. GB State Pension spending is £114.862bn under `reweight` versus £116.097bn under `frozen` in 2024–25. This pilot therefore does not preserve data-year weights; part C must assess this effect alongside the calibrated-input bridge.

| Fiscal year | DWP GB total State Pension £bn | DWP GB recipients m | Five-treatment model comparison |
| --- | --- | --- | --- |
| 2024–25 | 131.254 | 11.885 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2025–26 | 140.442 | 12.116 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2026–27 | 148.269 | 12.152 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2027–28 | 152.847 | 12.041 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2028–29 | 157.761 | 12.142 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2029–30 | 165.775 | 12.417 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |
| 2030–31 | 174.065 | 12.692 | [Completed comparison](AGEING_PILOT_RESULTS.md#matched-gb-dwp-coverage) |

<!-- ageing-approved-selected-coverage:start -->

**Selected matched GB comparisons: base year, 2026–27 and 2030–31.** Differences are copied from the full-model aggregate output; no fiscal scaling or overseas type allocation is used.

| Year | Treatment | Model £bn | DWP £bn | Difference £bn | Model recipients m | DWP recipients m | Difference m |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024–25 | legacy | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | frozen | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | reweight | 114.862 | 131.254 | -16.392 | 10.960 | 11.885 | -0.925 |
| 2024–25 | types | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | both | 114.862 | 131.254 | -16.392 | 10.960 | 11.885 | -0.925 |
| 2026–27 | legacy | 127.498 | 148.269 | -20.771 | 11.193 | 12.152 | -0.959 |
| 2026–27 | frozen | 127.498 | 148.269 | -20.771 | 11.193 | 12.152 | -0.959 |
| 2026–27 | reweight | 129.078 | 148.269 | -19.191 | 11.339 | 12.152 | -0.813 |
| 2026–27 | types | 127.571 | 148.269 | -20.698 | 11.193 | 12.152 | -0.959 |
| 2026–27 | both | 129.152 | 148.269 | -19.118 | 11.339 | 12.152 | -0.813 |
| 2030–31 | legacy | 137.507 | 174.065 | -36.558 | 10.835 | 12.692 | -1.857 |
| 2030–31 | frozen | 137.507 | 174.065 | -36.558 | 10.835 | 12.692 | -1.857 |
| 2030–31 | reweight | 149.192 | 174.065 | -24.872 | 11.750 | 12.692 | -0.942 |
| 2030–31 | types | 137.878 | 174.065 | -36.187 | 10.835 | 12.692 | -1.857 |
| 2030–31 | both | 149.556 | 174.065 | -24.508 | 11.750 | 12.692 | -0.942 |

<!-- ageing-approved-selected-coverage:end -->

**Published GB plus overseas context only:** the workbook does not separate overseas amounts by pension type. These basic/new figures cannot be treated as matched GB benchmarks. New flat-rate spending excludes protected payments, shown separately. Source: the same workbook's nominal spending and caseload blocks.

| Fiscal year | Basic £bn | New flat rate £bn | New protected payments £bn | Basic recipients m | New recipients m |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024–25 | 66.660 | 46.353 | 1.195 | 8.591 | 4.393 |
| 2025–26 | 66.700 | 56.131 | 1.312 | 8.127 | 5.045 |
| 2026–27 | 66.150 | 64.812 | 1.430 | 7.666 | 5.527 |
| 2027–28 | 64.953 | 71.347 | 1.498 | 7.218 | 5.841 |
| 2028–29 | 62.565 | 79.503 | 1.575 | 6.777 | 6.369 |
| 2029–30 | 60.247 | 90.693 | 1.659 | 6.342 | 7.072 |
| 2030–31 | 57.755 | 102.426 | 1.724 | 5.907 | 7.775 |

| Comparison | Published benchmark status | Model status |
| --- | --- | --- |
| GB total spending and recipients, base through 2030–31 | Available above | Completed, five treatments |
| GB basic/new spending and recipients | Unavailable: overseas not separated by type | Completed model aggregates; no matched benchmark |
| Spending/recipients by age | Unavailable in this workbook | Publication-approved model age tables in results report |
| Spending/recipients by country/region | DWP geography benchmarks unavailable in this workbook | Withheld linked family for privacy |
| 2034–35 and 2039–40 spending, recipients and by-type breakdown | Unavailable: no verified long-term benchmark supplied | Completed model aggregates; no matched benchmark |

No overseas type share is imputed and no long-term benchmark is extrapolated. A later verified published source may extend these comparisons; until then they remain unavailable.

## Privacy, review and acceptance gates

Weights, identifiers and survey amounts stay in private `.cache` files. Public outputs contain aggregates only, with a minimum of ten contributing records for any nonzero cell. Zero cells may report zero. Alongside cell suppression, publication requires an input-support audit covering same-year treatment contrasts, all pairs of years within a treatment and changes in treatment contrasts between years. Direct subtractions between different treatments in different years are not separately enumerated. A small age or geography cell in either audit withholds the whole linked age-table or country/region family across treatments, years, paths and policies. A small GB contrast blocks publication. The completed output records the audit's scope and linked-family suppression.

This pinned-input support proof does not prove support for every nonlinear model-derived programme state. Period-derived `birth_year` and Savings Credit eligibility are examples outside the exhaustive input proof. Publication of net fiscal and household-income aggregates assumes that such derived changes do not permit exact recovery of fewer than ten contributors through released contrasts. The proof is specific to the inspected 2.90.2 formula hashes; that assumption and the programme-state scope must be renewed on the upgraded bundle.

Independent Subfleet reviews identified default-treatment, privacy, legacy-control, calibration and run-verification issues. Their fixes and the source-year audit prompted fresh runs; an unfinished or interrupted run is not validation evidence. Review comments and passing unit/synthetic tests do not sign off the population or fiscal gates.

All mandatory independent-review findings, including N1–N6, are fixed. The standard, read-only Subfleet closeout `20261005-025509-ageing-closeout-review` (private report `.cache/ageing-closeout-independent-review.md`), following approved postfix review `20261005-023519-ageing-postfix-review`, approved the current-bundle evidence with no Critical, High or Medium findings and no required corrections. The refreshed audit records **1,960 support comparisons** (160 + 600 + 1,200); age tables are available and the linked geography family is **withheld**. The saved exact-equality check confirms that the financial series and all 160 GB coverage rows from the 205 fiscal jobs remain unchanged from the originally approved publication. Two additional Info followups—a caveat pointer beside the central pension-bill table and a source/hash header for the renderer test log—are being closed at delivery. The acceptance gates below remain pending.

The latest saved publication checks passed **70 guard tests** and **219 renderer tests**. The two synthetic upstream oracle tests separately passed on UK 2.118.0/Core 3.32.16, with **3,008 exact cohort-type comparisons**. The combined regression run passed **366 tests**, with two skipped newer-model oracle tests and 19 warnings. Those two 2.118.0 oracle tests were exercised separately. The headline-results staleness check still fails pending part C's rebuild, so this is not a claim that the entire repository suite passes. Separate full-model engine and worker-equivalence evidence covers two plus three jobs by construction; the canonical publisher binds both original evidence files and their outcomes to the saved calculation-source hashes.

| Gate | Current report status | Evidence needed before acceptance |
| --- | --- | --- |
| Complete paired fiscal design | Passed on current bundle | Repeat after part A/data calibration upgrade |
| Model reads ages/types/residuals and entity weights | Passed on current bundle | Retain all-year readback checks in part C |
| ONS growth targets and runtime-anchor identity | Readback checks passed on native runtime 2025 weights; source calibration year verified | Certify the artifact and calibrated-year weight materialisation; runtime 2025 weights do not restore builder calibration |
| Eligible pension accounting | Eligible identity passes; full all-record gate pending | 40 positive below-SPA reports remain; resolve/report through the data/model build |
| Calibrated GB baseline and available coverage | Current-bundle aggregate comparisons complete; calibration gate pending | State Pension/Pension Credit/Housing Benefit version bridge and certified baseline |
| Engine and worker integration | File-backed legacy/opt-in/equivalence outcomes passed; five jobs by construction; preceding legacy mode verified in source | Repeat upgraded-bundle integration and test longer production worker reuse sequences |
| Final privacy and provenance | Publication audit passed; linked age family available; linked geography family withheld | Renew formula/support proof and independent review on the upgraded bundle |

<!-- ageing-pending-gates:start -->

**Pending gates remain literal:** source build **1.56.16 declares calibration year 2025**, and this pilot anchors native runtime **2025** weights. Those weights **do not restore builder calibration**; the private artifact calibration manifest and calibration preservation remain unverified. **40 positive below-SPA reports** prevent an all-record payable-components identity; matched **age benchmarks are unavailable**, while the model age family passed publication support; **DWP geography benchmarks are unavailable**. The model geography family is also withheld for privacy. None of these gates is closed by the completion of the current-bundle four-way run.

<!-- ageing-pending-gates:end -->

## What part C needs

Part C must retarget this work onto part A's certified model-v2 bundle, supply the verified calibration year explicitly, obtain certified calibrated-period inputs and artifact metadata, reconcile below-pension-age reported pensions, and remeasure the calibrated GB State Pension, Pension Credit and Housing Benefit baseline. The current release's source year is 2025; its runtime-native weights do not reconstruct the builder's calibrated weights. Part C must verify that income and weight materialization reproduce the calibrated period, compare awards with identical age/type/head inputs to isolate that bridge, then measure the demographic changes and run the complete paired design on that bundle.

The audited releases omit Scotland's Pension Age Winter Heating Payment and an explicit basic-pension age-80 addition. Reported additions can enter the residual, but that does not implement the statutory age addition separately. Cohort eligibility and inferred eldest-member/claimant ranking can change with represented ages. These upstream coverage and structural limits must remain explicit. Later retirees reuse survey amounts for people of the same age; pensioners abroad, survival, migration and contribution histories remain outside this static route.

Before enabling ageing in the published pipeline, part C must complete the version bridge, full pilot and independent review, verify any added long-term benchmarks, and perform the one authorized rebuild after the required forecast/statutory input updates. Regenerate results provenance and dashboard assumptions together; pending pilot estimates must not replace the committed headline.

Computing private aggregates on the current pilot anchor:

```sh
python scripts/validate_ageing.py --workers 1 --calibration-year 2025 --plan
python scripts/validate_ageing.py --workers 4 --persistent-workers --calibration-year 2025 -o .cache/ageing_validation.json
```

These commands reproduce the treatment design with four requested slots; they do not alone create publication-ready metadata. Before dispatch, save the full `ageing_validation.validation_plan(calibration_year=2025)` result with `ageing_publication.calculation_metadata(plan)`, including the original calculation head and source hashes. `--plan` prints only a summary. Retain the original aggregate execution report and complete log, the private input audit bound to the same plan, and both real engine-integration and persistent/isolated-equivalence evidence files. This pilot's eight-slot execution used a private driver to retain those files; that driver is not a public CLI feature.

After all jobs and evidence are complete, publish the retained 2025 pilot through the canonical guard, then render that exact approved JSON:

```sh
python scripts/publish_ageing_validation.py \
  --saved-plan .cache/ageing-publication-plan-2025.json \
  --execution-report .cache/ageing-pilot-2025.json \
  --execution-log .cache/ageing-pilot-2025.log \
  --execution-driver .cache/run_ageing_pilot_2025.py \
  --input-audit .cache/ageing-publication-audit-2025.json \
  --integration-evidence .cache/ageing-integration-checks.json \
  --equivalence-evidence .cache/ageing-runner-equivalence.json \
  -o data/ageing_validation.json
python scripts/report_ageing_validation.py data/ageing_validation.json \
  -o docs/AGEING_PILOT_RESULTS.md
```

The saved plan/head must come from before dispatch, rather than a newly reconstructed plan. The publisher checks completed cached jobs, the complete original execution log, hashes/outcomes of both control evidence files and the bound privacy audit; missing evidence blocks publication without starting fiscal jobs. These inputs stay in `.cache`. Only canonical publication-approved aggregates enter `data/ageing_validation.json` and the rendered pilot report. The dashboard's `data/results.json` remains unchanged.

The ordinary CLI permits at most four Enhanced FRS workers. The fresh full pilot requests **eight Enhanced FRS slots and zero Microcosm slots** through the same validation API and cache. Its dispatch log records **zero cache hits out of 205 planned jobs**, so 205 jobs were scheduled for fresh execution. These are requested slots, not a measured maximum of simultaneous processes. Before dispatch, the host check recorded 18 logical CPUs, 128.0 GiB total RAM, 79.43 GiB available RAM, a one-minute load of 7.42 and CPU use of 49.0%. Final metadata records completed-job receipts, initial cache hits and the execution-log hash alongside the private driver hash. The approved output JSON supplies aggregate tables and provenance; it is not a record-level data export.
