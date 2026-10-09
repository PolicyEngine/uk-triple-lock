"""The rebuild's Housing Benefit passport preflight (pipeline.housing_benefit_passport_preflight, policyengine-uk#1927).

The guard calculates two synthetic pensioners in the installed model and refuses to run unless the Guarantee Credit
passport keys on receipt. Stand-in models check its decision for every way a passport could key on the probe's
facts; one test runs it against the installed policyengine-uk (refused on the 2.120.0 pilot pin, passed from 2.123.6);
the build's entry points must run it before any model job, and every other test stubs or never reaches it.
"""

import importlib.metadata
import importlib.util
import itertools
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import expected_value as EV
from triple_lock import pipeline

FACTS = pipeline.passport_probe_facts()
YEAR = FACTS["year"]
VARIABLES = ("housing_benefit_pension_age_regulations_apply", "guarantee_credit", "pension_credit",
             "housing_benefit_assessable_capital", "housing_benefit_tariff_income",
             "housing_benefit_applicable_income", "housing_benefit")
# What policyengine-uk 2.120.0 and 2.123.6 calculate for the probe (the observed preflight record).
AMOUNTS = {"guarantee_credit": 1_336., "tariff_income": 1_040., "means_tested_housing_benefit": 0.}
FIRST_RELEASE = "2.123.6"


def entitlement(entitled, receipt, claims):
    return entitled  # policyengine-uk 2.120.0: guarantee_credit > 0


def receipt_keyed(entitled, receipt, claims):
    return receipt  # policyengine-uk#1927: in_receipt_of_guarantee_credit


def claim_keyed(entitled, receipt, claims):
    return entitled and claims  # a claim proxy that never reads in_receipt_of_guarantee_credit


def fake_model(passport, guarantee_credit=AMOUNTS["guarantee_credit"], tariff_income=AMOUNTS["tariff_income"],
               means_tested_housing_benefit=AMOUNTS["means_tested_housing_benefit"]):
    """A stand-in for policyengine-uk's Simulation on the probe: Guarantee Credit entitlement from ``guarantee_credit``,
    Pension Credit paid on a claim, receipt = claim and entitlement unless in_receipt_of_guarantee_credit is set, and
    the passport ``passport(entitled, receipt, claims)``: a passported family has its capital and income disregarded
    and maximum Housing Benefit (the whole rent); a means-tested one has them counted and
    ``means_tested_housing_benefit``."""
    def simulate(situation):
        values = {v: [] for v in VARIABLES}
        for unit in situation["benunits"].values():
            (name,) = unit["members"]
            person, household = situation["people"][name], situation["households"][f"{name}_household"]
            claims = unit["would_claim_pc"][YEAR]
            entitled = guarantee_credit > 0
            receipt = unit.get("in_receipt_of_guarantee_credit", {}).get(YEAR, claims and entitled)
            passported = passport(entitled, receipt, claims)
            income = person["state_pension_reported"][YEAR] + tariff_income
            for variable, value in (
                    ("housing_benefit_pension_age_regulations_apply", person["age"][YEAR] >= 66),
                    ("guarantee_credit", guarantee_credit),
                    ("pension_credit", guarantee_credit if claims else 0.),
                    ("housing_benefit_assessable_capital", 0. if passported else household["savings"][YEAR]),
                    ("housing_benefit_tariff_income", 0. if passported else tariff_income),
                    ("housing_benefit_applicable_income", 0. if passported else income),
                    ("housing_benefit", household["rent"][YEAR] if passported else means_tested_housing_benefit)):
                values[variable].append(value)
        return SimpleNamespace(calculate=lambda variable, year: np.array(values[variable]))
    return simulate


def refusal(simulate):
    with pytest.raises(pipeline.PassportNotOnReceipt) as refused:
        pipeline.housing_benefit_passport_preflight(simulate=simulate, log=lambda *a: pytest.fail("no pass log"))
    return str(refused.value)


def failed(message):
    return [line.removeprefix("  - failed: ") for line in message.splitlines() if line.startswith("  - failed: ")]


# ── Stand-in models ─────────────────────────────────────────────────────


