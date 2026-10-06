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
  zero; strict CI report checker permits only REBUILD.md's three named stale
  assertion failures. Six focused float/CI checks passed, 74.13 seconds.
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
  warnings, in 543.37 seconds. The strict JUnit checker accepted exactly those
  three named assertions for this draft PR; every other failure remains fatal.
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
pending. An independent shell-enabled Subfleet code review has started in that
clone; its verdict and the final review of the completed diagnostic are pending.
The [dominant-path diagnostic](../../data/pilot/full_new_net_se_diagnostic_validated.json)
completed fresh full thirteen-year kept and full-new replays. Both policies'
2034–35 and 2039–40 gross/net endpoints match the original caches exactly.
Five portable audit and diagnostic checks passed in 8.20 seconds, including
recipe/input/formula hashes, endpoint correspondence and linked publication
support. A separate aggregate probe will check Guarantee Credit amount and
actual receipt before the mechanism is classified; no incomplete output is used
as evidence.
