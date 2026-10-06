"""Replay one original fiscal path to inspect Guarantee Credit/Housing Benefit links.

The model calculates every fiscal year under both policies. Survey arrays stay
in memory; only disclosure-checked aggregates are published. Categorical checks
describe cooccurrence, not the effect of a hypothetical change to the model.
The launcher supplies HUGGING_FACE_TOKEN; this script never obtains a secret.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
import psutil


PATH_INDEX = 39769
HORIZON = list(range(2027, 2040))
DIAGNOSTIC_YEARS = (2034, 2039)
MIN_RECORDS = 10
BN = 1e9
REPLAY_TOLERANCE_BN = 0.001  # £1 million, with no relative tolerance.
SLOT_NAME = "h-item4-gc-precision0"
REGISTRY_NAME = "h-item4-gc-precision.pid.json"
MONETARY_VARIABLES = ("guarantee_credit", "housing_benefit", "pension_credit")
CAPTURE_VARIABLES = (
    *MONETARY_VARIABLES,
    "housing_benefit_pension_age_regulations_apply",
    "housing_benefit_applicable_income",
    "housing_benefit_assessable_capital",
    "housing_benefit_eligible",
    "housing_benefit_entitlement",
    "housing_benefit_pre_benefit_cap",
    "benefit_cap_reduction",
    "would_claim_housing_benefit",
    "in_receipt_of_guarantee_credit",
    "would_claim_pc",
    "minimum_guarantee",
    "pension_credit_income",
    "is_guarantee_credit_eligible",
    "is_pension_credit_eligible",
)
FORMULA_FILES = (
    "variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_applicable_income.py",
    "variables/gov/dwp/housing_benefit/housing_benefit_assessable_capital.py",
    "variables/gov/dwp/housing_benefit/entitlement/housing_benefit_entitlement.py",
    "variables/gov/dwp/housing_benefit/housing_benefit_eligible.py",
    "variables/gov/dwp/pension_credit/guarantee_credit/guarantee_credit.py",
    "variables/gov/dwp/pension_credit/guarantee_credit/in_receipt_of_guarantee_credit.py",
    "variables/gov/dwp/pension_credit/guarantee_credit/is_guarantee_credit_eligible.py",
    "variables/gov/dwp/pension_credit/pension_credit_income.py",
    "variables/gov/dwp/pension_credit/pension_credit.py",
    "variables/gov/dwp/pension_credit/pension_credit_entitlement.py",
    "variables/gov/dwp/pension_credit/would_claim.py",
)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emit(**values):
    print(json.dumps(values, sort_keys=True, allow_nan=False), flush=True)


def write_json(path, payload):
    """Atomically write aggregate-only JSON under the caller's restrictive umask."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def supported_count(count):
    return count == 0 or count >= MIN_RECORDS


def _count(mask):
    return int(np.count_nonzero(mask))


def _withheld_component():
    return {
        "status": "withheld_linked_family",
        "support_records": None,
        "support_complement_records": None,
        "triple_lock_bn": None,
        "burnham_2030_bn": None,
        "change_bn": None,
    }


