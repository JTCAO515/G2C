from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from cj_trip.domain import packed
from cj_trip.rich_calendar import classify, statutory_exception
from cj_trip.rich_notices import (calendar_notices, date_check_notices, route_notices,
                                  select_notices, venue_notices, winter_outdoor_notice)
from cj_trip.rich_source import capture
from cj_trip.structured import SourceRejected

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = json.loads((ROOT / 'contracts/trip/structured-examples.4.json').read_bytes())
VENUE = json.loads((ROOT / 'knowledge/visitor/entries-v2/venue-conditions.json').read_bytes())[0]


def bound_records(records):
    case = deepcopy(EXAMPLES['cases']['unconfirmed'])
    case['source']['records'] = records
    case['host_expected']['eligible_records'] = deepcopy(records)
    return capture(packed(case['source']), **case['host_expected'])


def record(provider, kind, payload):
    return dict(provider=provider, kind=kind, reference='synthetic-' + kind,
                sha256=sha256(packed(payload)).hexdigest(), payload=payload)


def venue(entry=VENUE, *, visit_date=date(2026, 11, 16), locale='zh', **kwargs):
    payload = dict(entry_id=entry['id'], entry_sha256=sha256(packed(entry)).hexdigest(),
                   checked_on=entry['checked_on'], expires_on=entry['expires_on'],
                   subject_key=entry['subject']['key'], item_ids=['item-1'], amap_ids=['poi-1'])
    # Test the actual dated source eligibility, not a direct RichSource bypass.
    case = deepcopy(EXAMPLES['cases']['unconfirmed'])
    case['source']['original']['question_day'] = '2026-11-14'
    case['host_expected']['expected_original'] = deepcopy(case['source']['original'])
    r = record('visitor', 'tip', payload)
    case['source']['records'] = [r]
    case['host_expected']['eligible_records'] = [r]
    source = capture(packed(case['source']), **case['host_expected'])
    arguments = dict(source=source, reference={k: v for k, v in r.items() if k != 'payload'},
                     item_id='item-1', amap_id='poi-1', visit_date=visit_date, locale=locale)
    arguments.update(kwargs)
    return venue_notices(entry, **arguments)


def test_calendar_distinguishes_ordinary_weekend_named_break_and_makeup_day():
    assert classify(date(2026, 11, 14)).kind == 'weekend'
    assert classify(date(2026, 11, 16)).kind == 'workday'
    holiday = classify(date(2026, 10, 5))
    assert holiday.kind == 'holiday_break' and holiday.long_break
    assert classify(date(2026, 10, 10)).kind == 'makeup_workday'
    assert statutory_exception(holiday) is None
    assert statutory_exception(classify(date(2026, 11, 14))) is False
    assert statutory_exception(classify(date(2026, 10, 10))) is False


def test_unsupported_year_remains_unknown_and_bad_date_is_rejected():
    assert classify(date(2050, 1, 1)).kind == 'unknown'
    assert statutory_exception(classify(date(2050, 1, 1))) is None
    with pytest.raises(ValueError):
        classify('2026-11-14')


@pytest.mark.parametrize('locale', ['zh', 'en'])
def test_real_h_conditions_close_monday_but_optional_seven_day_window_is_not_minimum(locale):
    notices = select_notices(venue(locale=locale))
    assert [n['type'] for n in notices] == ['day_opening', 'reservation']
    text = notices[1]['text']
    assert ('无需强制预约' if locale == 'zh' else 'do not require booking') in text
    assert ('最多提前7天' if locale == 'zh' else 'up to 7 days') in text
    assert notices[0]['source']['url'] == VENUE['source_urls'][0]
    assert notices[0]['source']['observed_at'] is None  # H has a date, not an instant.


def test_required_minimum_lead_and_window_max_have_different_meaning():
    entry = deepcopy(VENUE)
    entry['conditions'].update(reservation_required=True, advance_booking_rule='minimum_lead')
    assert '至少提前7天' in venue(entry)[1].text
    entry['conditions']['advance_booking_rule'] = 'window_max'
    text = venue(entry)[1].text
    assert '最多可提前7天' in text and '至少' not in text
    entry['conditions'].update(advance_booking_days=None, advance_booking_rule=None)
    assert venue(entry)[1].text == '这家场馆需要预约。'


def test_unknown_reservation_does_not_become_optional_or_zero_days():
    entry = deepcopy(VENUE)
    entry['conditions']['reservation_required'] = None
    assert '是否必须预约仍需确认' in venue(entry)[1].text
    entry['conditions'].update(advance_booking_days=None, advance_booking_rule=None)
    assert [n.type for n in venue(entry)] == ['day_opening']


@pytest.mark.parametrize('kwargs', [dict(item_id='other'), dict(amap_id='other')])
def test_city_or_similar_name_cannot_replace_exact_applicability(kwargs):
    with pytest.raises(SourceRejected):
        venue(**kwargs)


