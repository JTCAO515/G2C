"""Actual protected headers, held MESSAGE -> signed C Memory writer, no bodies."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import json,os,sys,tempfile,time
import psycopg
from fastapi.testclient import TestClient

from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_account_admission_v2 import account_checker_for
from cj_message.auth_boundary import Boundary,AccessBlocked
from cj_message.domain import Unavailable,InvalidInput
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_cleanup.core import encode

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['headers-a','headers-b'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('headers-a','headers-b')}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    database=LocalDatabase(path);checker=account_checker_for(auth,database)
    def resolve(principal):
        scope=scope_for(principal.issuer,principal.subject);database.provision(scope)
        return database.message_repository(scope)
    boundary=Boundary(checker,resolve,lambda:str(uuid4()))
    def read(project,who='headers-a',max_refs=100,max_result_bytes=32768):
        return boundary.with_history_context(tokens[who],lambda ctx:ctx.with_erasure_headers(project,max_refs=max_refs,max_result_bytes=max_result_bytes))
    app=create_local_app(conninfo_path=path,auth_dir=auth)
    with TestClient(app) as client:
        originals={};heads={}
        def send(cid,mid,text,through=0):
            response=client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text=text,
                trip_id=None,creation_intent='none',expected_generation=heads[cid]['generation'],expected_sequence=through)),headers=headers['headers-a'])
            assert response.status_code==200,response.text
            return response
        for cid in ('old','inactive'):
            heads[cid]=client.put('/v1/conversations',params={'conversation_id':cid},headers=headers['headers-a']).json()
            originals[cid]=send(cid,cid,'private source text '+cid).json()['receipt']
        client.put('/v1/conversations',params={'conversation_id':'empty'},headers=headers['headers-b'])
        owner=scope_for(ISSUER,'headers-a')
        with psycopg.connect(**config) as audit:audit.execute("UPDATE cj_message_chat SET active=false WHERE scope=%s AND conversation_id='inactive'",(owner,))
        def values():
            with psycopg.connect(**config) as audit:
                return [audit.execute(f'SELECT to_jsonb(t),xmin::text FROM {table} t ORDER BY to_jsonb(t)::text').fetchall()
                        for table in ('cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery')]
        before=values();captured=[]
        def inspect(snapshot):
            assert snapshot.complete and snapshot.scope==owner and snapshot.principal==checker.check(tokens['headers-a']).principal
            refs=[r.to_dict() for r in snapshot.references];assert len(refs)==2
            assert {r['message_id'] for r in refs}=={'old','inactive'}
            assert all(set(r)=={'conversation_id','generation','sequence','message_id','input_sha256'} for r in refs)
            assert all(r['input_sha256']==originals[r['message_id']]['input_sha256'] for r in refs)
            with ThreadPoolExecutor(max_workers=1) as other:
                try:other.submit(snapshot.check).result(timeout=5)
                except Unavailable:pass
                else:raise AssertionError('cross-thread metadata lease accepted')
            captured.append(snapshot);return encode(refs)
        raw=read(inspect);assert b'private source text' not in raw and values()==before
        for name in ('scope','principal','references','complete'):
            try:getattr(captured[0],name)
            except Unavailable:pass
            else:raise AssertionError('escaped metadata snapshot accepted')
        assert read(lambda s:encode(dict(complete=s.complete,refs=len(s.references))),'headers-b')==b'{"complete":true,"refs":0}'
        # SEND1 already accepts this ID. Metadata must preserve its full original
        # bytes rather than introduce an unsupported per-identifier length cap.
        long_id='long-'+'x'*4096
        empty=client.get('/v1/message-send-status',params={'conversation_id':'empty'},headers=headers['headers-b']).json()['head']
        long=client.post('/v1/messages',content=encode(dict(version='MESSAGE-send.1',conversation_id='empty',message_id=long_id,
            text='a legal original long ID',trip_id=None,creation_intent='none',expected_generation=empty['generation'],expected_sequence=0)),headers=headers['headers-b'])
        assert long.status_code==200,long.text
        def original_long(snapshot):
            assert snapshot.complete and len(snapshot.references)==1 and snapshot.references[0].message_id==long_id
            assert snapshot.references[0].input_sha256==long.json()['receipt']['input_sha256']
            return b'complete-original'
        assert read(original_long,'headers-b',max_refs=1,max_result_bytes=100)==b'complete-original'
        calls=[]
        for limits in ((0,100),(10001,100),(1,100),(100,0),(100,8388609)):
            try:read(lambda s:calls.append(s) or b'ok',max_refs=limits[0],max_result_bytes=limits[1])
            except (InvalidInput,Unavailable):pass
            else:raise AssertionError('invalid or truncated metadata accepted')
        assert not calls
        for project in (lambda s:b'xx',lambda s:(x for x in ())):
            try:read(project,max_result_bytes=1)
            except Unavailable:pass
            else:raise AssertionError('oversized/deferred callback accepted')

        # No plaintext is transferred to C. C's real long-term save uses its own
        # runtime connection while an actual competing MESSAGE writer is blocked.
        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
        typed=TypedConfiguration.from_bytes(encode(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'headers-a':profile}),travel_contexts={'headers-a':[]})))
        manager=create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=typed)
        with ThreadPoolExecutor(max_workers=1) as writers,TestClient(manager) as memory:
            futures=[]
            def freeze(snapshot):
                futures.append(writers.submit(send,'old','after-snapshot','a later user instruction',1))
                with psycopg.connect(**config,autocommit=True) as observer:
                    until=time.monotonic()+5
                    while time.monotonic()<until:
                        waiting=observer.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' AND wait_event_type='Lock' AND query LIKE '%cj_message_scope%'").fetchone()[0]
                        if waiting:break
                        time.sleep(.01)
                    else:raise AssertionError('actual MESSAGE writer did not wait on metadata scope')
                assert not futures[0].done() and len(snapshot.references)==2
                response=memory.post('/v2/memories',content=encode(dict(version='MEMORY-manual.2',operation_id='actual-c-write',item_id='actual-c-write',
                    subject='self',slot='pace',kind='preference',text='A signed C runtime action',extent='long_term',context=None,occurred_at='date unknown')),
                    headers=headers['headers-a'])
                assert response.status_code==200,response.text
                snapshot.check();assert not futures[0].done()
                return b'c-committed'
            assert read(freeze)==b'c-committed'
            assert futures[0].result(timeout=10).status_code==200
        assert read(lambda s:encode(len(s.references)))==b'3'
        with psycopg.connect(**config) as audit:
            assert audit.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(owner,)).fetchone()==(1,)

        for corruption in ('sha','head'):
            with psycopg.connect(**config) as audit:
                if corruption=='sha':
                    original=bytes(audit.execute("SELECT raw_input FROM cj_message_receipt WHERE scope=%s AND message_id='old'",(owner,)).fetchone()[0])
                    audit.execute("UPDATE cj_message_receipt SET raw_input=%s WHERE scope=%s AND message_id='old'",(original+b' ',owner))
                else:
                    audit.execute("UPDATE cj_message_chat SET last_sequence=3 WHERE scope=%s AND conversation_id='old'",(owner,))
            try:
                try:read(lambda s:calls.append(s) or b'ok')
                except Unavailable:pass
                else:raise AssertionError('incomplete/corrupt metadata accepted')
                assert not calls
            finally:
                with psycopg.connect(**config) as audit:
                    if corruption=='sha':audit.execute("UPDATE cj_message_receipt SET raw_input=%s WHERE scope=%s AND message_id='old'",(original,owner))
                    else:audit.execute("UPDATE cj_message_chat SET last_sequence=2 WHERE scope=%s AND conversation_id='old'",(owner,))
        invited=auth/'invited.json';original=invited.read_bytes()
        def revoke(snapshot):invited.write_text(json.dumps(['headers-b']));return b'private metadata'
        try:
            try:read(revoke)
            except AccessBlocked:pass
            else:raise AssertionError('withdrawn identity received projected metadata')
        finally:invited.write_bytes(original)
    print('PASS actual headers-only complete/empty/inactive snapshot, SQL SHA and gaps/limits, lifetime/thread/deferred/output guards, owner isolation/withdrawal, unchanged B values+xmin; real signed C runtime write commits while M holds competing MESSAGE until callback ends')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='erasure-headers-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
