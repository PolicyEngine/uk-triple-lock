"""Full central-path sensitivity to retaining the pension-age HB/guarantee gap.

Run only through the shared-host heavy_run.sh admission wrapper. This script
does not change production engine behavior or Savings Credit thresholds. The
experimental allowance is the path's guarantee plus the 2026 difference grown
by non-negative statutory September CPI (at the engine's published precision).
Both variants compute the complete horizon and both State Pension policies.
No survey arrays, identifiers, weights or individual amounts enter diagnostic receipts.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
HB_PATHS = {
    "single": "gov.dwp.housing_benefit.allowances.single.aged",
    "couple": "gov.dwp.housing_benefit.allowances.couple.aged",
    "lone_parent": "gov.dwp.housing_benefit.allowances.lone_parent.aged",
}
MIN_RECORDS = 10


def linked_levels(parameters, guarantee_levels, guarantees, base_year, years, component_growth):
    """Grow the retained 2026 component by the path's non-negative September CPI."""
    out = {}
    for family, path in HB_PATHS.items():
        guarantee = guarantees["couple" if family == "couple" else "single"]
        gap = (float(parameters.get_child(path)(f"{base_year}-06-01"))
               - float(parameters.get_child(guarantee)(f"{base_year}-06-01")))
        if gap < 0:
            raise ValueError("the experimental 2026 allowance is below its guarantee")
        out[path] = {}
        for year in years:
            gap *= 1 + max(float(component_growth[year - 1]), 0.0)
            out[path][year] = guarantee_levels[guarantee][year] + gap
    return out


def supported(count):
    return count == 0 or count >= MIN_RECORDS


def public_comparison(current, linked, positive):
    """Gate published savings and the offsets recoverable by subtracting them."""
    if set(current) != set(linked) or set(current) != set(positive):
        raise ValueError("comparison years differ")
    rows, safe = {}, True
    for year in current:
        mask = positive[year]
        total = int(np.count_nonzero(mask))
        rows[year] = {}
        contributions = {}
        safe = safe and supported(total)
        for measure in ("gross", "net"):
            original = np.asarray(current[year][measure], dtype=np.float64)
            experimental = np.asarray(linked[year][measure], dtype=np.float64)
            if original.shape != mask.shape or experimental.shape != mask.shape:
                raise ValueError("comparison household shapes differ")
            rows[year][measure] = {}
            contributions[measure] = {"current": original, "linked": experimental,
                                      "linked_minus_current": experimental - original}
            for label, vector in contributions[measure].items():
                if not np.isfinite(vector).all():
                    raise ValueError("non-finite fiscal contribution")
                count = int(np.count_nonzero((vector != 0) & mask))
                safe = safe and supported(count) and supported(total - count)
                rows[year][measure][label] = float(vector[mask].sum() / 1e9)
        # Publishing gross and net also publishes their difference. Check
        # every variant's implied offset, including the sensitivity effect,
        # even though the output contains no explicit offset cells.
        for label in contributions["gross"]:
            offset = contributions["net"][label] - contributions["gross"][label]
            if not np.isfinite(offset).all():
                raise ValueError("non-finite fiscal offset contribution")
            count = int(np.count_nonzero((offset != 0) & mask))
            safe = safe and supported(count) and supported(total - count)
    if not safe:
        rows = {year: {measure: {label: None for label in cells}
                       for measure, cells in measures.items()}
                for year, measures in rows.items()}
    return {"disclosure_status": "available" if safe else "withheld_linked_family",
            "uk_saving_bn": rows}


def alignment_digest(values):
    """Hash array values, including enum/string values rather than object pointers."""
    digest = hashlib.sha256()
    for value in values:
        array = np.asarray(value)
        if array.dtype.hasobject:
            array = array.astype(str)
        digest.update(str((array.dtype.str, array.shape)).encode())
        digest.update(array.tobytes())
    return digest.digest()


def alignment(simulation, year):
    """Return only a transient fingerprint and positive-weight mask."""
    income = simulation.calculate("household_net_income", year)
    weights = np.asarray(income.weights.to_numpy())
    digest = alignment_digest((simulation.calculate("household_id", year).to_numpy(), weights,
                               simulation.calculate("age", year).to_numpy(),
                               simulation.calculate("state_pension_type", year).to_numpy()))
    return digest, weights > 0


@contextmanager
def experimental_builder(engine, enabled, spec):
    original = engine.pension_credit_levels

    def builder(parameters, earnings, decimals):
        guarantees = original(parameters, earnings, decimals)
        return {**guarantees, **linked_levels(parameters, guarantees,
                engine.PENSION_CREDIT_GUARANTEE, engine.BASE_YEAR, engine.HORIZON,
                engine.september_cpi(spec))}

    if enabled:
        engine.pension_credit_levels = builder
    try:
        yield
    finally:
        engine.pension_credit_levels = original


