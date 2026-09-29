"""PolicyEngine runs for the triple lock analysis.

How the reform bites
--------------------
policyengine-uk builds the triple lock rate at parameter-load time
(create_triple_lock.py writes ``gov.economic_assumptions.yoy_growth.triple_lock``)
and then uprates the flat-rate State Pension amounts from it, also at load
time. A runtime reform to the triple-lock flags, or to the derived growth
parameter, therefore changes nothing downstream. The reform here instead
overwrites ``basic_state_pension.amount`` and ``new_state_pension.amount``
for every fiscal year 2027..2034 with levels compounded from the 2026-27
rates under the chosen rule. Each year needs its own value: setting only
2027 leaves 2028 on the baseline amount.

PolicyEngine uprates the additional State Pension with the flat-rate ratio,
so every reform simulation has that variable pinned to the baseline values
(``set_input`` before any calculation). In law it is CPI-linked and none of
the rules here change it.
"""

import numpy as np

from .benchmarks import BENCHMARKS_CSV, load_benchmarks
from .breakdowns import (
    BREAKDOWNS,
    NOTES as BREAKDOWN_NOTES,
    TENURE_GROUPS,
    age_band,
    all_breakdowns,
    breakdown,
    decile_groups,
    household_frame,
    household_type,
    largest_household_contribution,
    map_labels,
)
from .config import (
    ALTERNATIVES,
    BASE_YEAR,
    BASELINE_POLICY,
    CENTRAL_RATE_DECIMALS,
    CPI_PARAMETER,
    EARNINGS_PARAMETER,
    ERROR_CSV,
    EXTRA_DISTRIBUTION_YEAR,
    FINAL_YEAR,
    FISCAL_COMPONENTS,
    FLAT_RATE_PARAMETERS,
    FORECAST_SOURCE,
    FORECAST_SOURCE_URL,
    HORIZON,
    METHOD_LIMITATIONS,
    MODEL_TRIPLE_LOCK_PARAMETER,
    AWE_GAP_SD,
    AWE_CSV,
    AWE_PERIOD,
    AWE_URL,
    CENTRAL_FORECAST_CSV,
    CPI_Q3_PERIOD,
    EX_2022_23_TARGET_YEARS,
    STATUTORY_YEAR,
    N_DRAWS,
    POLICIES,
    QUARTERLY_GROWTH_YEARS,
    REPO,
    TRIPLE_LOCK_FLOOR,
)
from .provenance import build_provenance, file_hash
from .rules import cumulative_index, level_path, uprating_path

BN = 1e9
AMOUNT_REL_TOL = 1e-5
# Variables pinned to baseline in every reform run.
PINNED_VARIABLES = ["additional_state_pension"]


# ── Parameters ───────────────────────────────────────────────────────────


def _param(parameters, path):
    node = parameters
    for part in path.split("."):
        node = getattr(node, part)
    return node


def model_forecast(parameters, years=HORIZON):
    """PolicyEngine's OBR growth for the calendar years that set each uprating."""
    cpi = _param(parameters, CPI_PARAMETER)
    earnings = _param(parameters, EARNINGS_PARAMETER)
    growth_years = [y - 1 for y in years]
    return (
        {g: float(cpi(g)) for g in growth_years},
        {g: float(earnings(g)) for g in growth_years},
    )


def uprating_paths(cpi, earnings, years=HORIZON):
    return {
        p: uprating_path(p, cpi, earnings, years, decimals=CENTRAL_RATE_DECIMALS)
        for p in POLICIES
    }


def model_uprating(parameters, years=HORIZON):
    """Uprating on PolicyEngine's own calendar-year path (reproduces its triple lock)."""
    return uprating_paths(*model_forecast(parameters, years), years)


