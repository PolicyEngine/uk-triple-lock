I've finished the review. **None of the five forms passes, and that holds up.** Every form covers only 1/6 chronological terminal gaps under published earnings, which fails both the [0.50, 1.00] range and the Wilson-band condition. None of the problems below changes that outcome. I found no critical or high-severity bugs in the code as it stands. The main risks are in what happens after the gate, and in validation gaps.

**Limits of this review:**
- I had no shell, so I could not run `git diff ee02c8d..HEAD` or the test suite. I reviewed the working tree directly.
- The workspace changed while I was reading it. `docs/UNCERTAINTY_PILOT.md` grew a section on the historical aggregate estimate, and its test count went from 57 to 58.
- GitHub showed no comments on #14 or #15, so I could not check gate 3 or the corrected diagnosis for #15. I checked #14 section 4 and #9 A2 from the issue bodies.
- This was meant to be planning-only, but the plan file and exit-plan tools weren't available here, so this message is the review itself.

## What I checked and found correct
- **Held-out fitting:** the monthly forms are fitted on data to December of the year before each origin (`ts_backtest.py:462`), with no partly observed month. The annual VAR and its gap blocks also stop at `last_year = v0−1` (`ts_annual.py:35-46`). No outturn is used to set the means. Test B uses no leave-one-out pool.
- **Both suspension treatments:** applied to forecast draws (`ts_backtest.py:468-470`, and the past-years check at `:507-509`) and to outturns (`:249-251`).
- **Scores:** they match the pre-registered definitions (`ts_backtest.py:383-410`): earnings strictly below 2.5% for the floor, 28 variogram pairs, bias as forecast minus realised. The Newey–West SE matches the spec (Bartlett weights, lag 3, n/(n−1)), and origins are sorted (`history_data.error_blocks`).
- **Adequacy screen** (`ts_uncertainty.py:40-83`): applied literally. It requires both tests and both treatments, fails missing origins, allows only a zero score against a zero reference, and breaks ties by candidate order. `selection.json` agrees with the doc tables.
- **First-phase variance** (`expected_value.py:465-467`): includes the known-zero mass and handles an omitted zero stratum the same as an explicit one. `reweighted` passes the plug-in correctly.
- **Zero-stratum pairing:** with `include_zero=True` the zero stratum gets exactly 2 slots. `paired_mean_estimates` takes differences within strata over the same indices, and the stratum weights sum to 1.
- **Cache keys:** `engine.job_key` hashes the whole spec, so variant specs that reuse `draw_i` ids cannot collide with baseline specs.
- **Fiscal gate:** `build(run=True)` checks the screen before drawing anything or importing the engine (`expected_value.py:614-621`), and there is a test for it.

## Bugs and missing requirements

