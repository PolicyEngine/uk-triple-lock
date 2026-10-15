"""Deterministic represented ages and pension cohorts, independent of policy.

Age is read at 6 October of the fiscal year, following policyengine-uk
2.118.0. Birthday stratification reproduces its ``months_since_last_birthday``
draw; pin the result before reweighting so weights cannot move birth cohorts.
The dataset fingerprint scopes the cache, while the upstream birthday hash
uses person ids and salt 2. Top-code assignment also includes the dataset id.
"""

import hashlib
from collections.abc import Mapping

import numpy as np


MALE_BASIC_CUTOFF = np.datetime64("1951-04-06", "D")
FEMALE_BASIC_CUTOFF = np.datetime64("1953-04-06", "D")
TOPCODE_AGES = np.arange(80, 106)


def _aligned(*arrays):
    values = tuple(np.asarray(a) for a in arrays)
    if any(a.ndim != 1 for a in values) or len({a.shape for a in values}) != 1:
        raise ValueError("Inputs must be aligned one-dimensional arrays")
    return values


def cohort_type(birth_dates, is_female, is_sp_age):
    """BASIC before each sex's legal cutoff; NEW after it; NONE below SPA.

    Pensions Act 2014 s.1(2) and Pensions Act 1995 Schedule 4 give the
    6 April 1951 male and 6 April 1953 female boundaries. Eligibility is an
    explicit model input: this function does not approximate pensionable age.
    """
    dates, female, eligible = _aligned(birth_dates, is_female, is_sp_age)
    dates = dates.astype("datetime64[D]")
    if np.isnat(dates).any():
        raise ValueError("Birth dates must be known")
    cutoff = np.where(female.astype(bool), FEMALE_BASIC_CUTOFF, MALE_BASIC_CUTOFF)
    return np.where(eligible.astype(bool), np.where(dates < cutoff, "BASIC", "NEW"), "NONE")


def _splitmix64_uniform(ids, salt=2):
    """The upstream 2.118.0 id hash, including its float32-safe upper bound."""
    with np.errstate(over="ignore"):
        z = np.asarray(ids).astype(np.uint64) + np.uint64(salt) * np.uint64(0x632BE59BD9B4E019)
        z = z + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        z = z ^ (z >> np.uint64(31))
    draws = (z >> np.uint64(11)).astype(np.float64) / 2.0**53
    return np.minimum(draws, 1.0 - 2.0**-24)


def within_year_birth_months(person_ids, ages, is_female, person_weights):
    """Months since birthday at 6 October, matching the upstream data draw.

    Records within each whole-age/sex stratum are ordered by the upstream id
    hash and placed at weighted midpoints. Return float32 because model inputs
    use that representation. Positive fractional ages already encode exact
    age and therefore override the draw, as upstream does.
    """
    ids, ages, female, weights = _aligned(person_ids, ages, is_female, person_weights)
    ages = ages.astype(np.float64)
    weights = weights.astype(np.float64)
    if not np.isfinite(ages).all() or (ages < 0).any():
        raise ValueError("Ages must be finite and nonnegative")
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("Weights must be finite and nonnegative")
    if len(np.unique(ids)) != len(ids):
        raise ValueError("Person ids must be unique")
    strata = np.floor(ages) * 2 + ~female.astype(bool)
    draws = _splitmix64_uniform(ids)
    order = np.lexsort((draws, strata))
    _, groups = np.unique(strata[order], return_inverse=True)
    sorted_weights = weights[order]
    totals = np.bincount(groups, weights=sorted_weights)
    starts = np.concatenate(([0.0], np.cumsum(totals)[:-1]))
    within = np.cumsum(sorted_weights) - starts[groups] - sorted_weights / 2
    group_totals = totals[groups]
    positions = np.where(group_totals > 0, within / np.where(group_totals > 0, group_totals, 1), draws[order])
    result = np.empty_like(positions)
    result[order] = np.clip(positions, 0, 1.0 - 2.0**-24)
    fraction = ages - np.floor(ages)
    return (12 * np.where(fraction > 0, fraction, result)).astype(np.float32)


