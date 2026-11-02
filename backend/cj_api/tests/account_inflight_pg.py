"""Regression for #433 P1: actual busy worker cannot be erased by a device ACK."""
from dataclasses import asdict
import json,os,sys,tempfile,threading,time
from pathlib import Path
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for
from cj_api.local_cleanup import Configuration,Runtime
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for,account_checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_cleanup.core import encode,digest,Scope
from cj_agent.provider import FakeProvider
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker

def exercise(root,config,path):
    work=root/'repro';work.mkdir();auth=work/'auth';dev_auth.init(auth,['active-worker'])
    now=int(time.time());rp=work/'run.json'
    rp.write_text(json.dumps({'version':'CJ-LOCAL-RUN@2','current':{'meter':dict(unit='provider_call',budget=20,period_start=now-60,period_end=now+3600,max_steps=20,max_tools=10,max_output=10000,max_seconds=600),'output_limits':{'model':2000,'tool':2000,'memory':2000}},'history':[]}))
    context=load_run_context(rp);local_run_context.provision_budget(path,context,'active-worker')
    targets=('checkpoints/run','business/message','business/usage')
    reg=work/'registry.json';reg.write_bytes(encode(dict(version='review-repro',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),dict(id='business',objects=[dict(id=x,cleanup_protocol='CLEANUP@1.1') for x in ('message','usage')])])))
    options=Configuration({'review':b'local-review-only-synthetic-key-00'},'review',3600,targets,reg)
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,cleanup_configuration=options)
    database=LocalDatabase(path,run_context=context)
    headers={'Authorization':'Bearer '+dev_auth.token(auth,'active-worker',30),'Content-Type':'application/octet-stream'}
    independent=account_checker_for(auth,database)
    assert independent.check(headers['Authorization'][7:]).status is AdmissionStatus.ALLOWED
    entered,release=threading.Event(),threading.Event();errors=[]
    class BlockingFake(FakeProvider):
        def stream(self,messages,system=None):
            self.calls+=1
            yield 'first'
            entered.set()
            if not release.wait(30):raise AssertionError('review gate timed out')
            yield 'late'
    provider=BlockingFake()
    def worker():
        try:run_worker.run_once(database,provider,auth)
        except BaseException as exc:errors.append(type(exc).__name__)
    def counts():
        with psycopg.connect(**config) as c:
            owner=scope_for(ISSUER,'active-worker')
            return dict(run=c.execute('SELECT count(*) FROM cj_run_record WHERE scope=%s',(owner,)).fetchone()[0],message=c.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchone()[0],unknown=c.execute("SELECT count(*) FROM cj_usage_ledger_candidate WHERE ledger::text LIKE '%unknown%'").fetchone()[0],worker_alive=thread.is_alive())
    with TestClient(app) as client:
        def post(url,body,scheme=None,cap=None):
            return client.post(url,content=encode(body),headers=headers if scheme is None else {'Authorization':scheme+' '+cap,'Content-Type':'application/octet-stream'})
        head=client.put('/v1/conversations',params={'conversation_id':'live'},headers=headers).json()
        response=post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='live',message_id='live-message',text='review active worker',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
        assert response.status_code==200,response.status_code
        device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id='own-device',state_ref=digest(b'own-device-state'))).json()
        prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id'])).json();op=prepared['operation_id']
        thread=threading.Thread(target=worker);thread.start()
        try:
            assert entered.wait(20),errors
            assert counts()['unknown']>=1 and thread.is_alive()
            response=post('/v1/account-cleanup-operations/'+op+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
            assert response.status_code==200
            assert response.json().get('reason')=='original_tasks_not_yet_stopped',response.json()
            assert independent.check(headers['Authorization'][7:]).status is AdmissionStatus.DENIED
            print('PASS key-free independent business checker sees committed retirement before any domain erase',flush=True)
            before=counts()
            response=client.get('/v1/account-cleanup-operations/'+op,headers={'Authorization':'Cleanup '+prepared['progress_token']})
            assert response.status_code==200 and response.json()['status']=='unknown'
            assert response.json()['reason']=='original_tasks_not_yet_stopped'
            assert counts()==before
            call=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=device['binding_id'],reason='session_invalid'),'Device',device['device_token']).json()
            receipt=dict(version='CLEANUP-DEVICE@1',action_id='report',operation_id=op,invocation_id=call['call']['invocation_id'],binding_id=device['binding_id'],request_digest=call['request_digest'],outcome='confirmed')
            response=post('/v1/cleanup-device-receipts',receipt,'Cleanup',call['receipt_token'])
            after=counts()
            assert response.status_code==200 and response.json()['state']=='confirmed'
            assert before['run']==1 and before['message']==1 and after==before
            gateway=Runtime(database,options,scope_for).host_gateway(checker_for(auth))
            subject=digest(encode(asdict(Scope.from_principal('local',checker_for(auth).check(headers['Authorization'][7:]).principal))))
            assert gateway.resume(subject,op)['reason']=='original_tasks_not_yet_stopped'
            assert counts()==before
            with psycopg.connect(**config) as conn:
                event_count=conn.execute('SELECT count(*) FROM cj_run_event').fetchone()[0]
            release.set();thread.join(20);assert not thread.is_alive()
            with psycopg.connect(**config) as conn:
                assert conn.execute('SELECT count(*) FROM cj_run_event').fetchone()[0]==event_count
            result=gateway.resume(subject,op)
            assert result['status']=='unknown' and result['reason']=='original_usage_outcome_unresolved'
            final=counts();assert final['run']==1 and final['message']==1 and final['unknown']>=1
            observed=client.get('/v1/account-cleanup-operations/'+op,headers={'Authorization':'Cleanup '+prepared['progress_token']})
            assert observed.status_code==200 and observed.json()['reason']==result['reason']
            assert post('/v1/feedback',dict(action_id='late',problem='late',expectation='',references=[])).status_code==503
            print('PASS real busy worker/UNKNOWN usage: confirm, GET, original device receipt and host resume preserve RUN/message/accounting; late FakeProvider cannot publish; persistent original reason survives',flush=True)
        finally:
            release.set();thread.join(20)
            assert not thread.is_alive()


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-account-inflight-') as temp:
        path=Path(os.environ['CJ_E2E_CONNINFO'])
        exercise(Path(temp),json.loads(path.read_text()),path)
