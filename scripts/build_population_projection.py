"""Extract public UK principal NPP age/sex counts for mid-2024 to mid-2041.

The source is the exact 2024-based ONS zip used by policyengine-uk-data.
Only public population totals are written; this script never loads survey data.
Run with ``python scripts/build_population_projection.py`` (needs openpyxl).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "ons_npp_2024_uk_age_sex.csv"
MANIFEST = ROOT / "data" / "ons_npp_2024_uk_age_sex.provenance.json"
YEARS = tuple(range(2024, 2042))
COLUMNS = ("year", "sex", "age", "population")
ONS_ZIP_URL = (
    "https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/"
    "populationandmigration/populationprojections/datasets/"
    "z1zippedpopulationprojectionsdatafilesuk/2024based/uk.zip"
)
ONS_PAGE_URL = (
    "https://www.ons.gov.uk/peoplepopulationandcommunity/"
    "populationandmigration/populationprojections/datasets/"
    "z1zippedpopulationprojectionsdatafilesuk"
)
UPSTREAM_PATH = "policyengine_uk_data/targets/sources/ons_demographics.py"
UPSTREAM_COMMIT = "b45c373c6459762930d43a11bed5eaaec4131e14"
UPSTREAM_URL = (
    "https://github.com/PolicyEngine/policyengine-uk-data/blob/"
    + UPSTREAM_COMMIT
    + "/"
    + UPSTREAM_PATH
)
MEMBER_SUFFIX = "uk_ppp_machine_readable.xlsx"


def projection_member(names: Iterable[str]) -> str:
    """Choose the principal workbook unambiguously, never a variant workbook."""
    matches = [name for name in names if name.endswith(MEMBER_SUFFIX)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one UK principal workbook, found {len(matches)}")
    return matches[0]


def source_age_span(value: object) -> tuple[int, int | None]:
    """Preserve source age intervals so missing or overlapping tails are caught."""
    label = str(value).strip()
    if re.fullmatch(r"\d+", label):
        age = int(label)
        if age < 105:
            return age, age
    if label == "105 - 109":
        return 105, 109
    if label == "110 and over":
        return 110, None
    if label in ("105+", "105 and over"):
        return 105, None
    raise ValueError(f"Unrecognised ONS age label: {value!r}")


def _validate_age_spans(spans: set[tuple[int, int | None]], sex: str) -> None:
    expected = {(age, age) for age in range(105)}
    tail = spans - expected
    complete_tail = tail in ({(105, None)}, {(105, 109), (110, None)})
    if not expected.issubset(spans) or not complete_tail:
        raise ValueError(f"Incomplete or overlapping single-age/105+ coverage for {sex}")


def parse_population_rows(rows: Iterable[Iterable[object]]) -> list[dict[str, object]]:
    """Parse the Population sheet, preserving every sex/age/year population.

    Ages 0--104 are single years. ONS publishes 105--109 and 110+ separately;
    their sum becomes the open-ended age=105 cell, without losing anyone.
    Fail closed when source layout, coverage or numeric values change.
    """
    iterator = iter(rows)
    try:
        headers = [str(value).strip() for value in next(iterator)]
    except StopIteration as error:
        raise ValueError("Population sheet is empty") from error
    required = ["Sex", "Age", *map(str, YEARS)]
    for label in required:
        if headers.count(label) != 1:
            raise ValueError(f"Missing or duplicate Population column: {label}")
    positions = {label: headers.index(label) for label in required}
    source_spans: dict[str, set[tuple[int, int | None]]] = {"female": set(), "male": set()}
    populations: dict[tuple[int, str, int], int] = {}
    sex_names = {"Females": "female", "Males": "male"}
    for raw in iterator:
        values = list(raw)
        if not any(value is not None for value in values):
            continue
        if len(values) <= max(positions.values()):
            raise ValueError("Population row is shorter than the required columns")
        source_sex = values[positions["Sex"]]
        if source_sex not in sex_names:
            raise ValueError(f"Unrecognised ONS sex label: {source_sex!r}")
        sex = sex_names[source_sex]
        span = source_age_span(values[positions["Age"]])
        if span in source_spans[sex]:
            raise ValueError(f"Duplicate source age cell for {sex}")
        source_spans[sex].add(span)
        age = min(span[0], 105)
        for year in YEARS:
            population = values[positions[str(year)]]
            if (
                isinstance(population, bool)
                or not isinstance(population, (int, float))
                or not math.isfinite(population)
                or population < 0
                or population != int(population)
            ):
                raise ValueError(f"Invalid population for {year}, {sex}, age {age}")
            key = year, sex, age
            populations[key] = populations.get(key, 0) + int(population)
    for sex, spans in source_spans.items():
        _validate_age_spans(spans, sex)
    return [
        {"year": year, "sex": sex, "age": age, "population": populations[year, sex, age]}
        for year in YEARS
        for sex in ("female", "male")
        for age in range(106)
    ]


def parse_zip(data: bytes) -> tuple[list[dict[str, object]], str, bytes]:
    import openpyxl

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        member = projection_member(archive.namelist())
        workbook_bytes = archive.read(member)
    workbook = openpyxl.load_workbook(io.BytesIO(workbook_bytes), read_only=True, data_only=True)
    try:
        rows = parse_population_rows(workbook["Population"].iter_rows(values_only=True))
    finally:
        workbook.close()
    return rows, member, workbook_bytes


def csv_bytes(rows: list[dict[str, object]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def build(source_zip: Path | None = None) -> dict[str, object]:
    if source_zip is None:
        request = urllib.request.Request(
            ONS_ZIP_URL, headers={"User-Agent": "PolicyEngine uk-triple-lock public NPP build"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            source_bytes = response.read()
            retrieved_url = response.url
    else:
        source_bytes = source_zip.read_bytes()
        retrieved_url = ONS_ZIP_URL
    rows, member, workbook_bytes = parse_zip(source_bytes)
    data = csv_bytes(rows)
    manifest = {
        "title": "ONS 2024-based principal population projection, United Kingdom",
        "publisher": "Office for National Statistics",
        "edition": "2024-based",
        "release_date": "2026-04-28",
        "publisher_correction_date": "2026-05-01",
        "publisher_correction_note": "2062-63 column header corrected; requested 2024-2041 data unaffected",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": ONS_ZIP_URL,
        "retrieved_url": retrieved_url,
        "dataset_page_url": ONS_PAGE_URL,
        "same_source_as": UPSTREAM_URL,
        "source_zip_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "workbook_member": member,
        "workbook_sha256": hashlib.sha256(workbook_bytes).hexdigest(),
        "sheet": "Population",
        "licence": "Open Government Licence v3.0",
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "output": OUTPUT.relative_to(ROOT).as_posix(),
        "output_sha256": hashlib.sha256(data).hexdigest(),
        "rows": len(rows),
        "columns": list(COLUMNS),
        "years": [YEARS[0], YEARS[-1]],
        "age_definition": "Age in completed years at mid-year; age=105 denotes 105+ (105-109 plus 110+)",
        "units": "people",
        "fiscal_year_conversion": "FY y/y+1: 0.75 * mid-y population + 0.25 * mid-(y+1) population",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(data)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, help="Read an already downloaded official ONS zip")
    args = parser.parse_args()
    manifest = build(args.source_zip)
    print(f"Wrote {manifest['rows']} public population cells to {manifest['output']}")
    print(f"sha256: {manifest['output_sha256']}")


if __name__ == "__main__":
    main()
