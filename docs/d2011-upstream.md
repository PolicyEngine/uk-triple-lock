# d2011 Budget-wheel upstream source audit (policyengine-uk 2.151.0)

Read on 25 October 2026 from the released **policyengine-uk 2.151.0** wheel, compared file by file with **2.147.2**, the model of #715's a133f37a pair. 2.151.0 is the model of the pair d2011 recommends: María's national Microcosm cut `a6299504`, built at microcosm#1396 (`67ee2ddf3`). That commit's `uv.lock` pins this wheel (SHA-256 `5722f55aca3eb88e1a228e95e1a57e3bd70a4d530a5a000991565ebd8955ce35`) with policyengine-core **3.33.3**, the core already attested for 2.147.2.

`data/certification/d2011-model-wheel.json` attests the wheel. Its archive SHA-256 equals PyPI's release metadata, and every one of its 3,176 RECORD members was checked for digest and size. The generator first reproduced the committed `d1983-model-wheel.json` byte for byte from PyPI's 2.147.2 wheel. No survey or Microcosm records were loaded.

`model_horizon.UPSTREAM_2151` and `UPSTREAM_2151_PARAMETERS` name the 2.151.0 bytes, and `check_upstream()` accepts that exact version alongside 2.125.1, 2.147.2 and the historical 2.153.4. The 2.147.2 absence guards apply to 2.151.0 too. Max ruled **d2011 = A** on 25 October, so the binding pins now name this pair: UK 2.151.0 in `pyproject.toml` and the lock, and Microcosm a6299504 in `datasets.py` and `config.PRIMARY_DATASET`. Certification stays closed until a policyengine.py release carries the pair. #715's pair (2.147.2 / a133f37a) stays registered as d2011's fallback.

## Every changed guard

Of the 30 guarded modules, 3 differ in 2.151.0. All 11 guarded parameter files differ. Each complete diff was read. Paths are relative to `policyengine_uk/`.

