"""Offline answer-quality checks for default Lio dialogue (#1472 / #1473).

Scores model-written answer text for concrete content (places, times, prices,
steps), day-by-day structure and template phrases. It never calls a model,
dispatches a message or grants a save; answers come from a JSON file that maps
case id to the visible answer text.

Profiles:
  detail      (default, checks.1) the #1472 detail checks: minimum length, morning/afternoon per day.
  one-screen  (checks.3) the one-screen structure JT chose on 2026-11-25 (strategy/lio-answer-design.md):
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
from datetime import date
from functools import lru_cache
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
PROFILES = {DETAIL: VERSION, ONE_SCREEN: 'LIO-answer-quality-checks.3'}
# Body budget per answer type (zh characters, en words), from the design table; None = unlimited.
BUDGETS = {'greeting': (40, 25), 'task': (150, 90), 'nearby': (130, 80), 'compare': (180, 110),
           'plan': (200, 120), 'edit': (100, 60), 'emergency': None}
SCENARIO_KIND = {'planning': 'plan', 'practical': 'task', 'chat': 'task', 'recommendation': 'compare',
                 'greeting': 'greeting', 'followup': 'edit', 'emergency': 'emergency'}
MAX_ACTIONS, MAX_CHIPS = 2, 3  # S contract: at most 3 chips per answer (2026-11-25)
# Cases whose question has a button in the first whitelist (S contract, A confirmed 2026-11-25):
# open_guide payment-setup / payment-troubleshooting / taxi. view_trip needs a saved trip, and
# default-dialogue plans are unsaved suggestions, so no planning case qualifies. Every other
# answer has no valid first-version button and ends with 2-3 tappable follow-ups
# (docs/lio-voice.md §4.2, §9.1).
V1_ACTION_CASES = frozenset({'alipay-zh', 'visa-card-en', 'taxi-foreigner-zh', 'uber-taxi-en'})
# Two bubbles (JT 2026-11-25, docs/lio-voice.md §3.2): layout=split answers put only the answer
# (or, in an emergency, the action) in the first paragraph, then a blank line.
SPLIT_KINDS = frozenset({'task', 'nearby', 'compare', 'emergency'})
FIRST_PARAGRAPH_UNITS = (35, 20)
BLANK_LINE = re.compile(r'\n[ \t\u3000]*\n')
# Entry facts come from the landing-mode rules (single source, coordination 2026-11-25).
ARRIVAL_RULES = ROOT.parent / 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioArrivalRules.v1.json'
ENTRY_CASES = {'transit-visa-zh': 'US', 'visa-uk-en': 'GB'}


@lru_cache(maxsize=1)
def entry_facts():
    """Entry facts from the landing-mode rules (single source, coordination 2026-11-25).

    Read lazily, only for entry cases in the one-screen profile; the Chinese and English
    summaries must agree, otherwise the data changed shape and scoring stops loudly.
    """
    try:
        rules = json.loads(ARRIVAL_RULES.read_text())
        policies = {policy['id']: policy for policy in rules['policies']}
        transit = policies['transit-240h']
        zh, en = transit['summary']['zh'], transit['summary']['en']
        ports = {int(re.search(r'(\d+)\s*个开放口岸', zh)[1]), int(re.search(r'(\d+) open ports', en)[1])}
        provinces = {int(re.search(r'(\d+)\s*个省份', zh)[1]), int(re.search(r'in (\d+) provinces', en)[1])}
        countries = {int(re.search(r'(\d+)\s*国', source['publisher']['zh'])[1]) for source in transit['sources']
                     if re.search(r'(\d+)\s*国', source['publisher']['zh'])}
        if len(ports) != 1 or len(provinces) != 1 or len(countries) != 1:
            raise ValueError('summaries disagree')
        visa_free, until = {}, {}
        for country in rules['countries']:
            granted = [policies[key] for key in country['policies'] if policies[key]['kind'] == 'visa_free']
            if granted:
                best = max(granted, key=lambda policy: policy['max_stay_days'])
                visa_free[country['code']] = best['max_stay_days']
                until[country['code']] = date.fromisoformat(best['valid_until']) if best['valid_until'] else date.max
        return dict(ports=ports.pop(), provinces=provinces.pop(), countries=countries.pop(),
                    transit_hours=24 * transit['max_stay_days'], transit_days=transit['max_stay_days'],
                    visa_free_days=visa_free, visa_free_until=until,
                    data_version=rules['data_version'], checked_at=rules['checked_at'])
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise ValueError('landing-mode rules unavailable or changed shape: ' + str(ARRIVAL_RULES.name)) from error


SENTENCE = re.compile(r'(?<=[。！？!?；;\n])|(?<=\.)\s+')
# Precision first: only clear slips fail; a correct sentence must never fail. Each claim
# needs its object (the entry city, the origin country), and a negation right before it or
# a correction in the same sentence (a myth marker first, or the correct rule stated) clears it.
CITY_LIMIT = re.compile(
    r'不得跨[市省]|(?<!能)不能跨[市省]|不可跨[市省]|只(?:能|可)(?:待|留|停留)?在?(?:入境|落地|所在)的?城市|仅限(?:入境|落地)城市|'
    r'(?:不能|不可|不得)离开(?:入境|落地)的?城市|'
    r"(?:cannot|can't|may not|not allowed to)\s+travel (?:to|across) (?:other |different )?provinces|"
    r'(?:must|have to|can only|cannot|can\'t|may not|not allowed to)\s+(?:stay|remain|leave|be)\b[^.]{0,25}?\b(?:arrival|entry|landing) city|'
    r'(?:must|have to)\s+stay in the (?:same )?city (?:where )?you (?:land|arrive|enter)|limited to the city|'
    r'only stay in (?:your|the) (?:arrival|entry|landing) city', re.I)
RETURN_HOME = re.compile(r'原路返回|飞回出发国|返回出发国|fly back to (?:the (?:US|UK)|your (?:home|origin) country)|return to your (?:home|origin) country', re.I)
NEAR_NEGATION = re.compile(r"(?:n't|\bnot\b|\bno\b|never|no longer|不能是?|不可|不得|不用|无需|并不是|不是)\s*$", re.I)
CORRECTION = re.compile(r'有人说|有人以为|很多人以为|误以为|误传|误解|并不是|不是只能|myth|misconception|common mistake|'
                        r'contrary to|not true|some people say', re.I)
CORRECT_RULE = re.compile(r'可以?跨省|可跨省|跨省活动|across provinces|travel across|第三国|third country', re.I)
OLD_TRANSIT = re.compile(r'(?<!\d)(?:72|144)\s*(?:个)?(?:小时|-?hours?\b)', re.I)
TRANSIT = re.compile(r'过境|transit', re.I)
NEEDS_VISA = re.compile(
    r"\b(?:need|needs|needed)\s+(?:to\s+(?:get|apply for|obtain)\s+)?(?:a|an)\s+(?:[a-z]+\s+)?visa\b|"
    r"\bmust\s+(?:get|apply for|obtain)\s+(?:a|an)\s+(?:[a-z]+\s+)?visa\b|\brequires?\s+(?:a|an)\s+visa\b|"
    r'(?:需要|仍需|须|必须)(?:办|申请|办理)?签证', re.I)
VISA_CONDITION = re.compile(r'\bonly if\b|\bif you\b|\bif\b|otherwise|whether|unless|\bwork|stud(?:y|ies)|journalis|\bover\b|'
                            r'\bafter \d+|more than|longer than|or more|beyond|exceed|超过|以上|才|否则|工作|学习|留学|采访', re.I)
CONTRAST = re.compile(r'\bbut\b|\bhowever\b|但是?|不过|然而|[;；]', re.I)
VISA_FREE_CAP = re.compile(r'(\d+)\s*天免签|免签(?:停留|入境)?(?:最多|最长|不超过|可达)?\s*(\d+)\s*天|(\d+)-day visa-free|'
                           r'visa-free (?:entry |stays? )?(?:for )?(?:up to|of up to|at most|a maximum of) (\d+) days|'
                           r'up to (\d+) days without a visa', re.I)


def today():
    return date.today()


def _cleared(sentence, match):
    """A claim is cleared by a negation right before it or a correction in the same sentence."""
    before = sentence[:match.start()]
    if NEAR_NEGATION.search(before[-12:]):
        return True
    marker = CORRECTION.search(sentence)
    return bool(marker and marker.start() < match.start()) or bool(CORRECT_RULE.search(sentence))


def _entry_facts_hold(text, country):
    facts = entry_facts()
    days = facts['visa_free_days'].get(country)
    if days is not None and today() > facts['visa_free_until'][country]:
        days = None  # the rules file has not been renewed: do not enforce an expired policy
    for sentence in (re.sub(r'[*_`]', '', part).strip() for part in SENTENCE.split(text) if part and part.strip()):
        for pattern in (CITY_LIMIT, RETURN_HOME):
            for match in pattern.finditer(sentence):
                if not _cleared(sentence, match):
                    return False
        if OLD_TRANSIT.search(sentence) and '240' not in sentence:
            return False
        if TRANSIT.search(sentence):
            for regex, key in ((r'(\d+)\s*个?(?:开放)?口岸|(\d+)\s*(?:open |border |entry )?ports\b', 'ports'),
                               (r'(\d+)\s*个?国家|(\d+)\s*国(?![内际])|(\d+)\s*countries', 'countries'),
                               (r'(\d+)\s*(?:天|-?days?\b)', 'transit_days')):
                for match in re.finditer(regex, sentence, re.I):
                    if int(next(group for group in match.groups() if group)) != facts[key]:
                        return False
        if days is not None and not sentence.rstrip().endswith(('?', '？')):
            for match in NEEDS_VISA.finditer(sentence):
                # A condition only clears the claim inside its own clause ("not if X, but Y needs a visa").
                clause = CONTRAST.split(sentence[:match.start()])[-1] + sentence[match.start():]
                clause = CONTRAST.split(clause)[0] if CONTRAST.search(sentence[match.end():]) else clause
                if not VISA_CONDITION.search(clause) and not NEAR_NEGATION.search(sentence[:match.start()][-12:]):
                    return False
            if not TRANSIT.search(sentence):
                for match in VISA_FREE_CAP.finditer(sentence):
                    if int(next(group for group in match.groups() if group)) != days:
                        return False
    return True


# Openings that are not an answer: greetings, self-introductions and praise anywhere at the start;
# assent words ("当然可以", "Sure") only when they stand alone as the whole first sentence.
_END = r'(?![\w-])'
PREFACE = re.compile(r'\s*(?:你好(?!像)|您好|嗨(?!皮)|hey' + _END + r'|hi' + _END + r'|hello' + _END + r'|'
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
                                    and (bool(actions) if case['id'] in V1_ACTION_CASES
                                         else not actions and len(chips) >= 2))
        if kind in SPLIT_KINDS:
            parts = BLANK_LINE.split(answer.strip(), maxsplit=1)
            head = parts[0].strip()
            checks['first_paragraph'] = (len(parts) == 2 and bool(head) and '\n' not in head
                                         and count_units(head, locale) <= FIRST_PARAGRAPH_UNITS[LOCALES.index(locale)])
        if case['id'] in ENTRY_CASES:
            checks['entry_facts'] = _entry_facts_hold(answer, ENTRY_CASES[case['id']])
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
                           for name in ('screen_budget', 'first_answer', 'has_action', 'first_paragraph', 'entry_facts')}
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
        cause = f' ({error.__cause__})' if error.__cause__ else ''
        raise SystemExit(str(error) + cause)
    for row in result['rows']:
        failed = [name for name, ok in row['checks'].items() if not ok]
        print(('PASS' if row['passed'] else 'FAIL'), row['id'], row['units'], ','.join(failed), sep='\t')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
