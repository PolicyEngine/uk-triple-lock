# B1 full runs on a weighted sample of the Bayesian paths: report

Generated 2026-11-19T02:24+00:00 by `scripts/b1_full_runs.py` (docs/METHOD.md, "Specification: full runs on a weighted sample of the Bayesian paths, 18 November 2026"). Full data: `data/b1/full_runs.json`. Nothing here changes `data/results.json` or the paper.

## What was run
- policyengine.py 6.20.2, policyengine-uk 2.179.1, policyengine-core 3.34.10, Python 3.13.15; Microcosm national file `uk-frs-calibration-attempt-20261115T104657Z-fcfac709` (SHA-256 301d2fe5e780..., the file the 6.20.2 bundle certifies).
- **Not a certified pair:** 6.20.2 pins and certifies policyengine-uk 2.177.7 / core 3.34.10 with this file; the runs use 2.179.1 as instructed and registered (see deviations).
- Paths: the headline's 399,440 B1 paths (seed 20261113; 2039 rule-arithmetic gross median reproduced, £9.24bn). Stratum 0 (rules identical every April to 2039): 32,141 paths, W0 = 0.0805, no runs. Non-identical paths with no positive 2039 saving: 0.
- Sample: N = 100 draws (seed 20261118, min 4 per stratum, Neyman on rule-arithmetic gross), 100 unique paths. N=100 (the registered minimum): the central rerun took 871 s at one worker on this shared host (about 40 GiB held by other workloads, ~14 GiB available); two workers give about 100 runs in ~12.5 h, finishing before 08:00 on 19 November

| Stratum | Probability | 2039 rule gross £bn | W | Draws | Runs ok | Net/gross mean (min-max) | Full/rule gross (6.20.2 base) |
|---|---|---|---|---|---|---|---|
| 1 | 0.00-0.10 | 0.2-2.4 | 0.0920 | 5 | 5 | 0.689 (0.676-0.707) | 1.0000 (1.0000-1.0000) |
| 2 | 0.10-0.25 | 2.4-5.3 | 0.1379 | 10 | 10 | 0.693 (0.676-0.711) | 1.0000 (1.0000-1.0000) |
| 3 | 0.25-0.40 | 5.3-8.1 | 0.1379 | 10 | 10 | 0.695 (0.684-0.708) | 1.0000 (1.0000-1.0000) |
| 4 | 0.40-0.50 | 8.1-10.1 | 0.0920 | 5 | 5 | 0.692 (0.686-0.700) | 1.0000 (1.0000-1.0000) |
| 5 | 0.50-0.60 | 10.1-12.4 | 0.0920 | 5 | 5 | 0.683 (0.670-0.690) | 1.0000 (1.0000-1.0000) |
| 6 | 0.60-0.75 | 12.4-16.6 | 0.1379 | 14 | 14 | 0.695 (0.686-0.703) | 1.0000 (1.0000-1.0000) |
| 7 | 0.75-0.90 | 16.6-23.7 | 0.1379 | 25 | 25 | 0.693 (0.681-0.710) | 1.0000 (1.0000-1.0000) |
| 8 | 0.90-0.95 | 23.7-28.9 | 0.0460 | 6 | 6 | 0.691 (0.681-0.697) | 1.0000 (1.0000-1.0000) |
| 9 | 0.95-0.99 | 28.9-41.1 | 0.0368 | 11 | 11 | 0.694 (0.684-0.704) | 1.0000 (1.0000-1.0000) |
| 10 | 0.99-1.00 | 41.1-187.7 | 0.0092 | 9 | 9 | 0.687 (0.675-0.699) | 1.0000 (1.0000-1.0000) |

