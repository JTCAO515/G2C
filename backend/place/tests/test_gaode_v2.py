"""POI2 bounded original observations, not a provider-dispatch or source grant."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json

import pytest
from cj_place.gaode import Config,Response
from cj_place.gaode_v2 import TextSearch,Nearby,POIDetail,prepare,parse
from cj_place.models import Coordinate,FieldState

NOW=datetime(2026,11,14,tzinfo=timezone.utc)
CONFIG=Config('https://restapi.amap.com',4096,16384,10,60)


def poi():
    return dict(id='B000SYNTH1',name='合成博物馆',adcode='110101',cityname='北京市',address='合成街1号',
        location='116.400000,39.900000',navi=dict(entr_location='116.400001,39.900001'),
        business=dict(opentime_today='09:00-17:00',opentime_week='周一闭馆'))


def receipt(request,rows):
    body=json.dumps(dict(status='1',infocode='10000',count=str(len(rows)),pois=rows),ensure_ascii=False).encode()
    return Response(request.binding_digest,request.origin,request.path,200,body,NOW)


def test_queries_are_explicit_poi2_first_pages_with_strict_city_and_no_secret():
    for query,path in ((TextSearch('博物馆','北京',4),'/v5/place/text'),
                       (Nearby('餐馆','110000',Coordinate('116.4,39.9'),1500,4),'/v5/place/around'),
                       (POIDetail('B000SYNTH1'),'/v5/place/detail')):
        request=prepare(CONFIG,query,'actual-operation',NOW)
        assert request.path==path
        params=dict(request.params)
        assert params['show_fields']=='business,navi'and params['output']=='json'
        assert 'key'not in params and 'langCode'not in params
        if not isinstance(query,POIDetail):assert params['page_num']=='1'and params['city_limit']=='true'
        assert parse(CONFIG,request,receipt(request,[poi()]),NOW).pois[0].name_zh=='合成博物馆'


def test_raw_provider_coordinates_and_roles_remain_exact_without_invented_english():
    request=prepare(CONFIG,TextSearch('博物馆','110000',2),'original-query',NOW)
    point=poi();point['location']='116.400000000001,39.900000000001'
    result=parse(CONFIG,request,receipt(request,[point]),NOW)
    row=result.pois[0]
    assert row.place_projection('poi_center')['coordinate']['raw']==point['location']
    assert row.place_projection('entrance')['coordinate_role']=='entrance'
    assert row.place_projection('exit')is None
    assert row.opening_today.value=='09:00-17:00'
    assert row.opening_week.value=='周一闭馆'
    assert len(result.raw_response_sha256)==64 and result.request_ref=='original-query'
    assert 'name_en'not in row.place_projection('poi_center')


@pytest.mark.parametrize('value',[None,[],42,'39.9,116.4','0,999'])
def test_missing_or_bad_coordinate_never_becomes_a_matched_place(value):
    request=prepare(CONFIG,TextSearch('博物馆','北京',2),'original-query',NOW)
    row=poi();row['location']=value
    parsed=parse(CONFIG,request,receipt(request,[row]),NOW).pois[0]
    assert parsed.place_projection('poi_center')is None


def test_unknown_opening_fields_stay_separate_and_are_never_parsed_as_clear():
    request=prepare(CONFIG,TextSearch('博物馆','北京',2),'original-query',NOW)
    row=poi();row.pop('business');row.pop('navi')
    parsed=parse(CONFIG,request,receipt(request,[row]),NOW).pois[0]
    assert parsed.opening_today.state is FieldState.MISSING
    assert parsed.opening_week.state is FieldState.MISSING
    assert parsed.place_projection('entrance')is None
    row['business']={};row['business']['opentime_today']=[]
    parsed=parse(CONFIG,request,receipt(request,[row]),NOW).pois[0]
    assert parsed.opening_today.state is FieldState.EMPTY_ARRAY
    assert parsed.opening_week.state is FieldState.MISSING


def test_wrong_city_duplicate_ids_wrong_detail_or_excess_count_refuse_the_receipt():
    request=prepare(CONFIG,TextSearch('博物馆','510100',1),'original-query',NOW)
    with pytest.raises(ValueError):parse(CONFIG,request,receipt(request,[poi()]),NOW)
    request=prepare(CONFIG,TextSearch('博物馆','北京',2),'original-query',NOW)
    with pytest.raises(ValueError):parse(CONFIG,request,receipt(request,[poi(),poi()]),NOW)
    request=prepare(CONFIG,TextSearch('博物馆','北京',1),'original-query',NOW)
    with pytest.raises(ValueError):parse(CONFIG,request,receipt(request,[poi(),poi()]),NOW)
    request=prepare(CONFIG,POIDetail('B000OTHER'),'original-query',NOW)
    with pytest.raises(ValueError):parse(CONFIG,request,receipt(request,[poi()]),NOW)


def test_same_original_binding_path_time_and_complete_json_are_required():
    request=prepare(CONFIG,TextSearch('博物馆','北京',2),'original-query',NOW)
    good=receipt(request,[poi()])
    for changes in (dict(binding_digest='0'*64),dict(path='/v3/place/text'),dict(origin='https://other.invalid'),
                    dict(received_at=NOW+timedelta(seconds=1)),dict(received_at=NOW-timedelta(seconds=1)),
                    dict(http_status=500),dict(body=good.body[:-1]),dict(body=b'{"status":"1","status":"1"}')):
        with pytest.raises((ValueError,UnicodeError)):parse(CONFIG,request,replace(good,**changes),NOW)
    with pytest.raises(ValueError):parse(CONFIG,request,good,NOW+timedelta(seconds=61))
    with pytest.raises(ValueError):parse(CONFIG,request,replace(good,body=b'x'*16385),NOW)


def test_parameter_boundaries_do_not_batch_keywords_round_points_or_invent_region():
    for values in (('a|b','北京',4),('a'*81,'北京',4),('博物馆','Beijing',4),('博物馆','北京',True),('博物馆','北京',26)):
        with pytest.raises(ValueError):TextSearch(*values)
    with pytest.raises(ValueError):Nearby('餐馆','北京',Coordinate('116.1234567,39.9'),1500,4)
    with pytest.raises(ValueError):Nearby('餐馆','北京',Coordinate('116.4,39.9'),0,4)
