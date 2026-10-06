# C2 dry run — 6 October 2026

Pre-registration: `65343e2ee43a359f056ce5a027739509d32ab49f`; arithmetic correction: `a99ac2e`.

**Dry run only. Binding C2 remains pending after 28 October. No PolicyEngine jobs, no survey data, no expected value authorized; all forms have fiscal_eligible=false.**

Command: `.venv313/bin/python -u -m triple_lock.ts_uncertainty --screen c2 --output out/uncertainty-c2-dry-run`. 5,000 draws at each of 12 origins; A uses 6 chronological origins. Diagnostic future handoffs have 50,000 draws.

**Required reproduction PASS:** primary A suspended terminal 4/6, annual 80.0% on 20 cells, with 4 excluded. Published sensitivity terminal 1/6.

All 340 mean comparisons reproduce retained C1 within 1e-12 after the specified suspended annual gap exclusions/pooling (maximum roundoff 4.44e-16). Every past-years record is identical. Future baseline/paired draw hashes are identical to the first run.

The [first dry run](F-first-dry-run.md) revealed inherited fiscal rounding in the shared terminal helper. Four explicit decimals=None calls restore the already-committed unrounded candidate/past convention. No threshold, treatment, future draw or fiscal spec changed; first score artifacts remain in the record.

## Coverage and bias

Each suspended result is immediately followed by published sensitivity. Bias means forecast minus realised. Full per-origin rows and SEs: [scores.json](uncertainty-c2-dry-run/scores.json).

| Test / treatment | Form | Annual cells | Excluded | Annual coverage | Terminal hits | Gap bias (pp) | Switch bias | Floor bias | Terminal bias (pp) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A / suspended | VAR(1) bootstrap (primary) | 20 | 4 | 80.0% | 4/6 | 1.359 | -0.166 | 0.241 | -0.745 |
| A / published | VAR(1) bootstrap (primary) | 24 | 0 | 66.7% | 1/6 | 0.471 | -0.898 | 0.180 | -2.311 |
| A / suspended | VAR(2) bootstrap | 20 | 4 | 65.0% | 4/6 | 1.358 | -0.206 | 0.216 | -0.867 |
| A / published | VAR(2) bootstrap | 24 | 0 | 54.2% | 1/6 | 0.471 | -0.955 | 0.149 | -2.480 |
| A / suspended | Annual bootstrap + gap blocks | 20 | 4 | 80.0% | 4/6 | 1.364 | -0.367 | 0.244 | -0.926 |
| A / published | Annual bootstrap + gap blocks | 24 | 0 | 66.7% | 1/6 | 0.474 | -1.179 | 0.198 | -2.572 |
| A / suspended | VAR(1) Student-t | 20 | 4 | 60.0% | 4/6 | 1.356 | -0.210 | 0.221 | -0.887 |
| A / published | VAR(1) Student-t | 24 | 0 | 50.0% | 1/6 | 0.469 | -0.963 | 0.155 | -2.511 |
| A / suspended | VAR(1) Gaussian | 20 | 4 | 80.0% | 4/6 | 1.357 | -0.141 | 0.249 | -0.709 |
| A / published | VAR(1) Gaussian | 24 | 0 | 66.7% | 1/6 | 0.470 | -0.865 | 0.190 | -2.260 |
| B / suspended | VAR(1) bootstrap (primary) | 44 | 4 | 88.6% | 10/12 | 1.348 | -0.189 | 0.033 | 0.165 |
| B / published | VAR(1) bootstrap (primary) | 48 | 0 | 81.2% | 7/12 | 0.905 | -0.555 | 0.003 | -0.618 |
| B / suspended | VAR(2) bootstrap | 44 | 4 | 72.7% | 10/12 | 1.346 | -0.261 | 0.002 | -0.003 |
| B / published | VAR(2) bootstrap | 48 | 0 | 66.7% | 7/12 | 0.904 | -0.635 | -0.032 | -0.810 |
| B / suspended | Annual bootstrap + gap blocks | 44 | 4 | 84.1% | 10/12 | 1.358 | -0.407 | 0.039 | -0.086 |
| B / published | Annual bootstrap + gap blocks | 48 | 0 | 77.1% | 7/12 | 0.913 | -0.813 | 0.016 | -0.909 |
| B / suspended | VAR(1) Student-t | 44 | 4 | 70.5% | 10/12 | 1.347 | -0.256 | 0.008 | -0.007 |
| B / published | VAR(1) Student-t | 48 | 0 | 64.6% | 7/12 | 0.904 | -0.632 | -0.025 | -0.819 |
| B / suspended | VAR(1) Gaussian | 44 | 4 | 88.6% | 10/12 | 1.347 | -0.166 | 0.041 | 0.199 |
| B / published | VAR(1) Gaussian | 48 | 0 | 81.2% | 7/12 | 0.904 | -0.528 | 0.011 | -0.576 |

## Proper scores

Mean ± one overlap-adjusted Newey–West SE (lag 3), all lower is better. Units/components retain C1 definitions.