def statutory_inputs(awe_csv=AWE_CSV, forecast_csv=CENTRAL_FORECAST_CSV):
    """Inputs for the April 2027 uprating on the statutory timing.

    Earnings: published May-July 2026 AWE total pay growth (ONS KAC3, July
    2026 value). CPI: the OBR March 2026 forecast of 2026 Q3 CPI inflation,
    standing in for September 2026 CPI until it is published.
    """
    import csv

    with awe_csv.open(newline="") as f:
        awe = {row[0]: row[1] for row in csv.reader(f) if len(row) >= 2}
    earnings = float(awe[AWE_PERIOD]) / 100
    with forecast_csv.open(newline="") as f:
        cpi_rows = [
            r for r in csv.DictReader(f)
            if r["variable"] == "cpi" and r["basis"] == "q3_yoy" and r["period"] == CPI_Q3_PERIOD
        ]
    if len(cpi_rows) != 1:
        raise KeyError(f"{forecast_csv} must have exactly one cpi q3_yoy {CPI_Q3_PERIOD} row")
    return {
        "growth_year": STATUTORY_YEAR,
        "earnings": earnings,
        "earnings_source": f"ONS AWE whole-economy total pay, 3-month average y/y (KAC3), {AWE_PERIOD}",
        "earnings_url": AWE_URL,
        "cpi": float(cpi_rows[0]["value"]),
        "cpi_source": f"OBR March 2026 EFO forecast of CPI inflation, {CPI_Q3_PERIOD} "
        "(proxy for September 2026 CPI, published 21 October 2026)",
        "cpi_url": cpi_rows[0]["source_url"],
    }


def central_path(parameters, years=HORIZON):
    """Model growth path with the statutory April 2027 inputs substituted."""
    cpi, earnings = model_forecast(parameters, years)
    statutory = statutory_inputs()
    statutory["model_cpi"] = cpi[STATUTORY_YEAR]
    statutory["model_earnings"] = earnings[STATUTORY_YEAR]
    cpi[STATUTORY_YEAR] = statutory["cpi"]
    earnings[STATUTORY_YEAR] = statutory["earnings"]
    return cpi, earnings, statutory


def base_levels(parameters):
    """2026-27 weekly flat-rate amounts every rule compounds from."""
    return {
        name: float(_param(parameters, path)(BASE_YEAR))
        for name, path in FLAT_RATE_PARAMETERS.items()
    }


def check_baseline_reproduction(parameters, triple_lock_rates, years=HORIZON, tol=1e-6):
    """Fail loudly if our triple lock path differs from the model's own.

    Confirms both the rate (and so the y-1 timing) and the compounded weekly
    amounts, which is what makes the triple-lock reform identical to the
    unreformed baseline.
    """
    model_rate = _param(parameters, MODEL_TRIPLE_LOCK_PARAMETER)
    for y in years:
        if abs(model_rate(y) - triple_lock_rates[y]) > tol:
            raise AssertionError(
                f"triple lock {y}: model {model_rate(y)} vs reproduced {triple_lock_rates[y]}"
            )
    for name, path in FLAT_RATE_PARAMETERS.items():
        base = float(_param(parameters, path)(BASE_YEAR))
        ours = level_path(base, triple_lock_rates, years)
        for y in years:
            model = float(_param(parameters, path)(y))
            # The model uprates through an index stored to 5 dp, so its amounts
            # differ from exact compounding by up to ~5e-6 (about £0.001 a week,
            # under £0.001bn a year of spending).
            if abs(model - ours[y]) > AMOUNT_REL_TOL * model:
                raise AssertionError(f"{name} {y}: model {model} vs reproduced {ours[y]}")


def flat_rate_reform(levels_by_parameter):
    """Reform dict setting each flat-rate amount for each fiscal year.

    Parameters are held on calendar-year periods after policyengine-uk's
    fiscal-year conversion, so year ``y`` covers 2027-04 to 2028-03 when
    read as ``param(y)``.
    """
    return {
        FLAT_RATE_PARAMETERS[name]: {
            f"{y}-01-01.{y}-12-31": float(level) for y, level in levels.items()
        }
        for name, levels in levels_by_parameter.items()
    }


