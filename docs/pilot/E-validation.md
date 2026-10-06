# Part E validation record

Historical validation in the original private-Git workspace. Part H corrects the normal-clone limitations and supersedes these test claims with [fresh shallow-clone validation](H-validation.md).

**Python, final E evidence and refreshed dashboard validation are complete, with only the three permitted stale-results failures.** The full clean suite collected **873 tests: 869 passed, three failed, one skipped**, with 19 warnings, in **3310.81 seconds (0:55:10)**. It exited **1** because of the three failures listed below. All refreshed dashboard commands exited **0**. Final independent standard Subfleet review **APPROVE** is recorded in the historical APPROVE verdict (job and reviewed head below), job `20261006-023048-model-v2-e-final-review`, at review head `e64657f8621298b0cfb101f2614dd207efd2555e`.

The full Python suite's actual tested head is **`7bf01575760e40f8b4b0c360a124da1713471bcd`**. The parent run confirms that Python source, tests and dependencies remain unchanged through **`166e23abc9f1be35fbe54257a7346fc14b6bf7cd`** and the evidence commit **`dea4866`**. The final E targeted checks ran at actual head **`166e23a`**, against the newly materialized evidence. Dashboard presentation and tests changed in `166e23a`; the earlier `c38d4da` dashboard results below are historical and do not establish validation of that change.

The completed clean command was **`.venv313/bin/python -u -m pytest -ra --durations=20`**, at actual tested head **`7bf0157`**. All **22 model cases passed**, including both fixed ordinary/already-installed entry states. The suite owner confirmed the command, counts, duration and termination; this public record uses that completion report and no raw private run logs.

The final E targeted command was:

```sh
.venv313/bin/python -u -m pytest -ra --durations=10 --tb=short tests/test_pilot_evidence.py tests/test_model_v2_e_driver.py tests/test_e_coverage_driver.py tests/test_pilot_table_renderer.py tests/test_model_v2_determinism.py tests/test_model_v2_determinism_resume.py tests/test_model_v2_efrs_determinism.py
```

It collected **155 tests; all 155 passed**, with no failures or skips, in **26.92 seconds**, and exited **0**. This includes privacy/redaction checks over the new pilot JSON, fiscal and coverage drivers, the table renderer, Microcosm resume/current-source receipts, and the Enhanced FRS current-source receipt. The thread-capped environment and private logs were preserved; no survey model job was admitted for these checks.

Direct read-only checks also passed. They verified all **12 recorded frozen-source semantic hashes** using the engine's semantic-hash method, the aggregation driver's and frozen estimator's byte hashes, and the installed package versions, including **policyengine-uk 2.120.0** and **policyengine-core 3.32.16**. The fresh coverage receipt's SHA-256 matches its saved artifact, and the entire coverage payload matches `data/pilot/model_v2_e_coverage.json`. The committed macro-specification hash, original **40 unique paired draw indices**, their multiplicities, order and stratum probabilities match exactly. Population descriptors pass the forbidden-field guard and remain unchanged by record redaction.

The final fiscal artifact has **104 central and 104 paired cells**, with unique, aligned identities covering six treatments and seven recorded contrasts, UK/GB, gross/net and 2034/2039. Metadata records **41 fiscal batches**, representing **246 full treatment-path runs**; the completed replacement coverage receipt supplies the six coverage runs. The **648 country comparison cells** are unique; unavailable benchmarks retain null DWP values and differences. The historical D binding retains its figures and the explicit **£1m (0.001bn) absolute, zero-relative tolerance**.

Final artifact **`data/pilot/model_v2_e.json`**, committed with the fiscal table and state in **`dea4866`**, is **670,216 bytes**, SHA-256 **`ee4ef921cc013054bc6516210a52bfd593864654b564b8ba76698e57f1e1b771`**. Attribution correction **`8f712cc`** regenerated it through the same exact-cache-only assembly: **670,323 bytes**, SHA-256 **`ac3ad91ca4650108dab90b2dbaae92808a913160fd174371a01d5c875bd3ee7a`**, with every numeric value unchanged (see the last section). Direct read-back of **`docs/pilot/E-fiscal-tables.md`** exactly matches the renderer's selection from that JSON; the table is **11,695 bytes**, SHA-256 **`b465e967a9eff7421304a0132b506a583f1181b7e0a323d43eac3ffa6a3b790d`**. The renderer selects recorded values and preserves withholding; this check does not calculate new contrasts or SEs.

The refreshed dashboard checks ran sequentially in `dashboard/` at presentation-fix head **`166e23a`**. The owner verified that the dashboard directory is unchanged from that head through the current head and reports:

| Check | Refreshed result |
| --- | --- |
| `bun run test --testTimeout 30000` | Exit 0; **83 tests passed** in four files; **19.44 seconds** reported by Vitest, **29.56 seconds** elapsed wall time. |
| `bun run lint` | Exit 0; **zero errors, two existing warnings**; **87.48 seconds** elapsed wall time. The warnings remain `ChartLogo.jsx` (`@next/next/no-img-element`) and `Dashboard.jsx` (`react-hooks/set-state-in-effect`). |
| `bun run build` | Exit 0; **production build passed**, all **three static pages** generated. Compilation took **56 seconds**; elapsed wall time was **115.19 seconds**. The only notice was Node **DEP0205**. Owner session **40074** is terminal. |

