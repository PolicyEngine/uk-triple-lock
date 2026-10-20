"""Pin validation and aggregate comparisons for the pending binding bridge.

An endpoint is a released model bundle plus exact dataset bytes. The model
step holds the dataset fixed; the data step holds the model bundle fixed.
No PolicyEngine import or fiscal calculation is needed to validate the plan.
"""

from copy import deepcopy
import hashlib
import json


PACKAGES = ("policyengine", "policyengine-uk", "policyengine-core")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_endpoint(endpoint):
    if set(endpoint) != {"packages", "dataset"} or set(endpoint["packages"]) != set(PACKAGES):
        raise ValueError("bridge endpoints require exact bundle, UK model, core and dataset pins")
    if any(not isinstance(version, str) or not version.strip() or version != version.strip()
           for version in endpoint["packages"].values()):
        raise ValueError("bridge package pins must name released versions")
    dataset = endpoint["dataset"]
    if (set(dataset) != {"name", "sha256"} or not isinstance(dataset["name"], str)
            or not dataset["name"].startswith("enhanced_frs_2024_25@")
            or not isinstance(dataset["sha256"], str) or len(dataset["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in dataset["sha256"])):
        raise ValueError("bridge dataset pins require an Enhanced FRS release and SHA-256")


def validate_configuration(configuration):
    if configuration.get("status") != "ready":
        raise ValueError("binding bundle is pending: fill released pins and mark the bridge configuration ready")
    if configuration.get("schema_version") != 1 or set(configuration.get("steps", {})) != {"model", "data"}:
        raise ValueError("bridge configuration requires model and data steps")
    steps = configuration["steps"]
    for step in steps.values():
        if set(step) != {"from", "to"}:
            raise ValueError("bridge steps require from and to endpoints")
        for endpoint in step.values():
            validate_endpoint(endpoint)
    model, data = steps["model"], steps["data"]
    if model["from"]["dataset"] != model["to"]["dataset"]:
        raise ValueError("model bridge step must hold dataset bytes fixed")
    if model["from"]["packages"] == model["to"]["packages"]:
        raise ValueError("model bridge step must change the model bundle")
    if data["from"]["packages"] != data["to"]["packages"]:
        raise ValueError("data bridge step must hold the model bundle fixed")
    if data["from"]["dataset"] == data["to"]["dataset"]:
        raise ValueError("data bridge step must change the dataset")
    if model["to"] != data["from"]:
        raise ValueError("bridge steps must chain: data/from must equal model/to")
    baseline = configuration.get("baseline_receipt", {})
    if not isinstance(baseline.get("sha256"), str) or len(baseline["sha256"]) != 64:
        raise ValueError("bridge configuration requires the historical baseline receipt SHA-256")
    return deepcopy(configuration)


def validate_runtime(endpoint, packages, dataset):
    """Refuse declared pins that differ from installed packages or registry bytes."""
    validate_endpoint(endpoint)
    actual_packages = {name: packages.get(name) for name in PACKAGES}
    actual_dataset = {"name": dataset.get("dataset"), "sha256": dataset.get("runtime_dataset_sha256")}
    if endpoint != {"packages": actual_packages, "dataset": actual_dataset}:
        raise ValueError("bridge runtime from/to does not match its declared package and dataset pins")
    # Dataset provenance probes the installed distributions separately. Neither
    # probe may disagree about the model executing these dataset bytes.
    if any(dataset.get(key) != actual_packages[name] for key, name in (
            ("bundle_version", "policyengine"), ("model_version", "policyengine-uk"),
            ("core_version", "policyengine-core"))):
        raise ValueError("bridge dataset provenance does not match its declared model pins")


def validate_source_receipt(configuration, step, receipt, raw, design, specs_sha256):
    """Authenticate the old endpoint and require data/from to reuse model/to."""
    validate_runtime(configuration["steps"][step]["from"], receipt["provenance"]["packages"],
                     receipt["provenance"]["dataset"])
    if (receipt.get("complete") is not True or receipt.get("quote_eligible") is not False
            or receipt.get("paired_macro_design") != json.loads(json.dumps(design))
            or receipt["provenance"].get("specs_sha256") != specs_sha256
            or not receipt.get("fiscal", {}).get("central")
            or not receipt.get("fiscal", {}).get("paired") or not receipt.get("coverage", {}).get("rows")):
        raise ValueError("bridge from receipt must contain the complete frozen central, coverage and paired design")
    identity = receipt.get("bridge", {})
    if step == "data":
        if (identity.get("step") != "model" or identity.get("endpoint") != "to"
                or identity.get("configuration_sha256") != fingerprint(configuration)
                or identity.get("declared_pins") != configuration["steps"]["data"]["from"]):
            raise ValueError("data/from must reuse the model/to receipt from this bridge configuration")
    elif identity:
        if (identity.get("step") != "model" or identity.get("endpoint") != "from"
                or identity.get("configuration_sha256") != fingerprint(configuration)
                or identity.get("declared_pins") != configuration["steps"]["model"]["from"]):
            raise ValueError("model/from receipt does not match this bridge configuration")
    elif hashlib.sha256(raw).hexdigest() != configuration["baseline_receipt"]["sha256"]:
        raise ValueError("historical bridge baseline receipt differs from its committed SHA-256")


def compare(before, after):
    """Report each endpoint and their difference without inventing a paired SE.

    The historical baseline retains paired estimates, rather than individual
    draw outcomes. Its covariance with the new run is unavailable, so the
    difference of estimates has no claimed standard error.
    """
    output = {}
    for kind in ("central", "paired"):
        keys = ("geography", "year", "measure")
        old = {tuple(row[k] for k in keys): row for row in before["fiscal"][kind]}
        new = {tuple(row[k] for k in keys): row for row in after["fiscal"][kind]}
        if old.keys() != new.keys() or len(old) != len(before["fiscal"][kind]) or len(new) != len(after["fiscal"][kind]):
            raise ValueError("bridge fiscal endpoints have different or duplicate rows")
        rows = []
        for key, row in new.items():
            previous = old[key]
            available = previous["status"] == row["status"] == "available"
            field = "value_bn" if kind == "central" else "estimate_bn"
            first, last = (previous[field], row[field]) if available else (None, None)
            difference = ((last - first) if kind == "central" else (last["mean"] - first["mean"])) if available else None
            rows.append({**dict(zip(keys, key, strict=True)),
                         "status": "available" if available else "withheld_family",
                         "from": deepcopy(first), "to": deepcopy(last), "difference_bn": difference,
                         "difference_se": None})
        output[kind] = rows
    keys = ("year", "metric")
    old = {tuple(row[k] for k in keys): row for row in before["coverage"]["rows"]}
    new = {tuple(row[k] for k in keys): row for row in after["coverage"]["rows"]}
    if old.keys() != new.keys() or len(old) != len(before["coverage"]["rows"]) or len(new) != len(after["coverage"]["rows"]):
        raise ValueError("bridge coverage endpoints have different or duplicate rows")
    output["coverage"] = []
    for key, row in new.items():
        previous = old[key]
        available = previous["status"] == row["status"] == "available"
        output["coverage"].append({**dict(zip(keys, key, strict=True)), "unit": row["unit"],
            "status": "available" if available else "withheld_family",
            "from": {geo: previous[geo] if available else None for geo in ("UK", "GB")},
            "to": {geo: row[geo] if available else None for geo in ("UK", "GB")},
            "difference": {geo: row[geo] - previous[geo] if available else None for geo in ("UK", "GB")}})
    output["paired_design"] = deepcopy(after["paired_macro_design"])
    output["uncertainty_note"] = "Endpoint paired estimates retain their SEs; the difference has no estimated SE."
    return output
