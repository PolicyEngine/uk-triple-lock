"""Model-v2 uncertainty pilot and reproducible fiscal-run handoff, without simulation.

Run with ``python -m triple_lock.ts_uncertainty --output out/uncertainty``.
The fixed scoring/adequacy rule was committed in docs/METHOD.md before scoring.
Draw artifacts are independent of the PolicyEngine job cache.
"""

import argparse
import csv
from copy import deepcopy
from datetime import date
import os
import re
import subprocess
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import scipy

from . import ts_annual, ts_monthly
from .central import central_path, long_run_earnings_variant, obr_premium_comparator
from .expected_value import SEED, SAMPLE_SEED

CANDIDATES = {
    'monthly_var1_boot': {'lag_order': 1, 'kind': 'boot'},
    'monthly_var2_boot': {'lag_order': 2, 'kind': 'boot'},
    'annual_boot_gap': {'annual': True},
    'monthly_var1_tcop': {'lag_order': 1, 'kind': 'tcop'},
    'monthly_var1_gauss': {'lag_order': 1, 'kind': 'gauss'},
}
PRIMARY_FORM = 'monthly_var1_boot'
PROPER_SCORES = ('gap_crps', 'switch_crps', 'floor_crps', 'energy', 'variogram')
PRE_REGISTRATION_COMMIT = 'a8d2ac8'
C2_PRE_REGISTRATION_COMMIT = '65343e2ee43a359f056ce5a027739509d32ab49f'
C1_RULE = {
    'treatments': ['published', 'suspended'],
    'exclusion': 'none',
    'thresholds': {
        'annual_coverage': [0.5, 1.0], 'terminal_coverage': [0.5, 1.0],
        'terminal_wilson_contains': 0.8, 'gap_bias_pp': 1.5,
        'switch_bias': 1.0, 'floor_bias': 0.25, 'proper_score_ratio': 1.25,
        'past_percentile': [5.0, 95.0], 'minimum_origins': 2,
        'finite_scores': True, 'complete_origins': True,
    },
}
C2_RULE = deepcopy(C1_RULE)
C2_RULE.update(treatments=['suspended'], exclusion='statistics fixed by the suspended-earnings legal rule')
C2_BUDGET_DATE = date(2026, 10, 28)

N_FULL_RUNS = 160


def candidate_paths(form, years, n, seed, end_obs=None, calendar_target=None):
    config = CANDIDATES[form]
    if config.get('annual'):
        return ts_annual.paths(years, n, seed, end_obs=end_obs, calendar_target=calendar_target)
    return ts_monthly.paths(years, n, seed, end_obs=end_obs, calendar_target=calendar_target,
                            kind=config['kind'], lag_order=config['lag_order'])


