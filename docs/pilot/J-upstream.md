# Part J: certified-model port audit

Pre-Budget audit, 11 October 2026. This is a source audit and rehearsal record; it does not authorize the binding C2 build or make pilot figures quotable. Historical committed pilot records retain policyengine-uk 2.120.0 and Enhanced FRS 1.56.16 with `certified: false`.

## Sources and scope

Read the [2.125.1 changelog](https://github.com/PolicyEngine/policyengine-uk/blob/2.125.1/CHANGELOG.md) from the pilot release onward, and compared the complete source archives for the two tags. The old tag is `b5b092312df7aa56a4e89c4b9b7c133507dea114`; the certified model tag is `e89b8abcf524de48e590b9680e1a04288d30eacd`. The [GitHub comparison](https://github.com/PolicyEngine/policyengine-uk/compare/2.120.0...2.125.1) identifies the merge commits. The file comparison uses the complete archives because the compare API's file response stops at 300 files.

The engine reads every item on `GOV_TAX_VARIABLES` and `GOV_SPENDING_VARIABLES`, plus household income, poverty, distribution and coverage dependencies. Consequently this audit includes changes to other benefits, taxes, consumption and student support as well as pensioner programmes. A listed mechanism is supported by the changed source, not by an assumption about its fiscal size. The numerical attribution belongs to the separate full-run bridge; this audit makes no per-PR fiscal estimate.

## Upstream changes that touch engine reads

| Release | Upstream change | Source read and engine implication |
| --- | --- | --- |
| 2.121.0 | [#2140](https://github.com/PolicyEngine/policyengine-uk/pull/2140): rental tenure | Household `is_renting` now includes housing-association tenants. `benunit_is_renting` uses the same shared predicate in `utils/tenure.py`, preserving its existing three rental categories. This reaches rental-benefit eligibility and household tenure dependencies. The engine retains the published tenure categories. |
| 2.121.0 | #2140: Child Benefit opt-outs | `child_benefit`, `would_claim_child_benefit`, `child_benefit_opts_out` and the charge helper preserve the independent claim gate and restore payment when the charge falls below the configured opt-out threshold. `CB_HITC` handles a cliff without division warnings. Both Child Benefit spending and income tax enter the fiscal accounts. |
| 2.121.0 | #2140: Scottish two-child payment | `two_child_limit_payment` reads its `in_effect` switch; the unimplemented Scottish payment remains inactive in the baseline. This is an indirect household-income dependency rather than a new engine fiscal-list item. |
| 2.121.0 | #2140: bus fares | `simulation.py` moves stored household bus spending to `bus_fare_spending_reported`; the new journey inputs and `person_bus_fare_spending` use regional yields, single-fare caps and proportional controls, preserving legacy reported spending where journey data is absent. Consumption and bus-policy dependencies can change. The loader guard was rehashed after reading this move. |
| 2.122.0 | [#2081](https://github.com/PolicyEngine/policyengine-uk/pull/2081): UC work-related requirements | `uc_mif_applies`, `uc_minimum_income_floor_gross`, `uc_expected_hours`, responsible-carer and work-group variables now apply the floor only to claimants subject to all work requirements, with each partner's own threshold. Caring, disability, qualifying age and child age can remove or lower it. Universal Credit spending and household income are read in every fiscal run. |
| 2.122.1 | [#2062](https://github.com/PolicyEngine/policyengine-uk/pull/2062): resolved household head | New `is_resolved_household_head` selects exactly one member from raw nominations and age, with stable input order breaking ties. Rent liability/shares, personal rent, UC counted claims and non-dependants, maintenance-loan household rules and CTR liability use it. The engine's age breakdown now reads that same resolved head. Raw survey head nominations are still pinned; the derived resolved flag is cleared after age pins so it recomputes. |
| 2.122.2 | [#2158](https://github.com/PolicyEngine/policyengine-uk/pull/2158): CTR capital caveat and HB regression | The release adds tests and documents the `corporate_wealth` proxy problem in older data: pension wealth embedded in the proxy can produce a CTR capital-route loss. It does not introduce a new formula. The bridge records CTR and the data step separately; it does not interpret a proxy-driven loss as a real behavioural effect. |
| 2.122.3 | [#2160](https://github.com/PolicyEngine/policyengine-uk/pull/2160): UC qualifying age | The no-work-requirements group reads the State Pension Credit qualifying age. The source distinguishes this from men's own pensionable age for the historical pre-December-1953 cohort. The engine continues to use `is_SP_age` for State Pension accounting and upstream programme-specific age tests for coverage. |
| 2.123.0 | [#2096](https://github.com/PolicyEngine/policyengine-uk/pull/2096): reduced VAT history | Corrects the April 1994–August 1997 reduced VAT schedule. VAT is on the tax list; this historical parameter correction precedes the engine's current future horizon and last-decade replay. |
| 2.123.0 | [#2097](https://github.com/PolicyEngine/policyengine-uk/pull/2097): tax-credit withdrawal date | Corrects the withdrawal rate's start to 6 April 2011. Tax credits are fiscal spending; the changed historical boundary precedes the last-decade replay. |
| 2.123.0 | [#2144](https://github.com/PolicyEngine/policyengine-uk/pull/2144): Guarantee Credit boundary | `is_guarantee_credit_eligible` includes income equal to the guarantee (`<=` rather than `<`). Pension Credit and passport dependencies read this flag; the engine introduces no replacement eligibility formula. |
| 2.123.0 | [#2172](https://github.com/PolicyEngine/policyengine-uk/pull/2172): property finance costs and allowance | Optional rental receipts, current finance costs and brought-forward costs support the finance-cost income-tax reduction. The allowance no longer stacks on already-netted expenses; the selected tax route compares the resulting tax. `property_income_after_finance_costs` now feeds Pension Credit, HB, Income Support, tax-credit and CTR income lists. UC puts the reduction against property tax rather than earnings tax. The engine keeps raw `property_income` in its path-movement diagnostic but reads the upstream tax/benefit outputs. |
| 2.123.1 | [#2163](https://github.com/PolicyEngine/policyengine-uk/pull/2163): legislated pension split | Basic, new and additional State Pension obtain the data-year split rate from a baseline's legislated parameters when a comparator exists. The engine discards the Scenario comparator to eliminate behavioural incidence, so its historical fixed-denominator reform remains needed when changing data-year flat rates. The current future reforms leave data-year rates alone. All three guarded files were reread and rehashed. |
| 2.123.1 | [#2164](https://github.com/PolicyEngine/policyengine-uk/pull/2164): high-value council-tax surcharge | `high_value_council_tax_surcharge` now charges owners, not tenants. This variable is on `GOV_TAX_VARIABLES`; the engine's decomposition already reads it. |
| 2.123.2 | [#2165](https://github.com/PolicyEngine/policyengine-uk/pull/2165): employer NI secondary threshold | Stores the annual statutory £5,000 threshold as £5,000/52 rather than a rounded weekly value. `ni_employer` is a fiscal tax item. Removing the Scenario comparator still makes the engine's employer-NI incidence zero; statutory employer NI revenue remains in the accounts. |
| 2.123.3 | [#2098](https://github.com/PolicyEngine/policyengine-uk/pull/2098): energy price support | Energy Price Cap history uses the final quarterly illustrations; EPG effective dates and prepayment discounts are explicit. `monthly_epg_consumption_level` and energy inputs feed consumption and `epg_subsidy` spending. Prepayment discounts require the corresponding supplied meter input. |
| 2.123.4 | [#2013](https://github.com/PolicyEngine/policyengine-uk/pull/2013): Income Support claimant and partner | `income_support_eligible` scopes award-holder, ESA and existing-award conditions to claimant/partner, adds the placed-child category and excludes locally placed children from the family youngest-child test. The reported award holder must independently meet the age/category requirements; another family member's award no longer supplies or blocks the claim. Income Support spending and HB/CTR passport dependencies are read by the engine. |
| 2.123.5 | [#2182](https://github.com/PolicyEngine/policyengine-uk/pull/2182): historical employer NI threshold | Corrects the secondary threshold for 2015–16 and 2016–17 to £156 per week. This tax dependency predates the April 2017–2026 replay. |
| 2.123.6 | [#2015](https://github.com/PolicyEngine/policyengine-uk/pull/2015): CTR per-claim scheme | CTR scheme support moves from household to benefit-unit level; each claim uses its own pension-age test and non-dependant exemption. Shared-liability reported awards are capped where a simulated claim pays against the same bill, subject to the source's student exception. The engine reads `council_tax_benefit` as spending and coverage; its entity is `BenUnit`, and support counts use that entity dynamically. |
| 2.123.6 | [#1927](https://github.com/PolicyEngine/policyengine-uk/pull/1927): HB Guarantee Credit receipt passport | Applicable income, tariff income and assessable capital disregard on `in_receipt_of_guarantee_credit`, preserving their pension-age-regulations guards and Savings Credit-only branches. Positive entitlement without a Pension Credit claim retains the ordinary means test. The existing behavioural preflight passes on the certified model, including reversal of the receipt flag. |
| 2.123.7 | [#2152](https://github.com/PolicyEngine/policyengine-uk/pull/2152): TV-licence transition | `tv_licence_discount` day-weights the over-75 Pension Credit transition from 1 August 2020. TV licence revenue is fiscal tax and the Pension Credit receipt interaction remains relevant. |
| 2.123.7 | [#2103](https://github.com/PolicyEngine/policyengine-uk/pull/2103): Energy Bills Support Scheme | Corrects monthly timing, amounts and GB/NI eligibility. `energy_bills_rebate` is fiscal spending; the historical support schedule is read during historical calculations. GB country masks remain separate from programme eligibility. |
| 2.123.8 | [#2084](https://github.com/PolicyEngine/policyengine-uk/pull/2084): UC member of couple claiming singly | The claimant's own age sets the single standard allowance; the other member supplies no LCWRA/carer element or personal-benefit cap exception, while the couple's income/capital remain assessed. Shared HB/UC LHA and cap rules keep legacy couple treatment when the family stays on legacy benefits. UC childcare tests distinguish claimant and partner limbs. |
| 2.123.10 | [#2025](https://github.com/PolicyEngine/policyengine-uk/pull/2025): Income Support work and JSA gates | `income_support_remunerative_work_hours` supplies the work gate; claimant/partner hour thresholds apply subject to the source's carer exception. The claimant's JSA of either kind and partner's income-based JSA bar the claim, with stored-precision award comparisons. Fiscal Income Support and its passport interactions can change. |
| 2.124.0 | [#2201](https://github.com/PolicyEngine/policyengine-uk/pull/2201): reported benefit-unit capital | New `benunit_reported_capital` feeds UC and Pension Credit's programme capital formulas. Stored inputs uprate like savings; direct situation inputs apply only in the supplied years. The certified data's recorded capital therefore reaches PC without the old household wealth proxy, with downstream HB/CTR income/capital interactions. No engine capital formula is substituted. |
| 2.124.0 | [#2192](https://github.com/PolicyEngine/policyengine-uk/pull/2192): build metadata | Package metadata now returns only policyengine-uk's own checkout or installer git record, not the enclosing analysis repository's head. This touches certification metadata rather than a fiscal mechanism. The engine also records installed package versions, dataset SHA and analysis source hashes. |
| 2.124.0 | [#2227](https://github.com/PolicyEngine/policyengine-uk/pull/2227): employer NI levy | Corrects the 2022–23 employer Class 1 rate to 15.05% and its November end date. `ni_employer` and historical tax accounts read the schedule. |
| 2.125.0 | [#2027](https://github.com/PolicyEngine/policyengine-uk/pull/2027): claimant/partner legacy awards | New claimant/partner ESA/JSA amounts replace whole-benefit-unit awards in HB/CTR/tax-credit income and their passports, Scottish Child Payment and targeted childcare. Person-level payable-status variables scope local CTR non-dependant exemptions and the student support schedule to the payee. Income Support claiming requires claimant/partner reports. Total ESA/JSA awards remain in household income. |
| 2.125.1 | [#2058](https://github.com/PolicyEngine/policyengine-uk/pull/2058): Class 2 and Class 4 NI | Class 2 tests Class 4 profits and the corrected small/lower-profit thresholds, weekly rate, contribution-week count and abolition date; the UC notional floor shares the Class 2 helper. Historical Class 4 rates/limits are corrected. National Insurance is tax; UC's floor is a spending dependency. |

The only intervening release without a runtime or metadata implication here is 2.123.9 ([#2199](https://github.com/PolicyEngine/policyengine-uk/pull/2199), CI concurrency and timeouts). Documentation/versioning changes are not fiscal mechanisms. `dynamics/participation.py` removes an unused raw-head calculation; this engine does not invoke that dynamic participation model. `programs.yaml` is registry metadata. The appendix below inventories all changed upstream runtime/parameter paths so the scope can be checked independently of this grouping.

## Guarded formulas, horizons and port choices

`model_horizon.check_upstream()` checks the installed 2.125.1 wheel against the source read for this audit and passes. Of the original guarded files, only `basic_state_pension`, `new_state_pension`, `additional_state_pension` and `simulation` changed; their new hashes were installed after reading their complete diffs. Guards for raw and resolved household-head definitions were added because the latter is now read by the engine.

`GOV_TAX_VARIABLES`, `GOV_SPENDING_VARIABLES` and `gov_balance` are byte-identical to the pilot. The engine still mirrors the council-tax abolition conditional and expands `state_pension` into basic, new and additional parts. Its accounting checks compare the sum with upstream `gov_balance` and independently bridge government and household income. The UK/GB masks still follow household `country` and project membership to people and benefit units; the underlying country/region definitions are unchanged. `UNKNOWN` remains outside GB.

All horizon builders are unchanged. Lagged CPI/earnings and statutory triple lock already cover beyond the final analysis year, economic indices reach 2039, and the fiscal conversion covers 2015–2040. The sole retained horizon extension is `create_private_pension_uprating.YEARS`: upstream still stops at 2034; the engine extends it to 2042. The existing processed-tree differential test checks that no other parameter series changes through 2039.

State Pension type, date-of-birth helpers, own pensionable-age timetable, `is_SP_age`, birthday draw, stochastic draw and reported-pension formula are unchanged. The demography treatment retains its fixed represented ages, birthday, ONS growth rake, data calibration anchor and cohort types. It preserves raw survey household/benefit-unit head flags and now clears the new age-derived resolved household head with the other age-derived values after pinning. No raw head flags are replaced by invented survey nominations.

The additional-pension formula still uprates by the flat-rate ratio in 2.125.1. The engine's September-CPI pin is therefore retained. The Pension Credit guarantee's upstream CPI uprating also remains, so the engine's statutory-earnings guarantee override remains. The historical actual-law fixed-denominator reform remains because this engine intentionally drops the Scenario's comparator; the new upstream denominator chooses current parameters when no comparator exists.

Package version provenance now includes `policyengine` as well as UK/core and numerical dependencies. Coverage support receipts include State Pension and CTR alongside PC, total HB and pension-age HB, counting only positive-weight contributors. This supplies the bridge's ten-record and complementary-suppression checks without publishing survey rows.

The model-version bridge step includes the core upgrade and this engine port. Unless separate same-version engine runs isolate it, it must not be represented as the isolated effect of any one upstream PR. The data step compares the certified model and port on the two pinned data files.

## Actual certified-model preflight

The synthetic `housing_benefit_passport_preflight` passed all 17 checks on policyengine-uk 2.125.1. With claims as supplied, the synthetic entitled non-claimant receives no HB and the Pension Credit claimant receives maximum HB. Reversing only `in_receipt_of_guarantee_credit` reverses the income, tariff and capital passports and HB amounts, while preserving positive entitlement and the claim pattern. These are hypothetical household checks, not licensed survey observations. No preflight requirement was relaxed.

The focused synthetic/formula suite and the full repository tests are recorded in the Part J state/report after completion. Microcosm's compatibility is established only by the separate full dataset load/run; it is not certified by this model bundle.

## Complete changed-path inventory

208 upstream runtime, parameter and registry paths changed between the two tags (excluding upstream tests). Paths below are relative to `policyengine_uk/`.

| Status | Path |
| --- | --- |
| changed | `build_metadata.py` |
| changed | `data/uprating_indices.yaml` |
| changed | `dynamics/participation.py` |
| changed | `parameters/gov/dcms/bbc/tv_licence/discount/aged/discount.yaml` |
| changed | `parameters/gov/dcms/bbc/tv_licence/discount/aged/min_age.yaml` |
| changed | `parameters/gov/dcms/bbc/tv_licence/discount/aged/must_claim_pc.yaml` |
| changed | `parameters/gov/dfe/targeted_childcare_entitlement/qualifying_benefits.yaml` |
| added | `parameters/gov/dft/bus/boardings_per_trip.yaml` |
| added | `parameters/gov/dft/bus/default_single_fare_share.yaml` |
| added | `parameters/gov/dft/bus/fare_index.yaml` |
| added | `parameters/gov/dft/bus/fares/cap.yaml` |
| added | `parameters/gov/dft/bus/fares/index.yaml` |
| added | `parameters/gov/dft/bus/prior_law_fare_index.yaml` |
| added | `parameters/gov/dft/bus/reference_fares/cap.yaml` |
| added | `parameters/gov/dft/bus/reference_fares/index.yaml` |
| added | `parameters/gov/dft/bus/reference_year.yaml` |
| added | `parameters/gov/dft/bus/ridership_index.yaml` |
| added | `parameters/gov/dft/bus/uncapped_single_fare.yaml` |
| added | `parameters/gov/dft/bus/yield_per_boarding.yaml` |
| added | `parameters/gov/dwp/income_support/eligibility/remunerative_work/claimant_hours.yaml` |
| added | `parameters/gov/dwp/income_support/eligibility/remunerative_work/partner_hours.yaml` |
| changed | `parameters/gov/dwp/pension_credit/guarantee_credit/income.yaml` |
| changed | `parameters/gov/dwp/tax_credits/means_test/income_reduction_rate.yaml` |
| changed | `parameters/gov/dwp/universal_credit/means_test/capital/sources.yaml` |
| added | `parameters/gov/dwp/universal_credit/means_test/minimum_income_floor/ineligible_partner_hours.yaml` |
| added | `parameters/gov/dwp/universal_credit/means_test/minimum_income_floor/no_requirements_partner_hours.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/interview_or_preparation_threshold_hours.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/child_age/interview_only.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/child_age/no_requirements.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/child_age/work_preparation.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/expected_hours/below_compulsory_school_age.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/expected_hours/child_age_limit.yaml` |
| added | `parameters/gov/dwp/universal_credit/work_requirements/responsible_carer/expected_hours/compulsory_school_age.yaml` |
| changed | `parameters/gov/hmrc/child_benefit/README.md` |
| added | `parameters/gov/hmrc/child_benefit/opt_out_charge_share.yaml` |
| changed | `parameters/gov/hmrc/income_tax/allowances/property_allowance.yaml` |
| changed | `parameters/gov/hmrc/income_tax/income_tax_subtractions.yaml` |
| added | `parameters/gov/hmrc/income_tax/reliefs/property_finance_costs/disallowed_share.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_1/rates/employee/main.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_1/rates/employer.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_1/thresholds/secondary_threshold.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_2/flat_rate.yaml` |
| added | `parameters/gov/hmrc/national_insurance/class_2/lower_profits_threshold.yaml` |
| added | `parameters/gov/hmrc/national_insurance/class_2/lower_profits_threshold_applies.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_2/small_profits_threshold.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_4/rates/additional.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_4/rates/main.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_4/thresholds/lower_profits_limit.yaml` |
| changed | `parameters/gov/hmrc/national_insurance/class_4/thresholds/upper_profits_limit.yaml` |
| changed | `parameters/gov/hmrc/vat/reduced_rate.yaml` |
| changed | `parameters/gov/ofgem/energy_price_cap.yaml` |
| changed | `parameters/gov/ofgem/energy_price_guarantee.yaml` |
| added | `parameters/gov/ofgem/energy_price_guarantee_in_effect.yaml` |
| added | `parameters/gov/ofgem/energy_price_guarantee_prepayment_discount.yaml` |
| changed | `parameters/gov/social_security_scotland/two_child_limit_payment/in_effect.yaml` |
| changed | `parameters/gov/treasury/energy_bills_rebate/energy_bills_credit.yaml` |
| added | `parameters/gov/treasury/energy_bills_rebate/energy_bills_credit_monthly.yaml` |
| added | `parameters/gov/treasury/energy_bills_rebate/energy_bills_credit_northern_ireland.yaml` |
| changed | `programs.yaml` |
| changed | `simulation.py` |
| changed | `utils/benefit_unit.py` |
| added | `utils/bus_fares.py` |
| added | `utils/child_benefit.py` |
| added | `utils/class_2.py` |
| changed | `utils/supplied_inputs.py` |
| added | `utils/tenure.py` |
| added | `utils/uc_work_related_requirements.py` |
| changed | `variables/gov/dcms/bbc/tv_licence/tv_licence_discount.py` |
| changed | `variables/gov/dfe/maintenance_loans/maintenance_loan_entitled_to_benefits.py` |
| changed | `variables/gov/dfe/maintenance_loans/maintenance_loan_household_income.py` |
| changed | `variables/gov/dfe/maintenance_loans/maintenance_loan_living_arrangement.py` |
| added | `variables/gov/dft/bus_fare_spending_reported.py` |
| added | `variables/gov/dft/bus_in_london_trips.py` |
| added | `variables/gov/dft/bus_pass_eligible.py` |
| added | `variables/gov/dft/local_bus_single_fare_share.py` |
| added | `variables/gov/dft/local_bus_trips.py` |
| added | `variables/gov/dft/local_bus_uncapped_single_fare.py` |
| added | `variables/gov/dft/other_local_bus_trips.py` |
| changed | `variables/gov/dft/person_bus_fare_spending.py` |
| added | `variables/gov/dwp/_legacy_award_payee.py` |
| changed | `variables/gov/dwp/additional_state_pension.py` |
| changed | `variables/gov/dwp/basic_state_pension.py` |
| added | `variables/gov/dwp/claimant_or_partner_esa_income.py` |
| added | `variables/gov/dwp/claimant_or_partner_jsa_income.py` |
| changed | `variables/gov/dwp/council_tax_benefit.py` |
| changed | `variables/gov/dwp/esa_income.py` |
| changed | `variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_applicable_income.py` |
| changed | `variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_tariff_income.py` |
| changed | `variables/gov/dwp/housing_benefit/housing_benefit_assessable_capital.py` |
| changed | `variables/gov/dwp/housing_benefit/housing_benefit_on_passporting_benefit.py` |
| changed | `variables/gov/dwp/in_receipt_of_income_support_jsa_ib_or_esa_ir.py` |
| changed | `variables/gov/dwp/income_support_applicable_income.py` |
| changed | `variables/gov/dwp/income_support_eligible.py` |
| added | `variables/gov/dwp/income_support_remunerative_work_hours.py` |
| changed | `variables/gov/dwp/is_benefit_cap_exempt_health_disability.py` |
| changed | `variables/gov/dwp/is_benefit_cap_exempt_other.py` |
| changed | `variables/gov/dwp/is_benefit_cap_single_claimant_rate.py` |
| changed | `variables/gov/dwp/is_lha_shared_accommodation_rate_specified_renter.py` |
| changed | `variables/gov/dwp/is_non_dependant_of_household_head.py` |
| added | `variables/gov/dwp/is_on_income_based_jsa.py` |
| added | `variables/gov/dwp/is_on_income_related_esa.py` |
| added | `variables/gov/dwp/is_on_income_support.py` |
| changed | `variables/gov/dwp/jsa_income.py` |
| changed | `variables/gov/dwp/new_state_pension.py` |
| changed | `variables/gov/dwp/pension_credit/guarantee_credit/is_guarantee_credit_eligible.py` |
| changed | `variables/gov/dwp/pension_credit/pension_credit_reported_capital.py` |
| changed | `variables/gov/dwp/tax_credits_applicable_income.py` |
| changed | `variables/gov/dwp/universal_credit/carer_element/uc_carer_element.py` |
| changed | `variables/gov/dwp/universal_credit/childcare_element/uc_childcare_work_condition.py` |
| changed | `variables/gov/dwp/universal_credit/disability_element/limited_work_ability/uc_LCWRA_element.py` |
| changed | `variables/gov/dwp/universal_credit/housing_costs_element/non_dep_deduction/uc_non_dependants_counted.py` |
| changed | `variables/gov/dwp/universal_credit/income/income_floor/uc_mif_applies.py` |
| changed | `variables/gov/dwp/universal_credit/income/income_floor/uc_minimum_income_floor_gross.py` |
| changed | `variables/gov/dwp/universal_credit/income/income_floor/uc_minimum_income_floor_national_insurance.py` |
| changed | `variables/gov/dwp/universal_credit/income/uc_income_tax_on_earnings.py` |
| changed | `variables/gov/dwp/universal_credit/is_uc_claimant.py` |
| changed | `variables/gov/dwp/universal_credit/is_uc_eligible.py` |
| added | `variables/gov/dwp/universal_credit/is_uc_single_or_joint_claimant.py` |
| changed | `variables/gov/dwp/universal_credit/standard_allowance/uc_standard_allowance_claimant_type.py` |
| changed | `variables/gov/dwp/universal_credit/uc_assessable_capital.py` |
| added | `variables/gov/dwp/universal_credit/uc_member_of_couple_claims_as_single_person.py` |
| changed | `variables/gov/dwp/universal_credit/uc_reported_capital.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_expected_hours.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_has_limited_capability_for_work.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_adopter_in_first_year.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_foster_parent_or_new_friend_or_family_carer.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_in_gainful_self_employment.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_in_pregnancy_or_post_confinement_period.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_ineligible_partner.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_responsible_carer.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_responsible_foster_parent_of_child_under_one.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_is_student_with_no_work_related_requirements.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_work_related_group_apart_from_earnings.py` |
| added | `variables/gov/dwp/universal_credit/work_related_requirements/uc_youngest_child_age.py` |
| changed | `variables/gov/dwp/would_claim_IS.py` |
| changed | `variables/gov/dwp/youngest_child_age_for_legacy_benefits.py` |
| changed | `variables/gov/hmrc/child_benefit.py` |
| changed | `variables/gov/hmrc/child_benefit_opts_out.py` |
| changed | `variables/gov/hmrc/high_value_council_tax_surcharge.py` |
| changed | `variables/gov/hmrc/income_tax/allowances/property_allowance_deduction.py` |
| added | `variables/gov/hmrc/income_tax/allowances/property_allowance_deduction_if_used.py` |
| added | `variables/gov/hmrc/income_tax/allowances/property_receipts_within_allowance.py` |
| added | `variables/gov/hmrc/income_tax/allowances/uses_property_allowance.py` |
| added | `variables/gov/hmrc/income_tax/bases/deductible_property_finance_costs.py` |
| added | `variables/gov/hmrc/income_tax/bases/property_allowable_expenses.py` |
| changed | `variables/gov/hmrc/income_tax/bases/taxable_property_income.py` |
| changed | `variables/gov/hmrc/income_tax/charges/child_benefit_hitc.py` |
| changed | `variables/gov/hmrc/income_tax/other_tax_credits.py` |
| added | `variables/gov/hmrc/income_tax/reliefs/property_finance_cost_relief.py` |
| added | `variables/gov/hmrc/income_tax/reliefs/property_finance_costs_carried_forward.py` |
| added | `variables/gov/hmrc/income_tax/reliefs/property_finance_costs_relievable.py` |
| added | `variables/gov/hmrc/income_tax/reliefs/property_finance_costs_relieved.py` |
| changed | `variables/gov/hmrc/national_insurance/class_2/ni_class_2.py` |
| changed | `variables/gov/hmrc/national_insurance/class_4/ni_class_4_maximum.py` |
| changed | `variables/gov/hmrc/would_claim_child_benefit.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/_legacy.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/benunit_contains_household_head.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/config.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_applicable_income.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_applicant_has_non_dep_exemption.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_claim_pensioner.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_claim_scheme_supported.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_claims_are_joint.py` |
| added | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_head_applies_alone.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_household_has_non_dep_exemption.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_household_has_pensioner.py` |
| added | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_household_has_simulated_claim.py` |
| removed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_household_head.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_liable_person.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_pensioner.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_relevant_income_based_benefit.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/council_tax_reduction_scheme_supported.py` |
| added | `variables/gov/local_authorities/council_tax_reduction/is_council_tax_reduction_applicant_or_partner.py` |
| changed | `variables/gov/local_authorities/council_tax_reduction/simulated_council_tax_reduction_benunit.py` |
| changed | `variables/gov/local_authorities/kingston_upon_thames/council_tax_reduction/kingston_upon_thames_council_tax_reduction.py` |
| changed | `variables/gov/local_authorities/kingston_upon_thames/council_tax_reduction/kingston_upon_thames_council_tax_reduction_individual_non_dep_deduction.py` |
| changed | `variables/gov/local_authorities/merton/council_tax_reduction/merton_council_tax_reduction.py` |
| changed | `variables/gov/local_authorities/merton/council_tax_reduction/merton_council_tax_reduction_individual_non_dep_deduction.py` |
| changed | `variables/gov/local_authorities/newham/council_tax_reduction/newham_council_tax_reduction.py` |
| changed | `variables/gov/local_authorities/newham/council_tax_reduction/newham_council_tax_reduction_individual_non_dep_deduction.py` |
| changed | `variables/gov/local_authorities/oxford/council_tax_reduction/oxford_council_tax_reduction.py` |
| changed | `variables/gov/local_authorities/oxford/council_tax_reduction/oxford_council_tax_reduction_individual_non_dep_deduction.py` |
| changed | `variables/gov/local_authorities/westminster/council_tax_reduction/westminster_council_tax_reduction.py` |
| changed | `variables/gov/local_authorities/westminster/council_tax_reduction/westminster_council_tax_reduction_individual_non_dep_deduction.py` |
| changed | `variables/gov/social_security_scotland/is_scp_eligible.py` |
| changed | `variables/gov/social_security_scotland/two_child_limit_payment.py` |
| added | `variables/gov/treasury/energy_bills_rebate/ebr_energy_bills_credit_eligible.py` |
| changed | `variables/gov/treasury/energy_bills_rebate/energy_bills_credit.py` |
| added | `variables/gov/treasury/energy_bills_rebate/monthly_ebr_energy_bills_credit.py` |
| changed | `variables/gov/treasury/price_cap_subsidy/monthly_epg_consumption_level.py` |
| changed | `variables/household/consumption/personal_rent.py` |
| changed | `variables/household/consumption/rent/is_liable_for_household_rent.py` |
| changed | `variables/household/consumption/rent/share_of_household_rent.py` |
| added | `variables/household/demographic/benunit_contains_household_head.py` |
| changed | `variables/household/demographic/benunit_is_renting.py` |
| changed | `variables/household/demographic/is_household_head.py` |
| changed | `variables/household/demographic/is_renting.py` |
| added | `variables/household/demographic/is_resolved_household_head.py` |
| changed | `variables/household/income/pays_rent_to_householder.py` |
| added | `variables/household/income/property_income_after_finance_costs.py` |
| added | `variables/household/wealth/benunit_reported_capital.py` |
| changed | `variables/input/consumption/bus_fare_spending.py` |
| changed | `variables/input/consumption/energy.py` |
| changed | `variables/input/main_residence_value.py` |
| added | `variables/input/property_finance_costs.py` |
| added | `variables/input/property_finance_costs_brought_forward.py` |
| changed | `variables/input/property_income.py` |
| added | `variables/input/property_rental_income.py` |
