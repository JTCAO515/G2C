"""Signed PG Lio projection custody; local FakeProvider, no external calls."""
import json,time
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.local_lio_memory import lio_candidates
from cj_api.lio_memory_routes import LioMemoryCards
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.model_v2 import SYSTEM as MEMORY_SYSTEM
from cj_message.auth_boundary import Boundary,HistoryReadContext
from cj_message.domain import Unavailable as MessageUnavailable
from cj_message.postgres import Transaction
from cj_message.travel import ABI
from runtime_adapter.contract import encode
import local_history_pg as harness
import dev_auth,local_run_context,run_worker


def exercise(root,conninfo):
    root.mkdir(mode=0o700)
    subjects=frozenset({'projection-owner','projection-foreign'})
    auth=root/'auth';dev_auth.init(auth,subjects)
    path=root/'connection.json';path.write_text(json.dumps(json.loads(conninfo.read_bytes())))
    meter=root/'meter.json';now=int(time.time())
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=12,max_tools=4,max_output=60000,max_seconds=600),
        output_limits=dict(model=12000,tool=4000,memory=12000)),history=[])))
    context=load_run_context(meter)
    for subject in subjects:
        local_run_context.provision_budget(path,context,subject)
        dev_auth.activate_travel(path,subject,context,ABI)
    database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    profile=dict(subjects=['self'],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at='2099-01-01T00:00:00Z',profiles={s:profile for s in subjects}),travel_contexts={s:[] for s in subjects})
    memory=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=policy,
        selections={s:dict(subject='self',slots=['travel.pace'],max_bytes=1000)for s in subjects})))
    readers=[]
    def memory_host(boundary):
        reader=lio_candidates(database,boundary,subjects,memory.collection);readers.append(reader)
        return LioMemoryCards(reader.collection,reader.current)
    class Model(FakeProvider):
        def stream(self,messages,system=None):
            if system==MEMORY_SYSTEM:
                self.calls+=1
                yield json.dumps(dict(version='MEMORY-EXTRACT@2',entries=[]))
            else:yield from super().stream(messages,system)
    model=Model();owner=dev_auth.token(auth,'projection-owner',300);foreign=dev_auth.token(auth,'projection-foreign',300)
    scope=scope_for(ISSUER,'projection-owner');headers={'Authorization':'Bearer '+owner,'Content-Type':'application/octet-stream'}
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,
        demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects,lio_memory_factory=memory_host)
    worker=run_worker._worker_for_scope(database,model,auth,scope,checker_for(auth),memory_configuration=memory,
                                         demo_planning=True,lio_memory_enabled=True)
    locks=[];native_lock=Transaction.lock_scope
    def lock(tx):locks.append(tx.scope);return native_lock(tx)
    with TestClient(app)as api:
        assert api.get('/v1/lio/timeline',headers=headers).json()['messages']==[]
        for mid,text in [('projection-empty','Tell me about a park.'),('projection-tags','I prefer fewer stops in a day.')]:
            assert api.post('/v1/lio/messages',headers=headers,content=encode(dict(version='LIO-message.1',message_id=mid,text=text,locale='en'))).status_code==200
            assert [o.status for o in worker.process()]==['completed']
            calls=model.calls
            with patch.object(HistoryReadContext,'with_lio_timeline_projection',lambda ctx,operation:operation()),patch.object(Transaction,'lock_scope',lock):
                legacy=api.get('/v1/lio/timeline',headers=headers)
            legacy_locks=len(locks);locks.clear()
            with patch.object(Transaction,'lock_scope',lock):current=api.get('/v1/lio/timeline',headers=headers)
            assert legacy.status_code==current.status_code==200 and legacy.json()==current.json()
            assert len(locks)==1 and legacy_locks>=3 and model.calls==calls,(legacy_locks,len(locks))
            shown=current.json()['messages'][-1]
            assert bool(shown['memory'])==(mid=='projection-tags'),shown
        # A worker cannot steal M between validated-original and C projection.
        attempts=[];native_query=HistoryReadContext.query_lio_message;started=[]
        def contend():
            try:
                with database.connect(scope)as db:
                    db.execute("SET LOCAL lock_timeout='100ms'")
                    db.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
                attempts.append('stole-lock')
            except psycopg.errors.LockNotAvailable:attempts.append('blocked')
        def query(ctx,mid):
            original=native_query(ctx,mid)
            if not started:
                started.append(True);thread=Thread(target=contend);thread.start();thread.join(timeout=2)
                assert not thread.is_alive()
            return original
        with patch.object(HistoryReadContext,'query_lio_message',query):
            assert api.get('/v1/lio/timeline',headers=headers).json()==current.json()
        assert attempts==['blocked']
        # Initial contention remains fail-closed, rather than a fake empty page.
        with database.connect(scope)as db:
            db.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
            assert api.get('/v1/lio/timeline',headers=headers).status_code==503
        assert api.get('/v1/lio/timeline',headers=headers).json()==current.json()
        # An immutable-reference read failure cannot become a null memory card.
        with patch('cj_message.lio_timeline.read_reference',side_effect=MessageUnavailable('private reference fault')):
            assert api.get('/v1/lio/timeline',headers=headers).status_code==503
        boundary=Boundary(checker_for(auth),lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:'unused')
        reader=readers[0]
        def wrong_run(ctx):
            return ctx.with_lio_timeline_projection(lambda:reader.current(ctx,owner,'projection-tags','wrong-original-run'))
        from cj_memory_jobs.codec import Unavailable
        try:boundary.with_history_context(owner,wrong_run)
        except Unavailable:pass
        else:raise AssertionError('wrong RUN became empty projection')
        def wrong_owner(ctx):
            return ctx.with_lio_timeline_projection(lambda:reader.current(ctx,foreign,'projection-tags','wrong-original-run'))
        try:boundary.with_history_context(foreign,wrong_owner)
        except Unavailable:pass
        else:raise AssertionError('foreign owner became empty projection')
        assert model.calls==calls
    print('PASS native signed PG empty/tag projection: same-body legacy compatibility, one M custody, competing worker blocked, initial contention503, invalid reference/wrong RUN/foreign owner withheld, no model calls during reads')


if __name__=='__main__':
    harness.exercise=lambda auth,conninfo:exercise(auth.parent/'lio-projection',conninfo)
    harness.main()
