"""Static population ageing (#14 section 3): the survey population a run uses, the same under every policy.

A record represents a person of its age in each fiscal year, not a surviving
individual aged forward: a 75-year-old record is a 75-year-old of 2024 in
2024-25 and of 2039 in 2039-40. Three inputs follow from that, in the
treatments config.DEMOGRAPHY_MODES names:

* **Represented ages** (every treatment but ``legacy``). Records top-coded at
  80 get a represented age from 80 to 105 (105+) by a deterministic draw on
  the anchor year's ONS single-age shares (cohorts.represent_topcoded_ages),
  and every record a fixed birthday within its year of age
  (cohorts.within_year_birth_months, upstream's own draw). Both are pinned as
  the model's ``age`` and ``months_since_last_birthday`` in every year, so the
  model's own State Pension age (``is_SP_age``, by date of birth) reads them.
* **Household weights** (``reweight``, ``both``). In the anchor year, the
  dataset's calibration year (datasets.ageing_anchor), and every year before
  it, the weights are the dataset's own, exactly: the rake never moves the
  calibrated weights. After it they are raked (bounded minimum relative
  entropy, ratios 0.2 to 5 of the anchor's) so that each age/sex cell grows
  from its anchor-year survey count as the ONS 2024-based projection's does
  (annual_weights). Person and benefit-unit weights are their household's.
* **State Pension types** (``types``, ``both``). In each year, basic for men
  born before 6 April 1951 and women born before 6 April 1953 (State Pension
  age before 6 April 2016: Pensions Act 2014 s.1(2) and s.4), new after, none
  below State Pension age, from the birth date the represented age and
  birthday give at 6 October of that year (cohorts.cohort_type). The other
  treatments hold the survey year's type.

``population`` computes these once per dataset, treatment and anchor and
caches them privately (``.cache/demography``, owner-only): the weights, ages,
birthdays, the model's State Pension age mask and the types in every year.
Every path shares the entry; a run reads the model's own ``is_SP_age`` back
against the cached mask in every year and fails if they differ
(EligibilityChanged), so a change to the model's State Pension age cannot
reuse stale types. Nothing that depends on a path is cached: the additional
State Pension follows each path's September CPI (engine.pinned_inputs).

The State Pension accounting (engine.pinned_inputs) splits each person's
reported State Pension in the data year by the year's type
(pension_components): the flat-rate part up to the type's data-year flat rate,
the rest additional pension or protected payments, which follow September CPI.
Reported State Pension counts only for people over State Pension age in the
data year (payable_reported), as the law pays it only from then.

All record arrays stay in the private cache; job results carry aggregates.
"""

import csv
import hashlib
import importlib
import importlib.metadata
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.optimize import least_squares

from .cohorts import birth_dates_from_age, cohort_type, represent_topcoded_ages, within_year_birth_months
from .config import DEMOGRAPHY_MODES, POPULATION_PROJECTION, REPO

PROJECTION = POPULATION_PROJECTION
PRIVATE_CACHE = REPO / ".cache" / "demography"
RATIO_BOUNDS = (0.2, 5.0)
REL_TOL = 1e-6
MODES = tuple(m for m in DEMOGRAPHY_MODES if m != "legacy")  # the four treatments of the factorial design
RAKED = ("reweight", "both")
COHORT_TYPES = ("types", "both")
PENSION_TYPES = ("BASIC", "NEW", "NONE")
AGE_BANDS = tuple([(a, a + 5) for a in range(0, 60, 5)]
                  + [(a, a + 1) for a in range(60, 80)]
                  + [(80, 85), (85, 90), (90, 106)])
# Survey head flags pinned so that ties among represented ages cannot move a household's head.
SURVEY_FLAGS = ("is_household_head", "is_benunit_head")
# Model variables derived from age and birthday, cleared after the pins so the model recomputes them from the
# represented ages (date_of_birth from policyengine-uk 2.119.0).
DERIVED_FROM_AGE = ("is_SP_age", "state_pension_age", "months_since_state_pension_age", "birth_year", "date_of_birth")
# The upstream files the model's State Pension age and type come from: part of the cache key.
ELIGIBILITY_MODULES = (
    "policyengine_uk.variables.gov.dwp.is_SP_age",
    "policyengine_uk.variables.gov.dwp.state_pension_age",
    "policyengine_uk.variables.gov.dwp.months_since_state_pension_age",
    "policyengine_uk.variables.gov.dwp.state_pension_type",
    "policyengine_uk.utils.state_pension_age",
    "policyengine_uk.utils.dates",
)


