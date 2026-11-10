"""Resolve an explicit Lio replacement against the current structured itinerary."""
from dataclasses import dataclass
from datetime import date, time
from hashlib import sha256
import json
import re

from cj_manual_edit.scoped import Preview, Request, preview, resolve
from cj_trip.domain import Conflict, packed


_CHINESE_EDIT = re.compile(r'^(?:请|能不能|可以)?\s*把\s*(?P<target>.+?)\s*(?:换成|改成|替换成)\s*(?P<replacement>.+)$')
_ENGLISH_EDIT = re.compile(
    r'^(?:please\s+|(?:could|can|would) you\s+)?(?:change|replace|swap)\s+(?P<target>.+?)'
    r'\s+(?:to|with|for)\s+(?P<replacement>.+)$', re.I,
)
_KEEP_OTHER_STOPS = re.compile(
    r'(?:[，,]\s*)?保留(?:其他|其余)安排$|'
    r'(?:,\s*(?:and\s+)?|\s+and\s+)keep\s+(?:the\s+)?'
    r'(?:other (?:plans|stops|arrangements)|rest)(?:\s+(?:unchanged|the same))?$', re.I)
_QUALIFIED_REPLACEMENT = re.compile(
    r'[，,;；。.!！?？\r\n]|然后|并且|如果|除非|只有|不过|先别|暂不|不要|'
    r'\b(?:if|unless|provided|otherwise|but|then|until|wait|cancel)\b|'
    r'\bonly\s+(?:after|when|once)\b|'
    r'\band\s+(?:change|replace|swap|remove|add|move|cancel|do|wait|keep)\b', re.I)
_CHINESE_SLOT = re.compile(r'第([一二三四五六七八九十]|[1-9][0-9]?)天\s*(上午|下午|晚上)')
_ENGLISH_SLOT = re.compile(r'(?:the\s+)?(?:day\s+([1-9][0-9]?)|(?:the\s+)?(first|second|third)\s+day)'
                           r'(?:\s+in\s+the)?\s+(morning|afternoon|evening)', re.I)
_ENGLISH_PERIOD_FIRST = re.compile(r'(?:the\s+)?(morning|afternoon|evening)\s+of\s+'
                                   r'(?:day\s+([1-9][0-9]?)|(?:the\s+)?(first|second|third)\s+day)', re.I)
_DATED_SLOT = re.compile(r'([0-9]{4}-[0-9]{2}-[0-9]{2})\s*(上午|下午|晚上|morning|afternoon|evening)', re.I)
_ENGLISH_DATED_SLOT = re.compile(r'(?:the\s+)?(morning|afternoon|evening)\s+(?:of|on)\s+'
                                 r'([0-9]{4}-[0-9]{2}-[0-9]{2})', re.I)
_ORDINALS = {**dict(zip('一二三四五六七八九十', range(1, 11), strict=True)),
             'first': 1, 'second': 2, 'third': 3}
_PERIODS = {
    '上午': (time(0), time(12)), 'morning': (time(0), time(12)),
    '下午': (time(12), time(18)), 'afternoon': (time(12), time(18)),
    '晚上': (time(18), time.max), 'evening': (time(18), time.max),
}


@dataclass(frozen=True)
class LioEditSelection:
    status: str
    candidate: Preview | None = None


def match_edit(text):
    utterance = text.strip()
    return _CHINESE_EDIT.fullmatch(utterance) or _ENGLISH_EDIT.fullmatch(utterance)


def _ordinal(value):
    return int(value) if value.isascii() and value.isdigit() else _ORDINALS[value.lower()]


def _slot(target):
    chinese = _CHINESE_SLOT.fullmatch(target)
    if chinese:
        return _ordinal(chinese[1]), _PERIODS[chinese[2]]
    english = _ENGLISH_SLOT.fullmatch(target)
    if english:
        return _ordinal(english[1] or english[2]), _PERIODS[english[3].lower()]
    reversed_english = _ENGLISH_PERIOD_FIRST.fullmatch(target)
    if reversed_english:
        return _ordinal(reversed_english[2] or reversed_english[3]), _PERIODS[reversed_english[1].lower()]
    return None


def _known(observation):
    return observation['value'] if observation['state'] == 'known' else None


def _dated_slot(target):
    dated = _DATED_SLOT.fullmatch(target)
    if dated:
        return dated[1], _PERIODS[dated[2].lower()]
    english = _ENGLISH_DATED_SLOT.fullmatch(target)
    if english:
        return english[2], _PERIODS[english[1].lower()]
    return None


def _select(items, target, starts_on):
    relative = _slot(target)
    dated = _dated_slot(target) if relative is None else None
    if relative is None and dated is None:
        return [item for item in items if item['text'].casefold() == target.casefold()]

    dates = [_known(item['schedule']['start']['date']) for item in items]
    if None in dates:
        return []
    if relative is not None:
        ordinal, (lower, upper) = relative
        displayed_dates = sorted(set(dates))
        if starts_on is None or ordinal > len(displayed_dates):
            return []
        day = displayed_dates[ordinal - 1]
        # A day with no stops is absent from the current card. A relative edit
        # must select the same date in the trip calendar and in that card.
        if (date.fromisoformat(day) - starts_on).days != ordinal - 1:
            return []
    else:
        day, (lower, upper) = dated
        if day not in dates:
            return []
    selected = []
    for item, item_date in zip(items, dates, strict=True):
        start = item['schedule']['start']
        end = item['schedule']['end']
        end_date = _known(end['date'])
        if end_date is None or (item_date != end_date and item_date <= day <= end_date):
            return []
        if item_date != day:
            continue
        start_clock, end_clock = _known(start['time']), _known(end['time'])
        if start_clock is None or end_clock is None:
            return []
        begins, ends = time.fromisoformat(start_clock), time.fromisoformat(end_clock)
        if lower <= begins < ends <= upper:
            selected.append(item)
        elif begins < upper and lower < ends:
            return []
    return selected


def select_lio_edit(trip, text, locale, request_id, *, starts_on):
    """Return an exact provisional change. This does not authorize publication."""
    match = match_edit(text)
    if match is None:
        return None
    target = match['target'].strip()
    replacement = match['replacement'].strip().rstrip('。.!！?？').rstrip()
    replacement = _KEEP_OTHER_STOPS.sub('', replacement).rstrip()
    if trip is None or not target or not replacement or _QUALIFIED_REPLACEMENT.search(replacement):
        return LioEditSelection('clarify')
    document = json.loads(trip.content)
    selected = _select(document['items'], target, starts_on)
    if len(selected) != 1 or selected[0]['text'] == replacement:
        return LioEditSelection('clarify')
    item = selected[0]
    if item['fixed'] != {'state': 'known', 'value': False}:
        return LioEditSelection('protected')

    identity = dict(request_id=request_id, trip_id=trip.trip_id, expected_version=trip.version,
                    original_hash=sha256(trip.content).hexdigest())
    try:
        request = Request.parse(packed(dict(identity, version='TRIP-scoped-request.1',
            text=text, language='zh-Hans' if locale == 'zh' else 'en',
            selection=dict(kind='items', item_ids=[item['id']]))))
        selection = resolve(trip, request)
        if selection.status != 'READY':
            return LioEditSelection('clarify')
        edit = packed(dict(identity, version='TRIP-manual-edit.2', title=None, order=None,
                           changes=[dict(item_id=item['id'], field='text', value=replacement)]))
        candidate = preview(selection, edit)
    except (ValueError, Conflict):
        return LioEditSelection('clarify')
    if candidate.candidate is None:
        return LioEditSelection('clarify')
    return LioEditSelection('preview', candidate)
