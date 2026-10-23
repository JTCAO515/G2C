#!/usr/bin/env python3
"""CJ-028 offline record validation; no agent execution or release authority."""
import argparse
from collections import Counter
from decimal import Context, Decimal, DecimalException, Inexact, localcontext
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import sys


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def unique_objects(items, label):
    require(isinstance(items, list) and items, label + ' must be a nonempty list')
    result = {}
    for item in items:
        require(isinstance(item, dict) and nonempty(item.get('id')), label + ' needs id')
        require(item['id'] not in result, label + ' duplicate id: ' + item['id'])
        result[item['id']] = item
    return result


def amount(value):
    require(isinstance(value, str), 'cost amount must be a decimal string or null')
    require(len(value) <= 256, 'cost amount exceeds 256-character input limit')
    try:
        result = Decimal(value)
    except DecimalException as exc:
        raise InputError('invalid cost amount') from exc
    require(result.is_finite() and result >= 0, 'invalid cost amount')
    parts = result.as_tuple()
    require(len(parts.digits) <= 100 and -100 <= parts.exponent <= 100
            and result.adjusted() <= 100,
            'cost amount outside supported range: 100 coefficient digits, exponent -100..100, adjusted exponent <=100')
    return result


def exact_sum(values):
    # Nonnegative bounded amounts: aligned digits plus carry space for every term.
    precision = (max(value.adjusted() for value in values)
                 - min(value.as_tuple().exponent for value in values)
                 + len(str(len(values))) + 1)
    with localcontext(Context(prec=max(1, precision))) as context:
        context.traps[Inexact] = True
        return sum(values, Decimal(0))


def validate(plan, records):
    require(isinstance(plan, dict) and type(plan.get('schema_version')) is int
            and plan['schema_version'] == 1, 'plan schema_version must be integer 1')
    for key in ('sample_set_id', 'sample_set_version', 'provenance'):
        require(nonempty(plan.get(key)), 'plan needs ' + key)
    require(plan.get('evidence_layer') in ('synthetic', 'local', 'real'), 'invalid evidence_layer')
    scenarios = unique_objects(plan.get('scenarios'), 'scenarios')
    candidates = unique_objects(plan.get('candidates'), 'candidates')
    networks = unique_objects(plan.get('networks'), 'networks')
    product = holdout = 0
    for scenario in scenarios.values():
        require(type(scenario.get('product')) is bool, 'scenario needs product boolean')
        require(scenario.get('split') in ('tuning', 'holdout'), 'invalid split')
        require(type(scenario.get('used_for_tuning')) is bool, 'scenario needs tuning history boolean')
        require(nonempty(scenario.get('history_ref')), 'scenario needs history_ref (including explicit unknown)')
        for key in ('input_version', 'expectation_ref', 'pairing_ref', 'task_kind'):
            require(nonempty(scenario.get(key)), 'scenario needs ' + key)
        require(isinstance(scenario.get('inputs'), dict) and set(scenario['inputs']) == {'zh', 'en'},
                'scenario requires exactly zh/en inputs')
        require(all(nonempty(v) for v in scenario['inputs'].values()), 'empty language input')
        require(not (scenario['split'] == 'holdout' and scenario['used_for_tuning']), 'holdout tuning leakage')
        if scenario['product']:
            product += 1
            holdout += scenario['split'] == 'holdout'
    require(product > 0 and holdout * 3 >= product, 'at least 1/3 independent product scenarios must be holdout')
    for candidate in candidates.values():
        require(isinstance(candidate.get('commit'), str) and re.fullmatch(r'[0-9a-f]{40}', candidate['commit']),
                'candidate needs full commit SHA')
        for key in ('config_version', 'model_version', 'source_as_of'):
            require(nonempty(candidate.get(key)), 'candidate needs ' + key)
    for network in networks.values():
        require(nonempty(network.get('description')), 'network needs description')
    attempts = plan.get('attempts')
    require(isinstance(attempts, list) and attempts and all(type(a) is int and a > 0 for a in attempts)
            and len(set(attempts)) == len(attempts), 'attempts must be distinct positive integers')
    require(isinstance(records, list), 'observations must be a JSON list')
    seen = set()
    for record in records:
        require(isinstance(record, dict), 'observation must be an object')
        for key, allowed in (('scenario_id', scenarios), ('candidate_id', candidates), ('network_id', networks),
                             ('language', ('zh', 'en')), ('attempt', attempts)):
            require(record.get(key) in allowed, 'unknown observation ' + key)
        key = record_key(record)
        require(key not in seen, 'duplicate attempt: ' + str(key))
        seen.add(key)
        require(record.get('status') in ('success', 'failure', 'timeout', 'unknown', 'missing'), 'invalid status')
        require(record.get('purpose') in ('tuning', 'evaluation', 'holdout'), 'invalid purpose')
        require(not (scenarios[record['scenario_id']]['split'] == 'holdout' and record['purpose'] == 'tuning'),
                'holdout tuning leakage')
        require(type(record.get('attempt')) is int, 'attempt must be an integer')
        for field in ('attempt_source', 'observed_at', 'source_as_of'):
            require(nonempty(record.get(field)), 'observation needs ' + field)
        candidate = candidates[record['candidate_id']]
        for field in ('commit', 'config_version', 'model_version'):
            require(field not in record or record[field] == candidate[field],
                    'observation conflicts with candidate ' + field)
        for field in ('first_body_seconds', 'draft_seconds'):
            require(record.get(field) is None or number(record[field]), 'invalid latency ' + field)
        judgment = record.get('judgment')
        if judgment is not None:
            require(isinstance(judgment, dict), 'judgment must be object or null')
            require(judgment.get('kind') in ('human', 'program', 'model'), 'invalid judgment kind')
            require(judgment.get('outcome') in ('PASS', 'FAIL', 'UNKNOWN'), 'invalid judgment outcome')
            require(nonempty(judgment.get('ref')), 'judgment needs ref')
            require(type(judgment.get('independent')) is bool, 'judgment needs independent boolean')
        errors = record.get('serious_errors', [])
        require(isinstance(errors, list), 'serious_errors must be a list')
        for error in errors:
            require(isinstance(error, dict) and error.get('kind') in ('human', 'program')
                    and nonempty(error.get('ref')) and nonempty(error.get('description'))
                    and type(error.get('resolved')) is bool, 'serious errors require explicit external judgments')
        cost = record.get('cost')
        if cost is not None:
            require(isinstance(cost, dict) and type(cost.get('complete')) is bool, 'cost needs complete boolean')
            require(isinstance(cost.get('components'), list), 'cost needs components list')
            require(not cost['complete'] or bool(cost['components']), 'complete cost requires components (explicit zero allowed)')
            for component in cost['components']:
                require(isinstance(component, dict) and nonempty(component.get('name'))
                        and nonempty(component.get('currency')) and nonempty(component.get('source')),
                        'cost component needs name/currency/source')
                if component.get('amount') is not None:
                    amount(component['amount'])
    return scenarios, candidates, networks


