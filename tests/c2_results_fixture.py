"""Public synthetic C2 results shapes; no engine execution or macro scoring."""

from copy import deepcopy

from triple_lock import expected_value as EV, ts_uncertainty as TU
from triple_lock.config import FINAL_YEAR, HORIZON, SWITCH_YEAR


def artifact(primary_passes):
    score = {"n_origins": 12, "expected_origins": 12,
             **{key: {"mean": 1.} for key in TU.PROPER_SCORES},
             **{key: {"mean": 0.} for key in ("gap_bias_pp", "switch_bias", "floor_bias")},
             "annual_gap_coverage": {"mean": .8},
             "terminal_coverage": {"mean": .8, "wilson95_independent": [.5, .95]}}
    saved = {"scores": {test: {treatment: {form: deepcopy(score) for form in TU.CANDIDATES}
                               for treatment in ("suspended", "published")} for test in ("A", "B")},
             "past_years": {form: {treatment: {"realised_percentile": 50.}
                                   for treatment in ("suspended", "published")} for form in TU.CANDIDATES},
             "origins": {"A": list(range(2016, 2022)), "B": list(range(2010, 2022))},
             "suspended_determination_years": [2021], "exclusion": "statutory constant cells"}
    for form in TU.CANDIDATES:
        saved["scores"]["A"]["published"][form]["terminal_coverage"]["mean"] = 1 / 6
    if not primary_passes:
        saved["past_years"][TU.PRIMARY_FORM]["suspended"]["realised_percentile"] = 99.
    outcome = TU.adequacy(saved, screen="c2")
    effective = "c" if primary_passes else "a"
    screen = {"screen": "c2", "rule_sha": TU.C2_PRE_REGISTRATION_COMMIT, "run_kind": "binding",
              "scoring_head": "f" * 40, "score_table_sha256": "a" * 64,
              "expected_value_authorized": primary_passes,
              "authorization": "binding primary pass" if primary_passes else "binding automatic scenario-only fallback",
              "c1_failure": TU.c1_failure_provenance(), "c2_scores": saved, "c2_outcome": outcome}
    ruling = {"decision": "d955", "requested_ruling": "c", "effective_ruling": effective,
              "ruling": effective, **deepcopy(screen)}
    if not primary_passes:
        ruling["fallback_reason"] = "Original primary failed C2 past-years check; automatic d955(a) fallback"

    paths = []
    for i in range(4):
        outputs = {dataset: {key: {str(y): (i + 1) * factor * (y - SWITCH_YEAR + 1) if y >= SWITCH_YEAR else 0.
                                   for y in HORIZON} for key, factor in (("gross", scale), ("net", scale / 2))}
                   for dataset, scale in (("primary", 1.), ("sensitivity", 1.1))}
        paths.append({"draw": i, "stratum": 1 if i < 2 else 2, "times_drawn": 40,
                      "times_drawn_sensitivity": 10, "gap_2039_gbp_week": i + 1,
                      "outputs": outputs, "weight_ratio": {}})
    weights = {1: .6, 2: .4}

    def estimate(dataset, key, y, paired=False):
        values = {k: [] for k in weights}
        for path in paths:
            value = path["outputs"][dataset][key][str(y)]
            if paired:
                value -= path["outputs"]["primary"][key][str(y)]
            count = path["times_drawn" if dataset == "primary" else "times_drawn_sensitivity"]
            values[path["stratum"]] += [value] * count
        return EV.stratified_estimate(values, weights, 50_000)

    estimates = {dataset: {key: {str(y): estimate(dataset, key, y) for y in HORIZON}
                           for key in ("gross", "net")} for dataset in ("primary", "sensitivity")}
    paired = {key: {str(y): estimate("sensitivity", key, y, paired=True) for y in HORIZON}
              for key in ("gross", "net")}
    means = {"interpretation": "paired mean-path scenarios; not a probability interval",
             "adequacy_gate_applies": False, "provenance": deepcopy(ruling),
             "sample_slots": 160, "baseline_full_runs": 4,
             "scenarios": {label: {"calendar_earnings_delta": delta, "from_year": 2031,
                                   "paired_difference": deepcopy(paired), "scenario_path_set": deepcopy(estimates["primary"])}
                           for label, delta in (("earnings_minus_0_5pp", -.005), ("earnings_plus_0_5pp", .005))}}
    fixed = {"data_year": 2024, "population": {"weights": "survey", "ages": "survey_year", "pension_types": "survey_year"},
             "state_pension_age": {str(y): [66., 67.] if y < 2028 else [67.] for y in HORIZON},
             "held_pension_type_records": {str(y): {"BASIC": 20, "NEW": 30, "NONE": 50} for y in HORIZON}}
    run = {"fixed_inputs": fixed, "dataset": "synthetic", "saving_bn": {str(FINAL_YEAR): {"gross": 1.}}}
    replay = {"switch_years": [2017], "model_years": {"2024": {"synthetic": True}}}
    historical_inputs = {key: {str(y): .02 for y in range(2017, 2027)} for key in ("cpi", "earnings")}
    central = {"path": {"synthetic": True}, "run": run}
    envelope = {"interpretation": "scenario envelope; not a probability interval", "central": deepcopy(central),
                "obr_wedge": {"path": {"id": "obr_premium"}, "run": deepcopy(run)},
                "last_decade_replay": {"years": list(range(2017, 2027)), "switch_year": 2017,
                                       "model_years": [2024, 2025, 2026], "counterfactual": replay,
                                       "interpretation": "historical legal replay; not a future forecast",
                                       "statutory": historical_inputs}, "paired_earnings_mean_paths": deepcopy(means)}
    results = {"central": central, "uncertainty_ruling": ruling, "uncertainty_screen": screen,
               "provenance": {"uncertainty_ruling": deepcopy(ruling), "uncertainty_screen": deepcopy(screen)},
               "mean_path_scenarios": means, "scenario_envelope": envelope,
               "trajectories": {"paths": [{"id": name, **deepcopy(run)} for name in ("central", "random")],
                                "models": {"boot": {"label": "Synthetic bootstrap", "runs_paths": True}}},
               "coverage": {"year": 2026, "datasets": {"primary": {"max_age": 100}},
                            "dwp": {"geography": "Great Britain, synthetic comparator"},
                            "rows": [{"key": key, "primary": 2., "primary_gb": 1.9, "dwp": 1.8}
                                     for key in ("pension_credit_claims_m", "housing_benefit_pension_age_bn")]}}
    if primary_passes:
        results["expected_value"] = {"label": "model-conditional", "interpretation": EV.UNCERTAINTY_RULINGS["c"],
                                     "method": "C1 160-slot own-form Neyman handoff; full paired PolicyEngine rule runs",
                                     "provenance": deepcopy(ruling), "adequacy": deepcopy(outcome),
                                     "form": TU.PRIMARY_FORM, "primary": "means_shift", "sample_slots": 160,
                                     "unique_full_runs": 4, "draws": {"n": 50_000},
                                     "calibrations": {"means_shift": {"draws": "shifted", "ess": 50_000},
                                                      "shift_dynamics.rejected": {"draws": "shifted", "error": "synthetic infeasible tilt"}},
                                     "strata": [{"stratum": k, "probability": weight, "paths": 80,
                                                 "unique_paths": 2, "sensitivity_paths": 20}
                                                for k, weight in weights.items()],
                                     "identical_rates": {"probability": 0., "included_in_strata": False, "check_run": None},
                                     "datasets": {"primary": "synthetic", "sensitivity": "populace_uk_2023"},
                                     "estimates": estimates, "paired_difference": paired, "sensitivities": {},
                                     "paths": paths, "uncertainty_reporting": {"monte_carlo": "synthetic conditional precision"}}
    else:
        results["expected_value_omission"] = {"requested_ruling": "c", "effective_ruling": "a",
                                              "reason": ruling["fallback_reason"]}
    return results
