"""Uprating rules and the pension-level paths they produce.

Pure functions, no PolicyEngine dependency: the pipeline and the Monte Carlo
both build on these, and the unit tests check them on synthetic inputs.

Timing follows policyengine_uk's create_triple_lock.py: the uprating that
takes effect in fiscal year ``y`` (April y) uses growth in calendar year
``y - 1``.
"""

import numpy as np

from .config import TRIPLE_LOCK_FLOOR


def rule_rate(policy, cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """Uprating rate under ``policy`` given the relevant CPI and earnings growth.

    Works elementwise on scalars or numpy arrays.
    """
    cpi = np.asarray(cpi, dtype=float)
    earnings = np.asarray(earnings, dtype=float)
    if policy == "triple_lock":
        rate = np.maximum(np.maximum(cpi, earnings), floor)
    elif policy == "double_lock":
        rate = np.maximum(cpi, earnings)
    elif policy == "earnings_link":
        rate = earnings
    elif policy == "cpi_link":
        rate = cpi
    else:
        raise ValueError(f"unknown policy {policy!r}")
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


def floor_binds(cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """True where the 2.5% floor, not CPI or earnings, sets the triple lock."""
    return np.maximum(np.asarray(cpi), np.asarray(earnings)) < floor
