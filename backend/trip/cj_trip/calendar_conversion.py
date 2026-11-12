"""Deterministic calendar transformation. No writer or authority is created here."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
import re

from .domain import Conflict, identifier, packed
from .structured import _date, _fields, _text
from .structured_v3 import calendar_dates, legacy_validation_view


def original_reference(value):
    _fields(value, {'conversation_id', 'generation', 'message_id', 'run_id', 'sequence',
                   'input_sha256', 'message_version', 'lio_protocol'}, 'reference', 'exact original reference required')
    for name in ('conversation_id', 'generation', 'message_id', 'run_id'):
        _text(value[name], 1024)
        if '\x00' in value[name]:
            raise ValueError('original reference cannot contain NUL')
    if type(value['sequence']) is not int or not 1 <= value['sequence'] <= 2**63-1:
        raise ValueError('explicit original sequence required')
    if type(value['input_sha256']) is not str or re.fullmatch('[0-9a-f]{64}', value['input_sha256']) is None:
        raise ValueError('canonical original MESSAGE digest required')
    if value['message_version'] not in ('MESSAGE-send.1', 'MESSAGE-send.2', 'MESSAGE-send.3', 'MESSAGE-send.4'):
        raise ValueError('existing canonical MESSAGE version required')
    if value['lio_protocol'] not in ('LIO-message.1', 'LIO-message.2', 'LIO-message.3'):
        raise ValueError('original Lio protocol required')


@dataclass(frozen=True, repr=False)
class DateConvert:
    raw: bytes
    action_id: str
    trip_id: str
    expected_version: int
    original_hash: str
    start_date: date
    source_reference: bytes
    quote: str
    question_day: date

    @classmethod
    def parse(cls, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= 32768:
            raise ValueError('bounded original date-conversion bytes required')
        value = json.loads(raw)
        _fields(value, {'version', 'action_id', 'trip_id', 'expected_version', 'original_hash',
                       'start_date', 'date_source'}, 'conversion', 'exact conversion fields required')
        if value['version'] != 'TRIP-date-convert.1' or packed(value) != raw:
            raise ValueError('canonical date-conversion input required')
        identifier(value['action_id']); identifier(value['trip_id'])
        if type(value['expected_version']) is not int or not 1 <= value['expected_version'] <= 2**63-1:
            raise ValueError('original Trip version required')
        if type(value['original_hash']) is not str or re.fullmatch('[0-9a-f]{64}', value['original_hash']) is None:
            raise ValueError('original Trip digest required')
        _date(value['start_date'])
        source = value['date_source']
        _fields(source, {'reference', 'quote', 'question_day'}, 'date_source', 'exact date source required')
        original_reference(source['reference'])
        _text(source['quote'], 12000)
        if len(source['quote'].encode()) > 12000:
            raise ValueError('bounded original date quote required')
        _date(source['question_day'])
        return cls(raw, value['action_id'], value['trip_id'], value['expected_version'], value['original_hash'],
                   date.fromisoformat(value['start_date']), packed(source['reference']), source['quote'],
                   date.fromisoformat(source['question_day']))


@dataclass(frozen=True)
class CalendarTransform:
    content: bytes | None
    conflicts: tuple


def fixed_date_conflicts(document, dates, fixed_fields):
    items = {i['id']: i for i in document['items']}
    conflicts = []
    for fixed in fixed_fields:
        item = items.get(fixed['item_id'])
        if item is None:
            raise Conflict('conversion cannot omit original fixed source')
        if fixed['locked'] != {'state': 'known', 'value': True}:
            continue
        for edge in ('start', 'end'):
            source_date = fixed[edge]['date']
            if source_date['state'] == 'known' and source_date['value'] != dates[item['schedule'][edge]['day_index']-1]:
                conflicts.append(dict(kind='hard_fixed', code='FIXED_DATE_CONFLICT',
                    day_indices=[item['schedule'][edge]['day_index']], item_ids=[item['id']],
                    reason='requested start conflicts with the original fixed date', evidence_refs=[]))
    return tuple(conflicts)


def check_conflicts(date_checks):
    return tuple(dict(kind='date_dependent', code='DATE_' + check['kind'].upper(),
        day_indices=check['day_indices'], item_ids=check['item_ids'], reason=check['reason'],
        evidence_refs=check['evidence_refs']) for check in date_checks if check['state'] == 'conflict')


def source_window_conflicts(document, fields):
    """Preserve known destination/window facts without inventing missing dates.

    Inputs are the validated Trip and actual NEEDS snapshot. This is a pure
    counterpart of the original SourceWindow publisher's date/zone/instant checks.
    """
    from cj_feasibility.time_checks import instant, known
    zone = known(fields.get('destination_timezone', dict(state='unknown')))
    bounds = [fields.get(key) for key in ('arrival', 'departure')]
    dates = [None if event is None else known(event['date']) for event in bounds]
    moments = [None if event is None else instant(event, key)[0]
               for event, key in zip(bounds, ('arrival', 'departure'))]
    conflicts = []

    def conflict(code, reason, item=None, day_indices=None):
        conflicts.append(dict(kind='hard_fixed', code=code,
            day_indices=[] if day_indices is None else day_indices,
            item_ids=[] if item is None else [item['id']], reason=reason, evidence_refs=[]))

    if dates[0] is not None and dates[1] is not None and dates[1] < dates[0]:
        conflict('SOURCE_WINDOW_REVERSED', 'confirmed source planning dates are reversed')
    if moments[0] is not None and moments[1] is not None and moments[1] < moments[0]:
        conflict('SOURCE_WINDOW_REVERSED', 'confirmed source planning instants are reversed')
    for key, event in zip(('arrival', 'departure'), bounds):
        if event is not None and zone is not None and known(event['timezone']) not in (None, zone):
            conflict('SOURCE_TIMEZONE_CONFLICT', key+' differs from confirmed destination timezone')
    if document['calendar']['state'] == 'dated':
        for day in document['days']:
            if ((dates[0] is not None and day['date'] < dates[0])
                    or (dates[1] is not None and day['date'] > dates[1])):
                conflict('SOURCE_DATE_WINDOW_CONFLICT', 'calendar day is outside confirmed source bounds',
                         day_indices=[day['day_index']])
    projected = legacy_validation_view(document)
    for item, copy in zip(document['items'], projected['items']):
        for edge in ('start', 'end'):
            event = copy['schedule'][edge]
            index = item['schedule'][edge]['day_index']
            if zone is not None and known(event['timezone']) not in (None, zone):
                conflict('SOURCE_TIMEZONE_CONFLICT', 'activity differs from confirmed destination timezone', item, [index])
            moment = instant(event, edge, utc_offset=event['utc_offset'])[0]
            if moment is not None and ((moments[0] is not None and moment < moments[0])
                                      or (moments[1] is not None and moment > moments[1])):
                conflict('SOURCE_TIME_WINDOW_CONFLICT', 'activity is outside confirmed source instants', item, [index])
    return tuple(conflicts)


def converted_content(document, start, date_checks, fixed_fields):
    """Internal builder; the caller still needs actual source/identity/commit leases."""
    if document['content_version'] != 'structured.3' or document['calendar']['state'] != 'undated':
        raise Conflict('date conversion requires an undated calendar version')
    dates = calendar_dates(start, len(document['days']))
    conflicts = fixed_date_conflicts(document, dates, fixed_fields)
    if conflicts:
        return CalendarTransform(None, conflicts)
    result = deepcopy(document)
    result['calendar'] = dict(state='dated', start_date=start.isoformat())
    result['days'] = [dict(day_index=i+1, date=d) for i, d in enumerate(dates)]
    result['date_checks'] = deepcopy(date_checks)
    return CalendarTransform(packed(result), check_conflicts(date_checks))
