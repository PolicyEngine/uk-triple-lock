"""Verify historical E cold receipts and unchanged fixed-spec fiscal code.

This is source and public-input correspondence, not a new cold-run proof.
The authorized F modules change the broad source fingerprint without changing the
retained E engine execution, whose supplied macro specification is frozen.
"""

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


F_CHANGED_MODULES = frozenset(f"src/triple_lock/{name}.py" for name in
                            ("expected_value", "pipeline", "ts_backtest", "ts_uncertainty", "history_data"))
DEPENDENCIES = frozenset(("pyproject.toml", "requirements-lock.txt", "uv.lock"))
FISCAL_INPUTS = ("data/ons_npp_2024_uk_age_sex.csv", "data/pilot/d_macro_specs.json")
MC_DRIVER = "scripts/run_model_v2_determinism.py"
EFRS_DRIVER = "scripts/run_model_v2_efrs_determinism.py"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args):
    return subprocess.run(["/usr/bin/git", *args], cwd=repo,
                          env={**os.environ, "GIT_DIR": str(repo / ".git-e")},
                          check=True, capture_output=True).stdout


def scientific_path(name):
    return name.startswith("src/") and name.endswith(".py") or name in DEPENDENCIES


def committed_files(repo, head):
    assert re.fullmatch(r"[0-9a-f]{40}", head), "receipt needs its actual calculation head"
    paths = git(repo, "ls-tree", "-r", "--name-only", "-z", head).decode().split("\0")
    selected = [name for name in paths if scientific_path(name) or
                name in (*FISCAL_INPUTS, MC_DRIVER, EFRS_DRIVER)]
    archive = git(repo, "archive", head, *selected)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as stream:
        return {member.name: stream.extractfile(member).read()
                for member in stream.getmembers() if member.isfile()}


def current_files(repo):
    paths = [*sorted((repo / "src").rglob("*.py")),
             *(repo / name for name in DEPENDENCIES if (repo / name).exists()),
             *(repo / name for name in (*FISCAL_INPUTS, MC_DRIVER, EFRS_DRIVER))]
    return {str(path.relative_to(repo)): path.read_bytes() for path in paths}


def scientific_fingerprint(files):
    return fingerprint({name: digest(value) for name, value in files.items() if scientific_path(name)})


def selected_ast(source, names, *, imports=False, assignments=False, exclude=(), whole_module_except=()):
    tree = ast.parse(source)
    if whole_module_except:
        omitted = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name in whole_module_except]
        assert len(omitted) == len(whole_module_except) and set(omitted) == set(whole_module_except), \
            "the single authorized CSV loader must remain present once"
        protected = ast.Module(body=[node for node in tree.body if not
                                     (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                                      node.name in whole_module_except)], type_ignores=tree.type_ignores)
        return fingerprint(ast.dump(protected, include_attributes=False))
    selected = []
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found.add(node.name)
            selected.append(ast.dump(node, include_attributes=False))
        elif imports and isinstance(node, (ast.Import, ast.ImportFrom)):
            selected.append(ast.dump(node, include_attributes=False))
        elif isinstance(node, ast.Assign):
            targets = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if targets & set(names) or assignments and not targets & set(exclude):
                found.update(targets & set(names))
                selected.append(ast.dump(node, include_attributes=False))
    assert found == set(names), "protected fiscal functions/constants must remain present"
    return fingerprint(selected)


