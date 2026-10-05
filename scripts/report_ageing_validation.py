"""Render publication-approved full-model aggregate ageing results as Markdown.

Reads only the final JSON named by the caller. Never loads a model, survey,
private demographic cache or individual job result. The publication audit and
coverage-cell privacy checks must pass before any output file is written.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ("legacy", "frozen", "reweight", "types", "both")
CONTRASTS = (*MODES, "interaction", "common_input_effect")
FORECAST_YEARS = tuple(range(2027, 2040))
COVERAGE_YEARS = tuple(range(2024, 2031))
BILL_YEARS = (2024, 2026, 2027, 2028, 2029, 2030, 2034, 2039)
BREAKDOWN_YEARS = (*COVERAGE_YEARS, 2034, 2039)
CELL_FIELDS = (
    "recipients_m", "state_pension_bn", "basic_state_pension_bn",
    "new_state_pension_bn", "additional_state_pension_bn",
    "basic_recipients_m", "new_recipients_m",
)
PRIVATE_FIELDS = {
    "household_id", "household_ids", "person_id", "person_ids",
    "household_weight", "person_weight", "benunit_weight", "weights",
    "base_weights", "pinned_inputs", "private_inputs", "record_amounts",
    "largest_household", "concentration_by_year",
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Required aggregate number is missing or nonfinite")
    return value


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def year(values, value):
    if str(value) in values:
        return values[str(value)]
    if value in values:
        return values[value]
    raise ValueError("Required fiscal year is missing from approved aggregates")


def coverage_cells(report):
    for mode in MODES:
        policies = report["central_coverage"][mode]
        if set(policies) != {"triple_lock", "burnham_2030"}:
            raise ValueError("Both pension policies are required for coverage privacy validation")
        for tables in policies.values():
            for table in tables.values():
                yield table["GB"]
                for name in ("by_age", "by_country", "by_region"):
                    yield from table.get(name, {}).values()


def validate_cell(cell, minimum):
    status = cell.get("status")
    if status not in ("available", "suppressed", "withheld_family"):
        raise ValueError("Unknown coverage-cell publication status")
    if status != "available":
        if any(value is not None for key, value in cell.items() if key != "status"):
            raise ValueError("A nonavailable coverage cell still contains data")
        return
    records = cell.get("records")
    if isinstance(records, bool) or not isinstance(records, int) or records < 0:
        raise ValueError("Available coverage cell lacks an integer support count")
    values = [number(cell[field]) for field in CELL_FIELDS]
    if any(value < 0 for value in values):
        raise ValueError("Coverage spending and recipient counts cannot be negative")
    if any(value != 0 for value in values) and records < minimum:
        raise ValueError("Nonzero coverage cell has fewer than the required contributors")
    if records == 0 and any(value != 0 for value in values):
        raise ValueError("Zero-support cell contains a nonzero aggregate")


def validate_report(report):
    audit = report.get("publication_privacy_audit")
    if not isinstance(audit, dict) or audit.get("passed") is not True:
        raise ValueError("A passed publication_privacy_audit is required")
    for flag in ("person_and_household_support_checked", "field_component_and_union_support_checked"):
        if audit.get(flag) is not True:
            raise ValueError("Publication audit lacks the required support checks")
    minima = [audit.get("minimum_contributing_records"), report.get("minimum_contributing_records")]
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 10 for v in minima):
        raise ValueError("Publication requires a minimum of ten contributors")
    minimum = max(minima)
    for node in walk(report):
        if isinstance(node, dict):
            if PRIVATE_FIELDS.intersection(node):
                raise ValueError("Input contains a prohibited record-level field")
            if any(isinstance(node.get(name), list) for name in ("age", "ages", "population_records")):
                raise ValueError("Input contains an individual demographic array")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("Input contains a nonfinite number")
    if report.get("complete_paired_design") is not True:
        raise ValueError("The complete paired design is required for publication")
    if sum(len(indices) for indices in report["paired_sample"]["draws_by_stratum"].values()) != 40:
        raise ValueError("Expected the forty paired draw selections")
    if audit.get("model_version") != report["bundle"]["model_version"]:
        raise ValueError("Publication audit and model bundle versions disagree")
    for cell in coverage_cells(report):
        validate_cell(cell, minimum)
    suppression = report["suppression_policy"]
    withheld = audit.get("withheld_families", {})
    for family, flag, names in (
        ("age", "age_tables_withheld", ("by_age",)),
        ("geography", "geography_tables_withheld", ("by_country", "by_region")),
    ):
        if (not isinstance(suppression.get(flag), bool) or not isinstance(withheld.get(family), bool)
                or (withheld[family] and not suppression[flag])):
            raise ValueError("Family suppression metadata weakens the publication audit")
        for policies in report["central_coverage"].values():
            for tables in policies.values():
                for table in tables.values():
                    for name in names:
                        for cell in table.get(name, {}).values():
                            expected = "withheld_family" if suppression[flag] else "available"
                            if cell["status"] != expected:
                                raise ValueError("Coverage family does not follow its publication status")
    for sample in ("central_four_way_saving_bn", "expected_four_way_saving_bn"):
        for metric in ("gross", "net"):
            if {int(y) for y in report[sample][metric]} != set(FORECAST_YEARS):
                raise ValueError("All thirteen forecast years are required")
            for y in FORECAST_YEARS:
                for contrast in CONTRASTS:
                    value = year(report[sample][metric], y)[contrast]
                    if sample.startswith("expected"):
                        number(value["mean_bn"])
                        if number(value["se_bn"]) < 0:
                            raise ValueError("A standard error cannot be negative")
                    else:
                        number(value)
    return minimum


def text(value):
    return html.escape(str(value), quote=False).replace("|", "\\|").replace("\n", " ")


def fmt(value, digits=3):
    return f"{number(value):.{digits}f}"


def fiscal(y):
    return f"{y}–{str(y + 1)[-2:]}"


def table(headers, rows):
    return "\n".join([
        "| " + " | ".join(map(text, headers)) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(map(text, row)) + " |" for row in rows),
    ])


def saving(report, sample, metric, y, contrast):
    item = year(report[sample][metric], y)[contrast]
    return f"{fmt(item['mean_bn'])} ± {fmt(item['se_bn'])}" if sample.startswith("expected") else fmt(item)


def check_summary(report):
    errors, accounting, flags = [], [], []
    for node in walk(report["checks"]):
        if not isinstance(node, dict):
            continue
        if "max_relative_cell_error" in node:
            errors.append(number(node["max_relative_cell_error"]))
        if "eligible_components_identity_within_penny" in node:
            accounting.append(node)
        if "represented_topcoding_applied" in node:
            flags.append(node)
    if not errors or max(errors) > 1e-6:
        raise ValueError("Raking readback checks are missing or exceed tolerance")
    if not accounting or any(row.get("eligible_components_identity_within_penny") is not True
                             or row.get("unchanged_type_additional_matches_original_within_penny") is not True
                             for row in accounting):
        raise ValueError("Eligible data-year accounting checks are missing or failed")
    exceptions = {row.get("positive_reports_below_model_pension_age_records") for row in accounting}
    return errors, accounting, flags, exceptions


def render(report, input_sha256, input_name):
    minimum = validate_report(report)
    errors, accounting, flags, exceptions = check_summary(report)
    bundle, audit, worker = report["bundle"], report["publication_privacy_audit"], report["worker_execution"]
    frs_workers = worker.get("enhanced_frs_workers", worker.get("Enhanced_FRS_workers"))
    mc_workers = worker.get("microcosm_workers", worker.get("Microcosm_workers"))
    if not isinstance(frs_workers, int) or not isinstance(mc_workers, int):
        raise ValueError("Actual Enhanced FRS and Microcosm worker counts are required")
    head = report.get("calculation_head", worker.get("calculation_head", "Not supplied in approved JSON"))
    chunks = [
        "# Static ageing pilot: full-model aggregate results",
        "Generated only from the publication-approved final aggregate JSON. Values are full PolicyEngine UK "
        "outputs or the paired estimates already supplied in that JSON; the renderer performs no fiscal scaling "
        "or counterfactual estimation. See [AGEING_PILOT.md](AGEING_PILOT.md) for design and pending part C gates.",
        f"Model **{text(bundle['model_version'])}**, policyengine **{text(bundle['policyengine_version'])}**; "
        f"dataset **{text(report['dataset'])}**; calculation head **{text(head)}**. "
        f"Actual execution: **{frs_workers} Enhanced FRS workers, {mc_workers} Microcosm workers**. "
        "The paired paths all use Enhanced FRS.",
        "## Four-way saving at 2034–35 and 2039–40",
        "Nominal £bn. Expected-value entries show mean ± path-sampling SE. Interaction is "
        "`both − reweight − types + frozen`. Common input effect is `frozen − legacy`; the factorial contrasts "
        "are conditional on the shared represented inputs. On the current 2.90.2 bundle, legacy and frozen already "
        "share the integer-age pension-eligibility gate and zero additional pension below that age. Their difference "
        "therefore measures represented ages and any head/claimant changes from resolving age ties. On a newer bundle, "
        "birthday inputs can also affect eligibility, so the general contrast does not isolate age representation alone.",
    ]
    headers = ["Sample", "Year", "Saving", *MODES, "Interaction", "Common inputs"]
    chunks.append(table(headers, [
        [label, fiscal(y), metric, *(saving(report, sample, metric, y, c) for c in CONTRASTS)]
        for sample, label in (("central_four_way_saving_bn", "Central"),
                              ("expected_four_way_saving_bn", "Paired expected"))
        for y in (2034, 2039) for metric in ("gross", "net")
    ]))
    chunks.append("## Annual saving paths")
    for sample, label in (("central_four_way_saving_bn", "Central (£bn)"),
                          ("expected_four_way_saving_bn", "Paired expected (£bn, mean ± SE)")):
        for metric in ("gross", "net"):
            chunks.append(f"### {label}: {metric}")
            chunks.append(table(["Year", *MODES, "Interaction", "Common inputs"], [
                [fiscal(y), *(saving(report, sample, metric, y, c) for c in CONTRASTS)] for y in FORECAST_YEARS
            ]))
    chunks.extend(["## Central State Pension bill", "Great Britain, triple-lock rule, nominal £bn. "
                   "Additional pension includes the residual/protected-payment treatment already calculated by the model."])
    bill_rows = []
    for y in BILL_YEARS:
        for mode in MODES:
            cell = year(report["central_coverage"][mode]["triple_lock"], y)["GB"]
            if cell["status"] != "available":
                raise ValueError("GB headline coverage is unavailable after publication approval")
            bill_rows.append([fiscal(y), mode, *(fmt(cell[field]) for field in
                ("state_pension_bn", "basic_state_pension_bn", "new_state_pension_bn", "additional_state_pension_bn"))])
    chunks.append(table(["Year", "Treatment", "Total", "Basic", "New", "Additional/protected"], bill_rows))
    chunks.extend(["## Matched GB DWP coverage", "Published DWP all-type GB totals exclude its separately "
                   "reported overseas spending/caseload. Model values and differences below are copied from "
                   "`coverage_comparisons`; no overseas allocation is imputed."])
    comparisons = {(int(row["year"]), row["mode"], row["metric"]): row for row in report["coverage_comparisons"]}
    rows = []
    for y in COVERAGE_YEARS:
        for mode in MODES:
            spend, recipients = (comparisons[y, mode, metric] for metric in ("state_pension_bn", "recipients_m"))
            if any(row["status"] != "available" for row in (spend, recipients)):
                raise ValueError("Required matched GB DWP total comparison is unavailable")
            rows.append([fiscal(y), mode, *(fmt(row[field]) for row in (spend, recipients)
                         for field in ("model_GB", "benchmark_GB", "difference"))])
    chunks.append(table(["Year", "Treatment", "Model £bn", "DWP £bn", "Difference £bn",
                         "Model recipients m", "DWP recipients m", "Difference m"], rows))
    dwp = report["dwp"]
    chunks.append(f"DWP source: [{text(dwp['source'])}]({text(dwp['url'])}); workbook SHA-256 "
                  f"`{text(dwp['sha256'])}`.")
    chunks.extend(["### GB plus overseas type context", "These are published DWP context figures, "
                   "**not matched GB benchmarks**. New flat-rate spending excludes protected payments."])
    context_fields = ("basic_state_pension_bn", "new_state_pension_bn", "new_protected_payments_bn",
                      "basic_recipients_m", "new_recipients_m")
    chunks.append(table(["Year", "Basic £bn", "New flat £bn", "New protected £bn", "Basic recipients m", "New recipients m"], [
        [fiscal(y), *(fmt(year(dwp["years"], y)["GB_plus_overseas_context"][field]) for field in context_fields)]
        for y in COVERAGE_YEARS
    ]))
    chunks.append(table(["Benchmark comparison", "Status/reason"], [
        ["GB basic/new spending and recipients", "Unavailable: " + dwp["unavailable"]["GB_by_type"]],
        ["Age breakdown", "Unavailable: " + dwp["unavailable"]["by_age"]],
        ["Country/region breakdown", "Unavailable: " + dwp["unavailable"]["by_geography"]],
        ["2034–35 / 2039–40", "Unavailable: " + dwp["unavailable"]["after_2030"]],
    ]))
    chunks.append("## Combined treatment: GB age and geography coverage")
    for name, label, flag in (("by_age", "Age", "age_tables_withheld"),
                              ("by_country", "Country", "geography_tables_withheld"),
                              ("by_region", "Region", "geography_tables_withheld")):
        chunks.append(f"### {label}")
        if report["suppression_policy"][flag]:
            chunks.append("**Withheld family:** a positive small cell required suppression in linked tables. "
                          "The whole family is withheld across paths, treatments, years and policies; no raw-data fallback is used.")
            continue
        rows = []
        for y in BREAKDOWN_YEARS:
            for label_name, cell in year(report["central_coverage"]["both"]["triple_lock"], y)[name].items():
                if cell["status"] != "available":
                    raise ValueError("An approved breakdown family contains a nonavailable cell")
                rows.append([fiscal(y), label_name, *(fmt(cell[field]) for field in
                    ("recipients_m", "state_pension_bn", "basic_state_pension_bn", "new_state_pension_bn",
                     "additional_state_pension_bn", "basic_recipients_m", "new_recipients_m"))])
        chunks.append(table(["Year", label, "Recipients m", "Total £bn", "Basic £bn", "New £bn",
                             "Additional £bn", "Basic recipients m", "New recipients m"], rows))
    exception_text = ", ".join("suppressed" if count is None else str(count) for count in sorted(exceptions, key=lambda c: -1 if c is None else c))
    chunks.extend([
        "## Checks, privacy and part C gates",
        table(["Check", "Result"], [
            ["Complete paired design", "Passed; forty paired selections and five treatments"],
            ["Maximum raking readback relative error, all runs/years", f"{max(errors):.9g} ({len(errors)} checks; required ≤1e-6)"],
            ["Eligible data-year component identity to £0.01", "Passed in all supplied accounting checks"],
            ["Unchanged-type additional pension to £0.01", "Passed in all supplied accounting checks"],
            ["Below-model-pension-age positive-report exceptions", exception_text],
            ["Publication privacy audit", "Passed; person/household, component and union support checked"],
            ["Minimum nonzero contributors", minimum],
            ["Linked age family withheld", report["suppression_policy"]["age_tables_withheld"]],
            ["Linked geography family withheld", report["suppression_policy"]["geography_tables_withheld"]],
            ["Represented top-coding applied", ", ".join(map(str, sorted({row["represented_topcoding_applied"] for row in flags})))],
            ["Uncapped-age fallback", ", ".join(map(str, sorted({row["uncapped_age_fallback"] for row in flags})))],
            ["Supplied survey head flags retained", ", ".join(sorted({name for row in flags for name in row.get("pinned_survey_flags", [])})) or "None supplied"],
        ]),
        f"Calibration anchor **{text(report['calibration_year'])}** remains unverified for this pilot. "
        "The eligible-record identity passes; the all-record identity gate remains pending for below-pension-age "
        f"positive reporters ({exception_text} in the supplied build). Part C needs the certified calibration year, resolution/reporting "
        "of those exceptions through the appropriate data/model build, a State Pension/Pension Credit/Housing Benefit "
        "version bridge, and a repeat on part A's upgraded bundle. Later native calibrations, Scottish heating-payment "
        "coverage, the explicit age-80 addition and survey/overseas limitations remain as described in the design report. "
        "The publication support proof is tied to the read pension-formula hashes; part C must reread changed formulas "
        "and renew the common-positive-factor proof when moving to the upgraded bundle.",
        "## Runtime and publication provenance",
    ])
    projection_hash = report["provenance"]["engine_semantics"].get("population_projection_sha256")
    if projection_hash is None:
        projection_hash = report["provenance"]["validation_semantics"].get("ons_npp_2024_uk_age_sex.csv")
    provenance_rows = [
        ["Final approved JSON", input_name], ["Final JSON SHA-256", input_sha256],
        ["Generated at", report["generated_at"]], ["Calculation head", head],
        ["Dataset", report["dataset"]], ["Data year", report["data_year"]],
        ["Bundle id", bundle["bundle_id"]], ["Certified data build", bundle["certified_data_build_id"]],
        ["ONS projection CSV SHA-256", projection_hash],
        ["Source expected-value JSON SHA-256", report["source_results_sha256"]],
        ["Execution driver SHA-256", worker.get("execution_driver_sha256", "Not supplied")],
        ["Fiscal function SHA-256", audit.get("fiscal_function_sha256", "Not supplied")],
        ["Publication guard SHA-256", audit.get("publication_guard_sha256", "Not supplied")],
        ["Publication-audited plan SHA-256", audit.get("plan_sha256", "Not supplied")],
        ["Persistent workers", worker.get("persistent")],
        ["Maximum jobs per worker", worker.get("maximum_jobs_per_worker")],
    ]
    chunks.append(table(["Provenance", "Value"], provenance_rows))
    for title, mapping in (("Runtime engine source hashes", report["provenance"]["engine_semantics"]),
                           ("Runtime validation source hashes", report["provenance"]["validation_semantics"]),
                           ("Audited pension formula hashes", audit.get("pension_formula_sha256", {})),
                           ("Publication audit engine hashes", audit.get("audit_engine_semantics", {}))):
        chunks.append(f"### {title}")
        chunks.append(table(["Source", "Saved hash/value"], [[key, value if isinstance(value, str) else json.dumps(value, sort_keys=True)]
                                                              for key, value in sorted(mapping.items())]))
    if report.get("publication_changes_note"):
        chunks.append(text(report["publication_changes_note"]))
    chunks.append("The runtime hashes above describe the calculations. Later publication guards or default-input "
                  "enforcement can change the final branch head without changing these explicitly anchored runs; "
                  "runtime and publication provenance are retained separately.")
    return "\n\n".join(chunks) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Final publication-approved aggregate JSON")
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "docs" / "AGEING_PILOT_RESULTS.md")
    args = parser.parse_args(argv)
    raw = args.input.read_bytes()
    report = json.loads(raw)
    output = render(report, hashlib.sha256(raw).hexdigest(), args.input.name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Wrote publication-approved aggregate report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
