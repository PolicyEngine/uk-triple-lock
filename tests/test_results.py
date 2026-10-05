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
from triple_lock.config import CENTRAL_RATE_DECIMALS, DASHBOARD_COPY, FINAL_YEAR, HORIZON, OUTPUT, REPO, SWITCH_YEAR
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


def test_provenance_names_the_model_it_ran_on(results):
    """From model-v2 on the file records the installed policyengine-uk (which test_not_stale compares with the
    environment) and says no policyengine.py bundle certifies it with the data; a file built earlier records the
    bundle."""
    p = results["provenance"]
    if "model" not in p:
        assert p["release_bundle"]["model_version"] == p["packages"]["policyengine-uk"]
        return
    m = p["model"]
    assert m["model_version"] == p["packages"]["policyengine-uk"]
    assert m["certified"] is False and m["certification"].startswith("uncertified")
    assert p["datasets"]["primary"] == m["dataset"]
    assert results["central"]["run"]["dataset"] == m["runtime_dataset"]


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
    """State Pension age 67 for every survey age from 2028-29 (before it, part of age 66 is over it under
    policyengine-uk's timetable by date of birth; a file built before model-v2 has 66); the Pension Credit guarantee
    rising with May-July earnings; the additional State Pension identical under both rules (so it never enters the
    saving)."""
    for name, r in runs:
        spa = ints(r["fixed_inputs"]["state_pension_age"])
        assert all(spa[y] == [67.0] for y in HORIZON if y >= 2028), name
        assert all(spa[y] in ([66.0], [66.0, 67.0]) for y in HORIZON if y < 2028), name
        assert r["path_following"]["pension_credit_guarantee_single"]["max_abs_error"] <= 1e-9, name
        for y in HORIZON:
            assert r["saving_bn"][str(y)]["components"]["additional_state_pension"] == 0.0, (name, y)
        basic = {y: r["totals_bn"]["triple_lock"][str(y)]["basic_state_pension"] for y in (HORIZON[0], FINAL_YEAR)}
        rate_growth = r["weekly"]["triple_lock"]["basic_state_pension"][str(FINAL_YEAR)] / \
            r["weekly"]["triple_lock"]["basic_state_pension"][str(HORIZON[0])]
        if pension_types(r) == "survey_year":
            # The held types reached the model: basic State Pension spending persists to the final year (with types
            # recomputed from frozen ages it fell to zero by 2033-34), growing with the flat rate and the weights.
            assert 0.8 * rate_growth <= basic[FINAL_YEAR] / basic[HORIZON[0]] <= 1.2 * rate_growth, (name, basic)
        else:  # cohort types: later cohorts reach State Pension age on the new State Pension
            assert basic[FINAL_YEAR] / basic[HORIZON[0]] < rate_growth, (name, basic)


def pension_types(run):
    """The run's pension type rule (engine.population_treatment); a file built before model-v2 held survey types."""
    return run["fixed_inputs"].get("population", {}).get("pension_types", "survey_year")


def test_the_model_used_the_held_pension_types(runs):
    """The counts come from the model after pinning (engine.held_pension_types failed the run on any person whose
    type differed from the pinned one). Ages are held, so the same records are counted every year and people only
    move to none when the State Pension age rises past them (2028-29). With survey-year types nothing else moves;
    with cohort types (part B) records only move from the basic to the new State Pension, as later cohorts reach
    State Pension age, so the basic count never rises and over-State-Pension-age counts hold from 2028-29."""
    for name, r in runs:
        records = ints(r["fixed_inputs"]["held_pension_type_records"])
        people = ints(r["fixed_inputs"]["held_pension_type_people"])
        assert sorted(records) == sorted(people) == HORIZON, name
        assert len({sum(records[y].values()) for y in HORIZON}) == 1, name  # the same survey people every year
        over = {y: records[y]["BASIC"] + records[y]["NEW"] for y in HORIZON}
        assert all(over[y] == over[2028] for y in HORIZON if y >= 2028), name
        if pension_types(r) == "survey_year":
            for t in ("BASIC", "NEW"):
                assert records[FINAL_YEAR][t] <= records[HORIZON[0]][t], (name, t)
                assert all(records[y][t] == records[2028][t] for y in HORIZON if y >= 2028), (name, t)
        else:
            assert pension_types(r) == "cohort", name
            assert all(records[y + 1]["BASIC"] <= records[y]["BASIC"] for y in HORIZON[:-1]), name
            assert all(records[y + 1]["NEW"] >= records[y]["NEW"] for y in HORIZON[:-1] if y >= 2028), name
        for t in ("BASIC", "NEW"):
            assert people[FINAL_YEAR][t] > 0, (name, t)
        assert records[FINAL_YEAR]["BASIC"] > 0 and records[FINAL_YEAR]["NEW"] > 0, name


