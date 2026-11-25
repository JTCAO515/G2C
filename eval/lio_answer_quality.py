"""Offline answer-quality checks for default Lio dialogue (#1472 / #1473).

Scores model-written answer text for concrete content (places, times, prices,
steps), day-by-day structure and template phrases. It never calls a model,
dispatches a message or grants a save; answers come from a JSON file that maps
case id to the visible answer text.

Profiles:
  detail      (default, checks.1) the #1472 detail checks: minimum length, morning/afternoon per day.
  one-screen  (checks.2) the one-screen structure JT chose on 2026-11-25 (strategy/lio-answer-design.md):
              body within the per-type screen budget, the first sentence answers, one or two actions
              (or tappable follow-ups for "where to go"), and required elements counted only inside
              the budget, so a longer answer no longer earns more hits.

Usage:
  python -m eval.lio_answer_quality cases                                  # list questions
  python -m eval.lio_answer_quality score answers.json                     # detail profile, text answers
  python -m eval.lio_answer_quality score --profile one-screen answers.json
    # answers map case id to text, or to {"text": ..., "actions": [...], "chips": [...]}
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
DETAIL = 'detail'
ONE_SCREEN = 'one-screen'
PROFILES = {DETAIL: VERSION, ONE_SCREEN: 'LIO-answer-quality-checks.2'}
# Body budget per answer type (zh characters, en words), from the design table; None = unlimited.
BUDGETS = {'greeting': (40, 25), 'task': (150, 90), 'nearby': (130, 80), 'compare': (180, 110),
           'plan': (200, 120), 'edit': (100, 60), 'emergency': None}
SCENARIO_KIND = {'planning': 'plan', 'practical': 'task', 'chat': 'task', 'recommendation': 'compare',
                 'greeting': 'greeting', 'followup': 'edit', 'emergency': 'emergency'}
MAX_ACTIONS, MAX_CHIPS = 2, 3  # S contract: at most 3 chips per answer (2026-11-25)
# Openings that are not an answer: greetings, self-introductions and praise anywhere at the start;
# assent words ("当然可以", "Sure") only when they stand alone as the whole first sentence.
_END = r'(?![\w-])'
PREFACE = re.compile(r'\s*(?:(?:你好|您好|嗨)(?!像)|hey' + _END + r'|hi' + _END + r'(?!\s+[A-Z])|hello' + _END + r'(?!\s+[A-Z])|'
                     r'我是\s*Lio|I[\'’]m Lio|好问题|这是个好问题|问得好|great question|good question|happy to help|glad you asked)', re.I)
ASSENT = re.compile(r'\s*(?:当然可以|当然|没问题|好的|sure|of course|absolutely|certainly)\W*', re.I)
FIRST_SENTENCE = re.compile(r'\s*(.*?)([。！？!?\n]|\.(?=\s|$)|$)', re.S)
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


def _within_budget(text, locale, budget):
    """The longest prefix of text whose unit count fits the budget."""
    if budget is None or count_units(text, locale) <= budget:
        return text
    # English counts are not monotonic over prefixes (a pinyin annotation stops counting only once
    # its bracket closes), so check every word end instead of bisecting; Chinese counts characters.
    ends = range(1, len(text) + 1) if locale == 'zh' else [m.end() for m in re.finditer(r'\S+', text)]
    return text[:max((end for end in ends if count_units(text[:end], locale) <= budget), default=0)]


def _structured(answer, profile):
    if type(answer) is str:
        return answer, [], []
    if profile != ONE_SCREEN or type(answer) is not dict or set(answer) - {'text', 'actions', 'chips'}:
        raise ValueError('answers must be text, or text with actions and chips in the one-screen profile')
    actions, chips = answer.get('actions', []), answer.get('chips', [])
    if type(answer.get('text')) is not str or not all(type(v) is list and all(type(i) is str for i in v) for v in (actions, chips)):
        raise ValueError('structured answer needs text and string lists')
    return answer['text'], actions, chips


def check_answer(case, answer, profile=DETAIL):
    """Deterministic surface checks. Factual accuracy still needs human or judge review."""
    if profile not in PROFILES:
        raise ValueError('unknown profile ' + str(profile))
    text, actions, chips = _structured(answer, profile)
    if not text.strip():
        raise ValueError('missing model answer for ' + case['id'])
    answer = text
    locale = case['locale']
    units = count_units(answer, locale)
    one_screen = profile == ONE_SCREEN
    kind = SCENARIO_KIND[case['scenario']]
    budget = BUDGETS[kind] and BUDGETS[kind][LOCALES.index(locale)]
    scope = _within_budget(answer, locale, budget) if one_screen else answer
    checks = {}
    checks['red_line'] = not (INTERNAL.search(answer) or COORDINATES.search(answer) or TEST_LEAK.search(answer))
    if case['scenario'] != 'greeting':
        checks['no_template'] = TEMPLATE_PHRASES.search(answer) is None
    if one_screen:
        checks['screen_budget'] = budget is None or units <= budget
        if case['scenario'] != 'greeting':
            first = FIRST_SENTENCE.match(answer)
            checks['first_answer'] = (bool(first.group(1).strip()) and first.group(2) not in ('?', '？')
                                      and PREFACE.match(first.group(1)) is None
                                      and ASSENT.fullmatch(first.group(1)) is None)
            visible = [a for a in actions if a.strip()]
            shown = [c for c in chips if c.strip()]
            checks['has_action'] = (len(visible) == len(actions) and len(shown) == len(chips)
                                    and len(actions) <= MAX_ACTIONS and len(chips) <= MAX_CHIPS
                                    and (bool(actions) or kind == 'compare' and len(chips) >= 2))
    else:
        if 'min_units' in case:
            checks['detail_length'] = units >= case['min_units']
        if 'max_units' in case:
            checks['brief'] = units <= case['max_units']
    for index, group in enumerate(case.get('require', ())):
        checks[f'element_{index + 1}'] = any(re.search(p, scope, re.I) for p in group)
    if case.get('forbid'):
        checks['uses_context'] = not any(re.search(p, answer, re.I) for p in case['forbid'])
    if 'days' in case:
        sections = _day_sections(scope, locale, case['days'])
        checks['every_day'] = sections is not None
        if not one_screen:
            checks['day_periods'] = sections is not None and all(
                len(set(m.group(0).casefold() for m in PERIODS[locale].finditer(s))) >= 2 for s in sections)
    if 'steps' in case:
        checks['steps'] = len(LIST_ITEM.findall(scope)) >= case['steps']
    if 'han_terms' in case:
        checks['chinese_names'] = len(set(re.findall(r'[㐀-鿿]{2,}', scope))) >= case['han_terms']
    if 'first_sentence' in case:
        first = SENTENCE_END.split(answer.strip(), maxsplit=1)[0]
        checks['emergency_first'] = any(token in first for token in case['first_sentence'])
    row = dict(id=case['id'], units=units, checks=checks, passed=all(checks.values()))
    if one_screen:
        row.update(kind=kind, budget_units=budget)
    return row


def summarize(cases, answers, profile=DETAIL):
    rows = [check_answer(case, answers[case['id']], profile) for case in cases if case['id'] in answers]
    total = sum(len(row['checks']) for row in rows)
    hit = sum(sum(row['checks'].values()) for row in rows)
    result = dict(version=PROFILES[profile], answered=len(rows), cases=len(cases),
                  passed_cases=sum(row['passed'] for row in rows),
                  check_rate=round(hit / total, 3) if total else None,
                  template_free=sum(row['checks'].get('no_template', True) for row in rows),
                  rows=rows)
    if profile == ONE_SCREEN:
        def rate(names):
            values = [ok for row in rows for name, ok in row['checks'].items() if names(name)]
            return round(sum(values) / len(values), 3) if values else None
        result['rates'] = {name: rate(lambda n, name=name: n == name)
                           for name in ('screen_budget', 'first_answer', 'has_action')}
        result['rates']['elements_in_budget'] = rate(lambda n: n.startswith('element_'))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m eval.lio_answer_quality')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('cases')
    score = sub.add_parser('score')
    score.add_argument('--profile', choices=sorted(PROFILES), default=DETAIL)
    score.add_argument('answers')
    args = parser.parse_args(argv)
    cases = load_cases()
    if args.command == 'cases':
        for case in cases:
            print(case['id'], case['locale'], ' ⏎ '.join(case['turns']), sep='\t')
        return 0
    answers = strict_json(Path(args.answers).read_bytes())
    if type(answers) is not dict or not all(
            type(v) is str or args.profile == ONE_SCREEN and type(v) is dict for v in answers.values()):
        raise SystemExit('answers must map case id to answer text')
    try:
        result = summarize(cases, answers, args.profile)
    except ValueError as error:
        raise SystemExit(str(error))
    for row in result['rows']:
        failed = [name for name, ok in row['checks'].items() if not ok]
        print(('PASS' if row['passed'] else 'FAIL'), row['id'], row['units'], ','.join(failed), sep='\t')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
