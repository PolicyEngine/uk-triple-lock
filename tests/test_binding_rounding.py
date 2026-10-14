"""Published statutory rates remain consistent despite input-level rounding."""

import csv

from hypothesis import given, settings, strategies as st
import numpy as np
import pytest

from triple_lock import config, ts_monthly as TM


@pytest.mark.parametrize('field,path,months,precision,minimum_count', [
    ('cpi_september_12m', TM.CPI_INDEX_CSV, (9,), .1, 16),
    ('awe_total_pay_may_jul_3m_yoy', TM.AWE_LEVEL_CSV, (5, 6, 7), 1., 17),
])
def test_every_committed_statutory_rate_matches_rounded_levels(field, path, months, precision, minimum_count):
    observations = TM.read_monthly(path)
    checked = []
    with config.ACTUALS_CSV.open(newline='') as fh:
        for row in csv.DictReader(fh):
            if not row[field]:
                continue
            year, rate = int(row['determination_year']), float(row[field])
            current = [observations[year, month] for month in months]
            previous = [observations[year - 1, month] for month in months]
            interval = TM.growth_rate_interval(current, previous, level_precision=precision)
            low, high = TM.published_rate_interval(interval)
            assert low <= rate <= high, (year, rate, interval)
            checked.append(year)
    assert len(checked) >= minimum_count


@settings(max_examples=500, deadline=None)
@given(st.data(), st.sampled_from([.1, 1.]), st.sampled_from([1, 3]))
def test_rounding_interval_contains_true_and_published_growth(data, precision, window):
    values = st.lists(st.floats(min_value=10, max_value=2000, allow_nan=False,
                               allow_infinity=False), min_size=window, max_size=window)
    current, previous = np.array(data.draw(values)), np.array(data.draw(values))
    rounded_current = np.round(current / precision) * precision
    rounded_previous = np.round(previous / precision) * precision
    interval = TM.growth_rate_interval(rounded_current, rounded_previous, level_precision=precision)
    true_rate = np.mean(current) / np.mean(previous) - 1
    rounded_level_rate = np.mean(rounded_current) / np.mean(rounded_previous) - 1
    assert interval[0] <= true_rate <= interval[1]
    assert interval[0] <= rounded_level_rate <= interval[1]
    published_rate = round(true_rate / .001) * .001
    low, high = TM.published_rate_interval(interval)
    assert low <= published_rate <= high


@pytest.mark.parametrize('precision', [.1, 1.])
def test_deliberately_wrong_rate_is_outside_rounding_interval(precision):
    interval = TM.growth_rate_interval([102] * 3, [100] * 3, level_precision=precision)
    low, high = TM.published_rate_interval(interval)
    assert not low <= .07 <= high


def test_interval_uses_extreme_levels_and_rate_rounding_separately():
    interval = TM.growth_rate_interval([100, 110, 120], [90, 100, 110], level_precision=1)
    assert interval == pytest.approx((109.5 / 100.5 - 1, 110.5 / 99.5 - 1))
    assert TM.published_rate_interval(interval) == pytest.approx((interval[0] - .0005,
                                                               interval[1] + .0005))


@pytest.mark.parametrize('current,previous,precision', [
    ([np.nan], [100], .1), ([100], [np.inf], .1), ([100], [0], .1),
    ([100], [.05], .1), ([], [100], .1), ([100], [100], -1),
])
def test_invalid_levels_cannot_create_an_admissible_interval(current, previous, precision):
    with pytest.raises(ValueError, match='finite positive'):
        TM.growth_rate_interval(current, previous, level_precision=precision)


def test_committed_earnings_levels_and_rate_keep_september_vintage():
    assert TM.release_date(TM.AWE_LEVEL_CSV) == TM.BINDING_AWE_RELEASE_DATE
    assert TM.release_date(config.AWE_CSV) == TM.BINDING_AWE_RELEASE_DATE