def test_rate_sources_recompute_from_the_recorded_inputs(runs):
    """Differential: the labels in the file are engine.rate_sources on each run's own statutory inputs and rates."""
    for name, r in runs:
        cpi, earnings = ints(r["statutory"]["cpi"]), ints(r["statutory"]["earnings"])
        rates = {p: ints(r["rates"][p]) for p in r["rates"]}
        expected = engine.rate_sources(cpi, earnings, rates, HORIZON, r["rate_decimals"])
        assert {p: ints(v) for p, v in r["rate_sources"].items()} == expected, name


def test_savings_reconcile_with_the_model_totals(runs):
    for name, r in runs:
        tl, bp = r["totals_bn"]["triple_lock"], r["totals_bn"]["burnham_2030"]
        for y in HORIZON:
            s, a, b = r["saving_bn"][str(y)], tl[str(y)], bp[str(y)]
            assert s["gross"] == pytest.approx(a["state_pension_flat_rate"] - b["state_pension_flat_rate"], abs=TOL_BN)
            assert s["net"] == pytest.approx(b["gov_balance"] - a["gov_balance"], abs=TOL_BN)
            assert a["state_pension_flat_rate"] == pytest.approx(a["basic_state_pension"] + a["new_state_pension"], abs=1e-6)


def test_the_components_are_the_net_saving_exactly(runs):
    """From model-v2 on every run decomposes the net saving into policyengine-uk's own tax and spending variables
    (GOV_TAX_VARIABLES, GOV_SPENDING_VARIABLES): taxes added and spending subtracted, the groups and the variables each
    make the change in gov_balance to 1e-6 £bn, and Great Britain's do the same for its net saving. A file built
    earlier records the eight named components only."""
    from triple_lock.config import FISCAL_GROUPS

    for name, r in runs:
        for y in HORIZON:
            s = r["saving_bn"][str(y)]
            if "components_by_variable" not in s:
                continue
            tax = set(r["totals_bn"]["triple_lock"][str(y)]["tax_variables"])
            taxes = {g for g, vs in FISCAL_GROUPS.items() if set(vs) <= tax} | {"other_tax"}
            assert set(s["components"]) == {*FISCAL_GROUPS, "other_spending", "other_tax"}, name
            assert abs(sum(c if g in taxes else -c for g, c in s["components"].items()) - s["net"]) <= 1e-6, (name, y)
            assert abs(sum(c if v in tax else -c for v, c in s["components_by_variable"].items()) - s["net"]) <= 1e-6
            assert abs(s["net_model_float32"] - s["net"]) <= 1e-5, (name, y)
            gb = s["gb"]
            assert abs(sum(c if g in taxes else -c for g, c in gb["components"].items()) - gb["net"]) <= 1e-6, (name, y)


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
    """A legacy run's single-record diagnostic agrees with itself; an ageing run publishes none (its weights are
    derived from the survey's), only the ten largest records' combined share, and no run publishes both."""
    for name, r in runs:
        if r.get("record_diagnostics_suppressed"):
            assert "largest_household" not in r and "concentration_by_year" not in r, name
            assert all(c["records"] == 10 for c in r["concentration_top10_by_year"].values()), name
            continue
        assert "concentration_top10_by_year" not in r, name  # never both: nine records by subtraction
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
    new_estimator = "uncertainty_reporting" in ev
    estimate = expected_value.stratified_estimate(vals, W, ev["draws"]["n"])
    return estimate["mean"], estimate["se"] if new_estimator else estimate["se_path_sampling"]


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
            estimate = expected_value.stratified_estimate(vals, W, ev["draws"]["n"])
            m = estimate["mean"]
            se = estimate["se"] if "uncertainty_reporting" in ev else estimate["se_path_sampling"]
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


