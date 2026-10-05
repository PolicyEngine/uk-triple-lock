#!/usr/bin/env python3
"""Render the committed E fiscal aggregates without estimating or deriving values."""

import argparse
import json
import math
import re
from pathlib import Path


TREATMENTS = (
    ("frozen", "E frozen"),
    ("reweight", "E reweight"),
    ("types", "E types"),
    ("both", "E both, kept"),
    ("total", "E total only"),
    ("both_full_new", "E both, full-new bound"),
)
CONTRASTS = (
    ("retyped_level_upper_minus_kept", "Full-new bound minus kept"),
    ("total_population_effect", "Total minus frozen"),
    ("reweight_minus_ons_total", "Reweight minus ONS-total control"),
    ("reweight_effect", "Reweight minus frozen"),
    ("types_effect", "Types minus frozen"),
    ("combined_effect", "Both minus frozen"),
    ("interaction", "Interaction"),
)
YEARS = (2034, 2039)
GEOGRAPHIES = ("UK", "GB")
MEASURES = ("gross", "net")
ESTIMATE_FIELDS = ("mean", "se", "se_path_sampling", "se_first_phase")
MATCHED_CONTRASTS = (
    ("matched_population_total_effect", "Matched-total control minus frozen"),
    ("matched_age_structure_effect", "Reweight minus matched-total control"),
)


def number(value, precision=8):
    if value is None:
        return "withheld"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("fiscal cells must contain finite aggregate numbers or null")
    return f"{value:.{precision}g}"


def _index(rows, historical=False):
    result = {}
    for row in rows:
        if historical:
            key = (int(row["year"]), row["geo"].upper(), row["measure"])
        else:
            # Read old public pilot artifacts without carrying their
            # over-specific age-effect label into newly rendered tables.
            family = row["treatment_or_contrast"]
            if family == "age_structure_effect":
                family = "reweight_minus_ons_total"
            key = (family, int(row["year"]), row["geography"].upper(), row["measure"])
        if key in result:
            raise ValueError("duplicate aggregate fiscal cell")
        result[key] = row
    return result


def _family_withheld(suppression, measure):
    return bool(suppression.get("whole_family_withheld", {}).get(measure)
                or suppression.get("treatment_level_family_withheld", {}).get(measure)
                or any(family.get(measure) for family in suppression.get("contrast_family_withheld", {}).values()))


def _current_cell(rows, key, field, suppressed):
    if suppressed:
        return "withheld"
    row = rows.get(key)
    if row is None:
        return "unavailable"
    if row.get("status") != "available":
        return "withheld"
    if field == "value_bn":
        return number(row.get(field))
    return _estimate(row.get(field))


def _estimate(estimate):
    if estimate is None:
        return "withheld"
    # Print the recorded total and both components, never recalculate the SE.
    return "; ".join(number(estimate.get(field)) for field in ESTIMATE_FIELDS)


