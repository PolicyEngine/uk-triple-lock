# Static ageing pilot: full-model aggregate results

Generated only from the publication-approved final aggregate JSON. Values are full PolicyEngine UK outputs or the paired estimates already supplied in that JSON; the renderer performs no fiscal scaling or counterfactual estimation. See [AGEING_PILOT.md](AGEING_PILOT.md) for design and pending part C gates.

Model **2.90.2**, policyengine **5.3.0**; dataset **enhanced_frs_2024_25**; calculation head **217395208083401744b4325f9a0375d7ffb55574**. Requested execution: **8 Enhanced FRS slots, 0 Microcosm workers**. The completed execution log records **0 initially cached of 205 planned jobs; 205 newly complete**. The paired paths all use Enhanced FRS.

## Four-way saving at 2034–35 and 2039–40

Great Britain, nominal £bn. The existing dashboard headline has UK coverage. Expected-value entries show mean ± path-sampling SE. Interaction is `both − reweight − types + frozen`. Common input effect is `frozen − legacy`; the factorial contrasts are conditional on the shared represented inputs. On the current 2.90.2 bundle, legacy and frozen already share the integer-age pension-eligibility gate and zero additional pension below that age. Their difference therefore measures represented ages and any head/claimant changes from resolving age ties. On a newer bundle, birthday inputs can also affect eligibility, so the general contrast does not isolate age representation alone.

| Sample | Year | Saving | legacy | frozen | reweight | types | both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Central | 2034–35 | gross | 0.529 | 0.529 | 0.614 | 0.570 | 0.658 | 0.003 | 0.000 |
| Central | 2034–35 | net | 0.355 | 0.354 | 0.410 | 0.383 | 0.442 | 0.002 | -0.001 |
| Central | 2039–40 | gross | 0.641 | 0.641 | 0.778 | 0.705 | 0.854 | 0.013 | 0.000 |
| Central | 2039–40 | net | 0.419 | 0.419 | 0.506 | 0.468 | 0.566 | 0.011 | 0.000 |
| Paired expected | 2034–35 | gross | 2.527 ± 0.275 | 2.527 ± 0.275 | 2.935 ± 0.319 | 2.723 ± 0.296 | 3.147 ± 0.342 | 0.015 ± 0.002 | 0.000 ± 0.000 |
| Paired expected | 2034–35 | net | 1.644 ± 0.180 | 1.640 ± 0.180 | 1.895 ± 0.208 | 1.787 ± 0.195 | 2.055 ± 0.224 | 0.012 ± 0.001 | -0.005 ± 0.001 |
| Paired expected | 2039–40 | gross | 8.042 ± 0.057 | 8.042 ± 0.057 | 9.765 ± 0.070 | 8.842 ± 0.063 | 10.723 ± 0.077 | 0.158 ± 0.001 | 0.000 ± 0.000 |
| Paired expected | 2039–40 | net | 5.130 ± 0.090 | 5.130 ± 0.089 | 6.165 ± 0.136 | 5.708 ± 0.091 | 6.858 ± 0.137 | 0.115 ± 0.002 | 0.000 ± 0.001 |

## Annual GB saving paths

### Central (£bn): gross

| Year | legacy | frozen | reweight | types | both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2027–28 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2028–29 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2029–30 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2030–31 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2031–32 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2032–33 | 0.247 | 0.247 | 0.278 | 0.264 | 0.296 | 0.000 | 0.000 |
| 2033–34 | 0.510 | 0.510 | 0.584 | 0.547 | 0.622 | 0.002 | 0.000 |
| 2034–35 | 0.529 | 0.529 | 0.614 | 0.570 | 0.658 | 0.003 | 0.000 |
| 2035–36 | 0.549 | 0.549 | 0.646 | 0.595 | 0.696 | 0.005 | 0.000 |
| 2036–37 | 0.571 | 0.571 | 0.678 | 0.621 | 0.735 | 0.006 | 0.000 |
| 2037–38 | 0.593 | 0.593 | 0.710 | 0.648 | 0.773 | 0.008 | 0.000 |
| 2038–39 | 0.616 | 0.616 | 0.744 | 0.677 | 0.815 | 0.011 | 0.000 |
| 2039–40 | 0.641 | 0.641 | 0.778 | 0.705 | 0.854 | 0.013 | 0.000 |

### Central (£bn): net

| Year | legacy | frozen | reweight | types | both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2027–28 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2028–29 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2029–30 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2030–31 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2031–32 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2032–33 | 0.165 | 0.165 | 0.185 | 0.177 | 0.198 | 0.000 | 0.000 |
| 2033–34 | 0.022 | 0.029 | 0.005 | 0.056 | 0.033 | 0.001 | 0.007 |
| 2034–35 | 0.355 | 0.354 | 0.410 | 0.383 | 0.442 | 0.002 | -0.001 |
| 2035–36 | 0.367 | 0.366 | 0.430 | 0.400 | 0.467 | 0.003 | -0.001 |
| 2036–37 | 0.382 | 0.380 | 0.450 | 0.416 | 0.491 | 0.005 | -0.002 |
| 2037–38 | 0.394 | 0.392 | 0.468 | 0.431 | 0.513 | 0.006 | -0.002 |
| 2038–39 | 0.396 | 0.397 | 0.475 | 0.447 | 0.537 | 0.013 | 0.000 |
| 2039–40 | 0.419 | 0.419 | 0.506 | 0.468 | 0.566 | 0.011 | 0.000 |

