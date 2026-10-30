from copy import deepcopy
from hashlib import sha256
import pytest
import json

from cj_trip.domain import Trip, Conflict, packed
from cj_trip.manual import ManualEdit, prepare, VERSION
from test_structured import document


def setup(fixed=False):
    doc = document()
    doc['items'][0]['fixed'] = {'state': 'known', 'value': fixed}
    doc['items'].append(deepcopy(doc['items'][0]))
    doc['items'][1]['id'] = 'item-2'
    trip = Trip('trip-1', 2, packed(doc))
    request = dict(version=VERSION, request_id='manual-1', trip_id='trip-1', expected_version=2,
                   original_hash=sha256(trip.content).hexdigest(), title=None, changes=[], order=None)
    return trip, request


def test_selected_text_preserves_other_item_and_no_source_upgrade():
    trip, request = setup()
    request['changes'] = [dict(item_id='item-1', field='text', value='用户明确改写 / explicit edit')]
    candidate = prepare(trip, ManualEdit.parse(packed(request)))
    after = json.loads(candidate.content)
    before = json.loads(trip.content)
    assert after['items'][1] == before['items'][1]
    assert after['sources'] == before['sources']
    assert after['items'][0]['verification'] == 'pending'
    assert after['items'][0]['evidence'] == []
    assert candidate.original == trip


@pytest.mark.parametrize('fixed', [True, None])
def test_locked_or_unknown_rejects_content_and_move(fixed):
    trip, request = setup()
    if fixed is None:
        doc = json.loads(trip.content); doc['items'][0]['fixed'] = {'state':'unknown'}
        trip = Trip(trip.trip_id, trip.version, packed(doc)); request['original_hash'] = sha256(trip.content).hexdigest()
    else: trip, request = setup(True)
    request['changes'] = [dict(item_id='item-1', field='text', value='changed')]
    with pytest.raises(Conflict): prepare(trip, ManualEdit.parse(packed(request)))
    request['changes'] = []; request['order'] = ['item-2', 'item-1']
    with pytest.raises(Conflict): prepare(trip, ManualEdit.parse(packed(request)))


def test_unlock_is_explicit_independent_edit_and_stale_original_refused():
    trip, request = setup(True)
    request['changes'] = [dict(item_id='item-1', field='fixed', value={'state':'known','value':False})]
    edit = ManualEdit.parse(packed(request)); result = prepare(trip, edit)
    assert b'"value":false' in result.content
    with pytest.raises(Conflict): prepare(Trip(trip.trip_id, 3, trip.content), edit)
    request['changes'].append(dict(item_id='item-1', field='text', value='incidental edit'))
    with pytest.raises(Conflict): prepare(trip, ManualEdit.parse(packed(request)))


def test_invalid_owner_field_or_noncanonical_input_or_foreign_id_refused():
    trip, request = setup(); request['title'] = '明确标题'
    request['owner'] = 'caller'
    with pytest.raises(ValueError): ManualEdit.parse(packed(request))
    del request['owner']
    with pytest.raises(ValueError): ManualEdit.parse(packed(request) + b' ')
    request['changes'] = [dict(item_id='foreign', field='text', value='changed')]
    with pytest.raises(ValueError): prepare(trip, ManualEdit.parse(packed(request)))


def test_changed_queried_text_does_not_keep_old_source_or_verified_claim():
    import base64
    trip, request = setup()
    doc = json.loads(trip.content)
    text = doc['items'][0]['text']
    snapshot = packed(dict(display_text=text, record=dict(
        source=dict(request_ref='query-1', evidence='synthetic'), query={}, place=dict(name_zh=text))))
    doc['sources'] = [dict(id='source-1', kind='place', reference='query-1', text=text,
        snapshot_utf8_base64=base64.b64encode(snapshot).decode(),
        snapshot_sha256=sha256(snapshot).hexdigest(), evidence_level='synthetic')]
    doc['items'][0].update(source_category='queried', source_refs=['source-1'])
    trip = Trip(trip.trip_id, trip.version, packed(doc))
    request['original_hash'] = sha256(trip.content).hexdigest()
    request['changes'] = [dict(item_id='item-1', field='text', value='用户重新声明')]
    result = prepare(trip, ManualEdit.parse(packed(request)))
    after = json.loads(result.content)
    assert after['sources'] == []
    assert after['items'][0]['source_category'] == 'user_provided'
    assert after['items'][0]['source_refs'] == []
    assert after['items'][1] == doc['items'][1]
    assert json.loads(result.original.content)['sources'] == doc['sources']
