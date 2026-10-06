# Part E country table

**Pilot on an uncertified data/model pair; not for quoting.** These are saved full PolicyEngine UK aggregates for the default `both` treatment (age/sex reweighting and re-typing, kept flat-rate amounts). The [complete public receipt](../../data/pilot/model_v2_e_coverage.json) contains all six treatments and unrounded values. Fiscal-year labels use the receipt's saved start year.

Recipients are **millions of people** (`recipients_m`); all spending and gaps are **£bn** (`*_bn`). Display values are rounded to four decimal places. Combined spending is the saved `state_pension_bn`, including basic, new and additional State Pension: the installed policyengine-uk 2.120.0 formula adds all three components, consistent with [the engine's component list and coverage metrics](../../src/triple_lock/engine.py). Additional pension explains the gap between combined spending and the basic/new columns.

| Year | Country | Recipients (m) | Basic (£bn) | New (£bn) | Combined (£bn) | DWP combined (£bn) | Saved gap, model − DWP (£bn) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024–25 | England | 9.5535 | 54.8811 | 31.9647 | 100.1428 | 112.5060 | -12.3632 |
| 2024–25 | Scotland | 0.8738 | 4.7745 | 3.3885 | 9.2389 | 11.6484 | -2.4096 |
| 2024–25 | Wales | 0.6437 | 3.6616 | 2.2599 | 6.7156 | 7.0779 | -0.3623 |
| 2025–26 | England | 9.6223 | 52.9907 | 38.7514 | 104.6906 | unavailable | unavailable |
| 2025–26 | Scotland | 0.8801 | 4.6839 | 3.9363 | 9.6620 | unavailable | unavailable |
| 2025–26 | Wales | 0.6484 | 3.5393 | 2.7301 | 7.0233 | unavailable | unavailable |
| 2026–27 | England | 9.6774 | 50.2747 | 47.6364 | 110.3489 | unavailable | unavailable |
| 2026–27 | Scotland | 0.8800 | 4.7174 | 4.3416 | 10.1072 | unavailable | unavailable |
| 2026–27 | Wales | 0.6482 | 3.5374 | 3.0467 | 7.3268 | unavailable | unavailable |
| 2027–28 | England | 9.6113 | 48.7293 | 52.7197 | 113.5702 | unavailable | unavailable |
| 2027–28 | Scotland | 0.8818 | 4.7258 | 4.7551 | 10.5327 | unavailable | unavailable |
| 2027–28 | Wales | 0.6498 | 3.5743 | 3.3042 | 7.6318 | unavailable | unavailable |
| 2028–29 | England | 9.6915 | 46.5656 | 58.8750 | 117.3511 | unavailable | unavailable |
| 2028–29 | Scotland | 0.8918 | 4.6524 | 5.2208 | 10.9230 | unavailable | unavailable |
| 2028–29 | Wales | 0.6506 | 3.3845 | 3.7069 | 7.8192 | unavailable | unavailable |
| 2029–30 | England | 9.9111 | 44.2798 | 67.1576 | 123.0021 | unavailable | unavailable |
| 2029–30 | Scotland | 0.9103 | 4.4400 | 5.9315 | 11.4228 | unavailable | unavailable |
| 2029–30 | Wales | 0.6634 | 3.1021 | 4.3910 | 8.1734 | unavailable | unavailable |
| 2030–31 | England | 10.1395 | 41.6985 | 76.0405 | 128.9921 | unavailable | unavailable |
| 2030–31 | Scotland | 0.9281 | 4.2304 | 6.6808 | 11.9341 | unavailable | unavailable |
| 2030–31 | Wales | 0.6778 | 2.7642 | 5.1916 | 8.5624 | unavailable | unavailable |
| 2034–35 | England | 11.0296 | 32.5558 | 113.5077 | 156.7793 | unavailable | unavailable |
| 2034–35 | Scotland | 1.0072 | 4.3808 | 8.9867 | 14.4423 | unavailable | unavailable |
| 2034–35 | Wales | 0.7477 | 2.8093 | 7.1269 | 10.5502 | unavailable | unavailable |
| 2039–40 | England | 11.8189 | 19.7753 | 168.9109 | 198.6570 | unavailable | unavailable |
| 2039–40 | Scotland | 1.0895 | 4.0743 | 13.4295 | 18.5172 | unavailable | unavailable |
| 2039–40 | Wales | 0.8378 | 3.1058 | 10.2837 | 13.9783 | unavailable | unavailable |

The verified [DWP regional workbook](https://assets.publishing.service.gov.uk/media/6940017ac72b0f8ccf33d78f/benefit-expenditure-by-country-and-region-2024-25.ods) supplies combined **2024–25** State Pension spending for these three countries. Its source records residents of each country and leaves overseas/unknown expenditure separate. Country recipients, basic/new spending splits and every forecast-year comparator remain **unavailable**. The spring 2026 workbook has no country forecast split. The saved receipt has a gap field (`difference`) and no ratio field; no ratio is reconstructed. María's substantive geographic coverage gate remains unresolved.

**Disclosure:** no linked country family is withheld. All 162 actual-change support receipts (six treatments × nine years × three countries) are available, with zero or at least ten contributors; all 648 country model comparison rows and 108 GB rows are available. The aggregate privacy/redaction, coverage recipe and replacement checks passed: **59 tests**. No survey records are included.

**Calculation provenance:**

- Completed coverage proof commit: **`4a57c6c`**.
- Actual calculation head: `5d8b53c632fa4d8e69c2624738afd8cf823a9a52`; source export: `.cache/pilot-e-5d8b53c`.
- Source SHA-256: `6afc1a733e94f679eed69b2d7c955fc985420e5c8b703aaa40191ccc27099dbc`; macro-specification SHA-256: `9b940b203a4e6466e5972888c58b2bbefe99c92ad96d2f6b08a2209c63b4af36`.
- Dataset: `enhanced_frs_2024_25@1.56.16`, built with **policyengine-uk 2.89.2**; dataset SHA-256: `e433e532b17bd8ce76030156285816e33d44e93edabd2204adbef71d19a68712`.
- Packages: policyengine-uk **2.120.0**, policyengine-core **3.32.16**; the complete package versions and source-file hashes are in the JSON.
- Public receipt SHA-256: `89ee5300652903fb40eecfc2c9d65a68614488b3ed2994a07972eca192dd5dbc`; six full coverage jobs, one Enhanced FRS worker, minimum cell **10**.
- Published regional workbook SHA-256: `36fb3ff05310880ea0a8d847ed783ec2d6db8d32e13d189ef6dac630e604bf03`; verified country-benchmark input SHA-256: `97c30a06854388eee786db2caff6bc31c8a042632dd10378ce689009e76cdef4`.

Max's d778 ruling requires the later rebuild to use a certified bundle after the uk-data batch; this pilot remains uncertified. d833's batch go remains pending.
