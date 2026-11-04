"""Acceptance cannot pass with model-only, unknown or empty product evidence."""
import copy
import asyncio
import hashlib
import json
import tempfile
from datetime import datetime,timezone
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from real_services_acceptance import verification_passed,record_place_responses,M4_BASE,M4_MODEL
from cj_usage.authorization_budget import canonical
from cj_api.real_services import canonical_tool
from cj_place.gaode import Config,prepare,Response
from cj_place.models import ORIGIN,Search
from cj_place.contract_v1 import decode_query
from cj_agent.provider import ProviderFailed


def proof():
    cases={};attempts=[]
    for name,registration,endpoint,status in (
        ('place-zh','tool.place','https://restapi.amap.com/v3/place/text','ok'),
        ('weather-en','tool.weather','https://restapi.amap.com/v3/weather/weatherInfo','observed')):
        run='run-'+name;mid='message-'+name;operations=[]
        for key,kind,receipt in (
            ('model.tool_turn.0','model.tool_turn',dict(model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',usage={'total_tokens':10})),
            ('tool.0.0',registration,dict(endpoint=endpoint,result_status=status)),
            ('model.tool_turn.1','model.tool_turn',dict(model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',usage={'total_tokens':10}))):
            attempt=name+'-'+key
            operations.append(dict(run_id=run,operation_key=key,registration_id=kind,attempt_id=attempt))
            attempts.append(dict(attempt_id=attempt,state='RECEIVED',receipt=receipt))
        cases[name]=dict(state='completed',run_id=run,message_id=mid,operations=operations,
            display=dict(run_id=run,message_id=mid,status='completed',text_state='complete',answer_chars=30,text_sha256='a'*64))
    return dict(state='COMPLETE',cases=cases),attempts


NOW=datetime(2026,11,4,tzinfo=timezone.utc)


def search_exchange(keyword,identity,coordinate):
    config=Config(ORIGIN,8192,65536,20,60)
    request=prepare(config,Search(keyword,'北京',1,1),'fixture-'+identity,NOW,basic=True)
    body=canonical(dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(id=identity,name=keyword,location=coordinate)]))
    result=SimpleNamespace(state='received',response=Response(request.binding_digest,ORIGIN,request.path,200,body,NOW))
    return config,request,result,body


class Verification(unittest.TestCase):
    def test_diagnostic_still_requires_actual_tool_and_complete_continuation(self):
        batch,attempts=proof();batch['verification_profile']='native-diagnostics-1'
        del batch['cases']['weather-en']
        self.assertTrue(verification_passed(batch,attempts))
        batch['cases']['place-zh']['provider_diagnostics']=['metadata only']
        batch['cases']['place-zh']['display']['answer_chars']=0
        self.assertFalse(verification_passed(batch,attempts))

    def test_route_diagnostic_needs_original_queries_order_and_receipts(self):
        batch,attempts=proof();case=batch['cases']['place-zh'];batch.update(verification_profile='route-diagnostics-1',cases={'route-zh':case})
        case['operations'][-1]['operation_key']='model.tool_turn.3'
        sources=[dict(kind='search',keyword=keyword,provider_id=identity,coordinate_raw=coordinate,request_ref=ref) for keyword,identity,coordinate,ref in
            (('北海公园','SYNTH_A','116.1,39.1','north-search'),('恭王府','SYNTH_B','116.2,39.2','palace-search'))]
        route=dict(kind='route',request_ref='walking-query',mode='walking')
        for prefix,source in zip(('origin','destination'),sources):route[prefix]={k:source[k] for k in ('provider_id','coordinate_raw')};route[prefix].update(coordinate_role='poi_center',search_ref=source['request_ref'])
        batch['route_audit']=[*sources,route]
        operations=[next(op for op in case['operations'] if op['registration_id']=='tool.place')]
        for index,endpoint in ((1,'https://restapi.amap.com/v3/place/text'),(2,'https://restapi.amap.com/v3/direction/walking')):
            identity='route-extra-'+str(index)
            op=dict(run_id=case['run_id'],operation_key='tool.'+str(index)+'.0',registration_id='tool.place',attempt_id=identity)
            case['operations'].append(op);operations.append(op)
            attempts.append(dict(attempt_id=identity,state='RECEIVED',receipt=dict(endpoint=endpoint,result_status='ok')))
        for source,op in zip(sources,operations):op['input']=dict(query=dict(version='PLACE-query.1',query=dict(kind='Search',keyword=source['keyword'],city='北京',page=1,page_size=1)),request_ref=source['request_ref'])
        arguments=dict(mode='walking')
        for prefix,source in zip(('origin','destination'),sources):
            arguments.update({prefix+'_provider_id':source['provider_id'],prefix+'_coordinate':source['coordinate_raw'],prefix+'_coordinate_role':'poi_center'})
        _,raw=canonical_tool('place_route',canonical(arguments))
        operations[-1]['input']=dict(query=json.loads(raw),request_ref=route['request_ref'])
        records={a['attempt_id']:a for a in attempts}
        for op in operations:records[op['attempt_id']]['input_sha']=hashlib.sha256(canonical(op['input'])).hexdigest()
        self.assertTrue(verification_passed(batch,attempts))
        for mutate in (
            lambda b,a:b.update(response_capture_failed=True),
            lambda b,a:b['route_audit'][-1].update(mode='driving'),
            lambda b,a:b['route_audit'][0].update(keyword='故宫'),
            lambda b,a:b['cases']['route-zh']['operations'][1].update(operation_key='tool.3.0'),
            lambda b,a:a[-1]['receipt'].update(result_status='invalid_response'),
        ):
            other,records=copy.deepcopy((batch,attempts));mutate(other,records)
            self.assertFalse(verification_passed(other,records))

    def test_response_observer_preserves_original_transport_result_and_private_bytes(self):
        from cj_api import real_services
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);batch={'provider_responses':[]};state=root/'batch.json'
            config,request,result,body=search_exchange('北海公园','SYNTH_A','116.1,39.1')
            original=AsyncMock(return_value=result)
            with patch.object(real_services,'fetch_candidate',original):
                with record_place_responses(root,batch,state):observed=asyncio.run(real_services.fetch_candidate(config,request,'fixture-credentials',basic=True))
                self.assertIs(real_services.fetch_candidate,original)
            self.assertIs(observed,result);original.assert_awaited_once()
            saved=root/batch['provider_responses'][0]['file']
            self.assertEqual(saved.read_bytes(),body);self.assertEqual(saved.stat().st_mode&0o777,0o600)
            self.assertEqual(batch['provider_responses'][0]['response_sha256'],hashlib.sha256(body).hexdigest())
            self.assertNotIn('fixture-credentials',state.read_text())

    def test_observer_io_failure_is_reported_but_original_response_continues(self):
        from cj_api import real_services
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);batch={'provider_responses':[]};config,request,result,_=search_exchange('北海公园','SYNTH_A','116.1,39.1')
            original=AsyncMock(return_value=result)
            with patch.object(real_services,'fetch_candidate',original),record_place_responses(root,batch,root/'batch.json'):
                with patch('real_services_acceptance.os.fsync',side_effect=OSError('synthetic disk full')),self.assertLogs('cj_provider.audit',level='ERROR'):
                    observed=asyncio.run(real_services.fetch_candidate(config,request,'fixture-credentials',basic=True))
            self.assertIs(observed,result);self.assertTrue(batch['response_capture_failed']);original.assert_awaited_once()

    def test_r1_refuses_unplanned_or_duplicate_queries_before_http(self):
        from cj_api import real_services
        config,first,rfirst,_=search_exchange('北海公园','SYNTH_A','116.1,39.1')
        _,second,rsecond,_=search_exchange('恭王府','SYNTH_B','116.2,39.2')
        _,other,_,_=search_exchange('故宫','SYNTH_OTHER','116.3,39.3')
        args=dict(origin_provider_id='SYNTH_WRONG',origin_coordinate='116.1,39.1',origin_coordinate_role='poi_center',
            destination_provider_id='SYNTH_B',destination_coordinate='116.2,39.2',destination_coordinate_role='poi_center',mode='walking')
        _,raw=canonical_tool('place_route',canonical(args));route=prepare(config,decode_query(raw),'route-wrong-owner',NOW)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);batch={'provider_responses':[]};original=AsyncMock(side_effect=[rfirst,rsecond])
            with patch.object(real_services,'fetch_candidate',original),record_place_responses(root,batch,root/'batch.json'):
                for forbidden in (other,route):
                    with self.assertRaises(ProviderFailed):asyncio.run(real_services.fetch_candidate(config,forbidden,'fixture',basic=True))
                self.assertEqual(original.await_count,0)
                asyncio.run(real_services.fetch_candidate(config,first,'fixture',basic=True))
                with self.assertRaises(ProviderFailed):asyncio.run(real_services.fetch_candidate(config,first,'fixture',basic=True))
                asyncio.run(real_services.fetch_candidate(config,second,'fixture',basic=True))
                with self.assertRaises(ProviderFailed):asyncio.run(real_services.fetch_candidate(config,route,'fixture',basic=True))
                self.assertEqual(original.await_count,2)

    def test_legacy_profiles_keep_previous_multiple_valid_tool_acceptance(self):
        batch,attempts=proof();case=batch['cases']['place-zh'];op=copy.deepcopy(case['operations'][1]);op.update(operation_key='tool.0.1',attempt_id='legacy-extra')
        case['operations'].append(op);attempts.append(dict(attempt_id='legacy-extra',state='RECEIVED',receipt=dict(endpoint='https://restapi.amap.com/v3/place/text',result_status='ok')))
        self.assertTrue(verification_passed(batch,attempts))

    def test_matching_tool_followup_receipts_and_product_body_required(self):
        batch,attempts=proof();self.assertTrue(verification_passed(batch,attempts))
        for mutate in (
            lambda b,a:b.update(state='UNKNOWN_INTERRUPTED'),
            lambda b,a:b['cases']['place-zh'].update(operations=b['cases']['place-zh']['operations'][:1]),
            lambda b,a:b['cases']['place-zh']['display'].update(answer_chars=0),
            lambda b,a:b['cases']['weather-en']['display'].update(run_id='different-original'),
            lambda b,a:a[2].update(state='INTENT'),
            lambda b,a:a[1]['receipt'].update(result_status='rate_limited'),
            lambda b,a:b['cases']['weather-en']['operations'][1].update(registration_id='tool.fact'),
            lambda b,a:b['cases']['place-zh'].update(operations=b['cases']['place-zh']['operations'][:2]),
        ):
            b,a=copy.deepcopy((batch,attempts));mutate(b,a)
            self.assertFalse(verification_passed(b,a))


if __name__=='__main__':unittest.main()