### Paired expected (£bn, mean ± SE): gross

| Year | legacy | frozen | reweight | types | both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2027–28 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2028–29 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2029–30 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2030–31 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2031–32 | 0.397 ± 0.177 | 0.397 ± 0.177 | 0.439 ± 0.196 | 0.422 ± 0.188 | 0.465 ± 0.207 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2032–33 | 1.026 ± 0.203 | 1.026 ± 0.203 | 1.157 ± 0.229 | 1.097 ± 0.217 | 1.229 ± 0.243 | 0.002 ± 0.000 | 0.000 ± 0.000 |
| 2033–34 | 1.693 ± 0.244 | 1.693 ± 0.244 | 1.939 ± 0.279 | 1.815 ± 0.261 | 2.067 ± 0.297 | 0.006 ± 0.001 | 0.000 ± 0.000 |
| 2034–35 | 2.527 ± 0.275 | 2.527 ± 0.275 | 2.935 ± 0.319 | 2.723 ± 0.296 | 3.147 ± 0.342 | 0.015 ± 0.002 | 0.000 ± 0.000 |
| 2035–36 | 3.610 ± 0.244 | 3.610 ± 0.244 | 4.246 ± 0.287 | 3.911 ± 0.264 | 4.577 ± 0.309 | 0.030 ± 0.002 | 0.000 ± 0.000 |
| 2036–37 | 4.713 ± 0.317 | 4.713 ± 0.317 | 5.599 ± 0.376 | 5.128 ± 0.345 | 6.068 ± 0.408 | 0.053 ± 0.004 | 0.000 ± 0.000 |
| 2037–38 | 5.260 ± 0.343 | 5.260 ± 0.343 | 6.301 ± 0.411 | 5.746 ± 0.375 | 6.861 ± 0.447 | 0.074 ± 0.005 | 0.000 ± 0.000 |
| 2038–39 | 6.630 ± 0.308 | 6.630 ± 0.308 | 8.003 ± 0.371 | 7.277 ± 0.338 | 8.765 ± 0.407 | 0.115 ± 0.005 | 0.000 ± 0.000 |
| 2039–40 | 8.042 ± 0.057 | 8.042 ± 0.057 | 9.765 ± 0.070 | 8.842 ± 0.063 | 10.723 ± 0.077 | 0.158 ± 0.001 | 0.000 ± 0.000 |

### Paired expected (£bn, mean ± SE): net

| Year | legacy | frozen | reweight | types | both | Interaction | Common inputs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2027–28 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2028–29 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2029–30 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2030–31 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| 2031–32 | 0.267 ± 0.120 | 0.269 ± 0.121 | 0.297 ± 0.133 | 0.287 ± 0.129 | 0.315 ± 0.141 | -0.000 ± 0.000 | 0.001 ± 0.001 |
| 2032–33 | 0.670 ± 0.137 | 0.672 ± 0.137 | 0.755 ± 0.154 | 0.723 ± 0.147 | 0.807 ± 0.164 | 0.001 ± 0.000 | 0.002 ± 0.001 |
| 2033–34 | 1.109 ± 0.163 | 1.108 ± 0.162 | 1.263 ± 0.185 | 1.198 ± 0.175 | 1.358 ± 0.198 | 0.005 ± 0.001 | -0.001 ± 0.002 |
| 2034–35 | 1.644 ± 0.180 | 1.640 ± 0.180 | 1.895 ± 0.208 | 1.787 ± 0.195 | 2.055 ± 0.224 | 0.012 ± 0.001 | -0.005 ± 0.001 |
| 2035–36 | 2.308 ± 0.204 | 2.301 ± 0.202 | 2.689 ± 0.243 | 2.518 ± 0.217 | 2.929 ± 0.259 | 0.023 ± 0.002 | -0.007 ± 0.001 |
| 2036–37 | 3.008 ± 0.217 | 2.996 ± 0.216 | 3.533 ± 0.261 | 3.293 ± 0.235 | 3.870 ± 0.282 | 0.039 ± 0.003 | -0.011 ± 0.002 |
| 2037–38 | 3.346 ± 0.218 | 3.335 ± 0.217 | 3.956 ± 0.265 | 3.683 ± 0.239 | 4.359 ± 0.290 | 0.054 ± 0.004 | -0.011 ± 0.001 |
| 2038–39 | 4.196 ± 0.212 | 4.197 ± 0.212 | 5.013 ± 0.267 | 4.668 ± 0.232 | 5.570 ± 0.289 | 0.085 ± 0.004 | 0.000 ± 0.001 |
| 2039–40 | 5.130 ± 0.090 | 5.130 ± 0.089 | 6.165 ± 0.136 | 5.708 ± 0.091 | 6.858 ± 0.137 | 0.115 ± 0.002 | 0.000 ± 0.001 |

## Central State Pension bill

Great Britain, triple-lock rule, nominal £bn. Additional pension includes the residual/protected-payment treatment already calculated by the model.

