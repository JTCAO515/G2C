"""Compact ordinal suggestions composed with protected source/current items."""
from copy import deepcopy
from datetime import date, time
import json

from cj_strict_json import reject_duplicates
from cj_needs.domain import subjects
from cj_trip.domain import packed
from cj_trip.structured import FieldRejected, SourceRejected, _fields, _date
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


def _day_count(day_count):
    if type(day_count) is not int or not 1 <= day_count <= 1_000_000 // 16:
        raise FieldRejected('days', 'requested days must fit the existing content byte bound')


def _calendar(start_date, retained):
    if retained is not None:
        # Calendar changes require the explicit source-bound conversion operation.
        calendar = deepcopy(retained['calendar'])
        if start_date is not None and (calendar['state'] != 'dated' or calendar['start_date'] != start_date):
            raise SourceRejected('calendar', 'replan cannot silently convert or change calendar dates')
        start_date = calendar.get('start_date')
    return dict(state='undated') if start_date is None else dict(state='dated', start_date=start_date)


def _protected_items(fields, fixed_days, day_count, retained):
    """Shared merge of already checked data; no source or model abstraction."""
    current = [] if retained is None else deepcopy(retained['items'])
    current_by_id = {i['id']: i for i in current}
    originals = fields.get('fixed_items', ())
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
    return current


def protected_base_data(fields, fixed_days, day_count, *, start_date=None, retained=None):
    """Pure pre-city data for complete-graph capacity checks, not source authority.

    fields/fixed_days are source-span-checked projections with the same final
    code-owned fixed IDs used after city binding. retained is the actual read,
    validated structured.3/.4 document, never a fabricated Snapshot/capture.
    No timezone, date evidence, party or provider fact is inferred here. Unknown
    observations remain original. All retained rich metadata/sources is copied.

    This is not a Trip document or feasibility verdict. The caller adds the full
    skeleton, hotel/edge items and legs before measuring canonical bytes. It must
    bind the real city, run original fields/date/fixed guards and recapture/rebuild
    the final candidate afterwards. No preflight result supplies that permission.
    """
    _day_count(day_count)
    if type(fields) is not dict:
        raise FieldRejected('fields', 'checked projected fields data required')
    if retained is not None and (type(retained) is not dict
            or retained.get('content_version') not in ('structured.3', 'structured.4')):
        raise SourceRejected('content_version', 'explicit original calendar/rich data required')
    originals = fields.get('fixed_items', ())
    ids = [item['item_id'] for item in originals]
    if len(ids) != len(set(ids)):
        raise SourceRejected('fixed_items', 'distinct original fixed IDs required')
    calendar = _calendar(start_date, retained)
    days = [dict(day_index=i) for i in range(1, day_count+1)]
    if calendar['state'] == 'dated':
        _date(calendar['start_date'])
        dates = calendar_dates(date.fromisoformat(calendar['start_date']), day_count)
        days = [dict(day_index=i+1, date=d) for i, d in enumerate(dates)]
    items = _protected_items(fields, fixed_days, day_count, retained)
    for item in items:
        first, last = (item['schedule'][edge]['day_index'] for edge in ('start', 'end'))
        if (any(type(index) is not int for index in (first, last)) or not 1 <= first <= last <= day_count):
            raise SourceRejected('fixed_items', 'complete protected endpoints outside requested calendar')
    retained_ids = set() if retained is None else {item['id'] for item in retained['items']}
    fixed_ids = set(ids)
    return dict(calendar=calendar, days=days, items=items,
        sources=[] if retained is None else deepcopy(retained['sources']),
        origins={item['id']: [name for name, present in
            (('current_trip', item['id'] in retained_ids), ('fixed_fields', item['id'] in fixed_ids)) if present]
            for item in items})


def compose(raw, snapshot, fixed_days, day_count, *, start_date=None, retained=None, date_checks=None):
    """No writer. Caller must supply a current issued source and protected day map.

    The model proposes only new stops. It cannot change source, fixed/current
    content, calendar mode, title on replan or participant count.
    """
    _day_count(day_count)
    model = parse_model(raw, retained=retained is not None)
    if retained is not None and retained['content_version'] != 'structured.3':
        raise SourceRejected('content_version', 'legacy context requires its original publisher')
    calendar = _calendar(start_date, retained)
    start_date = calendar.get('start_date')
    days = [dict(day_index=i) for i in range(1, day_count+1)]
    if start_date is not None:
        dates = calendar_dates(date.fromisoformat(start_date), day_count)
        days = [dict(day_index=i+1, date=d) for i, d in enumerate(dates)]
    current = _protected_items(snapshot.fields, fixed_days, day_count, retained)
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
