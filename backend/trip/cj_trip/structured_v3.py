"""Explicit day-ordinal calendars; no date, source or publishing inference."""
from copy import deepcopy
from datetime import date, timedelta

from .structured import FieldRejected, _date, _fields, _text
from .structured_v2 import validate_document as validate_legacy_fields

VERSION = 'structured.3'


def calendar_dates(start, count):
    """Internal arithmetic over an already parsed date and explicit day count."""
    try:
        return tuple((start + timedelta(days=i)).isoformat() for i in range(count))
    except OverflowError:
        raise FieldRejected('calendar.start_date', 'calendar range exceeds representable dates') from None


def legacy_validation_view(document):
    """Validation-only copy. Never stored or returned under a different version."""
    result = dict(content_version='structured.2', title=document['title'],
                  sources=document['sources'], items=deepcopy(document['items']))
    dated = document['calendar']['state'] == 'dated'
    for item in result['items']:
        for edge in ('start', 'end'):
            event = item['schedule'][edge]
            index = event.pop('day_index')
            event['date'] = (dict(state='known', value=document['days'][index-1]['date'])
                             if dated else dict(state='unknown'))
    return result


def validate_document(document):
    _fields(document, {'content_version', 'title', 'calendar', 'days', 'items', 'sources', 'date_checks'},
            'document', 'exact structured.3 document required')
    if document['content_version'] != VERSION:
        raise FieldRejected('content_version', 'structured.3 required')
    calendar = document['calendar']
    if type(calendar) is not dict or calendar.get('state') not in ('undated', 'dated'):
        raise FieldRejected('calendar', 'explicit undated/dated calendar required')
    dated = calendar['state'] == 'dated'
    _fields(calendar, {'state', 'start_date'} if dated else {'state'}, 'calendar', 'exact calendar fields required')
    days = document['days']
    if type(days) is not list or not days:
        raise FieldRejected('days', 'explicit nonempty days required')
    if dated:
        _date(calendar['start_date'])
        expected = calendar_dates(date.fromisoformat(calendar['start_date']), len(days))
    for index, day in enumerate(days, 1):
        _fields(day, {'day_index', 'date'} if dated else {'day_index'}, f'days[{index-1}]', 'exact calendar day required')
        if type(day['day_index']) is not int or day['day_index'] != index:
            raise FieldRejected(f'days[{index-1}].day_index', 'contiguous positive integer day indices required')
        if dated and day['date'] != expected[index-1]:
            raise FieldRejected(f'days[{index-1}].date', 'date must equal start plus ordinal minus one')
    if type(document['items']) is not list or not 1 <= len(document['items']) <= 60:
        raise FieldRejected('items', 'bounded structured items required')
    for index, item in enumerate(document['items']):
        _fields(item, {'id', 'text', 'verification', 'evidence', 'schedule', 'fixed', 'source_category', 'source_refs'},
                f'items[{index}]', 'exact structured item required')
        _fields(item['schedule'], {'start', 'end'}, f'items[{index}].schedule', 'exact schedule required')
        for edge in ('start', 'end'):
            event = item['schedule'][edge]
            path = f'items[{index}].schedule.{edge}'
            _fields(event, {'day_index', 'time', 'timezone', 'utc_offset'}, path, 'exact ordinal event required')
            if type(event['day_index']) is not int or not 1 <= event['day_index'] <= len(days):
                raise FieldRejected(path + '.day_index', 'event day outside explicit calendar')
            if not dated and type(event['utc_offset']) is dict and event['utc_offset'].get('state') == 'known':
                raise FieldRejected(path + '.utc_offset', 'undated event has no resolved instant offset')
    # Reuse unchanged field, Observation, fixed, source-record and evidence rules.
    validate_legacy_fields(legacy_validation_view(document))
    checks = document['date_checks']
    if type(checks) is not list or len(checks) != 2:
        raise FieldRejected('date_checks', 'both date-dependent check results required')
    kinds = set()
    item_ids = {i['id'] for i in document['items']}
    for index, check in enumerate(checks):
        path = f'date_checks[{index}]'
        _fields(check, {'kind', 'state', 'day_indices', 'item_ids', 'reason', 'evidence_refs'}, path,
                'exact date-check result required')
        if check['kind'] not in ('weather', 'day_opening') or check['kind'] in kinds:
            raise FieldRejected(path + '.kind', 'distinct date-check kinds required')
        kinds.add(check['kind'])
        if check['state'] not in ('not_checked', 'unknown', 'clear', 'conflict'):
            raise FieldRejected(path + '.state', 'explicit date-check state required')
        indices, ids, refs = check['day_indices'], check['item_ids'], check['evidence_refs']
        if (type(indices) is not list or not indices or any(type(i) is not int or not 1 <= i <= len(days) for i in indices)
                or len(indices) != len(set(indices))):
            raise FieldRejected(path + '.day_indices', 'distinct in-range day indices required')
        if type(ids) is not list or any(type(i) is not str or i not in item_ids for i in ids) or len(ids) != len(set(ids)):
            raise FieldRejected(path + '.item_ids', 'distinct original item references required')
        _text(check['reason'], 500)
        if type(refs) is not list or len(refs) > 40:
            raise FieldRejected(path + '.evidence_refs', 'bounded evidence references required')
        for reference in refs:
            _text(reference, 4096)
        if not dated and (check['state'] != 'not_checked' or check['reason'] != 'date_not_set' or refs):
            raise FieldRejected(path, 'undated check cannot claim date-dependent evidence')
        if dated and (check['state'] == 'not_checked' or check['state'] in ('clear', 'conflict') and not refs):
            raise FieldRejected(path, 'dated check requires explicit result/unknown and evidence for a claim')