def test_changed_h_bytes_are_not_accepted_under_the_original_reference():
    original = venue()[0]
    assert original.source.title == VENUE['subject']['name_zh']
    # Build an actual bound source, then mutate just the raw entry.
    payload = dict(entry_id=VENUE['id'], entry_sha256=sha256(packed(VENUE)).hexdigest(),
                   checked_on=VENUE['checked_on'], expires_on=VENUE['expires_on'],
                   subject_key=VENUE['subject']['key'], item_ids=['item-1'], amap_ids=['poi-1'])
    case = deepcopy(EXAMPLES['cases']['unconfirmed'])
    case['source']['original']['question_day'] = '2026-11-14'
    case['host_expected']['expected_original'] = deepcopy(case['source']['original'])
    r = record('visitor', 'tip', payload)
    case['source']['records'] = case['host_expected']['eligible_records'] = [r]
    source = capture(packed(case['source']), **case['host_expected'])
    changed = deepcopy(VENUE)
    changed['conditions']['reservation_required'] = True
    with pytest.raises(SourceRejected):
        venue_notices(changed, source=source, reference={k:v for k,v in r.items() if k!='payload'},
                      item_id='item-1', amap_id='poi-1', visit_date=None, locale='en')


def test_weekend_makeup_and_named_break_do_not_silently_clear_weekly_closure():
    entry = deepcopy(VENUE)
    entry['conditions']['closed_weekdays'] = [6]
    assert '常规闭馆日，建议调换' in venue(entry, visit_date=date(2026, 11, 14))[0].text
    assert '常规闭馆日，建议调换' in venue(entry, visit_date=date(2026, 10, 10))[0].text
    entry['conditions']['closed_weekdays'] = [1]
    assert '例外是否适用尚待确认' in venue(entry, visit_date=date(2026, 10, 5))[0].text
    assert '确定出发日期后' in venue(entry, visit_date=None)[0].text


@pytest.mark.parametrize('locale', ['zh', 'en'])
def test_calendar_notices_only_long_break_makeup_or_unknown(locale):
    result = calendar_notices([date(2026, 11, 14), date(2026, 11, 16),
                               date(2026, 10, 5), date(2026, 10, 10), date(2050, 1, 1)], locale=locale)
    assert len(result) == 3
    assert all(n.type == 'holiday' for n in result)
    assert ('调休' if locale=='zh' else 'makeup') in result[1].text
    assert ('尚未确认' if locale=='zh' else 'unconfirmed') in result[2].text


@pytest.mark.parametrize('kind', ['weather', 'day_opening'])
@pytest.mark.parametrize('state', ['not_checked', 'unknown', 'clear', 'conflict'])
def test_exact_date_check_states_are_sourced_and_never_promoted(kind, state):
    check = dict(kind=kind, state=state, day_indices=[1], item_ids=['item-1'],
                 reason='synthetic code result', evidence_refs=['synthetic-original'])
    source = bound_records([record('checks', kind, check)])
    notices = date_check_notices([check], source=source, locale='en')
    assert len(notices) == (0 if state == 'clear' else 1)
    if notices:
        assert notices[0].severity == ('warning' if state == 'conflict' else 'info')
        assert ('unconfirmed' in notices[0].text) == (state != 'conflict')
    bad = dict(check, state='clear' if state!='clear' else 'conflict')
    with pytest.raises(SourceRejected):
        date_check_notices([bad], source=source, locale='en')


def test_route_strictly_over_sixty_minutes_and_original_amounts_required():
    case = deepcopy(EXAMPLES['cases']['matched'])
    leg = next(n for n in case['content']['legs'] if n['state']=='estimated')
    r = next(r for r in case['source']['records'] if r['kind']=='route' and r['sha256']==leg['source']['sha256'])
    for duration, count in [(3600, 0), (3600.01, 1), (3601, 1)]:
        r['payload']['duration_seconds'] = leg['duration_seconds'] = duration
        r['sha256'] = sha256(packed(r['payload'])).hexdigest()
        leg['source']['sha256'] = r['sha256']
        case['host_expected']['eligible_records'] = deepcopy(case['source']['records'])
        source = capture(packed(case['source']), **case['host_expected'])
        assert len(route_notices([leg], source=source, locale='zh')) == count
    bad = deepcopy(leg)
    bad['duration_seconds'] += 1
    with pytest.raises(SourceRejected):
        route_notices([bad], source=source, locale='zh')
    assert not route_notices([dict(leg, state='unconfirmed')], source=source, locale='en')


def test_season_is_explicit_not_guessed_from_undated_or_place_name():
    assert not winter_outdoor_notice(season=None, outdoor_item_ids=['item-1'], locale='zh')
    assert not winter_outdoor_notice(season='winter', outdoor_item_ids=[], locale='en')
    assert len(winter_outdoor_notice(season='winter', outdoor_item_ids=['item-1'], locale='en')) == 1


def test_at_most_two_stable_deduplicated_code_notices_and_exact_message4_shape():
    groups = (venue(), calendar_notices([date(2026, 10, 5)], locale='zh'),
              winter_outdoor_notice(season='winter', outdoor_item_ids=['item-1'], locale='zh'))
    output = select_notices(*groups, *groups)
    assert len(output) == 2 and output == select_notices(*reversed(groups))
    assert len({n['id'] for n in output}) == 2
    schema = json.loads((ROOT/'contracts/message/lio-exploration-schema.4.json').read_bytes())
    registry = Registry()
    for path in (ROOT/'contracts/message').glob('*.json'):
        resource = json.loads(path.read_bytes())
        if isinstance(resource, dict) and '$id' in resource:
            registry = registry.with_resource(resource['$id'], Resource.from_contents(resource))
    validator = Draft202012Validator({'$ref':schema['$id']+'#/$defs/Notice'}, registry=registry, format_checker=FormatChecker())
    for notice in output:
        validator.validate(notice)
    assert select_notices() == []