def record_key(record):
    return tuple(record[k] for k in ('candidate_id', 'scenario_id', 'language', 'network_id', 'attempt'))


def outcome(record):
    if record is None or record['status'] == 'missing':
        return 'UNRUN'
    if any(not e['resolved'] for e in record.get('serious_errors', [])):
        return 'FAIL'
    if record['status'] == 'failure':
        return 'FAIL'
    judgment = record.get('judgment')
    supported = (judgment and judgment['kind'] in ('human', 'program') and judgment['independent']
                 and nonempty(record.get('raw_evidence_ref')))
    if supported and judgment['outcome'] == 'FAIL':
        return 'FAIL'
    if supported and judgment['outcome'] == 'PASS' and record['status'] == 'success':
        return 'PASS'
    return 'UNKNOWN'


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def latency(rows, field):
    values = sorted(r[field] for r in rows if r is not None and r.get(field) is not None)
    n = len(values)
    return {'known_n': n, 'planned_n': len(rows), 'unknown_or_missing_n': len(rows) - n,
            'p50': values[math.ceil(.5 * n) - 1] if n else None,
            'p95': values[math.ceil(.95 * n) - 1] if n else None,
            'max': max(values) if n else None, 'threshold_decision': 'UNKNOWN'}


def costs(rows):
    totals = {}
    complete = 0
    unknown_components = 0
    for record in rows:
        cost = record.get('cost') if record else None
        if cost is None:
            continue
        components = cost['components']
        known = all(c.get('amount') is not None for c in components)
        complete += bool(cost['complete'] and known)
        for component in components:
            if component.get('amount') is None:
                unknown_components += 1
            else:
                currency = component['currency']
                totals.setdefault(currency, []).append(amount(component['amount']))
    return {'known_subtotals_by_currency': {k: str(exact_sum(v)) for k, v in sorted(totals.items())},
            'complete_attempt_n': complete, 'unknown_or_missing_attempt_n': len(rows) - complete,
            'unknown_component_n': unknown_components, 'planned_attempt_n': len(rows),
            'total_cost_known': complete == len(rows), 'budget_decision': 'UNKNOWN'}


