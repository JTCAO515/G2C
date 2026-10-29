"""Model text -> canonical TRIP document; untrusted input is rejected, never repaired."""
import json
import sys

import pytest

from cj_agent.draft import DraftRejected, document_from_model, proposal_id_for, trip_scope_for
from cj_trip.domain import identifier


def test_model_json_becomes_pending_items_without_evidence():
    raw = 'Here you go:\n{"title": " 北京三日游 ", "items": ["第一天：故宫", "第二天：长城"]}\nEnjoy'
    doc = json.loads(document_from_model(raw))
    assert doc['title'] == '北京三日游'
    assert doc['items'] == [
        {'id': 'item-1', 'text': '第一天：故宫', 'verification': 'pending', 'evidence': []},
        {'id': 'item-2', 'text': '第二天：长城', 'verification': 'pending', 'evidence': []}]


@pytest.mark.parametrize('raw', [
    'no json at all', '{"title": "x"}', '{"title": "", "items": ["a"]}', '{"title": "x", "items": []}',
    '{"title": "x", "items": ["a", 3]}', '{"title": "x", "items": ["a"], "verified": true}',
    '{"title": "x", "items": ["' + 'y' * 501 + '"]}', '{"title": "x", "items": ' + json.dumps(['a'] * 21) + '}',
    '{"title": "x", "items": ["a"]'])
def test_invalid_model_output_is_rejected(raw):
    with pytest.raises(DraftRejected):
        document_from_model(raw)


def test_identifiers_are_valid_trip_identifiers():
    run_id = '3f1c2b9e-0d4a-4c61-9d1e-8a7b6c5d4e3f'
    assert identifier(proposal_id_for(run_id)) == 'p-' + run_id
    scope = trip_scope_for('local:https://local.g2c.invalid:alice')
    assert identifier(scope) == scope and scope != trip_scope_for('local:https://local.g2c.invalid:bob')


@pytest.mark.parametrize('field', ['date', 'time', 'start', 'end', 'timezone'])
@pytest.mark.parametrize('location', ['document', 'item'])
def test_structured_time_rejects_entire_draft(field, location):
    value = {'title': 'Beijing', 'items': ['Keep this text']}
    if location == 'document':
        value[field] = '2026-11-01T09:00:00+08:00'
    else:
        value['items'].append({'text': 'Forbidden City', field: '2026-11-01T09:00:00+08:00'})
    with pytest.raises(DraftRejected):
        document_from_model(json.dumps(value))


def test_object_item_without_time_is_not_silently_flattened():
    with pytest.raises(DraftRejected):
        document_from_model(json.dumps({'title': 'Beijing', 'items': ['Keep this text', {'text': 'Temple'}]}))


def test_time_descriptions_remain_unverified_text_without_time_validation():
    items = ['09:00–11:00 故宫', '10:00–12:00 Temple of Heaven',
             '18:00–09:00 倒序时间待核实', 'Date TBD / 日期待定']
    doc = json.loads(document_from_model(json.dumps({'title': 'Beijing', 'items': items})))
    assert doc == {'title': 'Beijing', 'items': [
        {'id': f'item-{n}', 'text': text, 'verification': 'pending', 'evidence': []}
        for n, text in enumerate(items, 1)]}


@pytest.mark.parametrize('raw', [
    '{"title":"discarded","title":"replacement","items":["a"]}',
    '{"title":"x","items":[],"items":["a"]}',
    '{"title":"x","items":["a"],"it\\u0065ms":["b"]}',
    '{"title":"x","items":["\\ud800"]}',
    '{"title":"x","items":' + '[' * (sys.getrecursionlimit() + 10) + '0' + ']' * (sys.getrecursionlimit() + 10) + '}',
], ids=['duplicate-title', 'overwritten-items', 'escaped-duplicate', 'unpaired-surrogate', 'nesting-limit'])
def test_ambiguous_or_unencodable_model_json_is_rejected_as_a_whole(raw):
    with pytest.raises(DraftRejected):
        document_from_model(raw)
