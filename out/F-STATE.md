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
