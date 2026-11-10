import json
from types import SimpleNamespace

import pytest

from cj_draft.lio_plan import LioPlanPublisher
from cj_draft.needs_context import ContextPublisher
from cj_needs.domain import Command, Revision, Snapshot
from cj_trip.domain import packed
from cj_trip.needs_plan import MODEL_VERSION
from cj_trip.structured import SourceRejected


def known(value):
    return {'state': 'known', 'value': value}


def stop(item_id, start, end):
    def event(clock):
        return {'date': known('2026-11-12'), 'time': clock,
                'timezone': known('Asia/Shanghai'), 'utc_offset': {'state': 'unknown'}}

    return {'id': item_id, 'fixed': {'state': 'unknown'},
            'schedule': {'start': event(start), 'end': event(end)}}


def build(monkeypatch, items, *, fixed=(), adopted=()):
    candidate, report = object(), object()
    capture = SimpleNamespace(binding='original', records=lambda: (
        SimpleNamespace(fields={'fixed_items': [{'item_id': item['id']} for item in fixed]}), ()))
    current = SimpleNamespace(trip=SimpleNamespace(content=packed({'items': adopted}))) if adopted else None
    publisher = LioPlanPublisher.__new__(LioPlanPublisher)
    publisher.source = SimpleNamespace(contexts={'original': current})
    monkeypatch.setattr(ContextPublisher, 'build_plan', lambda *_: (
        packed({'items': items}), candidate, report))
    raw, saved_candidate, saved_report = publisher.build_plan(b'plan', capture)
    assert (saved_candidate, saved_report) == (candidate, report)
    return json.loads(raw)['items']


def test_lio_time_gate_preserves_declared_and_adopted_items(monkeypatch):
    unknown = {'state': 'unknown'}
    declared = dict(stop('fixed', known('09:00'), known('10:00')), fixed=known(True))
    adopted = dict(stop('old', unknown, unknown), fixed=known(False))
    suggestion = stop('new', known('14:00'), known('15:00'))
    assert build(monkeypatch, [declared, adopted, suggestion], fixed=(declared,), adopted=(adopted,)) == [
        declared, adopted, dict(suggestion, fixed=known(False))]


@pytest.mark.parametrize(('edge', 'field', 'value'), [
    ('start', 'time', {'state': 'unknown'}),
    ('end', 'time', known('14:00:00')),
    ('end', 'date', known('2026-11-13')),
    ('end', 'timezone', known('Asia/Tokyo')),
])
def test_lio_time_gate_rejects_incomplete_or_invalid_new_intervals(monkeypatch, edge, field, value):
    suggestion = stop('new', known('14:00'), known('15:00'))
    suggestion['schedule'][edge][field] = value
    with pytest.raises(SourceRejected, match='same-day planned interval'):
        build(monkeypatch, [suggestion])


def test_lio_retains_only_verbatim_fixed_source():
    description = 'The hotel meetup from 9 to 10 a.m. on the first day is fixed'
    model_stop = dict(stop('fixed', known('09:00'), known('10:00')), text=description, fixed=known(True),
                      verification='pending', evidence=[], source_category='user_provided', source_refs=[])
    schedule = {edge: {key: event[key] for key in ('date', 'time', 'timezone')} | {'place': {'state': 'unknown'}}
                for edge, event in model_stop['schedule'].items()}
    fields = {'fixed_items': [dict(item_id='fixed', kind='appointment', description=description, applies_to=['self'],
                                   locked=known(True), booking_status={'state': 'unknown'}, **schedule)]}
    command = Command(packed(dict(action_id='declare', needs_id='need', expected_version=0, changes=fields,
                                  source=dict(kind='manual', text=description))))
    snapshot = Snapshot('need', 1, packed(fields))
    revision = Revision('need', 1, command.action_id, command.raw, snapshot.content)
    capture = SimpleNamespace(binding='original', records=lambda: (snapshot, (revision,)))
    publisher = LioPlanPublisher.__new__(LioPlanPublisher)
    publisher.source = SimpleNamespace(contexts={'original': None})

    def draft(item):
        return packed(dict(version=MODEL_VERSION, title='Beijing', items=[item], proposed_subjects={}))

    raw, _, _ = publisher.build_plan(draft(model_stop), capture)
    assert json.loads(raw)['items'] == [model_stop]
    for invalid in (dict(model_stop, source_category='unknown'), dict(model_stop, text='Hotel meetup')):
        with pytest.raises(SourceRejected, match='source association'):
            publisher.build_plan(draft(invalid), capture)
