"""Explicit single-stop text selection for calendar itineraries, without date buckets."""
from dataclasses import dataclass
from datetime import time
from hashlib import sha256
import json

from cj_manual_edit.scoped import Request
from cj_trip.domain import packed

from .lio_edit_selection import (_COMPOUND_EN, _COMPOUND_ZH, _STOP_QUOTES, _dated_slot,
    _edit_parts, _known, _national_replacement, _replacement_label, _slot, match_edit)


@dataclass(frozen=True)
class CalendarSelection:
    status: str
    request: Request | None = None
    edit: bytes | None = None
    selected_ids: tuple[str, ...] = ()


def _select(document, target):
    items = document['items']
    compound = _COMPOUND_ZH.fullmatch(target) or _COMPOUND_EN.fullmatch(target)
    if compound is not None:
        if _STOP_QUOTES[compound['open']] != compound['close']:
            return []
        return [item for item in _select(document, compound['slot'].strip())
                if item['text'].casefold() == compound['name'].strip().casefold()
                and _known(item['schedule']['start']['time']) == compound['start']
                and _known(item['schedule']['end']['time']) == compound['end']]
    relative, dated = _slot(target), _dated_slot(target)
    if relative is None and dated is None:
        return [item for item in items if item['text'].casefold() == target.casefold()]
    if relative is not None:
        ordinal, (lower, upper) = relative
        if ordinal == -1:
            ordinal = len(document['days'])
    else:
        if document['calendar']['state'] != 'dated':
            return []
        selected_date, (lower, upper) = dated
        ordinals = [day['day_index'] for day in document['days'] if day['date'] == selected_date]
        if len(ordinals) != 1:
            return []
        ordinal = ordinals[0]
    if not 1 <= ordinal <= len(document['days']):
        return []
    selected = []
    for item in items:
        start, end = item['schedule']['start'], item['schedule']['end']
        if start['day_index'] != end['day_index']:
            if start['day_index'] <= ordinal <= end['day_index']:
                return []
            continue
        if start['day_index'] != ordinal:
            continue
        clocks = _known(start['time']), _known(end['time'])
        if None in clocks:
            return []
        begins, ends = map(time.fromisoformat, clocks)
        if lower <= begins < ends <= upper:
            selected.append(item)
        elif begins < upper and lower < ends:
            return []
    return selected


def select_calendar_edit(trip, text, locale, request_id):
    match = match_edit(text)
    if match is None:
        return None
    document = json.loads(trip.content)
    interpretations = []
    for target, raw in _edit_parts(match):
        raw, protected = _national_replacement(raw)
        if raw is None:
            continue
        replacement = _replacement_label(raw, national_names=True)
        if replacement is None:
            continue
        for item in _select(document, target):
            if protected is None or protected.casefold() not in item['text'].casefold():
                interpretations.append((item, replacement))
    if len(interpretations) != 1:
        return CalendarSelection('clarify')
    (item, replacement), = interpretations
    if item['fixed'] != dict(state='known', value=False):
        return CalendarSelection('protected')
    if item['text'] == replacement:
        return CalendarSelection('clarify')
    identity = dict(request_id=request_id, trip_id=trip.trip_id, expected_version=trip.version,
                    original_hash=sha256(trip.content).hexdigest())
    request = Request.parse(packed(dict(identity, version='TRIP-scoped-request.1', text=text,
        language='zh-Hans' if locale == 'zh' else 'en', selection=dict(kind='items', item_ids=[item['id']]))))
    edit = packed(dict(identity, version='TRIP-calendar-edit.1', title=None, order=None,
                       changes=[dict(item_id=item['id'], field='text', value=replacement)]))
    return CalendarSelection('preview', request, edit, (item['id'],))
