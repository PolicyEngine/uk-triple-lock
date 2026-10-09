"""Verify historical E cold receipts and unchanged fixed-spec fiscal code.

This is source and public-input correspondence, not a new cold-run proof.
The authorized F modules change the broad source fingerprint without changing the
retained E engine execution, whose supplied macro specification is frozen.
"""

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess


F_CHANGED_MODULES = frozenset(f"src/triple_lock/{name}.py" for name in
                            ("expected_value", "pipeline", "ts_backtest", "ts_uncertainty", "history_data"))
DEPENDENCIES = frozenset(("pyproject.toml", "requirements-lock.txt", "uv.lock"))
FISCAL_INPUTS = ("data/ons_npp_2024_uk_age_sex.csv", "data/pilot/d_macro_specs.json")
MC_DRIVER = "scripts/run_model_v2_determinism.py"
EFRS_DRIVER = "scripts/run_model_v2_efrs_determinism.py"
PRIVACY_CHANGED_MODULES = frozenset(("src/triple_lock/engine.py", "src/triple_lock/disclosure.py",
                                    "src/triple_lock/pipeline.py"))
REBUILD_ENTRYPOINT_MODULES = frozenset(("src/triple_lock/ageing_validation.py",))
REBUILD_ENTRYPOINT_EDITS = (
    (b"    from . import jobs\n\n    results = jobs.run_jobs",
     b"    from .pipeline import housing_benefit_passport_preflight\n\n"
     b"    preflight = housing_benefit_passport_preflight()\n"
     b"    from . import jobs\n\n    results = jobs.run_jobs"),
    (b"    report = summarise(plan, results)\n",
     b"    report = summarise(plan, results)\n"
     b'    report.setdefault("provenance", {})["preflight"] = preflight\n'),
)
BINDING_FILE = "data/pilot/cold-source-binding.json"
PROTECTED_AST = {
    "src/triple_lock/pipeline.py": (("redact_records", "RECORD_FIELDS"), dict(imports=True, assignments=True)),
    "src/triple_lock/expected_value.py": (("draws", "rule_levels", "path_spec"),
                                           dict(imports=True, assignments=True, exclude=("UNCERTAINTY_RULINGS",))),
    "src/triple_lock/ts_backtest.py": (("switches",), {}),
    "src/triple_lock/history_data.py": ((), dict(whole_module_except=("load_forecast_errors",))),
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args):
    assigned = os.environ.get("GIT_DIR") or str(repo / (".git-e" if (repo / ".git-e").exists() else ".git"))
    return subprocess.run(["/usr/bin/git", *args], cwd=repo,
                          env={**os.environ, "GIT_DIR": assigned},
                          check=True, capture_output=True).stdout


def scientific_path(name):
    return name.startswith("src/") and name.endswith(".py") or name in DEPENDENCIES


def source_binding(bindings, source_sha256):
    """The committed file manifest is the binding; old Git heads are provenance."""
    assert source_sha256 in bindings["sources"], "historical cold source hash must match its committed file binding"
    binding = bindings["sources"][source_sha256]
    assert source_sha256 == fingerprint(binding["scientific_files_sha256"]), \
        "historical cold source hash must match its committed file binding"
    return binding


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


def module_ast(source):
    return fingerprint(ast.dump(ast.parse(source), include_attributes=False))


def privacy_normalized_source(source, edits):
    """Undo only the exact reviewed count-publication edits before fiscal checks.

    Each replacement's full new AST is pinned in the committed manifest. A
    changed helper or redactor cannot be hidden by this normalization.
    """
    tree = ast.parse(source)
    same = lambda a, b: ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
    for edit in edits:
        kind = edit["kind"]
        if kind == "module_node":
            after = ast.parse(edit["after"]).body[0]
            matches = [index for index, node in enumerate(tree.body) if same(node, after)]
            assert len(matches) == 1, "reviewed privacy helper/import changed"
            index = matches[0]
            if edit["before"] is None:
                tree.body.pop(index)
            else:
                tree.body[index] = ast.parse(edit["before"]).body[0]
        else:
            functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                         and node.name == edit["function"]]
            assert len(functions) == 1, "reviewed privacy fiscal function changed"
            before = ast.parse(edit["before"], mode="eval").body
            after = ast.parse(edit["after"], mode="eval").body
            matches = []
            for node in ast.walk(functions[0]):
                if kind == "dict_value" and isinstance(node, ast.Dict):
                    for index, key in enumerate(node.keys):
                        if isinstance(key, ast.Constant) and key.value == edit["key"]:
                            assert same(node.values[index], after), "reviewed privacy count publication changed"
                            matches.append((node.values, index))
                elif kind == "assignment_value" and isinstance(node, ast.Assign):
                    if any(ast.unparse(candidate) == edit["target"] for candidate in node.targets):
                        assert same(node.value, after), "reviewed privacy count publication changed"
                        matches.append((node, "value"))
            assert len(matches) == 1, "reviewed privacy count publication changed"
            holder, key = matches[0]
            if isinstance(holder, list):
                holder[key] = before
            else:
                setattr(holder, key, before)
    return ast.unparse(ast.fix_missing_locations(tree)).encode()


