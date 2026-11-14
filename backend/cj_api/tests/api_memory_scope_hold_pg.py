"""Real signed M effect frame + API Memory lock, no model/Trip/Memory item write."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import json,time,uuid
import psycopg
import local_history_pg as harness
import local_run_context
from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_message.auth_boundary import Boundary
from cj_message.travel_reference import MessageContextAuthority
from cj_message.travel import ABI
from cj_run.core import Binding
from cj_memory.api_scope_hold import ApiMemoryScopeHolder
from cj_memory.postgres import Repository
from cj_memory.typed_local import TypedConfiguration
from cj_memory_jobs.service import Service as HistoryService
from cj_memory.runtime import RuntimeDenied


def exercise(auth,conninfo):
    subjects=['holder','missing'];harness.dev_auth.init(auth,subjects);now=int(time.time())
    path=auth.parent/'run.json';path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=800,
        period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=12000)),history=[])))
    context=load_run_context(path)
    for subject in subjects:
        local_run_context.provision_budget(conninfo,context,subject);harness.dev_auth.activate_travel(conninfo,subject,context,ABI)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    checker=checker_for(auth);boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    policy=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    configuration=TypedConfiguration.from_bytes(json.dumps(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={s:policy for s in subjects}),travel_contexts={s:[]for s in subjects})).encode())
    holder=ApiMemoryScopeHolder(database,configuration);saved=[]
    def memory(scope):return Repository(lambda:database.connect(scope),scope,typed_context=True,transaction_binder=lambda conn,cur:conn.bind_scope(cur))
    for subject in subjects:
        token=harness.dev_auth.token(auth,subject,600);scope=scope_for(ISSUER,subject)
        receipt=boundary.receive_lio(token,json.dumps(dict(version='LIO-message.2',message_id=subject,text='API holder test',locale='en',new_conversation=True)).encode(),prepare_scope=database._provision_scope,version='LIO-message.2')
        original=boundary.with_history_context(token,lambda ctx:ctx.query_lio_message(receipt.message_id)).receipt
        if subject=='holder':
            head=boundary.with_history_context(token,lambda ctx:ctx.send_status(receipt.conversation_id).head)
            history=HistoryService(boundary,lambda principal,owner:memory(owner))
            history.apply_consent(token,json.dumps(dict(version='MEMORY-HISTORY@1',action_id='explicit-disable',operation='disable',conversation_id=receipt.conversation_id,expected_generation=head.generation,expected_epoch=head.epoch,expected_source_version=0)).encode())
        def admit():
            result=checker.check(token)
            if result.status is not AdmissionStatus.ALLOWED:raise RuntimeDenied('admission withdrawn')
            return result.principal
        authority=MessageContextAuthority(database.message_repository(scope),admit)
        binding=Binding(scope,original.conversation_id,original.generation,original.message_id,original.run_id,original.sequence)
        with authority.hold_for_effect(binding)as lease:
            def check():lease.check(binding)
            frame=SimpleNamespace(principal=admit(),scope=scope,check=check)
            if subject=='missing':
                try:
                    with holder.hold(frame):raise AssertionError('missing scope was initialized')
                except RuntimeDenied:pass
                with database.connect(scope)as db:assert db.execute('SELECT count(*) FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone()[0]==0
                continue
            with psycopg.connect(**json.loads(conninfo.read_bytes()),autocommit=True)as admin:
                before=admin.execute('SELECT epoch,active FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone()
                with ThreadPoolExecutor(max_workers=1)as pool:
                    entered=Event()
                    def competing():
                        entered.set()
                        with memory(scope).transaction()as tx:return tx.lock_scope()
                    with holder.hold(frame)as held:
                        saved.append(held);held.check();assert held.epoch==before[0]
                        future=pool.submit(competing);assert entered.wait(3)
                        deadline=time.monotonic()+3
                        while time.monotonic()<deadline:
                            rows=admin.execute("SELECT query FROM pg_stat_activity WHERE wait_event_type='Lock'").fetchall()
                            if any('cj_memory_scope'in text for(text,)in rows):break
                            time.sleep(.01)
                        else:raise AssertionError('real competing Memory holder did not block')
                        assert not future.done();held.check()
                    assert future.result(timeout=5)==before[0]
                assert admin.execute('SELECT epoch,active FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone()==before
                assert admin.execute('SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s',(scope,)).fetchone()[0]==0
    for held in saved:
        try:held.check()
        except RuntimeDenied:pass
        else:raise AssertionError('escaped Memory API holder remained usable')
    print('PASS actual signed M effect frame -> native Memory row lock; real competitor blocked/released; epoch/active unchanged, no missing-scope INSERT, no provider/Trip/item write or escaped holder; full HTTP4 undo remains UNRUN')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
