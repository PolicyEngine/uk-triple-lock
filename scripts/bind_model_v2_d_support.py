"""Bind each retained D evidence family to its completed aggregate support receipts."""

import copy
import hashlib
import json
from pathlib import Path

from triple_lock.pipeline import redact_records

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "pilot"
FILES = {
    "coverage": "d_support_audit.json",
    "fiscal": "d_fiscal_support_audit.json",
    "microcosm": "microcosm_support_and_determinism.json",
}
FAMILIES = {
    "coverage_gb_dwp": ("coverage",),
    "integrated": ("fiscal",),
    "version_bridge": ("coverage", "fiscal"),
    "microcosm_central": ("microcosm",),
}


def retained_fiscal_equality(family, evidence, fiscal):
    """Compare published fiscal cells exactly; return flags, never numerical deltas."""
    pairs = {row["label"]: row for row in fiscal["pairs"]}
    extras = {row["label"]: row for row in fiscal["extra_legacy"]}
    cells = []
    if family == "integrated":
        for row in evidence["rows"]:
            year, geo, measure = str(row["year"]), row["geo"], row["measure"]
            for treatment in ("legacy", "both"):
                replay = pairs["central"][treatment]["aggregates"]["saving_bn"][year][geo][measure]
                cells.append({"year": row["year"], "geography": geo, "measure": measure,
                              "treatment": treatment,
                              "exact": replay == row[f"central_2.120.0_{treatment}"]})
        scope = "Central UK/GB gross and net in the two retained years. Historical expected-value and SE fields are not compared."
    elif family == "version_bridge":
        sources = {"2.120.0": pairs["central"]["legacy"], "2.120.0_1.57.4": extras["newer_central"]}
        for row in evidence["rows"]:
            if not row["figure"].startswith("Central path:"):
                continue
            year = 2034 if "2034-35" in row["figure"] else 2039
            measure = "gross" if "gross saving" in row["figure"] else "net"
            for column, run in sources.items():
                replay = run["aggregates"]["saving_bn"][str(year)]["uk"][measure]
                cells.append({"label": "central", "column": column, "year": year,
                              "geography": "uk", "measure": measure, "exact": replay == row[column]})
        for row in evidence["draws"]:
            index = row["draw"]
            run = pairs[f"draw_{index}"]["legacy"] if f"draw_{index}" in pairs else extras[f"bridge_draw_{index}"]
            for year in (2034, 2039):
                for measure in ("gross", "net"):
                    replay = run["aggregates"]["saving_bn"][str(year)]["uk"][measure]
                    cells.append({"macro_draw": index, "year": year, "geography": "uk", "measure": measure,
                                  "exact": replay == row[f"{measure}_{year}_2.120.0"]})
        scope = "Central UK gross/net on both data versions and the fourteen published macro-draw UK comparisons. Programme levels and components are not compared here."
    else:
        raise ValueError("Unsupported fiscal evidence family")
    return {"comparison": "exact Python scalar equality", "all_compared_cells_exact": all(row["exact"] for row in cells),
            "numeric_differences_published": False, "scope": scope, "cells": cells}


def suppress_small_bridge_component_family(evidence, fiscal):
    """Keep gross/net, withholding component rows together if a retained one is small."""
    central = next(row for row in fiscal["pairs"] if row["label"] == "central")["legacy"]
    newer = next(row for row in fiscal["extra_legacy"] if row["label"] == "newer_central")
    withheld = [row for row in central.get("withheld_component_changes", []) + newer.get("withheld_component_changes", [])
                if row["year"] == 2039 and row["geography"] == "uk"]
    if not withheld:
        return
    # Withhold all bridge component changes, including their version deltas,
    # so another displayed component plus gross/net cannot reconstruct a small
    # released component. Programme levels and gross/net are separate cells.
    figures = (
        "extra Pension Credit", "extra Housing Benefit", "extra council tax reduction",
        "income tax change", "extra Universal Credit",
    )
    for row in evidence["rows"]:
        if row["figure"].startswith("Central path 2039-40:") and any(word in row["figure"] for word in figures):
            for key in row:
                if key.startswith(("2.", "microcosm_")):
                    row[key] = None
            row["status"] = "withheld_family"
    evidence["component_privacy"] = {
        "status": "withheld_family", "minimum_contributing_records": 10,
        "reason": "At least one retained UK component change has fewer than ten contributors in the archived-source "
                  "replay. All component-change rows and version deltas are withheld to prevent subtraction.",
    }


def completed(role, value):
    if role == "coverage":
        runs = {(row["dataset"], row["treatment"]): row for row in value["runs"]}
        expected = {("enhanced_frs_2024_25@1.56.16", "legacy"),
                    ("enhanced_frs_2024_25@1.56.16", "both"),
                    ("enhanced_frs_2024_25@1.57.4", "legacy")}
        return expected.issubset(runs) and all(runs[key]["support_audit"]["passed"] for key in expected)
    if role == "fiscal":
        return value.get("status") == "passed" and value.get("complete") is True
    if value.get("complete") is not True:
        return False
    runs = {row["label"]: row for row in value.get("runs", [])}
    return {"d_legacy", "d_both"}.issubset(runs) and all(runs[label]["passed"] for label in ("d_legacy", "d_both"))


def main():
    # Archived runs import their historical pipeline. Apply the current repo's
    # redaction rules to every pilot artifact before calculating final hashes.
    for path in PILOT.glob("*.json"):
        value = json.loads(path.read_text())
        clean = redact_records(copy.deepcopy(value))
        if clean != value:
            path.write_text(json.dumps(clean, indent=2, allow_nan=False) + "\n")
    available = {}
    for role, filename in FILES.items():
        path = PILOT / filename
        if path.exists() and completed(role, json.loads(path.read_text())):
            available[role] = {"role": role, "receipt": str(path.relative_to(ROOT)),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    for family, roles in FAMILIES.items():
        path = PILOT / f"{family}.json"
        evidence = json.loads(path.read_text())
        if set(roles).issubset(available):
            audit = {"status": "passed", "family": family, "minimum_contributing_records": 10,
                     "receipts": [available[role] for role in roles],
                     "scope": "Archived-source full-model replay establishes contributor support for the retained "
                              "2.120.0 fields in this evidence family. It does not claim bit-identical replay "
                              "where the receipts disclose aggregate differences, or certify the model/data pair."}
            if family == "version_bridge":
                fiscal = json.loads((PILOT / FILES["fiscal"]).read_text())
                suppress_small_bridge_component_family(evidence, fiscal)
            if "fiscal" in roles:
                fiscal = json.loads((PILOT / FILES["fiscal"]).read_text())
                audit["retained_replay_comparison"] = retained_fiscal_equality(family, evidence, fiscal)
        else:
            audit = {"status": "pending", "family": family,
                     "reason": "Required family-specific support is not yet complete",
                     "missing_receipt_roles": sorted(set(roles) - available.keys())}
        evidence["provenance"]["support_audit"] = audit
        path.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
        print(f"{family}: {audit['status']}")


if __name__ == "__main__":
    main()
