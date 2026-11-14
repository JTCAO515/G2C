"""Synthetic destination windows; no city lookup, provider, database or key."""
from copy import deepcopy
from datetime import date, timedelta
import json
from types import SimpleNamespace

import pytest

from cj_agent.draft import DraftRejected
from cj_draft.lio_plan import (COMPACT_INITIAL_PLAN, LIO_REPLAN_DELTA_V3,
                               SOURCE_WINDOW_POLICY, LioPlanPublisher, LioSourceWindowPublisher)
from cj_needs.domain import Command, Revision, Snapshot
from cj_run.core import Binding
from cj_trip.domain import Proposal, Trip, packed
from cj_trip.lio_history import PLAN_BASIS
from cj_trip.structured import SourceRejected


CITIES = [('chengdu', '成都', 3), ('xian', '西安', 4), ('shanghai', '上海', 2),
          ('hangzhou', '杭州', 3), ('chongqing', '重庆', 3), ('shenzhen', '深圳', 2)]
FIRST = date(2026, 11, 12)
BINDING = Binding('synthetic-scope', 'synthetic-chat', 'synthetic-generation',
                  'synthetic-message', 'synthetic-run', 1)


def known(value):
    return {'state': 'known', 'value': value}


def source(city='成都', days=3, *, first=FIRST, fixed_day=None, fixed_time=True, zone='Asia/Shanghai',
           arrival_clock='00:00', departure_clock='23:59', meeting=('09:00', '10:00')):
    def event(day, clock):
        return dict(date=known(day.isoformat()), time=known(clock) if fixed_time else {'state': 'unknown'},
                    timezone=known(zone), place={'state': 'unknown'})

    fields = dict(destination_timezone=known(zone), arrival=event(first, arrival_clock),
                  departure=event(first + timedelta(days=days - 1), departure_clock),
                  fixed_items=[dict(item_id='meeting', kind='appointment', description=city + '合成酒店集合',
                                    applies_to=['self'], locked=known(True), booking_status={'state': 'unknown'},
                                    start=event(fixed_day or first, meeting[0]), end=event(fixed_day or first, meeting[1]))])
    fields['arrival']['place'] = known(city)
    command = Command(packed(dict(action_id='source', needs_id='need', expected_version=0,
                                  changes=fields, source=dict(kind='manual', text='Synthetic declared trip window'))))
    snapshot = Snapshot('need', 1, packed(fields))
    revision = Revision('need', 1, command.action_id, command.raw, snapshot.content)
    return SimpleNamespace(binding=BINDING, records=lambda: (snapshot, (revision,)))


def publisher(kind=LioSourceWindowPublisher, context=None):
    result = kind.__new__(kind)
    result.source = SimpleNamespace(contexts={BINDING: context})
    result.draft_guidance = ''
    return result


def plan(city='成都', days=3, *, first=FIRST, zone='Asia/Shanghai', language='zh'):
    return dict(version=COMPACT_INITIAL_PLAN, title=city,
                items=[dict(id=f'stop-{i}', text=city + ('合成活动' if language == 'zh' else ' synthetic visit'),
                            date=(first + timedelta(days=i)).isoformat(), start_time='14:00', end_time='16:00',
                            timezone=zone) for i in range(days)],
                proposed_subjects={f'stop-{i}': ['self'] for i in range(days)})


def save(pub, capture, content, candidate):
    proposal = Proposal('proposal', 'trip', 0, PLAN_BASIS, 2000000000, content)
    return pub._save(BINDING, None, None, capture, candidate, proposal, 'save', None)


@pytest.fixture
def original_save(monkeypatch):
    calls = []

    def admitted(self, *args):
        calls.append(args)
        return 'original-save-path'

    monkeypatch.setattr(LioPlanPublisher, '_save', admitted)
    return calls


@pytest.mark.parametrize(('slug', 'city', 'days'), CITIES)
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_each_city_keeps_fixed_source_and_uses_original_save(slug, city, days, language, original_save):
    capture = source(city, days)
    pub = publisher()
    content, candidate, report = pub.build_plan(packed(plan(city, days, language=language)), capture)
    document = json.loads(content)
    fixed = document['items'][0]
    assert fixed['id'] == 'meeting' and fixed['text'] == city + '合成酒店集合'
    assert fixed['fixed'] == known(True) and fixed['source_category'] == 'user_provided'
    assert [item['schedule']['start']['date']['value'] for item in document['items'][1:]] == [
        (FIRST + timedelta(days=i)).isoformat() for i in range(days)]
    assert all(item['source_refs'] == [] and item['verification'] == 'pending' for item in document['items'])
    assert report.status == 'UNKNOWN'  # Planned slots are not verified bookings or overall feasibility.
    assert save(pub, capture, content, candidate) == 'original-save-path' and len(original_save) == 1
    messages = pub.model_messages(BINDING, 'synthetic request', capture, [])
    assert json.loads(messages[-1]['content'])['version'] == 'TRIP-source-input.2'
    assert SOURCE_WINDOW_POLICY in pub.system


