"""Registered-chain integration using C's actual filtered processing V2."""
from datetime import datetime,timedelta,timezone
import hashlib,json,os,sys,tempfile,time,subprocess
from pathlib import Path
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_background import LocalBackgroundHost,GuardedCollectionAdapterV3
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_message.source import SourceQuery
from cj_run.background_store import JobRequest
from cj_run.background import BackgroundJobsV2,JobOutcomeUnknown
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,local_run_context,run_worker,migrate


class ExtractFake(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1
        data=json.loads(messages[0]['content']);message=data['messages'][0]
        yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[dict(subject='self',slot='diet.spicy',kind='preference',
            text=message['text'],extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=message['ref'],quote=message['text'])])]),ensure_ascii=False)


def exercise(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,['bg-a','bg-b','bg-limit']);now=int(time.time())
    path=root/'run.json';path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=10,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),
        output_limits=dict(model=3000,tool=3000,memory=3000)))))
    context=load_run_context(path)
    for who in ('bg-a','bg-b'):local_run_context.provision_budget(conninfo,context,who)
    database=LocalDatabase(conninfo,run_context=context)
    token=dev_auth.token(auth,'bg-a',30);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    normal=create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context)
    with TestClient(normal) as client:
        head=client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers).json()
        for index,text in enumerate(('I do not eat spicy food','No nuts','No shellfish')):
            response=client.post('/v1/messages',content=json.dumps(dict(version='MESSAGE-send.1',conversation_id='chat',message_id='m'+str(index),
                text=text,trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index)).encode(),headers=headers)
            assert response.status_code==200
    original_model=FakeProvider();first=run_worker.run_once(database,original_model,auth)
    assert original_model.calls==3 and len(first)==3 and all(item.status=='completed' for item in first)
    slots=frozenset({'diet.spicy'})
    extraction=CollectionPolicy(frozenset({'self'}),slots,10,4096,lambda entry:entry.slot in slots,
        lambda entry,rows:any(entry.text==row.text for row in rows))
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
    collection_app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)),run_context=context)
    host=collection_app.state.memory_history;collection=host.service
    with TestClient(collection_app) as client:
        def post(url,value):
            response=client.post(url,content=json.dumps(value).encode(),headers=headers)
            assert response.status_code==200,(response.status_code,response.text)
            return response.json()
        post('/v3/memory-history-actions',dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='chat',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0))
        source=dict(conversation_id='chat',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        post('/internal/v1/memory-history/jobs',dict(version='MEMORY-JOBS@1',job_id='job',attempt_id='attempt',source=source))
        collection.transition(token,'job','attempt','inflight')
        prepared=collection.prepare_model_input_v2(token,'job','attempt',max_payload_bytes=262144)
        jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=GuardedCollectionAdapterV3(collection),max_payload_bytes=262144)
        request=JobRequest('job','attempt',SourceQuery(**source),None,prepared)
        original=jobs.prepare(token,request)
        assert original['state']=='queued'
        provider=ExtractFake();worker=LocalBackgroundHost(jobs,auth)
        result=run_worker.run_once(database,provider,auth,background_jobs=worker)
        assert len(result)==1 and result[0].status=='completed' and provider.calls==1,result
        assert run_worker.run_once(database,provider,auth,background_jobs=worker)==[] and provider.calls==1
        recovered=jobs.query_original(token,'job','attempt');assert recovered['state']=='completed'
        assert recovered['run_id']==original['run_id'] and recovered['meter_attempt_id']==original['meter_attempt_id']
        assert jobs.prepare(token,request)['run_id']==original['run_id']
    with psycopg.connect(**json.loads(conninfo.read_text())) as conn:
        owner=scope_for(ISSUER,'bg-a')
        assert conn.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(owner,)).fetchone()==(3,)
        assert conn.execute('SELECT count(*) FROM cj_run_record WHERE scope=%s',(owner,)).fetchone()==(3,)
        assert conn.execute('SELECT count(*) FROM cj_run_background_job WHERE scope=%s',(owner,)).fetchone()==(1,)
        assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(owner,)).fetchone()==(1,)
        ledgers=conn.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchall()
        attempts=[a for row in ledgers for a in row[0]['attempts'].values()]
        assert len(attempts)==4 and all(a['state']=='settled' for a in attempts)
    # A physical failed invocation leaves the one original Meter claim UNKNOWN;
    # neither another worker pass nor withdrawal/cancellation can redispatch it.
    class UnknownFake(FakeProvider):
        def stream(self,messages,system=None):
            self.calls+=1
            raise ProviderFailed('synthetic original outcome unknown')
    second_source=source|dict(after=1,through=2)
    collection.enqueue(token,json.dumps(dict(version='MEMORY-JOBS@1',job_id='unknown-job',attempt_id='original-attempt',source=second_source)).encode())
    collection.transition(token,'unknown-job','original-attempt','inflight')
    second_input=collection.prepare_model_input_v2(token,'unknown-job','original-attempt',max_payload_bytes=262144)
    unknown=jobs.prepare(token,JobRequest('unknown-job','original-attempt',SourceQuery(**second_source),None,second_input))
    failing=UnknownFake()
    result=run_worker.run_once(database,failing,auth,background_jobs=worker)
    assert len(result)==1 and result[0].status=='unknown' and failing.calls==1
    assert run_worker.run_once(database,failing,auth,background_jobs=worker)==[] and failing.calls==1
    collection.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='disable',operation='disable',conversation_id='chat',
        expected_generation=head['generation'],expected_epoch=0,expected_source_version=1)).encode())
    observed=jobs.query_original(token,'unknown-job','original-attempt')
    assert observed['state']=='unknown' and observed['meter_attempt_id']==unknown['meter_attempt_id']
    stopped=jobs.cancel(token,'unknown-job','original-attempt');assert stopped['state']=='cancelled'
    with psycopg.connect(**json.loads(conninfo.read_text())) as conn:
        ledgers=conn.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchall()
        attempt=next(a for row in ledgers for key,a in row[0]['attempts'].items() if key==unknown['meter_attempt_id'])
        assert attempt['state']=='unknown' and attempt['receipt'] is None and attempt['cancelled'] is True
    assert failing.calls==1
    print('PASS local component original unknown claim retained, zero redispatch, source-independent status and cancel after consent withdrawal without financial release')
    # C commits an actual typed result, then its outer MESSAGE ACK is lost.
    # Reconciliation after withdrawal confirms that receipt without republishing.
    from unittest.mock import patch
    collection.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='re-enable',operation='enable',conversation_id='chat',
        expected_generation=head['generation'],expected_epoch=0,expected_source_version=2)).encode())
    ack_source=source|dict(after=0,through=3,source_version=3,withdrawal_epoch=1)
    collection.enqueue(token,json.dumps(dict(version='MEMORY-JOBS@1',job_id='ack-job',attempt_id='ack-attempt',source=ack_source)).encode())
    collection.transition(token,'ack-job','ack-attempt','inflight')
    ack_input=collection.prepare_model_input_v2(token,'ack-job','ack-attempt',max_payload_bytes=262144)
    armed={'publication':False,'remaining':1}
    class AckAdapter(GuardedCollectionAdapterV3):
        def __init__(self,c):
            super().__init__(c);self.actual=self.publication_policy;self.publication_policy=self.policy
        def policy(self,*args,**kwargs):
            actual=self.actual(*args,**kwargs)
            class Held:
                def hold(self,*args,**kwargs):return actual.hold(*args,**kwargs)
                def apply_original_result(self,*args,**kwargs):
                    result=actual.apply_original_result(*args,**kwargs);armed['publication']=True
                    return result
            return Held()
    class LostMessageAck:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            self.connection.commit()
            if armed['publication'] and armed['remaining']:
                armed['remaining']-=1
                raise OSError('synthetic known C result / lost outer MESSAGE ACK')
    ack_jobs=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=AckAdapter(collection),max_payload_bytes=262144)
    ack_original=ack_jobs.prepare(token,JobRequest('ack-job','ack-attempt',SourceQuery(**ack_source),None,ack_input))
    original_resolve=host.boundary.resolve_repository
    def lost_repository(principal):
        repository=original_resolve(principal);connect=repository.connect
        repository.connect=lambda:LostMessageAck(connect())
        return repository
    ack_model=ExtractFake()
    with patch.object(host.boundary,'resolve_repository',lost_repository):
        try:ack_jobs.process_one(token,'ack-job','ack-attempt',ack_model)
        except JobOutcomeUnknown:pass
        else:raise AssertionError('lost outer ACK was labelled success')
    assert ack_model.calls==1 and ack_jobs.query_original(token,'ack-job','ack-attempt')['state']=='unknown'
    collection.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='withdraw-after-ack',operation='disable',conversation_id='chat',
        expected_generation=head['generation'],expected_epoch=0,expected_source_version=3)).encode())
    actual=ack_jobs.reconcile(token,'ack-job','ack-attempt')
    assert actual['state']=='completed' and actual['meter_attempt_id']==ack_original['meter_attempt_id'] and ack_model.calls==1
    print('PASS local component C actual typed publication committed/outer ACK lost; original receipt reconciliation after withdrawal confirms completion with zero provider/publication resend')
    # A separate real quota has exactly one call, consumed by the accepted
    # normal MESSAGE worker. The new job must be denied before any model call.
    limit_document=json.loads(path.read_text());limit_document['current']['meter']['budget']=1
    limit_path=root/'limit.json';limit_path.write_text(json.dumps(limit_document))
    limit_context=load_run_context(limit_path);local_run_context.provision_budget(conninfo,limit_context,'bg-limit')
    limit_database=LocalDatabase(conninfo,run_context=limit_context)
    limit_token=dev_auth.token(auth,'bg-limit',30);limit_headers={'Authorization':'Bearer '+limit_token,'Content-Type':'application/octet-stream'}
    with TestClient(create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=limit_context)) as lc:
        lh=lc.put('/v1/conversations',params={'conversation_id':'limit-chat'},headers=limit_headers).json()
        sent=lc.post('/v1/messages',content=json.dumps(dict(version='MESSAGE-send.1',conversation_id='limit-chat',message_id='limit-m0',text='No spicy food',
            trip_id=None,creation_intent='none',expected_generation=lh['generation'],expected_sequence=0)).encode(),headers=limit_headers)
        assert sent.status_code==200
    limit_normal=FakeProvider();run_worker.run_once(limit_database,limit_normal,auth);assert limit_normal.calls==1
    limit_app=create_collection_app(conninfo_path=conninfo,auth_dir=auth,resolve_collection=lambda principal:(extraction,memory,lambda entry:(None,None)),run_context=limit_context)
    limit_host=limit_app.state.memory_history;limit_collection=limit_host.service
    limit_collection.apply_consent(limit_token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='limit-enable',operation='enable',conversation_id='limit-chat',
        expected_generation=lh['generation'],expected_epoch=0,expected_source_version=0)).encode())
    limit_source=source|dict(conversation_id='limit-chat',generation=lh['generation'])
    limit_collection.enqueue(limit_token,json.dumps(dict(version='MEMORY-JOBS@1',job_id='limit-job',attempt_id='limit-attempt',source=limit_source)).encode())
    limit_collection.transition(limit_token,'limit-job','limit-attempt','inflight')
    limit_input=limit_collection.prepare_model_input_v2(limit_token,'limit-job','limit-attempt',max_payload_bytes=262144)
    limited_jobs=BackgroundJobsV2(database=limit_host.database,boundary=limit_host.boundary,collection=GuardedCollectionAdapterV3(limit_collection),max_payload_bytes=262144)
    limit_original=limited_jobs.prepare(limit_token,JobRequest('limit-job','limit-attempt',SourceQuery(**limit_source),None,limit_input))
    forbidden=ExtractFake();limited_worker=LocalBackgroundHost(limited_jobs,auth)
    denied=run_worker.run_once(limit_database,forbidden,auth,background_jobs=limited_worker)
    assert len(denied)==1 and denied[0].status=='budget_exhausted' and forbidden.calls==0
    with psycopg.connect(**json.loads(conninfo.read_text())) as conn:
        ledgers=conn.execute('SELECT ledger FROM cj_usage_ledger_candidate').fetchall()
        assert all(limit_original['meter_attempt_id'] not in row[0]['attempts'] for row in ledgers)
    print('PASS local component actual shared quota exhausted by MESSAGE prevents background model outflow, no second Meter or forged reserve/receipt')
    # New process: original metadata remains readable without a model adapter,
    # C source grant, or current quota context. No new attempt can be claimed.
    child = """import sys,json,uuid
from pathlib import Path
from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_account_admission_v2 import account_checker_for
from cj_message.auth_boundary import Boundary
from cj_run.background import read_original
import dev_auth
p,a=map(Path,sys.argv[1:3]);db=LocalDatabase(p);boundary=Boundary(account_checker_for(a,db),lambda principal:db.message_repository(scope_for(principal.issuer,principal.subject)),lambda:uuid.uuid4().hex)
value=read_original(db,boundary,dev_auth.token(a,'bg-a',30),'unknown-job','original-attempt')
assert value['state']=='cancelled'
print(json.dumps({key:value[key] for key in ('run_id','meter_attempt_id','operation_input_sha256')}))
"""
    actual=subprocess.check_output([sys.executable,'-B','-c',child,str(conninfo),str(auth)],env=dict(os.environ,PYTHONPATH=os.environ['PYTHONPATH']+os.pathsep+str(ROOT/'scripts')),text=True)
    child_value=json.loads(actual)
    assert child_value['run_id']==unknown['run_id'] and child_value['meter_attempt_id']==unknown['meter_attempt_id']
    print('PASS local component fresh-process original metadata without C source or current quota; same original run/attempt/hash, no dispatch capability')
    # The registered schema itself is a trust boundary, independent of Python.
    owner=scope_for(ISSUER,'bg-a');other=scope_for(ISSUER,'bg-limit')
    config=json.loads(conninfo.read_text())
    columns='scope,job_id,attempt_id,run_id,ledger_scope,prepared_input_sha256,config_bytes,command_bytes,input_bytes'
    with psycopg.connect(**config,autocommit=True) as conn:
        sample=conn.execute('SELECT '+columns+' FROM cj_run_background_job WHERE scope=%s LIMIT 1',(owner,)).fetchone()
        before=conn.execute('SELECT * FROM cj_run_background_job ORDER BY scope,job_id,attempt_id').fetchall()
        # Exercise M40's own guard, not unrelated later migrations' down gates.
        migration=next(m for m in migrate.load() if m['version']==40)
        try:
            with conn.transaction():conn.execute((ROOT/migration['down']).read_text())
        except psycopg.errors.RaiseException as error:assert 'original background job evidence retained' in str(error)
        else:raise AssertionError('down discarded original background jobs')
        assert conn.execute('SELECT * FROM cj_run_background_job ORDER BY scope,job_id,attempt_id').fetchall()==before
    with database.connect(other) as conn:
        assert conn.execute('SELECT job_id FROM cj_run_background_job WHERE scope=%s',(owner,)).fetchall()==[]
        assert conn.execute("SELECT has_table_privilege(current_user,'cj_run_background_job','DELETE'),has_table_privilege(current_user,'cj_run_background_job','TRUNCATE')").fetchone()==(False,False)
    for sql,args in (
        ('INSERT INTO cj_run_background_job('+columns+') VALUES('+','.join(['%s']*9)+')',sample),
        ('DELETE FROM cj_run_background_job WHERE scope=%s',(owner,)),
        ('TRUNCATE cj_run_background_job',None),
        ('UPDATE cj_run_background_job SET input_bytes=%s WHERE scope=%s',(b'changed',owner))):
        try:
            with database.connect(other) as conn:conn.execute(sql,args)
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('runtime crossed original owner/column/destructive boundary')
    try:
        with database.connect(owner) as conn:
            conn.execute("UPDATE cj_run_background_job SET state='queued' WHERE scope=%s AND job_id='job'",(owner,))
    except psycopg.errors.RaiseException as error:assert 'cannot redispatch' in str(error)
    else:raise AssertionError('completed original returned to dispatch queue')
    with psycopg.connect(**dict(config,user='cj_local_cleanup')) as conn:
        conn.execute("SELECT set_config('cj.cleanup_scope',%s,true)",(owner,))
        assert conn.execute('SELECT job_id FROM cj_run_background_job').fetchall()==[]
        assert conn.execute('DELETE FROM cj_run_background_job WHERE scope=%s RETURNING job_id',(owner,)).fetchall()==[]
    # A real original account operation physically erases only its completed /
    # budget-denied RUN domain. Another owner's unknown financial evidence stays.
    from cj_api.local_cleanup import Configuration
    from cj_cleanup.core import encode,digest
    registry=root/'cleanup-registry.json'
    registry.write_bytes(encode(dict(version='background-run-component',stores=[dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')])])))
    cleanup=Configuration({'bg-cleanup':b'explicit-background-cleanup-test-00'},'bg-cleanup',3600,('checkpoints/run',),registry)
    cleanup_app=create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=limit_context,cleanup_configuration=cleanup)
    with TestClient(cleanup_app) as client:
        def cleanup_post(url,value):
            response=client.post(url,content=encode(value),headers=limit_headers)
            assert response.status_code==200,('background cleanup HTTP',response.status_code)
            return response.json()
        device=cleanup_post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id='limit-device',state_ref=digest(b'limit-state')))
        operation=cleanup_post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='delete-limit',binding_id=device['binding_id']))
        progress=cleanup_post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert progress['business_access']=='revoked' and progress['online_status']=='complete'
    with psycopg.connect(**config) as conn:
        assert conn.execute('SELECT count(*) FROM cj_run_background_job WHERE scope=%s',(other,)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM cj_run_background_job WHERE scope=%s',(owner,)).fetchone()==(3,)
    print('PASS registered background schema: nonempty down refusal, cross-owner read/write, immutable original/no redispatch, runtime no DELETE/TRUNCATE, dedicated cleanup no-intent denial and actual original account RUN erasure with other owner unchanged')
    print('PASS local component actual signed source/C policy + original run_once/one new Fake model/one same-Meter attempt/C typed publication; no fake MESSAGE or terminal RUN reuse; registered chain / actual C filtered V2; real provider/cloud/device UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-bg-jobs-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