def partition_aggregates(a, b, masks, include_levels=True):
    """Publish an exhaustive partition with linked support/complement checks.

    The universe is the same positive-weight benefit units under both policies.
    Any small group or complement suppresses every count in the partition. For
    each monetary variable, a small contributing support or its complement
    suppresses that variable throughout the partition, including its total.
    This prevents recovery by subtracting the other groups from the total.
    The second return value contains private aggregate cells only, never rows.
    """
    if not np.array_equal(a["weights"], b["weights"]):
        raise ValueError("policy weights differ")
    universe = np.asarray(a["weights"]) > 0
    masks = {name: np.asarray(mask, dtype=bool) & universe for name, mask in masks.items()}
    membership = sum((mask.astype(int) for mask in masks.values()), np.zeros(len(universe), dtype=int))
    if not np.array_equal(membership, universe.astype(int)):
        raise ValueError("aggregate groups must partition the positive-weight universe")
    total_records = _count(universe)
    private = {
        "records": total_records,
        "groups": {},
        "total_components": {},
    }
    for name, mask in masks.items():
        count = _count(mask)
        private["groups"][name] = {
            "records": count,
            "complement_records": total_records - count,
            "components": {},
        }
    count_family_safe = all(
        supported_count(n)
        for row in private["groups"].values()
        for n in (row["records"], row["complement_records"])
    ) and supported_count(total_records)
    variable_family_safe = {}
    for variable in MONETARY_VARIABLES:
        values = {
            "triple_lock": np.asarray(a[variable], dtype=np.float64),
            "burnham_2030": np.asarray(b[variable], dtype=np.float64),
            "change": np.asarray(b[variable], dtype=np.float64) - a[variable],
        }
        if not include_levels:
            values = {"change": values["change"]}
        if any(not np.isfinite(value).all() for value in values.values()):
            raise ValueError("nonfinite diagnostic amounts")
        total_support = {policy: _count(universe & (value != 0)) for policy, value in values.items()}
        total_complement = {policy: total_records - count for policy, count in total_support.items()}
        private["total_components"][variable] = {
            "support_records": total_support,
            "support_complement_records": total_complement,
            **{f"{policy}_bn": float(np.sum(value[universe] * a["weights"][universe]) / BN)
               for policy, value in values.items()},
        }
        safe = count_family_safe and all(
            supported_count(n) for n in (*total_support.values(), *total_complement.values())
        )
        for name, mask in masks.items():
            support = {policy: _count(mask & (value != 0)) for policy, value in values.items()}
            # Both the support outside this group and the noncontributing
            # records inside it are linked complements of a published count.
            complement = {
                policy: {
                    "outside_group": total_support[policy] - count,
                    "inside_group_noncontributors": private["groups"][name]["records"] - count,
                }
                for policy, count in support.items()
            }
            safe = safe and all(supported_count(n) for n in support.values())
            safe = safe and all(
                supported_count(n) for pair in complement.values() for n in pair.values()
            )
            private["groups"][name]["components"][variable] = {
                "support_records": support,
                "support_complement_records": complement,
                **{f"{policy}_bn": float(np.sum(value[mask] * a["weights"][mask]) / BN)
                   for policy, value in values.items()},
            }
        variable_family_safe[variable] = safe
    public = {
        "count_family_status": "available" if count_family_safe else "withheld_linked_family",
        "records": total_records if count_family_safe else None,
        "groups": {},
        "total_components": {},
    }
    for name, row in private["groups"].items():
        public["groups"][name] = {
            "records": row["records"] if count_family_safe else None,
            "complement_records": row["complement_records"] if count_family_safe else None,
            "components": {
                variable: {"status": "available", **component}
                if variable_family_safe[variable] else _withheld_component()
                for variable, component in row["components"].items()
            },
        }
    public["total_components"] = {
        variable: {"status": "available", **component}
        if variable_family_safe[variable] else _withheld_component()
        for variable, component in private["total_components"].items()
    }
    return public, private


def cooccurrence_check(mask, changed, weights):
    """A permitted presence check; withhold the numeric family when small.

    Neither the presence booleans nor this classification assert causation.
    No small count or sum is returned, even when a change is observed.
    """
    universe = np.asarray(weights) > 0
    observed = np.asarray(mask, dtype=bool) & universe
    changed = observed & np.asarray(changed, dtype=bool)
    n_observed, n_changed = _count(observed), _count(changed)
    family_safe = all(supported_count(n) for n in (
        n_observed, n_changed, n_observed - n_changed,
        _count(universe) - n_observed, _count(universe) - n_changed,
    ))
    return {
        "passport_flips_observed": bool(n_observed),
        "housing_benefit_changes_cooccur": bool(n_changed),
        "numeric_family_status": "available" if family_safe else "withheld_linked_family",
        "passport_flip_records": n_observed if family_safe else None,
        "housing_benefit_change_records": n_changed if family_safe else None,
        "interpretation": "cooccurrence only; no threshold intervention or causal estimate",
    }


