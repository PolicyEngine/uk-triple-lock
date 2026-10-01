"""Extend policyengine-uk's parameter builders past their built-in horizons, in memory.

policyengine-uk 2.90.2 builds several derived series at parameter-load time
(``CountryTaxBenefitSystem.process_parameters``) over fixed year ranges:

* ``lag_cpi.add_lagged_cpi``: ``yoy_growth.obr.lagged_cpi`` (CPI growth in the
  previous calendar year) for 2010-2029. Its index uprates
  ``gov.benefit_uprating_cpi``, which uprates the benefit parameters that follow
  CPI (86 parameter files: the Pension Credit guarantee, Universal Credit,
  Housing Benefit, tax credits, disability benefits, Child Benefit and others).
  From 2030 the series holds its 2029 value, so every such rate would grow at
  the path's 2028 CPI whatever the path does after.
* ``lag_average_earnings.add_lagged_earnings``: 2022-2029.
* ``create_triple_lock.add_triple_lock``: the model's own triple lock,
  2022-2034 (it uprates the flat-rate State Pension, and through it the
  additional State Pension the trajectory runs pin).
* ``create_private_pension_uprating.add_private_pension_uprating_factor``:
  min(RPI growth the year before, 5%), which uprates private pension income,
  2020-2034.
* ``create_economic_assumption_indices``: every growth index to 2039.
* ``utils.parameters.convert_to_fiscal_year_parameters``: fiscal years
  2015-2040.

After its last year each series holds its final value, so nothing fails: the
model quietly stops following the path. ``install()`` replaces each builder
with the same construction over years running to ``END_YEAR``, in the running
process only, and clears the processed-parameter cache so every tax-benefit
system built afterwards uses them. A Scenario cannot do this: its parameter
changes are applied after ``reset_parameters()`` and before
``process_parameters()``, which rebuilds these series from the builders.

Each replacement copies the upstream construction. ``install()`` first checks
the upstream source files against the versions copied here (SHA-256), so a
policyengine-uk upgrade that changes any of them fails here instead of
silently. The trajectory runs then record, for every year, the growth of series
built on these (benefit uprating, a CPI-indexed threshold, employment income and
the model's triple lock) and check that they follow the path; they check the
Pension Credit guarantee too, which every run sets from May-July earnings
instead (engine.pension_credit_levels).
"""

import contextlib
import hashlib
import importlib
from pathlib import Path

END_YEAR = 2042  # every extended series covers at least fiscal year 2041-42

# SHA-256 of the upstream files whose construction the replacements copy (policyengine-uk 2.90.2).
UPSTREAM = {
    "policyengine_uk.parameters.gov.economic_assumptions.lag_cpi":
        "e2c2da410cc3b07de58e9c25c802c55740719c9c494caf45fd5e00712dbfab46",
    "policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings":
        "b58b6ab89739f2fee029bdc1d3b62c07767f40dace7ad3f910b8444ee19ed5ab",
    "policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock":
        "c8fda9271d54d8880b1bdfca4a8bb152a5c417709c245641b4301b55d42a892a",
    "policyengine_uk.parameters.gov.contrib.create_private_pension_uprating":
        "3507c03c7388ea0cd2c45dd6368a5b4ac390a670dbf6e57567d84c6488b92ae2",
    "policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices":
        "7ad33ae7b0e6d8fa12ac7149aa8a33b2b01024208fc5538f5cae39a0bdf89244",
    "policyengine_uk.utils.parameters":
        "381d6b24a38a1c29bf6c1f129295acb65631abefc434c0fdc083b04bb8226b02",
    "policyengine_uk.tax_benefit_system":
        "9be5309abbf385299d06e37b8d48e73b1cf800f7b6e905180cf657550667ccc1",
}


class UpstreamChanged(RuntimeError):
    """policyengine-uk's builders differ from the versions the replacements copy."""


def check_upstream():
    """Raise UpstreamChanged unless every copied upstream file is byte-identical to the recorded version."""
    changed = []
    for module, expected in UPSTREAM.items():
        path = Path(importlib.import_module(module).__file__)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(module)
    if changed:
        raise UpstreamChanged(f"policyengine-uk changed {changed}; re-read them and update model_horizon.py")


def add_lagged_cpi(parameters, end_year=END_YEAR):
    """lag_cpi.add_lagged_cpi, to ``end_year``."""
    from policyengine_core.parameters import Parameter

    obr = parameters.gov.economic_assumptions.yoy_growth.obr
    cpi = obr.consumer_price_index
    obr.add_child("lagged_cpi", Parameter(
        "gov.economic_assumptions.yoy_growth.obr.lagged_cpi",
        data={"values": {f"{year}-01-01": cpi(year - 1) for year in range(2010, end_year + 1)}},
    ))
    return parameters