def _table(rows):
    return "\n".join([
        "| Series | Central gross | Central net | Paired gross: mean; total SE; path SE; first-phase SE | Paired net: mean; total SE; path SE; first-phase SE |",
        "| --- | ---: | ---: | --- | --- |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ])


def render(data, matched_data=None):
    """Select only public fiscal fields. No scaling, differencing or estimation."""
    fiscal = data.get("fiscal")
    if not isinstance(fiscal, dict):
        raise ValueError("completed fiscal aggregates are required; a planned pilot cannot be rendered")
    provenance = data["provenance"]
    if provenance.get("minimum_contributing_records") != 10 or fiscal.get("suppression", {}).get("minimum_records") != 10:
        raise ValueError("the ten-record disclosure rule must be recorded in the pilot")
    head = provenance["calculation_head"]
    historical = data.get("historical_part_d", {})
    historical_head = historical.get("calculation_head")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or (historical_head is not None and not re.fullmatch(r"[0-9a-f]{40}", historical_head)):
        raise ValueError("calculation commits must be full SHA-1 values")
    central = _index(fiscal.get("central", []))
    paired = _index(fiscal.get("paired", []))
    previous = _index(historical.get("rows", []), historical=True)
    suppression = fiscal["suppression"]
    matched_head, matched_central, matched_paired, matched_suppression = None, {}, {}, {}
    treatments, contrasts = TREATMENTS, CONTRASTS
    if matched_data is not None:
        proof = matched_data.get("reference_equivalence", {})
        if (proof.get("passed") is not True or proof.get("matched_runs") != 82
                or proof.get("reference_calculation_head") != head
                or matched_data.get("population_validation", {}).get("status") != "passed"):
            raise ValueError("matching all forty-one frozen/reweight reference paths is required before merging tables")
        matched_provenance, matched_fiscal = matched_data["provenance"], matched_data["fiscal"]
        matched_head = matched_provenance["calculation_head"]
        if (not re.fullmatch(r"[0-9a-f]{40}", matched_head)
                or matched_provenance.get("minimum_contributing_records") != 10
                or matched_fiscal.get("suppression", {}).get("minimum_records") != 10):
            raise ValueError("matched-total tables need a calculation commit and ten-record disclosure rule")
        matched_central = _index(matched_fiscal.get("central", []))
        matched_paired = _index(matched_fiscal.get("paired", []))
        matched_suppression = matched_fiscal["suppression"]
        treatments = (*TREATMENTS, ("total_matched", "E matched-total control"))
        contrasts = (*CONTRASTS, *MATCHED_CONTRASTS)

    def withheld(measure):
        # The supplement joins existing levels through its paired contrasts.
        return _family_withheld(suppression, measure) or _family_withheld(matched_suppression, measure)

    def fiscal_cells(family, year, geography):
        indices = ((matched_central, "value_bn"), (matched_paired, "estimate_bn")) if family in (
            "total_matched", *(key for key, _ in MATCHED_CONTRASTS)) else ((central, "value_bn"), (paired, "estimate_bn"))
        return [_current_cell(index, (family, year, geography, measure), field, withheld(measure))
                for index, field in indices for measure in MEASURES]

    lines = [
        "Pilot on an uncertified data/model pair; not for quoting. All amounts and SEs are £bn.",
        "",
        f"Part E calculation commit: `{head}`. Retained part D commit: `{historical_head or 'unavailable'}`.",
        "",
        "Central paths are scenarios. Paired estimates are model-conditional pilot aggregates; d955 presentation remains pending. "
        "Part D means and SEs are retained as recorded, without regeneration. Values below are selected from JSON; no contrasts or SEs are recalculated. "
        "`withheld` preserves suppression or null; `unavailable` denotes an absent row.",
        "Reweight minus ONS-total control changes age structure and, when their targets differ, the population total. "
        "The matched-total contrast holds the sum of the age/sex targets fixed and isolates age structure.",
    ]
    if matched_head is not None:
        lines.extend(["", f"Matched-total supplement calculation commit: `{matched_head}`. "
                      "Its independently rerun frozen/reweight paths match the E reference exactly; the matched control and its contrasts come from this separate source."])
    fixed_inputs = data.get("fixed_inputs", {})
    if matched_data is not None:
        fixed_inputs = {**fixed_inputs, "total_matched": matched_data.get("fixed_inputs", {}).get("total_matched", {})}
    if any(inputs.get("model_population_people_by_year") for inputs in fixed_inputs.values()):
        lines.extend(["", "Central-path model population totals, people", "",
                      "| Treatment | 2034–35 | 2039–40 |", "| --- | ---: | ---: |"])
        for family, label in treatments:
            population = fixed_inputs.get(family, {}).get("model_population_people_by_year", {})
            cells = [number(population[str(year)], precision=15) if str(year) in population else
                     number(population[year], precision=15) if year in population else "unavailable"
                     for year in YEARS]
            lines.append("| " + " | ".join([label, *cells]) + " |")
        lines.extend(["", "These are recorded model-read totals. Different population controls can imply different overall totals; no target is substituted here."])
    for year in YEARS:
        for geography in GEOGRAPHIES:
            title = f"{geography}, {year}–{str(year + 1)[-2:]}"
            rows = []
            prior_cells = []
            for field in ("central_2.120.0_both", "expected_2.120.0_both"):
                for measure in MEASURES:
                    prior = previous.get((year, geography, measure))
                    prior_cells.append("unavailable" if prior is None else
                                       number(prior.get(field)) if field.startswith("central_") else _estimate(prior.get(field)))
            rows.append(["D retained both", *prior_cells])
            for family, label in treatments:
                rows.append([label, *fiscal_cells(family, year, geography)])
            lines.extend(["", f"{title} — treatments", "", _table(rows), "", f"{title} — paired treatment contrasts", ""])
            rows = []
            for family, label in contrasts:
                rows.append([label, *fiscal_cells(family, year, geography)])
            lines.append(_table(rows))
    return "\n".join(lines).rstrip() + "\n"


def main(args):
    workspace = Path.cwd().resolve()
    if not args.output.resolve().is_relative_to(workspace):
        raise ValueError("rendered tables must stay in the assigned workspace")
    matched = None if args.matched_input is None else json.loads(args.matched_input.read_text())
    result = render(json.loads(args.input.read_text()), matched)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
    print(f"Wrote aggregate fiscal tables to {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/pilot/model_v2_e.json"))
    parser.add_argument("--matched-input", type=Path, help="separate full-run matched-total supplement with an exact reference proof")
    parser.add_argument("--output", type=Path, default=Path("out/E-fiscal-tables.md"))
    main(parser.parse_args())