@pytest.mark.parametrize(('day', 'zone'), [('2026-11-11', 'Asia/Shanghai'),
                                         ('2026-11-15', 'Asia/Shanghai'),
                                         ('2026-11-13', 'Asia/Tokyo')])
def test_new_suggestions_cannot_escape_confirmed_window(day, zone, original_save):
    capture = source()
    pub = publisher()
    value = plan(days=1)
    value['items'][0].update(date=day, timezone=zone)
    content, candidate, _ = pub.build_plan(packed(value), capture)
    with pytest.raises(DraftRejected, match='formal Needs draft rejected') as failure:
        save(pub, capture, content, candidate)
    assert isinstance(failure.value.__cause__, SourceRejected)
    assert original_save == []


@pytest.mark.parametrize('missing', ['arrival', 'departure', 'destination_timezone'])
def test_missing_source_parameter_does_not_reach_save(missing, original_save):
    complete = source()
    pub = publisher()
    content, candidate, _ = pub.build_plan(packed(plan()), complete)
    snapshot, revisions = complete.records()
    fields = deepcopy(snapshot.fields)
    del fields[missing]
    capture = SimpleNamespace(records=lambda: (SimpleNamespace(fields=fields), revisions))
    with pytest.raises(DraftRejected, match='formal Needs draft rejected'):
        save(pub, capture, content, candidate)
    assert original_save == []


def test_unknown_fixed_clocks_are_preserved_and_confirmed_other_zone_is_not_guessed(original_save):
    capture = source('乌鲁木齐', fixed_time=False, zone='Asia/Urumqi')
    pub = publisher()
    content, candidate, _ = pub.build_plan(packed(plan('乌鲁木齐', zone='Asia/Urumqi')), capture)
    fixed = json.loads(content)['items'][0]
    assert fixed['schedule']['start']['time'] == fixed['schedule']['end']['time'] == {'state': 'unknown'}
    assert fixed['schedule']['start']['utc_offset'] == {'state': 'unknown'}
    assert save(pub, capture, content, candidate) == 'original-save-path'


@pytest.mark.parametrize('edge', ['arrival', 'departure'])
def test_known_arrival_or_departure_clock_bounds_cannot_be_ignored(edge, original_save):
    capture = (source(arrival_clock='19:00', meeting=('20:00', '21:00')) if edge == 'arrival'
               else source(departure_clock='09:00'))
    pub = publisher()
    content, candidate, _ = pub.build_plan(packed(plan()), capture)
    with pytest.raises(DraftRejected, match='formal Needs draft rejected'):
        save(pub, capture, content, candidate)
    assert original_save == []


def test_replan_preserves_current_items_and_refuses_silently_moving_them(original_save):
    capture = source('重庆')
    pub = publisher()
    content, candidate, _ = pub.build_plan(packed(plan('重庆')), capture)
    trip = Trip('trip', 1, content)
    pub.source.contexts[BINDING] = SimpleNamespace(trip=trip, proposed=candidate.content)
    delta = packed(dict(version=LIO_REPLAN_DELTA_V3, items=[], proposed_subjects={}))
    same, saved_candidate, _ = pub.build_plan(delta, capture)
    assert same == content and save(pub, capture, same, saved_candidate) == 'original-save-path'
    moved = source('重庆', first=FIRST + timedelta(days=2), fixed_day=FIRST)
    with pytest.raises(DraftRejected, match='formal Needs draft rejected'):
        save(pub, moved, same, saved_candidate)
    assert len(original_save) == 1


def test_legacy_publisher_remains_a_separate_explicit_lane(original_save):
    capture = source()
    legacy = publisher(LioPlanPublisher)
    value = plan(days=1)
    value['items'][0].update(date='2026-11-20', timezone='Asia/Tokyo')
    content, candidate, _ = legacy.build_plan(packed(value), capture)
    assert save(legacy, capture, content, candidate) == 'original-save-path'
    assert len(original_save) == 1
