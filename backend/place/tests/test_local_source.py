from datetime import datetime,timedelta,timezone
import pytest
from cj_place.contract_v1 import encode_query,decode_result
from cj_place.gaode import Config
from cj_place.models import ORIGIN,Search,Detail,RouteQuery,Endpoint,Coordinate,Departure
from cj_place.local_source import LocalPlaceProducer


def source():return LocalPlaceProducer(Config(ORIGIN,4096,16384,5,60))


def test_real_parser_producer_keeps_separate_branches_and_synthetic_trace():
    producer=source()
    value=decode_result(producer.invoke(encode_query(Search('合成酒店','合成城市',1,20)),'original-server-op'))
    assert value['outcome']=='ok' and producer.invocations==producer.transport_calls==1
    assert [p['provider_id'] for p in value['places']]==['SYNTH_EAST','SYNTH_WEST']
    assert value['source']['evidence_kind']=='synthetic' and value['source']['request_ref']=='original-server-op'
    assert value['places'][1]['address_zh']=={'state':'empty_array','value':None}
    assert all(p['official_name_en']=={'state':'unknown','value':None} for p in value['places'])


@pytest.mark.parametrize('keyword,outcome',[('SYNTH_MISSING','no_results'),('SYNTH_RATE_LIMIT','rate_limited'),('SYNTH_BAD_JSON','invalid_response')])
def test_failures_are_not_successful_empty_results_or_raw_body_echo(keyword,outcome):
    producer=source();raw=producer.invoke(encode_query(Search(keyword,'合成城市',1,20)),'original-op')
    value=decode_result(raw)
    assert value['outcome']==outcome and value['places']==[] and producer.transport_calls==1
    assert b'SYNTHETIC_PRIVATE_SUPPLIER_BODY' not in raw


def test_details_and_route_roles_bind_to_original_query():
    producer=source();detail=decode_result(producer.invoke(encode_query(Detail('SYNTH_OTHER')),'detail'))
    assert detail['outcome']=='no_results'
    query=RouteQuery(Endpoint('SYNTH_EAST',Coordinate('116.100100,39.100100'),'entrance'),
        Endpoint('SYNTH_WEST',Coordinate('116.200000,39.200000'),'poi_center'),'walking',Departure('at_query_time',None))
    value=decode_result(producer.invoke(encode_query(query),'route'))
    assert value['routes'][0]['query']==value['query']
    assert value['routes'][0]['duration']['value']['value']=='90'
    assert value['routes'][0]['future_guaranteed'] is False


def test_future_departure_is_preserved_and_never_dispatched_as_now():
    producer=source()
    query=RouteQuery(Endpoint('SYNTH_EAST',Coordinate('116.1,39.1'),'entrance'),
        Endpoint('SYNTH_WEST',Coordinate('116.2,39.2'),'poi_center'),'driving',
        Departure('specified_time',datetime(2027,1,1,tzinfo=timezone(timedelta(hours=8)))))
    value=decode_result(producer.invoke(encode_query(query),'future'))
    assert value['outcome']=='unsupported' and value['query']['departure']['condition']=='specified_time'
    assert producer.invocations==1 and producer.transport_calls==0
