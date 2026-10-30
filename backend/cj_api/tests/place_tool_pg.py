"""Actual accepted MESSAGE -> model/tool/model -> PLACE readback; synthetic data."""
import json,os,sys,time
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import app_from_environment,LocalDatabase,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.local_tools import LocalTools,SyntheticToolModel
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode
from cj_usage.core import Meter
import local_history_pg as harness
sys.path.insert(0,str(harness.ROOT/'scripts'))
import local_run_context as operator


def exercise(auth,conninfo):
    import run_worker
    subjects=['alice','bob','steps','tools','output','revoke','deadline','cancel','missing','rate','malformed']
    harness.dev_auth.init(auth,subjects)
    now=int(time.time())
    def profile(subject,steps=8,tools=2,output=8000):
        value={'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=10,
            period_start=now-60,period_end=now+3600,max_steps=steps,max_tools=tools,max_output=20000,max_seconds=600),
            'output_limits':{'model':4000,'tool':output,'memory':1000}},'history':[]}
        path=auth.parent/(subject+'.json');path.write_text(json.dumps(value));return path,load_run_context(path)
    profiles={s:profile(s,steps=1 if s=='steps' else 8,tools=1 if s=='tools' else 2,output=16 if s=='output' else 8000) for s in subjects}
    for subject,(path,context) in profiles.items():operator.provision_budget(conninfo,context,subject)
    headers={s:{'Authorization':'Bearer '+harness.dev_auth.token(auth,s,30)} for s in subjects}
    config=json.loads(conninfo.read_text())
    def api(subject):
        with patch.dict(os.environ,{'CJ_LOCAL_AUTH_DIR':str(auth),'CJ_LOCAL_CONNINFO':str(conninfo),
            'CJ_LOCAL_RUN_CONTEXT':str(profiles[subject][0])}):return TestClient(app_from_environment())
    def send(client,subject,mid,text):
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':mid},headers=headers[subject]))
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=mid,message_id=mid,text=text,trip_id=None,
            creation_intent='none',expected_generation=chat['generation'],expected_sequence=0)).encode()
        return harness.expect(client.post('/v1/messages',content=raw,headers={**headers[subject],'Content-Type':'application/octet-stream'}))['receipt']
    def host(subject,model,tools):
        return run_worker._worker_for_scope(LocalDatabase(conninfo,run_context=profiles[subject][1]),model,auth,
            scope_for(ISSUER,subject),checker_for(auth),tools_configuration=tools)
    with api('alice') as client:
        receipt=send(client,'alice','search','请查询合成城市的合成酒店 / Find synthetic hotel')
        tools=LocalTools();model=SyntheticToolModel();worker=host('alice',model,tools)
        outcome=worker.process()[0]
        assert outcome.status=='completed' and model.calls==2
        assert tools.place.invocations==tools.place.transport_calls==1
        display=harness.expect(client.get('/v1/run-display',params={'message_id':'search'},headers=headers['alice']))
        frames=[json.loads(line) for line in display['snapshot']['text'].splitlines()]
        assert [f['version'] for f in frames]==['TOOL-output.1','TOOL-answer.1']
        value=frames[0]['result']
        assert frames[0]['data_origin']=='synthetic' and value['version']=='PLACE-result.1'
        assert [p['provider_id'] for p in value['places']]==['SYNTH_EAST','SYNTH_WEST']
        assert value['source']['evidence_kind']=='synthetic' and frames[1]['text_zh'] and frames[1]['text_en']
        harness.expect(client.get('/v1/run-display',params={'message_id':'search'},headers=headers['bob']),503)
        assert host('alice',model,tools).process()==[] and model.calls==2 and tools.place.invocations==1
        route=send(client,'alice','route','查询合成路线 / synthetic route')
        assert worker.process()[0].status=='completed'
        route_display=harness.expect(client.get('/v1/run-display',params={'message_id':'route'},headers=headers['alice']))
        routed=json.loads(route_display['snapshot']['text'].splitlines()[0])['result']
        assert routed['routes'][0]['query']==routed['query'] and routed['routes'][0]['duration']['value']['unit']=='s'
    for subject,keyword,outcome in [('missing','SYNTH_MISSING','no_results'),('rate','SYNTH_RATE_LIMIT','rate_limited'),('malformed','SYNTH_BAD_JSON','invalid_response')]:
        with api(subject) as client:
            send(client,subject,subject,keyword)
            tools=LocalTools();model=SyntheticToolModel();worker=host(subject,model,tools)
            assert worker.process()[0].status=='completed' and model.calls==2 and tools.place.invocations==1
            display=harness.expect(client.get('/v1/run-display',params={'message_id':subject},headers=headers[subject]))
            frames=[json.loads(line) for line in display['snapshot']['text'].splitlines()]
            assert frames[0]['result']['outcome']==outcome and frames[0]['result']['places']==[]
            assert ('no results' in frames[1]['text_en']) if outcome=='no_results' else (outcome in frames[1]['text_en'] and '待核实' in frames[1]['text_zh'])
            assert 'SYNTHETIC_PRIVATE_SUPPLIER_BODY' not in display['snapshot']['text']
    # Actual Core refusal, not a callback counter or producer-wide disable switch.
    for subject in ('steps','output'):
        with api(subject) as client:
            send(client,subject,subject,'查询合成酒店')
            tools=LocalTools();model=SyntheticToolModel();worker=host(subject,model,tools)
            assert worker.process()[0].status=='failed'
            status=harness.expect(client.get('/v2/run-draft-status',params={'message_id':subject},headers=headers[subject]))
            assert status['budget_exhausted_stage']=='answer'
            assert model.calls==1
            assert tools.place.invocations==(0 if subject=='steps' else 1)
    with api('tools') as client:
        send(client,'tools','tools','查询合成酒店')
        class DoubleToolModel(SyntheticToolModel):
            def stream(self,messages,system=None):
                for chunk in super().stream(messages,system=system):
                    value=json.loads(chunk)
                    if value.get('kind')=='tool':value['calls']*=2
                    yield json.dumps(value,ensure_ascii=False)
        tools=LocalTools();model=DoubleToolModel();worker=host('tools',model,tools)
        assert worker.process()[0].status=='failed' and model.calls==1 and tools.place.invocations==1
        status=harness.expect(client.get('/v2/run-draft-status',params={'message_id':'tools'},headers=headers['tools']))
        assert status['budget_exhausted_stage']=='answer'
    with api('revoke') as client:
        receipt_revoke=send(client,'revoke','revoke','查询合成酒店')
        tools=LocalTools();model=SyntheticToolModel();worker=host('revoke',model,tools)
        original=tools.place.prepare_call
        def revoke_after_preparation(query,request_ref):
            invoke=original(query,request_ref)
            (auth/'invited.json').write_text(json.dumps([s for s in subjects if s!='revoke']))
            return invoke
        tools.place.prepare_call=revoke_after_preparation
        try:
            assert worker.process()[0].status=='context_invalid'
        finally:(auth/'invited.json').write_text(json.dumps(subjects))
        assert model.calls==1 and tools.place.invocations==0
    with api('deadline') as client:
        send(client,'deadline','deadline','查询合成酒店')
        from cj_api.local_worker_context import LocalBudgetRouter
        original_resolve=LocalBudgetRouter._resolve_original
        offset=[0]
        def timed_resolve(router,binding,state):
            exit=original_resolve(router,binding,state);exit.clock=lambda:time.time()+offset[0];return exit
        tools=LocalTools();model=SyntheticToolModel();worker=host('deadline',model,tools)
        original=tools.place.prepare_call
        def delayed_preparation(query,request_ref):
            invoke=original(query,request_ref);offset[0]=601;return invoke
        tools.place.prepare_call=delayed_preparation
        with patch.object(LocalBudgetRouter,'_resolve_original',timed_resolve):
            assert worker.process()[0].status=='failed'
        assert model.calls==1 and tools.place.invocations==0
    with api('cancel') as client:
        send(client,'cancel','cancel','查询合成酒店')
        class CancellingModel(SyntheticToolModel):
            def stream(self,messages,system=None):
                if messages[-1]['role']!='tool':
                    yield from super().stream(messages,system=system);return
                self.calls+=1
                yield '{'
                value=harness.expect(client.post('/v1/run-cancellations',json={'version':'RUN-cancel.1','message_id':'cancel'},headers=headers['cancel']))
                assert value['status']=='cancelled'
                yield 'SYNTHETIC_LATE_MODEL_ANSWER'
        tools=LocalTools();model=CancellingModel();worker=host('cancel',model,tools)
        assert worker.process()[0].status=='cancelled' and tools.place.invocations==1 and model.calls==2
        display=harness.expect(client.get('/v1/run-display',params={'message_id':'cancel'},headers=headers['cancel']))
        assert [json.loads(line)['version'] for line in display['snapshot']['text'].splitlines()]==['TOOL-output.1']
    with psycopg.connect(**config) as admin:
        rows=admin.execute('SELECT kind,operation_key FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key',
            (scope_for(ISSUER,'alice'),receipt['run_id'])).fetchall()
        assert rows==[('model','model.tool_turn.0'),('model','model.tool_turn.1'),('tool','tool.0.0')],rows
        for subject in ('alice','steps','output','revoke','deadline','cancel'):
            account=ledger_scope_for(scope_for(ISSUER,subject),profiles[subject][1].current.meter)
            ledger=decode(admin.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
            assert Meter.exposure(ledger)>0
            if subject in ('revoke','deadline'):assert Meter.exposure(ledger)==2
            if subject=='cancel':assert Meter.exposure(ledger)==3
    print('PASS actual signed MESSAGE/model-tool-model/Meter/PLACE/source readback, route/query identity, owner, stable ops/no redispatch, step/output denial; all data synthetic, real services UNRUN')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
