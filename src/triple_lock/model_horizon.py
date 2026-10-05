"""Extend the one policyengine-uk parameter builder that stops before the final year, in memory.

policyengine-uk builds several derived series at parameter-load time
(``CountryTaxBenefitSystem.process_parameters``). Under 2.118.0 every one the
engine relies on reaches fiscal 2039-40 by itself except one:

* ``lag_cpi.add_lagged_cpi`` and ``lag_average_earnings.add_lagged_earnings``
  (through ``lagged_series.add_lagged_parameter``) run to the year after their
  source's last value. The OBR growth series now run to 2073, so these reach
  2074. (2.90.2 stopped lagged CPI at 2029, so benefit rates stopped following
  the path after April 2029.)
* ``create_statutory_uprating_inputs.add_statutory_uprating_inputs`` fills
  September CPI and May-July earnings to the last year of the calendar series
  (2073), and ``create_triple_lock.add_triple_lock`` builds the model's own
  triple lock from them to the year after (2.90.2 stopped it at 2034).
* ``create_economic_assumption_indices`` builds every growth index to 2039, and
  ``utils.parameters.convert_to_fiscal_year_parameters`` converts fiscal years
  2015 to 2040: both cover the final year, 2039-40, whose parameters a
  simulation reads at 1 January 2039.
* ``create_private_pension_uprating.add_private_pension_uprating_factor``
  (min(RPI growth the year before, 5%), which uprates private pension income)
  still covers only the module-level ``YEARS``, 2020 to 2034. After that it
  holds its 2034 value, so private pension income would stop following the
  path's RPI from 2035-36. ``install()`` extends ``YEARS`` to ``END_YEAR``.

A one-off check when porting (built for the central path, every parameter on
five dates a year) found the processed tree identical with and without the
old extensions of the indices, the fiscal-year conversion and the lagged
series on every date to 2039 (they first differ in 2040), and changed from
2036 by extending the private pension uprating. tests/test_model.py checks
the extension changes nothing else to the final year, and that every derived
series follows a path to it. A Scenario cannot
do this: its parameter changes are applied after ``reset_parameters()`` and
before ``process_parameters()``, which rebuilds these series from the builders.

``install()`` first checks the upstream files whose horizons this relies on,
those whose formulas the engine mirrors (gov_balance's tax and spending
lists, engine.fiscal_variables; the State Pension formulas,
engine.actual_law_denominators and the additional State Pension pin), those it
reads State Pension age and type through, and how a Scenario and a reform
reach a simulation, against the versions read here (SHA-256), so a
policyengine-uk upgrade that changes any of them fails here instead of
silently. The trajectory runs then
check, in every year, that the series built on these follow the path (benefit
uprating, a CPI-indexed threshold, employment income, the model's triple lock
from the path's statutory inputs), and record private pension income's growth.
"""

import contextlib
import hashlib
import importlib
from pathlib import Path

END_YEAR = 2042  # the private pension uprating covers at least fiscal year 2041-42