def test_the_probe_is_two_synthetic_pensioners_differing_only_in_their_pension_credit_claim():
    probe = pipeline.passport_probe()
    assert list(probe["benunits"]) == ["non_claimant_benunit", "claimant_benunit"]
    non_claimant, claimant = probe["benunits"].values()
    assert {k: v for k, v in non_claimant.items() if k not in ("members", "would_claim_pc")} == \
        {k: v for k, v in claimant.items() if k not in ("members", "would_claim_pc")}
    assert non_claimant["would_claim_pc"] == {YEAR: False} and claimant["would_claim_pc"] == {YEAR: True}
    assert probe["people"]["non_claimant"] == probe["people"]["claimant"]
    assert "in_receipt_of_guarantee_credit" not in non_claimant
    receipt = pipeline.passport_probe({"non_claimant": True, "claimant": False})["benunits"]
    assert receipt["non_claimant_benunit"]["in_receipt_of_guarantee_credit"] == {YEAR: True}
    assert receipt["claimant_benunit"]["in_receipt_of_guarantee_credit"] == {YEAR: False}
    # Synthetic: no survey identifier or weight.
    assert not {"household_id", "household_weight", "person_id"} & set(json.dumps(probe).split('"'))


def test_a_receipt_keyed_model_passes_and_the_run_records_what_it_observed():
    logs = []
    record = pipeline.housing_benefit_passport_preflight(simulate=fake_model(receipt_keyed), log=logs.append)
    check = record["housing_benefit_guarantee_credit_passport"]
    assert check["keyed_on"] == "receipt"
    assert check["upstream"] == "PolicyEngine/policyengine-uk#1927" and check["first_release"] == FIRST_RELEASE
    try:
        installed = importlib.metadata.version("policyengine-uk")
    except importlib.metadata.PackageNotFoundError:
        installed = "(not installed)"
    assert check["policyengine_uk"] == installed
    assert check["probe"] == FACTS
    assert check["observed"]["claims"]["housing_benefit"] == [0., FACTS["rent"]]
    assert check["observed"]["receipt_set"]["housing_benefit"] == [FACTS["rent"], 0.]
    assert check["checks"] == [name for name, _ in pipeline.passport_checks(
        check["observed"]["claims"], check["observed"]["receipt_set"], FACTS["rent"])]
    json.dumps(record, allow_nan=False)  # provenance is plain JSON
    assert len(logs) == 1 and "policyengine-uk#1927" in logs[0] and "receipt" in logs[0]


def test_an_entitlement_keyed_model_is_refused_naming_the_failing_checks_and_1927():
    message = refusal(fake_model(entitlement))
    assert "policyengine-uk#1927" in message and f"first released in policyengine-uk {FIRST_RELEASE}" in message
    assert "docs/REBUILD.md" in message
    assert failed(message) == [
        "the entitled non-claimant's housing_benefit_assessable_capital is counted, not disregarded",
        "the entitled non-claimant's housing_benefit_tariff_income is counted, not disregarded",
        "the entitled non-claimant's housing_benefit_applicable_income is counted, not disregarded",
        "the entitled non-claimant is not passported to maximum Housing Benefit",
        "in_receipt_of_guarantee_credit set false means-tests the claimant",
    ]
    observed = json.loads(message.split("Observed, [non-claimant, claimant]: ")[1].splitlines()[0])
    assert observed["claims"]["housing_benefit"] == [FACTS["rent"], FACTS["rent"]]


def test_a_claim_keyed_model_that_never_reads_the_receipt_variable_is_refused():
    assert failed(refusal(fake_model(claim_keyed))) == [
        "in_receipt_of_guarantee_credit set true passports the non-claimant",
        "in_receipt_of_guarantee_credit set false means-tests the claimant",
    ]


@pytest.mark.parametrize("changes, premise", [
    ({"guarantee_credit": 0.}, "both probe benefit units are entitled to Guarantee Credit (guarantee_credit > 0)"),
    ({"tariff_income": 0.}, "the entitled non-claimant's housing_benefit_tariff_income is counted, not disregarded"),
    ({"means_tested_housing_benefit": FACTS["rent"]},
     "the entitled non-claimant is not passported to maximum Housing Benefit"),
])
def test_a_probe_that_no_longer_tests_the_passport_fails_closed(changes, premise):
    """If the installed model no longer makes the probe entitled, or means-testing alone gives maximum Housing
    Benefit, a receipt-keyed passport can't be told from another: the guard refuses rather than passing."""
    assert premise in failed(refusal(fake_model(receipt_keyed, **changes)))


def test_the_probe_must_be_under_the_pension_age_regulations():
    def working_age(situation):
        situation["people"] = {name: {**person, "age": {YEAR: 40}} for name, person in situation["people"].items()}
        return fake_model(receipt_keyed)(situation)
    assert "the probe is under the pension-age Housing Benefit regulations" in failed(refusal(working_age))


@pytest.mark.parametrize("error", [KeyError("in_receipt_of_guarantee_credit"), ImportError("policyengine_uk")])
def test_a_model_that_cannot_calculate_the_probe_is_refused(error):
    def broken(situation):
        raise error
    message = refusal(broken)
    assert "could not calculate the preflight probe" in message and repr(error) in message
    assert "policyengine-uk#1927" in message


