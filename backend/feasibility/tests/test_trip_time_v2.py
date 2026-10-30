import pytest
from cj_trip.domain import packed
from cj_feasibility.trip_time import evaluate as old_evaluate
from cj_feasibility.trip_time_v2 import evaluate
from test_trip_time import document,event,codes


def test_explicit_minutes_offsets_and_original_version_remain_distinct():
    value=document(event('2026-11-02','10:00',offset='+08:00'),event('2026-11-02','09:00',offset='+08:00'))
    value['content_version']='structured.2'
    report=evaluate(packed(value))
    assert report.version=='FEASIBILITY-TRIP@2.0'
    assert codes(report)['ITEM_TIME_REVERSED']=='CONFLICT'
    with pytest.raises(ValueError):old_evaluate(packed(value))
    assert value['items'][0]['schedule']['start']['time']['value']=='10:00'


def test_explicit_fold_offset_and_mismatch_use_the_same_original_time_checks():
    value=document(event('2026-11-01','01:30','America/New_York','-04:00'),event('2026-11-01','04:00','America/New_York'))
    value['content_version']='structured.2'
    assert codes(evaluate(packed(value)))['ITEM_TIME_ORDER']=='PASS'
    value['items'][0]['schedule']['start']['utc_offset']['value']='+08:00'
    assert codes(evaluate(packed(value)))['ITEM_TIME_UNKNOWN']=='UNKNOWN'