| # | Sev. | Where | Finding | Fix now or at rebuild |
|---|---|---|---|---|
| M1 | Medium | `expected_value.py:614-645` vs `ts_uncertainty.py:193,218` | If the original primary ever passes, `build(run=True)` runs the old design: 200 slots, no zero-stratum slots, its own allocation and sample. That is not the pre-registered 160-slot design. The ±0.5pp specs are built on the handoff design's indices, so they would not pair with what `build` runs. `build` also never runs the mean paths or the alternative forms' designs. | Latent trap until rebuild; there is no C1 runner yet. Make `run=True` refuse until it uses the handoff design. |
| M2 | Medium | `ts_backtest.py:466-472`, `398-405` | Under the suspended treatment, the 2021 cell has forecast and outturn gaps both exactly 0. That cell is therefore always "covered", with zero CRPS and zero bias. It accounts for 4 of the 24 cells in A/suspended annual coverage (83.3% → 80% without it) and also dilutes bias and CRPS. It follows the pre-registered rule and doesn't change the verdict, but it isn't disclosed. | Disclose now; deal with it in any redesign. |
| M3 | Medium | `tests/test_uncertainty.py` | Validation gaps that need no PolicyEngine: (a) no test that the committed `selection.json` equals `adequacy(scores.json)`, or that the doc tables match `scores.json`; (b) no test that the backtest applies the suspension to the draws; (c) no check that monthly fits use no data after the origin (only the annual gap blocks are checked, at line 85); (d) the handoff test (225-235) only compares ids, which match by construction. | Now |
| M4 | Low–Med | `docs/uncertainty/historical_estimator.json` | No code in the repo writes this file. `reestimate_published` doesn't output the `published_results_sha256` field the JSON contains, and `main()` doesn't call it. The artifact can't be regenerated from the repo. | Now |
| L1 | Low | `ts_annual.py:53-54` | Gap blocks start at the first unobserved year (the origin year itself), so the four scored years span two independent blocks. This matches the pre-registered "concatenate and truncate" wording. But the claim that the bridge "jointly preserves four years" (pilot doc line 7, module docstring) doesn't hold for the scored window. | Fix the wording now; consider aligning blocks in a redesign |
| L2 | Low | `ts_uncertainty.py:86,122` vs `176` | Draw and sample seeds are hard-coded literals, while the manifest records `EV.SEED` and `EV.SAMPLE_SEED`. They agree today but nothing links them. | Now |
| L3 | Low | `ts_uncertainty.py:137` → `expected_value.py:256-264` | Design summaries label the gap `gbp_week`, but the design is built with `base_weekly=1`, so values are relative. Quantiles are also rounded to 2 decimal places (0.03–0.13), which loses most of the information. | Now |
| L4 | Low | `expected_value.py:504-506`; `ts_uncertainty.py:149-153` | The share-of-spending output averages per-run ratios rather than dividing mean saving by mean spending, and covers gross only; label it accordingly. Paired mean-path estimates cover only gross and net. | At rebuild |
| L5 | Low | `ts_backtest.py:501-516`; `ts_uncertainty.py:75` | The past-years check has no finiteness check, although the pre-registered rule requires all scores to be finite. Failure messages print unrounded percentiles such as `97.82000000000002`, which also appear in the doc. | Now |
| L6 | Low | `test_uncertainty.py:78`; manifest | `assert scipy.__version__ == '1.18.1'` makes every candidate test fail on any other scipy version; it pins an environment rather than testing reproducibility. The draw hashes depend on BLAS and LAPACK (`lstsq`), but the manifest doesn't record Python, platform or BLAS, so the "replays exactly" claim may not hold on Linux. | Now |
| L7 | Low | `ts_methods.py:167-172` | The Armijo fix itself is sound: Newton steps are descent directions, the threshold is about 1e3 times machine precision relative to the objective, a failure would still raise `TiltError`, and both cases from #15 are pinned with `@example`. The comment saying backtracking "can stall indefinitely" is inaccurate; it is bounded at `t > 1e-8`. | Fix the comment now |
| L8 | Low | `ts_uncertainty.py:218` | The mean-path spec files include the identical-rates check draw (`draw_109`), which is not identical under the variants, and nothing labels it. A runner that asserts zero saving by id would fail. | At rebuild |
| L9 | Info | `central.py:74-78`, `ts_uncertainty.py:115-116` | The premium compares rounded triple-lock rates minus statutory AWE growth against OBR fiscal-year LTED earnings. The definitions differ, but it is labelled as a comparator. | — |

## Issue coverage
- **#14 section 4:**
  - Implemented in code: the first-phase variance and its separate components for every year, the flag excluding reweightings under 100 effective runs, and the share of flat-rate spending.
  - Deferred, correctly blocked by the failed screen: full runs for the VAR(2) and annual forms, running the mean-path variants, and showing a range beside the headline.
  - Gate 3 not verified, since the issue comments weren't visible.
- **#9 A2:** the published `data/results.json` and dashboard still show path-sampling-only SEs and the old range, which rests on a row with 43.8 effective runs. The PR says so openly. A2 stays open for the published figures until the rebuild.
- **#15:** fixed, apart from the comment in L7. I couldn't compare it with the corrected diagnosis.

## Priorities
- **Before merge:** M1 (block `build(run=True)`), M3 (consistency and held-out tests), M4 (make the historical file regenerable), and L2, L3, L5 and L6.
- **For the rebuild and any re-registered redesign:** M2, L1, L4 and L8. The redesign must not retroactively change the frozen screen.