"""Check the engine against an installed upstream branch, using invented households.

Run in a throwaway venv containing either #2336 or #2340 and this repository's
dependencies, with ``PYTHONPATH=src``. For example::

    python scripts/check_state_pension_upstream.py --expect-age-addition present

No survey is loaded. The Simulation has a data-year metadata marker so its
pension formulas observe 2024 reports while calculating later years, as the
engine does. This marker contains no records and is never materialized.
"""

import argparse
import importlib.metadata
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import policyengine_uk
from policyengine_uk import Simulation
from policyengine_uk.model_api import WEEKS_IN_YEAR
from policyengine_uk.system import parameters as legislated_parameters

from triple_lock import engine
from triple_lock.config import FLAT_RATE_PARAMETERS
from triple_lock.demography import pension_components

DATA_YEAR = 2024
YEARS = [DATA_YEAR, 2027, 2031, 2039]


class Household:
    """The engine's Microsimulation array interface, backed by a Simulation."""

    def __init__(self, situation, reform=None):
        self.sim = Simulation(situation=situation, reform=reform)
        self.sim.dataset = SimpleNamespace(years=[DATA_YEAR])
        self.sim.baseline = None
        self.dataset = self.sim.dataset
        self.tax_benefit_system = self.sim.tax_benefit_system

    def calculate(self, variable, year):
        values = self.sim.calculate(variable, year, decode_enums=True)
        return pd.Series(values)

    def set_input(self, variable, year, values):
        self.sim.set_input(variable, year, values)

    def clone(self, reform=None):
        result = object.__new__(Household)
        result.sim = self.sim.clone(clone_tax_benefit_system=True)
        result.sim.baseline = None
        result.sim.tax_benefit_system.simulation = result.sim
        result.sim.input_variables = list(self.sim.input_variables)
        result.sim.calculated_periods = []
        result.sim._variable_dependencies = None
        result.sim._invalidate_all_caches()
        if reform is not None:
            result.sim.apply_reform(reform)
        result.dataset = result.sim.dataset
        result.tax_benefit_system = result.sim.tax_benefit_system
        return result


def invented_households(caps):
    # Include the entitlement boundary, no entitlement, a partial pension,
    # and a report below the age addition, whose data-year identity needs a pin.
    people = [
        ("turns_80", "BASIC", 79, caps[0] + 100, True),
        ("basic_80", "BASIC", 80, caps[0] + 100, True),
        ("partial", "BASIC", 90, caps[0] / 2, True),
        ("new_80", "NEW", 80, caps[1] + 100, True),
        ("small_report", "BASIC", 80, 5, True),
        ("no_report", "BASIC", 80, 0, True),
        ("no_type", "NONE", 80, 0, True),
        ("below_sp_age", "BASIC", 40, 1000, False),
    ]
    situation = {"people": {}, "benunits": {}, "households": {}}
    for name, pension_type, age, reported, over in people:
        situation["people"][name] = {
            "age": {y: age + y - DATA_YEAR for y in YEARS},
            "state_pension_type": {y: pension_type for y in YEARS},
            "is_SP_age": {y: over for y in YEARS},
            "state_pension_reported": {DATA_YEAR: reported},
        }
        situation["benunits"][name] = {"members": [name]}
        situation["households"][name] = {"members": [name]}
    return situation


def historical_denominator_check(source, parameters, pinned, payable, included, caps):
    """A data-year cut scales the legislated flat share and leaves fixed parts alone."""
    amounts = {name: float(parameters.get_child(path)(f"{DATA_YEAR}-06-01"))
               for name, path in FLAT_RATE_PARAMETERS.items()}
    base = source.clone()
    engine.pin(base, pinned)
    engine.state_pension_accounting(base, pinned)
    reformed = source.clone(engine.actual_law_denominators(amounts, DATA_YEAR))
    engine.pin(reformed, pinned)
    ratio = 0.83
    engine.set_flat_rates(reformed.sim, {name: {DATA_YEAR: amount * ratio} for name, amount in amounts.items()})
    basic, new, additional = pension_components(
        payable - included, pinned["state_pension_type"][DATA_YEAR], *caps)
    expected = (basic + new) * ratio + additional + included
    for variable, flat in (("basic_state_pension", basic), ("new_state_pension", new)):
        np.testing.assert_allclose(reformed.calculate(variable, DATA_YEAR), flat * ratio, rtol=1e-6, atol=0.002)
    np.testing.assert_allclose(reformed.calculate("additional_state_pension", DATA_YEAR), additional,
                               rtol=1e-6, atol=0.001)
    if engine.AGE_ADDITION in engine.state_pension_parts(reformed):
        np.testing.assert_array_equal(reformed.calculate(engine.AGE_ADDITION, DATA_YEAR), included)
    np.testing.assert_allclose(reformed.calculate("state_pension", DATA_YEAR), expected, rtol=1e-6, atol=0.002)
    return {"flat_rate_ratio": ratio, "state_pension": expected.tolist()}