| Year | Treatment | Total | Basic | New | Additional/protected |
| --- | --- | --- | --- | --- | --- |
| 2024–25 | legacy | 116.097 | 63.697 | 37.112 | 15.288 |
| 2024–25 | frozen | 116.097 | 63.697 | 37.112 | 15.288 |
| 2024–25 | reweight | 114.862 | 63.234 | 36.561 | 15.068 |
| 2024–25 | types | 116.097 | 63.317 | 37.613 | 15.167 |
| 2024–25 | both | 114.862 | 62.834 | 37.086 | 14.943 |
| 2026–27 | legacy | 127.498 | 70.250 | 40.931 | 16.317 |
| 2026–27 | frozen | 127.498 | 70.250 | 40.931 | 16.317 |
| 2026–27 | reweight | 129.078 | 70.879 | 41.760 | 16.440 |
| 2026–27 | types | 127.571 | 57.958 | 55.487 | 14.126 |
| 2026–27 | both | 129.152 | 58.539 | 56.363 | 14.250 |
| 2027–28 | legacy | 132.830 | 73.260 | 42.685 | 16.885 |
| 2027–28 | frozen | 132.830 | 73.260 | 42.685 | 16.885 |
| 2027–28 | reweight | 136.817 | 74.923 | 44.604 | 17.289 |
| 2027–28 | types | 132.965 | 55.469 | 63.869 | 13.627 |
| 2027–28 | both | 136.952 | 57.073 | 65.849 | 14.030 |
| 2028–29 | legacy | 129.891 | 75.392 | 37.330 | 17.170 |
| 2028–29 | frozen | 129.891 | 75.392 | 37.330 | 17.170 |
| 2028–29 | reweight | 135.937 | 78.131 | 39.963 | 17.844 |
| 2028–29 | types | 130.086 | 51.888 | 65.199 | 12.998 |
| 2028–29 | both | 136.131 | 54.646 | 67.797 | 13.688 |
| 2029–30 | legacy | 133.638 | 77.616 | 38.431 | 17.591 |
| 2029–30 | frozen | 133.638 | 77.616 | 38.431 | 17.591 |
| 2029–30 | reweight | 142.378 | 81.630 | 42.196 | 18.551 |
| 2029–30 | types | 133.913 | 47.684 | 73.952 | 12.277 |
| 2029–30 | both | 142.649 | 51.851 | 77.493 | 13.306 |
| 2030–31 | legacy | 137.507 | 79.915 | 39.569 | 18.023 |
| 2030–31 | frozen | 137.507 | 79.915 | 39.569 | 18.023 |
| 2030–31 | reweight | 149.192 | 85.404 | 44.475 | 19.313 |
| 2030–31 | types | 137.878 | 42.957 | 83.414 | 11.507 |
| 2030–31 | both | 149.556 | 48.745 | 87.905 | 12.907 |
| 2034–35 | legacy | 155.896 | 91.002 | 45.059 | 19.835 |
| 2034–35 | frozen | 155.896 | 91.002 | 45.059 | 19.835 |
| 2034–35 | reweight | 180.794 | 104.496 | 53.551 | 22.747 |
| 2034–35 | types | 156.801 | 31.937 | 114.710 | 10.154 |
| 2034–35 | both | 181.769 | 40.781 | 128.660 | 12.328 |
| 2039–40 | legacy | 187.235 | 110.309 | 54.619 | 22.307 |
| 2039–40 | frozen | 187.235 | 110.309 | 54.619 | 22.307 |
| 2039–40 | reweight | 227.716 | 137.684 | 62.571 | 27.461 |
| 2039–40 | types | 189.721 | 16.794 | 164.534 | 8.393 |
| 2039–40 | both | 230.692 | 25.045 | 194.845 | 10.801 |

## Matched GB DWP coverage

Published DWP all-type GB totals exclude its separately reported overseas spending/caseload. Model values and differences below are copied from `coverage_comparisons`; no overseas allocation is imputed.

**2024–25 backward-raking caveat:** this report anchors native runtime 2025 weights. Only the 2025 anchor weights stay unchanged. Raking back to the 2024 data year changes its weights and GB totals, so the 2024–25 comparisons below include that input change. The native 2025 weights do not restore the builder's calibration.

