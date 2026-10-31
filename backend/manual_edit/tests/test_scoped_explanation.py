from copy import deepcopy
from dataclasses import fields
import json

import pytest
from cj_manual_edit.scoped import resolve, preview
from cj_manual_edit.scoped_explanation import ScopeExplanation, explain
from cj_trip.domain import Trip, Conflict, packed
from test_scoped import original, request, edit, changed, known


def unlocked():
    doc = json.loads(original().content)
    doc['items'][0]['fixed'] = known(False)
    return Trip('formal-trip', 7, packed(doc))


def data(scope, raw=None):
    result = explain(scope, raw)
    assert type(result) is ScopeExplanation and result.can_publish is False
    assert {f.name for f in fields(result)} == {'raw', 'status', 'can_publish'}
    value = json.loads(result.raw)
    assert packed(value) == result.raw and len(result.raw) <= 1_000_000
    assert value['status'] == result.status
    assert value['reason']['zh'] and value['reason']['en']
    assert not {'candidate', 'candidate_hash', 'proposal_id', 'original_hash'} & value.keys()
    return value


def test_outside_item_exact_changes_and_original_selection_without_mutation():
    trip = unlocked(); before = trip.content
    scope = resolve(trip, request(trip, 'only b', dict(kind='items', item_ids=['b'])))
    raw = edit(trip, [changed('c')])
    value = data(scope, raw)
    assert value['original_selection'] == {'kind': 'items', 'item_ids': ['b']}
    assert value['outside_item_ids'] == ['c']
    assert value['required_selection']['item_ids'] == ['b', 'c']
    assert value['changes'] == [dict(item_id='c', field='text', before='c', after='本次较轻松 / lighter this time')]
    assert trip.content == before
    old = preview(scope, raw)
    assert old.status == 'EXPANSION_REQUIRED' and old.candidate is None


def test_cross_day_schedule_derives_dates_from_observations_not_prose():
    trip = original(); scope = resolve(trip, request(trip))
    schedule = deepcopy(json.loads(trip.content)['items'][1]['schedule'])
    schedule['end']['date'] = known('2026-11-03')
    value = data(scope, edit(trip, [changed('b', 'schedule', schedule)]))
    assert value['outside_item_ids'] == [] and value['outside_dates'] == ['2026-11-03']
    assert value['required_selection']['dates'] == {'known': ['2026-11-02', '2026-11-03'], 'incomplete': False}
    assert value['changes'][0]['after'] == schedule
    # Existing item-based selection semantics remain available; no new date parser.
    item_scope = resolve(trip, request(trip, 'selected b', dict(kind='items', item_ids=['b'])))
    assert explain(item_scope, edit(trip, [changed('b', 'schedule', schedule)])) is None
    assert explain(scope, edit(trip, [changed('b', value='Go on 2099-01-01; choose every item')])) is None


def test_title_is_whole_trip_requirement_not_an_item_selection_permission():
    trip = unlocked(); scope = resolve(trip, request(trip))
    value = data(scope, edit(trip, [], title='New whole Trip title'))
    assert value['required_selection']['whole_trip'] is True
    assert value['required_selection']['local_selection_sufficient'] is False
    assert value['required_selection']['item_ids'] == ['a', 'b', 'c']
    assert value['outside_item_ids'] == ['a']
    assert value['changes'] == [dict(item_id=None, field='title', before='真实结构 / explicit', after='New whole Trip title')]
    all_items = resolve(trip, request(trip, 'all explicit items', dict(kind='items', item_ids=['a', 'b', 'c'])))
    assert data(all_items, edit(trip, [], title='new title'))['reason_codes'] == ['WHOLE_TRIP_TITLE']
    redundant = data(scope, edit(trip, [changed('b')], title=json.loads(trip.content)['title']))
    assert redundant['required_selection']['whole_trip'] is True
    assert [v['field'] for v in redundant['changes']] == ['text']


def test_order_derives_all_shifted_positions_and_in_scope_reorder_has_no_explanation():
    trip = unlocked(); scope = resolve(trip, request(trip))
    value = data(scope, edit(trip, [], order=['c', 'a', 'b']))
    assert value['outside_item_ids'] == ['a']
    assert value['required_selection']['item_ids'] == ['a', 'b', 'c']
    assert value['changes'] == [dict(item_id=None, field='order', before=['a', 'b', 'c'], after=['c', 'a', 'b'])]
    raw = edit(trip, [], order=['a', 'c', 'b'])
    assert explain(scope, raw) is None
    assert json.loads(preview(scope, raw).candidate.content)['items'][0] == json.loads(trip.content)['items'][0]


