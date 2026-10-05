# Model v2 C1 uncertainty pilot

**No form passes the pre-registered adequacy screen. No full fiscal runs are authorized by this pilot.** The original monthly VAR(1) bootstrap also fails, so it cannot be presented as an adequately backtested predictive expectation. No replacement primary is selected; no fiscal scenario envelope can yet be quoted.

The rule was committed before scoring at `a8d2ac8`; its full definition is in [METHOD.md](METHOD.md#model-v2-uncertainty-pilot-pre-registered-rule-c1). Both April 2022 treatments must pass tests A and B, including 50–100% annual and terminal-gap coverage, a terminal coverage Wilson band containing 80%, fixed gap/switch/floor bias limits, proper scores no worse than 1.25 times the primary, and a 5th–95th percentile past-years check. The screen has not been relaxed after scoring.

Five forms were fitted only on pre-origin data, with 5,000 draws at each of the 12 complete OBR spring vintages (2010–2021); A is the existing chronological 2016–2021 subset (six origins). The monthly forms use the same smooth shift to the vintage’s OBR calendar means; the annual form uses an annual shift and de-meaned four-year statutory-gap blocks. These are latest revised inputs, and the inherited model design saw the full sample. For the legal treatment, the suspended earnings leg is set equal to CPI in both forecast draws and outturns.

## Proper scores

Each entry is mean ± one overlap-adjusted Newey–West SE (lag 3). Growth CRPS and energy use percentage points; switch CRPS uses counts; floor CRPS uses the fraction of years with earnings below 2.5%; the variogram uses all 28 pairs of the joint statutory four-year path. All are lower-is-better. These SEs are descriptive with so few overlapping origins; independent-origin SEs and all per-origin rows are retained in [scores.json](uncertainty/scores.json).

| Test / treatment | Form | Gap CRPS | Switch CRPS | Floor CRPS | Energy | Variogram |
|---|---|---:|---:|---:|---:|---:|
| A / published | VAR(1) bootstrap | 1.895 ± 0.185 | 0.664 ± 0.117 | 0.150 ± 0.042 | 7.870 ± 1.422 | 20.484 ± 3.693 |
| A / published | VAR(2) bootstrap | 1.939 ± 0.195 | 0.706 ± 0.117 | 0.140 ± 0.036 | 8.054 ± 1.462 | 21.978 ± 4.001 |
| A / published | Annual bootstrap + gap blocks | 1.890 ± 0.176 | 0.869 ± 0.157 | 0.150 ± 0.034 | 7.586 ± 1.315 | 18.888 ± 3.224 |
| A / published | VAR(1) Student-t | 1.944 ± 0.197 | 0.717 ± 0.120 | 0.145 ± 0.037 | 8.101 ± 1.463 | 22.582 ± 4.125 |
| A / published | VAR(1) Gaussian | 1.883 ± 0.181 | 0.642 ± 0.113 | 0.154 ± 0.045 | 7.850 ± 1.415 | 20.299 ± 3.650 |
| A / suspended | VAR(1) bootstrap | 1.436 ± 0.145 | 0.234 ± 0.039 | 0.194 ± 0.047 | 7.176 ± 1.479 | 18.506 ± 4.204 |
| A / suspended | VAR(2) bootstrap | 1.458 ± 0.150 | 0.261 ± 0.044 | 0.186 ± 0.040 | 7.316 ± 1.515 | 19.356 ± 4.508 |
| A / suspended | Annual bootstrap + gap blocks | 1.441 ± 0.136 | 0.299 ± 0.072 | 0.181 ± 0.040 | 6.899 ± 1.361 | 16.827 ± 3.562 |
| A / suspended | VAR(1) Student-t | 1.460 ± 0.154 | 0.263 ± 0.048 | 0.190 ± 0.042 | 7.356 ± 1.523 | 19.921 ± 4.652 |
| A / suspended | VAR(1) Gaussian | 1.431 ± 0.143 | 0.227 ± 0.039 | 0.199 ± 0.049 | 7.155 ± 1.474 | 18.377 ± 4.147 |
| B / published | VAR(1) bootstrap | 1.531 ± 0.239 | 0.569 ± 0.095 | 0.148 ± 0.034 | 5.529 ± 1.516 | 15.648 ± 3.539 |
| B / published | VAR(2) bootstrap | 1.551 ± 0.255 | 0.608 ± 0.098 | 0.153 ± 0.037 | 5.623 ± 1.573 | 15.466 ± 4.430 |
| B / published | Annual bootstrap + gap blocks | 1.544 ± 0.230 | 0.726 ± 0.135 | 0.150 ± 0.029 | 5.404 ± 1.409 | 14.690 ± 3.072 |
| B / published | VAR(1) Student-t | 1.548 ± 0.259 | 0.613 ± 0.102 | 0.152 ± 0.035 | 5.635 ± 1.588 | 15.806 ± 4.601 |
| B / published | VAR(1) Gaussian | 1.525 ± 0.234 | 0.554 ± 0.091 | 0.149 ± 0.035 | 5.521 ± 1.508 | 15.608 ± 3.456 |
| B / suspended | VAR(1) bootstrap | 1.301 ± 0.120 | 0.355 ± 0.071 | 0.170 ± 0.038 | 5.183 ± 1.363 | 14.660 ± 3.228 |
| B / suspended | VAR(2) bootstrap | 1.311 ± 0.131 | 0.385 ± 0.076 | 0.176 ± 0.037 | 5.254 ± 1.408 | 14.155 ± 3.927 |
| B / suspended | Annual bootstrap + gap blocks | 1.320 ± 0.115 | 0.441 ± 0.103 | 0.166 ± 0.032 | 5.060 ± 1.253 | 13.659 ± 2.682 |
| B / suspended | VAR(1) Student-t | 1.306 ± 0.132 | 0.386 ± 0.078 | 0.175 ± 0.037 | 5.262 ± 1.423 | 14.475 ± 4.096 |
| B / suspended | VAR(1) Gaussian | 1.299 ± 0.118 | 0.346 ± 0.070 | 0.171 ± 0.039 | 5.173 ± 1.356 | 14.647 ± 3.156 |

## Coverage and bias

Bias is **forecast minus realised**, so a positive terminal-gap bias overpredicts the rule-level saving. Coverage uses central 80% bands. Each annual-coverage entry averages the four per-year gap indicators within origins; terminal coverage is whole-origin hits. Bias entries again use one overlap-adjusted SE.

| Test / treatment | Form | Annual gap coverage | Terminal gap hits | Gap bias (pp) | Switch bias | Floor bias | Terminal gap bias (pp) |
|---|---|---:|---:|---:|---:|---:|---:|
| A / published | VAR(1) bootstrap | 66.7% | 1/6 | 0.471 ± 0.148 | -0.898 ± 0.254 | 0.180 ± 0.100 | -2.311 ± 0.580 |
| A / published | VAR(2) bootstrap | 54.2% | 1/6 | 0.471 ± 0.148 | -0.955 ± 0.254 | 0.149 ± 0.102 | -2.480 ± 0.579 |
| A / published | Annual bootstrap + gap blocks | 66.7% | 1/6 | 0.474 ± 0.149 | -1.179 ± 0.250 | 0.198 ± 0.099 | -2.572 ± 0.575 |
| A / published | VAR(1) Student-t | 50.0% | 1/6 | 0.469 ± 0.148 | -0.963 ± 0.261 | 0.155 ± 0.103 | -2.511 ± 0.573 |
| A / published | VAR(1) Gaussian | 66.7% | 1/6 | 0.470 ± 0.149 | -0.865 ± 0.254 | 0.190 ± 0.100 | -2.260 ± 0.576 |
| A / suspended | VAR(1) bootstrap | 83.3% | 4/6 | 1.133 ± 0.123 | -0.166 ± 0.152 | 0.241 ± 0.105 | -0.745 ± 0.817 |
| A / suspended | VAR(2) bootstrap | 70.8% | 4/6 | 1.132 ± 0.124 | -0.206 ± 0.155 | 0.216 ± 0.107 | -0.867 ± 0.819 |
| A / suspended | Annual bootstrap + gap blocks | 83.3% | 4/6 | 1.137 ± 0.124 | -0.367 ± 0.153 | 0.244 ± 0.103 | -0.926 ± 0.828 |
| A / suspended | VAR(1) Student-t | 66.7% | 4/6 | 1.130 ± 0.123 | -0.210 ± 0.162 | 0.221 ± 0.109 | -0.887 ± 0.812 |
| A / suspended | VAR(1) Gaussian | 83.3% | 4/6 | 1.131 ± 0.123 | -0.141 ± 0.153 | 0.249 ± 0.105 | -0.709 ± 0.812 |
| B / published | VAR(1) bootstrap | 81.2% | 7/12 | 0.905 ± 0.275 | -0.555 ± 0.321 | 0.003 ± 0.119 | -0.618 ± 0.979 |
| B / published | VAR(2) bootstrap | 66.7% | 7/12 | 0.904 ± 0.275 | -0.635 ± 0.316 | -0.032 ± 0.121 | -0.810 ± 0.969 |
| B / published | Annual bootstrap + gap blocks | 77.1% | 7/12 | 0.913 ± 0.277 | -0.813 ± 0.335 | 0.016 ± 0.121 | -0.909 ± 0.963 |
| B / published | VAR(1) Student-t | 64.6% | 7/12 | 0.904 ± 0.276 | -0.632 ± 0.323 | -0.025 ± 0.120 | -0.819 ± 0.979 |
| B / published | VAR(1) Gaussian | 81.2% | 7/12 | 0.904 ± 0.276 | -0.528 ± 0.319 | 0.011 ± 0.120 | -0.576 ± 0.974 |
| B / suspended | VAR(1) bootstrap | 89.6% | 10/12 | 1.235 ± 0.154 | -0.189 ± 0.245 | 0.033 ± 0.135 | 0.165 ± 0.615 |
| B / suspended | VAR(2) bootstrap | 75.0% | 10/12 | 1.234 ± 0.154 | -0.261 ± 0.250 | 0.002 ± 0.138 | -0.003 ± 0.596 |
| B / suspended | Annual bootstrap + gap blocks | 85.4% | 10/12 | 1.245 ± 0.155 | -0.407 ± 0.259 | 0.039 ± 0.134 | -0.086 ± 0.587 |
| B / suspended | VAR(1) Student-t | 72.9% | 10/12 | 1.234 ± 0.155 | -0.256 ± 0.254 | 0.008 ± 0.138 | -0.007 ± 0.601 |
| B / suspended | VAR(1) Gaussian | 89.6% | 10/12 | 1.235 ± 0.155 | -0.166 ± 0.244 | 0.041 ± 0.136 | 0.199 ± 0.612 |

All five forms cover only **1/6 chronological terminal gaps under published earnings**, failing both the minimum 50% coverage and the Wilson-band condition. That 1/6 Wilson band is approximately [3%, 56%]; it excludes 80% even before allowing for overlap. The corresponding coverage is **4/6 under the legal suspension**, but the screen requires both treatments. In the suspended scoring, the 2021 earnings-minus-CPI cell is deterministic zero in forecast and outturn; it automatically contributes coverage one and CRPS/bias zero. Four of A’s 24 cells have this property. For the primary, annual gap coverage is 83.3% including them and 80.0% among the other 20 cells. This is mechanical legal-regime scoring, not skill at forecasting the published earnings leg. All-origin coverage is 7/12 published and 10/12 suspended for every form.

## Past-years check and decisions

Uncalibrated fits stop at December 2010 and simulate determination years 2011–2025 (April 2012–2026 upratings). The realised terminal gap is 10.878% with published earnings and 6.297% with the suspended earnings leg. No realised future means enter this check.

| Form | Published percentile | Suspended percentile | Pass | Other failed checks |
|---|---:|---:|---|---|
| VAR(1) bootstrap | 92.08 | 56.54 | No | None beyond published chronological undercoverage |
| VAR(2) bootstrap | 97.82 | 69.66 | No | past/published: realised percentile 97.82 outside [5, 95] |
| Annual bootstrap + gap blocks | 88.96 | 52.44 | No | A/published: |switch_bias| 1.179 exceeds 1.0; A/published: switch_crps ratio 1.310 exceeds 1.25; A/suspended: switch_crps ratio 1.279 exceeds 1.25; B/published: switch_crps ratio 1.275 exceeds 1.25 |
| VAR(1) Student-t | 98.18 | 72.76 | No | past/published: realised percentile 98.18 outside [5, 95] |
| VAR(1) Gaussian | 92.18 | 55.44 | No | None beyond published chronological undercoverage |

VAR(2) and Student-t also put the published past-years gap beyond the 95th percentile. The annual bridge underpredicts lead switches by 1.179 per chronological published path and exceeds the 1.25 switch-score ratio limit in three test/treatment cells. Gaussian is close to the original primary on proper scores but fails the same coverage gate. Annual gap blocks begin at the first unobserved (origin) year, so the four scored target years cross two independent blocks; the bridge preserves dependence within each sampled block, not across that boundary. The annual/monthly alternatives therefore have no demonstrated case for fiscal promotion over the existing shock variants.

## Draws and paired mean-path handoff

Passing forms under the frozen C1 screen: **none**. This pilot authorized **zero** fiscal expected-value runs; no d955 ruling has been chosen. The implementation will make 50,000 draws and an independent own-gap Neyman design for every passing form if a subsequent pilot has any. Part E implements `expected_value.build(run=True)` as a consumer of the C1 160-slot handoff, with the exact 40-slot Microcosm subsample and step-3 fields. Execution requires Max's explicit recorded d955 ruling: (a) skips the expected value, (b) runs the original primary as model-conditional with its failure retained, (c) reruns a suspended-treatment-only screen and runs only a passing form. With no ruling it refuses and names d955. The old 200-slot `run=False` jobs remain diagnostic only. Paired mean-path scenarios are runnable independently of adequacy, with presentation pending d955 until it is recorded.

For audit and future paired runs, the original primary’s **diagnostic** 50,000 draws were generated with seed 20260929. Its 160-slot design includes two slots in the known-zero stratum, at least two in every other stratum, and an extra identical-rates check (161 unique specs). Allocation by stratum 0–10 is `2, 20, 11, 9, 8, 7, 8, 9, 11, 16, 59`. There are 160 unique sampled draw indices; the extra check is not part of the estimator. No spec has been run through PolicyEngine.

| Diagnostic path | Triple-lock premium, April 2034–2039 (pp) | First-phase SE (pp) | Runnable specs | Fiscal eligible |
|---|---:|---:|---:|---|
| Original primary | 0.546454 | 0.001935 | 161 | No |
| Calendar earnings −0.5pp from 2031 | 0.749442 | 0.002230 | 161 | No |
| Calendar earnings +0.5pp from 2031 | 0.389452 | 0.001647 | 161 | No |

The OBR comparator is **0.557167pp** (the committed unrounded fiscal determinants’ triple-lock minus earnings for input years 2033–2038), rather than the rounded 0.6pp note. These premiums are rule arithmetic, not fiscal estimates. The two mean paths reuse exactly the baseline innovations and sampled indices, including the partially observed first month. Smooth monthly drift can move statutory inputs near the 2031 boundary even when earlier calendar targets stay fixed.

All 50,000 draws in each of the three diagnostic sets passed the CPI/floor minimum, plan-level upper bound, April 2030 equality, earnings-anchor and finiteness checks at published-input precision. The calibration hits each calendar target to 1e-12. Draw hashes, versions, sample multiplicities and eligibility are in [handoff.json](uncertainty/handoff.json). The 50,000 primary draws replay exactly on the recorded macOS/arm64 runtime, with maximum error 0 (within 1e-12); all five candidates also reproduce in the test suite with scipy 1.18.1. Python, platform and NumPy/BLAS build details are recorded in the manifest; cross-platform equality has not been independently demonstrated. The arrays and per-draw strata are under `out/uncertainty/`; committed specs and design are:

- [Original-primary specs](uncertainty/monthly_var1_boot.specs.json) and [sample design](uncertainty/monthly_var1_boot.design.json).
- [Lower-earnings paired specs](uncertainty/earnings_minus_0_5pp.specs.json).
- [Higher-earnings paired specs](uncertainty/earnings_plus_0_5pp.specs.json).

## Estimation and dynamics

For every output and year, including 2034–35 and 2039–40, new estimator records carry `mean`, `se`, `plus_minus_95`, a 95% Monte Carlo band, `se_path_sampling`, `se_first_phase`, and the two variances. Path sampling is Σ W²s²/n; first phase is Σ W[s²+(m_h−m)²]/N_draws, including known-zero mass. Paired mean-path differences use within-stratum variant-minus-baseline outputs. Gross saving as a percentage of triple-lock flat-rate spending is also estimated from full-run outputs: this is the expected per-path ratio, not the ratio of two expected amounts. The current paired mean-path helper reports gross/net differences; the adapter now pairs every available fiscal-output field, including components and the share of flat-rate spending. No new-bundle fiscal estimate is available because no new fiscal runs were authorized or made. The next section publishes revised ± for the existing public full-run aggregates only.

Dynamics reweightings retain their effective-run counts and combined ± but receive `included_in_quoted_range=false` below 100 effective runs. They receive no extra run budget: past calibration evidence already disfavors those tilts, and a low-effective-run tail should not set the quoted envelope. Importance-reweighted first-phase errors are plug-in approximations conditional on fitted weights. Model/mean-path uncertainty is always a separate scenario envelope, with no averaging of forms.

Historical `data/results.json` and its dashboard copy are unchanged. They still contain path-sampling-only SEs and the old sensitivity range. This PR does not relabel those figures as newly validated, and historical-result recomputation tests distinguish the old and new variance definitions. The rebuild must consume the new fields and exclusion flag rather than carry the old range forward.

## Historical aggregate estimator update

This is a pure re-estimation of the already-published full-run aggregates on the old model/data bundle. No survey records or new model runs were used. Means and sample multiplicities are unchanged; only first-phase variance is added. These conditional Monte Carlo bands do not address the failed predictive adequacy screen or certify the old headline.

| Year | Output | Historical mean ±1.96 total SE (£bn) | Path-sampling SE (£bn) | First-phase SE (£bn) |
|---|---|---:|---:|---:|
| 2034–35 | gross | 2.591 ± 0.275 | 0.139750 | 0.009532 |
| 2034–35 | net | 1.683 ± 0.177 | 0.090028 | 0.006228 |
| 2039–40 | gross | 8.411 ± 0.091 | 0.042404 | 0.019330 |
| 2039–40 | net | 5.392 ± 0.074 | 0.035714 | 0.012432 |

All dynamics reweightings are shown individually below, with the same added first-phase term. “Eligible by effective-run rule” only addresses the count threshold; none is an adequate macro form under the C1 screen. No range is quoted. Window codes retain their historical definitions (including the older both-inputs-below-floor target).

| Historical reweighting | Effective runs | 2034–35 gross ± (£bn) | 2034–35 net ± (£bn) | 2039–40 gross ± (£bn) | 2039–40 net ± (£bn) | Eligible by effective-run rule |
|---|---:|---:|---:|---:|---:|---|
| shift_dynamics.2001_2025.covid_excluded | 60.7 | 2.066 ± 0.780 | 1.317 ± 0.484 | 6.698 ± 2.209 | 4.273 ± 1.427 | No: excluded |
| shift_dynamics_floor.2001_2025.covid_excluded | 43.8 | 3.273 ± 2.950 | 2.129 ± 1.982 | 10.659 ± 10.182 | 6.895 ± 6.677 | No: excluded |
| shift_dynamics.2001_2025.suspended | 69.6 | 2.045 ± 0.718 | 1.300 ± 0.439 | 6.611 ± 1.962 | 4.216 ± 1.264 | No: excluded |
| shift_dynamics_floor.2001_2025.suspended | 53.4 | 2.622 ± 1.639 | 1.684 ± 1.087 | 8.482 ± 5.379 | 5.456 ± 3.521 | No: excluded |
| shift_dynamics.2001_2025.published | 139.1 | 2.366 ± 0.400 | 1.534 ± 0.258 | 7.808 ± 0.961 | 4.981 ± 0.611 | Yes |
| shift_dynamics_floor.2001_2025.published | 93.1 | 2.589 ± 0.776 | 1.676 ± 0.513 | 8.501 ± 2.501 | 5.451 ± 1.636 | No: excluded |
| shift_dynamics.2010_2025.covid_excluded | 143.4 | 2.252 ± 0.378 | 1.450 ± 0.236 | 7.338 ± 0.859 | 4.686 ± 0.545 | Yes |
| shift_dynamics_floor.2010_2025.covid_excluded | 104.2 | 2.397 ± 0.597 | 1.538 ± 0.383 | 7.755 ± 1.719 | 4.965 ± 1.113 | Yes |
| shift_dynamics.2010_2025.suspended | 135.3 | 2.139 ± 0.394 | 1.368 ± 0.238 | 6.859 ± 0.890 | 4.381 ± 0.563 | Yes |
| shift_dynamics_floor.2010_2025.suspended | 123.3 | 2.185 ± 0.434 | 1.394 ± 0.265 | 6.990 ± 1.033 | 4.464 ± 0.650 | Yes |
| shift_dynamics.2010_2025.published | 179.0 | 2.736 ± 0.325 | 1.780 ± 0.207 | 8.911 ± 0.476 | 5.722 ± 0.314 | Yes |
| shift_dynamics_floor.2010_2025.published | 175.8 | 2.790 ± 0.356 | 1.811 ± 0.224 | 8.985 ± 0.570 | 5.769 ± 0.373 | Yes |

The full component/dataset/paired-difference update, source-file hash and separate SEs for every year are in [historical_estimator.json](uncertainty/historical_estimator.json). In particular, the historical high dynamics row has only 43.8 effective runs and is excluded; its 2039–40 gross band is much wider than the primary’s Monte Carlo band.

## Validation and rebuild requirements

Validation: the pure Python methods/expected-value/uncertainty suite passes (including historical re-estimation and the additional independent-review regression checks); it covers seed-averaged estimator unbiasedness within 3 SE, a 30,000-replicate synthetic first-phase check, exact calendar targets, shared shocks, pinned scipy reproducibility, candidate rule guarantees, allocation minimums, fixed-screen rejection, paired zero-stratum differences, and fiscal gating. Both saved tilt failures in #15 are explicit regression examples. Its fix skips Armijo backtracking only when the predicted Newton decrease is below 1e-12 × max(1, |objective|), rather than changing tolerances or iteration counts.

Reproduce using the pinned NumPy/scipy versions recorded in the manifest:

```sh
uv venv .venv
uv pip install --python .venv/bin/python numpy==2.5.3 scipy==1.18.1 pytest==8.4.2 hypothesis==6.168.3
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python -m triple_lock.ts_uncertainty --output out/uncertainty
# The historical diagnostic alone can be regenerated with --historical-only.
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 .venv/bin/python -m pytest tests/test_uncertainty.py tests/test_expected_value.py tests/test_methods.py -q
```

The full rebuild now has the C1 adapter, including explicit handling of the baseline-only extra zero check (allowed to save nonzero under a mean variant). It still needs the engine/data acceptance decisions, updated September CPI and Autumn Budget OBR means, a rerun of the screen on those inputs, and Max's recorded d955 ruling. An updated pilot with no passing forms must stop and explicitly redesign/pre-register the uncertainty process; it must not bypass or retrospectively weaken this screen. Future full runs need both-rule outputs for every selected index, independently runnable paired original-primary mean-path scenarios, separate variance components and scenario-envelope reporting. These results make no claim about the direction or size of fiscal effects on the upgraded population.

## Independent review

Subfleet job `20261004-223140-tl-c1-review` completed on the implementation and
artifacts. Its [original report](uncertainty/independent-review.md) confirmed the
no-passing-form decision and found no high-severity bug. The reviewer could not
run the suite or read the issue comments; those checks were performed in this
workspace, and the original report retains that limitation.

The medium findings were addressed by blocking the legacy execution route even
after a passing gate, disclosing the deterministic suspended gap cells, adding
artifact/doc consistency, suspension, pre-origin monthly fit and numeric spec
checks, and adding the historical artifact writer/CLI. The low findings were
addressed with shared seed constants, precise relative-gap units/quantiles,
finite-value checks, runtime provenance, narrower replay claims, corrected block
wording and solver comments, and an explicit variant extra-check flag. The
frozen scores and thresholds are unchanged. A C1 rebuild adapter and wider
paired output reporting remain explicitly deferred; no such full runs are
authorized by this pilot. The reviewer has not re-run this final revision.
