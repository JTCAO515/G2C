import json
from hashlib import sha256
import os
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import sqlite3

os.environ.setdefault('CJ_ENV','local')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smoke import cases, check, require_full_ready, model_input_digest
from real_budget import estimate, verified_journal
import real_budget
import real_phase
import smoke
from cj_api.real_services import canonical_tool, TOOL_SYSTEM, TOOLS
from cj_agent.provider import M4_BASE, M4_MODEL
from cj_place.models import (Result, Source, Outcome, Observed, FieldState, Place, Coordinate, Route)
from cj_place.contract_v1 import decode_query, encode_result
from datetime import datetime, timezone
from cj_usage.authorization_budget import canonical


def evidence(case, language='zh'):
    run='original-'+case['id']+'-'+language;mid='message-'+run;answer='Actual fixture body'
    ops=[];attempts=[]
    def model(n,messages):
        aid=run+'-model-'+str(n)
        inputs=dict(messages=deepcopy(messages),system=TOOL_SYSTEM,
                    native_tools=[t for t in TOOLS if t['function']['name'] in case['native']])
        ops.append(dict(run_id=run,operation_key='model.tool_turn.'+str(n),registration_id='model.tool_turn',
                        attempt_id=aid,input=inputs))
        attempts.append(dict(attempt_id=aid,kind='model',input_sha=model_input_digest(inputs),state='RECEIVED',receipt=dict(
            model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',receipt_sha256=sha256(aid.encode()).hexdigest(),
            usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))))
    model(0,[dict(role='user',content=case['inputs'][language])])
    calls=[];results=[]
    endpoints=dict(place='https://restapi.amap.com/v3/place/text',route='https://restapi.amap.com/v3/direction/walking',
                   weather='https://restapi.amap.com/v3/weather/weatherInfo',fact='https://en.nia.gov.cn/')
    for n,kind in enumerate(case['required']):
        aid=run+'-tool-'+str(n)
        native={'place':'place_search','route':'place_route','weather':'weather','fact':'fact'}[kind]
        arguments=(dict(keyword='FixturePOI',city='Beijing',page=1,page_size=1) if kind=='place' else
            dict(origin_provider_id='p1',origin_coordinate='116.1,39.1',origin_coordinate_role='poi_center',
                 destination_provider_id='p2',destination_coordinate='116.2,39.2',destination_coordinate_role='poi_center',mode='walking') if kind=='route'
            else dict(start_date='2026-11-05',end_date='2026-11-05'))
        name,query=canonical_tool(native,json.dumps(arguments).encode())
        tool_input=dict(name=name,query=json.loads(query),request_ref=aid,synthetic_only=True,
                        place_profile='basic-v3-default-zh' if name=='place' else None)
        ops.append(dict(run_id=run,operation_key='tool.0.'+str(n),registration_id='tool.'+('place' if kind=='route' else kind),
                        attempt_id=aid,input=tool_input))
        result='ok' if kind in ('place','route') else 'unknown' if kind=='fact' else 'observed'
        attempts.append(dict(attempt_id=aid,kind=kind,state='RECEIVED',
            input_sha=sha256(json.dumps(tool_input,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
            receipt=dict(endpoint=endpoints[kind],result_status=result)))
        calls.append(dict(id=aid,type='function',function=dict(name=native,arguments=json.dumps(arguments))))
        data=dict(source_url=endpoints[kind],status=result)
        if kind=='fact':data.update(original_bytes=42,original_sha256='a'*64,excerpts=['Synthetic official excerpt'])
        if kind in ('place','route'):
            q=decode_query(query);now=datetime(2026,11,4,tzinfo=timezone.utc)
            source=Source(endpoints[kind],now,now,aid,'b'*64,'unverified_bytes')
            missing=Observed(FieldState.MISSING)
            p=Place('p1','Synthetic POI',missing,Observed(FieldState.PRESENT,Coordinate('116.1,39.1')),
                    missing,missing,missing,missing,missing)
            value=Result(Outcome.OK,q,'provider_ok',source,places=(p,) if kind=='place' else (),
                         routes=(Route(q,Observed(FieldState.UNKNOWN),Observed(FieldState.UNKNOWN)),) if kind=='route' else (),
                         provider_code='10000',provider_count=1)
            wire=encode_result(value,evidence_kind='live_provider');data=json.loads(wire)
        else:wire=canonical(data)
        attempts[-1]['receipt']['response_sha256']=sha256(wire).hexdigest()
        results.append(dict(role='tool',tool_call_id=aid,content=json.dumps(dict(tool=name,result=data))))
    model(1,[dict(role='assistant',content=None,tool_calls=calls),*results])
    snapshot=dict(run_id=run,message_id=mid,status='completed',text_state='complete',text=answer)
    return dict(input_sha256=sha256(case['inputs'][language].encode()).hexdigest(),observed=dict(message_receipt=dict(run_id=run,message_id=mid),runtime_role='cj_m1_runtime',
        foreign_message_rows=0,foreign_mutations=0,formal_trip_count=0,memory_item_count=0),
        answer=answer,outcomes=[dict(run_id=run,message_id=mid,status='completed')],
        events=[dict(data=snapshot)],operations=ops,authorization_attempts=attempts)


class SmokeChecks(unittest.TestCase):
    def test_all_four_tool_flows_need_real_receipt_and_continuation(self):
        for c in cases('2026-11-04'):
            self.assertEqual(check(c,evidence(c))['status'],'PASS')

    def test_model_only_answer_cannot_pass_tool_smoke(self):
        c=cases('2026-11-04')[0];e=evidence(c)
        e['operations']=[v for v in e['operations'] if v['registration_id']=='model.tool_turn']
        self.assertEqual(check(c,e)['status'],'FAIL')

    def test_unknown_tool_or_followup_receipt_blocks_even_completed_body(self):
        c=cases('2026-11-04')[0]
        for aid in ('tool-0','model-1'):
            e=evidence(c)
            next(v for v in e['authorization_attempts'] if v['attempt_id'].endswith('-'+aid)).update(state='INTENT',receipt=None)
            self.assertEqual(check(c,e)['status'],'FAIL')

    def test_unknown_run_empty_body_or_foreign_snapshot_cannot_pass(self):
        c=cases('2026-11-04')[1]
        for mutation in ('run','body','owner'):
            e=evidence(c)
            if mutation=='run':e['outcomes'][0]['status']='unknown'
            elif mutation=='body':e['answer']='Source: https://example.com\n'
            else:e['events'][0]['data']['run_id']='foreign-run'
            self.assertEqual(check(c,e)['status'],'FAIL')

    def test_fact_unknown_applicability_requires_actual_excerpts(self):
        c=cases('2026-11-04')[2];e=evidence(c)
        self.assertEqual(check(c,e)['status'],'PASS')
        e['operations'][-1]['input']['messages']=[]
        self.assertEqual(check(c,e)['status'],'FAIL')

    def test_full_start_recomputes_all_six_instead_of_trusting_summary_PASS(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'PHASES',Path(folder)/'canonical'):
            p=Path(folder)/'out';p.mkdir();(p/'raw').mkdir();fixed=cases('2026-11-04')
            plan=dict(candidate_id='candidate',source_date='2026-11-04',planned_n=6,cases=fixed,batch_id='round2-smoke')
            rows=[]
            for c in fixed:
                for lang in ('zh','en'):
                    ref='raw/'+c['id']+'-'+lang+'.json';(p/ref).write_text(json.dumps(evidence(c,lang)))
                    rows.append(dict(case_id=c['id'],language=lang,raw_evidence_ref=ref))
            (p/'plan.json').write_text(json.dumps(plan));(p/'observations.json').write_text(json.dumps(rows))
            (p/'summary.json').write_text('{"status":"PASS"}')
            real_phase.claim('smoke',p,'candidate');real_phase.finish_smoke(p,'candidate','PASS')
            actual=[a for c in fixed for l in ('zh','en') for a in evidence(c,l)['authorization_attempts']]
            with patch('smoke.verified_journal',return_value=[]):
                with self.assertRaises(ValueError):require_full_ready(p,'candidate')
            with patch('smoke.verified_journal',return_value=actual):require_full_ready(p,'candidate')
            with self.assertRaises(ValueError):require_full_ready(p,'other-candidate')
            (p/'observations.json').write_text(json.dumps(rows[:-1]))
            with self.assertRaises(ValueError):require_full_ready(p,'candidate')
            (p/'observations.json').write_text(json.dumps(rows))
            (p/rows[1]['raw_evidence_ref']).write_text(json.dumps(evidence(fixed[0],'zh')))
            with self.assertRaises(ValueError):require_full_ready(p,'candidate')
            (p/rows[1]['raw_evidence_ref']).write_text(json.dumps(evidence(fixed[0],'en')))
            e=evidence(fixed[0]);e['outcomes'][0]['status']='unknown'
            (p/rows[0]['raw_evidence_ref']).write_text(json.dumps(e))
            with self.assertRaises(ValueError):require_full_ready(p,'candidate')

    def test_tool_receipts_without_tool_messages_do_not_pass(self):
        c=cases('2026-11-04')[1];e=evidence(c)
        e['operations'][-1]['input']['messages']=[]
        self.assertEqual(check(c,e)['status'],'FAIL')

    def test_tool_result_loss_cannot_pass_with_an_actual_model_hash_of_empty_result(self):
        for c in cases('2026-11-04')[:2]:
            e=evidence(c);follow=e['operations'][-1]
            message=next(v for v in follow['input']['messages'] if v['role']=='tool')
            value=json.loads(message['content']);value['result']={};message['content']=json.dumps(value)
            e['authorization_attempts'][-1]['input_sha']=model_input_digest(follow['input'])
            verdict=check(c,e)
            self.assertEqual(verdict['status'],'FAIL')
            self.assertIn('actual_tool_response_changed_before_followup_model',verdict['reasons'])

    def test_missing_or_rolled_back_original_history_never_creates_new_budget(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_budget,'STATE',Path(folder)):
            p=Path(folder)/'m4-outflows.sqlite'
            with self.assertRaises(sqlite3.OperationalError):verified_journal()
            self.assertFalse(p.exists())
            with sqlite3.connect(p) as db:
                db.execute('CREATE TABLE attempt(id TEXT PRIMARY KEY,kind TEXT,input_sha TEXT,state TEXT,receipt TEXT)')
            with self.assertRaises(ValueError):verified_journal()

    def test_different_output_or_cosmetic_candidate_cannot_reclaim_same_adapter(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(real_phase,'PHASES',Path(folder)/'canonical'):
            p=Path(folder)
            self.assertTrue(real_phase.claim('smoke',p/'a','candidate1'))
            self.assertFalse(real_phase.claim('smoke',p/'b','candidate1'))
            self.assertFalse(real_phase.claim('smoke',p/'c','cosmetic2'))
            self.assertTrue(real_phase.claim('full',p/'full-a','candidate1'))
            self.assertFalse(real_phase.claim('full',p/'full-b','candidate1'))

    @patch.object(real_budget,'TOOL_STOP',160)
    def test_first_round_based_estimate_and_equality_stop(self):
        previous=[dict(kind='model')]*166+[dict(kind='place')]*17+[dict(kind='weather')]*57+[dict(kind='fact')]*10
        r=estimate(previous,include_smoke=True)
        self.assertEqual(r['projected_conservative_cny'],dict(model=332,tool=136))
        self.assertTrue(r['within_stop_lines'])
        self.assertFalse(estimate(previous+[dict(kind='model')]*68,include_smoke=True)['within_stop_lines'])
        self.assertFalse(estimate(previous+[dict(kind='weather')]*24,include_smoke=True)['within_stop_lines'])

    def test_JT_tool_stop_change_allows_161_projection_within_original_200_budget(self):
        previous=[dict(kind='model')]*200+[dict(kind='place')]*99
        r=estimate(previous,include_smoke=True)
        self.assertEqual(r['projected_conservative_cny'],dict(model=366,tool=161))
        self.assertEqual(r['stop_cny'],dict(model=400,tool=10000))
        self.assertEqual(r['budget_cny'],dict(model=500,tool=200))
        self.assertTrue(r['within_authorization'])
        self.assertEqual(r['actual_billed_total'],'UNKNOWN')

    def test_raised_stop_does_not_authorize_more_than_original_tool_total(self):
        for before,allowed in ((138,True),(139,False)):
            with self.subTest(before=before):
                r=estimate([dict(kind='route')]*before,include_smoke=True)
                self.assertTrue(r['within_stop_lines'])
                self.assertEqual(r['within_budget'],allowed)
                self.assertEqual(r['within_authorization'],allowed)

    def test_model_equality_stop_still_blocks_after_tool_stop_change(self):
        r=estimate([dict(kind='model')]*234,include_smoke=True)
        self.assertEqual(r['projected_conservative_cny']['model'],400)
        self.assertTrue(r['within_budget'])
        self.assertFalse(r['within_authorization'])

    def test_smoke_over_total_budget_stops_before_credentials_claim_or_exit(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(sys,'argv',['smoke.py','--output',str(Path(folder)/'new')]), \
                patch.dict(os.environ,{'CJ_M4_SYNTHETIC_ONLY':'1'}), \
                patch.object(smoke,'claimed',return_value=False), \
                patch.object(smoke.subprocess,'check_output',return_value='candidate'), \
                patch.object(smoke,'verified_journal',return_value=[dict(kind='route')]*139), \
                patch.object(smoke,'keychain',side_effect=AssertionError('no key read')), \
                patch.object(smoke,'claim',side_effect=AssertionError('no phase claim')), \
                patch.object(smoke,'AuthorizationBudget',side_effect=AssertionError('no budget mutation')):
            with self.assertRaisesRegex(ValueError,'exceeds_authorization'):
                smoke.main()


if __name__=='__main__':unittest.main()
