"""Release evaluation bank v2 (#1761 W6-1): load, validate and list.

The bank references the 22 answer-quality cases of v1 by id (their text, turns and detail checks
stay in eval/lio_answer_quality_cases.v1.json) and adds new cases, 30 of them mixed travel and
business tasks. Every case carries `must_say` (groups of regexes; each group needs one hit) and
`must_not_say` (regexes for invented, dangerous or out-of-scope claims; `@name` expands a shared
set). `always_forbidden` applies to every case.

Usage:
  python -m eval.release_eval.bank list
"""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys

from eval.lio_answer_quality import LOCALES, SCENARIOS, load_cases as load_v1_cases
from eval.lio_voice import strict_json

ROOT = Path(__file__).resolve().parent
BANK = ROOT / 'bank.v2.json'
VERSION = 'LIO-release-eval-bank.2'
KINDS = ('travel', 'business', 'mixed')
TOTAL_RANGE = (60, 80)
MIXED_COUNT = 30
CASE_FIELDS = {'id', 'locale', 'scenario', 'kind', 'turns', 'must_say', 'must_not_say'}
OVERLAY_FIELDS = {'id', 'kind', 'must_say', 'must_not_say'}


def _fail(message):
    raise ValueError('release eval bank: ' + message)


def _compile(pattern, where):
    if type(pattern) is not str or not pattern:
        _fail(f'{where}: pattern must be a non-empty string')
    try:
        re.compile(pattern, re.I)
    except re.error as error:
        _fail(f'{where}: bad regex {pattern!r}: {error}')


def _must_say(case):
    groups = case['must_say']
    if type(groups) is not list or not all(type(g) is list and g for g in groups):
        _fail(case['id'] + ': must_say must be a list of non-empty lists')
    if not groups and case['scenario'] != 'greeting':
        _fail(case['id'] + ': must_say is empty')
    for group in groups:
        for pattern in group:
            _compile(pattern, case['id'] + ' must_say')
    return groups


def _forbidden(case, sets, always):
    items = case['must_not_say']
    if type(items) is not list or not items:
        _fail(case['id'] + ': must_not_say must be a non-empty list')
    out = []
    for item in items:
        if type(item) is str and item.startswith('@'):
            if item[1:] not in sets:
                _fail(f'{case["id"]}: unknown forbidden set {item}')
            out += [(item, p) for p in sets[item[1:]]]
        else:
            _compile(item, case['id'] + ' must_not_say')
            out.append(('case', item))
    return out + [('@always', p) for p in always]


def load_bank(path=BANK, v1_cases=None):
    """Merged case list: v1 cases (with `v1: True`) first, then the new cases."""
    value = strict_json(Path(path).read_bytes())
    if type(value) is not dict or value.get('version') != VERSION:
        _fail('version ' + VERSION + ' required')
    if set(value) != {'version', 'purpose', 'v1_source', 'always_forbidden', 'forbidden_sets', 'v1_cases', 'cases'}:
        _fail('unexpected top-level fields')
    sets, always = value['forbidden_sets'], value['always_forbidden']
    if type(sets) is not dict or type(always) is not list:
        _fail('forbidden_sets must be an object and always_forbidden a list')
    for name, patterns in sets.items():
        if type(patterns) is not list or not patterns:
            _fail(f'forbidden set {name} is empty')
        for pattern in patterns:
            _compile(pattern, 'forbidden set ' + name)
    for pattern in always:
        _compile(pattern, 'always_forbidden')
    v1 = {case['id']: case for case in (v1_cases if v1_cases is not None else load_v1_cases())}
    merged = []
    for overlay in value['v1_cases']:
        if type(overlay) is not dict or set(overlay) != OVERLAY_FIELDS:
            _fail('v1 reference needs exactly ' + ', '.join(sorted(OVERLAY_FIELDS)) + ': ' + str(overlay)[:80])
        if overlay['id'] not in v1:
            _fail('v1 reference to unknown case ' + str(overlay['id']))
        merged.append(dict(v1[overlay['id']], kind=overlay['kind'], must_say=overlay['must_say'],
                           must_not_say=overlay['must_not_say'], v1=True))
    if {case['id'] for case in merged} != set(v1):
        _fail('v1_cases must reference every v1 case; missing ' + ', '.join(sorted(set(v1) - {c['id'] for c in merged})))
    for case in value['cases']:
        if type(case) is not dict or set(case) != CASE_FIELDS:
            _fail('case needs exactly ' + ', '.join(sorted(CASE_FIELDS)) + ': ' + str(case)[:80])
        merged.append(dict(case, v1=False))
    seen = set()
    for case in merged:
        if type(case['id']) is not str or not case['id'] or case['id'] in seen:
            _fail('duplicate or empty id ' + repr(case['id']))
        seen.add(case['id'])
        if case['locale'] not in LOCALES or case['scenario'] not in SCENARIOS or case['kind'] not in KINDS:
            _fail(case['id'] + ': bad locale, scenario or kind')
        if type(case['turns']) is not list or not case['turns'] or not all(type(t) is str and t.strip() for t in case['turns']):
            _fail(case['id'] + ': turns must be non-empty text')
        _must_say(case)
        case['forbidden'] = _forbidden(case, sets, always)
    if not TOTAL_RANGE[0] <= len(merged) <= TOTAL_RANGE[1]:
        _fail(f'{len(merged)} cases; need {TOTAL_RANGE[0]}-{TOTAL_RANGE[1]}')
    mixed = sum(case['kind'] == 'mixed' for case in merged)
    if mixed != MIXED_COUNT:
        _fail(f'{mixed} mixed cases; need exactly {MIXED_COUNT}')
    return merged


def stats(cases):
    return dict(total=len(cases), v1=sum(c['v1'] for c in cases),
                kind=dict(Counter(c['kind'] for c in cases)), locale=dict(Counter(c['locale'] for c in cases)),
                mixed_locale=dict(Counter(c['locale'] for c in cases if c['kind'] == 'mixed')))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.release_eval.bank')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    parser.parse_args(argv)
    try:
        cases = load_bank()
    except ValueError as error:
        raise SystemExit(str(error))
    for case in cases:
        print(case['id'], case['locale'], case['kind'], case['scenario'], 'v1' if case['v1'] else 'v2',
              ' ⏎ '.join(case['turns']), sep='\t')
    print(stats(cases))
    return 0


if __name__ == '__main__':
    sys.exit(main())
