"""The committed results file, checked against the code that produced it (no private data needed).

* Staleness: source, engine and input hashes recorded at build time equal today's.
* Every path's savings reconcile with its own model totals, and its rates with the rules applied to its recorded
  inputs (a differential check between the engine's output and the pure rule arithmetic).
* Every run recorded that the model followed its path.
* The expected value recomputes from the per-path records (the stratified estimator applied to what was run).
* Invariants: a saving is never negative beyond rounding; identical rates give exactly zero; household tables sum to
  the net change; the figures the dashboard prints are in the file.
"""

import json

import numpy as np
import pytest

from triple_lock import engine, expected_value, rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, DASHBOARD_COPY, FINAL_YEAR, HORIZON, OUTPUT, SWITCH_YEAR
from triple_lock.pipeline import hashes, package_versions

TOL_BN = 1e-9


def ints(d):
    return {int(k): v for k, v in d.items()}


@pytest.fixture(scope="module")
def results():
    if not OUTPUT.exists():
        pytest.fail(f"{OUTPUT} is missing: run the build")
    return json.loads(OUTPUT.read_text())


@pytest.fixture(scope="module")
def runs(results):
    """Every full path run in the file: the central path and the trajectories."""
    return [("central", results["central"]["run"])] + [(t["id"], t) for t in results["trajectories"]["paths"]]


# ── Provenance ──────────────────────────────────────────────────────────


def test_not_stale(results):
    now = hashes()
    p = results["provenance"]
    assert p["source_hashes"] == now["source_hashes"], "sources changed since the build: rebuild"
    assert p["input_hashes"] == now["input_hashes"], "inputs changed since the build: rebuild"
    assert p["engine_hashes"] == engine.engine_hashes()
    assert p["packages"] == package_versions(), "installed packages differ from the build's: rebuild or reinstall"


def test_built_from_a_clean_tree(results):
    assert results["provenance"]["git_dirty"] is False


def test_dashboard_copy_matches(results):
    assert json.loads(DASHBOARD_COPY.read_text()) == results


def test_not_a_sample(results):
    assert results["sample"] is False


# ── Every path run ──────────────────────────────────────────────────────


def test_rates_follow_the_rules_from_the_recorded_inputs(runs):
    for name, r in runs:
        cpi, earnings = ints(r["statutory"]["cpi"]), ints(r["statutory"]["earnings"])
        for p in ("triple_lock", "burnham_2030"):
            expected = rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS)
            assert ints(r["rates"][p]) == pytest.approx(expected, abs=1e-12), name


def test_weekly_amounts_compound_the_rates(results, runs):
    base = results["base_year_weekly"]
    for name, r in runs:
        for p in ("triple_lock", "burnham_2030"):
            lv = rules.level_path(base["new_state_pension"], ints(r["rates"][p]), HORIZON)
            got = ints(r["weekly"][p]["new_state_pension"])
            assert all(got[y] == pytest.approx(lv[y], abs=0.006) for y in HORIZON), name


def test_the_model_applied_the_rules_flat_rates(runs):
    """What PolicyEngine read back after the reform equals the rule's weekly amount, in every year and run."""
    for name, r in runs:
        for p in ("triple_lock", "burnham_2030"):
            applied, weekly = ints(r["applied_new_state_pension"][p]), ints(r["weekly"][p]["new_state_pension"])
            assert all(applied[y] == pytest.approx(weekly[y], rel=1e-9) for y in HORIZON), (name, p)


def test_fixed_inputs_are_the_same_law_under_both_rules(runs):
    """State Pension age 67 from 2028-29; the Pension Credit guarantee rising with May-July earnings; the additional
    State Pension identical under both rules (so it never enters the saving)."""
    for name, r in runs:
        spa = ints(r["fixed_inputs"]["state_pension_age"])
        assert all(spa[y] == ([67.0] if y >= 2028 else [66.0]) for y in HORIZON), name
        assert r["path_following"]["pension_credit_guarantee_single"]["max_abs_error"] <= 1e-9, name
        for y in HORIZON:
            assert r["saving_bn"][str(y)]["components"]["additional_state_pension"] == 0.0, (name, y)
        # The held types reached the model: basic State Pension spending persists to the final year (with types
        # recomputed from frozen ages it fell to zero by 2033-34), growing with the flat rate and the weights.
        basic = {y: r["totals_bn"]["triple_lock"][str(y)]["basic_state_pension"] for y in (HORIZON[0], FINAL_YEAR)}
        rate_growth = r["weekly"]["triple_lock"]["basic_state_pension"][str(FINAL_YEAR)] / \
            r["weekly"]["triple_lock"]["basic_state_pension"][str(HORIZON[0])]
        assert 0.8 * rate_growth <= basic[FINAL_YEAR] / basic[HORIZON[0]] <= 1.2 * rate_growth, (name, basic)


