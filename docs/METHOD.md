# Method

Every fiscal and household figure is a full PolicyEngine UK run (policyengine-uk 2.118.0) on the Enhanced FRS 2024-25 (policyengine-uk-data 1.56.16), with Microcosm (`populace_uk_2023`) as a dataset sensitivity. Nothing is scaled or interpolated from another run. The code is the reference; this file points to it.

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

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. April 2027's benefit uprating is the model's own calendar-2026 CPI (2.3%) on every path, not September 2026 CPI.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. policyengine-uk takes up either only for a family reporting it unless no family in the simulation reports any of seven benefits (`claims_all_entitled_benefits`), which survey data always do; pension-age families may make new Housing Benefit claims in law, and in policyengine-uk from 2.102.5, but in the survey runs only those already claiming do. Pension Credit take-up is the dataset's own draw (`would_claim_pc`). A pension cut can make a household eligible for Pension Credit guarantee credit, which in policyengine-uk passports it to its full rent in Housing Benefit; one heavily weighted record does this on some paths, moving the net figure by billions of pounds. Each run records how much the single record with the largest effect contributes in every year, and its share of the change; FRS records are licensed data, so the published file never gives a record's identifier, weight or amounts.

**Council tax reduction for Pension Credit recipients.** Since policyengine-uk 2.104.2 the pensioner schemes disregard the whole income of a guarantee credit recipient (SI 2012/2885, Schedule 1, paragraph 13, and the Welsh and Scottish equivalents), and use the Pension Credit assessment for a savings-credit-only award, as the law requires. A guarantee credit recipient's council tax reduction no longer moves with the State Pension. A test checks that for the example pensioner on the guarantee under both rules, council tax reduction and Housing Benefit do not move and the change in income is exactly the change in savings credit, which pays 60% of income above its threshold (and which policyengine-uk 2.118.0 pays the example once the basic State Pension passes the threshold, where 2.90.2 paid none).

**The State Pension amounts.** The flat rates are set from each rule applied to the path's statutory inputs.

**Inputs held the same under both rules** (`engine.pinned_inputs`, `config.py`):
- **State Pension age.** The model's own: policyengine-uk sets it from each person's date of birth by the Pensions Act 1995 timetable, including the rise from 66 to 67 for people born from 6 April 1960 (#1899), and the engine reads it through `is_SP_age` and `state_pension_age`. The date of birth comes from the survey age and a position within the year of age. Survey ages are held, so a record's date of birth moves a year later each year: the survey's 66-year-olds are partly over State Pension age in 2026-27 and 2027-28 and below it from 2028-29 (until model-v2 the engine set 67 from 2028-29 itself, as the parameters stopped at 66). Each run records the youngest survey age with anyone over it and the youngest from which everyone is (`fixed_inputs.state_pension_age`).
- **Pension type.** Each person's State Pension type (basic or new) is held at its survey-year value. Survey ages never advance, and policyengine-uk takes the type from the date State Pension age was reached, so it would otherwise move records from the basic to the new State Pension year by year. policyengine-uk 2.118.0 splits the additional State Pension by each year's type (#1922), so the model alone no longer counts the band between the two flat rates twice; the engine's additional State Pension (below) is split by the survey year's type, so with moving types it would. Each run reads the types back from the model in every year, fails if anyone's differs from the held one, and records the counts (`held_pension_type_records`, `held_pension_type_people`).
- **Additional State Pension.** The survey-year amount (the reported pension above the flat rate of the survey-year type), grown by September CPI (published to April 2026, the path's after), as in law, for people over State Pension age that year. policyengine-uk 2.118.0 still scales it by the flat rates' ratio (its issue #1941, open): in a run that cuts the flat rates by 5%, its total falls by 5%. Under its own uprating the Burnham plan would cut the additional pension too.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; policyengine-uk 2.118.0 still uprates it by CPI.

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components, for the UK and for Great Britain (households in England, Scotland and Wales, as DWP's figures are; neither dataset has a household of unknown country);
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- the single survey household that moves each year's net figure most.

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
5. **Estimator.** Σ_h W_h ȳ_h with standard error sqrt(Σ_h W_h² s_h² / n_h). The reweighted sensitivities and the Microcosm subsample rest on few effective runs in some strata, so their ± figures are approximate; the file reports each sensitivity's effective runs. Tests check that it is unbiased and that its interval covers about 95% of the time on synthetic cases (`tests/test_expected_value.py`). They also check that the committed file's estimates recompute from its per-path records (`tests/test_results.py`).

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
