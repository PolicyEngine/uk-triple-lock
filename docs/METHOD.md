# Method

Every fiscal and household figure is a full PolicyEngine UK run (policyengine-uk 2.120.0) on the Enhanced FRS 2024-25 (policyengine-uk-data 1.56.16), with the population aged statically (below) and Microcosm (`populace_uk_2023`) as a dataset sensitivity. Nothing is scaled or interpolated from another run. The code is the reference; this file points to it.

The committed results (`data/results.json`) were built before model-v2, on policyengine-uk 2.90.2 with the survey population held, and are not rebuilt on this branch: [REBUILD.md](REBUILD.md) is the runbook for the one rebuild, and what it waits for.

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

**Entering the model.** In a Scenario applied before the data load:
- the calendar growth replaces `gov.economic_assumptions.yoy_growth.obr` (RPI and CPIH move by the same amount as CPI);
- the statutory inputs replace the model's own (`statutory_uprating_inputs`: September CPI and May–July AWE, each at its observation date), from which policyengine-uk builds its triple lock. Without them it would use the published figures and then calendar growth plus the OBR's forecast gap.

Passed as a reform, the same changes do nothing, because the derived series are built at load time. `model_horizon.py` first extends the private pension uprating, which policyengine-uk still stops at 2034; every other derived series now reaches 2039-40 by itself (the OBR series run to 2073). A one-off check when porting found the processed parameters for the central path identical with and without the old extensions on every date to 2039; a test checks that every derived series follows a path to 2039-40.

**What each run checks, in every year**, failing if any misses:
- CPI-uprated benefit rates follow the path's CPI the year before;
- CPI-indexed thresholds follow it the same year;
- employment income follows the path's earnings;
- the model's statutory inputs are the path's, its own triple lock is the larger of them and 2.5% (each input to 0.1 point as the model rounds it: halves away from zero), and its new State Pension compounds that;
- every flat-rate pension scales exactly by the ratio of the two rules' amounts;
- employer NI incidence is zero;
- the Pension Credit guarantee follows the path's earnings;
- the variables the net saving is decomposed into explain the model's own `gov_balance`, and its level and change agree with the independently calculated household-income bridge (below);
- the population treatment's inputs read back from the model (ages, birthdays, head flags, weights), person and benefit-unit weights are their household's, and every raked year hits its ONS growth targets to 1e-6 relative;
- the additional State Pension is the pinned one under every policy, and in the data year basic + new + additional State Pension equals the reported State Pension the run counts, for every person, to £0.01 (below).

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. April 2027's benefit uprating is the model's own calendar-2026 CPI (2.3%) on every path, not September 2026 CPI.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. policyengine-uk takes up either only for a family reporting it unless no family in the simulation reports any of seven benefits (`claims_all_entitled_benefits`), which survey data always do; pension-age families may make new Housing Benefit claims in law, and in policyengine-uk from 2.102.5, but in the survey runs only those already claiming do. Pension Credit take-up is the dataset's own draw (`would_claim_pc`). A pension cut can make a household eligible for Pension Credit guarantee credit, which in policyengine-uk passports it to its full rent in Housing Benefit; one heavily weighted record does this on some paths, moving the net figure by billions of pounds. A `legacy` run records how much the single record with the largest effect contributes in every year, and its share of the change. An ageing run does not, because its weights are derived from the survey's: it records the ten records with the largest effect together (`concentration_top10_by_year`, an aggregate of ten records), and never both, which would give a nine-record total by subtraction. FRS records are licensed data, so the published file never gives a record's identifier, weight or amounts.

**Council tax reduction for Pension Credit recipients.** Since policyengine-uk 2.104.2 the pensioner schemes disregard the whole income of a guarantee credit recipient (SI 2012/2885, Schedule 1, paragraph 13, and the Welsh and Scottish equivalents), and use the Pension Credit assessment for a savings-credit-only award, as the law requires. A guarantee credit recipient's council tax reduction no longer moves with the State Pension. A test checks that for the example pensioner on the guarantee under both rules, council tax reduction and Housing Benefit do not move and the change in income is exactly the change in savings credit, which pays 60% of income above its threshold (and which policyengine-uk 2.118.0 and later pay the example once the basic State Pension passes the threshold, where 2.90.2 paid none).

**The State Pension amounts.** The flat rates are set from each rule applied to the path's statutory inputs.

