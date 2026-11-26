"""Offline scoring of one release evaluation run (#1761 W6-1). Never calls a model.

Run file (written by `python -m eval.release_eval.run`, or by hand):
  {"run": {"source_sha": ..., "started_at": ..., "model": ..., ...},
   "answers": {case_id: [{"text": ..., "first_token_ms": ..., "total_ms": ..., "error": null}, ...]}}

An answer passes when it has no error, hits every must_say group, triggers no must_not_say
pattern and, for the referenced v1 cases, passes `check_answer` (detail profile). A case passes
when more than half of its answers pass (2 of the default 3).

Usage:
  python -m eval.release_eval.score RUN.json [--output SCORED.json]
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import sys

from eval.lio_answer_quality import DETAIL, check_answer
from eval.lio_voice import strict_json
from eval.release_eval.bank import load_bank

ANSWER_FIELDS = {'text', 'first_token_ms', 'total_ms', 'error'}
SNIPPET = 80


def load_run(path):
    value = strict_json(Path(path).read_bytes())
    validate_run(value)
    return value


def validate_run(value):
    if type(value) is not dict or set(value) != {'run', 'answers'} or type(value['run']) is not dict:
        raise ValueError('run file needs exactly "run" and "answers"')
    if type(value['answers']) is not dict:
        raise ValueError('answers must map case id to a list of answers')
    for case_id, items in value['answers'].items():
        if type(items) is not list or not items:
            raise ValueError(f'{case_id}: answers must be a non-empty list')
        for item in items:
            if type(item) is not dict or set(item) - ANSWER_FIELDS:
                raise ValueError(f'{case_id}: answer fields are {sorted(ANSWER_FIELDS)}')
            if item.get('text') is not None and type(item['text']) is not str:
                raise ValueError(f'{case_id}: text must be a string or null')
            if item.get('error') is not None and type(item['error']) is not str:
                raise ValueError(f'{case_id}: error must be a string or null')
            for key in ('first_token_ms', 'total_ms'):
                ms = item.get(key)
                if ms is not None and (type(ms) not in (int, float) or ms < 0 or not math.isfinite(ms)):
                    raise ValueError(f'{case_id}: {key} must be a non-negative number or null')


def snippet(text, match, width=SNIPPET):
    """The match with surrounding context, at most `width` characters on one line."""
    start, end = match.span()
    room = max(width - (end - start), 0)
    a = max(start - room // 2, 0)
    b = min(a + width, len(text))
    a = max(min(a, b - width), 0)
    return ' '.join(text[a:b].split())[:width]


def score_answer(case, item):
    error = item.get('error')
    text = item.get('text') or ''
    if error is None and not text.strip():
        error = 'empty answer'
    row = dict(error=error, first_token_ms=item.get('first_token_ms'), total_ms=item.get('total_ms'),
               must_say=[], violations=[], v1_failed=[])
    if error is not None:
        row['passed'] = False
        return row
    row['must_say'] = [any(re.search(p, text, re.I) for p in group) for group in case['must_say']]
    for label, pattern in case['forbidden']:
        match = re.search(pattern, text, re.I)
        if match:
            row['violations'].append(dict(source=label, pattern=pattern, snippet=snippet(text, match)))
    if case['v1']:
        checks = check_answer(case, text, DETAIL)['checks']
        row['v1_failed'] = [name for name, ok in checks.items() if not ok]
    row['passed'] = all(row['must_say']) and not row['violations'] and not row['v1_failed']
    return row


def percentile(values, q):
    """Nearest-rank percentile; None for no values."""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(math.ceil(q / 100 * len(ordered)), 1) - 1]


def _median(values):
    return statistics.median(values) if values else None


def score_case(case, items):
    answers = [score_answer(case, item) for item in items]
    ok = [a for a in answers if a['error'] is None]
    passed_runs = sum(a['passed'] for a in answers)
    missed = sorted({n for a in ok for n, hit in enumerate(a['must_say']) if not hit})
    return dict(
        id=case['id'], kind=case['kind'], locale=case['locale'], v1=case['v1'], runs=len(answers),
        passed_runs=passed_runs, passed=passed_runs * 2 > len(answers),
        errors=len(answers) - len(ok), error_messages=sorted({a['error'] for a in answers if a['error']}),
        must_say_hits=sum(sum(a['must_say']) for a in ok), must_say_total=sum(len(a['must_say']) for a in ok),
        missed_must_say=[' / '.join(case['must_say'][n]) for n in missed],
        violations=sum(len(a['violations']) for a in ok),
        violation_details=[v for a in ok for v in a['violations']],
        v1_failed=sorted({name for a in ok for name in a['v1_failed']}),
        first_token_ms_median=_median([a['first_token_ms'] for a in ok if a['first_token_ms'] is not None]),
        total_ms_median=_median([a['total_ms'] for a in ok if a['total_ms'] is not None]),
        answers=answers)


def score_run(cases, run):
    """Score a validated run against the merged bank."""
    validate_run(run)
    rows = {case['id']: score_case(case, run['answers'][case['id']]) for case in cases if case['id'] in run['answers']}
    answers = [a for row in rows.values() for a in row['answers']]
    ok = [a for a in answers if a['error'] is None]
    hits = sum(row['must_say_hits'] for row in rows.values())
    total = sum(row['must_say_total'] for row in rows.values())

    def latency(key):
        values = [a[key] for a in ok if a[key] is not None]
        return dict(p50=percentile(values, 50), p95=percentile(values, 95), n=len(values))

    def groups(field):
        out = {}
        for case in cases:
            bucket = out.setdefault(case[field], dict(cases=0, passed=0))
            bucket['cases'] += 1
            bucket['passed'] += bool(rows.get(case['id'], {}).get('passed'))
        return out

    summary = dict(
        cases=len(cases), answered_cases=len(rows), passed_cases=sum(row['passed'] for row in rows.values()),
        answers=len(answers), passed_answers=sum(a['passed'] for a in answers), errors=len(answers) - len(ok),
        must_say_hit_rate=round(hits / total, 3) if total else None,
        violations=sum(row['violations'] for row in rows.values()),
        violation_answers=sum(bool(a['violations']) for a in ok),
        first_token_ms=latency('first_token_ms'), total_ms=latency('total_ms'),
        by_kind=groups('kind'), by_locale=groups('locale'))
    known = {case['id'] for case in cases}
    return dict(run=run['run'], summary=summary, cases=rows,
                missing=[case['id'] for case in cases if case['id'] not in rows],
                unknown=sorted(set(run['answers']) - known))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.release_eval.score')
    parser.add_argument('run')
    parser.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        result = score_run(load_bank(), load_run(args.run))
    except ValueError as error:
        raise SystemExit(str(error))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    for row in result['cases'].values():
        print('PASS' if row['passed'] else 'FAIL', row['id'], f"{row['passed_runs']}/{row['runs']}",
              f"violations={row['violations']}", f"errors={row['errors']}", sep='\t')
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
