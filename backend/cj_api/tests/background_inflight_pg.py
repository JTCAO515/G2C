"""Prototype actual background ownership/revocation, no real account/provider."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sys,tempfile,threading,time
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_cleanup import Configuration,Runtime
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.local_background import LocalBackgroundHost
from cj_agent.provider import FakeProvider
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_message.source import SourceQuery
from cj_run.background_store import JobRequest
from cj_run.background import BackgroundJobs
from cj_cleanup.core import encode,digest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(Path(__file__).parent))
from background_jobs_pg import ExtractFake
import dev_auth,local_run_context,run_worker


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['bg-live'])
    now=int(time.time());quota=root/'quota.json';quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=10,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),output_limits=dict(model=3000,tool=3000,memory=3000)))))
    context=load_run_context(quota);local_run_context.provision_budget(path,context,'bg-live')
    database=LocalDatabase(path,run_context=context);token=dev_auth.token(auth,'bg-live',30)
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    registry=root/'registry.json';targets=('checkpoints/run','business/message','business/usage')
    registry.write_bytes(encode(dict(version='background-account-component',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=name,cleanup_protocol='CLEANUP@1.1') for name in ('message','usage')])])))
    options=Configuration({'bg-live':b'explicit-background-account-key-00'},'bg-live',3600,targets,registry)
    app=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,cleanup_configuration=options)
    slots=frozenset({'diet.spicy'});policy=CollectionPolicy(frozenset({'self'}),slots,10,4096,lambda entry:True,lambda entry,rows:any(entry.text==row.text for row in rows))
    memory=ManualPolicy(policy.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    collection_app=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=lambda principal:(policy,memory,lambda entry:(None,None)),run_context=context)
    host=collection_app.state.memory_history;collection=host.service
    entered,release=threading.Event(),threading.Event();errors=[]
    class Blocking(ExtractFake):
        def stream(self,messages,system=None):
            raw=next(super().stream(messages,system));half=len(raw)//2
            yield raw[:half]
            entered.set()
            if not release.wait(30):raise AssertionError('prototype provider gate timed out')
            yield raw[half:]
    model=Blocking();jobs=BackgroundJobs(database=host.database,boundary=host.boundary,collection=collection,max_payload_bytes=262144)
    with TestClient(app) as client:
        def post(url,value,scheme='Bearer',credential=token):
            response=client.post(url,content=encode(value),headers={'Authorization':scheme+' '+credential,'Content-Type':'application/octet-stream'})
            assert response.status_code==200,('HTTP status',response.status_code)
            return response.json()
        head=client.put('/v1/conversations',params={'conversation_id':'live'},headers=headers).json()
        post('/v1/messages',dict(version='MESSAGE-send.1',conversation_id='live',message_id='m0',text='No spicy food',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0))
        run_worker.run_once(database,FakeProvider(),auth)
        collection.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='live',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        source=dict(conversation_id='live',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        collection.enqueue(token,encode(dict(version='MEMORY-JOBS@1',job_id='live-job',attempt_id='original-attempt',source=source)))
        collection.transition(token,'live-job','original-attempt','inflight')
        prepared=collection.prepare_model_input(token,'live-job','original-attempt',max_payload_bytes=262144)
        original=jobs.prepare(token,JobRequest('live-job','original-attempt',SourceQuery(**source),None,prepared))
        device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id='live-device',state_ref=digest(b'live-device')))
        operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id']))
        def worker():
            try:run_worker.run_once(database,model,auth,background_jobs=LocalBackgroundHost(jobs,auth))
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=worker);thread.start()
        try:
            assert entered.wait(20),errors
            value=post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
            assert value['reason']=='original_tasks_not_yet_stopped' and thread.is_alive()
            call=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=device['binding_id'],reason='session_invalid'),'Device',device['device_token'])
            post('/v1/cleanup-device-receipts',dict(version='CLEANUP-DEVICE@1',action_id='report',operation_id=operation['operation_id'],invocation_id=call['call']['invocation_id'],binding_id=device['binding_id'],request_digest=call['request_digest'],outcome='confirmed'),'Cleanup',call['receipt_token'])
            owner=scope_for(ISSUER,'bg-live')
            def retained():
                with psycopg.connect(**config) as conn:
                    return (conn.execute('SELECT count(*) FROM cj_run_background_job WHERE scope=%s',(owner,)).fetchone()[0],
                            conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchone()[0],
                            conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(owner,)).fetchone()[0])
            assert retained()==(1,1,0) and model.calls==1
            release.set();thread.join(20);assert not thread.is_alive()
            assert retained()==(1,1,0) and model.calls==1
            runtime=Runtime(database,options,scope_for);claims=runtime.issuer.verify(operation['progress_token'],purpose='progress',operation_id=operation['operation_id'])
            progress=runtime.host_gateway(checker_for(auth)).resume(claims.subject_digest,operation['operation_id'])
            assert progress['status']=='unknown' and progress['reason']=='original_usage_outcome_unresolved'
            assert retained()==(1,1,0)
            print('PASS PROTOTYPE actual BG physical lease blocks cleanup/device continuation; fence rejects late output; original unknown billing/data retained after worker exits')
        finally:
            release.set();thread.join(20);assert not thread.is_alive()


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='bg-inflight-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
