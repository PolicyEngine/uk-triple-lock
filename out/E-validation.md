# Part E validation record

**Validation is complete, with only the three permitted stale-results failures.** The full clean suite collected **873 tests: 869 passed, three failed, one skipped**, with 19 warnings, in **3310.81 seconds (0:55:10)**. It exited **1** because of the three failures listed below. Final fiscal evidence and the independent Subfleet review remain pending.

Source correspondence was checked with workspace-private Git (`GIT_DIR="$PWD/.git-e"`) at head **`da5a279bf1cc5b4df09270876a0f136409403973`**, on **6 October 2026, 05:43Z**. The dashboard directory, including its source, tests and dependency declarations, is unchanged from `c38d4da` through that head and the working tree. Calculation source, orchestration, tests and dependency declarations (`src/`, `scripts/`, `tests/`, `pyproject.toml`, `requirements-lock.txt`, `uv.lock`) are unchanged from the clean suite's actual tested head **`7bf01575760e40f8b4b0c360a124da1713471bcd`** through the checked head and working tree. Private Git reported no relevant staged, unstaged or untracked changes. Later documentation/evidence commits do not change the tested sources.

The completed clean command was **`.venv313/bin/python -u -m pytest -ra --durations=20`**, at actual tested head **`7bf0157`**. All **22 model cases passed**, including both fixed ordinary/already-installed entry states. The suite owner confirmed the command, counts, duration and termination; this public record uses that completion report and no raw private run logs.

The recorded dashboard checks ran on 5 October in `dashboard/`. Their summarized results are:

| Command | Recorded result |
| --- | --- |
| `bun run test --testTimeout 30000` | Exit 0; **81 tests passed**, four test files; 125.13 seconds. |
| `bun run lint` | Exit 0; **zero errors, two existing warnings**: `ChartLogo.jsx` (`@next/next/no-img-element`) and `Dashboard.jsx` (`react-hooks/set-state-in-effect`). |
| `bun run build` | Sequential retry exited 0; **production build passed** under Next.js 16.2.6/Turbopack. Compilation took 7.3 minutes, TypeScript 14.0 seconds and static-page generation 86 seconds. `/` and `/_not-found` were prerendered. |

The initial default five-second-timeout test attempt recorded 80 passes and one timeout in the unchanged all-tabs render test (7.470 seconds). The retry changed only the execution timeout; source and assertions were unchanged. The recorded-2032/2034 scenario-year test and legacy-2031 fallback passed in both attempts. The first concurrent build hit its CSS-process IPC receive deadline. The sequential retry passed with the unchanged build command and source. These results are copied from the dashboard check summary; no private error logs were read for this record.

The previous full pytest suite completed with **869 collected: 864 passed, four failed, one skipped**, and 19 warnings, in 6162.75 seconds. Three failures are the documented stale-results checks listed below. The extra failure was `tests/test_model.py::test_model_horizon_changes_only_the_private_pension_uprating`: its supposed unextended reference inherited globally installed `YEARS` from preceding tests. The isolated installed-entry reproduction also failed.

Test-only correction **`7bf0157`** resets the pinned upstream builder's 2020–2034 `YEARS` and cache inside the test's monkeypatch context, exercises ordinary and already-installed entry, and restores the incoming state. **Three focused parameter checks passed**, followed by the completed clean full-suite result above. Calculation code under `src/` did not change.

The completed clean suite's three failures are exactly the documented stale-results nodes permitted before the rebuild:

- `tests/test_results.py::test_not_stale`
- `tests/test_results.py::test_method_text_percentiles_match_the_past_years_check`
- `tests/test_scenarios.py::test_not_stale`

The one clean-suite skip is reported at **`tests/test_results.py:691`**: the historical result was built before the pipeline assumptions block. No further failure remains. No tests, model runs, dependency changes or GitHub actions were started to assemble this record.
