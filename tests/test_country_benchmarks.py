"""Published country benchmarks match their source, without invented splits."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}


def published_cell(path, sheet_name, row_number, column_number):
    with ZipFile(path) as source:
        contents = ElementTree.fromstring(source.read("content.xml"))
    sheet = next(sheet for sheet in contents.findall(".//table:table", NS)
                 if sheet.get(f"{{{NS['table']}}}name") == sheet_name)
    row_position = 1
    for row in sheet.findall("table:table-row", NS):
        repeats = int(row.get(f"{{{NS['table']}}}number-rows-repeated", 1))
        if row_position <= row_number < row_position + repeats:
            column_position = 1
            for cell in row:
                repeats = int(cell.get(f"{{{NS['table']}}}number-columns-repeated", 1))
                if column_position <= column_number < column_position + repeats:
                    return cell.get(f"{{{NS['office']}}}value")
                column_position += repeats
        row_position += repeats
    raise AssertionError("Published source cell was not found")


@pytest.mark.parametrize("country,row_number", [("ENGLAND", 6), ("SCOTLAND", 17), ("WALES", 16)])
def test_combined_country_context_uses_verified_nominal_source_cells(country, row_number):
    benchmark = json.loads((ROOT / "data/pilot/country_benchmarks.json").read_text())
    source = benchmark["source"]
    path = ROOT / source["file"]
    assert source["verified"] is True
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    row = next(row for row in benchmark["rows"] if row["country"] == country)
    value = published_cell(path, "SP", row_number, 31)
    assert value == published_cell(path, "2024-25", row_number, 28)
    assert row["published_value_gbp_million"] == value
    assert row["state_pension_bn"] == pytest.approx(float(Decimal(value) / 1000))
    assert row["year"] == 2024
    assert all(row[metric] is None for metric in
               ("recipients_m", "basic_state_pension_bn", "new_state_pension_bn"))


def test_country_availability_records_missing_matching_metrics_and_forecasts():
    value = json.loads((ROOT / "data/pilot/country_benchmark_availability.json").read_text())
    assert value["coverage_gate_satisfied"] is False
    assert value["metrics"]["state_pension_bn"]["status"] == "available_context_only"
    assert all(value["metrics"][metric]["status"] == "unavailable" for metric in
               ("recipients_m", "basic_state_pension_bn", "new_state_pension_bn"))
    assert value["country_forecasts"]["status"] == "unavailable"
    for source in value["sources"].values():
        assert source["url"].startswith("https://")
        if "file" in source:
            assert hashlib.sha256((ROOT / source["file"]).read_bytes()).hexdigest() == source["sha256"]
