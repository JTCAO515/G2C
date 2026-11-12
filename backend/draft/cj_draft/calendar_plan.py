"""Compact ordinal suggestions composed with protected source/current items."""
from copy import deepcopy
from datetime import date, time
import json

from cj_strict_json import reject_duplicates
from cj_needs.domain import subjects
from cj_trip.domain import packed
from cj_trip.structured import FieldRejected, SourceRejected, _fields
from cj_trip.structured_v3 import calendar_dates, validate_document

FIRST_PLAN = 'TRIP-lio-day-plan.1'
REPLAN_DELTA = 'TRIP-lio-day-delta.1'
DAY_SYSTEM = (
    'Return one compact JSON object. Each new item has exactly id,text,day_index,start_time,end_time,timezone. '
    'Use only the explicit requested day ordinals, local HH:MM times and the source destination timezone. '
    'The server retains all current/fixed items; never return their IDs. Return proposed_subjects for exactly '
    'your new IDs using explicit subject lists; no party-size or calendar-date assumptions. '
    'Do not return dates, booking claims, evidence or fixed declarations.'
)


def parse_model(raw, *, retained):
    if type(raw) is not bytes or not 0 < len(raw) <= 1_000_000:
        raise FieldRejected('plan', 'bounded compact ordinal plan required')
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates(ValueError, 'duplicate plan field'))
    except (ValueError, RecursionError):
        raise FieldRejected('plan', 'strict compact plan JSON required') from None
    expected = {'version', 'items', 'proposed_subjects'} if retained else {'version', 'title', 'items', 'proposed_subjects'}
    _fields(value, expected, 'plan', 'exact ordinal model fields required')
    if value['version'] != (REPLAN_DELTA if retained else FIRST_PLAN):
        raise FieldRejected('version', 'explicit first-plan/delta profile required')
    return value


def compose(raw, snapshot, fixed_days, day_count, *, start_date=None, retained=None, date_checks=None):
    """No writer. Caller must supply a current issued source and protected day map.

    The model proposes only new stops. It cannot change source, fixed/current
    content, calendar mode, title on replan or participant count.
    """
    if type(day_count) is not int or not 1 <= day_count <= 1_000_000 // 16:
        raise FieldRejected('days', 'requested days must fit the existing content byte bound')
    model = parse_model(raw, retained=retained is not None)
    if retained is not None:
        if retained['content_version'] != 'structured.3':
            raise SourceRejected('content_version', 'legacy context requires its original publisher')
        # Calendar changes require the explicit source-bound conversion operation.
        calendar = deepcopy(retained['calendar'])
        if start_date is not None and (calendar['state'] != 'dated' or calendar['start_date'] != start_date):
            raise SourceRejected('calendar', 'replan cannot silently convert or change calendar dates')
        start_date = calendar.get('start_date')
    calendar = dict(state='undated') if start_date is None else dict(state='dated', start_date=start_date)
    days = [dict(day_index=i) for i in range(1, day_count+1)]
    if start_date is not None:
        dates = calendar_dates(date.fromisoformat(start_date), day_count)
        days = [dict(day_index=i+1, date=d) for i, d in enumerate(dates)]
    current = [] if retained is None else deepcopy(retained['items'])
    current_by_id = {i['id']: i for i in current}
    originals = snapshot.fields.get('fixed_items', ())
    if set(fixed_days) != {i['item_id'] for i in originals}:
        raise SourceRejected('fixed_items', 'complete protected fixed-day mapping required')
    for original in originals:
        first, last = fixed_days[original['item_id']]
        if any(type(i) is not int or not 1 <= i <= day_count for i in (first, last)):
            raise SourceRejected('fixed_items', 'protected fixed day outside requested calendar')
        if original['item_id'] in current_by_id:
            old = current_by_id[original['item_id']]
            if (old['schedule']['start']['day_index'], old['schedule']['end']['day_index']) != (first, last):
                raise SourceRejected('fixed_items', 'source/current fixed ordinal conflict')
            continue
        schedule = {edge: dict(day_index=index, time=deepcopy(original[edge]['time']),
                    timezone=deepcopy(original[edge]['timezone']), utc_offset=dict(state='unknown'))
                    for edge, index in (('start', first), ('end', last))}
        current.append(dict(id=original['item_id'], text=original['description'], verification='pending', evidence=[],
            schedule=schedule, fixed=deepcopy(original['locked']), source_category='user_provided', source_refs=[]))
    if type(model['items']) is not list or len(model['items']) + len(current) > 60:
        raise FieldRejected('items', 'bounded new and retained stops required')
    new_ids = set()
    retained_ids = {i['id'] for i in current}
    zone = snapshot.fields.get('destination_timezone', {'state': 'unknown'})
    for index, item in enumerate(model['items']):
        path = f'items[{index}]'
        _fields(item, {'id', 'text', 'day_index', 'start_time', 'end_time', 'timezone'}, path,
                'exact ordinal compact stop required')
        if type(item['id']) is not str or item['id'] in retained_ids or item['id'] in new_ids:
            raise SourceRejected(path + '.id', 'new unique ID required; current items are server-retained')
        if zone['state'] != 'known' or item['timezone'] != zone['value']:
            raise SourceRejected(path + '.timezone', 'original destination timezone required')
        new_ids.add(item['id'])
        schedule = {edge: dict(day_index=item['day_index'], time=dict(state='known', value=item[edge+'_time']),
                     timezone=deepcopy(zone), utc_offset=dict(state='unknown')) for edge in ('start', 'end')}
        current.append(dict(id=item['id'], text=item['text'], verification='pending', evidence=[], schedule=schedule,
                            fixed=dict(state='known', value=False), source_category='unknown', source_refs=[]))
    if type(model['proposed_subjects']) is not dict or set(model['proposed_subjects']) != new_ids:
        raise SourceRejected('proposed_subjects', 'explicit subjects required for exactly the new stops')
    for value in model['proposed_subjects'].values():
        subjects(value)
    if start_date is None:
        checks = [dict(kind=k, state='not_checked', day_indices=list(range(1, day_count+1)), item_ids=[],
                       reason='date_not_set', evidence_refs=[]) for k in ('weather', 'day_opening')]
    else:
        if date_checks is None:
            raise SourceRejected('date_checks', 'dated plan needs explicit source check results')
        checks = deepcopy(date_checks)
    document = dict(content_version='structured.3', title=model['title'] if retained is None else retained['title'],
        calendar=calendar, days=days, items=current, sources=[] if retained is None else deepcopy(retained['sources']),
        date_checks=checks)
    validate_document(document)
    for item in model['items']:
        if time.fromisoformat(item['start_time']) >= time.fromisoformat(item['end_time']):
            raise SourceRejected('items', 'new stop requires a planned positive same-day interval')
    result = packed(document)
    if len(result) > 1_000_000:
        raise FieldRejected('document', 'existing Trip content byte bound exceeded')
    return result, deepcopy(model['proposed_subjects'])
