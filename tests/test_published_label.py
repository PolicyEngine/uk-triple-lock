"""The dashboard and the results file agree on the adjustment's published name (d2123)."""

import re

from triple_lock import config, pipeline


def test_the_dashboard_maps_old_files_to_the_label_the_build_publishes():
    source = (config.REPO / "dashboard" / "src" / "lib" / "dataHelpers.js").read_text()
    (label,) = re.findall(r'export const ADJUSTED_TRIPLE_LOCK_LABEL = "([^"]+)";', source)
    assert label == pipeline.published_policies()["burnham_2030"]["label"]


def test_the_published_policies_keep_every_id_and_rule():
    published = pipeline.published_policies()
    assert published.keys() == config.POLICIES.keys()
    for policy_id, policy in config.POLICIES.items():
        assert {k: v for k, v in published[policy_id].items() if k != "label"} == {k: v for k, v in policy.items() if k != "label"}
