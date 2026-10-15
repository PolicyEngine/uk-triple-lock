# Model v2 pilot evidence

**Pilot on an uncertified data/model pair; not for quoting.** The primary pair is policyengine-uk **2.120.0**, policyengine-core **3.32.16**, and Enhanced FRS **1.56.16**, built on model **2.89.2**. These records do not certify that pair or replace `data/results.json`. Max decided **d955 = (c)** and **d778 = yes after the uk-data batch** on 5 October. The rebuild now pins the released certified bundle described in [part J](pilot/J-report.md); these historical figures retain their original versions.

[GB versus DWP coverage](../data/pilot/coverage_gb_dwp.json) and its [support audit](../data/pilot/d_support_audit.json) are committed. The actual calculation export is `498d970123adff4e8f05908e17c7b366ba71a28c`; package, dataset, macro-input and source hashes are recorded. Matched GB benchmarks remove overseas spending and recipients from the committed Spring 2026 workbook. Its forecast benchmarks cover 2026–27 through 2030–31. Basic/new components have no matched GB benchmark because overseas is separated only for their combined total.

The audit replays the archived full PolicyEngine UK coverage runs, checks contributor counts, and binds the published coverage file to the receipt hash. Current `pipeline.redact_records` changes neither file. Privacy tests reject record identifiers, weights, amounts and demographic arrays; nonzero cells require at least ten records, with linked-cell suppression. Retained `both` spending and recipients reproduce exactly through 2034–35. In 2039–40, State Pension and caseload totals still match, while some means-tested spending differs. The receipt discloses this limitation.

The [version bridge](../data/pilot/version_bridge.json), [integrated UK/GB savings](../data/pilot/integrated.json) and [Microcosm central aggregates](../data/pilot/microcosm_central.json) preserve D's retained figures without scaling. `0a67899` commits their completed publication binding and [national fiscal support receipt](../data/pilot/d_national_fiscal_support.json), with **52 privacy/evidence tests passed** and the historical-driver check passed. D's Enhanced FRS and Microcosm `legacy` runs used `498d970`; Microcosm `both` used `30318c4f9d1a5fdba290371dc5ab56bd1f064c0a`. Part A's 2.118.0 bridge used `432bb795d6eb28a3c6968de1c41a5008997e4812`. Review heads are never substituted for calculation commits. [AGEING_PILOT_RESULTS.md](AGEING_PILOT_RESULTS.md) and [ageing_validation.json](../data/ageing_validation.json) are the **2.90.2** record, with numerical values unchanged.

The per-path national fiscal contributor audit was stopped before completion as a scope cut: national fiscal totals draw on thousands of records (the Microcosm support audit has a minimum of **9,977 contributors per positive cell**, while the Enhanced FRS central cold receipt has a minimum of **1,035**), so per-path audits of them add nothing. The completed coverage audit remains. D's fiscal figures are published unchanged with a **£1m (£0.001bn)** independent-run tolerance. Replays at D's own calculation heads match gross to four decimal places and net within **£0.0003bn**: 2039–40 UK net is **0.6330** versus retained **0.6332** for `d_both`[^hb-gc-passport], and **0.4681** versus **0.4683** for `d_legacy`[^hb-gc-passport]. The replay receipts are private aggregates in `.cache/microcosm-check`; the public binder records the tolerance and outcome. Independent full runs use a stated float tolerance; exact comparisons apply only when head, inputs and cache are shared. **`8f712cc`** corrects earlier wording that wrongly attributed this cut to a ruling by Max, regenerating the bound files and the E receipt through their generators; no number changes.

The [country availability record](../data/pilot/country_benchmark_availability.json) and [verified benchmark cells](../data/pilot/country_benchmarks.json) document the limits of DWP's published country tables. The [regional workbook](../data/raw/dwp-benefit-expenditure-by-country-and-region-2024-25.ods), added to the [2025 publication](https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2025) on 18 December 2025, supplies combined 2024–25 State Pension spending for England, Scotland and Wales. It supplies no basic/new breakdown or financial-year recipient counts. [DWP guidance](https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-guidance-and-methodology/benefit-expenditure-and-caseload-tables-information-and-guidance) provides regional outturns, without country forecasts. Those requested comparators remain **unavailable**; no split or forecast is inferred, and María's country coverage gate remains unresolved.

Independent Subfleet reviews of parts A–D, summarized without transcripts:

