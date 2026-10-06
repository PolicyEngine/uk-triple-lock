# Part F checkpoint — implementation and validation complete

Assigned workspace only. Every Git command uses GIT_DIR="$PWD/.git-e" and
/usr/bin/git; local branch model-v2-e, pushes only origin HEAD:model-v2.
PR #24 remains OPEN and draft; no GitHub comments or main merges.
Existing untracked data/pilot/d_fiscal_support_audit.json remains untouched.
Base model-v2 head: 5fc1b19e6011c5014f0471590c66c1f8e637f53a (parts E and G).

Pre-registration: 65343e2ee43a359f056ce5a027739509d32ab49f, METHOD.md alone,
committed and successfully pushed before every C2 implementation/scoring commit.
SHA annotation followed separately. Frozen section still matches that commit.
Original rule: out/F-rule.md; push receipt: out/F-registration.json.

C2 implements Max d955(c): legal suspension in draws/outturns; legally fixed
statistic exclusions; all C1 thresholds unchanged; published sensitivity only;
original primary alone; automatic a fallback after primary failure. Binding
requires committed September 2026 CPI, May–July AWE and 28 October Budget means,
including newly complete origins. No dry run can authorize expected value.
Fiscal rebuild waits for certified d778 bundle after d833; no PE runs here.
Results preserve model-conditional label, scenario envelope, C1/C2 provenance.
Existing April 2017–2026 historical replay is dated and not extrapolated.

Dry run: required primary A 4/6 terminal coverage, 80.0% annual coverage across
20 cells, four exclusions. Primary, VAR2, Student-t and Gaussian pass; annual
fails switch CRPS ratio 1.279 > 1.25. Published A terminal 1/6 remains sensitivity.
First scores preserved at 25ef918/out/uncertainty-c2-first-dry-run. Initial
rounding leak inherited from 52b80bf corrected by explicit unrounded calls at
a99ac2e, restoring frozen C1/C2 arithmetic. All 340 C1 means reproduce within
1e-12 (max 4.44e-16), every past-years record exactly; future draw hashes unchanged.
Forecast-only parser integration fixed at 4ffd465: legacy error comparators
skip valid rows lacking both calendar observation/error; statutory means remain.
Malformed/partial rows still fail. Fresh dry-run provenance at 7097e89 leaves
entire scores.json and every scientific result unchanged. Canonical artifacts:
out/uncertainty-c2-dry-run; table out/F-dry-run.md; receipt F-dry-run-receipt.json.

Final checks complete: focused C2/adapter/parser 102 passed (15.12s); historical
E source/input correspondence and tamper tests 54 passed (13.77s). Full pytest
collection 931: 869 passed, three documented stale failures, 59 skipped (176.93s).
58 skips enforce the no-PolicyEngine-constructor instruction; one historical
assumptions skip. This is a guarded full collection, not an unguarded full pass.
No survey data or simulations. Dashboard 83 tests passed; lint/build exit0.
Logs .cache/F-{history-data-focused-final,E-correspondence-tests,pytest-post-parser,
dashboard-test,dashboard-lint,dashboard-build,c2-post-parser-dry-run}.log.
Historical E receipts unchanged: source/input correspondence only, no F cold run;
broader F source hash differs explicitly. Proof out/F-E-correspondence.json.

Remaining: independent STANDARD Subfleet review; fix/repeat until APPROVE;
commit/push review verdict and final state; verify remote head and PR draft.
Review prompt out/F-review-prompt.md; final report out/F-final.md, with substantive
tracked delivery out/F-delivery.md and validation out/F-validation.md.
Unposted #14 draft out/F-comment-14.md. Requested external ~/reviews/... path
is outside writable roots; do not copy there or post on GitHub.

Independent STANDARD Subfleet review dispatched after completed validation:
job 20261006-035622-model-v2-f-review; reviewed head e8f19a6a26111ede1ee7d2e5b1c479236f90947f;
read-only; output out/F-review-1.md. User-requested CLI with -p/-o, --detach.
Review explicitly checks pre-registration precedes every implementation/score.

Review1 TERMINAL0/REQUEST CHANGES: M1 results/schema/dashboard post-build
checks must handle C2 diagnostics and automatic missing-EV fallback. Core rule,
preregistration chronology, scoring, routing, inputgates and counts accepted.
Fixes in progress: backend contract tests/schema, C2 dashboard display/tests,
explicit dry-run authmarker, scoring HEAD auditprovenance, fallback wording.
Independent repeat review required after final affected checks.

Review fixes verified: dashboard now shows retained C2 diagnostics/past check
under pass and fallback, plus accurate omission/scenario text. Default dashboard
92 passed; synthetic C2-pass whole suite 89 passed/3 optional legacy skips;
C2-fail whole suite 73 passed/19 EV/legacy skips; lint/build exit0. Public results
untouched. Python L1/L2 authorization and scoring-HEAD audit fields + L3 omission
text focused101 PASS43.71s. Backend C2 results-contract/schema checks still finalizing.

Fresh C2 dry artifacts at scoring HEAD2ccf381 TERMINAL0: every numeric score,
origin row and past record exactly unchanged; explicit expected_value_authorized
false/no-authorization text and scoring commit recorded. Future array hashes
unchanged. Canonical report/receipt updated. Independent re-review still pending
backend result-contract tests and final guarded full collection.

Backend M1 final: C2 synthetic shared post-build verifiers8 PASS1.24s (pass/fail,
route/score/sensitivity and fiscal/paired estimate tampering); legacy module56
PASS/1 historical skip/only2 permittedstale failures20.29s before2extra negative
cases. Schema matches actual C2 shape, with optional legacy diagnostics absent.
No simulations or new scoring in contract checks. Final guardedfull collection
will include all new cases; then independent STANDARD review2.

Final review-fix guarded full collection (session 61757, exit 1): 953 collected;
891 passed, three permitted stale failures, 59 skips (58 guard + one historical),
114.86s. All validation complete. Every M1/L1/L2/L3 finding is addressed.
The current dry handoff validates at f56d5b5 with authorization false, scoring
HEAD 2ccf381 and unchanged thresholds. Ready for independent STANDARD review 2;
all source/scoring commits were exported BEFORE dispatch in history, diff and
registration audit. No additional runs needed.
