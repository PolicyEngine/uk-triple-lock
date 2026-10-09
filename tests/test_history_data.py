"""Calendar comparators ignore forecast-only rows that C2 can score statutorily."""

import csv
import json

import numpy as np
import pytest

from triple_lock import history_data as HD, ts_backtest as TB
from triple_lock.config import ERROR_CSV


def write_rows(path, rows):
    columns = ['year_forecast_made', 'forecast_vintage', 'horizon_years', 'variable',
               'forecast', 'outturn', 'error']
    with path.open('w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def observed_rows():
    return [{'year_forecast_made': year, 'forecast_vintage': f'March {year} EFO',
             'horizon_years': horizon, 'variable': variable,
             'forecast': .02, 'outturn': .025, 'error': .005}
            for year in (2020, 2021) for horizon in range(1, 5) for variable in HD.VARIABLES]


def forecast_only_row(**changes):
    row = {'year_forecast_made': 2022, 'forecast_vintage': 'March 2022 EFO',
           'horizon_years': 4, 'variable': 'cpi', 'forecast': .02, 'outturn': '', 'error': ''}
    return {**row, **changes}


def test_future_statutory_complete_forecast_does_not_complete_calendar_error_block(tmp_path):
    path = tmp_path / 'forecasts.csv'
    partial = [{'year_forecast_made': 2022, 'forecast_vintage': 'March 2022 EFO',
                'horizon_years': h, 'variable': variable, 'forecast': .02,
                'outturn': .025, 'error': .005}
               for h in range(1, 4) for variable in HD.VARIABLES]
    old = observed_rows() + partial
    write_rows(path, old)
    baseline = HD.load_forecast_errors(path)
    old_blocks, old_origins = HD.error_blocks(baseline)
    write_rows(path, old + [forecast_only_row(variable=variable) for variable in HD.VARIABLES])
    actual = HD.load_forecast_errors(path)
    blocks, origins = HD.error_blocks(actual)
    assert actual == baseline
    assert origins == old_origins == [(2020, 'March 2020 EFO'), (2021, 'March 2021 EFO')]
    np.testing.assert_array_equal(blocks, old_blocks)
    # The other reader retains horizon-4 means without inventing calendar
    # outcomes. C2 sees the statutory window when 2023..2026 are observed.
    means, outcomes = TB.load_forecasts(path)
    assert means[(2022, 'March 2022 EFO')]['cpi', 4] == .02
    assert ('cpi', 4) not in outcomes[(2022, 'March 2022 EFO')]
    statutory = {year: (.02, .03) for year in range(2021, 2027)}
    assert TB.complete_statutory_origins(means, statutory)[-1] == (2022, 'March 2022 EFO')


def test_committed_observed_errors_are_byte_equivalent_to_original_parser():
    with ERROR_CSV.open(newline='') as fh:
        rows = list(csv.DictReader(fh))
    grouped = {}
    for row in rows:
        if not row['outturn'].strip() and not row['error'].strip():
            continue
        vintage = (int(row['year_forecast_made']), row['forecast_vintage'].strip())
        key = (row['variable'].strip().lower(), int(row['horizon_years']))
        grouped.setdefault(vintage, {}).setdefault(key, []).append(float(row['error']))
    original = {vintage: {key: float(np.mean(values)) for key, values in errors.items()}
                for vintage, errors in grouped.items()}
    encoded = lambda table: json.dumps({str(vintage): {str(key): value for key, value in errors.items()}
                                       for vintage, errors in table.items()}, separators=(',', ':')).encode()
    assert encoded(HD.load_forecast_errors(ERROR_CSV)) == encoded(original)


@pytest.mark.parametrize('changes', [
    {'outturn': .03}, {'error': .01}, {'outturn': 'nan', 'error': .01},
    {'outturn': .03, 'error': 'inf'}, {'forecast': 'nan'}, {'forecast': 'inf'},
    {'forecast': 2.}, {'forecast': ''}, {'variable': 'unknown'},
    {'horizon_years': 0}, {'forecast_vintage': ''},
])
def test_forecast_only_support_retains_strict_validation(tmp_path, changes):
    path = tmp_path / 'invalid.csv'
    write_rows(path, observed_rows() + [forecast_only_row(**changes)])
    with pytest.raises(ValueError):
        HD.load_forecast_errors(path)


def test_duplicate_observed_errors_keep_existing_average(tmp_path):
    path = tmp_path / 'duplicates.csv'
    rows = observed_rows()
    duplicate = dict(rows[0], outturn=.029, error=.009)
    write_rows(path, rows + [duplicate, forecast_only_row()])
    assert HD.load_forecast_errors(path)[2020, 'March 2020 EFO']['cpi', 1] == pytest.approx(.007, abs=1e-15)