| Year | Treatment | Model £bn | DWP £bn | Difference £bn | Model recipients m | DWP recipients m | Difference m |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024–25 | legacy | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | frozen | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | reweight | 114.862 | 131.254 | -16.392 | 10.960 | 11.885 | -0.925 |
| 2024–25 | types | 116.097 | 131.254 | -15.157 | 11.071 | 11.885 | -0.814 |
| 2024–25 | both | 114.862 | 131.254 | -16.392 | 10.960 | 11.885 | -0.925 |
| 2025–26 | legacy | 121.355 | 140.442 | -19.087 | 11.151 | 12.116 | -0.965 |
| 2025–26 | frozen | 121.355 | 140.442 | -19.087 | 11.151 | 12.116 | -0.965 |
| 2025–26 | reweight | 121.355 | 140.442 | -19.087 | 11.151 | 12.116 | -0.965 |
| 2025–26 | types | 121.376 | 140.442 | -19.066 | 11.151 | 12.116 | -0.965 |
| 2025–26 | both | 121.376 | 140.442 | -19.066 | 11.151 | 12.116 | -0.965 |
| 2026–27 | legacy | 127.498 | 148.269 | -20.771 | 11.193 | 12.152 | -0.959 |
| 2026–27 | frozen | 127.498 | 148.269 | -20.771 | 11.193 | 12.152 | -0.959 |
| 2026–27 | reweight | 129.078 | 148.269 | -19.191 | 11.339 | 12.152 | -0.813 |
| 2026–27 | types | 127.571 | 148.269 | -20.698 | 11.193 | 12.152 | -0.959 |
| 2026–27 | both | 129.152 | 148.269 | -19.118 | 11.339 | 12.152 | -0.813 |
| 2027–28 | legacy | 132.830 | 152.847 | -20.017 | 11.234 | 12.041 | -0.807 |
| 2027–28 | frozen | 132.830 | 152.847 | -20.017 | 11.234 | 12.041 | -0.807 |
| 2027–28 | reweight | 136.817 | 152.847 | -16.030 | 11.574 | 12.041 | -0.467 |
| 2027–28 | types | 132.965 | 152.847 | -19.882 | 11.234 | 12.041 | -0.807 |
| 2027–28 | both | 136.952 | 152.847 | -15.895 | 11.574 | 12.041 | -0.467 |
| 2028–29 | legacy | 129.891 | 157.761 | -27.870 | 10.740 | 12.142 | -1.402 |
| 2028–29 | frozen | 129.891 | 157.761 | -27.870 | 10.740 | 12.142 | -1.402 |
| 2028–29 | reweight | 135.937 | 157.761 | -21.823 | 11.238 | 12.142 | -0.904 |
| 2028–29 | types | 130.086 | 157.761 | -27.675 | 10.740 | 12.142 | -1.402 |
| 2028–29 | both | 136.131 | 157.761 | -21.630 | 11.238 | 12.142 | -0.904 |
| 2029–30 | legacy | 133.638 | 165.775 | -32.137 | 10.787 | 12.417 | -1.630 |
| 2029–30 | frozen | 133.638 | 165.775 | -32.137 | 10.787 | 12.417 | -1.630 |
| 2029–30 | reweight | 142.378 | 165.775 | -23.397 | 11.489 | 12.417 | -0.928 |
| 2029–30 | types | 133.913 | 165.775 | -31.862 | 10.787 | 12.417 | -1.630 |
| 2029–30 | both | 142.649 | 165.775 | -23.126 | 11.489 | 12.417 | -0.928 |
| 2030–31 | legacy | 137.507 | 174.065 | -36.558 | 10.835 | 12.692 | -1.857 |
| 2030–31 | frozen | 137.507 | 174.065 | -36.558 | 10.835 | 12.692 | -1.857 |
| 2030–31 | reweight | 149.192 | 174.065 | -24.872 | 11.750 | 12.692 | -0.942 |
| 2030–31 | types | 137.878 | 174.065 | -36.187 | 10.835 | 12.692 | -1.857 |
| 2030–31 | both | 149.556 | 174.065 | -24.508 | 11.750 | 12.692 | -0.942 |