The following dashboard checks ran on 5 October at the earlier `c38d4da` source. Their results are retained as history:

| Command | Recorded result |
| --- | --- |
| `bun run test --testTimeout 30000` | Exit 0; **81 tests passed**, four test files; 125.13 seconds. |
| `bun run lint` | Exit 0; **zero errors, two existing warnings**: `ChartLogo.jsx` (`@next/next/no-img-element`) and `Dashboard.jsx` (`react-hooks/set-state-in-effect`). |
| `bun run build` | Sequential retry exited 0; **production build passed** under Next.js 16.2.6/Turbopack. Compilation took 7.3 minutes, TypeScript 14.0 seconds and static-page generation 86 seconds. `/` and `/_not-found` were prerendered. |

At that historical source, the initial default five-second-timeout test attempt recorded 80 passes and one timeout in the all-tabs render test (7.470 seconds). The retry changed only the execution timeout; source and assertions were unchanged between those attempts. The recorded-2032/2034 scenario-year test and legacy-2031 fallback passed in both. The first concurrent build hit its CSS-process IPC receive deadline; the sequential retry passed at that source. These owner-reported historical results are superseded for current validation by the refreshed checks above.

The previous full pytest suite completed with **869 collected: 864 passed, four failed, one skipped**, and 19 warnings, in 6162.75 seconds. Three failures are the documented stale-results checks listed below. The extra failure was `tests/test_model.py::test_model_horizon_changes_only_the_private_pension_uprating`: its supposed unextended reference inherited globally installed `YEARS` from preceding tests. The isolated installed-entry reproduction also failed in **57.43 seconds**.

Test-only correction **`7bf0157`** resets the pinned upstream builder's 2020–2034 `YEARS` and cache inside the test's monkeypatch context, exercises ordinary and already-installed entry, and restores the incoming state. **Three focused parameter checks passed in 21.68 seconds**, followed by the completed clean full-suite result above. Calculation code under `src/` did not change.

The completed clean suite's three failures are exactly the documented stale-results nodes permitted before the rebuild:

- `tests/test_results.py::test_not_stale`
- `tests/test_results.py::test_method_text_percentiles_match_the_past_years_check`
- `tests/test_scenarios.py::test_not_stale`

The one clean-suite skip is reported at **`tests/test_results.py:691`**: the historical result was built before the pipeline assumptions block. No other Python failure remains. Final standard Subfleet review is **APPROVE** at `e64657f`; the reviewer inspected public files and code, did not execute tests or recompute hashes, and relied on this completed validation record.

## Attribution correction, 6 October

**`8f712cc`** corrects the D support binder's text, which attributed the stop of the per-path national contributor audit to Max, in places as a ruling by Max. Max made no such ruling; the audit was stopped before completion as a scope cut, because national fiscal totals draw on thousands of records. The corrected text attributes the cut to no one. No model was run and no number changed.

- **Generator check.** Before the edit, the unchanged `scripts/bind_model_v2_d_support.py` rewrote every `data/pilot/*.json` byte for byte.
- **Regeneration.** The corrected binder rewrote `d_national_fiscal_support.json` and the support audit of `coverage_gb_dwp`, `integrated`, `version_bridge` and `microcosm_central`. The exact-cache-only E assembly then rewrote `model_v2_e.json`, using the unchanged public driver and all 41 exact fiscal checkpoints, with **zero model workers**. The untracked abandoned `d_fiscal_support_audit.json` was not changed.
- **No number changed.** A leaf-by-leaf comparison of the six files before and after found identical key paths, and every numeric leaf has the same path and value (136, 1,365, 345, 44, 324 and 5,829 numeric leaves). After ignoring `scope`, `per_path_national_audit`, the hash fields and `generated_at`, the files are equal. The only changed leaves are those text fields, the national receipt SHA-256 (`b4a3b115…` to `5742120d379529d7e9203fd97d7b0719c80f6adb881b561f14a53b9f8770c311`), the E receipt's bound `integrated.json` SHA-256 (`620b07ea…` to `8c53818da819962805c8bf281df2b379fa5b4bcbe8f50bb32f40da67a2b8de47`) and `generated_at`.
- **Tables.** The re-rendered `docs/pilot/E-fiscal-tables.md` is byte-identical: 11,695 bytes, SHA-256 `b465e967a9eff7421304a0132b506a583f1181b7e0a323d43eac3ffa6a3b790d`.
- **Microcosm proof.** `data/pilot/microcosm_support_and_determinism.json` (`ac231af`) is unchanged. Its `retained_D_source_sha256`, `826f88fc…`, is the pre-correction `microcosm_central.json` that the proof read. Regenerating the proof would need a new model run, and the correction changes none of the figures it compared.
- **Tests.** `tests/test_pilot_evidence.py` now fails if the support-audit text names a ruling or Max. All four families failed that check on the uncorrected files. With the corrected files, the targeted command above collected **155 tests and all 155 passed**, in 30.80 seconds, exit **0**. The adjacent `tests/test_country_benchmarks.py` and `tests/test_matched_total_driver.py` passed **8 of 8**. Python source under `src/` and the dependencies are unchanged, so the full-suite result at `7bf0157` and both cold proofs keep their source correspondence.

The same correction makes `docs/METHOD.md`'s matched-total line neutral; it had attributed that scope cut to Max too. The correction changes wording and hashes only, and the final review did not cover it.
