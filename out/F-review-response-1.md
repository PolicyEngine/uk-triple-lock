# Response to independent review 1

Review: [F-review-1.md](F-review-1.md), REQUEST CHANGES on M1. All changes are
committed on model-v2 with no history rewrite, numerical threshold changes or
PolicyEngine runs. A second independent STANDARD review is required.

- **M1:** Schema describes the actual C2 adapter result: its short method string,
  strata, calibration and Monte Carlo fields; frozen C2 diagnostics replace
  optional legacy backtest/past/history-target fields. Backend result checks
  reconstruct the verdict from saved C2 summaries, verify the original primary,
  requested/effective ruling and all provenance/envelope entries, and recompute
  published fiscal estimates and paired differences when present. Fallback
  checks validate omission and scenarios without accessing absent EV fields.
  Synthetic pass/fail and damaged fiscal/route/table cases test these checks;
  scorer calls are forbidden. Dashboard displays retained C2 coverage/bias and
  past-years diagnostics under either outcome, with published sensitivity and
  C1 disclosure. The default and both full synthetic dashboard result-contract
  suites pass; EV/legacy-only checks run when their inputs exist. Actual public
  result files are unchanged. The runbook states which contract checks apply.
- **L1:** `expected_value_authorized` and `authorization` distinguish a dry-run
  diagnostic verdict from permission. Current artifacts explicitly say false
  and `dry run: no expected value authorization`. Binding authorization is true
  only for an original-primary pass. The validator checks both fields. Standalone
  mean-path commands explicitly authorize no expected value of their own.
- **L2:** `scoring_head` records the commit before scoring; the handoff validates
  a real 40-character commit ancestral to the current build and matching score
  provenance. It is carried through scores, selection, handoff and results.
  The schema/code state that SHA checks detect accidental drift and provide an
  audit link; they do not authenticate artifacts jointly rewritten by an
  adversary. The current scoring commit is 2ccf3811481763ad5e11e54f77a2aaf5c977f4de.
- **L3:** The assumptions strip uses the actual primary failure and automatic
  d955(a) reason for C2 fallback, and refuses missing fallback reasoning. The
  dashboard uses the same reason under fallback.

All numeric scores, per-origin rows, past-years records and origins remain
exactly unchanged from the definitive unrounded dry run. Future draw hashes
remain unchanged. The frozen rule still matches the documentation-only
pre-registration 65343e2ee43a359f056ce5a027739509d32ab49f byte for byte.

Review dispatch 2 exports the private Git history and source diff beforehand,
so its read-only snapshot contains all implementation/scoring commits and
verification evidence. The protected ordinary .git remains an older head;
.git-e is the assigned private history. No GitHub message is posted, and PR24
remains a draft.
