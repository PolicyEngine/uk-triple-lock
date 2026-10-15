"""The two rules: examples and properties that hold for every input (no PolicyEngine needed)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine, rules
from triple_lock.config import CENTRAL_RATE_DECIMALS, HORIZON, POLICIES, SWITCH_YEAR, TRIPLE_LOCK_FLOOR

# Continuous rates; exact half-grid values (e.g. 0.0355), where rounding conventions disagree; and values on the
# 0.1-point grid, so inputs tie with each other and with the 2.5% floor.
half_grid = st.integers(-30, 120).map(lambda k: (k + 0.5) / 1000)
on_grid = st.integers(-30, 120).map(lambda k: k / 1000)
rates = st.one_of(st.floats(min_value=-0.03, max_value=0.12, allow_nan=False), half_grid, on_grid)
paths = st.lists(st.tuples(rates, rates), min_size=len(HORIZON), max_size=len(HORIZON))
STEP = 10 ** -CENTRAL_RATE_DECIMALS


def split(pairs):
    return np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])


def published(x):
    """The inputs as the rules see them with rounding on: to 0.1 point, as ONS publishes."""
    return np.round(x, CENTRAL_RATE_DECIMALS)


@pytest.mark.parametrize("cpi, earnings, expected", [
    (0.030, 0.040, 0.040),
    (0.050, 0.020, 0.050),
    (0.010, 0.020, 0.025),
    (-0.010, -0.005, 0.025),
])
def test_triple_lock_rate(cpi, earnings, expected):
    assert rules.rates_matrix("triple_lock", cpi, earnings)[0, 0] == pytest.approx(expected)


def test_unknown_policy_raises():
    with pytest.raises(ValueError):
        rules.rates_matrix("double_lock", 0.02, 0.03)


def test_uprating_uses_previous_year_growth():
    """Uprating in April y reads growth in y-1, as create_triple_lock does."""
    path = rules.uprating_path("triple_lock", {2026: 0.01, 2027: 0.05}, {2026: 0.03, 2027: 0.00}, [2027, 2028])
    assert path == {2027: 0.03, 2028: 0.05}


def test_levels_compound():
    r = {2027: 0.10, 2028: 0.10}
    assert rules.cumulative_index(r, [2027, 2028]) == pytest.approx({2027: 1.1, 2028: 1.21})
    assert rules.level_path(200.0, r, [2027, 2028]) == pytest.approx({2027: 220.0, 2028: 242.0})


def test_floor_binds_when_neither_input_exceeds_the_floor():
    assert rules.floor_binds(0.02, 0.024)
    assert rules.floor_binds(0.02, 0.025)  # a tie is the floor's, as April 2017 in the history table
    assert not rules.floor_binds(0.02, 0.026)
    assert not rules.floor_binds(0.03, 0.01)


@settings(max_examples=300, deadline=None)
@given(rates, rates)
def test_floor_binds_agrees_with_triple_lock_source(c, e):
    assert bool(rules.floor_binds(c, e)) == (rules.triple_lock_source(c, e) == "floor")


def test_burnham_keeps_the_floor_but_not_the_ratchet():
    years = [2030, 2031, 2032]
    cpi, earn = np.array([0.01, 0.01, 0.01]), np.array([0.01, 0.06, 0.06])
    tl = rules.rates_matrix("triple_lock", cpi, earn, years)[0]
    b = rules.rates_matrix("burnham_2030", cpi, earn, years)[0]
    assert tl == pytest.approx([0.025, 0.06, 0.06])
    assert b[0] == pytest.approx(0.025)
    assert b[1] == pytest.approx(max(0.025, 1.01 * 1.06 / 1.025 - 1)) and b[1] < tl[1]
    assert b[2] == pytest.approx(0.06)  # back on the earnings path, it follows earnings
    assert rules.rates_matrix("burnham_2030", cpi, np.zeros(3), years)[0] == pytest.approx([0.025] * 3)


def test_switch_year_is_a_parameter():
    cpi, earn = np.array([0.03, 0.01]), np.array([0.01, 0.05])
    late = rules.rates_matrix("burnham_2030", cpi, earn, [2012, 2013], switch_year=2030)[0]
    early = rules.rates_matrix("burnham_2030", cpi, earn, [2012, 2013], switch_year=2012)[0]
    assert late == pytest.approx([0.03, 0.05])  # triple lock throughout
    assert early[1] < 0.05  # from 2012 the plan only restores the earnings path


# ── Properties for all inputs ───────────────────────────────────────────


@settings(max_examples=300, deadline=None)
@given(paths)
def test_burnham_plan_invariants(pairs):
    """Triple lock before the switch; at least max(CPI, 2.5%) after; level never below its earnings path;
    above the triple lock only by rounding (at most 0.1pp in a year); never a cash cut."""
    cpi, earnings = split(pairs)
    cpi, earnings = published(cpi), published(earnings)
    tl = rules.rates_matrix("triple_lock", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    assert (tl >= TRIPLE_LOCK_FLOOR - 1e-12).all() and (bp >= 0).all()
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            assert bp[j] == tl[j]
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = float(np.round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS))
        assert bp[j] >= floor - 1e-12
        level *= 1 + bp[j]
        assert level >= anchor * (1 - 1e-12)
        assert bp[j] <= tl[j] + STEP + 1e-12


@settings(max_examples=300, deadline=None)
@given(paths)
def test_burnham_plan_is_the_smallest_rate_meeting_both_guarantees(pairs):
    """Each post-switch rate is on the 3 dp grid, meets both guarantees, and 0.1 point less would break one."""
    cpi, earnings = split(pairs)
    cpi, earnings = published(cpi), published(earnings)
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    level, anchor = 1.0, None
    for j, y in enumerate(HORIZON):
        if y < SWITCH_YEAR:
            level *= 1 + bp[j]
            continue
        anchor = level if anchor is None else anchor
        anchor *= 1 + earnings[j]
        floor = float(np.round(max(cpi[j], TRIPLE_LOCK_FLOOR, 0.0), CENTRAL_RATE_DECIMALS))
        assert abs(bp[j] / STEP - round(bp[j] / STEP)) < 1e-6, "not a 3 dp rate"
        assert bp[j] >= floor - 1e-12 and level * (1 + bp[j]) >= anchor * (1 - 1e-12)
        lower = bp[j] - STEP
        assert lower < floor - 1e-12 or level * (1 + lower) < anchor * (1 - 1e-12), "a smaller rate would do"
        level *= 1 + bp[j]


@settings(max_examples=200, deadline=None)
@given(paths)
def test_burnham_level_never_exceeds_the_triple_lock_unrounded(pairs):
    """Without rounding the plan's level is at most the triple lock's in every year (the saving is never negative)."""
    cpi, earnings = split(pairs)
    tl = np.cumprod(1 + rules.rates_matrix("triple_lock", cpi, earnings, HORIZON)[0])
    bp = np.cumprod(1 + rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON)[0])
    assert (bp <= tl * (1 + 1e-12)).all()


@settings(max_examples=200, deadline=None)
@given(paths)
def test_vectorised_rates_equal_one_path_at_a_time(pairs):
    """Differential: the (n, years) array path gives each draw what the single-path call gives it."""
    cpi, earnings = split(pairs)
    C = np.stack([cpi, cpi * 0.5, earnings])
    E = np.stack([earnings, earnings + 0.01, cpi])
    for p in POLICIES:
        full = rules.rates_matrix(p, C, E, HORIZON, CENTRAL_RATE_DECIMALS)
        for i in range(3):
            assert np.array_equal(full[i], rules.rates_matrix(p, C[i], E[i], HORIZON, CENTRAL_RATE_DECIMALS)[0])


@settings(max_examples=400, deadline=None)
@given(paths, st.sampled_from([CENTRAL_RATE_DECIMALS, None]))
def test_rate_sources_name_the_binding_input(pairs, decimals):
    """The label names an input equal to the rate the rule paid, with the history table's tie conventions: the floor
    whenever neither input exceeds 2.5%, CPI when the inputs tie; after the switch the plan's "cpi" only above 2.5%."""
    cpi = {y - 1: p[0] for y, p in zip(HORIZON, pairs)}
    earnings = {y - 1: p[1] for y, p in zip(HORIZON, pairs)}
    r = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals) for p in POLICIES}
    src = engine.rate_sources(cpi, earnings, r, HORIZON, decimals)
    for y in HORIZON:
        c, e = cpi[y - 1], earnings[y - 1]
        if decimals is not None:
            c, e = float(np.round(c, decimals)), float(np.round(e, decimals))
        label = src["triple_lock"][y]
        chosen = {"earnings": e, "cpi": c, "floor": TRIPLE_LOCK_FLOOR}[label]
        assert chosen == max(c, e, TRIPLE_LOCK_FLOOR) == pytest.approx(r["triple_lock"][y], abs=1e-12)
        assert (label == "floor") == (max(c, e) <= TRIPLE_LOCK_FLOOR)
        assert label != "earnings" or e > c  # a tie between the inputs is CPI's
        if y < SWITCH_YEAR:
            assert src["burnham_2030"][y] == "triple_lock"
        else:
            floor = max(c, TRIPLE_LOCK_FLOOR)
            floor = float(np.round(floor, decimals)) if decimals is not None else floor
            bp = src["burnham_2030"][y]
            assert (bp == "earnings_path") == (r["burnham_2030"][y] > floor + 1e-12)
            if bp != "earnings_path":
                assert bp == ("cpi" if c > TRIPLE_LOCK_FLOOR else "floor")
                assert r["burnham_2030"][y] == pytest.approx(floor, abs=1e-12)


