"""Bind retained D aggregates to completed coverage and central national receipts.

Max stopped the per-path national support audit. Existing central full runs
suffice; independent fiscal replays use a £1m absolute float tolerance.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from triple_lock.pipeline import redact_records

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "pilot"
D_HEAD = "498d970123adff4e8f05908e17c7b366ba71a28c"
MICROCOSM_BOTH_HEAD = "30318c4f9d1a5fdba290371dc5ab56bd1f064c0a"
FISCAL_ABSOLUTE_TOLERANCE_BN = 0.001  # £1m; relative tolerance is zero.
FILES = {"coverage": "d_support_audit.json", "national": "d_national_fiscal_support.json"}
FAMILIES = {
    "coverage_gb_dwp": ("coverage",), "integrated": ("national",),
    "version_bridge": ("coverage", "national"), "microcosm_central": ("national",),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def positive_counts(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from positive_counts(child)
    else:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("National support must contain nonnegative integer counts")
        if value:
            yield value


def national_run(row, path, *, label, head):
    """Select existing full-run national gross/net aggregates and their support."""
    years = list(range(2027, 2040))
    # The original full-output D recipe records support for every calculated
    # fiscal year in cells; later recipes also state the calculation years.
    calculated = row.get("calculated_fiscal_years", row.get("checks", {}).get(
        "full_fiscal_calculation_years", sorted(int(year) for year in row.get("cells", {}))))
    if row.get("passed") is not True or calculated != years:
        raise ValueError("National receipt must be a passed full thirteen-year PolicyEngine run")
    if row.get("calculation_head") != head:
        raise ValueError("National receipt does not have the retained treatment's calculation head")
    packages = row.get("packages", {})
    if packages and (packages.get("policyengine-uk") != "2.120.0" or
                     packages.get("policyengine-core") != "3.32.16"):
        raise ValueError("National receipt must use the retained pilot's pinned PolicyEngine versions")
    cells = {
        str(year): {geo: {measure: row["cells"][str(year)][geo]["saving"][measure]
                         for measure in ("gross", "net")}
                    for geo in ("uk", "gb")}
        for year in (2034, 2039)
    }
    minimum = min(positive_counts(cells), default=0)
    if minimum < 10:
        raise ValueError("National positive cell has fewer than ten contributors")
    for year, geographies in cells.items():
        for geo, measures in geographies.items():
            for measure, count in measures.items():
                aggregate = row["aggregates"]["saving_bn"][year][geo][measure]
                if not isinstance(aggregate, (int, float)) or isinstance(aggregate, bool) or not math.isfinite(aggregate):
                    raise ValueError("National aggregate must be a finite number")
                if aggregate != 0 and count < 10:
                    raise ValueError("National nonzero aggregate has fewer than ten contributors")
    return {
        "label": label, "calculation_head": head, "treatment": row["treatment"],
        "dataset": row["dataset"], "dataset_sha256": row["dataset_sha256"],
        "policyengine_uk": "2.120.0", "policyengine_core": "3.32.16",
        "passed": True, "minimum_contributing_records": 10,
        "minimum_observed_positive_cell_contributors": minimum,
        "source_receipt_sha256": digest(path), "full_spec_sha256": row["full_spec_sha256"],
        "calculated_fiscal_years": years, "fiscal_output_years": [2034, 2039], "cells": cells,
        "aggregates": {"saving_bn": {
            str(year): row["aggregates"]["saving_bn"][str(year)] for year in (2034, 2039)
        }},
    }


def create_national_receipt(efrs, microcosm_legacy, microcosm_both):
    central = json.loads(efrs.read_text())
    if central["calculation_head"] != D_HEAD:
        raise ValueError("Enhanced FRS central receipt must use D's calculation head")
    if central["driver_sha256"] != digest(ROOT / central["driver"]):
        raise ValueError("Enhanced FRS central receipt does not bind its full-output recipe")
    if central["policyengine_uk"] != "2.120.0" or central["policyengine_core"] != "3.32.16":
        raise ValueError("Enhanced FRS central receipt must use the retained pinned versions")
    runs = [national_run({**central[t], "calculation_head": central["calculation_head"]},
                         efrs, label=f"efrs_{t}", head=D_HEAD)
            for t in ("legacy", "both")]
    for path, treatment, head in ((microcosm_legacy, "legacy", D_HEAD),
                                  (microcosm_both, "both", MICROCOSM_BOTH_HEAD)):
        runs.append(national_run(json.loads(path.read_text()), path,
                                 label=f"d_{treatment}", head=head))
    return {
        "status": "passed", "complete": True, "certified": False, "quote_eligible": False,
        "minimum_contributing_records": 10,
        "minimum_observed_positive_cell_contributors": min(
            row["minimum_observed_positive_cell_contributors"] for row in runs),
        "scope": "Existing central full-run UK/GB gross and net national aggregates only. "
                 "The completed coverage audit separately checks programme coverage. Max stopped "
                 "the per-path national publication-support audit: national fiscal totals draw "
                 "on thousands of records. No completed paired-path audit is claimed.",
        "per_path_national_audit": "stopped under Max's scope ruling; unnecessary for national totals",
        "independent_full_run_comparison": {
            "absolute_tolerance_bn": FISCAL_ABSOLUTE_TOLERANCE_BN,
            "relative_tolerance": 0, "retained_numbers_changed": False,
        },
        "runs": runs,
    }


def retained_fiscal_comparison(family, evidence, national):
    """Compare available central fiscal cells with £1m tolerance, retaining D."""
    runs = {row["label"]: row for row in national["runs"]}
    cells = []

    def compare(replay, retained, **labels):
        finite = all(isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) for value in (replay, retained))
        cells.append({**labels, "within_tolerance": finite and math.isclose(
            replay, retained, rel_tol=0, abs_tol=FISCAL_ABSOLUTE_TOLERANCE_BN)})

    if family == "integrated":
        for row in evidence["rows"]:
            year, geo, measure = str(row["year"]), row["geo"], row["measure"]
            for treatment in ("legacy", "both"):
                replay = runs[f"efrs_{treatment}"]["aggregates"]["saving_bn"][year][geo][measure]
                compare(replay, row[f"central_2.120.0_{treatment}"],
                        year=row["year"], geography=geo, measure=measure, treatment=treatment)
        scope = "Central Enhanced FRS UK/GB gross and net in 2034 and 2039. Historical paired means and SEs are retained, not independently replayed."
    elif family == "version_bridge":
        for row in evidence["rows"]:
            if not row["figure"].startswith("Central path:"):
                continue
            year = 2034 if "2034-35" in row["figure"] else 2039
            measure = "gross" if "gross saving" in row["figure"] else "net"
            replay = runs["efrs_legacy"]["aggregates"]["saving_bn"][str(year)]["uk"][measure]
            compare(replay, row["2.120.0"], column="2.120.0", year=year,
                    geography="uk", measure=measure)
        scope = "Central Enhanced FRS UK gross/net on data 1.56.16 only. Newer-data, OBR and macro-draw fiscal figures are retained from D without additional replays; coverage on both data versions has its separate completed audit."
    elif family == "microcosm_central":
        for treatment, retained in evidence["treatments"].items():
            for year in (2034, 2039):
                for geo in ("uk", "gb"):
                    for measure in ("gross", "net"):
                        replay = runs[f"d_{treatment}"]["aggregates"]["saving_bn"][str(year)][geo][measure]
                        compare(replay, retained["saving_bn"][str(year)][geo][measure],
                                year=year, geography=geo, measure=measure, treatment=treatment)
        scope = "Central Microcosm UK/GB gross and net in 2034 and 2039 at each retained treatment's own head."
    else:
        raise ValueError("Unsupported fiscal evidence family")
    return {
        "comparison": "independent full runs with absolute float tolerance",
        "absolute_tolerance_bn": FISCAL_ABSOLUTE_TOLERANCE_BN, "relative_tolerance": 0,
        "all_compared_cells_within_tolerance": bool(cells) and all(row["within_tolerance"] for row in cells),
        "retained_numbers_changed": False, "numeric_differences_published": False,
        "scope": scope, "cells": cells,
    }


def completed(role, value):
    if role == "coverage":
        runs = {(row["dataset"], row["treatment"]): row for row in value["runs"]}
        expected = {("enhanced_frs_2024_25@1.56.16", "legacy"),
                    ("enhanced_frs_2024_25@1.56.16", "both"),
                    ("enhanced_frs_2024_25@1.57.4", "legacy")}
        return expected.issubset(runs) and all(runs[key]["support_audit"]["passed"] for key in expected)
    if value.get("status") != "passed" or value.get("complete") is not True:
        return False
    runs = {row["label"]: row for row in value.get("runs", [])}
    expected = {"efrs_legacy", "efrs_both", "d_legacy", "d_both"}
    return set(runs) == expected and all(
        runs[label]["passed"] and runs[label]["minimum_observed_positive_cell_contributors"] >= 10
        for label in expected)


def main(efrs, microcosm_legacy, microcosm_both):
    receipt = create_national_receipt(efrs, microcosm_legacy, microcosm_both)
    (PILOT / FILES["national"]).write_text(json.dumps(redact_records(receipt), indent=2, allow_nan=False) + "\n")
    # Apply the current redaction rules to every pilot artifact before hashes.
    for path in PILOT.glob("*.json"):
        value = json.loads(path.read_text())
        clean = redact_records(copy.deepcopy(value))
        if clean != value:
            path.write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n")
    available = {}
    for role, filename in FILES.items():
        path = PILOT / filename
        if path.exists() and completed(role, json.loads(path.read_text())):
            available[role] = {"role": role, "receipt": str(path.relative_to(ROOT)), "sha256": digest(path)}
    for family, roles in FAMILIES.items():
        path = PILOT / f"{family}.json"
        evidence = json.loads(path.read_text())
        if set(roles).issubset(available):
            audit = {"status": "passed", "family": family, "minimum_contributing_records": 10,
                     "receipts": [available[role] for role in roles],
                     "scope": "Completed archived-source coverage audit and/or existing central national "
                              "full-run support, as applicable. Per-path audits of national totals were "
                              "stopped under Max's ruling. This does not certify the model/data pair."}
            if "national" in roles:
                comparison = retained_fiscal_comparison(family, evidence, receipt)
                if not comparison["all_compared_cells_within_tolerance"]:
                    raise ValueError(f"Retained {family} central replay exceeds the £1m absolute tolerance")
                audit["retained_replay_comparison"] = comparison
        else:
            audit = {"status": "pending", "family": family,
                     "reason": "Required coverage or central national support is not yet complete",
                     "missing_receipt_roles": sorted(set(roles) - available.keys())}
        evidence["provenance"]["support_audit"] = audit
        path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
        print(f"{family}: {audit['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--efrs-central", type=Path, default=PILOT / "d_fiscal_full_central_reference.json")
    parser.add_argument("--microcosm-legacy", type=Path, default=ROOT / ".cache/microcosm-check/final-d_legacy.aggregate.json")
    parser.add_argument("--microcosm-both", type=Path, default=ROOT / ".cache/microcosm-check/final-d_both.aggregate.json")
    args = parser.parse_args()
    main(args.efrs_central, args.microcosm_legacy, args.microcosm_both)
