"""The two uprating rules and the pension-level paths they produce.

Pure functions, no PolicyEngine dependency: every module builds on these, and
the unit and property tests check them on synthetic inputs.

Timing follows policyengine_uk's create_triple_lock.py: the uprating that
takes effect in fiscal year ``y`` (April y) uses growth in the year ``y - 1``.
"""

import numpy as np

from .config import CENTRAL_RATE_DECIMALS, POLICIES, SWITCH_YEAR, TRIPLE_LOCK_FLOOR, ZERO_FLOOR


def round_rate(x, decimals=CENTRAL_RATE_DECIMALS):
    """``x`` to ``decimals`` places, elementwise; None leaves it unrounded. The one rounding of rates and inputs.

    Everything that takes a statutory input or a rate to 0.1 point uses this: the rules, what set each rise, the
    additional pension's September CPI and the Pension Credit guarantee's earnings. It is numpy's (half to even on
    the scaled value). Python's round() works on the exact binary value instead and disagrees at half-grid values:
    round(0.0355, 3) is 0.035 and this gives 0.036. The one exception reproduces policyengine-uk's own rounding
    (engine.model_triple_lock_rate). Scalars come back as float.
    """
    if decimals is None:
        return x
    r = np.round(np.asarray(x, dtype=float), decimals)
    return float(r) if r.ndim == 0 else r


def triple_lock_source(cpi, earnings, floor=TRIPLE_LOCK_FLOOR):
    """What set a triple-lock rise, from the inputs as the rule saw them: "floor", "earnings" or "cpi".

    The floor whenever neither input exceeds 2.5% (a tie with it included); otherwise the larger input, CPI when
    the two tie (as in April 2022, when the earnings leg was suspended). engine.rate_sources and
    trajectories.triple_lock_history both label with this.
    """
    if max(cpi, earnings) <= floor:
        return "floor"
    return "earnings" if earnings > cpi else "cpi"


def burnham_floor_source(cpi, floor=TRIPLE_LOCK_FLOOR):
    """What set a Burnham-plan rise that needed no top-up to its earnings path: "cpi" above 2.5%, else "floor"."""
    return "cpi" if cpi > floor else "floor"


def triple_lock_rate(cpi, earnings):
    """max(CPI, earnings, 2.5%), elementwise."""
    return np.maximum(np.maximum(np.asarray(cpi, dtype=float), np.asarray(earnings, dtype=float)), TRIPLE_LOCK_FLOOR)


def burnham_floor_rate(cpi):
    """The rise the Burnham plan guarantees before any top-up to its earnings path: max(CPI, 2.5%)."""
    return np.maximum(np.asarray(cpi, dtype=float), TRIPLE_LOCK_FLOOR)


def rates_matrix(policy, cpi, earnings, uprating_years=None, decimals=None, switch_year=SWITCH_YEAR, triple_lock=None):
    """Rates for every draw and year, arrays (n_draws, n_years); 1-d inputs are one draw.

    Column j of ``cpi`` and ``earnings`` is the growth that sets uprating year
    ``uprating_years[j]``. Years before ``switch_year`` follow the triple lock; with
    ``uprating_years`` None the Burnham plan applies from the first column. The
    Burnham plan is path dependent: each April the pension rises by at least
    max(CPI, 2.5%), and it never falls below an earnings link started from its
    level in the year before the switch:

        L_t = max(L_{t-1} (1 + max(CPI, 2.5%)), A_t),  A_t = A_{t-1} (1 + earnings)

    No rule cuts the cash pension (both floors are above zero). ``decimals``
    rounds the inputs, and so each year's rate, with round_rate (3 dp: 0.1
    point, the precision ONS publishes; policyengine-uk's own triple lock also
    takes 3 dp, with Python's round(), which differs only on exact half-grid
    values); the top-up to the earnings path is rounded up, so rounding never
    leaves the pension below it.

    ``triple_lock`` (same shape as ``cpi``): rates the triple lock pays instead
    of max(CPI, earnings, 2.5%), e.g. the OBR's own long-term uprating line; the
    Burnham plan follows them before the switch and anchors on the level they give.
    """
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    cpi = np.atleast_2d(np.asarray(cpi, dtype=float))
    earnings = np.atleast_2d(np.asarray(earnings, dtype=float))
    # The inputs as ONS publishes them (September CPI and May-July AWE growth to 0.1 point), so both rules see the
    # same figures and the triple lock's rate is exactly the larger input.
    cpi, earnings = round_rate(cpi, decimals), round_rate(earnings, decimals)
    n, m = cpi.shape
    switched = np.ones(m, dtype=bool) if uprating_years is None else np.asarray(uprating_years) >= switch_year

    def rnd(r):
        return round_rate(r, decimals)

    def rnd_up(r):
        if decimals is None:
            return r
        scale = 10**decimals
        return np.ceil(np.round(r * scale, 9)) / scale

    if triple_lock is None:
        tl = rnd(np.maximum(triple_lock_rate(cpi, earnings), ZERO_FLOOR))
    else:
        tl = rnd(np.broadcast_to(np.atleast_2d(np.asarray(triple_lock, dtype=float)), cpi.shape))
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


def uprating_path(policy, cpi_by_year, earnings_by_year, years, decimals=None, triple_lock_by_year=None):
    """{uprating year: rate}, using growth in the preceding year.

    ``triple_lock_by_year``: optional {uprating year: rate} the triple lock pays instead (see rates_matrix).
    """
    cpi = np.array([cpi_by_year[y - 1] for y in years])
    earnings = np.array([earnings_by_year[y - 1] for y in years])
    tl = None if triple_lock_by_year is None else np.array([triple_lock_by_year[y] for y in years])
    rates = rates_matrix(policy, cpi, earnings, list(years), decimals, triple_lock=tl)[0]
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
