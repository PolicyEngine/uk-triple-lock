Model v2 part E continuation state, updated 5 October 2026 at 16:15 UTC.

Latest update, 16:29 UTC (overrides earlier live-resource/session notes): head
bfa112a after recipe commits107909a/fac5a19. E resumed atONE worker in session
14688 using the unchanged ccb export and its10 completed batches. Final
Microcosm serial pair at3cf3144 is active in session38698, run-label final3cf,
reusing `.cache/microcosm-check/final-d_legacy.aggregate.json` and
`final-d_both.aggregate.json`. Fresh RAM recovered to79GiB/load27on18CPUs.
D coordinator remains1worker; an extra serial far-end D pair helper is
authorized only after freshavailable>=40GiB and compressor<25GiB, at most3
EFRS overall. Read-only Subfleet admission coordinator20261005-122437-model-v2-e-admit
is queued to request this workspace's writable continuation once parent is
terminal; direct concurrent writable admission was rejected and is not bypassed.
Independent review20261005-084849-review remains queued. Task is NOT complete.

Continue the original authorized task until every requested run, test, draft,
PR-body update and independent Subfleet review is complete. Work ONLY in this
assigned workspace. Do not merge main, post GitHub comments, rewrite history,
change operator holds, or change Max's d955/d833/d778 decisions.

The protected `.git` marker points at the original detached ee02c8d checkout.
Current work uses workspace-private Git metadata: prefix every Git operation
with `GIT_DIR="$PWD/.git-e"`. Branch is model-v2-e, pushing ONLY model-v2.
Use `/usr/bin/git` for pushes; Homebrew git has a TLS failure. Current local
head is 4f4bbca; inspect the actual head because this note is a checkpoint.
All scientific sources were frozen at
3cf314445db944bf6f33f1943ae11b22b5146a33. Later recipe/docs changes do not
change scientific files. PR #24 remains OPEN and draft.

All required GitHub input is cached under `.cache/review-inputs/`. The original
job prompt is copied into the continuation prompt. Required external pilot
folders were read but must never be written. Drafts live at workspace paths
`out/E-reply-vahid.md`, `out/E-maria-14.md`, `out/E-pr24-body.md`; requested
external draft destinations are outside sandbox writable roots. Preserve
these files in commits and report their workspace paths honestly.

Engineering is implemented and committed: upper flat-rate sensitivity (kept
default); total-only ONS aggregate control; content-hash represented ages;
independent household-income fiscal identity with a mutation test; core pin;
C1 handoff/rulings/fake engine tests; independent mean-path scenarios; Kish
effective-size first-phase SE; full-year pristine EFRS batching. New
total_matched control targets the EXACT sum of existing age/sex targets using
one population margin, without changing the original six modes. Source commit
3cf3144 has pure/Hypothesis and synthetic full-engine validation.

Environment: `.venv313` Python3.13.9, PE UK2.120.0, core3.32.16; installed lock.
Always set TMPDIR="$PWD/.cache/tmp", HF_HOME="$PWD/.cache/hf",
OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1, VECLIB_MAXIMUM_THREADS=1.
Authentication: HUGGING_FACE_TOKEN=$(agent-secret get HUGGING_FACE_TOKEN_MAX),
ONLY in environment, NEVER printed. Primary dataset is materialized under
`.cache/datasets/`. Host128GiB/18logical CPUs. At most3 EFRS and2 Microcosm
workers; respect current RAM rather than merely filling the caps. top/ps and
swap APIs are sandbox-denied; vm_stat and psutil aggregate metrics work.

At this checkpoint host load169/18CPUs and compressor69GiB. NO NEW MODEL
LAUNCHES until resource recovery. Parent has reduced/stopped its E2 pool:
session36476 exited130, with10 completed aggregate batches preserved. D1 is
still running, with central+6/40 paired draws complete, slow on9699 both.
Parent's native21600s runtime ends around18:09UTC. A continuation must first
wait for parent job20261005-080931-model-v2-e to be terminal, avoid competing
writes or computations, then inspect fresh resources and resume checkpoints.

Remaining scientific work:

1. E six-mode pilot: immutable export `.cache/pilot-e-ccb857c`, actual source
   ccb857cbc6d1745f589258b8b57e693123129462. NEVER edit this export. 41 batches
   each containing frozen/reweight/types/both/total/both_full_new, plus6coverage
   jobs =252 full labels,47 process jobs. Completed batch cache is
   `.cache/pilot-e-ccb857c/.cache/jobs-pilot-e/`. Resume ROOT driver against that
   exact export/cache, initially1worker after RAM recovery; it will select
   only safe aggregates and include updated population/complement checks:
   `scripts/run_model_v2_e_pilot.py --source .cache/pilot-e-ccb857c --source-head
   ccb857cbc6d1745f589258b8b57e693123129462 --country-benchmarks
   data/pilot/country_benchmarks.json --workers 1`. Final public output is
   data/pilot/model_v2_e.json. All13fiscalyears are calculated before selecting
   2034/2039; never shorten or reorder the calculation sequence.

