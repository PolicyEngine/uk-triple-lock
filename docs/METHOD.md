# Method

The committed `data/results.json` is the **binding post-Budget release**: the primary failed the frozen C2 screen, so the build took the automatic fallback to uncertainty ruling (a) and wrote scenarios with no expected value. Every fiscal figure is a full PolicyEngine UK run on policyengine.py **6.11.1**, UK **2.151.0**, core **3.33.3** and the Microcosm national cut named below, with static ageing below. The pre-Budget release, publicized in Vahid's post as provisional, ran on policyengine.py 6.2.6, UK 2.125.1, core 3.33.0 and Enhanced FRS 1.58.0, with Enhanced FRS as primary and the earlier Microcosm artifact as its uncertified paired sensitivity; git history holds its file. The original uncertified model-v2 pilot (UK 2.120.0 / EFRS 1.56.16) is retained separately in `data/pilot`; model-v2 is merged. The completed historical bridge and rehearsal are bound by [J-completed-verification](../data/pilot/J-completed-verification.json).

Max's **d1983 = B** ruling on 24 October put the binding successor's primary on the certified Microcosm UK Budget pair, superseding d1727's qualification-ledger primary. His **d2011 = A** ruling on 25 October chose that pair: the 2.151.0 national and local-area pair built at [microcosm#1396](https://github.com/PolicyEngine/microcosm/pull/1396), national cut `microcosm-uk-2024-25-national-20261025T091414Z-a6299504`, UK **2.151.0**, core **3.33.3**. If it is not certified by 27 October 18:00Z, the fallback is [policyengine.py #715](https://github.com/PolicyEngine/policyengine.py/pull/715)'s `a133f37a` / UK 2.147.2 pair with [#699](https://github.com/PolicyEngine/policyengine.py/pull/699)'s area routing. Enhanced FRS **1.58.2** is the designated paired sensitivity; the scenarios-only build runs no paired sensitivity, so it gives only the data check. policyengine.py 6.11.1 released the pair on 27 October, certified by [policyengine.py #720](https://github.com/PolicyEngine/policyengine.py/pull/720), so the fallback was not taken; certification requires that release's exact manifest, which is pinned. [REBUILD.md](REBUILD.md) gives the fixed-data model bridge on Enhanced FRS 1.58.0 and the cross-family data bridge to Microcosm. The pre-Budget and binding releases use different data; bridge step (b) measures that move. Historical pre-Budget provenance stays at 6.2.6 / 1.58.0. Nothing is scaled or interpolated from another run. The code is the reference.

## The rules (`rules.py`)

- **Triple lock**: each April the basic and new State Pension rise by max(September CPI, May–July AWE total pay growth, 2.5%) of the year before. The inputs are taken to 0.1 point, as ONS publishes them, so the rate is exactly the larger input. One rounding (`rules.round_rate`, numpy's) takes every statutory input to 0.1 point: in the rules, in what set each rise, in the additional pension's September CPI and in the Pension Credit guarantee's earnings. What set a rise is the floor whenever neither input exceeds 2.5%, and CPI when the two inputs tie, in the history table and on every path alike.
- **Adjusted Triple Lock** (Budget 2026, paragraph 5.23 and Box 5.A; earlier releases called it the Burnham plan, after Andy Burnham's speech of 29 September 2026): the triple lock to April 2029. From April 2030 the level is L_t = max(L_{t-1}(1 + max(CPI, 2.5%)), A_t), where A_t = A_{t-1}(1 + earnings) and A starts at the 2029-30 level. The top-up to the earnings path is rounded up, so rounding never leaves the pension below it.

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

On UK 2.147.2 and 2.151.0, dated parameter reforms passed during simulation construction rebuild the derived series, including the triple lock. The earlier 2.125.1 dict-reform route edited already-processed parameters without that rebuild. The engine uses a Scenario before data load so projected inputs follow the path, then applies explicit flat-rate amounts computed by its own rules, preserving their precision, complete horizon and earnings-path top-up. `model_horizon.py` first extends the private pension uprating, which policyengine-uk still stops at 2034; every other derived series now reaches 2039-40 by itself (the OBR series run to 2073). A one-off check when porting found the processed parameters for the central path identical with and without the old extensions on every date to 2039; a test checks that every derived series follows a path to 2039-40.

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
- the additional State Pension is the pinned one under every policy, and in the data year basic + new + additional State Pension (plus the age addition when the installed model defines it) equals the reported State Pension the run counts, for every person, to £0.01; the age addition is identical under both rules in every path/year (below).

**What does not follow the path.** Dividend, property, savings and self-employment income, rents and council tax are recorded as not following it. Rents and council tax stay at their 2030 amounts from 2031, because the survey data are extended to 2030. UK 2.151.0 includes #2557 (first released in 2.148.2): `gov.benefit_uprating_cpi` has uprating metadata `gov.economic_assumptions.indices.september_cpi_uprating`, so every benefit it uprates rises each April by the path's September CPI the year before, to 0.1 point and never cut, and the benefit path check expects exactly that. April 2027 therefore uses the path's September 2026 input. UK 2.147.2 (the fallback) and the historical 2.125.1 lack #2557: their metadata is `gov.economic_assumptions.indices.obr.lagged_cpi`, and the check uses lagged calendar CPI. Any other index fails the run. Statutory September inputs still determine the State Pension, the engine's additional-pension pin and its earnings override independently of this benefit-index branch.

**Housing Benefit allowances and Savings Credit thresholds are a projection choice.** Under d1753's default, keep the installed projection and publish the alternative as a sensitivity. UK 2.151.0, like 2.147.2, lacks both the Savings Credit `maximum` parameter and #2576's `project_pension_age_allowances` and `project_savings_credit_threshold` builders (first released in 2.151.2). Its installed HB allowances and Savings Credit thresholds therefore remain on CPI: they name lagged calendar CPI themselves, the projection they reached through `gov.benefit_uprating_cpi` on 2.147.2 ([d2011-upstream.md](d2011-upstream.md)). Defensive tests also cover a model with `maximum` but without linked builders: the parameter alone never enables linked derivation. The engine overrides the guarantee to follow each path's non-negative May–July earnings, while leaving those two installed projections intact. On a later model that defines the linked builders, it also refreshes their linked amounts from its exact guarantee. The foreground sensitivity command in [REBUILD.md](REBUILD.md) compares two complete central-path pairs of the triple lock and the adjusted Triple Lock on this bundle: installed CPI and the explicitly labelled guarantee-linked alternative. No fiscal comparison has run in this preparation.

The guarantee's earnings duty ([SSAA 1992 s150A](https://www.legislation.gov.uk/ukpga/1992/5/section/150A)) does not itself prescribe future HB allowances or Savings Credit thresholds: these are separate cash amounts in [HB Regulations Schedule 3](https://www.legislation.gov.uk/uksi/2006/214/schedule/3) and [Pension Credit Regulations reg7](https://www.legislation.gov.uk/uksi/2002/1792/regulation/7). DWP describes protected HB allowances as guarantee plus maximum Savings Credit, with that uplift removed for pension-age entrants from April 2021 ([A3/2021](https://www.gov.uk/government/publications/housing-benefit-adjudication-circulars-2021/a32021-housing-benefit-person-who-have-attained-the-qualifying-age-for-state-pension-credit-amendment-regulations-2021)). Savings Credit's maximum is 60% of guarantee minus threshold ([2002 Act s3(7)](https://www.legislation.gov.uk/ukpga/2002/16/section/3)). Continuing these relationships is a documented projection convention. [HB_ALLOWANCE_REVIEW.md](HB_ALLOWANCE_REVIEW.md) preserves the historical UK 2.125.1 comparisons, whose whole-CPI headline used the old calendar-CPI benefit index.

**Take-up.** In the survey runs, Housing Benefit and council tax reduction respond only for households already receiving them: nobody newly entitled starts claiming. On policyengine-uk 2.151.0 (as on 2.147.2; the formulas are byte-identical), both take-up formulas use reported claims directly in data-built simulations, including Microcosm; they ignore `claims_all_entitled_benefits` there. That flag is false for every data-built family (#1831), while hand-entered situations apply its per-family seven-benefit test. Direct take-up inputs can override the defaults. Pension-age families may make new Housing Benefit claims in law and in the household calculator, but the default data-built formulas do not add new claimants. Pension Credit take-up is the dataset's own draw (`would_claim_pc`). A pension cut can make a household eligible for Pension Credit guarantee credit, which the certified model passports only when it is received. Individual-record diagnostics are private and omitted from published outputs. The engine privately computes `concentration_top10_by_year`; selecting ten records does not prove ten nonzero contributors or adequate recoverable complements, so new publishers omit that family too. Microcosm records are constructed from survey donors, so the same linked ten-record withholding applies to both dataset families. The published file never gives a record's identifier, weight, amount or contribution.

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
| `total_matched` (available follow-up) | represented | sum of the age/sex anchored targets after the anchor year | survey year's |

- **Represented ages.** Records top-coded at 80 get a represented age from 80 to 105 (105+): within each sex a deterministic hash of the verified dataset content and synthetic ordering key orders them and weighted midpoints take the anchor year's ONS single-age shares, so the weighted 80+ total is unchanged. Other ages are the survey's. If any age in a dataset is above 80 it is not top-coded and every age is kept. Every record also gets a fixed birthday within its year of age (`months_since_last_birthday`). A record that keeps its survey age keeps policyengine-uk's own data-year birthday, as the model gives it, and so its type: the dataset's where it supplies one (the Microcosm cuts do; Enhanced FRS 1.58.0 does not), otherwise policyengine-uk's draw on the data year's weights. A top-coded record takes policyengine-uk's rule within its represented year of age: `cohorts.within_year_birth_months`, which gives policyengine-uk's own months for whole ages, as represented ages are, and person weights equal to their household's (a differential test checks it on a survey that supplies neither a birthday nor person weights). A run fails if a kept record's data-year type changes, as it does where a dataset supplies a State Pension type or months since State Pension age that give one another type. A supplied date of birth must give the pinned age on 6 October of each year, or policyengine-uk refuses it and the run fails. A single-year dataset's dates always fail: policyengine-uk copies the dataset into each projected year, dates included, while a record keeps its age. A multi-year dataset's dates can pass, and where one is not the day the pinned age and birthday place, `is_SP_age`, and so which records have a State Pension type, reads it, while whether a type is basic or new reads the pinned birthday. Tests check the State Pension input case, the single-year dates and the multi-year dates. Represented ages use the anchor year's ONS shares and weights. Both are pinned in every year, and anything the model derived from the survey ages before is cleared (`demography._clear_derived`), so the model's own State Pension age (`is_SP_age`, by date of birth) and every reader of it in the engine (the State Pension age band, poverty, the age bands, coverage) see the represented ages. The survey's household and benefit-unit head flags are pinned too, so ties among represented ages cannot move a head.
- **Household weights.** In the anchor year and every year before it the weights are the dataset's own, exactly (`demography.annual_weights`): the rake never moves the calibrated weights and never runs back to the survey year. The anchor is the data build's calibration year, from its source (`datasets.ageing_anchor`: 2025 for the Enhanced FRS, `frs_release.py`; 2025 for the Microcosm primary, whose build solves its household weights at 2025 and writes them divided by policyengine-uk's own 2024-to-2025 projection, so the model's 2025 weights are the solved ones). After it, household weights are raked (bounded minimum relative entropy, ratios 0.2 to 5 of the anchor year's; a convex problem with one solution, which `demography.rake_households` finds by least squares on the calibration residual (the dual's gradient) and, where that stalls on a bound, by Newton or gradient steps on the dual) so that every sex and age cell (five-year bands to 59, single ages 60 to 79, 80-84, 85-89, 90+) grows from its anchor-year survey count as the ONS 2024-based UK principal projection's does ([ONS_PROJECTION.md](ONS_PROJECTION.md); fiscal year = 75% of mid-year *y* + 25% of *y*+1). Targets are survey counts times ONS growth, not ONS levels. Person and benefit-unit weights are their household's. A target the bounds cannot reach fails the run. A property test checks that, for any growth, the raked weights equal the dataset's own through the anchor year.
- **Cohort types.** Basic for men born before 6 April 1951 and women born before 6 April 1953 (State Pension age before 6 April 2016, by the Pensions Act 1995 Schedule 4 timetable: Pensions Act 2014 s.1(2)), new from those dates, none below State Pension age, from the birth date the represented age and birthday give at 6 October of each year. A test checks they equal policyengine-uk's own `state_pension_type` on the same ages and birthday in every year (on 2.120.0; part B's oracle tests passed on 2.118.0 too).

**Inputs held the same under both rules** (`engine.pinned_inputs`):
- **State Pension age.** The model's own: policyengine-uk sets it from each person's date of birth by the Pensions Act 1995 timetable, including the rise from 66 to 67 for people born from 6 April 1960 (#1899), and the engine reads it through `is_SP_age` and `state_pension_age`. Ages are held, so a record's date of birth moves a year later each year: 66-year-olds are partly over State Pension age in 2026-27 and 2027-28 and below it from 2028-29. Each run records the youngest age with anyone over it and the youngest from which everyone is (`fixed_inputs.state_pension_age`).
- **Pension type**, by the treatment's rule (above). Each run reads the types back from the model in every year, fails if anyone's differs, and records the counts (`held_pension_type_records`, `held_pension_type_people`).
- **The State Pension accounting, one rule under every treatment.** The reported State Pension counts only for people over State Pension age in the data year: none is payable before it (Pensions Act 2014 s.2(1)(a) and s.4(1)(a); SSCBA 1992 s.44(1); a survivor's inherited pension is their own from it, Pensions Act 2014 s.7(1)(a) and s.9(1)(a)). In the Enhanced FRS 40 records report State Pension below it, most of them within a year of it; two-fifths of them also report contributory ESA, which nobody over pensionable age can get, and two-thirds report earnings. They are reporting errors, and the model already paid them none; the data year's `state_pension_reported` is pinned without them (`demography.payable_reported`), and each run records how many there are and what they report (`state_pension_accounting`). In each year the counted report is split by that year's type at the type's data-year flat rate (`demography.pension_components`), as policyengine-uk's own formulas split it: the flat-rate part, which policyengine-uk scales by the flat rate, and the rest, the additional State Pension (SERPS, S2P and, on the new State Pension, protected payments, inherited amounts included), which the engine pins at its data-year amount grown by September CPI (published to April 2026, the path's after; never cut), for people over State Pension age that year. Historical policyengine-uk 2.120.0 and 2.125.1 scaled it by the flat rates' ratio (#1941). UK 2.147.2 includes #2336: upstream now uses September CPI from the data year. The engine retains its path-specific explicit input, which takes precedence over that formula; this is no longer described as a remaining correction to upstream law. Splitting the additional pension by each year's type is what keeps cohort types from paying anything twice: split by the survey year's type, a record moved from the basic to the new State Pension would be paid the band between the two flat rates inside its new State Pension and again as additional pension (part A measured £14.2bn in 2034-35 and £16.0bn in 2039-40). Every run checks, from the model, that in the data year basic + new + additional equals the counted report for every person (to £0.01) and nobody below State Pension age is paid, and that the additional pension is the pinned one under both rules in every year; tests check the same on a synthetic survey under every treatment, and that a 5% cut in the flat rates moves only the basic and new State Pension.
- **Pension Credit guarantee.** The standard minimum guarantee rises with May–July earnings (never cut), the minimum SSAA 1992 s150A requires; UK 2.151.0 still projects it by lagged calendar CPI because it lacks #2576. The engine's explicit earnings-linked override remains necessary and is the same under both pension rules. The OBR publishes no May–July earnings forecast, so on the central path the guarantee's April 2028–2031 rises follow its April–June average earnings growth, the triple lock's earnings proxy (`central.py`). A May–July projection can differ. On the October 2026 figures, September CPI sets April 2028's State Pension rise, so a lower May–July figure would make the guarantee's April 2028 rise smaller and leave the pension's unchanged. The results file's limitations give the figures.

**Age addition with a newer model.** When the installed model defines `state_pension_age_addition`, the engine takes the legislated addition out of the payable report before the flat-rate/additional split, matching `state_pension_reported_excluding_age_addition`: the report, age and BASIC type are the data year's, the legislated parameters come from the baseline when present, and the remainder is clamped at zero. At the reviewed #2340 head this is 25p a week from age 80, never uprated, using the model's annual 6 October age convention. policyengine-uk computes the separate addition for each simulated year. Only a positive data-year report below the addition needs an input override: the engine caps that year's addition at the payable report, because upstream's full £13 would otherwise exceed it; later years retain the model formula. Basic + new + additional + age addition then equals the payable report in the data year, and the age addition is the same under both rules, so its saving is zero. It appears separately as `state_pension_age_addition` in fiscal components, household calculations, breakdowns and coverage. With no such variable, including UK 2.125.1 and 2.147.2 (#2340 remains unmerged), the original three-part calculation and output schema apply. The reviewed names, pending-release audit and additional-pension input precedence are recorded in [REBUILD.md](REBUILD.md#pending-state-pension-patches).

**Re-typed pension level.** The default is `retyped_level="kept"`: a survey BASIC record assigned NEW in a later year retains its reported amount, split at that year's type's data-year cap. The `full_new` sensitivity raises only that re-typed record's flat-rate part to the full new State Pension rate under each policy. Additional pension follows the same CPI pin; the data year is untouched and its components still sum to the counted report to £0.01. This bounds the flat-rate part, not the total transitional entitlement or an estimated confidence interval.

The revised [Pensions Act 2014 s.4](https://www.legislation.gov.uk/ukpga/2014/19/section/4) sets entitlement; [s.5](https://www.legislation.gov.uk/ukpga/2014/19/section/5) and [Schedule 1 paragraphs 2–7](https://www.legislation.gov.uk/ukpga/2014/19/schedule/1) determine the rate. The pre-2016 foundation amount is the higher of the old-system and new-system calculations, with contracting-out deductions and revaluation, then post-2016 qualifying years are added subject to the cap/protection. [State Pension Regulations 2015 reg.13](https://www.legislation.gov.uk/uksi/2015/173/regulation/13) specifies ten qualifying years for transitional entitlement. These current revised texts were read on 5 October 2026. Inspection of the verified Enhanced FRS 1.56.16 HDF5 schema finds total `state_pension_reported` and private pension income, but no pre/post-2016 qualifying years, separate additional-pension history or contracting-out deduction. Today's reported total cannot reconstruct the Schedule 1 calculation. The law therefore does not settle a counterfactual amount for this static representation: the existing treatment stays the default and the full-rate treatment is a labelled sensitivity, requiring full model runs.

**Total-only control.** `total` uses one incidence margin: the number of persons in each household. Its target is the anchor survey population times the ONS total-population growth factor, with the same bounds, represented ages, fixed birthdays and survey-year types as `frozen`/`reweight`. `total − frozen` measures this population-total replacement through paired full model runs. `reweight − total` compares the age/sex cell-growth control with the total-only control; because the anchor survey's age/sex mix differs from ONS's, the sum of the cell-growth targets can imply a different overall total. That contrast therefore includes any resulting total difference. The part E pilot records `model_population_people_by_year` to expose it rather than claim a fixed-total age-structure comparison. Through the anchor every treatment retains the native weights.

**Possible matched-total follow-up.** The implemented `total_matched` option uses the exact sum of the age/sex anchored targets as its single margin: Σ_c S_c × P_c(y)/P_c(anchor), where S_c is the anchor survey count and P_c the ONS cell population. It otherwise shares represented ages, birthdays, survey-year types, bounds and native weights through the anchor. It could compare the age/sex margins at a shared aggregate target, but needs its own full runs and source-bound readback checks. That supplement was dropped from part E's closeout as a scope cut; part E reports the ONS total-only control above. No matched-total estimate is published.

**The Enhanced FRS calibration year's level.** This is a sensitivity/bridge caveat. The Microcosm primary's build divides its solved weights by the model's own projection factor (1.0072 from 2024 to 2025; microcosm#1095), so its 2025 weights are exactly the solved ones. The pre-Budget cross-check cut 5c6b3f68 was built before that change and stores its solved weights undivided, so its 2025 weights are the solved ones times 1.0072: every 2025 total 0.72% high. The Enhanced FRS builder calibrates its weights in 2025 and saves them to 2024 with its own weight index (2024: 1.027, 2025: 1.039); policyengine-uk uprates them back to 2025 by its population growth (0.72%). In a simulation the 2025 weights are therefore the calibrated ones times 0.9956: relative weights exactly the calibrated ones, every 2025 total 0.44% low ([policyengine-uk-data#538](https://github.com/PolicyEngine/policyengine-uk-data/issues/538)). Static ageing keeps the simulation's own 2025 weights, so it neither adds to the gap nor closes it; the fix belongs to the data build or the model.

**Private cache.** The population (represented ages, birthdays, the weights and the State Pension age mask and types of every year) is computed once per dataset, treatment, anchor, set of years and model (`demography.eligibility_fingerprint`: the installed policyengine-uk and the files its State Pension age and type come from) and cached under `.cache/demography`, owner-only; every path job shares one entry, and the coverage and history jobs, with other years, have their own. A run reads the model's own `is_SP_age` back against the cached mask in every year and fails if they differ, so a change to the model's State Pension age cannot reuse stale types. Nothing that depends on a path is cached: the additional pension follows each path's September CPI. No record id, weight or amount leaves the cache; an ageing run returns no single-record diagnostic, and a failed path, coverage or history job keeps its error output in an owner-only file in an owner-only worker directory instead of the build log (`jobs.private_inputs`).

**Programme limits.** The new State Pension has no age addition, but the basic State Pension has one, 25p a week at 80 (SSCBA 1992 s.79 and Sch 4 Pt III para 8), which the historical UK 2.125.1 bundle, the binding UK 2.151.0 model and the 2.147.2 fallback do not model ([policyengine-uk#2139](https://github.com/PolicyEngine/policyengine-uk/issues/2139)): in that bundle a reported one is in the additional pension. The version-aware handling above applies when a later bundle includes #2340. UK 2.151.0's Winter Fuel Payment and Scotland's Pension Age Winter Heating Payment (`pawhp`, in `other_spending`) use the shared winter-heating amount helper, unchanged from 2.147.2, with jurisdiction-specific eligibility and amounts. The Scotland formula distinguishes qualifying-benefit couples from non-benefit households and their shared amounts; the old £100-per-household limitation does not describe this wheel. On 2.151.0 the payment's amounts rise each April by `gov.benefit_uprating_cpi`, rounded to the nearest 5p (#2575). Later retirees' amounts come from today's records of the same age; deaths, migration and contribution histories are not simulated, and pensioners abroad are outside the survey. A dynamic projection is the longer-term route (PolicyEngine/microcosm-dynamics#501).

**Outputs of each run, by year:**
- gross saving (basic and new State Pension spending) and net saving (change in `gov_balance`), with the components, for the UK and for Great Britain (households in England, Scotland and Wales, as DWP's figures are; neither dataset has a household of unknown country);
- households losing more than £1 a year;
- poverty after housing costs;
- household tables for 2034-35 and 2039-40;
- individual-record and unsupported concentration diagnostics remain private and are omitted;
- the population treatment and its checks (`fixed_inputs`: `demography`, `population`, `ageing`, `state_pension_accounting`).

**Gross to net.** `gov_balance` is policyengine-uk's `gov_tax` less its `gov_spending`, each the household sum of its own list of variables (`GOV_TAX_VARIABLES`, `GOV_SPENDING_VARIABLES`). Each run totals every variable on the two lists (`engine.fiscal_variables`, which mirrors their formulas' council-tax-abolition conditional and splits State Pension into basic, additional and new, plus the age addition when defined), records the change in each, and groups them: the State Pension flat rate, additional State Pension, the age addition when defined, Pension Credit, Housing Benefit, Universal Credit, council tax reduction, Winter Fuel Payment, income tax, other spending and other tax. The model computes `gov_balance` household by household in float32, which leaves its total a few £1,000 off the float64 sum of the same variables (3.2e-6 £bn on the Enhanced FRS in 2026-27) and a change in it about 1e-6 £bn off. The run therefore takes the net saving as that float64 sum, so the components add up to it by construction (the recorded `decomposition_residual` is float64 rounding, about 1e-13 £bn). The test that the lists explain the model is against the model's own float32 `gov_balance`, recorded beside it: its level to 1e-4 £bn (£0.1m) and its change between the rules to 1e-5 £bn (£0.01m). A variable missing from the lists, or extra, fails the run if its total is over £0.1m a year or either rule moves it by over £0.01m; in the pilot runs the change agreed to 3e-6 £bn or better.

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

The binding release carries no expected value, because its primary failed C2. This section describes the estimator a passing build publishes.

The saving comes from years when CPI or the 2.5% floor runs ahead of earnings, so the saving on the expected path is not the expected saving.

1. **Draws.** 50,000 paths of a monthly VAR on log changes of the CPI index (D7BT) and AWE total pay (KAB9), fitted to 2000–2026 without the furlough months, with residual-bootstrap shocks (`ts_monthly.py`). Both the statutory and the calendar measures come from the same simulated months.
2. **Calibration.** The smoothest monthly drift path that makes the draws' mean calendar-year CPI and earnings growth equal the central path in every year (`ts_monthly.shift_to_calendar_means`, an equality-constrained least squares iterated to 1e-12).
   - Every draw moves by the same amount, so the shocks and their dependence are the model's own.
   - Only calendar-year averages are matched. The draws' mean statutory inputs sit off the OBR's quarterly figures in 2026-2028 (before the switch), and September 2026 CPI is simulated from August's rather than fixed at the published inputs.
   - Entropy tilting to the same means, the earlier approach, keeps about 1,000 effective draws of 50,000. A drift held constant within each year oscillates from year to year and puts spurious reversals into the statutory measures.
3. **Choice of calibration.** Tilting further to history's gap variance and lead-switch rate (`ts_methods.tilt_moments`) was tested in a chronological expected-value backtest over 12 OBR forecasts, and in a past-years check (a model fitted before 2011, scored on the plan started in 2012).
   - The shift alone had a bias within its standard error with April 2022 as in law, and about one standard error with April 2022 as published. The OBR point forecast had the largest bias under both.
   - The dynamics tilt made the bias larger and put the realised 2012-start gap at its 93rd percentile, against the 56th for the untilted model. The tilts are reported as sensitivities, reweighting the same runs.
4. **Historical sample, retained for reproducing the pre-Budget bundle.**
   - Draws on which the two rules pay the same every year save exactly nothing. They form their own stratum, and one is run to confirm it.
   - The rest are split into 10 strata of equal probability on the 2039-40 weekly gap. 200 paths are allocated by Neyman allocation (at least 2 a stratum) and drawn with probability proportional to weight.
   - Each is a full run of both rules. A 40-slot stratified subsample is paired on Microcosm.
   - Executing builds now use the selected form's **160-slot C1 handoff**, described below, rather than this historical 200-slot diagnostic route. They deduplicate replacement draws for full engine runs, add an identical-rates check, and preserve every slot's multiplicity in the estimator. The binding handoff's original-primary design has 159 distinct sampled indices and one extra check, hence 160 unique runs; the dry run's had 160 and 161. Its 40-slot sensitivity subsample (Enhanced FRS for d1983, Microcosm in historical releases) takes at least two slots in every sampled stratum, including stratum zero. Updated inputs and other forms can have fewer distinct runs than slots.
5. **Estimator.** Σ_h W_h ȳ_h. Historical committed results use only sqrt(Σ_h W_h² s_h² / n_h); new estimates add first-phase variance and report both components separately, as specified in the C1 rule below. The reweighted sensitivities and the paired sensitivity subsample rest on few effective runs in some strata, so their ± figures are approximate; the file reports each sensitivity's effective runs. Tests check that it is unbiased and that its interval covers about 95% of the time on synthetic cases (`tests/test_expected_value.py`). They also check that the committed file's estimates recompute from its per-path records (`tests/test_results.py`).

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
- Both rules are the triple lock until April 2029, so a specified triple lock before the switch is also what the adjusted Triple Lock pays, and the plan anchors its earnings path on the level that gives. A scenario can specify the adjusted Triple Lock's rate only from the switch; it replaces the plan's own rule that year, and later years run the rule from the level it leaves.
- `rate_sources` labels a specified year `specified` for that policy; before the switch the plan stays `triple_lock`.

A scenario is one full run of the central path with its specified rates, nothing else changed (`trajectories.SCENARIOS`). Every full build runs every scenario after the paths and writes each to `data/scenarios/NAME.json`, with the main results' provenance and record-level fields redacted, so one rebuild refreshes the results file and the scenarios together; `triple-lock-build --scenario NAME` reruns one alone (`pipeline.scenario`) and leaves the results file alone. Tests recompute its rates from the inputs it records, check that it holds the same fixed inputs as the central run, and fail once any source, input or engine file has changed since the run.

**The OBR wedge (`obr_premium`).** The triple lock pays the 'Triple lock' row of the OBR's long-term economic determinants (March 2026), its value for the fiscal year of the inputs paid the next April, from April 2032, the first rise whose inputs the central path takes from those determinants. April 2027 is set by published inputs (May-July 2026 AWE), and the Aprils 2028 to 2031 follow the October 2026 outlook (d2124), so to April 2031 both rules pay the central path's rates. For the fiscal years 2027-28 to 2030-31 the row is 2.5%, the March 2026 forecast, which the October outlook supersedes: on the October path, September 2027 CPI (3.382%) sets April 2028's rise at 3.4%. The adjusted Triple Lock therefore anchors on the central path's 2029-30 level and pays the central path's rates in every year. From 2033-34 it is, in the OBR's note, average earnings growth plus 0.6 points (0.56 above the fiscal-year earnings growth the central path uses), phased in over the two years between. The 0.6 points is the OBR's stylised allowance for the years CPI or the floor beat earnings, an average-rate assumption: no CPI and earnings path pays it every year, so the run is a comparison with the OBR's costing convention, not a forecast. Only the triple lock gets the premium. The plan runs its own rule from the switch, on the central path's CPI and earnings, so it gets no credit for the volatility that sets its own floor. Spending is the aged survey bill (static ageing, above), for the UK, where DWP's figures are for Great Britain.

## Datasets and DWP

`dwp.py` reads DWP's spending and caseloads (Spring Forecast 2026, Great Britain) for 2026-27 to 2030-31, where its tables stop, and its uprating analysis. DWP estimates £15bn of annual nominal GB direct AME savings in 2039-40 using Pensim3. These savings exclude tax and debt-interest effects. Its published assumptions do not establish a single path or a distribution comparable with our probability-weighted estimate; [DWP's analysis](https://www.gov.uk/government/publications/state-pension-uprating-analysis-2026/state-pension-uprating) and [HL3774 (answered 15 October 2026)](https://questions-statements.parliament.uk/written-questions/detail/2026-10-05/hl3774) do not permit a like-for-like comparison. HL3774 says the analysis did not use single-year earnings or prices-growth assumptions.

**Coverage.** One coverage job per dataset runs the central path under the triple lock, as the central run's triple-lock policy does (the same population treatment), for 2026-27 to 2030-31, 2034-35 and 2039-40. It gives each year's State Pension (by part, recipients and types, and in Great Britain by age, where every cell rests on at least ten records), Pension Credit (guarantee and savings credit, and claims), Housing Benefit and pension-age Housing Benefit (spending and claims), council tax reduction and Universal Credit, for the UK and for Great Britain. The results set Great Britain against DWP, like for like, in every year DWP's tables give. Pension-age Housing Benefit is Housing Benefit paid under the pension-age regulations (`housing_benefit_pension_age_regulations_apply`), nearest DWP's "over Pension Credit qualifying age". 2034-35 and 2039-40 have no DWP figure.

The population here is the path runs': static ageing, ONS growth after the dataset's anchor year and cohort pension types. Both the Microcosm primary and Enhanced FRS anchor at their 2025 calibration year. Ages above 80 demonstrate that a dataset is not top-coded there and are retained. The deterministic synthetic ordering key matches the model's 64-bit-id to 32-bit wrapping without publishing identifiers. The State Pension age follows the law's timetable by date of birth, so every age of 67 and over is above it from 2028-29. DWP's figures come from its own projection of the population and of contribution records; matched by-type, by-age and post-2030 benchmarks are unavailable (part B's [AGEING_PILOT.md](AGEING_PILOT.md) lists them).

## The certified model and the historical pilot (`datasets.py`)

For the binding rebuild, the primary registry entry is `microcosm_uk_2024_25@a6299504`. It pins `policyengine/populace-uk-private`, expected revision `microcosm-uk-2024-25-national-20261025T091414Z-a6299504`, path `microcosm_uk_2024_25.h5`, SHA-256 `b96a8cd625b645a409c063b1de5158532708a2f0d3c3897a794a8fb0bbd5064e`: the bytes of the staged attempt `uk-frs-calibration-attempt-20261025T091414Z-a6299504`, built at microcosm `67ee2ddf3`. That revision exists on the Hub with those bytes (checked on 26 October), and materialization verifies them before every use. The model wheel is UK 2.151.0, SHA-256 `5722f55aca3eb88e1a228e95e1a57e3bd70a4d530a5a000991565ebd8955ce35` (microcosm#1396's `uv.lock`; attested in `data/certification/d2011-model-wheel.json`), with core 3.33.3. The pair's released carrier also routes constituency and local-authority runs to its local-area cut, and the registry requires exactly that cut: its file, tag and SHA-256 in the bundle's `datasets` entry, its release manifest's URIs (and digest, where the bundle records one), and no `regional_certification`, since both halves are on 2.151.0. The certificate must cover core 3.33.3 by a rule stricter than policyengine.py's: under `core_binding` `certified` the named core, which must equal the bundle's core pin; under `bundle_pin` the pin, which a named core must equal. The released carrier is policyengine.py 6.11.1: its manifest SHA-256 `ab60903b…`, certifying pull request #720 and merge commit `610ebc42…`, and the local-area cut `microcosm-uk-2024-25-dense-20261026T105309Z-c9df4b86` (file `microcosm_uk_2024_25_dense.h5`, SHA-256 `cb3712f2…`, release manifest SHA-256 `30be4754…`) are pinned in `datasets.BINDING_*`, and `datasets.provenance` and the publication preflight certify only that installed release; a released-manifest certificate also needs its certifying pull request and commit. #715's `microcosm_uk_2024_25@a133f37a` / UK 2.147.2 entry stays registered as d2011's fallback. #715's candidate routes national only, but d2011's fallback adds #699's area routing to the 19 October dense cut (`ee5c2dbe`, built on 2.132.6), so the entry pins that cut and requires #699's record of the accepted mismatch; its bundle identities stay pending.

The lock installs base `policyengine==6.11.1`, the released carrier, plus exact `policyengine-uk==2.151.0` and `policyengine-core==3.33.3`, without `[uk]`. While the release was pending it installed `policyengine==6.10.1` (`datasets.PREPARATORY_CARRIER`), whose extra pins its previous UK line; 6.11.1's extra pins the pair's model and core, and the lock still omits it. The engine constructs `policyengine_uk` directly and materializes its own registry-pinned dataset rather than asking that extra to select the data. `scripts/fill_release_identities.py` filled only the authenticated identities left unset in `datasets.py`, and the carrier version in the lock and ready bridge config, from the 6.11.1 tag; the lock was then re-resolved for that carrier, moving only `policyengine` ([REBUILD.md](REBUILD.md)).

The designated paired sensitivity is Enhanced FRS 1.58.2: d1727's salary-sacrifice/uprating-table fixes and preserved household ids through cloning. Enhanced FRS 1.58.0 remains for bridge step (a). The pre-Budget release's `policyengine[uk]==6.2.6` / UK 2.125.1 / core 3.33.0 / Enhanced FRS 1.58.0 identity and historical receipt bytes remain as published; [J-certification](pilot/J-certification.md) retains their hashes. The [2.125.1-to-2.147.2 source audit](d1983-upstream.md) records the reviewed upstream guards. #2019, #2507–2509, #1913, #2336, #2458, #1831, #2518 and #2516 are present; #2557 and #2576 are absent, and #2340 remains unmerged. The behavioural HB passport preflight remains mandatory. #36's separate [2.153.4 audit](d1727-upstream.md) and fail-closed qualification-ledger implementation remain history; they do not authorize this primary.
The remainder of this section records the pilot's version history, rather than the current bundle.

At the pilot checkpoint, no policyengine.py release bundle carried the pensioner fixes this analysis needed: 6.2.1 pinned policyengine-uk 2.102.3, and its import failed beside 2.118.0 and later, because its data certification found no release certified for the installed version. The pilot therefore pinned policyengine-uk 2.120.0 (and policyengine-core 3.32.16) directly. The engine loaded each dataset itself, pinned to a revision and a SHA-256 and hashed before every use, as policyengine.py's managed loader did:

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

**From 2.118.0 to 2.120.0** (both released on 5 October 2026; 2.120.0 was the pilot's latest release), as their changelogs record them. Every Fixed entry is a fix to the law; the Added entries (`date_of_birth`, the date parameters, `is_uc_assessed_claimant`) serve those fixes, and the Changed one (`birth_year`) follows from them. So the pin moved to 2.120.0 without a methodology choice:

| Change (policyengine-uk) | Moves | The engine relied on the old behaviour? |
|---|---|---|
| `date_of_birth` from age and the birthday, and every date-of-birth rule read through one birth instant (2.119.0). For survey data, with no `date_of_birth` input, State Pension age and type come from the same instant as in 2.118.0 | nothing for the engine | No: `cohorts.birth_dates_from_age` matches it (tested), and the upstream guard (`model_horizon.UPSTREAM`) now covers the moved files |
| The Pension Credit mixed-age couple saving by date of birth: the older member born on or before 5 February 1954 (SI 2019/37 art 4); the Universal Credit and Child Tax Credit child limits and the Pension Credit first child addition on 6 April 2017 by date of birth (2.119.0) | Pension Credit for mixed-age couples; child elements | No |
| `birth_year` is the calendar year of the date of birth (2.119.0); no rule reads it any more | nothing | No |
| Universal Credit counts only the claimants' income, not their dependants' (UC Regs 2013 reg 22(1); 2.120.0) | Universal Credit baseline and offset | No |

Part A's version bridge rerun on 2.120.0 is retained as aggregate pilot evidence in [data/pilot/version_bridge.json](../data/pilot/version_bridge.json), with its calculation commit and model/data versions. It is an uncertified-pair pilot, not for quoting; [MODEL_V2_PILOT.md](MODEL_V2_PILOT.md) records the publication-support audit status. The pre-Budget release subsequently used core 3.33.0; the binding successor must authenticate d2011's exact released UK 2.151.0 / core 3.33.3 pair, or on fallback a133f37a's UK 2.147.2 / core 3.33.3 pair ([REBUILD.md](REBUILD.md)).

The pilot-time open issues included #1927 (the Housing Benefit guarantee credit passport keyed on receipt), #1925 (benefit rates at announced amounts), #1913 (pension-age Housing Benefit allowances by cohort), #2019 (Pension Credit earnings disregards), #1941 (the additional State Pension's uprating), #2138 (Scotland's Pension Age Winter Heating Payment from winter 2025) and #2139 (the age addition). Their certified-port status is recorded in [J-upstream](pilot/J-upstream.md); #1927 is included in 2.125.1.

## The four-way ageing design (`ageing_validation.py`)

What represented ages, the ONS reweighting and cohort types each do to the saving, alone and together, on paired full runs (#14 section 3). Every validation job is an ordinary engine job with the path's `demography` set: the central path and the rebuilt expected value's exact 40 paired draw slots (Enhanced FRS sensitivity for d1983), each under `legacy`, `frozen`, `reweight`, `types`, `both` and the `total` population-only control. With forty distinct paired indices, this is 246 path-job labels plus six coverage jobs (252 labels); repeated draw indices reduce the unique path jobs. If the 41 `both` paths are already cached by the build, validation adds 205 path jobs and six coverage jobs (211). Under d955 ruling (a), the rebuilt file has no expected-value section: `--central-only` runs six central paths and six coverage jobs, adding eleven if the build's central `both` path is cached. The frozen/reweight/types/both factorial remains four-way; legacy and total are controls.

```sh
python scripts/validate_ageing.py --plan                                   # job counts and the paired draws
python scripts/validate_ageing.py --workers 1 -o .cache/ageing_validation.json
# Under d955 ruling (a), use --central-only because no expected-value subsample exists.
```

Contrasts are computed within each path, then averaged over the strata (`expected_value.stratified_estimate`, with the committed stratum probabilities and both the path-sampling and first-phase variances); the identical-rates stratum saves exactly nothing under every treatment:
- `reweight_effect` = reweight − frozen, `types_effect` = types − frozen, `combined_effect` = both − frozen;
- `interaction` = both − reweight − types + frozen, the four-way term;
- `common_input_effect` = frozen − legacy, the represented ages and birthday.
- `population_total_effect` = total − frozen; `reweight_minus_ons_total` = reweight − total. The latter can combine age-structure and population-total changes because the two controls can imply different totals; it is not labelled an isolated age effect.

The report holds savings for the UK and Great Britain, State Pension against DWP's matched GB totals (2024-25 to 2030-31), and GB State Pension by age, withheld whole across treatments if any cell in any is suppressed. The validation now runs on the configured Microcosm primary. Use one worker until current-cut memory is measured; the CLI's historical worker cap does not establish capacity. Historical pilot timings are not a final-head runtime measurement.

The separate part E pilot runs six treatments—frozen/reweight/types/both/total and `both_full_new`—on its central path and the original part D forty distinct paired indices. It also has 246 full path-run labels and six coverage jobs, but executes the paths as 41 same-path six-treatment batches, for **47 execution jobs**. Each treatment still computes both policies in full; retained part D values are comparison evidence, not reused inputs or fiscal outputs. Use at most three Enhanced FRS workers while available RAM is at least 40 GiB and load is below about twice the CPU count (about 36 on this 18-CPU host); otherwise use fewer. Its chosen years restrict publication, not calculations.

The matched-total recipe (`scripts/run_model_v2_matched_total.py`) remains available as a possible follow-up, outside part E's closeout. Its treatment is not part of the ordinary six-mode validation or the published E evidence. Any later execution needs its own full runs, population-target readbacks and source-bound reference checks; independent full-run comparisons must state a float tolerance rather than require bit equality unless head, inputs and cache are shared.

The full-new country support receipt counts positive-weight re-typed records whose stored flat amount actually changes under the bound. A re-typed amount already at the full new rate does not support that contrast. The engine compares the existing kept/bounded arrays at the model variable's stored precision, without additional model calculations. `scripts/run_model_v2_e_coverage.py` supplies six fresh coverage jobs at the corrected support head; it calculates all nine requested coverage years, records its separate source/data/package hashes, and replaces the old coverage block only after every treatment and country support receipt is complete. It runs no fiscal path job.

Part B ran the original five-mode design (legacy plus the four factorial treatments) on policyengine-uk 2.90.2 with its own worker and publication guard; its approved output is the record (`data/ageing_validation.json`, rendered as [AGEING_PILOT_RESULTS.md](AGEING_PILOT_RESULTS.md) by `scripts/report_ageing_validation.py`; [AGEING_PILOT.md](AGEING_PILOT.md)). The integration replaced the worker with the engine's own jobs, so the four-way runs and the published runs are one implementation of the fiscal totals, and retired the guard, which certified that one run on the retired engine. Part E adds the total-only control.

The Spring 2026 DWP workbook covers GB plus overseas, excluding Northern Ireland. Only its all-type State Pension spending and caseload separate the overseas amounts; subtracting those gives matched GB totals through 2030–31. Published basic/new amounts are GB plus overseas context, not matched benchmarks, and the workbook gives no State Pension forecast by age or country, so those comparisons are unavailable, as is everything after 2030–31; no benchmark is extrapolated or allocated.

The separately published regional outturn table supplies combined State Pension spending for England, Scotland and Wales in 2024–25 as context. It does not supply the requested basic/new split or financial-year annual recipient counts, and its guidance excludes forecast years. Those country benchmarks remain unavailable; the source tables, exact cells and hashes are recorded in [country_benchmark_availability.json](../data/pilot/country_benchmark_availability.json) and [country_benchmarks.json](../data/pilot/country_benchmarks.json). No combined expenditure is split and no quarterly caseload is treated as an annual financial-year mean.

The historical sampling descriptions below and the frozen C1/C2 handoff call the 40-slot sensitivity “Microcosm-paired”. Under d1983 only its dataset role changes: those identical slots now run on Enhanced FRS 1.58.2. Slot selection, strata, multiplicities, seeds and the frozen source remain unchanged; regenerate a current handoff through the registered C2 route after the authorized config change.

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

**Recorded method input (part E, post-scoring implementation).** Max selected
**d955(c)** on 5 October: a new statutory screen uses the suspended April 2022
earnings treatment and excludes cells that are zero by construction. Part F will
write and publish that pre-registration before the binding post-Budget re-score;
part E does not implement the new screen. If the primary passes, its expected value
is labelled **model-conditional** beside the **scenario envelope**. If it fails,
fall back to (a), retaining central and mean-path scenarios without expected value.
The adapter keeps the explicit recorded `uncertainty_ruling` input; `None` refuses
execution and names d955. Its tested (b) route retains the original primary's failed
screen and model-conditional label, but is not the selected rebuild route. Existing
treatment-only (c) tests verify the adapter branch, not the future statutory screen.
Mean-path scenarios remain independently runnable. Their zero-stratum and all
fiscal-output paired differences are retained.

**Implementation update, 6 October 2026 (part F).** The historical part E
treatment-only (c) branch described above is superseded by the frozen C2
handoff below. The adapter reads its committed rule SHA and binding-data
provenance, runs only a passing original primary, and automatically records
(a) when that primary fails. It does not re-score or choose another form.

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

## Model v2 statutory uncertainty screen: pre-registration (C2)

Pre-registration commit: `65343e2ee43a359f056ce5a027739509d32ab49f`,
pushed to `model-v2` before C2 implementation or scoring. This SHA annotation is
a follow-up record; the frozen section below is unchanged from that commit.

The portable execution binding is SHA256
`ce198c838070b175cecefb668b776731333373c8e642030456f736978eb336ac`
of the exact 5,114 UTF-8 bytes between the begin and end markers, including the
newlines immediately inside them. The adapter compares those bytes with the
committed hash; it does not retrieve an old commit to execute the screen.
Score/handoff input hashes bind the current committed data and source files.
Pre-registration and scoring commit IDs remain provenance only, so a shallow
checkout or squash merge does not remove an executable binding.

The annotated tag `c2-preregistration` retains the original rule commit after
the working branch is deleted. To audit that registration preceded scoring,
fetch the tag, verify its target, inspect the committer dates, and recompute the
marked section's content hash:

```sh
git fetch origin tag c2-preregistration
git rev-parse c2-preregistration^{commit}
git show -s --format='%H %cI %s' c2-preregistration
# Inspect the first implementation when that history is retained locally.
if git cat-file -e '67b10d3^{commit}' 2>/dev/null; then
  git show -s --format='%H %cI %s' 67b10d3
fi
git show c2-preregistration:docs/METHOD.md > /tmp/c2-preregistration-method.md
python - <<'PY'
from pathlib import Path
import hashlib
content = Path('/tmp/c2-preregistration-method.md').read_bytes()
marker = b'<!-- C2 frozen rule '
section = content.split(marker + b'begins -->', 1)[1].split(marker + b'ends -->', 1)[0]
print(len(section), hashlib.sha256(section).hexdigest())
PY
```

The tag's target is `65343e2ee43a359f056ce5a027739509d32ab49f`. Its
committer date is 6 October 2026 07:14:07 UTC; the first C2 implementation
commit `67b10d3` is dated 07:27:22 UTC that day and is later in the same history.
The registration changed `docs/METHOD.md` alone. In a checkout where later
scoring commits were squashed away, the tag still permits checking the original
registration bytes, target and date; the published scoring heads and dates are
the corresponding provenance record. A merge commit for #24 is recommended
to retain that complete history on main. The merge method remains Max's call.

<!-- C2 frozen rule begins -->
This is the new rule required by Max's d955(c) decision of 5 October 2026.
Commit and push this section alone before any C2 scoring or implementation;
record that commit's SHA separately afterwards. It is an adequacy screen for
statutory behaviour, not evidence of calibrated predictive probabilities.

**Disclosure of the change after scoring.** All five forms failed C1's common
coverage gate on test A with published earnings: terminal coverage was 1/6,
driven by the 2021 furlough base effect. There were additional candidate-specific
failures, retained in the C1 record. This rule was changed after those scores
were seen. The reason is that the analysis models statutory behaviour, and
Parliament suspended the earnings leg for April 2022. The original C1 rule,
scores and failures remain in the record; C2 does not turn C1 into a pass.

**Treatment and legal exclusion.** Score April 2022 as the law applied it:
for its determination year, replace earnings with CPI in both forecast draws
and outturns. More generally the legal regime supplies the determination years
whose earnings leg is suspended; the scoring rule must work for any such year.
Exclude from coverage, bias and proper scores every statistic cell whose
forecast and outturn are both fixed by that legal rule, rather than choosing
cells from their numerical values. Under the C1 origins this removes the
determination-year 2021 earnings-minus-CPI cell from each window containing it:
four of test A's 24 annual gap cells. Pool the remaining annual cells with equal
cell weight (20 in test A), retaining per-origin rows, counts and overlap SEs.
Apply the same exclusion to annual gap CRPS and annual gap bias. Do not exclude
an accidentally zero draw or observation. The suspended year's CPI level,
earnings-below-floor indicator and joint CPI/earnings components are not fixed
by law and remain scored. Joint energy and variogram scores retain their C1
components and pairs unless a component is itself fixed by law.

Terminal policy gaps spanning a suspended year retain that year in the complete
compounded policy path, with earnings equal to CPI in both draws and outturns.
They remain scored when other uncertain years or CPI/floor effects make them
nonconstant; a whole statistic fixed by the legal rule would be excluded, with
its denominator disclosed. No suspended year is deleted from policy arithmetic,
lead-switch counts or floor fractions.

**Unchanged C1 thresholds and design.** Keep the five C1 candidates, fits,
pre-origin training boundaries, mean shifts, test A chronological and test B
all-complete spring origins, score definitions and descriptive SE conventions.
These forms share means and much of their residual pool and are not independent
tests. Keep the annual form's existing block alignment; C2 does not repair or
promote it after seeing scores. Apply every C1 threshold to **suspended treatment
only**, in both tests: annual and terminal central-80% coverage in [0.50, 1.00];
the descriptive terminal-coverage 95% Wilson band containing 0.80; absolute
gap bias at most 1.5 percentage points, switch bias at most 1.0 per four-year
path and floor-fraction bias at most 0.25; each of the five proper scores no
worse than 1.25 times the original primary for that test/treatment (zero
reference permits only zero); the uncalibrated pre-2011 past-years realised
terminal gap within the 5th–95th percentiles; finite paths and scores, complete
origins and successful fits. No other threshold changes.

**Sensitivity, primary and automatic fallback.** Report published-earnings
scoring beside every C2 result, including the past-years check, as a sensitivity
with no influence on the C2 verdict. The original monthly VAR(1) residual
bootstrap stays primary if it passes C2. Never promote another form on C2 scores;
report passing alternatives individually and never average forms. Only a
passing primary permits an expected value, labelled **model-conditional** and
shown beside the **scenario envelope**: the central path, OBR wedge,
last-decade replay and paired −0.5/+0.5 percentage-point earnings mean paths.
If the primary fails C2, the build automatically takes ruling (a): no expected
value, scenarios only, recording the failure and fallback without another
method choice. Monte Carlo precision stays separate from that envelope.

**Binding data and handoff.** The binding C2 score uses September 2026 CPI,
May–July 2026 AWE, and the OBR's Budget-day (28 October 2026) forecast means,
plus every forecast origin those inputs make complete. Re-score after the
Budget inputs are committed. A run on earlier inputs is a **dry run** and must
be labelled so throughout; it cannot authorize a binding rebuild. Record the
screen name, pre-registration commit SHA, data hashes/vintage, run status and
C1 failure in the handoff and results provenance. Refuse a handoff with a rule
SHA different from this committed pre-registration. The certified policyengine.py
bundle authorized by d778 follows the uk-data batch d833 and is required for
the fiscal rebuild. No PolicyEngine runs or survey data enter this screen.
<!-- C2 frozen rule ends -->

## Forward publication rule and prospective test: pre-registration (C3)

The section between the markers below registers C3. The binding 28 October 2026 release does not use it.

Pre-registration commit: `bd6fdbb20913fb223fdffa0966490f7b817fb59f`, the merge of #52 to main on 1 November 2026 under Max's d2247 ruling. Its second parent, `999635adbd3c9609406eb06adb7321e528093402`, holds the same frozen bytes and is the head the final independent review approved. This annotation is a follow-up record; the frozen section below is unchanged from that commit.

The binding is SHA256 `04d32a12fac7c2c27fe46d7e3a74dcaa9e2ab4060f984a299138d986363b0095` of the exact 12,525 UTF-8 bytes between the begin and end markers, including the newlines immediately inside them. `tests/test_c3_registration.py` compares those bytes with that hash.

The annotated tag `c3-preregistration` retains the registration commit after the working branch is deleted. To audit it, fetch the tag, verify its target and date, and recompute the marked section's hash:

```sh
git fetch origin tag c3-preregistration
git show -s --format='%H %cI %s' 'c3-preregistration^{commit}'
git show c3-preregistration:docs/METHOD.md > /tmp/c3-preregistration-method.md
python - <<'PY'
from pathlib import Path
import hashlib
content = Path('/tmp/c3-preregistration-method.md').read_bytes()
marker = b'<!-- C3 frozen rule '
section = content.split(marker + b'begins -->', 1)[1].split(marker + b'ends -->', 1)[0]
print(len(section), hashlib.sha256(section).hexdigest())
PY
```

The tag's target is `bd6fdbb20913fb223fdffa0966490f7b817fb59f`, with a committer date of 1 November 2026 16:45:51 UTC. No C3 implementation or scoring commit precedes it.

<!-- C3 frozen rule begins -->
This rule carries out Max's d2202 ruling of 31 October 2026. We froze this section before any C3 implementation or scoring, and before anyone computed the δ or the targets it defines. It governs future releases only. The binding 28 October 2026 release stays scenarios only under C2, and the two paired mean-path averages on its dashboard stay as Max approved them.

**What we had already seen.** All five forms failed C1. C2 changed the rule after those scores, and the original primary then failed one C2 check: test A floor-fraction bias 0.267 against a limit of 0.25. Before writing C3 we saw every form's C2 scores and unpublished exploratory averages under several reweighting targets. So C3 does not claim blindness to how a target moves the saving. It stays blind to outcomes: the newest statutory inputs anyone has seen come from determination year 2026 (May–July 2026 AWE and September 2026 CPI). The exploratory averages stay unpublished and set nothing here.

**Scope.** A future release is any release whose central path uses an OBR forecast published after the 28 October 2026 EFO.

**Forward policy.** Every future release publishes two averages of the primary's draws, whatever C2 and C3 show: the equal-weight average and the calibrated average below.

- Each carries the label **model-conditional sensitivity**. It may carry **model-conditional estimate** only while it holds a C3 pass. The test decides that one word: the figures, their place on the page and their caveats stay the same either way, and a failed test never withdraws a figure.
- Both averages sit beside the scenario envelope, with Monte Carlo margins that say they measure sampling alone. The paired mean-path averages keep the sensitivity label and take no C3 verdict.
- No release calls either average central, likely, typical, expected or a forecast.
- C3 covers averages alone. It authorises no percentile, no range and no statement about how likely a path is.
- For future releases this replaces C2's automatic scenarios-only fallback. Each release still re-scores C2 on every complete origin and prints that verdict beside the averages.

**Form.** The original monthly VAR(1) residual bootstrap stays primary and supplies both averages. No score promotes another form: the five forms' binding test A floor biases span 0.243 to 0.275, each with an overlap SE of about 0.10, so that test barely separates them. Forms are never averaged.

**Calibration rule.** One number, δ, carries the model's log-odds error on the statistic that failed: earnings growth strictly below 2.5%, unrounded, as `ts_backtest.candidate_score` defines it, with suspended years treated as in C2.

1. Take every complete spring origin (`ts_backtest.complete_statutory_origins`) and the primary's C2 draws for it: the same fit, training boundary, 5,000 draws and seed. For each origin and determination year, p is the share of draws below 2.5%, and y is 1 if the outturn fell below 2.5% and 0 if not. Throughout, clip a share of n draws to [1/(n+1), n/(n+1)].
2. Solve Σ expit(logit p + δ) = Σ y over all cells, each with equal weight.
3. From the release's 50,000 draws, take p_t for each determination year t that sets an April uprating from 2030 on. Each year's target is expit(logit p_t + δ).
4. Entropy-tilt the equal-weight draws (`ts_methods.tilt_moments`, with the `mean` and `floor_share` scales of `expected_value.SCALE` and tolerance `expected_value.TILT_TOL`) to hold every OBR calendar-year mean and to make each such year's weighted share of draws below 2.5% equal its target. The tilt targets nothing else.

Each release prints four statistics of those years before and after the tilt:

- (a) mean annual earnings variance: the mean across years of Σ w_i (x_i − μ)² over draws, for earnings growth x_i and μ = Σ w_i x_i, with w_i = 1/50,000 before the tilt and the tilted weights, summing to one, after it;
- (b) within-path gap variance: the weighted mean across draws of `expected_value.moments`' `gap_variance`;
- (c) lead-switch rate: the weighted mean across draws of `moments`' `switch_rate`;
- (d) CPI–earnings correlation: the mean across years of their correlation across draws, built from weighted moments of the same form as (a).

If every y equals 0 or every y equals 1, δ has no solution. If δ has no solution, the tilt fails, its Kish effective size falls below 500 (`expected_value.MIN_ESS`) or any of (a) to (c) moves by more than 10% of its untilted value, that release publishes the equal-weight average alone and says why. The correlation takes no limit, because a proportional limit means little on a value near zero.

Each release also prints δ, the cell count, Σ y, each year's target, the effective size, the largest tilted weight and a 95% interval for δ. The interval uses 10,000 resamples of the determination years with replacement (`numpy.random.default_rng(20261031)`). Each resample takes every cell of each drawn year, once for each time it drew that year, and solves for δ again. A resample with no solution counts as an infinite δ of its sign. Sort the values, drop the 250 lowest and the 250 highest, and the interval spans the rest.

δ moves the model's floor probabilities in log odds, so each target depends on today's forecast means, as a historical rate would not. It has one parameter because thirteen origins cover only sixteen determination years. It pools every complete origin, so it needs no choice between tests A and B. It never reads the saving. It assumes the same error holds in every year and every economic regime, and that the error at one to four years ahead carries to later years. No complete origin can test the last of those, and sixteen years cannot establish the rest. An entropy tilt that holds means can also narrow the earnings distribution, hence the limit above. We chose that 10% limit without seeing any outcome it depends on.

**Estimators.** The equal-weight average keeps the C1 estimator, 160-slot design and seeds. For the calibrated average, keep the design's strata and write w_i for each draw's tilted weight, summing to one, and g_i for its gap in the year between the two rules' pension levels (`expected_value.rule_levels`). A year with no gap in any draw saves nothing and needs no fit. Otherwise fit gross = κg and net = S(g) = ag + bg² by ordinary least squares, unweighted, over the distinct sampled draws with a nonzero gap, each counted once. A year with fewer than two distinct nonzero gaps gets no calibrated average.

- **Gross.** The average is Σ w_i κ g_i over all 50,000 draws, with variance Σ w_i² (κ g_i − average)².
- **Net.** The average is Σ w_i S(g_i) over all 50,000 draws plus Σ_h W_h r_h. W_h is stratum h's tilted mass. Over h's n_h sampled slots, a repeated draw counting once per slot, r_h = Σ ρ_j e_j / Σ ρ_j, where e_j is the slot's net saving less S(g_j) and ρ_j is its tilted weight times 50,000. A stratum in which every gap is zero has r_h = 0.
- **Net variance.** Add two terms. The first-phase term comes from `expected_value.stratified_estimate`, called as `expected_value.reweighted` calls it: each stratum's tilted mass, with the mean and variance of its slots' net savings from `expected_value._weighted_moments` under weights ρ_j, over the tilt's Kish effective size. With equal weights it equals C1's term. The path-sampling term is Σ_h W_h² [n_h/(n_h − 1)] Σ ρ_j² (e_j − r_h)² / (Σ ρ_j)². Both variances condition on the fitted weights and surrogates. Margins are ±1.96 standard errors.

Three gates apply. The largest absolute residual of the gross fit across full runs must not exceed 0.001 in `saving_bn` units. With equal weights in place of the tilt, each route must land within the C1 estimator's ±1.96 total Monte Carlo SE. And the slots must keep at least 100 effective runs, as `expected_value.reweighted` counts them, the limit C1 set for any quoted reweighting. If a gate fails for a year, that release publishes no calibrated average for that year and says why. These gates read fiscal outcomes only from sampled runs, so a heavily tilted draw that no slot sampled could bias the net average beyond its margin without tripping one.

**Prospective test.** A cell joins the test if its determination year is 2027 or later and a spring origin forecast it one to four years ahead. Forecast means for origins March 2023 to March 2026 come from the committed `data/raw/Historical_official_forecasts_database_Spring_2026.xlsx`, and those for later origins from each spring EFO. Everything else follows C2 unchanged: fits that stop in the December before the origin, 5,000 draws, the origin's seed, mean shifts, suspended-year treatment, legal exclusions, score definitions and latest-vintage statutory outturns. The past-years check stays out, because it uses only years we have seen.

The calibrated figure's draws take a tilt built by steps 3 and 4 on the origin's own four years. Each origin uses the δ from the origins complete when its EFO appeared, except that origins March 2023 to March 2026 all use the δ from the thirteen origins complete at this registration. So no cell uses a δ fitted to its own outcome. To score, draw 5,000 paths with `ts_methods.resample(draws, weights, 5000, seed)`, seed the origin's year, and pass them to `ts_backtest.candidate_score` as equal-weight draws, so one scorer serves both figures. A tilt that fails at any origin, or leaves an effective size below 500, fails the calibrated figure's test.

C2's thresholds apply unchanged, under suspended treatment:

- across all cells, with equal weight: annual central-80% gap coverage in [0.50, 1.00], absolute gap bias at most 1.5 percentage points, and absolute floor-fraction bias at most 0.25;
- across origins whose four years have all joined the test (March 2026 onward): terminal central-80% coverage in [0.50, 1.00], with its descriptive 95% Wilson band containing 0.80, and absolute switch bias at most 1.0 per four-year path;
- for the calibrated figure alone, across those same origins: each of the five proper scores at most 1.25 times the equal-weight primary's;
- finite paths and scores, successful fits and no missing cell. If the OBR publishes no spring forecast in a year, that origin drops out and the release says so.

**Verdict.** A figure passes if it meets every threshold once all eight determination years 2027 to 2034 have joined the test. That cannot happen before October 2034, when September 2034 CPI appears. Until then each release prints the scores so far, says "no verdict", and labels both figures sensitivities. From then on, each release re-scores every cell and the label follows the latest verdict, so a pass can lapse.

**Why eight years.** Simulated outcomes from the primary's own draws show how little a few years can say (`scripts/c3_operating_characteristics.py`, `docs/uncertainty/c3-operating-characteristics.json`, which holds every span from four to twelve years). On the checks both figures share, a correct model passes 36% of the time on four years, 68% on eight and 86% on twelve. A model that states double the true floor rate passes 35%, 43% and 64%. So four years cannot tell those two apart. From six years on the gap between them holds at 21 to 28 points, so eight sets no statistical minimum. We chose eight because a correct model then passes about two times in three, and because it gives two non-overlapping four-year windows.

Eight years still makes a weak test. It passes a model whose mean earnings growth misses by a point a year 44% of the time, whichever way it misses, a model with 2/3 of the true spread 46%, a model with 4/3 of the true floor rate 62%, and a model with 3/2 of the true spread 75%. That last rate beats a correct model's, because coverage has no ceiling below 100%. These rates treat each year's four cells as one and ignore differences between origins, so they describe the test's shape, not its exact behaviour. The test also scores statutory paths of four years at most, so it cannot check an average that runs to 2039-40, and no pass covers that. A pass therefore means that outcomes nobody had seen did not contradict the figure's model. It does not show the figure is right, and a fail does not show it is wrong.

**Changes.** Changing any of this takes a new registration and Max's ruling, made before the outcomes it touches appear. A failed verdict opens no repair. Implementation follows in a later change and must match this text. Where it cannot, the new registration says so.
<!-- C3 frozen rule ends -->

## Forecast-error path model and its test: pre-registration (C4)

The section between the markers below registers C4. It was written on 11 November 2026, before any C4 code existed and before the model it defines was scored on any origin. Erratum item 2 below states what the public record shows of that order, and no more. The commit that adds this section changes `docs/METHOD.md` alone. A follow-up note records that commit's SHA and the section's SHA-256, as for C2 and C3.

Pre-registration commit: `7ed1244267f54f4ce7c13a7731401023f809251d`, committed and pushed to `paper-academic-revision` (PR #56) on 11 November 2026 at 15:19:59 UTC, before the first C4 code (`e1e8134`, 15:23:00 UTC). This annotation is a follow-up record; the frozen section below is unchanged from that commit. The binding is SHA256 `1f51be2ed354fd13629c7eeb1415a2830002f4b916117dc4596353acecaccec8` of the exact 11,142 UTF-8 bytes between the begin and end markers, including the newlines immediately inside them; `tests/test_c4_obr_errors.py` compares those bytes with that hash, and `triple_lock.ts_obr_errors` refuses to score if they differ. No tag marks the commit yet. The model is `src/triple_lock/ts_obr_errors.py`; its scores, the rule arithmetic and the sample specification are in `data/c4/`.

**Result, 11 November 2026: C4 failed.** The test ran once, at `0ceb8b8`, with no tuning. The model met every check but one: on the thirteen-forecast test its variogram score is 1.295 times the first model's binding C2 score, above the limit of 1.25. Test A's floor-fraction bias is 0.249 against the limit of 0.25, a pass by a margin the test cannot resolve. Under the rule above the paper stays scenarios only, and a different model would need a new registration that counts this failure. Among the sensitivities, which have no influence on the verdict, the model without the draw of the centre and the small-sample factor would have met every check; the rule forbids promoting it. `data/c4/scores.json` holds every check and per-forecast row, `data/c4/rule_arithmetic.json` the distribution of G and the share over 10,000 forward paths, labelled as the output of a model that failed its test, and `data/c4/sample_design.json` and `sample_specs.json` the sample for full runs, which has not been run. `data/c4/emulator_check.json` (`scripts/c4_emulator_check.py`) checks on the five stored single-path runs how far cash savings follow from rule arithmetic.

**Erratum, 11 November 2026 (follow-up record; the frozen section below is unchanged).** An independent review after scoring found two statements about C4 that the record does not support. Neither changes the verdict, the code or any score; `scripts/c4_diagnostics.py` computes every figure here and writes them to `data/c4/diagnostics.json`.

1. *Centring.* The registered text says the model "is centred on the OBR path by construction". That holds for years 1 to 4 only. From year 5 the walk of step 3 moves each path to the next target year and restarts uniformly only when the record runs out, so later years over-weight the late origins: the weight on the four-year-ahead errors for target years 2021 to 2023 rises from 0.23 under uniform sampling to between 0.25 and 0.39 in years 5 to 12. Those errors are large and positive, so the forward paths' mean statutory error, exact from the walk's weights, is +0.14 points for CPI and +0.32 for earnings in year 5 (determination year 2031), rising to +1.22 and +1.35 in year 12 (2038), with earnings at +1.60 in year 11; the 10,000 draws agree within Monte Carlo error. Removing each year's mean error from the forward paths lowers the 2039-40 mean share from 7.03% to 6.26%, 0.77 points. The design defect stays in the registered model: the rule forbids repairing it, and a corrected model would need a new registration that counts this one.
2. *Timing.* The text above says the registration "was written ... before any C4 code existed". The public record shows order, not that. GitHub's activity log for `paper-academic-revision` shows the registration commit `7ed1244` pushed at 15:20:01 UTC and the 457-line module with its 173 lines of tests (`e1e8134`) pushed at 15:23:02 UTC, three minutes later. The scores and verdict (`5285818`) were pushed at 15:23:59 UTC. The registration was therefore committed and pushed three minutes before we pushed the model's code and four minutes before its scores; the public record shows that order and no more. It cannot show that no code existed when the registration was written. The module's own docstring (`src/triple_lock/ts_obr_errors.py`, lines 3 and 4) said the rule "was committed before any of this code existed"; no hash pins that file, and a docstring-only commit replaces the sentence with the order above, changing no executable line.

The same review checked the verdict's robustness. Over 40 alternative seed sets (origin v seeded v + 100,000k, k = 1 to 40, where the registered run uses v), the test B variogram ratio runs from 1.284 to 1.297, above the 1.25 limit in all 40; test A's floor bias runs from 0.2459 to 0.2518, above 0.25 in 9 of 40, so the registered pass at 0.249 is indistinguishable from the limit. Origins 2011 to 2015, whose hold-out pools hold mostly the March 2017 to March 2022 forecasts, carry 95% of the variogram excess over the first model. The 10,000 forward paths hold 576 distinct error histories, and the top 5% of the 2039-40 share comes from 24 of them, three of which hold half those paths; percentiles beyond the quartiles and shares above thresholds rest on a handful of past years and are not interpretable.

**Further erratum, 11 November 2026 (follow-up record; the frozen section below is unchanged).** A second review of the paper added three points. None changes the verdict, the code that scored or any committed score; `scripts/c4_diagnostics.py` writes the new figures to `data/c4/diagnostics.json`, whose every entry, old and new, was computed after the verdict and none of which was registered.

3. *Robustness runs both ways.* The 40 seed sets above vary only C4's own draws; the first model's scores are fixed. Leaving one forecast's registered score out of both models' test B averages, with no pool changed and nothing rescored, moves the variogram ratio between 1.230 and 1.361 over the 13 single drops, and dropping any one of the March 2012, 2013 or 2014 forecasts puts it at 1.230 to 1.244, below the 1.25 limit. The test can no more separate 1.295 from 1.25 than it can separate the floor bias of 0.249 from 0.25. The verdict stands because the rule compares point estimates with the limits.
4. *Reporting.* The registration's forward use asks for the mean, the median, the 5th, 25th, 75th and 95th percentiles and the probability that the share exceeds seven thresholds. The paper prints the mean and quartiles only and points to `data/c4/rule_arithmetic.json`, which holds the rest. That is a departure from the registered reporting list, made after scoring: above the upper quartile of the 2039-40 share the 10,000 paths come from 75 error histories, 4 of which hold half of them; the five largest histories hold 38% of all paths; and 79% of the share's variance lies between histories. The quartile cut is a reporting choice, not a property of the model.
5. *Status of the diagnostics.* The registration fixed two outputs for a failed model: the distribution of G and the share, and every score. The seed sets, the single-score drops, the history counts, the drift and the decomposition were all computed after the verdict. No row of the decomposition is the result of a corrected model, and none may be read as one.

The committed outputs regenerate byte for byte. At `888060c`, with numpy 2.5.4 (the version `scores.json` records), `python -m triple_lock.ts_obr_errors --output <new directory>` rewrote `scores.json`, `rule_arithmetic.json`, `sample_design.json` and `sample_specs.json` identical to the committed files, and `scripts/c4_diagnostics.py` and `scripts/c4_emulator_check.py` rewrote `diagnostics.json` and `emulator_check.json` in place with no change.

<!-- C4 frozen rule begins -->
**Why this exists, stated plainly.** This model was designed after the first model failed. The monthly VAR(1) residual bootstrap failed the binding C2 test on one check (test A floor-fraction bias 0.267 against a limit of 0.25), and the paper in PR #56 therefore reports scenarios only. Max, reviewing that paper, asked for a rerun that moves from scenarios to a credible probability distribution, because averages over scenarios mean little without one. María's review of PR #8 (finding A2) had made the same point about the first model: one macro process, no coefficient uncertainty, 1/6 realised four-year gaps inside the central 80% band on published April 2022 earnings. C4 defines a second model, anchored on the OBR's own forecast record, and the test it must pass. It is the sixth model form scored against the same past forecasts, under the third rule applied to them, so a pass here carries less weight than a pass by a model registered first would.

**Standing of C4.** C4 leaves the C2 verdict and the binding 28 October 2026 release as they are, and changes no byte of the C2 or C3 rules. C3 governs releases on later OBR forecasts and is not affected. C4 applies to the working paper only. Its only authority so far is that request; whether a C4 pass lets the paper replace C2's scenarios-only fallback is Max's ruling to make, and C4 records the test result either way.

**What we had already seen.** Before writing this we had seen: every C1 and C2 score of the five forms, including test A's realised floor frequency (0.179) and the first model's expectation (0.446); the gap bias of about 1.0 point that all five forms share because they are centred on OBR forecasts; the OBR's forecast errors by horizon in `data/obr_forecast_error_summary.csv`, including the rows that leave out 2020–23; the statutory outturns; and the scores of the older forecast-error comparator `block_bootstrap_statutory` in `data/results.json`, which is close to this model: with only earlier forecasts as its pool (two to seven blocks) it put 3 of 6 four-year gaps inside its band, and with leave-one-forecast-out it put 10 of 12 inside. We have not computed any score of the C4 model, nor any forward distribution from it. From what we had seen we expect the floor-bias check to be close to its limit for any model centred on OBR forecasts with roughly symmetric errors; we did not compute it, and no choice below was made to move it.

**The record.** The spring forecasts with four complete statutory outturns: the June 2010 Budget forecast and the March EFOs of 2011 to 2022 (`ts_backtest.complete_statutory_origins`), thirteen origins, the same past forecasts C2 scores. For origin v and horizon h = 1..4, the forecast f(v, h) is the OBR's calendar-year CPI inflation and average earnings growth for year v + h (`data/obr_forecast_errors.csv`). The statutory error is a(v, h) = statutory outturn for year v + h (September CPI, May–July average weekly earnings growth, `data/triple_lock_actual_inputs.csv`, latest vintage, as published, so the May–July 2021 figure of 8.4% stays in the record) less f(v, h). The calendar error c(v, h) is the OBR's calendar-year outturn less f(v, h); for 2026, which has no calendar outturn yet, it uses the October 2026 EFO's estimate for 2026. Calendar errors supply the calendar-year inputs a microsimulation run needs and enter neither the test nor the rule arithmetic. The committed OBR database starts at June 2010 and holds no earlier official forecast of CPI or earnings, so no HMT forecast enters the record.

**The model.** A path for an origin with central values m(h) is m(h) + ε(h), CPI and earnings jointly. For a pool of n origins, with ā(h) the pool's mean error by horizon and variable:

1. *Uncertainty about the centre.* Order the pool by year. Draw ⌈n/4⌉ start positions uniformly with replacement; each start takes four consecutive positions, wrapping from the last to the first; join them and keep the first n. This moving-block resample keeps neighbouring forecasts together, because they share target years. μ*(h) is the resample's mean error less ā(h). It says how far the average error of n forecasts could itself sit from zero, and it is drawn afresh for every path.
2. *Error pattern, years 1 to 4.* Draw one origin u uniformly from the pool, independently of step 1. Its residual is r(u, h) = √(n/(n − 1)) (a(u, h) − ā(h)); the factor corrects the spread lost by removing an estimated mean. Then ε(h) = μ*(h) + r(u, h).
3. *Years 5 onward.* No forecast in the record runs past four years (five for a few), so later years use four-year-ahead errors, which measure how far outturns land from where the OBR expected the economy to settle. The path continues the history its block came from: year 5 takes the four-year-ahead residual for target year u + 5 (from origin u + 1), year 6 that for u + 6, and so on, while the record lasts. When it runs out, draw a restart target year uniformly from the pool's four-year-ahead target years and continue from there, year by year. Then ε(h) = μ*(4) + r(T_h − 4, 4) for the target year T_h reached.
4. Calendar-year paths use the same u, the same resample and the same target years with c in place of a, so each path's statutory and calendar inputs differ by a gap that some past year showed.

The model is centred on the OBR path by construction: errors are de-meaned, and the mean shift μ* has mean zero. Its uncertainty about its own parameters is the per-path draw of the centre (step 1) and the small-sample factor (step 2); the error distribution itself is the empirical record, with no fitted shape. Spring errors are used for the October 2026 origin too, which is seven months closer to its first target year than a March forecast, so the first years' spread is if anything too wide. Random numbers come from `numpy.random.default_rng(seed)`.

**Hold-out.** When scoring origin o, the pool is every record origin that shares no target year with o: those at least four years away. No outturn of a scored year, and no error measured against one, enters the pool that forecasts it. Leave-one-forecast-out is not enough, because neighbouring forecasts share target years (the 2022 inflation errors sit in four of them). The pools hold six to nine origins. This hold-out is not chronological: pools include later forecasts. A strictly chronological pool cannot carry the verdict, because the record starts in 2010 and only two complete forecasts precede March 2016; it is reported as a sensitivity. Steps 1 and 2 are tested; step 3 is not, because no scored window runs past four years.

**The test.** C2's design and thresholds, unchanged, applied to this one model: test A's seven origins (March 2016 to 2022) and test B's thirteen; target years origin + 1 to origin + 4; centre f(o, h); 5,000 draws per origin, seed the origin's year; April 2022 scored as the law applied it (determination year 2021 earnings set to CPI in draws and outturns, legally fixed cells excluded, annual cells pooled with equal weight); statistics from `ts_backtest.candidate_score`; standard errors as in C2. The model passes only if, in both tests:

- annual and four-year central-80% coverage each lie in [0.50, 1.00], and the four-year coverage's descriptive 95% Wilson band contains 0.80;
- absolute gap bias is at most 1.5 points, absolute switch bias at most 1.0 per four-year path and absolute floor-fraction bias at most 0.25;
- each of the five proper scores (gap, switch and floor CRPS, energy, variogram) is at most 1.25 times the first model's binding C2 score for that test (`data/pilot/c2-binding/scores.json`, suspended treatment);
- every path and score is finite and no origin is missing;

and, on test B, these added checks of the central bands, which C2's upper limit of 100% cannot make:

- annual central-80% coverage in [0.65, 0.95];
- annual central-50% coverage (25th to 75th percentile) in [0.30, 0.70];
- between 3 and 10 of the 13 four-year gaps inside the central-50% band.

The added limits were chosen now, without scores, as roughly the range a calibrated model would give on about sixteen independent years; they are a broad screen and have no finer basis. C2's past-years check cannot be scored: it needs a pool of errors from before 2011 and none exists. It is recorded as not scored, never as passed, and the paper must say that the model beyond four years is untested.

**Sensitivities, with no influence on the verdict.** Published April 2022 earnings; raw errors (no de-meaning, no step 1); the model without step 1 and without the small-sample factor; leave-one-forecast-out pools; chronological pools (origins whose four outturns were published before the scored origin) on test A.

**Forward use.** Central values: the OBR central path the paper already uses (`central.central_path`: October 2026 EFO, then the March 2026 long-term determinants), with the published 2026 inputs fixed. Pool: all thirteen origins. 10,000 paths, seed 20261111, determination years 2027 to 2038 as years 1 to 12. For each path, rule arithmetic only: both rules at the published 0.1-point rounding over April 2027 to 2039, the log gap G (the sum of ln(1 + triple-lock rise) − ln(1 + adjusted rise) to the year in question) and the share 1 − e^(−G), for 2034-35 and 2039-40. Report the mean, median, 5th, 25th, 75th and 95th percentiles, and the probability that the share exceeds 0, 1, 2, 3, 5, 7.5 and 10%. These go in a new file and change no existing result. A stratified sample for full microsimulation runs (ten equal-probability groups on the 2039-40 gap plus the group in which the rules pay the same, Neyman allocation with at least two a group, 180 runs, `expected_value.stratify`, `allocate` and `draw_sample`) is written as a specification and not run.

**What the paper reports.** If C4 passes and Max rules that it may be used: the distribution of the share and of G, labelled as conditional on this model, with the test's low power, the six forms tried and the untested years 5 to 12 stated beside it; cash figures only from microsimulation runs on the sample above or from an emulator whose error is reported. If C4 fails: the paper stays scenarios only. It reports that a second model, anchored on the OBR's forecast errors, was registered and failed, names the failing checks and gives the model's distribution of G and the share once, in an appendix, labelled as the output of a model that failed its test; it makes no probability statement and gives no expected cash figure. Either way the verdict and every score are published.

**Changes.** Nothing here is tuned after scoring. A coding error found after scoring is fixed in a commit that says so, with scores before and after. A failed verdict opens no repair: another model needs another registration, which must count this one among its failures. The test is weak: seven and thirteen overlapping windows over sixteen years, with a hold-out that is not chronological and a design made with the whole record in view. A pass means outcomes did not contradict the model on four-year windows. It does not show the distribution is right.
<!-- C4 frozen rule ends -->

## Conditional volatility bands (V1)

Written on 12 November 2026 at about 11:05 UTC. The commit that adds this section changes `docs/METHOD.md` alone and comes before any V1 code or V1 figure exists. It fixes every choice below before anything is computed, so that no choice can follow the results.

**What V1 is.** V1 gives the working paper a distribution of results that is conditional on stated volatility assumptions: if September CPI and May–July earnings growth vary around the OBR central path as they varied over a stated span of past years, the rules' gap is distributed as follows. It is a sensitivity, not a calibrated forecast. It is not a registration: it takes no test and cannot pass or fail one, and no figure it gives may be read as tested. It is not output of the first model (C2) or of the second (C4), it uses neither model's code or draws, and it changes no byte of the C2, C3 or C4 rules. C4's fail clause says the paper stays scenarios only, and whether anything may replace that fallback is Max's ruling (C4, standing). Vahid adds V1 to the paper as a conditional sensitivity, beside the scenarios, which stay; Max's ruling on it is pending, and the pull request records that. V1 makes no claim to comply with C4's fail clause.

**Why no tested distribution.** A tested distribution needs an out-of-sample record. The OBR's database holds no official forecast of CPI or earnings before June 2010 and none more than five years ahead, so no record exists against which a distribution over twelve years can be scored, and the 2021–23 errors dominate the short record there is. V1 therefore states its assumptions instead of testing them.

**What we had already seen.** Every C1, C2 and C4 score; C4's forward distribution of G and the share (`data/c4/rule_arithmetic.json`) and its diagnostics; every stored scenario and single-path saving in `data/results.json`; and, from the feasibility notes, the standard deviations of calendar CPI and of national-accounts earnings growth over spans starting in 1989, 1993, 1997 and 2011, with and without 2021–23, and the share of their squared deviations that 2021–23 contribute. We have not estimated any V1 parameter or drawn any V1 path.

**Series.** Annual statutory inputs by determination year t (the year before the April they set), latest ONS vintage as committed in `data/raw`:

- CPI: the September 12-month rate (D7G7, the September row), available from 1989.
- Earnings: May–July average weekly earnings total pay growth (KAC3, the July row), available from 2001, as published, so 2021 stays at 8.4%. For 1997 to 2000, which KAC3 does not cover, the calendar-year growth of national-accounts wages and salaries per employee on the OBR's definition (`history_data.history()`). That is a different measure, an annual average that is smoother than a three-month statutory figure, so it if anything understates earnings volatility in those four years.

**Settings.** Two, always shown together:

- (a) 1997–2025, every year;
- (b) 1997–2025 without 2021, 2022 and 2023.

1997 is the first year of the Bank of England's operational independence; 2025 is the last complete determination year before the published April 2027 inputs. No third span is used.

**Model.** For each setting and each variable separately:

1. *Anchor.* m = the mean of the setting's retained years.
2. *Deviations.* x(t) = s(t) − m for each retained year.
3. *Persistence.* φ = Σ x(t) x(t−1) / Σ x(t−1)², the least-squares AR(1) coefficient through the origin, over the lag pairs (t−1, t) with both years retained. Setting (a) has 28 pairs (1997–1998 to 2024–2025); setting (b) drops every pair that includes 2021, 2022 or 2023 (2020–2021, 2021–2022, 2022–2023 and 2023–2024) and has 24.
4. *Innovations.* u(t) = x(t) − φ x(t−1) over the same pairs. Σ is the 2 × 2 covariance of (u_CPI, u_earnings) with divisor (number of pairs − 1), so it carries both variances and their correlation. There are no cross-lags.
5. *Stationarity.* If |φ| ≥ 1 for either variable in either setting, V1 stops and writes nothing; a changed model would need a new dated section.

**Forward paths.** The centre is the OBR central path's statutory inputs at every determination year (`central.central_path()`): 2026 fixed at the published inputs, 2027–2030 the October 2026 EFO's quarterly proxies, 2031–2038 the calendar path. The deviation from the centre is ε(2026) = 0 and ε(t) = diag(φ) ε(t−1) + L z(t) for t = 2027 to 2038, with L the lower Cholesky factor of Σ and z(t) standard normal pairs. Starting from zero keeps the mean deviation at zero in every year: no drift away from the OBR path. The statutory input is centre + ε. Draws: 5,000 paths of z from `numpy.random.default_rng(20261112)` and their 5,000 negatives (antithetic pairs), 10,000 paths, so every year's sample mean deviation is exactly zero. Both settings use the same z, so their difference comes from φ and Σ and not from Monte Carlo noise. Errors are joint normal; the empirical tails are not resampled.

**Rule arithmetic.** For every path, both rules exactly as the paper's rule arithmetic: `rules.rates_matrix` on the statutory inputs for the Aprils 2027 to 2039 (`config.HORIZON`) at the published 0.1-point rounding (`config.CENTRAL_RATE_DECIMALS`), with the 2.5% floor, the switch in April 2030 and the adjusted Triple Lock's earnings anchor as coded there. G(y) = Σ ln(1 + triple-lock rise) − ln(1 + adjusted rise) over the Aprils to y; share(y) = 1 − e^(−G(y)). The rules *pay the same* to y when every April's rate is identical under both, to that year.

**Cash.** Gross saving in fiscal year y on a path: gross = share(y) × B(y) × I_path(y) / I_central(y), where B(y) is the central run's basic and new State Pension spending under the triple lock (`scenario_envelope.central.run.totals_bn.triple_lock[y].state_pension_flat_rate` in `data/results.json`) and I is the triple lock's cumulative index from April 2027 under rule arithmetic. On the five stored single-path runs this identity reproduces the stored gross to £0.00001bn (`data/c4/emulator_check.json`), with the runs' own weekly levels. V1 uses rule-arithmetic levels instead, so a test must show that `rules.rates_matrix` on each stored run's statutory inputs reproduces its stored weekly levels and then its stored gross; if it does not, V1 reports no cash figure. The identity is checked again on the stored earnings scenarios' sample design. Net = ρ × gross, with ρ the least-squares slope through the origin of net on gross over the 40 stored path-years with a gap (the five runs), and its leave-one-path-out error reported beside it (`data/c4/emulator_check.json`). The stored runs' gross reaches about £19.8bn, so a net figure above that extrapolates ρ, and every run shares one population and one set of offsets.

**Outputs.** `data/v1/bands.json`: φ, Σ, the anchors and the retained years for each setting; for each setting and for every fiscal year 2027-28 to 2039-40, the mean, median and 5th, 25th, 75th and 95th percentiles of G, the share, gross and net; and for 2034-35 and 2039-40 the share of paths on which the rules pay the same. The paper's fan chart shows the median, the 25–75 and the 5–95 ranges of gross saving by year for both settings; its distribution figure shows the 2039-40 gross saving for both settings.

**Wording rule.** Every statement of a V1 figure is conditional ("if prices and earnings vary around the OBR central path as they did in 1997–2025 …"); both settings are always shown together; no V1 figure is called calibrated, tested, likely or expected, and none is described as a probability of an outcome rather than a share of paths under a stated setting; nothing implies the C2 or C4 models produced it.

**Changes.** Any change to the above after V1 figures exist is made in a new dated paragraph that says what changed and why, with the figures before and after.

**Record of order, 12 November 2026 (follow-up; the section above is unchanged).** The section above was committed and pushed as `fcf1609f673f488958fd6343288a3eaa499b0d4b` at 11:06:21 UTC, changing `docs/METHOD.md` alone. The first V1 code (`src/triple_lock/v1_bands.py`) was committed as `33c58de` at 11:07:38 UTC, 77 seconds later, and the first V1 figures (`data/v1/`) as `2d3af6d` at 11:09:12 UTC. The public record shows that order and no more; it cannot show that no code existed when the section was written. Nothing in the section changed after any V1 figure existed. The identity check (`scripts/v1_identity_check.py`, `data/v1/identity_check.json`) found the rule-arithmetic weekly levels equal to the five stored runs' and the gross saving within £0.00001bn of every stored run and of both earnings scenarios' stratified means, so V1 reports cash figures.

**Changes, 12 November 2026 (after a referee review of V1; the sections above are unchanged).** Made after V1 figures existed, so recorded here with the figures before and after.

- *Paths.* With 10,000 paths the Monte Carlo standard error in 2039-40 in setting (a) was about £0.10bn on the 5th percentile, £0.08bn on the median and £0.17bn on the 95th (the batch standard errors below times √40), as large as the paper's rounding. `v1_bands.N_HALF` is now 200,000: 400,000 paths from the same seed, among them the earlier 10,000 (the first 5,000 draws and their negatives). Everything else in the specification is unchanged. Gross saving in 2039-40, 5th percentile, median and 95th percentile, before → after: (a) £1.28bn, £10.66bn, £23.60bn → £1.45bn, £10.73bn, £23.80bn; (b) £0.00bn, £6.50bn, £18.21bn → £0.00bn, £6.58bn, £18.18bn. Net: (a) £0.88bn, £7.29bn, £16.12bn → £0.99bn, £7.33bn, £16.26bn; (b) £0.00bn, £4.44bn, £12.44bn → £0.00bn, £4.50bn, £12.42bn. Paths on which the rules pay the same to 2039-40: (a) 2.06% → 2.03%; (b) 6.76% → 6.61%.
- *Monte Carlo standard errors.* `bands.json` now records, for every year, batch-means standard errors of the 5th, 50th and 95th percentiles of gross saving: 40 batches of 5,000 antithetic pairs, each pair kept in one batch, the standard deviation of the batch percentiles over √40. In 2039-40 they are £0.016bn, £0.012bn and £0.027bn in (a), and £0.011bn and £0.027bn for the median and 95th percentile in (b), whose 5th percentile is exactly zero in every batch.
- *Further outputs.* `bands.json` also records the largest gross saving in 2039-40 on any path and, for every year, the share of paths whose gross saving exceeds the largest stored run's (£19.8bn), where the net figure extrapolates ρ.
- *Wording.* The opening paragraph's "it fixes every choice below before anything is computed, so that no choice can follow the results" states the intention. The record shows only that the section was pushed before the first V1 code and figures (Record of order); the spans were chosen after seeing the standard deviations listed under "What we had already seen" and both models' results. The Series paragraph's "smoother … so it if anything understates earnings volatility" does not hold: over 2001–2019 the national-accounts measure's standard deviation is 1.74 points against KAC3's 1.45. It is a different, calendar-year measure; starting the span in 2001 moves the medians by £0.3bn or less (`data/v1/robustness.json`).
- *Covariance.* `np.cov` takes Σ about the residuals' mean, not about zero as a through-origin regression would. Left as it is; taking it about zero moves the 2039-40 medians by at most £0.06bn and the 95th percentiles by at most £0.19bn (`data/v1/robustness.json`).
- *Robustness runs, not settings.* `scripts/v1_robustness.py` writes `data/v1/robustness.json`: each run changes one stated assumption with V1's own draws and arithmetic, and none is a third setting. They are the innovation correlation set to 0 and to 0.8 with the standard deviations held; φ = 0 with Σ held; spans from 2001; setting (b) also without 2020; a VAR(1) with cross-lags; residuals resampled in place of normal draws; and Σ about zero. The file also records how often the CPI–earnings lead passes on V1's paths and on the first model's paths behind the earnings scenarios, V1's statutory input standard deviation by year, and the OBR's forecast errors: `data/obr_forecast_error_summary.csv` is calendar-year (calendar-year CPI and earnings growth against calendar-year outturns), so the file adds the spring forecasts' errors against the statutory inputs.

## Bayesian forecast of the uprating inputs (B1)

Written on 12 November 2026 at about 14:40 UTC. The commit that adds this section changes `docs/METHOD.md` alone and is pushed before any B1 code exists, any B1 parameter is estimated or any B1 path is drawn. A follow-up note will record its SHA and time against the first B1 code and figures; that record can show order and no more.

**Authority.** Max is co-author, and the C2 and C4 registrations reserve to him the decision on what may replace the scenarios-only fallback; V1's section records his ruling as pending. He ruled on Slack on 12 November 2026 at 14:23, verbatim:

> "No - we need to make it a forecast we can stand behind"
>
> "Not sensitivity - take a Bayesian approach"

He had earlier asked that the paper move "from hypothetical scenarios to a credible probability distribution. Without that, the aggregates/averages are ~meaningless." On that ruling B1 is the working paper's primary method. It supersedes the scenarios-only fallback for the working paper, and V1 becomes a robustness check and no longer the headline distribution; the scenarios stay in the paper. The ruling changes no byte of the C2, C3 or C4 rules, no V1 code or output, the C2 verdict or the binding 28 October 2026 release. C2 and C4 remain failed, and B1 does not turn either into a pass.

**Stated plainly.** B1 is designed after the first model failed C2, the second failed C4 and V1's figures and referee review were seen. It is the seventh model form set against the same short record. Its headline stands on Max's ruling, not on a test: the scores below are reported whatever they show and are not a pass/fail gate, because the record cannot support one. C2's failure was a floor bias of 0.267 against 0.25 and C4's a ratio of 1.295 against 1.25 that single-forecast drops move between 1.23 and 1.36; a gate that turns on such margins would decide by noise. The one hard gate is numerical (Convergence, below). What the paper must say if the scores are poor is fixed now (Wording).

**What we had already seen.** Every C1, C2 and C4 score and diagnostic; C4's forward distribution; V1's parameters, bands and robustness runs (`data/v1/`), including V1's persistence estimates, the spring forecasts' errors against the statutory inputs (standard deviation 2.0 to 3.2 points one to four years ahead, CPI–earnings correlation 0.55 to 0.84 against V1's 0.21 to 0.31) and the share of variation that 2021–23 carry; `data/obr_forecast_error_summary.csv`; the statutory record; every stored scenario and single-path saving. No statistic of the data was computed to choose any number below. No B1 parameter has been estimated and no B1 path drawn.

**Data.** All growth rates in percentage points.

- *Forecast-error record (F).* Every cell (v, h) of `data/obr_forecast_errors.csv` with a spring origin v (the June 2010 Budget forecast and the March forecasts from 2011), h = 1 to 4, and a statutory outturn for year v + h in `data/triple_lock_actual_inputs.csv` (latest vintage, as published, so May–July 2021 stays at 8.4%). The error is a(v, h) = statutory outturn (September CPI, May–July total pay growth) less the OBR's calendar-year forecast for v + h, as in C4, with a(v, 0) = 0. Target years run from 2011 to 2026; the thirteen complete origins give 52 cells and the incomplete origins the rest.
- *Outturn record (O).* The statutory inputs s(t) for 1989 to 2010: September CPI (D7G7); May–July total pay growth (KAC3) from 2001 and, for 1989 to 2000, which KAC3 does not cover, calendar-year national-accounts wages and salaries per employee on the OBR's definition (`v1_bands.statutory_history`). That stand-in is a different measure and varies somewhat more than KAC3 where both exist (V1 Changes); a sensitivity starts the block later.
- *Each year enters once.* A year's surprise is measured against the OBR's forecast where one exists (2011 on) and against the model's own one-year-ahead prediction where none does (1990 to 2010). The outturns of 2011 to 2025 do not enter a second time as an outturn likelihood, because they are already inside the errors.

**Model.** One process for the deviation of the two inputs from a forecast path, ε(t) = (CPI, earnings):

ε(origin) = 0, ε(t) = Φ ε(t − 1) + u(t), u(t) ~ bivariate Student-t with ν degrees of freedom, location zero and scale matrix Σ,

with Φ a full 2 × 2 matrix (own persistence on the diagonal, lagged pass-through between prices and pay off it), spectral radius below 0.98. The t shock is a normal shock whose variance is multiplied each year by one draw w(t) ~ inverse-gamma(ν/2, ν/2) common to both variables: most years are ordinary and a few, like 2021–23, are several times as volatile for prices and pay together. This is the simplest form of changing volatility that the record can identify. A Markov-switching or stochastic-volatility law would need to estimate how long turbulent spells last from one or two spells in 37 years, so the model has none, and a sensitivity says what clustering would do. The process has mean zero at every horizon: no drift from the centre. It is a Bayesian VAR(1) in forecast deviations, chosen because a referee can read it as "forecast errors accumulate and decay", because it is the same law forward as in the likelihood, and because it has few enough parameters to fit on about 37 years.

*How the two records enter.*

- F: an origin's errors are the process started at zero at the origin, so r(v, h) = a(v, h) − Φ a(v, h − 1) is a draw of u with scale Σ_F. Forecasts made in neighbouring years share target years, so the cells are not independent: each cell's log density is weighted by 1/n(T), where n(T) is the number of cells with target year T = v + h. Every target year then carries total weight one (16 years of information, not 57 cells). The likelihood has mean zero: the record's positive mean errors are treated as surprises that widen Σ_F, not as a bias to project forward.
- O: x(t) = s(t) − m, and x(t) − Φ x(t − 1) for t = 1990 to 2010 is a draw of u with scale Σ_O (21 transitions, weight one each). The anchor m is estimated and exists only inside this block.
- Shared between the records: Φ and ν. Linked but not equal, because V1's review showed outturn variation is not forecast error: the scale. Σ_F has standard-deviation parameters σ_c, σ_e and correlation ρ_F. Σ_O has κ_c σ_c, κ_e σ_e and ρ_O, with atanh ρ_O = atanh ρ_F + ζ. The outturn record therefore informs persistence, pass-through and tail weight fully, and the forecast scale and correlation only through the priors on κ and ζ.
- Forward, the process is the forecast-error process: scale Σ_F.

*Long-run level.* No forecast in the record runs past four or five years, so nothing in either likelihood measures how far the economy settles from the OBR's long-run assumptions. From determination year 2031, where the central path passes from the EFO to the long-term determinants, each path adds a constant shift: δ_c to CPI and δ_c + δ_r to earnings, δ_c ~ N(0, 0.25²) and δ_r ~ N(0, 0.5²), independent of each other and of everything else. These are priors that no data here update. They have mean zero, so the forecast keeps no drift.

**Priors.**

| Parameter | Prior | Why |
|---|---|---|
| Φ own lags (CPI, earnings) | N(0.5, 0.25²) each | Annual growth rates sit between no memory (0) and a random walk (1); the prior covers both ends at two standard deviations and shrinks towards the middle. A judgment, in the manner of a Minnesota prior. |
| Φ earnings on lagged CPI | N(0.2, 0.2²) | Pay catching up with past inflation: partial pass-through, sign from the wage–price literature, size a judgment; zero is one standard deviation away. |
| Φ CPI on lagged earnings | N(0.1, 0.2²) | Labour costs feeding prices: weaker and less certain. A judgment. |
| Spectral radius of Φ | below 0.98 | Deviations from a forecast die out. |
| σ_c, σ_e (forecast shock scale) | log-normal, median 1.5, log-sd 0.5 | 95% range 0.56 to 4.0 points: wide around the scale of official one-year errors already seen. |
| atanh ρ_F | N(0.4, 0.5²) | Median ρ 0.38, 95% range −0.52 to 0.88: prices and pay are moved by common shocks, between V1's 0.2–0.3 and the error record's 0.55–0.84, both already seen. |
| ζ = atanh ρ_O − atanh ρ_F | N(0, 0.5²) | The two records may differ in correlation. |
| κ_c, κ_e | log-normal, median 1, log-sd 0.5 | Outturn innovations may be up to about 2.7 times smaller or larger than forecast errors (95% range). |
| ν − 2 | Gamma(shape 2, rate 0.1) | After Juárez and Steel (2010), who put this gamma prior on ν; ν > 2 keeps the variance finite; prior mean 22, with material mass below 10. |
| m_c | N(2.0, 0.5²) | The 2% CPI target (and its RPIX predecessor, about the same in CPI terms). |
| m_e | N(4.0, 1.0²) | 2% inflation plus about 2% real earnings growth, roughly the pre-2008 average; the OBR's long-run earnings growth is 3.83%. |
| δ_c | N(0, 0.25²) | The target anchors long-run CPI; 0.25 allows a small persistent miss. A judgment. |
| δ_r | N(0, 0.5²) | Long-run real earnings growth: the paper's own earnings scenarios are ±0.5 points, and the OBR has revised its productivity growth assumptions by amounts of that order. A judgment. |

The priors on m shape only the outturn block's anchor. Neither they nor any other prior moves the forward centre.

**Fitting.** NumPyro's NUTS sampler on the joint posterior with the t densities in closed form, seed 20261112, four chains, 1,500 warm-up and 2,500 kept iterations each (10,000 draws), target acceptance 0.95. The posterior draws are committed with their hash, and everything after the fit uses numpy alone on those draws, so the figures regenerate from the committed draws; a refit is checked against them to a tolerance, not bit for bit.

**Convergence: the one hard gate.** For every parameter: rank-normalised split R-hat at most 1.01, bulk and tail effective sample sizes at least 1,000, and at most 10 divergent transitions in the 10,000. If unmet, one rerun with target acceptance 0.99 and 3,000 warm-up; if still unmet, B1 reports no headline. The share of draws with spectral radius above 0.95 is reported. Every refit below records the same diagnostics, and any that misses them is marked and its figures are not quoted.

**Forward paths.** Centre: the OBR central path's statutory inputs (`central.central_path()`), 2026 fixed at the published inputs, as V1 uses. For each of the 10,000 posterior draws, 20 paths and their mirror images (shocks and level shifts negated, the same w), 400,000 paths, numpy seed 20261113; the mean deviation is exactly zero in every year. Deviations run from 2027 (year 1) to 2038 (year 12) and are not truncated. The spring errors stand in for an October forecast, which is seven months closer to its first target year, so the first years are if anything too wide.

**Rule arithmetic and cash.** As V1: `rules.rates_matrix` at the published 0.1-point rounding for the Aprils 2027 to 2039; G(y) the cumulative log gap and share(y) = 1 − e^(−G(y)); gross = share × B(y) × I_path(y) / I_central(y), the identity checked on every stored run (`data/v1/identity_check.json`), re-checked by a B1 test; net = ρ × gross with ρ from the stored runs and its leave-one-path-out error (1.1% mean, 2.8% largest) stated beside every net figure. No microsimulation runs.

**Outputs** (`data/b1/`). For every fiscal year 2027-28 to 2039-40: mean, median and the 5th, 25th, 75th and 95th percentiles of G, the share, gross and net; the probability (share of posterior predictive paths) that the saving exceeds £0 (G > 0, the complement of the paths on which the rules pay the same, at 0.1-point rounding), £5bn and £10bn, gross and net; the largest gross saving and the share of paths above £19.8bn gross, the largest stored run, beyond which ρ extrapolates. Monte Carlo standard errors: batch means over 40 batches of 250 posterior draws with all their paths. Posterior uncertainty: (i) each chain's own median, 5th and 95th percentiles and probabilities, and their range across chains; (ii) for 1,000 posterior draws (every tenth), 2,000 paths each, the median saving and the probability above £10bn given that draw's parameters, summarised by their standard deviation and 5th to 95th percentiles across draws: how much of the spread is uncertainty about the parameters.

**Validation, reported whatever it shows.**

1. *Prior predictive check.* 10,000 draws from the priors alone, with no data, pushed through the same forward arithmetic: the standard deviation of the deviations in years 1, 4 and 12 and the distribution of the 2039-40 gross saving, beside the posterior's.
2. *Posterior predictive checks.* (a) Replicated error records: for 4,000 posterior draws, shocks for target years 2011 to 2026 and each origin's errors built from them (so replicated origins share target-year shocks as real ones do), with the origins' actual forecasts as centres. Statistics, each with the realised value and the share of replications at or beyond it: the share of the 52 complete-origin cells with earnings below 2.5%; lead changes between CPI and earnings per four-year path; the standard deviation of errors by variable and horizon; the CPI–earnings error correlation by horizon; the largest absolute error. (b) Forward paths against the statutory record 2001–2025, descriptively, because the centres differ: share of years with earnings below 2.5%, lead changes per year, and the correlation of CPI and earnings.
3. *The C2/C4 scores on pseudo-out-of-sample fits.* For each of the thirteen complete origins o, the model is refitted (four chains, 1,000 warm-up, 1,500 kept) and 5,000 four-year paths are drawn around f(o, h) with seed o, without the long-run shift. Scores are C2's and C4's exactly: `ts_backtest.candidate_score`, C4's central-50% statistics and summaries, tests A and B, April 2022 scored as the law applied it and as published, and ratios to the first model's binding C2 scores. Two hold-outs: *chronological* (primary): the refit sees the outturn block and only F cells whose target year is at most o − 1, which is what was known in spring of year o; the 2010 and 2011 origins therefore rest on the outturn record and the priors. *Target-year* (C4's): the refit drops every F cell whose target year, or whose lagged year, lies in o + 1 to o + 4. Each score is set beside the C2/C4 limit, and the report says whether C4's rule would have passed B1 under each hold-out.
4. *Sensitivity.* Each run changes one thing, refits where the posterior changes, and reports the 2039-40 and 2034-35 gross median, 5th and 95th percentiles and probabilities: S1 persistence looser (Φ prior standard deviations doubled); S2 tighter (halved); S3 thin tails (ν fixed at 30); S4 fat tails (ν fixed at 3); S5 low correlation (atanh ρ_F ~ N(0, 0.25²)); S6 high correlation (atanh ρ_F ~ N(atanh 0.8, 0.25²)); S7 without 2021–23 (every F cell dropped whose target year or lagged year is 2021, 2022 or 2023); S8 no long-run level uncertainty (δ = 0); S9 its standard deviations doubled; S10 outturn block from 1997; S11 forecast-error record alone; S12 outturn record alone, 1989–2025, forward scale Σ_O (the Bayesian counterpart of V1); S13 clustered volatility forward (w(t) repeats w(t − 1) with probability one half; no refit); S14 every F cell at weight one; S15 errors de-meaned by variable and horizon before they enter. The prior-sensitivity range is the lowest and highest 2039-40 gross median over S1 to S6 and S8 to S9; the full range is over S1 to S15. Both are reported, with S7 named beside the headline.

**Wording.** The paper states B1's figures as a forecast: probabilities are posterior predictive probabilities under the stated model and priors. It may not call B1 tested, validated or calibrated. Beside the headline it states: that B1 was designed after two failed models and V1; each C2/C4 limit B1 misses under the chronological hold-out, by name and value, and whether C4's rule would have passed it; any posterior predictive statistic whose realised value lies outside the central 98% of replications, by name, as a feature of the record the model does not reproduce; the sensitivity ranges and S7; that years 5 to 12 rest on the fitted persistence and on priors for the long-run level, which no record tests; and that net figures carry ρ's error. If the convergence gate is unmet there is no headline.

**Changes.** Nothing above is changed after B1 figures exist. A coding error found later is fixed in a commit that says so, with figures before and after. Anything else is a new dated paragraph that states what changed and why, with figures before and after.

**Record of order and of the first fit, 12 November 2026 (follow-up; the B1 section above is unchanged).** Written at about 14:45 UTC, before any B1 forecast figure existed: no forward path had been drawn from any posterior, and the only B1 outputs were the fit's diagnostics and parameter summaries.

- *Order.* The section above was committed and pushed as `de576a54c8b83d075cd1905352fd55cfdc4b29df` at 14:32:46 UTC (its "about 14:40 UTC" is wrong by seven minutes), changing `docs/METHOD.md` alone. The first B1 code was `4f2bb1f` at 14:38:44 UTC and the first fit `8c798a0` at 14:40:17 UTC. The public record shows that order and no more.
- *A count.* The Model paragraph says "not 57 cells". The committed file gives 55: the March 2023 and March 2024 forecasts have no rows for 2026. The rule (every cell in the file with a statutory outturn) is unchanged, and the sixteen target years still carry weight one each.
- *The convergence gate was unmet as first coded.* At `8c798a0` the first fit gave R-hat at most 1.0006 and effective sample sizes of at least 6,636, with 74 transitions flagged divergent against the gate's 10; the rerun the gate allows (target acceptance 0.99, 3,000 warm-up) gave R-hat at most 1.0010, effective sample sizes of at least 6,354 and 90 flagged. `data/b1/fit.json` at that commit records `headline_permitted: false`.
- *Diagnosis.* The code imposed the spectral-radius bound as a wall of zero density inside the sampler. NUTS flags any trajectory that crosses such a wall as divergent, whatever the posterior's shape. The same run without the wall (same seed, same settings) gave 0 divergent transitions, R-hat at most 1.0009 and effective sample sizes of at least 6,456; 14 of its 10,000 draws had a spectral radius of 0.98 or more.
- *Fix.* The sampler now runs on the posterior without the bound, and the draws outside the bound are discarded afterwards. That targets exactly the posterior the section specifies (the unbounded posterior restricted to the region). The gate is evaluated on the chains as run, all 10,000 draws and all their divergent transitions, with the rerun rule unchanged; the discarded and retained counts are recorded. Chain lengths are not changed and nothing is topped up, so the forward step uses the retained draws (about 9,986, so about 399,440 paths, not 400,000), batches for the Monte Carlo standard errors differ in size by at most one draw, and a pseudo-out-of-sample refit that retains fewer than 5,000 draws samples them with replacement. The same code path serves the fit, the refits and the sensitivity runs. The stored posterior is `data/b1/posterior.npy`, the chains as run.
- *Whose call.* The gate as written and first coded was unmet twice. We treat the wall as a coding error under the Changes clause and proceed, and the choice was made before any forecast figure existed. Whether that reading stands, or the unmet gate bars a B1 headline, is Max's ruling. To show what turns on it, `data/b1/gate_record.json` gives the 2039-40 saving from the wall-coded draws of `8c798a0` beside the figures from the fixed fit.

**Results, 12 November 2026 (follow-up; the B1 section above is unchanged).** Every figure is in `data/b1/`; `python -m triple_lock.b1_bayes` rewrites `forecast.json` and `validation.json` from the stored draws, and `scripts/b1_fit.py`, `b1_backtest.py`, `b1_sensitivity.py` and `b1_gate_record.py` write the rest. Nothing in the specification was changed after a figure existed; the two code fixes (the bound, above, and a loader call that stopped the first forward run before it printed anything) are in commits that say so.

- *Fit.* On the chains as run: 0 divergent transitions, R-hat at most 1.0009, effective sample sizes of at least 6,456; 14 draws outside the bound discarded, 9,986 retained, 399,440 paths. Posterior medians (5th to 95th percentiles): own persistence 0.42 (0.20 to 0.64) for CPI and 0.48 (0.24 to 0.70) for earnings; shock scale 1.72 (1.21 to 2.41) and 2.08 (1.52 to 2.82) points; ρ_F 0.38 (0.06 to 0.62), which is its prior's median, so the data say little about it; ν 9.0 (3.6 to 31).
- *Forecast.* Gross saving in 2039-40: median £9.2bn, 5th to 95th percentile £0.0bn to £28.2bn, quartiles £4.0bn and £15.9bn, mean £11.0bn; net median £6.3bn (£0.0bn to £19.3bn). Probability of any saving 92.0%, of more than £5bn 70.2% gross and 58.9% net, of more than £10bn 46.6% gross and 28.8% net. In 2034-35: gross median £1.5bn (£0.0bn to £9.4bn), net £1.0bn (£0.0bn to £6.4bn); probabilities 66.4%, 20.0% and 4.1% gross. On the OBR central path itself the saving is £0.5bn in 2039-40: the forecast's saving comes from variation around that path, not from the path. Monte Carlo standard errors in 2039-40: £0.02bn on the median, £0.07bn on the 95th percentile, 0.1 points on the probabilities; the four chains' medians run from £9.17bn to £9.31bn. Given one posterior draw's parameters the median saving has standard deviation £2.2bn across draws (5th to 95th percentile £6.2bn to £13.0bn) and the probability above £10bn runs from 32% to 62%. The largest path saves £188bn; 15.4% of paths exceed £19.8bn gross in 2039-40, where the net ratio extrapolates.
- *Gate record.* The wall-coded draws of `8c798a0` give a 2039-40 median of £9.23bn and a 95th percentile of £28.33bn, against £9.24bn and £28.23bn: the reading of the gate does not move the answer.
- *Prior predictive.* The priors alone give a 2039-40 gross median of £6.9bn and a 95th percentile of £28.5bn (probability above £10bn 35.6%). The data raise the median by £2.4bn and leave the upper tail where the priors put it. The forecast is therefore substantially shaped by the priors on the shock scale.
- *Posterior predictive.* No statistic of the realised error record lies outside the central 98% of 4,000 replications. Closest to the edge: lead changes per four-year path, 1.62 realised against a replicated median of 1.00 (7.6% of replications at or above); the one-year-ahead CPI error standard deviation, 2.66 points against 1.87 (12.8%). Share of cells with earnings below 2.5%: 0.33 realised, 0.37 replicated. Error correlation by horizon: 0.55 to 0.67 realised, 0.40 to 0.51 replicated medians. Forward paths, descriptively: earnings below 2.5% in 42% of years against 28% over 2001–2025 (the forward centre is lower), 0.36 lead changes a year against 0.33, deviation correlation 0.53.
- *C2/C4 scores, reported and not a gate.* All 26 refits met the convergence gate without a rerun. Chronological hold-out (primary): every C2/C4 limit is met, so C4's rule would have passed B1; test A floor bias is 0.2499 against 0.25, which the record cannot tell apart from the limit, and annual central-50% coverage on test B is 0.375. Target-year hold-out (C4's own): test A floor bias 0.2585 misses 0.25 and every other limit is met, so C4's rule would have failed B1. Gap bias is 1.0 to 1.2 points in every case (limit 1.5), the overprediction common to models centred on OBR forecasts. Variogram ratios 0.87 to 0.96 (C4: 1.295). The June 2010 origin's chronological refit sees the 2010 outturn, published after that forecast.
- *Sensitivity, 2039-40 gross median.* Prior runs (S1 to S6, S8, S9): £8.6bn to £9.8bn. All runs: £6.8bn (S7, without 2021–23: 5th to 95th percentile £0.0bn to £22.5bn, probability above £10bn 34%) to £10.5bn (S11, the forecast-error record alone). Outturn record alone (S12): £8.0bn. Fat tails (S4) move the 95th percentile to £31.3bn; no other run moves it outside £22.5bn to £30.2bn. Every refit met the gate.
