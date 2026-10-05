"""Static population ageing, shared by every policy on a dataset.

Survey records represent people of the same age in successive fiscal years,
not surviving individuals. Household weights follow age/sex projection growth
relative to the calibrated survey margins. All record arrays stay in .cache.
"""

import csv
import hashlib
import importlib.metadata
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.optimize import least_squares

from .config import REPO
from .cohorts import (birth_dates_from_age, cohort_type, represent_topcoded_ages,
                      within_year_birth_months)

PROJECTION = REPO / "data" / "ons_npp_2024_uk_age_sex.csv"
PRIVATE_CACHE = REPO / ".cache" / "demography"
RATIO_BOUNDS = (0.2, 5.0)
REL_TOL = 1e-6
MODES = ("frozen", "reweight", "types", "both")
AGE_BANDS = tuple([(a, a + 5) for a in range(0, 60, 5)]
                  + [(a, a + 1) for a in range(60, 80)]
                  + [(80, 85), (85, 90), (90, 106)])


class InfeasibleTargets(ValueError):
    """The supplied household support/bounds cannot achieve the target cells."""


class DemographicInputs(dict):
    """The existing pin mapping with a private mode for readback validation."""

    def __init__(self, values, mode, original_types, original_asp, calibration_year):
        super().__init__(values)
        self.demography_mode = mode
        self.original_types = original_types
        self.original_asp = original_asp
        self.calibration_year = calibration_year