def birth_dates_from_age(ages, months_since_last_birthday, reference_year):
    """Infer legal birth dates from age at 6 October of ``reference_year``.

    Matches ``policyengine_uk.utils.state_pension_age.date_of_birth``: months
    begin on the sixth, fractional grid months are spread over calendar days,
    and the legal birth date begins at or after the inferred instant. The
    upstream 0.001-day tolerance preserves boundaries after float32 storage.
    """
    ages, months = _aligned(ages, months_since_last_birthday)
    ages, months = ages.astype(np.float64), months.astype(np.float64)
    if not np.isfinite(ages).all() or (ages < 0).any():
        raise ValueError("Ages must be finite and nonnegative")
    if not np.isfinite(months).all() or (months < 0).any() or (months >= 12).any():
        raise ValueError("Months since birthday must be finite in [0, 12)")
    whole_age = np.floor(ages)
    fraction = ages - whole_age
    exact_months = 12 * whole_age + np.clip(np.where(fraction > 0, 12 * fraction, months), 0, 12 - 1e-4)
    birth = 12 * int(reference_year) + 9 - exact_months
    whole = np.floor(birth).astype(np.int64)
    sixth = (whole - 12 * 1970).astype("datetime64[M]").astype("datetime64[D]") + np.timedelta64(5, "D")
    next_sixth = (whole + 1 - 12 * 1970).astype("datetime64[M]").astype("datetime64[D]") + np.timedelta64(5, "D")
    length = (next_sixth - sixth).astype(np.int64)
    elapsed = np.ceil((birth - whole) * length - 1e-3).astype(np.int64)
    return sixth + elapsed.astype("timedelta64[D]")


def represent_topcoded_ages(ages, is_female, person_ids, person_weights, ons_shares, *, dataset_id):
    """Give records at 80 a represented age from 80 to 105 (the 105+ cell).

    ``ons_shares`` maps sex booleans (False male, True female) to mappings of
    age 80..105 to population or shares. Each sex's vector is normalised.
    Records are ordered by SHA256(dataset id, person id) and assigned using
    cumulative-weight midpoints. Each single-age weighted count differs from
    its target by at most the largest record weight in that sex. No weight
    changes, no record splits, and ages other than exactly 80 are untouched.
    If any record is older than 80, the dataset already supplies uncapped
    ages: return all original ages, including genuine 80-year-olds. This
    conservative guard avoids adding a second 80+ tail to such a dataset;
    partial top-coding cannot be inferred from ages alone.
    """
    ages, female, ids, weights = _aligned(ages, is_female, person_ids, person_weights)
    if not isinstance(ons_shares, Mapping):
        raise ValueError("ONS shares must map sex to single-age populations")
    if not np.isfinite(ages).all() or (ages < 0).any():
        raise ValueError("Ages must be finite and nonnegative")
    weights = weights.astype(np.float64)
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("Weights must be finite and nonnegative")
    if len(np.unique(ids)) != len(ids):
        raise ValueError("Person ids must be unique")
    result = ages.copy()
    if np.any(ages > 80):
        return result
    female = female.astype(bool)
    for sex in (False, True):
        indices = np.flatnonzero((ages == 80) & (female == sex))
        if not len(indices):
            continue
        shares = np.array([ons_shares[sex].get(int(age), 0.0) for age in TOPCODE_AGES], dtype=np.float64)
        if not np.isfinite(shares).all() or (shares < 0).any() or shares.sum() <= 0:
            raise ValueError("Each represented sex needs finite nonnegative 80+ shares with positive total")
        hashes = [hashlib.sha256(f"{dataset_id}\0{ids[i]}".encode()).digest() for i in indices]
        order = indices[sorted(range(len(indices)), key=lambda j: (hashes[j], str(ids[indices[j]])))]
        total = weights[order].sum()
        if total <= 0:
            raise ValueError("Each represented sex needs positive total weight")
        midpoint = (np.cumsum(weights[order]) - weights[order] / 2) / total
        cumulative = np.cumsum(shares / shares.sum())
        cumulative[-1] = 1.0
        result[order] = TOPCODE_AGES[np.minimum(np.searchsorted(cumulative, midpoint, side="right"), 25)]
    return result
