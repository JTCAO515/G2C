"""Pure protected-base projection controls; native writer proof is separate PG."""
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from cj_draft.lio_rich import protected_records
from cj_needs.domain import Command, Revision, Snapshot
from cj_trip.domain import Trip, packed
from cj_trip.structured import SourceRejected
from test_rich_calendar_source import source_harness


def fixture_source(monkeypatch):
    h = source_harness(monkeypatch)
    snapshot, _ = h.capture.records()
    command = Command(packed(dict(action_id='original-fixed-source', needs_id=snapshot.needs_id,
        expected_version=0, changes=snapshot.fields, source=dict(kind='manual', text='Synthetic original fixed meetup'))))
    revision = Revision(snapshot.needs_id, snapshot.version, command.action_id, command.raw, snapshot.content)
    h.capture.needs.records = lambda: (snapshot, (revision,))
    return h


def test_original_fixed_base_is_code_projected_with_unknowns_and_digest_intact(monkeypatch):
    h = fixture_source(monkeypatch)
    records = protected_records(h.capture, None, [])
    snapshot, _ = h.capture.records()
    fixed, = snapshot.fields['fixed_items']
    record, = records
    assert (record['provider'], record['kind']) == ('needs', 'fixed_item')
    assert record['reference'] == f'{snapshot.needs_id}:{snapshot.version}:{fixed["item_id"]}'
    assert record['sha256'] == sha256(packed(record['payload'])).hexdigest()
    item = record['payload']['item']
    assert item['id'] == fixed['item_id'] and item['text'] == fixed['description']
    assert item['fixed'] == fixed['locked']
    first, last = h.capture.basis.day_indices()[fixed['item_id']]
    for edge, day in (('start', first), ('end', last)):
        assert item['schedule'][edge] == dict(day_index=day, time=fixed[edge]['time'],
            timezone=fixed[edge]['timezone'], utc_offset={'state': 'unknown'})
    assert item['source_refs'] == [] and item['verification'] == 'pending'


@pytest.mark.parametrize('version', ['structured.1', 'structured.2'])
def test_legacy_context_requires_its_real_calendar_bridge(monkeypatch, version):
    h = fixture_source(monkeypatch)
    current = SimpleNamespace(trip=SimpleNamespace(content=packed({'content_version': version})))
    with pytest.raises(SourceRejected, match='explicit source bridge'):
        protected_records(h.capture, current, [])


def test_retained_base_uses_exact_previous_items_and_source_reference(monkeypatch):
    h = fixture_source(monkeypatch)
    first = protected_records(h.capture, None, [])
    item = first[0]['payload']['item']
    snapshot, _ = h.capture.records()
    checks = [dict(kind=k, state='not_checked', day_indices=[1, 2, 3], item_ids=[],
        reason='date_not_set', evidence_refs=[]) for k in ('weather', 'day_opening')]
    content = packed(dict(content_version='structured.3', title='Original', calendar={'state': 'undated'},
        days=[dict(day_index=i) for i in (1, 2, 3)], items=[item], sources=[], date_checks=checks))
    current = SimpleNamespace(trip=Trip('original-trip', 1, content), proposed=snapshot.content)
    records = protected_records(h.capture, current, checks)
    retained, = [row for row in records if row['provider'] == 'trip']
    assert retained['reference'] == 'original-trip:1:'+item['id']
    assert retained['payload']['item'] == json.loads(content)['items'][0]
    assert retained['sha256'] == sha256(packed(retained['payload'])).hexdigest()


@pytest.mark.parametrize('day_index,source_date,conflict', [
    (1, '2026-12-01', False),
    (2, '2026-12-02', False),
    (3, '2026-12-03', False),
    (2, '2026-12-01', True),
    (3, '2026-12-02', True),
])
def test_dated_protected_records_check_the_actual_ordinal_date(monkeypatch, day_index, source_date, conflict):
    h = fixture_source(monkeypatch)
    original, _ = h.capture.records()
    fields = original.fields
    fixed, = fields['fixed_items']
    for edge in ('start', 'end'):
        fixed[edge]['date'] = dict(state='known', value=source_date)
    snapshot = Snapshot(original.needs_id, original.version, packed(fields))
    command = Command(packed(dict(action_id='dated-fixed-source', needs_id=snapshot.needs_id,
        expected_version=0, changes=fields, source=dict(kind='manual', text='Synthetic dated fixed meetup'))))
    revision = Revision(snapshot.needs_id, snapshot.version, command.action_id, command.raw, snapshot.content)
    # Projection-only data: no MESSAGE/source lease or publishing capability.
    capture = SimpleNamespace(records=lambda: (snapshot, (revision,)),
        basis=SimpleNamespace(day_count=3, start_date='2026-12-01',
            day_indices=lambda: {fixed['item_id']: (day_index, day_index)}))
    checks = [dict(kind=k, state='unknown', day_indices=[1, 2, 3], item_ids=[],
                   reason='synthetic date-check input', evidence_refs=[]) for k in ('weather', 'day_opening')]
    before = snapshot.content
    if conflict:
        with pytest.raises(SourceRejected, match='calendar conflicts with an original fixed date'):
            protected_records(capture, None, checks)
    else:
        record, = protected_records(capture, None, checks)
        item = record['payload']['item']
        assert record['reference'] == f'{snapshot.needs_id}:{snapshot.version}:{fixed["item_id"]}'
        assert record['sha256'] == sha256(packed(record['payload'])).hexdigest()
        assert item['id'] == fixed['item_id'] and item['text'] == fixed['description']
        assert item['fixed'] == fixed['locked']
        for edge in ('start', 'end'):
            assert item['schedule'][edge] == dict(day_index=day_index, time=fixed[edge]['time'],
                timezone=fixed[edge]['timezone'], utc_offset={'state': 'unknown'})
    assert snapshot.content == before
