"""Audit kept/full-new pairing and net precision from full-run aggregate caches.

This reads completed treatment batches. It never starts PolicyEngine or reads
survey files. Path indices are macro draw indices, never survey identifiers.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np


REMOVED_TREATMENT_KEYS = {"dataset", "demography", "retyped_level", "fiscal_output_years"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def estimate(values, indices, probabilities, n_draws):
    """The published stratified_estimate formula, applied to completed paths."""
    strata = {h: np.asarray([values[i] for i in draws], dtype=float)
              for h, draws in indices.items()}
    mean = sum(probabilities[h] * rows.mean() for h, rows in strata.items())
    path_variances = {h: probabilities[h] ** 2 * rows.var(ddof=1) / len(rows)
                      for h, rows in strata.items()}
    first = (sum(probabilities[h] * (rows.var(ddof=1) + (rows.mean() - mean) ** 2)
                 for h, rows in strata.items())
             + (1 - sum(probabilities.values())) * mean ** 2) / n_draws
    return {"mean": float(mean), "se": math.sqrt(sum(path_variances.values()) + first),
            "variance_path_sampling": float(sum(path_variances.values())),
            "variance_first_phase": float(first)}, path_variances


def audit(cache, specs_path, fiscal_path):
    specs = json.loads(specs_path.read_text())
    fiscal = json.loads(fiscal_path.read_text())
    paths = {"central": specs["central"],
             **{f"draw_{i}": row["spec"] for i, row in specs["paired"].items()}}
    lookup = {canonical(value): name for name, value in paths.items()}
    matched, cache_receipts = {}, []
    for path in sorted(cache.glob("treatment_paths-*.json")):
        record = json.loads(path.read_text())
        payload = {key: record[key] for key in ("kind", "arg", "engine", "packages")}
        key = hashlib.sha256(canonical(payload).encode()).hexdigest()
        if record["key"] != key or path.name != f"treatment_paths-{key[:24]}.json":
            raise ValueError("batch cache content/key mismatch")
        if record["engine"] != fiscal["provenance"]["engine_semantics"] or record["packages"] != fiscal["provenance"]["packages"]:
            raise ValueError("batch source/package provenance mismatch")
        macro = {name: {key: value for key, value in specification.items()
                        if key not in REMOVED_TREATMENT_KEYS}
                 for name, specification in record["arg"]["specs"].items()}
        if len({canonical(value) for value in macro.values()}) != 1:
            raise ValueError("treatments do not share identical macro inputs")
        name = lookup[canonical(macro["both"])]
        if name in matched:
            raise ValueError("duplicate path cache")
        for treatment, output in record["result"].items():
            specification = record["arg"]["specs"][treatment]
            if (output["calendar"] != {key: specification[key] for key in ("cpi", "earnings")}
                    or output["statutory"] != {"cpi": specification["statutory_cpi"],
                                               "earnings": specification["statutory_earnings"]}
                    or output["fixed_inputs"]["demography"] != specification["demography"]
                    or output["fixed_inputs"]["retyped_level"] != specification["retyped_level"]
                    or output["fixed_inputs"]["calculated_fiscal_years"] != list(range(2027, 2040))
                    or output["fixed_inputs"]["simulation_setup"] != "independent_pristine_path_clones"):
                raise ValueError("full-run output does not correspond to its path/treatment arguments")
        kept, upper = record["arg"]["specs"]["both"], record["arg"]["specs"]["both_full_new"]
        if {k: v for k, v in kept.items() if k != "retyped_level"} != {
                k: v for k, v in upper.items() if k != "retyped_level"}:
            raise ValueError("kept/full-new differ in more than the requested level treatment")
        left, right = (record["result"][t]["fixed_inputs"] for t in ("both", "both_full_new"))
        if any(left[field] != right[field] for field in ("population", "ageing", "state_pension_age",
                                                        "held_pension_type_records")):
            raise ValueError("kept/full-new demographics or birthday draw differ")
        matched[name] = record["result"]
        cache_receipts.append({"path": name, "cache_key": key, "aggregate_cache_sha256": digest(path)})
    if set(matched) != set(paths):
        raise ValueError("audit requires exactly central and all forty original paths")
    design = fiscal["provenance"]["paired_macro_draws"]
    indices = {int(h): draws for h, draws in design["indices_by_stratum"].items()}
    probabilities = {int(h): value for h, value in design["probability_by_stratum"].items()}
    if (len({i for draws in indices.values() for i in draws}) != 40
            or any(specs["paired"][str(i)]["stratum"] != h
                   for h, draws in indices.items() for i in draws)):
        raise ValueError("paired stratum/index design mismatch")
    summary, path_rows, contrast_variance = [], [], {}
    for year in (2034, 2039):
        for measure in ("gross", "net"):
            values = {treatment: {int(name[5:]): output[treatment]["saving_bn"][str(year)][measure]
                                  for name, output in matched.items() if name != "central"}
                      for treatment in ("both", "both_full_new")}
            contrast = {i: values["both_full_new"][i] - values["both"][i] for i in values["both"]}
            results = {treatment: estimate(v, indices, probabilities, fiscal["provenance"]["draws"]["n"])[0]
                       for treatment, v in {**values, "full_new_minus_kept": contrast}.items()}
            a, b, c = (results[treatment]["se"] for treatment in ("both", "both_full_new", "full_new_minus_kept"))
            summary.append({"year": year, "geography": "UK", "measure": measure,
                            "kept": results["both"], "full_new": results["both_full_new"],
                            "full_new_minus_kept": results["full_new_minus_kept"],
                            "estimator_correlation": (a * a + b * b - c * c) / (2 * a * b)})
            if measure == "net":
                _, variance_by_stratum = estimate(contrast, indices, probabilities,
                                                  fiscal["provenance"]["draws"]["n"])
                contrast_variance[str(year)] = {str(h): float(v) for h, v in variance_by_stratum.items()}
        for name, output in sorted(matched.items()):
            if name == "central":
                continue
            kept, upper = (output[treatment]["saving_bn"][str(year)]
                           for treatment in ("both", "both_full_new"))
            path_rows.append({"macro_path_index": int(name[5:]),
                              "stratum": specs["paired"][name[5:]]["stratum"], "year": year,
                              "kept_bn": {m: kept[m] for m in ("gross", "net")},
                              "full_new_bn": {m: upper[m] for m in ("gross", "net")},
                              "net_contrast_bn": upper["net"] - kept["net"]})
    result = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "input_files_sha256": {"data/pilot/d_macro_specs.json": digest(specs_path),
                                      "data/pilot/model_v2_e.json": digest(fiscal_path)},
              "audit_script_sha256": digest(__file__), "draw_provenance": fiscal["provenance"]["draws"],
              "checks": {"batch_count": len(matched), "paired_distinct_indices": 40,
                         "unique_full_cache_keys": len({r["cache_key"] for r in cache_receipts}),
                         "same_macro_and_statutory_inputs": True, "output_arguments_correspond": True,
                         "independent_same_path_pristine_clones": True,
                         "all_thirteen_fiscal_years_calculated": True,
                         "paired_seed_and_indices_preserved": True},
              "method": "No new fiscal simulation: audit of the original complete full-run aggregate caches. "
                        "Estimator correlation derives from the three published estimator variances, including "
                        "path-sampling and first-phase variance; it is not unweighted path Pearson correlation. "
                        "Macro sampling uses the recorded common seed. Fiscal runs have deterministic "
                        "dataset-scoped demographic draws and share identical input data and macro scenarios.",
              "cache_receipts": cache_receipts, "summary": summary,
              "net_contrast_path_variance_by_stratum": contrast_variance, "paths": path_rows}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--specs", type=Path, default=Path("data/pilot/d_macro_specs.json"))
    parser.add_argument("--fiscal", type=Path, default=Path("data/pilot/model_v2_e.json"))
    parser.add_argument("--out", type=Path, default=Path("data/pilot/full_new_net_se_audit.json"))
    args = parser.parse_args()
    args.out.write_text(json.dumps(audit(args.cache, args.specs, args.fiscal), indent=2) + "\n")


if __name__ == "__main__":
    main()