class InfeasibleTargets(ValueError):
    """The supplied household support/bounds cannot achieve the target cells."""


class EligibilityChanged(RuntimeError):
    """The model's State Pension age differs from the cached population's: the cached types do not apply."""


class Population(dict):
    """{name: {year: array}} model inputs to pin, with the treatment's arrays as attributes (private)."""


# ── Weights ──────────────────────────────────────────────────────────────


def age_cells(ages, is_female):
    ages, female = np.asarray(ages), np.asarray(is_female)
    if ages.shape != female.shape or not np.isfinite(ages).all() or np.any(ages < 0):
        raise ValueError("ages must be nonnegative and finite, with matching sex")
    ages = np.minimum(ages, 105)  # group genuine older ages in the 105+ cell only
    bands = np.searchsorted([hi for _, hi in AGE_BANDS], ages, side="right")
    return bands + female.astype(bool).astype(int) * len(AGE_BANDS)


def household_incidence(person_households, cells, n_households):
    """Cell-by-household person counts; each member inherits one household weight."""
    households, cells = np.asarray(person_households), np.asarray(cells)
    if households.shape != cells.shape or np.any((households < 0) | (households >= n_households)):
        raise ValueError("invalid person-to-household mapping")
    return sparse.coo_matrix((np.ones(len(cells)), (cells, households)),
                             shape=(2 * len(AGE_BANDS), n_households)).tocsr()


def rake_households(base_weights, incidence, targets, bounds=RATIO_BOUNDS, rtol=REL_TOL):
    """Bounded minimum-relative-entropy household calibration.

    Solve the entropy dual: w = w0 * clip(exp(A' lambda), lower, upper).
    The analytic Jacobian uses only interior weights. Failure to achieve the
    requested tolerance is an error, never silently relaxed or output-scaled.
    A household with no weight keeps none (Microcosm holds such records), so
    it neither moves nor supports a cell.
    """
    base = np.asarray(base_weights, dtype=float)
    target = np.asarray(targets, dtype=float)
    a = sparse.csr_matrix(incidence, dtype=float)
    lo, hi = bounds
    if (base.ndim != 1 or a.shape != (len(target), len(base))
            or not np.isfinite(base).all() or np.any(base < 0) or not base.sum() > 0
            or not np.isfinite(target).all() or np.any(target < 0)
            or not np.isfinite(a.data).all() or np.any(a.data < 0)
            or not 0 < lo <= 1 <= hi):
        raise ValueError("invalid calibration arrays or ratio bounds")
    weighted = base > 0
    if not weighted.all():
        out = np.zeros_like(base)
        out[weighted] = rake_households(base[weighted], a[:, np.flatnonzero(weighted)], target, bounds, rtol)
        return out
    margins = np.asarray(a @ base).ravel()
    if np.array_equal(margins, target):
        return base.copy()
    unsupported = margins == 0
    if np.any(target[unsupported] != 0) or np.any((target == 0) & ~unsupported):
        raise InfeasibleTargets("positive bounded household weights cannot achieve these cells")
    if np.any(target < margins * lo * (1 - rtol)) or np.any(target > margins * hi * (1 + rtol)):
        raise InfeasibleTargets("target cells exceed household weight bounds")
    active = ~unsupported
    total = base.sum()
    c = a[active].multiply((total / target[active])[:, None]).tocsr()
    wn = base / total
    log_lo, log_hi = np.log(lo), np.log(hi)

    def weights(lam):
        z = np.asarray(c.T @ lam).ravel()
        return wn * np.exp(np.clip(z, log_lo, log_hi)), (z >= log_lo) & (z <= log_hi)

    def residual(lam):
        w, _ = weights(lam)
        return np.asarray(c @ w).ravel() - 1

    def jacobian(lam):
        w, interior = weights(lam)
        return (c.multiply(w * interior) @ c.T).toarray()

    def missed(lam):
        w, _ = weights(lam)
        return float(np.max(np.abs(np.asarray(a @ (w * total)).ravel()[active] / target[active] - 1)))

    fit = least_squares(residual, np.zeros(active.sum()), jac=jacobian,
                        ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=1000)
    lam = fit.x
    if not missed(lam) <= rtol:  # (a NaN miss counts as a miss)
        # Least squares on the residual can stall where weights sit on their bounds (the residual is not smooth
        # there). The problem is convex, so maximise its concave dual instead, with Newton steps and a line search:
        # the same unique solution, reached from where least squares stopped.
        def dual(lam):
            z = np.asarray(c.T @ lam).ravel()
            r = np.exp(np.clip(z, log_lo, log_hi))
            # Each weight's conjugate of the bounded relative entropy r log r - r + 1 on [lo, hi]. A trial step so
            # long that this overflows gives NaN, which the line search rejects.
            with np.errstate(over="ignore", invalid="ignore"):
                return float(lam.sum() - wn @ (r * z - (r * np.log(r) - r + 1)))

        for _ in range(500):
            w, interior = weights(lam)
            gradient = 1 - np.asarray(c @ w).ravel()
            if missed(lam) <= rtol / 10:
                break
            hessian = (c.multiply(w * interior) @ c.T).toarray()
            ridge = 1e-10 * max(float(np.trace(hessian)) / len(lam), 1e-300)
            newton = np.linalg.lstsq(hessian + ridge * np.eye(len(lam)), gradient, rcond=None)[0]
            current, moved = dual(lam), False
            for step in (newton, gradient):  # Newton first; the gradient if Newton cannot raise the dual
                if not gradient @ step > 0:  # not an ascent direction (or NaN)
                    continue
                t = 1.0
                while t > 1e-12 and not dual(lam + t * step) >= current + 1e-4 * t * (gradient @ step):
                    t /= 2
                if t > 1e-12:
                    lam, moved = lam + t * step, True
                    break
            if not moved:  # nothing raises the dual: stalled; the check below decides
                break
    result, _ = weights(lam)
    result *= total
    err = missed(lam)
    if not np.isfinite(lam).all() or not err <= rtol:
        raise InfeasibleTargets(f"bounded household rake did not converge (relative error {err:.3g})")
    return result


