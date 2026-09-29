"""Uprating rules and the pension-level paths they produce.

Pure functions, no PolicyEngine dependency: the pipeline and the Monte Carlo
both build on these, and the unit tests check them on synthetic inputs.

Timing follows policyengine_uk's create_triple_lock.py: the uprating that
takes effect in fiscal year ``y`` (April y) uses growth in calendar year
``y - 1``.
"""

import numpy as np

from .config import SWITCH_YEAR, TRIPLE_LOCK_FLOOR, ZERO_FLOOR

# Rules whose rate depends on the path so far, not just the year's growth.
PATH_RULES = {"burnham_2030", "burnham_2030_review5"}
# Policy-definition sensitivity (not a compared rule): the same floor, with the
# pension restored to the earnings path only at five-yearly reviews, the first
# in April SWITCH_YEAR + 5.
REVIEW_EVERY = 5


def unfloored_rate(policy, cpi, earnings):
    """The index a rule follows before the no-cash-cut floor (triple lock: with its 2.5%)."""
    cpi = np.asarray(cpi, dtype=float)
    earnings = np.asarray(earnings, dtype=float)
    if policy == "triple_lock":
        return np.maximum(np.maximum(cpi, earnings), TRIPLE_LOCK_FLOOR)
    if policy in ("burnham_2030", "burnham_2030_review5"):
        # The floor it guarantees (it may be topped up to the earnings path).
        return np.maximum(cpi, TRIPLE_LOCK_FLOOR)
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


def rates_matrix(policy, cpi, earnings, uprating_years=None, decimals=None):
    """Rates for every draw and year, arrays (n_draws, n_years) or (n_years,).

    Column j of ``cpi`` and ``earnings`` is the growth that sets uprating year
    ``uprating_years[j]``. Years before SWITCH_YEAR follow the triple lock
    (every alternative starts in April 2030); with ``uprating_years`` None the
    rule applies from the first column. The Burnham plan is path dependent:
    each April the pension rises by at least max(CPI, 2.5%), and it never
    falls below an earnings link started from its level in the year before
    the switch:

        L_t = max(L_{t-1} (1 + max(CPI, 2.5%)), A_t),  A_t = A_{t-1} (1 + earnings)

    ``decimals`` rounds each year's rate, as the central run does.
    """
    cpi = np.atleast_2d(np.asarray(cpi, dtype=float))
    earnings = np.atleast_2d(np.asarray(earnings, dtype=float))
    n, m = cpi.shape
    switched = np.ones(m, dtype=bool) if uprating_years is None else np.asarray(uprating_years) >= SWITCH_YEAR

    def rnd(r):
        return np.round(r, decimals) if decimals is not None else r

    def rnd_up(r):
        # Rounding a guaranteed minimum must not take the pension below it.
        if decimals is None:
            return r
        scale = 10**decimals
        return np.ceil(np.round(r * scale, 9)) / scale

    tl = rnd(rule_rate("triple_lock", cpi, earnings))
    if policy not in PATH_RULES:
        own = rnd(rule_rate(policy, cpi, earnings))
        out = np.where(switched[None, :], own, tl)
    else:
        out = np.empty((n, m))
        level = np.ones(n)
        anchor = np.ones(n)
        for j in range(m):
            if not switched[j]:
                out[:, j] = tl[:, j]
                level = level * (1 + out[:, j])
                anchor = level.copy()
                continue
            anchor = anchor * (1 + earnings[:, j])
            floor_rate = rnd(np.maximum(np.maximum(cpi[:, j], TRIPLE_LOCK_FLOOR), ZERO_FLOOR))
            year = None if uprating_years is None else uprating_years[j]
            review = policy == "burnham_2030" or (
                year is not None and year > SWITCH_YEAR and (year - SWITCH_YEAR) % REVIEW_EVERY == 0
            )
            rate = np.maximum(floor_rate, rnd_up(anchor / level - 1)) if review else floor_rate
            out[:, j] = rate
            level = level * (1 + rate)
    return out


def uprating_path(policy, cpi_by_year, earnings_by_year, years, decimals=None):
    """{uprating year: rate}, using growth in the preceding calendar year."""
    cpi = np.array([cpi_by_year[y - 1] for y in years])
    earnings = np.array([earnings_by_year[y - 1] for y in years])
    rates = rates_matrix(policy, cpi, earnings, list(years), decimals)[0]
    return {y: float(r) for y, r in zip(years, rates)}


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


def zero_floor_binds(policy, cpi, earnings, uprating_years=None):
    """True where the rule's index is negative, so the no-cash-cut floor sets the rate.

    Only switched years count (before SWITCH_YEAR every rule is the triple lock).
    """
    binds = unfloored_rate(policy, cpi, earnings) < ZERO_FLOOR
    if uprating_years is not None:
        binds = binds & (np.asarray(uprating_years) >= SWITCH_YEAR)
    return binds


def floor_binds(cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """True where the 2.5% floor, not CPI or earnings, sets the triple lock."""
    return np.maximum(np.asarray(cpi), np.asarray(earnings)) < floor
