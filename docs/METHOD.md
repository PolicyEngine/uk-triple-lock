# Method

Every fiscal and household figure is a full PolicyEngine UK run (policyengine-uk 2.118.0) on the Enhanced FRS 2024-25 (policyengine-uk-data 1.56.16), with Microcosm (`populace_uk_2023`) as a dataset sensitivity. Nothing is scaled or interpolated from another run. The code is the reference; this file points to it.

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
- the variables the net saving is decomposed into explain the model's own `gov_balance` (below).
- opt-in demographic pins read back correctly, person and benefit-unit weights equal their household weights, and raked treatments hit their anchored ONS growth targets to 1e-6 relative in every year.

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. April 2027's benefit uprating is the model's own calendar-2026 CPI (2.3%) on every path, not September 2026 CPI.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. policyengine-uk takes up either only for a family reporting it unless no family in the simulation reports any of seven benefits (`claims_all_entitled_benefits`), which survey data always do; pension-age families may make new Housing Benefit claims in law, and in policyengine-uk from 2.102.5, but in the survey runs only those already claiming do. Pension Credit take-up is the dataset's own draw (`would_claim_pc`). A pension cut can make a household eligible for Pension Credit guarantee credit, which in policyengine-uk passports it to its full rent in Housing Benefit; one heavily weighted record does this on some paths, moving the net figure by billions of pounds. Each run records how much the single record with the largest effect contributes in every year, and its share of the change; FRS records are licensed data, so the published file never gives a record's identifier, weight or amounts.

**Council tax reduction for Pension Credit recipients.** Since policyengine-uk 2.104.2 the pensioner schemes disregard the whole income of a guarantee credit recipient (SI 2012/2885, Schedule 1, paragraph 13, and the Welsh and Scottish equivalents), and use the Pension Credit assessment for a savings-credit-only award, as the law requires. A guarantee credit recipient's council tax reduction no longer moves with the State Pension. A test checks that for the example pensioner on the guarantee under both rules, council tax reduction and Housing Benefit do not move and the change in income is exactly the change in savings credit, which pays 60% of income above its threshold (and which policyengine-uk 2.118.0 pays the example once the basic State Pension passes the threshold, where 2.90.2 paid none).

**The State Pension amounts.** The flat rates are set from each rule applied to the path's statutory inputs.

