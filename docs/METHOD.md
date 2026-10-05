# Method

Every fiscal and household figure is a full PolicyEngine UK run (policyengine 5.3.0, policyengine-uk 2.90.2) on the certified Enhanced FRS 2024-25, with Microcosm (`populace_uk_2023`) as a dataset sensitivity. Nothing is scaled or interpolated from another run. The code is the reference; this file points to it.

The committed headline results predate the static ageing described below and have not been rebuilt on this branch. The published pipeline and ordinary forecast paths retain the legacy demographic treatment by default. Ageing is opt-in through the path's `demography` setting until validation and part C explicitly enable the combined treatment. The ageing pilot uses the current 2.90.2 engine until part A's certified model-v2 bundle is available; it tests the method and does not establish the upgraded model's absolute spending level.

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
- the Pension Credit guarantee follows the path's earnings;
- opt-in demographic pins read back correctly, person and benefit-unit weights equal their household weights, and raked treatments hit their anchored ONS growth targets to 1e-6 relative in every year.

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. April 2027's benefit uprating is the model's own calendar-2026 CPI (2.3%) on every path, not September 2026 CPI.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. A pension cut can make a household eligible for Pension Credit guarantee credit, which in policyengine-uk passports it to its full rent in Housing Benefit; one heavily weighted record does this on some paths, moving the net figure by billions of pounds. Each run records how much the single record with the largest effect contributes in every year, and its share of the change; FRS records are licensed data, so the published file never gives a record's identifier, weight or amounts.

**Council tax reduction for Pension Credit recipients.** In England's pensioner scheme, policyengine-uk tapers council tax reduction on income after tax, does not count Pension Credit, and does not disregard the income of guarantee credit recipients as SI 2012/2885 (Schedule 1, paragraph 13) requires. Their council tax reduction therefore rises as the State Pension falls, when it should not change. In step 4 this makes the example pensioners on Pension Credit come out slightly ahead rather than even. In the survey runs the whole council tax reduction offset is small.

**The State Pension amounts.** The flat rates are set from each rule applied to the path's statutory inputs.

**Inputs held the same under both rules** (`engine.demographic_inputs`, `demography.py`, `cohorts.py`, `config.py`):

- **Represented age and birthday.** Survey records at exactly age 80 are assigned one represented age from 80 through 105, where 105 means 105+. Within sex, a deterministic hash orders records and weighted midpoints assign calibration-year ONS single-age shares. The weighted 80+ total is preserved; each single-age allocation differs from its target by at most the largest record weight for that sex. Other ages remain unchanged. The same represented ages are used in all four demographic treatments and are set as the model's `age` input. A within-year birthday draw follows the 2.118.0 hash and weighted stratification and is pinned as `months_since_last_birthday` when that variable exists. Both are fixed before reweighting.
- **Household weights.** The `reweight` and combined `both` treatments apply bounded minimum-relative-entropy calibration to household weights. Every person and benefit unit inherits its household's weight; model weight inputs are pinned and checked where present. Sex-specific cells are five-year age bands 0–59, single ages 60–79, 80–84, 85–89 and 90+. Weight ratios are bounded between 0.2 and 5 relative to anchor-year weights; an infeasible or unconverged target fails the run rather than relaxing the bounds. The `frozen` and `types` treatments retain the dataset's native weights for each year.
- **Pension type.** In `types` and `both`, a record represents a contemporaneous person of its fixed age in each fiscal year. Its synthetic birth date is inferred at 6 October of that year from the represented age and fixed birthday draw. Eligible men born before 6 April 1951 and eligible women born before 6 April 1953 have type `BASIC`; later births have type `NEW`, including the cutoff day itself. Those below the model's State Pension age have type `NONE`. This replaces successive cohorts rather than ageing surviving individuals. The `frozen` and `reweight` treatments retain the survey-year type, subject to the same pension-age eligibility gate. Every policy run reads the pinned types back each year and fails on a mismatch.
- **Additional State Pension and protected payments.** For each selected contemporaneous type in `types` and `both`, the data-year reported State Pension is repartitioned against that type's data-year flat-rate ceiling: its basic or new component is the smaller of the reported amount and ceiling, and the nonnegative excess is additional pension. Thus basic + new + additional equals reported pension to the penny for an eligible data-year record. On a `NEW` record, the excess represents protected payments, including inherited amounts already reported; contribution histories and new protected entitlements are not simulated. The excess follows September CPI from the data year, never a negative uprating, and is zero below pensionable age. In `frozen` and `reweight`, the original data-year additional amount is retained on the same CPI basis. Each path uses exactly the same additional-pension input under the triple lock, plan and baseline; only its CPI path affects uprating.
- **State Pension age.** Eligibility is calculated by the installed model after represented ages and birthday inputs are pinned. The current 2.90.2 engine retains its existing override to 67 from 2028–29 because its parameters stop at 66. The upgraded bundle's cohort-specific timetable is part A's port, so the current-engine pilot cannot validate that timetable's population effect.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk uprates it by CPI.

