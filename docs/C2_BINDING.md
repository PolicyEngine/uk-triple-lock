# Binding C2 screen — 28 October 2026

**FAIL → ruling (a), scenarios only.** The original monthly VAR(1) residual
bootstrap fails the registered test-A floor-fraction-bias limit:
**0.26712857142857144 > 0.25**. Its other checks pass. Test B passes every
check. `selected_primary` is `null`, `effective_ruling` is `a`, and
`expected_value_authorized` is `false`. Passing alternatives do not authorize
an expected value and are not promoted or averaged.

This is the binding post-Budget score. It supersedes the [6 October dry run](pilot/C2-dry-run.md)
for the rebuild decision; that historical dry run authorized nothing. C1's
failure remains disclosed: all five forms failed its chronological published-earnings coverage gate, with 1/6 terminal hits. C2 changed the rule after those
scores were seen because Parliament suspended the April 2022 earnings leg.
No PolicyEngine microsimulation or survey data entered this screen.

## Registration, inputs and reproduction

- Frozen pre-registration: `65343e2ee43a359f056ce5a027739509d32ab49f`
  ([METHOD](METHOD.md#model-v2-statutory-uncertainty-screen-pre-registration-c2)),
  committed 6 October 2026 before implementation and before these inputs.
- Exact marked rule-section SHA-256:
  `ce198c838070b175cecefb668b776731333373c8e642030456f736978eb336ac`.
- Input-only commit: `593c355cd75d28d50a2bac732e078c1294873b84`.
- Scoring head, after the runbook's input identity and test-pin updates:
  `2af75405125aa5529f230e05784ab69ccb1ab233`.
- Canonical scoring-input-hashes SHA-256:
  `05b8c65d3cec2729800771d1cd5b4a9d0aa7f0c1da72121af03aaeb46c36efc9`.

```sh
python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2
```

The unchanged screen uses 5,000 draws per origin/form. Its frozen rule hash is
checked before scoring. The handoff validator rejects any `rule_sha` different
from the full pre-registration SHA above, altered frozen rule bytes, stale
code/input hashes, a verdict inconsistent with its scores, omitted complete
origins, or authorization inconsistent with the original-primary verdict.
Input identity updates set September CPI and the 20 October AWE vintage as
[REBUILD](REBUILD.md#inputs-to-update-first) requires; no candidate, threshold,
fit, treatment, legal exclusion or scenario was changed.

The binding readiness guard reports `ready: true`, no missing requirements,
no incomplete forecast windows, CPI period `2026 SEP` and AWE period `2026 JUL`.
September CPI is **3.5%**, published 21 October 2026. May–July AWE is **3.9%**,
from the 20 October 2026 KAC3/KAB9 release. The October revision also changes
July 2025 AWE from 4.9% to 4.8%; statutory outturns follow the existing latest-vintage convention. All required 2026–2030 calendar and quarterly OBR means
identify the 28 October 2026 EFO. Official URLs, publication records and the
manual OBR download route are recorded in [sources](sources.md#binding-c2-inputs-28-october-2026);
[the extraction record](c2-input-extraction.txt) gives workbook cells and checks.

The newly observed September 2026 CPI completes the March 2022 EFO's statutory
four-year window. Its horizon-4 means were recovered from the committed Spring
2026 historical forecasts workbook: `CPI!T29` = 1.9999999999999796% and
`Earnings!T29` = 3.201978355983348%, stored as 0.02 and 0.03202 using the existing
six-decimal convention. Calendar 2026 outturn/error fields remain blank.
Test A now contains **7 origins, March 2016–2022**. Test B contains all **13
complete spring origins, June 2010 and March 2011–2022**. All fits succeed; the score
artifact's failures list is empty.

## Every primary check

Only suspended treatment determines C2. Thresholds below are unchanged from C1.
The earnings leg for determination year 2021 is set equal to CPI in both draws
and outturns. Each test excludes four annual gap cells fixed by that legal
rule. Remaining annual cells receive equal weight: **24 in A, 48 in B**.
All **7 test-A and 13 test-B terminal paths** remain scored; no suspended year is removed from
compounding, lead switches or floor fractions. CPI, floor and joint components
that remain uncertain are still scored.

| Check | Registered requirement | A / suspended | B / suspended | Result |
|---|---|---:|---:|---|
| Origins and fits | Complete expected origins; at least 2; successful fits | 7/7; successful | 13/13; successful | Pass |
| Paths and scores | Finite | Finite | Finite | Pass |
| Annual central-80% coverage | [50%, 100%] | 83.3333% (20/24 cells) | 89.5833% (43/48 cells) | Pass |
| Terminal central-80% coverage | [50%, 100%] | 71.4286% (5/7) | 84.6154% (11/13) | Pass |
| Terminal 95% Wilson band | Contains 80% | [35.8934%, 91.7781%] | [57.7654%, 95.6742%] | Pass |
| Absolute annual gap bias (pp) | ≤ 1.5 | 0.999188183 | 1.168582103 | Pass |
| Absolute switch bias / four-year path | ≤ 1.0 | 0.064914286 | 0.062800000 | Pass |
| Absolute floor-fraction bias | ≤ 0.25 | **0.267128571** | 0.063288462 | **Fail A** |
| Gap CRPS / original primary | ≤ 1.25 | 1.000000 | 1.000000 | Pass |
| Switch CRPS / original primary | ≤ 1.25 | 1.000000 | 1.000000 | Pass |
| Floor CRPS / original primary | ≤ 1.25 | 1.000000 | 1.000000 | Pass |
| Energy / original primary | ≤ 1.25 | 1.000000 | 1.000000 | Pass |
| Variogram / original primary | ≤ 1.25 | 1.000000 | 1.000000 | Pass |
| Uncalibrated past-years realised percentile | [5, 95] | 55.44 (shared past-years check) | 55.44 | Pass |

The primary predicts an A floor frequency of 0.4457 against realised 0.178571429.
Its positive difference breaches the fixed 0.25 limit. Descriptive SEs do not
change that point-estimate gate. Terminal-gap bias is reported below but has
no additional registered threshold.

## Each form's verdict

| Form | Binding C2 verdict | Complete failure list |
|---|---|---|
| VAR(1) bootstrap (primary) | Fail | A/suspended: absolute floor bias 0.267 exceeds 0.25 |
| VAR(2) bootstrap | Pass | None |
| Annual bootstrap + gap blocks | Fail | A/suspended: absolute floor bias 0.271 exceeds 0.25 |
| VAR(1) Student-t | Pass | None |
| VAR(1) Gaussian | Fail | A/suspended: absolute floor bias 0.275 exceeds 0.25 |

VAR(2) bootstrap and Student-t pass individually. Neither replaces the original
primary. The annual form's existing block alignment is unchanged. The automatic
(a) fallback follows the primary failure without another method choice.

The suspended proper-score ratios below compare each form with the original
primary in the same test; every ratio is within the unchanged 1.25 limit.

| Form | Test | Gap CRPS | Switch CRPS | Floor CRPS | Energy | Variogram |
|---|---|---:|---:|---:|---:|---:|
| VAR(1) bootstrap (primary) | A | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| VAR(1) bootstrap (primary) | B | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| VAR(2) bootstrap | A | 1.010707 | 1.071631 | 0.952318 | 1.019966 | 1.044474 |
| VAR(2) bootstrap | B | 1.005055 | 1.072417 | 1.022048 | 1.014624 | 0.968651 |
| Annual bootstrap + gap blocks | A | 1.009440 | 1.063474 | 0.932890 | 0.959028 | 0.914922 |
| Annual bootstrap + gap blocks | B | 1.016858 | 1.152563 | 0.969548 | 0.973602 | 0.934309 |
| VAR(1) Student-t | A | 1.011677 | 1.060784 | 0.972270 | 1.025561 | 1.073092 |
| VAR(1) Student-t | B | 1.001144 | 1.067289 | 1.019024 | 1.016486 | 0.989670 |
| VAR(1) Gaussian | A | 0.997274 | 0.988333 | 1.027367 | 0.996972 | 0.993205 |
| VAR(1) Gaussian | B | 0.998216 | 0.983202 | 1.010232 | 0.998095 | 0.998990 |

## Coverage and bias, with published-earnings sensitivity

Each suspended row is immediately followed by the published-earnings sensitivity,
which never influences C2. Coverage uses central 80% intervals. Bias means
forecast minus realised. Gap/terminal bias is in percentage points, switch bias
in switches per four-year path and floor bias in the fraction of path years
with earnings below 2.5%. Bias entries show mean ± one overlap-adjusted
Newey–West SE (lag 3). These are descriptive SEs from overlapping origins.

Annual scored/excluded cells are 24/4 (A suspended), 28/0 (A published),
48/4 (B suspended), and 52/0 (B published), for every form. No terminal origin
is excluded. Full precision, per-origin rows and independent-origin SEs remain
in [scores.json](../data/pilot/c2-binding/scores.json).

| Test / treatment | Form | Annual coverage | Terminal hits | Gap bias (pp) | Switch bias | Floor bias | Terminal bias (pp) |
|---|---|---:|---:|---:|---:|---:|---:|
| A / suspended | VAR(1) bootstrap (primary) | 83.3% | 5/7 | 0.999 ± 0.439 | 0.065 ± 0.297 | 0.267 ± 0.101 | -0.445 ± 0.560 |
| A / published | VAR(1) bootstrap (primary) | 71.4% | 2/7 | 0.290 ± 0.198 | -0.563 ± 0.500 | 0.215 ± 0.104 | -1.787 ± 0.604 |
| A / suspended | VAR(2) bootstrap | 66.7% | 5/7 | 0.998 ± 0.439 | 0.032 ± 0.304 | 0.243 ± 0.103 | -0.569 ± 0.559 |
| A / published | VAR(2) bootstrap | 57.1% | 2/7 | 0.289 ± 0.199 | -0.610 ± 0.508 | 0.185 ± 0.107 | -1.951 ± 0.606 |
| A / suspended | Annual bootstrap + gap blocks | 79.2% | 5/7 | 0.985 ± 0.456 | -0.148 ± 0.277 | 0.271 ± 0.101 | -0.638 ± 0.566 |
| A / published | Annual bootstrap + gap blocks | 67.9% | 2/7 | 0.276 ± 0.212 | -0.844 ± 0.496 | 0.232 ± 0.102 | -2.049 ± 0.599 |
| A / suspended | VAR(1) Student-t | 62.5% | 5/7 | 0.996 ± 0.439 | 0.023 ± 0.304 | 0.247 ± 0.104 | -0.591 ± 0.554 |
| A / published | VAR(1) Student-t | 53.6% | 2/7 | 0.287 ± 0.198 | -0.623 ± 0.509 | 0.191 ± 0.107 | -1.984 ± 0.605 |
| A / suspended | VAR(1) Gaussian | 83.3% | 5/7 | 0.997 ± 0.439 | 0.086 ± 0.295 | 0.275 ± 0.101 | -0.407 ± 0.555 |
| A / published | VAR(1) Gaussian | 71.4% | 2/7 | 0.288 ± 0.199 | -0.534 ± 0.495 | 0.225 ± 0.104 | -1.736 ± 0.602 |
| B / suspended | VAR(1) bootstrap (primary) | 89.6% | 11/13 | 1.169 ± 0.256 | -0.063 ± 0.283 | 0.063 ± 0.138 | 0.257 ± 0.519 |
| B / published | VAR(1) bootstrap (primary) | 82.7% | 8/13 | 0.773 ± 0.302 | -0.401 ± 0.354 | 0.035 ± 0.125 | -0.466 ± 0.864 |
| B / suspended | VAR(2) bootstrap | 72.9% | 11/13 | 1.167 ± 0.256 | -0.129 ± 0.293 | 0.033 ± 0.141 | 0.091 ± 0.500 |
| B / published | VAR(2) bootstrap | 67.3% | 8/13 | 0.772 ± 0.302 | -0.474 ± 0.355 | 0.002 ± 0.127 | -0.653 ± 0.854 |
| B / suspended | Annual bootstrap + gap blocks | 83.3% | 11/13 | 1.169 ± 0.264 | -0.286 ± 0.289 | 0.069 ± 0.137 | 0.004 ± 0.492 |
| B / published | Annual bootstrap + gap blocks | 76.9% | 8/13 | 0.773 ± 0.309 | -0.661 ± 0.363 | 0.048 ± 0.127 | -0.756 ± 0.849 |
| B / suspended | VAR(1) Student-t | 70.8% | 11/13 | 1.167 ± 0.256 | -0.127 ± 0.294 | 0.038 ± 0.140 | 0.085 ± 0.506 |
| B / published | VAR(1) Student-t | 65.4% | 8/13 | 0.772 ± 0.303 | -0.475 ± 0.360 | 0.008 ± 0.127 | -0.665 ± 0.865 |
| B / suspended | VAR(1) Gaussian | 89.6% | 11/13 | 1.168 ± 0.256 | -0.041 ± 0.282 | 0.071 ± 0.138 | 0.292 ± 0.516 |
| B / published | VAR(1) Gaussian | 82.7% | 8/13 | 0.773 ± 0.303 | -0.376 ± 0.352 | 0.043 ± 0.126 | -0.424 ± 0.859 |

Published terminal coverage is **2/7 in A** for every form, against suspended
5/7; its 95% Wilson band is [8.2219%, 64.1066%] and excludes 80%. Published
B coverage is 8/13. These published sensitivities do not rescue or overturn
the suspended-treatment verdict.

## Proper scores, with published-earnings sensitivity

All scores are lower is better. Entries are mean ± one overlap-adjusted
Newey–West SE (lag 3). CRPS/energy growth components use percentage points;
switch CRPS uses counts; floor CRPS uses path-year fractions. Energy and
variogram retain the registered joint components and pairs.

| Test / treatment | Form | Gap CRPS | Switch CRPS | Floor CRPS | Energy | Variogram |
|---|---|---:|---:|---:|---:|---:|
| A / suspended | VAR(1) bootstrap (primary) | 1.594 ± 0.182 | 0.338 ± 0.109 | 0.207 ± 0.048 | 6.910 ± 1.175 | 17.177 ± 3.707 |
| A / published | VAR(1) bootstrap (primary) | 1.760 ± 0.207 | 0.706 ± 0.080 | 0.170 ± 0.049 | 7.504 ± 1.141 | 18.872 ± 3.634 |
| A / suspended | VAR(2) bootstrap | 1.611 ± 0.190 | 0.362 ± 0.108 | 0.197 ± 0.041 | 7.048 ± 1.205 | 17.941 ± 3.982 |
| A / published | VAR(2) bootstrap | 1.793 ± 0.221 | 0.744 ± 0.081 | 0.158 ± 0.044 | 7.681 ± 1.173 | 20.189 ± 4.017 |
| A / suspended | Annual bootstrap + gap blocks | 1.609 ± 0.173 | 0.360 ± 0.079 | 0.193 ± 0.042 | 6.627 ± 1.076 | 15.716 ± 3.140 |
| A / published | Annual bootstrap + gap blocks | 1.765 ± 0.197 | 0.848 ± 0.148 | 0.167 ± 0.041 | 7.216 ± 1.056 | 17.482 ± 3.191 |
| A / suspended | VAR(1) Student-t | 1.613 ± 0.192 | 0.359 ± 0.104 | 0.202 ± 0.042 | 7.087 ± 1.211 | 18.433 ± 4.124 |
| A / published | VAR(1) Student-t | 1.798 ± 0.223 | 0.748 ± 0.085 | 0.162 ± 0.045 | 7.725 ± 1.175 | 20.714 ± 4.161 |
| A / suspended | VAR(1) Gaussian | 1.590 ± 0.177 | 0.334 ± 0.112 | 0.213 ± 0.050 | 6.889 ± 1.171 | 17.060 ± 3.658 |
| A / published | VAR(1) Gaussian | 1.751 ± 0.202 | 0.689 ± 0.076 | 0.174 ± 0.052 | 7.485 ± 1.135 | 18.708 ± 3.588 |
| B / suspended | VAR(1) bootstrap (primary) | 1.381 ± 0.164 | 0.401 ± 0.072 | 0.179 ± 0.040 | 5.192 ± 1.258 | 14.240 ± 2.880 |
| B / published | VAR(1) bootstrap (primary) | 1.486 ± 0.213 | 0.600 ± 0.088 | 0.159 ± 0.037 | 5.513 ± 1.388 | 15.152 ± 3.190 |
| B / suspended | VAR(2) bootstrap | 1.388 ± 0.174 | 0.431 ± 0.075 | 0.183 ± 0.038 | 5.268 ± 1.301 | 13.793 ± 3.529 |
| B / published | VAR(2) bootstrap | 1.503 ± 0.227 | 0.636 ± 0.091 | 0.162 ± 0.038 | 5.609 ± 1.441 | 15.004 ± 4.008 |
| B / suspended | Annual bootstrap + gap blocks | 1.404 ± 0.160 | 0.463 ± 0.091 | 0.173 ± 0.034 | 5.055 ± 1.151 | 13.304 ± 2.393 |
| B / published | Annual bootstrap + gap blocks | 1.503 ± 0.205 | 0.726 ± 0.124 | 0.159 ± 0.031 | 5.373 ± 1.284 | 14.256 ± 2.773 |
| B / suspended | VAR(1) Student-t | 1.382 ± 0.176 | 0.428 ± 0.075 | 0.182 ± 0.038 | 5.278 ± 1.315 | 14.093 ± 3.681 |
| B / published | VAR(1) Student-t | 1.500 ± 0.230 | 0.638 ± 0.094 | 0.161 ± 0.037 | 5.622 ± 1.456 | 15.321 ± 4.163 |
| B / suspended | VAR(1) Gaussian | 1.378 ± 0.161 | 0.395 ± 0.073 | 0.181 ± 0.042 | 5.183 ± 1.251 | 14.225 ± 2.814 |
| B / published | VAR(1) Gaussian | 1.481 ± 0.209 | 0.586 ± 0.086 | 0.160 ± 0.038 | 5.503 ± 1.381 | 15.112 ± 3.114 |

## Past-years check, with published-earnings sensitivity

Uncalibrated fits stop at December 2010 and simulate determination years
2011–2025; realised future means are not used. The realised terminal policy gap
is 6.207347637% under suspension and 10.793150751% under published earnings.
Only the suspended realised percentile determines C2's [5, 95] check.

| Form | Suspended realised percentile | Published realised percentile (sensitivity) | Suspended check |
|---|---:|---:|---|
| VAR(1) bootstrap (primary) | 55.44 | 91.74 | Pass |
| VAR(2) bootstrap | 68.72 | 97.68 | Pass |
| Annual bootstrap + gap blocks | 51.44 | 88.56 | Pass |
| VAR(1) Student-t | 71.70 | 98.04 | Pass |
| VAR(1) Gaussian | 54.18 | 91.70 | Pass |

VAR(2) and Student-t exceed the 95th percentile under published earnings only.
That sensitivity has no effect on their individual C2 results or the primary's
failure. C2 does not establish calibrated predictive probabilities: origins
overlap, forms share means and residual pools, latest revised inputs are used,
and the model design saw the full sample.

## Data vintages and hashes

The following raw source bytes support the binding inputs. Official URLs,
publication timestamps, the coordinator's browser download and ZIP-member
identity are in [sources](sources.md#binding-c2-inputs-28-october-2026). The
[extraction record](c2-input-extraction.txt) preserves the precise cells used.
All hashes are SHA-256.

| File under `data/raw/` | Vintage / publication | SHA-256 |
|---|---|---|
| `ons_d7g7_cpi_annual_rate.csv` | ONS 21 October 2026; September observation | `f849c7535125edb6532c3c24772247c2dccb241345e6b5122eaa4bf08f69610d` |
| `ons_d7bt_cpi_index.csv` | ONS 21 October 2026; September index | `05bf2ec5459e46961aa994c2cbfdd2abcef5c1591b99659358a414652966bee6` |
| `ons_kab9_awe_total_pay.csv` | ONS 20 October 2026 | `50110c2c139718459acec37fadfef2ad45ef61b6eac34d5efaff36c6690ea9f5` |
| `ons_kac3_awe_total_pay_3m_yoy.csv` | ONS 20 October 2026; May–July | `82dc7689b364f160453bd060931e36e6c8174a4efe7cb34f959877ffdbfd531b` |
| `efo-october-2026-charts-and-tables-chapter-2.xlsx` | OBR 28 October 2026 | `4f045932423cdddba9b2ba7132f0c7cb716dae8b0a0f2a982fba61788e4c6c80` |
| `efo-october-2026-detailed-forecast-tables-zipfile.zip` | OBR 28 October 2026 | `06ac908c69fce7d69dbfda4e16fc3b091a83bd8140ecd2f24990acd13d945fc2` |
| `efo-october-2026-detailed-forecast-tables-economy.xlsx` | Unchanged economy member of preceding ZIP | `96795d1747bb5a4978c7fb768689d5fd31f568e5223db8a94b1bd92ba7f6c118` |
| `Historical_official_forecasts_database_Spring_2026.xlsx` | Spring 2026; existing committed historical source | `e00b17cb7ec8dfddc4bfd4d212c1e93362147fff81d74a10480e599b26e634db` |
| `Long-term-economic-determinants-March-2026-EFO.xlsx` | March 2026 EFO, dated 28 May 2026; unchanged | `8983f5a1ed4912fe5b950e3d9d9fbd0cd973eb8ac47940e622899eeef4d35112` |

The binding guard additionally records these derived input hashes; its seven-file
`data_hashes` also include the four ONS files above. The full score/handoff input
fingerprint includes the historical series and scoring source files.

| Derived input | SHA-256 |
|---|---|
| `data/triple_lock_actual_inputs.csv` | `96bee42882bbc98870efe793112fa2c4ea18f17ba80c9f9960197cab75ec97b1` |
| `data/obr_central_forecast.csv` | `d01a417e5c0b9882f36a4c5e326f09fa351036cd909ad08702e97f778a793eb8` |
| `data/obr_forecast_errors.csv` | `2ff3537738cf1d4e29d459f6c04833efedd0f9fbbd4a8a9f05ab1427d18b6c69` |

The separate `obr_outturn_crosscheck.csv` is deliberately retained from the
pre-Budget comparison, as [sources](sources.md#definitions-and-caveats) explains.
It is fingerprinted but not read by C2 scoring. The latest-vintage convention
above refers to the actual-inputs and monthly files that C2 scores. The owning
session must review the retained crosscheck before dependent rebuild uses;
refreshing it requires a new handoff under the unchanged rule.

## Handoff, bundle and next rebuild

The retained binding JSON artifacts belong in
[`data/pilot/c2-binding/`](../data/pilot/c2-binding/):
[scores](../data/pilot/c2-binding/scores.json),
[selection](../data/pilot/c2-binding/selection.json), and the handoff/design/spec
files produced by the same command. Arrays and strata remain local. The CLI's
separate historical fiscal-estimator output is excluded from this record.
The binding command completed with exit code 0. The committed handoff validates
against the current inputs; a copy with a different rule SHA is refused with
`C2 handoff rule SHA differs from the committed pre-registration`. The
[run receipt](../data/pilot/c2-binding-receipt.json) records these checks and
every committed artifact hash. Future draws use 50,000 draws per form; the
160-slot design and paired scenarios are unchanged. All alternative forms
remain diagnostic and ineligible for a fiscal expected value.
The handoff's generic `rebuild_needs` text mentions passing forms; its C2
selection and per-form fiscal-eligibility flags enforce the primary-only ruling.

Before scoring, code inspection confirmed that `run_candidate_backtest()` reads
historical forecast means, statutory outturns and pre-origin histories. It never
reads `fiscal_year_lted` rows or `central_path()` after 2030. The binding guard
requires the Budget's 2026–2030 calendar/quarterly means and records long-term
sources separately. Future diagnostic handoff draws do use the preserved March
long-term path. They do not enter the scores or decision. Every long-term row
and the March workbook remain unchanged; whether the fiscal rebuild may use
that path after 2030 awaits Max's **d2124**. This record makes no such decision.

Runtime `certified_bundle_preflight()` passed on the unchanged `origin/main`
implementation: **policyengine 6.11.1**, **policyengine-uk 2.151.0**, and
**policyengine-core 3.33.3**, certifying the national Microcosm `a6299504` and
local-area `c9df4b86` pair released under
[policyengine.py #720](https://github.com/PolicyEngine/policyengine.py/pull/720).
Enhanced FRS 1.58.2 remains the designated paired sensitivity. The unused #715 fallback
was not selected. This preflight loads no survey dataset and supplies no fiscal
result.

The rebuild therefore takes **(a) automatically**, omits an expected value and
runs no paired sensitivity.
The scenario envelope remains the central path, OBR wedge, labelled historical
last-decade replay and paired −0.5/+0.5-point earnings-mean paths. No passing
alternative is promoted. The owning uk-triple-lock session handles the bridge,
coverage review, pending d2124 dependency and fiscal rebuild described in
[REBUILD](REBUILD.md); this task stops at the C2 verdict and artifacts.

## Validation and independent review

Independent Subfleet hard review **APPROVE**, job `20261028-132903-review`,
reviewed head `72d798a33bc121c8b915e98373428beafae6bf99` against `origin/main`.
The reviewer found no actionable issues, reproduced 1,020 summary statistics
and checked 55 documentation rows without changing files or running a fiscal
build. [Unchanged review output](../data/pilot/c2-binding-review.txt), SHA-256
`563cc61c6a6748f5b674b7de934803273d661be8b182d2347465a74469736f6a`.

Follow-up hard review `20261028-143615-review` at `b076562` requested changes
for historical test fixtures, the synthetic helper caller and the CI record.
It independently reconfirmed the binding data, unchanged rule, scores and (a)
decision. Those findings were addressed in `124d742`; final approval is recorded below.

The complete raw Actions logs establish this full serial CI history:

| Run / head | Passed | Failed | Skipped | Failure breakdown |
|---|---:|---:|---:|---|
| `40737839616` / `fe532a7` | 2,291 | 32 | 6 | 4 initial input fixtures + 24 further historical fixtures + 4 permitted |
| `40746589626` / `b076562` | 2,294 | 29 | 6 | 24 historical fixtures + 1 synthetic caller + 4 permitted |
| `40757203401` / `124d742` | **2,321** | **4** | **6** | **Only the three documented stale assertions and d2124** |

The first run's counts come from its complete pytest terminal summary
(2,249.69s), not a printed completion JSON. The second run completed all
2,329 selected tests and independently records no errors, `complete: true`
and `interrupted: false` (1,920.18s). The complete Actions
log ZIP supplies the completion and JUnit records. The formatted `gh run view`
output truncates before a 114,725-character assertion line and must not be used
to count failures. CI prints its existing completion/JUnit evidence while
preserving pytest's exact exit code and the unchanged strict checker.

Four failures are permitted by the task and remain unchanged. CI's strict
checker still rejects the d2124 assertion and remains red; this task exception
does not change CI's allowlist or make the draft ready for the fiscal rebuild:

- `tests/test_model.py::test_central_path_sources`: October/March vintage mix,
  conversion error `0.014552500000000003` against `< 0.001`, awaiting d2124.
- `tests/test_results.py::test_not_stale`: sources changed since the retained build.
- `tests/test_results.py::test_assumptions_block_is_current`: retained assumptions
  await the rebuild.
- `tests/test_scenarios.py::test_not_stale`: retained scenario sources await reruns.

The other 25 failures identify historical test fixtures or a synthetic helper
caller. Reconstruction tests now authenticate archived pre-Budget macro bytes
against retained source provenance; exact assertions and tolerances remain.
Pre-Budget adapter fixtures use those bytes only in historical tests, with an
explicit check that live September/October inputs refuse that route. The live
monthly-drift test starts in October after observed September CPI. The shared
historical context also scopes the CPI series used by provenance hashing to
the archived CPI loader and restores both afterward. No source model, fiscal
result, rule or failure threshold was changed; no xfail or failure exemption
was added. The four initial input-pin fixes passed together (208.81s), the
synthetic caller/path replay passed all three cases (77.14s), and the SC/scenario
historical checks passed all three cases (289.71s). The complete adapter module
then passed all **58 tests** (375.02s), including all 21 historical cases, the
live-input refusal, metadata tampering and loader/hash-restoration checks.

The slow duplicate local full run was interrupted after 11 passes and is not
counted as completion. The final full serial run
[`40757203401`](https://github.com/PolicyEngine/uk-triple-lock/actions/runs/40757203401)
at `124d742158fee8c0ebfa103f39d1bfbc291c250d` completed all **2,331 selected
tests**, with no errors or interruption, in 2,100.21s of pytest runtime. Its
four exact assertion reasons were checked against the complete raw log; there
are **no unexpected failures**. Strict CI remains red because its unchanged
checker rejects the d2124 conversion assertion. Fresh integrity verification
also confirms all 12 artifact hashes, the unchanged (a) handoff, wrong-rule-SHA
refusal, rule-before-input ancestry and pipeline equality with `origin/main`.
Final Subfleet hard review **APPROVE**, job `20261028-154612-review`, reviewed
this same head and independently read the completed CI run. No actionable
correctness issue remains. The [unchanged review report](../data/pilot/c2-binding-review-3.txt) has
SHA-256 `1b885c27f49c9eea77668d468f37934187415c5c3d98584affc5935dc67452b6`. The
[validation receipt](../data/pilot/c2-binding-validation.json) records the complete CI evidence,
exact permitted assertion reasons, raw-log hashes, integrity checks and review
history; its SHA-256 is `5fc9231fc26233d9964586e71111e28a2513f474adaac82f4ba0d6fb08d61411`.
The final record commit changes only documentation and validation evidence
after the tested/reviewed head.