def test_path_positions_recompute_from_the_primary_draws(results):
    """Where each drawn path sits, recomputed directly: the expected value's draws and its primary calibration's
    weights, the 2039-40 weekly gap by rule arithmetic, and the weighted shares below, tied with and above it."""
    from triple_lock.central import central_path
    from triple_lock.config import STATUTORY_YEARS

    ev = results["expected_value"]
    d = expected_value.draws(central_path())
    prim = expected_value.calibrations(d, {})[ev["primary"]]
    ds, w = d[prim["draws"]], prim["weights"]
    levels, _ = expected_value.rule_levels(ds["stat_cpi"], ds["stat_earnings"],
                                           results["base_year_weekly"]["new_state_pension"])
    gap = levels["triple_lock"][:, -1] - levels["burnham_2030"][:, -1]
    drawn = [t for t in results["trajectories"]["paths"] if "selection" in t]
    assert [t["id"] for t in drawn] == ["random", "monthly_p50", "monthly_p90"]
    for t in drawn:
        s = t["selection"]
        i = s["draw"]
        # The draws reproduce to floating-point precision across platforms, not bit for bit.
        assert [t["statutory"]["cpi"][str(y)] for y in STATUTORY_YEARS] == pytest.approx(ds["stat_cpi"][i].tolist(),
                                                                                       rel=0, abs=1e-12), t["id"]
        assert [t["statutory"]["earnings"][str(y)] for y in STATUTORY_YEARS] == pytest.approx(
            ds["stat_earnings"][i].tolist(), rel=0, abs=1e-12), t["id"]
        assert round(float(gap[i]), 2) == s["gap_gbp_week"]
        below, tied, above = (float(w[m].sum()) for m in (gap < gap[i], gap == gap[i], gap > gap[i]))
        assert s["draws_compared"] == len(w) == ev["draws"]["n"]
        assert s["gap_percentile_2039"] == pytest.approx(100 * (below + tied / 2) / w.sum(), abs=0.005), t["id"]
        assert s["larger_gap_pct_2039"] == pytest.approx(100 * above / w.sum(), abs=0.005), t["id"]


def test_gross_saving_rises_with_the_gap(results):
    """Step 3 says the paths with a larger 2039-40 gap save more: across every full run in the expected value, the
    final year's gross saving rises with the weekly gap."""
    runs = sorted((p["gap_2039_gbp_week"], p["outputs"]["primary"]["gross"][str(FINAL_YEAR)])
                  for p in results["expected_value"]["paths"])
    assert all(later[1] > earlier[1] for earlier, later in zip(runs, runs[1:]) if later[0] > earlier[0])


def test_benchmarks_resolve(results):
    from triple_lock.benchmarks import resolve

    for b in results["benchmarks"]:
        assert resolve(results, b["our_metric"]) == b["our_value"]


def test_method_text_percentiles_match_the_past_years_check(results):
    """docs/METHOD.md and the expected-value method text quote the past-years check's percentiles, whatever they are."""
    def ordinal(n):
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

    pc = results["expected_value"]["past_years_check"]
    model, dynamics = (ordinal(round(pc[k]["realised_percentile"])) for k in ("model", "dynamics"))
    method_doc = (REPO / "docs" / "METHOD.md").read_text()
    assert f"{model} percentile" in results["expected_value"]["method"] and dynamics in results["expected_value"]["method"]
    assert f"the {model} for the untilted model" in method_doc and f"its {dynamics} percentile" in method_doc


# ── What the headline assumes ───────────────────────────────────────────

# How today's engine treats the population (engine.population_treatment): what a build's central run records.
TODAY = {"weights": "survey", "ages": "survey_year", "pension_types": "survey_year"}


def with_population(results, population=TODAY):
    """A copy of the results whose path runs (the central run and every trajectory) record `population`, as runs
    from this engine will (the committed file predates the record)."""
    import copy

    out = copy.deepcopy(results)
    for run in [out["central"]["run"], *out["trajectories"]["paths"]]:
        if population is None:
            run["fixed_inputs"].pop("population", None)
        else:
            run["fixed_inputs"]["population"] = dict(population)
    return out


@pytest.fixture(scope="module")
def recorded(results):
    return with_population(results)