def linked_partition_aggregates(a, b, masks, changing_masks):
    """Suppress linked full/subset tables together, including their differences."""
    public, private = partition_aggregates(a, b, masks)
    changing_public, changing_private = partition_aggregates(a, b, changing_masks)
    if masks.keys() != changing_masks.keys():
        raise ValueError("linked partitions must have the same group names")
    universe = a["weights"] > 0
    count_safe = public["count_family_status"] == changing_public["count_family_status"] == "available"
    variable_safe = {
        variable: public["total_components"][variable]["status"]
        == changing_public["total_components"][variable]["status"] == "available"
        for variable in MONETARY_VARIABLES
    }
    for name, mask in masks.items():
        difference = (mask ^ changing_masks[name]) & universe
        count_safe = count_safe and supported_count(_count(difference))
        for variable in MONETARY_VARIABLES:
            values = (a[variable], b[variable], b[variable] - a[variable])
            for value in values:
                support = _count(difference & (value != 0))
                complement = _count(difference) - support
                variable_safe[variable] = variable_safe[variable] and all(
                    supported_count(n) for n in (support, complement)
                )
    for table in (public, changing_public):
        if not count_safe:
            table["count_family_status"] = "withheld_linked_family"
            table["records"] = None
            for row in table["groups"].values():
                row["records"] = row["complement_records"] = None
        for variable in MONETARY_VARIABLES:
            if not count_safe or not variable_safe[variable]:
                table["total_components"][variable] = _withheld_component()
                for row in table["groups"].values():
                    row["components"][variable] = _withheld_component()
    return (public, changing_public), (private, changing_private)


def substantial_change_partition(a, b, flips, hb_changed, selected):
    """A broad change-only partition linked to the existing all-flip totals."""
    public, private = partition_aggregates(a, b, {
        "hb_changing_passport_flips_with_gc_above_ten_pounds": selected,
        "remaining_benefit_units": ~selected,
    }, include_levels=False)
    universe = a["weights"] > 0
    # The original diagnostic also reports the support on all HB-changing
    # passport flips. Protect a small remainder recoverable by subtraction.
    count_safe = supported_count(_count(flips & hb_changed & ~selected & universe))
    if not count_safe:
        public["count_family_status"] = "withheld_linked_family"
        public["records"] = None
        for row in public["groups"].values():
            row["records"] = row["complement_records"] = None
    remaining_flips = flips & ~selected & universe
    for variable in MONETARY_VARIABLES:
        changed = a[variable] != b[variable]
        support = _count(remaining_flips & changed)
        complement = _count(remaining_flips) - support
        if not count_safe or not all(supported_count(n) for n in (support, complement)):
            public["total_components"][variable] = _withheld_component()
            for row in public["groups"].values():
                row["components"][variable] = _withheld_component()
    return public, private


