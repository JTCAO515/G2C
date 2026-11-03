"""New current projection preserves an unrelated candidate after shared job erase."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory.manual import ManualPolicy
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
                value=freeze(tx,ErasureCommand.parse(encode(dict(version=VERSION,action_id='erase-one',item_id=selected['candidate_id'],expected_version=1))),
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
        review=projected['candidates'][0]['review'];assert review==dict(job_id='shared-job',attempt_id='shared-attempt')
        # Existing Action1 uses current canonical origin, not erased job payload.
        service.apply_candidate(token,encode(dict(version='MEMORY-CANDIDATE@1',action_id='confirm-retained',**review,candidate_id=other['candidate_id'],
            expected_candidate_version=1,expected_memory_epoch=projected['memory_epoch'],operation='confirm',kind='preference',
            text='Explicit retained route',extent='long_term',context=None,occurred_at='date unknown')))
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        assert conn.execute('SELECT count(*) FROM cj_memory_history_job WHERE scope=%s',(scope[0],)).fetchone()==(0,)
        assert conn.execute('SELECT item_id,status FROM cj_memory_item WHERE scope=%s',(scope[0],)).fetchall()==[(other['candidate_id'],'active')]
    print('PASS actual one-item erasure removes shared private job while unrelated canonical candidate remains discoverable via current projection and confirms with original Action1; no second confirmation authority or fallback')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-shared-candidate-') as folder:
        root=Path(folder)
        with pg_suites.cluster('shared_candidate',port=55817,role='cj_c_shared_candidate',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                migrate.up(conn,migrate.load(),42);conn.execute((ROOT/'backend/migrations/0044_memory_item_erasure.sql').read_text())
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600);exercise(root,path)