def reform_for_rates(parameters, rates, years=HORIZON):
    base = base_levels(parameters)
    levels = {name: level_path(base[name], rates, years) for name in FLAT_RATE_PARAMETERS}
    return flat_rate_reform(levels), levels


# ── Simulation helpers ───────────────────────────────────────────────────


def _baseline_sim():
    from policyengine.tax_benefit_models.uk import managed_microsimulation

    return managed_microsimulation()


def _reform_sim(reform, pinned):
    """Reform simulation with ``pinned`` variables set to baseline before any calculation."""
    from policyengine.tax_benefit_models.uk import managed_microsimulation

    sim = managed_microsimulation(reform=reform)
    for var, by_year in pinned.items():
        for year, values in by_year.items():
            sim.set_input(var, year, values)
    return sim


def collect(sim, years):
    """Weighted fiscal totals (£bn) and household net income MicroSeries per year."""
    totals, income = {}, {}
    for y in years:
        t = {
            name: sum(float(sim.calculate(v, y, map_to="household").sum()) for v in variables) / BN
            for name, variables in FISCAL_COMPONENTS.items()
        }
        t["gov_balance"] = float(sim.calculate("gov_balance", y, map_to="household").sum()) / BN
        income[y] = sim.calculate("household_net_income", y)
        t["household_net_income"] = float(income[y].sum()) / BN
        totals[y] = t
    return {"totals": totals, "income": income}


def household_groups(sim, year):
    """Group label arrays (one per household) for every breakdown."""
    decile, quintile = decile_groups(sim.calculate("household_income_decile", year).to_numpy())
    head_age = sim.map_result(
        sim.calculate("age", year).to_numpy() * sim.calculate("is_household_head", year).to_numpy(),
        "person",
        "household",
    )
    heads = sim.calculate("is_household_head", year, map_to="household").to_numpy()
    if not (heads == 1).all():
        raise ValueError("every household must have exactly one head")
    return {
        "decile": decile,
        "quintile": quintile,
        "region": np.asarray(sim.calculate("region", year).to_numpy()).astype(str),
        "tenure": map_labels(sim.calculate("tenure_type", year).to_numpy(), TENURE_GROUPS, "tenure"),
        "hh_type": household_type(
            sim.calculate("is_adult", year, map_to="household").to_numpy(),
            sim.calculate("is_SP_age", year, map_to="household").to_numpy(),
            sim.calculate("is_child", year, map_to="household").to_numpy(),
        ),
        "age_band": age_band(head_age),
    }


# ── Outputs ──────────────────────────────────────────────────────────────


def cost_vs_baseline(reform_totals, baseline_totals, years):
    """Gross and net cost of a rule relative to the triple lock, £bn by year.

    gross: change in basic + new State Pension spend.
    net:   change in the government balance (gov_balance: taxes minus
           spending attributed to households), sign-flipped so that a
           negative value is a saving.
    """
    gross, net, components, hni = {}, {}, {}, {}
    for y in years:
        r, b = reform_totals[y], baseline_totals[y]
        gross[str(y)] = round(r["state_pension_flat_rate"] - b["state_pension_flat_rate"], 2)
        net[str(y)] = round(-(r["gov_balance"] - b["gov_balance"]), 2)
        hni[str(y)] = round(r["household_net_income"] - b["household_net_income"], 2)
        components[str(y)] = {
            k: round(r[k] - b[k], 3) for k in FISCAL_COMPONENTS if k != "state_pension_flat_rate"
        }
    return {
        "gross": gross,
        "net": net,
        "change_in_household_net_income": hni,
        "components": components,
    }


def _round_map(d, nd):
    return {str(k): round(float(v), nd) for k, v in d.items()}


# ── Pipeline ─────────────────────────────────────────────────────────────


