# d1727 upstream source audit

Read on 24 October 2026 against the released policyengine-uk **2.153.4** wheel and the full [2.125.1…2.153.4 source diff](https://github.com/PolicyEngine/policyengine-uk/compare/2.125.1...2.153.4). No survey records were loaded. The SHA-256s below are wheel source bytes; `model_horizon.check_upstream()` checks them before any engine run. The historical 2.125.1 audit and receipt bytes remain unchanged.

The source gate retains the exact original 2.125.1 module hashes alongside this cut, selected by the installed package's exact version. It refuses every other version and checks every file for the selected version. This lets the committed bundle remain testable while the new pair's ledger qualification is pending; source review does not constitute data certification or authorize a pin change.

## Changed existing guards

Every changed file in the previous `model_horizon.UPSTREAM` was read. All other existing entries retain their original hashes. Paths below are relative to `policyengine_uk/`.

| File | SHA-256 in 2.153.4 | Law or model effect |
| --- | --- | --- |
| `parameters/gov/dwp/state_pension/triple_lock/create_triple_lock.py` | `f09e1e8c0eb780160bc82cdad6395166157c50a8526d9c1c39cbf9f2d7c8e48d` | Moves published-precision rounding to the shared statutory helper; the existing triple-lock rule is unchanged. |
| `parameters/gov/economic_assumptions/create_economic_assumption_indices.py` | `30a4da9498bff121f2e704884b4716687a4d356cff6d750ba7bfb258dd5ccbad` | Marks calendar-year indices and stops rounding the earnings index to five decimals, protecting the earnings floor; other indices retain rounding. |
| `parameters/gov/economic_assumptions/create_statutory_uprating_inputs.py` | `d0d1f73c43de6e0d64d08d54ba560e0e2e23a24f6f7ca80d578524bb1462af50` | Provides shared half-away-from-zero rounding to the ONS published 0.1 percentage point precision; statutory input horizons are unchanged. |
| `simulation.py` | `f7a677923f9358e44a50523e6fc3bc7e17417ed30f3b7557ca1b8d5f625bc105` | Rebuilds dated Scenario changes before data projection, isolates cache use by uprating inputs, preserves supplied-input provenance across reforms/clones, validates entity IDs and adds optional CGT projection metadata. |
| `tax_benefit_system.py` | `003d176278399cd51d895e0d8184b9d31d451e232d0ee619d08459128fe3e972` | Rebuilds reforms from statutory timelines, derives earnings/September-CPI indices and SC/HB amounts before annualisation on tree and baseline, and memoises rebuilt trees; the horizon installer now clears/restores those memos. |
| `utils/dates.py` | `f0da56854b6c7f0a8405162c06747a4a4f98c6b917494e46f5388102076428c6` | Adds April/September/January school-term starts; the State Pension birthday/date calculations read by this engine are unchanged. |
| `utils/parameters.py` | `8ed13881276d1b9a1c72ce8810f9b4fcaba28252c6cfd0761a0c5f2a45ba1793` | Annualises canonical NI descendants, preserves pre-reform backdated values and gives migration errors for removed parameters; fiscal conversion remains 2015–2040. |
| `utils/scenario.py` | `ecdc5358b553ca56ea7090ab9d64acef5b71b593c61548285cf6c3bf9fcb9d48` | Distinguishes statutory-time construction from annualised runtime overrides, preserves before/after-load ordering in sums and retains dated reforms across rebuilds. |
| `variables/gov/dwp/additional_state_pension.py` | `59756afa1279d478bcc94983f27c7c7076e80cfd9c915f5abdb85af1cf07ef5e` | #2336 uprates the add-on/protected payment by September CPI from the data year, independently of full-rate reforms (SSAA 1992 ss150/151A; SI 2026/148 arts 4/6). |
| `variables/gov/dwp/basic_state_pension.py` | `477a158655fc1d74d59eb9a97e3fce69870fe7415aed34846f316ecc562ea407` | Uses masked numpy division at a zero legislated cap; the nonzero-cap flat-share formula and type/age eligibility are unchanged. |
| `variables/gov/dwp/new_state_pension.py` | `f5ff9f73cfb267a1fa69e635089e0b6a6518405824c9bc549210aba0050f812e` | Uses masked numpy division at a zero legislated cap; the nonzero-cap flat-share formula and type/age eligibility are unchanged. |
| `variables/gov/gov_spending.py` | `14829a2571a1baa187deab4a6859da1e24815735e318fb837da7e874dbe81e17` | Adds war widow/parent and statutory paternity benefits plus Healthy Start, two-child-limit and Scottish Child Payments to total spending; engine.fiscal_variables reads this installed list. |
| `variables/gov/gov_tax.py` | `3d3c151d58a5ede6c7c01dcbdef15012fa24100da40947d5769b156dd31988a9` | Adds gambling duty to tax receipts; engine.fiscal_variables reads this installed list. |
| `variables/household/demographic/months_since_last_birthday.py` | `aac44746d7996e6dc721b8ccd4fede455f867732e20d301cc433b25a49ac1212` | Uses the built_from_data helper instead of only a flag for survey birthday imputation; the deterministic stratification and situation treatment remain the same. |

## Pension and uprating rules added to the guard

The [#2576 diff](https://github.com/PolicyEngine/policyengine-uk/pull/2576/files), [#2557 diff](https://github.com/PolicyEngine/policyengine-uk/pull/2557/files) and [#2336 diff](https://github.com/PolicyEngine/policyengine-uk/pull/2336/files) were read separately. The following builders and YAML metadata are now guarded as well; the complete SHA-256 values are in `model_horizon.UPSTREAM` and `UPSTREAM_PARAMETERS`.

| File | Model effect read in the source |
| --- | --- |
| `parameters/gov/economic_assumptions/create_earnings_uprating.py` | Compounds the previous May–July AWE increase at published precision with a zero floor, implementing the Pension Credit earnings minimum (SSAA 1992 s150A(2)). |
| `parameters/gov/economic_assumptions/create_september_cpi_uprating.py` | Compounds the previous September CPI at published precision with a zero floor; runs to one year after the statutory inputs. |
| `parameters/gov/dwp/pension_credit/guarantee_credit/minimum_guarantee.yaml` | Preserves published rates through 2026 and projects later guarantees by the earnings index. |
| `parameters/gov/dwp/pension_credit/savings_credit/create_savings_credit_threshold.py` | After published thresholds, derives guarantee minus maximum divided by phase-in; zero phase-in retains the threshold previously in force. |
| `parameters/gov/dwp/pension_credit/savings_credit/{maximum,threshold}.yaml` | The maximum follows benefit September CPI; threshold metadata delegates projection to the guarantee/maximum identity. |
| `parameters/gov/dwp/housing_benefit/allowances/create_pension_age_allowances.py` | Derives pre-April 2021 pension-age HB allowances as guarantee plus maximum Savings Credit for single/couple/lone parent (SI 2006/214 Sch 3; HB A3/2021). |
| `parameters/gov/dwp/housing_benefit/allowances/{single,couple,lone_parent}/aged.yaml` | Published higher allowances are retained; projected amounts use the builder above. |
| `parameters/gov/dwp/housing_benefit/allowances/{single,couple,lone_parent}/aged_from_cutoff.yaml` | Post-April 2021 allowances follow the earnings index from their published amounts, equal to the corresponding guarantee. |
| `parameters/gov/benefit_uprating_cpi.yaml` | #2557 replaces lagged calendar CPI with the September-CPI index for benefit uprating. |
| `parameters/gov/economic_assumptions/statutory_uprating_inputs/{cpi_september,awe_total_pay_may_july}.yaml` | Sets the 2026 observations to 3.5% CPI and 3.9% AWE; future missing observations are completed from the supplied path. |

The `variables/input/state_pension.py` aggregate was also read: its SHA-256 remains `549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352`. It still sums basic + additional + new pension, applies the contributor uplift and respects abolition. **#2340 is absent** from 2.153.4: GitHub reported it OPEN and draft on 24 October, head `bc81c88913d9430365e9c9ca03a122d4c4410dd2` (updated 12:16:44Z). The compatibility script checks the absent-variable route on this cut. For a future present-variable run it now checks the exact 25p weekly amount and eligibility for each invented person as well as cross-policy equality, preventing a shared eligibility error from passing.

## Horizon and input precedence

The private-pension builder is unchanged and still has `YEARS=2020…2034`, so its extension to 2042 remains necessary. General economic indices still generate through 2039 and fiscal conversion still covers 2015…2040. New Scenario rebuild caches hold trees produced with the builder horizon but their keys do not include that horizon. `install()` therefore invalidates the processed/statutory/projected caches and rebuild memo; `installed()` restores all four afterwards. This prevents a cached pre-extension Scenario from reintroducing the short private-pension horizon.

The additional-pension check passed on UK 2.153.4 / core 3.33.3: eight invented households, two CPI paths (one containing negative inflation) and both policy settings in 2024, 2027, 2031 and 2039. Every pinned add-on matched the independently compounded path CPI and differed from the installed default by 2031; historical-denominator accounting also passed. For the first invented recipient, the model's default 2031 add-on was £118.3823, against pinned £117.2545 on the steady path and £125.8153 on the volatile path. The equivalent standalone command is:

```bash
PYTHONPATH=src .bundle-work/venv/bin/python scripts/check_state_pension_upstream.py --expect-age-addition absent
```

The behavioural HB passport preflight passed on 2.153.4 through `tests/test_passport_preflight.py::test_the_installed_policyengine_uk_meets_the_guard_only_with_1927`. It uses two synthetic pensioners and reverses explicit Guarantee Credit receipt; it requires no survey data. All named entitlement, capital, income, claim and receipt checks passed. Its standalone command is:

```bash
PYTHONPATH=src .bundle-work/venv/bin/python -c 'from triple_lock.pipeline import housing_benefit_passport_preflight; housing_benefit_passport_preflight()'
```

`check_upstream()` passed against the installed source and YAML hashes. A static comparison also confirmed that all 30 legacy guard entries exactly equal the original committed map. The focused suite covering horizon guards, exact future age-addition eligibility, State Pension accounting and passport admission passed 238 tests; two passport admission unit tests passed on a focused rerun after their certification prerequisite was stubbed. Those tests now isolate the passport failure when the throwaway model differs from the committed bundle; certification admission remains tested separately. Python compilation and the whitespace check also passed.

## Later release check

A 2.153.5 tag existed during preparation. Its diff from 2.153.4 was read: 18 files cover domestic-energy VAT, coverage metadata, documentation, tests and version/lock files; no guarded file or pensioner entitlement rule changed. The requested pin remains 2.153.4.