| Test / treatment | Form | Gap CRPS | Switch CRPS | Floor CRPS | Energy | Variogram |
|---|---|---:|---:|---:|---:|---:|
| A / suspended | VAR(1) bootstrap (primary) | 1.723 ± 0.192 | 0.234 ± 0.039 | 0.194 ± 0.047 | 7.176 ± 1.479 | 18.506 ± 4.204 |
| A / published | VAR(1) bootstrap (primary) | 1.895 ± 0.185 | 0.664 ± 0.117 | 0.150 ± 0.042 | 7.870 ± 1.422 | 20.484 ± 3.693 |
| A / suspended | VAR(2) bootstrap | 1.749 ± 0.199 | 0.261 ± 0.044 | 0.186 ± 0.040 | 7.316 ± 1.515 | 19.356 ± 4.508 |
| A / published | VAR(2) bootstrap | 1.939 ± 0.195 | 0.706 ± 0.117 | 0.140 ± 0.036 | 8.054 ± 1.462 | 21.978 ± 4.001 |
| A / suspended | Annual bootstrap + gap blocks | 1.729 ± 0.182 | 0.299 ± 0.072 | 0.181 ± 0.040 | 6.899 ± 1.361 | 16.827 ± 3.562 |
| A / published | Annual bootstrap + gap blocks | 1.890 ± 0.176 | 0.869 ± 0.157 | 0.150 ± 0.034 | 7.586 ± 1.315 | 18.888 ± 3.224 |
| A / suspended | VAR(1) Student-t | 1.752 ± 0.203 | 0.263 ± 0.048 | 0.190 ± 0.042 | 7.356 ± 1.523 | 19.921 ± 4.652 |
| A / published | VAR(1) Student-t | 1.944 ± 0.197 | 0.717 ± 0.120 | 0.145 ± 0.037 | 8.101 ± 1.463 | 22.582 ± 4.125 |
| A / suspended | VAR(1) Gaussian | 1.717 ± 0.189 | 0.227 ± 0.039 | 0.199 ± 0.049 | 7.155 ± 1.474 | 18.377 ± 4.147 |
| A / published | VAR(1) Gaussian | 1.883 ± 0.181 | 0.642 ± 0.113 | 0.154 ± 0.045 | 7.850 ± 1.415 | 20.299 ± 3.650 |
| B / suspended | VAR(1) bootstrap (primary) | 1.420 ± 0.191 | 0.355 ± 0.071 | 0.170 ± 0.038 | 5.183 ± 1.363 | 14.660 ± 3.228 |
| B / published | VAR(1) bootstrap (primary) | 1.531 ± 0.239 | 0.569 ± 0.095 | 0.148 ± 0.034 | 5.529 ± 1.516 | 15.648 ± 3.539 |
| B / suspended | VAR(2) bootstrap | 1.430 ± 0.203 | 0.385 ± 0.076 | 0.176 ± 0.037 | 5.254 ± 1.408 | 14.155 ± 3.927 |
| B / published | VAR(2) bootstrap | 1.551 ± 0.255 | 0.608 ± 0.098 | 0.153 ± 0.037 | 5.623 ± 1.573 | 15.466 ± 4.430 |
| B / suspended | Annual bootstrap + gap blocks | 1.440 ± 0.186 | 0.441 ± 0.103 | 0.166 ± 0.032 | 5.060 ± 1.253 | 13.659 ± 2.682 |
| B / published | Annual bootstrap + gap blocks | 1.544 ± 0.230 | 0.726 ± 0.135 | 0.150 ± 0.029 | 5.404 ± 1.409 | 14.690 ± 3.072 |
| B / suspended | VAR(1) Student-t | 1.424 ± 0.205 | 0.386 ± 0.078 | 0.175 ± 0.037 | 5.262 ± 1.423 | 14.475 ± 4.096 |
| B / published | VAR(1) Student-t | 1.548 ± 0.259 | 0.613 ± 0.102 | 0.152 ± 0.035 | 5.635 ± 1.588 | 15.806 ± 4.601 |
| B / suspended | VAR(1) Gaussian | 1.417 ± 0.188 | 0.346 ± 0.070 | 0.171 ± 0.039 | 5.173 ± 1.356 | 14.647 ± 3.156 |
| B / published | VAR(1) Gaussian | 1.525 ± 0.234 | 0.554 ± 0.091 | 0.149 ± 0.035 | 5.521 ± 1.508 | 15.608 ± 3.456 |

## Past-years sensitivity and C2 outcome

| Form | Suspended percentile | Published percentile (sensitivity) | C2 dry-run verdict |
|---|---:|---:|---|
| VAR(1) bootstrap (primary) | 56.54 | 92.08 | Pass |
| VAR(2) bootstrap | 69.66 | 97.82 | Pass |
| Annual bootstrap + gap blocks | 52.44 | 88.96 | Fail: A/suspended: switch_crps ratio 1.279 exceeds 1.25 |
| VAR(1) Student-t | 72.76 | 98.18 | Pass |
| VAR(1) Gaussian | 55.44 | 92.18 | Pass |

Original primary retained; no alternative promotion or averaging. Annual form fails A/suspended switch CRPS ratio 1.279 > 1.25. Primary floor bias remains 0.241, close to its 0.25 limit. Suspended terminal misses at origins 2020–2021 remain; this pass is not calibrated predictive coverage.

All five forms failed the common C1 A/published coverage gate; extra candidate-specific failures remain. C2 changed the rule after those scores were seen because the target is statutory behaviour and Parliament suspended April 2022 earnings.

Binding requires committed September 2026 CPI, May–July 2026 AWE, dated Budget-day OBR means and every newly complete origin. Current handoff records missing requirements and run_kind=dry_run; ruling c refuses it. Arrays/strata stay local; portable JSON scores/handoff/designs/specs are committed.
