"""Import retained model-v2 part D aggregates, never private job files.

This copies existing full-run evidence and reads public DWP benchmarks. It
does not estimate a fiscal result or load survey data. The binder attaches
the completed coverage audit and existing central national support receipts.
Independent full-run fiscal replays use an explicit £1m absolute tolerance.
"""

import argparse
import hashlib
import json
from pathlib import Path

from triple_lock import datasets, dwp
from triple_lock.pipeline import redact_records

ROOT = Path(__file__).resolve().parents[1]
D_HEAD = "498d970123adff4e8f05908e17c7b366ba71a28c"
A_HEAD = "432bb795d6eb28a3c6968de1c41a5008997e4812"
MICROCOSM_BOTH_HEAD = "30318c4f9d1a5fdba290371dc5ab56bd1f064c0a"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance(source, *, head=D_HEAD, dataset="enhanced_frs_2024_25@1.56.16"):
    data = datasets.DATASETS[dataset]
    return {
        "status": "pilot on an uncertified data/model pair; not for quoting",
        "certified": False,
        "quote_eligible": False,
        "calculation_head": head,
        "policyengine_uk": "2.120.0",
        "policyengine_core": "3.32.16",
        "dataset": dataset,
        "dataset_sha256": data["sha256"],
        "data_built_with": data["built_with"],
        "macro_inputs": "March 2026 OBR central means; original part D pilot inputs",
        "source_file": source.name,
        "source_sha256": digest(source),
        "minimum_contributing_records": 10,
        "record_redaction": "triple_lock.pipeline.redact_records, then aggregate fields only",
        "support_audit": {"status": "pending", "receipt": None,
                          "reason": "Bind the completed coverage audit and existing central national "
                                    "support receipts before publication; no per-path national audit is required"},
    }


def write(path, value):
    # Apply the same redaction rules as the main published pipeline, even
    # though the import only selects aggregate fields from retained summaries.
    path.write_text(json.dumps(redact_records(value), indent=2, allow_nan=False) + "\n")