@pytest.mark.parametrize("values", [[], [1.], [1., 1., 1.], [np.nan, 1.], [1., np.inf]])
def test_malformed_probe_outputs_fail_with_the_named_preflight_and_1927(values):
    def malformed(situation):
        sim = fake_model(receipt_keyed)(situation)
        calculate = sim.calculate
        sim.calculate = lambda variable, year: np.array(values) if variable == "guarantee_credit" else calculate(variable, year)
        return sim
    message = refusal(malformed)
    assert "housing_benefit_passport_preflight" in message and "policyengine-uk#1927" in message
    assert "claims.guarantee_credit: expected two finite synthetic-household values" in message


def test_the_guard_accepts_exactly_the_passports_keyed_on_receipt():
    """Exhaustive over every passport an entitled family's (receipt, claim) can key: of the sixteen truth tables, only
    receipt itself passes; entitlement (always true here) and the claim proxy are among those refused."""
    passed = []
    for table in itertools.product((False, True), repeat=4):
        truth = dict(zip(itertools.product((False, True), repeat=2), table))

        def passport(entitled, receipt, claims, truth=truth):
            return truth[(bool(receipt), bool(claims))]
        try:
            pipeline.housing_benefit_passport_preflight(simulate=fake_model(passport), log=lambda *a: None)
            passed.append(table)
        except pipeline.PassportNotOnReceipt:
            pass
    assert passed == [tuple(receipt for receipt, _ in itertools.product((False, True), repeat=2))]


@settings(max_examples=60, deadline=None)
@given(st.sampled_from([entitlement, receipt_keyed, claim_keyed]),
       st.floats(min_value=0.01, max_value=20_000), st.floats(min_value=0.01, max_value=5_000),
       st.floats(min_value=0, max_value=FACTS["rent"] - 0.02))
def test_the_decision_depends_only_on_how_the_passport_keys(passport, guarantee_credit, tariff_income, housing_benefit):
    """Whatever positive Guarantee Credit and tariff income the model calculates, and whatever means-tested Housing
    Benefit short of the maximum, the guard passes a receipt-keyed passport and refuses the others."""
    simulate = fake_model(passport, guarantee_credit=guarantee_credit, tariff_income=tariff_income,
                          means_tested_housing_benefit=housing_benefit)
    if passport is receipt_keyed:
        assert pipeline.housing_benefit_passport_preflight(simulate=simulate, log=lambda *a: None)[
            "housing_benefit_guarantee_credit_passport"]["keyed_on"] == "receipt"
    else:
        refusal(simulate)


# ── The installed model ─────────────────────────────────────────────────


def test_the_installed_policyengine_uk_meets_the_guard_only_with_1927():
    """Behavioural, on the installed policyengine-uk: the 2.120.0 pilot pin keys the passport on entitlement, so the
    guard refuses it, with the probe's premises met; from 2.123.6 it passes. (2.123.5, without #1927, was refused and
    2.123.6 passed when checked on 8 October 2026.)"""
    pytest.importorskip("policyengine_uk")
    from packaging.version import Version

    version = importlib.metadata.version("policyengine-uk")
    if Version(version) >= Version(FIRST_RELEASE):
        record = pipeline.housing_benefit_passport_preflight(log=lambda *a: None)
        assert record["housing_benefit_guarantee_credit_passport"]["keyed_on"] == "receipt"
        return
    message = refusal(None)
    assert f"The installed policyengine-uk {version} fails the preflight check" in message
    assert failed(message) == [
        "the entitled non-claimant's housing_benefit_assessable_capital is counted, not disregarded",
        "the entitled non-claimant's housing_benefit_tariff_income is counted, not disregarded",
        "the entitled non-claimant's housing_benefit_applicable_income is counted, not disregarded",
        "the entitled non-claimant is not passported to maximum Housing Benefit",
        "in_receipt_of_guarantee_credit set false means-tests the claimant",
    ]


# ── Where it runs ───────────────────────────────────────────────────────


def refuse(*a, **kw):
    raise pipeline.PassportNotOnReceipt("synthetic: keyed on entitlement")


def no_jobs(*a, **kw):
    pytest.fail("no model job may start before the preflight passes")


def test_the_build_refuses_before_any_model_job(monkeypatch):
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)  # nor loads the model
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(EV, "_handoff", lambda *a, **kw: ("synthetic", {}))
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", refuse)
    monkeypatch.setattr(pipeline.jobs, "run_jobs", no_jobs)
    monkeypatch.setattr(EV, "build", no_jobs)
    with pytest.raises(pipeline.PassportNotOnReceipt):
        pipeline.build(uncertainty_ruling="c")


