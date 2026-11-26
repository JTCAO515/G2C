"""Entry questions answered from the App's own arrival rules (W2-4, #1731).

With CJ_LIO_ENTRY_RULES=1, a visa, visa-free, transit or arrival-card question is
answered by code from backend/fact/cj_fact/arrival_rules.v1.json, the server copy
of the file the App bundles (#1730), instead of the model or the fixed transit
sentence. The answer quotes the rule summaries word for word, names their
official sources and the check date, and never states personal eligibility.

Nationality comes only from what the traveler wrote in this conversation (the
current message or an earlier one). Nothing stored on the device or in Memory
is used: that would be new outbound personal data and is not part of this
ticket. Without a stated nationality, Lio asks for it once. After the file's
review date, Lio draws no conclusion and points to the official channels, the
same way the App does. A question that also asks for a plan is left to the
planning path (multi-task handling is W2-8).
"""
from dataclasses import dataclass
from datetime import date
import os
import re

from cj_fact.arrival import load_rules, review_due

_VISA = re.compile(r'签证|免签|过境|入境(?:政策|要求|条件|规定|材料|手续)|能不能入境|怎么入境|'
                   r'\bvisas?\b|visa[- ]free|\btransit\b|\blayover\b|\bentry (?:requirements?|rules?|polic(?:y|ies))\b|'
                   r'\benter(?:ing)? China\b', re.I)
_CARD = re.compile(r'入境卡|入境登记卡|\barrival card\b|\bentry card\b|\blanding card\b', re.I)
_PLAN = re.compile(r'规划|行程|攻略|玩\s*[0-9一二三四五六七八九十两]+\s*天|[0-9一二三四五六七八九十两]+\s*天|'
                   r'\bitinerar\w*|\bplan\b|\b\d+\s*days?\b', re.I)
_NEGATED = re.compile(r'不是|并非|\bnot\b|\bno longer\b', re.I)

# Demonyms and extra names for the countries in the rules file; the main names come from the file.
_DEMONYMS = {'US': ('American',), 'GB': ('British',), 'CA': ('Canadian',), 'DE': ('German',), 'FR': ('French',),
             'IT': ('Italian',), 'ES': ('Spanish',), 'NL': ('Dutch',), 'AU': ('Australian',),
             'NZ': ('New Zealander', 'New Zealand'), 'JP': ('Japanese',), 'KR': ('Korean', 'South Korean'),
             'SG': ('Singaporean',)}
_EXTRA_NAMES = {'US': ('USA', 'US', 'U.S.', 'America', 'United States of America'),
                'GB': ('UK', 'U.K.', 'Britain', 'Great Britain', 'England'),
                'KR': ('Korea', 'Republic of Korea'), 'NL': ('Holland',)}
_ZH_EXTRA = {'US': ('美利坚',), 'KR': ('南韩',)}
# Only an explicit nationality statement counts; "Japanese food" or "from the airport" do not.
_NAME_ZH = r'([\u4e00-\u9fff]{2,6}?)'
_NAME_EN = r"([A-Z][A-Za-z.]+(?: [A-Z][A-Za-z.]+){0,3})"
_ZH_TAIL = r'(?=[，,。.!！?？；;\s的]|$)'
# (pattern, accepts a country that is not in the rules file)
_STATEMENTS = (
    (re.compile(r'我(?:们)?是' + _NAME_ZH + r'人'), True),
    (re.compile(r'持(?:有)?' + _NAME_ZH + r'(?:的)?(?:普通)?护照'), True),
    (re.compile(_NAME_ZH + r'(?:的)?(?:普通)?护照'), True),
    (re.compile(_NAME_ZH + r'国籍'), True),
    (re.compile(r'国籍(?:是|为|[:：])\s*([\u4e00-\u9fff]{2,6})' + _ZH_TAIL), True),
    (re.compile(r'我(?:们)?来自([\u4e00-\u9fff]{2,6})' + _ZH_TAIL), True),
    # "I'm Tom" is not a nationality: a bare "I am X" only counts for a known demonym or name.
    (re.compile(r"\b(?:I am|I'm|I’m|[Ww]e are|[Ww]e're|[Ww]e’re)\s+(?:an?\s+)?" + _NAME_EN + r'(?=$|[\s,.;!?])'), False),
    (re.compile(r'\b' + _NAME_EN + r'\s+(?:passport|citizen|national)s?\b'), True),
    (re.compile(r"\b(?:I am|I'm|I’m|[Ww]e are|[Ww]e're|[Ww]e’re|I come|[Ww]e come)\s+from\s+(?:the\s+)?" + _NAME_EN + r'(?=$|[\s,.;!?])'), True),
    (re.compile(r'\bcitizens? of\s+(?:the\s+)?' + _NAME_EN + r'(?=$|[\s,.;!?])'), True),
    (re.compile(r'\bpassport is\s+(?:an?\s+)?' + _NAME_EN + r'(?=$|[\s,.;!?])'), True),
)
_PLACE_WORDS = frozenset(('Airport', 'Station', 'Hotel', 'Street', 'Road', 'District', 'City', 'Province', 'Hostel',
                          'Terminal', 'Beijing', 'Shanghai', 'Chengdu', 'Guangzhou', 'Shenzhen', 'Hangzhou', "Xi'an",
                          'Hong', 'Kong', 'Macau', 'Taiwan', 'Pudong', 'Hongqiao', 'Daxing', 'Capital'))