**Calibration anchor and population source.** The source is the public ONS 2024-based UK principal projection, mid-years 2024–2041; the [population-input notes](ONS_PROJECTION.md) document its download and SHA-256 provenance. Fiscal-year population is 75% of mid-year *y* plus 25% of mid-year *y+1*. The target for each cell is its anchor-year survey margin multiplied by ONS growth from that fiscal year, not the raw ONS population level. Targets therefore equal base margins in the anchor year and leave the selected anchor weights unchanged. Benefit-calibration preservation also requires verified calibrated inputs and a controlled comparison of the other model inputs.

The demographic API requires an explicit anchor or verified dataset `calibration_year` metadata and fails if both are absent. The fresh pilot explicitly anchors **2025**, the calibration year declared by the [exact data-release source](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57). The [bundle/source audit](CALIBRATION_ANCHOR.md) maps that source version to the certified Enhanced FRS and explains the remaining artifact qualification: its private build manifest is gated, and runtime-native 2025 weights differ from the builder's restored calibrated weights. This pilot preserves runtime-native 2025 weights mechanically; it does not establish that Housing Benefit or Pension Credit calibration is preserved. Represented ages and cohort retyping can change awards even when weights are unchanged.

The raked treatments replace other years' native weights with weights derived from this one anchor. The inspected 2.90.2 runtime generates later native weights by population uprating rather than annual recalibration. Part C must obtain the certified calibrated-period inputs, verify the runtime materialization of incomes and weights, and measure the effects of the demographic changes on the calibrated benefit baseline.

**Data-year identity gate.** The pilot's aggregate audit found 40 current dataset records with positive reported State Pension below the installed model's State Pension age. Payable components cannot both reproduce a positive reported amount and be zero with type `NONE`. The identity passes for eligible data-year records; the full gate remains pending for these ineligible reporters. Part C must report the discrepancy and resolve verified survey misreporting or pension-age model defects through the appropriate data/model build. It must not create payable pension below pensionable age to force the accounting identity.

**Private demographic cache.** Dataset-driven ages, birthday draws, cell targets and weights are cached under `.cache/demography`, using input-array, projection, source-code, model-version and treatment fingerprints. The cache excludes the policy rule and CPI path. Cache directories/files use private permissions; no record ids, weights or amounts enter public validation results. Additional-pension uprating is calculated separately for each CPI path.

**Scope and programme limits.** The [rule audit](AGEING_RULE_AUDIT.md) reads the relevant 2.90.2 and 2.118.0 code. It finds no further implemented monetary age band between 80 and 105 for the inspected programmes, but pension cohort eligibility and eldest-member ranking remain dependencies. Supplied head and relationship flags are retained; inferred heads or claimant/partner status can change when top-coded age ties are resolved. Neither inspected release models Scotland's Pension Age Winter Heating Payment or an explicit basic-pension age-80 addition. Reported additions can enter the residual; this does not implement the statutory addition as a separate entitlement. The pilot must preserve these limits when interpreting programme spending.

