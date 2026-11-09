"""Derive authoritative itinerary inputs from explicit, bounded declarations."""
from datetime import date, timedelta
from hashlib import sha256
import re


NUMBERS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten'),
                   range(1, 11), strict=True))
NUMBERS.update(zip('一二三四五六七八九十', range(1, 11), strict=True))
NUMBERS['两'] = 2
NUMBER = r'[0-9]{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十]'
PLAN_REQUEST = re.compile(
    r"^\s*(?:(?:(?:请|麻烦)?(?:(?:帮|给|为)(?:我们|我)[^。！？.!?]{0,16}?)?"
    r"(?:规划|(?:安排|设计|做)(?:个|一个|一份)?[^。！？.!?]*(?:行程|日游|天游|旅行|旅游|游玩|攻略))"
    r"|(?:(?:can|could|would) you\s+|please\s+|i(?: would|'d) like you to\s+)?"
    r"(?:help (?:me|us) (?:to )?)?(?:plan|build|create|organize|put together|draft|make)\b"
    r"[^.!?]*\b(?:itinerary|trip|visit|days?\s+in)\b))", re.I,
)
ISO = r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)'
SPAN = re.compile(rf'({ISO})\s*(?:to\b|through\b|到|至|–|—)\s*({ISO})', re.I)
TRIP_DATES = re.compile(rf'^(?:(?:Travel|Trip dates?)\s*(?:from\s*)?|(?:日期|行程日期)\s*[:：]?\s*|'
                        rf'(?:Beijing|北京)\s*[,，：:]\s*)?(?:{ISO})\s*(?:to\b|through\b|到|至|–|—)', re.I)
DATES_UNDECIDED = re.compile(
    r'\b(?:dates? (?:are|is) undecided|travel dates? (?:are|is) unknown)\b|'
    r'\b(?:suggest|recommend|choose|pick|help me decide)\b[^.?!]{0,32}\bdates?\b|'
    r'日期(?:未定|待定)|(?:推荐|建议|帮我选)[^。！？]{0,12}日期', re.I)
DURATION = re.compile(rf'({NUMBER})\s*(?:-?\s*days?\b|天)', re.I)
START = re.compile(r'\b(?:starting|beginning|from)\s+(tomorrow|today)\b|从?(明天|今天|后天)(?:开始|起)', re.I)
PARTY = re.compile(rf'\bfor\s+({NUMBER})\s+(?:people|persons?)\b|({NUMBER})\s*(?:个人|人)', re.I)
DESTINATION = re.compile(r'\b(?:itinerary|trip|days?)\s+(?:in|to)\s+Beijing\b|'
                         r'\bBeijing\s+(?:itinerary|trip|visit)\b|'
                         r'(?:去|到|在)北京|北京(?:\s*[，,：:]|[一二两三四五六七八九十\d]+天|游|行程)', re.I)
PRIMARY_DESTINATION = re.compile(r'\b(?:itinerary|trip|days?)\s+(?:in|to)\s+([A-Za-z]+)\b', re.I)
OTHER_DESTINATION = re.compile(r'\bfrom\s+Beijing\s+to\b|从北京(?:去|到)', re.I)
CITY_REPLY = re.compile(r'^(?:Beijing|北京)(?=$|[,，：:]|\s+(?:\d{4}-|from\b|从|明天|今天))', re.I)
FIXED = re.compile(r'已经定好|固定安排|已锁定|已预订|已订|不可更改|不能改|'
                   r'\b(?:is fixed|already set|already booked|have (?:actually )?booked|'
                   r'has booked|is booked|must keep|cannot be changed)\b', re.I)
NEGATED = re.compile(
    r"\b(?:not|never|cancel|without|if|whether|maybe|might|suppose|assuming|in case|hypothetically)\b"
    r"|n['’]t\b|还没|没有|未订|不再|不要|取消|如果|可能|不确定|假如|假设|要是|倘若", re.I)
OTHER = re.compile(r'孩子|女儿|儿子|母亲|父亲|同伴|家人|\b(?:daughter|son|mother|father|friend|guest)\b', re.I)
CLOCK = r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?'
RANGE = re.compile(rf'{CLOCK}\s*(?:[-–—到至]|\bto\b)\s*{CLOCK}', re.I)
CLAUSE_BREAK = re.compile(r'[!?。；;\n]+|\.(?=\s+[A-Z])|，(?=\s*(?:第[一二三四五六七八九十\d]+天|酒店集合))')
FIXED_REPLY = re.compile(r'^(?:全体|大家|本人|我参加|第[一二三四五六七八九十\d]+天|'
                         r'(?:for (?:everyone|our party|both of us)|on (?:the first day|\d{4}-))\b)', re.I)


def _clauses(text):
    return tuple(clause.strip().rstrip('.') for clause in CLAUSE_BREAK.split(text) if clause.strip())