def adequacy(backtest, treatments=None, *, screen='c1'):
    """Apply the pre-registered screen literally; no fitted/tuned thresholds."""
    if screen not in ('c1', 'c2'):
        raise ValueError('screen must be c1 or c2')
    rule = C2_RULE if screen == 'c2' else C1_RULE
    treatments = tuple(rule['treatments']) if treatments is None or screen == 'c2' else treatments
    limits = rule['thresholds']
    decision = {}
    for form in CANDIDATES:
        failures, ratios = [], []
        for test in ('A', 'B'):
            for treatment in treatments:
                s = backtest['scores'][test][treatment][form]
                ref = backtest['scores'][test][treatment][PRIMARY_FORM]
                tag = f'{test}/{treatment}'
                if s['n_origins'] != s['expected_origins'] or s['n_origins'] < limits['minimum_origins']:
                    failures.append(f'{tag}: missing/failed origins')
                    continue
                if any(metric['mean'] is None or not np.isfinite(metric['mean']) for metric in s.values()
                       if isinstance(metric, dict) and 'mean' in metric
                       and not metric.get('excluded_by_law')):
                    failures.append(f'{tag}: non-finite score or statistic')
                    continue
                for k in ('annual_gap_coverage', 'terminal_coverage'):
                    if s[k].get('excluded_by_law'):
                        continue
                    coverage_limits = limits['annual_coverage' if k == 'annual_gap_coverage' else 'terminal_coverage']
                    if not coverage_limits[0] <= s[k]['mean'] <= coverage_limits[1]:
                        failures.append(f'{tag}: {k} {s[k]["mean"]:.3f} outside [0.50, 1.00]')
                if not s['terminal_coverage'].get('excluded_by_law'):
                    lo, hi = s['terminal_coverage']['wilson95_independent']
                    if not lo <= limits['terminal_wilson_contains'] <= hi:
                        failures.append(f'{tag}: terminal coverage Wilson band excludes 0.80')
                for k in ('gap_bias_pp', 'switch_bias', 'floor_bias'):
                    limit = limits[k]
                    if s[k].get('excluded_by_law'):
                        continue
                    if abs(s[k]['mean']) > limit:
                        failures.append(f'{tag}: |{k}| {abs(s[k]["mean"]):.3f} exceeds {limit}')
                for k in PROPER_SCORES:
                    if s[k].get('excluded_by_law'):
                        continue
                    value, baseline = s[k]['mean'], ref.get(k, {}).get('mean')
                    if baseline is None:
                        failures.append(f'{tag}: no primary reference for {k}')
                        continue
                    ratio = value / baseline if baseline > 0 else (1.0 if value == 0 else float('inf'))
                    ratios.append(ratio)
                    if not np.isfinite(ratio) or ratio > limits['proper_score_ratio']:
                        failures.append(f'{tag}: {k} ratio {ratio:.3f} exceeds 1.25')
        p = backtest['past_years'][form]
        for treatment in treatments:
            q = p.get(treatment, {}).get('realised_percentile')
            if q is None or not np.isfinite(q) or not limits['past_percentile'][0] <= q <= limits['past_percentile'][1]:
                label = 'missing' if q is None else f'{q:.2f}'
                failures.append(f'past/{treatment}: realised percentile {label} outside [5, 95]')
        rank = (float(np.exp(np.mean(np.log(np.maximum(ratios, 1e-15)))))
                if ratios and np.isfinite(ratios).all() else None)
        decision[form] = {'passes': not failures, 'failures': failures, 'proper_score_ratio_geomean': rank}
    passing = [f for f in CANDIDATES if decision[f]['passes']]
    chosen = PRIMARY_FORM if PRIMARY_FORM in passing else (
        min(passing, key=lambda f: decision[f]['proper_score_ratio_geomean']) if passing and screen == 'c1' else None)
    result = {'forms': decision, 'passing_forms': passing, 'selected_primary': chosen,
            'primary_retained': chosen == PRIMARY_FORM,
            'interpretation': 'Scenario envelope; never a probability interval; do not average forms.'}
    if screen == 'c2':
        result.update(screen='c2', screen_treatments=['suspended'],
                      published_earnings='sensitivity only; never enters the verdict',
                      effective_ruling='c' if chosen == PRIMARY_FORM else 'a',
                      expected_value_label='model-conditional' if chosen == PRIMARY_FORM else None,
                      fallback_reason=None if chosen == PRIMARY_FORM else 'Original primary failed C2; automatic d955(a) scenarios-only fallback.')
    return result


def future_draws(form, central, n=50_000, seed=SEED):
    from .config import BASE_YEAR, CALENDAR_YEARS

    target = {y: (central['calendar']['cpi'][y], central['calendar']['earnings'][y]) for y in CALENDAR_YEARS}
    m, info = candidate_paths(form, [BASE_YEAR, *CALENDAR_YEARS], n, seed, calendar_target=target)
    return {'stat_cpi': m['statutory_cpi'][:, :-1], 'stat_earnings': m['statutory_earnings'][:, :-1],
            'calendar': np.stack([m['calendar_cpi'][:, 1:], m['calendar_earnings'][:, 1:]], axis=2),
            'info': info}


def validate_rule_draws(d):
    """Check all draws against the inputs at their published precision."""
    from . import expected_value as EV, rules
    from .config import HORIZON

    levels, rates = EV.rule_levels(d['stat_cpi'], d['stat_earnings'], 1.)
    c, e = rules.round_rate(d['stat_cpi']), rules.round_rate(d['stat_earnings'])
    bp, tl = levels['burnham_2030'], levels['triple_lock']
    j = HORIZON.index(2030)
    earnings_anchor = bp[:, j-1, None] * np.cumprod(1 + e[:, j:], axis=1)
    checks = {
        'finite': all(np.isfinite(x).all() for x in (c, e, bp, tl)),
        'plan_rate_at_least_cpi_floor': np.all(rates['burnham_2030'] >= np.maximum(c, .025) - 1e-12),
        'plan_level_at_most_triple_lock': np.all(bp <= tl + 1e-12),
        'equal_in_april_2030': np.all(np.abs(bp[:, j] - tl[:, j]) <= 1e-12),
        'plan_at_least_2029_earnings_anchor': np.all(bp[:, j:] >= earnings_anchor - 1e-12),
    }
    if not all(checks.values()):
        raise AssertionError(f'candidate draw rules failed: {checks}')
    late = [i for i, y in enumerate(HORIZON) if y >= 2034]
    premium = 100 * (rates['triple_lock'][:, late] - d['stat_earnings'][:, late]).mean(axis=1)
    return {'n_checked': len(c), **{k: bool(v) for k, v in checks.items()},
            'premium_2034_2039_pp': float(premium.mean()),
            'premium_first_phase_se_pp': float(premium.std(ddof=1) / np.sqrt(len(c)))}


