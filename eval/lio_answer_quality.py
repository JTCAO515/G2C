"""Offline answer-quality checks for default Lio dialogue (#1472 / #1473).

Scores model-written answer text for concrete content (places, times, prices,
steps), day-by-day structure and template phrases. It never calls a model,
dispatches a message or grants a save; answers come from a JSON file that maps
case id to the visible answer text.

Usage:
  python -m eval.lio_answer_quality cases                 # list questions
  python -m eval.lio_answer_quality score answers.json    # score answers
"""
import argparse
import json
from pathlib import Path
import re
import sys

from eval.lio_voice import COORDINATES, INTERNAL, count_units, strict_json

ROOT = Path(__file__).resolve().parent
CASES = ROOT / 'lio_answer_quality_cases.v1.json'
VERSION = 'LIO-answer-quality-checks.1'
LOCALES = ('zh', 'en')
SCENARIOS = ('planning', 'practical', 'recommendation', 'emergency', 'chat', 'greeting', 'followup')

# Fixed openings and self-introductions copied into non-greeting answers.
TEMPLATE_PHRASES = re.compile(
    r'准备去哪儿玩|你好！?准备|Where are you off to|^\s*(?:你好|您好|Hey|Hi|Hello)\s*[!！,，]'
    r'|^\s*(?:我是\s*Lio|I[\'’]m Lio)', re.I | re.M)
TEST_LEAK = re.compile(r'synthetic|合成(?:数据|测试)|测试数据', re.I)
DAY_MARK = {'zh': r'第\s*(?:{n}|{cn})\s*天', 'en': r'Day\s*{n}\b'}
CN_DIGITS = '零一二三四五六七八九十'
PERIODS = {'zh': re.compile(r'早上|上午|中午|午饭|午餐|下午|傍晚|晚上|晚饭|晚餐|夜'),
           'en': re.compile(r'\b(?:morning|noon|lunch|afternoon|evening|dinner|night)\b', re.I)}
LIST_ITEM = re.compile(r'^\s*(?:[-+*•]\s+|\d+[.)、．]\s*|[一二三四五六七八九十]+[、.．])', re.M)
SENTENCE_END = re.compile(r'[。！？!?\n]|\.(?:\s|$)')


def load_cases(path=CASES):
    value = strict_json(Path(path).read_bytes())
    if type(value) is not dict or value.get('version') != 'LIO-answer-quality-cases.1':
        raise ValueError('answer quality cases version required')
    cases = value['cases']
    seen = set()
    for case in cases:
        if (case['id'] in seen or case['locale'] not in LOCALES or case['scenario'] not in SCENARIOS
                or type(case['turns']) is not list or not case['turns']):
            raise ValueError('invalid answer quality case: ' + str(case.get('id')))
        seen.add(case['id'])
        for group in case.get('require', ()):
            for pattern in group:
                re.compile(pattern)
    return cases


def _day_sections(text, locale, days):
    """Split the answer at its day markers; None when any day is missing or out of order."""
    starts = []
    for n in range(1, days + 1):
        pattern = DAY_MARK[locale].format(n=n, cn=CN_DIGITS[n] if n <= 10 else n)
        match = re.search(pattern, text, re.I)
        if match is None:
            return None
        starts.append(match.start())
    if starts != sorted(starts):
        return None
    ends = starts[1:] + [len(text)]
    return [text[a:b] for a, b in zip(starts, ends)]


def check_answer(case, answer):
    """Deterministic surface checks. Factual accuracy still needs human or judge review."""
    if type(answer) is not str or not answer.strip():
        raise ValueError('missing model answer for ' + case['id'])
    locale = case['locale']
    units = count_units(answer, locale)
    checks = {}
    checks['red_line'] = not (INTERNAL.search(answer) or COORDINATES.search(answer) or TEST_LEAK.search(answer))
    if case['scenario'] != 'greeting':
        checks['no_template'] = TEMPLATE_PHRASES.search(answer) is None
    if 'min_units' in case:
        checks['detail_length'] = units >= case['min_units']
    if 'max_units' in case:
        checks['brief'] = units <= case['max_units']
    for index, group in enumerate(case.get('require', ())):
        checks[f'element_{index + 1}'] = any(re.search(p, answer, re.I) for p in group)
    if case.get('forbid'):
        checks['uses_context'] = not any(re.search(p, answer, re.I) for p in case['forbid'])
    if 'days' in case:
        sections = _day_sections(answer, locale, case['days'])
        checks['every_day'] = sections is not None
        checks['day_periods'] = sections is not None and all(
            len(set(m.group(0).casefold() for m in PERIODS[locale].finditer(s))) >= 2 for s in sections)
    if 'steps' in case:
        checks['steps'] = len(LIST_ITEM.findall(answer)) >= case['steps']
    if 'han_terms' in case:
        checks['chinese_names'] = len(set(re.findall(r'[㐀-鿿]{2,}', answer))) >= case['han_terms']
    if 'first_sentence' in case:
        first = SENTENCE_END.split(answer.strip(), maxsplit=1)[0]
        checks['emergency_first'] = any(token in first for token in case['first_sentence'])
    return dict(id=case['id'], units=units, checks=checks, passed=all(checks.values()))


def summarize(cases, answers):
    rows = [check_answer(case, answers[case['id']]) for case in cases if case['id'] in answers]
    total = sum(len(row['checks']) for row in rows)
    hit = sum(sum(row['checks'].values()) for row in rows)
    return dict(version=VERSION, answered=len(rows), cases=len(cases),
                passed_cases=sum(row['passed'] for row in rows),
                check_rate=round(hit / total, 3) if total else None,
                template_free=sum(row['checks'].get('no_template', True) for row in rows),
                rows=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.lio_answer_quality')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('cases')
    score = sub.add_parser('score')
    score.add_argument('answers')
    args = parser.parse_args(argv)
    cases = load_cases()
    if args.command == 'cases':
        for case in cases:
            print(case['id'], case['locale'], ' ⏎ '.join(case['turns']), sep='\t')
        return 0
    answers = strict_json(Path(args.answers).read_bytes())
    if type(answers) is not dict or not all(type(v) is str for v in answers.values()):
        raise SystemExit('answers must map case id to answer text')
    result = summarize(cases, answers)
    for row in result['rows']:
        failed = [name for name, ok in row['checks'].items() if not ok]
        print(('PASS' if row['passed'] else 'FAIL'), row['id'], row['units'], ','.join(failed), sep='\t')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
