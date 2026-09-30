"""The job cache key: what the engine's code computes, not how its prose reads (no PolicyEngine needed).

* Invariance: comments, docstrings, bare strings and layout never move ``engine.source_semantics``, on the real
  engine files with random edits.
* Sensitivity: changing any value, name or operator in the code does, and so does any dependency in pyproject.toml.
* The results file's provenance (``engine_hashes``, raw bytes) still moves on any edit.
* The key covers every module a job imports, and none of them reads a docstring at run time.
"""

import ast
import io
import shutil
import tokenize
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from triple_lock import engine
from triple_lock.config import REPO

SRC = REPO / "src" / "triple_lock"
FILES = engine.ENGINE_FILES
prose = st.text(st.characters(min_codepoint=32, max_codepoint=126), max_size=40)


def comment_rows(text):
    """Rows where a comment can be appended or a comment line inserted after: those ending a physical line of code
    outside any string (so not inside a multi-line string, and not continued with a backslash)."""
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return sorted({t.start[0] for t in tokens if t.type in (tokenize.NEWLINE, tokenize.NL)})


def add_comments(text, picks, words):
    """Append a comment to a row that can take one, and insert a comment line after it, once per pick."""
    for pick, word in zip(picks, words):
        lines = text.splitlines()
        rows = [r for r in comment_rows(text) if r <= len(lines)]
        row = rows[pick % len(rows)] - 1
        lines[row] += f"  # {word}"
        lines.insert(row + 1, f"# {word}")
        text = "\n".join(lines) + "\n"
    return text


class Redoc(ast.NodeTransformer):
    """Replace every bare string statement (docstrings included) with new text."""

    def __init__(self, words):
        self.words, self.i = words, 0

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            self.i += 1
            return ast.Expr(ast.Constant(self.words[self.i % len(self.words)]))
        return self.generic_visit(node)


def semantics_of(text, tmp_path, name="m.py"):
    path = tmp_path / name
    path.write_text(text)
    return engine.source_semantics(path)


@pytest.mark.parametrize("name", FILES)
def test_layout_does_not_move_the_key(name, tmp_path):
    """The file rewritten from its syntax tree (new layout, no comments) has the same semantics."""
    text = (SRC / name).read_text()
    assert semantics_of(ast.unparse(ast.parse(text)), tmp_path) == engine.source_semantics(SRC / name)


@settings(max_examples=60, deadline=None)
@given(st.sampled_from(FILES), st.lists(st.integers(0, 10_000), min_size=1, max_size=8),
       st.lists(prose, min_size=8, max_size=8), st.lists(prose, min_size=1, max_size=5))
def test_prose_edits_keep_the_key_and_move_the_provenance(name, picks, words, docs):
    """Random comments added anywhere and every docstring rewritten: the job key's semantics stay, the raw hash the
    results file records moves (so the committed results still go stale and must be rebuilt, from the cache)."""
    import tempfile

    text = (SRC / name).read_text()
    edited = add_comments(text, picks, words)
    tree = Redoc(docs).visit(ast.parse(edited))
    redoc = ast.unparse(tree)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        original = engine.source_semantics(SRC / name)
        assert semantics_of(edited, d, "a.py") == original
        assert semantics_of(redoc, d, "b.py") == original
        assert engine.file_hash(d / "a.py") != engine.file_hash(SRC / name)


class Mutate(ast.NodeTransformer):
    """Change the k-th constant that is not a bare string statement to ``value``."""

    def __init__(self, k, value):
        self.k, self.value, self.seen, self.old = k, value, 0, None

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node  # docstrings are prose
        return self.generic_visit(node)

    def visit_JoinedStr(self, node):
        return node  # an f-string's literal parts must stay strings to unparse

    def visit_Constant(self, node):
        if self.seen == self.k:
            self.old = node.value
            node = ast.copy_location(ast.Constant(self.value), node)
        self.seen += 1
        return node


def code_constants(tree):
    m = Mutate(-1, None)
    m.visit(tree)
    return m.seen


@settings(max_examples=150, deadline=None)
@given(name=st.sampled_from(FILES), k=st.integers(0, 10_000),
       value=st.one_of(st.integers(-10**6, 10**6), st.floats(allow_nan=False, allow_infinity=False), prose,
                       st.booleans()))
