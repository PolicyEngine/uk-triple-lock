# Part E final report — template awaiting complete evidence

**PENDING TEMPLATE: do not submit as the final report.** Fill the marked slots from complete aggregate receipts, tests and a Subfleet APPROVE. The present pilot is **uncertified and not for quoting**.

Branch/head: **PENDING final model-v2 SHA**. PR [#24](https://github.com/PolicyEngine/uk-triple-lock/pull/24): **PENDING final OPEN/draft/head verification**. Work uses this assigned workspace and private Git metadata; only `model-v2` is pushed. Existing changes and history are preserved; no main/master merge or GitHub comment is authorized.

The pilot uses policyengine-uk **2.120.0**, core **3.32.16**, and Enhanced FRS **1.56.16**, built on **2.89.2**. Fiscal calculation source is `ccb857cbc6d1745f589258b8b57e693123129462`; fresh coverage and final cold checks use scientific freeze `5d8b53c632fa4d8e69c2624738afd8cf823a9a52`. Final branch documentation/recipe commits do not relabel those calculation heads.

## Vahid's items

The table identifies implementation commits and load-bearing tests. Focused checks recorded in the state and prior commits pass; the completed final suite and evidence slots below remain required.

| Item | Change and commit | Test/evidence |
| --- | --- | --- |
| 1. Committed evidence | `0a67899` binds retained D version bridge, integrated UK/GB and Microcosm central aggregates; `2d6b751` binds GB/DWP coverage and its completed audit. `0c5f087` labels the old ageing report/JSON **2.90.2**, changing no numbers. `5d2106d` records A–D review verdicts and updated rulings. | `tests/test_pilot_evidence.py`: aggregate-only fields, minimum cells, linked suppression, actual heads, versions and binding. **52 evidence/privacy tests plus one historical-driver check passed**. Final E evidence commit: **PENDING**. |
| 2. Re-typed level | `9e1150f` adds kept/full-new sensitivity; kept stays default. `5d8b53c` counts actual stored changes for disclosure. | `tests/test_demography.py`: rate monotonicity and never below kept; `tests/test_ageing_model.py`: each policy's rate, data-year identity to £0.01, unchanged additional pension and prior fiscal-value equivalence. Full-run bounds: **PENDING**. |
| 3. C1 adapter | `444624a` runs the 160-slot handoff, extra identical-rates check and exact 40-slot paired subsample. It writes path multiplicities, stratum sensitivity paths/probabilities and draw n/seed/shocks. The original primary has 161 unique runs including its extra check. Explicit ruling input is retained. | `tests/test_uncertainty_adapter.py`: fake-engine end to end, duplicate slots, written fields, no-ruling refusal naming d955, all a/b/c inputs, a mutation that breaks the check, and Hypothesis slot-sum property. Part F's new statutory screen is not implemented here. |
| 4. Determinism | `7d5f7b9` narrows checks and uses stated float tolerance; `9185580` binds EFRS receipts to current scientific sources; `b6f5a69` resumes a missing Microcosm repeat from a validated full first checkpoint. EFRS receipt commit: `878c363` (ten focused receipt/source/recipe/privacy tests passed). | `data/pilot/efrs_determinism.json`: final `5d8b53c` central both pair complete/passed, all thirteen years, identical selected aggregates within £1m tolerance. Final Microcosm repeat/verdict: **PENDING**. |
| 5. Core pin | `9e1150f` pins core **3.32.16** in pyproject, matching the lock. | `tests/test_datasets.py::test_provenance_records_the_installed_model_and_that_it_is_uncertified` checks runtime version and pyproject pin. |
| 5. Fiscal identity | `9e1150f` independently compares household income and government balance; `6bcbd59` fixes summation order. | `tests/test_ageing_model.py::test_independent_fiscal_income_identity_rejects_mutated_household_income` proves the identity can fail. |
| 5. First-phase SE | `444624a` uses Kish effective macro-draw counts and target moments for reweighted first-phase precision. | `tests/test_sampling_precision.py`: equal-weight Hypothesis reduces to the plain formula; unequal-weight brute-force Monte Carlo agrees. |
| 5. Mean paths | `444624a` makes paired ±0.5pp earnings runs independent scenarios; `9e38420` checks sampled baseline-zero strata; `c38d4da` displays the recorded scenario start year. | Fake-engine mean-scenario/zero-stratum tests and dashboard scenario-year tests pass. Presentation follows d955(c), below. |
| 5. Represented-age order | `9e1150f` keys ordering to verified dataset content. | `tests/test_demography.py::test_same_dataset_name_different_content_changes_topcode_order` passes. |
| 5. Total-only control | `9e1150f` adds the one-margin ONS population-total rake; `00ef7ce` adds paired SEs. `4f7e465` gives the reweight-minus-total comparison its precise label. | `tests/test_demography.py::test_total_population_rake_preserves_anchor_and_does_not_target_age_cells`; full central/40-paired numeric results: **PENDING**. |
| 5. Country table | `48d9641` verifies DWP source cells/hashes and records comparator availability; `a3376c2` separates fresh corrected coverage provenance. | Country/source checks and complementary-support checks pass. Final model country table/suppression: **PENDING**. Requested unavailable benchmarks stay unavailable. |
| 5. María/certification | `5d2106d` rewrites the María draft: pilot stays uncertified; d778 authorizes a certified rebuild bundle after the uk-data batch. | Draft is `out/E-maria-14.md`; no request to approve an uncertified rebuild remains. |
| 5. PR body | Draft updated for the integrated head, current coverage ranges and rulings. | `gh pr edit 24 --body-file out/E-pr24-body.md` and final draft/head verification: **PENDING**. No comments or merges. |

## Re-typed bounds and total-only results beside D

The revised [Pensions Act 2014 s.4](https://www.legislation.gov.uk/ukpga/2014/19/section/4), [s.5](https://www.legislation.gov.uk/ukpga/2014/19/section/5), [Schedule 1](https://www.legislation.gov.uk/ukpga/2014/19/schedule/1) and [2015 Regulations reg.13](https://www.legislation.gov.uk/uksi/2015/173/regulation/13) were read in this work. The transitional calculation needs qualifying-year and contracting-out histories absent from the verified Enhanced FRS schema, including a separate additional-pension history. `kept` remains the methodological default; `full_new` raises only re-typed flat-rate amounts to each policy's full new rate. Additional pension keeps the CPI pin, and the data-year components identity remains intact. This is a flat-rate sensitivity, not reconstructed entitlement or a probability bound.

E calculates the full thirteen-year horizon before selecting **2034–35** and **2039–40**. Its six modes are frozen/reweight/types/both/total/both_full_new on central plus forty original paired macro indices: **246 fiscal labels**, with six fresh coverage jobs carrying separate provenance. Every fiscal figure is a full PolicyEngine UK result; no scaling, interpolation or side model is used.

The retained D comparison below is copied from `data/pilot/integrated.json` committed in `0a67899`, rounded for display. All figures are **£bn**. The paired means are historical model-conditional estimates; SEs measure Monte Carlo precision, not macro model uncertainty. D paired means and SEs are retained, not independently replayed.

| Year | Geography | Saving | D central legacy | D central both | D paired both | SE total | SE path | SE first phase |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2034–35 | UK | gross | 0.5444 | 0.6741 | 3.2222 | 0.3503 | 0.3501 | 0.0118 |
| 2034–35 | GB | gross | 0.5293 | 0.6556 | 3.1334 | 0.3406 | 0.3404 | 0.0115 |
| 2034–35 | UK | net | 0.3592 | 0.4564 | 2.1661 | 0.2359 | 0.2358 | 0.0079 |
| 2034–35 | GB | net | 0.3513 | 0.4468 | 2.1129 | 0.2303 | 0.2302 | 0.0078 |
| 2039–40 | UK | gross | 0.6599 | 0.8781 | 11.0208 | 0.0827 | 0.0787 | 0.0252 |
| 2039–40 | GB | gross | 0.6416 | 0.8548 | 10.7279 | 0.0805 | 0.0766 | 0.0246 |
| 2039–40 | UK | net | 0.4331 | 0.5867 | 7.0993 | 0.1106 | 0.1094 | 0.0163 |
| 2039–40 | GB | net | 0.4232 | 0.5743 | 6.9434 | 0.1102 | 0.1091 | 0.0160 |

<!-- E-FINAL-FISCAL: insert saved E central/paired rows and kept/full-new/total contrasts with all SE components beside D. -->
**PENDING E numeric results and evidence/table commits.** Insert the completed `out/E-fiscal-tables.md` or a concise saved-row selection; include UK/GB gross/net at both selected years. Keep central scenarios separate from paired model-conditional estimates.

`total − frozen` measures replacement of aggregate population growth. `reweight_minus_ons_total` retains any difference between the age/sex-growth target sum and ONS overall-growth target; it is not a fixed-total estimate of age/sex margins alone. The matched-total supplement is a possible follow-up, outside this closeout.

Max stopped D's per-path national contributor audit. The retained central receipts already show at least **9,977 contributors per positive cell**; the completed coverage audit remains. D numbers stay unchanged with **£1m (£0.001bn)** absolute tolerance for independent full-run replay comparisons. Archived replays match gross to four decimal places and net within **£0.0003bn**. Microcosm 2039–40 UK net is **0.6330** versus retained **0.6332** for d_both and **0.4681** versus **0.4683** for d_legacy; these are distinct from the Enhanced FRS rows above. The binder records the scope and tolerance; it does not claim replay of D's paired means.

## Country coverage

<!-- E-FINAL-COUNTRY: insert complete model table or linked-family suppression verdict, sourced to fresh coverage receipt. -->
**PENDING model recipients/basic/new State Pension spending for England, Scotland and Wales**, with a ten-record minimum and linked-cell/complementary suppression. Use the base year and every covered forecast year from the completed coverage artifact.

`48d9641` commits the verified regional DWP workbook, exact source cells and hashes. It supplies **combined 2024–25 State Pension spending only** for these countries. Financial-year recipient counts, basic/new components and country forecasts are **unavailable**. Spring 2026 matched GB combined spending/caseload benchmarks cover through **2030–31**; no later, type or country benchmark is extrapolated or allocated. Source availability limits leave María's geographic coverage gate unresolved.

## Determinism and validation

The Enhanced FRS central both cold pair at `5d8b53c` is **complete and passed**, recorded in `data/pilot/efrs_determinism.json`. Both fresh interpreters/caches calculate all thirteen fiscal years before selecting 2034/2039 aggregates. The selected aggregates are identical and pass the **£1m (£0.001bn)** absolute comparison tolerance, relative tolerance zero. Source fingerprint `6e4bbedc` and aggregate fingerprint `bd6cc11a` agree; current scientific-source correspondence passes. The eight-run EFRS matrix was dropped.

Archived Microcosm current_first/current_repeat receipts record actual head `ccb857c`, with equal source fingerprints and results; that is an earlier-head proof. Calculation code under src changed since `0091af4`, so final-head Microcosm first/repeat is required at `5d8b53c`. The first full cold-run checkpoint is complete; repeat proof is pending.

<!-- E-FINAL-DETERMINISM: replace with actual completed pair receipt paths, source fingerprint checks, comparison tolerance and outcome. -->
**PENDING final Microcosm cold-pair verdict and completed receipt commit.** Enhanced FRS is passed as stated above. Independent full runs use a stated float tolerance, with exact comparisons reserved for shared head, inputs and cache.

<!-- E-FINAL-TESTS: replace with final full-suite counts and names of allowed failures, plus final receipt/privacy checks. -->
**PENDING full pytest count/verdict.** Only these documented stale-results failures are permitted: `test_results::test_not_stale`, `test_scenarios::test_not_stale`, and `test_model::test_method_text_percentiles_match_the_past_years_check`. An interrupted suite is not a completed validation result.

Dashboard source is unchanged since `c38d4da`. Recorded checks in `.cache/E-dashboard-checks.md`: **81 tests passed** with `bun run test --testTimeout 30000`; lint **0 errors / 2 existing warnings**; production build **passed**. The sequential checks used unchanged source/commands; the increased test timeout addresses this loaded host. **PENDING final root confirmation of the validation record used.**

<!-- E-FINAL-REVIEW: insert final standard-tier Subfleet job/head/report/APPROVE and correction commits. -->
**PENDING Subfleet standard review APPROVE.** Initial `out/E-review-1.md` requested changes for missing evidence, the population-contrast label, actual-change support, private default inputs and the hard-coded dashboard year. The implementation corrections are committed and focused tests pass; completed-evidence review remains required. Reviews use Subfleet only.

## Decisions and draft paths

**d955 = (c), decided.** Part F will write and publish the statutory-screen pre-registration before the binding re-score on post-Budget data: suspend the April 2022 earnings leg and exclude construction-zero cells. If the primary passes, label expected value **model-conditional** beside the **scenario envelope**; if it fails, fallback **(a)** omits expected value. Part E keeps the explicit adapter input and does not implement that new screen.

**d778 = yes after the uk-data batch, decided.** policyengine.py will release a certified bundle pinning the latest policyengine-uk and new data; the rebuild uses it. The present pilot stays uncertified. **d833's batch go is pending**, as are the release/certification work and part F's screen/pre-registration/score.

Drafted comments remain unposted at `out/E-reply-vahid.md` and `out/E-maria-14.md`. The PR body is `out/E-pr24-body.md`. The completed report will be `out/E-final.md`, in the assigned workspace.