| Part | Verdict and limits | Corrections |
| --- | --- | --- |
| A: engine port | Two REQUEST CHANGES rounds, then APPROVE at `c962978`; code read, suites not run. | GB matching, cache provenance, rebuild checks and stale wording; final low findings fixed in `60d0aeb`. |
| B: ageing | Initial privacy/provenance findings; final job `20261005-031407-ageing-final-pointer-review`: APPROVE, no required corrections, merge nothing. | Linked-cell suppression, contrast audits and source binding. Approval covers the historical 2.90.2 record, not certification of 2.120.0. |
| C: uncertainty | `20261004-223140-tl-c1-review`: no high finding, medium execution/validation findings, no explicit final APPROVE; no test execution or re-review of the corrected revision. | Legacy fiscal route blocked; suspended cells, artifact checks and provenance corrected. Part E implements the deferred adapter. |
| D: integration | Seven APPROVE rounds; first conditional on tests. Final review read `f2ea89a`, with its low test finding fixed in `30a1be9`. | Rake fallback/failure checks, zero-weight handling and private error logs. Earlier-head cold reruns reproduced the pilot. |

Part E's completed six-treatment fiscal pilot calculates the full thirteen-year horizon before selecting 2034–35 and 2039–40: central plus forty original paired macro indices, with separate central scenarios, model-conditional paired estimates and total, path-sampling and first-phase SEs. Treatments are frozen/reweight/types/both/total and `both_full_new`. Fiscal calculation source is `ccb857cbc6d1745f589258b8b57e693123129462`; completed fresh country coverage at `5d8b53c632fa4d8e69c2624738afd8cf823a9a52` carries its own provenance in `4a57c6c`. Neither receipt relabels the other's calculation source. A complete `--coverage-results` receipt is validated before any job starts; the driver scheduled 41 fiscal batches and skipped the six redundant original coverage jobs, assembling 246 fiscal plus six fresh coverage labels. The default without a replacement remains 47 execution jobs and 252 labels.