def rebuild_entrypoint_normalized_source(source):
    """Undo the two exact reviewed CLI/provenance insertions, preserving bytes.

    The restored whole-file digest must still match the original source map;
    no manifest edit can authorize different fiscal arithmetic or an altered
    preflight/provenance insertion.
    """
    for before, after in REBUILD_ENTRYPOINT_EDITS:
        assert source.count(after) == 1, "reviewed rebuild preflight/provenance insertion changed"
        source = source.replace(after, before, 1)
    return source


def verify_historical_cold_receipt(repo, public, labels):
    """Check immutable source hashes and current supplied-input execution scope."""
    repo = Path(repo)
    rows = [row for row in public["runs"] if row["label"] in labels]
    assert rows, "historical E cold rows are required"
    assert {row["label"] for row in rows} == set(labels), "both historical cold repeats are required"
    bindings = json.loads((repo / BINDING_FILE).read_text())
    historical = {}
    for row in rows:
        historical[row["source_sha256"]] = source_binding(bindings, row["source_sha256"])

    correspondence = public["final_head_scientific_source_correspondence"]
    assert correspondence["passed"]
    checked_head = correspondence["branch_head_at_check"]
    source_binding(bindings, correspondence["scientific_source_sha256"])
    executed_heads = {row["calculation_head"] for row in rows}
    assert set(correspondence["executed_calculation_heads"]) == executed_heads
    assert correspondence["matching_executed_sources"] == {row["label"]: True for row in rows}
    assert all(row["source_sha256"] == correspondence["scientific_source_sha256"] for row in rows)

    current = current_files(repo)
    # Historical AST subsets establish correspondence with the E execution;
    # they cannot authorize new executable statements in an F module. Bind
    # every byte of each separately reviewed current F module before applying
    # those historical checks, including imports and top-level expressions.
    reviewed_f_files = bindings["reviewed_current_F_files_sha256"]
    assert set(reviewed_f_files) == F_CHANGED_MODULES, \
        "reviewed current F module binding must cover every authorized module"
    for name, expected in reviewed_f_files.items():
        assert digest(current[name]) == expected, f"reviewed current F module bytes changed: {name}"
    reviewed_entrypoints = bindings.get("rebuild_entrypoint_preflight", {})
    assert set(reviewed_entrypoints) == REBUILD_ENTRYPOINT_MODULES, \
        "reviewed rebuild entrypoint binding must cover exactly the ageing CLI module"
    restored_entrypoints = {}
    for name, metadata in reviewed_entrypoints.items():
        assert set(metadata) == {"accepted_file_sha256", "scope"}, \
            "reviewed rebuild entrypoint binding metadata changed"
        assert isinstance(metadata["scope"], str) and metadata["scope"].strip(), \
            "reviewed rebuild entrypoint binding requires its exact reviewed scope"
        assert digest(current[name]) == metadata["accepted_file_sha256"], \
            f"reviewed rebuild entrypoint bytes changed: {name}"
        restored_entrypoints[name] = rebuild_entrypoint_normalized_source(current[name])
    ast_checks = {}
    byte_checks = {}
    changed = set()
    privacy_checks = {}
    entrypoint_checks = {}
    for source_sha256, old in historical.items():
        old_science = set(old["scientific_files_sha256"])
        now_science = {name for name in current if scientific_path(name)}
        assert old_science == now_science, "scientific source/dependency file set changed"
        differences = {name for name in old_science if old["scientific_files_sha256"][name] != digest(current[name])}
        assert differences <= F_CHANGED_MODULES | PRIVACY_CHANGED_MODULES | REBUILD_ENTRYPOINT_MODULES, \
            "fixed-spec fiscal source changed outside the authorized F modules, count suppression and exact rebuild CLI insertions"
        changed.update(differences)
        for name, restored in restored_entrypoints.items():
            assert digest(restored) == old["scientific_files_sha256"][name], \
                f"fixed-spec fiscal source changed outside exact rebuild CLI insertions: {name}"
            entrypoint_checks[name] = {
                **reviewed_entrypoints[name],
                "restored_historical_file_sha256": digest(restored),
                "normalization_removes_only_reviewed_preflight_provenance_insertions": True,
            }
        for name in sorted(old_science - F_CHANGED_MODULES - PRIVACY_CHANGED_MODULES - REBUILD_ENTRYPOINT_MODULES | set(FISCAL_INPUTS)):
            expected = old["scientific_files_sha256"].get(name, old["fiscal_inputs_sha256"].get(name))
            assert expected == digest(current[name]), f"fixed-spec fiscal source/input changed: {name}"
            byte_checks[name] = digest(current[name])
        normalized = {}
        for name, privacy in bindings["privacy_count_suppression"].items():
            if name not in F_CHANGED_MODULES:
                assert digest(current[name]) in (old["scientific_files_sha256"][name], privacy["accepted_file_sha256"]), \
                    f"fixed-spec fiscal source/input changed: {name}"
            if digest(current[name]) != old["scientific_files_sha256"][name]:
                normalized[name] = privacy_normalized_source(current[name], privacy["edits"])
            else:
                normalized[name] = current[name]
            if name not in F_CHANGED_MODULES:
                assert module_ast(normalized[name]) == old["module_ast_sha256"][name], \
                    f"fixed-spec fiscal source changed outside count suppression: {name}"
            privacy_checks[name] = {"accepted_file_sha256": digest(current[name]),
                                    "normalized_module_ast_sha256": module_ast(normalized[name]),
                                    "normalization_removes_only_reviewed_count_publication_edits": True}
        for name, (symbols, options) in PROTECTED_AST.items():
            expected = old["protected_ast_sha256"][name]
            actual = selected_ast(normalized.get(name, current[name]), symbols, **options)
            assert actual == expected, f"protected fiscal helper/constants changed: {name}"
            ast_checks[name] = {"symbols": list(symbols), "ast_sha256": actual, "matches": True}
            if options.get("whole_module_except"):
                ast_checks[name]["protected_scope"] = "entire module AST, including imports and assignments"
                ast_checks[name]["except_functions"] = list(options["whole_module_except"])

    # The recipes changed during E after its source freeze. Their own recorded
    # driver hashes bind the code actually executed, independently of that head.
    assert all(row["driver_sha256"] in bindings["recipes"][MC_DRIVER]["executed_sha256"] for row in rows), \
        "cold worker execution recipe provenance changed"
    assert digest(current[MC_DRIVER]) == bindings["recipes"][MC_DRIVER]["accepted_current_sha256"], \
        "cold worker recipe changed"
    if "execution_driver_sha256" in public:
        assert public["execution_driver_sha256"] in bindings["recipes"][EFRS_DRIVER]["executed_sha256"], \
            "EFRS coordinator execution recipe provenance changed"
        assert digest(current[EFRS_DRIVER]) == bindings["recipes"][EFRS_DRIVER]["accepted_current_sha256"], \
            "EFRS coordinator recipe changed"
    specification = json.loads(current["data/pilot/d_macro_specs.json"])["central"]
    for row in rows:
        full_spec = {**specification, "dataset": row["dataset"], "demography": row["treatment"]}
        assert row["full_spec_sha256"] == fingerprint(full_spec), "retained cold macro inputs changed"

    return {"passed": True,
            "scope": "historical E cold receipts and current fixed-spec fiscal source/input correspondence; no new cold run",
            "binding_file": BINDING_FILE, "binding_file_sha256": digest((repo / BINDING_FILE).read_bytes()),
            "executed_calculation_heads": sorted(executed_heads),
            "historical_source_sha256": correspondence["scientific_source_sha256"],
            "historical_correspondence_head": checked_head,
            "current_scientific_source_sha256": scientific_fingerprint(current),
            "current_broad_source_matches_historical": scientific_fingerprint(current) == correspondence["scientific_source_sha256"],
            "changed_scientific_files": sorted(changed), "authorized_F_modules": sorted(F_CHANGED_MODULES),
            "reviewed_current_F_files_sha256": reviewed_f_files,
            "unchanged_fiscal_source_input_sha256": byte_checks, "unchanged_ast": ast_checks,
            "privacy_count_suppression": privacy_checks,
            "rebuild_entrypoint_preflight": entrypoint_checks,
            "worker_recipe_sha256": digest(current[MC_DRIVER]),
            "executed_worker_recipe_sha256": sorted({row["driver_sha256"] for row in rows}),
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
    parser.add_argument("--output", type=Path, default=Path("data/pilot/historical-cold-correspondence.json"))
    args = parser.parse_args()
    repo = Path(__file__).parents[1]
    assert args.output.resolve().is_relative_to(repo), "proof must stay in the assigned workspace"
    write_public_proof(repo, args.output)
