# PR33 Savings Credit result review

VERDICT: APPROVE

Reviewed on 20 October 2026 against authoritative source head
`2f40b798b4e24149977463ee984bd6aeef4d87ec`, since
`503eaa5`. The delta touches only three files:
`docs/HB_ALLOWANCE_REVIEW.md`, `tests/test_hb_link_central.py` and the new
`data/diagnostics/sc_threshold_central.json`. All three are byte-identical in
the authoritative checkout and this review snapshot, as are
`data/diagnostics/hb_link_central.json` and `scripts/compare_hb_link.py`. The
authoritative checkout was only read. This artifact is the only tracked change
from the review.

## Findings

No blocking findings.

- **Aggregate-only allowlist:** `data/diagnostics/sc_threshold_central.json:1`
  has exactly the HB file's ten top-level keys. Its 13 year keys (2027–2039)
  each hold only `gross`/`net`, and each of those holds only `current`,
  `linked` and `linked_minus_current`. All values are finite floats. The file
  has no records, identifiers, weights, counts, host data or engine
  provenance. No dashboard, `src`, pipeline or CI code reads it.
- **Receipt agreement:** I read only selected fields of the private
  `.cache/sc-threshold-comparison.json`: status, timestamps, method labels,
  host admissions, version and certification metadata, run counts and the
  `comparison` block. The status is `completed` and
  `comparison.disclosure_status` is `available`. Both host admissions are
  `admitted: true`, at 08:49:45Z and 08:50:41Z, so "about 08:50Z" is accurate.
  The receipt has `cached_results_reused: false`, `full_pair_count: 2` and
  `policy_calculation_count: 4`, and `full_fiscal_years` covers 2027–2039.
  `certified` is true, with certification bundle `uk-6.2.6` (policyengine
  6.2.6, UK 2.125.1, core 3.33.0) and data `enhanced_frs_2024_25@1.58.0`.
  The receipt's `comparison.uk_saving_bn` **equals** the committed
  `uk_saving_bn` exactly (Python `==` on the whole tree). The version labels,
  status and disclosure also match. The receipt's `diagnostic_sha256`
  (`d2197889…6325a9`) equals the SHA-256 of `scripts/compare_hb_link.py` at
  HEAD; the delta does not change that script.
- **Shared baseline:** gross and net current-method cells match exactly in
  every year. This holds both between the committed HB and SC files and
  between the two private receipts. The fresh SC current pair therefore
  reproduces the HB baseline, as `docs/HB_ALLOWANCE_REVIEW.md:116` says.
- **Eight-year table:** `docs/HB_ALLOWANCE_REVIEW.md:105`–114 has eight rows
  (2032–33 to 2039–40). Each JSON year Y correctly becomes fiscal year Y–(Y+1).
  Every cell equals the JSON value rounded to 6 dp, or to signed 7 dp for
  differences; this was checked by script, not by eye. Gross differences are
  exactly 0 in every year. Difference identities hold to 1.5e-16 or better.
- **Headline and "about 1%":** the 2039–40 net change is −£0.0070169bn
  (−£7.02m), or **−1.1245%** of the current £0.6240157bn, which falls to
  £0.6169988bn. "−£7.0m (about 1.1%, from £0.624bn to £0.617bn)" is correct.
  HB is +£0.0013908bn (+£1.39m), or +0.2229%, so "+£1.4m (about 0.2%)" is
  correct. "About 1% or less" (`:134`) holds as an approximate band; it is not
  a strict ≤1% bound, and the text does not claim one.
- **Proposed default is explicitly undecided:** `:134` says "this proposal is
  not a decision" and that the choice remains Max and Vahid's. The
  forwardable note (`:142`) says "The choice remains yours; no decision or
  production behaviour change is made here." "Binding rebuild" is an
  established term (`docs/REBUILD.md:103`–111).
- **No combined or generalised effects:** `:130` says the two sensitivities
  "have not been estimated jointly". `:134` says "central-path results only".
  The forwardable note says the results "do not estimate other paths or the two
  conventions combined". Nothing adds the two effects together or extends them
  beyond the central UK path.
- **No production behaviour change:** the delta adds no `src`, `scripts`,
  config, dashboard or CI changes.
- **Test changes:** the HB peak check moved from a signed maximum to an
  absolute one. HB differences are all non-negative, so it still resolves to
  2037 and the original assertion keeps its meaning. The new baseline test
  checks for exact equality. The parametrised test already pins both year
  sets to 2027–2039, so iterating `hb`'s keys loses no coverage.

## Nonblocking observations

1. `tests/test_hb_link_central.py:1`: the docstring says "sensitivities
   contains"; it should say "contain".
2. In the SC table header (`docs/HB_ALLOWANCE_REVIEW.md:105`), both difference
   columns are titled "Difference". The HB table uses "Gross difference" and
   "Net difference", which are clearer.
3. Both fiscal tables start in 2032–33, but neither says why. Every 2027–28 to
   2031–32 cell in the committed JSON is exactly 0. One clause such as "earlier
   years are zero under both methods" would make the eight-row table read as
   deliberate.
4. For context, the SC relative change in 2038–39 is −1.17%, slightly larger
   than 2039–40's −1.12%. The text claims only the 2039–40 figure, so it is
   accurate. Nobody should restate it as "at most 1.1% in every year".
5. The proposed default would publish both conventions as sensitivities, which
   is Max's call. If it is not already queued, the owner session should
   register it with `cos add-decision`.

## Validation

Independent synthetic and aggregate checks, run against the snapshot's `src`
(`PYTHONPATH=src`) using the authoritative `.venv` interpreter read-only:

```text
pytest -q -p no:cacheprovider tests/test_hb_link_central.py
3 passed in 0.66s

pytest -q -p no:cacheprovider tests/test_sc_threshold_comparison.py tests/test_hb_link_central.py
17 passed in 50.15s
```

I also ran read-only scripts that check the public schema and allowlist, exact
receipt/public aggregate equality, the shared current-method baseline, the
difference identities, the table rounding, the fiscal-year labels, the
percentages and the runner hash.

I ran no full suite, heavy wrapper, rebuild or fiscal run, and loaded no
survey dataset. I read neither `.cache-hb-link-run.log` nor
`.cache-sc-run.log`, and read only the private receipt fields listed above. I
made no source changes, pushes, merges or PR comments.