def diagnose_year(a, b):
    """Aggregate the two policies without retaining any record-level output."""
    if not np.array_equal(a["weights"], b["weights"]):
        raise ValueError("policy weights differ")
    flips = a["passport"] != b["passport"]
    hb_changed = a["housing_benefit"] != b["housing_benefit"]
    largest_gc = np.maximum(a["guarantee_credit"], b["guarantee_credit"])
    small_gc = flips & (largest_gc > 0) & (largest_gc <= 0.01)
    amount_masks = {
        "positive_gc_at_most_one_penny": small_gc,
        "gc_above_one_penny_at_most_ten_pounds": flips & (largest_gc > 0.01) & (largest_gc <= 10),
        "gc_above_ten_pounds": flips & (largest_gc > 10),
        "not_a_gc_passport_flip": ~flips,
    }
    actual_receipt = (
        (a["passport"] & a["in_receipt_of_guarantee_credit"].astype(bool))
        | (b["passport"] & b["in_receipt_of_guarantee_credit"].astype(bool))
    )
    would_claim = (
        (a["passport"] & a["would_claim_pc"].astype(bool))
        | (b["passport"] & b["would_claim_pc"].astype(bool))
    )
    receipt_masks = {
        "passport_flip_with_actual_gc_receipt": flips & actual_receipt,
        "passport_flip_entitlement_only_nonclaimant": flips & ~actual_receipt & ~would_claim,
        "passport_flip_other_without_actual_gc_receipt": flips & ~actual_receipt & would_claim,
        "not_a_gc_passport_flip": ~flips,
    }
    def changing_partition(masks):
        changed = {name: mask & hb_changed for name, mask in masks.items() if name != "not_a_gc_passport_flip"}
        changed["not_a_gc_passport_flip"] = ~(flips & hb_changed)
        return changed

    (amount_public, amount_changing_public), (amount_private, amount_changing_private) = linked_partition_aggregates(
        a, b, amount_masks, changing_partition(amount_masks)
    )
    (receipt_public, receipt_changing_public), (receipt_private, receipt_changing_private) = linked_partition_aggregates(
        a, b, receipt_masks, changing_partition(receipt_masks)
    )
    substantial_changed = flips & hb_changed & (largest_gc > 10)
    substantial_public, substantial_private = substantial_change_partition(
        a, b, flips, hb_changed, substantial_changed
    )
    checks = {
        "at_most_one_penny_gc_passport_flips": cooccurrence_check(small_gc, hb_changed, a["weights"]),
        "entitlement_only_nonclaimant_gc_passport_flips": cooccurrence_check(
            receipt_masks["passport_flip_entitlement_only_nonclaimant"], hb_changed, a["weights"]
        ),
    }
    receipt_formula_matches = all(
        np.array_equal(
            side["in_receipt_of_guarantee_credit"].astype(bool),
            side["is_pension_credit_eligible"].astype(bool)
            & side["would_claim_pc"].astype(bool)
            & (side["guarantee_credit"] > 0),
        )
        for side in (a, b)
    )
    public = {
        "gc_passport_flip_amount_bands": amount_public,
        "gc_passport_flip_hb_changing_subset_amount_bands": amount_changing_public,
        "gc_passport_flip_receipt_attribution": receipt_public,
        "gc_passport_flip_hb_changing_subset_receipt_attribution": receipt_changing_public,
        "substantial_gc_hb_changing_passport_flip_changes": substantial_public,
        "categorical_cooccurrence_checks": checks,
        "in_receipt_variable_matches_eligible_claimant_with_positive_gc": bool(receipt_formula_matches),
        "guarantee_credit_reconstruction_matches_within_one_penny": all(
            side["gc_reconstruction_matches"] for side in (a, b)
        ),
    }
    private = {
        "amount_bands": amount_private,
        "hb_changing_subset_amount_bands": amount_changing_private,
        "receipt_attribution": receipt_private,
        "hb_changing_subset_receipt_attribution": receipt_changing_private,
        "substantial_gc_hb_changing_passport_flip_changes": substantial_private,
    }
    return public, private


def saving_replay_summary(expected, actual, supports, positive_household_records):
    """Gate endpoint monetary comparisons on their actual household supports."""
    if any(abs(actual[measure] - expected[measure]) > REPLAY_TOLERANCE_BN for measure in ("gross", "net")):
        raise RuntimeError("original endpoint does not replay within £1 million")
    complements = {measure: positive_household_records - supports[measure] for measure in ("gross", "net")}
    if any(count < 0 for count in complements.values()):
        raise RuntimeError("saving support exceeds the positive-weight household population")
    safe = all(supported_count(count) for count in (*supports.values(), *complements.values()))
    return {
        "numeric_family_status": "available" if safe else "withheld_linked_family",
        "replay_within_absolute_tolerance": True,
        **{
            measure: {
                "support_records": supports[measure] if safe else None,
                "support_complement_records": complements[measure] if safe else None,
                "cached_bn": expected[measure] if safe else None,
                "replay_bn": actual[measure] if safe else None,
                "difference_bn": actual[measure] - expected[measure] if safe else None,
            }
            for measure in ("gross", "net")
        },
    }


