Independently review Model v2 part F in this assigned worktree. Return APPROVE
or REQUEST CHANGES, with concrete file/line findings and severity. Do not edit
files, post to GitHub, run PolicyEngine or read survey files/private caches.
Review public code, docs, tests and committed out/F artifacts. This is the
requested STANDARD independent Subfleet review, not an implementation agent.

The private Git directory is .git-e. Every Git command, if tools permit it,
must be prefixed GIT_DIR="$PWD/.git-e" and use /usr/bin/git. The protected .git
points at an older worktree head. out/F-history.txt exports the actual private
Git history with timestamps and changed files. Verify the pre-registration
commit 65343e2ee43a359f056ce5a027739509d32ab49f changes METHOD.md alone and
precedes EVERY C2 implementation/scoring commit. It was pushed separately
before implementation/scoring (receipt in out/F-registration.json). The SHA
annotation was a follow-up commit; the frozen rule markers must match that
original commit byte for byte. Do not mistake existing C1 scores for C2 scores.

Read out/F-final.md, out/F-validation.md, out/F-rule.md, out/F-dry-run.md and
out/F-STATE.md first, then docs/METHOD.md, UNCERTAINTY_PILOT.md, REBUILD.md,
RESULTS_SCHEMA.md and the diff from base 5fc1b19e6011c5014f0471590c66c1f8e637f53a.

Required checks:
1. d955(c): earnings=CPI in forecast/outturn for legally suspended years.
   Exclusions follow the legal regime, not numerical zeros or an enumerated
   cell list. Pool annual scored cells equally; retain suspended years in
   terminal compounding. Synthetic alternative years and wholly fixed
   statistics are covered. Verify dry-run primary A 4/6 terminal and 80% annual
   on 20 cells; published sensitivity 1/6 remains disclosed.
2. Every C1 threshold unchanged, with byte-identical rule thresholds; only
   treatment/exclusion differ. Published-earnings tables never affect C2
   verdict. Proper scores/finite checks/complete origins retain their meaning.
   C1 common coverage failure and extra candidate-specific failures remain;
   the post-scoring rule change is disclosed plainly.
3. C2 original monthly VAR(1) bootstrap stays primary if it passes. No passing
   alternative can replace it or be averaged. Build ruling c reads frozen C2
   handoff, never silently re-scores; failing primary automatically routes to
   effective a with no EV and explicit reason, retaining independent scenarios.
4. Rule SHA, frozen section, input/code hashes and score/verdict are validated
   before any fiscal job. Dry-run handoffs cannot authorize binding EV. Binding
   inputs require September 2026 CPI, May–July 2026 AWE and dated official 28 Oct
   Budget forecast means, consistent raw/statutory central inputs, committed
   inputs and newly complete spring origins (including missing March 2022 H4).
5. Results label permitted EV model-conditional beside central/OBR wedge/
   historical last-decade replay/paired ±0.5pt scenario envelope. Replay is
   explicitly April 2017–2026 historical, not extrapolated into a future fiscal
   range. Quantitative published sensitivity, C1 failure and C2 outcome remain
   in results provenance even when EV omitted. No fiscal outputs invented.
6. Runbook exact commands cover pass/fail with same c input; certified d778
   bundle follows uk-data batch d833. Review job counts/formulas under both
   outcomes. PR24 remains draft and only HEAD:model-v2 was pushed.
7. Review routing/property tests, validation results and scope limitations.
   Task explicitly prohibits PE microsimulation runs and asks full pytest:
   full collection used a temporary guard skipping PE constructors. All skips
   are disclosed; no survey runs made. Do not describe this as an unguarded
   full-suite pass. Dashboard test/lint/build completed separately.

Requested external comment destination is outside writable roots; the comment
is drafted in out/F-comment-14.md and unposted. Do not move/post it. Your own
review verdict and final review-result commit may remain pending at review
dispatch; all implementation, scores and validation must already be complete.