def projection_totals(path=None):
    """{midyear: 2 x 106 sex/single-age population array}."""
    out = {}
    with open(path or PROJECTION, newline="") as stream:
        for row in csv.DictReader(stream):
            year, age = int(row["year"]), int(row["age"])
            sex = {"male": 0, "female": 1}[row["sex"].lower()]
            out.setdefault(year, np.zeros((2, 106)))[sex, age] = float(row["population"])
    return out


def fiscal_population(year, projection):
    """April–March fiscal midpoint: 3/4 midyear y + 1/4 midyear y+1."""
    return 0.75 * projection[year] + 0.25 * projection[year + 1]


def projection_cells(population):
    return np.array([population[sex, lo:hi].sum()
                     for sex in range(2) for lo, hi in AGE_BANDS])


def anchored_targets(base_margins, base_projection, year_projection):
    """Keep calibrated margins; apply only ONS cell growth from that year."""
    base, reference, current = (np.asarray(x, dtype=float) for x in
                                (base_margins, base_projection, year_projection))
    if base.shape != reference.shape or base.shape != current.shape or np.any(reference <= 0):
        raise ValueError("projection cells must be positive and match calibrated margins")
    return base * (current / reference)


def annual_weights(native, anchor, incidence, growth=None, rake=True, rtol=REL_TOL):
    """{year: household weights}: the dataset's own (``native[year]``) in the anchor year and every year before it,
    whatever ``growth`` says; after it, with ``rake``, the anchor year's weights raked so that every age/sex cell's
    weighted count is its anchor-year count times ``growth[year]`` (that cell's ONS growth from the anchor year).

    The calibration year's weights are the builder's calibrated weights (uprated by the model like every year), so the
    rake never moves them, and it never runs backwards to the survey year. Without ``rake`` every year keeps the
    dataset's own.
    """
    if anchor not in native:
        raise ValueError(f"the anchor year {anchor} has no weights")
    base = np.asarray(native[anchor], dtype=float)
    margins = np.asarray(incidence @ base).ravel()
    out = {}
    for y in sorted(native):
        if y <= anchor or not rake:
            out[y] = np.asarray(native[y], dtype=float).copy()
        else:
            out[y] = rake_households(base, incidence, margins * np.asarray(growth[y], dtype=float), rtol=rtol)
    return out


# ── State Pension accounting ─────────────────────────────────────────────


