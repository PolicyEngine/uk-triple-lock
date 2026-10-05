"""Pilot job design and fail-closed aggregate disclosure, without an engine run."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    "part_e_pilot_driver", Path(__file__).parents[1] / "scripts" / "run_model_v2_e_pilot.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def synthetic_specs():
    return {
        'central': {'id': 'central'}, 'september_cpi_history': {},
        'paired': {i: {'stratum': 1 + i // 4, 'times_drawn': 1, 'spec': {'id': f'draw_{i}'}}
                   for i in range(40)},
        'paired_strata_probability': {k: .09 for k in range(1, 11)},
        'identical_rates_probability': .1,
    }


def test_driver_has_all_full_paired_runs_and_no_microcosm_jobs():
    planned = driver.plan(synthetic_specs(), {'n': 50_000, 'seed': 41, 'shocks': 'boot'})
    assert len(planned['jobs']) == 252
    assert sum(kind == 'path' for kind, _ in planned['jobs']) == 246
    assert sum(kind == 'coverage' for kind, _ in planned['jobs']) == 6
    assert all(arg['dataset'] == driver.PRIMARY for _, arg in planned['jobs'])
    for treatment in driver.TREATMENTS:
        assert sum(mode == treatment for name, mode in planned['labels'] if name != 'coverage') == 41
    upper = [arg for kind, arg in planned['jobs'] if kind == 'path' and arg['retyped_level'] == 'full_new']
    assert len(upper) == 41 and all(arg['demography'] == 'both' for arg in upper)
    assert sum(map(len, planned['sample'].values())) == 40
    assert planned['probabilities'] == synthetic_specs()['paired_strata_probability']
    assert len(planned['execution_jobs']) == 47
    assert sum(kind == 'treatment_paths' for kind, _ in planned['execution_jobs']) == 41


def test_driver_executes_fresh_batches_and_flattens_all_252_aggregates(tmp_path):
    planned = driver.plan(synthetic_specs(), {'n': 50_000})
    seen = []
    def fake_run_jobs(jobs, **options):
        assert options['workers'] == 2 and options['cache'] == tmp_path
        seen.extend(jobs)
        return [({mode: {'macro_label': arg['id']} for mode, arg in arguments['specs'].items()}
                 if kind == 'treatment_paths' else {'coverage': True}) for kind, arguments in jobs]
    grouped, coverage = driver.execute_design(planned, fake_run_jobs, workers=2, cache=tmp_path)
    assert len(seen) == 47 and len(grouped) == 41 and len(coverage) == 6
    assert sum(map(len, grouped.values())) + len(coverage) == 252
    assert grouped['draw_39']['both_full_new']['macro_label'] == 'draw_39'
    assert all(arguments['contrasts'] == driver.CONTRASTS for kind, arguments in seen if kind == 'treatment_paths')
    with pytest.raises(ValueError, match='at most two'):
        driver.execute_design(planned, fake_run_jobs, workers=3, cache=tmp_path)


def test_driver_refuses_a_changed_paired_design():
    data = synthetic_specs()
    data['paired'][0]['times_drawn'] = 2
    with pytest.raises(ValueError, match='40 distinct'):
        driver.plan(data, {'n': 50_000})


def test_one_small_fiscal_cell_withholds_the_whole_linked_family():
    counts = {year: {geography: {'gross': 10, 'net': 100} for geography in driver.GEOGRAPHIES}
              for year in driver.YEARS}
    grouped = {'central': {'both': {'saving_support_records_by_year': counts}}}
    assert driver.fiscal_suppression(grouped) == {'gross': False, 'net': False}
    counts[2039]['gb']['gross'] = 9
    assert driver.fiscal_suppression(grouped) == {'gross': True, 'net': False}
    del counts[2034]['uk']['net']
    assert driver.fiscal_suppression(grouped) == {'gross': True, 'net': True}


def test_country_suppression_is_linked_across_all_years_and_treatments():
    cell = {'status': 'available', 'records': 10, 'recipients_m': 1.,
            'basic_state_pension_bn': 2., 'new_state_pension_bn': 3.}
    coverage = {treatment: {'by_year': {year: {'gb': {'state_pension_by_country': {
        country: dict(cell) for country in driver.COUNTRIES}}} for year in (2024, 2039)}}
        for treatment in ('both', 'both_full_new')}
    for run in coverage.values():
        run['state_pension_country_contrast_support'] = {
            year: {country: {'status': 'available', 'records': 10} for country in driver.COUNTRIES}
            for year in (2024, 2039)}
    rows, withheld = driver.linked_country_tables(coverage)
    assert not withheld and rows['both'][2024]['ENGLAND']['recipients_m'] == 1.
    coverage['both_full_new']['by_year'][2039]['gb']['state_pension_by_country']['WALES']['status'] = 'suppressed'
    rows, withheld = driver.linked_country_tables(coverage)
    assert withheld
    assert all(row['status'] == 'withheld_family' and row['records'] is None and row['recipients_m'] is None
               for years in rows.values() for countries in years.values() for row in countries.values())


def test_country_change_support_withholds_family_even_when_each_level_is_large():
    cell = {'status': 'available', 'records': 100, 'recipients_m': 1.}
    coverage = {'both': {'by_year': {2024: {'gb': {'state_pension_by_country': {
        country: dict(cell) for country in driver.COUNTRIES}}}},
        'state_pension_country_contrast_support': {2024: {
            country: {'status': 'available', 'records': 10} for country in driver.COUNTRIES}}}}
    coverage['both']['state_pension_country_contrast_support'][2024]['WALES'] = {
        'status': 'suppressed', 'records': None}
    _, withheld = driver.linked_country_tables(coverage)
    assert withheld


def test_fiscal_levels_do_not_authorize_across_treatment_differences():
    run = {
        'saving_bn': {year: {'gross': 1., 'net': .5, 'gb': {'gross': .9, 'net': .4}}
                      for year in driver.YEARS},
        'saving_support_records_by_year': {year: {geography: {'gross': 50, 'net': 50}
                                                 for geography in driver.GEOGRAPHIES}
                                          for year in driver.YEARS},
    }
    grouped = {path: {treatment: dict(run) for treatment in driver.TREATMENTS}
               for path in ('central', 'draw_0')}
    estimator = SimpleNamespace(stratified_estimate=lambda *args: {'mean': 1., 'se': .1})
    design = {'sample': {1: [0, 0]}, 'probabilities': {1: 1.}, 'draw_provenance': {'n': 100}}
    tables = driver.fiscal_tables(design, grouped, estimator)
    assert all(row['status'] == 'withheld_family' for row in tables['central'])
    family = 'retyped_level_upper_minus_kept'
    for treatments in grouped.values():
        for run in treatments.values():
            run['treatment_contrast_support_records_by_year'] = {
                year: {geography: {contrast: {'gross': 50, 'net': 50} for contrast in driver.CONTRASTS}
                       for geography in driver.GEOGRAPHIES} for year in driver.YEARS}
    tables = driver.fiscal_tables(design, grouped, estimator)
    assert all(row['status'] == 'available' for row in tables['central'])
    for treatment in ('both', 'both_full_new'):
        grouped['draw_0'][treatment]['treatment_contrast_support_records_by_year'][2039]['gb'][family]['gross'] = None
    tables = driver.fiscal_tables(design, grouped, estimator)
    # Hide every connected level and contrast, in both geographies/years:
    # hiding just the small direct difference would permit algebraic recovery.
    assert all(row['status'] == 'withheld_family' for row in tables['central'] if row['measure'] == 'gross')
    assert all(row['status'] == 'available' for row in tables['central'] if row['measure'] == 'net')