def test_savings_reconcile_with_the_model_totals(runs):
    for name, r in runs:
        tl, bp = r["totals_bn"]["triple_lock"], r["totals_bn"]["burnham_2030"]
        for y in HORIZON:
            s, a, b = r["saving_bn"][str(y)], tl[str(y)], bp[str(y)]
            assert s["gross"] == pytest.approx(a["state_pension_flat_rate"] - b["state_pension_flat_rate"], abs=TOL_BN)
            assert s["net"] == pytest.approx(b["gov_balance"] - a["gov_balance"], abs=TOL_BN)
            assert a["state_pension_flat_rate"] == pytest.approx(a["basic_state_pension"] + a["new_state_pension"], abs=1e-6)


def test_no_saving_before_the_switch(runs):
    for name, r in runs:
        for y in HORIZON:
            if y < SWITCH_YEAR:
                assert r["saving_bn"][str(y)]["gross"] == 0.0 and r["saving_bn"][str(y)]["net"] == 0.0, name


def test_gross_saving_is_never_negative(runs):
    """With the inputs at 0.1 point the plan's level never exceeds the triple lock's (test_rules), so its flat-rate
    spending never does either."""
    for name, r in runs:
        for y in HORIZON:
            assert r["saving_bn"][str(y)]["gross"] >= -1e-6, (name, y)


def test_every_run_followed_its_path(runs):
    for name, r in runs:
        f = r["path_following"]
        for key in engine.PATH_PARAMETERS:
            assert f[key]["max_abs_error"] <= engine.PATH_GROWTH_TOL, (name, key)
        assert f["employment_income"]["max_abs_error"] <= engine.PATH_GROWTH_TOL, name
        assert f["model_triple_lock"]["max_abs_error"] <= 1e-12, name
        assert r["checks"]["max_proportionality_error_gbp"] <= engine.PROPORTIONALITY_TOL_GBP, name
        assert all(v == 0 for v in r["checks"]["employer_ni_incidence_bn"].values()), name


def test_benefit_uprating_is_not_stuck_after_2029(runs):
    """Without the horizon extension, CPI-linked benefits stop following the path after April 2029."""
    for name, r in runs:
        g = ints(r["path_following"]["benefit_uprating_cpi"]["growth"])
        assert all(abs(g[y]) > 1e-6 for y in HORIZON if y > 2029), name


@pytest.mark.parametrize("year_key", ["2034", str(FINAL_YEAR)])
def test_household_tables_sum_to_the_net_change(runs, year_key):
    for name, r in runs:
        change = r["saving_bn"][year_key]["household_income_change"]
        for key, rows in r["distribution"][year_key].items():
            if key == "households_affected":
                continue
            assert sum(row["total_bn"] for row in rows) == pytest.approx(change, abs=0.002 * len(rows)), (name, key)


def test_largest_household_is_the_largest(runs):
    for name, r in runs:
        lh, c = r["largest_household"], r["concentration_by_year"][str(FINAL_YEAR)]
        assert lh["contribution_bn"] == pytest.approx(c["contribution_bn"]), name
        assert lh["share_of_income_change"] == pytest.approx(c["share_of_income_change"]), name


RECORD_LEVEL = {"household_id", "weight", "median_weight", "income_change_gbp", "change_gbp", "amounts_gbp",
                "gross_contribution_bn"}


def test_no_survey_record_is_published(results):
    """FRS records are licensed: the file gives a record's contribution to totals, never its id, weight or amounts."""
    from triple_lock.pipeline import RECORD_FIELDS

    def walk(x, path):
        if isinstance(x, dict):
            assert "household_id" not in x, path
            for k, v in x.items():
                if k in RECORD_FIELDS:
                    entries = [v] if k == "largest_household" else list(v.values())
                    for e in entries:
                        assert set(e) == set(RECORD_FIELDS[k]) and not set(e) & RECORD_LEVEL, (path, k)
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")

    walk(results, "$")


def test_no_household_weight_is_published(results):
    """No key anywhere carries a survey household's weight (the largest one included)."""

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                assert "household_weight" not in k, f"{path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{path}[{i}]")

    walk(results, "$")
    for dataset in results["coverage"]["datasets"].values():
        assert not any("weight" in k for k in dataset), dataset.keys()


# ── The central path ────────────────────────────────────────────────────


def test_central_run_is_the_central_path(results):
    path, run = results["central"]["path"], results["central"]["run"]
    assert ints(run["statutory"]["cpi"]) == pytest.approx(ints(path["statutory"]["cpi"]))
    assert ints(run["calendar"]["earnings"]) == pytest.approx(ints(path["calendar"]["earnings"]))
    central_traj = next(t for t in results["trajectories"]["paths"] if t["id"] == "central")
    assert central_traj["saving_bn"] == run["saving_bn"]  # the same cached job


# ── The expected value ──────────────────────────────────────────────────


def _recompute(ev, dataset, key, y, ratio=None):
    W = {s["stratum"]: s["probability"] for s in ev["strata"]}
    vals = {k: [] for k in W}
    times = "times_drawn" if dataset == "primary" else "times_drawn_sensitivity"
    for p in ev["paths"]:
        n = p.get(times, 0)
        if n and dataset in p["outputs"]:
            r = 1.0 if ratio is None else p["weight_ratio"][ratio]
            vals[p["stratum"]] += [p["outputs"][dataset][key][y] * r] * n
    return expected_value.stratified_mean(vals, W)