def age_cells(ages, is_female):
    ages, female = np.asarray(ages), np.asarray(is_female, dtype=bool)
    if ages.shape != female.shape or not np.isfinite(ages).all() or np.any(ages < 0):
        raise ValueError("ages must be nonnegative and finite, with matching sex")
    ages = np.minimum(ages, 105)  # group genuine older ages in the 105+ cell only
    bands = np.searchsorted([hi for _, hi in AGE_BANDS], ages, side="right")
    return bands + female.astype(int) * len(AGE_BANDS)


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
    """
    base = np.asarray(base_weights, dtype=float)
    target = np.asarray(targets, dtype=float)
    a = sparse.csr_matrix(incidence, dtype=float)
    lo, hi = bounds
    if (base.ndim != 1 or a.shape != (len(target), len(base))
            or not np.isfinite(base).all() or np.any(base <= 0)
            or not np.isfinite(target).all() or np.any(target < 0)
            or not np.isfinite(a.data).all() or np.any(a.data < 0)
            or not 0 < lo <= 1 <= hi):
        raise ValueError("invalid calibration arrays or ratio bounds")
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

    fit = least_squares(residual, np.zeros(active.sum()), jac=jacobian,
                        ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=1000)
    result, _ = weights(fit.x)
    result *= total
    err = np.max(np.abs(np.asarray(a @ result).ravel()[active] / target[active] - 1))
    if err > rtol:
        raise InfeasibleTargets(f"bounded household rake did not converge (relative error {err:.3g})")
    return result


def projection_totals(path=PROJECTION):
    """{midyear: 2 x 106 sex/single-age population array}."""
    out = {}
    with open(path, newline="") as stream:
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


def pension_components(reported, types, basic_cap, new_cap):
    """Data-year identity, including residual protected payments on NEW records.

    A synthetic re-typed record keeps its reported total but repartitions it
    at the corresponding data-year ceiling. It does not carry an old BASIC
    residual on top of a newly capped NEW amount.
    """
    amount, types = np.asarray(reported, dtype=float), np.asarray(types).astype(str)
    if np.any(amount < 0) or not np.isfinite(amount).all() or min(basic_cap, new_cap) <= 0:
        raise ValueError("invalid reported State Pension or ceilings")
    basic = np.where(types == "BASIC", np.minimum(amount, basic_cap), 0)
    new = np.where(types == "NEW", np.minimum(amount, new_cap), 0)
    additional = np.where(types != "NONE", np.maximum(amount - basic - new, 0), 0)
    return basic, new, additional


def _array(sim, name, year):
    return np.asarray(sim.calculate(name, year).to_numpy())


def _survey_array(sim, entity, name, year):
    """Original dataset inputs, unaffected by pins already applied to this sim."""
    return np.asarray(getattr(sim.dataset[year], entity)[name].to_numpy())


def _fingerprint(arrays, metadata):
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode())
    for array in arrays:
        a = np.ascontiguousarray(array)
        digest.update(str(a.dtype).encode())
        digest.update(str(a.shape).encode())
        digest.update(a.tobytes())
    for source in (Path(__file__), Path(__file__).with_name("cohorts.py"), PROJECTION):
        digest.update(source.read_bytes())
    return digest.hexdigest()


def _dataset_demography(sim, years, mode, calibration_year=None):
    """Cache only dataset-driven inputs; CPI and reform parameters never enter."""
    data_year = int(min(sim.dataset.years))
    # The certified dataset may publish a calibration year separately from its
    # survey year. Otherwise its first weight year is the explicit anchor.
    if calibration_year is None:
        calibration_year = (getattr(sim.dataset, "calibration_year", None) or
                            min((y for y in sim.dataset.years if y >= 2024), default=2024))
    calibration_year = int(calibration_year)
    if not 2024 <= calibration_year <= 2040:
        raise ValueError("ONS fiscal population supports calibration years 2024..2040")
    if calibration_year not in sim.dataset.years:
        raise ValueError("dataset has no stored weight year covered by the ONS projection (2024 onward)")
    ages = _survey_array(sim, "person", "age", data_year)
    female = _array(sim, "is_female", data_year).astype(bool)
    person_ids = _survey_array(sim, "person", "person_id", data_year)
    household_ids = _survey_array(sim, "household", "household_id", calibration_year)
    if not np.array_equal(person_ids, _array(sim, "person_id", data_year)) or not np.array_equal(
            household_ids, _array(sim, "household_id", calibration_year)):
        raise ValueError("dataset and model record orders differ")
    member_ids = _survey_array(sim, "person", "person_household_id", data_year)
    index = {v: i for i, v in enumerate(household_ids)}
    membership = np.array([index[v] for v in member_ids], dtype=int)
    benunit_ids = _survey_array(sim, "benunit", "benunit_id", data_year)
    member_units = _survey_array(sim, "person", "person_benunit_id", data_year)
    unit_index = {v: i for i, v in enumerate(benunit_ids)}
    unit_membership = np.array([unit_index[v] for v in member_units], dtype=int)
    unit_min = np.full(len(benunit_ids), len(household_ids), dtype=int)
    unit_max = np.full(len(benunit_ids), -1, dtype=int)
    np.minimum.at(unit_min, unit_membership, membership)
    np.maximum.at(unit_max, unit_membership, membership)
    if np.any(unit_min != unit_max):
        raise ValueError("each benefit unit must belong to one household and contain a person")
    weights = _survey_array(sim, "household", "household_weight", calibration_year).astype(float)
    person_weights = weights[membership]
    dataset_id = str(getattr(sim.dataset, "name", type(sim.dataset).__name__))
    native_weights = ({y: _array(sim, "household_weight", y).astype(float) for y in years}
                      if mode in ("frozen", "types") else {})
    key = _fingerprint((ages, female, person_ids, membership, unit_membership, unit_min, weights, *native_weights.values()),
                       {"dataset": dataset_id, "data_year": data_year, "anchor": calibration_year,
                        "years": list(years), "mode": mode, "bounds": RATIO_BOUNDS,
                        "model_version": importlib.metadata.version("policyengine-uk")})
    PRIVATE_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(PRIVATE_CACHE, 0o700)
    path = PRIVATE_CACHE / f"{key}.npz"
    if path.exists():
        with np.load(path, allow_pickle=False) as saved:
            return {k: saved[k] for k in saved.files}, data_year, calibration_year
    projection = projection_totals()
    base_population = fiscal_population(calibration_year, projection)
    represented = represent_topcoded_ages(
        ages, female, person_ids, person_weights,
        {bool(sex): {age: base_population[sex, age] for age in range(80, 106)} for sex in range(2)},
        dataset_id=dataset_id)
    months = within_year_birth_months(person_ids, represented, female, person_weights)
    incidence = household_incidence(membership, age_cells(represented, female), len(weights))
    margins = np.asarray(incidence @ weights).ravel()
    reference = projection_cells(base_population)
    arrays = {"age": represented, "birth_months": months, "membership": membership,
              "base_weights": weights, "is_female": female, "benunit_households": unit_min}
    for flag in ("is_household_head", "is_benunit_head"):
        if flag in sim.dataset[data_year].person:
            arrays[f"flag_{flag}"] = _survey_array(sim, "person", flag, data_year).astype(bool)
    for y in years:
        target = anchored_targets(margins, reference, projection_cells(fiscal_population(y, projection)))
        arrays[f"targets_{y}"] = target
        arrays[f"weights_{y}"] = (rake_households(weights, incidence, target, rtol=REL_TOL / 10)
                                   if mode in ("reweight", "both") else
                                   native_weights[y])
    # Each process uses a unique temporary name; completed cache files are
    # atomically installed and never returned as public job results.
    fd, name = tempfile.mkstemp(prefix=f"{key}-", suffix=".tmp.npz", dir=PRIVATE_CACHE)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.savez_compressed(stream, **arrays)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return arrays, data_year, calibration_year


def pinned_inputs(sim, years, sep_cpi, mode="both", calibration_year=None):
    """Prepare all private inputs; return the engine's existing pin contract."""
    if mode not in MODES:
        raise ValueError(f"unknown demography mode: {mode}")
    years = sorted(set(int(y) for y in years))
    data_year = int(min(sim.dataset.years))
    frozen_type = _array(sim, "state_pension_type", data_year).astype(str)
    frozen_asp = _array(sim, "additional_state_pension", data_year).astype(float)
    reported = _array(sim, "state_pension_reported", data_year).astype(float)
    arrays, data_year, anchor = _dataset_demography(sim, years, mode, calibration_year)
    out = {"age": {}, "household_weight": {}, "person_weight": {},
           "state_pension_type": {}, "additional_state_pension": {}}
    variables = sim.tax_benefit_system.variables
    if "benunit_weight" in variables:
        out["benunit_weight"] = {}
    for flag in ("is_household_head", "is_benunit_head"):
        if f"flag_{flag}" in arrays:
            out[flag] = {}
    if "months_since_last_birthday" in variables:
        out["months_since_last_birthday"] = {}
    from .engine import pin
    for y in years:
        out["age"][y] = arrays["age"]
        out["household_weight"][y] = arrays[f"weights_{y}"]
        out["person_weight"][y] = arrays[f"weights_{y}"][arrays["membership"]]
        if "benunit_weight" in out:
            out["benunit_weight"][y] = arrays[f"weights_{y}"][arrays["benunit_households"]]
        for flag in ("is_household_head", "is_benunit_head"):
            if flag in out:
                out[flag][y] = arrays[f"flag_{flag}"]
        if "months_since_last_birthday" in out:
            out["months_since_last_birthday"][y] = arrays["birth_months"]
    # Eligibility must see represented ages and the same birth draw as the
    # type classifier. Set these before querying upstream State Pension age.
    pin(sim, out)
    for variable in ("is_SP_age", "state_pension_age", "months_since_state_pension_age", "birth_year"):
        if variable in variables:
            for y in years:
                # Preserve genuine dataset inputs, clear derived values that
                # might have been cached while taking the frozen snapshot.
                if y not in sim.dataset.years or variable not in sim.dataset[y].person:
                    sim.delete_arrays(variable, y)
    p = sim.tax_benefit_system.parameters.gov.dwp.state_pension
    from policyengine_uk.model_api import WEEKS_IN_YEAR
    basic_cap = float(p.basic_state_pension.amount(data_year)) * WEEKS_IN_YEAR
    new_cap = float(p.new_state_pension.amount(data_year)) * WEEKS_IN_YEAR
    index = 1.0
    for y in range(data_year, max(years) + 1):
        if y > data_year:
            index *= 1 + max(sep_cpi[y - 1], 0.0)
        if y not in years:
            continue
        sp = _array(sim, "is_SP_age", y).astype(bool)
        if mode in ("types", "both"):
            birth = birth_dates_from_age(arrays["age"], arrays["birth_months"], y)
            types = cohort_type(birth, arrays["is_female"], sp)
            _, _, asp = pension_components(reported, types, basic_cap, new_cap)
        else:
            types, asp = np.where(sp, frozen_type, "NONE"), frozen_asp
        out["state_pension_type"][y] = types
        out["additional_state_pension"][y] = asp * index * sp
    return DemographicInputs(out, mode, frozen_type, frozen_asp, anchor), data_year


