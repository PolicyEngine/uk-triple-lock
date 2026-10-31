"""The parameter audit never needs a survey dataset or changes published policy."""

import csv
import hashlib
import json
import pytest
from hypothesis import given, settings, strategies as st

from historical_macro_inputs import macro_inputs_for
from triple_lock import engine, hb_allowance_diagnostic as diagnostic
from triple_lock.config import BASE_YEAR, HORIZON, PENSION_CREDIT_GUARANTEE, REPO


@pytest.fixture(scope="module")
def snapshot():
    return json.loads(diagnostic.SNAPSHOT.read_text())


@pytest.fixture(scope="module")
def paths():
    return diagnostic.committed_paths(json.loads((REPO / "data/results.json").read_text()))[0]


def test_snapshot_verifies_all_enacted_bases_and_uprating_metadata(snapshot):
    diagnostic.verify_index_anchor(snapshot)
    bases, phase = diagnostic.snapshot_base_values(snapshot)
    assert diagnostic.snapshot_base_values(snapshot, "installed") == (bases, phase)
    assert phase == 0.6
    assert bases == {
        **{PENSION_CREDIT_GUARANTEE[name]: value for name, value in (("single", 238), ("couple", 363.25))},
        **{diagnostic.HB_PATHS[name]: value for name, value in (("single", 256), ("lone_parent", 256), ("couple", 383.35))},
        diagnostic.SC_PATHS["single"]: 208.07, diagnostic.SC_PATHS["couple"]: 329.75}
    for record in snapshot["files"].values():
        assert len(record["upstream"]["sha256"]) == len(record["installed"]["sha256"]) == 64
    for name in diagnostic.HB_PATHS:
        source = snapshot["files"][f"gov/dwp/housing_benefit/allowances/{name}/aged.yaml"]
        assert source["upstream"]["yaml"]["metadata"]["uprating"] == "gov.benefit_uprating_cpi"
    sc = snapshot["files"]["gov/dwp/pension_credit/savings_credit/threshold.yaml"]
    assert sc["upstream"]["yaml"]["metadata"]["uprating"] == "gov.benefit_uprating_cpi"


def test_all_saved_envelope_specs_and_their_paired_baselines_are_included(paths):
    from collections import Counter

    assert Counter(p["group"] for p in paths) == {
        "central": 1, "obr_wedge": 1, "illustrated": 3, "paired_baseline": 160,
        "earnings_minus_0_5pp": 160, "earnings_plus_0_5pp": 160}
    assert all(set(p["statutory_earnings"]) == {y - 1 for y in HORIZON} for p in paths)
    assert all(set(p["cpi"]) == set(HORIZON) for p in paths)



def test_committed_macro_paths_do_not_depend_on_refreshable_handoff(tmp_path):
    """A clean checkout needs only the three actual macro inputs, not receipt metadata."""
    results = json.loads((REPO / "data/results.json").read_text())
    expected, inputs = diagnostic.committed_paths(results)
    assert {path.name for path in inputs} == {
        "monthly_var1_boot.specs.json", "earnings_minus_0_5pp.specs.json",
        "earnings_plus_0_5pp.specs.json"}
    for path in inputs:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    actual, copied_inputs = diagnostic.committed_paths(results, tmp_path)
    assert actual == expected
    assert {path.name for path in copied_inputs} == {path.name for path in inputs}
    # Even an unrelated or invalid provenance receipt cannot affect macro paths.
    (tmp_path / "handoff.json").write_text("provenance-only refresh")
    assert diagnostic.committed_paths(results, tmp_path) == (actual, copied_inputs)

def test_every_committed_path_year_preserves_component_sensitivity_invariants(snapshot, paths):
    """These are the options' definitions, not an assertion of an HB statutory minimum."""
    for spec in paths:
        _, rows = diagnostic.project_path(spec, snapshot)
        for row in rows:
            if row["kind"] == "hb":
                assert row["component_option_weekly"] >= row["guarantee_weekly"]
                assert row["guarantee_floor_option_weekly"] >= row["guarantee_weekly"]
            else:
                assert row["component_option_weekly"] < row["guarantee_weekly"]


@given(earnings=st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False), min_size=13, max_size=13),
       cpi=st.lists(st.floats(min_value=-0.5, max_value=0.5, allow_nan=False), min_size=13, max_size=13))
@settings(max_examples=30)
def test_component_option_covers_guarantee_for_arbitrary_growth(earnings, cpi):
    snapshot = json.loads(diagnostic.SNAPSHOT.read_text())
    spec = {"id": "synthetic", "group": "synthetic", "label": "Synthetic macro inputs", "rate_decimals": 3,
            "statutory_earnings": dict(zip(range(2026, 2039), earnings)),
            "statutory_cpi": dict(zip(range(2026, 2039), cpi)), "cpi": dict(zip(HORIZON, cpi))}
    _, rows = diagnostic.project_path(spec, snapshot)
    assert all(row["component_option_weekly"] >= row["guarantee_weekly"] for row in rows if row["kind"] == "hb")