def sample_design(d, base_weekly=1.0, n_runs=N_FULL_RUNS, seed=SAMPLE_SEED, include_zero=False):
    from . import expected_value as EV

    n = len(d['stat_cpi'])
    w = np.full(n, 1 / n)
    levels, rates = EV.rule_levels(d['stat_cpi'], d['stat_earnings'], base_weekly)
    gap = levels['triple_lock'][:, -1] - levels['burnham_2030'][:, -1]
    identical = np.all(rates['triple_lock'] == rates['burnham_2030'], axis=1)
    strata = EV.stratify(w, gap, identical)
    alloc = EV.allocate(w, gap, strata, n_runs, include_zero=include_zero)
    sample = EV.draw_sample(w, strata, alloc, seed)
    zero = int(np.flatnonzero(identical)[0]) if identical.any() else None
    W = {int(k): float(w[strata == k].sum()) for k in np.unique(strata)}
    relative = gap / base_weekly
    summary = EV.gap_summary(d, w, base_weekly)
    summary.pop('mean_gap_gbp_week')
    summary.pop('gap_gbp_week')
    summary.update({'mean_gap_relative_to_base': float(w @ relative),
                    'gap_relative_quantiles': {f'p{int(100*q)}': float(np.quantile(relative, q))
                                               for q in (.1, .25, .5, .75, .9)}})
    return {'n_draws': n, 'allocation': alloc, 'sample': sample, 'stratum_weights': W,
            'strata': strata, 'gap': gap, 'identical_check_draw': zero,
            'summary': summary}


def paired_mean_estimates(design, baseline_results, variant_results, n_draws=50_000):
    """Variant-minus-baseline from the *same* sampled indices, including zero strata.

    Results map draw index to full engine result. Variance is computed on paired
    differences, not on independent baseline/variant standard errors.
    """
    from . import expected_value as EV
    from .config import HORIZON

    return {key: {y: EV.stratified_estimate(
        {int(k): [variant_results[i]['saving_bn'][y][key] - baseline_results[i]['saving_bn'][y][key]
                  for i in idx] for k, idx in design['sample'].items()},
        {int(k): v for k, v in design['stratum_weights'].items()}, n_draws)
        for y in HORIZON} for key in EV.OUTPUTS}


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def _save_draws(path, d):
    np.savez_compressed(path, **{k: d[k] for k in ('stat_cpi', 'stat_earnings', 'calendar')})
    return {k: hashlib.sha256(np.ascontiguousarray(d[k]).tobytes()).hexdigest()
            for k in ('stat_cpi', 'stat_earnings', 'calendar')}


