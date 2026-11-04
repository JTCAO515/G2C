import json
from hashlib import sha256
import os
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('CJ_ENV','local')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smoke import cases, check, require_full_ready
from real_budget import estimate
from cj_agent.provider import M4_BASE, M4_MODEL


def evidence(case, language='zh'):
    run='original-'+case['id']+'-'+language;mid='message-'+run;answer='Actual fixture body'
    ops=[];attempts=[]
    def model(n,messages):
        aid=run+'-model-'+str(n)
        ops.append(dict(run_id=run,operation_key='model.tool_turn.'+str(n),registration_id='model.tool_turn',
                        attempt_id=aid,input=dict(messages=messages)))
        attempts.append(dict(attempt_id=aid,kind='model',state='RECEIVED',receipt=dict(
            model_id=M4_MODEL,endpoint=M4_BASE,region='cn-beijing',receipt_sha256=sha256(aid.encode()).hexdigest(),
            usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))))
    model(0,[dict(role='user',content=case['inputs'][language])])
    messages=[]
    endpoints=dict(place='https://restapi.amap.com/v3/place/text',route='https://restapi.amap.com/v3/direction/walking',
                   weather='https://restapi.amap.com/v3/weather/weatherInfo',fact='https://en.nia.gov.cn/')
    for n,kind in enumerate(case['required']):
        aid=run+'-tool-'+str(n)
        ops.append(dict(run_id=run,operation_key='tool.0.'+str(n),registration_id='tool.'+('place' if kind=='route' else kind),
                        attempt_id=aid,input={}))
        result='ok' if kind in ('place','route') else 'unknown' if kind=='fact' else 'observed'
        attempts.append(dict(attempt_id=aid,kind=kind,state='RECEIVED',receipt=dict(endpoint=endpoints[kind],result_status=result)))
        if kind=='fact':
            messages.append(dict(role='tool',content=json.dumps(dict(tool='fact',result=dict(source_url=endpoints[kind],
                original_bytes=42,original_sha256='a'*64,excerpts=['Synthetic official excerpt'],status='unknown')))))
    model(1,messages)
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
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'raw').mkdir();fixed=cases('2026-11-04')
            plan=dict(candidate_id='candidate',source_date='2026-11-04',planned_n=6,cases=fixed,batch_id='round2-smoke')
            rows=[]
            for c in fixed:
                for lang in ('zh','en'):
                    ref='raw/'+c['id']+'-'+lang+'.json';(p/ref).write_text(json.dumps(evidence(c,lang)))
                    rows.append(dict(case_id=c['id'],language=lang,raw_evidence_ref=ref))
            (p/'plan.json').write_text(json.dumps(plan));(p/'observations.json').write_text(json.dumps(rows))
            (p/'summary.json').write_text('{"status":"PASS"}')
            require_full_ready(p,'candidate')
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

    def test_first_round_based_estimate_and_equality_stop(self):
        previous=[dict(kind='model')]*166+[dict(kind='place')]*17+[dict(kind='weather')]*57+[dict(kind='fact')]*10
        r=estimate(previous,include_smoke=True)
        self.assertEqual(r['projected_conservative_cny'],dict(model=332,tool=136))
        self.assertTrue(r['within_stop_lines'])
        self.assertFalse(estimate(previous+[dict(kind='model')]*68,include_smoke=True)['within_stop_lines'])
        self.assertFalse(estimate(previous+[dict(kind='weather')]*24,include_smoke=True)['within_stop_lines'])


if __name__=='__main__':unittest.main()