def resource_snapshot(root, stage):
    """Read host RAM/CPU immediately before imports, dataset load and path run."""
    vm_stat = subprocess.check_output(["vm_stat"], text=True)
    match = re.search(r"page size of (\d+) bytes", vm_stat)
    if match is None:
        raise RuntimeError("vm_stat page size unavailable")
    page_size = int(match[1])
    pages = {}
    for name in ("Pages free", "Pages inactive", "Pages speculative"):
        match = re.search(rf"{name}:\s*(\d+)", vm_stat)
        if match is None:
            raise RuntimeError("vm_stat available-page count unavailable")
        pages[name] = int(match[1])
    snapshot = {
        "at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "cpu_count": os.cpu_count(),
        "load": list(os.getloadavg()),
        "available_gib": psutil.virtual_memory().available / 2**30,
        "vm_stat_available_gib": sum(pages.values()) * page_size / 2**30,
        "maximum_own_workers": 1,
        "maximum_workspace_diagnostic_workers": 2,
    }
    diagnostic_workers = 0
    own_workers = 0
    for process in psutil.process_iter():
        try:
            if Path(process.cwd()).resolve() != root:
                continue
            command = process.cmdline()
            if "--execute" in command and any(
                Path(argument).name.startswith("diagnose_model_v2_") for argument in command
            ):
                diagnostic_workers += 1
                if any(Path(argument).name == "diagnose_model_v2_gc_precision.py" for argument in command):
                    own_workers += 1
        except (psutil.AccessDenied, psutil.NoSuchProcess, FileNotFoundError):
            continue
    snapshot["workspace_diagnostic_workers"] = diagnostic_workers
    snapshot["own_workers"] = own_workers
    if min(snapshot["available_gib"], snapshot["vm_stat_available_gib"]) < 40:
        raise RuntimeError("less than 40 GiB available RAM")
    if diagnostic_workers > 2:
        raise RuntimeError("more than two workspace diagnostic workers")
    if own_workers > 1:
        raise RuntimeError("more than one precision diagnostic worker")
    emit(status="resource admission passed", **snapshot)
    return snapshot


def original_cache_record(cache, macro_spec):
    matches = []
    for path in cache.glob("treatment_paths-*.json"):
        record = json.loads(path.read_text())
        specification = record["arg"]["specs"]["both"]
        macro = {
            key: value for key, value in specification.items()
            if key not in ("dataset", "demography", "retyped_level", "fiscal_output_years")
        }
        if macro == macro_spec:
            matches.append((path, record))
    if len(matches) != 1:
        raise RuntimeError("target macro path must have exactly one original cache record")
    return matches[0]