def test_assumptions_quote_the_results(recorded):
    """The block the pipeline writes for the dashboard's "What these figures assume" strip quotes figures that are
    elsewhere in the file: the reweightings' extremes, the coverage rows and the paired Microcosm difference."""
    from triple_lock.pipeline import assumptions

    results = recorded
    block = {item["key"]: item for item in assumptions(results)}
    assert list(block) == ["population", "paths", "benefits"]
    pop = block["population"]["facts"]
    assert {k: pop[k] for k in TODAY} == TODAY and pop["final_year"] == FINAL_YEAR
    assert pop["data_year"] == results["central"]["run"]["fixed_inputs"]["data_year"]
    assert pop["state_pension_age"] == results["central"]["run"]["fixed_inputs"]["state_pension_age"][str(FINAL_YEAR)]
    assert pop["max_age"] == results["coverage"]["datasets"]["primary"]["max_age"]
    assert block["population"]["title"] == "Today's pensioners, held fixed"
    assert "survey weights and the State Pension age" in block["population"]["text"]

    sens = results["expected_value"]["sensitivities"]
    gross = {name: s["gross"][str(FINAL_YEAR)] for name, s in sens.items()}
    paths = block["paths"]["facts"]
    lo, hi = min(gross, key=lambda n: gross[n]["mean"]), max(gross, key=lambda n: gross[n]["mean"])
    assert paths["reweightings"] == len(sens) and paths["calibration"] == results["expected_value"]["primary"]
    assert paths["lowest"] == {"calibration": lo, **gross[lo]}
    assert paths["highest"] == {"calibration": hi, **gross[hi], "effective_runs": sens[hi]["effective_runs"]}
    models = results["trajectories"]["models"]
    assert paths["shock_models_run"] == [m for m in models if models[m]["runs_paths"]]
    assert paths["shock_models_not_run"] == [m for m in models if not models[m]["runs_paths"]]
    assert "2.5% floor" in block["paths"]["text"]

    ben = block["benefits"]["facts"]
    rows = {r["key"]: r for r in results["coverage"]["rows"]}
    assert ben["coverage_year"] == results["coverage"]["year"]
    field = "primary_gb" if ben["model_geography"] == "Great Britain" else "primary"  # GB from model-v2 on
    for key in ("pension_credit_claims_m", "housing_benefit_pension_age_bn"):
        assert ben[key] == {"primary": rows[key][field], "dwp": rows[key]["dwp"]}
    ev = results["expected_value"]
    assert ben["paired_difference_net"] == {"year": FINAL_YEAR, **ev["paired_difference"]["net"][str(FINAL_YEAR)],
                                            "paths": sum(s["sensitivity_paths"] for s in ev["strata"]),
                                            "dataset": "Microcosm"}
    assert ben["dwp_geography"] == "Great Britain"


@pytest.mark.parametrize("change, says", [
    # #14 §3.1 alone: weights raked to the ONS projection, ages and types untouched.
    ({"weights": "ons_projection"}, "ONS population projection"),
    ({"weights": "reweighted"}, "reweighted in the run"),
    # #14 §3.3 alone: pension types by cohort, weights and ages untouched.
    ({"pension_types": "cohort"}, "follows their cohort"),
    ({"pension_types": "model"}, "the model's own"),
    # #14 §3.2: top-coded ages redrawn, so ages differ from the survey's without moving between years.
    ({"ages": "adjusted"}, "differ from their survey values"),
    ({"ages": "aged_forward"}, "aged forward each year"),
    # §3 together.
    ({"weights": "ons_projection", "ages": "adjusted", "pension_types": "cohort"}, "follows their cohort"),
])
def test_the_population_item_follows_the_runs_population(results, change, says):
    """Any change to how the runs treat the population, even to one of weights, ages or pension types alone, moves
    the population item off "held fixed"."""
    from triple_lock.pipeline import assumptions

    item = assumptions(with_population(results, {**TODAY, **change}))[0]
    assert item["key"] == "population" and says in item["text"]
    assert item["title"] != "Today's pensioners, held fixed"
    assert "Survey ages and State Pension types are fixed" not in item["text"]
    assert {k: item["facts"][k] for k in TODAY} == {**TODAY, **change}


def test_the_benefits_item_compares_great_britain_with_dwp_where_the_file_has_it(recorded):
    """From model-v2 the coverage rows give Great Britain beside the UK, and the strip quotes Great Britain against
    DWP's Great Britain figures, like for like; a file without them keeps the UK wording."""
    import copy

    from triple_lock.pipeline import assumptions

    gb = copy.deepcopy(recorded)
    for row in gb["coverage"]["rows"]:
        row["primary_gb"] = 0.97 * row["primary"]
    item = {i["key"]: i for i in assumptions(gb)}["benefits"]
    rows = {r["key"]: r for r in gb["coverage"]["rows"]}
    for key in ("pension_credit_claims_m", "housing_benefit_pension_age_bn"):
        assert item["facts"][key] == {"primary": rows[key]["primary_gb"], "dwp": rows[key]["dwp"]}
    assert item["facts"]["model_geography"] == "Great Britain" and "in Great Britain" in item["text"]
    assert "a UK model" not in item["text"]
    committed_gb = "primary_gb" in {r["key"]: r for r in recorded["coverage"]["rows"]}["pension_credit_claims_m"]
    old = {i["key"]: i for i in assumptions(recorded)}["benefits"]
    assert old["facts"]["model_geography"] == ("Great Britain" if committed_gb else "UK")


