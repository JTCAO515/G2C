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

_VISA = re.compile(r'签证|免签|入境(?:政策|要求|条件|规定|材料|手续|需要|要带|要准备|要办)|能不能入境|怎么入境|能入境吗|'
                   r'\bvisas?\b|visa[- ]free|\bentry (?:requirements?|rules?|polic(?:y|ies))\b|'
                   r'\b(?:need|require|allowed|can I|how (?:do|can) I)\b[^.?!]{0,30}\benter China\b|\bto enter China\b', re.I)
# A transit or layover only counts together with an entry or visa word.
_TRANSIT = re.compile(r'过境|转机|中转|\btransit\b|\blayover\b|\bstopover\b', re.I)
_TRANSIT_ENTRY = re.compile(r'签|入境|出机场|出关|\bvisa|\bimmigration\b|\bleave the airport\b|\b24[- ]?hour|\b240\b', re.I)
# A card payment brand is not a visa.
_PAYMENT_VISA = re.compile(r'\bVisa\b\s*(?:card|credit|debit|or Mastercard)|\b(?:pay|paying|paid|accept\w*|use|using|with)\b[^.?!]{0,15}\bVisa\b|'
                           r'\bMastercard\b|\bAmex\b', re.I)
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
    (re.compile(r'我(?:们)?是' + r'([\u4e00-\u9fff]{1,3}籍)'), True),
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
_ZH_NOT_COUNTRY = re.compile(r'中国|个|地|城|本|次|的|游|客|生|人|外|家|们|这|那|一|两|普通|自己|学|老|朋友|有效|过期|新|旧|护照|证件|籍|华|侨|裔|拿|持|用|张|本人|和|双|重|多')
# 美籍华人 is a US national: X籍 takes the one- or two-character country abbreviation.
_ZH_ABBREVIATION = {'美': 'US', '英': 'GB', '加': 'CA', '德': 'DE', '法': 'FR', '意': 'IT', '西': 'ES', '荷': 'NL',
                    '澳': 'AU', '新西兰': 'NZ', '日': 'JP', '韩': 'KR', '新加坡': 'SG', '新': 'SG'}
_EN_WORDS = frozenset(('Chinese', 'China', 'Going', 'Planning', 'Travelling', 'Traveling', 'Visiting', 'Not',
                       'Here', 'Lio', 'Hello', 'Hi', 'Sorry', 'Ok', 'OK', 'Thanks', 'Ready', 'Back', 'New', 'Just',
                       'Also', 'Still', 'Staying', 'Arriving', 'Leaving', 'Flying', 'The', 'My', 'Our'))
_NEGATED = re.compile(r'不是|并非|\bnot\b|\bno longer\b|\bisn[’\x27]t\b|\baren[’\x27]t\b', re.I)
# Somebody else's nationality never stands in for the traveler's own.
_OTHER_PERSON = re.compile(r'朋友|同事|同伴|家人|妻子|老婆|丈夫|老公|太太|先生|孩子|儿子|女儿|父母|爸爸|妈妈|父亲|母亲|他们|她们|他|她|'
                           r'\b(?:my|our) (?:friend|wife|husband|partner|colleague|son|daughter|child|children|kids?|parents?|'
                           r'mother|father|mum|mom|dad|family|boyfriend|girlfriend|companion)s?\b|\b(?:he|she|they|his|her|their)\b', re.I)


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
    if _PAYMENT_VISA.search(text) and not re.search(r'签证|免签|visa[- ]free|\bvisas\b|\btourist visa\b|\bvisa (?:on arrival|application|requirement)', text, re.I):
        return None
    if _VISA.search(text) or (_TRANSIT.search(text) and _TRANSIT_ENTRY.search(text)):
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


def _clause_before(text, start):
    clause_start = max(text.rfind(mark, 0, start) for mark in '，,。.!！?？;；\n')
    return text[clause_start + 1:start]


def _clause_negated(text, start):
    return _NEGATED.search(_clause_before(text, start)) is not None


def _someone_else(text, start, end):
    """The statement is about another person (a friend's or a spouse's passport)."""
    clause_end = min([position for position in (text.find(mark, end) for mark in '，,。.!！?？;；\n') if position >= 0]
                     or [len(text)])
    after = re.split(r'\s(?:and|but|while|whereas)\s|和|而|但', text[end:clause_end], maxsplit=1, flags=re.I)[0]
    return _OTHER_PERSON.search(_clause_before(text, start) + text[start:end] + after) is not None


def _classify(name, names):
    """('rules', code), ('other', name) or None for a captured nationality name."""
    if name in names:
        return 'rules', names[name]
    if name.casefold() in names:
        return 'rules', names[name.casefold()]
    if re.fullmatch(r'[\u4e00-\u9fff]+', name):
        if '籍' in name:
            prefix = name.split('籍')[0]
            return ('rules', _ZH_ABBREVIATION[prefix]) if prefix in _ZH_ABBREVIATION else None
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
                if _clause_negated(text, match.start()) or _someone_else(text, match.start(), match.end()):
                    continue
                value = _classify(match.group(1).strip(), names)
                if value is not None and (other or value[0] == 'rules'):
                    found.append((match.start(), value))
        if found:
            latest = max(found)[1]
    return latest


_REPLY_PREFIX = re.compile(r'^(?:我(?:们)?(?:是|持|持有|用|拿|拿的是)?\s*|(?:I am|I\'m|I’m|I hold|I have|We are|We\'re|We’re|we are|we\'re)\s+(?:an?\s+)?|an?\s+)', re.I)
_REPLY_SUFFIX = re.compile(r'(?:的)?(?:普通)?(?:人|护照|国籍)$|\s+(?:passport|citizen|national)s?$', re.I)


def nationality_reply(text, rules):
    """The nationality when the whole message is only that, such as 美国, 我持美国护照 or "American"."""
    value = re.sub(r'[\s。.!！]+$', '', text.strip())
    value = _REPLY_SUFFIX.sub('', _REPLY_PREFIX.sub('', value)).strip()
    names = _lookup(rules)
    if value in names:
        return 'rules', names[value]
    if value.casefold() in names:
        return 'rules', names[value.casefold()]
    if value.endswith('s') and value[:-1].casefold() in names:
        return 'rules', names[value[:-1].casefold()]
    return None


def entry_turn(question, prior_texts, locale, today, rules=None):
    """entry_reply for this message, or for the previous visa question when this one only gives a nationality."""
    if entry_question(question) is not None:
        return entry_reply(question, prior_texts, locale, today, rules)
    rules = load_rules() if rules is None else rules
    if not prior_texts or entry_question(prior_texts[-1]) != 'visa' or nationality_reply(question, rules) is None:
        return None
    nationality = nationality_reply(question, rules)
    statement = ('我是' + next(row['name']['zh'] for row in rules['countries'] if row['code'] == nationality[1]) + '人'
                 if nationality[0] == 'rules' else question)
    return entry_reply(prior_texts[-1], (*prior_texts[:-1], statement), locale, today, rules)


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
    article = 'the ' if locale == 'en' and name in ('United States', 'United Kingdom', 'Netherlands') else ''
    parts = [(f'持{name}普通护照：' if locale == 'zh' else f'With an ordinary passport issued by {article}{name}:')]
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
