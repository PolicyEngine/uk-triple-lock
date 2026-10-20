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

Current policyengine-uk main is pinned in the parameter snapshot, including original YAML and hashes. Its three protected `aged.yaml` files carry £256.00 single/lone-parent and £383.35 couple from April 2026 and `uprating: gov.benefit_uprating_cpi`. The certified installed UK 2.125.1 has the same 2026 bases and whole-CPI projections, although some historical rates and labels differ. `hb_allowance_parameter_snapshot.json` preserves both sources rather than treating the installed bundle as current main.

Read [upstream PR #2092](https://github.com/PolicyEngine/policyengine-uk/pull/2092)'s diff at `3c8b9bf7706b4c2fa66b23115fb14c4c45deccdb` and Vahid's 13 October review. Its new builders run in `_add_generated_parameters`, called during `process_parameter_tree`. HB is built from guarantee plus retained uplift, and the Savings Credit threshold from projected guarantee and CPI-grown maximum. The indices are built during processing; a later guarantee reform does not re-derive them. Its HB builder rejects a negative 2026 retained component. Vahid reports six CI failures from base-year guarantee reforms to £300/£459; this audit verifies the guard and ordering in source, **not** a reproduction of those upstream CI cases. Landing #2092 would change the model's default projection, so re-run this diagnostic and review the methodology on the recertified bundle rather than assuming current CPI results still apply.

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


The Savings Credit guarantee is already above its threshold in 2026–27 on every path, as intended; that is not an inconsistency. The reverse crossing (threshold above guarantee) can eliminate the positive maximum. See the per-path JSON and annual CSV for temporary crossings, including reversals before 2039–40.

The saved paths are deterministic scenarios and selected paired draws, not a probability interval. Their path counts do not measure population prevalence. The historical decade replay remains a dated historical exercise and is not extrapolated to 2039–40.

## Options for Max and Vahid

1. **Retain installed-model projections:** no production change. The crossing tables quantify the departure from DWP's annual component convention.
2. **HB component convention:** set HB to the applied path guarantee plus its enacted 2026 retained component, growing the latter by non-negative rounded statutory September CPI. This keeps the experimental allowance at least the guarantee. It changes HB single/couple by **+£43.33/+£66.05 a week in central 2039–40**, to **£375.35/£563.25**. A narrower guarantee floor would instead add **£19.79/£39.77**, without preserving the retained uplift.
3. **Separately choose a Savings Credit maximum convention:** holding the penny-rounded 2026 maximum on non-negative statutory CPI and solving `threshold = guarantee − maximum / 0.6` raises central 2039–40 thresholds by **£42.82/£65.49**, to **£312.68/£493.16**. This is a separate method decision, not a legal consequence of the guarantee override. The annual CSV contains each option's size on every path.

These sensitivity definitions state their rounding choices; they are not a claim to reproduce every generated index or future parameter-processing change in #2092.

## Fiscal run and exact rebuild command

The required wrapper was actually invoked with `HEAVY_CALLER=uk-triple-lock`. It exited **75** before starting the comparison:

> heavy_run: refusing to run at nice unknown; the heavy-lock holder must run at nice 0. Run it in the foreground of an un-niced shell (zsh '&' adds +5 via BG_NICE).

This is a wrapper admission refusal, not evidence of memory/load saturation or a continued Route A hold. No model run, fiscal estimate, scaling or interpolation was performed. The [admission receipt](../data/diagnostics/hb_link_run_admission.json) records the exact command and refusal. Per the task instruction, no retry or gate bypass was attempted.

Run from this workspace in an admitted foreground shell with the certified bundle and dataset credentials:

```sh
HEAVY_CALLER=uk-triple-lock ~/reviews/us-hub/scripts/heavy_run.sh hb-link-central \
  .venv/bin/python scripts/compare_hb_link.py --execute \
  --output .cache/hb-link-comparison.json
```

The committed experimental runner makes two complete central-path EFRS comparisons: triple lock against Burnham with existing allowances, then the same pair with the HB component convention. It leaves Savings Credit thresholds unchanged; checks the applied HB amounts and guarantee floor; preserves population, cohort and weights; checks host admission before model/data load and before the second pair; and releases only supported aggregate fiscal differences. Full fiscal execution remains **unverified** because admission refused it. Any eventual comparison is a sensitivity within the then-certified engine, rather than a causal comparison with the old published population/model file. Keep its private receipt under `.cache`; publish only disclosure-reviewed aggregates.

## Validation and delivery

Draft PR: [#33](https://github.com/PolicyEngine/uk-triple-lock/pull/33), branch/head: [`hb-allowance-vs-guarantee2`](https://github.com/PolicyEngine/uk-triple-lock/tree/hb-allowance-vs-guarantee2). No merge, main/master push or PR comments. C2 pre-registration and uncertainty thresholds are unchanged.

Focused sensitivity checks: **16 passed**. Parameter checks include independent model preprocessing on the central, negative-CPI and temporary Savings Credit excursion paths, plus committed-input and artifact reproduction checks. Final focused parameter verification and the full `pytest -n 4` run are in progress. Independent review is pending; its final verdict will be recorded here.

Forwardable note: “DWP's protected pension-age HB allowance follows Guarantee Credit plus retained Savings Credit by annual policy convention, implemented as cash rates. With our guarantee override and whole-CPI HB projection, the central couple allowance falls below the guarantee in 2034–35 and the single allowance in 2036–37; gaps reach £39.77/£19.79 a week in 2039–40. A component projection would add £66.05/£43.33 to the current allowances. Savings Credit thresholds are separately prescribed too. Please choose the projection method before recertification; production behaviour is unchanged. The required heavy wrapper refused the fiscal sensitivity, so no net-saving effect is claimed.”