@settings(max_examples=300, deadline=None)
@given(paths)
def test_with_published_inputs_the_plan_never_pays_more_than_the_triple_lock(pairs):
    """Rounding the inputs to 0.1 point first (as published) removes the rounding artefact: when earnings set both
    rules' rise, they pay the same; the plan's level never exceeds the triple lock's."""
    cpi, earnings = split(pairs)
    tl = rules.rates_matrix("triple_lock", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS)[0]
    assert (np.cumprod(1 + bp) <= np.cumprod(1 + tl) * (1 + 1e-12)).all()


def test_rounding_happens_to_the_inputs():
    """A May-July figure of 4.21% is published as 4.2%: both rules use 4.2%."""
    tl = rules.rates_matrix("triple_lock", [0.02], [0.0421], [2030], CENTRAL_RATE_DECIMALS)[0, 0]
    bp = rules.rates_matrix("burnham_2030", [0.02], [0.0421], [2030], CENTRAL_RATE_DECIMALS)[0, 0]
    assert tl == pytest.approx(0.042) and bp == pytest.approx(0.042)


# ── One rounding, one set of labels ─────────────────────────────────────


@settings(max_examples=400, deadline=None)
@given(rates)
def test_round_rate_is_numpys_rounding(x):
    """rules.round_rate is np.round to 0.1 point for scalars and arrays alike, and None leaves the input as it is."""
    assert rules.round_rate(x) == float(np.round(x, CENTRAL_RATE_DECIMALS))
    assert isinstance(rules.round_rate(x), float)
    assert rules.round_rate(np.array([x, x])).tolist() == [float(np.round(x, CENTRAL_RATE_DECIMALS))] * 2
    assert rules.round_rate(x, None) is x