def write_historical_estimator(output, published_path=None):
    """Reproduce the committed diagnostic from public aggregate full-run outputs."""
    from . import expected_value as EV
    from .config import OUTPUT

    path = Path(published_path or OUTPUT)
    result = EV.reestimate_published(json.loads(path.read_text())['expected_value'])
    result['published_results_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / 'historical_estimator.json', result)
    return result


def runtime_provenance():
    return {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
            'numpy_build': np.show_config(mode='dicts')}


def handoff_input_hashes():
    """Macro sources and model code needed to reject stale executable handoffs."""
    from .config import ACTUALS_CSV, AWE_CSV, CENTRAL_FORECAST_CSV, CROSSCHECK_CSV, CPI_CSV, ERROR_CSV
    from .history_data import SERIES
    paths = [ts_monthly.AWE_LEVEL_CSV, ts_monthly.CPI_INDEX_CSV, ACTUALS_CSV,
             AWE_CSV, CPI_CSV, CENTRAL_FORECAST_CSV, CROSSCHECK_CSV, ERROR_CSV, *[value[0] for value in SERIES.values()]]
    here = Path(__file__).parent
    paths.extend(here / name for name in ('ts_monthly.py', 'ts_annual.py', 'ts_uncertainty.py',
                                          'ts_backtest.py', 'ts_methods.py', 'history_data.py',
                                          'expected_value.py', 'rules.py', 'central.py', 'config.py'))
    return {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _git_bytes(*args):
    """Read the assigned private Git directory; never mutate Git here."""
    from .config import REPO

    assigned = os.environ.get('GIT_DIR') or str(REPO / ('.git-e' if (REPO / '.git-e').exists() else '.git'))
    env = dict(os.environ, GIT_DIR=assigned)
    result = subprocess.run(['/usr/bin/git', *args], env=env, cwd=REPO, check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout


def _frozen_c2_section(text):
    begin, end = '<!-- C2 frozen rule begins -->', '<!-- C2 frozen rule ends -->'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('C2 frozen rule markers missing or ambiguous')
    return text.split(begin, 1)[1].split(end, 1)[0]


def committed_c2_rule_hash():
    """Bind the current frozen section to the actual pre-registration commit."""
    from .config import REPO

    committed = _git_bytes('show', f'{C2_PRE_REGISTRATION_COMMIT}:docs/METHOD.md').decode()
    section = _frozen_c2_section(committed)
    current = _frozen_c2_section((REPO / 'docs/METHOD.md').read_text())
    if current != section:
        raise ValueError('C2 rule differs from the committed pre-registration; refuse scoring')
    return hashlib.sha256(section.encode()).hexdigest()


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


def c1_failure_provenance():
    from .config import REPO

    path = REPO / 'docs/uncertainty/selection.json'
    selection = json.loads(path.read_text())
    return {'screen': 'c1', 'rule_sha': PRE_REGISTRATION_COMMIT, 'all_five_failed': True,
            'common_failure': 'Test A/published terminal coverage 1/6; 2021 furlough base effect',
            'rule_changed_after_scores_seen': True,
            'reason': 'Statutory behaviour: Parliament suspended the earnings leg for April 2022',
            'retained_selection_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'forms': selection['forms']}


def binding_input_provenance(*, binding=False, today=None):
    """Check the release-specific macro inputs before a binding C2 score.

    Actual statutory rates must agree at published precision with the raw
    monthly observations. Every central mean must identify the dated OBR
    Budget release. Complete statutory windows require all forecast means,
    even when a calendar outturn/error is not yet published.
    """
    from .config import ACTUALS_CSV, AWE_CSV, AWE_PERIOD, CENTRAL_FORECAST_CSV, CPI_CSV, CPI_PERIOD, ERROR_CSV, REPO
    from .ts_backtest import H, complete_statutory_origins, load_forecasts, statutory_outturns

    committed_c2_rule_hash()
    paths = [ACTUALS_CSV, AWE_CSV, CPI_CSV, CENTRAL_FORECAST_CSV, ERROR_CSV,
             ts_monthly.CPI_INDEX_CSV, ts_monthly.AWE_LEVEL_CSV]
    hashes = {str(Path(path).relative_to(REPO)): hashlib.sha256(Path(path).read_bytes()).hexdigest()
              for path in paths}
    missing = []
    now = date.today() if today is None else today
    if now < C2_BUDGET_DATE:
        missing.append('Budget-day inputs are not yet released (28 October 2026)')
    with ACTUALS_CSV.open(newline='') as fh:
        actual = {int(row['determination_year']): row for row in csv.DictReader(fh)}.get(2026, {})
    cpi = ts_monthly.read_monthly(ts_monthly.CPI_INDEX_CSV)
    awe = ts_monthly.read_monthly(ts_monthly.AWE_LEVEL_CSV)
    values = {}
    if CPI_PERIOD != '2026 SEP' or AWE_PERIOD != '2026 JUL':
        missing.append('Central statutory periods must be CPI_PERIOD=2026 SEP and AWE_PERIOD=2026 JUL')
    for name, field, observed, months in (
            ('september_2026_cpi', 'cpi_september_12m', cpi, (9,)),
            ('may_july_2026_awe', 'awe_total_pay_may_jul_3m_yoy', awe, (5, 6, 7))):
        raw = actual.get(field, '')
        keys = [(year, month) for year in (2025, 2026) for month in months]
        if not raw or not all(key in observed for key in keys):
            missing.append(f'{name}: actual statutory rate and matching raw monthly observations required')
            continue
        rate = float(raw)
        denominator = np.mean([observed[2025, month] for month in months])
        derived = np.mean([observed[2026, month] for month in months]) / denominator - 1
        if not np.isfinite(rate) or not np.isfinite(derived) or abs(rate - derived) > .00050001:
            missing.append(f'{name}: actual statutory rate disagrees with raw monthly observations')
        values[name] = {'actual': rate, 'monthly_derived': float(derived),
                        'published_precision_tolerance': .00050001}
    for name, path, period, field in (
            ('september_2026_cpi', CPI_CSV, '2026 SEP', 'cpi_september_12m'),
            ('may_july_2026_awe', AWE_CSV, '2026 JUL', 'awe_total_pay_may_jul_3m_yoy')):
        with path.open(newline='') as fh:
            published_rates = {row[0].strip(): float(row[1]) / 100 for row in csv.reader(fh)
                               if len(row) > 1 and re.fullmatch(r'\d{4} [A-Z]{3}', row[0].strip()) and row[1].strip()}
        if period not in published_rates or not actual.get(field):
            missing.append(f'{name}: published central statutory rate {period} required')
        elif abs(published_rates[period] - float(actual[field])) > 1e-10:
            missing.append(f'{name}: published central statutory rate differs from actuals')
    with CENTRAL_FORECAST_CSV.open(newline='') as fh:
        all_means = list(csv.DictReader(fh))
        means = [row for row in all_means if row['basis'] in ('calendar_year', 'q3_yoy', 'q2_yoy')
                 and row['variable'] in ('cpi', 'earnings')]
    required = {(variable, 'calendar_year', str(year)) for variable in ('cpi', 'earnings') for year in range(2026, 2031)}
    required.update(('cpi', 'q3_yoy', f'{year}Q3') for year in range(2026, 2031))
    required.update(('earnings', 'q2_yoy', f'{year}Q2') for year in range(2026, 2031))
    provided = {(row['variable'], row['basis'], row['period']) for row in means}
    if not required <= provided:
        missing.append('Budget central calendar and quarterly CPI/earnings means for 2026–2030 are incomplete')
    budget_sources = []
    for row in means:
        if (row['variable'], row['basis'], row['period']) not in required:
            continue
        source = ' '.join(row.get(key, '') for key in ('source', 'note', 'source_date')).lower()
        url = row.get('source_url', '').lower()
        date_identified = bool(re.search(r'28\s+(?:october|oct)\s+2026|2026-10-28', source))
        if not (date_identified and 'obr' in source and ('budget' in source or 'efo' in source)
                and re.match(r'https://(?:www\.)?obr\.uk/', url)
                and np.isfinite(float(row['value']))):
            missing.append(f"{row['variable']}/{row['period']}: explicit OBR Budget 28 October 2026 source required")
        budget_sources.append({'variable': row['variable'], 'basis': row['basis'], 'period': row['period'],
                               'source': row.get('source'), 'source_url': row.get('source_url'),
                               'source_date': row.get('source_date')})
    forecasts, _ = load_forecasts(path=ERROR_CSV)
    outturns = statutory_outturns()
    complete = complete_statutory_origins(forecasts, outturns)
    incomplete = [v[1] for v, rows in forecasts.items()
                  if v[1].startswith(('March ', 'June 2010 '))
                  and all(v[0] + h in outturns for h in range(1, H + 1))
                  and not all((variable, h) in rows for variable in ('cpi', 'earnings') for h in range(1, H + 1))]
    if incomplete:
        missing.append('Statutory outcomes now complete but forecast means missing: ' + ', '.join(incomplete))
    # The binding inputs must have been committed before re-scoring.
    if binding:
        for relative, expected in hashes.items():
            try:
                committed = _git_bytes('show', f'HEAD:{relative}')
            except subprocess.CalledProcessError:
                missing.append(f'{relative}: binding input is not committed')
                continue
            if hashlib.sha256(committed).hexdigest() != expected:
                missing.append(f'{relative}: binding input differs from committed HEAD')
    result = {'budget_date': C2_BUDGET_DATE.isoformat(), 'ready': not missing,
              'missing_requirements': missing, 'data_hashes': hashes, 'statutory_inputs': values,
              'central_statutory_periods': {'cpi': CPI_PERIOD, 'earnings': AWE_PERIOD},
              'obr_forecast_sources': budget_sources,
              'long_term_sources': [{key: row.get(key) for key in ('variable', 'basis', 'period', 'source', 'source_url')}
                                    for row in all_means if row['basis'] == 'fiscal_year_lted'],
              'complete_origins': [v[1] for v in complete],
              'incomplete_forecast_windows': incomplete}
    if binding and missing:
        raise ValueError('Binding C2 requires post-Budget committed inputs: ' + '; '.join(missing))
    return result


def c2_authorization(outcome, *, binding=False):
    """Separate the diagnostic score verdict from permission to execute it."""
    authorized = bool(binding and outcome['selected_primary'] == PRIMARY_FORM)
    if not binding:
        label = 'dry run: no expected value authorization'
    elif authorized:
        label = 'binding C2: passing primary authorizes a model-conditional expected value'
    else:
        label = 'binding C2: primary failed; automatic d955(a), scenarios only'
    return {'expected_value_authorized': authorized, 'authorization': label}


def c2_metadata(score_table, outcome, binding_inputs, *, binding=False):
    """Provenance shared by the executable handoff and its score artifact.

    The scoring commit is an audit link. Hashes detect accidental drift; they
    do not authenticate artifacts rewritten together by an adversary.
    """
    if outcome != adequacy(score_table, screen='c2'):
        raise ValueError('C2 verdict does not match the supplied frozen-screen scores')
    scoring_head = score_table.get('scoring_head') or _git_bytes('rev-parse', 'HEAD').decode().strip()
    return {'screen': 'c2', 'rule_sha': C2_PRE_REGISTRATION_COMMIT, 'scoring_head': scoring_head,
            'rule_section_sha256': committed_c2_rule_hash(), 'rule': deepcopy(C2_RULE),
            'run_kind': 'binding' if binding else 'dry_run',
            **c2_authorization(outcome, binding=binding),
            'c2_outcome': outcome, 'score_table': score_table,
            'score_table_sha256': _canonical_hash(score_table),
            'c1_failure': c1_failure_provenance(), 'binding_inputs': binding_inputs}


def validate_c2_handoff(manifest, *, require_binding=True):
    """Return the verified C2 verdict before the adapter admits any fiscal jobs."""
    if manifest.get('screen') != 'c2':
        raise ValueError('d955(c) requires a C2 handoff')
    if manifest.get('rule_sha') != C2_PRE_REGISTRATION_COMMIT:
        raise ValueError('C2 handoff rule SHA differs from the committed pre-registration')
    scoring_head = manifest.get('scoring_head')
    if not isinstance(scoring_head, str) or not re.fullmatch(r'[0-9a-f]{40}', scoring_head):
        raise ValueError('C2 handoff lacks a valid scoring head commit')
    try:
        _git_bytes('cat-file', '-e', f'{scoring_head}^{{commit}}')
        _git_bytes('merge-base', '--is-ancestor', scoring_head, 'HEAD')
    except subprocess.CalledProcessError as error:
        raise ValueError('C2 handoff scoring head must be a real commit and ancestor of current HEAD') from error
    if manifest.get('rule_section_sha256') != committed_c2_rule_hash() or manifest.get('rule') != C2_RULE:
        raise ValueError('C2 handoff rule differs from the committed pre-registration')
    scores = manifest.get('score_table')
    if scores is None or manifest.get('score_table_sha256') != _canonical_hash(scores):
        raise ValueError('C2 handoff score table does not match its hash')
    if scores.get('scoring_head', scoring_head) != scoring_head:
        raise ValueError('C2 handoff scoring head disagrees with its score provenance')
    outcome = adequacy(scores, screen='c2')
    if outcome != manifest.get('c2_outcome'):
        raise ValueError('C2 handoff verdict does not reproduce from its scores')
    if manifest.get('c1_failure') != c1_failure_provenance():
        raise ValueError('C2 handoff lacks the retained C1 failure disclosure')
    if manifest.get('run_kind') not in ('dry_run', 'binding'):
        raise ValueError('C2 handoff must identify dry_run or binding status')
    authorization = c2_authorization(outcome, binding=manifest['run_kind'] == 'binding')
    if any(manifest.get(key) != value for key, value in authorization.items()):
        raise ValueError('C2 handoff expected-value authorization disagrees with its run status and primary verdict')
    if require_binding and manifest['run_kind'] != 'binding':
        raise ValueError('C2 dry-run handoff cannot authorize a binding fiscal rebuild')
    recorded = manifest.get('binding_inputs', {})
    current = binding_input_provenance(binding=require_binding)
    if recorded != current:
        raise ValueError('C2 handoff binding-input provenance changed; re-score the committed inputs')
    if require_binding and not recorded.get('ready'):
        raise ValueError('C2 handoff lacks ready post-Budget binding inputs')
    if manifest.get('input_hashes') != handoff_input_hashes():
        raise ValueError('C2 handoff scoring inputs or code changed; regenerate it')
    if scores.get('origins', {}).get('B') != current['complete_origins']:
        raise ValueError('C2 handoff omitted or changed complete statutory forecast origins')
    for form, metadata in manifest.get('forms', {}).items():
        eligible = manifest['run_kind'] == 'binding' and form == PRIMARY_FORM and outcome['selected_primary'] == PRIMARY_FORM
        if metadata.get('fiscal_eligible') != eligible:
            raise ValueError('C2 handoff fiscal eligibility violates the primary-only rule')
    return outcome


def handoff(output, screen, n=50_000, n_runs=N_FULL_RUNS, log=print, central=None,
            uncertainty_ruling=None, *, screen_name="c1", score_table=None,
            binding_inputs=None, binding=False):
    """Save own-form draws/strata/specs for passing forms; original-primary diagnostics.

    No engine is imported or run. Mean paths are scenarios and can be executed
    independently of adequacy; their presentation still needs d955's ruling.
    """
    from . import expected_value as EV

    central = central_path() if central is None else central
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'n_draws': n, 'draw_seed': SEED, 'sample_seed': SAMPLE_SEED,
                'shocks': 'boot', 'uncertainty_ruling': uncertainty_ruling,
                'central_sha256': hashlib.sha256(json.dumps(central, sort_keys=True).encode()).hexdigest(),
                'input_hashes': handoff_input_hashes(),
                'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
                'runtime': runtime_provenance(),
                'rate_decimals': 3, 'gap_unit': 'level relative to base pension = 1',
                'obr_2034_2039_premium_pp': obr_premium_comparator(central),
                'forms': {}, 'mean_paths': {}, 'no_microsimulation': True,
                'rebuild_needs': ['Certified PolicyEngine/data bundle and baseline acceptance gates',
                                  'Updated Autumn Budget OBR means and refreshed September CPI',
                                  'Re-run this frozen screen on the updated committed inputs',
                                  'Full paired rule runs only for passing forms; no interpolation',
                                  'Paired original-primary mean paths are scenarios, independent of adequacy',
                                  'Separate path-sampling/first-phase SEs for every output and year',
                                  'Scenario envelope across passing forms; no model averaging']}
    if screen_name == 'c2':
        if score_table is None or binding_inputs is None:
            raise ValueError('C2 handoff requires its complete score table and binding-input provenance')
        manifest.update(c2_metadata(score_table, screen, binding_inputs, binding=binding))
    required = list(dict.fromkeys([*screen['passing_forms'], PRIMARY_FORM]))
    for form in required:
        log(f'Future draws {form}: {n}')
        d = future_draws(form, central, n)
        validation = validate_rule_draws(d)
        design = sample_design(d, n_runs=n_runs, include_zero=form == PRIMARY_FORM)
        hashes = _save_draws(output / f'{form}.npz', d)
        np.save(output / f'{form}.strata.npy', design.pop('strata'))
        design.pop('gap')
        slots = [i for indices in design['sample'].values() for i in indices]
        unique = sorted(set(slots) | ({design['identical_check_draw']} if design['identical_check_draw'] is not None else set()))
        specs = [EV.path_spec(d, i) for i in unique]
        # The labels and design live outside engine specs: preserve semantic job keys.
        _write_json(output / f'{form}.specs.json', specs)
        _write_json(output / f'{form}.design.json', design)
        eligible = ((binding and form == PRIMARY_FORM and screen['selected_primary'] == PRIMARY_FORM) if screen_name == 'c2'
                    else form in screen['passing_forms'] or (uncertainty_ruling == 'b' and form == PRIMARY_FORM))
        manifest['forms'][form] = {'fiscal_eligible': eligible, 'diagnostic_only': not eligible,
                                   'sample_slots': len(slots), 'unique_full_runs': len(unique),
                                   'premium_2034_2039_pp': validation['premium_2034_2039_pp'],
                                   'all_draw_rule_checks': validation,
                                   'draw_hashes': hashes, 'model': d['info'], 'design': design,
                                   'specs_file': f'{form}.specs.json'}
        if form == PRIMARY_FORM:
            for label, delta in (('earnings_minus_0_5pp', -0.005), ('earnings_plus_0_5pp', 0.005)):
                log(f'Paired primary {label}')
                variant = future_draws(form, long_run_earnings_variant(central, delta), n)
                variant_validation = validate_rule_draws(variant)
                if variant['info']['shock_distribution']['innovation_sha256'] != d['info']['shock_distribution']['innovation_sha256']:
                    raise AssertionError('mean-path variants changed the shocks')
                hashes = _save_draws(output / f'{label}.npz', variant)
                _write_json(output / f'{label}.specs.json', [EV.path_spec(variant, i) for i in unique])
                manifest['mean_paths'][label] = {'calendar_earnings_delta': delta, 'from_year': 2031,
                                                'paired_baseline': form, 'same_sample_indices': True,
                                                'same_shock_sha256': variant['info']['shock_distribution']['innovation_sha256'],
                                                'fiscal_eligible': True, 'interpretation': 'scenario',
                                                'presentation_pending_d955': uncertainty_ruling is None,
                                                'draw_hashes': hashes,
                                                'all_draw_rule_checks': variant_validation,
                                                'specs_file': f'{label}.specs.json',
                                                'unique_full_runs': len(unique)}
                manifest['mean_paths'][label]['extra_check_draw'] = design['identical_check_draw']
                manifest['mean_paths'][label]['extra_check_requires_zero_saving'] = False
    _write_json(output / 'handoff.json', manifest)
    return manifest


def main():
    from .ts_backtest import run_candidate_backtest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('out/uncertainty'))
    parser.add_argument('--screen', choices=('c1', 'c2'), default='c1')
    parser.add_argument('--binding', action='store_true', help='Require committed post-28-October-2026 Budget inputs; otherwise C2 is a dry run')
    parser.add_argument('--backtest-draws', type=int, default=5000)
    parser.add_argument('--draws', type=int, default=50_000)
    parser.add_argument('--full-runs', type=int, default=N_FULL_RUNS)
    parser.add_argument('--scores-only', action='store_true')
    parser.add_argument('--historical-only', action='store_true',
                        help='Re-estimate only published aggregate SEs; no backtests or new draws')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.historical_only:
        write_historical_estimator(args.output)
        return
    if args.binding and args.screen != 'c2':
        parser.error('--binding is defined only for screen c2')
    provenance = binding_input_provenance(binding=args.binding) if args.screen == 'c2' else None
    scoring_head = _git_bytes('rev-parse', 'HEAD').decode().strip() if args.screen == 'c2' else None
    backtest = run_candidate_backtest(args.backtest_draws, screen=args.screen)
    backtest['pre_registration_commit'] = C2_PRE_REGISTRATION_COMMIT if args.screen == 'c2' else PRE_REGISTRATION_COMMIT
    if args.screen == 'c2':
        backtest.update(screen='c2', rule_sha=C2_PRE_REGISTRATION_COMMIT, scoring_head=scoring_head,
                        rule_section_sha256=committed_c2_rule_hash(),
                        run_kind='binding' if args.binding else 'dry_run', binding_inputs=provenance)
    screen = adequacy(backtest, screen=args.screen)
    if args.screen == 'c2':
        backtest.update(c2_authorization(screen, binding=args.binding))
    _write_json(args.output / 'scores.json', backtest)
    selection = dict(screen)
    if args.screen == 'c2':
        selection.update(rule_sha=C2_PRE_REGISTRATION_COMMIT, scoring_head=scoring_head,
                         rule_section_sha256=committed_c2_rule_hash(),
                         run_kind='binding' if args.binding else 'dry_run',
                         **c2_authorization(screen, binding=args.binding))
    _write_json(args.output / 'selection.json', selection)
    print(json.dumps(selection, indent=2))
    if not args.scores_only:
        handoff(args.output, screen, args.draws, args.full_runs,
                uncertainty_ruling='c' if args.screen == 'c2' else None,
                screen_name=args.screen, score_table=backtest,
                binding_inputs=provenance, binding=args.binding)
        write_historical_estimator(args.output)


if __name__ == '__main__':
    main()
