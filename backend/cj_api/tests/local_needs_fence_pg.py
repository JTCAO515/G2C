"""Real PG/canonical AUTH module composition; formal host activation remains PR4."""
import json
import uuid
import time
from threading import Thread, Event as ThreadEvent
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from cj_api.local_app import LocalDatabase, ISSUER, AUDIENCE, KEY_ID, scope_for, InvitedSubjects
from cj_auth.admission import AdmissionChecker
from cj_auth.jwt_adapter import PyJWTVerifier, JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.auth_boundary import Boundary, AccessBlocked
from cj_message.domain import Service as Messages, Unavailable
from cj_message.postgres import Repository as MessageRepository, Transaction as MessageTransaction
from cj_message.needs_binding import needs_scope_for
from cj_needs.domain import Command as NeedsCommand, Denied
from cj_needs.postgres import Repository as NeedsRepository
from cj_needs.revision_lease import RevisionLease, LeaseUnavailable
from cj_run.core import Binding, Event, Service as Runs
from cj_run.postgres import CommitUnknown
from cj_agent.worker import RunWorker, original_context_valid
from cj_agent.draft import DraftPublisher
from cj_agent.provider import FakeProvider
import local_history_pg as harness


class TestNeedsConnection:
    """Test-only scoped hook; does not alter the formal local_app factory."""
    def __init__(self, connection, needs_scope): self.connection,self.needs_scope=connection,needs_scope
    def __getattr__(self,name): return getattr(self.connection,name)
    def bind_scope(self,cursor):
        self.connection.bind_scope(cursor)
        cursor.execute("SELECT current_setting('cj.needs_scope',true)")
        assert cursor.fetchone()[0] in (None,'')
        cursor.execute("SELECT set_config('cj.needs_scope',%s,true)",(self.needs_scope,))