def run_full_pipeline(error_csv=ERROR_CSV, n_draws=N_DRAWS, log=print):
    from .uncertainty import (
        bias_label,
        error_blocks,
        load_forecast_errors,
        mean_error_by_horizon,
        run_monte_carlo,
    )

    years = HORIZON
    dist_years = [FINAL_YEAR, EXTRA_DISTRIBUTION_YEAR]
    input_hashes = {str(error_csv.relative_to(REPO)): file_hash(error_csv)}
    errors = load_forecast_errors(error_csv)

    log("Unreformed model (additional State Pension to pin)")
    model_sim = _baseline_sim()
    bundle = model_sim.policyengine_bundle
    parameters = model_sim.tax_benefit_system.parameters
    check_baseline_reproduction(parameters, model_uprating(parameters)[BASELINE_POLICY])
    pinned = {
        v: {y: model_sim.calculate(v, y).to_numpy() for y in years} for v in PINNED_VARIABLES
    }
    del model_sim
    input_hashes[str(AWE_CSV.relative_to(REPO))] = file_hash(AWE_CSV)
    input_hashes[str(CENTRAL_FORECAST_CSV.relative_to(REPO))] = file_hash(CENTRAL_FORECAST_CSV)
    cpi, earnings, statutory = central_path(parameters)
    uprating = uprating_paths(cpi, earnings)

    log("Baseline: triple lock on the central path")
    tl_reform, _ = reform_for_rates(parameters, uprating[BASELINE_POLICY])
    baseline_sim = _reform_sim(tl_reform, pinned)
    baseline = collect(baseline_sim, years)
    groups = {y: household_groups(baseline_sim, y) for y in dist_years}
    del baseline_sim

    weekly, costs, dist = {}, {}, {y: {} for y in dist_years}
    _, tl_levels = reform_for_rates(parameters, uprating[BASELINE_POLICY])
    weekly[BASELINE_POLICY] = _round_map(tl_levels["new_state_pension"], 2)
    basic_weekly = {BASELINE_POLICY: _round_map(tl_levels["basic_state_pension"], 2)}
    for policy in ALTERNATIVES:
        log(f"Central: {policy}")
        reform, levels = reform_for_rates(parameters, uprating[policy])
        weekly[policy] = _round_map(levels["new_state_pension"], 2)
        basic_weekly[policy] = _round_map(levels["basic_state_pension"], 2)
        result = collect(_reform_sim(reform, pinned), years)
        for y in years:
            moved = result["totals"][y]["additional_state_pension"] - baseline["totals"][y]["additional_state_pension"]
            if abs(moved) > 1e-6:
                raise AssertionError(f"additional State Pension moved in {policy} {y}")
        costs[policy] = cost_vs_baseline(result["totals"], baseline["totals"], years)
        largest = {
            str(y): largest_household_contribution(result["income"][y] - baseline["income"][y])
            for y in years
        }
        costs[policy]["largest_single_household"] = largest
        costs[policy]["net_excluding_largest_household"] = {
            y: round(costs[policy]["net"][y] - largest[y]["contribution_bn"], 2) for y in largest
        }
        for y in dist_years:
            dist[y][policy] = all_breakdowns(
                result["income"][y] - baseline["income"][y], baseline["income"][y], groups[y]
            )

    baseline_spend = {
        str(y): {
            "state_pension_flat_rate_bn": round(baseline["totals"][y]["state_pension_flat_rate"], 2),
            "additional_state_pension_bn": round(baseline["totals"][y]["additional_state_pension"], 2),
            "pension_credit_bn": round(baseline["totals"][y]["pension_credit"], 2),
        }
        for y in years
    }

    tl_index = cumulative_index(uprating[BASELINE_POLICY], years)
    final_spend = baseline["totals"][FINAL_YEAR]["state_pension_flat_rate"]
    composition = composition_effect(baseline["totals"], uprating, costs, years)

    def tables(year):
        keys = list(BREAKDOWNS) + ["households_affected"]
        return {key: {p: dist[year][p][key] for p in ALTERNATIVES} for key in keys}

    central = {
        "forecast": {
            "source": FORECAST_SOURCE,
            "source_url": FORECAST_SOURCE_URL,
            "timing": "uprating in fiscal year y uses calendar-year growth in y-1; "
            "keys here are the growth (calendar) years",
            "cpi": _round_map(cpi, 4),
            "earnings": _round_map(earnings, 4),
            "statutory_2027_inputs": statutory,
            "statutory_2027_note": f"growth year {STATUTORY_YEAR} (the April 2027 uprating) uses the "
            "statutory-timing inputs in statutory_2027_inputs instead of PolicyEngine's calendar-year "
            f"growth (CPI {statutory['model_cpi']:.3f}, earnings {statutory['model_earnings']:.3f}); "
            "PolicyEngine's own April 2027 triple lock rate is therefore not used",
        },
        "uprating": {p: _round_map(r, 4) for p, r in uprating.items()},
        "cost_vs_triple_lock_bn": costs,
        "net_cost_basis": "net = minus the change in PolicyEngine gov_balance (household "
        "taxes minus household benefits); components gives the main channels; "
        "change_in_household_net_income is a cross-check",
        "composition_effect": composition,
        "timing_sensitivity": timing_sensitivity(cpi, earnings, final_spend, tl_index[FINAL_YEAR], years),
        "full_state_pension_weekly": weekly,
        "full_basic_state_pension_weekly": basic_weekly,
        "base_year_weekly": {
            "year": BASE_YEAR,
            **{k: round(v, 2) for k, v in base_levels(parameters).items()},
        },
        "baseline_spend": baseline_spend,
        "distribution_year": FINAL_YEAR,
        **tables(FINAL_YEAR),
        "breakdown_notes": BREAKDOWN_NOTES,
        "households_affected_note": "losing_pct: % of households with a net income "
        "loss over £1 a year vs the triple lock; mean_loss_gbp: their mean loss, positive",
        f"distribution_{EXTRA_DISTRIBUTION_YEAR}": tables(EXTRA_DISTRIBUTION_YEAR),
    }

    # ── Uncertainty ──
    blocks, kept = error_blocks(errors)
    mc_args = dict(
        central_cpi=cpi,
        central_earnings=earnings,
        uprating_years=years,
        forecast_year=BASE_YEAR,
        blocks=blocks,
        final_year_spend_bn=final_spend,
        central_final_index=tl_index[FINAL_YEAR],
        n_draws=n_draws,
    )
    log(f"Monte Carlo: {n_draws} draws over {len(kept)} vintages")
    uncertainty = run_monte_carlo(**mc_args, demean=True)
    uncertainty["basis_note"] = (
        "gross: change in basic + new State Pension spend, £bn nominal, "
        f"{FINAL_YEAR}-{str(FINAL_YEAR + 1)[2:]}; positive = triple lock costs more"
    )
    uncertainty["error_source"] = {
        "title": "OBR Historical official forecasts database (Spring 2026), "
        "CPI and average earnings growth forecast errors by vintage and horizon",
        "url": "https://obr.uk/docs/dlm_uploads/Historical_official_forecasts_database_Spring_2026.xlsx",
        "file": str(error_csv.relative_to(REPO)),
        "years_used": sorted({v[0] for v in kept}),
        "vintages_used": [v[1] for v in kept],
        "block_horizon": int(blocks.shape[1]),
        "mean_error_by_horizon": mean_error_by_horizon(blocks),
        "method": (
            "Block bootstrap of whole forecast vintages (CPI and earnings errors "
            "drawn together, preserving their correlation and horizon structure), "
            "de-meaned by horizon so the draws centre on the OBR central path, and "
            "added to it. Horizon 0 (2026, setting the April 2027 uprating) is not "
            f"perturbed; horizons 1-{blocks.shape[1]} come from one vintage; later horizons "
            "from further independently drawn vintages' longest-horizon errors (horizons "
            "2-4). No rule cuts the cash pension: every rule's uprating is floored at 0 in "
            "every draw. Final-year cost = PolicyEngine baseline basic+new State Pension "
            "spend x (I_TL - I_alt) / I_TL,central, validated against full PolicyEngine "
            "runs on the representative paths. The raw-error run, which keeps the OBR's "
            "historical bias, is sensitivity_raw_errors."
        ),
    }
    ex_blocks, ex_kept = error_blocks(errors, exclude_target_years=EX_2022_23_TARGET_YEARS)

    def sensitivity(mc, description, **extra):
        return {"description": description, **extra, **mc}

    uncertainty["sensitivity_raw_errors"] = sensitivity(
        run_monte_carlo(**mc_args),
        "Raw (not de-meaned) forecast errors: " + bias_label(blocks),
        mean_error_by_horizon=mean_error_by_horizon(blocks),
    )
    uncertainty["sensitivity_ex_2022_23"] = sensitivity(
        run_monte_carlo(**{**mc_args, "blocks": ex_blocks}, demean=True),
        "De-meaned; drops every vintage whose horizon 1-4 target years include 2022 or 2023",
        years_used=sorted({v[0] for v in ex_kept}),
    )
    uncertainty["sensitivity_awe_gap"] = sensitivity(
        run_monte_carlo(**mc_args, demean=True, earnings_noise_sd=AWE_GAP_SD),
        "De-meaned, plus independent N(0, 1.4pp) noise on earnings each perturbed year for "
        "the gap between OBR average earnings and May-July AWE",
    )
    uncertainty["var_cross_check"] = var_cross_check(
        cpi, earnings, years, final_spend, tl_index[FINAL_YEAR], n_draws, input_hashes
    )
    uncertainty["representative_path_runs"] = run_representative_paths(
        parameters, uncertainty["representative_paths"], pinned, groups[FINAL_YEAR], log
    )

    results = {
        "sample": False,
        "provenance": build_provenance(bundle, input_hashes),
        "horizon": years,
        "policies": POLICIES,
        "central": central,
        "uncertainty": uncertainty,
        "metadata": {
            "method_limitations": METHOD_LIMITATIONS,
            "triple_lock_floor": TRIPLE_LOCK_FLOOR,
            "sources": [
                {
                    "title": "policyengine-uk triple lock construction (create_triple_lock.py, outturn.yaml)",
                    "url": "https://github.com/PolicyEngine/policyengine-uk",
                },
                {"title": "OBR Economic and fiscal outlook, March 2026", "url": FORECAST_SOURCE_URL},
                {
                    "title": "OBR Historical official forecasts database",
                    "url": "https://obr.uk/data/",
                },
                {
                    "title": "DWP benefit and pension rates 2026 to 2027",
                    "url": "https://www.gov.uk/government/news/over-12-million-pensioners-to-receive-575-state-pension-boost",
                },
            ],
        },
    }
    input_hashes[str(BENCHMARKS_CSV.relative_to(REPO))] = file_hash(BENCHMARKS_CSV)
    results["metadata"]["benchmarks"] = load_benchmarks(results)
    return results


