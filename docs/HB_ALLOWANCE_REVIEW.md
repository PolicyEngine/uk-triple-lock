VERDICT: METHOD CHOICE

The earnings-linked Pension Credit guarantee can overtake the protected pension-age Housing Benefit (HB) personal allowance on the committed paths. Continuing the annual policy relationship in a forecast is a methodology decision. Production behaviour is unchanged, as requested when the law leaves the projection open.

## Law

- HB Regulations 2006 regulation 22(1)(a) uses Schedule 3, Part 1, paragraph 1's cash table. It contains no continuing formula linking these personal allowances to a reformed Pension Credit guarantee. The annual Up-rating Orders replace the table: 2025 and 2026 article 24(6)(a), Schedule 6. Protected single/couple allowances are £244.40/£366.00 in 2025–26 and £256.00/£383.35 in 2026–27. Sources: [reg22](https://www.legislation.gov.uk/uksi/2006/214/regulation/22), [Schedule 3 paragraph 1](https://www.legislation.gov.uk/uksi/2006/214/schedule/3/paragraph/1), [2025 Order Schedule 6](https://www.legislation.gov.uk/uksi/2025/295/schedule/6/made), [2026 Order article 24](https://www.legislation.gov.uk/uksi/2026/148/article/24/made) and [Schedule 6](https://www.legislation.gov.uk/uksi/2026/148/schedule/6/made).
- SSAA 1992 s150(1)(h) and (l) includes HB applicable amounts and non-guarantee Pension Credit amounts in the annual price review. They are outside s150(3)'s mandatory minimum-price list, so increases are discretionary under s150(2)(b); s150(7) also empowers increases to income-related amounts. In contrast, s150A(1)(d) and (2) requires the standard minimum guarantee's annual earnings review and an increase at least matching earnings, subject to its rounding provisions. Neither section creates an automatic HB/guarantee link. Sources: [s150](https://www.legislation.gov.uk/ukpga/1992/5/section/150), [s150A](https://www.legislation.gov.uk/ukpga/1992/5/section/150A).
- DWP explicitly describes protected HB allowances as based on the guarantee plus maximum Savings Credit, to protect Savings Credit from HB withdrawal. Pension-age entrants from 1 April 2021 lose that uplift. The 2026 Order gives these newer entrants £238.00/£363.25, equal to that year's guarantee. This is an annual policy convention implemented by cash rates, rather than a statutory forecast formula. Sources: [A3/2021 paragraphs 3–6](https://www.gov.uk/government/publications/housing-benefit-adjudication-circulars-2021/a32021-housing-benefit-person-who-have-attained-the-qualifying-age-for-state-pension-credit-amendment-regulations-2021), [2026 Order Schedule 6](https://www.legislation.gov.uk/uksi/2026/148/schedule/6/made).
- Savings Credit has a statutory **maximum** formula: 60% × (standard minimum guarantee − Savings Credit threshold). The threshold is independently prescribed by regulation 7(2). Raising the guarantee without moving the threshold increases the statutory maximum; keeping the maximum on CPI and solving for the threshold adds a projection assumption. Sources: [Pension Credit Act 2002 s3(7)](https://www.legislation.gov.uk/ukpga/2002/16/section/3), [Pension Credit Regulations 2002 reg7(1)(a), (2)](https://www.legislation.gov.uk/uksi/2002/1792/regulation/7).
- The 2026 Order separately sets guarantees (£238.00/£363.25, art29(2)) and thresholds (£208.07/£329.75, art29(3)). DWP explains a 4.8% earnings increase for the guarantee and a 3.8% CPI increase for maximum Savings Credit (£17.96/£20.10). The HB retained components are £18.00/£20.10: annual cash-table rounding means the single uplift is not exactly the Savings Credit maximum. Sources: [2026 Order art29](https://www.legislation.gov.uk/uksi/2026/148/article/29/made), [A14/2025 paragraphs 5–6 and 20](https://www.gov.uk/government/publications/housing-benefit-adjudication-circulars-2025/a142025-housing-benefit-uprating-for-the-financial-year-ending-march-2027).

A parameter crossing alone establishes no fiscal effect. Guarantee Credit recipients receive HB income/capital disregards, so the effect depends on receipt, applicable income and other model rules: [HB reg26](https://www.legislation.gov.uk/uksi/2006/214/regulation/26). This audit concerns the three existing `aged` parameters; it does not fix the separate post-April-2021 cohort-routing issue.

## Code and upstream verification

The assigned checkout was clean at `ee02c8d808ae`; the branch starts from fetched `origin/main` `eedc6cafb06bcf9b3a435e755ec8e08a5352633f`. Git writes through its original worktree pointer were sandbox-denied, so local metadata in the ignored `.workspace-git` directory handles commits/pushes without modifying the caller's checkout.

Read `config.PENSION_CREDIT_GUARANTEE`, `engine.pension_credit_levels`, `engine.run_path` and `engine.run_coverage`: the config contains only the single/couple guarantee paths; the builder compounds the 2026 base by rounded May–July earnings, floored at zero; the same extra amounts apply under both pension rules. No production engine code overrides HB allowances or Savings Credit thresholds. The existing guarantee following check reads the single guarantee; this audit introduces no new production following checks or legal HB invariant.

Current policyengine-uk main is pinned at [`47642d1ee00e33f98affd32d47e7a5516e5e4bd8`](https://github.com/PolicyEngine/policyengine-uk/tree/47642d1ee00e33f98affd32d47e7a5516e5e4bd8) in the parameter snapshot, including original YAML and hashes. Its three protected `aged.yaml` files carry £256.00 single/lone-parent and £383.35 couple from April 2026 and `uprating: gov.benefit_uprating_cpi`. The certified installed UK 2.125.1 has the same 2026 bases and whole-CPI projections, although some historical rates and labels differ. `hb_allowance_parameter_snapshot.json` preserves both sources rather than treating the installed bundle as current main.

Read [upstream PR #2092](https://github.com/PolicyEngine/policyengine-uk/pull/2092)'s diff at `3c8b9bf7706b4c2fa66b23115fb14c4c45deccdb` and Vahid's 13 October review. Its new builders run in `_add_generated_parameters`, called during `process_parameter_tree`. HB is built from guarantee plus retained uplift, and the Savings Credit threshold from projected guarantee and CPI-grown maximum. The indices are built during processing; a later guarantee reform does not re-derive them. Its HB builder rejects a negative 2026 retained component. Vahid reports six CI failures from base-year guarantee reforms to £300/£459; this audit verifies the guard and ordering in source, **not** a reproduction of those upstream CI cases. Landing #2092 would change the model's default projection. Before regenerating these frozen-snapshot tables on the recertified bundle, refresh the pinned parameter sources and check the diagnostic projection against that bundle; do not assume the current whole-CPI results still describe its default. The experimental HB override is checked after processing, including when future HB levels already exist.

## Parameter results

Reproduce without a dataset:

```sh
.venv/bin/python scripts/diagnose_pension_age_allowances.py
```

The script calls the production guarantee builder and mirrors the model's five-decimal lagged calendar-CPI index, anchored in 2026. April 2027 uses the model's calendar-2026 CPI (2.3%); subsequent years use each saved path's calendar CPI. Guarantee uprating uses each path's statutory earnings and precision. This separates calendar CPI from the statutory September CPI used for the experimental retained component.

The committed [annual CSV](../data/diagnostics/pension_age_allowances.csv) gives every year 2026–27 through 2039–40 for every path, including guarantees, HB single/couple/lone-parent allowances, Savings Credit thresholds and alternative levels. The [crossing JSON](../data/diagnostics/pension_age_allowances.json) gives each path's first crossing and signed final gap. These contain parameters and macro paths only. A positive gap below means **guarantee minus current allowance/threshold**, £ per week. Lone-parent results equal single results.

| Path | First guarantee > HB single | First guarantee > HB couple | 2039–40 HB gap single/couple | 2039–40 Savings Credit threshold gap single/couple |
|---|---|---|---:|---:|
| central | 2036–37 | 2034–35 | £19.79 / £39.77 | £81.96 / £109.29 |
| obr_wedge | 2036–37 | 2034–35 | £19.79 / £39.77 | £81.96 / £109.29 |
| random | 2036–37 | 2034–35 | £46.75 / £81.41 | £112.10 / £154.49 |
| monthly_p50 | 2038–39 | 2035–36 | £2.89 / £14.06 | £65.59 / £84.18 |
| monthly_p90 | 2036–37 | 2036–37 | £33.41 / £60.38 | £94.47 / £128.66 |

| Saved paired group (161 paths each) | HB single paths with crossing; first-year range | HB couple paths with crossing; first-year range | 2039–40 HB gap range single/couple | 2039–40 threshold gap range single/couple |
|---|---|---|---|---|
| paired_baseline | 135/161; 2028–29 to 2039–40 | 150/161; 2028–29 to 2039–40 | £-40.43 to £88.29 / £-51.38 to £143.95 | £26.71 to £148.09 / £23.71 to £210.82 |
| earnings_minus_0_5pp | 124/161; 2028–29 to 2039–40 | 137/161; 2028–29 to 2039–40 | £-52.65 to £72.89 / £-70.04 to £120.45 | £14.49 to £132.69 / £5.05 to £187.32 |
| earnings_plus_0_5pp | 153/161; 2028–29 to 2039–40 | 157/161; 2028–29 to 2039–40 | £-27.77 to £104.22 / £-32.06 to £168.27 | £39.37 to £164.02 / £43.03 to £235.14 |

For **every** path, the first guarantee > Savings Credit threshold year is **2026–27**. Conversely, the couple threshold temporarily exceeds the guarantee on **one baseline path and two earnings-minus paths**, first in **2036–37**; no single threshold does so. These are parameter-path counts, not survey counts. All final-year guarantee-minus-threshold gaps are positive.


On the central/OBR-wedge path in 2039–40, guarantees are **£351.82/£536.97**, current HB allowances **£332.02/£497.19**, and Savings Credit thresholds **£269.86/£427.68**, single/couple respectively.

The Savings Credit guarantee is already above its threshold in 2026–27 on every path, as intended; that is not an inconsistency. The reverse crossing (threshold above guarantee) can eliminate the positive maximum. See the per-path JSON and annual CSV for temporary crossings, including reversals before 2039–40.

The saved paths are deterministic scenarios and selected paired draws, not a probability interval. Their path counts do not measure population prevalence. The historical decade replay remains a dated historical exercise and is not extrapolated to 2039–40.

## Options for Max and Vahid

1. **Retain installed-model projections:** no production change. The crossing tables quantify the departure from DWP's annual component convention.
2. **HB component convention:** set HB to the applied path guarantee plus its enacted 2026 retained component, growing the latter by non-negative rounded statutory September CPI. This keeps the experimental allowance at least the guarantee. It changes HB single/couple by **+£43.33/+£66.05 a week in central 2039–40**, to **£375.35/£563.25**. A narrower guarantee floor would instead add **£19.79/£39.77**, without preserving the retained uplift.
3. **Separately choose a Savings Credit maximum convention:** holding the penny-rounded 2026 maximum on non-negative statutory CPI and solving `threshold = guarantee − maximum / 0.6` raises central 2039–40 thresholds by **£42.82/£65.49**, to **£312.68/£493.16**. This is a separate method decision, not a legal consequence of the guarantee override. The annual CSV contains each option's size on every path.

These sensitivity definitions state their rounding choices; they are not a claim to reproduce every generated index or future parameter-processing change in #2092.

## Central-path HB fiscal result

The main session completed the documented command in an admitted foreground shell on **20 October 2026**, following the lane's earlier `nice unknown` refusal. The private receipt `.cache/hb-link-comparison.json` records `status: completed`, `disclosure_status: available`, both host admissions admitted, and the certified **policyengine 6.2.6 / UK 2.125.1 / Enhanced FRS 1.58.0** bundle. The original [lane refusal receipt](../data/diagnostics/hb_link_run_admission.json) remains a historical record.

This is **the central path only, UK**, with **one complete triple-lock/Burnham pair under the current method and one complete pair under the HB component convention**. Every pair calculates the full horizon. The current method reproduces the published 2039–40 headline at its reported precision: gross **£0.865bn**, net **£0.624bn**. Its exact net differs slightly from the old published file; the table reports the fresh, same-engine comparison rather than subtracting across files.

All table values are **£bn**; differences are **linked minus current**. Gross saving is unchanged in every year. Net saving increases by **£0.0014bn in 2039–40**, with a maximum increase of **£0.0016bn in 2037–38**. These are full-run aggregate results, with no scaling or interpolation, and do not establish an effect on other paths or an expected saving.

| Fiscal year | Gross current | Gross linked | Gross difference | Net current | Net linked | Net difference |
|---|---:|---:|---:|---:|---:|---:|
| 2032–33 | 0.298291 | 0.298291 | +0.0000000 | 0.203742 | 0.204497 | +0.0007558 |
| 2033–34 | 0.627692 | 0.627692 | +0.0000000 | 0.447026 | 0.447443 | +0.0004177 |
| 2034–35 | 0.664876 | 0.664876 | +0.0000000 | 0.463548 | 0.464228 | +0.0006801 |
| 2035–36 | 0.704230 | 0.704230 | +0.0000000 | 0.498092 | 0.498708 | +0.0006161 |
| 2036–37 | 0.742234 | 0.742234 | +0.0000000 | 0.524369 | 0.525626 | +0.0012575 |
| 2037–38 | 0.781562 | 0.781562 | +0.0000000 | 0.565139 | 0.566730 | +0.0015912 |
| 2038–39 | 0.823118 | 0.823118 | +0.0000000 | 0.597110 | 0.597912 | +0.0008016 |
| 2039–40 | 0.864839 | 0.864839 | +0.0000000 | 0.624016 | 0.625406 | +0.0013908 |

Completed HB command (the default remains `hb`):

```sh
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh hb-link-central \
  .venv/bin/python scripts/compare_hb_link.py --execute \
  --output .cache/hb-link-comparison.json
```

The full receipt stays private in `.cache`. The committed [aggregate-only copy](../data/diagnostics/hb_link_central.json) contains only UK central-path gross/net totals and differences plus version labels. Before copying, its status, certification, admissions, available disclosure decision, exact UK aggregate schema, finite amounts and difference identities were checked. No records, identifiers, weights or counts were copied.

The experimental runner applies the HB override after parameter processing and checks the applied levels and guarantee floor, population/cohort/weight alignment, fiscal identities, aggregate support and recoverable offsets. This is a sensitivity within this certified engine. Production behaviour and Savings Credit thresholds remain unchanged.

## Central-path Savings Credit option 3 fiscal result

The main session completed this comparison in an admitted foreground shell at about 08:50Z on 20 October 2026. This is **the UK central path only, one full current-method pair and one full SC-convention pair**, each triple lock against Burnham. Both host admissions passed; no cached results were reused. The certified versions are PolicyEngine 6.2.6, policyengine-uk 2.125.1 and Enhanced FRS 1.58.0. Disclosure status is **available**. Gross saving is unchanged in every year.

Amounts are £bn; differences are linked minus current. The committed JSON preserves the full precision of the UK aggregates.

| Year | Gross current | Gross linked | Difference | Net current | Net linked | Difference |
|---|---:|---:|---:|---:|---:|---:|
| 2032–33 | 0.298291 | 0.298291 | +0.0000000 | 0.203742 | 0.203065 | -0.0006764 |
| 2033–34 | 0.627692 | 0.627692 | +0.0000000 | 0.447026 | 0.445065 | -0.0019603 |
| 2034–35 | 0.664876 | 0.664876 | +0.0000000 | 0.463548 | 0.463322 | -0.0002264 |
| 2035–36 | 0.704230 | 0.704230 | +0.0000000 | 0.498092 | 0.495607 | -0.0024854 |
| 2036–37 | 0.742234 | 0.742234 | +0.0000000 | 0.524369 | 0.521651 | -0.0027178 |
| 2037–38 | 0.781562 | 0.781562 | +0.0000000 | 0.565139 | 0.561440 | -0.0036991 |
| 2038–39 | 0.823118 | 0.823118 | +0.0000000 | 0.597110 | 0.590095 | -0.0070155 |
| 2039–40 | 0.864839 | 0.864839 | +0.0000000 | 0.624016 | 0.616999 | -0.0070169 |

The full receipt stays private in `.cache/sc-threshold-comparison.json`. The [aggregate-only copy](../data/diagnostics/sc_threshold_central.json) passed the same disclosure and strict UK aggregate-schema checks as the HB result, plus certification, admissions, version, finite-value, difference-identity and runner-hash checks. Its current-method totals match the fresh HB comparison baseline. No records, identifiers, weights or counts were copied.

`--method sc-threshold` selects the separate Savings Credit maximum convention. The builder takes the enacted 2026 single/couple guarantee and threshold, computes **0.6 × (guarantee − threshold)** with decimal arithmetic, and rounds the base maximum to pennies, halves up: **£17.96/£20.10**. It then grows that maximum by each prior year's **non-negative statutory September CPI, rounded at the path's precision**, without further cash rounding, and sets **threshold = applied path guarantee − projected maximum / 0.6** for every horizon year and both relationship types.

This is the third convention alongside current projections and the HB component option. **HB allowances remain on their current projections in the SC variant**; the HB component override is not combined with it. The runner checks the applied threshold against the formula in every year before calculating either pension policy's totals, including when future threshold projections already exist. Its normal fiscal, population/alignment, certification, host-admission and disclosure checks remain in place. Production engine/config behaviour is unchanged.

Completed SC command:

```sh
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh sc-threshold-central \
  .venv/bin/python scripts/compare_hb_link.py --execute --method sc-threshold \
  --output .cache/sc-threshold-comparison.json
```

The comparison covers every year from 2027–28 to 2039–40 with full runs, without scaling or interpolation. The SC and HB sensitivities are separate; their effects have not been estimated jointly.

## Proposed default for Max and Vahid

Both conventions change central net saving by about 1% or less in 2039–40: HB **+£1.4m** (about 0.2%), Savings Credit **−£7.0m** (about 1.1%, from £0.624bn to £0.617bn). Neither changes gross saving. These are central-path results only. **Proposed default:** keep the installed projections for the binding rebuild and publish both conventions as documented sensitivities. The methodology choice remains Max and Vahid's; this proposal is not a decision.

## Validation and delivery

Draft PR: [#33](https://github.com/PolicyEngine/uk-triple-lock/pull/33), branch/head: [`hb-allowance-vs-guarantee2`](https://github.com/PolicyEngine/uk-triple-lock/tree/hb-allowance-vs-guarantee2). No merge, main/master push or PR comments. C2 pre-registration and uncertainty thresholds are unchanged.

Original audit validation (before this continuation): **100 focused checks passed**: 65 existing engine/model tests, 7 parameter tests and 28 sensitivity tests. Parameter checks include independent model preprocessing on the central, negative-CPI and temporary Savings Credit excursion paths, plus committed-input and artifact reproduction checks. **Full `pytest -n 4`: 1,762 passed, 2 skipped, 2 failed**, 20 warnings, 1,087.22 seconds, exit 1. The only failures are the documented stale-results assertions `tests/test_results.py::test_not_stale` and `tests/test_scenarios.py::test_not_stale`; no rebuild was attempted. [Validation receipt](../data/diagnostics/hb_allowance_validation.json). Independent Subfleet review **APPROVE**: job `20261020-030104-review`, reviewed implementation head `9ea6c1fe2005739b5806f031a3f635667fe20145` including the subsequent prose edits. The reviewer independently passed all 35 focused tests and verified all path/input bindings. [Full review](reviews/pension-age-hb-review.md) records one nonblocking floating-point robustness observation about inferring fiscal offset support; that original review preceded the completed foreground HB comparison. The full suite completed after review with only the two permitted stale-results failures above.

Forwardable note: “The protected pension-age HB allowances and Savings Credit thresholds are separately prescribed cash rates; their projection conventions remain a methodology choice. The completed UK central-path full comparisons change 2039–40 net saving by +£1.4m for the HB component convention and −£7.0m for the Savings Credit maximum convention (about 0.2% and 1.1%); neither changes gross. Proposed default: retain the installed projections for the binding rebuild and publish both as documented sensitivities. The choice remains yours; no decision or production behaviour change is made here. These results do not estimate other paths or the two conventions combined.”

## Continuation validation

Focused validation: **50 passed** in 342.61 seconds (HB regression checks, SC properties/readback/routing, public aggregate schema and parameter reproduction). Independent delta review **APPROVE**, job `20261020-040134-review`, reviewed head `2fc35f519a028359b9ac7822050628e0bf893165`, with 37 synthetic/aggregate tests independently passing and no findings: [review artifact](reviews/pr33-continuation-review.md). **Full `pytest -n 4`: 1,777 passed, 2 skipped, 2 failed**, 20 warnings, 2,541.29 seconds (42 minutes 21 seconds), exit 1. Only `tests/test_results.py::test_not_stale` and `tests/test_scenarios.py::test_not_stale` fail, both documented stale-results assertions. No rebuild was attempted. [Continuation validation receipt](../data/diagnostics/hb_sc_continuation_validation.json). The completed HB receipt matches the original committed runner's hash; that validation preceded the main session’s completed SC run recorded above.
