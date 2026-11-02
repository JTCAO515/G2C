"""#15 real signed API/runtime-role PG/original run_once/FakeProvider, local only."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_cleanup.core import Scope,digest,encode
from cj_cleanup.registry import freeze
from cj_cleanup.store import Store
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.hooks_v1_1 import Selection
from cj_feedback.lifecycle import FeedbackHook,scope_digest
from cj_feedback.lifecycle import bind_runtime,check_current
from cj_feedback.boundary import Boundary as FeedbackBoundary
from cj_feedback.domain import Unavailable as FeedbackUnavailable

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker,migrate


def exercise(auth,conninfo):
    config=json.loads(conninfo.read_text());dev_auth.init(auth,['alice','bob','projection'])
    now=int(time.time());profile=auth.parent/'run.json'
    profile.write_text(json.dumps({'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=20,
        period_start=now-10,period_end=now+3600,max_steps=20,max_tools=10,max_output=10000,max_seconds=600),
        'output_limits':{'model':2000,'tool':2000,'memory':2000}},'history':[]}))
    context=load_run_context(profile)
    for subject in ('alice','bob'):local_run_context.provision_budget(conninfo,context,subject)
    tokens={s:dev_auth.token(auth,s,30) for s in ('alice','bob','projection')}
    headers={s:{'Authorization':'Bearer '+t,'Content-Type':'application/octet-stream'} for s,t in tokens.items()}
    env=dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(profile))
    database=LocalDatabase(conninfo,run_context=context)
    with patch.dict(os.environ,env),TestClient(app_from_environment()) as client:
        def expect(response,status=200):
            assert response.status_code==status,(response.status_code,response.text)
            return response.json()
        def post(action,subject='alice',status=200):
            raw=json.dumps(action,ensure_ascii=False,separators=(',',':')).encode()
            return expect(client.post('/v1/feedback',content=raw,headers=headers[subject]),status),raw
        head=expect(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['alice']))
        message=dict(version='MESSAGE-send.1',conversation_id='chat',message_id='answer',text='PRIVATE_INPUT_NOT_COPIED',trip_id=None,
            creation_intent='none',expected_generation=head['generation'],expected_sequence=0)
        receipt=expect(client.post('/v1/messages',content=json.dumps(message).encode(),headers=headers['alice']))['receipt']
        model=FakeProvider();run_worker.run_once(database,model,auth);assert model.calls==1
        action=dict(action_id='feedback1',problem='站名错误 / Wrong station',expectation='核对名称 / Check name',
            references=[dict(kind='message',id=receipt['message_id']),dict(kind='run',id=receipt['run_id'])])
        submitted,raw=post(action);original=submitted['receipt']
        assert original['status']=='submitted' and original['source']['run_status_at_read']=='completed'
        assert original['input_sha256']==digest(raw)
        assert post(action)[0]['receipt']==original
        assert expect(client.get('/v1/feedback-action-receipts?action_id=feedback1',headers=headers['alice']))['receipt']==original
        assert expect(client.get('/v1/feedback-action-receipts?action_id=feedback1',headers=headers['bob']))['receipt'] is None
        post(dict(action,action_id='foreign'),'bob',503)
        post(dict(action,references=[dict(kind='memory',id='not-implemented')]),status=400)
        post(dict(action,problem='different'),status=409)
        general,_=post(dict(action,action_id='general',references=[]),'bob')
        assert general['receipt']['source'] is None
        print('PASS FEEDBACK@1.0 actual signed/runtime PG submit→original receipt, exact-byte idempotence/conflict, own source, cross-owner/memory rejection, general Memory-page form')
        locator=expect(client.get('/internal/v1/feedback-diagnostics?action_id=feedback1',headers=headers['alice']))
        current=locator['current_locator']
        assert current['message_version']=='MESSAGE-send.1' and current['status']=='completed'
        assert current['registered_source_abi']=='RUN-USAGE-OPERATIONS@1'
        assert current['operations'] and current['operations'][0]['registration_id']=='model.answer'
        assert current['first_recorded_at'] and current['last_recorded_at'] and current['run_event_interval_seconds']>=0
        assert locator['external_model_version'] is None and locator['references_are_execution_proof'] is False
        assert 'PRIVATE_INPUT_NOT_COPIED' not in json.dumps(locator)
        expect(client.get('/internal/v1/feedback-diagnostics?action_id=feedback1',headers=headers['bob']),503)
        with psycopg.connect(**config) as conn:
            row=conn.execute('SELECT original_input,source_reference FROM cj_feedback_action WHERE scope=%s AND action_id=%s',
                             (scope_for(ISSUER,'alice'),'feedback1')).fetchone()
            assert bytes(row[0])==raw and 'PRIVATE_INPUT_NOT_COPIED' not in json.dumps(row[1])
        print('PASS current persisted protocol/registration/attempt/stage/timing locator, unknown external metadata, no copied message/tool payload or foreign diagnostic')
        principal=checker_for(auth).check(tokens['alice']).principal
        subject=digest(encode(asdict(Scope.from_principal('local',principal))))
        connect=lambda:psycopg.connect(**dict(config,user='cj_local_cleanup'))
        store=Store(connect,subject,lambda stage:None)
        target='business/feedback-private-actions';scope=scope_for(ISSUER,'alice')
        registry=encode(dict(version='feedback-local-proof',stores=[dict(id='business',objects=[dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1',objects=['cj_feedback_action','cj_feedback_scope'])])]))
        frozen=freeze(registry,(target,),versions=('CLEANUP@1.1',))
        # P1 regression: real retirement after query COMMIT, before final encoding.
        projected,_=post(dict(action,action_id='projection-original',references=[]),'projection')
        projector=checker_for(auth);p=projector.check(tokens['projection']).principal
        projection_subject=digest(encode(asdict(Scope.from_principal('local',p))))
        projection_scope=scope_for(ISSUER,'projection')
        projection_store=Store(connect,projection_subject,lambda stage:None)
        projection_host=Coordinator(projection_store,lambda:frozen,{target:FeedbackHook(projection_store,projection_scope)})
        projection_host.create('retire-during-projection',digest(b'projection test confirmation'),'account',
            {target:{'domain_scope':projection_scope,'selection':{'kind':'account'}}})
        projection_request=projection_host.request('retire-during-projection',target,projection_scope,Selection('account'))
        boundary=FeedbackBoundary(projector,lambda principal:(lambda:database.connect(scope_for(principal.issuer,principal.subject)),scope_for(principal.issuer,principal.subject)),
            scope_binder=bind_runtime,scope_current=check_current)
        def retire_after_query(op):
            read=op.query_action('projection-original')
            assert projection_host.advance(projection_request)['status']=='complete'
            return encode(asdict(read))
        try:boundary.with_operation(tokens['projection'],retire_after_query)
        except FeedbackUnavailable:pass
        else:raise AssertionError('retired scope published an old receipt after query COMMIT')
        print('PASS P1 regression: actual retirement after query COMMIT/inside projection withholds final private receipt')
        host=Coordinator(store,lambda:frozen,{target:FeedbackHook(store,scope)})
        host.create('delete-feedback',digest(b'original explicit local test confirmation'),'account',
                    {target:{'domain_scope':scope,'selection':{'kind':'account'}}})
        request=host.request('delete-feedback',target,scope,Selection('account'))
        # A writer already inside the same scope lock must settle before erasure.
        writer=database.connect(scope);writer.__enter__()
        try:
            writer.execute('SELECT retired FROM cj_feedback_scope WHERE scope_digest=%s FOR UPDATE',(scope_digest(scope),))
            with ThreadPoolExecutor(max_workers=1) as pool:
                cleanup=pool.submit(host.advance,request)
                deadline=time.monotonic()+5;blocked=False
                while time.monotonic()<deadline:
                    with psycopg.connect(**config) as inspect:
                        blocked=inspect.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE usename='cj_local_cleanup' AND wait_event_type='Lock')").fetchone()[0]
                    if blocked:break
                    time.sleep(.01)
                assert blocked and not cleanup.done(),'cleanup did not wait for original writer'
                pending=json.dumps(dict(action,action_id='inflight',references=[])).encode()
                writer.execute("INSERT INTO cj_feedback_action(scope,operation,action_id,original_input,input_sha256) VALUES(%s,'submit','inflight',%s,%s)",(scope,pending,digest(pending)))
                writer.__exit__(None,None,None);writer=None
                assert cleanup.result(timeout=10)['status']=='complete'
        finally:
            if writer is not None:writer.__exit__(RuntimeError,RuntimeError('test aborted'),None)
        assert host.advance(request)['status']=='complete'
        assert host.reconcile(request)['status']=='complete'
        post(dict(action,action_id='late'),status=503)
        post(action,status=503)
        post(dict(action,action_id='bob-still-active',references=[]),'bob')
        with psycopg.connect(**config) as conn:
            assert conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(scope,)).fetchone()[0]==0
            assert conn.execute('SELECT retired FROM cj_feedback_scope WHERE scope_digest=%s',(scope_digest(scope),)).fetchone()==(True,)
            assert conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(scope_for(ISSUER,'bob'),)).fetchone()[0]==2
        with database.connect(scope) as conn:
            try:conn.execute('INSERT INTO cj_feedback_action(scope,operation,action_id,original_input,input_sha256) VALUES(%s,\'submit\',\'raw-late\',%s,%s)',(scope,b'late',digest(b'late')))
            except psycopg.Error:pass
            else:raise AssertionError('retired raw runtime writer resurrected feedback')
        try:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),32)
        except psycopg.Error:pass
        else:raise AssertionError('down erased feedback fence')
        print('PASS actual feedback hook same original invocation/result, physical erasure plus irreversible fence, API/raw late writer refused, other account preserved, nonempty down refused')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-feedback-auth-') as temp:
        exercise(Path(temp)/'auth',Path(os.environ['CJ_E2E_CONNINFO']))