def test_standalone_mean_path_scenarios_refuse_before_any_model_job(monkeypatch):
    # None in sys.modules makes importing policyengine_uk.system fail: the refusal comes first.
    monkeypatch.setitem(sys.modules, "policyengine_uk.system", None)
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", refuse)
    monkeypatch.setattr(EV, "build_mean_path_scenarios", no_jobs)
    monkeypatch.setattr(pipeline.jobs, "run_jobs", no_jobs)
    with pytest.raises(pipeline.PassportNotOnReceipt):
        pipeline.mean_path_scenarios(uncertainty_ruling="c")


def test_a_single_scenario_run_refuses_before_any_model_job_and_records_a_pass(monkeypatch):
    monkeypatch.setattr(pipeline, "snapshot", lambda: {"git_dirty": False, "git_revision": "synthetic"})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", refuse)
    monkeypatch.setattr(pipeline, "run_scenarios", no_jobs)
    with pytest.raises(pipeline.PassportNotOnReceipt):
        pipeline.scenario("obr_premium")
    passed = {"housing_benefit_guarantee_credit_passport": {"keyed_on": "receipt"}}
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", lambda log=print: passed)
    monkeypatch.setattr(pipeline.central_module, "central_path", lambda: {})
    monkeypatch.setattr(pipeline, "run_scenarios", lambda central, names, log=print: {names[0]: ({}, {})})
    monkeypatch.setattr(pipeline, "check_unchanged", lambda *a: None)
    monkeypatch.setattr(pipeline, "scenario_record", lambda spec, run, start, what: start)
    assert pipeline.scenario("obr_premium")["preflight"] == passed