def run_representative_paths(parameters, paths, pinned, groups, log=print):
    """Full PolicyEngine runs, final year only, on the p10/p50/p90 growth paths.

    Each path gets its own triple-lock run as the comparator. Reports the
    PolicyEngine gross and net cost of the triple lock over each alternative,
    and the approximation's error against the gross figure.
    """
    years = [FINAL_YEAR]
    pinned_final = {v: {FINAL_YEAR: by_year[FINAL_YEAR]} for v, by_year in pinned.items()}
    out = {}
    for label, path in paths.items():
        log(f"Representative path {label}")
        results, weekly = {}, {}
        for policy in POLICIES:
            rates = {int(y): r for y, r in path["uprating"][policy].items()}
            reform, levels = reform_for_rates(parameters, rates)
            weekly[policy] = round(levels["new_state_pension"][FINAL_YEAR], 2)
            results[policy] = collect(_reform_sim(reform, pinned_final), years)
        tl = results[BASELINE_POLICY]
        entry = {"full_state_pension_weekly": weekly, "cost_of_triple_lock_vs": {}, "by_decile": {}}
        for alt in ALTERNATIVES:
            t_tl, t_alt = tl["totals"][FINAL_YEAR], results[alt]["totals"][FINAL_YEAR]
            gross = t_tl["state_pension_flat_rate"] - t_alt["state_pension_flat_rate"]
            net = -(t_tl["gov_balance"] - t_alt["gov_balance"])
            approx = path["approx_cost_of_triple_lock_vs_bn"][alt]
            change = results[alt]["income"][FINAL_YEAR] - tl["income"][FINAL_YEAR]
            entry["cost_of_triple_lock_vs"][alt] = {
                "gross_bn": round(gross, 3),
                "net_bn": round(net, 3),
                "approximation_bn": round(approx, 3),
                "approximation_error_bn": round(approx - gross, 4),
                "mean_household_change_gbp": round(float(change.mean()), 2),
            }
            frame = household_frame(change, tl["income"][FINAL_YEAR], groups)
            entry["by_decile"][alt] = breakdown(frame, *BREAKDOWNS["by_decile"])
        out[label] = entry
    return out


