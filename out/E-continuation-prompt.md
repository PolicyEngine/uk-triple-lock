Continue the authorized Model v2 part E task in the SAME assigned workspace.
This is a runtime continuation, not a new objective. Preserve all existing changes.
Before doing any writes or starting model runs, wait for parent Subfleet job
20261005-080931-model-v2-e to become terminal (subfleet wait with --timeout 30;
never stop it). While it is active, read-only preparation is allowed. Parent's
21600-second runtime ends around18:09UTC. Do not compete with its workers.
Read out/E-STATE.md immediately, then inspect actual files, Git head, receipts,
resource levels and queued review state; the state note may have newer updates.
Use workspace-private Git .git-e throughout. Work only here; no caller-repo writes.
Resume checkpoints, finish all runs/tests/evidence and independent Subfleet
reviews until approved, then update draft PR24 body, push ONLY model-v2 and
produce the complete final report. No GitHub comments, merge, history rewrite,
operator-policy changes, survey-record output, or invented/scaled model numbers.
Do not mark the goal complete while required evidence/review remains pending.
The original user task follows and remains fully in force.

# Model v2, part E: address Vahid's re-review of #24 at 30a1be9

**Repo:** PolicyEngine/uk-triple-lock, branch `model-v2` (draft PR #24, head 30a1be9). Work in your own worktree on `model-v2` and push to it; #24 stays a draft. Merge nothing into main.

Read first:
- every comment on #24, and especially Vahid Ahmadi's three of 2026-10-05: 10:02Z (the post-merge review of #23's ageing method), 10:05Z, and 10:52Z (the re-review of 30a1be9, the list this job closes);
- Vahid's comments on #22 (items 7 and 8 are the mean-path and first-phase points);
- issue #14 and its comments (María Juaristi's four gates);
- `docs/REBUILD.md`, `docs/AGEING_PILOT.md`, `docs/AGEING_PILOT_RESULTS.md`, `docs/UNCERTAINTY_PILOT.md`, `docs/METHOD.md`;
- the integrated pilot folder `~/reviews/uk-triple-lock-2026-09-29/model-v2-integrate/` (`README.md`, `PROGRESS.md`, `bridge.md`, `integrated.md`, `summary.json`, `pilot.py`, `run_head*.sh`) and part A's `~/reviews/uk-triple-lock-2026-09-29/model-v2-pilot/bridge.md`.

## Vahid's open items (his numbering, 10:52Z)

1. **Evidence.** Commit the 2.120.0 pilot aggregates, both the version bridge and the GB-vs-DWP coverage tables, with the commit and policyengine-uk version they came from. Put them in `data/pilot/` as JSON plus a short `docs/MODEL_V2_PILOT.md`, labelled as a pilot on an uncertified data/model pair, not for quoting.
   - Mark `docs/AGEING_PILOT_RESULTS.md` and `data/ageing_validation.json` as the policyengine-uk 2.90.2 record: a header line, no number changes.
   - Aggregates only, with a 10-record minimum cell. Run the repo's record-redaction rules over anything you commit, and add a test that the committed pilot files carry no record-level field.
   - Include the review notes Vahid asked for on 10:05: a summary of the independent reviews of parts A–D, with verdicts. Don't paste reviewer transcripts.
2. **Re-typed level.** A basic-era record re-typed to the new State Pension keeps its basic-era amount.
   - Read the Pensions Act 2014 s.4 and Sch 1 (starting amount; the transitional rate) and the related regulations on legislation.gov.uk, current revised text.
   - Implement the s.4 starting-amount rule for re-typed records if the data supports it. Check what the Enhanced FRS carries: qualifying years, additional pension, contracting out.
   - If it doesn't, implement a bounding sensitivity instead. Re-typed records' flat-rate part goes to the full new State Pension rate (upper bound), against kept as now (lower bound). Run both as full PolicyEngine UK runs on the central path and on the 40 Microcosm-paired draw indices.
   - Say which you built and why, citing the section.
   - Keep the components identity (basic + new + additional = reported State Pension in the data year, to £0.01) and its tests.
   - State in `docs/METHOD.md` which is the default treatment. If the choice is methodological rather than one the law settles, keep the current behaviour as the default and report the other as a sensitivity.
3. **C1 adapter.** `expected_value.build(run=True)` must run end to end.
   - It consumes `ts_uncertainty`'s output for a chosen form: the 160-slot Neyman design, 161 unique runs with the identical-rates check. It writes the expected-value section, including every field `docs/REBUILD.md` step 3 says the paired Microcosm step needs: per path `times_drawn_sensitivity`; per stratum `sensitivity_paths` and `probability`; and the draws' `n`, `seed` and `shocks`.
   - The method decision is Max's (d955: (a) a scenario envelope with no expected value; (b) an expected value labelled model-conditional; (c) re-pre-register with the suspended April 2022 treatment). Don't decide it.
   - Make the ruling an explicit, recorded input, for example `--uncertainty-ruling a|b|c` written into provenance. Under (a) the stage is skipped cleanly. Under (b) the original primary runs with the model-conditional label in the results. Under (c) the screen is re-run under the suspended treatment and only a passing form runs.
   - Keep C1's gate: with no ruling, `build(run=True)` refuses as now, with a message that names d955.
   - Test the adapter end to end with a fake engine (no PolicyEngine run): the slot counts, the duplicate check, the written fields, and that each ruling does what it says.
4. **Determinism.** f2ea89a and 30a1be9 changed the rake fallback. Rerun the determinism check the pilot used (see `PROGRESS.md`) at your final head, and record the result in `docs/MODEL_V2_PILOT.md`.
5. **Smaller points:**
   - Pin `policyengine-core==3.32.16` in `pyproject.toml` to match the lock; a fresh install now resolves 3.32.17. Add it to the version-provenance test if that test reads core.
   - The `gov_balance` check near `engine.py:469` is tautological, since `gov_balance` is the sum of its components. Replace it with an identity that can fail, for example the change in `gov_balance` against the change in household net income plus the tax and spending items outside household income, computed independently. Or remove it and say why. Show it can fail with a mutation test.
   - **First-phase SE for reweightings** (`stratified_estimate`, Vahid's #22 item 8): use the reweighted draws' effective sample size, not N=50,000. Test it against brute-force Monte Carlo on synthetic strata with unequal weights.
   - **Mean paths** (#22 item 7): the paired ±0.5pt earnings mean-path runs are a scenario, not a probability claim, so they need not wait for the screen.
     - Make them runnable independently of C1's adequacy gate, labelled as a scenario in results and docs.
     - How they're presented still follows d955. Update `docs/REBUILD.md`'s job counts and gates.
   - **Represented-age ordering** (`demography.py`, about line 223): key it on the dataset's content hash, not its name. Add a test that two datasets with the same name and different content order differently.
   - **Total-only control** (Vahid's 10:02 item 2): add a treatment that rakes only the total population to ONS totals, isolating the age-structure effect from the population-total effect. Run it with full runs on the central path and the 40 paired draws, beside frozen / reweight / types / both.
   - **Country table** (María's gate 2 by geography): compare recipients and basic/new State Pension spending for England, Scotland and Wales with the committed DWP spring 2026 tables, on the base year and every forecast year they cover. Suppress any cell under 10 records. If DWP's committed tables lack a country split, say so and use only a verified published source; otherwise mark it "unavailable".
   - **#24 body:** rewrite it to match the head. Drop the stale part A text (it lives at `model-v2-integrate/pr24-body-part-A.md` for the record), and update the test count and the coverage ranges.

## Pilot reruns

Items 2 and 5 (total-only and the country table) need full PolicyEngine UK runs, on the Enhanced FRS and policyengine-uk 2.120.0 as in part D.
- Check host RAM and CPU first (`vm_stat`, `top -l 1`); other sessions run builds on this machine. At most 2 Microcosm workers at about 32 GB each, and at most 3 Enhanced FRS workers.
- Use `HUGGING_FACE_TOKEN=$(agent-secret get HUGGING_FACE_TOKEN_MAX)`.
- Report GB and UK gross and net for 2034-35 and 2039-40 with SEs. Show each new treatment next to part D's integrated numbers, so each step is attributable.

## Tests and checks

- Full pytest, plus the dashboard's `bun run test`, `bun run lint` and `bun run build`. Only the documented stale-results tests may fail.
- Add Hypothesis properties where logic is load-bearing:
  - the re-typed level rule: monotone in the rate, and never below the kept amount under the upper bound;
  - the effective-sample-size SE: reduces to the plain formula under equal weights;
  - the adapter's design: the allocation sums to the slot count.
- Get an independent review on Subfleet (`subfleet run --task review --tier standard -C <worktree> -p <prompt> -o <out>`). Fix what it finds and repeat until it approves.

## Rules

- Every number comes from a full PolicyEngine UK run. No scaling, interpolation or side models.
- No survey record's id, weight or amounts in code, results, commits, PR text or pasted logs. Aggregates only, with a 10-record minimum cell.
- Nikhil Woodruff may appear in GitHub text but never in the paper or the dashboard.
- Mechanism and legal claims only from code you read, runs you made, or legislation you read this session.
- Use Subfleet for reviews, never in-session Workflow or agents.
- Don't post comments on GitHub issues or PRs. Draft them as files instead:
  - `~/reviews/uk-triple-lock-2026-09-29/out/E-reply-vahid.md`: a reply to Vahid's 10:52 comment, item by item, with commit SHAs;
  - `~/reviews/uk-triple-lock-2026-09-29/out/E-maria-14.md`: a short #14 comment asking María to agree, or not, to running the rebuild on the uncertified pair (data 1.56.16 built on 2.89.2, model 2.120.0). State what certification would change and what d778 / d833 decide.

  The body rewrite of #24 is yours to do.

## Output (to the `-o` path)

- the `model-v2` head and the PR state;
- each of Vahid's items: what was done, the commit, and the test;
- the re-typed level: rule or sensitivity, the legal basis, and the run results;
- the total-only control and country tables;
- determinism;
- the review verdict;
- the paths of the two drafted comments;
- what's still blocked on Max: d955, d833, d778.
