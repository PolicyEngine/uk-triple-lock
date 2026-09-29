"""Uprating rules and the pension-level paths they produce.

Pure functions, no PolicyEngine dependency: the pipeline and the Monte Carlo
both build on these, and the unit tests check them on synthetic inputs.

Timing follows policyengine_uk's create_triple_lock.py: the uprating that
takes effect in fiscal year ``y`` (April y) uses growth in calendar year
``y - 1``.
"""

import numpy as np

from .config import TRIPLE_LOCK_FLOOR, ZERO_FLOOR


def unfloored_rate(policy, cpi, earnings):
    """The index a rule follows before the no-cash-cut floor (triple lock: with its 2.5%)."""
    cpi = np.asarray(cpi, dtype=float)
    earnings = np.asarray(earnings, dtype=float)
    if policy == "triple_lock":
        return np.maximum(np.maximum(cpi, earnings), TRIPLE_LOCK_FLOOR)
    if policy == "double_lock":
        return np.maximum(cpi, earnings)
    if policy == "earnings_link":
        return earnings
    if policy == "cpi_link":
        return cpi
    raise ValueError(f"unknown policy {policy!r}")


def rule_rate(policy, cpi, earnings):
    """Uprating rate under ``policy`` given the relevant CPI and earnings growth.

    No rule cuts the cash pension: every rate is floored at 0 (the triple lock
    is already floored at 2.5%). Works elementwise on scalars or numpy arrays.
    """
    rate = np.maximum(unfloored_rate(policy, cpi, earnings), ZERO_FLOOR)
    return rate if rate.ndim else float(rate)


def uprating_path(policy, cpi_by_year, earnings_by_year, years, decimals=None):
    """{uprating year: rate}, using growth in the preceding calendar year."""
    path = {}
    for year in years:
        rate = rule_rate(policy, cpi_by_year[year - 1], earnings_by_year[year - 1])
        path[year] = round(rate, decimals) if decimals is not None else rate
    return path


def cumulative_index(rates_by_year, years):
    """{year: level relative to the base year} from compounding the rates."""
    index, level = {}, 1.0
    for year in years:
        level *= 1 + rates_by_year[year]
        index[year] = level
    return index


def level_path(base_level, rates_by_year, years):
    """{year: amount} compounding ``base_level`` by each year's rate."""
    return {y: base_level * i for y, i in cumulative_index(rates_by_year, years).items()}


def zero_floor_binds(policy, cpi, earnings):
    """True where the rule's index is negative, so the no-cash-cut floor sets the rate."""
    return unfloored_rate(policy, cpi, earnings) < ZERO_FLOOR


def floor_binds(cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """True where the 2.5% floor, not CPI or earnings, sets the triple lock."""
    return np.maximum(np.asarray(cpi), np.asarray(earnings)) < floor
