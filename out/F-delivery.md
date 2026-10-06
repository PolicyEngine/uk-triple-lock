# Model v2, part F — d955(c)

Pre-registration: **65343e2ee43a359f056ce5a027739509d32ab49f**, committed and pushed with `docs/METHOD.md` alone before any C2 implementation or scoring. The SHA annotation followed in a separate commit. [Registration receipt](F-registration.json), [original committed C2 rule](F-rule.md), [history](F-history.txt).

The committed rule applies the suspended earnings leg to forecast and outturn, excludes legally fixed statistic cells, preserves every C1 threshold, keeps published earnings as sensitivity, retains only the original primary, and automatically routes a failing primary to (a). All five C1 failures and the change after seeing scores remain disclosed. A permitted expected value is labelled **model-conditional** beside the central, OBR-wedge, dated historical last-decade replay and paired ±0.5pt earnings scenarios.

The binding score waits for committed September 2026 CPI, May–July 2026 AWE, the OBR's 28 October Budget means and newly complete origins. It is one command:

```sh
.venv313/bin/python -m triple_lock.ts_uncertainty --screen c2 --binding --output out/uncertainty-c2
```

The rebuild uses the certified d778 bundle after d833, with the same `--uncertainty-ruling c` command under either outcome. The adapter refuses changed rule SHAs, scoring inputs/code, altered scores/verdicts and dry-run authorization before any fiscal job. [Exact commands and job counts](../docs/REBUILD.md).

[Definitive dry-run table](F-dry-run.md) gives every primary/alternative suspended result beside its published sensitivity, proper scores and past-years percentiles. Required primary A reproduction: **4/6 terminal coverage; 80.0% annual coverage on 20 cells; 4 exclusions**. Primary, VAR(2), Student-t and Gaussian pass; annual bootstrap fails switch CRPS ratio 1.279 > 1.25. Published primary A terminal coverage is 1/6. This is a dry run, with no expected value authorized.

The first dry run reproduced required coverage but exposed inherited terminal/past-years rounding from a prior merge. Its original artifacts remain committed. Four explicit unrounded calls restore the convention already frozen in C1 and C2; three analytic regressions protect it. The definitive run reproduces all 340 aggregate C1 mean comparisons within 1e-12 (maximum floating-point difference 4.44e-16), with the specified annual exclusions/pooling, and every past-years record exactly. Future draw hashes stayed unchanged. [Comparison receipt](F-dry-run-receipt.json), [first-run explanation](F-first-dry-run.md).

Forecast-only rows needed by newly complete statutory origins remain available to C2 while the legacy calendar comparator skips them until observations exist. Partial or malformed observations still fail. Parser and protection regressions pass; the score artifacts were refreshed after this integration fix to keep current code hashes.

[Validation and routing tests](F-validation.md) document random-table sensitivity invariance, alternate legal years, passing/failing primary routes, handoff SHA refusal and byte-identical threshold objects. No PolicyEngine simulations or survey data were used. Full pytest collection used an explicit simulation-constructor guard; its skips are disclosed rather than called a full unguarded pass. Historical E receipts remain unchanged: immutable source/input correspondence is verified separately from the broader F source hash, without a new cold-run claim. Dashboard test, lint and build passed.

The independent STANDARD Subfleet review verdict and final head are recorded in `F-final.md` after review completion. Every coherent step is committed and pushed only as `HEAD:model-v2`; PR #24 stays draft. Existing untracked `data/pilot/d_fiscal_support_audit.json` is preserved.

[Draft #14 comment](F-comment-14.md) is unposted. The requested `~/reviews/uk-triple-lock-2026-09-29/out/F-comment-14.md` is outside the permitted writable roots, so the draft remains in this assigned workspace. No GitHub comment was posted.