_ZH_NOT_COUNTRY = re.compile(r'中国|个|地|城|本|次|的|游|客|生|人|外|家|们|这|那|一|两|普通|自己|学|老|朋友')
_EN_WORDS = frozenset(('Chinese', 'China', 'Going', 'Planning', 'Travelling', 'Traveling', 'Visiting', 'Not',
                       'Here', 'Lio', 'Hello', 'Hi', 'Sorry', 'Ok', 'OK', 'Thanks', 'Ready', 'Back', 'New', 'Just',
                       'Also', 'Still', 'Staying', 'Arriving', 'Leaving', 'Flying', 'The', 'My', 'Our'))
_NEGATED = re.compile(r'不是|并非|\bnot\b|\bno longer\b|\bisn[’\x27]t\b|\baren[’\x27]t\b', re.I)


def entry_rules_enabled():
    """Server switch; off unless explicitly set to 1."""
    value = os.environ.get('CJ_LIO_ENTRY_RULES', '0')
    if value not in ('0', '1'):
        raise ValueError('explicit entry rules switch value required')
    return value == '1'


@dataclass(frozen=True)
class EntryReply:
    text: str
    citations: tuple  # (key, title, url)


def entry_question(text):
    """'card', 'visa' or None. A plan request goes to the planning path."""
    if _PLAN.search(text):
        return None
    if _CARD.search(text):
        return 'card'
    if _VISA.search(text):
        return 'visa'
    return None


def _lookup(rules):
    names = {}
    for country in rules['countries']:
        code = country['code']
        for name in (country['name']['zh'], *_ZH_EXTRA.get(code, ())):
            names[name] = code
        for name in (country['name']['en'], *_EXTRA_NAMES.get(code, ()), *_DEMONYMS.get(code, ())):
            names[name.casefold()] = code
    return names


def _clause_negated(text, start):
    clause_start = max(text.rfind(mark, 0, start) for mark in '，,。.!！?？;；\n')
    return _NEGATED.search(text[clause_start + 1:start]) is not None


def _classify(name, names):
    """('rules', code), ('other', name) or None for a captured nationality name."""
    if name in names:
        return 'rules', names[name]
    if name.casefold() in names:
        return 'rules', names[name.casefold()]
    if re.fullmatch(r'[\u4e00-\u9fff]+', name):
        for known, code in sorted(names.items(), key=lambda row: -len(row[0])):
            if len(known) >= 2 and re.fullmatch(r'[\u4e00-\u9fff]+', known) and (name.startswith(known) or name.endswith(known)):
                return 'rules', code
        return None if _ZH_NOT_COUNTRY.search(name) else ('other', name)
    name = name.rstrip('.')
    words = name.split()
    if any(word in _EN_WORDS or word in _PLACE_WORDS for word in words):
        return None
    if len(words) == 1 and words[0].endswith('s') and words[0][:-1].casefold() in names:
        return 'rules', names[words[0][:-1].casefold()]
    for size in range(len(words), 0, -1):
        prefix = ' '.join(words[:size])
        if prefix.casefold() in names:
            return 'rules', names[prefix.casefold()]
    return 'other', name