def composition_effect(baseline_totals, uprating, costs, years=HORIZON):
    """How much the frozen-age composition drift inflates the gross costs.

    Flat-rate spending per point of the triple-lock index would be constant
    with a fixed pensioner population; here it rises as the modelled caseload
    moves from the basic to the (higher) new State Pension. Holding it at its
    first-year value gives the gross cost with the 2027-28 composition.
    """
    first = years[0]
    tl_index = cumulative_index(uprating[BASELINE_POLICY], years)
    per_point = {y: baseline_totals[y]["state_pension_flat_rate"] / tl_index[y] for y in years}
    fixed = {}
    for alt in ALTERNATIVES:
        alt_index = cumulative_index(uprating[alt], years)
        fixed[alt] = {
            str(y): round(-per_point[first] * (tl_index[y] - alt_index[y]), 2) for y in years
        }
    overstatement = {str(y): round(100 * (per_point[y] / per_point[first] - 1), 2) for y in years}
    last = str(years[-1])
    return {
        "description": "gross cost vs the triple lock (negative = saving) with flat-rate "
        f"spending per index point held at its {first}-{str(first + 1)[2:]} value, i.e. the "
        f"{first}-{str(first + 1)[2:]} pensioner composition; overstatement_pct is how much the "
        "model's drifting composition raises every gross cost in that year "
        f"(overstatement_pct: {last}-{str(int(last) + 1)[2:]}; by year in overstatement_pct_by_year)",
        "year": int(last),
        "spend_per_index_point_bn": {str(y): round(v, 3) for y, v in per_point.items()},
        "overstatement_pct": overstatement[last],
        "overstatement_pct_by_year": overstatement,
        "gross_fixed_composition": fixed,
        "gross_model": {alt: costs[alt]["gross"] for alt in ALTERNATIVES},
    }