def pension_components(reported, types, basic_cap, new_cap):
    """(basic, new, additional): reported State Pension split by type at the data year's flat rates.

    The flat-rate part is the reported amount up to the type's flat rate, and
    the rest is additional pension (SERPS and S2P on the basic State Pension)
    or protected payments (on the new State Pension), as policyengine-uk splits
    it. A record retyped from basic to new keeps its reported total, split at
    the new flat rate: it does not carry its basic-State-Pension residual on
    top of a new flat rate. NONE pays nothing.
    """
    amount, types = np.asarray(reported, dtype=float), np.asarray(types).astype(str)
    if np.any(amount < 0) or not np.isfinite(amount).all() or min(basic_cap, new_cap) <= 0:
        raise ValueError("invalid reported State Pension or ceilings")
    basic = np.where(types == "BASIC", np.minimum(amount, basic_cap), 0)
    new = np.where(types == "NEW", np.minimum(amount, new_cap), 0)
    additional = np.where(types != "NONE", np.maximum(amount - basic - new, 0), 0)
    return basic, new, additional


def payable_reported(reported, over_pension_age):
    """The reported State Pension the run accounts for: the survey's amount for people over State Pension age in the
    data year, nothing below it.

    No State Pension is payable before pensionable age: the new State Pension
    needs it (Pensions Act 2014 s.2(1)(a) and s.4(1)(a): "has reached
    pensionable age"), a Category A retirement pension starts on the day it is
    reached (SSCBA 1992 s.44(1)), and a survivor's inherited additional pension
    is a State Pension of their own from it (Pensions Act 2014 s.7(1)(a) and
    s.9(1)(a)), so an inheritance does not explain a report below it. A
    positive report below it is not State Pension in payment. In the Enhanced
    FRS 2024-25 (1.56.16) 40 records report one, most of them aged 65, within a
    year of State Pension age, the rest younger. Two-fifths also report
    contributory ESA, which nobody over pensionable age can get (Welfare Reform
    Act 2007 s.1(3)(c)), and two-thirds report earnings, against none and under
    a tenth of the people over State Pension age who report State Pension. They
    are reporting errors (another benefit or pension under the State Pension
    heading, or an age), and the model already pays them no State Pension
    (their type is NONE). Setting the reported amount to nil below State
    Pension age makes the accounting identity basic + new + additional =
    reported hold for every record, and moves no other figure: in
    policyengine-uk the reported amount enters nothing but the three parts.
    """
    reported = np.asarray(reported, dtype=float)
    return np.where(np.asarray(over_pension_age, dtype=bool), reported, 0.0)


# ── The cached population ────────────────────────────────────────────────


def _array(sim, name, year):
    return np.asarray(sim.calculate(name, year).to_numpy())


def _survey_array(sim, entity, name, year):
    """A dataset input as stored for ``year``, unaffected by pins applied to this sim."""
    return np.asarray(getattr(sim.dataset[year], entity)[name].to_numpy())


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def eligibility_fingerprint():
    """What the model's State Pension age and type depend on besides the inputs: the installed model (its timetable
    parameters ship with it) and the files the variables are in (ELIGIBILITY_MODULES, those this version has). A
    cached population is also read back against the model's own is_SP_age on every use (population)."""
    modules = {}
    for name in ELIGIBILITY_MODULES:
        try:
            modules[name] = _file_hash(importlib.import_module(name).__file__)
        except ImportError:
            modules[name] = None
    try:
        version = importlib.metadata.version("policyengine-uk")
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {"model_version": version, "modules": modules}


def _fingerprint(arrays, metadata):
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, default=str).encode())
    for array in arrays:
        a = np.ascontiguousarray(array)
        digest.update(str(a.dtype).encode())
        digest.update(str(a.shape).encode())
        digest.update(a.tobytes())
    for source in (Path(__file__), Path(__file__).with_name("cohorts.py"), Path(PROJECTION)):
        digest.update(Path(source).read_bytes())
    return digest.hexdigest()


def _save_private(path, arrays):
    """Install the cache file atomically, owner-only."""
    fd, name = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp.npz", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(stream, **arrays)
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def resolve_anchor(sim, anchor=None):
    """The year the treatment anchors its weights to: ``anchor`` if given, else the dataset's
    (datasets.ageing_anchor, recorded on the simulation by engine._managed), else a ``calibration_year`` the dataset
    object declares. Fails without one: a guessed year could rake calibrated weights."""
    if anchor is None:
        anchor = (getattr(sim, "triple_lock_provenance", None) or {}).get("ageing_anchor", {}).get("year")
    if anchor is None:
        anchor = getattr(sim.dataset, "calibration_year", None)
    if anchor is None:
        raise ValueError("demography requires an explicit calibration year or verified dataset calibration_year "
                         "metadata (datasets.DATASETS[...]['ageing_anchor'])")
    anchor = int(anchor)
    if not 2024 <= anchor <= 2040:
        raise ValueError("the ONS 2024-based projection supports anchor years 2024..2040")
    if anchor not in sim.dataset.years:
        raise ValueError(f"the dataset holds no weights for the anchor year {anchor}")
    if anchor < int(min(sim.dataset.years)):
        raise ValueError("the anchor year precedes the data year")
    return anchor