def ageing_entry_point(entry):
    if entry == "module":
        from triple_lock.ageing_validation import main
        return main
    spec = importlib.util.spec_from_file_location(
        "validate_ageing", Path(__file__).resolve().parents[1] / "scripts" / "validate_ageing.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return script.run


@pytest.mark.parametrize("entry", ["module", "wrapper"])
@pytest.mark.parametrize("central_only", [False, True])
def test_the_ageing_validation_refuses_before_any_model_job(monkeypatch, tmp_path, entry, central_only):
    from triple_lock import ageing_validation as AV, jobs

    output = tmp_path / "ageing.json"
    monkeypatch.setattr(AV, "validation_plan", lambda *a: {"jobs": [("path", {})]})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", refuse)
    monkeypatch.setattr(jobs, "run_jobs", no_jobs)
    monkeypatch.setattr(AV, "summarise", no_jobs)
    argv = ["--workers", "3", "-o", str(output)] + (["--central-only"] if central_only else [])
    with pytest.raises(pipeline.PassportNotOnReceipt):
        ageing_entry_point(entry)(argv)
    assert not output.exists()


def test_python_m_ageing_validation_refuses_before_any_model_job(monkeypatch, tmp_path):
    """Execute the module's actual __main__ block, so guarding only the script cannot pass this regression."""
    from triple_lock import central, jobs, trajectories

    source = tmp_path / "source.json"
    source.write_text("{}")
    output = tmp_path / "ageing.json"
    monkeypatch.setattr(central, "central_path", lambda: {})
    monkeypatch.setattr(central, "september_cpi_history", lambda: {})
    monkeypatch.setattr(trajectories, "central_spec", lambda central: {})
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", refuse)
    monkeypatch.setattr(jobs, "run_jobs", no_jobs)
    monkeypatch.setattr(sys, "argv", ["triple_lock.ageing_validation", "--central-only",
                                     "--source-results", str(source), "-o", str(output)])
    monkeypatch.delitem(sys.modules, "triple_lock.ageing_validation", raising=False)
    with pytest.raises(pipeline.PassportNotOnReceipt):
        runpy.run_module("triple_lock.ageing_validation", run_name="__main__")
    assert not output.exists()


@pytest.mark.parametrize("entry", ["module", "wrapper"])
@pytest.mark.parametrize("argv", [["--plan"], ["--plan", "--central-only"], ["--help"], ["-h"]])
def test_ageing_plans_and_help_do_not_run_the_preflight(monkeypatch, capsys, entry, argv):
    from triple_lock import ageing_validation as AV, jobs

    plan = {"jobs": [("path", {}), ("coverage", {})], "modes": ["both"],
            "sample": {}, "W": {}, "W0": 1.0}
    monkeypatch.setattr(AV, "validation_plan", lambda *a: plan)
    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", no_jobs)
    monkeypatch.setattr(jobs, "run_jobs", no_jobs)
    if {"-h", "--help"} & set(argv):
        with pytest.raises(SystemExit) as exited:
            ageing_entry_point(entry)(argv)
        assert exited.value.code == 0
        assert "usage:" in capsys.readouterr().out
    else:
        assert ageing_entry_point(entry)(argv) == 0
        assert json.loads(capsys.readouterr().out)["jobs"] == 2


@pytest.mark.parametrize("entry", ["module", "wrapper"])
@pytest.mark.parametrize("central_only", [False, True])
def test_ageing_reports_record_the_full_passed_preflight(monkeypatch, tmp_path, entry, central_only):
    """Both real report modes retain the observations; the wrapper delegates so each run checks exactly once."""
    from triple_lock import ageing_validation as AV, jobs

    record = pipeline.housing_benefit_passport_preflight(simulate=fake_model(receipt_keyed), log=lambda *a: None)
    names = ["central"] if central_only else ["central", "draw_1", "draw_2"]
    plan = {"jobs": [("path", {"label": name}) for name in names],
            "labels": [(name, "both") for name in names], "modes": ["both"],
            "sample": {} if central_only else {1: [1, 2]}, "W": {} if central_only else {1: 0.8},
            "W0": 1.0 if central_only else 0.2, "central_only": central_only, "n_draws": 50_000,
            "dataset": "synthetic", "source": "synthetic.json", "source_sha256": "synthetic"}
    results = [{"saving_bn": {year: {"gross": float(i), "net": float(i) / 2,
                                     "gb": {"gross": float(i), "net": float(i) / 2}}
                              for year in AV.HORIZON},
                "fixed_inputs": {"population": {}, "ageing": None, "state_pension_accounting": {}},
                "model": {"model_version": record["housing_benefit_guarantee_credit_passport"]["policyengine_uk"]}}
               for i, _ in enumerate(names, start=1)]
    events = []

    def preflight():
        events.append("preflight")
        return record

    def run_jobs(arguments, workers, slot_prefix):
        assert events == ["preflight"]
        assert arguments == plan["jobs"] and workers == 1 and slot_prefix == "efrs"
        events.append("jobs")
        return results

    def validation_plan(source, requested_central_only, modes):
        assert requested_central_only == central_only and modes == ("both",)
        return plan

    monkeypatch.setattr(pipeline, "housing_benefit_passport_preflight", preflight)
    monkeypatch.setattr(AV, "validation_plan", validation_plan)
    monkeypatch.setattr(AV, "dwp_forecasts", lambda: {"years": {}})
    monkeypatch.setattr(jobs, "run_jobs", run_jobs)
    output = tmp_path / "reports" / "ageing.json"
    argv = ["--modes", "both", "-o", str(output)] + (["--central-only"] if central_only else [])
    assert ageing_entry_point(entry)(argv) == 0
    report = json.loads(output.read_text())
    assert report["provenance"]["preflight"] == record
    assert report["model"] == results[0]["model"]
    assert report["complete_paired_design"] == (not central_only)
    assert bool(report["expected_saving_bn"]) == (not central_only)
    assert events == ["preflight", "jobs"]


def test_a_rebuilt_results_file_must_record_a_passed_preflight():
    """The results and scenario files' contract (test_results.check_passport_preflight), which the committed
    pre-rebuild files meet vacuously: a model-v2 file must carry a passed record for its own policyengine-uk."""
    import copy

    import test_results

    record = pipeline.housing_benefit_passport_preflight(simulate=fake_model(receipt_keyed), log=lambda *a: None)
    version = record["housing_benefit_guarantee_credit_passport"]["policyengine_uk"]
    rebuilt = {"model": {"model_version": version}, "packages": {"policyengine-uk": version}, "preflight": record}
    test_results.check_passport_preflight(rebuilt)
    test_results.check_passport_preflight({"release_bundle": {}, "packages": {}})  # built before model-v2

    def broken(change):
        provenance = copy.deepcopy(rebuilt)
        change(provenance, provenance["preflight"]["housing_benefit_guarantee_credit_passport"])
        return provenance
    for provenance in (
            broken(lambda p, c: p.pop("preflight")),
            broken(lambda p, c: c.update(keyed_on="entitlement")),
            broken(lambda p, c: p["packages"].update({"policyengine-uk": version + ".post1"})),
            broken(lambda p, c: c["observed"]["claims"].update(housing_benefit=[FACTS["rent"]] * 2)),
            broken(lambda p, c: c["checks"].pop())):
        with pytest.raises((AssertionError, KeyError)):
            test_results.check_passport_preflight(provenance)
