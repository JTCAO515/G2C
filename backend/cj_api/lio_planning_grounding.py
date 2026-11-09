"""Derive authoritative itinerary inputs from explicit, bounded declarations."""
from datetime import date, timedelta
from hashlib import sha256
import re


NUMBERS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten'),
                   range(1, 11), strict=True))
NUMBERS.update(zip('一二三四五六七八九十', range(1, 11), strict=True))
NUMBERS['两'] = 2
NUMBER = r'[0-9]{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十]'
ISO = r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)'
SPAN = re.compile(rf'({ISO})\s*(?:to\b|through\b|到|至|–|—)\s*({ISO})', re.I)
DURATION = re.compile(rf'({NUMBER})\s*(?:-?\s*days?\b|天)', re.I)
START = re.compile(r'\b(?:starting|beginning|from)\s+(tomorrow|today)\b|从?(明天|今天|后天)(?:开始|起)', re.I)
PARTY = re.compile(rf'\bfor\s+({NUMBER})\s+(?:people|persons?)\b|({NUMBER})\s*(?:个人|人)', re.I)
DESTINATION = re.compile(r'\b(?:in|to|visit)\s+Beijing\b|\bBeijing\s+(?:itinerary|trip|visit)\b|'
                         r'(?:去|到|在)北京|北京(?:\s*[，,：:]|[一二两三四五六七八九十\d]+天|游|行程)', re.I)
OTHER_DESTINATION = re.compile(r'\bfrom\s+Beijing\s+to\b|从北京(?:去|到)', re.I)
FIXED = re.compile(r'已经定好|固定安排|已锁定|已预订|已订|不可更改|不能改|'
                   r'\b(?:is fixed|already set|already booked|booked|must keep|cannot be changed)\b', re.I)
NEGATED = re.compile(r"\b(?:not|never|cancel|without)\b|n['’]t\b|还没|没有|未订|不再|不要|取消", re.I)
OTHER = re.compile(r'孩子|女儿|儿子|母亲|父亲|同伴|家人|\b(?:daughter|son|mother|father|friend|guest)\b', re.I)
CLOCK = r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?'
RANGE = re.compile(rf'{CLOCK}\s*(?:[-–—到至]|\bto\b)\s*{CLOCK}', re.I)
CLAUSE_BREAK = re.compile(r'[!?。；;\n]+|\.(?=\s+[A-Z])')


def _clauses(text):
    return tuple(clause.strip().rstrip('.') for clause in CLAUSE_BREAK.split(text) if clause.strip())


def _number(value):
    return int(value) if value.isascii() and value.isdigit() else NUMBERS[value.lower()]


def _known(value):
    return dict(state='known', value=value) if value is not None else dict(state='missing')


def stated_city(text, city):
    if city.casefold() not in ('beijing', '北京'):
        return any(city in clause and not NEGATED.search(clause) for clause in _clauses(text))
    return any(city in clause and DESTINATION.search(clause)
               and not (NEGATED.search(clause) or OTHER_DESTINATION.search(clause))
               for clause in _clauses(text))


def _day_span(clauses, today):
    spans = set()
    for clause in clauses:
        if NEGATED.search(clause) or FIXED.search(clause):
            continue
        try:
            explicit = tuple(SPAN.finditer(clause))
            for match in explicit:
                spans.add((date.fromisoformat(match[1]), date.fromisoformat(match[2])))
            if explicit:
                continue
            start, duration = START.search(clause), DURATION.search(clause)
            if start and duration:
                word = (start[1] or start[2]).lower()
                offset = {'tomorrow':1,'明天':1,'后天':2,'today':0,'今天':0}[word]
                first = today + timedelta(days=offset)
                spans.add((first, first + timedelta(days=_number(duration[1])-1)))
        except ValueError:
            return None, None
    if len(spans) == 1:
        first, last = spans.pop()
        if first <= last:
            return first, last
    return None, None


def _clock(hour, minute, meridiem):
    h, m = int(hour), int(minute or '0')
    if meridiem is not None:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if meridiem[0].lower() == 'p' else 0)
    if not 0 <= h < 24 or not 0 <= m < 60:
        return None
    return f'{h:02d}:{m:02d}'


def _event(day, *, time=None, zone=None, place=None):
    return dict(date=_known(day.isoformat() if day else None), time=_known(time),
                timezone=_known(zone), place=_known(place))


def _fixed_item(clause, first, zone, party):
    if NEGATED.search(clause) or OTHER.search(clause) or zone is None:
        return None
    clocks = RANGE.search(clause)
    if re.search(r'第一天|\b(?:the )?first day\b', clause, re.I):
        day = first
    else:
        dates = re.findall(ISO, clause)
        try:
            day = date.fromisoformat(dates[0]) if len(dates) == 1 else None
        except ValueError:
            return None
    if clocks is None or day is None:
        return None
    start_h, start_m, start_meridiem, end_h, end_m, end_meridiem = clocks.groups()
    start = _clock(start_h, start_m, start_meridiem or end_meridiem)
    end = _clock(end_h, end_m, end_meridiem or start_meridiem)
    if not start or not end or end <= start:
        return None
    if re.search(r'全体|大家|\b(?:for our party|for everyone|for both of us)\b', clause, re.I):
        subject = 'party'
    elif re.search(r'^本人|^我已|^I have\b', clause, re.I):
        subject = 'self'
    elif party is not None and not re.search(r'我的|他的|她的|\b(?:my|your|their|his|her)\b', clause, re.I):
        subject = 'party'
    else:
        return None
    return dict(item_id='fixed-'+sha256(clause.encode()).hexdigest()[:20], kind='appointment',
                description=clause, applies_to=[subject], locked=_known(True),
                booking_status=dict(state='unknown'), start=_event(day, time=start, zone=zone),
                end=_event(day, time=end, zone=zone))


def grounded_fields(text, city, today):
    clauses = _clauses(text)
    first, last = _day_span(clauses, today)
    parties = {_number(match[1] or match[2]) for clause in clauses if not NEGATED.search(clause)
               for match in PARTY.finditer(clause)}
    party = parties.pop() if len(parties) == 1 else None
    zone = 'Asia/Shanghai' if city and city.casefold() in ('北京', 'beijing') else None
    fixed_clauses = tuple(dict.fromkeys(clause for clause in clauses if FIXED.search(clause)))
    fixed_items = [_fixed_item(clause, first, zone, party) for clause in fixed_clauses]
    result = dict(arrival=_event(first, zone=zone, place=city), departure=_event(last, zone=zone))
    if party:
        result['party_size'] = _known(party)
    if fixed_items and all(item is not None for item in fixed_items):
        result['fixed_items'] = fixed_items
    return result, None in fixed_items
