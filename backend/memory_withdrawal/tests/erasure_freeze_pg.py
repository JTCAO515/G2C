"""Candidate M44: actual protected freeze/model projection, no cleanup dispatch."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory.domain import Service,Conflict
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
from cj_memory_withdrawal.erasure_store import freeze
from cj_memory_withdrawal.association_reader import AssociationReader
from cj_cleanup.store import Store,receipt_for
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.registry import freeze as freeze_registry
from cj_cleanup.hooks_v1_1 import Selection
from cj_cleanup.core import Denied,encode,digest
from cj_api.local_account_admission_v2 import subject_digest
from source_graph_pg import exercise as seed

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import migrate,pg_suites


def exercise(root,path,*,physical=False):
    fixture=seed(root,path);token=fixture['tokens']['graph-alice']
    c=create_collection_app(conninfo_path=path,auth_dir=fixture['auth'],resolve_collection=lambda principal:None).state.memory_history.service
    original=json.dumps(dict(version=VERSION,action_id='erase-original',item_id=fixture['item_id'],expected_version=3),indent=2).encode()
    command=ErasureCommand.parse(original)
    def in_memory(operation):
        def project(context):
            repo,principal,guard=c._binding(context,token)
            def bound(stage):guard(stage);return principal,repo.scope
            return operation(repo,principal,bound)
        return c.boundary.with_history_context(token,project)
    def current(repo,principal,guard):
        return Service(repo).with_operation(guard,lambda context:context.consume_current_typed('self',None,
            lambda view:json.dumps(dict(items=[dict(id=i.command.item_id,text=i.command.text) for i in view.items])).encode(),max_result_bytes=32768))
    before=in_memory(current);assert b'very slow pace' in before
    def stop(repo,principal,guard):
        with repo.transaction() as memory:
            result=freeze(memory,command,subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
            guard('item_freeze_precommit');return result
    raw=in_memory(stop);descriptor=json.loads(raw)
    assert descriptor['selection']==dict(kind='memory',item_id=fixture['item_id'],item_version=4,scope_epoch=5)
    assert len(descriptor['source_refs'])==3 and len(descriptor['message_refs'])==1
    assert in_memory(stop)==raw
    # Reader sees only the persisted original, under a real same-operation
    # in-progress B intent. A DTO or absence never grants private-source access.
    targets=('memory-derived','business/memory-management-actions','business/trip-authoritative','business/memory-authoritative') if physical else ('business/memory-authoritative',)
    stores=[dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in targets if '/' in t])]
    if physical:stores.append(dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'))
    registry=freeze_registry(encode(dict(version='item-reader-component',stores=stores)),targets,versions=('CLEANUP@1.1',))
    store=Store(lambda:psycopg.connect(**dict(json.loads(path.read_text()),user='cj_local_cleanup')),
                descriptor['subject_digest'],lambda stage:None)
    reader=AssociationReader(store,fixture['scope']);seen=[]
    class Observe:
        def execute(self,request):
            seen.append(reader.read_original(request))
            assert reader.read_original(request)==seen[-1]
            return receipt_for(request,'unknown')
        def reconcile(self,request):return receipt_for(request,'unknown')
    coordinator=Coordinator(store,lambda:registry,{'business/memory-authoritative':Observe()})
    operation=descriptor['operation_id'];selection=Selection.from_dict(descriptor['selection'])
    if not physical:coordinator.create(operation,digest(original),'memory',{'business/memory-authoritative':dict(
        domain_scope=fixture['scope'],selection=selection.to_dict())})
    request=coordinator.request(operation,'business/memory-authoritative',fixture['scope'],selection)
    if not physical:
        try:reader.read_original(request)
        except Denied:pass
        else:raise AssertionError('association exposed without committed intent')
        coordinator.advance(request);assert seen==[raw]
    after=in_memory(current);assert json.loads(after)==dict(items=[])
    with fixture['database'].connect(fixture['scope']) as conn:
        assert conn.execute('SELECT status,version FROM cj_memory_item').fetchone()==('withdrawn',4)
        assert conn.execute('SELECT count(*) FROM cj_memory_source WHERE active').fetchone()==(0,)
        stored=conn.execute('SELECT approved_input,source_id FROM cj_memory_source LIMIT 1').fetchone()
        assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone()==(1,)
        assert conn.execute('SELECT count(*) FROM cj_memory_erasure_fence').fetchone()[0]>=6
    with fixture['database'].connect(fixture['scope']) as conn:
        try:conn.execute('''INSERT INTO cj_memory_source(scope,source_id,version,approved_input,authorized,confirmed,semantic_resolved,active,expires_at)
            VALUES(%s,%s,1,%s,true,true,true,true,clock_timestamp()+interval '1 hour') ON CONFLICT DO NOTHING''',
            (fixture['scope'],stored[1],stored[0]))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('old source identifier recreated')
    profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    config=TypedConfiguration.from_bytes(json.dumps(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'graph-alice':profile}),travel_contexts={'graph-alice':[]})).encode())
    app=create_local_typed_app(conninfo_path=path,auth_dir=fixture['auth'],configuration=config)
    with TestClient(app) as client:
        response=client.post('/v2/memories',content=json.dumps(dict(version='MEMORY-manual.2',operation_id='explicit-new-save',item_id='explicit-new-item',
            subject='self',slot='pace',kind='preference',text='New explicit saving',extent='long_term',context=None,occurred_at='date unknown')).encode(),
            headers=fixture['headers']['graph-alice'])
        assert response.status_code==200,response.text
    assert b'New explicit saving' in in_memory(current) and b'very slow pace' not in in_memory(current)
    if physical:
        from cj_memory_withdrawal.item_cleanup import DerivedItemHook,ManagementItemHook,TripDerivedItemHook,AuthorityItemHook
        from cj_agent.draft import trip_scope_for
        hooks={c.target:c(store,fixture['scope']) for c in (DerivedItemHook,ManagementItemHook,TripDerivedItemHook,AuthorityItemHook)}
        coordinator=Coordinator(store,lambda:registry,hooks)
        plan={t:dict(domain_scope=trip_scope_for(fixture['scope']) if t=='business/trip-authoritative' else fixture['scope'],
                     selection=selection.to_dict()) for t in targets}
        coordinator.create(operation,digest(original),'memory',plan)
        for target in targets:
            request=coordinator.request(operation,target,plan[target]['domain_scope'],selection)
            coordinator.advance(request)
        assert coordinator.query(operation)['status']=='complete'
        with psycopg.connect(**json.loads(path.read_text())) as conn:
            assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s AND item_id=%s',(fixture['scope'],fixture['item_id'])).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest WHERE scope=%s',(fixture['scope'],)).fetchone()==(0,)
            assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(fixture['scope'],)).fetchone()==(1,)
            assert conn.execute('SELECT count(*) FROM cj_memory_source WHERE scope=%s',(fixture['scope'],)).fetchone()==(1,)
        assert b'New explicit saving' in in_memory(current)
    with psycopg.connect(**json.loads(path.read_text()),autocommit=True) as conn:
        try:conn.execute((ROOT/'backend/migrations/down/0044_memory_item_erasure.down.sql').read_text())
        except psycopg.errors.RaiseException:pass
        else:raise AssertionError('erasure evidence downgraded')
    print('PASS actual canonical freeze/model projection, immutable reader/real intent, old source fence/replay/new save; C-only physical component='+str(physical)+'; no global/B payload cleanup/production API claim')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-item-freeze-') as folder:
        root=Path(folder)
        with pg_suites.cluster('item_freeze',port=55816,role='cj_c_item_freeze',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,42)
                conn.execute((ROOT/'backend/migrations/0044_memory_item_erasure.sql').read_text())
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(root,path,physical=os.environ.get('CJ_ITEM_PHYSICAL')=='1')