def stated_nationality(texts, rules):
    """The last nationality the traveler stated: ('rules', code), ('other', name) or None."""
    latest = None
    names = _lookup(rules)
    for text in texts:
        found = []
        for pattern, other in _STATEMENTS:
            for match in pattern.finditer(text):
                if _clause_negated(text, match.start()):
                    continue
                value = _classify(match.group(1).strip(), names)
                if value is not None and (other or value[0] == 'rules'):
                    found.append((match.start(), value))
        if found:
            latest = max(found)[1]
    return latest


def _active(policy, today):
    start = policy['valid_from']
    end = policy['valid_until']
    return (start is None or date.fromisoformat(start) <= today) and (end is None or today <= date.fromisoformat(end))


def _sources(rows, locale, prefix):
    return tuple((f'{prefix}:{index}', row['publisher'][locale], row['url']) for index, row in enumerate(rows))


def _official(rules, locale, lead):
    names = '、'.join(row['publisher']['zh'] for row in rules['official_fallback']) if locale == 'zh' else \
        ', '.join(row['publisher']['en'] for row in rules['official_fallback'])
    text = lead + ('请以官方为准：' + names + '。' if locale == 'zh' else ' Please check the official sources: ' + names + '.')
    return EntryReply(text, _sources(rules['official_fallback'], locale, 'entry-official'))


def entry_reply(question, prior_texts, locale, today, rules=None):
    """The code answer for an entry question, or None when it is not one."""
    kind = entry_question(question)
    if kind is None:
        return None
    rules = load_rules() if rules is None else rules
    if today >= review_due(rules):
        lead = ('入境政策可能已经更新，我这里的资料过了复核期，先不下结论。' if locale == 'zh'
                else 'Entry rules may have changed and my copy is past its review date, so I will not draw a conclusion.')
        return _official(rules, locale, lead)
    if kind == 'card':
        card = rules['arrival_card']
        tail = (f'（核对日 {card["checked_at"]}，以官方为准）' if locale == 'zh'
                else f' (checked {card["checked_at"]}; the official channel decides.)')
        return EntryReply(card['summary'][locale] + tail, _sources(card['sources'], locale, 'entry-card'))
    nationality = stated_nationality((*prior_texts, question), rules)
    if nationality is None:
        return EntryReply('入境免签和过境政策按护照国家不同。你持哪国护照？' if locale == 'zh' else
                          'Visa-free entry and transit rules depend on your passport. Which country issued your passport?', ())
    source, value = nationality
    if source == 'other':
        lead = (f'我这里没有{value}护照的入境规则。' if locale == 'zh'
                else f'I do not have entry rules for a {value} passport.')
        return _official(rules, locale, lead)
    country = next(row for row in rules['countries'] if row['code'] == value)
    policies = {row['id']: row for row in rules['policies']}
    active = [policies[key] for key in country['policies'] if key in policies and _active(policies[key], today)]
    transit_first = re.search(r'过境|转机|\btransit\b|\blayover\b', question, re.I) is not None
    active.sort(key=lambda row: (row['kind'] != 'transit') if transit_first else (row['kind'] == 'transit'))
    name = country['name'][locale]
    parts = [(f'持{name}普通护照：' if locale == 'zh' else f'With an ordinary {name} passport:')]
    citations = []
    for policy in active:
        parts.append(policy['summary'][locale] + ('' if locale == 'zh' else ' ') + policy['not_covered'][locale])
        citations += _sources(policy['sources'], locale, 'entry-' + policy['id'])
    if not active or country['otherwise'] == 'check_official':
        parts.append('其他情况请以官方为准。' if locale == 'zh' else 'For anything else, check the official sources.')
        citations += _sources(rules['official_fallback'], locale, 'entry-official')
    elif country['otherwise'] == 'visa_required':
        parts.append('不符合以上条件的，需要在出发前办好签证。' if locale == 'zh'
                     else 'If none of these apply, get a visa before you travel.')
    parts.append(f'（核对日 {country["checked_at"]}，个人是否适用以官方为准）' if locale == 'zh'
                 else f'(Checked {country["checked_at"]}; whether it applies to you is decided by the official sources.)')
    return EntryReply('\n\n'.join(parts), tuple(citations))