## Anchor reruns (2039-40), 6.20.2 against stored 6.11.1
| Path | Gross £bn | Net £bn | Households losing % | Mean loss £ | Run time s | Peak RSS GiB |
|---|---|---|---|---|---|---|
| OBR central | 0.48 -> 0.48 | 0.33 -> 0.33 | 29.63 -> 29.96 | 35 -> 35 | 756 | 7.7 |
| OBR long-term (wedge) | 10.87 -> 10.90 | 7.34 -> 7.48 | 29.74 -> 30.38 | 801 -> 790 | 701 | 8.1 |

## Headline estimates, 2039-40 (stratified bootstrap, 2,000 resamples within strata, seed 20261118)
- **Median net saving:** £6.70 (SE 0.31; 95% 5.97 to 6.89)bn.
- **Average annual loss among losing households (mean_loss_gbp):** stratum-weighted median over paths £745 (SE 15; 95% 745 to 781); in the median-gross stratum (stratum 4) £681 (SE 17; 95% 648 to 713).
- **Gross median:** full runs £9.70 (SE 0.46; 95% 8.67 to 9.96)bn; rule arithmetic £9.24bn on the stored 6.11.1 base, £9.27bn on the 6.20.2 central rerun's base.
- **Net-to-gross:** the paper's fixed ratio is 0.683 (D.B1_RHO); by stratum see the table. Fixed ratio x full-run gross median = £6.63bn.
- *Not registered, a check on the above:* full-run gross equals the rule arithmetic path by path (table), so the 100-run median carries sampling noise (its gross median £9.70bn against £9.27bn over all paths). Each stratum's mean net/gross and loss/gross applied to all 399,440 paths gives median net £6.41 (SE 0.02; 95% 6.38 to 6.45)bn and median mean_loss_gbp £737 (SE 2; 95% 735 to 741); pooled net/gross 0.692.
- mean_loss_gbp median with stratum 0 at the engine's £0 (the reading parallel to the net median): £703 (SE 33; 95% 630 to 722).
- Like-for-like net/gross: 6.20.2 anchors 0.686 (central) and 0.686 (long-term), against 0.692 pooled over the sample and 0.683 fixed in the paper (stored 6.11.1 anchors 0.684 and 0.675).
- Weighted mean net (error budget only, not for print): £7.64bn, SE 0.07 (path sampling 0.07).
- Engine rates against rule arithmetic, every run: max difference 0.0e+00.
- Failed runs: none after retry.

## Adaptations and deviations from the registered design
- **Version and dataset pins (datasets.py, model_horizon.check_upstream):** relaxed in memory by this script only: a DATASETS entry for the fcfac709 file (SHA-256 checked before every use by datasets.materialize) and check_upstream_2179, which admits exactly the 21 reviewed changed files of the 2.153.4 guard set and still fails if any other guarded file, or any of the builders the horizon extension and Scenario entry rely on (lagged series, statutory inputs, triple lock, private pension uprating, gov_balance, scenario, September-CPI uprating), differs.
- **path_following: model_new_state_pension:** 2.179.1 projects the model's own full new State Pension each April from the previous year's rate to the nearest 5p (create_rate_projection, not in 2.151.0). The unrounded expectation (tolerance 2e-4) failed on the first B1 path (3.9e-4). Expectation replaced by the same 5p-rounded rule on the model's own triple lock, checked exactly (1e-9); every other check unchanged.
- **Model version.** The registered text and the instruction name policyengine.py 6.20.2 with policyengine-uk 2.179.1, but 6.20.2's [uk] extra and bundle manifest pin and certify policyengine-uk 2.177.7 / core 3.34.10 with the fcfac709 Microcosm file. Installed: policyengine 6.20.2 (without [uk]), policyengine-uk 2.179.1, policyengine-core 3.34.10, and the file 6.20.2 certifies. The model/data pair is therefore uncertified (built and certified for 2.177.7).
- **Host admission floor.** jobs.py's 40 GiB Microcosm reservation could not be met on this shared host (12-17 GiB available while other workloads held 25-45 GiB). Jobs were admitted against measured resident peaks (5.6-15 GiB; 6 GiB budget + 2 GiB + outstanding) with one or two workers, adjusted live; the runner was restarted once (19:16), discarding two in-progress jobs, which reran from scratch. None of this changes a result (the central rerun before and after reproduced bit for bit).
- **Anchors in the queue.** The OBR long-term and central reruns ran in the sample queue (same specs and cache key as the anchors mode); the central path was run twice (before and after the path_following adaptation) with identical output.
- **mean_loss_gbp over paths.** Its stratum-weighted median is taken over the positive-saving paths (strata 1-10, W renormalised): on stratum-0 paths no household loses and the engine reports 0. The 'median-gross stratum' is the stratum holding the all-path rule-arithmetic 2039 gross median (stratum 4, £8.1-10.1bn).
- **Sample.** N = 100 draws as written to the design before any sample run (100 unique paths, no duplicate draws); all 100 completed, none failed after retry, so the failed-run min/max variants are not needed. The only failure (the first B1 path, model_new_state_pension 3.9e-4) predates the path_following adaptation and reran cleanly under it.

