"""New current projection preserves an unrelated candidate after shared job erase."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.source_policy import SourcePolicy
from cj_memory_jobs.model_v2 import prepared
from cj_message.source import SourceQuery
from cj_memory_jobs.codec import Conflict
from cj_memory.manual import ManualPolicy
from cj_memory.domain import Unavailable
from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
from cj_memory_withdrawal.erasure_store import freeze
from cj_api.local_account_admission_v2 import subject_digest
from cj_cleanup.core import encode,digest
from cj_cleanup.registry import freeze as registry_freeze
from cj_cleanup.store import Store
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.hooks_v1_1 import Selection
from cj_memory_withdrawal.item_cleanup import DerivedItemHook,ManagementItemHook,AuthorityItemHook

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(root,path):
    auth=root/'auth';dev_auth.init(auth,['shared-alice','shared-bob']);token=dev_auth.token(auth,'shared-alice',30)
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    policy=CollectionPolicy(frozenset({'self'}),frozenset({'pace','route'}),5,4096,lambda entry:True,lambda entry,rows:False)
    memory=ManualPolicy(policy.subjects,policy.slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),
        lambda command,raw:True,lambda command,raw:True)
    app=create_collection_app(conninfo_path=path,auth_dir=auth,resolve_collection=lambda principal:(policy,memory,lambda entry:(None,None)))
    service=app.state.memory_history.service;scope=[]
    def ok(response):assert response.status_code==200,response.text;return response.json()
    with TestClient(app) as client:
        head=ok(client.put('/v1/conversations',params={'conversation_id':'source'},headers=headers))
        text='Maybe I prefer a slow pace and a scenic route'
        ok(client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id='source',message_id='source',text=text,
            trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0)),headers=headers))
        service.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',conversation_id='source',
            expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        query=dict(conversation_id='source',generation=head['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        service.enqueue(token,encode(dict(version='MEMORY-JOBS@1',job_id='shared-job',attempt_id='shared-attempt',source=query)))
        service.transition(token,'shared-job','shared-attempt','inflight')
        output=encode(dict(version='MEMORY-EXTRACT@1',entries=[dict(subject='self',slot=slot,kind='inference',text='Candidate '+slot,
            extent='long_term',occurred_at='date unknown',evidence=[dict(message_id='source',quote=text)]) for slot in ('pace','route')]))
        service.record_output(token,'shared-job','shared-attempt',output);service.publish_output(token,'shared-job','shared-attempt')
        listed=json.loads(service.candidates(token,'shared-job','shared-attempt'));selected,other=sorted(listed['candidates'],key=lambda v:v['slot'])
        def stop(context):
            repo,principal,guard=service._binding(context,token);scope.append(repo.scope)
            with repo.transaction() as tx:
                value=freeze(tx,ErasureCommand.parse(encode(dict(version=VERSION,action_id='erase-one',item_id=selected['candidate_id'],expected_version=1,derived_range='owned_trip_derived_scope'))),
                    subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                guard('shared_job_freeze');return value
        association=json.loads(service.boundary.with_history_context(token,stop));selection=Selection.from_dict(association['selection'])
        targets=('memory-derived','business/memory-management-actions','business/memory-authoritative')
        registry=registry_freeze(encode(dict(version='shared-job-component',stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
            dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in targets[1:]])])),targets,versions=('CLEANUP@1.1',))
        store=Store(lambda:psycopg.connect(**dict(json.loads(path.read_text()),user='cj_local_cleanup')),association['subject_digest'],lambda stage:None)
        hooks={c.target:c(store,scope[0]) for c in (DerivedItemHook,ManagementItemHook,AuthorityItemHook)}
        coordinator=Coordinator(store,lambda:registry,hooks);operation=association['operation_id']
        coordinator.create(operation,digest(b'explicit component one-item delete'),'memory',
            {t:dict(domain_scope=scope[0],selection=selection.to_dict()) for t in targets})
        for target in targets:coordinator.advance(coordinator.request(operation,target,scope[0],selection))
        projected=ok(client.get('/v6/memory-candidates',params=dict(conversation_id='source',after_candidate_id=''),headers=headers))['result']
        assert len(projected['candidates'])==1 and projected['candidates'][0]['candidate_id']==other['candidate_id']
        def historical(context):
            repo,principal,guard=service._binding(context,token);held=SourcePolicy(repo,principal,guard)
            def project(snapshot):
                raw,count=prepared(held.transaction,snapshot,policy,'incremental',max_payload_bytes=262144)
                assert count==0 and text not in raw.decode()
                return raw
            return context.with_enabled_source(SourceQuery(**query),held,project)
        masked=service.boundary.with_history_context(token,historical)
        assert json.loads(json.loads(masked)['messages'][0]['content'])['messages']==[]
        for action,operation,version in (('off-rebuild','disable',1),('on-rebuild','enable',2)):
            service.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id=action,operation=operation,
                conversation_id='source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=version)))
        rebuilt=dict(query,source_version=3)
        try:service.enqueue(token,encode(dict(version='MEMORY-JOBS@1',job_id='rebuild-old',attempt_id='rebuild-attempt',source=rebuilt)))
        except Conflict:pass
        else:raise AssertionError('original erased message copied by re-extraction/rebuild')
        review=projected['candidates'][0]['review'];assert review==dict(job_id='shared-job',attempt_id='shared-attempt')
        # Existing Action1 uses current canonical origin, not erased job payload.
        service.apply_candidate(token,encode(dict(version='MEMORY-CANDIDATE@1',action_id='confirm-retained',**review,candidate_id=other['candidate_id'],
            expected_candidate_version=1,expected_memory_epoch=projected['memory_epoch'],operation='confirm',kind='preference',
            text='Explicit retained route',extent='long_term',context=None,occurred_at='date unknown')))
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_history_job WHERE scope=%s',(scope[0],)).fetchone()==(0,)
        assert conn.execute('SELECT item_id,status FROM cj_memory_item WHERE scope=%s',(scope[0],)).fetchall()==[(other['candidate_id'],'active')]
    with TestClient(app) as client:
        fresh=ok(client.put('/v1/conversations',params={'conversation_id':'independent'},headers=headers))
        ok(client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id='independent',message_id='independent-message',
            text='A separate future source',trip_id=None,creation_intent='none',expected_generation=fresh['generation'],expected_sequence=0)),headers=headers))
        service.apply_consent(token,encode(dict(version='MEMORY-HISTORY@1',action_id='enable-independent',operation='enable',conversation_id='independent',
            expected_generation=fresh['generation'],expected_epoch=0,expected_source_version=0)))
        fresh_source=dict(conversation_id='independent',generation=fresh['generation'],epoch=0,after=0,through=1,source_version=1,withdrawal_epoch=1,mode='incremental')
        for jid,attempt in (('shared-job','shared-attempt'),('shared-job','new-attempt'),('new-job','shared-attempt')):
            try:service.enqueue(token,encode(dict(version='MEMORY-JOBS@1',job_id=jid,attempt_id=attempt,source=fresh_source)))
            except Conflict:pass
            else:raise AssertionError('erased job/attempt identity reused for independent new source')
        fresh_raw=encode(dict(version='MEMORY-JOBS@1',job_id='independent-job',attempt_id='independent-attempt',source=fresh_source))
        service.enqueue(token,fresh_raw)
    bad_raw=encode(dict(version='MEMORY-JOBS@1',job_id='shared-job',attempt_id='shared-attempt',source=fresh_source))
    with app.state.memory_history.database.connect(scope[0]) as conn:
        try:conn.execute('''INSERT INTO cj_memory_history_job(scope,job_id,attempt_id,source_key,stream_key,original_input,batch,memory_epoch,state,processed)
            SELECT scope,'shared-job','shared-attempt',source_key,stream_key,%s,batch,memory_epoch,'pending',processed
            FROM cj_memory_history_job WHERE job_id='independent-job' ''',(bad_raw,))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('runtime SQL resurrected erased job identity')
    second_command=encode(dict(version=VERSION,action_id='erase-retained-later',item_id=other['candidate_id'],expected_version=2,
                               derived_range='owned_trip_derived_scope'))
    def stop_second(context):
        repo,principal,guard=service._binding(context,token)
        with repo.transaction() as tx:
            result=freeze(tx,ErasureCommand.parse(second_command),subject_digest(principal),
                          max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
            guard('second_shared_payload_erasure');return result
    # Controlled restore/corruption probe: valid new bytes at an old identifier
    # must be refused, never silently substituted into an immutable association.
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        conn.execute("UPDATE cj_memory_history_job SET job_id='shared-job',attempt_id='shared-attempt',original_input=%s WHERE scope=%s AND job_id='independent-job'",(bad_raw,scope[0]))
    try:
        try:service.boundary.with_history_context(token,stop_second)
        except Unavailable:pass
        else:raise AssertionError('association substituted restored unrelated original input hash')
    finally:
        with psycopg.connect(**json.loads(path.read_text())) as conn:
            conn.execute("UPDATE cj_memory_history_job SET job_id='independent-job',attempt_id='independent-attempt',original_input=%s WHERE scope=%s AND job_id='shared-job'",(fresh_raw,scope[0]))
    second=json.loads(service.boundary.with_history_context(token,stop_second))
    assert second['job_refs']==[dict(job_id='shared-job',attempt_id='shared-attempt',
                                     original_input_sha256=association['job_refs'][0]['original_input_sha256'],state='erased')]
    selection2=Selection.from_dict(second['selection']);operation2=second['operation_id']
    coordinator.create(operation2,digest(second_command),'memory',
        {t:dict(domain_scope=scope[0],selection=selection2.to_dict()) for t in targets})
    for target in targets:coordinator.advance(coordinator.request(operation2,target,scope[0],selection2))
    assert coordinator.query(operation2)['status']=='complete'
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(scope[0],)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM cj_memory_history_origin WHERE scope=%s',(scope[0],)).fetchone()==(0,)
        assert conn.execute('SELECT job_id,attempt_id,original_input FROM cj_memory_history_job WHERE scope=%s',(scope[0],)).fetchall()==[
            ('independent-job','independent-attempt',fresh_raw)]
    print('PASS actual shared-job one-item deletion preserves unrelated candidate/discovery/Action1, actual retained-message Data2 contains no erased text even with other origin retained; re-enabled source/index rebuild cannot recopy old bytes or recreate canonical memory')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-shared-candidate-') as folder:
        root=Path(folder)
        if os.environ.get('CJ_E2E_CONNINFO'):
            exercise(root,Path(os.environ['CJ_E2E_CONNINFO']))
            sys.exit(0)
        with pg_suites.cluster('shared_candidate',port=55817,role='cj_c_shared_candidate',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                migrate.up(conn,migrate.load(),44)
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600);exercise(root,path)
