"""Aggregate-only fingerprint and minimum-cell rules, without microsimulation."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location(
    "model_v2_determinism", Path(__file__).parents[1] / "scripts" / "run_model_v2_determinism.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_fingerprint_is_key_order_invariant_and_preserves_float_bits():
    assert driver.fingerprint({'a': 1., 'b': 2.}) == driver.fingerprint({'b': 2., 'a': 1.})
    assert driver.fingerprint({'a': 1.}) != driver.fingerprint({'a': float(np.nextafter(1., 2.))})
    assert driver.fingerprint({'a': 0.}) != driver.fingerprint({'a': -0.})
    with pytest.raises(ValueError):
        driver.fingerprint({'a': np.nan})


@pytest.mark.parametrize('changed', (
    'aggregate_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
    'package_sha256', 'dataset_sha256', 'full_spec_sha256'))
def test_determinism_requires_matching_aggregates_and_every_provenance_hash(changed):
    first = {key: 'a' for key in (
        'aggregate_sha256', 'engine_semantics_sha256', 'engine_file_sha256',
        'package_sha256', 'dataset_sha256', 'full_spec_sha256')}
    assert driver.compare_runs(first, first)['passed']
    second = {**first, changed: 'b'}
    result = driver.compare_runs(first, second)
    assert not result['passed'] and not result['matching_hashes'][changed]


def test_signed_fiscal_cells_apply_the_same_minimum_contributor_floor():
    assert driver.supported_cell(0, 0.)['records'] == 0
    assert driver.supported_cell(10, -2.)['records'] == 10
    for amount in (-2., 2.):
        with pytest.raises(RuntimeError, match='ten-household'):
            driver.supported_cell(9, amount)
