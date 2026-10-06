"""Synthetic disclosure checks for the precision diagnostic; no model loads."""

import importlib.util
from pathlib import Path

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    "gc_precision_diagnostic",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_model_v2_gc_precision.py",
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def policies(size):
    def side():
        return {
            "weights": np.ones(size),
            **{variable: np.ones(size) for variable in diagnostic.MONETARY_VARIABLES},
        }
    return side(), side()


def partition(size, split):
    mask = np.arange(size) < split
    return {"first": mask, "remaining": ~mask}


def published_counts(value, count_context=False):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from published_counts(child, count_context or key.endswith("records"))
    elif isinstance(value, list):
        for child in value:
            yield from published_counts(child, count_context)
    elif count_context and value is not None:
        yield value


def test_small_group_complement_suppresses_entire_count_and_money_families():
    a, b = policies(20)
    public, private = diagnostic.partition_aggregates(a, b, partition(20, 11))
    assert private["groups"]["remaining"]["records"] == 9
    assert public["count_family_status"] == "withheld_linked_family"
    assert public["records"] is None
    for row in public["groups"].values():
        assert row["records"] is row["complement_records"] is None
        assert all(component["status"] == "withheld_linked_family" for component in row["components"].values())
    assert all(component["change_bn"] is None for component in public["total_components"].values())


def test_small_monetary_support_complement_hides_linked_variable_and_total():
    a, b = policies(40)
    a["guarantee_credit"][0] = b["guarantee_credit"][0] = 0
    public, _ = diagnostic.partition_aggregates(a, b, partition(40, 20))
    assert public["count_family_status"] == "available"
    assert public["total_components"]["guarantee_credit"]["status"] == "withheld_linked_family"
    assert public["total_components"]["housing_benefit"]["status"] == "available"
    for row in public["groups"].values():
        component = row["components"]["guarantee_credit"]
        assert component["support_records"] is component["support_complement_records"] is None
        assert component["triple_lock_bn"] is component["burnham_2030_bn"] is component["change_bn"] is None


def test_linked_subset_cannot_reveal_nine_records_by_subtraction():
    a, b = policies(40)
    (public, subset), _ = diagnostic.linked_partition_aggregates(
        a, b, partition(40, 20), partition(40, 11)
    )
    for table in (public, subset):
        assert table["count_family_status"] == "withheld_linked_family"
        assert all(row["records"] is None for row in table["groups"].values())
        assert all(component["status"] == "withheld_linked_family" for component in table["total_components"].values())


def test_small_cooccurrence_reports_presence_without_count_or_amount():
    weights = np.ones(40)
    flips = np.arange(40) < 3
    changes = np.arange(40) < 1
    result = diagnostic.cooccurrence_check(flips, changes, weights)
    assert result["passport_flips_observed"] is True
    assert result["housing_benefit_changes_cooccur"] is True
    assert result["numeric_family_status"] == "withheld_linked_family"
    assert result["passport_flip_records"] is result["housing_benefit_change_records"] is None
    assert "cooccurrence only" in result["interpretation"]


def test_no_hb_change_is_reported_separately_from_flip_presence():
    result = diagnostic.cooccurrence_check(np.arange(40) < 20, np.zeros(40, dtype=bool), np.ones(40))
    assert result["passport_flips_observed"] is True
    assert result["housing_benefit_changes_cooccur"] is False
    assert result["numeric_family_status"] == "available"
    assert result["housing_benefit_change_records"] == 0


def test_subpenny_flip_with_hb_change_has_no_public_numeric_family():
    a, b = policies(40)
    for side in (a, b):
        side["guarantee_credit"][:] = 0
        side["pension_credit"][:] = 0
        side["passport"] = np.zeros(40, dtype=bool)
        side["in_receipt_of_guarantee_credit"] = np.zeros(40, dtype=bool)
        side["would_claim_pc"] = np.zeros(40, dtype=bool)
        side["is_pension_credit_eligible"] = np.ones(40, dtype=bool)
        side["gc_reconstruction_matches"] = True
    b["guarantee_credit"][:3] = 0.005
    b["passport"][:3] = True
    b["housing_benefit"][:3] = 2
    public, private = diagnostic.diagnose_year(a, b)
    check = public["categorical_cooccurrence_checks"]["at_most_one_penny_gc_passport_flips"]
    assert check["housing_benefit_changes_cooccur"] is True
    assert check["passport_flip_records"] is None
    assert public["gc_passport_flip_hb_changing_subset_amount_bands"]["count_family_status"] == "withheld_linked_family"
    assert private["hb_changing_subset_amount_bands"]["groups"]["positive_gc_at_most_one_penny"]["records"] == 3
    assert public["in_receipt_variable_matches_eligible_claimant_with_positive_gc"] is True


