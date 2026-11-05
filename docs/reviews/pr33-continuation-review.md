# PR33 continuation review

VERDICT: APPROVE

Reviewed on 20 October 2026 against authoritative source head
`2fc35f519a028359b9ac7822050628e0bf893165`, since
`167753283f00b6a70cb0b9168d65d4d498e22b22`.
The six requested source files matched both that commit and the assigned review
snapshot. The authoritative checkout was read only; this artifact is the only
tracked review change.

## Findings

No blocking findings. Risk is low for the existing HB diagnostic; the separate
SC fiscal comparison remains unexecuted.

- **Publication:** `data/diagnostics/hb_link_central.json:1` has a strict aggregate
  schema: UK central-path gross/net current, linked and difference amounts,
  status/disclosure and simple descriptive/version labels. No records, IDs,
  weights or counts appear. Restricted receipt verification confirmed selected
  completion/admission/certification metadata and exact agreement of all public
  aggregate cells; no additional receipt content is reproduced here.
- **Numeric result:** `docs/HB_ALLOWANCE_REVIEW.md:70`–87 accurately describes the
  completed HB run. All 2032–2039 gross/net table cells match the public artifact
  at their displayed precision; difference identities hold throughout the full
  horizon. Final net increase is **£0.001390797bn**, with a maximum of
  **£0.001591156bn in 2037**. The current-method final headline reproduces
  **£0.865bn gross / £0.624bn net** at £0.001bn precision; its exact net differs
  from the historical published file, as disclosed.
- **SC convention:** `scripts/compare_hb_link.py:58`–89 computes the 2026 maximum
  with decimal arithmetic and half-up penny rounding, compounds nonnegative
  rounded prior-year statutory CPI, then derives both family thresholds as
  applied guarantee minus maximum / 0.6 across all 13 years. SC and HB overrides
  are separate. Applied threshold readback occurs before each policy's totals
  (`:92`–106, `:198`–217). Tests cover existing future projections, corrupted
  applied thresholds, nonnegative maxima, threshold below guarantee for positive
  maxima, and the annual CPI relationship
  (`tests/test_sc_threshold_comparison.py:33`–139).
- **Regression and execution:** Default HB arithmetic and receipt destination are
  preserved. `scripts/compare_hb_link.py:247`–301 selects a separate private SC
  default receipt and directly requests a fresh current-method pair plus a fresh
  SC pair. The unchanged engine constructs full-horizon policy simulations;
  neither cached fiscal results nor scaling is used. Existing
  `tests/test_hb_link_comparison.py` is unchanged in the delta.
- **Documentation and scope:** The exact SC foreground command at
  `docs/HB_ALLOWANCE_REVIEW.md:100`–102 passes shell syntax checking and matches
  the wrapper's label/command interface and the runner's arguments. It was
  inspected, not executed. The original legal conclusions, production
  engine/config, C2 pre-registration and uncertainty thresholds are unchanged.

## Validation

Independent synthetic/aggregate checks:

```text
tests/test_hb_link_central.py
tests/test_sc_threshold_comparison.py
tests/test_hb_link_comparison.py
pytest -q -p no:cacheprovider -k 'not applied and not runtime_readback'
36 passed, 7 deselected in 21.28s

tests/test_sc_threshold_comparison.py::test_implied_maximum_grows_by_exact_rounded_nonnegative_cpi
1 passed in 12.03s
```

The initial keyword filter also excluded the CPI property, so it was run directly
and passed all 80 generated examples. The six processed-parameter/readback cases
were reviewed statically; the source session's focused and full validation were
left to that session. Additional
read-only checks verified the public schema, every receipt/public aggregate
cell, all difference identities, headline rounding, documentation table rounding,
shell syntax and the exact continuation file scope.

No full suite, heavy wrapper or real SC fiscal option was run. No survey dataset
was loaded, and the prohibited run log was not read. No source changes, pushes,
merges or external comments were made. GitNexus tools were unavailable; the
changed symbols and their engine callers were traced directly.
