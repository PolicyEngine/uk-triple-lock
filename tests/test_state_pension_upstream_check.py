"""The upstream probe rejects an eligibility mistake shared by both rules."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("policyengine_uk")

_spec = importlib.util.spec_from_file_location(
    "state_pension_upstream_check",
    Path(__file__).parents[1] / "scripts/check_state_pension_upstream.py",
)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


@pytest.mark.parametrize("year", [2027, 2031, 2039])
def test_future_age_addition_rejects_shared_eligibility_errors(year):
    annual = 0.25 * probe.WEEKS_IN_YEAR
    actual = np.array([annual, annual, annual, 0, annual, 0, 0, 0], dtype=np.float32)
    probe.assert_expected_age_addition(actual, year, included=None)
    # Cross-policy equality alone would accept both rules paying nothing.
    with pytest.raises(AssertionError):
        probe.assert_expected_age_addition(np.zeros(8, dtype=np.float32), year, included=None)
    # A NEW pensioner aged 80 is still ineligible for the BASIC age addition.
    actual[3] = annual
    with pytest.raises(AssertionError):
        probe.assert_expected_age_addition(actual, year, included=None)


def test_data_year_small_report_stays_capped_to_reported_amount():
    annual = 0.25 * probe.WEEKS_IN_YEAR
    included = np.array([0, annual, annual, 0, 5, 0, 0, 0])
    actual = included.astype(np.float32)
    probe.assert_expected_age_addition(actual, probe.DATA_YEAR, included)
    actual[4] = annual
    with pytest.raises(AssertionError):
        probe.assert_expected_age_addition(actual, probe.DATA_YEAR, included)