def _clear_derived(sim, years):
    """Clear values the model may have derived from the survey ages, keeping genuine dataset inputs."""
    variables = sim.tax_benefit_system.variables
    for variable in DERIVED_FROM_AGE:
        if variable not in variables:
            continue
        for y in years:
            if y not in sim.dataset.years or variable not in sim.dataset[y].person:
                sim.delete_arrays(variable, y)


def population(sim, years, mode, anchor=None):
    """The treatment's population inputs for ``years`` (a Population of {variable: {year: array}} to pin), pinned on
    ``sim`` already, with the arrays the accounting needs as attributes: ``types`` and ``over_pension_age``
    ({year: array}), ``survey_types``, ``survey_ages``, ``membership``, ``anchor``, ``data_year``, ``declared``
    (engine.population_treatment's {weights, ages}) and ``type_rule``.

    ``sim`` must not have been pinned: the survey arrays and the dataset's own weights are read from it. Computed once
    per dataset, treatment, anchor and model eligibility (eligibility_fingerprint) and cached privately; a later call
    reads the model's ``is_SP_age`` back against the cached mask in every year (EligibilityChanged if it differs).
    """
    if mode not in MODES:
        raise ValueError(f"unknown demography treatment {mode!r}: one of {MODES}")
    years = sorted({int(y) for y in years})
    data_year = int(min(sim.dataset.years))
    if years[0] < data_year:
        raise ValueError("population years start at the data year")
    anchor = resolve_anchor(sim, anchor)
    # The data year (its weights draw the birthday) and the anchor year (its weights are recorded and read back).
    years = sorted({*years, data_year, anchor})
    ages = _survey_array(sim, "person", "age", data_year).astype(float)
    female = _array(sim, "is_female", data_year).astype(bool)
    person_ids = _survey_array(sim, "person", "person_id", data_year)
    household_ids = _survey_array(sim, "household", "household_id", data_year)
    if not np.array_equal(person_ids, _array(sim, "person_id", data_year)) or not np.array_equal(
            household_ids, _array(sim, "household_id", data_year)):
        raise ValueError("dataset and model record orders differ")
    index = {v: i for i, v in enumerate(household_ids)}
    membership = np.array([index[v] for v in _survey_array(sim, "person", "person_household_id", data_year)],
                          dtype=int)
    benunit_ids = _survey_array(sim, "benunit", "benunit_id", data_year)
    unit_index = {v: i for i, v in enumerate(benunit_ids)}
    unit_membership = np.array([unit_index[v] for v in _survey_array(sim, "person", "person_benunit_id", data_year)],
                               dtype=int)
    unit_min = np.full(len(benunit_ids), len(household_ids), dtype=int)
    unit_max = np.full(len(benunit_ids), -1, dtype=int)
    np.minimum.at(unit_min, unit_membership, membership)
    np.maximum.at(unit_max, unit_membership, membership)
    if np.any(unit_min != unit_max):
        raise ValueError("each benefit unit must belong to one household and contain a person")
    # The dataset's own weights in every year (the model uprates them uniformly by population growth) and its own
    # State Pension types, read before anything is pinned.
    native = {y: _array(sim, "household_weight", y).astype(float) for y in years}
    survey_types = _array(sim, "state_pension_type", data_year).astype(str)
    survey_flags = {flag: _survey_array(sim, "person", flag, data_year).astype(bool)
                    for flag in SURVEY_FLAGS if flag in sim.dataset[data_year].person}
    dataset_id = str((getattr(sim, "triple_lock_provenance", None) or {}).get("dataset")
                     or getattr(sim.dataset, "name", type(sim.dataset).__name__))
    key = _fingerprint((ages, female, person_ids, membership, unit_membership, survey_types,
                        *native.values(), *survey_flags.values()),
                       {"dataset": dataset_id, "data_year": data_year, "anchor": anchor, "years": years,
                        "mode": mode, "bounds": RATIO_BOUNDS, "survey_flags": list(survey_flags),
                        "eligibility": eligibility_fingerprint()})
    PRIVATE_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PRIVATE_CACHE, 0o700)
    path = PRIVATE_CACHE / f"{key}.npz"
    cached = None
    if path.exists():
        with np.load(path, allow_pickle=False) as saved:
            cached = {k: saved[k] for k in saved.files}
    if cached is None:
        anchor_population = fiscal_population(anchor, projection := projection_totals())
        represented = represent_topcoded_ages(
            ages, female, person_ids, native[anchor][membership],
            {bool(sex): {age: anchor_population[sex, age] for age in range(80, 106)} for sex in range(2)},
            dataset_id=dataset_id)
        # Upstream's own birthday draw places records by the data year's weights, so every record that keeps its
        # survey age keeps policyengine-uk's birthday, and with it its date of birth, State Pension age and type.
        months = within_year_birth_months(person_ids, represented, female, native[data_year][membership])
        incidence = household_incidence(membership, age_cells(represented, female), len(household_ids))
        reference = projection_cells(anchor_population)
        growth = {y: projection_cells(fiscal_population(y, projection)) / reference for y in years if y > anchor}
        weights = annual_weights(native, anchor, incidence, growth, rake=mode in RAKED, rtol=REL_TOL / 10)
        cached = {"age": represented, "birth_months": months,
                  "represented_topcoding_applied": np.asarray(bool(np.any(ages == 80) and not np.any(ages > 80))),
                  "uncapped_age_fallback": np.asarray(bool(np.any(ages > 80))),
                  **{f"weights_{y}": weights[y] for y in years},
                  **({f"targets_{y}": np.asarray(incidence @ native[anchor]).ravel() * growth[y] for y in growth}
                     if mode in RAKED else {})}
    unchanged = all(np.array_equal(cached[f"weights_{y}"], native[y]) for y in years if y <= anchor)
    if not unchanged:  # the rake never moves the calibrated weights (annual_weights), checked on the cache too
        raise RuntimeError(f"the {mode} weights at or before the anchor year {anchor} are not the dataset's own")
    pins = Population(age={})
    variables = sim.tax_benefit_system.variables
    if mode in RAKED:  # the other treatments keep the dataset's own weights, unpinned
        pins["household_weight"], pins["person_weight"] = {}, {}
        if "benunit_weight" in variables:
            pins["benunit_weight"] = {}
    if "months_since_last_birthday" in variables:
        pins["months_since_last_birthday"] = {}
    for flag in survey_flags:
        pins[flag] = {}
    for y in years:
        pins["age"][y] = cached["age"]
        if mode in RAKED:
            pins["household_weight"][y] = cached[f"weights_{y}"]
            pins["person_weight"][y] = cached[f"weights_{y}"][membership]
            if "benunit_weight" in pins:
                pins["benunit_weight"][y] = cached[f"weights_{y}"][unit_min]
        if "months_since_last_birthday" in pins:
            pins["months_since_last_birthday"][y] = cached["birth_months"]
        for flag, values in survey_flags.items():
            pins[flag][y] = values
    for name, by_year in pins.items():
        for y, values in by_year.items():
            sim.set_input(name, y, values)
    # The model's State Pension age must read the represented ages and birthday, not values it derived earlier.
    _clear_derived(sim, years)
    over = {y: _array(sim, "is_SP_age", y).astype(bool) for y in years}
    if "over_pension_age_" + str(years[0]) in cached:
        changed = [y for y in years if not np.array_equal(over[y], cached[f"over_pension_age_{y}"])]
        if changed:
            raise EligibilityChanged(f"the model's State Pension age differs from the cached population's in {changed}")
    else:
        # The survey year's type, as the model gives it on the pinned ages and birthday, so types and the State
        # Pension age mask come from one birth date. Held from year to year by the survey-year treatments;
        # recomputed each year by cohort. A record that is not top-coded keeps upstream's birthday draw (on the
        # data year's weights), so its type is the one policyengine-uk gives it on the survey's own inputs; if not,
        # the run fails. (A top-coded record's type can change; in data years to about 2030 it cannot, as everyone
        # 80 and over then reached State Pension age before 6 April 2016.)
        held = cohort_type(birth_dates_from_age(cached["age"], cached["birth_months"], data_year), female,
                           over[data_year])
        # A record top-coded at 80 has another birthday stratum even when it is drawn to 80, so only the others.
        kept = (cached["age"] == ages) & ~((ages == 80) & bool(cached["represented_topcoding_applied"]))
        moved = int(np.count_nonzero((held != survey_types) & kept))
        if moved:
            raise EligibilityChanged(f"{moved} records that keep their survey age changed State Pension type in the "
                                     "data year: the pinned birthday is not policyengine-uk's")
        cached["data_year_type_changes"] = np.asarray(int(np.count_nonzero(held != survey_types)))
        for y in years:
            cached[f"over_pension_age_{y}"] = over[y]
            if mode in COHORT_TYPES:
                birth = birth_dates_from_age(cached["age"], cached["birth_months"], y)
                cached[f"types_{y}"] = cohort_type(birth, female, over[y]).astype("U5")
            else:
                cached[f"types_{y}"] = np.where(over[y], held, "NONE").astype("U5")
        _save_private(path, cached)
    pins.weights_unchanged_through_anchor = unchanged
    pins.data_year_type_changes = int(cached["data_year_type_changes"])
    pins.types = {y: cached[f"types_{y}"].astype(str) for y in years}
    pins.weights = {y: cached[f"weights_{y}"] for y in years}
    pins.over_pension_age = over
    pins.survey_types = survey_types
    pins.survey_ages = ages
    pins.membership = membership
    pins.benunit_households = unit_min
    pins.anchor = anchor
    pins.data_year = data_year
    pins.mode = mode
    pins.targets = {y: cached[f"targets_{y}"] for y in years if f"targets_{y}" in cached}
    pins.incidence = household_incidence(membership, age_cells(cached["age"], female), len(household_ids))
    pins.represented_topcoding_applied = bool(cached["represented_topcoding_applied"])
    pins.uncapped_age_fallback = bool(cached["uncapped_age_fallback"])
    pins.survey_flags = list(survey_flags)
    pins.declared = {"weights": "ons_projection" if mode in RAKED else "survey",
                     "ages": "adjusted" if not np.array_equal(cached["age"], ages) else "survey_year"}
    pins.type_rule = "cohort" if mode in COHORT_TYPES else "survey_year"
    return pins