def test_half_grid_values_are_where_pythons_round_disagrees():
    """Why one helper: Python's round() and numpy's differ on 84 of the 151 half-grid values from -3% to 12%."""
    half = [(k + 0.5) / 1000 for k in range(-30, 121)]
    differ = [x for x in half if round(x, 3) != rules.round_rate(x)]
    assert len(differ) == 84 and rules.round_rate(0.0355) == 0.036 and round(0.0355, 3) == 0.035


@settings(max_examples=400, deadline=None)
@given(rates, rates)
def test_triple_lock_source_names_the_input_the_rule_paid(c, e):
    """For published inputs: the named input equals the triple lock's rate; the floor exactly when neither input
    exceeds 2.5%; CPI on a tie between the inputs."""
    c, e = rules.round_rate(c), rules.round_rate(e)
    label = rules.triple_lock_source(c, e)
    rate = float(rules.rates_matrix("triple_lock", c, e, decimals=CENTRAL_RATE_DECIMALS)[0, 0])
    assert {"earnings": e, "cpi": c, "floor": TRIPLE_LOCK_FLOOR}[label] == pytest.approx(rate, abs=1e-12)
    assert (label == "floor") == (max(c, e) <= TRIPLE_LOCK_FLOOR)
    assert (label == "earnings") == (e > c and e > TRIPLE_LOCK_FLOOR)
    assert rules.burnham_floor_source(c) == ("cpi" if c > TRIPLE_LOCK_FLOOR else "floor")


@pytest.mark.parametrize("c, e, label", [
    (0.010, 0.025, "floor"),     # April 2017: earnings exactly 2.5%
    (0.025, 0.020, "floor"),     # CPI exactly 2.5%
    (0.025, 0.025, "floor"),
    (0.031, 0.031, "cpi"),       # April 2022: the earnings leg suspended, set equal to CPI
    (0.031, 0.032, "earnings"),
    (0.032, 0.031, "cpi"),
])
def test_triple_lock_source_ties(c, e, label):
    assert rules.triple_lock_source(c, e) == label


# ── Specified rates (scenario runs) ─────────────────────────────────────


def _lagged(values):
    """{input year: value} for the uprating years HORIZON (each uses the year before)."""
    return {y - 1: float(v) for y, v in zip(HORIZON, values)}