def main(folder, out):
    summary_file = folder / "summary.json"
    summary = json.loads(summary_file.read_text())
    committed = json.loads((ROOT / "data" / "results.json").read_text())
    historical_ageing = json.loads((ROOT / "data" / "ageing_validation.json").read_text())
    micro_file = folder / "microcosm.json"
    micro = json.loads(micro_file.read_text())
    out.mkdir(parents=True, exist_ok=True)

    write(out / "version_bridge.json", {
        "provenance": provenance(summary_file),
        "comparison_provenance": {
            "2.90.2": {"calculation_head": committed["provenance"]["git_revision"],
                       "source_snapshot_head": "ee02c8d808ae117d055cb226ea260c6d0f518ac7",
                       "source": "data/results.json", "dataset": "enhanced_frs_2024_25@1.56.16"},
            "2.118.0": {"calculation_head": A_HEAD, "dataset": "enhanced_frs_2024_25@1.56.16",
                        "source": "part A retained aggregate summary"},
            "2.120.0": {"calculation_head": D_HEAD, "dataset": "enhanced_frs_2024_25@1.56.16"},
            "2.120.0_1.57.4": {"calculation_head": D_HEAD, "dataset": "enhanced_frs_2024_25@1.57.4",
                               "dataset_sha256": datasets.DATASETS["enhanced_frs_2024_25@1.57.4"]["sha256"],
                               "data_built_with": "policyengine-uk 2.93.0"},
        },
        "population_treatment": "legacy",
        "units": "Rows give £bn unless unit=m; draw numbers identify macro simulations, never survey records",
        **summary["bridge"],
    })

    write(out / "integrated.json", {
        "provenance": provenance(summary_file),
        "comparison_provenance": {
            "2.90.2_committed": {"calculation_head": committed["provenance"]["git_revision"],
                                  "policyengine_uk": "2.90.2", "source": "data/results.json"},
            "2.90.2_B": {"calculation_head": historical_ageing["calculation_head"],
                          "policyengine_uk": "2.90.2", "source": "data/ageing_validation.json"},
            "2.118.0_A": {"calculation_head": A_HEAD, "policyengine_uk": "2.118.0"},
            "2.120.0": {"calculation_head": D_HEAD, "policyengine_uk": "2.120.0"},
        },
        "sample": {"distinct_paired_macro_draws": 40,
                   "design": "The committed results' original Microcosm-paired indices, with original multiplicities "
                             "and stratum probabilities; both-minus-legacy is paired within each draw"},
        "interpretation": "Historical model-conditional pilot estimates. Original expected_* field labels are "
                          "retained for reproducibility. Max decided d955=(c): part F will pre-register the "
                          "suspended-April-2022 statutory screen before the binding post-Budget re-score, "
                          "falling back to (a) if it fails; any passing expected value is model-conditional "
                          "and presented beside the scenario envelope. This historical pilot is uncertified.",
        "standard_errors": "se_path_sampling is path SE; se includes the historical first-phase term. "
                           "These original D estimates are preserved, not regenerated by this import.",
        "rows": summary["integrated"]["table"],
    })

    # Every D model entry below is a retained full-run aggregate. Only ratios
    # and unit conversions are calculated here; no fiscal model is approximated.
    targets = dwp.coverage_targets_by_year()
    fields = (
        ("state_pension_bn", "state_pension_in_gb", 1),
        ("state_pension_recipients", "state_pension_caseload_in_gb", 1e6),
        ("pension_credit_bn", "pension_credit", 1),
        ("pension_credit_benefit_units", "pension_credit_caseload", 1e6),
        ("housing_benefit_bn", "housing_benefit", 1),
        ("housing_benefit_pension_age_bn", "housing_benefit_pension_age", 1),
        ("housing_benefit_pension_age_benefit_units", "housing_benefit_caseload_pension_age", 1e6),
    )
    comparisons = []
    for year, geographies in summary["integrated"]["coverage_both"].items():
        benchmark = targets.get(int(year))
        for field, dwp_field, divisor in fields:
            model = geographies["gb"][field] / divisor
            target = benchmark["values"][dwp_field] if benchmark else None
            comparisons.append({"year": int(year), "metric": field, "unit": "m" if divisor == 1e6 else "£bn",
                                "model_GB": model, "dwp_GB": target,
                                "model_over_dwp": model / target if target else None,
                                "benchmark_status": "available" if target else "unavailable"})
    write(out / "coverage_gb_dwp.json", {
        "provenance": provenance(summary_file),
        "population_treatment": "both",
        "dwp": {"source": dwp.TABLES_PAGE, "url": dwp.TABLES_URL,
                "file": str(dwp.TABLES.relative_to(ROOT)), "sha256": digest(dwp.TABLES),
                "matched_geography": "Great Britain; overseas State Pension spending and recipients subtracted",
                "years": dwp.TABLE_YEARS,
                "basic_new_by_country": "unavailable in this retained pilot; see the separate country evidence",
                "basic_new_GB": "unavailable: the committed type breakdown includes overseas"},
        "model": summary["integrated"]["coverage_both"],
        "comparisons": comparisons,
        "age_table_privacy": "Each nonzero age-band component was subject to the engine's ten-record rule "
                             "and complementary suppression. This is not an audit of cross-treatment differences.",
    })

    write(out / "microcosm_central.json", {
        "provenance": provenance(micro_file, dataset="populace_uk_2023"),
        "treatments": {t: {"calculation_head": D_HEAD if t == "legacy" else MICROCOSM_BOTH_HEAD,
                           "policyengine_uk": row["policyengine_uk"],
                           "saving_bn": row["saving_bn"], "totals_2039_triple_lock_bn": row["totals_2039_triple_lock_bn"]}
                       for t, row in micro.items()},
        "note": "The both central run used the zero-weight-preserving fix at 30318c4; legacy used 498d970.",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrated-pilot", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "pilot")
    args = parser.parse_args()
    main(args.integrated_pilot, args.out)