**The population** (`demography.py`, `cohorts.py`; `config.DEMOGRAPHY`). The survey is aged statically (#14 section 3): each record stands for a person of its age in every year, not a survivor aged forward, so a 75-year-old record is a 75-year-old of 2024 in 2024-25 and of 2039 in 2039-40. Every run uses the model-v2 treatment, `both`; a path can name another (`spec["demography"]`), which the four-way design below does:

| Treatment | Ages | Household weights | State Pension type |
|---|---|---|---|
| `legacy` (part A's engine) | survey | the dataset's own | survey year's |
| `frozen` | represented | the dataset's own | survey year's |
| `reweight` | represented | ONS projection after the anchor year | survey year's |
| `types` | represented | the dataset's own | cohort |
| `both` (model-v2) | represented | ONS projection after the anchor year | cohort |
| `total` (control) | represented | ONS total only after the anchor year | survey year's |

- **Represented ages.** Records top-coded at 80 get a represented age from 80 to 105 (105+): within each sex a deterministic hash of the verified dataset content and synthetic ordering key orders them and weighted midpoints take the anchor year's ONS single-age shares, so the weighted 80+ total is unchanged. Other ages are the survey's. If any age in a dataset is above 80 it is not top-coded and every age is kept. Every record also gets a fixed birthday within its year of age (`months_since_last_birthday`), drawn as policyengine-uk draws it, on the data year's weights (upstream's own input), so every record that keeps its survey age keeps policyengine-uk's birthday and type; a run fails if one's data-year type changes. Represented ages use the anchor year's ONS shares and weights. Both are pinned in every year, and anything the model derived from the survey ages before is cleared (`demography._clear_derived`), so the model's own State Pension age (`is_SP_age`, by date of birth) and every reader of it in the engine (the State Pension age band, poverty, the age bands, coverage) see the represented ages. The survey's household and benefit-unit head flags are pinned too, so ties among represented ages cannot move a head.
- **Household weights.** In the anchor year and every year before it the weights are the dataset's own, exactly (`demography.annual_weights`): the rake never moves the calibrated weights and never runs back to the survey year. The anchor is the data build's calibration year, from its source (`datasets.ageing_anchor`: 2025 for the Enhanced FRS, `frs_release.py`; Microcosm has none, so its anchor is 2024-25, the first year the projection covers). After it, household weights are raked (bounded minimum relative entropy, ratios 0.2 to 5 of the anchor year's; a convex problem with one solution, which `demography.rake_households` finds by least squares on the calibration residual (the dual's gradient) and, where that stalls on a bound, by Newton or gradient steps on the dual) so that every sex and age cell (five-year bands to 59, single ages 60 to 79, 80-84, 85-89, 90+) grows from its anchor-year survey count as the ONS 2024-based UK principal projection's does ([ONS_PROJECTION.md](ONS_PROJECTION.md); fiscal year = 75% of mid-year *y* + 25% of *y*+1). Targets are survey counts times ONS growth, not ONS levels. Person and benefit-unit weights are their household's. A target the bounds cannot reach fails the run. A property test checks that, for any growth, the raked weights equal the dataset's own through the anchor year.
- **Cohort types.** Basic for men born before 6 April 1951 and women born before 6 April 1953 (State Pension age before 6 April 2016, by the Pensions Act 1995 Schedule 4 timetable: Pensions Act 2014 s.1(2)), new from those dates, none below State Pension age, from the birth date the represented age and birthday give at 6 October of each year. A test checks they equal policyengine-uk's own `state_pension_type` on the same ages and birthday in every year (on 2.120.0; part B's oracle tests passed on 2.118.0 too).

