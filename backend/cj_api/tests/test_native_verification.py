"""Acceptance cannot pass with model-only, unknown or empty product evidence."""
import copy
import asyncio
import hashlib
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from real_services_acceptance import verification_passed,record_place_responses,M4_BASE,M4_MODEL


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


class Verification(unittest.TestCase):
    def test_diagnostic_still_requires_actual_tool_and_complete_continuation(self):
        batch,attempts=proof();batch['verification_profile']='native-diagnostics-1'
        del batch['cases']['weather-en']
        self.assertTrue(verification_passed(batch,attempts))
        batch['cases']['place-zh']['provider_diagnostics']=['metadata only']
        batch['cases']['place-zh']['display']['answer_chars']=0
        self.assertFalse(verification_passed(batch,attempts))

    def test_route_diagnostic_needs_two_searches_one_route_and_later_model(self):
        batch,attempts=proof();case=batch['cases']['place-zh']
        batch.update(verification_profile='route-diagnostics-1',cases={'route-zh':case})
        case['operations'][-1]['operation_key']='model.tool_turn.3'
        for index,endpoint in ((1,'https://restapi.amap.com/v3/place/text'),(2,'https://restapi.amap.com/v3/direction/walking')):
            identity='route-extra-'+str(index)
            case['operations'].append(dict(run_id=case['run_id'],operation_key='tool.'+str(index)+'.0',registration_id='tool.place',attempt_id=identity))
            attempts.append(dict(attempt_id=identity,state='RECEIVED',receipt=dict(endpoint=endpoint,result_status='ok')))
        self.assertTrue(verification_passed(batch,attempts))
        attempts[-1]['receipt']['result_status']='invalid_response'
        self.assertFalse(verification_passed(batch,attempts))

    def test_response_observer_preserves_original_transport_result_and_private_bytes(self):
        from cj_api import real_services
        from datetime import datetime,timezone
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);batch={'provider_responses':[]};state=root/'batch.json'
            now=datetime(2026,11,4,tzinfo=timezone.utc)
            request=SimpleNamespace(path='/v3/direction/walking',binding_digest='a'*64,request_ref='op-'+'b'*64,started_at=now)
            body=b'{"status":"1","info":"ok","infocode":"10000","count":"0","route":{"paths":[]}}'
            result=SimpleNamespace(state='received',response=SimpleNamespace(http_status=200,body=body,received_at=now))
            original=AsyncMock(return_value=result)
            with patch.object(real_services,'fetch_candidate',original):
                with record_place_responses(root,batch,state):
                    observed=asyncio.run(real_services.fetch_candidate('fixture-config',request,'fixture-credentials',basic=True))
                self.assertIs(real_services.fetch_candidate,original)
            self.assertIs(observed,result);original.assert_awaited_once()
            saved=root/batch['provider_responses'][0]['file']
            self.assertEqual(saved.read_bytes(),body);self.assertEqual(saved.stat().st_mode&0o777,0o600)
            self.assertEqual(batch['provider_responses'][0]['response_sha256'],hashlib.sha256(body).hexdigest())
            self.assertNotIn('fixture-credentials',state.read_text())

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