The default re-typed flat-rate treatment remains **kept**; **full_new** is a methodological upper sensitivity. The revised [Pensions Act 2014 s.4](https://www.legislation.gov.uk/ukpga/2014/19/section/4), [s.5](https://www.legislation.gov.uk/ukpga/2014/19/section/5), [Schedule 1](https://www.legislation.gov.uk/ukpga/2014/19/schedule/1) and [2015 Regulations reg.13](https://www.legislation.gov.uk/uksi/2015/173/regulation/13) require qualifying-year and contracting-out information for a transitional entitlement. The verified Enhanced FRS schema does not carry the histories needed to reconstruct it. The sensitivity changes only re-typed flat-rate amounts; the data-year identity and CPI treatment of additional pension remain tested. It is not an entitlement estimate or a confidence bound.

The ONS **total-only** control addresses the population-total comparison. `total − frozen` measures replacing aggregate population growth. The `reweight_minus_ons_total` contrast includes any difference between the age/sex-growth target sum and ONS aggregate-growth target. A matched-total supplement is a **possible follow-up**, outside this closeout.

The completed [E fiscal receipt](../data/pilot/model_v2_e.json) and [full fiscal tables beside D](pilot/E-fiscal-tables.md), committed in **`dea4866`**, report all six treatments and seven saved contrasts: **104 central and 104 paired rows**, all available under the ten-record linked-family/complement rule. The receipt SHA-256 is `ac3ad91ca4650108dab90b2dbaae92808a913160fd174371a01d5c875bd3ee7a`: **`8f712cc`** regenerated it through the same exact-cache-only assembly, with no model workers, to carry the corrected D support-audit text, and every numeric value matches the `dea4866` receipt (`ee4ef921…`). **155 focused publication/source/recipe/read-back checks passed**, before and after that correction. The first exact-cache-only reassembly reproduced the naturally completed result exactly apart from `generated_at`.

Selected endpoints follow, in **£bn**, rounded from saved aggregates. “±” is **one total Monte Carlo SE**, not a probability bound. The full tables give path-sampling and first-phase SEs separately for every UK/GB gross/net row and contrast.

| Year | Geography | Series | Central gross | Central net | Paired gross ± total SE | Paired net ± total SE |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 2034–35 | UK | D retained both | 0.6741 | 0.4564 | 3.2222 ± 0.3503 | 2.1661 ± 0.2359 |
| 2034–35 | UK | E both, kept | 0.6755 | 0.4587 | 3.2286 ± 0.3510 | 2.1259 ± 0.2317 |
| 2034–35 | UK | E both, full-new | 0.7430 | 0.5110 | 3.5512 ± 0.3860 | 2.4371 ± 0.2638 |
| 2034–35 | UK | E total only | 0.5317 | 0.3569 | 2.5411 ± 0.2762 | 1.6654 ± 0.1812 |
| 2034–35 | GB | D retained both | 0.6556 | 0.4468 | 3.1334 ± 0.3406 | 2.1129 ± 0.2303 |
| 2034–35 | GB | E both, kept | 0.6580 | 0.4492 | 3.1452 ± 0.3419 | 2.0746 ± 0.2263 |
| 2034–35 | GB | E both, full-new | 0.7245 | 0.5007 | 3.4630 ± 0.3764 | 2.3802 ± 0.2579 |
| 2034–35 | GB | E total only | 0.5169 | 0.3491 | 2.4707 ± 0.2686 | 1.6231 ± 0.1769 |
| 2039–40 | UK | D retained both | 0.8781 | 0.5867[^hb-gc-passport] | 11.0208 ± 0.0827 | 7.0993 ± 0.1106[^hb-gc-passport] |
| 2039–40 | UK | E both, kept | 0.8759 | 0.5815[^hb-gc-passport] | 10.9935 ± 0.0825 | 6.9881 ± 0.1157[^hb-gc-passport] |
| 2039–40 | UK | E both, full-new | 0.9933 | 0.6735[^hb-gc-passport] | 12.4661 ± 0.0935 | 8.1971 ± 0.0868[^hb-gc-passport] |
| 2039–40 | UK | E total only | 0.6358 | 0.4202[^hb-gc-passport] | 7.9795 ± 0.0599 | 5.0559 ± 0.0901[^hb-gc-passport] |
| 2039–40 | GB | D retained both | 0.8548 | 0.5743[^hb-gc-passport] | 10.7279 ± 0.0805 | 6.9434 ± 0.1102[^hb-gc-passport] |
| 2039–40 | GB | E both, kept | 0.8531 | 0.5691[^hb-gc-passport] | 10.7074 ± 0.0803 | 6.8322 ± 0.1154[^hb-gc-passport] |
| 2039–40 | GB | E both, full-new | 0.9674 | 0.6592[^hb-gc-passport] | 12.1410 ± 0.0911 | 8.0613 ± 0.0763[^hb-gc-passport] |
| 2039–40 | GB | E total only | 0.6182 | 0.4106[^hb-gc-passport] | 7.7585 ± 0.0582 | 4.9380 ± 0.0900[^hb-gc-passport] |

These are comparisons between E and retained D at different calculation heads/recipes. D's historical own-head replay tolerance is **£1m**; it applies to those historical replays. The saved E/D UK 2039–40 net figures are **0.58149206 versus 0.58665527**[^hb-gc-passport] centrally and **6.9881045 versus 7.0993269**[^hb-gc-passport] for paired means, with D preserved unchanged.

Selected **saved UK contrasts** are below; the full tables also give the GB contrasts. Contrast means and SEs are read directly from the receipt.

| Year | Saved contrast (UK) | Central gross | Central net | Paired gross ± total SE | Paired net ± total SE |
| --- | --- | ---: | ---: | ---: | ---: |
| 2034–35 | Full-new minus kept[^hb-gc-passport] | 0.0675 | 0.0523 | 0.3225 ± 0.0351 | 0.3112 ± 0.0407 |
| 2034–35 | Total minus frozen | -0.0127 | -0.0083 | -0.0609 ± 0.0066 | -0.0388 ± 0.0042 |
| 2034–35 | Reweight minus ONS total | 0.1001 | 0.0673 | 0.4782 ± 0.0520 | 0.3102 ± 0.0338 |
| 2039–40 | Full-new minus kept[^hb-gc-passport] | 0.1173 | 0.0920[^hb-gc-passport] | 1.4725 ± 0.0110 | 1.2090 ± 0.1192[^hb-gc-passport] |
| 2039–40 | Total minus frozen | -0.0241 | -0.0155[^hb-gc-passport] | -0.3025 ± 0.0023 | -0.1854 ± 0.0040[^hb-gc-passport] |
| 2039–40 | Reweight minus ONS total | 0.1665 | 0.1090[^hb-gc-passport] | 2.0899 ± 0.0157 | 1.2915 ± 0.0250[^hb-gc-passport] |

[^hb-gc-passport]: The pilot uses policyengine-uk 2.120.0, whose Housing Benefit Guarantee Credit passport keys on entitlement rather than receipt. Its net estimates require the certified version bridge before drawing conclusions about the correction's overall effect. The reported net means, total/path/first-phase SEs and kept/full-new net contrast describe that pilot model. [policyengine-uk #1927](https://github.com/PolicyEngine/policyengine-uk/pull/1927) corrects the passport to receipt; the certified rebuild includes that correction with policyengine-uk 2.125.1. The receipt-predicate sensitivity remains withheld under the ten-record linked-family rule; no forty-path SE for an isolated receipt correction is published.

<!-- H-FULL-NEW-NET-SE: completed source tracing and receipt-predicate sensitivity. -->
The [paired-path audit](../data/pilot/full_new_net_se_audit.json) confirms that kept and full-new use the same forty indices, macro seed **20260929**, demographic inputs and statutory scenarios. The forty-one full batch cache keys are unique, and their treatment arguments and output labels correspond. The only kept/full-new argument difference is the re-typed flat-rate level. The net SEs imply an estimator correlation of **0.333318**[^hb-gc-passport] in UK 2039–40, compared with **0.994870** in 2034–35; this is the covariance of the stratified estimates, including first-phase variance. Gross estimator correlations are effectively one. Stratum 8, containing macro indices **29401, 37304 and 39769**, contributes **74.04%** of the 2039–40 net contrast's path-sampling variance[^hb-gc-passport]. Index **39769** alone contributes **49.19%** through its centered within-stratum contrast.

The [fresh full-horizon diagnostic](../data/pilot/full_new_net_se_diagnostic_validated.json), produced by its [frozen recipe](../scripts/diagnose_model_v2_full_new_housing_benefit.py), independently recalculates kept and full-new at index 39769 using the original fiscal source and thirteen fiscal years. Both 2034–35 and 2039–40 gross/net endpoints reproduce the original caches exactly. At this index the two policy uprating paths coincide through 2034–35, so both savings are zero then; they differ by 2039–40. The 2039–40 net savings are **£7.057416bn** kept and **£11.796855bn** full-new, a **£4.739440bn** contrast[^hb-gc-passport].

Housing Benefit explains **£2.798741bn** of that contrast: its Burnham-minus-triple-lock spending offset is **£3.469389bn** kept, versus **£0.670648bn** full-new. The supported group that gains the model's Guarantee Credit passport under Burnham contributes **£3.324397bn** of the kept Housing Benefit offset (**76** change contributors), versus **£0.292794bn** under full-new (**35**). These are supported path aggregates; no survey record is published.

**Conclusion: an upstream model limitation.** The installed policyengine-uk **2.120.0** Housing Benefit applicable-income, assessable-capital and tariff-income formulas use `housing_benefit_pension_age_regulations_apply & (guarantee_credit > 0)`. Guarantee Credit entitlement is computed without requiring a Pension Credit claim. The separately installed `in_receipt_of_guarantee_credit` requires eligibility, `would_claim_pc` and positive Guarantee Credit, preserving baseline receipt under a Pension Credit freeze. The [full kept-path receipt probe](../data/pilot/gc_precision_diagnostic.json) observes entitlement-only nonclaimant passport changes together with Housing Benefit changes; its linked amounts and counts are withheld. It finds no positive-Guarantee-Credit passport changes of at most **£0.01** on this kept path. That limited result does not describe other paths or full-new.

The [receipt-predicate sensitivity](../data/pilot/hb_gc_receipt_intervention.json) completed two fresh kept paths and four independent policy calculations across all thirteen years, using the [committed recipe](../scripts/diagnose_model_v2_hb_gc_receipt_intervention.py). The native 2034/2039 endpoints replay the original cache within **£1m**. In memory, the sensitivity changes only the three entitlement predicates to actual Guarantee Credit receipt, retaining the pension-age gate and savings-credit-only branches. Both policies' 2034 savings remain zero. The linked 2039 intervention saving and fiscal-component families are withheld because at least one support or complement fails the ten-record rule. Consequently the supported **£2.798741bn** native Housing Benefit contrast above is not a published causal estimate of the receipt correction, and no corrected forty-path SE is claimed.

The actual diff of [policyengine-uk #1927](https://github.com/PolicyEngine/policyengine-uk/pull/1927), which was open and unmerged when checked on **6 October 2026**, changes all three Housing Benefit passport call sites from positive entitlement to `in_receipt_of_guarantee_credit`. Its older age guard differs from 2.120.0's pension-age-regulation gate; this sensitivity preserves the installed gate. The correction merged on **8 October 2026** and first shipped in policyengine-uk **2.123.6**. The certified policyengine.py model/data bundle rebuild authorized by **d778** must pin policyengine-uk at **2.123.6 or later** and pass the behavioural receipt-passport preflight. The committed pilot figures remain the 2.120.0 record.

The completed [country table](pilot/E-country-table.md) reports default `both` recipients and basic/new/combined State Pension spending for England, Scotland and Wales in all nine saved years: 2024–25 through 2030–31, then 2034–35 and 2039–40. Combined spending includes additional State Pension. [Fresh coverage](../data/pilot/model_v2_e_coverage.json), committed in **`4a57c6c`**, supplies all six treatments: **648 country** and **108 GB** model comparison rows are available, with no linked country family withheld. All **162 actual-change support receipts** are zero or at least ten contributors; **59 coverage/replacement/privacy tests passed**.

DWP supplies **18 available base-year combined-spending comparisons** across the six modes, with all **630 other country comparator cells unavailable**. For default `both`, saved 2024–25 model-minus-DWP gaps are **−£12.3632bn** for England, **−£2.4096bn** for Scotland and **−£0.3623bn** for Wales. These are rounded saved differences. No recipient/type split, country forecast or ratio is inferred; the receipt records gaps rather than ratios. Verified comparator limits leave María's substantive coverage gate unresolved.

<!-- E-DETERMINISM: completed final source-bound proof. -->
The [Enhanced FRS central `both` cold pair](../data/pilot/efrs_determinism.json) is **complete and passed** at scientific head **`5d8b53c632fa4d8e69c2624738afd8cf823a9a52`**. Both fresh interpreters/caches calculated all thirteen fiscal years before selecting 2034/2039 fingerprints. Selected aggregates are identical; the stated independent-run comparison uses **£1m (£0.001bn)** absolute tolerance, relative tolerance zero. The receipt binds both runs to that historical scientific source (source fingerprint `6e4bbedc`, aggregate fingerprint `bd6cc11a`), authenticated through its archived source. It establishes no correspondence with the certified port. The eight-run Enhanced FRS matrix is dropped.

The [Microcosm central `both` cold pair](../data/pilot/microcosm_support_and_determinism.json) is also **complete and passed**, committed in **`ac231af`** with **66 focused tests passed**. Both runs calculated and fingerprinted all thirteen fiscal years at `5d8b53c`; source fingerprint `6e4bbedc` and aggregate fingerprint `dc02b9c1` match that historical source archive. This establishes no correspondence with the certified port. Aggregates are identical, with the same **£1m** absolute comparison tolerance and relative tolerance zero. The Enhanced FRS proof is committed in **`878c363`**, with **ten focused tests passed**. The Microcosm receipt's `retained_D_source_sha256` (`826f88fc…`) is `microcosm_central.json` as the proof read it; `8f712cc` later changed only that file's support-audit text and bound receipt hash, not the compared figures.

The older archived Microcosm receipts `final-current_first.aggregate.json` and `final-current_repeat.aggregate.json` actually calculated at `ccb857cbc6d1745f589258b8b57e693123129462`, not `0091af4`. They remain an earlier-head record; the new final-source pair supplies the required proof after calculation code changed. These cold checks cover central `both` for the two datasets. Recipes record actual source, engine, package, dataset and macro fingerprints. Independent runs use a stated float tolerance; shared-head/input/cache checks may use exact equality.

The [completed validation record](pilot/E-validation.md) reports full pytest at actual tested head **`7bf0157`**: **873 collected, 869 passed, three permitted stale-results failures, one historical skip**, 19 warnings, **3310.81 seconds**, exit **1**. All **22 model cases passed**. At the part E closeout, Python source and dependencies had remained unchanged; its later script/test change, **`8f712cc`**, corrects the D binder's audit-stop wording and adds its regression check, and the 155 focused tests pass after it. Dashboard fix **`166e23a`** labels (c)'s permitted EV model-conditional and displays the recorded envelope on both tabs, using neutral copy that makes no claim about part F's screen. Five targeted ruling checks passed. Refreshed full checks all exit **0**: **83 tests** (19.44 seconds), lint **zero errors/two existing warnings**, and **production build passed** (56-second compilation, all three static pages, 115.19 seconds wall). These are historical E checks; F subsequently added C2 presentation. [Part H validation](pilot/H-validation.md) supersedes the original private-workspace claims.

Part E's first two independent Subfleet rounds returned **REQUEST CHANGES**: the first required complete evidence and implementation corrections; the second identified the ruling-(c) presentation defect fixed in `166e23a`. Final standard-tier job **`20261006-023048-model-v2-e-final-review`** returned **APPROVE** at **`e64657f8621298b0cfb101f2614dd207efd2555e`**; its historical verdict and access limitations are summarized here. Its one required P3 correction removes stale wording in the prepared final report; the reviewer explicitly permits that finalization without another review. The reviewer had file-read/search access only, confirmed the head from private refs/history, and relied on committed code, public receipts and validation; no shell/Git diff, tests or hashes were rerun. All scientific evidence and validation are complete. The later attribution correction (`8f712cc`) changes wording and hashes only and was not re-reviewed. PR #24 stays a draft.

Under **d955(c)**, part F committed and published the [C2 statutory-screen pre-registration](METHOD.md#model-v2-statutory-uncertainty-screen-pre-registration-c2), before implementation and scoring; the binding re-score waits for post-Budget data. It suspends the April 2022 earnings leg and excludes cells that are zero by construction. A passing primary permits a model-conditional expected value beside the scenario envelope; a failed primary falls back to **(a)**, the envelope without an expected value. Part E retains the adapter's explicit ruling input and does not implement the new screen.

The d833/d778 releases are independently verified: `policyengine[uk]==6.2.6`, UK 2.125.1/core 3.33.0 and Enhanced FRS 1.58.0. The original 11 October execution stopped under host saturation; the unattended bridge and rehearsal subsequently completed at `b31137ea055ab7e2b2ef7dd8b63df1302f5affdf`. Every historical pilot figure above retains its original uncertified label. The binding C2 score and post-Budget rebuild remain pending.

## Part J: completed pre-Budget bridge

The [model-step receipt](../data/pilot/J-bridge-model-step.json) and [certified receipt](../data/pilot/J-bridge-certified.json) were generated by the committed full-run bridge, then verified and imported with [the completed-run importer](../scripts/import_model_v2_j_completed.py). The [completion receipt](../data/pilot/J-completed-verification.json) binds the original receipt hashes and calculation head. Exact cache keys, frozen forty-path recipe, retained-pilot correspondence, fiscal tables and GB coverage reproduce. All linked gross/net/total-offset, UK/GB and HB subset/complement families pass the ten-record rule. The intermediate completed central plus coverage (two labels); the certified pair completed central, forty paired paths and coverage (42 labels). The [separate certified coverage receipt](../data/pilot/J-coverage-gb-dwp.json) has 63 available rows. Rehearsal fiscal amounts stay private.

**Pre-Budget; not for quoting.** The retained pilot is UK 2.120.0/core 3.32.16 on Enhanced FRS 1.56.16, uncertified. The intermediate uses carrier 6.2.6/UK 2.125.1/core 3.33.0 with the same old data, still uncertified. The certified pair holds that model/core/port fixed and changes data to 1.58.0. The intermediate identifies the combined model/core/engine-port step; it does not isolate any one component.

### Central bridge

All amounts £bn; deterministic central scenarios have no Monte Carlo SE. Each path computes the complete thirteen-year horizon before selecting the endpoints.

| Geography | Year | Pilot gross | Pilot net | Model/core/port gross | Model/core/port net | Certified gross | Certified net |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| UK | 2034–35 | 0.675496 | 0.458670 | 0.675496 | 0.458606 | 0.664876 | 0.463548 |
| UK | 2039–40 | 0.875950 | 0.581492 | 0.875950 | 0.581300 | 0.864839 | 0.623953 |
| GB | 2034–35 | 0.658044 | 0.449156 | 0.658044 | 0.449090 | 0.645965 | 0.450057 |
| GB | 2039–40 | 0.853148 | 0.569077 | 0.853148 | 0.568887 | 0.841065 | 0.605865 |

### Paired bridge

All amounts £bn. ± is one **total Monte Carlo SE**, with path-sampling and first-phase components in the receipts. These measure simulation precision on the frozen model-conditional forty-path design, not predictive uncertainty or a binding C2 result. The intermediate paired runs are absent by design, so paired attribution is combined model/core/port plus data.

| Geography | Year | Pilot gross ± SE | Pilot net ± SE | Model/core/port gross ± SE | Model/core/port net ± SE | Certified gross ± SE | Certified net ± SE |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| UK | 2034–35 | 3.228633 ± 0.350965 | 2.125905 ± 0.231651 | not run | not run | 3.177875 ± 0.345448 | 2.280987 ± 0.247607 |
| UK | 2039–40 | 10.993534 ± 0.082476 | 6.988105 ± 0.115671 | not run | not run | 10.854098 ± 0.081430 | 7.653775 ± 0.059125 |
| GB | 2034–35 | 3.145222 ± 0.341898 | 2.074620 ± 0.226327 | not run | not run | 3.087488 ± 0.335622 | 2.213478 ± 0.240363 |
| GB | 2039–40 | 10.707357 ± 0.080329 | 6.832229 ± 0.115369 | not run | not run | 10.555724 ± 0.079191 | 7.428122 ± 0.057316 |

### Observed attribution

On old data, the combined model/core/port step leaves central gross unchanged. It changes UK central net by −£0.064m in 2034–35 and −£0.192m in 2039–40. The data step changes UK central gross by −£10.620m/−£11.110m and net by +£4.942m/+£42.653m. GB data-step gross changes are −£12.079m/−£12.082m and net +£0.967m/+£36.978m. These are differences between displayed supported aggregate receipts; there is no contributor audit for publishing an independently computed cross-version contrast SE.

The combined UK 2039–40 paired net mean rises from £6.988105bn to £7.653775bn, while its total Monte Carlo SE falls from £0.115671bn to £0.059125bn. The recoverable **total** gross-minus-net offset falls from £4.005430bn to £3.200323bn. Neither change isolates Housing Benefit or policyengine-uk #1927.

### Certified GB coverage against DWP

The receipt contains all 63 available rows: seven metrics in nine years (2024–25 through 2030–31, then 2034–35 and 2039–40). Selected years follow. Caseloads here are in millions; all spending is £bn. DWP comparisons exclude Northern Ireland; State Pension also excludes published overseas spending and recipients. No DWP forecast is extended after 2030–31. CTR has no comparator. Pension-age HB uses `housing_benefit_pension_age_regulations_apply`, the model's benefit-rules classification nearest DWP's over-Pension-Credit-qualifying-age category. The separate any-State-Pension-age-member total is not the selected metric; DWP's unpublished mixed-age classification remains a comparator limitation.

| Year | Metric | UK model | GB model | DWP GB | GB / DWP |
| --- | --- | ---: | ---: | ---: | ---: |
| 2024–25 | State Pension spending (£bn) | 117.895123 | 114.847824 | 131.254488 | 0.875001 |
| 2024–25 | State Pension recipients (m) | 11.328562 | 11.040476 | 11.885000 | 0.928942 |
| 2024–25 | Pension Credit spending (£bn) | 6.525927 | 6.438401 | 6.007695 | 1.071692 |
| 2024–25 | Pension Credit benefit units (m) | 1.485414 | 1.454586 | 1.376000 | 1.057112 |
| 2024–25 | Housing Benefit total (£bn) | 7.617248 | 7.251289 | 15.397347 | 0.470944 |
| 2024–25 | Housing Benefit pension-age rules (£bn) | 7.020595 | 6.656908 | 6.851043 | 0.971663 |
| 2024–25 | Council Tax Reduction (£bn) | 2.062934 | 2.062601 | unavailable | unavailable |
| 2025–26 | State Pension spending (£bn) | 123.260519 | 120.074771 | 140.442052 | 0.854977 |
| 2025–26 | State Pension recipients (m) | 11.410128 | 11.119968 | 12.116000 | 0.917792 |
| 2025–26 | Pension Credit spending (£bn) | 6.382167 | 6.299397 | 6.144472 | 1.025214 |
| 2025–26 | Pension Credit benefit units (m) | 1.476368 | 1.445440 | 1.382000 | 1.045905 |
| 2025–26 | Housing Benefit total (£bn) | 8.147494 | 7.749736 | 12.892852 | 0.601088 |
| 2025–26 | Housing Benefit pension-age rules (£bn) | 7.498826 | 7.103796 | 7.114744 | 0.998461 |
| 2025–26 | Council Tax Reduction (£bn) | 2.112892 | 2.112556 | unavailable | unavailable |
| 2030–31 | State Pension spending (£bn) | 150.966172 | 146.763338 | 174.064736 | 0.843154 |
| 2030–31 | State Pension recipients (m) | 11.984946 | 11.657919 | 12.692000 | 0.918525 |
| 2030–31 | Pension Credit spending (£bn) | 8.700325 | 8.583696 | 5.821767 | 1.474414 |
| 2030–31 | Pension Credit benefit units (m) | 1.619996 | 1.585679 | 1.133000 | 1.399540 |
| 2030–31 | Housing Benefit total (£bn) | 10.175139 | 9.640380 | 14.346749 | 0.671956 |
| 2030–31 | Housing Benefit pension-age rules (£bn) | 9.375138 | 8.844160 | 7.941310 | 1.113690 |
| 2030–31 | Council Tax Reduction (£bn) | 2.436706 | 2.436341 | unavailable | unavailable |

The data step improves 2025–26 PC caseload fit from 1.2113 to 1.0459 times DWP and pension-age HB spending from 1.5781 to 0.9985. PC spending instead moves from 1.0077 to 1.0252 times DWP, so the runs do not show an improvement in every PC metric. By 2030–31 PC is 1.4744 times DWP spending and 1.3995 times caseload. Total HB remains below DWP (0.6011 in 2025–26, 0.6720 in 2030–31), and State Pension spending remains below DWP. Certification establishes compatible releases and provenance, not calibration accuracy or closure of María's coverage gate.

### Upstream mechanisms and limitations

- [uk-data #490](https://github.com/PolicyEngine/policyengine-uk-data/pull/490) replaces comparison of UK model HB against the GB OBR target with GB-restricted DWP age-group spending/caseload calibration; wholly pension-age units no longer receive `would_claim_uc`. The working-age calibration nets off all-age supported/temporary-accommodation spending and claims, a lower-bound/general-needs approximation that exists only in 2024–25 and 2025–26. Those accommodation rules remain unmodelled as such. This explains a structural reason to expect total-HB undercoverage, but the bridge does not quantify a causal accommodation gap.
- [uk-data #510](https://github.com/PolicyEngine/policyengine-uk-data/pull/510) solves weighted take-up over entitled GB benefit units, anchors survey reporters, gives entitled nonreporters the solved fill probability, gives units not entitled in the calibration year the 37% newly-entitled rate, and adds GB DWP spending and caseload targets. The source uses pre-calibration survey weights for the solve and a separate deterministic seed.
- [uk-data #513](https://github.com/PolicyEngine/policyengine-uk-data/pull/513) supplies FRS `TOTCAPB4` financial capital for every benefit unit, falling back to `TOTCAPB3`, and sets missing and SPI-synthetic copies to −1 to retain the household-proxy fallback. It aligns capital uprating with the model. Observed financial capital is an approximation of countable PC capital: it omits second homes/land and applies neither statutory disregards nor valuation rules.
- [policyengine-uk #1927](https://github.com/PolicyEngine/policyengine-uk/pull/1927), included in 2.125.1, changes the three HB income, capital and tariff-income passport predicates from positive Guarantee Credit entitlement to `in_receipt_of_guarantee_credit`, preserving the pension-age and Savings Credit-only branches. Installed code and both bridge preflights verify that an entitled nonclaimant is means-tested, a claimant keeps the passport, and flipping only the receipt flag reverses the passport. This removes the entitlement-only channel identified by part H. This numerical bridge combines many model changes with core/port changes; it gives no isolated #1927 fiscal or HB-offset estimate and no intermediate paired SE.

Do not add monetary HB-specific programme offsets from raw job caches: the committed bridge design audits joint gross/net/recoverable-total-offset support, not individual programme-change and linked-complement families. Preserve the part H withheld sensitivity and all historical pilot labels. No rehearsal fiscal value should enter these tables.

Source checks used the installed certified model and release-tag data code, independently of upstream PR narrative:

- [1.58.0 PC take-up implementation](https://github.com/PolicyEngine/policyengine-uk-data/blob/1.58.0/policyengine_uk_data/datasets/pension_credit_takeup.py).
- [1.58.0 FRS input builder](https://github.com/PolicyEngine/policyengine-uk-data/blob/1.58.0/policyengine_uk_data/datasets/frs.py), including `derive_pension_credit_reported_capital` and the stored PC-capital column.
- [1.58.0 DWP HB calibration targets](https://github.com/PolicyEngine/policyengine-uk-data/blob/1.58.0/policyengine_uk_data/targets/sources/dwp_housing_benefit.py).
- [2.125.1 HB applicable income](https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_applicable_income.py), [capital](https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/gov/dwp/housing_benefit/housing_benefit_assessable_capital.py), and [tariff income](https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/policyengine_uk/variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_tariff_income.py).

The completed C2 dry run, core/coverage rehearsal and 20 Enhanced FRS + 2 Microcosm sample verify against their original source and caches. Their fiscal values remain private; safe timing metadata and the labelled post-Budget estimate are in [REBUILD](REBUILD.md#part-j-pre-budget-rehearsal-and-post-budget-sequence) and [the runtime receipt](../data/pilot/J-runtime-planning.json). The dry handoff remains unauthorized. María's substantive coverage/calibration gate remains unresolved despite the improvement in the calibration-year PC caseload and older HB fit.
