# Method

Every fiscal and household figure is a full PolicyEngine UK run (policyengine 5.3.0, policyengine-uk 2.90.2) on the certified Enhanced FRS 2024-25, with Microcosm (`populace_uk_2023`) as a dataset sensitivity. Nothing is scaled or interpolated from another run. The code is the reference; this file points to it.

## The rules (`rules.py`)

- **Triple lock**: each April the basic and new State Pension rise by max(September CPI, May–July AWE total pay growth, 2.5%) of the year before. The inputs are taken to 0.1 point, as ONS publishes them, so the rate is exactly the larger input. One rounding (`rules.round_rate`, numpy's) takes every statutory input to 0.1 point: in the rules, in what set each rise, in the additional pension's September CPI and in the Pension Credit guarantee's earnings. What set a rise is the floor whenever neither input exceeds 2.5%, and CPI when the two inputs tie, in the history table and on every path alike.
- **Burnham plan**: the triple lock to April 2029. From April 2030 the level is L_t = max(L_{t-1}(1 + max(CPI, 2.5%)), A_t), where A_t = A_{t-1}(1 + earnings) and A starts at the 2029-30 level. The top-up to the earnings path is rounded up, so rounding never leaves the pension below it.

Property tests (`tests/test_rules.py`) check, for all inputs:
- the plan's guarantees;
- that its rate is the smallest one meeting both guarantees;
- that its unrounded level never exceeds the triple lock's;
- that the vectorised and single-path rates agree.

## A path through the model (`engine.py`)

A path is calendar-year CPI and earnings growth for 2027–2039, plus the statutory inputs for 2026–2038.

**Entering the model.** The calendar growth replaces `gov.economic_assumptions.yoy_growth.obr` (RPI and CPIH move by the same amount as CPI) in a Scenario applied before the data load. Passed as a reform, the same changes do nothing, because the derived series are built at load time. `model_horizon.py` first extends policyengine-uk's derived series to 2042; without it, benefit rates stop following the path after April 2029.

**What each run checks, in every year**, failing if any misses:
- CPI-uprated benefit rates follow the path's CPI the year before;
- CPI-indexed thresholds follow it the same year;
- employment income follows the path's earnings;
- the model's own triple lock and new State Pension follow the path;
- every flat-rate pension scales exactly by the ratio of the two rules' amounts;
- employer NI incidence is zero;
- the Pension Credit guarantee follows the path's earnings.

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. April 2027's benefit uprating is the model's own calendar-2026 CPI (2.3%) on every path, not September 2026 CPI.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. A pension cut can make a household eligible for Pension Credit guarantee credit, which in policyengine-uk passports it to its full rent in Housing Benefit; one heavily weighted record does this on some paths, moving the net figure by billions of pounds. Each run records how much the single record with the largest effect contributes in every year, and its share of the change; FRS records are licensed data, so the published file never gives a record's identifier, weight or amounts.

**Council tax reduction for Pension Credit recipients.** In England's pensioner scheme, policyengine-uk tapers council tax reduction on income after tax, does not count Pension Credit, and does not disregard the income of guarantee credit recipients as SI 2012/2885 (Schedule 1, paragraph 13) requires. Their council tax reduction therefore rises as the State Pension falls, when it should not change. In step 4 this makes the example pensioners on Pension Credit come out slightly ahead rather than even. In the survey runs the whole council tax reduction offset is small.

**The State Pension amounts.** The flat rates are set from each rule applied to the path's statutory inputs.

**Inputs held the same under both rules** (`engine.pinned_inputs`, `config.py`):
- **Pension type.** Each person's State Pension type (basic or new) is held at its survey-year value. Survey ages never advance, and policyengine-uk decides the type from age each year, so it would otherwise move a cohort a year from the basic to the new State Pension while still paying its additional pension on the basic basis, counting part of it twice. Each run reads the types back from the model in every year, fails if anyone's differs from the held one, and records the counts (`held_pension_type_records`, `held_pension_type_people`).
- **Additional State Pension.** The survey-year amount, grown by September CPI (published to April 2026, the path's after), as in law, for people over State Pension age that year.
- **State Pension age.** 67 from 2028-29 (the installed parameters stop at 66; the Pensions Act 2014 raises it). With ages held fixed, the survey's 66-year-olds are below it from then on.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk uprates it by CPI.

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components;
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- the single survey household that moves each year's net figure most.

**Jobs.** Each run is a job in its own process, cached under a hash of its arguments, what the engine's code computes (each file's syntax tree without comments or docstrings) and the package versions. The results file's provenance records the files' raw hashes.

## The central path (`central.py`)

**Calendar growth:**
- 2027–2030: the OBR's March 2026 EFO calendar-year CPI and average earnings, unrounded;
- 2031–2039: the OBR's long-term economic determinants (March 2026), converted from fiscal to calendar years (1/4 and 3/4).

**Statutory inputs:**
- April 2027: published May–July 2026 AWE and August 2026 CPI (September's is published on 21 October 2026);
- 2027–2030: the EFO's September-quarter CPI and April–June earnings;
- after that: the calendar path.

## The expected saving (`expected_value.py`)

The saving comes from years when CPI or the 2.5% floor runs ahead of earnings, so the saving on the expected path is not the expected saving.

1. **Draws.** 50,000 paths of a monthly VAR on log changes of the CPI index (D7BT) and AWE total pay (KAB9), fitted to 2000–2026 without the furlough months, with residual-bootstrap shocks (`ts_monthly.py`). Both the statutory and the calendar measures come from the same simulated months.
2. **Calibration.** The smoothest monthly drift path that makes the draws' mean calendar-year CPI and earnings growth equal the central path in every year (`ts_monthly.shift_to_calendar_means`, an equality-constrained least squares iterated to 1e-12).
   - Every draw moves by the same amount, so the shocks and their dependence are the model's own.
   - Only calendar-year averages are matched. The draws' mean statutory inputs sit off the OBR's quarterly figures in 2026-2028 (before the switch), and September 2026 CPI is simulated from August's rather than fixed at the published inputs.
   - Entropy tilting to the same means, the earlier approach, keeps about 1,000 effective draws of 50,000. A drift held constant within each year oscillates from year to year and puts spurious reversals into the statutory measures.
3. **Choice of calibration.** Tilting further to history's gap variance and lead-switch rate (`ts_methods.tilt_moments`) was tested in a chronological expected-value backtest over 12 OBR forecasts, and in a past-years check (a model fitted before 2011, scored on the plan started in 2012).
   - The shift alone had a bias within its standard error with April 2022 as in law, and about one standard error with April 2022 as published. The OBR point forecast had the largest bias under both.
   - The dynamics tilt made the bias larger and put the realised 2012-start gap at its 93rd percentile, against the 55th for the untilted model. The tilts are reported as sensitivities, reweighting the same runs.
4. **Sample.**
   - Draws on which the two rules pay the same every year save exactly nothing. They form their own stratum, and one is run to confirm it.
   - The rest are split into 10 strata of equal probability on the 2039-40 weekly gap. 200 paths are allocated by Neyman allocation (at least 2 a stratum) and drawn with probability proportional to weight.
   - Each is a full run of both rules. Microcosm runs the first 40 of them, paired.
5. **Estimator.** Σ_h W_h ȳ_h with standard error sqrt(Σ_h W_h² s_h² / n_h). The reweighted sensitivities and the Microcosm subsample rest on few effective runs in some strata, so their ± figures are approximate; the file reports each sensitivity's effective runs. Tests check that it is unbiased and that its interval covers about 95% of the time on synthetic cases (`tests/test_expected_value.py`). They also check that the committed file's estimates recompute from its per-path records (`tests/test_results.py`).

## Few paths, one pensioner, past years

- **Paths (`trajectories.py`).** The central path, one random draw, and the draws nearest the middle and the 90th percentile of the 2039-40 gap, each a full run.
- **Example pensioners (`households.py`).** Each path also runs example pensioners through PolicyEngine UK as households.
  - Each gets the full flat rate and claims everything it is entitled to; the renters are existing Housing Benefit claimants, which policyengine-uk requires.
  - Private pensions, rents and council tax grow with the path's CPI.
  - A test checks that each example's change in net income equals its State Pension change plus the changes in Pension Credit, Housing Benefit, council tax reduction and Winter Fuel Payment (means-tested above an income threshold, so a lower pension can bring a pensioner back under it), less the change in income tax.
- **Past years.** The rule replayed on the published inputs from each April since 2012, with full runs for the survey years 2024-25 to 2026-27.

## Datasets and DWP

`dwp.py` reads DWP's 2026-27 spending and caseloads (Spring Forecast 2026, Great Britain) and its uprating analysis. DWP costs the plan at £15bn in 2039-40, nominal, on one path through Pensim3, a dynamic population model, for Great Britain.

The survey here is not aged. Enhanced FRS ages are top-coded at 80 and held at their survey values; pension types are held at the survey year, and the State Pension age rises to 67 in 2028-29.

## Model v2 uncertainty pilot: pre-registered rule (C1)

This rule is committed before generating the C1 candidate scores. It is a pilot
adequacy screen, not evidence of an 80% calibrated probability interval. No
PolicyEngine or survey data is used by the pilot.

**Candidates, fixed in advance.** `monthly_var1_boot` is the primary (the current
BIC winner). `monthly_var2_boot` tests the nearby lag-order choice on the same
monthly log changes and seasonal regressors. `annual_boot_gap` uses the existing
AIC-selected annual VAR(1–2) on calendar CPI and OBR-definition earnings, adding
independently resampled, jointly de-meaned, consecutive four-year blocks of
statutory-minus-calendar gaps. Blocks are drawn only from years before the origin;
long paths concatenate independent blocks and truncate the last one. The
statutory bridge is approximate and loses calendar/gap dependence; this is why it
must pass the same held-out screen. `monthly_var1_tcop` and
`monthly_var1_gauss` retain the existing Student-t marginal/t-copula and Gaussian
shock generators. All five match the same OBR calendar means by a common drift
shift for monthly forms, and a deterministic annual mean shift for the annual
form. This compares lag order, aggregation and shock tails without confounding
these with entropy calibration. The earlier tilted Student-t/Gaussian results
remain historical diagnostics, not a justification for excluding these forms.

**Data and origins.** Reuse `ts_backtest`'s complete spring vintages, 2010–2021
(test B, 12 overlapping four-year origins), and its chronological subset with two
fully observed earlier error blocks (test A, 2016–2021, six origins). All five
candidate fits and gap blocks stop at December of the year before each origin,
including test B: the leave-one-out error-pool design is relevant only to the
older forecast-error comparator. Forecast target years are origin+1 through
origin+4. These are latest revised ONS/OBR inputs, not unrevised real-time
vintages; the original model design saw the full sample. No forecast outturn is
used for mean calibration. Score twice, on published September CPI/May–July AWE,
and with determination-year 2021 earnings set equal to CPI (the legally
suspended April 2022 leg). Apply the same suspension to forecast draws when
scoring that legal regime; otherwise one compares different policy rules.

**Scores and sign.** Every origin reports (lower is better): mean CRPS of the
four earnings-minus-CPI gaps in percentage points; CRPS of the lead-switch count
(ties retain the previous lead); CRPS of the fraction of years with earnings
strictly below 2.5%; joint eight-component energy score and order-0.5 variogram
score (all 28 pairs). Also report forecast-minus-realised bias of each statistic,
and of the terminal plan/triple-lock level gap, with **positive bias meaning
an overprediction**. Coverage is checked both for per-year earnings-minus-CPI
gaps and for the terminal four-uprating plan/triple-lock gap, using central 80%
bands. The terminal policy gap uses the repo's unrounded backtest arithmetic;
future engine specs retain published-input rounding. Floor frequency here is
earnings below 2.5%, distinct from the older both-inputs-below-floor diagnostic.

For every mean report the independent-origin SE and Newey–West SE (Bartlett
weights, lag 3, finite-sample n/(n−1) correction). The latter acknowledges
shared target years but remains imprecise with 6/12 origins; neither is a reliable
confidence interval. Retain the per-origin rows so overlapping windows are
visible. Coverage Wilson bands are descriptive independent-origin bands only,
not a remedy for dependence.

**Fixed adequacy screen.** A form must meet every condition under **both** April
2022 treatments, in **both** A and B:

- Annual gap coverage and terminal policy-gap coverage each lie in [0.50, 1.00].
  In addition, the terminal coverage's descriptive 95% Wilson band must contain
  0.80. This broad pilot calibration band still rejects severe undercoverage.
- Absolute mean forecast-minus-realised biases are at most 1.5 percentage points
  for the earnings-minus-CPI gap, 1 switch per four-year path, and 0.25 for the
  earnings-below-floor fraction.
- Each of the five proper scores above is no more than 1.25 times the primary's
  score for that test and treatment. A zero reference permits only a zero score.
  This prevents accepting coverage by arbitrarily inflating dispersion.
- In an **uncalibrated**, pre-2011 fit simulating determination years 2011–2025,
  the realised terminal policy gap is in the [5th, 95th] percentile, under each
  treatment. No 15-year OBR forecast exists at that origin; using realised
  calendar means would leak held-out information. Report the past-years check
  separately from the forecast-conditioned backtests.
- Paths and all scores must be finite; missing origins or failed fits fail the
  screen, rather than silently dropping difficult cases.

**Selection fixed in advance.** Keep VAR(1) bootstrap primary if it passes.
Otherwise choose the passing form with the lowest geometric mean of the five
score ratios to VAR(1), over both tests and treatments (ties broken by the
candidate order above). If none passes, say that no uncertainty model is
adequate under this screen and authorize no full fiscal runs. Do not relax the
screen after seeing the scores. The across-form/mean-path spread is a **scenario
envelope**, never a probability interval, and forms are never averaged.

**Rebuild handoff.** Each passing form gets its own 50,000 equally weighted
draws, ten strata on its own 2039–40 weekly pension gap, and 160 Neyman-allocated
sample slots (at least two per nonzero stratum), plus an identical-rates check
when present. Allocation uses rule-gap spread as a proxy, not observed fiscal
variance. Report its mean triple-lock premium over statutory earnings for April
2034–2039 beside the OBR fiscal-input comparator (0.557 points from the committed
unrounded determinants, rather than the rounded 0.6-point note). Save the draw
arrays, allocation, sample multiplicities and runnable engine specs.

The **original** primary also gets two diagnostic mean-path specs: earnings
±0.5 percentage points in calendar targets from 2031 onward, simulated using
exactly the same seed, shock stream and sampled draw indices. Monthly drift may
smooth the statutory response across the boundary; do not add 0.5 points directly
to statutory inputs. These paired specs get full runs only if the original
primary passes. Estimate each variant-minus-baseline from within-stratum paired
outputs, retaining baseline-zero strata if a variant ceases to be zero there.

For every fiscal output and year, including 2034–35 and 2039–40, publish the
mean and ±1.96 total Monte Carlo SE, with separate variance components:

- path sampling: Σ_h W_h² s_h²/n_h;
- first phase: Σ_h W_h [s_h² + (m_h−m)²]/N_draws (including the known-zero
  stratum in the between-stratum term);
- model/mean-path uncertainty: the labelled scenario envelope and paired
  differences, kept separate from either Monte Carlo component.

The first-phase formula is for independent first-phase draws and plug-in stratum
moments; it is approximate for reweighted, estimated calibrations. Dynamics
reweightings with fewer than 100 effective full runs will retain their ± and
effective-run count but be **excluded from any quoted range**. This choice avoids
funding extra full runs for tilts that already worsened the calibration backtest;
no dynamics tilt is promoted to an adequate model by this exclusion rule.
