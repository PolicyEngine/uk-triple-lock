# Trajectory viewer: `data/trajectory_results.json`

The **Trajectories** tab compares the Burnham plan with the triple lock on a few macro paths and on past years. Every fiscal and household figure in it is a full PolicyEngine UK run on the certified Enhanced FRS. Nothing is scaled from another run.

```bash
HUGGING_FACE_TOKEN=... python -m triple_lock.trajectories   # about 25 minutes; writes data/ and the dashboard copy
python -m pytest tests/test_trajectories.py                 # needs scipy and hypothesis; no private data
```

## Future paths

A path's calendar-year CPI and earnings growth for 2027–2033 replace `gov.economic_assumptions.yoy_growth.obr` in a `Scenario` applied before the data load; RPI and CPIH move by the same amount as CPI. `process_parameters()` then rebuilds the uprating indices, so every uprated benefit rate, threshold and microdata income follows the path. A plain `reform=` dict would change the growth series and nothing derived from them.

State Pension flat rates are set from each rule applied to the path's statutory inputs (September CPI, May–July AWE), with rates to 3 dp as in the central run. The additional State Pension is pinned to the unreformed model on the same path. Each path runs three simulations (unreformed, triple lock, Burnham plan), each in its own process and working directory.

| Path | Where it comes from |
|---|---|
| Central forecast | The dashboard's central path. Its calendar values also serve as the statutory inputs, and April 2027 uses the published inputs. |
| Monthly model: middle, 90th percentile | `ts_monthly` is a VAR(3) on monthly log changes of the CPI index (ONS D7BT) and AWE total pay (ONS KAB9). It has Student-t marginal shocks joined by a t-copula and excludes the furlough months from the fit. It simulates from August 2026, so September CPI, May–July AWE and the calendar measures come from the same months. It draws 20,000 paths, entropy-tilted so that calendar CPI and earnings average the central path in every year. The path shown is the most typical draw near the weighted median or 90th percentile of the 2034-35 Burnham gap. |
| Uncertainty tab: middle, 90th percentile | The main run's representative paths, applied here to the whole model. |

Each run records the single household record that moves the final-year net figure most (`largest_household`). The tab flags a path when that record accounts for at least a fifth of the net figure. On the monthly model's 90th-percentile path, record 8566 stands for 273,720 households against a median of 96. The Pension Credit guarantee passports it to full Housing Benefit, adding £2.5bn.

## Past years

The same rule is applied to published September CPI and May–July AWE from an earlier April. These are the latest ONS vintage. In April 2022 the earnings leg was suspended, so both rules use CPI that year. The counterfactual flat rate is the actual rate multiplied by the ratio of the Burnham plan's cumulative rise to the triple lock's, on the same inputs. Start years with identical paths are grouped. Savings for 2024-25 to 2026-27, the years the survey data cover, are full runs.

## Backtests

`ts_backtest.run_statutory_backtest` scores each method against the realised statutory inputs. `run_backtest` scores against the calendar measures the OBR forecasts. Two test designs:

- **Chronological**, 2016–2021: each method uses only what was known at the time.
- **Leave-one-out**, all 12 spring vintages from 2010 to 2021: the block bootstrap sees later forecasts' errors.

Every method is calibrated to that vintage's OBR forecast. The scores are:

- the energy score;
- variogram scores split into serial, cross and cross-lagged pairs;
- a band-depth multivariate PIT;
- CRPS per value and for four-year cumulative growth;
- CRPS and 10–90% coverage of the triple-lock gap to each alternative;
- the expected against actual number of reversals between CPI and earnings.

VAR variants are also scored with years shuffled (no autocorrelation) and series shuffled (no co-movement).

## Invariants (tested)

- **Burnham plan rule** (Hypothesis, all inputs):
  - it equals the triple lock before April 2030;
  - after that it is at least max(CPI, 2.5%) and its level is never below its earnings path;
  - it exceeds the triple lock only by rounding, at most 0.1 point a year.
- **Rate sources:** each names the input that binds.
- **Entropy tilting** (Hypothesis): weights are non-negative and sum to one, and the weighted means hit the target.
- **Scores:** CRPS matches the normal closed form; the variogram score prefers the true dependence; the band-depth PIT is uniform for a calibrated forecast.
- **Committed file:**
  - rates equal `rules.uprating_path` on the recorded inputs, and weekly amounts compound them;
  - the model received those amounts and the recorded macro path;
  - savings reconcile with the model totals;
  - the central path matches the main results;
  - the monthly-model paths and past-year ratios regenerate exactly;
  - the source hashes match the code.