def check(expect_age_addition):
    parameters = legislated_parameters
    p = parameters.gov.dwp.state_pension
    caps = (float(p.basic_state_pension.amount(DATA_YEAR)) * WEEKS_IN_YEAR,
            float(p.new_state_pension.amount(DATA_YEAR)) * WEEKS_IN_YEAR)
    situation = invented_households(caps)
    source = Household(situation)
    has_addition = engine.AGE_ADDITION in engine.state_pension_parts(source)
    assert has_addition == expect_age_addition, (has_addition, expect_age_addition)
    reports = source.calculate("state_pension_reported", DATA_YEAR).to_numpy()
    payable = reports * source.calculate("is_SP_age", DATA_YEAR).to_numpy()
    base_types = source.calculate("state_pension_type", DATA_YEAR).to_numpy()
    ages = source.calculate("age", DATA_YEAR).to_numpy()
    included = (np.minimum(payable, 0.25 * WEEKS_IN_YEAR)
                * (base_types == "BASIC") * (ages >= 80) if has_addition else 0)
    expected_extra = pension_components(payable - included, base_types, *caps)[2]
    unpinned_extra = source.calculate("additional_state_pension", 2031).to_numpy()
    # Both paths differ from the model default, including a year of falling
    # prices. Their exact compounded CPI, rather than an upstream index or
    # a ratio of flat rates, must control the additional pension.
    paths = {
        "steady": {y: 0.023 for y in range(DATA_YEAR, max(YEARS))},
        "volatile": {y: (-0.01 if y % 3 == 0 else 0.047) for y in range(DATA_YEAR, max(YEARS))},
    }
    observed = {}
    historical = None
    for path, cpi in paths.items():
        pinned, data_year = engine.pinned_inputs(source.clone(), YEARS, cpi, "legacy")
        assert data_year == DATA_YEAR
        if historical is None:
            historical = historical_denominator_check(source, parameters, pinned, payable, included, caps)
        additions = []
        extras = []
        for policy, factor in (("triple_lock", 1.08), ("burnham_2030", 0.85)):
            sim = source.clone()
            engine.pin(sim, pinned)
            levels = {
                name: {y: float(parameters.get_child(parameter)(f"{y}-06-01")) * factor
                       for y in YEARS if y != DATA_YEAR}
                for name, parameter in FLAT_RATE_PARAMETERS.items()
            }
            engine.set_flat_rates(sim.sim, levels)
            parts = engine.state_pension_parts(sim)
            total = sum(sim.calculate(v, DATA_YEAR).to_numpy() for v in parts)
            np.testing.assert_allclose(total, payable, rtol=0, atol=0.002)
            np.testing.assert_allclose(sim.calculate("state_pension", DATA_YEAR), total, rtol=0, atol=0.002)
            by_year = {}
            for year in YEARS:
                index = np.prod([1 + max(cpi[y], 0) for y in range(DATA_YEAR, year)])
                extra = sim.calculate("additional_state_pension", year).to_numpy()
                np.testing.assert_allclose(extra, expected_extra * index, rtol=1e-6, atol=0.001)
                np.testing.assert_allclose(extra, pinned["additional_state_pension"][year], rtol=1e-6, atol=0.001)
                by_year[year] = extra.tolist()
            assert not np.allclose(by_year[2031], unpinned_extra), "path did not override the model's CPI index"
            extras.append(by_year)
            if has_addition:
                additions.append({y: sim.calculate(engine.AGE_ADDITION, y).to_numpy() for y in YEARS})
        assert extras[0] == extras[1], (path, "policy changed a pinned additional pension")
        if has_addition:
            for year in YEARS:
                np.testing.assert_array_equal(additions[0][year], additions[1][year])
            np.testing.assert_array_equal(additions[0][DATA_YEAR], included)
            assert engine.AGE_ADDITION in engine.fiscal_variables(parameters, DATA_YEAR, source)[1]
        observed[path] = {"additional_pension": extras[0],
                          "age_addition": {y: v.tolist() for y, v in additions[0].items()} if additions else None}
    return {"policyengine_uk": importlib.metadata.version("policyengine-uk"),
            "policyengine_uk_source": policyengine_uk.__file__,
            "policyengine_core": importlib.metadata.version("policyengine-core"),
            "age_addition_present": has_addition, "households": len(situation["people"]),
            "years": YEARS, "historical_denominator": historical,
            "unpinned_additional_pension_2031": unpinned_extra.tolist(), "paths": observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-age-addition", choices=("present", "absent"), required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.expect_age_addition == "present"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