def _rules_before_specified_rates(policy, cpi, earnings, years, decimals):
    """The rules as main had them before specified rates (ee02c8d), one path, written out year by year: a frozen
    reference, so the tests below compare the new code with the old rather than with itself."""
    def rnd(r):
        return r if decimals is None else float(np.round(r, decimals))

    def rnd_up(r):
        return r if decimals is None else float(np.ceil(np.round(r * 10**decimals, 9)) / 10**decimals)

    out, level, anchor = {}, 1.0, 1.0
    for y in years:
        c, e = rnd(cpi[y - 1]), rnd(earnings[y - 1])
        tl = rnd(max(c, e, TRIPLE_LOCK_FLOOR, 0.0))
        if policy == "triple_lock" or y < SWITCH_YEAR:
            out[y] = tl
            level *= 1 + tl
            anchor = level
            continue
        anchor *= 1 + e
        out[y] = max(rnd(max(c, TRIPLE_LOCK_FLOOR, 0.0)), rnd_up(anchor / level - 1))
        level *= 1 + out[y]
    return out


@settings(max_examples=200, deadline=None)
@given(paths, st.sampled_from([CENTRAL_RATE_DECIMALS, None]))
def test_no_specified_rates_give_the_rules_as_they_were(pairs, decimals):
    """Without specified rates (none, empty, or empty per policy) every rate is what the rules gave before specified
    rates existed (the frozen reference above), and every label is the rules' own."""
    cpi, earnings = (_lagged(x) for x in split(pairs))
    before = {p: _rules_before_specified_rates(p, cpi, earnings, HORIZON, decimals) for p in POLICIES}
    for specified in (None, {}, {"triple_lock": {}, "burnham_2030": {}}):
        got = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=decimals, specified=specified)
               for p in POLICIES}
        for p in POLICIES:
            assert got[p] == pytest.approx(before[p], abs=1e-12), p
        src = engine.rate_sources(cpi, earnings, got, HORIZON, decimals, specified)
        assert "specified" not in {s for by_year in src.values() for s in by_year.values()}


def test_no_specified_rates_reproduce_every_rate_in_the_results_file():
    """Differential against main's committed output: every path run in data/results.json, built before specified
    rates existed, gets the same rates from the new code with no specified rates."""
    import json

    from triple_lock.config import OUTPUT

    results = json.loads(OUTPUT.read_text())
    runs = [results["central"]["run"], *results["trajectories"]["paths"]]
    for r in runs:
        cpi = {int(y): v for y, v in r["statutory"]["cpi"].items()}
        earnings = {int(y): v for y, v in r["statutory"]["earnings"].items()}
        for p in POLICIES:
            got = rules.uprating_path(p, cpi, earnings, HORIZON, r["rate_decimals"], specified={})
            assert got == {int(y): v for y, v in r["rates"][p].items()}, p


@settings(max_examples=200, deadline=None)
@given(paths, st.lists(rates, min_size=len(HORIZON), max_size=len(HORIZON)))
def test_a_specified_triple_lock_is_what_the_plan_pays_before_the_switch(pairs, given_rates):
    """The triple lock pays the specified rates, rounded like every rate; so does the plan before the switch. After
    it the plan runs its own rule from the level they leave: its rates are the rule's from the switch alone, since
    its earnings path starts from that level."""
    cpi, earnings = split(pairs)
    spec = {"triple_lock": np.array(given_rates)}
    tl = rules.rates_matrix("triple_lock", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS, specified=spec)[0]
    bp = rules.rates_matrix("burnham_2030", cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS, specified=spec)[0]
    assert np.array_equal(tl, rules.round_rate(np.array(given_rates)))
    before = np.asarray(HORIZON) < SWITCH_YEAR
    assert np.array_equal(bp[before], tl[before])
    alone = rules.rates_matrix("burnham_2030", cpi[~before], earnings[~before], None, CENTRAL_RATE_DECIMALS)[0]
    assert np.array_equal(bp[~before], alone)