DWP source: [https://www.gov.uk/government/publications/benefit-expenditure-and-caseload-tables-2026](https://assets.publishing.service.gov.uk/media/69dcdc8c6b695d635c34dcc4/outturn-and-forecast-tables-spring-forecast-2026.xlsx); workbook SHA-256 `11a591e4a2144ed6a686be6a9ded4e5d5b3b8d4887bd57c1ff0632bd251009de`.

### GB plus overseas type context

These are published DWP context figures, **not matched GB benchmarks**. New flat-rate spending excludes protected payments.

| Year | Basic £bn | New flat £bn | New protected £bn | Basic recipients m | New recipients m |
| --- | --- | --- | --- | --- | --- |
| 2024–25 | 66.660 | 46.353 | 1.195 | 8.591 | 4.393 |
| 2025–26 | 66.700 | 56.131 | 1.312 | 8.127 | 5.045 |
| 2026–27 | 66.150 | 64.812 | 1.430 | 7.666 | 5.527 |
| 2027–28 | 64.953 | 71.347 | 1.498 | 7.218 | 5.841 |
| 2028–29 | 62.565 | 79.503 | 1.575 | 6.777 | 6.369 |
| 2029–30 | 60.247 | 90.693 | 1.659 | 6.342 | 7.072 |
| 2030–31 | 57.755 | 102.426 | 1.724 | 5.907 | 7.775 |

| Benchmark comparison | Status/reason |
| --- | --- |
| GB basic/new spending and recipients | Unavailable: Overseas expenditure/caseload are separated only for all State Pension types together. |
| Age breakdown | Unavailable: No State Pension age-band expenditure/caseload table in this workbook. |
| Country/region breakdown | Unavailable: No country/region State Pension forecast table in this workbook. |
| 2034–35 / 2039–40 | Unavailable: No verified published long-term spending benchmark supplied. |

## Combined treatment: GB age and geography coverage

### Age

| Year | Age | Recipients m | Total £bn | Basic £bn | New £bn | Additional £bn | Basic recipients m | New recipients m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024–25 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2024–25 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2024–25 | 65_69 | 2.074 | 22.992 | 0.000 | 22.652 | 0.341 | 0.000 | 2.074 |
| 2024–25 | 70_74 | 2.907 | 30.977 | 13.491 | 14.435 | 3.051 | 1.564 | 1.343 |
| 2024–25 | 75_79 | 2.550 | 26.276 | 21.209 | 0.000 | 5.067 | 2.550 | 0.000 |
| 2024–25 | 80_84 | 1.694 | 17.566 | 14.016 | 0.000 | 3.550 | 1.694 | 0.000 |
| 2024–25 | 85_89 | 1.145 | 11.600 | 9.377 | 0.000 | 2.223 | 1.145 | 0.000 |
| 2024–25 | 90_plus | 0.591 | 5.451 | 4.741 | 0.000 | 0.711 | 0.591 | 0.000 |
| 2025–26 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2025–26 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2025–26 | 65_69 | 2.139 | 24.674 | 0.000 | 24.317 | 0.358 | 0.000 | 2.139 |
| 2025–26 | 70_74 | 2.907 | 32.215 | 8.808 | 21.101 | 2.306 | 0.988 | 1.919 |
| 2025–26 | 75_79 | 2.570 | 27.487 | 22.226 | 0.000 | 5.261 | 2.570 | 0.000 |
| 2025–26 | 80_84 | 1.767 | 18.998 | 15.221 | 0.000 | 3.778 | 1.767 | 0.000 |
| 2025–26 | 85_89 | 1.159 | 12.157 | 9.871 | 0.000 | 2.286 | 1.159 | 0.000 |
| 2025–26 | 90_plus | 0.609 | 5.844 | 5.088 | 0.000 | 0.756 | 0.609 | 0.000 |
| 2026–27 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2026–27 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2026–27 | 65_69 | 2.202 | 26.621 | 0.000 | 26.238 | 0.383 | 0.000 | 2.202 |
| 2026–27 | 70_74 | 2.939 | 34.149 | 4.598 | 27.979 | 1.572 | 0.503 | 2.436 |
| 2026–27 | 75_79 | 2.536 | 28.326 | 21.212 | 2.145 | 4.969 | 2.353 | 0.183 |
| 2026–27 | 80_84 | 1.877 | 21.099 | 16.944 | 0.000 | 4.155 | 1.877 | 0.000 |
| 2026–27 | 85_89 | 1.162 | 12.692 | 10.332 | 0.000 | 2.360 | 1.162 | 0.000 |
| 2026–27 | 90_plus | 0.623 | 6.266 | 5.453 | 0.000 | 0.812 | 0.623 | 0.000 |
| 2027–28 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2027–28 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2027–28 | 65_69 | 2.264 | 28.438 | 0.000 | 28.031 | 0.407 | 0.000 | 2.264 |
| 2027–28 | 70_74 | 2.993 | 36.156 | 1.419 | 33.752 | 0.985 | 0.151 | 2.841 |
| 2027–28 | 75_79 | 2.449 | 28.371 | 19.708 | 4.067 | 4.596 | 2.114 | 0.335 |
| 2027–28 | 80_84 | 2.040 | 23.790 | 19.123 | 0.000 | 4.668 | 2.040 | 0.000 |
| 2027–28 | 85_89 | 1.188 | 13.501 | 10.997 | 0.000 | 2.504 | 1.188 | 0.000 |
| 2027–28 | 90_plus | 0.640 | 6.696 | 5.826 | 0.000 | 0.871 | 0.640 | 0.000 |
| 2028–29 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2028–29 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2028–29 | 65_69 | 1.744 | 22.690 | 0.000 | 22.396 | 0.293 | 0.000 | 1.744 |
| 2028–29 | 70_74 | 3.056 | 37.862 | 0.000 | 37.034 | 0.827 | 0.000 | 3.056 |
| 2028–29 | 75_79 | 2.414 | 28.653 | 16.292 | 8.366 | 3.995 | 1.715 | 0.699 |
| 2028–29 | 80_84 | 2.129 | 25.421 | 20.450 | 0.000 | 4.971 | 2.129 | 0.000 |
| 2028–29 | 85_89 | 1.236 | 14.425 | 11.747 | 0.000 | 2.677 | 1.236 | 0.000 |
| 2028–29 | 90_plus | 0.660 | 7.080 | 6.156 | 0.000 | 0.924 | 0.660 | 0.000 |
| 2029–30 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2029–30 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2029–30 | 65_69 | 1.797 | 23.972 | 0.000 | 23.664 | 0.308 | 0.000 | 1.797 |
| 2029–30 | 70_74 | 3.136 | 39.823 | 0.000 | 38.959 | 0.864 | 0.000 | 3.136 |
| 2029–30 | 75_79 | 2.407 | 29.306 | 11.331 | 14.870 | 3.105 | 1.163 | 1.245 |
| 2029–30 | 80_84 | 2.173 | 26.567 | 21.395 | 0.000 | 5.172 | 2.173 | 0.000 |
| 2029–30 | 85_89 | 1.297 | 15.525 | 12.644 | 0.000 | 2.881 | 1.297 | 0.000 |
| 2029–30 | 90_plus | 0.678 | 7.456 | 6.480 | 0.000 | 0.976 | 0.678 | 0.000 |
| 2030–31 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2030–31 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2030–31 | 65_69 | 1.852 | 25.315 | 0.000 | 24.992 | 0.323 | 0.000 | 1.852 |
| 2030–31 | 70_74 | 3.231 | 42.045 | 0.000 | 41.139 | 0.906 | 0.000 | 3.231 |
| 2030–31 | 75_79 | 2.416 | 30.179 | 6.179 | 21.774 | 2.227 | 0.632 | 1.783 |
| 2030–31 | 80_84 | 2.201 | 27.548 | 22.208 | 0.000 | 5.340 | 2.201 | 0.000 |
| 2030–31 | 85_89 | 1.358 | 16.673 | 13.584 | 0.000 | 3.089 | 1.358 | 0.000 |
| 2030–31 | 90_plus | 0.691 | 7.795 | 6.774 | 0.000 | 1.021 | 0.691 | 0.000 |
| 2034–35 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2034–35 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2034–35 | 65_69 | 1.935 | 29.596 | 0.000 | 29.231 | 0.364 | 0.000 | 1.935 |
| 2034–35 | 70_74 | 3.622 | 52.734 | 0.000 | 51.646 | 1.088 | 0.000 | 3.622 |
| 2034–35 | 75_79 | 2.646 | 37.092 | 0.000 | 35.465 | 1.627 | 0.000 | 2.646 |
| 2034–35 | 80_84 | 2.071 | 28.936 | 12.920 | 12.317 | 3.698 | 1.138 | 0.933 |
| 2034–35 | 85_89 | 1.699 | 23.271 | 19.046 | 0.000 | 4.225 | 1.699 | 0.000 |
| 2034–35 | 90_plus | 0.803 | 10.140 | 8.815 | 0.000 | 1.325 | 0.803 | 0.000 |
| 2039–40 | under_60 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2039–40 | 60_64 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 2039–40 | 65_69 | 1.865 | 33.906 | 0.000 | 33.518 | 0.388 | 0.000 | 1.865 |
| 2039–40 | 70_74 | 3.789 | 65.395 | 0.000 | 64.152 | 1.243 | 0.000 | 3.789 |
| 2039–40 | 75_79 | 3.068 | 50.979 | 0.000 | 48.893 | 2.085 | 0.000 | 3.068 |
| 2039–40 | 80_84 | 2.283 | 38.045 | 0.000 | 35.972 | 2.073 | 0.000 | 2.283 |
| 2039–40 | 85_89 | 1.640 | 26.534 | 11.167 | 12.310 | 3.058 | 0.809 | 0.831 |
| 2039–40 | 90_plus | 1.063 | 15.833 | 13.879 | 0.000 | 1.954 | 1.063 | 0.000 |

### Country

**Withheld family:** a coverage level or treatment/year difference had too few contributors for publication. The whole family is withheld across paths, treatments, years and policies; no raw-data fallback is used.

### Region

**Withheld family:** a coverage level or treatment/year difference had too few contributors for publication. The whole family is withheld across paths, treatments, years and policies; no raw-data fallback is used.

## Checks, privacy and part C gates

| Check | Result |
| --- | --- |
| Complete paired design | Passed; forty paired selections and five treatments |
| Maximum raking readback relative error, all runs/years | 3.12764343e-08 (3936 checks; required ≤1e-6) |
| Eligible data-year component identity to £0.01 | Passed in all supplied accounting checks |
| Unchanged-type additional pension to £0.01 | Passed in all supplied accounting checks |
| Below-model-pension-age positive-report exceptions | 40 |
| Publication privacy audit | Passed; person/household, component and union support checked |
| Audited treatment pairs / years | 160 |
| Audited consecutive-year treatment comparisons | 75 |
| Audited all-year treatment comparisons | 600 |
| Audited treatment-contrast/year comparisons | 1200 |
| Exact published-statistic contributor comparisons | 1960 |
| Exact cell-contributor support | Passed; recipient-weighted counts and normalised weighted amounts |
| Audited comparison scope | same-year treatment pairs; all-year pairs within treatment; four-snapshot treatment-contrast changes. Direct mixed treatment/year pairs are not separately audited. |
| Cross-year support checks | Passed; recipient/type, age-cell and weights beyond a common factor |
| Minimum nonzero contributors | 10 |
| Linked age family withheld | False |
| Linked geography family withheld | True |
| Represented top-coding applied | True |
| Uncapped-age fallback | False |
| Supplied survey head flags retained | is_benunit_head, is_household_head |

Source build **1.56.16** declares calibration year **2025** ([immutable source](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57)). This pilot anchors **native runtime 2025 weights**. Builder calibration restored: **False**; artifact calibration manifest verified: **False**. Native runtime 2025 weights; builder calibration preservation unverified. The eligible-record identity passes; the all-record identity gate remains pending for below-pension-age positive reporters (40 in the supplied build). Part C needs the certified calibrated-year artifact and weight-materialisation contract, resolution/reporting of those exceptions through the appropriate data/model build, a State Pension/Pension Credit/Housing Benefit version bridge, and a repeat on part A's upgraded bundle. Later native calibrations, Scottish heating-payment coverage, the explicit age-80 addition and survey/overseas limitations remain as described in the design report. The publication support proof is tied to the read pension-formula hashes; part C must reread changed formulas and renew the common-positive-factor proof when moving to the upgraded bundle. It checks the audited pension components and pinned inputs over the comparison families listed above; it does not enumerate every nonlinear programme-state contrast.

### Integration evidence from full-model runs

| Check | File-derived result |
| --- | --- |
| Legacy central versus committed reference | True |
| Opt-in engine run | True |
| Record diagnostics suppressed | True |
| Persistent versus isolated worker | True |
| Full-model verification jobs (by construction) | 5 |
| Preceding worker mode (verified calculation source) | legacy |
| Integration file SHA-256 | cddcd25af6866e2ea7b55c017478740e04900d91456f9407393e305e497d99fb |
| Worker-equivalence file SHA-256 | 008868d0324348c99e378badba3cb8b99791c520160d4f75cbf5653f9aad39c1 |

The four check outcomes come from the two private evidence files, whose saved source hashes are bound to this calculation. The five-job count follows the checks by construction; the preceding legacy mode comes from the verified calculation source. The equivalence check has one preceding legacy job; it does not exhaust the production worker reuse sequence.

## Runtime and publication provenance

| Provenance | Value |
| --- | --- |
| Final approved JSON | ageing_validation.json |
| Final JSON SHA-256 | cf6718a62fc3ac774d1d5cce8a1431012df07aa8fa601922d4191a31a392a918 |
| Generated at | 2026-10-05T06:53:49+00:00 |
| Calculation head | 217395208083401744b4325f9a0375d7ffb55574 |
| Calculation source files verified against head | True |
| Calculation source files checked | 15 |
| Saved producer dirty flag (unmeasured) | False |
| Calculation-start whole-tree cleanliness | Not measured by the pilot driver; source-map files verified separately |
| Publication head | 88d579a8f6c319f1eb368ab3a2afda2334a4a070 |
| Publication tree dirty | False |
| Dataset | enhanced_frs_2024_25 |
| Data year | 2024 |
| Bundle id | uk-5.3.0 |
| Certified data build | policyengine-uk-data-1.56.16 |
| ONS projection CSV SHA-256 | df91f70d81232225fe5516842390f3de3b2d5e6279b6a762cb28bcf63378229f |
| Source expected-value JSON SHA-256 | e94cce9fe564c25d493bcef2f6f5489270801bfff8e8f930c3aed77c6fdd7f14 |
| Execution driver SHA-256 (rehashed at publication) | 15c496b283d834bf509219aad9bd5828b94435d5431dba29bf0bc10cafb6faf2 |
| Execution driver verified at publication | True |
| Execution log head/requested slots basis | declared_by_driver |
| Execution log SHA-256 | e25172e6f5e0e47c6917ceefa48e203e2edbf74a7e4acfc06fa98e08bc9c4055 |
| Fiscal function SHA-256 | 753dce8b69efebc1c049097992e802a489f09f41ddecbc7dab046c5bb5e8fa5e |
| Publication guard SHA-256 | 5968e81d9192f9552aeb91958a0885116a95a31de2d8d980cda6e5227bf4a92b |
| Publication-audited plan SHA-256 | c7eac9ce327c923a6e64b080d5e42ce40247353bd9ddc2d87ec633c08db12f50 |
| Persistent workers | True |
| Maximum jobs per worker | 20 |

Calculation verification compares saved Python/TOML semantics and raw population-input hashes against the files at the calculation commit. It establishes the covered code/input identity; the original driver did not measure whole-tree cleanliness at job dispatch.

### Runtime engine source hashes

| Source | Saved hash/value |
| --- | --- |
| breakdowns.py | d00508f5721dad16db354dd316cce68af61f8161cbbad074e5aca0aad1dca27f |
| cohorts.py | 2db29a3e9917418a242921d91fa1b6eff986f3be2ef710304b584c0a3a21d8c5 |
| config.py | b1b294ad8398827223ab5ada124b14f34c59ac63558a8c11f25f00b9ce8c8676 |
| demography.py | ad65c311fbe78d4573ed78300d948461929d6bcdc95c6e22b3da3c009e18c434 |
| engine.py | bc7964e799e14347737f773bc26881560a138dfc97a2e5ab1c35cd96d10016d1 |
| model_horizon.py | 4b1fb5b9706790557388826a269fe9b910613eaaca62840ad1de83e55f1fa5e4 |
| pyproject.toml | 9ba4c11d1d7e131945660d655f82a1ea0e691cfa1b96529fc5a5e7c4cd7c0522 |
| rules.py | c96b7960bce2c30cfb844659c72704ac763953c31c441c2a885375defa5fbaf1 |

### Runtime validation source hashes

| Source | Saved hash/value |
| --- | --- |
| ageing_validation.py | ca95b0c130e9588cef27489b61edc999aae1f72a551bed0211b031301e8319f0 |
| central.py | 00aa0b707a07e54d04e93958c6c58c800eac4d934acb1e212a57d2d8c5c843a3 |
| demography.py | ad65c311fbe78d4573ed78300d948461929d6bcdc95c6e22b3da3c009e18c434 |
| expected_value.py | a394b8ea2cc70c49d6d6f8cfde1196efa23d1a1ce5b6930beb2181114baf865f |
| ons_npp_2024_uk_age_sex.csv | df91f70d81232225fe5516842390f3de3b2d5e6279b6a762cb28bcf63378229f |
| ts_backtest.py | 940a77bed8696356b5ff9155440e2470d5db0c4a082f12b85af8997281754aeb |
| ts_methods.py | 921840847364ce210463f9c78e7b3ee636d91519eea7e889ea4dba069f1bd260 |
| ts_monthly.py | 3658130784f7afa81171fc21f8873a37b9b91055b6f933e5ca4e92e91c4b7af9 |

### Audited pension formula hashes

| Source | Saved hash/value |
| --- | --- |
| additional_state_pension | b36dd29ab73166135941d0a8e5cead2b9eb983ae1b5ce586a9839806e4e7c1bd |
| basic_state_pension | 80fcb72367d5cfe5f693e0d5d4fd86337028443ca0b3dab225eff96e97cf8aa3 |
| new_state_pension | cc6ed27cede8a02b1bfc25fcbd7dbb8b05e1fe3ea3c160762bec5cfcbe7b8e2c |
| state_pension | 549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352 |

### Publication audit engine hashes

| Source | Saved hash/value |
| --- | --- |
| breakdowns.py | d00508f5721dad16db354dd316cce68af61f8161cbbad074e5aca0aad1dca27f |
| cohorts.py | 2db29a3e9917418a242921d91fa1b6eff986f3be2ef710304b584c0a3a21d8c5 |
| config.py | b1b294ad8398827223ab5ada124b14f34c59ac63558a8c11f25f00b9ce8c8676 |
| demography.py | ad65c311fbe78d4573ed78300d948461929d6bcdc95c6e22b3da3c009e18c434 |
| engine.py | bc7964e799e14347737f773bc26881560a138dfc97a2e5ab1c35cd96d10016d1 |
| model_horizon.py | 4b1fb5b9706790557388826a269fe9b910613eaaca62840ad1de83e55f1fa5e4 |
| pyproject.toml | 9ba4c11d1d7e131945660d655f82a1ea0e691cfa1b96529fc5a5e7c4cd7c0522 |
| rules.py | c96b7960bce2c30cfb844659c72704ac763953c31c441c2a885375defa5fbaf1 |

### Publication code SHA-256

| Source | Saved hash/value |
| --- | --- |
| ageing_publication.py | 5968e81d9192f9552aeb91958a0885116a95a31de2d8d980cda6e5227bf4a92b |
| publish_ageing_validation.py | e93fc92a8ca5fd7dc66352532ec7cbbee725a5f449d1de4e9bdc0641f11f53f9 |
| report_ageing_validation.py | ba9b0e3edfee7d2759add4e71123fb9790e817aa88c63143974d781286c4e4e6 |

### Publication engine source hashes

| Source | Saved hash/value |
| --- | --- |
| breakdowns.py | d00508f5721dad16db354dd316cce68af61f8161cbbad074e5aca0aad1dca27f |
| cohorts.py | 2db29a3e9917418a242921d91fa1b6eff986f3be2ef710304b584c0a3a21d8c5 |
| config.py | b1b294ad8398827223ab5ada124b14f34c59ac63558a8c11f25f00b9ce8c8676 |
| demography.py | ad65c311fbe78d4573ed78300d948461929d6bcdc95c6e22b3da3c009e18c434 |
| engine.py | bc7964e799e14347737f773bc26881560a138dfc97a2e5ab1c35cd96d10016d1 |
| model_horizon.py | 4b1fb5b9706790557388826a269fe9b910613eaaca62840ad1de83e55f1fa5e4 |
| pyproject.toml | 9ba4c11d1d7e131945660d655f82a1ea0e691cfa1b96529fc5a5e7c4cd7c0522 |
| rules.py | c96b7960bce2c30cfb844659c72704ac763953c31c441c2a885375defa5fbaf1 |

### Publication validation source hashes

| Source | Saved hash/value |
| --- | --- |
| ageing_validation.py | ca95b0c130e9588cef27489b61edc999aae1f72a551bed0211b031301e8319f0 |
| central.py | 00aa0b707a07e54d04e93958c6c58c800eac4d934acb1e212a57d2d8c5c843a3 |
| demography.py | ad65c311fbe78d4573ed78300d948461929d6bcdc95c6e22b3da3c009e18c434 |
| expected_value.py | a394b8ea2cc70c49d6d6f8cfde1196efa23d1a1ce5b6930beb2181114baf865f |
| ons_npp_2024_uk_age_sex.csv | df91f70d81232225fe5516842390f3de3b2d5e6279b6a762cb28bcf63378229f |
| ts_backtest.py | 940a77bed8696356b5ff9155440e2470d5db0c4a082f12b85af8997281754aeb |
| ts_methods.py | 921840847364ce210463f9c78e7b3ee636d91519eea7e889ea4dba069f1bd260 |
| ts_monthly.py | 3658130784f7afa81171fc21f8873a37b9b91055b6f933e5ca4e92e91c4b7af9 |

The runtime hashes above describe the calculations. Later publication guards or default-input enforcement can change the final branch head without changing these explicitly anchored runs; runtime and publication provenance are retained separately.