def readback(sim, pinned, years):
    """Read the treatment's inputs back from the model after pinning; aggregate error measures only.

    Raises RuntimeError if the model does not use a pinned age, birthday, survey flag or household weight, if person
    or benefit-unit weights are not their household's, or (raked treatments) if a year after the anchor misses its
    ONS growth targets by more than REL_TOL relative.
    """
    out = {"mode": pinned.mode, "anchor": pinned.anchor, "survey_flags": pinned.survey_flags,
           "represented_topcoding_applied": pinned.represented_topcoding_applied,
           "uncapped_age_fallback": pinned.uncapped_age_fallback, "max_relative_cell_error": {}}
    for y in years:
        for name in ("age", "household_weight", "months_since_last_birthday", *pinned.survey_flags):
            if name not in pinned:
                continue
            actual = _array(sim, name, y)
            if not np.array_equal(actual, np.asarray(pinned[name][y]).astype(actual.dtype)):
                raise RuntimeError(f"the model did not read the pinned {name} in {y}")
        household = _array(sim, "household_weight", y).astype(float)
        if "household_weight" not in pinned and not np.array_equal(household, pinned.weights[y]):
            raise RuntimeError(f"the model's household weights in {y} are not the dataset's own")
        if not np.array_equal(_array(sim, "person_weight", y).astype(float), household[pinned.membership]):
            raise RuntimeError(f"person weights differ from household weights in {y}")
        if "benunit_weight" in sim.tax_benefit_system.variables and not np.array_equal(
                _array(sim, "benunit_weight", y).astype(float), household[pinned.benunit_households]):
            raise RuntimeError(f"benefit-unit weights differ from household weights in {y}")
        if y in pinned.targets:
            target = pinned.targets[y]
            positive = target > 0
            error = float(np.max(np.abs(np.asarray(pinned.incidence @ household).ravel()[positive] / target[positive]
                                        - 1)))
            # The rake solves to a tenth of this, leaving room for the model's float32 weights.
            if not error <= REL_TOL:
                raise RuntimeError(f"ONS growth targets missed in {y}: relative error {error:.3g}")
            out["max_relative_cell_error"][y] = error
    return out