2. D publication-support audit: original source498d970123adff4e8f05908e17c7b366ba71a28c
   exported `.cache/pilot-d-source`; canonical immutable audit driver is
   scripts/audit_model_v2_d_fiscal.py (commit5444a90). Atomic aggregate pair
   checkpoints `.cache/d-fiscal-full-reuse-support/`. Resume coordinator after
   parent termination; it skips complete checkpoints. Do not edit its driver
   (receipt hashes would change). Once free slots exist, pair helper
   scripts/audit_model_v2_d_fiscal_pair.py --draw INDEX can precompute untouched
   far-end indices while coordinator consumes earlier ones. Never duplicate
   an in-progress pair. Then scripts/assemble_model_v2_d_support.py.
   Coverage audit d_support_audit.json is complete. Full fiscal support needs
   central+40pairs+3bridgeextras+newercentral+OBR. Central full old-engine
   calibration passed24 comparisons for each legacy/both treatment, including
   all13year calculation order. Keep retained D numerical values unchanged:
   archived replays have 2039 UK/GB net discrepancies; publish only equality
   flags/limitations, not unsupported differences or explanations.

3. Matched-total supplement: scripts/run_model_v2_matched_total.py is committed
   at4f4bbca, tests10pass withrenderer. Export frozen scientific source3cf3144
   using private Git, hardlink the verified primary H5 into its store. 41
   THREE-mode batches frozen/reweight/total_matched,123paths,no coverage. Use
   --reference-results data/pilot/model_v2_e.json and --reference-cache the
   original E cache. Requires exact82 frozen/reweight reference matches plus
   model-read shared target proof before combining tables. No reused fiscal
   values. Output data/pilot/matched_total.json. Current helper/renderer names
   matched_population_total_effect and matched_age_structure_effect.

4. Final Microcosm: two fresh cold full13-year both paths at3cf3144 still NEED
   execution. `.cache/microcosm-check/` holds validated original D legacy/both
   private aggregate receipts and exact ccb intermediate proof. Reuse ONLY
   original D receipts, never relabel ccb as final. Driver
   scripts/run_model_v2_determinism.py --current-head3cf3144 --reuse-historical-receipts
   BOTHPRIVATEPATHS --workers1|2. Single admission44GiB, two80GiB. Actual full
   SHA required; CLI stale control cannot redirect. Public output
   data/pilot/microcosm_support_and_determinism.json; source/engine/packages/data/
   spec/cold fingerprints must ALL match. Source correspondence must match
   final Git head science. No aggregate fiscal levels enter public receipt.

5. Final EFRS cold checks: scripts/run_model_v2_efrs_determinism.py --headFULLSHA
   --workers1|2; eight full paths: centrallegacy/frozen/both and draw2948both,
   each repeatedcold. All13years, fingerprint2034/2039 only. Start only allocated
   free EFRS slots. Then record verdict/actualheads in docs/MODEL_V2_PILOT.md.

Publication/evidence agent owns uncommitted imports:
data/pilot/{version_bridge,integrated,coverage_gb_dwp,microcosm_central}.json,
docs/MODEL_V2_PILOT.md, scripts/{import_model_v2_pilot,bind_model_v2_d_support}.py,
tests/test_pilot_evidence.py. All retained numbers exact, A–D review verdicts
summarized without transcripts. Final binder runs current record-redactor on
ALLpilotJSON and binds complete D/MC support receipts plus replay flags.
Strict tests reject generic id/weight/amount fields too. Do not commit pending
receipts as complete or alter old pilot figures. Old2.90.2 labels committed
0c5f087 change no number. Country verified ODS/sha/exact2024combinedoutturn are
committed48d9641; requested annualrecipient/basic/new/countryforecasts are
UNAVAILABLE, never inferred. All cells minimum10, complementary suppression.

Full pytest currently running session79655 at `.cache/pytest-final.log`, 766
collected before later added tests. At16:06 it had reached test_model.py; do not
run another suite concurrently. Final suite/checks need only documented3stale
failures: test_results/test_not_stale, test_scenarios/test_not_stale,
test_method_text_percentiles_match_the_past_years_check. Preliminary original
fullsuite had12failures/711pass/1skip; all nonreceipt implementation failures
were fixed. Focused newlogic tests pass; receipts await completion. Dashboard
FINAL80testsPASS/lint0errors2OLDwarnings/productionbuildPASS (logs.cache/c1-dashboard-*).
No dashboard changes afterward, so do not repeat absent new changes.

Independent review MUST use Subfleet, never in-session agents. Queued standard
review job20261005-084849-review since12:48UTC (out/E-review-1.md), awaitingcapacity.
Check actual state. Prompt explicitly names privateGit and pending receipts.
After completed artifacts/head, request final standard-tier Subfleet review,
fix findings and repeat untilAPPROVE. Never release holds/change account policy.
Optional user capacity question has been asked; no answer. No approval verdict
exists yet. Normal Git metadata cannot show final diff; reviewer must use.git-e.

Render public UK/GB2034/2039 central/pairedmeans+total/path/firstphaseSEs beside
retained D via scripts/render_model_v2_e_tables.py --matched-input MATCHEDJSON.
It refuses unproved matched refs/targets and preserves suppression. Put short
tables/links and all limitations in MODEL_V2_PILOT. Fill two drafted replies,
PR body, exact test count and commits. Commit each coherent step. Push only
model-v2 with/usr/bin/git, gh pr edit24 --body-file out/E-pr24-body.md; no comments.
VerifyOPEN/drafttrue/headmodel-v2. Force-add only safe requested out Markdown
drafts/report if needed; out ignored by default. Final report must cover every
Vahid item/commit/test, legal sensitivity/full-run results, controls/countries,
determinism/review, draft paths, Max's still-unmade d955/d833/d778 decisions.
