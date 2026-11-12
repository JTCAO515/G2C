"""One source-selected ordinal replacement, never a whole-plan regeneration."""
from copy import deepcopy
from hashlib import sha256
import json

from cj_manual_edit.scoped import Request
from cj_trip.domain import Conflict, Proposal, packed
from cj_trip.manual import ManualEdit
from cj_trip.lio_history import TripHead, edit_action_id
from cj_trip.structured_v3 import validate_document
from cj_feasibility.trip_time_v3 import evaluate

BASIS = 'lio-calendar-edit.1'
VERSION = 'TRIP-calendar-edit.1'  # Internal command, not a public HTTP ingress.


def replacement(trip, request, edit):
    expected = (trip.trip_id, trip.version, sha256(trip.content).hexdigest())
    if ((request.trip_id, request.expected_version, request.original_hash) != expected
            or (edit.trip_id, edit.expected_version, edit.original_hash) != expected
            or request.request_id != edit.request_id):
        raise Conflict('original calendar selection changed')
    if (request.kind != 'items' or len(request.selected) != 1 or edit.title is not None
            or edit.order is not None or len(edit.changes) != 1
            or edit.changes[0][:2] != (request.selected[0], 'text')):
        raise Conflict('one selected text replacement required')
    value = json.loads(edit.changes[0][2])
    if type(value) is not str or not value.strip() or value not in request.text:
        raise Conflict('replacement must come from the original request')
    before = json.loads(trip.content)
    validate_document(before)
    after = deepcopy(before)
    selected = [i for i in after['items'] if i['id'] == request.selected[0]]
    if len(selected) != 1 or selected[0]['fixed'] != {'state': 'known', 'value': False}:
        raise Conflict('selected item unavailable, fixed or protection unknown')
    item = selected[0]
    item.update(text=value, verification='pending', evidence=[], source_category='unknown', source_refs=[])
    # Keep all original source records. Unselected items, schedules, calendar,
    # empty days, fixed flags and source bytes remain exactly unchanged.
    if after['calendar']['state'] == 'dated':
        for check in after['date_checks']:
            if check['kind'] == 'day_opening':
                check.update(state='unknown', reason='selected_place_changed', evidence_refs=[])
    validate_document(after)
    return after


def publish(publisher, binding, original, current, request_raw, edit_raw, capture, limits, before_publish):
    publisher.source.check(binding, capture)
    context = publisher.source.contexts[binding]
    if current is None or current != original or context is None or before_publish is None:
        raise Conflict('original calendar edit context required')
    request = Request.parse(request_raw)
    edit = ManualEdit._parse(edit_raw, VERSION)
    if request.text != json.loads(original.raw)['text']:
        raise Conflict('calendar request differs from original MESSAGE')
    expected = TripHead.from_trip(context.trip)
    publisher.require_lio(binding, original, expected)
    held = publisher.source.calendar_active.get()[1]
    reference = json.loads(capture.basis.fixed_bindings)['reference']
    publisher.source._original(held, reference)
    if tuple(held.selected_item_ids(reference, request.raw)) != request.selected:
        raise Conflict('selection differs from protected original compiler result')
    document = replacement(context.trip, request, edit)
    if document['calendar']['state'] == 'dated':
        document['date_checks'] = publisher.date_reader.read(binding, capture, document)
    content = packed(document)
    if any(c.code in ('ITEM_TIME_REVERSED', 'ITEM_RELATIVE_REVERSED') for c in evaluate(content).checks):
        raise Conflict('calendar edit interval conflict')
    from .lio_calendar import needs_projection
    candidate, _ = needs_projection(document, capture, {}, context, selected_ids=request.selected, limits=limits)
    proposal = Proposal('lio-calendar-edit-'+binding.run_id, context.trip.trip_id, context.trip.version,
                        BASIS, int(publisher.clock())+300, content)
    return publisher._save(binding, original, expected, capture, candidate, proposal,
                           edit_action_id(binding.run_id), before_publish)