def run_variant(engine, spec, enabled, reference_alignment, positive):
    """Run both policies, checking ordering and the applied experimental rates."""
    original_totals = engine.totals
    captured, calls = [], []

    def totals(simulation, years):
        if list(years) != list(engine.HORIZON):
            raise RuntimeError("every fiscal year must be calculated")
        if enabled:
            parameters = simulation.tax_benefit_system.parameters
            guarantees = {path: {year: float(parameters.get_child(path)(f"{year}-06-01"))
                                for year in years}
                          for path in engine.PENSION_CREDIT_GUARANTEE.values()}
            expected = linked_levels(parameters, guarantees, engine.PENSION_CREDIT_GUARANTEE,
                                     engine.BASE_YEAR, years, engine.september_cpi(spec))
            for path, levels in expected.items():
                family = next(family for family, hb_path in HB_PATHS.items() if hb_path == path)
                guarantee = engine.PENSION_CREDIT_GUARANTEE["couple" if family == "couple" else "single"]
                for year, level in levels.items():
                    applied = float(parameters.get_child(path)(f"{year}-06-01"))
                    if applied < guarantees[guarantee][year]:
                        raise engine.PathNotFollowed("experimental HB allowance is below its guarantee")
                    if not np.isclose(applied, level, rtol=0, atol=1e-9):
                        raise engine.PathNotFollowed("experimental HB allowance was not applied")
        result = original_totals(simulation, years)
        for year in years:
            fingerprint, mask = alignment(simulation, year)
            if year in reference_alignment:
                if reference_alignment[year] != fingerprint or not np.array_equal(positive[year], mask):
                    raise RuntimeError("variant population, ordering or weights differ")
            else:
                reference_alignment[year], positive[year] = fingerprint, mask
        calls.append(True)
        return result

    engine.totals = totals
    try:
        with experimental_builder(engine, enabled, spec):
            result = engine.run_path(spec, _support_callback=captured.append)
    finally:
        engine.totals = original_totals
    if len(calls) != 2 or len(captured) != 1:
        raise RuntimeError("a full pair must compute both policies exactly once")
    # Keep only aggregate provenance; engine's detailed result is never written.
    model = result["model"]
    for year in engine.HORIZON:
        for measure in ("gross", "net"):
            aggregate = captured[0][year][measure].sum() / engine.BN
            if not np.isclose(aggregate, result["saving_bn"][year][measure], rtol=0, atol=1e-6):
                raise RuntimeError("transient fiscal contributions do not match engine totals")
    del result
    gc.collect()
    return captured.pop(), model


def write_receipt(path, payload):
    """Owner-only output, always below this workspace's ignored cache."""
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / ".cache"):
        raise ValueError("--output must be inside the assigned workspace's .cache directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".cache/hb-link-comparison.json")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    # Fail on an invalid destination before any possibility of a model load.
    if not args.output.resolve().is_relative_to(ROOT / ".cache"):
        parser.error("--output must be inside this workspace's .cache directory")
    if not args.execute:
        print("Planned: two full central-path EFRS pairs (current and experimental HB link); no model loaded.")
        return 0
    if os.environ.get("HEAVY_CALLER") != "uk-triple-lock":
        parser.error("launch through heavy_run.sh with HEAVY_CALLER=uk-triple-lock")
    from triple_lock import host, jobs

    receipt = {"status": "started", "at": datetime.now(timezone.utc).isoformat(),
               "interpretation": "method sensitivity within the installed certified engine; no production change",
               "experimental_method": "HB aged allowance = path guarantee + retained 2026 difference grown by non-negative statutory September CPI",
               "savings_credit_threshold": "unchanged", "host_admissions": []}
    try:
        # Parameter/system construction and dataset materialization occur only
        # after this existing engine admission rule has admitted the host.
        receipt["host_admissions"].append(jobs.host_admission(40, "before_hb_link_model_imports"))
        from triple_lock import central, engine, trajectories

        spec = {key: value for key, value in trajectories.central_spec(central.central_path()).items()
                if key not in ("id", "label", "source")}
        spec.update(dataset=engine.datasets.resolve(), demography="both", retyped_level="kept")
        if not engine.datasets.provenance(spec["dataset"])["certified"]:
            raise RuntimeError("the installed bundle does not certify this EFRS pair")
        receipt.update(spec=spec, engine_semantics=engine.engine_semantics(),
                       engine_hashes=engine.engine_hashes(), packages=engine.package_versions(),
                       diagnostic_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       full_fiscal_years=list(engine.HORIZON), full_pair_count=2,
                       policy_calculation_count=4, cached_results_reused=False)
        fingerprints, positive = {}, {}
        current, model = run_variant(engine, spec, False, fingerprints, positive)
        receipt["host_admissions"].append(jobs.host_admission(40, "before_hb_link_experimental_pair"))
        linked, linked_model = run_variant(engine, spec, True, fingerprints, positive)
        if model != linked_model:
            raise RuntimeError("variant dataset/model provenance differs")
        if engine.engine_hashes() != receipt["engine_hashes"]:
            raise RuntimeError("engine source changed during the comparison")
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != receipt["diagnostic_sha256"]:
            raise RuntimeError("diagnostic source changed during the comparison")
        receipt.update(status="completed", model=model,
                       comparison=public_comparison(current, linked, positive))
    except host.HostSaturated as error:
        receipt.update(status="refused", reason=str(error),
                       refusal=error.host_admission)
        write_receipt(args.output, receipt)
        print(str(error), file=sys.stderr)
        return 75
    except Exception as error:
        # Model errors can embed survey values; do not publish their messages.
        receipt.update(status="failed", exception_type=type(error).__name__)
        write_receipt(args.output, receipt)
        print(f"comparison failed ({type(error).__name__}); no survey details written", file=sys.stderr)
        return 1
    write_receipt(args.output, receipt)
    print(f"Completed aggregate-only comparison: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
