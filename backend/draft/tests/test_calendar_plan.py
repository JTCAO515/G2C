from copy import deepcopy
import json
from pathlib import Path

import pytest

from cj_needs.domain import Snapshot
from cj_trip.domain import packed
from cj_draft.calendar_plan import compose, FIRST_PLAN, REPLAN_DELTA

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())


def snapshot():
    return Snapshot('needs-demo', 1, packed(FIXTURES['needs_basis']['fields']))


def model():
    return dict(version=FIRST_PLAN, title='成都三日', items=[dict(id='museum', text='成都博物馆',
        day_index=2, start_time='13:00', end_time='15:00', timezone='Asia/Shanghai')],
        proposed_subjects={'museum': ['self']})


def build(value, **options):
    return compose(packed(value), snapshot(), {'hotel-meetup': (1, 1)}, 3, **options)


def test_city_days_with_no_date_or_party_size_has_explicit_undated_content():
    before = snapshot().content
    raw, subjects = build(model())
    document = json.loads(raw)
    assert document['calendar'] == {'state': 'undated'}
    assert document['days'] == [{'day_index': 1}, {'day_index': 2}, {'day_index': 3}]
    assert all(c['state'] == 'not_checked' for c in document['date_checks'])
    assert document['items'][0]['id'] == 'hotel-meetup'
    assert document['items'][0]['fixed'] == {'state': 'known', 'value': True}
    assert document['items'][0]['schedule']['start']['time']['value'] == '09:00'
    assert 'party_size' not in snapshot().fields
    assert snapshot().content == before and subjects == {'museum': ['self']}
    assert b'2026-' not in raw and all('date' not in e for i in document['items'] for e in i['schedule'].values())


@pytest.mark.parametrize('change', [
    lambda v: v['items'][0].update(id='hotel-meetup'),
    lambda v: v['items'][0].update(day_index=0),
    lambda v: v['items'][0].update(day_index=4),
    lambda v: v['items'][0].update(date='2026-11-12'),
    lambda v: v['items'][0].update(timezone='Europe/Paris'),
    lambda v: v['items'][0].update(start_time='16:00'),
    lambda v: v.update(proposed_subjects={}),
])
def test_model_cannot_override_fixed_source_days_zone_or_subject_scope(change):
    value = model()
    change(value)
    with pytest.raises(ValueError):
        build(value)


def test_fixed_mapping_missing_is_not_a_default_first_day():
    with pytest.raises(ValueError):
        compose(packed(model()), snapshot(), {}, 3)


def test_replan_server_retains_every_old_item_title_sources_and_mode():
    first, _ = build(model())
    retained = json.loads(first)
    delta = dict(version=REPLAN_DELTA, items=[dict(id='park', text='公园散步', day_index=3,
        start_time='10:00', end_time='11:00', timezone='Asia/Shanghai')], proposed_subjects={'park': ['self']})
    result, _ = build(delta, retained=retained)
    actual = json.loads(result)
    assert actual['items'][:len(retained['items'])] == retained['items']
    assert actual['title'] == retained['title'] and actual['sources'] == retained['sources']
    assert actual['calendar'] == {'state': 'undated'}
    with pytest.raises(ValueError):
        build(delta, retained=retained, start_date='2026-12-01')