def test_expected_value_recomputes_from_the_path_records(results):
    """The stratified estimator on the recorded paths (each counted as often as it was drawn) reproduces every
    published estimate: every output, every year, both datasets, and every reweighted sensitivity."""
    ev = results["expected_value"]
    for dataset in ("primary", "sensitivity"):
        for key, by_year in ev["estimates"][dataset].items():
            for y, est in by_year.items():
                m, se = _recompute(ev, dataset, key, y)
                assert m == pytest.approx(est["mean"], abs=1e-9), (dataset, key, y)
                assert se == pytest.approx(est["se"], abs=1e-9), (dataset, key, y)
    for name, sens in ev["sensitivities"].items():
        for key in ("gross", "net"):
            for y, est in sens[key].items():
                m, se = _recompute(ev, "primary", key, y, ratio=name)
                assert m == pytest.approx(est["mean"], abs=1e-9), (name, key, y)
                assert se == pytest.approx(est["se"], abs=1e-9), (name, key, y)


def test_paired_difference_recomputes_from_the_path_records(results):
    ev = results["expected_value"]
    W = {s["stratum"]: s["probability"] for s in ev["strata"]}
    for o in ("gross", "net"):
        for y in ev["paired_difference"][o]:
            vals = {k: [] for k in W}
            for p in ev["paths"]:
                n = p.get("times_drawn_sensitivity", 0)
                if n:
                    vals[p["stratum"]] += [p["outputs"]["sensitivity"][o][y] - p["outputs"]["primary"][o][y]] * n
            m, se = expected_value.stratified_mean(vals, W)
            assert m == pytest.approx(ev["paired_difference"][o][y]["mean"], abs=1e-9)
            assert se == pytest.approx(ev["paired_difference"][o][y]["se"], abs=1e-9)


def test_household_examples_account_for_every_pound(results):
    """On every published path, example and year: net income change = State Pension + Pension Credit + Housing
    Benefit + council tax reduction + Winter Fuel Payment - income tax."""
    for t in results["trajectories"]["paths"]:
        for ex, r in t["households"]["results"].items():
            tl, bp = r["triple_lock"], r["burnham_2030"]
            for y in HORIZON:
                d = {k: bp[k][str(y)] - tl[k][str(y)] for k in tl}
                explained = (d["state_pension"] + d["pension_credit"] + d["housing_benefit"]
                             + d["council_tax_reduction"] + d["winter_fuel_payment"] - d["income_tax"])
                assert d["net_income"] == pytest.approx(explained, abs=1.0), (t["id"], ex, y)


def test_every_calibration_solved(results):
    cals = results["expected_value"]["calibrations"]
    assert all("error" not in c for c in cals.values()), [n for n, c in cals.items() if "error" in c]


def test_the_2012_start_changes_something(results):
    """Two benchmarks read the 2012-start group's model years."""
    g = results["trajectories"]["history"]["groups"][0]
    assert 2012 in g["switch_years"] and g["changes_anything"] is True and g["model_years"] is not None


def test_strata_probabilities_sum_to_one(results):
    ev = results["expected_value"]
    total = sum(s["probability"] for s in ev["strata"]) + ev["identical_rates"]["probability"]
    assert total == pytest.approx(1.0, abs=1e-9)
    assert all(s["paths"] >= expected_value.MIN_PER_STRATUM for s in ev["strata"])


def test_identical_rates_saved_exactly_nothing(results):
    check = results["expected_value"]["identical_rates"]["check_run"]
    assert check is None or check["largest_abs_saving_bn"] == 0.0


def test_primary_calibration_matches_the_central_means(results):
    ev = results["expected_value"]
    c = ev["calibrations"][ev["primary"]]
    assert c["draws"] == "shifted" and c["ess"] == pytest.approx(ev["draws"]["n"])


def test_the_calibration_choice_still_holds(results):
    """The primary calibration was chosen because tilting to past dynamics made the expected gap more biased
    (docs/METHOD.md); the Method tab's prose is generated from the file, but the choice itself is checked here."""
    for t in ("suspended", "published"):
        s = results["expected_value"]["backtest"]["summary"][t]
        assert abs(s["shift_dynamics"]["bias_pct_points"]) > abs(s["means_shift"]["bias_pct_points"]), t
        assert abs(s["obr_point"]["bias_pct_points"]) == max(abs(r["bias_pct_points"]) for r in s.values()), t


def test_benchmarks_resolve(results):
    from triple_lock.benchmarks import resolve

    for b in results["benchmarks"]:
        assert resolve(results, b["our_metric"]) == b["our_value"]


def test_method_text_percentiles_match_the_past_years_check(results):
    """docs/METHOD.md and the expected-value method text quote the past-years check's percentiles."""
    pc = results["expected_value"]["past_years_check"]
    assert round(pc["model"]["realised_percentile"]) == 55
    assert round(pc["dynamics"]["realised_percentile"]) == 93
    assert "55th percentile" in results["expected_value"]["method"] and "93rd" in results["expected_value"]["method"]