def verify_historical_cold_receipt(repo, public, labels):
    """Check immutable source hashes and current supplied-input execution scope."""
    repo = Path(repo)
    rows = [row for row in public["runs"] if row["label"] in labels]
    assert rows, "historical E cold rows are required"
    historical = {}
    for row in rows:
        head = row.get("calculation_head", "")
        if head not in historical:
            historical[head] = committed_files(repo, head)
        assert row["source_sha256"] == scientific_fingerprint(historical[head]), \
            "historical cold source hash must match its actual calculation head"
    assert {row["label"] for row in rows} == set(labels), "both historical cold repeats are required"

    correspondence = public["final_head_scientific_source_correspondence"]
    assert correspondence["passed"]
    checked_head = correspondence["branch_head_at_check"]
    assert correspondence["scientific_source_sha256"] == scientific_fingerprint(committed_files(repo, checked_head))
    assert set(correspondence["executed_calculation_heads"]) == set(historical)
    assert correspondence["matching_executed_sources"] == {row["label"]: True for row in rows}
    assert all(row["source_sha256"] == correspondence["scientific_source_sha256"] for row in rows)

    current = current_files(repo)
    ast_checks = {}
    byte_checks = {}
    changed = set()
    protected_ast = {
        "src/triple_lock/pipeline.py": (("redact_records", "RECORD_FIELDS"), dict(imports=True, assignments=True)),
        "src/triple_lock/expected_value.py": (("draws", "rule_levels", "path_spec"),
                                               dict(imports=True, assignments=True, exclude=("UNCERTAINTY_RULINGS",))),
        "src/triple_lock/ts_backtest.py": (("switches",), {}),
        "src/triple_lock/history_data.py": ((), dict(whole_module_except=("load_forecast_errors",))),
    }
    for head, old in historical.items():
        old_science = {name for name in old if scientific_path(name)}
        now_science = {name for name in current if scientific_path(name)}
        assert old_science == now_science, "scientific source/dependency file set changed"
        differences = {name for name in old_science if old[name] != current[name]}
        assert differences <= F_CHANGED_MODULES, "fixed-spec fiscal source changed outside the authorized F modules"
        changed.update(differences)
        for name in sorted(old_science - F_CHANGED_MODULES | set(FISCAL_INPUTS)):
            assert old[name] == current[name], f"fixed-spec fiscal source/input changed: {name}"
            byte_checks[name] = digest(current[name])
        for name, (symbols, options) in protected_ast.items():
            expected = selected_ast(old[name], symbols, **options)
            actual = selected_ast(current[name], symbols, **options)
            assert actual == expected, f"protected fiscal helper/constants changed: {name}"
            ast_checks[name] = {"symbols": list(symbols), "ast_sha256": actual, "matches": True}
            if options.get("whole_module_except"):
                ast_checks[name]["protected_scope"] = "entire module AST, including imports and assignments"
                ast_checks[name]["except_functions"] = list(options["whole_module_except"])

    # The recipes changed during E after its source freeze. Their own recorded
    # driver hashes bind the code actually executed, independently of that head.
    assert all(row["driver_sha256"] == digest(current[MC_DRIVER]) for row in rows), "cold worker recipe changed"
    if "execution_driver_sha256" in public:
        assert public["execution_driver_sha256"] == digest(current[EFRS_DRIVER]), "EFRS coordinator recipe changed"
    specification = json.loads(current["data/pilot/d_macro_specs.json"])["central"]
    for row in rows:
        full_spec = {**specification, "dataset": row["dataset"], "demography": row["treatment"]}
        assert row["full_spec_sha256"] == fingerprint(full_spec), "retained cold macro inputs changed"

    return {"passed": True,
            "scope": "historical E cold receipts and current fixed-spec fiscal source/input correspondence; no F cold run",
            "executed_calculation_heads": sorted(historical),
            "historical_source_sha256": correspondence["scientific_source_sha256"],
            "historical_correspondence_head": checked_head,
            "current_scientific_source_sha256": scientific_fingerprint(current),
            "current_broad_source_matches_historical": scientific_fingerprint(current) == correspondence["scientific_source_sha256"],
            "changed_scientific_files": sorted(changed), "authorized_F_modules": sorted(F_CHANGED_MODULES),
            "unchanged_fiscal_source_input_sha256": byte_checks, "unchanged_ast": ast_checks,
            "worker_recipe_sha256": digest(current[MC_DRIVER]),
            "runs": [{key: row[key] for key in ("label", "calculation_head", "source_sha256", "full_spec_sha256")}
                     for row in rows]}


def write_public_proof(repo, output):
    receipts = (("microcosm_support_and_determinism.json", {"current_first", "current_repeat"}),
                ("efrs_determinism.json", {"central_both_first", "central_both_repeat"}))
    proofs = {}
    for filename, labels in receipts:
        path = repo / "data/pilot" / filename
        proofs[filename] = {"retained_receipt_sha256": digest(path.read_bytes()),
                            **verify_historical_cold_receipt(repo, json.loads(path.read_text()), labels)}
    value = {"checked_head": git(repo, "rev-parse", "HEAD").decode().strip(),
             "scope": "source/input checks only; retained E receipts unchanged; no PolicyEngine run",
             "receipts": proofs, "passed": all(proof["passed"] for proof in proofs.values())}
    output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    return value


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/F-E-correspondence.json"))
    args = parser.parse_args()
    repo = Path(__file__).parents[1]
    assert args.output.resolve().is_relative_to(repo), "proof must stay in the assigned workspace"
    write_public_proof(repo, args.output)