def test_actual_receipt_attribution_classifies_the_hb_changing_subset():
    a, b = policies(60)
    for side in (a, b):
        side["guarantee_credit"][:] = 0
        side["passport"] = np.zeros(60, dtype=bool)
        side["in_receipt_of_guarantee_credit"] = np.zeros(60, dtype=bool)
        side["would_claim_pc"] = np.zeros(60, dtype=bool)
        side["is_pension_credit_eligible"] = np.ones(60, dtype=bool)
        side["gc_reconstruction_matches"] = True
    b["guarantee_credit"][:40] = 20
    b["passport"][:40] = True
    b["in_receipt_of_guarantee_credit"][:20] = True
    b["would_claim_pc"][:20] = True
    b["housing_benefit"][:20] = 2
    public, _ = diagnostic.diagnose_year(a, b)
    all_flips = public["gc_passport_flip_receipt_attribution"]["groups"]
    changing = public["gc_passport_flip_hb_changing_subset_receipt_attribution"]["groups"]
    assert all_flips["passport_flip_entitlement_only_nonclaimant"]["records"] == 20
    assert changing["passport_flip_entitlement_only_nonclaimant"]["records"] == 0
    assert changing["passport_flip_with_actual_gc_receipt"]["records"] == 20
    assert changing["passport_flip_with_actual_gc_receipt"]["components"]["housing_benefit"]["support_records"]["change"] == 20


def test_replay_money_is_withheld_when_household_support_complement_is_small():
    values = {"gross": 2.0, "net": 1.0}
    result = diagnostic.saving_replay_summary(values, values, {"gross": 20, "net": 31}, 40)
    assert result["replay_within_absolute_tolerance"] is True
    assert result["numeric_family_status"] == "withheld_linked_family"
    assert result["gross"]["replay_bn"] is result["net"]["replay_bn"] is None


def test_replay_checks_absolute_one_million_tolerance():
    expected = {"gross": 2.0, "net": 1.0}
    actual = {"gross": 2.0, "net": 1.0009}
    result = diagnostic.saving_replay_summary(expected, actual, {"gross": 20, "net": 20}, 40)
    assert result["numeric_family_status"] == "available"
    with pytest.raises(RuntimeError, match="within £1 million"):
        diagnostic.saving_replay_summary(expected, {"gross": 2.0, "net": 1.002}, {"gross": 20, "net": 20}, 40)


def test_change_only_partition_publishes_supported_change_without_small_level_cell():
    a, b = policies(60)
    a["housing_benefit"][:5] = 0
    b["housing_benefit"][:30] = 2
    masks = partition(60, 20)
    full, _ = diagnostic.partition_aggregates(a, b, masks)
    changes, _ = diagnostic.partition_aggregates(a, b, masks, include_levels=False)
    assert full["total_components"]["housing_benefit"]["status"] == "withheld_linked_family"
    assert changes["total_components"]["housing_benefit"]["status"] == "available"
    assert changes["groups"]["first"]["components"]["housing_benefit"]["support_records"] == {"change": 20}
    assert "triple_lock_bn" not in changes["groups"]["first"]["components"]["housing_benefit"]


def test_substantial_partition_cannot_reveal_small_remainder_from_all_flip_table():
    a, b = policies(60)
    b["housing_benefit"][:23] = 2
    flips = np.arange(60) < 40
    changed = np.arange(60) < 23
    selected = np.arange(60) < 20
    public, _ = diagnostic.substantial_change_partition(a, b, flips, changed, selected)
    assert public["count_family_status"] == "withheld_linked_family"
    assert public["groups"]["hb_changing_passport_flips_with_gc_above_ten_pounds"]["records"] is None
    assert public["total_components"]["housing_benefit"]["change_bn"] is None


@settings(deadline=None)
@given(size=st.integers(min_value=1, max_value=100), split=st.integers(min_value=0, max_value=100))
def test_published_counts_are_zero_or_at_least_ten(size, split):
    a, b = policies(size)
    b["housing_benefit"][::3] = 2
    a["guarantee_credit"][::4] = 0
    public, _ = diagnostic.partition_aggregates(a, b, partition(size, min(size, split)))
    assert all(count == 0 or count >= 10 for count in published_counts(public))
    for variable in diagnostic.MONETARY_VARIABLES:
        statuses = {public["total_components"][variable]["status"]}
        statuses.update(row["components"][variable]["status"] for row in public["groups"].values())
        assert len(statuses) == 1


def test_policy_weight_misalignment_is_rejected():
    a, b = policies(40)
    b["weights"][0] = 2
    with pytest.raises(ValueError, match="policy weights differ"):
        diagnostic.partition_aggregates(a, b, partition(40, 20))


def test_overlapping_partition_is_rejected():
    a, b = policies(40)
    with pytest.raises(ValueError, match="must partition"):
        diagnostic.partition_aggregates(a, b, {"first": np.ones(40, dtype=bool), "second": np.ones(40, dtype=bool)})