def add_lagged_earnings(parameters, end_year=END_YEAR):
    """lag_average_earnings.add_lagged_earnings, to ``end_year``."""
    from policyengine_core.parameters import Parameter

    obr = parameters.gov.economic_assumptions.yoy_growth.obr
    earnings = obr.average_earnings
    obr.add_child("lagged_average_earnings", Parameter(
        "gov.economic_assumptions.yoy_growth.lagged_average_earnings",
        data={"values": {f"{year}-01-01": earnings(year - 1) for year in range(2022, end_year + 1)}},
    ))
    return parameters


def create_economic_assumption_indices(parameters, end_year=END_YEAR):
    """create_economic_assumption_indices.create_economic_assumption_indices, to ``end_year``."""
    from policyengine_core.parameters import Parameter, ParameterNode

    econ_assumptions = parameters.gov.economic_assumptions
    yoy_growth = econ_assumptions.yoy_growth
    econ_assumptions.add_child("indices", ParameterNode(name="gov.economic_assumptions.indices", data={}))
    for descendant in yoy_growth.get_descendants():
        parent_node = parameters.get_child(descendant.parent.name.replace("yoy_growth", "indices"))
        child_name = descendant.name.split(".")[-1]
        if isinstance(descendant, ParameterNode):
            parent_node.add_child(child_name, ParameterNode(
                name=descendant.name.replace("yoy_growth", "indices"), data={}))
        else:
            start_year = int(descendant.values_list[-1].instant_str[:4])
            values = {start_year: 1.0}
            for year in range(start_year + 1, end_year + 1):
                values[year] = round(values[year - 1] * (1 + descendant(year)), 5)
            parent_node.add_child(child_name, Parameter(
                name=descendant.name.replace("yoy_growth", "indices"),
                data={"values": {f"{year}-01-01": value for year, value in values.items()}},
            ))
    return parameters


def convert_to_fiscal_year_parameters(parameters, end_year=END_YEAR):
    """utils.parameters.convert_to_fiscal_year_parameters, fiscal years 2015 to ``end_year``."""
    from policyengine_core.parameters import Parameter
    from policyengine_uk.utils.parameters import fiscal_year_average

    years = list(range(2015, end_year + 1))
    for param in parameters.get_descendants():
        if isinstance(param, Parameter):
            blend = (param.metadata or {}).get("fiscal_year_blend", False)
            values = {}
            for year in years:
                value = fiscal_year_average(param, year) if blend else None
                if value is None:
                    value = param(f"{year}-04-30")
                values[year] = value
            for year, value in values.items():
                param.update(period=f"{year}", value=value)
    return parameters


def extensions(end_year=END_YEAR):
    """What ``install`` extends: each series' upstream first and last years, and the new last year."""
    return {
        "upstream": "policyengine-uk 2.90.2",
        "end_year": end_year,
        "upstream_years": {
            "lagged_cpi": [2010, 2029],
            "lagged_average_earnings": [2022, 2029],
            "triple_lock": [2022, 2034],
            "private_pension_index": [2020, 2034],
            "economic_assumption_indices": [None, 2039],
            "fiscal_year_parameters": [2015, 2040],
        },
    }


def install(end_year=END_YEAR):
    """Point policyengine-uk's parameter processing at the extended builders; returns what was changed."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating
    from policyengine_uk.parameters.gov.dwp.state_pension.triple_lock import create_triple_lock

    check_upstream()
    tbs.add_lagged_cpi = lambda p: add_lagged_cpi(p, end_year)
    tbs.add_lagged_earnings = lambda p: add_lagged_earnings(p, end_year)
    tbs.create_economic_assumption_indices = lambda p: create_economic_assumption_indices(p, end_year)
    tbs.convert_to_fiscal_year_parameters = lambda p: convert_to_fiscal_year_parameters(p, end_year)
    # These two read a module-level YEARS list when called.
    create_triple_lock.YEARS = list(range(2022, end_year + 1))
    create_private_pension_uprating.YEARS = list(range(2020, end_year + 1))
    # Systems built from here on run process_parameters() with the builders above.
    tbs._processed_parameters_cache = None
    return extensions(end_year)


@contextlib.contextmanager
def installed(end_year=END_YEAR):
    """``install()`` for the duration of a block, then restore the upstream builders (for tests)."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating
    from policyengine_uk.parameters.gov.dwp.state_pension.triple_lock import create_triple_lock

    names = ["add_lagged_cpi", "add_lagged_earnings", "create_economic_assumption_indices",
             "convert_to_fiscal_year_parameters", "_processed_parameters_cache"]
    saved = {n: getattr(tbs, n) for n in names}
    years = create_triple_lock.YEARS, create_private_pension_uprating.YEARS
    try:
        yield install(end_year)
    finally:
        for n, v in saved.items():
            setattr(tbs, n, v)
        create_triple_lock.YEARS, create_private_pension_uprating.YEARS = years