def summarize(plan, records):
    scenarios, candidates, networks = validate(plan, records)
    index = {record_key(r): r for r in records}
    groups = []
    severe = []
    for record in records:
        for error in record.get('serious_errors', []):
            severe.append({'attempt_key': list(record_key(record)), **error})
    # Split is part of each cell: tuning results never improve holdout rates.
    task_kinds = sorted({s['task_kind'] for s in scenarios.values()})
    for candidate, language, network, split, task_kind in itertools.product(
            candidates, ('zh', 'en'), networks, ('tuning', 'holdout'), task_kinds):
        ids = [s['id'] for s in scenarios.values() if s['split'] == split and s['task_kind'] == task_kind]
        if not ids:
            continue
        keys = [(candidate, sid, language, network, a) for sid in ids for a in plan['attempts']]
        rows = [index.get(key) for key in keys]
        counts = Counter(outcome(r) for r in rows)
        planned = len(rows)
        started = planned - counts['UNRUN']
        groups.append({'candidate_id': candidate, 'candidate': candidates[candidate], 'language': language,
                       'network_id': network, 'network': networks[network], 'evidence_layer': plan['evidence_layer'],
                       'split': split, 'task_kind': task_kind, 'independent_scenario_n': len(ids), 'planned_attempt_n': planned,
                       'serious_errors': [e for e in severe if e['attempt_key'][0] == candidate
                                          and e['attempt_key'][1] in ids and e['attempt_key'][2] == language
                                          and e['attempt_key'][3] == network],
                       'outcomes': {k: counts[k] for k in ('PASS', 'FAIL', 'UNKNOWN', 'UNRUN')},
                       'statuses': dict(Counter(r['status'] if r else 'missing' for r in rows)),
                       'pass_rate': ratio(counts['PASS'], started), 'failure_rate': ratio(counts['FAIL'], started),
                       'unknown_rate': ratio(counts['UNKNOWN'], started),
                       'conservative_not_passed_rate': ratio(counts['FAIL'] + counts['UNKNOWN'], started),
                       'coverage': ratio(started, planned),
                       'first_body_seconds': latency(rows, 'first_body_seconds'),
                       'draft_seconds': latency(rows, 'draft_seconds'), 'cost': costs(rows),
                       'attempts': [{'key': list(key), 'outcome': outcome(row), 'observation': row}
                                    for key, row in zip(keys, rows)]})
    product = [s for s in scenarios.values() if s['product']]
    holdout = [s for s in product if s['split'] == 'holdout']
    reuse = []
    for sid, language, network in itertools.product(scenarios, ('zh', 'en'), networks):
        uses = [r for r in records if r['scenario_id'] == sid and r['language'] == language and r['network_id'] == network
                and r['status'] != 'missing']
        if len(uses) > 1:
            reuse.append({'scenario_id': sid, 'language': language, 'network_id': network,
                          'split': scenarios[sid]['split'], 'attempt_keys': [list(record_key(r)) for r in uses]})
    blockers = ['offline summary has no product release authority; H/I and real acceptance remain unverified']
    if not plan.get('approved_thresholds'):
        blockers.append('thresholds unconfirmed')
    if any(g['outcomes']['UNKNOWN'] or g['outcomes']['UNRUN'] for g in groups):
        blockers.append('unknown or missing task evidence')
    if any(not e['resolved'] for e in severe):
        blockers.append('unresolved externally judged serious errors')
    return {'schema_version': 1, 'validation': 'PASS', 'release_decision': 'UNKNOWN' if any(r['status'] != 'missing' for r in records) else 'UNRUN',
            'release_blockers': blockers, 'plan': plan, 'independent_product_scenario_n': len(product),
            'holdout_product_scenario_n': len(holdout), 'holdout_fraction': ratio(len(holdout), len(product)),
            'observed_attempt_n': len(records), 'groups': groups, 'serious_errors': severe,
            'repeated_uses': reuse, 'raw_observations': records}


def read_json(data):
    def duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON object key: ' + key)
            result[key] = value
        return result
    return json.loads(data.decode('utf-8'), object_pairs_hook=duplicate_keys,
                      parse_constant=lambda value: (_ for _ in ()).throw(InputError('nonfinite JSON number: ' + value)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenarios', type=Path, required=True, help='explicit JSON plan file')
    parser.add_argument('--observations', type=Path, required=True, help='explicit JSON observation array')
    args = parser.parse_args(argv)
    inputs = {}
    payloads = {}
    try:
        for name, path in (('scenarios', args.scenarios), ('observations', args.observations)):
            payloads[name] = path.read_bytes()
            inputs[name] = {'path': str(path.resolve()), 'sha256': hashlib.sha256(payloads[name]).hexdigest()}
        plan = read_json(payloads['scenarios'])
        records = read_json(payloads['observations'])
        report = summarize(plan, records)
        exit_code = 0
    except (InputError, OSError, ValueError, TypeError, KeyError, DecimalException) as exc:
        report = {'validation': 'FAIL', 'release_decision': 'UNKNOWN', 'error': str(exc),
                  'plan': locals().get('plan'), 'raw_observations': locals().get('records')}
        exit_code = 2
    report['input_files'] = inputs
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2, allow_nan=False)
    sys.stdout.write('\n')
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
