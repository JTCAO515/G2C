"""Formal Trip selectors: no inference, owner fields or legacy wire broadening."""
import json
import pytest
from cj_message.domain import Command, InvalidInput, Unavailable
from cj_message.trip_context import TripSelection, decode_source, on_day
from cj_trip.domain import packed


def event(day='2026-10-31', zone='Asia/Shanghai', time='10:00:00'):
    return {key:dict(state='known',value=value) for key,value in
            [('date',day),('time',time),('timezone',zone),('utc_offset','+08:00')]}


def document():
    return dict(content_version='structured.1',title='Explicit synthetic Trip',sources=[],items=[
        dict(id='item-a',text='用户声明的活动',verification='pending',evidence=[],
             schedule=dict(start=event(),end=event(time='11:00:00')),
             fixed=dict(state='unknown'),source_category='unknown',source_refs=[])])


def raw(selection=None,**changes):
    value=dict(version='MESSAGE-send.3',conversation_id='chat',message_id='original',text='这里呢？',
        trip_id=None,creation_intent='none',expected_generation='g',expected_sequence=0,
        travel_context=None,needs_reference=None,trip_context=selection)
    value.update(changes)
    return json.dumps(value,ensure_ascii=False).encode()


def select(**changes):
    value=dict(id='trip-a',expected_version=1,day=dict(date='2026-10-31',timezone='Asia/Shanghai'),item_id='item-a')
    value.update(changes)
    return value


def test_explicit_selection_and_legacy_parser_isolation():
    command=Command.parse_v3(raw(select()))
    assert command.trip_context.public_value()==select()
    assert Command.parse_original(command.raw)==command
    for parser in (Command.parse,Command.parse_v2,Command.parse_stored):
        with pytest.raises(InvalidInput):parser(command.raw)
    assert Command.parse_v3(raw()).trip_context is None
    for value in (select(owner='caller'),select(expected_version=True),select(expected_version=0),
                  select(day=dict(date='20261031',timezone='Asia/Shanghai')),
                  select(day=dict(date='2026-10-31',timezone='localtime')),select(item_id='a/b')):
        with pytest.raises(InvalidInput):Command.parse_v3(raw(value))
    with pytest.raises(InvalidInput):Command.parse_v3(raw(select(),travel_context=dict(id='a'*32,expected_version=1)))
    with pytest.raises(InvalidInput):Command.parse_v3(raw(select(),creation_intent='consider_trip'))


def test_real_document_membership_and_unknown_is_not_a_default_day():
    data=document(); selection=TripSelection.parse(select())
    assert decode_source(packed(data),selection)==data
    for wrong in (select(item_id='foreign'),select(day=dict(date='2026-11-01',timezone='Asia/Shanghai')),
                  select(day=dict(date='2026-10-31',timezone='UTC'))):
        with pytest.raises(Unavailable):decode_source(packed(data),TripSelection.parse(wrong))
    data['items'][0]['schedule']['start']['date']=dict(state='unknown')
    data['items'][0]['schedule']['end']['date']=dict(state='missing')
    with pytest.raises(Unavailable):decode_source(packed(data),selection)
    assert decode_source(packed(data),TripSelection.parse(select(day=None)))==data


def test_midnight_exclusion_cross_day_and_zone_membership():
    item=document()['items'][0]
    item['schedule']['end']=event(day='2026-11-02',time='00:00:00')
    assert on_day(item,('2026-11-01','Asia/Shanghai'))
    assert not on_day(item,('2026-11-02','Asia/Shanghai'))
    item['schedule']['end']['timezone']=dict(state='known',value='Asia/Tokyo')
    assert not on_day(item,('2026-11-01','Asia/Shanghai'))
