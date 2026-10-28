"""Reconstruct retained paths using the macro bytes their results actually record.

The pre-Budget results and older pilot share these macro input hashes. Their
draw-reproduction tests must keep using those bytes after live inputs advance.
Only the seven changed aggregate input files are archived, as deterministic gzip
members; every decompressed file must match the source results' own provenance.
No historical Git objects, model source archive or survey data are needed.

The context also accepts a future rebuilt source whose hashes match live inputs.
It never changes a production file, scoring rule, draw or assertion tolerance.
"""

from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "tests/fixtures/pre-budget-macro-inputs"
MANIFEST = json.loads((ARCHIVE / "manifest.json").read_text())
ARCHIVED_INPUTS = (
    "data/obr_central_forecast.csv",
    "data/obr_forecast_errors.csv",
    "data/triple_lock_actual_inputs.csv",
    "data/raw/ons_kac3_awe_total_pay_3m_yoy.csv",
    "data/raw/ons_d7g7_cpi_annual_rate.csv",
    "data/raw/ons_d7bt_cpi_index.csv",
    "data/raw/ons_kab9_awe_total_pay.csv",
)
UNCHANGED_INPUTS = (
    "data/obr_outturn_crosscheck.csv",
    "data/raw/ons_dtwm_compensation_of_employees.csv",
    "data/raw/ons_royk_employers_social_contributions.csv",
    "data/raw/ons_mgrz_employment_16plus.csv",
    "data/raw/ons_mgrq_self_employed_16plus.csv",
)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def historical_macro_bytes(relative):
    """Return one exact archived macro input, checking its recorded archive pin."""
    if relative not in ARCHIVED_INPUTS:
        raise KeyError(relative)
    content = gzip.decompress((ARCHIVE / (relative + ".gz")).read_bytes())
    assert digest(content) == MANIFEST["input_sha256"][relative], \
        f"archived historical macro input changed: {relative}"
    return content


@contextmanager
def macro_inputs_for(source, monkeypatch, tmp_path):
    """Scope loaders to this source's authenticated macro vintage; yield its root.

    A repository-shaped temporary tree keeps provenance paths canonical for
    tests that also rebuild a historical diagnostic. References imported before
    this context still use the correct files because default-bound loader paths
    are patched on the original function objects, then restored on exit.
    """
    from triple_lock import central, config, ts_monthly

    recorded = source["provenance"]["input_hashes"]
    historical = all(recorded.get(relative) == MANIFEST["input_sha256"][relative]
                     for relative in ARCHIVED_INPUTS)
    if not historical:
        for relative in (*ARCHIVED_INPUTS, *UNCHANGED_INPUTS):
            assert digest((ROOT / relative).read_bytes()) == recorded[relative], \
                f"source results do not match live macro input: {relative}"
        yield ROOT
        return

    root = Path(tmp_path) / "historical-macro-inputs"
    for relative in ARCHIVED_INPUTS:
        content = historical_macro_bytes(relative)
        assert digest(content) == recorded[relative], \
            f"historical macro input does not match source results: {relative}"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # These remaining macro sources still have the recorded bytes in the live
    # tree. Check them too, so the archived inputs cannot conceal a later drift.
    for relative in UNCHANGED_INPUTS:
        assert digest((ROOT / relative).read_bytes()) == recorded[relative], \
            f"unchanged historical macro input changed: {relative}"

    paths = {
        "CENTRAL_FORECAST_CSV": root / "data/obr_central_forecast.csv",
        "ERROR_CSV": root / "data/obr_forecast_errors.csv",
        "ACTUALS_CSV": root / "data/triple_lock_actual_inputs.csv",
        "AWE_CSV": root / "data/raw/ons_kac3_awe_total_pay_3m_yoy.csv",
        "CPI_CSV": root / "data/raw/ons_d7g7_cpi_annual_rate.csv",
    }
    with monkeypatch.context() as patch:
        for name, path in paths.items():
            patch.setattr(config, name, path)
            if hasattr(central, name):
                patch.setattr(central, name, path)
        patch.setattr(config, "CPI_PERIOD", "2026 AUG")
        patch.setattr(central, "CPI_PERIOD", "2026 AUG")
        patch.setattr(central, "EFO_SOURCE", "OBR Economic and fiscal outlook, March 2026 "
                      "(detailed forecast tables: economy, Tables 1.6 and 1.7)")
        patch.setattr(central, "EFO_URL", "https://obr.uk/docs/d055fbf02d5b3g6jq8l2/"
                      "efo-march-2026-detailed-forecast-tables-economy.xlsx")
        patch.setattr(ts_monthly, "CPI_INDEX_CSV", root / "data/raw/ons_d7bt_cpi_index.csv")
        patch.setattr(ts_monthly, "AWE_LEVEL_CSV", root / "data/raw/ons_kab9_awe_total_pay.csv")
        patch.setattr(ts_monthly, "BINDING_AWE_RELEASE_DATE", "2026-09-15")
        patch.setattr(central._rows, "__defaults__", (paths["CENTRAL_FORECAST_CSV"],))
        patch.setattr(central.central_path, "__defaults__", (paths["CENTRAL_FORECAST_CSV"],))
        patch.setattr(central.statutory_inputs, "__defaults__",
                      (paths["AWE_CSV"], paths["CPI_CSV"], paths["CENTRAL_FORECAST_CSV"]))
        patch.setattr(central.september_cpi_history, "__defaults__", (paths["ACTUALS_CSV"],))
        yield root