def test_assumptions_fail_without_wording_or_figures(results):
    """No record of the population, a treatment with no wording, or a missing figure fails the build rather than
    publish a strip that no longer describes the model."""
    from triple_lock.pipeline import MissingFigure, assumptions

    with pytest.raises(MissingFigure, match="population"):
        assumptions(with_population(results, None))
    with pytest.raises(MissingFigure, match="no wording for population.weights"):
        assumptions(with_population(results, {**TODAY, "weights": "something_new"}))
    for path in (("expected_value", "paired_difference"), ("trajectories", "models"), ("expected_value", "strata")):
        damaged = with_population(results)
        del damaged[path[0]][path[1]]
        with pytest.raises(MissingFigure, match=".".join(path)):
            assumptions(damaged)
    damaged = with_population(results)
    del damaged["coverage"]["datasets"]["primary"]["max_age"]
    with pytest.raises(MissingFigure, match="max_age"):
        assumptions(damaged)


def test_every_path_run_must_record_the_same_population(results):
    """The strip describes every run: a trajectory whose population differs from the central run's, or that records
    none, fails the build."""
    from triple_lock.pipeline import MissingFigure, assumptions

    for population in ({**TODAY, "weights": "ons_projection"}, None):
        mixed = with_population(results)
        last = mixed["trajectories"]["paths"][-1]
        if population is None:
            del last["fixed_inputs"]["population"]
        else:
            last["fixed_inputs"]["population"] = population
        with pytest.raises(MissingFigure, match=f"trajectory '{last['id']}'"):
            assumptions(mixed)


def test_other_sensitivities_and_models_are_worded_without_failing(recorded):
    """#14 §4 adds sensitivity families and models: the range stays the reweightings' and says what it leaves out,
    and a model with no short name is named by its own label, rather than failing the build at its end."""
    import copy

    from triple_lock.pipeline import assumptions

    before = {i["key"]: i for i in assumptions(recorded)}["paths"]
    wider = copy.deepcopy(recorded)
    ev = wider["expected_value"]
    any_name = next(iter(ev["sensitivities"]))
    ev["sensitivities"]["mean_path.earnings_plus_0_5"] = copy.deepcopy(ev["sensitivities"][any_name])
    ev["sensitivities"]["mean_path.earnings_plus_0_5"]["gross"][str(FINAL_YEAR)]["mean"] += 100
    wider["trajectories"]["models"]["var2"] = {"label": "Monthly VAR(2)", "runs_paths": False}
    after = {i["key"]: i for i in assumptions(wider)}["paths"]
    assert after["facts"]["highest"] == before["facts"]["highest"]
    assert after["facts"]["other_sensitivities"] == ["mean_path.earnings_plus_0_5"]
    assert "The range leaves out 1 other sensitivity." in after["text"]
    assert "Monthly VAR(2)" in after["text"]


def test_the_pilot_check_reports_the_block_or_why_not(results, tmp_path, capsys):
    """scripts/check_assumptions.py: the #14 §5 pilot's fast check that its results can carry the block."""
    import importlib.util

    from triple_lock.config import REPO

    spec = importlib.util.spec_from_file_location("check_assumptions", REPO / "scripts" / "check_assumptions.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(with_population(results)))
    bad.write_text(json.dumps(with_population(results, None)))
    assert check.main(good) == 0 and "population: Today's pensioners, held fixed" in capsys.readouterr().out
    assert check.main(bad) == 1 and "no assumptions block" in capsys.readouterr().out


def test_held_population_must_match_the_held_type_counts(results):
    """With ages and types held, the type counts cannot move once the State Pension age stops rising."""
    from triple_lock.pipeline import MissingFigure, assumptions

    moved = with_population(results)
    counts = moved["central"]["run"]["fixed_inputs"]["held_pension_type_records"][str(FINAL_YEAR)]
    counts["NEW"], counts["NONE"] = counts["NEW"] + 1, counts["NONE"] - 1
    with pytest.raises(MissingFigure, match="type counts move"):
        assumptions(moved)


def test_assumptions_read_the_build_s_integer_year_keys(recorded):
    """In the build the runs carry integer year keys (jobs.run_jobs returns cached jobs through _keys_to_int); the
    block is the same as from the file read back."""
    import copy

    from triple_lock.pipeline import assumptions

    assert assumptions(engine._keys_to_int(copy.deepcopy(recorded))) == assumptions(recorded)


def test_assumptions_block_is_current(results):
    """Once a build has written the block, it is what the pipeline generates from the same file."""
    from triple_lock.pipeline import assumptions

    if "assumptions" not in results:
        pytest.skip("built before the pipeline wrote the assumptions block")
    assert results["assumptions"] == assumptions(results)
