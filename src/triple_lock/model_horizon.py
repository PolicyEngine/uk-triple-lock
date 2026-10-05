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

Built for the central path, the processed parameter tree is identical with
and without the old extensions of the indices, the fiscal-year conversion and
the lagged series on every date to 2039 (they first differ in 2040);
extending the private pension uprating changes it from 2036. A Scenario cannot
do this: its parameter changes are applied after ``reset_parameters()`` and
before ``process_parameters()``, which rebuilds these series from the builders.

``install()`` first checks the upstream files whose horizons this relies on
against the versions read here (SHA-256), so a policyengine-uk upgrade that
changes any of them fails here instead of silently. The trajectory runs then
check, in every year, that the series built on these follow the path (benefit
uprating, a CPI-indexed threshold, employment income, the model's triple lock
from the path's statutory inputs), and record private pension income's growth.
"""

import contextlib
import hashlib
import importlib
from pathlib import Path

END_YEAR = 2042  # the private pension uprating covers at least fiscal year 2041-42

# SHA-256 of the upstream files whose horizons the engine relies on, as read for policyengine-uk 2.118.0.
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
