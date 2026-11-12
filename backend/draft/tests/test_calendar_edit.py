from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from cj_draft.calendar_edit import replacement, VERSION
from cj_manual_edit.scoped import Request
from cj_trip.calendar_history import CalendarUndo, protect_fixed
from cj_trip.domain import Conflict, Trip, packed
from cj_trip.lio_history import Undo
from cj_trip.manual import ManualEdit

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT/'contracts/trip/structured-examples.3.json').read_bytes())


def inputs():
    document = deepcopy(FIXTURE['base'])
    document['items'][0]['fixed'] = dict(state='known', value=False)
    trip = Trip('calendar-edit', 1, packed(document))
    base = dict(request_id='calendar-edit-request', trip_id=trip.trip_id, expected_version=trip.version,
                original_hash=sha256(trip.content).hexdigest())
    request = dict(version='TRIP-scoped-request.1', **base, text='Replace the museum with Renmin Park 人民公园.',
                   language='en', selection=dict(kind='items', item_ids=[document['items'][0]['id']]))
    edit = dict(version=VERSION, **base, title=None, order=None,
                changes=[dict(item_id=document['items'][0]['id'], field='text', value='Renmin Park 人民公园')])
    return trip, request, edit


def test_exact_undated_replacement_retains_schedule_calendar_sources_and_input_bytes():
    trip, request, edit = inputs()
    before = json.loads(trip.content)
    after = replacement(trip, Request.parse(packed(request)), ManualEdit._parse(packed(edit), VERSION))
    expected = deepcopy(before)
    expected['items'][0].update(text=edit['changes'][0]['value'], verification='pending', evidence=[],
                                source_category='unknown', source_refs=[])
    assert after == expected
    assert json.loads(trip.content) == before


@pytest.mark.parametrize('change', [
    lambda r,e: e.update(title='expanded'),
    lambda r,e: e.update(order=[]),
    lambda r,e: e['changes'][0].update(field='fixed', value=False),
    lambda r,e: e['changes'][0].update(value='model invented elsewhere'),
    lambda r,e: e.update(original_hash='0'*64),
    lambda r,e: r['selection']['item_ids'].append('outside'),
])
def test_edit_cannot_expand_original_selected_text(change):
    trip, request, edit = inputs()
    change(request, edit)
    with pytest.raises((Conflict, ValueError)):
        replacement(trip, Request.parse(packed(request)), ManualEdit._parse(packed(edit), VERSION))


def test_fixed_and_unknown_protection_are_not_edit_authority():
    trip, request, edit = inputs()
    for fixed in (dict(state='known', value=True), dict(state='unknown')):
        document = json.loads(trip.content)
        document['items'][0]['fixed'] = fixed
        other = Trip(trip.trip_id, trip.version, packed(document))
        for value in (request, edit): value['original_hash'] = sha256(other.content).hexdigest()
        with pytest.raises(Conflict):
            replacement(other, Request.parse(packed(request)), ManualEdit._parse(packed(edit), VERSION))


def test_calendar_undo_is_new_version_and_protects_whole_fixed_item():
    trip, _, _ = inputs()
    value = dict(version='TRIP-lio-undo.2', action_id='undo-calendar', trip_id=trip.trip_id,
                 expected_version=2, original_hash=sha256(trip.content).hexdigest())
    assert CalendarUndo.parse(packed(value)).raw == packed(value)
    with pytest.raises(ValueError): Undo.parse(packed(value))
    with pytest.raises(ValueError): CalendarUndo.parse(packed(dict(value, version='TRIP-lio-undo.1')))
    fixed = deepcopy(FIXTURE['base'])
    current = Trip('trip', 2, packed(fixed))
    previous = Trip('trip', 1, packed(FIXTURE['base']))
    protect_fixed(current, previous)
    fixed['items'][0]['schedule']['start']['time'] = dict(state='known', value='08:15')
    with pytest.raises(Conflict): protect_fixed(Trip('trip', 2, packed(fixed)), previous)


def test_calendar_edit_keeps_the_independent_output_horizon_check_and_limits():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from cj_needs.domain import Command, Revision, Snapshot
    from cj_draft.calendar_plan import compose, FIRST_PLAN
    from cj_draft.lio_calendar import needs_projection
    from cj_feasibility.solver import Limits
    fields = deepcopy(json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())['needs_basis']['fields'])
    fields['fixed_items'][0]['locked'] = dict(state='known', value=False)
    for edge in ('start', 'end'):
        fields['fixed_items'][0][edge]['date'] = dict(state='known', value='2026-12-01')
    command = Command(packed(dict(action_id='source', needs_id='visit', expected_version=0,
        source=dict(kind='manual', text='explicit synthetic booked date'), changes=fields)))
    snapshot = Snapshot('visit', 1, packed(fields))
    revisions = (Revision('visit', 1, command.action_id, command.raw, snapshot.content),)
    capture = SimpleNamespace(records=lambda: (snapshot, revisions), raw=packed(dict(snapshot='same')))
    current = SimpleNamespace(proposed=snapshot.content, needs_source=capture.raw)
    content, _ = compose(packed(dict(version=FIRST_PLAN, title='three days', items=[], proposed_subjects={})),
        snapshot, {'hotel-meetup': (1,1)}, 3)
    document = json.loads(content)
    document['items'][0]['text'] = 'Original user replacement'
    limits = Limits(datetime(2026,11,1,tzinfo=timezone.utc), 86400, 1, 10_000_000, 60,120,128,.05,.05,100)
    with pytest.raises(Conflict, match='independent output invariants rejected'):
        needs_projection(document, capture, {}, current, selected_ids={'hotel-meetup'}, limits=limits)
    limits = Limits(datetime(2026,12,1,tzinfo=timezone.utc), 3*86400, 1, 10_000_000,60,120,128,.05,.05,100)
    candidate, report = needs_projection(document, capture, {}, current,
                                          selected_ids={'hotel-meetup'}, limits=limits)
    assert json.loads(candidate.content)['fixed_items'][0]['description'] == 'Original user replacement'
    assert any(c.code == 'PROTECTED_SCOPE_UNCHANGED' and c.status == 'PASS' for c in report.checks)