def validate_inputs(sim, pinned, years, mode="both"):
    """Read inputs back after pinning; publish only aggregate error measures."""
    arrays, _, anchor = _dataset_demography(sim, sorted(set(years)), mode, pinned.calibration_year)
    result = {"mode": mode, "calibration_year": anchor, "years": {}}
    incidence = household_incidence(arrays["membership"], age_cells(arrays["age"], arrays["is_female"]),
                                    len(arrays["base_weights"]))
    for y in years:
        for name in ("age", "state_pension_type", "additional_state_pension"):
            if not np.array_equal(_array(sim, name, y), pinned[name][y].astype(_array(sim, name, y).dtype)):
                raise RuntimeError(f"model did not read pinned {name} in {y}")
        household = _array(sim, "household_weight", y).astype(float)
        person = _array(sim, "person_weight", y).astype(float)
        if not np.array_equal(person, household[arrays["membership"]]):
            raise RuntimeError(f"person weights differ from household weights in {y}")
        if "benunit_weight" in pinned and not np.array_equal(
                _array(sim, "benunit_weight", y), household[arrays["benunit_households"]]):
            raise RuntimeError(f"benefit-unit weights differ from household weights in {y}")
        if mode in ("reweight", "both"):
            target = arrays[f"targets_{y}"]
            positive = target > 0
            error = np.max(np.abs(np.asarray(incidence @ household).ravel()[positive] / target[positive] - 1))
            # The solver uses tighter tolerance to leave room for float32
            # model storage; readback must still achieve 1e-6 overall.
            if error > REL_TOL:
                raise RuntimeError(f"ONS growth targets missed in {y}: relative error {error:.3g}")
            result["years"][y] = {"max_relative_cell_error": float(error)}
    return result


