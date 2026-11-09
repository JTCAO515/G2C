"""Resolve an explicit Lio replacement against the current structured itinerary."""
from dataclasses import dataclass
from datetime import time
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
_CHINESE_SLOT = re.compile(r'第([一二三四五六七八九十]|[1-9][0-9]?)天\s*(上午|下午|晚上)')
_ENGLISH_SLOT = re.compile(r'(?:the\s+)?(?:day\s+([1-9][0-9]?)|(?:the\s+)?(first|second|third)\s+day)'
                           r'(?:\s+in\s+the)?\s+(morning|afternoon|evening)', re.I)
_ENGLISH_PERIOD_FIRST = re.compile(r'(?:the\s+)?(morning|afternoon|evening)\s+of\s+'
                                   r'(?:day\s+([1-9][0-9]?)|(?:the\s+)?(first|second|third)\s+day)', re.I)
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


def _select(items, target):
    slot = _slot(target)
    if slot is None:
        return [item for item in items if item['text'].casefold() == target.casefold()]

    ordinal, (lower, upper) = slot
    dates = [_known(item['schedule']['start']['date']) for item in items]
    if None in dates:
        return []
    days = sorted(set(dates))
    if ordinal > len(days):
        return []
    day = days[ordinal - 1]
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


def select_lio_edit(trip, text, locale, request_id):
    """Return an exact provisional change. This does not authorize publication."""
    match = match_edit(text)
    if match is None:
        return None
    target = match['target'].strip()
    replacement = match['replacement'].strip().rstrip('。.!！?？').rstrip()
    if trip is None or not target or not replacement or re.search(r'[;；]|(?:并且|然后|\band then\b)', replacement, re.I):
        return LioEditSelection('clarify')
    document = json.loads(trip.content)
    selected = _select(document['items'], target)
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