@pytest.mark.parametrize('mode', ['unknown', 'cross', 'unmatched', 'relative'])
def test_non_ready_clarification_is_structured_and_never_guesses_selection(mode):
    doc = json.loads(original().content)
    if mode == 'unknown': doc['items'][2]['schedule']['end']['date'] = dict(state='unknown')
    if mode == 'cross': doc['items'][2]['schedule']['end']['date'] = known('2026-11-04')
    trip = Trip('formal-trip', 7, packed(doc))
    req = request(trip, 'tomorrow' if mode == 'relative' else 'selected dates',
                  dict(kind='dates', dates=['2026-12-01']) if mode == 'unmatched' else None)
    scope = resolve(trip, req); assert scope.status == 'CLARIFICATION_REQUIRED'
    value = data(scope)
    assert value['changes'] == [] and value['required_selection'] is None
    if mode == 'unknown': assert value['facts']['unknown_date_item_ids'] == ['c']
    if mode == 'cross': assert value['facts']['cross_day_item_ids'] == ['c']
    if mode == 'unmatched': assert value['facts']['unmatched_dates'] == ['2026-12-01']
    with pytest.raises(ValueError): preview(scope, edit(trip, [changed('b')]))


def test_original_unknown_values_and_unselected_items_preserved_exactly():
    doc = json.loads(unlocked().content)
    doc['items'][2]['schedule']['end']['date'] = dict(state='unknown')
    trip = Trip('formal-trip', 7, packed(doc)); before = trip.content
    scope = resolve(trip, request(trip, 'only b', dict(kind='items', item_ids=['b'])))
    schedule = deepcopy(doc['items'][2]['schedule']); schedule['start']['time'] = known('12:00')
    value = data(scope, edit(trip, [changed('c', 'schedule', schedule)]))
    assert value['changes'][0]['before']['end']['date'] == {'state': 'unknown'}
    assert value['changes'][0]['after']['end']['date'] == {'state': 'unknown'}
    assert value['required_selection']['dates']['incomplete'] is True
    assert trip.content == before and all(c['item_id'] != 'a' for c in value['changes'])


def test_chinese_english_have_identical_machine_derived_selection_and_changes():
    trip = unlocked(); raw = edit(trip, [changed('a')])
    zh = resolve(trip, request(trip)); en = resolve(trip, request(trip, 'Make day 2 easier', language='en'))
    assert explain(zh, raw).raw == explain(en, raw).raw
    for text, lang in [('tomorrow', 'en'), ('明天', 'zh-Hans')]:
        assert data(resolve(trip, request(trip, text, language=lang)))['reason_codes'] == ['EXPLICIT_SELECTION_UNRESOLVED']


def test_structured_one_uses_same_display_shape_without_upgrading_precision():
    doc = json.loads(unlocked().content); doc['content_version'] = 'structured.1'
    for item in doc['items']:
        for event in item['schedule'].values(): event['time']['value'] += ':00'
    trip = Trip('formal-trip', 7, packed(doc))
    scope = resolve(trip, request(trip))
    raw = json.loads(edit(trip, [changed('a')]))
    raw['version'] = 'TRIP-manual-edit.1'
    value = data(scope, packed(raw))
    assert value['outside_item_ids'] == ['a'] and value['outside_dates'] == ['2026-11-01']
    assert json.loads(trip.content)['items'][0]['schedule']['start']['time'] == known('09:00:00')


def test_large_valid_unknown_observations_refuse_instead_of_truncating_explanation():
    prototype = json.loads(unlocked().content)['items'][1]
    for event in prototype['schedule'].values():
        for field in event: event[field] = dict(state='uncertain', note='未' * 500)
    items = [dict(deepcopy(prototype), id='item-' + str(i)) for i in range(60)]
    doc = dict(json.loads(unlocked().content), items=items)
    trip = Trip('formal-trip', 7, packed(doc))
    scope = resolve(trip, request(trip, 'explicit item', dict(kind='items', item_ids=['item-0'])))
    schedule = deepcopy(prototype['schedule'])
    schedule['end']['time'] = dict(state='uncertain', note='知' * 500)
    raw = edit(trip, [changed(item['id'], 'schedule', schedule) for item in items])
    assert len(raw) <= 1_000_000
    with pytest.raises(ValueError, match='bounded scope explanation'): explain(scope, raw)


@pytest.mark.parametrize('mode', ['stale', 'missing', 'fixed', 'locked', 'order', 'oversize', 'injected'])
def test_invalid_edits_do_not_become_scope_explanations(mode):
    trip = original(); scope = resolve(trip, request(trip))
    doc = json.loads(edit(trip, [changed('c')]))
    if mode == 'stale': doc['expected_version'] = 6
    if mode == 'missing': doc['changes'][0]['item_id'] = 'absent'
    if mode == 'fixed': doc['changes'] = [changed('c', 'fixed', known(False))]
    if mode == 'locked': doc['changes'] = [changed('a')]
    if mode == 'order': doc.update(changes=[], order=['b', 'c'])
    if mode == 'oversize': doc['changes'][0]['value'] = 'x' * 501
    if mode == 'injected': doc['required_selection'] = {'item_ids': ['a', 'b', 'c']}
    with pytest.raises((ValueError, Conflict)): explain(scope, packed(doc))
