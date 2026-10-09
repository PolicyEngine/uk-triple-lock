"""Synthetic flat-rate inputs exercise the country disclosure floor."""

from types import SimpleNamespace

import numpy as np
import pytest

from triple_lock import engine


class Array:
    def __init__(self, values):
        self.values = np.asarray(values)

    def to_numpy(self):
        return self.values


class SyntheticFlatRateSimulation:
    """One person per household; the holder stores model float32 inputs."""

    def __init__(self, kept, countries, weights=None):
        from policyengine_uk.model_api import WEEKS_IN_YEAR

        self.amount = np.asarray(kept, dtype=np.float32)
        self.country = np.asarray(countries)
        self.weight = np.ones(len(kept)) if weights is None else np.asarray(weights)
        self.populations = {"household": SimpleNamespace(project=lambda mask: mask)}
        self.tax_benefit_system = SimpleNamespace(
            variables={"new_state_pension": SimpleNamespace(dtype=np.dtype("float32"))},
            parameters=SimpleNamespace(get_child=lambda path: lambda date: 10000 / WEEKS_IN_YEAR))
        self.calculations = []

    def calculate(self, variable, year, **kwargs):
        self.calculations.append((variable, year))
        return Array({"new_state_pension": self.amount, "country": self.country,
                      "person_weight": self.weight}[variable])

    def set_input(self, variable, year, values):
        if variable == "new_state_pension":
            self.amount = np.asarray(values, dtype=np.float32)


def pinned(records):
    inputs = engine.Pinned({"state_pension_reported": {2024: np.full(records, 9000)},
                           "state_pension_type": {2024: np.full(records, "BASIC")}})
    inputs.data_year = 2024
    inputs.retyped_level = "full_new"
    inputs.retyped_new = {2039: np.ones(records, dtype=bool)}
    return inputs


def test_already_full_retyped_records_do_not_pass_the_country_floor():
    # England has ten re-typed records, but only nine change: one already
    # has the full flat rate. Scotland has ten actual changed amounts.
    sim = SyntheticFlatRateSimulation([5000] * 9 + [10000] + [6000] * 10,
                                     ["ENGLAND"] * 10 + ["SCOTLAND"] * 10)
    inputs = pinned(20)
    engine.pin(sim, inputs)
    assert sim.calculations == [("new_state_pension", 2039)]  # no extra model reads
    support = engine.pension_contrast_support(sim, inputs, [2039])[2039]
    assert support["ENGLAND"] == {"status": "suppressed", "records": None}
    assert support["SCOTLAND"] == {"status": "available", "records": 10}
    assert support["uk"] == support["gb"] == {"status": "available", "records": 19}
    np.testing.assert_array_equal(sim.amount, np.full(20, 10000, dtype=np.float32))


def test_support_uses_stored_precision_and_positive_weights():
    # A double-precision difference lost when the holder casts to float32
    # is not an actual changed model amount. Zero weights do not contribute.
    sim = SyntheticFlatRateSimulation([10000 - 1e-8, 5000, 5000], ["ENGLAND"] * 3, [1, 1, 0])
    inputs = pinned(3)
    engine.pin(sim, inputs)
    np.testing.assert_array_equal(sim.triple_lock_retyped_level_changed[2039], [False, True, True])
    assert engine.pension_contrast_support(sim, inputs, [2039])[2039]["uk"] == {
        "status": "suppressed", "records": None}


def test_full_new_support_refuses_before_the_level_input_is_applied():
    sim = SyntheticFlatRateSimulation([5000] * 10, ["ENGLAND"] * 10)
    with pytest.raises(engine.PathNotFollowed, match="applied flat-rate change masks"):
        engine.pension_contrast_support(sim, pinned(10), [2039])