**Inputs held the same under both rules** (`engine.pinned_inputs`):
- **State Pension age.** The model's own: policyengine-uk sets it from each person's date of birth by the Pensions Act 1995 timetable, including the rise from 66 to 67 for people born from 6 April 1960 (#1899), and the engine reads it through `is_SP_age` and `state_pension_age`. Ages are held, so a record's date of birth moves a year later each year: 66-year-olds are partly over State Pension age in 2026-27 and 2027-28 and below it from 2028-29. Each run records the youngest age with anyone over it and the youngest from which everyone is (`fixed_inputs.state_pension_age`).
- **Pension type**, by the treatment's rule (above). Each run reads the types back from the model in every year, fails if anyone's differs, and records the counts (`held_pension_type_records`, `held_pension_type_people`).
- **The State Pension accounting, one rule under every treatment.** The reported State Pension counts only for people over State Pension age in the data year: none is payable before it (Pensions Act 2014 s.2(1)(a) and s.4(1)(a); SSCBA 1992 s.44(1); a survivor's inherited pension is their own from it, Pensions Act 2014 s.7(1)(a) and s.9(1)(a)). In the Enhanced FRS 40 records report State Pension below it, most of them within a year of it; two-fifths of them also report contributory ESA, which nobody over pensionable age can get, and two-thirds report earnings. They are reporting errors, and the model already paid them none; the data year's `state_pension_reported` is pinned without them (`demography.payable_reported`), and each run records how many there are and what they report (`state_pension_accounting`). In each year the counted report is split by that year's type at the type's data-year flat rate (`demography.pension_components`), as policyengine-uk's own formulas split it: the flat-rate part, which policyengine-uk scales by the flat rate, and the rest, the additional State Pension (SERPS, S2P and, on the new State Pension, protected payments, inherited amounts included), which the engine pins at its data-year amount grown by September CPI (published to April 2026, the path's after; never cut), for people over State Pension age that year. policyengine-uk 2.120.0 still scales it by the flat rates' ratio (its issue #1941): in a run that cuts the flat rates by 5%, its total would fall by 5%. Splitting the additional pension by each year's type is what keeps cohort types from paying anything twice: split by the survey year's type, a record moved from the basic to the new State Pension would be paid the band between the two flat rates inside its new State Pension and again as additional pension (part A measured £14.2bn in 2034-35 and £16.0bn in 2039-40). Every run checks, from the model, that in the data year basic + new + additional equals the counted report for every person (to £0.01) and nobody below State Pension age is paid, and that the additional pension is the pinned one under both rules in every year; tests check the same on a synthetic survey under every treatment, and that a 5% cut in the flat rates moves only the basic and new State Pension.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk 2.120.0 still uprates it by CPI.

**Re-typed pension level.** The default is `retyped_level="kept"`: a survey BASIC record assigned NEW in a later year retains its reported amount, split at that year's type's data-year cap. The `full_new` sensitivity raises only that re-typed record's flat-rate part to the full new State Pension rate under each policy. Additional pension follows the same CPI pin; the data year is untouched and its components still sum to the counted report to £0.01. This bounds the flat-rate part, not the total transitional entitlement or an estimated confidence interval.

The revised [Pensions Act 2014 s.4](https://www.legislation.gov.uk/ukpga/2014/19/section/4) sets entitlement; [s.5](https://www.legislation.gov.uk/ukpga/2014/19/section/5) and [Schedule 1 paragraphs 2–7](https://www.legislation.gov.uk/ukpga/2014/19/schedule/1) determine the rate. The pre-2016 foundation amount is the higher of the old-system and new-system calculations, with contracting-out deductions and revaluation, then post-2016 qualifying years are added subject to the cap/protection. [State Pension Regulations 2015 reg.13](https://www.legislation.gov.uk/uksi/2015/173/regulation/13) specifies ten qualifying years for transitional entitlement. These current revised texts were read on 5 October 2026. Inspection of the verified Enhanced FRS 1.56.16 HDF5 schema finds total `state_pension_reported` and private pension income, but no pre/post-2016 qualifying years, separate additional-pension history or contracting-out deduction. Today's reported total cannot reconstruct the Schedule 1 calculation. The law therefore does not settle a counterfactual amount for this static representation: the existing treatment stays the default and the full-rate treatment is a labelled sensitivity, requiring full model runs.

**Total-only control.** `total` uses one incidence margin: the number of persons in each household. Its target is the anchor survey population times the ONS total-population growth factor, with the same bounds, represented ages, fixed birthdays and survey-year types as `frozen`/`reweight`. `total − frozen` measures this population-total replacement through paired full model runs. `reweight − total` compares the age/sex cell-growth control with the total-only control; because the anchor survey's age/sex mix differs from ONS's, the sum of the cell-growth targets can imply a different overall total. That contrast therefore includes any resulting total difference. The part E pilot records `model_population_people_by_year` to expose it rather than claim a fixed-total age-structure comparison. Through the anchor every treatment retains the native weights.

**The calibration year's level.** The Enhanced FRS builder calibrates its weights in 2025 and saves them to 2024 with its own weight index (2024: 1.027, 2025: 1.039); policyengine-uk uprates them back to 2025 by its population growth (0.72%). In a simulation the 2025 weights are therefore the calibrated ones times 0.9956: relative weights exactly the calibrated ones, every 2025 total 0.44% low ([policyengine-uk-data#538](https://github.com/PolicyEngine/policyengine-uk-data/issues/538)). Static ageing keeps the simulation's own 2025 weights, so it neither adds to the gap nor closes it; the fix belongs to the data build or the model.

**Private cache.** The population (represented ages, birthdays, the weights and the State Pension age mask and types of every year) is computed once per dataset, treatment, anchor, set of years and model (`demography.eligibility_fingerprint`: the installed policyengine-uk and the files its State Pension age and type come from) and cached under `.cache/demography`, owner-only; every path job shares one entry, and the coverage and history jobs, with other years, have their own. A run reads the model's own `is_SP_age` back against the cached mask in every year and fails if they differ, so a change to the model's State Pension age cannot reuse stale types. Nothing that depends on a path is cached: the additional pension follows each path's September CPI. No record id, weight or amount leaves the cache; an ageing run returns no single-record diagnostic, and a failed path, coverage or history job keeps its error output in an owner-only file in an owner-only worker directory instead of the build log (`jobs.private_inputs`).

**Programme limits.** The new State Pension has no age addition, but the basic State Pension has one, 25p a week at 80 (SSCBA 1992 s.79 and Sch 4 Pt III para 8), which policyengine-uk does not model ([policyengine-uk#2139](https://github.com/PolicyEngine/policyengine-uk/issues/2139)): a reported one is in the additional pension. Scotland's Pension Age Winter Heating Payment is modelled (`pawhp`, in `other_spending`), but from winter 2025 policyengine-uk pays £100 a household without a qualifying benefit where the regulations (SSI 2024/351 reg 10, as substituted by SSI 2025/282) pay £203.40 a person living alone, £305.10 at 80, and shared rates ([policyengine-uk#2138](https://github.com/PolicyEngine/policyengine-uk/issues/2138)). (Part B's rule audit, on 2.90.2 and 2.118.0, said neither was modelled; `pawhp` has been since December 2024.) Later retirees' amounts come from today's records of the same age; deaths, migration and contribution histories are not simulated, and pensioners abroad are outside the survey. A dynamic projection is the longer-term route (PolicyEngine/microcosm-dynamics#501).

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components, for the UK and for Great Britain (households in England, Scotland and Wales, as DWP's figures are; neither dataset has a household of unknown country);
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- the single largest record's contribution (`legacy` runs), or the ten largest records' together (ageing runs);
- the population treatment and its checks (`fixed_inputs`: `demography`, `population`, `ageing`, `state_pension_accounting`).

**Gross to net.** `gov_balance` is policyengine-uk's `gov_tax` less its `gov_spending`, each the household sum of its own list of variables (`GOV_TAX_VARIABLES`, `GOV_SPENDING_VARIABLES`). Each run totals every variable on the two lists (`engine.fiscal_variables`, which mirrors their formulas' council-tax-abolition conditional and splits State Pension into basic, additional and new), records the change in each, and groups them: the State Pension flat rate, additional State Pension, Pension Credit, Housing Benefit, Universal Credit, council tax reduction, Winter Fuel Payment, income tax, other spending and other tax. The model computes `gov_balance` household by household in float32, which leaves its total a few £1,000 off the float64 sum of the same variables (3.2e-6 £bn on the Enhanced FRS in 2026-27) and a change in it about 1e-6 £bn off. The run therefore takes the net saving as that float64 sum, so the components add up to it by construction (the recorded `decomposition_residual` is float64 rounding, about 1e-13 £bn). The test that the lists explain the model is against the model's own float32 `gov_balance`, recorded beside it: its level to 1e-4 £bn (£0.1m) and its change between the rules to 1e-5 £bn (£0.01m). A variable missing from the lists, or extra, fails the run if its total is over £0.1m a year or either rule moves it by over £0.01m; in the pilot runs the change agreed to 3e-6 £bn or better.

The component sum is an arithmetic reconciliation, not independent validation. A separate check uses `engine.household_income_bridge`: government balance plus household net income must equal market income less pension contributions, adjusted for items counted in only one of the government's and household-income lists. The bridge reads the household tax/benefit lists separately and calculates the unmatched terms directly, including council-tax abolition and optional broad benefit uprating. The level must agree to £0.1m and the change between policies to £0.01m. The result records `household_income_identity_residual`. A synthetic-model mutation test changes household net income while leaving fiscal components intact and confirms this identity fails (`tests/test_ageing_model.py`).

**Jobs.** Ordinary path, coverage and history jobs run in separate processes and are cached under a hash of their arguments, what the engine's code computes (each file's syntax tree without comments or docstrings) and the package versions. The results file's provenance records the files' raw hashes. The part E pilot's optional `treatment_paths` job batches Enhanced FRS treatments of one macro path in one process: it loads a pristine same-path setup once, then independently copies parameters, supplied inputs and input provenance for every treatment and policy. Computed caches are cleared, every treatment applies its own population/pension inputs, and all horizon calculations retain their original order. `fiscal_output_years` selects returned fields only after those calculations. No fiscal output is shared, scaled or interpolated. Ordinary builds and Microcosm retain fresh loads. Synthetic fresh-versus-cloned equality and input-isolation tests cover this optimization; its real-data validation is recorded in [MODEL_V2_PILOT.md](MODEL_V2_PILOT.md).

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
   - The dynamics tilt made the bias larger and put the realised 2012-start gap at its 93rd percentile, against the 56th for the untilted model. The tilts are reported as sensitivities, reweighting the same runs.
4. **Historical sample, retained for reproducing the committed bundle.**
   - Draws on which the two rules pay the same every year save exactly nothing. They form their own stratum, and one is run to confirm it.
   - The rest are split into 10 strata of equal probability on the 2039-40 weekly gap. 200 paths are allocated by Neyman allocation (at least 2 a stratum) and drawn with probability proportional to weight.
   - Each is a full run of both rules. A 40-slot stratified subsample is paired on Microcosm.
   - Executing builds now use the selected form's **160-slot C1 handoff**, described below, rather than this historical 200-slot diagnostic route. They deduplicate replacement draws for full engine runs, add an identical-rates check, and preserve every slot's multiplicity in the estimator. The committed original-primary design has 160 distinct sampled indices and one extra check, hence 161 unique runs. Its 40-slot Microcosm subsample takes at least two slots in every sampled stratum, including stratum zero. Updated inputs and other forms can have fewer distinct runs than slots.
5. **Estimator.** Σ_h W_h ȳ_h. Historical committed results use only sqrt(Σ_h W_h² s_h² / n_h); new estimates add first-phase variance and report both components separately, as specified in the C1 rule below. The reweighted sensitivities and the Microcosm subsample rest on few effective runs in some strata, so their ± figures are approximate; the file reports each sensitivity's effective runs. Tests check that it is unbiased and that its interval covers about 95% of the time on synthetic cases (`tests/test_expected_value.py`). They also check that the committed file's estimates recompute from its per-path records (`tests/test_results.py`).

For reweighted calibrations, the first-phase term uses the target stratum
probabilities and ratio-weighted within-stratum outcome moments, divided by
the Kish effective count of all macro draws, N_eff = (Σw)²/Σw². Path-sampling
variance keeps the importance pseudo-outcomes r·y under the original design;
using their variance again with the effective count would count unequal weights
twice. This is a plug-in approximation conditional on the fitted weights and
does not account fully for dependence between fitted weights and outcomes.
Equal weights recover the ordinary first-phase formula. Synthetic Monte Carlo
and Hypothesis checks exercise both cases (`tests/test_sampling_precision.py`).
The historical aggregate bundle lacks exact target stratum masses, so its
diagnostic recalculation estimates those masses from sampled macro weight ratios
and explicitly records that approximation; its means and path-sampling errors
are unchanged.

## Few paths, one pensioner, past years

- **Paths (`trajectories.py`).** The central path, one random draw, and the draws nearest the middle and the 90th percentile of the 2039-40 gap, each a full run.
- **Example pensioners (`households.py`).** Each path also runs example pensioners through PolicyEngine UK as households.
  - Each gets the full flat rate and claims everything it is entitled to. None reports a benefit, so policyengine-uk takes each to claim in full.
  - The renters make new Housing Benefit claims, as the law allows once every adult in the family is over State Pension age (SI 2014/1230 reg 6A(4)). policyengine-uk does this from 2.102.5. Before that, it paid Housing Benefit only to a family already reporting it, so the examples carried a reported claim, a claim-everything flag and no Universal Credit claim. A test checks that dropping those inputs changes nothing for pension-age families.
  - Private pensions, rents and council tax grow with the path's CPI.
  - A test checks that each example's change in net income equals its State Pension change plus the changes in Pension Credit, Housing Benefit, council tax reduction and Winter Fuel Payment (means-tested above an income threshold, so a lower pension can bring a pensioner back under it), less the change in income tax.
- **Past years.** The rule replayed on the published inputs from each April since 2012, with full runs for the survey years 2024-25 to 2026-27.

## Scenario runs

A path's spec may carry `specified_rates`, {policy: {April: rate}}: in those years that policy pays the given rate instead of its rule (`rules.rates_matrix`, `engine.spec_specified`). It is the engine's one mechanism for a scenario on the rates themselves; with none, every rate is the rules' own.

- Specified rates are rounded with `rules.round_rate`, like every other rate, and not floored: they are inputs, not a rule.
- Both rules are the triple lock until April 2029, so a specified triple lock before the switch is also what the Burnham plan pays, and the plan anchors its earnings path on the level that gives. A Burnham-plan rate can be specified only from the switch; it replaces the plan's own rule that year, and later years run the rule from the level it leaves.
- `rate_sources` labels a specified year `specified` for that policy; before the switch the plan stays `triple_lock`.

A scenario is one full run of the central path with its specified rates, nothing else changed (`trajectories.SCENARIOS`). Every full build runs every scenario after the paths and writes each to `data/scenarios/NAME.json`, with the main results' provenance and record-level fields redacted, so one rebuild refreshes the results file and the scenarios together; `triple-lock-build --scenario NAME` reruns one alone (`pipeline.scenario`) and leaves the results file alone. Tests recompute its rates from the inputs it records, check that it holds the same fixed inputs as the central run, and fail once any source, input or engine file has changed since the run.

**The OBR wedge (`obr_premium`).** The triple lock pays the 'Triple lock' row of the OBR's long-term economic determinants (March 2026), its value for the fiscal year of the inputs paid the next April, from April 2028. April 2027 is set by published inputs (May-July 2026 AWE), so it is the central path's under both rules, not the OBR's projection. For the fiscal years 2027-28 to 2030-31 the row is 2.5% (paid the Aprils 2028 to 2031, as on the central path); from 2033-34 it is, in the OBR's note, average earnings growth plus 0.6 points (0.56 above the fiscal-year earnings growth the central path uses), phased in over the two years between. The 0.6 points is the OBR's stylised allowance for the years CPI or the floor beat earnings, an average-rate assumption: no CPI and earnings path pays it every year, so the run is a comparison with the OBR's costing convention, not a forecast. Only the triple lock gets the premium. The plan runs its own rule from the switch, on the central path's CPI and earnings, so it gets no credit for the volatility that sets its own floor. Spending is the aged survey bill (static ageing, above), for the UK, where DWP's figures are for Great Britain.

## Datasets and DWP

`dwp.py` reads DWP's spending and caseloads (Spring Forecast 2026, Great Britain) for 2026-27 to 2030-31, where its tables stop, and its uprating analysis. DWP costs the plan at £15bn in 2039-40, nominal, on one path through Pensim3, a dynamic population model, for Great Britain.

**Coverage.** One coverage job per dataset runs the central path under the triple lock, as the central run's triple-lock policy does (the same population treatment), for 2026-27 to 2030-31, 2034-35 and 2039-40. It gives each year's State Pension (by part, recipients and types, and in Great Britain by age, where every cell rests on at least ten records), Pension Credit (guarantee and savings credit, and claims), Housing Benefit and pension-age Housing Benefit (spending and claims), council tax reduction and Universal Credit, for the UK and for Great Britain. The results set Great Britain against DWP, like for like, in every year DWP's tables give. Pension-age Housing Benefit is Housing Benefit paid under the pension-age regulations (`housing_benefit_pension_age_regulations_apply`), nearest DWP's "over Pension Credit qualifying age". 2034-35 and 2039-40 have no DWP figure.

The population here is the path runs': static ageing with represented ages above 80, ONS growth from 2026-27 and cohort pension types. The State Pension age follows the law's timetable by date of birth, so every age of 67 and over is above it from 2028-29. DWP's figures come from its own projection of the population and of contribution records; matched by-type, by-age and post-2030 benchmarks are unavailable (part B's [AGEING_PILOT.md](AGEING_PILOT.md) lists them).

## The model: policyengine-uk 2.120.0, pinned directly (`datasets.py`)

policyengine.py's release bundles certify one policyengine-uk version with one data build. None yet carries the pensioner fixes this analysis needs: 6.2.1 pins policyengine-uk 2.102.3, and its import fails beside 2.118.0 and later, because its data certification finds no release certified for the installed version. So `pyproject.toml` and `requirements-lock.txt` pin policyengine-uk 2.120.0 (and policyengine-core 3.32.16) directly. The engine loads each dataset itself, pinned to a revision and a SHA-256 and hashed before every use, as policyengine.py's managed loader did:

- the Enhanced FRS 2024-25, policyengine-uk-data 1.56.16, built with policyengine-uk 2.89.2, the build policyengine.py 5.3.0 and 6.2.1 certified (for 2.90.2 and 2.102.3);
- policyengine-uk-data 1.57.4 (built with 2.93.0), registered for comparison;
- Microcosm `populace_uk_2023`, the dataset overlay policyengine.py carries.

Both Enhanced FRS releases load and compute on 2.118.0 and 2.120.0, and store the same variables (1.57.4 adds one childcare column). Twenty stored columns are not variables in 2.118.0 (geography codes and build bookkeeping such as `clone_index`), and eleven are variables it would otherwise compute, whose stored values it uses (`state_pension_reported` among them). Every run records the installed model and core versions and the dataset's pin, with `certified: false` and the reason (`provenance.model`). A test checks that the recorded version is the installed policyengine-uk.

**What changed upstream between 2.90.2 and 2.118.0**, as policyengine-uk's changelog records the entries that touch this analysis (77 releases), and whether the engine relied on the old behaviour (from the engine's code):

| Change (policyengine-uk) | Moves | The engine relied on the old behaviour? |
|---|---|---|
| State Pension age by date of birth, with the rise to 67 (#1899, 2.112.0); the scalar age parameters removed | who is over State Pension age in 2026-27 and 2027-28 | Yes: it set 67 from 2028-29 on the removed parameters. Dropped; reads `is_SP_age` |
| Triple lock from September CPI and May–July AWE, with forecast gaps (#1939, 2.109.0); an optional earnings-path guarantee | the model's own flat rates | Yes: its check expected calendar growth. Now sets and checks the statutory inputs; the rules set both rules' flat rates, as before |
| Additional State Pension split by the year's own pension type (#1922, 2.113.3) | additional pension, where types move | No: the engine splits its pin by each year's type the same way, under every treatment |
| Additional State Pension still scaled by the flat rates' ratio (#1941, open) | – | Yes, and still needed: the CPI-linked pin stays |
| Pension Credit guarantee still uprated by CPI | – | Yes, and still needed: the earnings-linked override stays |
| Derived series now run to 2073-74 (lagged CPI and earnings, the triple lock) | – | Yes: `model_horizon` extended them. Now extends only the private pension uprating |
| New Housing Benefit claims at pension age (#1901, 2.102.5) | the example renters | Yes: the examples carried a reported claim. Dropped; in survey runs only families already claiming respond, as before |
| Council tax reduction disregards guarantee credit recipients' income (#1909, 2.104.2) | council tax reduction for Pension Credit recipients | It was a stated limitation; dropped |
| Housing Benefit: LHA cap before the taper (#1926, 2.105.1), earnings disregards (#1908, 2.111.1), savings credit in income (#1945, 2.114.1), the Universal Credit and income-based passports (2.109.7, 2.117.1), LHA rates from the published determinations (2.114.3), joint tenants' shares (2.113.0) | Housing Benefit baseline and offset | No |
| Pension Credit: dataset capital input, a no-op without it (#2018, 2.105.0), the qualifying age by date of birth (#1907, 2.115.0), mixed-age couples (#1940, 2.109.4), carers' income and the severe disability addition (#1938, #1951, #1952), Lifetime ISA capital where a dataset has it (2.103.0) | Pension Credit baseline and offset | No |
| Winter Fuel Payment on pensionable age from 2024-25 (2.115.0); employer NI over State Pension age (2.102.6); Class 4 NI; NICs thresholds frozen to 2030-31 (2.106.1, the lower earnings limit still follows CPI) | small baseline changes | No (the NI lower earnings limit the engine checks is still CPI-indexed) |
| Universal Credit counts State Pension and other income for mixed-age couples (2.104.7, 2.104.1, 2.108.0, 2.113.2) | Universal Credit offset | No |

**From 2.118.0 to 2.120.0** (both released on 5 October 2026; 2.120.0 is the latest), as their changelogs record them. Every Fixed entry is a fix to the law; the Added entries (`date_of_birth`, the date parameters, `is_uc_assessed_claimant`) serve those fixes, and the Changed one (`birth_year`) follows from them. So the pin moved to 2.120.0 without a methodology choice:

| Change (policyengine-uk) | Moves | The engine relied on the old behaviour? |
|---|---|---|
| `date_of_birth` from age and the birthday, and every date-of-birth rule read through one birth instant (2.119.0). For survey data, with no `date_of_birth` input, State Pension age and type come from the same instant as in 2.118.0 | nothing for the engine | No: `cohorts.birth_dates_from_age` matches it (tested), and the upstream guard (`model_horizon.UPSTREAM`) now covers the moved files |
| The Pension Credit mixed-age couple saving by date of birth: the older member born on or before 5 February 1954 (SI 2019/37 art 4); the Universal Credit and Child Tax Credit child limits and the Pension Credit first child addition on 6 April 2017 by date of birth (2.119.0) | Pension Credit for mixed-age couples; child elements | No |
| `birth_year` is the calendar year of the date of birth (2.119.0); no rule reads it any more | nothing | No |
| Universal Credit counts only the claimants' income, not their dependants' (UC Regs 2013 reg 22(1); 2.120.0) | Universal Credit baseline and offset | No |

Part A's version bridge rerun on 2.120.0 is retained as aggregate pilot evidence in [data/pilot/version_bridge.json](../data/pilot/version_bridge.json), with its calculation commit and model/data versions. It is an uncertified-pair pilot, not for quoting; [MODEL_V2_PILOT.md](MODEL_V2_PILOT.md) records the publication-support audit status. policyengine-core 3.32.17 (5 October, uprating and cloned-storage fixes) came out after it and is left for the rebuild's version check ([REBUILD.md](REBUILD.md)).

Still open upstream: #1927 (the Housing Benefit guarantee credit passport keyed on receipt), #1925 (benefit rates at announced amounts), #1913 (pension-age Housing Benefit allowances by cohort), #2019 (Pension Credit earnings disregards), #1941 (the additional State Pension's uprating), #2138 (Scotland's Pension Age Winter Heating Payment from winter 2025) and #2139 (the age addition).

## The four-way ageing design (`ageing_validation.py`)

What represented ages, the ONS reweighting and cohort types each do to the saving, alone and together, on paired full runs (#14 section 3). Every validation job is an ordinary engine job with the path's `demography` set: the central path and the rebuilt expected value's exact 40 Microcosm-paired draw slots, each under `legacy`, `frozen`, `reweight`, `types`, `both` and the `total` population-only control. With forty distinct paired indices, this is 246 path-job labels plus six coverage jobs (252 labels); repeated draw indices reduce the unique path jobs. If the 41 `both` paths are already cached by the build, validation adds 205 path jobs and six coverage jobs (211). Under d955 ruling (a), the rebuilt file has no expected-value section: `--central-only` runs six central paths and six coverage jobs, adding eleven if the build's central `both` path is cached. The frozen/reweight/types/both factorial remains four-way; legacy and total are controls.

```sh
python scripts/validate_ageing.py --plan                                   # job counts and the paired draws
python scripts/validate_ageing.py --workers 3 -o .cache/ageing_validation.json
# Under d955 ruling (a), use --central-only because no expected-value subsample exists.
```

Contrasts are computed within each path, then averaged over the strata (`expected_value.stratified_estimate`, with the committed stratum probabilities and both the path-sampling and first-phase variances); the identical-rates stratum saves exactly nothing under every treatment:
- `reweight_effect` = reweight − frozen, `types_effect` = types − frozen, `combined_effect` = both − frozen;
- `interaction` = both − reweight − types + frozen, the four-way term;
- `common_input_effect` = frozen − legacy, the represented ages and birthday.
- `population_total_effect` = total − frozen; `age_structure_effect` = reweight − total.

The report holds savings for the UK and Great Britain, State Pension against DWP's matched GB totals (2024-25 to 2030-31), and GB State Pension by age, withheld whole across treatments if any cell in any is suppressed. The command permits at most three Enhanced FRS workers and starts no Microcosm job. Historical pilot timings are not a final-head runtime measurement.

The separate part E pilot runs six treatments—frozen/reweight/types/both/total and `both_full_new`—on its central path and the original part D forty distinct paired indices. It also has 246 full path-run labels and six coverage jobs, but executes the paths as 41 same-path six-treatment batches, for **47 execution jobs**. Each treatment still computes both policies in full; retained part D values are comparison evidence, not reused inputs or fiscal outputs. The pilot limits these batches to two Enhanced FRS workers. Its chosen years restrict publication, not calculations.

Part B ran the original five-mode design (legacy plus the four factorial treatments) on policyengine-uk 2.90.2 with its own worker and publication guard; its approved output is the record (`data/ageing_validation.json`, rendered as [AGEING_PILOT_RESULTS.md](AGEING_PILOT_RESULTS.md) by `scripts/report_ageing_validation.py`; [AGEING_PILOT.md](AGEING_PILOT.md)). The integration replaced the worker with the engine's own jobs, so the four-way runs and the published runs are one implementation of the fiscal totals, and retired the guard, which certified that one run on the retired engine. Part E adds the total-only control.

The Spring 2026 DWP workbook covers GB plus overseas, excluding Northern Ireland. Only its all-type State Pension spending and caseload separate the overseas amounts; subtracting those gives matched GB totals through 2030–31. Published basic/new amounts are GB plus overseas context, not matched benchmarks, and the workbook gives no State Pension forecast by age or country, so those comparisons are unavailable, as is everything after 2030–31; no benchmark is extrapolated or allocated.

The separately published regional outturn table supplies combined State Pension spending for England, Scotland and Wales in 2024–25 as context. It does not supply the requested basic/new split or financial-year annual recipient counts, and its guidance excludes forecast years. Those country benchmarks remain unavailable; the source tables, exact cells and hashes are recorded in [country_benchmark_availability.json](../data/pilot/country_benchmark_availability.json) and [country_benchmarks.json](../data/pilot/country_benchmarks.json). No combined expenditure is split and no quarterly caseload is treated as an annual financial-year mean.

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
long paths concatenate independent blocks and truncate the last one. Blocks
start in the first unobserved year (the origin year), so an origin+1..origin+4
scored window crosses two blocks; dependence is preserved within a block, not
across that boundary. The
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
scoring that legal regime; otherwise one compares different policy rules. The
2021 earnings-minus-CPI gap then becomes a deterministic zero in both forecast
and outcome: its CRPS and bias are zero and its coverage is automatically one.
This dilutes the suspended-treatment gap scores; it is an explicit consequence
of this frozen legal-regime check, not predictive skill for actual earnings.

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
screen after seeing the scores. This is the original C1 rule; the separate post-scoring d955 inputs below explicitly record any changed execution or presentation. The across-form/mean-path spread is a **scenario
envelope**, never a probability interval, and forms are never averaged.

**Rebuild handoff.** Each passing form gets its own 50,000 equally weighted
draws, ten strata on its own 2039–40 weekly pension gap, and 160 Neyman-allocated
sample slots (at least two per nonzero stratum), plus an identical-rates check
when present. For original-primary paired mean-path designs, two of the 160
slots sample the zero stratum when it exists, retaining its probability mass
if a mean-path variant makes its saving nonzero. Allocation uses rule-gap spread as a proxy, not observed fiscal
variance. Report its mean triple-lock premium over statutory earnings for April
2034–2039 beside the OBR fiscal-input comparator (0.557 points from the committed
unrounded determinants, rather than the rounded 0.6-point note). Save the draw
arrays, allocation, sample multiplicities and runnable engine specs. The existing
200-slot `run=False` route remains a labelled legacy diagnostic only. The executing
`expected_value.build` adapter consumes the chosen-form 160-slot C1 handoff and
its paired indices, checks their draw hashes/specs, runs the identical-rates
check independently, and writes an exact 40-slot Microcosm-paired subsample.
The results record every path's `times_drawn_sensitivity` (including zero), every
sampled stratum's `sensitivity_paths` and `probability`, and `draws.n`, `seed`,
`shocks` and `form`, so the ageing validation can reconstruct that form and verify
its stored statutory inputs. It counts the zero-stratum probability once.

The **original** primary also gets two diagnostic mean-path specs: earnings
±0.5 percentage points in calendar targets from 2031 onward, simulated using
exactly the same seed, shock stream and sampled draw indices. Monthly drift may
smooth the statutory response across the boundary; do not add 0.5 points directly
to statutory inputs. These paired specs are scenarios and can get full runs independently of the
adequacy screen. Their presentation still follows Max's recorded d955 ruling. Estimate each variant-minus-baseline from within-stratum paired
outputs, retaining baseline-zero strata if a variant ceases to be zero there.

**Recorded method input (part E, post-scoring implementation).** No ruling is
selected here. `uncertainty_ruling=None` refuses fiscal expected-value execution
and names d955. Ruling (a) omits the expected value, retaining central and mean-path
scenarios; (b) executes the original primary and labels every result model-conditional,
retaining its frozen-screen failure; (c) reruns the screen on the suspended April 2022
treatment only and executes a selected passing form, refusing if none passes. The
flag is recorded in results/provenance; it records Max's decision rather than taking
it. Standalone mean-path runs may precede the decision, with presentation explicitly
pending d955. Their zero-stratum and all fiscal-output paired differences are retained.

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
