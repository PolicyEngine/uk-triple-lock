# Static ageing pilot: model v2 part B

**Status: full-model results pending.** This report is a scaffold for the aggregate output of the fresh 205-job pilot, explicitly anchored to runtime-native 2025 weights after verifying the exact source release's calibration year. It contains published DWP benchmarks, but no pilot fiscal estimates. The committed dashboard results have not been rebuilt. Ageing remains opt-in; the published pipeline retains `legacy` until validation and part C explicitly enable the combined treatment.

Draft PR: [#23](https://github.com/PolicyEngine/uk-triple-lock/pull/23). Target: `main`, to be retargeted onto part A's `model-v2`. The final delivery records the pushed head. Merge status: pending acceptance gates; merge nothing from this pilot.

## Design and provenance

The pilot uses policyengine 5.3.0 / policyengine-uk **2.90.2** and its certified Enhanced FRS, as permitted while part A's upgraded bundle is unavailable. It tests the static method, not the absolute spending level of policyengine-uk 2.118.0. [METHOD.md](METHOD.md) describes the implemented inputs; [AGEING_RULE_AUDIT.md](AGEING_RULE_AUDIT.md) records programme and legal-cutoff checks.

The population input is [ONS's 2024-based UK principal projection](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationprojections/datasets/z1zippedpopulationprojectionsdatafilesuk), using the same public UK zip as policyengine-uk-data. It covers mid-years 2024–2041 by sex and single age, with ages 105–109 and 110+ combined into 105+. The committed CSV is public OGL data; its SHA-256 is `df91f70d81232225fe5516842390f3de3b2d5e6279b6a762cb28bcf63378229f`. The [provenance manifest](../data/ons_npp_2024_uk_age_sex.provenance.json) records live-download mode, source/workbook hashes and URLs. [ONS_PROJECTION.md](ONS_PROJECTION.md) documents extraction.

Fiscal-year population is `0.75 × mid-y + 0.25 × mid-(y+1)`, representing the October midpoint. Household targets apply those fiscal ONS growth factors to the anchor-year survey margins, rather than imposing raw ONS population levels. Sex-specific cells are five-year bands through 55–59, single ages 60–79, then 80–84, 85–89 and 90+. Bounded minimum-relative-entropy calibration permits ratios 0.2–5 relative to anchor weights and fails when targets are infeasible or not reached to 1e-6 relative. Person and benefit-unit weights follow their household weight.

The pilot explicitly anchors **2025**, the calibration year declared by the [exact data 1.56.16 source](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57). The API requires an explicit anchor or verified dataset metadata. These are **runtime-native 2025 weights**, which remain unchanged at the anchor; this does not establish preserved DWP benefit calibration. The builder materializes calibrated 2025 weights back to 2024 using a different factor from the runtime's forward uprating. The private artifact build manifest was gated. [CALIBRATION_ANCHOR.md](CALIBRATION_ANCHOR.md) records the bundle mapping, public source proof and materialization mismatch. Raked forecasts replace later native weights, which this runtime produces through population uprating. Part C must verify certified calibrated-period incomes and weights and measure the effect of age/type changes on benefit outcomes.

For top-coded data, a deterministic hash ordering assigns age-80 records represented ages 80–105 using sex-specific ONS shares and weighted midpoints. The weighted 80+ population is preserved and other ages stay unchanged. If any original age exceeds 80, the uncapped-data guard retains all original ages rather than spreading genuine age-80 records into another older tail. The report checks must identify whether top-code representation occurred and which supplied head flags were retained.

Represented ages and within-year birthday draws remain fixed across years. A record represents a person of that age in each year's contemporaneous cohort; it is not a surviving individual aged forward. Synthetic birth dates are inferred at 6 October each fiscal year. Model-eligible men born before 6 April 1951 and women born before 6 April 1953 receive `BASIC`, those born on or after the cutoff receive `NEW`, and those below model pensionable age receive `NONE`. Birthday inputs follow the upstream 2.118.0 draw when available. The separate synthetic upstream differential validates the mechanism; it does not replace full population runs on the pilot bundle.

For recomputed types, the original reported State Pension is repartitioned against the selected type's data-year flat-rate ceiling. The nonnegative excess is additional pension; on `NEW` records it represents protected payments, including inherited amounts already reported. The excess follows September CPI and is identical under the triple lock, plan and baseline for a given path. The model does not simulate contribution histories or newly acquired protected entitlements. Below pensionable age, payable components remain zero.

The eligible data-year components identity passes to the penny, and unchanged-type additional pension is checked against the original model amount. An aggregate audit identified **40 records** with positive reported pension below the installed model's pensionable age. Their reported total cannot equal zero payable components. The all-record identity gate is therefore pending: part C must report and resolve verified misreporting or model eligibility defects through the proper data/model build, without creating payment below pensionable age to force equality.

## Planned treatments and results

The 205 jobs comprise five treatments for the central path and five for each of the exact 40 committed Microcosm-paired expected-value selections, all run on Enhanced FRS. Stratum probabilities and repeated selections are retained. Every treatment is a full model run of both pension rules with common baseline inputs; no fiscal result is scaled.

| Treatment | Age/birthday representation | Annual weights | Pension type/additional base |
| --- | --- | --- | --- |
| `legacy` | Original survey inputs | Native | Existing engine pins |
| `frozen` | Common represented ages and birthday draw | Native | Survey type and original additional amount |
| `reweight` | Common representation | Raked | Survey type and original additional amount |
| `types` | Common representation | Native | Contemporaneous cohort and repartitioned residual |
| `both` | Common representation | Raked | Contemporaneous cohort and repartitioned residual |

The core factorial interaction is `both − reweight − types + frozen`. The separate common-input effect is `frozen − legacy`. Both treatments already apply the same integer-age eligibility gate and zero additional pension below that age on 2.90.2. Their difference on this bundle therefore measures represented ages and any head/claimant changes from resolving age ties. The completed pilot must report the free regression check comparing central State Pension totals under `legacy` and `frozen` in every year. On a newer bundle, birthday inputs can also affect eligibility, so the general contrast does not claim to isolate age representation alone. Both contrasts are computed within each path before stratified averaging. Expected-value uncertainty here is paired path-sampling uncertainty, not total model uncertainty.

**Four-way saving table (£bn): all entries await the full-model aggregate output.** Fill from `central_four_way_saving_bn` and `expected_four_way_saving_bn`; expected rows require their `mean_bn` and `se_bn`. The completed JSON covers every forecast year, including household-income change, and separately reports central basic/new/total pension spending.

| Sample | Fiscal year | Metric | Legacy | Frozen | Reweight | Types | Both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Central | 2034–35 | Gross saving | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Central | 2034–35 | Net saving | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Central | 2039–40 | Gross saving | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Central | 2039–40 | Net saving | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Paired expected value | 2034–35 | Gross saving ± SE | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Paired expected value | 2034–35 | Net saving ± SE | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Paired expected value | 2039–40 | Gross saving ± SE | Pending | Pending | Pending | Pending | Pending | Pending | Pending |
| Paired expected value | 2039–40 | Net saving ± SE | Pending | Pending | Pending | Pending | Pending | Pending | Pending |

No direction or size is inferred before these runs finish.

## Published benchmarks and coverage

[DWP's Spring Forecast 2026 workbook](https://assets.publishing.service.gov.uk/media/69dcdc8c6b695d635c34dcc4/outturn-and-forecast-tables-spring-forecast-2026.xlsx), published on its [2026 tables page](https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2026), was read directly from the committed copy. A live publisher download matched that copy byte for byte: SHA-256 `11a591e4a2144ed6a686be6a9ded4e5d5b3b8d4887bd57c1ff0632bd251009de`.

The workbook's coverage is GB plus overseas, excluding Northern Ireland. Its separate overseas rows allow matched **all-type GB totals** by subtraction. Spending is nominal £bn and caseload is millions, converted from the workbook's £million and thousands. Model outputs below remain pending for all five treatments; fill them from `coverage_comparisons`.

| Fiscal year | DWP GB total State Pension £bn | DWP GB recipients m | Five-treatment model comparison |
| --- | ---: | ---: | --- |
| 2024–25 | 131.254 | 11.885 | Pending |
| 2025–26 | 140.442 | 12.116 | Pending |
| 2026–27 | 148.269 | 12.152 | Pending |
| 2027–28 | 152.847 | 12.041 | Pending |
| 2028–29 | 157.761 | 12.142 | Pending |
| 2029–30 | 165.775 | 12.417 | Pending |
| 2030–31 | 174.065 | 12.692 | Pending |

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
| GB total spending and recipients, base through 2030–31 | Available above | Pending |
| GB basic/new spending and recipients | Unavailable: overseas not separated by type | Pending |
| Spending/recipients by age and country/region | Unavailable in this workbook | Pending, subject to suppression |
| 2034–35 and 2039–40 spending, recipients and by-type breakdown | Unavailable: no verified long-term benchmark supplied | Pending |

No overseas type share is imputed and no long-term benchmark is extrapolated. A later verified published source may extend these comparisons; until then they remain unavailable.

## Privacy, review and acceptance gates

Weights, identifiers and survey amounts stay in private `.cache` files. Public outputs contain aggregates only, with a minimum of ten contributing records for any nonzero cell. Zero cells may report zero. If any positive cell needs suppression, the entire linked age-table family or country/region family is withheld across treatments, years and policies; this prevents recovery by cross-table subtraction. Aggregate GB totals are retained only when they meet the same minimum. The completed output records its suppression policy.

Independent Subfleet reviews identified default-treatment, privacy, legacy-control, calibration and run-verification issues. Their fixes and the source-year audit prompted fresh runs; an unfinished or interrupted run is not validation evidence. Review comments and passing unit/synthetic tests do not sign off the population or fiscal gates.

| Gate | Current report status | Evidence needed before acceptance |
| --- | --- | --- |
| Complete paired fiscal design | Pending | All 205 jobs and aggregate checks complete; central alone is insufficient |
| Model reads ages/types/residuals and entity weights | Pending population-run confirmation | Readback checks every year under baseline and both rules |
| ONS growth targets and runtime-anchor identity | Pending population-run confirmation | Every raked year ≤1e-6 relative; runtime-native 2025 weights unchanged |
| Eligible pension accounting | Eligible audit passes; full all-record gate pending | Report/resolve the 40 below-pension-age exceptions on the certified build |
| Calibrated GB baseline and available coverage | Pending calibrated-input bridge | Verify artifact materialization and certified 2025 inputs; model/bundle and ageing bridge for State Pension, Pension Credit and Housing Benefit |
| Engine and worker integration | Pending | Legacy regression comparison, opt-in `run_path`, real persistent/isolated agreement, worker cleanup and bounded resources |
| Final privacy and provenance | Pending completed-output confirmation | Linked-table suppression, no record outputs, matching model/data/source hashes |

## What part C needs

Part C must retarget this work onto part A's certified model-v2 bundle, supply the verified calibration year explicitly, obtain certified calibrated-period inputs and artifact metadata, reconcile below-pension-age reported pensions, and remeasure the calibrated GB State Pension, Pension Credit and Housing Benefit baseline. The current release's source year is 2025; its runtime-native weights do not reconstruct the builder's calibrated weights. Part C must verify that income and weight materialization reproduce the calibrated period, compare awards with identical age/type/head inputs to isolate that bridge, then measure the demographic changes and run the complete paired design on that bundle.

The audited releases omit Scotland's Pension Age Winter Heating Payment and an explicit basic-pension age-80 addition. Reported additions can enter the residual, but that does not implement the statutory age addition separately. Cohort eligibility and inferred eldest-member/claimant ranking can change with represented ages. These upstream coverage and structural limits must remain explicit. Later retirees reuse survey amounts for people of the same age; pensioners abroad, survival, migration and contribution histories remain outside this static route.

Before enabling ageing in the published pipeline, part C must complete the version bridge, full pilot and independent review, verify any added long-term benchmarks, and perform the one authorized rebuild after the required forecast/statutory input updates. Regenerate results provenance and dashboard assumptions together; pending pilot estimates must not replace the committed headline.

Reproduction on the current pilot anchor:

```sh
python scripts/validate_ageing.py --workers 1 --calibration-year 2025 --plan
python scripts/validate_ageing.py --workers 4 --persistent-workers --calibration-year 2025 -o .cache/ageing_validation.json
```

The ordinary CLI permits at most four Enhanced FRS workers. The fresh full pilot uses the same validation API and cache with **eight Enhanced FRS slots and zero Microcosm workers**, after CPU and RAM checks. The new host measurements, private execution-driver hash and worker count are recorded in the aggregate provenance. The command above reproduces the same experiment with four slots. The output JSON supplies the completed aggregate tables and provenance; it is not a record-level data export.
