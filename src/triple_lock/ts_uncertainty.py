"""Model-v2 uncertainty pilot and reproducible fiscal-run handoff, without simulation.

Run with ``python -m triple_lock.ts_uncertainty --output out/uncertainty``.
The fixed scoring/adequacy rule was committed in docs/METHOD.md before scoring.
Draw artifacts are independent of the PolicyEngine job cache.
"""

import argparse
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
N_FULL_RUNS = 160


def candidate_paths(form, years, n, seed, end_obs=None, calendar_target=None):
    config = CANDIDATES[form]
    if config.get('annual'):
        return ts_annual.paths(years, n, seed, end_obs=end_obs, calendar_target=calendar_target)
    return ts_monthly.paths(years, n, seed, end_obs=end_obs, calendar_target=calendar_target,
                            kind=config['kind'], lag_order=config['lag_order'])


def adequacy(backtest):
    """Apply the pre-registered screen literally; no fitted/tuned thresholds."""
    decision = {}
    for form in CANDIDATES:
        failures, ratios = [], []
        for test in ('A', 'B'):
            for treatment in ('published', 'suspended'):
                s = backtest['scores'][test][treatment][form]
                ref = backtest['scores'][test][treatment][PRIMARY_FORM]
                tag = f'{test}/{treatment}'
                if s['n_origins'] != s['expected_origins'] or s['n_origins'] < 2:
                    failures.append(f'{tag}: missing/failed origins')
                    continue
                if any(not np.isfinite(metric['mean']) for metric in s.values()
                       if isinstance(metric, dict) and 'mean' in metric):
                    failures.append(f'{tag}: non-finite score or statistic')
                for k in ('annual_gap_coverage', 'terminal_coverage'):
                    if not 0.5 <= s[k]['mean'] <= 1.0:
                        failures.append(f'{tag}: {k} {s[k]["mean"]:.3f} outside [0.50, 1.00]')
                lo, hi = s['terminal_coverage']['wilson95_independent']
                if not lo <= 0.8 <= hi:
                    failures.append(f'{tag}: terminal coverage Wilson band excludes 0.80')
                for k, limit in (('gap_bias_pp', 1.5), ('switch_bias', 1.0), ('floor_bias', 0.25)):
                    if abs(s[k]['mean']) > limit:
                        failures.append(f'{tag}: |{k}| {abs(s[k]["mean"]):.3f} exceeds {limit}')
                for k in PROPER_SCORES:
                    value, baseline = s[k]['mean'], ref.get(k, {}).get('mean')
                    if baseline is None:
                        failures.append(f'{tag}: no primary reference for {k}')
                        continue
                    ratio = value / baseline if baseline > 0 else (1.0 if value == 0 else float('inf'))
                    ratios.append(ratio)
                    if not np.isfinite(ratio) or ratio > 1.25:
                        failures.append(f'{tag}: {k} ratio {ratio:.3f} exceeds 1.25')
        p = backtest['past_years'][form]
        for treatment in ('published', 'suspended'):
            q = p.get(treatment, {}).get('realised_percentile')
            if q is None or not np.isfinite(q) or not 5 <= q <= 95:
                label = 'missing' if q is None else f'{q:.2f}'
                failures.append(f'past/{treatment}: realised percentile {label} outside [5, 95]')
        rank = (float(np.exp(np.mean(np.log(np.maximum(ratios, 1e-15)))))
                if ratios and np.isfinite(ratios).all() else None)
        decision[form] = {'passes': not failures, 'failures': failures, 'proper_score_ratio_geomean': rank}
    passing = [f for f in CANDIDATES if decision[f]['passes']]
    chosen = PRIMARY_FORM if PRIMARY_FORM in passing else (
        min(passing, key=lambda f: decision[f]['proper_score_ratio_geomean']) if passing else None)
    return {'forms': decision, 'passing_forms': passing, 'selected_primary': chosen,
            'primary_retained': chosen == PRIMARY_FORM,
            'interpretation': 'Scenario envelope; never a probability interval; do not average forms.'}


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


def handoff(output, screen, n=50_000, n_runs=N_FULL_RUNS, log=print):
    """Save own-form draws/strata/specs for passing forms; original-primary diagnostics.

    No engine is imported or run. Diagnostic primary and mean paths remain
    explicitly blocked from fiscal execution if the primary fails the screen.
    """
    from . import expected_value as EV

    central = central_path()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'n_draws': n, 'draw_seed': SEED, 'sample_seed': SAMPLE_SEED,
                'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
                'runtime': runtime_provenance(),
                'rate_decimals': 3, 'gap_unit': 'level relative to base pension = 1',
                'obr_2034_2039_premium_pp': obr_premium_comparator(central),
                'forms': {}, 'mean_paths': {}, 'no_microsimulation': True,
                'rebuild_needs': ['Certified PolicyEngine/data bundle and baseline acceptance gates',
                                  'Updated Autumn Budget OBR means and refreshed September CPI',
                                  'Re-run this frozen screen on the updated committed inputs',
                                  'Full paired rule runs only for passing forms; no interpolation',
                                  'Paired original-primary mean paths only if that primary passes',
                                  'Separate path-sampling/first-phase SEs for every output and year',
                                  'Scenario envelope across passing forms; no model averaging']}
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
        eligible = form in screen['passing_forms']
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
                                                'fiscal_eligible': eligible, 'draw_hashes': hashes,
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
    backtest = run_candidate_backtest(args.backtest_draws)
    backtest['pre_registration_commit'] = PRE_REGISTRATION_COMMIT
    _write_json(args.output / 'scores.json', backtest)
    screen = adequacy(backtest)
    _write_json(args.output / 'selection.json', screen)
    print(json.dumps(screen, indent=2))
    if not args.scores_only:
        handoff(args.output, screen, args.draws, args.full_runs)
        write_historical_estimator(args.output)


if __name__ == '__main__':
    main()
