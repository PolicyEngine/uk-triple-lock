"""Public-input integrity and parser regression tests, without survey data."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_population_projection", ROOT / "scripts" / "build_population_projection.py"
)
projection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(projection)


def source_rows():
    headers = ["Sex", "Age", *map(str, projection.YEARS)]
    rows = [headers]
    for sex in ("Females", "Males"):
        for age in range(105):
            rows.append([sex, str(age), *([age + 1] * len(projection.YEARS))])
        rows.append([sex, "105 - 109", *([19] * len(projection.YEARS))])
        rows.append([sex, "110 and over", *([3] * len(projection.YEARS))])
    return rows


def test_preserves_all_people_when_collapsing_the_oldest_open_group():
    source = source_rows()
    parsed = projection.parse_population_rows(source)
    assert len(parsed) == 18 * 2 * 106
    oldest = [row for row in parsed if row["age"] == 105]
    assert len(oldest) == 18 * 2
    assert all(row["population"] == 22 for row in oldest)
    for sex in ("female", "male"):
        for year in projection.YEARS:
            counts = [row["population"] for row in parsed if row["sex"] == sex and row["year"] == year]
            assert sum(counts) == sum(range(1, 106)) + 19 + 3


def test_accepts_a_single_105_plus_source_cell():
    rows = [row for row in source_rows() if row[1] != "110 and over"]
    for row in rows:
        if row[1] == "105 - 109":
            row[1] = "105+"
    parsed = projection.parse_population_rows(rows)
    assert all(row["population"] == 19 for row in parsed if row["age"] == 105)


@pytest.mark.parametrize("missing_age", ["0", "79", "105 - 109", "110 and over"])
def test_refuses_incomplete_age_coverage(missing_age):
    rows = [row for row in source_rows() if row[1] != missing_age]
    with pytest.raises(ValueError, match="coverage"):
        projection.parse_population_rows(rows)


def test_refuses_overlapping_oldest_tail():
    rows = source_rows()
    rows.append(["Females", "105+", *([7] * len(projection.YEARS))])
    with pytest.raises(ValueError, match="overlapping"):
        projection.parse_population_rows(rows)


def test_refuses_duplicate_source_cells():
    rows = source_rows()
    rows.append(rows[1])
    with pytest.raises(ValueError, match="Duplicate source age"):
        projection.parse_population_rows(rows)


@pytest.mark.parametrize("bad_count", [None, -1, 1.5, float("nan"), float("inf"), True, "12"])
def test_refuses_missing_invalid_and_noninteger_population(bad_count):
    rows = source_rows()
    rows[1][2] = bad_count
    with pytest.raises(ValueError, match="Invalid population"):
        projection.parse_population_rows(rows)


def test_refuses_missing_year():
    rows = [row[:-1] for row in source_rows()]
    with pytest.raises(ValueError, match="2041"):
        projection.parse_population_rows(rows)


@pytest.mark.parametrize("names", [[], ["uk_ppp_machine_readable.xlsx", "duplicate/uk_ppp_machine_readable.xlsx"]])
def test_principal_workbook_selection_requires_one_match(names):
    with pytest.raises(ValueError, match="exactly one"):
        projection.projection_member(names)


def test_chooses_principal_and_ignores_variant_workbooks():
    assert projection.projection_member(
        ["uk_ppq_machine_readable.xlsx", "uk_ppp_machine_readable.xlsx", "uk_pps_machine_readable.xlsx"]
    ) == "uk_ppp_machine_readable.xlsx"


def test_committed_public_data_match_manifest_and_have_complete_cells():
    data = projection.OUTPUT.read_bytes()
    manifest = json.loads(projection.MANIFEST.read_text())
    assert hashlib.sha256(data).hexdigest() == manifest["output_sha256"]
    with projection.OUTPUT.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == projection.COLUMNS
        rows = list(reader)
    assert len(rows) == manifest["rows"] == 3816
    cells = {(int(row["year"]), row["sex"], int(row["age"])) for row in rows}
    assert cells == {
        (year, sex, age)
        for year in range(2024, 2042)
        for sex in ("female", "male")
        for age in range(106)
    }
    assert all(int(row["population"]) >= 0 for row in rows)
    assert manifest["licence"] == "Open Government Licence v3.0"