def test_any_change_to_a_value_moves_the_key(name, k, value, tmp_path_factory):
    """Change one constant in the code (a number, a parameter path, a label) to anything else: the key moves."""
    tree = ast.parse((SRC / name).read_text())
    n = code_constants(tree)
    m = Mutate(k % n, value)
    mutated = m.visit(tree)
    if type(m.old) is type(value) and repr(m.old) == repr(value):
        return  # no change
    d = tmp_path_factory.mktemp("mutated")
    assert semantics_of(ast.unparse(mutated), d) != engine.source_semantics(SRC / name)


@settings(max_examples=60, deadline=None)
@given(name=st.sampled_from(FILES), k=st.integers(0, 10_000))
def test_renaming_or_changing_an_operator_moves_the_key(name, k, tmp_path_factory):
    tree = ast.parse((SRC / name).read_text())
    names = [n for n in ast.walk(tree) if isinstance(n, ast.Name)]
    names[k % len(names)].id += "_renamed"
    d = tmp_path_factory.mktemp("renamed")
    assert semantics_of(ast.unparse(tree), d) != engine.source_semantics(SRC / name)
    tree = ast.parse((SRC / name).read_text())
    ops = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)]
    if ops:
        op = ops[k % len(ops)]
        op.op = ast.Sub() if not isinstance(op.op, ast.Sub) else ast.Add()
        assert semantics_of(ast.unparse(tree), d, "op.py") != engine.source_semantics(SRC / name)


def copy_engine(tmp_path):
    root = tmp_path / "triple_lock"
    root.mkdir()
    for name in FILES:
        shutil.copy(SRC / name, root / name)
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    return root, tmp_path / "pyproject.toml"


def test_the_job_key_survives_prose_edits_and_moves_on_code_edits(tmp_path):
    root, pyproject = copy_engine(tmp_path)
    semantics, raw = engine.engine_semantics(root, pyproject), engine.engine_hashes(root, pyproject)
    assert semantics == engine.engine_semantics() and raw == engine.engine_hashes()
    key = engine.job_key("path", {"x": 1}, semantics, {"p": "1"})

    rules = root / "rules.py"
    rules.write_text(rules.read_text().replace('"""The two uprating rules', '"""The two uprating rules, reworded', 1)
                     + "\n# a comment\n")
    pyproject.write_text(pyproject.read_text() + "\n# a comment\n")
    assert engine.job_key("path", {"x": 1}, engine.engine_semantics(root, pyproject), {"p": "1"}) == key
    moved = {k for k, v in engine.engine_hashes(root, pyproject).items() if v != raw[k]}
    assert moved == {"rules.py", "pyproject.toml"}

    rules.write_text(rules.read_text().replace("np.maximum(np.asarray(cpi, dtype=float), TRIPLE_LOCK_FLOOR)",
                                               "np.maximum(np.asarray(cpi, dtype=float), ZERO_FLOOR)", 1))
    assert engine.job_key("path", {"x": 1}, engine.engine_semantics(root, pyproject), {"p": "1"}) != key


def test_a_dependency_change_in_pyproject_moves_the_key(tmp_path):
    root, pyproject = copy_engine(tmp_path)
    before = engine.engine_semantics(root, pyproject)["pyproject.toml"]
    pyproject.write_text(pyproject.read_text().replace('"scipy==1.18.1"', '"scipy==1.18.2"'))
    assert engine.engine_semantics(root, pyproject)["pyproject.toml"] != before


def package_imports(path):
    """Modules of this package that ``path`` imports (``from . import x``, ``from .x import y``)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            out |= {f"{a.name}.py" for a in node.names} if node.module is None else {f"{node.module}.py"}
    return out


@pytest.mark.parametrize("entry, covered", [
    ("engine.py", set(FILES)),
    ("households.py", set(FILES) | {"households.py"}),
])
def test_the_key_covers_every_module_a_job_imports(entry, covered):
    """Every module of this package a job can execute (transitively) is hashed into its key."""
    seen, todo = set(), [entry]
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo += sorted(package_imports(SRC / name))
    assert seen <= covered, seen - covered


@pytest.mark.parametrize("name", [*FILES, "households.py"])
def test_no_module_the_key_covers_reads_a_docstring(name):
    """Dropping docstrings from the key is safe only if no code reads one (as expected_value.py does for its method
    text, which is why it is not a job module)."""
    for node in ast.walk(ast.parse((SRC / name).read_text())):
        assert not (isinstance(node, ast.Name) and node.id == "__doc__"), name
        assert not (isinstance(node, ast.Attribute) and node.attr == "__doc__"), name
        assert not (isinstance(node, ast.Name) and node.id == "getdoc"), name