| File | SHA-256 in 2.151.0 | Law or model effect read in source |
| --- | --- | --- |
| `variables/gov/gov_tax.py` | `3d3c151d58a5ede6c7c01dcbdef15012fa24100da40947d5769b156dd31988a9` | Adds `gambling_duty` (#2590) to `GOV_TAX_VARIABLES`. The formula and its council tax conditional are unchanged. `engine.fiscal_variables` imports the installed list, so gambling duty enters both gov_balance and its decomposition. |
| `variables/gov/gov_spending.py` | `14829a2571a1baa187deab4a6859da1e24815735e318fb837da7e874dbe81e17` | Adds `widowed_parents_allowance` (#2573) to `GOV_SPENDING_VARIABLES`, with the same conditionals. It enters the decomposition the same way. |
| `simulation.py` | `0aadac70bd31d62fb23fbb81363ffecea5aac6ca98ac4a0d6bf391727204ea71` | Four build routes now set `self.dataset` before `build_from_multi_year_dataset` rather than after it. `set_input` now calls `input_dataframe.hold_identifiers_in`, which sets the identifiers for the year an input starts in only when the simulation holds them solely for later years. A core Dataset's energy price basis is passed to its single-year projection. Scenario and reform application are untouched: `utils/scenario.py` and `tax_benefit_system.py` are byte-identical to 2.147.2. |
| `parameters/gov/benefit_uprating_cpi.yaml` | `860e8aa55c5456588823cf572027048ab90ab42e2a3c9a2eabce35c6777341b1` | #2557. The index's uprating moves from `gov.economic_assumptions.indices.obr.lagged_cpi` to `gov.economic_assumptions.indices.september_cpi_uprating`, so April Y rises by September Y−1 CPI, to 0.1 point and never cut (SSAA 1992 s150; HCWS1101; the SI 2026/148 EM). The 81 uprating entries in 2.151.0's parameters that name this index (80 in 2.147.2) follow it. |
| `parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml` | `a0dec724311b165bd5cc060a1cbcccd6953b5ac6f5fb18bd8ed1690c5df45b8d` | Both families now name `obr.lagged_cpi` themselves (comment: reviewed against earnings under s150A(1)(d)), keeping the projection they reached through `gov.benefit_uprating_cpi` on 2.147.2. The engine sets the guarantee from each path's May–July earnings in every run regardless. |
| `parameters/gov/dwp/pension_credit/savings_credit/threshold.yaml` | `efafcca3b8b63181cf233ae67755382c774b3b4b626855e776393c8da801b5fd` | Names `obr.lagged_cpi` itself (comment: the threshold rose 4.9% in April 2026 against 3.8% September CPI). Same projection as on 2.147.2. |
| `parameters/gov/dwp/housing_benefit/allowances/{single,couple,lone_parent}/aged.yaml` | `22a9275e…`, `501227fb…`, `57237318…` | Each names `obr.lagged_cpi` itself (comment: the pension-age allowances rose 4.75% in April 2026 against 3.8% September CPI). Same projection. |
| `parameters/gov/dwp/housing_benefit/allowances/{single,couple,lone_parent}/aged_from_cutoff.yaml` | `5d1f60d3…`, `9f10e1f2…`, `d2e73703…` | Each names `obr.lagged_cpi` itself (comment: the post-April-2021 allowances equal the guarantee in every year 2021-22 to 2026-27). Same projection. |
| `parameters/gov/economic_assumptions/statutory_uprating_inputs/cpi_september.yaml` | `35fecf09e37ea8c02d4c805d0fc0bea0f0183254e6407b2e9399be0b45bb3e42` | Enters September 2026 CPI, **3.5%** (ONS, 21 October 2026); the first null moves to 2027. Every run replaces the 2026–2038 inputs with its path's. |
| `parameters/gov/economic_assumptions/statutory_uprating_inputs/awe_total_pay_may_july.yaml` | `1ea1e805e8adca251dfe1469874ce3129c835e45c1fff1a4351207dd593ef10a` | Comment and reference only: May–July 2026 stays **3.9%**, unrevised in ONS's 20 October 2026 release. |

Full SHA-256 values for every file are in `model_horizon.py`.

## What this means for the engine

- **Benefit uprating.** `path_following` already has a branch for #2557 models. On 2.151.0 it reads `september_cpi_uprating` from `gov.benefit_uprating_cpi`'s metadata, so it checks each April's benefit uprating against the path's September CPI the year before. On 2.147.2 it checks the previous calendar year's CPI. April 2027 is the change that matters: on 2.151.0 it uses the path's September 2026 input (3.5% on the committed binding inputs) rather than 2.147.2's installed calendar-2026 forecast.
- **Pension Credit, Savings Credit and HB pension-age amounts (d1753).** The guarantee, both Savings Credit thresholds and the six pension-age HB allowances now name lagged calendar CPI themselves. On 2.147.2 they reached the same index through `gov.benefit_uprating_cpi`. #2576's linked builders and the Savings Credit maximum are still absent, so `set_flat_rates` leaves the thresholds and HB amounts on that installed projection while the engine earnings-links the guarantee. d1753's question is unchanged.
- **Fiscal decomposition.** Gambling duty and Widowed Parent's Allowance join the installed lists that `fiscal_variables` reads. The decomposition still sums to gov_balance by construction of those lists; no engine list needs editing.
- **Inputs.** The engine sets its pinned inputs (ages, weights, birthdays, State Pension types, additional State Pension) for the dataset's first year and the run years after it (`engine.pinned_inputs`: `every = {data_year, *years}`, with `data_year` the dataset's first year). A data-built simulation already holds its identifiers from that first year, so `hold_identifiers_in` adds nothing for these inputs.
- **State Pension formulas, State Pension age and the builders `model_horizon` extends** are byte-identical to 2.147.2. The age addition (#2340) is still absent, so the three-part State Pension identity applies.

## Other version-aware changes read on this wheel

PRs between 2.147.2 and 2.151.0 that reach pensioners' benefits, their taxes or the engine's outputs. They change the model, not the engine's mirrored mechanisms. Bridge step (a) measures their effect on the results.

| Change | Code read and behaviour |
| --- | --- |
| #2557 | Besides the files above, `hmrc/council_tax/high_value_surcharge/amount.yaml` moves off `gov.benefit_uprating_cpi` to name `obr.lagged_cpi` itself (it is not an s150 amount), so it keeps its projection. Every rate still naming `gov.benefit_uprating_cpi` follows September CPI. |
| #2575 | `social_security_scotland/pawhp/amount/*.yaml`: Scotland's Pension Age Winter Heating Payment now uprates by `gov.benefit_uprating_cpi` (so September CPI) each April, rounded to the nearest 5p, instead of by the calendar-year CPI index (`indices.obr.consumer_price_index`). |
| #2153 | `tv_licence_free_licence_share.py`: where the free over-75 licence needs Pension Credit, a person of qualifying age must now be in a benefit unit that receives it. Before, any Pension Credit in the household sufficed. Because the triple-lock reforms move Pension Credit receipt, this reaches the TV licence line of gov_tax. |
| #2573 | New `spousal_maintenance_income` counts in Guarantee Credit income (SPC Regs reg 15(5)(d)) and is excluded from Savings Credit qualifying income (reg 9(f)). HB's Savings-Credit-only income route deducts HB's maintenance disregard. New `widowed_parents_allowance` is taxable social security income (ITEPA s577(1)), in gov_spending, with HB, IS and CTR disregards. Both have effect only where a dataset supplies the inputs. |
| #2209 | `housing_benefit/means_test/capital/pension_age/tariff_income/threshold.yaml`: adds the history (£6,000 from April 2006, £10,000 from November 2009). The current value is unchanged. |
| #1864, #2566 | Council tax statutory discounts are modelled. The council tax growth series now holds receipts growth (bills times the tax base), and dataset projection grows each household's bill by it net of household weight growth (`uprate_council_tax`). Council tax does not move with the path; every run records its growth in `not_moving`. |
| #2276, #2531 | The absolute poverty thresholds' deflated years and the after-housing-costs CPI series change. The engine's poverty outputs (`in_relative_poverty_ahc`, `in_poverty_ahc`) read them, so absolute AHC poverty levels move with this wheel. |
| #2590 | Gambling duty is a new consumption tax in gov_tax, computed from gambling inputs a dataset supplies. |

## Verification

Run on 25 October 2026 in two environments built from the committed lock: exact UK 2.147.2 / core 3.33.3, and the same lock with only policyengine-uk changed to 2.151.0. No simulation over a survey or over Microcosm was run.

- **Model-facing tests on 2.151.0:** 379 passed and 5 skipped across `test_model_horizon_upstream`, `test_model`, `test_passport_preflight`, `test_hb_link_comparison`, `test_sc_threshold_comparison`, `test_state_pension_age_addition`, `test_budget_model_projection`, `test_engine_pure`, `test_datasets`, `test_microcosm_primary` and `test_hb_allowance_diagnostic`. `check_upstream()` accepts the wheel, and `test_model`'s horizon and path checks pass. The 2 failures are `test_datasets`' pin-agreement tests, which assert that the installed model equals the binding pin, still 2.147.2. They fail by design in this environment. The skips are the #2576-only HB/SC builder test and, in that run, the then 2.147.2-only Budget-wheel tests.
- **The changed tests:** on 2.151.0, `test_model_horizon_upstream` and `test_budget_model_projection` give 17 passed, 0 skipped. On 2.147.2 they give 12 passed and 5 skipped, the five 2.151.0-only absence-guard cases.
- **Dependent projections:** the guarantee, both Savings Credit thresholds and the six pension-age HB allowances on the installed default path, 2026 to 2039. They differ from 2.147.2's by at most £1.2×10⁻¹³ a week, which is floating-point noise; `obr.lagged_cpi` is identical. `gov.benefit_uprating_cpi` differs, as #2557 intends.
- **`scripts/check_state_pension_upstream.py --expect-age-addition absent` on 2.151.0:** exit 0 over its 8 invented households, age addition absent. The engine's pinned additional State Pension input takes precedence over #2336's formula in 2024, 2027, 2031 and 2039.
- **`housing_benefit_passport_preflight()` on 2.151.0:** passes. The Guarantee Credit passport is keyed on receipt (#1927).
- **Wheel:** `certification._verify_installed_wheel` passes on the 2.151.0 environment against `d2011-model-wheel.json`'s 3,176 members.

Source review, invented-household checks and the wheel attestation do not certify a data pair. The policyengine.py release that certifies d2011's pair must still pass the release-manifest admission before any binding job.
