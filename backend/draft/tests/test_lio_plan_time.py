import json
from types import SimpleNamespace

import pytest

from cj_draft.lio_plan import LioPlanPublisher
from cj_draft.needs_context import ContextPublisher
from cj_trip.domain import packed
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
