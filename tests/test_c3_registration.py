"""The frozen C3 rule, and the simulation behind the pass rates it quotes (docs/METHOD.md)."""

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock.ts_backtest import candidate_score
from triple_lock.ts_uncertainty import committed_c2_rule_hash

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("c3_oc", ROOT / "scripts/c3_operating_characteristics.py")
OC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OC)

C3_RULE_SECTION_SHA256 = "6a98009162c406c7e73bfa315aa52f1730efa74a9fa634f0f4db6645a3464ef2"
RIGHT, DOUBLE, MILD = "model is right", "true floor rate is 1/2 of the model's", "true floor rate is 3/4 of the model's"
TOO_WIDE, NARROW = "true spread is 2/3 of the model's", "true spread is 3/2 of the model's"
HIGHER, LOWER = "true earnings growth is 1pp higher", "true earnings growth is 1pp lower"


def section():
    content = (ROOT / "docs/METHOD.md").read_bytes()
    begin, end = b"<!-- C3 frozen rule begins -->", b"<!-- C3 frozen rule ends -->"
    assert content.count(begin) == 1 and content.count(end) == 1
    return content.split(begin, 1)[1].split(end, 1)[0]


def rates():
    return json.loads((ROOT / "docs/uncertainty/c3-operating-characteristics.json").read_text())["pass_rates"]


def percent(rate):
    return f"{round(100 * rate)}%"


def draws_and_outcome(seed, n=400):
    rng = np.random.default_rng(seed)
    forecast = rng.normal([0.025, 0.03], [0.015, 0.02], size=(n, 4, 2))
    return forecast, rng.normal([0.025, 0.03], [0.015, 0.02], size=(4, 2))


def test_frozen_rule_keeps_its_registered_bytes():
    assert hashlib.sha256(section()).hexdigest() == C3_RULE_SECTION_SHA256


def test_registering_c3_leaves_the_c2_rule_intact():
    assert committed_c2_rule_hash()


def test_frozen_rule_publishes_no_fiscal_figure():
    text = section().decode()
    assert "£" not in text and not re.search(r"\d\s*(bn|billion|million)\b", text)


def test_quoted_rates_match_the_committed_simulation():
    text = section().decode()
    r = rates()
    eight = {name: percent(v["8"]["all"]) for name, v in r.items()}
    right, double = ([percent(r[name][k]["all"]) for k in ("4", "8", "12")] for name in (RIGHT, DOUBLE))
    assert f"a correct model passes {right[0]} of the time on four years, {right[1]} on eight and {right[2]} on twelve" in text
    assert f"double the true floor rate passes {double[0]}, {double[1]} and {double[2]}" in text
    assert eight[HIGHER] == eight[LOWER]
    assert f"misses by a point a year {eight[HIGHER]} of the time" in text
    assert f"2/3 of the true spread {eight[NARROW]}" in text
    assert f"4/3 of the true floor rate {eight[MILD]}" in text
    assert f"3/2 of the true spread {eight[TOO_WIDE]}" in text


def test_quoted_gap_from_six_years_on_matches_the_simulation():
    r = rates()
    gaps = [round(100 * (r[RIGHT][str(k)]["all"] - r[DOUBLE][str(k)]["all"])) for k in range(6, 13)]
    assert f"holds at {min(gaps)} to {max(gaps)} points" in section().decode()


def test_the_too_wide_model_beats_a_correct_one_as_the_rule_says():
    assert len(rates()) == 7
    assert rates()[TOO_WIDE]["8"]["all"] > rates()[RIGHT]["8"]["all"]


def test_every_truth_covers_every_span_from_four_to_twelve_years():
    assert all(set(v) == {str(k) for k in range(4, 13)} for v in rates().values())


def synthetic(seed, k, n=4000):
    rng = np.random.default_rng(seed)
    return rng.normal(0.025, 0.015, (n, k)), rng.normal(0.03, 0.02, (n, k))


@settings(max_examples=12)
@given(st.integers(0, 2**32 - 1), st.sampled_from([4, 8, 12]))
def test_each_truth_is_what_its_label_says_on_the_years_it_covers(seed, k):
    cpi, earnings = synthetic(seed, k)
    t = OC.truths(cpi, earnings, np.random.default_rng(seed))
    floor = (earnings < OC.FLOOR).mean()
    assert abs((t[RIGHT][1] < OC.FLOOR).mean() - floor) < 0.015
    assert abs((t[MILD][1] < OC.FLOOR).mean() - 0.75 * floor) < 0.015
    assert abs((t[DOUBLE][1] < OC.FLOOR).mean() - 0.5 * floor) < 0.015
    assert abs(t[HIGHER][1].mean() - t[RIGHT][1].mean() - 0.01) < 1e-12
    assert abs(t[LOWER][1].mean() - t[RIGHT][1].mean() + 0.01) < 1e-12
    assert abs(t[NARROW][1].std() / t[RIGHT][1].std() - 1.5) < 0.03
    assert abs(t[TOO_WIDE][1].std() / t[RIGHT][1].std() - 2 / 3) < 0.03


def test_main_scores_every_truth_on_its_own_span(monkeypatch, tmp_path):
    cpi, earnings = synthetic(7, 13, n=3000)
    seen = []
    real = OC.truths

    def spy(c, e, rng):
        seen.append(c.shape[1])
        return real(c, e, rng)

    monkeypatch.setattr(OC, "future_draws", lambda form, central: {"stat_cpi": cpi, "stat_earnings": earnings})
    monkeypatch.setattr(OC, "central_path", lambda: None)
    monkeypatch.setattr(OC, "truths", spy)
    monkeypatch.setattr(OC, "N_OUTCOMES", 2000)
    monkeypatch.setattr(OC, "OUTPUT", tmp_path / "out.json")
    OC.main()
    written = json.loads((tmp_path / "out.json").read_text())
    assert seen == list(range(4, 13))
    assert set(written["pass_rates"]) == {RIGHT, MILD, DOUBLE, HIGHER, LOWER, TOO_WIDE, NARROW}


@given(st.integers(0, 2**32 - 1))
def test_simulated_statistics_match_the_scorer_on_one_window(seed):
    forecast, outcome = draws_and_outcome(seed)
    s = OC.statistics(forecast[:, :, 0], forecast[:, :, 1], outcome[None, :, 0], outcome[None, :, 1])
    scored = candidate_score(forecast, outcome)
    assert s["annual_coverage"][0] == scored["annual_gap_coverage"]
    assert np.isclose(s["gap_bias"][0], scored["gap_bias_pp"])
    assert np.isclose(s["floor_bias"][0], scored["floor_bias"])
    assert np.isclose(s["switch_bias"][0], scored["switch_bias"])
    assert float(s["terminal_hits"][0, 0]) == scored["terminal_coverage"]


@given(st.integers(0, 2**32 - 1), st.integers(4, 8))
def test_passing_every_check_never_exceeds_passing_any_one(seed, k):
    rng = np.random.default_rng(seed)
    cpi, earnings = rng.normal(0.025, 0.015, (300, k)), rng.normal(0.03, 0.02, (300, k))
    truth_cpi, truth_earnings = rng.normal(0.025, 0.015, (40, k)), rng.normal(0.03, 0.02, (40, k))
    r = OC.pass_rates(cpi, earnings, truth_cpi, truth_earnings)
    assert 0 <= r["all"] <= min(v for name, v in r.items() if name != "all") <= 1


def test_every_origin_with_four_untouched_years_gives_one_window():
    assert [len(OC.windows(k)) for k in (4, 8, 12)] == [1, 5, 9]
    assert all(w.stop - w.start == 4 for w in OC.windows(12))