def exercise(auth, conninfo):
    harness.dev_auth.init(auth,['alice','bob'])
    config=json.loads(conninfo.read_text())
    database=LocalDatabase(conninfo)
    tokens={s:harness.dev_auth.token(auth,s,30) for s in ('alice','bob')}
    checker=AdmissionChecker(PyJWTVerifier(JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
        StaticPublicKeys({KEY_ID:VerificationKey('RS256',(auth/'public.pem').read_bytes())})),InvitedSubjects(auth/'invited.json'))
    def connect(scope): return TestNeedsConnection(database.connect(scope),needs_scope_for(scope))
    def repository(principal):
        scope=scope_for(principal.issuer,principal.subject)
        database.provision(scope)
        return MessageRepository(lambda:connect(scope),scope,bind_needs=True)
    boundary=Boundary(checker,repository,lambda:uuid.uuid4().hex)
    def resolve(principal):
        scope=scope_for(principal.issuer,principal.subject)
        return lambda:connect(scope),scope,needs_scope_for(scope)
    lease=RevisionLease(checker,resolve,environment='local',issuer=ISSUER,audience=AUDIENCE)
    scope=scope_for(ISSUER,'alice'); ns=needs_scope_for(scope)
    database.provision(scope)
    with psycopg.connect(**config,autocommit=True) as admin:
        admin.execute('INSERT INTO cj_needs_scope VALUES(%s)',(ns,))
    writer=NeedsRepository(lambda:psycopg.connect(**config),ns,lambda stage:None)
    def revise(version):
        return writer.act(NeedsCommand(json.dumps(dict(action_id='edit-'+str(version),needs_id='needs',expected_version=version,
            source={'kind':'manual','text':'explicit local test input'},changes={'party_size':{'state':'known','value':version+1}})).encode()))
    revise(0)
    def send(selected=True):
        cid,mid=uuid.uuid4().hex,uuid.uuid4().hex
        chat=boundary.open_conversation(tokens['alice'],cid)
        if selected:
            with psycopg.connect(**config) as admin:
                admin.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
                admin.execute('INSERT INTO cj_message_needs_selection VALUES(%s,%s,%s,%s,%s)',(scope,cid,chat.generation,ns,'needs'))
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text='Beijing',trip_id=None,
            creation_intent='consider_trip',expected_generation=chat.generation,expected_sequence=0)).encode()
        return mid,raw
    missing,raw=send(False)
    try: boundary.receive(tokens['alice'],raw)
    except Unavailable: pass
    else: raise AssertionError('missing selection accepted')
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_message_receipt WHERE message_id=%s',(missing,)).fetchone()[0]==0
        assert admin.execute('SELECT count(*) FROM cj_message_delivery WHERE message_id=%s',(missing,)).fetchone()[0]==0
        assert admin.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_id=%s',(missing,)).fetchone()[0]==0
    mid,raw=send()
    receipt=boundary.receive(tokens['alice'],raw)
    binding=Binding(scope,receipt.conversation_id,receipt.generation,mid,receipt.run_id,receipt.sequence)
    with lease.hold(tokens['alice'],binding) as check:
        check()
    try: check()
    except LeaseUnavailable: pass
    else: raise AssertionError('escaped lease remained usable')
    try:
        with lease.hold(tokens['bob'],binding): pass
    except Denied: pass
    else: raise AssertionError('foreign identity read original binding')
    revise(1)
    assert boundary.receive(tokens['alice'],raw)==receipt
    try:
        with lease.hold(tokens['alice'],binding): pass
    except Denied: pass
    else: raise AssertionError('stale original version accepted')
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT needs_version FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',(scope,mid)).fetchone()[0]==1
        assert admin.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s AND message_id=%s',(scope,mid)).fetchone()[0]==1
    messages=Messages(MessageRepository(lambda:connect(scope),scope,bind_needs=True),lambda:None)
    runs=Runs(database.run_repository(scope),lambda b:original_context_valid(b,messages,lambda:True))
    worker=RunWorker(scope=scope,messages=messages,runs=runs,provider=FakeProvider(),drafts=DraftPublisher(database.trip_repository(scope)),
                     needs_lease=lambda b:lease.hold(tokens['alice'],b))
    result=worker.process()[0]
    assert result.status=='context_invalid' and result.proposal_id is None
    assert worker.provider.calls==0
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]==0
        assert admin.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(receipt.run_id,)).fetchone()[0]==0
    # Revision during the second provider call wins before candidate publication.
    mid2,raw2=send()
    receipt2=boundary.receive(tokens['alice'],raw2)
    class RevisesDuringDraft(FakeProvider):
        def stream(self, messages, system=None):
            if system is not None: revise(2)
            yield from super().stream(messages,system=system)
    worker.provider=RevisesDuringDraft()
    outcome=worker.process()[0]
    assert outcome.message_id==mid2 and outcome.status=='context_invalid'
    assert worker.provider.calls==2
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]==0

    # Publication wins first. The writer must wait through the RUN commit, not
    # merely through the TRIP callback. Inspect PostgreSQL's actual wait state.
    mid3,raw3=send()
    receipt3=boundary.receive(tokens['alice'],raw3)
    binding3=Binding(scope,receipt3.conversation_id,receipt3.generation,mid3,receipt3.run_id,receipt3.sequence)
    started=ThreadEvent(); finished=ThreadEvent(); writer_pid=[]; errors=[]
    def writer_connect():
        connection=psycopg.connect(**config)
        writer_pid.append(connection.info.backend_pid)
        started.set()
        return connection
    def write_next():
        try:
            repo=NeedsRepository(writer_connect,ns,lambda stage:None)
            repo.act(NeedsCommand(json.dumps(dict(action_id='concurrent-edit',needs_id='needs',expected_version=3,
                source={'kind':'manual','text':'concurrent explicit input'},changes={'party_size':{'state':'known','value':4}})).encode()))
        except BaseException as error: errors.append(error)
        finally: finished.set()
    def wait_for_database_block():
        assert started.wait(3)
        deadline=time.monotonic()+3
        with psycopg.connect(**config,autocommit=True) as admin:
            while time.monotonic()<deadline:
                waiting=admin.execute('SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=%s',(writer_pid[0],)).fetchone()
                if waiting==('Lock','advisory'): return
                if finished.is_set(): raise AssertionError('writer escaped publication lease')
                time.sleep(0.01)
        raise AssertionError('writer did not block on actual advisory lock')
    probe=[False]; commits=[]
    base_repository=database.run_repository(scope)
    class CommitProbe:
        def __getattr__(self,name): return getattr(base_repository,name)
        @contextmanager
        def transaction(self):
            with base_repository.transaction() as tx:
                yield tx
                if probe[0]:
                    wait_for_database_block()
                    commits.append('writer blocked before RUN commit')
    checked_runs=Runs(CommitProbe(),runs.valid)
    checked_runs.accept(binding3)
    checked_runs.apply(Event(binding3,1,'start-publication','started'))
    checked_worker=RunWorker(scope=scope,messages=messages,runs=checked_runs,provider=FakeProvider(),
        drafts=DraftPublisher(database.trip_repository(scope)),needs_lease=lambda b:lease.hold(tokens['alice'],b))
    thread=Thread(target=write_next)
    def publish():
        draft=checked_worker.drafts.publish(binding3.run_id,'{"title":"bound","items":["pending"]}')
        thread.start()
        wait_for_database_block()
        return draft
    probe[0]=True
    try:
        state,draft=checked_worker._step(binding3,publish,lambda d:'trip_proposal:'+d.proposal_id,draft=True)
    finally: probe[0]=False
    assert commits==['writer blocked before RUN commit']
    thread.join(5)
    assert finished.is_set() and not errors, errors
    assert state.effects==('trip_proposal:'+draft.proposal_id,)
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]==1
        assert admin.execute('SELECT version FROM cj_needs_record WHERE scope=%s',(ns,)).fetchone()[0]==4
    # Already committed RUN receipt but lost ACK: no replacement publication.
    mid4,raw4=send()
    receipt4=boundary.receive(tokens['alice'],raw4)
    binding4=Binding(scope,receipt4.conversation_id,receipt4.generation,mid4,receipt4.run_id,receipt4.sequence)
    armed=[False]
    class AckLoss:
        def __getattr__(self,name): return getattr(base_repository,name)
        @contextmanager
        def transaction(self):
            with base_repository.transaction() as tx: yield tx
            if armed[0]:
                armed[0]=False
                raise CommitUnknown('injected after actual commit')
    loss_runs=Runs(AckLoss(),runs.valid)
    loss_runs.accept(binding4)
    loss_runs.apply(Event(binding4,1,'start-ack','started'))
    recovery_provider=FakeProvider()
    loss_worker=RunWorker(scope=scope,messages=messages,runs=loss_runs,provider=recovery_provider,
        drafts=DraftPublisher(database.trip_repository(scope)),needs_lease=lambda b:lease.hold(tokens['alice'],b))
    armed[0]=True
    try:
        loss_worker._step(binding4,lambda:loss_worker.drafts.publish(binding4.run_id,'{"title":"original","items":["pending"]}'),
            lambda d:'trip_proposal:'+d.proposal_id,draft=True)
    except CommitUnknown: pass
    else: raise AssertionError('commit ACK loss reported success')
    recovered=loss_worker._one(receipt4)
    assert recovered.status=='unknown' and recovery_provider.calls==0
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+binding4.run_id,)).fetchone()[0]==1

    # Cancellation wins between chunks, outside the first provider advance fence.
    mid5,raw5=send()
    receipt5=boundary.receive(tokens['alice'],raw5)
    binding5=Binding(scope,receipt5.conversation_id,receipt5.generation,mid5,receipt5.run_id,receipt5.sequence)
    class CancelsDuringDraft(FakeProvider):
        def stream(self,messages,system=None):
            self.calls+=1
            if system is None: yield 'answer before cancellation'
            else:
                yield '{"title":"late",'
                runs.cancel(binding5)
                yield '"items":["late"]}'
    cancelled_worker=RunWorker(scope=scope,messages=messages,runs=runs,provider=CancelsDuringDraft(),
        drafts=DraftPublisher(database.trip_repository(scope)),needs_lease=lambda b:lease.hold(tokens['alice'],b))
    cancelled=cancelled_worker._one(receipt5)
    assert cancelled.status=='cancelled' and cancelled.proposal_id is None
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+binding5.run_id,)).fetchone()[0]==0
    for failure_stage in ('before_call','after_publish','connection_lost'):
        mid6,raw6=send()
        receipt6=boundary.receive(tokens['alice'],raw6)
        binding6=Binding(scope,receipt6.conversation_id,receipt6.generation,mid6,receipt6.run_id,receipt6.sequence)
        published=[False]; injected=[False]
        class PublishedMarker(DraftPublisher):
            def publish(self,*args,**kwargs):
                result=super().publish(*args,**kwargs)
                published[0]=True
                return result
        class CloseFailure:
            def __init__(self,connection): self.connection=connection
            def __getattr__(self,name): return getattr(self.connection,name)
            def cursor(self):
                cursor=self.connection.cursor()
                owner=self
                class LostCursor:
                    def __getattr__(self,name): return getattr(cursor,name)
                    def execute(self,sql,*args,**kwargs):
                        if failure_stage=='connection_lost' and not injected[0] and sql.startswith('SELECT b.needs_id'):
                            injected[0]=True
                            owner.connection.close()
                        return cursor.execute(sql,*args,**kwargs)
                return LostCursor()
            def close(self):
                self.connection.close()
                if not injected[0] and (failure_stage=='before_call' or published[0]):
                    injected[0]=True
                    raise OSError('injected after actual connection close')
        def faulty_resolve(principal):
            factory,owner,needs=resolve(principal)
            return lambda:CloseFailure(factory()),owner,needs
        failing_lease=RevisionLease(checker,faulty_resolve,environment='local',issuer=ISSUER,audience=AUDIENCE)
        failing_provider=FakeProvider()
        failing_worker=RunWorker(scope=scope,messages=messages,runs=runs,provider=failing_provider,
            drafts=PublishedMarker(database.trip_repository(scope)),needs_lease=lambda b:failing_lease.hold(tokens['alice'],b))
        outcome=failing_worker._one(receipt6)
        assert injected[0] and outcome.status=='unknown'
        if failure_stage in ('before_call','connection_lost'): assert failing_provider.calls==0
        with psycopg.connect(**config) as admin:
            count=admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+binding6.run_id,)).fetchone()[0]
            assert count==(1 if failure_stage=='after_publish' else 0)
        before_calls=failing_provider.calls
        assert failing_worker._one(receipt6).status=='unknown'
        assert failing_provider.calls==before_calls
    original_enqueue=MessageTransaction.enqueue
    for failure in ('after_writes','revoked_before_commit'):
        rejected_mid,rejected_raw=send()
        def enqueue_then_fail(tx, receipt):
            original_enqueue(tx,receipt)
            if failure=='after_writes': raise RuntimeError('injected after all transaction writes')
            (auth/'invited.json').write_text('["bob"]')
        try:
            with patch.object(MessageTransaction,'enqueue',enqueue_then_fail):
                boundary.receive(tokens['alice'],rejected_raw)
        except (RuntimeError,AccessBlocked): pass
        else: raise AssertionError('fault/revocation unexpectedly committed')
        finally: (auth/'invited.json').write_text('["alice","bob"]')
        with psycopg.connect(**config) as admin:
            for table,column in (('cj_message_receipt','message_id'),('cj_message_delivery','message_id'),('cj_message_needs_binding','message_id')):
                assert admin.execute('SELECT count(*) FROM '+table+' WHERE '+column+'=%s',(rejected_mid,)).fetchone()[0]==0
        accepted=boundary.receive(tokens['alice'],rejected_raw)
        assert accepted.message_id==rejected_mid
    print('PASS binding atomic rollback/revocation/replay, revision/publication ordering, cancellation, ACK and close uncertainty; host UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
