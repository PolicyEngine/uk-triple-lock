"""The two uprating rules and the pension-level paths they produce.

Pure functions, no PolicyEngine dependency: every module builds on these, and
the unit and property tests check them on synthetic inputs.

Timing follows policyengine_uk's create_triple_lock.py: the uprating that
takes effect in fiscal year ``y`` (April y) uses growth in the year ``y - 1``.
"""

import numpy as np

from .config import POLICIES, SWITCH_YEAR, TRIPLE_LOCK_FLOOR, ZERO_FLOOR


def triple_lock_rate(cpi, earnings):
    """max(CPI, earnings, 2.5%), elementwise."""
    return np.maximum(np.maximum(np.asarray(cpi, dtype=float), np.asarray(earnings, dtype=float)), TRIPLE_LOCK_FLOOR)


def burnham_floor_rate(cpi):
    """The rise the Burnham plan guarantees before any top-up to its earnings path: max(CPI, 2.5%)."""
    return np.maximum(np.asarray(cpi, dtype=float), TRIPLE_LOCK_FLOOR)


def rates_matrix(policy, cpi, earnings, uprating_years=None, decimals=None, switch_year=SWITCH_YEAR):
    """Rates for every draw and year, arrays (n_draws, n_years); 1-d inputs are one draw.

    Column j of ``cpi`` and ``earnings`` is the growth that sets uprating year
    ``uprating_years[j]``. Years before ``switch_year`` follow the triple lock; with
    ``uprating_years`` None the Burnham plan applies from the first column. The
    Burnham plan is path dependent: each April the pension rises by at least
    max(CPI, 2.5%), and it never falls below an earnings link started from its
    level in the year before the switch:

        L_t = max(L_{t-1} (1 + max(CPI, 2.5%)), A_t),  A_t = A_{t-1} (1 + earnings)

    No rule cuts the cash pension (both floors are above zero). ``decimals``
    rounds each year's rate as policyengine-uk does (3 dp); the top-up to the
    earnings path is rounded up, so rounding never leaves the pension below it.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    cpi = np.atleast_2d(np.asarray(cpi, dtype=float))
    earnings = np.atleast_2d(np.asarray(earnings, dtype=float))
    n, m = cpi.shape
    switched = np.ones(m, dtype=bool) if uprating_years is None else np.asarray(uprating_years) >= switch_year

    def rnd(r):
        return np.round(r, decimals) if decimals is not None else r

    def rnd_up(r):
        if decimals is None:
            return r
        scale = 10**decimals
        return np.ceil(np.round(r * scale, 9)) / scale

    tl = rnd(np.maximum(triple_lock_rate(cpi, earnings), ZERO_FLOOR))
    if policy == "triple_lock":
        return tl
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
        floor_rate = rnd(np.maximum(burnham_floor_rate(cpi[:, j]), ZERO_FLOOR))
        out[:, j] = np.maximum(floor_rate, rnd_up(anchor / level - 1))
        level = level * (1 + out[:, j])
    return out


def uprating_path(policy, cpi_by_year, earnings_by_year, years, decimals=None):
    """{uprating year: rate}, using growth in the preceding year."""
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


def floor_binds(cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """True where the 2.5% floor, not CPI or earnings, sets the triple lock."""
    return np.maximum(np.asarray(cpi), np.asarray(earnings)) < floor
