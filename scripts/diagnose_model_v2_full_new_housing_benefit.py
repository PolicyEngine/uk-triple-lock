"""Replay complete kept/full-new fiscal paths and publish only HB group aggregates.

Requires a frozen fiscal source export and its aggregate caches. This diagnoses
one original macro path, with all thirteen years calculated anew and independent
simulation clones. Survey arrays exist only transiently and are never written.
"""
import argparse
from pathlib import Path
import os, sys, json, hashlib, subprocess, re, importlib.util
from datetime import datetime, timezone
import psutil
import numpy as np

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--specs', default=Path('data/pilot/d_macro_specs.json'), type=Path)
    parser.add_argument('--fiscal', default=Path('data/pilot/model_v2_e.json'), type=Path)
    parser.add_argument('--out', default=Path('data/pilot/full_new_net_se_diagnostic.json'), type=Path)
    parser.add_argument('--path-index', default=39769, type=int)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'status': 'planned; no model run', 'path_index': args.path_index, 'full_path_count': 2, 'fiscal_years': list(range(2027, 2040)), 'maximum_workers': 1}))
        return
    ROOT = Path.cwd().resolve()
    SOURCE = args.source.resolve()
    PUBLIC = args.out.resolve()
    if not SOURCE.is_relative_to(ROOT) or not PUBLIC.is_relative_to(ROOT):
        raise ValueError('source and output must be inside this workspace')
    os.umask(63)
    sys.path.insert(0, str(SOURCE / 'src'))
    from triple_lock import engine as E, jobs, model_horizon

    def resources():
        out = subprocess.check_output(['vm_stat'], text=True)
        page = int(re.search('page size of (\\d+) bytes', out)[1])
        counts = {name: int(re.search(f'{name}:\\s*(\\d+)', out)[1]) for name in ['Pages free', 'Pages inactive', 'Pages speculative']}
        cpu = os.cpu_count()
        available = psutil.virtual_memory().available / 2 ** 30
        vm = sum(counts.values()) * page / 2 ** 30
        r = {'at': datetime.now(timezone.utc).isoformat(), 'cpu_count': cpu, 'available_gib': available, 'vm_stat_available_gib': vm, 'load': list(os.getloadavg()), 'maximum_workers': 1}
        if min(available, vm) < 40:
            raise RuntimeError('resources not admitted')
        return r

    def emit(**kw):
        print(json.dumps(kw, sort_keys=True), flush=True)
    records = []
    for p in (args.cache or SOURCE / '.cache/jobs-pilot-e').glob('treatment_paths-*.json'):
        r = json.loads(p.read_text())
        spec = json.loads(args.specs.read_text())['paired'][str(args.path_index)]['spec']
        s = r['arg']['specs']['both']
        macro = {k: v for k, v in s.items() if k not in ['dataset', 'demography', 'retyped_level', 'fiscal_output_years']}
        if macro == spec:
            record = r
            break
    else:
        raise RuntimeError('target path cache missing')
    assert E.engine_semantics() == record['engine']
    assert E.package_versions() == record['packages']
    assert E.job_key(record['kind'], record['arg'], record['engine'], record['packages']) == record['key']
    arguments = E._keys_to_int(record['arg'])
    original_totals = E.totals
    variables = ['guarantee_credit', 'housing_benefit_pension_age_regulations_apply', 'housing_benefit_applicable_income', 'housing_benefit_assessable_capital', 'housing_benefit_eligible', 'housing_benefit_entitlement', 'housing_benefit', 'housing_benefit_pre_benefit_cap', 'benefit_cap_reduction', 'would_claim_housing_benefit', 'pension_credit', 'in_receipt_of_guarantee_credit', 'minimum_guarantee', 'pension_credit_income', 'is_guarantee_credit_eligible', 'is_pension_credit_eligible']
    monetary = {'guarantee_credit', 'housing_benefit', 'pension_credit'}
    arrays = []

    def captured_totals(sim, years):
        output = {}
        for year in years:
            output.update(original_totals(sim, [year]))
            emit(status='fiscal totals completed', year=year,
                 policy_position=len(arrays))
        table = {}
        for y in [2034, 2039]:
            d = {v: np.asarray(sim.calculate(v, y).to_numpy(), dtype=np.float64).copy() for v in variables}
            d['weights'] = np.asarray(sim.calculate('housing_benefit', y).weights.to_numpy(), dtype=np.float64).copy()
            expected_gc = np.maximum(0, d['minimum_guarantee'].astype(np.float64) - d['pension_credit_income'].astype(np.float64)) * d['is_guarantee_credit_eligible'].astype(bool) * d['is_pension_credit_eligible'].astype(bool)
            d['formula_matches_float64'] = bool(np.allclose(d['guarantee_credit'], expected_gc, rtol=0, atol=0.01))
            d['passport'] = d['housing_benefit_pension_age_regulations_apply'].astype(bool) & (d['guarantee_credit'] > 0)
            assert abs(np.sum(d['housing_benefit'] * d['weights']) / 1000000000.0 - output[y]['variables']['housing_benefit']) < 1e-06
            table[y] = d
        arrays.append(table)
        return output

    def aggregate_group(a, b, mask):
        supported = (a['weights'] > 0) | (b['weights'] > 0)
        count = int(np.count_nonzero(mask & supported))
        if 0 < count < 10:
            return {'status': 'withheld_family', 'records': None}
        summary = {'status': 'available', 'records': count, 'components_bn': {v: {'support_records': {'triple_lock': int(np.count_nonzero((a[v] != 0) & mask & (a['weights'] > 0))), 'burnham_2030': int(np.count_nonzero((b[v] != 0) & mask & (b['weights'] > 0))), 'change': int(np.count_nonzero((b[v] != a[v]) & mask & (a['weights'] > 0)))}, 'triple_lock': float(np.sum(a[v][mask] * a['weights'][mask]) / 1000000000.0), 'burnham_2030': float(np.sum(b[v][mask] * b['weights'][mask]) / 1000000000.0), 'change': float(np.sum((b[v][mask] - a[v][mask]) * a['weights'][mask]) / 1000000000.0)} for v in sorted(monetary)}}
        return summary
    admission = resources()
    emit(status='admitted', **admission)
    registry = ROOT / '.cache' / f'{args.out.stem}.pid.json'
    registry.write_text(json.dumps({'pid': os.getpid(), **admission}, indent=2) + '\n')
    original_managed = E._managed

    def guarded_managed(*args, **kwargs):
        snapshot = resources()
        emit(status='immediate dataset load admission', **snapshot)
        return original_managed(*args, **kwargs)
    E._managed = guarded_managed
    with model_horizon.installed(), jobs.slot_lock(SOURCE / '.cache/workers/h-item4-efrs-correct0'):
        template = E._prepare_path_template(arguments['specs']['both'])
        try:
            for treatment in ['both', 'both_full_new']:
                admission = resources()
                emit(status='starting full 13-year path', treatment=treatment, **admission)
                arrays.clear()
                E.totals = captured_totals
                result = E.run_path(arguments['specs'][treatment], _template=template)
                E.totals = original_totals
                assert len(arrays) == 2
                comparisons = {}
                for y in [2034, 2039]:
                    expected = record['result'][treatment]['saving_bn'][str(y)]
                    actual = result['saving_bn'][y]
                    comparisons[str(y)] = {m: {'cached_bn': expected[m], 'replay_bn': actual[m], 'difference_bn': actual[m] - expected[m]} for m in ['gross', 'net']}
                    assert all((abs(actual[m] - expected[m]) <= 0.001 for m in ['gross', 'net']))
                diagnostics = {}
                for y in [2034, 2039]:
                    a, b = (arrays[0][y], arrays[1][y])
                    assert np.array_equal(a['weights'], b['weights'])
                    masks = {'passport_both': a['passport'] & b['passport'], 'passport_triple_lock_only': a['passport'] & ~b['passport'], 'passport_burnham_only': ~a['passport'] & b['passport'], 'passport_neither': ~a['passport'] & ~b['passport']}
                    groups = {name: aggregate_group(a, b, mask) for name, mask in masks.items()}
                    national = aggregate_group(a, b, np.ones(len(a['weights']), dtype=bool))
                    for variable in monetary:
                        if any(0 < count < 10 for count in national['components_bn'][variable]['support_records'].values()):
                            national['components_bn'][variable] = {'status': 'withheld_family', 'support_records': None, 'triple_lock': None, 'burnham_2030': None, 'change': None}
                    if any((g['status'] != 'available' for g in groups.values())):
                        groups = {name: {'status': 'withheld_family', 'records': None} for name in masks}
                    else:
                        for variable in monetary:
                            if any((0 < count < 10 for group in groups.values() for count in group['components_bn'][variable]['support_records'].values())):
                                for group in groups.values():
                                    group['components_bn'][variable] = {'status': 'withheld_family', 'support_records': None, 'triple_lock': None, 'burnham_2030': None, 'change': None}
                    bucket_masks = {'zero_both': (a['guarantee_credit'] == 0) & (b['guarantee_credit'] == 0), 'positive_up_to_one_penny': (np.maximum(a['guarantee_credit'], b['guarantee_credit']) > 0) & (np.maximum(a['guarantee_credit'], b['guarantee_credit']) <= 0.01), 'above_one_penny_up_to_one_pound': (np.maximum(a['guarantee_credit'], b['guarantee_credit']) > 0.01) & (np.maximum(a['guarantee_credit'], b['guarantee_credit']) <= 1), 'above_one_pound_up_to_ten_pounds': (np.maximum(a['guarantee_credit'], b['guarantee_credit']) > 1) & (np.maximum(a['guarantee_credit'], b['guarantee_credit']) <= 10), 'above_ten_pounds': np.maximum(a['guarantee_credit'], b['guarantee_credit']) > 10}
                    flips = (a['passport'] != b['passport']) & (a['weights'] > 0)
                    buckets = {name: int(np.count_nonzero(flips & mask)) for name, mask in bucket_masks.items()}
                    if any((0 < count < 10 for count in buckets.values())):
                        buckets = {name: None for name in buckets}
                    diagnostics[str(y)] = {'national_components': national, 'passport_groups': groups, 'passport_flip_guarantee_credit_amount_buckets_records': buckets, 'guarantee_credit_formula_matches_float64_to_one_penny': a['formula_matches_float64'] and b['formula_matches_float64']}
                records.append({'treatment': treatment, 'full_horizon': list(E.HORIZON), 'saving_replay': comparisons, 'housing_benefit_passport_groups': diagnostics})
                (ROOT / '.cache' / f'{args.out.stem}-completed-paths.json').write_text(json.dumps({'path_index': args.path_index, 'cache_key': record['key'], 'completed_runs': records}, indent=2) + '\n')
                arrays.clear()
                del result
                emit(status='full path completed; published aggregates only', treatment=treatment)
        finally:
            E.totals = original_totals
    assert E.engine_semantics() == record['engine']
    uk_package = Path(importlib.util.find_spec('policyengine_uk').origin).parent
    formula_files = [
        'variables/gov/dwp/housing_benefit/applicable_income/housing_benefit_applicable_income.py',
        'variables/gov/dwp/housing_benefit/housing_benefit_assessable_capital.py',
        'variables/gov/dwp/housing_benefit/entitlement/housing_benefit_entitlement.py',
        'variables/gov/dwp/housing_benefit/housing_benefit_eligible.py',
        'variables/gov/dwp/pension_credit/guarantee_credit/guarantee_credit.py',
        'variables/gov/dwp/pension_credit/guarantee_credit/is_guarantee_credit_eligible.py',
        'variables/gov/dwp/pension_credit/pension_credit_income.py',
    ]
    formula_hashes = {path: hashlib.sha256((uk_package / path).read_bytes()).hexdigest()
                      for path in formula_files}
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(), 'status': 'two full PolicyEngine UK paths; aggregates only', 'path_index': args.path_index, 'source_head_provenance': json.loads(args.fiscal.read_text())['provenance']['calculation_head'], 'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'input_files_sha256': {'data/pilot/d_macro_specs.json': hashlib.sha256(args.specs.read_bytes()).hexdigest(), 'data/pilot/model_v2_e.json': hashlib.sha256(args.fiscal.read_bytes()).hexdigest()}, 'policyengine_formula_source_sha256': formula_hashes, 'engine_semantics': record['engine'], 'packages': record['packages'], 'original_batch_cache_key': record['key'], 'specification_sha256': hashlib.sha256(E._canonical(record['arg']['specs']).encode()).hexdigest(), 'admission': admission, 'minimum_records': 10, 'method': 'Same frozen fiscal source and original macro input, one fresh pristine setup, independent deep clones for every policy/treatment. Every path calculates all thirteen fiscal years. Derived diagnostics are transient benefit-unit arrays aggregated into the four exhaustive guarantee-credit Housing Benefit passport groups. If any group has 1–9 positive-weight records all linked groups are withheld. No record id, weight or record amount is written.', 'runs': records}
    PUBLIC.write_text(json.dumps(payload, indent=2) + '\n')
    emit(status='diagnostic completed', receipt=str(PUBLIC.relative_to(ROOT)))
if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status': 'diagnostic stopped; private inputs withheld', 'error_type': type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