def _number(value):
    return int(value) if value.isascii() and value.isdigit() else NUMBERS[value.lower()]


def _known(value):
    return dict(state='known', value=value) if value is not None else dict(state='missing')


def stated_city(turns, city):
    if city.casefold() not in ('beijing', '北京'):
        return any(city in clause and PLAN_REQUEST.match(clause) and not NEGATED.search(clause)
                   for turn in turns for clause in _clauses(turn))
    for turn in turns:
        for clause in _clauses(turn):
            if (city not in clause or not PLAN_REQUEST.match(clause) or not DESTINATION.search(clause)
                    or NEGATED.search(clause) or OTHER_DESTINATION.search(clause)):
                continue
            primary = PRIMARY_DESTINATION.search(clause)
            if primary is None or primary[1].casefold() == 'beijing':
                return True
    return len(turns) > 1 and any(city in clause and CITY_REPLY.match(clause) and not NEGATED.search(clause)
                                 for clause in _clauses(turns[-1]))


def _day_span(turns, today):
    for turn in reversed(turns):
        if DATES_UNDECIDED.search(turn):
            return None, None
        spans = set()
        for clause in _clauses(turn):
            if NEGATED.search(clause) or FIXED.search(clause):
                continue
            if not (PLAN_REQUEST.match(clause) or TRIP_DATES.match(clause)):
                continue
            try:
                explicit = tuple(SPAN.finditer(clause))
                for match in explicit:
                    prefix = clause[:match.start()].strip()
                    scoped = TRIP_DATES.match(clause) is not None or re.search(
                        rf'(?:Beijing(?:\s+for\s+(?:{NUMBER})\s+people)?\s+from|'
                        r'北京\s*(?:从|在)?|(?:trip|itinerary)\s+dates?\s*[:：]?)$', prefix, re.I)
                    if scoped:
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
        if spans:
            if len(spans) == 1:
                first, last = spans.pop()
                if first <= last:
                    return first, last
            return None, None
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


def _fixed_item(clause, first, zone, party, *, reply=''):
    details = f'{clause}\n{reply}' if reply else clause
    if NEGATED.search(details) or OTHER.search(details) or zone is None:
        return None
    ranges = {match.groups() for match in RANGE.finditer(re.sub(ISO, ' ', details))}
    try:
        dates = {date.fromisoformat(value) for value in re.findall(ISO, details)}
    except ValueError:
        return None
    if first and re.search(r'第一天|\b(?:the )?first day\b', details, re.I):
        dates.add(first)
    if len(ranges) != 1 or len(dates) != 1:
        return None
    day = dates.pop()
    start_h, start_m, start_meridiem, end_h, end_m, end_meridiem = ranges.pop()
    start = _clock(start_h, start_m, start_meridiem or end_meridiem)
    end = _clock(end_h, end_m, end_meridiem or start_meridiem)
    if not start or not end or end <= start:
        return None
    if re.search(r'全体|大家|\b(?:for our party|for everyone|for both of us)\b', details, re.I):
        subject = 'party'
    elif re.search(r'本人|我参加|\b(?:for myself|for me only|only me)\b', details, re.I):
        subject = 'self'
    elif party is not None and not re.search(r'我的|他的|她的|\b(?:my|your|their|his|her)\b', clause, re.I):
        subject = 'party'
    else:
        return None
    return dict(item_id='fixed-'+sha256(clause.encode()).hexdigest()[:20], kind='appointment',
                description=clause, applies_to=[subject], locked=_known(True),
                booking_status=dict(state='unknown'), start=_event(day, time=start, zone=zone),
                end=_event(day, time=end, zone=zone))


def grounded_fields(turns, city, today):
    clauses = tuple(clause for turn in turns for clause in _clauses(turn))
    first, last = _day_span(turns, today)
    parties = {_number(match[1] or match[2]) for clause in clauses
               if PLAN_REQUEST.match(clause) and not NEGATED.search(clause)
               for match in PARTY.finditer(clause)}
    party = parties.pop() if len(parties) == 1 else None
    zone = 'Asia/Shanghai' if city and city.casefold() in ('北京', 'beijing') else None
    fixed_clauses = tuple(dict.fromkeys(clause for clause in clauses if FIXED.search(clause)))
    fixed_items = [_fixed_item(clause, first, zone, party) for clause in fixed_clauses]
    if len(turns) > 1 and fixed_items.count(None) == 1:
        reply = turns[-1].strip()
        if FIXED_REPLY.match(reply) and not FIXED.search(reply):
            index = fixed_items.index(None)
            fixed_items[index] = _fixed_item(fixed_clauses[index], first, zone, party, reply=reply)
    result = dict(arrival=_event(first, zone=zone, place=city), departure=_event(last, zone=zone))
    if party:
        result['party_size'] = _known(party)
    if fixed_items and all(item is not None for item in fixed_items):
        result['fixed_items'] = fixed_items
    return result, None in fixed_items