Historical replay, the legacy coverage helper and forecast paths with absent or `legacy` demography settings continue to use `engine.pinned_inputs`, retaining survey ages, native weights, survey-year types and the original additional-pension treatment. The new treatment applies to explicitly requested forecast paths and the dedicated ageing pilot. Existing historical and legacy coverage outputs are not regenerated ageing validation.

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components;
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- for legacy runs, the private single-household diagnostic; opted-in demographic runs suppress all record diagnostics before returning results.

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

The committed headline results and default published pipeline hold the original top-coded ages and survey-year types. Explicit ageing treatments vary household weights and contemporaneous pension cohorts as described above. Amounts for later retirees still come from survey records representing the same age; deaths, migration and contribution histories are not simulated. Pensioners abroad are outside the household survey.

## Four-way ageing pilot (`ageing_validation.py`)

Inspect the planned jobs without loading private data:

```sh
python scripts/validate_ageing.py --workers 1 --calibration-year 2025 --plan
```

Run the complete pilot on the certified Enhanced FRS:

```sh
python scripts/validate_ageing.py --workers 4 --persistent-workers --calibration-year 2025 -o .cache/ageing_validation.json
```

The runner records host CPU and available RAM before starting full model jobs. One worker is the default; the CLI permits at most four Enhanced FRS workers and starts no Microcosm workers. It requires an explicit calibration year; 2025 above is the source release's calibration year, used here with the runtime-native weights and qualified as described above. The fresh pilot uses the same API with eight Enhanced FRS slots after separate host checks, recorded in its aggregate execution provenance. It runs the central path and the exact committed 40 Microcosm-paired expected-value draw selections, all on Enhanced FRS, preserving stratum probabilities and repeated selections. Each path runs `frozen`, `reweight`, `types` and `both` under both pension rules with the same baseline demographic pins. These four treatments share represented ages and birthdays. A fifth `legacy` control retains original survey inputs and measures the shared changes as `frozen − legacy` (`common_input_effect`). On 2.90.2, both controls already use the same integer-age pension eligibility gate and zero additional pension below that age; the contrast measures represented ages and any head/claimant effects. On newer bundles, birthday inputs can also change eligibility. The complete plan has 205 treatment jobs: five for the central path and five for each of the 40 paired selections. The core four-way interaction is `both − reweight − types + frozen`, computed within each path before stratified averaging. An optional `--central-only` run is explicitly preliminary and does not satisfy the complete design.

The output contains aggregate GB fiscal totals, gross/net saving, four-way effects and their interaction, the separate legacy comparison, path-sampling standard errors, and pension recipients and basic/new spending by age, country and region. Coverage includes every year from the data year through 2039. Every nonzero contributor cell requires at least ten records; zero-contributor cells can report zero. If any positive age or geography cell needs suppression, its entire linked age family or country/region family is withheld across all paths, treatments, years and policies. This prevents recovery through changing complements in linked tables. No survey ids, weights or amounts are exported. All fiscal values come from full PolicyEngine calculations using pinned inputs. Optional persistent workers construct fresh simulations for every job, record private stage timings/RSS, and recycle after 20 jobs. `--verify-workers` compares a real isolated central job with a persistent central job after a different draw.

The Spring 2026 DWP workbook covers GB plus overseas, excluding Northern Ireland. Only its all-type State Pension spending and caseload have separately identifiable overseas amounts; subtracting those provides matched GB totals through 2030–31. Published basic/new amounts and recipients are shown separately as **GB plus overseas context**, not matched GB benchmarks. This workbook supplies no State Pension forecast breakdown by age or country/region, so those benchmark comparisons are labelled unavailable. Comparisons after 2030–31 are also unavailable until a published long-term source is verified; no benchmark is extrapolated or allocated from an overseas share.

The full four-way fiscal validation and the ineligible-reporter identity gate are pending. Changes in the State Pension bill, gross saving and means-tested offsets remain hypotheses until these paired runs and the calibrated baseline checks are complete. Part C needs the certified upgraded model/data bundle with an explicit calibration year, a version bridge for State Pension, Pension Credit and Housing Benefit, resolution/reporting of verified below-pension-age reporters, the complete paired pilot including its legacy control, and verified sources for any additional benchmark comparisons before the one full rebuild and an explicit change to the published pipeline's demographic treatment.