def capture_policy(simulation, fiscal_totals):
    table = {}
    for year in DIAGNOSTIC_YEARS:
        values = {
            variable: np.asarray(simulation.calculate(variable, year).to_numpy(), dtype=np.float64).copy()
            for variable in CAPTURE_VARIABLES
        }
        values["weights"] = np.asarray(
            simulation.calculate("housing_benefit", year).weights.to_numpy(), dtype=np.float64
        ).copy()
        # An aggregate count alone is retained for the separate household
        # fiscal replay gate. The household weights themselves stay transient.
        values["positive_household_records"] = _count(np.asarray(
            simulation.calculate("household_net_income", year).weights.to_numpy()
        ) > 0)
        values["passport"] = values["housing_benefit_pension_age_regulations_apply"].astype(bool) & (
            values["guarantee_credit"] > 0
        )
        expected_gc = (
            np.maximum(0, values["minimum_guarantee"] - values["pension_credit_income"])
            * values["is_guarantee_credit_eligible"].astype(bool)
            * values["is_pension_credit_eligible"].astype(bool)
        )
        values["gc_reconstruction_matches"] = bool(np.allclose(
            values["guarantee_credit"], expected_gc, rtol=0, atol=0.01
        ))
        hb_total = float(np.sum(values["housing_benefit"] * values["weights"]) / BN)
        if abs(hb_total - fiscal_totals[year]["variables"]["housing_benefit"]) > 1e-6:
            raise RuntimeError("diagnostic Housing Benefit sum differs from full fiscal total")
        table[year] = values
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--specs", default=Path("data/pilot/d_macro_specs.json"), type=Path)
    parser.add_argument("--fiscal", default=Path("data/pilot/model_v2_e.json"), type=Path)
    parser.add_argument("--out", default=Path("data/pilot/gc_precision_diagnostic.json"), type=Path)
    parser.add_argument("--treatment", choices=("both", "both_full_new"), default="both")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        emit(
            status="planned; no model run",
            path_index=PATH_INDEX,
            treatment=args.treatment,
            retyped_level="kept" if args.treatment == "both" else "full_new",
            full_path_count=1,
            fiscal_years=HORIZON,
            diagnostic_years=list(DIAGNOSTIC_YEARS),
            maximum_own_workers=1,
            slot=SLOT_NAME,
            registry=f".cache/{REGISTRY_NAME}",
            output=str(args.out),
            suggested_launcher_log=".cache/h-item4-gc-precision.log",
        )
        return
    root = Path.cwd().resolve()
    source = args.source.resolve()
    cache = (args.cache or source / ".cache/jobs-pilot-e").resolve()
    public = args.out.resolve()
    for path in (source, cache, public, args.specs.resolve(), args.fiscal.resolve()):
        if not path.is_relative_to(root):
            raise ValueError("every input and output must be inside this workspace")
    if public.exists():
        raise RuntimeError("a completed diagnostic output already exists")
    if not os.environ.get("HUGGING_FACE_TOKEN"):
        raise RuntimeError("launcher must supply HUGGING_FACE_TOKEN")
    os.umask(0o077)
    admissions = [resource_snapshot(root, "before model imports")]
    sys.path.insert(0, str(source / "src"))
    from triple_lock import engine, jobs, model_horizon

    if not Path(engine.__file__).resolve().is_relative_to(source):
        raise RuntimeError("engine was imported from a different source tree")
    if list(engine.HORIZON) != HORIZON or list(engine.POLICIES) != ["triple_lock", "burnham_2030"]:
        raise RuntimeError("unexpected model horizon or policies")
    macro_spec = json.loads(args.specs.read_text())["paired"][str(PATH_INDEX)]["spec"]
    cache_file, record = original_cache_record(cache, macro_spec)
    cache_record_hash = file_sha256(cache_file)
    if engine.engine_semantics() != record["engine"] or engine.package_versions() != record["packages"]:
        raise RuntimeError("original source semantics or package versions differ")
    if engine.job_key(record["kind"], record["arg"], record["engine"], record["packages"]) != record["key"]:
        raise RuntimeError("original cache key does not match its arguments")
    arguments = engine._keys_to_int(record["arg"])
    specification = arguments["specs"][args.treatment]
    retyped_level = "kept" if args.treatment == "both" else "full_new"
    if specification.get("demography") != "both" or specification.get("retyped_level") != retyped_level:
        raise RuntimeError("original treatment is not the required path")
    if not specification["dataset"].startswith("enhanced_frs_"):
        raise RuntimeError("the original path must use Enhanced FRS")
    recipe_hash = file_sha256(__file__)
    source_hashes = engine.engine_hashes()
    package_root = Path(importlib.util.find_spec("policyengine_uk").origin).parent
    formula_hashes = {name: file_sha256(package_root / name) for name in FORMULA_FILES}
    input_hashes = {
        str(path.resolve().relative_to(root)): file_sha256(path)
        for path in (args.specs, args.fiscal)
    }
    original_managed, original_totals = engine._managed, engine.totals
    captured = []
    registry = root / ".cache" / REGISTRY_NAME
    private_file = root / ".cache" / "h-item4-gc-precision-aggregate-only.json"

    def guarded_managed(*positional, **keywords):
        admissions.append(resource_snapshot(root, "immediate dataset load"))
        return original_managed(*positional, **keywords)

    def captured_totals(simulation, years):
        if list(years) != HORIZON:
            raise RuntimeError("the full fiscal horizon must be calculated")
        fiscal_totals = {}
        for year in years:
            fiscal_totals.update(original_totals(simulation, [year]))
            emit(status="fiscal totals completed", year=year, policy_position=len(captured))
        captured.append(capture_policy(simulation, fiscal_totals))
        return fiscal_totals

    engine._managed, engine.totals = guarded_managed, captured_totals
    try:
        with model_horizon.installed(), jobs.slot_lock(root / ".cache/workers" / SLOT_NAME, timeout=0):
            write_json(registry, {
                "pid": os.getpid(), "status": "admitted", "audit_script_sha256": recipe_hash,
                "path_index": PATH_INDEX, "treatment": args.treatment,
                "maximum_own_workers": 1, "admissions": admissions,
            })
            template = engine._prepare_path_template(specification)
            admissions.append(resource_snapshot(root, "immediate full 13-year path"))
            emit(status="starting full path", path_index=PATH_INDEX, treatment=args.treatment)
            result = engine.run_path(specification, _template=template)
    finally:
        engine._managed, engine.totals = original_managed, original_totals
    if len(captured) != 2:
        raise RuntimeError("one original path must calculate exactly two independent policies")
    replay = {}
    diagnostics, private = {}, {}
    for year in DIAGNOSTIC_YEARS:
        expected = record["result"][args.treatment]["saving_bn"][str(year)]
        actual = result["saving_bn"][year]
        if captured[0][year]["positive_household_records"] != captured[1][year]["positive_household_records"]:
            raise RuntimeError("positive-weight household population differs between policies")
        replay[str(year)] = saving_replay_summary(
            expected, actual, result["saving_support_records_by_year"][year]["uk"],
            captured[0][year]["positive_household_records"],
        )
        diagnostics[str(year)], private[str(year)] = diagnose_year(captured[0][year], captured[1][year])
    captured.clear()
    del result, template
    if engine.engine_hashes() != source_hashes or engine.engine_semantics() != record["engine"]:
        raise RuntimeError("source changed during the run")
    if engine.package_versions() != record["packages"] or file_sha256(__file__) != recipe_hash:
        raise RuntimeError("packages or diagnostic recipe changed during the run")
    if any(file_sha256(package_root / name) != digest for name, digest in formula_hashes.items()):
        raise RuntimeError("PolicyEngine formula source changed during the run")
    if any(file_sha256(root / name) != digest for name, digest in input_hashes.items()):
        raise RuntimeError("a public input changed during the run")
    if file_sha256(cache_file) != cache_record_hash:
        raise RuntimeError("the original cache record changed during the run")
    write_json(private_file, {
        "status": "private aggregate cells only; no survey rows, identifiers, weights or individual amounts",
        "path_index": PATH_INDEX, "treatment": args.treatment, "audit_script_sha256": recipe_hash,
        "aggregates": private,
    })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "one full original PolicyEngine UK path; disclosure-checked aggregates only",
        "path_index": PATH_INDEX, "treatment": args.treatment, "retyped_level": retyped_level,
        "full_path_count": 1, "fiscal_years_calculated": HORIZON,
        "audit_script_sha256": recipe_hash, "source_files_sha256": source_hashes,
        "input_files_sha256": input_hashes, "policyengine_formula_source_sha256": formula_hashes,
        "original_cache_record_sha256": cache_record_hash,
        "original_batch_cache_key": record["key"],
        "specification_sha256": hashlib.sha256(engine._canonical(record["arg"]["specs"][args.treatment]).encode()).hexdigest(),
        "engine_semantics": record["engine"], "packages": record["packages"],
        "source_head_provenance": json.loads(args.fiscal.read_text())["provenance"]["calculation_head"],
        "minimum_records": MIN_RECORDS, "replay_absolute_tolerance_bn": REPLAY_TOLERANCE_BN,
        "admissions": admissions, "saving_replay": replay, "diagnostics": diagnostics,
        "method": (
            "One fresh pristine same-macro Enhanced FRS setup, independent deep policy clones, "
            "original integer-key arguments and all thirteen fiscal years in their original order. "
            "The Housing Benefit formulas use pension-age regulations and positive Guarantee Credit "
            "entitlement; the separately captured receipt variable also requires Pension Credit eligibility "
            "and would_claim_pc. Amount and receipt partitions attribute observed Housing Benefit changes, "
            "without a counterfactual intervention. Every published monetary cell and support/complement "
            "count has zero or at least ten contributors. Any small linked cell withholds that whole "
            "partition's count family or monetary-variable family, including totals. Full flip groups "
            "and their Housing Benefit changing subsets are suppressed together if either table or "
            "their difference has a small support. Presence checks "
            "may report cooccurrence while their numeric family is withheld. Survey arrays remain "
            "transient and no record identifier, weight or individual amount is written."
        ),
    }
    write_json(public, payload)
    write_json(registry, {
        "pid": os.getpid(), "status": "completed", "audit_script_sha256": recipe_hash,
        "path_index": PATH_INDEX, "receipt_sha256": file_sha256(public), "admissions": admissions,
    })
    emit(status="diagnostic completed", receipt=str(public.relative_to(root)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exception:
        emit(status="diagnostic stopped; private inputs withheld", error_type=type(exception).__name__)
        raise SystemExit(1) from None