def data_year_diagnostics(sim, pinned, data_year):
    """Data-quality and accounting checks, with no record amounts or weights."""
    original = pinned.original_types
    types = _array(sim, "state_pension_type", data_year).astype(str)
    reported = _array(sim, "state_pension_reported", data_year).astype(float)
    sp = _array(sim, "is_SP_age", data_year).astype(bool)
    basic = _array(sim, "basic_state_pension", data_year).astype(float)
    new = _array(sim, "new_state_pension", data_year).astype(float)
    asp = _array(sim, "additional_state_pension", data_year).astype(float)
    identity = np.abs(basic + new + asp - reported) <= .01
    unchanged = (types == original) & (types != "NONE")
    unchanged_asp = np.abs(asp[unchanged] - pinned.original_asp[unchanged]) <= .01
    if not identity[sp].all() or not unchanged_asp.all():
        raise RuntimeError("eligible data-year State Pension accounting failed")

    def private_count(mask):
        count = int(np.count_nonzero(mask))
        return count if count == 0 or count >= 10 else None

    return {"eligible_components_identity_within_penny": True,
            "unchanged_type_additional_matches_original_within_penny": True,
            "data_year_type_changes_records": private_count(types != original),
            "positive_reports_below_model_pension_age_records": private_count((reported > 0) & ~sp),
            "all_records_components_identity_within_penny": bool(identity.all()),
            "below_pension_age_treatment": "NONE type and zero payable components; inconsistent reports are retained as data-quality exceptions"}
