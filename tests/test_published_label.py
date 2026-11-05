"""The dashboard and the results file agree on the adjustment's published name (d2123)."""

import csv
import json
import re

import pytest

from triple_lock import config, pipeline

LABEL = pipeline.published_policies()["burnham_2030"]["label"]


def _strings(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _results_files():
    yield config.OUTPUT
    yield from sorted((config.REPO / "data" / "interim").glob("*.json"))


@pytest.mark.parametrize("path", list(_results_files()), ids=lambda p: p.name)
def test_a_file_built_after_d2123_names_burnham_only_in_ids(path):
    results = json.loads(path.read_text())
    if results["policies"]["burnham_2030"]["label"] != LABEL:
        pytest.skip(f"{path.name} predates d2123 (the provisional pre-Budget release says 'Burnham plan')")
    # The id burnham_2030 and metric paths that contain it are lower case; every capitalised "Burnham" is prose.
    assert [(p, s[:120]) for p, s in _strings(results) if "Burnham" in s] == []


def test_the_benchmark_rows_the_build_publishes_do_not_say_burnham():
    with (config.REPO / "data" / "benchmarks.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and [(r.get("id"), k) for r in rows for k, v in r.items() if v and "Burnham" in v] == []


def test_the_dashboard_maps_old_files_to_the_label_the_build_publishes():
    source = (config.REPO / "dashboard" / "src" / "lib" / "dataHelpers.js").read_text()
    (label,) = re.findall(r'export const ADJUSTED_TRIPLE_LOCK_LABEL = "([^"]+)";', source)
    assert label == pipeline.published_policies()["burnham_2030"]["label"]


def test_the_published_policies_keep_every_id_and_rule():
    published = pipeline.published_policies()
    assert published.keys() == config.POLICIES.keys()
    for policy_id, policy in config.POLICIES.items():
        assert {k: v for k, v in published[policy_id].items() if k != "label"} == {k: v for k, v in policy.items() if k != "label"}
