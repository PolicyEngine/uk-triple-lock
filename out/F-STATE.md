# Part F checkpoint

Work only in this assigned part E workspace; preserve the untracked abandoned
`data/pilot/d_fiscal_support_audit.json`. All Git commands use
`GIT_DIR="$PWD/.git-e" /usr/bin/git`; local branch model-v2-e, pushes only
`origin HEAD:model-v2`. PR24 stays draft; no GitHub comments or main merges.

Base: 5fc1b19e6011c5014f0471590c66c1f8e637f53a (parts E and G).
Pre-registration: 65343e2ee43a359f056ce5a027739509d32ab49f, METHOD.md only,
committed and successfully pushed before any C2 implementation or scores.
Max d955(c): statutory suspension, exclude legally fixed cells, original primary
only; failing primary automatically routes to (a). Current inputs permit only a
dry run. Binding after September CPI and 28 October Budget inputs; fiscal
rebuild on d778 certified bundle after d833, outside this task.

In progress: code, legal exclusion/property/routing tests, dry run, runbook/schema,
full pytest and dashboard checks, independent STANDARD Subfleet review until
approval. No microsimulation runs authorized here. Full pytest requested; clarification pending for existing synthetic PE simulation
tests because this task separately prohibits microsimulation runs. Preserve that
limit; report any simulation-test skips explicitly.
Comment must be drafted within workspace first; requested external
~/reviews/uk-triple-lock-2026-09-29/out/F-comment-14.md is outside writable roots.
Final report: out/F-final.md. State updated at every coherent commit.

Dashboard completed: bun run test 83/83 PASS (4 files, 38.18s); lint and build
exit0. Logs .cache/F-dashboard-{test,lint,build}.log. No dashboard source changes.
Docs/schema/comment drafted; code and focused tests still in progress.

Implementation ready: generic legal-year scoring/exclusions and pooled cells;
C1/C2 rule objects share byte-identical thresholds; C2 CLI/handoff validates
committed rule, fresh Budget/September/July inputs and complete origins. Build c
reads only binding handoff, preserves original primary or automatically falls
through to a; schema keeps quantitative published sensitivity and scenario
envelope. Focused adapter22/22 PASS; combined85 PASS before final dry-run
fiscal-eligibility refinement (final combined85/85 PASS,15.16s). No PE jobs run.
Next: exactly one current-input C2 dryrun and full pytest collection under
.cache/f_no_policyengine_runs.py guard, then independent STANDARD review.

Implementation committed/pushed67b10d383f1fc54ca58a310666bb5c9c158861da.
LIVE root sessions:83261 C2dryrun, log.cache/F-c2-dry-run.log;96865 full
pytest guarded against all PE simulation constructors, log.cache/F-pytest.log.
Commands use .venv313 and BLAS/OMP1, private Git, task TMPDIR. No model builds.
PR24 read-only API verifies OPEN/draft/model-v2, head67b10d3.

FirstC2dryrun83261 TERMINAL0. Requiredcoverage matched but wideraudit found
inherited52b80bf roundingdefault differs fromC1 unrounded convention; preserved
all outputs underout/uncertainty-c2-first-dry-run, tracked scores/selection/handoff.
Explicit unrounded candidate/past fix delegated; will commit before rerun.
Full guardedpytest908collected finishing, two additionalE sourcecorrespondence
failures being investigated without PE runs or relabelling historicalreceipts.

Unrounded correction ready: four explicit decimals=None candidate/past calls;
legacy comparator precision unchanged. Three analyticregressions; focused
88/88 PASS34.06s. First guardedfullpytest96865 TERMINAL1:908collected,
844passed/5failed/59skipped285.17s;58simulationguard skips plus1historical.
Two Ecorrespondence failures are being corrected by immutable calculationhead
verification and unchanged fixed-spec fiscalruntime proof, not relabelled
receipts or newmodelruns. Three originalstale failures remainpermitted.

DefinitiveC2dryrun18037 TERMINAL0; requiredcoveragePASS,340 C1mean
comparisons within1e-12 and entirepastrecords exact afterunroundedcorrection.
Futurebaseline/pairedhashes unchanged. PortableJSON/table ready tocommit.

Historical E correspondence verified without models: immutable recorded Git
sources, worker recipes and macro/ONS inputs match their receipts; protected
fixed-spec fiscal helpers match current code. The broader F source hash differs
and is explicitly reported as such. Test-only correction plus tamper regressions
53/53 PASS; proof out/F-E-correspondence.json. E receipts remain unchanged.

Pre-parser final full suite completed: 916 collected, 854 passed, only the
three documented stale-result failures, 59 skips (58 PE guard + 1 historical),
147.68s. Full collection, not an unguarded pass. Integration check then found
forecast-only rows needed by new statutory origins would break the legacy
calendar-error parser. A narrow parser fix and pure regressions are in progress;
current-input scores will be refreshed to retain valid code-hash provenance.
Dashboard remains passed. Independent review waits for this final fix/check.

Forecast-only CSV fix finalized: load_forecast_errors skips only valid rows
whose outturn/error are both blank, and retains strict malformed/partial checks.
Legacy observed errors reproduce byte for byte; C2 keeps their forecast means.
102 focused C2/adapter/parser tests PASS (15.12s). Historical E proof now
protects the whole history_data AST except that unused fixed-spec CSV loader.
Next: commit/push parser; final guarded full suite and provenance-fresh dry run;
then independent STANDARD review.

Parser committed/pushed 4ffd465. Final live root sessions: 68692 guarded
pytest (.cache/F-pytest-post-parser.log), 27983 fresh dry score/handoff
(.cache/F-c2-post-parser-dry-run.log). No PE jobs; parser-only changes leave
scientific inputs/design unchanged. Sourceproof regenerated at committed tip.