@settings(max_examples=200, deadline=None)
@given(paths, st.sampled_from([y for y in HORIZON if y >= SWITCH_YEAR]), rates)
def test_a_specified_plan_rate_replaces_its_rule_that_year(pairs, year, rate):
    """The plan pays the specified rate that year; its earlier years and the triple lock are as without it."""
    cpi, earnings = (_lagged(x) for x in split(pairs))
    specified = {"burnham_2030": {year: rate}}
    plain = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS) for p in POLICIES}
    got = {p: rules.uprating_path(p, cpi, earnings, HORIZON, decimals=CENTRAL_RATE_DECIMALS, specified=specified)
           for p in POLICIES}
    assert got["triple_lock"] == plain["triple_lock"]
    assert got["burnham_2030"][year] == rules.round_rate(rate)
    assert all(got["burnham_2030"][y] == plain["burnham_2030"][y] for y in HORIZON if y < year)
    src = engine.rate_sources(cpi, earnings, got, HORIZON, CENTRAL_RATE_DECIMALS, specified)
    assert [y for y in HORIZON if src["burnham_2030"][y] == "specified"] == [year]
    assert "specified" not in src["triple_lock"].values()


def test_specified_rates_are_rounded_with_round_rate():
    """0.0355 is paid as 3.6% (round_rate, numpy's rounding), as any rate on the 0.1-point grid is."""
    r = rules.uprating_path("triple_lock", {2026: 0.01}, {2026: 0.01}, [2027], CENTRAL_RATE_DECIMALS,
                            specified={"triple_lock": {2027: 0.0355}})
    assert r == {2027: rules.round_rate(0.0355)} == {2027: 0.036}


def test_the_rate_sources_name_specified_years():
    cpi, earnings = _lagged([0.02] * len(HORIZON)), _lagged([0.04] * len(HORIZON))
    specified = {"triple_lock": {HORIZON[0]: 0.03, SWITCH_YEAR + 1: 0.05}}
    r = {p: rules.uprating_path(p, cpi, earnings, HORIZON, CENTRAL_RATE_DECIMALS, specified) for p in POLICIES}
    src = engine.rate_sources(cpi, earnings, r, HORIZON, CENTRAL_RATE_DECIMALS, specified)
    assert {y for y in HORIZON if src["triple_lock"][y] == "specified"} == set(specified["triple_lock"])
    assert src["burnham_2030"][HORIZON[0]] == "triple_lock"  # it pays the triple lock's rate, specified or not
    assert r["burnham_2030"][HORIZON[0]] == 0.03


@pytest.mark.parametrize("specified, message", [
    ({"burnham_2030": {SWITCH_YEAR - 1: 0.03}}, "is the triple lock before the switch"),
    ({"winter_fuel": {SWITCH_YEAR: 0.03}}, "unknown policy"),
    ({"triple_lock": {HORIZON[-1] + 1: 0.03}}, "outside the path"),
])
def test_specified_rates_a_rule_cannot_take_are_refused(specified, message):
    cpi = _lagged([0.02] * len(HORIZON))
    with pytest.raises(ValueError, match=message):
        rules.uprating_path("burnham_2030", cpi, cpi, HORIZON, CENTRAL_RATE_DECIMALS, specified)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_specified_rates_are_refused(bad):
    """NaN or infinity is never a rate: refused by the rules (by year or as an array) and by the spec reader."""
    cpi = _lagged([0.02] * len(HORIZON))
    with pytest.raises(ValueError, match="finite"):
        rules.uprating_path("triple_lock", cpi, cpi, HORIZON, CENTRAL_RATE_DECIMALS,
                            {"triple_lock": {SWITCH_YEAR: bad}})
    with pytest.raises(ValueError, match="finite"):
        engine.spec_specified({"specified_rates": {"triple_lock": {str(SWITCH_YEAR): bad}}})
    if not np.isnan(bad):  # in an array NaN marks a year with no rate given
        with pytest.raises(ValueError, match="finite"):
            rules.rates_matrix("triple_lock", [0.02], [0.02], [SWITCH_YEAR], CENTRAL_RATE_DECIMALS,
                               specified={"triple_lock": [bad]})


def test_negative_specified_rates_are_allowed():
    """A specified rate is an input, not a rule: a cut is paid as given (rounded), not floored."""
    cpi = _lagged([0.02] * len(HORIZON))
    r = rules.uprating_path("triple_lock", cpi, cpi, HORIZON, CENTRAL_RATE_DECIMALS, {"triple_lock": {SWITCH_YEAR: -0.01}})
    assert r[SWITCH_YEAR] == -0.01
    assert engine.spec_specified({"specified_rates": {"triple_lock": {"2030": -0.01}}}) == {"triple_lock": {2030: -0.01}}


def test_spec_specified_reads_json_keys():
    """A job's spec arrives through JSON, with string keys: they are read as years."""
    assert engine.spec_specified({"specified_rates": {"triple_lock": {"2030": "0.04"}}}) == {"triple_lock": {2030: 0.04}}
    assert engine.spec_specified({}) == {}
