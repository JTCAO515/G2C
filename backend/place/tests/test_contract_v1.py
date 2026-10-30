"""PLACE@1.0 actual producer/consumer codec, entirely synthetic and offline."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import runpy
import pytest

from cj_place import Config,ORIGIN,Search,Detail,RouteQuery,Departure,Outcome,execute,prepare,Response,parse_response
from cj_place.models import Coordinate,Endpoint
from cj_place.contract_v1 import decode_query,encode_query,decode_result,encode_result,publish_response

ROOT=Path(__file__).resolve().parents[3]


def examples():
    return runpy.run_path(str(ROOT/'contracts/place/examples.py'))['examples']()


def wire(result):return encode_result(result,evidence_kind='synthetic')


def test_existing_real_parser_values_roundtrip_in_new_version_without_old_upgrade():
    for result in examples():
        assert decode_query(encode_query(result.query))==result.query
        value=decode_result(wire(result))
        assert value['version']=='PLACE-result.1' and value['outcome']==result.outcome.value
        if value['source'] is not None:
            assert value['source']['evidence_kind']=='synthetic' and value['source']['recording_ref'] is None
            assert value['source']['adapter_profile']=='CJ-PLACE-GAODE@0.1.0-rc.1'
    assert execute(Search('合成','合成城市',1,1)).outcome is Outcome.UNAVAILABLE


def test_names_and_coordinates_do_not_merge_or_invent_official_english():
    value=decode_result(wire(examples()[0]))
    assert [p['provider_id'] for p in value['places']]==['SYNTH_EAST','SYNTH_WEST']
    assert value['places'][0]['name_zh']==value['places'][1]['name_zh']=='合成酒店'
    assert value['places'][1]['address_zh']=={'state':'empty_array','value':None}
    assert all(p['official_name_en']=={'state':'unknown','value':None} for p in value['places'])
    assert value['places'][0]['coordinate']['value']['longitude']=='116.1'


def test_routes_include_actual_distance_duration_and_exact_bound_endpoints():
    value=decode_result(wire(examples()[1]));route=value['routes'][0]
    assert route['query']==value['query']
    assert route['query']['origin']['coordinate_role']=='entrance'
    assert route['distance']['value']=={'raw':'100','value':'100','unit':'m'}
    assert route['duration']['value']=={'raw':'90','value':'90','unit':'s'}
    assert route['future_guaranteed'] is False


@pytest.mark.parametrize('change',[
    lambda x:x.update(owner='another'),
    lambda x:x.update(version='CJ-PLACE-TRIP-JSON@0.1.0-rc.1'),
    lambda x:x['query'].update(url='https://private.invalid'),
    lambda x:x['query'].update(page=True),
    lambda x:x['query'].update(page=201),
    lambda x:x['query'].update(keyword='a|b'),
])
def test_query_rejects_authority_fields_legacy_and_unsupported_grammar(change):
    value=json.loads(encode_query(Search('合成','合成城市',1,1)));change(value)
    with pytest.raises(ValueError):decode_query(json.dumps(value).encode())


@pytest.mark.parametrize('change',[
    lambda x:x.update(accepted=True),
    lambda x:x.update(version='future'),
    lambda x:x.update(provider_count=True),
    lambda x:x.update(provider_count=0),
    lambda x:x['places'].append(deepcopy(x['places'][0])),
    lambda x:x['places'][0]['coordinate']['value'].update(longitude=116.1),
    lambda x:x['places'][0]['coordinate']['value'].update(longitude='116.2'),
    lambda x:x['places'][0]['coordinate']['value'].update(crs='WGS84'),
    lambda x:x['places'][0]['exit_coordinate'].update(value={'raw':'0,0','longitude':'0','latitude':'0','crs':'GCJ-02'}),
    lambda x:x['source'].update(endpoint='http://169.254.169.254/latest'),
    lambda x:x['source'].update(max_age_seconds=999999),
    lambda x:x['source'].update(evidence_kind='verified'),
    lambda x:x['source'].update(evidence_kind='recorded_replay'),
    lambda x:x['source']['query_started_at'].update(iso8601='2026-10-22T12:00:00.000000'),
    lambda x:x['source']['received_at'].update(fold=True),
    lambda x:x.update(outcome='no_results'),
])
def test_result_negative_vectors_are_rejected_by_actual_decoder(change):
    value=json.loads(wire(examples()[0]));change(value)
    with pytest.raises(ValueError):decode_result(json.dumps(value).encode())


def test_duplicate_json_and_deep_input_fail_at_boundary():
    raw=encode_query(Search('合成','合成城市',1,1))
    with pytest.raises(ValueError):decode_query(raw.replace(b'"version":',b'"version":"ignored","version":',1))
    with pytest.raises(ValueError):decode_query(b'['*1100+b'0'+b']'*1100)


def test_detail_identity_route_original_time_and_source_chronology():
    result=examples()[0]
    value=json.loads(wire(result));value['query']={'kind':'Detail','provider_id':'SYNTH_OTHER'}
    value['source']['endpoint']=ORIGIN+'/v3/place/detail'
    with pytest.raises(ValueError):decode_result(json.dumps(value).encode())
    route=json.loads(wire(examples()[1]))
    route['routes'][0]['query']['destination']['provider_id']='SYNTH_OTHER'
    with pytest.raises(ValueError):decode_result(json.dumps(route).encode())
    value=json.loads(wire(result));value['source']['received_at']['iso8601']='2026-10-22T11:59:59.000000+00:00'
    with pytest.raises(ValueError):decode_result(json.dumps(value).encode())
    future=RouteQuery(Endpoint('SYNTH_A',Coordinate('116.1,39.1'),'poi_center'),
        Endpoint('SYNTH_B',Coordinate('116.2,39.2'),'entrance'),'walking',
        Departure('specified_time',datetime(2027,1,1,tzinfo=timezone(timedelta(hours=8)))))
    assert decode_query(encode_query(future))==future
    assert decode_query(encode_query(future)).departure.condition=='specified_time'
    with pytest.raises(ValueError,match='departure_not_supported'):
        prepare(Config(ORIGIN,4096,16384,3,60),decode_query(encode_query(future)),
                'synthetic-future',datetime(2026,10,22,tzinfo=timezone.utc))


def test_one_parser_publisher_keeps_failure_and_cannot_promote_synthetic():
    at=datetime(2026,10,22,12,tzinfo=timezone.utc)
    config=Config(ORIGIN,4096,16384,3,60);request=prepare(config,Detail('SYNTH_A'),'synthetic-v1',at)
    response=Response(request.binding_digest,request.origin,request.path,429,b'not a successful empty page',at+timedelta(seconds=1))
    value=decode_result(publish_response(config,request,response,now=at+timedelta(seconds=2),evidence_kind='synthetic'))
    assert value['outcome']=='rate_limited' and value['places']==[]
    with pytest.raises(ValueError):encode_result(examples()[0],evidence_kind='live_provider')


def test_frozen_golden_is_from_product_codec_and_labeled_synthetic():
    data=json.loads((ROOT/'contracts/place/v1-examples.json').read_text())
    assert data['data_origin']=='synthetic'
    assert data['positive']==[json.loads(wire(r)) for r in examples()]
