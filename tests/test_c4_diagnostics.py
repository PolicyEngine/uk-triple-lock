"""The committed diagnostics of the failed forecast-error path model (scripts/c4_diagnostics.py, data/c4/diagnostics.json).

The cheap parts are recomputed here; the seed sets and the first model's draws are checked for consistency only.
"""

import json
import sys

import numpy as np
import pytest

from triple_lock import ts_obr_errors as C4
from triple_lock.config import REPO

sys.path.insert(0, str(REPO / "scripts"))
import c4_diagnostics as X  # noqa: E402

DIAG = json.loads((REPO / "data" / "c4" / "diagnostics.json").read_text())
SCORES = json.loads((REPO / "data" / "c4" / "scores.json").read_text())
ARITH = json.loads((REPO / "data" / "c4" / "rule_arithmetic.json").read_text())


@pytest.fixture(scope="module")
def record():
    return C4.load_record()


@pytest.fixture(scope="module")
def forward(record):
    return C4.forward_draws(record=record)


def test_the_model_failed_and_the_diagnostics_say_so():
    assert SCORES["verdict"]["passes"] is False and ARITH["c4_passes"] is False
    assert "failed its registered test" in DIAG["label"] and "no cash figure" in DIAG["label"]
    assert DIAG["rule_section_sha256"] == C4.RULE_SECTION_SHA256 == C4.frozen_rule_hash()


def test_seed_offset_zero_is_the_registered_run(record):
    reference = json.loads(C4.C2_REFERENCE.read_text())
    _, row = X.run_seed_set(record, reference, 0)
    reg = {c["test"] + ": " + c["check"]: c["value"] for c in SCORES["verdict"]["checks"]}
    assert row["variogram_ratio_b"] == reg["B: variogram ratio to the first model"]
    assert row["floor_bias_a"] == reg["A: |floor_bias|"]
    assert row["variogram_ratio_b"] == DIAG["seed_robustness"]["registered"]["variogram_ratio_b"]


def test_seed_summary_is_consistent_with_its_rows():
    s = DIAG["seed_robustness"]
    rows = s["by_seed_set"]
    assert len(rows) == s["n_seed_sets"] == X.N_SEED_SETS
    assert len({r["offset"] for r in rows}) == len(rows) and 0 not in {r["offset"] for r in rows}
    for key in ("variogram_ratio_b", "floor_bias_a"):
        values = [r[key] for r in rows]
        assert s[key]["min"] == min(values) and s[key]["max"] == max(values)
        assert s[key]["sets_above_limit"] == sum(v > s[key]["limit"] for v in values)
    # The failure does not depend on the seed: every set fails the variogram check.
    assert s["variogram_ratio_b"]["min"] > s["variogram_ratio_b"]["limit"]
    assert s["sets_passing_every_check"] == sum(r["passes"] for r in rows)


def test_the_variogram_excess_sums_to_the_registered_mean():
    v = DIAG["variogram_by_origin_b"]
    rows = v["rows"]
    assert len(rows) == 13
    b = SCORES["primary"]["scores"]["B"]["suspended"]["variogram"]["mean"]
    assert np.isclose(np.mean([r["c4"] for r in rows]), b)
    assert np.isclose(sum(r["excess"] for r in rows), v["total_excess"])


def test_resolution_is_recomputed(record, forward):
    origin, later = X.walk(record)
    assert later.shape == (C4.N_FORWARD, 8)
    assert DIAG["resolution"] == X.resolution(record, forward)
    assert DIAG["resolution"]["distinct_histories"] == len({tuple(r) for r in np.c_[origin, later].tolist()})


def test_walk_follows_the_registered_rule(record):
    origin, later = X.walk(record)
    n = len(record["years"])
    # Year 5 takes the next forecast's four-year-ahead error while the record lasts.
    has_next = origin + 1 < n
    assert np.array_equal(later[has_next, 0], origin[has_next] + 1)


def test_drift_is_recomputed_and_the_exact_walk_agrees_with_the_draws(record, forward):
    from triple_lock.central import central_path

    d = X.drift(record, central_path(), forward)
    assert d == DIAG["drift"]
    for v in C4.VARIABLES:
        mc, exact, se = (np.array(d[k][v]) for k in ("mean_error_monte_carlo", "mean_error_exact", "monte_carlo_se"))
        assert np.all(np.abs(mc - exact) < 4 * se), v
    # The registered text says the paths are centred on the OBR path; from year 5 they are not.
    assert d["mean_error_exact"]["earnings"][-1] > 1 and d["mean_error_exact"]["cpi"][-1] > 1
    assert max(d["weight_on_late_targets_from_year_5"]) > d["uniform_weight_on_late_targets"]


def test_decomposition_matches_the_committed_rule_arithmetic():
    de = DIAG["decomposition"]
    for y in map(str, C4.REPORT_YEARS):
        stored = ARITH["distribution"][y]["share"]
        for k in ("mean", "median", "p25", "p75"):
            assert np.isclose(de["registered"][y][k], stored[k], rtol=0, atol=1e-12), (y, k)
        assert de["error_scale"]["1.0"][y] == de["registered"][y]
    means = [de["error_scale"][str(k)]["2039"]["mean"] for k in X.SCALES]
    assert means == sorted(means)  # the saving grows with the inputs' volatility
    gap = de["gap_to_scenarios_2039"]
    assert np.isclose(gap["floor_part"], gap["with_floor"] - gap["floor_off"])
    assert np.isclose(gap["re_centring_part"], de["registered"]["2039"]["mean"] - de["re_centred"]["2039"]["mean"])


def test_gross_identity_holds_on_the_first_models_runs():
    g = DIAG["gross_identity"]
    assert g["sample_slots"] == 160
    assert g["single_paths_max_abs_error_bn"] < 1e-4
    assert max(g["scenario_stratified_max_abs_error_bn"].values()) < 1e-5


def test_no_cash_figure_from_the_failed_model():
    text = json.dumps(DIAG["decomposition"]) + json.dumps(DIAG["resolution"]) + json.dumps(DIAG["drift"])
    assert "_bn" not in text and "gross" not in text