# SHA-256 of the upstream files whose horizons or formulas the engine relies on, as read for policyengine-uk 2.118.0.
UPSTREAM = {
    "policyengine_uk.parameters.gov.economic_assumptions.lag_cpi":
        "73135eebeb353f6f5c6debadde76d3988636c3277ecbd13881ec3fde53114128",
    "policyengine_uk.parameters.gov.economic_assumptions.lag_average_earnings":
        "18ea4ed4763b5d0ddd86f0d6b3365d016514f276ade9133340c10da7368ed252",
    "policyengine_uk.parameters.gov.economic_assumptions.lagged_series":
        "ead387b033f3d5d2a6c6dd41980bb418d1bf39378b6c8601ae9192c532b19917",
    "policyengine_uk.parameters.gov.economic_assumptions.create_statutory_uprating_inputs":
        "e8e745b6d9a36d73d529b558df33ad6b2936fbd880279bb97961d9e8b405360a",
    "policyengine_uk.parameters.gov.dwp.state_pension.triple_lock.create_triple_lock":
        "33473e3652ed22b6bd7f90e2e9649fafecad86ac1aec2bbec9181613d4439f30",
    "policyengine_uk.parameters.gov.contrib.create_private_pension_uprating":
        "3507c03c7388ea0cd2c45dd6368a5b4ac390a670dbf6e57567d84c6488b92ae2",
    "policyengine_uk.parameters.gov.economic_assumptions.create_economic_assumption_indices":
        "7ad33ae7b0e6d8fa12ac7149aa8a33b2b01024208fc5538f5cae39a0bdf89244",
    "policyengine_uk.utils.parameters":
        "a8b40d995666e3658e836bba2d0304478d1a9ae3a29429c82105ba9b4738383a",
    "policyengine_uk.tax_benefit_system":
        "e9ac5e7ac02fcf303ed51356a1ab133e034e71117385e1a663a099d5ecf9183d",
    # Formulas the engine mirrors.
    "policyengine_uk.variables.gov.gov_tax":
        "7b4b90ed5515315a94a1080c400ed5bf7fcff4e3395d963f8d8fd2ca78ce11b4",
    "policyengine_uk.variables.gov.gov_spending":
        "1f57caad0a12f33bb9916437f18a220177f83c4c2ebfbedea20ad25e6fe0173e",
    "policyengine_uk.variables.gov.gov_balance":
        "7cda3e7be35cdd221502809047455430a8f7faaadef48a5871fcfe284624439c",
    "policyengine_uk.variables.input.state_pension":
        "549bb8157bc8275364391210ca098f329d761d6b3288eacd2ff52b21a0d46352",
    "policyengine_uk.variables.gov.dwp.basic_state_pension":
        "80fcb72367d5cfe5f693e0d5d4fd86337028443ca0b3dab225eff96e97cf8aa3",
    "policyengine_uk.variables.gov.dwp.new_state_pension":
        "cc6ed27cede8a02b1bfc25fcbd7dbb8b05e1fe3ea3c160762bec5cfcbe7b8e2c",
    "policyengine_uk.variables.gov.dwp.additional_state_pension":
        "44b1b6728f09c2f582b457fbfa05e74bcd6c15cbbfab5dd70c69280d552287d4",
    # What the engine reads State Pension age and type through, and how a Scenario and a reform reach a simulation.
    "policyengine_uk.variables.gov.dwp.state_pension_type":
        "8da2f941fdead378366c11ef1580d3ca405bdd97c0553e921d380a36a1b1e3e9",
    "policyengine_uk.utils.state_pension_age":
        "30e07732165ce856d5db6a6d543cd3161dfa8aa928a9c241593762c4a1113e73",
    "policyengine_uk.variables.gov.dwp.is_SP_age":
        "e6ad740b675db92b635f2e34d056175e277aa947ca34e09f7d53631e7bd7b332",
    "policyengine_uk.simulation":
        "09f65db0db92789d5788ede3b9e4a788f4e3fdceb9385647460a1196363e4d3e",
    "policyengine_uk.utils.scenario":
        "a5a3f688891177b2895fd93e5f016a0bcad14ba6b9da5db52f889f0ea0a117d4",
}


class UpstreamChanged(RuntimeError):
    """policyengine-uk's builders differ from the versions read here."""


def check_upstream():
    """Raise UpstreamChanged unless every upstream file relied on is byte-identical to the recorded version."""
    changed = []
    for module, expected in UPSTREAM.items():
        path = Path(importlib.import_module(module).__file__)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changed.append(module)
    if changed:
        raise UpstreamChanged(f"policyengine-uk changed {changed}; re-read them and update model_horizon.py")


def extensions(end_year=END_YEAR):
    """What ``install`` extends: the series' upstream first and last years, and the new last year."""
    return {
        "upstream": "policyengine-uk 2.118.0",
        "end_year": end_year,
        "upstream_years": {"private_pension_index": [2020, 2034]},
    }


def install(end_year=END_YEAR):
    """Extend the private pension uprating to ``end_year`` for every system built from here on; returns what changed."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating

    check_upstream()
    # add_private_pension_uprating_factor reads this module-level list when called.
    create_private_pension_uprating.YEARS = list(range(2020, end_year + 1))
    # Systems built from here on run process_parameters() again, with the list above.
    tbs._processed_parameters_cache = None
    return extensions(end_year)


@contextlib.contextmanager
def installed(end_year=END_YEAR):
    """``install()`` for the duration of a block, then restore the upstream list (for tests)."""
    import policyengine_uk.tax_benefit_system as tbs
    from policyengine_uk.parameters.gov.contrib import create_private_pension_uprating

    years, cache = create_private_pension_uprating.YEARS, tbs._processed_parameters_cache
    try:
        yield install(end_year)
    finally:
        create_private_pension_uprating.YEARS = years
        tbs._processed_parameters_cache = cache
