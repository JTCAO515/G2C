from copy import deepcopy
import pytest
from cj_trip.domain import packed
from cj_feasibility.trip_time import evaluate


def obs(value):return {'state':'known','value':value}
def event(day,clock,zone='Asia/Shanghai',offset=None):
    return dict(date=obs(day),time=obs(clock),timezone=obs(zone),utc_offset={'state':'unknown'} if offset is None else obs(offset))
def document(start,end):
    return dict(content_version='structured.1',title='Explicit 声明',sources=[],items=[dict(id='one',text='Tomorrow is text',
        verification='pending',evidence=[],schedule=dict(start=start,end=end),fixed={'state':'unknown'},source_category='user_provided',source_refs=[])])
def codes(value):return {c.code:c.status for c in value.checks}


def test_reversed_and_cross_day_share_existing_codes():
    value=document(event('2026-11-02','10:00:00'),event('2026-11-02','09:00:00'))
    assert codes(evaluate(packed(value)))['ITEM_TIME_REVERSED']=='CONFLICT'
    value['items'][0]['schedule']['end']=event('2026-11-03','09:00:00')
    result=evaluate(packed(value));assert result.status=='UNKNOWN';assert codes(result)['ITEM_TIME_ORDER']=='PASS'


@pytest.mark.parametrize('day,clock',[('2026-11-01','01:30:00'),('2026-03-08','02:30:00')])
def test_fold_and_gap_remain_unknown_without_explicit_resolution(day,clock):
    value=document(event(day,clock,'America/New_York'),event(day,'04:00:00','America/New_York'))
    assert codes(evaluate(packed(value)))['ITEM_TIME_UNKNOWN']=='UNKNOWN'


def test_explicit_offset_resolves_fold_but_mismatch_is_unknown():
    value=document(event('2026-11-01','01:30:00','America/New_York','-04:00'),event('2026-11-01','04:00:00','America/New_York'))
    assert codes(evaluate(packed(value)))['ITEM_TIME_ORDER']=='PASS'
    value['items'][0]['schedule']['start']['utc_offset']=obs('+08:00')
    assert codes(evaluate(packed(value)))['ITEM_TIME_UNKNOWN']=='UNKNOWN'


def test_touching_boundaries_and_no_fabricated_occupancy():
    value=document(event('2026-11-02','09:00:00'),event('2026-11-02','10:00:00'))
    other=deepcopy(value['items'][0]);other['id']='two';other['schedule']=dict(start=event('2026-11-02','10:00:00'),end=event('2026-11-02','11:00:00'))
    value['items'].append(other)
    assert 'OVERLAP_MEANING_UNKNOWN' not in codes(evaluate(packed(value)))
    other['schedule']['start']=event('2026-11-02','09:30:00')
    result=evaluate(packed(value));assert codes(result)['OVERLAP_MEANING_UNKNOWN']=='UNKNOWN'
    assert result.status=='UNKNOWN';assert all(c.zh and c.en for c in result.checks)
