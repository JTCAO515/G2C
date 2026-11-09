"""Canonical planning declarations derived from the admitted user wording."""
from datetime import date, timedelta
from hashlib import sha256
import re


NUMBERS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten'),
                   range(1, 11), strict=True))
NUMBERS.update(zip('一二三四五六七八九十', range(1, 11), strict=True))
NUMBERS['两'] = 2
NUMBER = r'[0-9]{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十]'
DURATION = re.compile(rf'({NUMBER})\s*(?:-?\s*days?\b|天)', re.I)
PARTY = re.compile(rf'({NUMBER})\s*(?:people\b|persons?\b|个人|人)', re.I)
FIXED = re.compile(r'已经定好|固定安排|已锁定|已预订|已订|不可更改|不能改|'
                   r'\b(?:is fixed|already set|already booked|booked|must keep|cannot be changed)\b', re.I)
NEGATED = re.compile(r'\b(?:not|never|cancel|without)\b|还没|没有|未订|不再|不要|取消', re.I)
CLOCK = r'(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?'
RANGE = re.compile(rf'{CLOCK}\s*(?:[-–—到至]|\bto\b)\s*{CLOCK}', re.I)


def _number(value):
    return int(value) if value.isascii() and value.isdigit() else NUMBERS[value.lower()]


def _known(value):
    return dict(state='known', value=value) if value is not None else dict(state='missing')


def _positive(text, matches):
    return (match for match in matches
            if not NEGATED.search(text[max(0, match.start()-12):match.start()]))


def stated_city(text, city):
    return next(_positive(text, re.finditer(re.escape(city), text)), None) is not None


def _date_mentions(text, today):
    result = []
    pattern = r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)|明天|后天|今天|\b(?:day after tomorrow|tomorrow|today)\b'
    for match in _positive(text, re.finditer(pattern, text, re.I)):
        word = match[0].lower()
        offset = {'明天':1,'tomorrow':1,'后天':2,'day after tomorrow':2,'今天':0,'today':0}.get(word)
        try:
            parsed = today + timedelta(days=offset) if offset is not None else date.fromisoformat(word)
        except ValueError:
            continue
        if parsed not in result:
            result.append(parsed)
    return result


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


def _fixed_items(text, fields, today, first, zone, party):
    items = []
    for proposal in fields.get('fixed_items', []):
        quote = proposal['description']
        if quote not in text or not FIXED.search(quote) or NEGATED.search(quote):
            continue
        clocks = RANGE.search(quote)
        dates = _date_mentions(quote, today)
        first_day = re.search(r'第一天|\b(?:the )?first day\b', quote, re.I)
        day = dates[0] if dates else first if first_day else None
        if clocks is None or day is None or zone is None:
            continue
        start_h, start_m, start_meridiem, end_h, end_m, end_meridiem = clocks.groups()
        start = _clock(start_h, start_m, start_meridiem or end_meridiem)
        end = _clock(end_h, end_m, end_meridiem or start_meridiem)
        if not start or not end or end <= start:
            continue
        if party is not None or re.search(r'我们|全体|\b(?:our|we|party)\b', text, re.I):
            applies_to = ['party']
        elif re.search(r'本人|我|\b(?:I|my)\b', text, re.I):
            applies_to = ['self']
        else:
            continue
        items.append(dict(item_id='fixed-'+sha256(quote.encode()).hexdigest()[:20],
                          kind='appointment', description=quote, applies_to=applies_to,
                          locked=_known(True), booking_status=dict(state='unknown'),
                          start=_event(day, time=start, zone=zone),
                          end=_event(day, time=end, zone=zone)))
    return items


def grounded_fields(text, city, fields, today):
    days = _date_mentions(text, today)
    first = days[0] if days else None
    last = days[1] if len(days) > 1 else None
    duration = next(_positive(text, DURATION.finditer(text)), None)
    if first and duration:
        count = _number(duration[1])
        expected = first + timedelta(days=count-1) if count > 0 else None
        last = expected if last is None or last == expected else None
    if first and last and last < first:
        last = None
    party_match = next(_positive(text, PARTY.finditer(text)), None)
    party = _number(party_match[1]) if party_match else None
    zone = 'Asia/Shanghai' if city and city.casefold() in ('北京', 'beijing') else None
    fixed_items = _fixed_items(text, fields, today, first, zone, party)
    fixed_words = tuple(_positive(text, FIXED.finditer(text)))
    missing_fixed = any(not any(text.find(item['description']) <= match.start()
                        < text.find(item['description']) + len(item['description'])
                        for item in fixed_items) for match in fixed_words)
    result = dict(arrival=_event(first, zone=zone, place=city), departure=_event(last, zone=zone))
    if party:
        result['party_size'] = _known(party)
    if fixed_items:
        result['fixed_items'] = fixed_items
    return result, missing_fixed