- On the 2.179.1 default parameter tree, Savings Credit threshold = guarantee - maximum/phase_in and pension-age HB aged = guarantee + maximum, aged_from_cutoff = guarantee, exactly in every projected year 2027-2039 (gaps only in published 2026: £0.04 and £0.003 a week), so set_flat_rates' linked branch reproduces the model's own derivation from the engine's earnings-linked guarantee.
- Diffs read against 2.153.4: the State Pension variables (basic, new, additional, state_pension input, state_pension_reported: age addition #2340 removed before the split, which the engine already handles), months_since_last_birthday (whole-population branch value only), create_economic_assumption_indices (horizon from the growth series; triple lock index unrounded), tax_benefit_system (new generation steps: State Pension 5p rate projection, linked PC/HB projection, UK total growth, energy indices), utils.parameters (fiscal-year conversion keeps 2015-2041 annual records), gov_tax/gov_spending (adds LISA charges/bonus, household_energy_payment, wales_childcare_offer: picked up by fiscal_variables, which reads the lists), create_earnings_uprating (docstring only), simulation.py against 2.177.7 (stored-draw input checks, dataset identifier checks). Admitted on run-time checks without a line-by-line read: the full 2.153.4->2.179.1 simulation.py diff and the two PC/HB builders (behaviour checked above) and the six PC/HB YAMLs.
- The 2.153.4 guard set used here omits household_tax and household_benefits, which 2.151.0's guards include and which differ on 2.179.1; the engine's run-time government/household income identity (totals, saving_components) covers them on every run.

## Caveats
- The registered median is the weighted median of 100 runs plus a point mass: a step function whose bootstrap intervals are asymmetric and whose value is set by a few runs in strata 3-5 (5-10 runs each). The supplementary ratio estimator (not registered) shows the size of that noise: £6.41bn against £6.70bn.
- The stored-vs-rerun differences reflect model and data changes together (not decomposed): base 2039 flat-rate spending +0.27%; lower Pension Credit and Housing Benefit offsets on the wedge (PC 0.81 -> 0.76bn, HB 0.23 -> 0.15bn), consistent with 2.179.1 deriving the Savings Credit threshold and pension-age HB allowances from the earnings-linked guarantee (#2576; checked to match the model's own derivation) but also affected by the new dataset; a winter fuel offset near zero (0.027 -> 0.001bn); the State Pension age addition (#2340) present but identical under both rules. Anchor net/gross 0.675 -> 0.686 (wedge), 0.684 -> 0.686 (central).
- Calendar CPI and earnings for each path are the central calendar path plus the path's statutory deviation (2039: the 2038 deviation), the registered modelling assumption.
- Peak memory figures are resident set sizes; macOS compressed much of each job, whose footprint reached 10-14 GiB.
- Run times are not representative of the model: median 636 s, up to 6,142 s, on a host thrashing under other workloads' memory load.
- The weighted mean net is for the error budget only and is not for print.