**Inputs held the same under both rules** (`engine.pinned_inputs`, `config.py`):
- **State Pension age.** The model's own: policyengine-uk sets it from each person's date of birth by the Pensions Act 1995 timetable, including the rise from 66 to 67 for people born from 6 April 1960 (#1899), and the engine reads it through `is_SP_age` and `state_pension_age`. The date of birth comes from the survey age and a position within the year of age. Survey ages are held, so a record's date of birth moves a year later each year: the survey's 66-year-olds are partly over State Pension age in 2026-27 and 2027-28 and below it from 2028-29 (until model-v2 the engine set 67 from 2028-29 itself, as the parameters stopped at 66). Each run records the youngest survey age with anyone over it and the youngest from which everyone is (`fixed_inputs.state_pension_age`).
- **Pension type.** Each person's State Pension type (basic or new) is held at its survey-year value. Survey ages never advance, and policyengine-uk takes the type from the date State Pension age was reached, so it would otherwise move records from the basic to the new State Pension year by year. policyengine-uk 2.118.0 splits the additional State Pension by each year's type (#1922), so the model alone no longer counts the band between the two flat rates twice; the engine's additional State Pension (below) is split by the survey year's type, so with moving types it would. Each run reads the types back from the model in every year, fails if anyone's differs from the held one, and records the counts (`held_pension_type_records`, `held_pension_type_people`).
- **Additional State Pension.** The survey-year amount (the reported pension above the flat rate of the survey-year type), grown by September CPI (published to April 2026, the path's after), as in law, for people over State Pension age that year. policyengine-uk 2.118.0 still scales it by the flat rates' ratio (its issue #1941, open): in a run that cuts the flat rates by 5%, its total falls by 5%. Under its own uprating the Burnham plan would cut the additional pension too.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk 2.118.0 still uprates it by CPI.

**Ageing treatments (opt-in; `demography.py`, `cohorts.py`):**

- **Represented age and birthday.** Survey records at exactly age 80 are assigned one represented age from 80 through 105, where 105 means 105+. Within sex, a deterministic hash orders records and weighted midpoints assign calibration-year ONS single-age shares. The weighted 80+ total is preserved; each single-age allocation differs from its target by at most the largest record weight for that sex. Other ages remain unchanged. The same represented ages are used in all four demographic treatments and are set as the model's `age` input. A within-year birthday draw follows the 2.118.0 hash and weighted stratification and is pinned as `months_since_last_birthday` when that variable exists. Both are fixed before reweighting.
- **Household weights.** The `reweight` and combined `both` treatments apply bounded minimum-relative-entropy calibration to household weights. Every person and benefit unit inherits its household's weight; model weight inputs are pinned and checked where present. Sex-specific cells are five-year age bands 0–59, single ages 60–79, 80–84, 85–89 and 90+. Weight ratios are bounded between 0.2 and 5 relative to anchor-year weights; an infeasible or unconverged target fails the run rather than relaxing the bounds. The `frozen` and `types` treatments retain the dataset's native weights for each year.
- **Pension type.** In `types` and `both`, a record represents a contemporaneous person of its fixed age in each fiscal year. Its synthetic birth date is inferred at 6 October of that year from the represented age and fixed birthday draw. Eligible men born before 6 April 1951 and eligible women born before 6 April 1953 have type `BASIC`; later births have type `NEW`, including the cutoff day itself. Those below the model's State Pension age have type `NONE`. This replaces successive cohorts rather than ageing surviving individuals. The `frozen` and `reweight` treatments retain the survey-year type, subject to the same pension-age eligibility gate. Every policy run reads the pinned types back each year and fails on a mismatch.
- **Additional State Pension and protected payments.** For each selected contemporaneous type in `types` and `both`, the data-year reported State Pension is repartitioned against that type's data-year flat-rate ceiling: its basic or new component is the smaller of the reported amount and ceiling, and the nonnegative excess is additional pension. Thus basic + new + additional equals reported pension to the penny for an eligible data-year record. On a `NEW` record, the excess represents protected payments, including inherited amounts already reported; contribution histories and new protected entitlements are not simulated. The excess follows September CPI from the data year, never a negative uprating, and is zero below pensionable age. In `frozen` and `reweight`, the original data-year additional amount is retained on the same CPI basis. Each path uses exactly the same additional-pension input under the triple lock, plan and baseline; only its CPI path affects uprating.
- **State Pension age.** Eligibility is calculated by the installed model after represented ages and birthday inputs are pinned. The current 2.90.2 engine retains its existing override to 67 from 2028–29 because its parameters stop at 66. The upgraded bundle's cohort-specific timetable is part A's port, so the current-engine pilot cannot validate that timetable's population effect.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk uprates it by CPI.

**Calibration anchor and population source.** The source is the public ONS 2024-based UK principal projection, mid-years 2024–2041; the [population-input notes](ONS_PROJECTION.md) document its download and SHA-256 provenance. Fiscal-year population is 75% of mid-year *y* plus 25% of mid-year *y+1*. The target for each cell is its anchor-year survey margin multiplied by ONS growth from that fiscal year, not the raw ONS population level. Targets therefore equal base margins in the anchor year and leave the selected anchor weights unchanged. Benefit-calibration preservation also requires verified calibrated inputs and a controlled comparison of the other model inputs.

The demographic API requires an explicit anchor or verified dataset `calibration_year` metadata and fails if both are absent. The fresh pilot explicitly anchors **2025**, the calibration year declared by the [exact data-release source](https://github.com/PolicyEngine/policyengine-uk-data/blob/12a1e028afeef08d8b2d74ee03fd9de3a78b2dd3/policyengine_uk_data/datasets/frs_release.py#L53-L57). The [bundle/source audit](CALIBRATION_ANCHOR.md) maps that source version to the certified Enhanced FRS and explains the remaining artifact qualification: its private build manifest is gated, and runtime-native 2025 weights differ from the builder's restored calibrated weights. This pilot preserves runtime-native 2025 weights mechanically; it does not establish that Housing Benefit or Pension Credit calibration is preserved. Represented ages and cohort retyping can change awards even when weights are unchanged.

The raked treatments replace other years' native weights with weights derived from this one anchor, including backward raking to the 2024 data year. Only the 2025 anchor weights remain unchanged. In 2024–25, GB State Pension spending is £114.862bn under `reweight` versus £116.097bn under `frozen`; this is not data-year weight preservation. The inspected 2.90.2 runtime generates later native weights by population uprating rather than annual recalibration. Part C must obtain the certified calibrated-period inputs, verify the runtime materialization of incomes and weights, and measure the effects of the demographic changes on the calibrated benefit baseline.

**Data-year identity gate.** The pilot's aggregate audit found 40 current dataset records with positive reported State Pension below the installed model's State Pension age. Payable components cannot both reproduce a positive reported amount and be zero with type `NONE`. The identity passes for eligible data-year records; the full gate remains pending for these ineligible reporters. Part C must report the discrepancy and resolve verified survey misreporting or pension-age model defects through the appropriate data/model build. It must not create payable pension below pensionable age to force the accounting identity.

**Private demographic cache.** Dataset-driven ages, birthday draws, cell targets and weights are cached under `.cache/demography`, using input-array, projection, source-code, model-version and treatment fingerprints. The cache excludes the policy rule and CPI path. Cache directories/files use private permissions; no record ids, weights or amounts enter public validation results. Additional-pension uprating is calculated separately for each CPI path.

**Scope and programme limits.** The [rule audit](AGEING_RULE_AUDIT.md) reads the relevant 2.90.2 and 2.118.0 code. It finds no further implemented monetary age band between 80 and 105 for the inspected programmes, but pension cohort eligibility and eldest-member ranking remain dependencies. Supplied head and relationship flags are retained; inferred heads or claimant/partner status can change when top-coded age ties are resolved. Neither inspected release models Scotland's Pension Age Winter Heating Payment or an explicit basic-pension age-80 addition. Reported additions can enter the residual; this does not implement the statutory addition as a separate entitlement. The pilot must preserve these limits when interpreting programme spending.

Historical replay, the legacy coverage helper and forecast paths with absent or `legacy` demography settings continue to use `engine.pinned_inputs`, retaining survey ages, native weights, survey-year types and the original additional-pension treatment. The new treatment applies to explicitly requested forecast paths and the dedicated ageing pilot. Existing historical and legacy coverage outputs are not regenerated ageing validation.

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components, for the UK and for Great Britain (households in England, Scotland and Wales, as DWP's figures are; neither dataset has a household of unknown country);
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- for legacy runs, the private single-household diagnostic; opted-in demographic runs suppress all record diagnostics before returning results.

**Gross to net.** `gov_balance` is policyengine-uk's `gov_tax` less its `gov_spending`, each the household sum of its own list of variables (`GOV_TAX_VARIABLES`, `GOV_SPENDING_VARIABLES`). Each run totals every variable on the two lists (`engine.fiscal_variables`, which mirrors their formulas' council-tax-abolition conditional and splits State Pension into basic, additional and new), records the change in each, and groups them: the State Pension flat rate, additional State Pension, Pension Credit, Housing Benefit, Universal Credit, council tax reduction, Winter Fuel Payment, income tax, other spending and other tax. The model computes `gov_balance` household by household in float32, which leaves its total a few £1,000 off the float64 sum of the same variables (3.2e-6 £bn on the Enhanced FRS in 2026-27) and a change in it about 1e-6 £bn off. The run therefore takes the net saving as that float64 sum, so the components add up to it by construction (the recorded `decomposition_residual` is float64 rounding, about 1e-13 £bn). The test that the lists explain the model is against the model's own float32 `gov_balance`, recorded beside it: its level to 1e-4 £bn (£0.1m) and its change between the rules to 1e-5 £bn (£0.01m). A variable missing from the lists, or extra, fails the run if its total is over £0.1m a year or either rule moves it by over £0.01m; in the pilot runs the change agreed to 3e-6 £bn or better.

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
   - The dynamics tilt made the bias larger and put the realised 2012-start gap at its 93rd percentile, against the 56th for the untilted model. The tilts are reported as sensitivities, reweighting the same runs.
4. **Sample.**
   - Draws on which the two rules pay the same every year save exactly nothing. They form their own stratum, and one is run to confirm it.
   - The rest are split into 10 strata of equal probability on the 2039-40 weekly gap. 200 paths are allocated by Neyman allocation (at least 2 a stratum) and drawn with probability proportional to weight.
   - Each is a full run of both rules. Microcosm runs the first 40 of them, paired.
5. **Estimator.** Σ_h W_h ȳ_h. Historical committed results use only sqrt(Σ_h W_h² s_h² / n_h); new estimates add first-phase variance and report both components separately, as specified in the C1 rule below. The reweighted sensitivities and the Microcosm subsample rest on few effective runs in some strata, so their ± figures are approximate; the file reports each sensitivity's effective runs. Tests check that it is unbiased and that its interval covers about 95% of the time on synthetic cases (`tests/test_expected_value.py`). They also check that the committed file's estimates recompute from its per-path records (`tests/test_results.py`).

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

**The OBR wedge (`obr_premium`).** The triple lock pays the 'Triple lock' row of the OBR's long-term economic determinants (March 2026), its value for the fiscal year of the inputs paid the next April, from April 2028. April 2027 is set by published inputs (May-July 2026 AWE), so it is the central path's under both rules, not the OBR's projection. For the fiscal years 2027-28 to 2030-31 the row is 2.5% (paid the Aprils 2028 to 2031, as on the central path); from 2033-34 it is, in the OBR's note, average earnings growth plus 0.6 points (0.56 above the fiscal-year earnings growth the central path uses), phased in over the two years between. The 0.6 points is the OBR's stylised allowance for the years CPI or the floor beat earnings, an average-rate assumption: no CPI and earnings path pays it every year, so the run is a comparison with the OBR's costing convention, not a forecast. Only the triple lock gets the premium. The plan runs its own rule from the switch, on the central path's CPI and earnings, so it gets no credit for the volatility that sets its own floor. Spending is the static survey bill (no ageing beyond the weights), for the UK, where DWP's figures are for Great Britain.

## Datasets and DWP

`dwp.py` reads DWP's spending and caseloads (Spring Forecast 2026, Great Britain) for 2026-27 to 2030-31, where its tables stop, and its uprating analysis. DWP costs the plan at £15bn in 2039-40, nominal, on one path through Pensim3, a dynamic population model, for Great Britain.

**Coverage.** One coverage job per dataset runs the central path under the triple lock, as the central run's triple-lock policy does (pension types held at the survey year), for 2026-27 to 2030-31, 2034-35 and 2039-40. It gives each year's State Pension (by part, recipients and types), Pension Credit (guarantee and savings credit, and claims), Housing Benefit and pension-age Housing Benefit (spending and claims), council tax reduction and Universal Credit, for the UK and for Great Britain. The results set Great Britain against DWP, like for like, in every year DWP's tables give. Pension-age Housing Benefit is Housing Benefit paid under the pension-age regulations (`housing_benefit_pension_age_regulations_apply`), nearest DWP's "over Pension Credit qualifying age". 2034-35 and 2039-40 have no DWP figure.

The survey here is not aged. Enhanced FRS ages are top-coded at 80 and held at their survey values, and pension types are held at the survey year. The State Pension age follows the law's timetable by date of birth, so every survey age of 67 and over is above it from 2028-29.

## The model: policyengine-uk 2.118.0, pinned directly (`datasets.py`)

policyengine.py's release bundles certify one policyengine-uk version with one data build. None yet carries the pensioner fixes this analysis needs: 6.2.1 pins policyengine-uk 2.102.3, and its import fails beside 2.118.0, because its data certification finds no release certified for the installed version. So `pyproject.toml` and `requirements-lock.txt` pin policyengine-uk 2.118.0 (and policyengine-core 3.32.16) directly. The engine loads each dataset itself, pinned to a revision and a SHA-256 and hashed before every use, as policyengine.py's managed loader did:

- the Enhanced FRS 2024-25, policyengine-uk-data 1.56.16, built with policyengine-uk 2.89.2, the build policyengine.py 5.3.0 and 6.2.1 certified (for 2.90.2 and 2.102.3);
- policyengine-uk-data 1.57.4 (built with 2.93.0), registered for comparison;
- Microcosm `populace_uk_2023`, the dataset overlay policyengine.py carries.

Both Enhanced FRS releases load and compute on 2.118.0 with no warnings and no NaN, and store the same variables (1.57.4 adds one childcare column). Twenty stored columns are not variables in 2.118.0 (geography codes and build bookkeeping such as `clone_index`), and eleven are variables it would otherwise compute, whose stored values it uses (`state_pension_reported` among them). Every run records the installed model and core versions and the dataset's pin, with `certified: false` and the reason (`provenance.model`). A test checks that the recorded version is the installed policyengine-uk.

**What changed upstream between 2.90.2 and 2.118.0**, as policyengine-uk's changelog records the entries that touch this analysis (77 releases), and whether the engine relied on the old behaviour (from the engine's code):

| Change (policyengine-uk) | Moves | The engine relied on the old behaviour? |
|---|---|---|
| State Pension age by date of birth, with the rise to 67 (#1899, 2.112.0); the scalar age parameters removed | who is over State Pension age in 2026-27 and 2027-28 | Yes: it set 67 from 2028-29 on the removed parameters. Dropped; reads `is_SP_age` |
| Triple lock from September CPI and May–July AWE, with forecast gaps (#1939, 2.109.0); an optional earnings-path guarantee | the model's own flat rates | Yes: its check expected calendar growth. Now sets and checks the statutory inputs; the rules set both rules' flat rates, as before |
| Additional State Pension split by the year's own pension type (#1922, 2.113.3) | additional pension, where types move | No: types are held, and the engine's pin is split by the survey year's type |
| Additional State Pension still scaled by the flat rates' ratio (#1941, open) | – | Yes, and still needed: the CPI-linked pin stays |
| Pension Credit guarantee still uprated by CPI | – | Yes, and still needed: the earnings-linked override stays |
| Derived series now run to 2073-74 (lagged CPI and earnings, the triple lock) | – | Yes: `model_horizon` extended them. Now extends only the private pension uprating |
| New Housing Benefit claims at pension age (#1901, 2.102.5) | the example renters | Yes: the examples carried a reported claim. Dropped; in survey runs only families already claiming respond, as before |
| Council tax reduction disregards guarantee credit recipients' income (#1909, 2.104.2) | council tax reduction for Pension Credit recipients | It was a stated limitation; dropped |
| Housing Benefit: LHA cap before the taper (#1926, 2.105.1), earnings disregards (#1908, 2.111.1), savings credit in income (#1945, 2.114.1), the Universal Credit and income-based passports (2.109.7, 2.117.1), LHA rates from the published determinations (2.114.3), joint tenants' shares (2.113.0) | Housing Benefit baseline and offset | No |
| Pension Credit: dataset capital input, a no-op without it (#2018, 2.105.0), the qualifying age by date of birth (#1907, 2.115.0), mixed-age couples (#1940, 2.109.4), carers' income and the severe disability addition (#1938, #1951, #1952), Lifetime ISA capital where a dataset has it (2.103.0) | Pension Credit baseline and offset | No |
| Winter Fuel Payment on pensionable age from 2024-25 (2.115.0); employer NI over State Pension age (2.102.6); Class 4 NI; NICs thresholds frozen to 2030-31 (2.106.1, the lower earnings limit still follows CPI) | small baseline changes | No (the NI lower earnings limit the engine checks is still CPI-indexed) |
| Universal Credit counts State Pension and other income for mixed-age couples (2.104.7, 2.104.1, 2.108.0, 2.113.2) | Universal Credit offset | No |

Still open upstream: #1927 (the Housing Benefit guarantee credit passport keyed on receipt), #1925 (benefit rates at announced amounts), #1913 (pension-age Housing Benefit allowances by cohort) and #2019 (Pension Credit earnings disregards). policyengine-uk 2.119.0 and 2.120.0 followed 2.118.0, adding the date of birth to the mixed-age couple saving and the child cut-offs and limiting Universal Credit to the claimants' income; the pin stays at 2.118.0.

The committed headline results and default published pipeline hold the original top-coded ages and survey-year types. Explicit ageing treatments vary household weights and contemporaneous pension cohorts as described above. Amounts for later retirees still come from survey records representing the same age; deaths, migration and contribution histories are not simulated. Pensioners abroad are outside the household survey.

## Four-way ageing pilot (`ageing_validation.py`)

Inspect the planned jobs without loading private data:

```sh
python scripts/validate_ageing.py --workers 1 --calibration-year 2025 --plan
```

Compute the complete treatment design on the certified Enhanced FRS, keeping its aggregate execution report private:

```sh
python scripts/validate_ageing.py --workers 4 --persistent-workers --calibration-year 2025 -o .cache/ageing_validation.json
```

This command computes private aggregates; it does not by itself retain all evidence required for canonical publication. Before dispatch, save the full return value of `ageing_validation.validation_plan(calibration_year=2025)` with `ageing_publication.calculation_metadata(plan)`, including the original calculation head and source hashes. The `--plan` command above prints a summary, not that full saved plan. Retain the original execution report and complete log, an input audit bound to that exact plan, and both real engine-integration and persistent/isolated-equivalence evidence files. The eight-slot driver used for this pilot supplied those records privately; it is not a public CLI feature.

For the retained 2025 pilot evidence, canonical publication and rendering use:

```sh
python scripts/publish_ageing_validation.py \
  --saved-plan .cache/ageing-publication-plan-2025.json \
  --execution-report .cache/ageing-pilot-2025.json \
  --execution-log .cache/ageing-pilot-2025.log \
  --execution-driver .cache/run_ageing_pilot_2025.py \
  --input-audit .cache/ageing-publication-audit-2025.json \
  --integration-evidence .cache/ageing-integration-checks.json \
  --equivalence-evidence .cache/ageing-runner-equivalence.json \
  -o data/ageing_validation.json
python scripts/report_ageing_validation.py data/ageing_validation.json \
  -o docs/AGEING_PILOT_RESULTS.md
```

The publisher requires the original plan/head, complete cached jobs, original execution evidence and current privacy audit before writing approved aggregates. It does not start missing fiscal jobs. The saved plan, execution files, input audit and control evidence remain private in `.cache`; the approved pilot JSON and rendered report are separate from the unchanged dashboard `data/results.json`.

The runner records host CPU and available RAM before starting full model jobs. One worker is the default; the CLI permits at most four Enhanced FRS workers and starts no Microcosm workers. It requires an explicit calibration year; 2025 above is the source release's calibration year, used here with the runtime-native weights and qualified as described above. The fresh pilot requests eight Enhanced FRS slots and zero Microcosm slots through the same API after separate host checks. The execution log records zero of 205 jobs cached at dispatch, so all 205 were scheduled for fresh execution. Requested slots do not establish observed peak concurrency; completed-job receipts and the execution-log hash supply separate execution evidence. It runs the central path and the exact committed 40 Microcosm-paired expected-value draws, all on Enhanced FRS, preserving stratum probabilities. All 40 draws are distinct in this pilot; the API also supports selection multiplicities. Each path runs `frozen`, `reweight`, `types` and `both` under both pension rules with the same baseline demographic pins. These four treatments share represented ages and birthdays. A fifth `legacy` control retains original survey inputs and measures the shared changes as `frozen − legacy` (`common_input_effect`). On 2.90.2, both controls already use the same integer-age pension eligibility gate and zero additional pension below that age; the contrast measures represented ages and any head/claimant effects. On newer bundles, birthday inputs can also change eligibility. The complete plan has 205 treatment jobs: five for the central path and five for each of the 40 paired selections. The core four-way interaction is `both − reweight − types + frozen`, computed within each path before stratified averaging. An optional `--central-only` run is explicitly preliminary and does not satisfy the complete design.

All pilot fiscal totals, gross/net savings, household-income effects and their four-way contrasts cover **Great Britain**, with Northern Ireland excluded by the model household-region mask. Coverage uses the same GB scope. These pilot estimates must not be compared directly with the committed dashboard's UK headline. The approved output includes the interaction, separate legacy comparison, path-sampling standard errors, and pension recipients and basic/new spending by age. The linked country/region family is withheld for privacy. Coverage includes every year from the data year through 2039. Every nonzero contributor cell requires at least ten records; zero-contributor cells can report zero. Publication also requires an input-support audit of same-year treatment contrasts, every pair of years within a treatment, and changes in treatment contrasts between years. Direct subtractions between different treatments in different years are not separately enumerated. A small age or geography cell in either audit withholds its entire linked age family or country/region family across paths, treatments, years and policies. A small GB contrast blocks publication. No survey ids, weights or amounts are exported.

The support proof covers the audited pinned demographic inputs and pension components under the inspected model formulas. It does not establish support for every model-derived programme state. For example, period-derived `birth_year` can change Savings Credit eligibility while represented age is fixed. Net fiscal and household-income outputs remain nonlinear full-model aggregates; their publication assumes that the omitted derived-state changes do not permit exact recovery of fewer than ten contributors from the released contrasts. That assumption is separate from the input-support checks and must be reassessed for an upgraded model. All fiscal values come from full PolicyEngine calculations using pinned inputs. Optional persistent workers construct fresh simulations for every job, record private stage timings/RSS, and recycle after 20 jobs. `--verify-workers` compares a real isolated central job with a persistent central job after a different draw.

The Spring 2026 DWP workbook covers GB plus overseas, excluding Northern Ireland. Only its all-type State Pension spending and caseload have separately identifiable overseas amounts; subtracting those provides matched GB totals through 2030–31. Published basic/new amounts and recipients are shown separately as **GB plus overseas context**, not matched GB benchmarks. This workbook supplies no State Pension forecast breakdown by age or country/region, so those benchmark comparisons are labelled unavailable. Comparisons after 2030–31 are also unavailable until a published long-term source is verified; no benchmark is extrapolated or allocated from an overseas share.

The complete 205-job four-way pilot and its mechanical checks have passed on the current 2.90.2 bundle; [AGEING_PILOT.md](AGEING_PILOT.md) interprets the approved GB results and [AGEING_PILOT_RESULTS.md](AGEING_PILOT_RESULTS.md) records the full tables and provenance. The combined treatment increases paired expected-value gross and net savings relative to frozen inputs, with a positive interaction, while central-path savings remain much smaller. The matched GB State Pension spending gap to DWP remains substantial. The calibrated-input bridge and all-record pension identity remain pending, alongside the disclosed benchmark, programme, type-cache and derived-state privacy limits. Part C needs the certified upgraded model/data bundle with an explicit calibration year, a version bridge for State Pension, Pension Credit and Housing Benefit, resolution/reporting of verified below-pension-age reporters, a repeat of the complete paired pilot including its legacy control, and verified sources for any additional benchmark comparisons before the one full rebuild and an explicit change to the published pipeline's demographic treatment.

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
screen after seeing the scores. The across-form/mean-path spread is a **scenario
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
200-slot `expected_value.build` execution route is disabled even after a passing
screen: a rebuild adapter must consume the 160-slot C1 handoff and its paired
indices. Its `run=False` route is a labelled legacy diagnostic only.

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