def quarterly_growth(path=CENTRAL_FORECAST_CSV):
    """September-quarter CPI and April-June earnings growth from the EFO file."""
    import csv

    cpi, earnings = {}, {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["basis"] == "q3_yoy" and row["variable"] == "cpi":
                cpi[int(row["period"][:4])] = float(row["value"])
            elif row["basis"] == "q2_yoy" and row["variable"] == "earnings":
                earnings[int(row["period"][:4])] = float(row["value"])
    missing = [g for g in QUARTERLY_GROWTH_YEARS if g not in cpi or g not in earnings]
    if missing:
        raise KeyError(f"{path} lacks quarterly growth for {missing}")
    return cpi, earnings


def timing_sensitivity(cpi, earnings, final_spend_bn, central_final_index, years=HORIZON):
    """Final-year gross cost of the triple lock using quarterly timing proxies.

    Growth years in QUARTERLY_GROWTH_YEARS (2027-2030, where the EFO publishes
    quarters) use September-quarter CPI and April-June earnings; 2026 already
    uses the statutory inputs and later years keep the calendar-year path. Priced by the same linear scaling as the
    Monte Carlo. Not used for the headline figures.
    """
    q_cpi, q_earn = quarterly_growth()
    cpi_q = {g: (q_cpi[g] if g in QUARTERLY_GROWTH_YEARS else v) for g, v in cpi.items()}
    earn_q = {g: (q_earn[g] if g in QUARTERLY_GROWTH_YEARS else v) for g, v in earnings.items()}
    spend_per_index = final_spend_bn / central_final_index

    def final_cost(c, e):
        rates = {p: uprating_path(p, c, e, years, decimals=CENTRAL_RATE_DECIMALS) for p in POLICIES}
        index = {p: cumulative_index(r, years)[FINAL_YEAR] for p, r in rates.items()}
        cost = {
            alt: round(spend_per_index * (index[BASELINE_POLICY] - index[alt]), 2)
            for alt in ALTERNATIVES
        }
        return rates, cost

    rates, cost = final_cost(cpi_q, earn_q)
    _, calendar_cost = final_cost(cpi, earnings)
    return {
        "description": "September-quarter CPI and April-June earnings (March 2026 EFO) "
        "for growth years with quarterly data; gross cost, linear scaling",
        "growth_years_replaced": list(QUARTERLY_GROWTH_YEARS),
        "uprating": {p: {str(y): r[y] for y in years} for p, r in rates.items()},
        "cost_of_triple_lock_vs_final_year_bn": cost,
        "calendar_basis_cost_of_triple_lock_vs_final_year_bn": calendar_cost,
    }


def var_cross_check(cpi, earnings, years, final_spend_bn, central_final_index, n_draws, input_hashes):
    """Same outputs as the main Monte Carlo, from mean-calibrated VAR draws."""
    from .uncertainty import summarise_draws
    from .var_check import SERIES, history, var_draws

    for path, _ in SERIES.values():
        input_hashes[str(path.relative_to(REPO))] = file_hash(path)
    growth_years = [y - 1 for y in years]
    hist_years, data = history()
    vc, ve, info = var_draws(cpi, earnings, growth_years, data, hist_years, n_draws=n_draws)
    mc = summarise_draws(vc, ve, years, final_spend_bn, central_final_index)
    return {
        "method": (
            f"Bivariate VAR({info['lag_order']}) with intercept on annual CPI inflation (ONS D7G7) "
            "and OBR-definition average earnings growth (ONS (DTWM-ROYK)/(MGRZ-MGRQ)), "
            f"{info['sample_years'][0]}-{info['sample_years'][1]}, lag order 1-2 by AIC, OLS. "
            f"{n_draws} Gaussian simulations with the residual covariance from the observed "
            "history; 2026 fixed at the OBR central value as in the main method; each year's "
            "draws mean-shifted to the OBR central path. Costs by the same linear scaling."
        ),
        "lag_order": info["lag_order"],
        "residual_correlation": info["residual_correlation"],
        "fit": info,
        "sources": [url for _, url in SERIES.values()],
        "source_series": {k: url for k, (_, url) in SERIES.items()},
        "n_draws": mc["n_draws"],
        "cost_of_triple_lock_vs": mc["cost_of_triple_lock_vs"],
        "fan": mc["fan"],
        "prob_triple_lock_binds_on_floor": mc["prob_triple_lock_binds_on_floor"],
        "representative_paths": mc["representative_paths"],
    }