def test_central_crossings_and_threshold_crossing_direction(snapshot, paths):
    central, _ = diagnostic.project_path(paths[0], snapshot)
    p = central["parameters"]
    assert p["hb_single"]["first_guarantee_exceeds_parameter_year"] == 2037
    assert p["hb_lone_parent"] == p["hb_single"]
    assert p["hb_couple"]["first_guarantee_exceeds_parameter_year"] == 2035
    assert p["hb_single"]["guarantee_minus_current_weekly"] == pytest.approx(15.452163377342345)
    assert p["hb_couple"]["guarantee_minus_current_weekly"] == pytest.approx(33.38025170014191)
    for kind in ("savings_threshold_single", "savings_threshold_couple"):
        assert p[kind]["first_guarantee_exceeds_parameter_year"] == BASE_YEAR
        assert p[kind]["first_parameter_exceeds_guarantee_year"] is None
    crossing_spec = next(p for p in paths if p["id"] == "paired_baseline/draw_23404")
    crossing, _ = diagnostic.project_path(crossing_spec, snapshot)
    assert crossing["parameters"]["savings_threshold_couple"]["first_parameter_exceeds_guarantee_year"] == 2037


def test_committed_artifacts_reproduce_exactly(tmp_path, monkeypatch):
    """The retained diagnostic reproduces from its independently pinned input vintage."""
    expected_report = json.loads(diagnostic.OUTPUT.read_text())
    source_results = json.loads((REPO / "data/results.json").read_text())
    with macro_inputs_for(source_results, monkeypatch, tmp_path) as historical_root:
        # Preserve the diagnostic's canonical source names and verify every
        # source byte against the report, including unchanged results/specs.
        for relative, expected_sha256 in expected_report["input_sha256"].items():
            destination = historical_root / relative
            content = (destination if destination.exists() else REPO / relative).read_bytes()
            assert hashlib.sha256(content).hexdigest() == expected_sha256, relative
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        monkeypatch.setattr(diagnostic, "REPO", historical_root)
        for name in ("CENTRAL_FORECAST_CSV", "AWE_CSV", "CPI_CSV"):
            relative = getattr(diagnostic, name).relative_to(REPO)
            monkeypatch.setattr(diagnostic, name, historical_root / relative)
        report, annual = diagnostic.build(
            results_path=historical_root / "data/results.json",
            snapshot_path=historical_root / diagnostic.SNAPSHOT.relative_to(REPO),
            spec_dir=historical_root / diagnostic.MEAN_SPEC_DIR.relative_to(REPO),
        )
    assert expected_report == report
    with diagnostic.ANNUAL_OUTPUT.open(newline="") as source:
        csv_rows = list(csv.DictReader(source))
    expected = [{key: str(value) for key, value in row.items()} for row in diagnostic.annual_table(annual)]
    assert csv_rows == expected


def test_model_rounded_index_matches_the_actual_processed_parameter_tree(snapshot, paths):
    """Independent model processing, with no Simulation or dataset, checks the reproduction."""
    pytest.importorskip("policyengine_uk")
    from policyengine_core.periods import instant
    from policyengine_uk import CountryTaxBenefitSystem

    system = CountryTaxBenefitSystem()
    base_parameters = system.parameters
    bases, _ = diagnostic.snapshot_base_values(snapshot)
    for path, value in bases.items():
        assert base_parameters.get_child(path)(f"{BASE_YEAR}-06-01") == value
    assert base_parameters.get_child("gov.economic_assumptions.indices.obr.lagged_cpi")("2026-06-01") == 1.61059
    # Include a central path, a path with an SC-threshold excursion, and a
    # negative-CPI path. This exercises real preprocessing rather than merely
    # repeating the diagnostic's recurrence in another test.
    negative = next(p for p in paths if min(p["cpi"].values()) < 0)
    excursion = next(p for p in paths if p["id"] == "paired_baseline/draw_23404")
    for spec in (paths[0], negative, excursion):
        system.reset_parameters()
        cpi_node = system.parameters.get_child(engine.OBR_GROWTH + ".consumer_price_index")
        cpi = {**({BASE_YEAR: spec["calendar_cpi_2026"]} if spec["calendar_cpi_2026"] is not None else {}),
               **spec["cpi"]}
        for year, value in cpi.items():
            cpi_node.update(start=instant(f"{year}-01-01"), stop=instant(f"{year}-12-31"), value=value)
        system.process_parameters()
        _, rows = diagnostic.project_path(spec, snapshot)
        for row in rows:
            parameters = diagnostic.HB_PATHS if row["kind"] == "hb" else diagnostic.SC_PATHS
            path = parameters[row["relationship"]]
            actual = system.parameters.get_child(path)(f"{row['year']}-06-01")
            assert row["current_weekly"] == pytest.approx(actual, abs=1e-9)
