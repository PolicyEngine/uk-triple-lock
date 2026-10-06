# Part H validation

This follows Vahid Ahmadi's 6 October 2026 09:49 UTC re-review of `70aa009`.
The historical main results await the certified model/data bundle and post-Budget
inputs; this work repairs portable validation and publication privacy.

- `90536bb`: public receipts moved to `data/pilot`, tables and historical validation
  to `docs/pilot`; all 54 tracked `out/` files removed, local copies preserved.
- `d269397`: C2 raw frozen-section SHA-256 and score/input content bindings;
  support counts suppressed both in engine output and cached-result redaction;
  ageing tests restore horizon installation. C2 focused checks: 67 passed,
  64 deselected, 214.67 seconds. Support/horizon checks: 33 passed, 687.15 seconds.
- `4f9d2e4`: historical floating artifacts compared at absolute `1e-12`, relative
  zero; initial CI report checker allowed REBUILD.md's three named stale
  test failures; the later Subfleet findings below required a stricter verifier. Six focused float/CI checks passed, 74.13 seconds.
- `e875cac`: [committed source manifest](../../data/pilot/cold-source-binding.json)
  and [historical correspondence proof](../../data/pilot/historical-cold-correspondence.json).
  All 84 deterministic, resume and tamper checks passed in 163.05 seconds.
  Original source maps reproduce recorded full-source hashes. Heads remain
  provenance, and no historical Git objects are read by the verifier. The
  privacy changes have exact accepted file hashes and a narrow AST proof that
  the original fiscal calculations and redaction fields remain protected.
- `3ec6eb3`: [matching-path/cache audit](../../data/pilot/full_new_net_se_audit.json).
  Two portable audit checks passed. The dominant-path mechanism is under full-run
  diagnostic verification; no diagnosis is asserted from correlation alone.

The annotated `c2-preregistration` tag points to the original registration
`65343e2ee43a359f056ce5a027739509d32ab49f` and is pushed separately. The frozen
section is 5,114 bytes, SHA-256
`ce198c838070b175cecefb668b776731333373c8e642030456f736978eb336ac`.
METHOD.md documents tag/date/content verification and recommends a merge commit;
Max chooses the merge method. Execution does not require the tag or old commits.

The fiscal table bytes are unchanged by their move: SHA-256
`b465e967a9eff7421304a0132b506a583f1181b7e0a323d43eac3ffa6a3b790d`.
Country-table links now resolve from `docs/pilot`. Original full-run receipt
numbers and calculation-source identities remain unchanged.

At `3528e742e41d22430fccfad3e4428b59763887f0`, both GitHub checks passed:

- [Pipeline run 37465742308](https://github.com/PolicyEngine/uk-triple-lock/actions/runs/37465742308):
  the normal depth-1 checkout completed 975 tests: 971 passed, the three
  documented stale-results assertion failures, one historical skip and 19
  warnings, in 543.37 seconds. The initial JUnit checker accepted those three named failures for this draft
  PR. The later independent review found that this checker did not establish
  complete execution or distinguish unrelated exceptions under a stale-test
  name; the replacement verifier and regression evidence are recorded below.
- [Dashboard run 37465742298](https://github.com/PolicyEngine/uk-triple-lock/actions/runs/37465742298):
  all four files / 92 tests passed; lint had zero errors and two existing
  warnings; the production build compiled in 27.7 seconds and generated all
  three pages. It used the unchanged stock test runner and default build.

Local dashboard attempts were limited by host worker-startup and IPC timeouts;
they are not counted as passing. The independent clean Ubuntu checks above ran
the complete dashboard commands successfully.

The [Dashboard check at `054a0b9`](https://github.com/PolicyEngine/uk-triple-lock/actions/runs/37476366361)
also passed: 92 tests in four files, zero lint errors and the same two warnings,
and a production build compiled in 36.2 seconds with all three pages generated.

The separately installed fresh normal shallow clone's full suite is still
pending. The retained shell-enabled Subfleet code review requested changes for
three reproduced verifier/guard issues. Its export attempt was quarantined, so
it supplies no accepted final approval. The findings are being fixed, and a
new final review of all completed evidence is required.
The [dominant-path diagnostic](../../data/pilot/full_new_net_se_diagnostic_validated.json)
completed fresh full thirteen-year kept and full-new replays. Both policies'
2034–35 and 2039–40 gross/net endpoints match the original caches exactly.
Five portable audit and diagnostic checks passed in 8.20 seconds, including
recipe/input/formula hashes, endpoint correspondence and linked publication
support. A separate aggregate probe will check Guarantee Credit amount and
actual receipt before the mechanism is classified; no incomplete output is used
as evidence.

The separate probe's 21 focused privacy and admission tests passed in 6.19
seconds, including a Hypothesis publication-support property, linked
complements, receipt attribution and denied/stale/live task-PID checks. Host
process enumeration is unavailable in this workspace. The probe instead checks
its two explicit task PID receipts and holds both exclusive diagnostic worker
slots; RAM and CPU are read again before imports, dataset loading and the full
path. This is a scoped task admission check, rather than a global process count.

The [kept amount/receipt probe](../../data/pilot/gc_precision_diagnostic.json)
completed its original full path and again reproduced the endpoints exactly.
Its 2039–40 kept passport flips contain no positive Guarantee Credit awards of
at most one penny. Entitlement-only nonclaimant passport flips and Housing
Benefit changes cooccur, with the linked numeric family withheld. This is an
observational finding; a separate complete-run receipt-predicate intervention
is being prepared before the mechanism is classified. All 29 portable
audit/receipt/privacy checks passed in 1.27 seconds.

The retained early Subfleet code review reproduced a bypass in the historical AST subset guard. The guard now requires the exact committed SHA-256 of all five reviewed F modules before checking historical AST correspondence. Effective annotated, conditional and expression replacements and all-module byte/manifest tampering are rejected. The focused cold/determinism/EFRS/resume suite passed **94 tests in 280.56s**. No production source or full-run receipt changed. The independent review must be repeated after all reported issues are fixed.

The Housing Benefit receipt-predicate sensitivity recipe was reviewed before execution. It computes a fresh original and a fresh intervened thirteen-year path, with independent policy clones, replacing exactly the three positive-entitlement passport predicates with actual Guarantee Credit receipt. Savings-credit-only branches remain intact. Native/intervened contributions and their differences are disclosure checked as linked families. The recipe and its **19 passing synthetic tests (70.70s)** are committed before any execution; no sensitivity result is claimed here yet.

The CI privacy failure at `5c56a56` was the safe aggregate map `components_bn` in the dominant-path diagnostic: its unit suffix made the unchanged generic guard expect a scalar. `b9dd557` renames only that published map to `aggregate_components`, records the original receipt byte hash, and verifies reversibility. Every original count and monetary value is unchanged; the executed calculation recipe remains frozen. All 58 pilot-privacy and portable diagnostic/receipt tests passed in 59.19 seconds.

The other two retained Subfleet findings are fixed by checking pytest's actual process exit code, an independent selected/completed identity record and consistent JUnit identities/counters. Stale exceptions must match both the documented test identity and its assertion reason. RuntimeError under a stale identity, KeyboardInterrupt, pytest.exit during a partial suite, collection/setup/teardown errors and missing/tampered completion evidence fail closed. The 35 regression tests include real child pytest processes and passed in 325.79 seconds. The exact-source guard was independently rechecked with 18 focused tamper regressions passing in 43.47 seconds. A new complete-scope Subfleet review remains required.
