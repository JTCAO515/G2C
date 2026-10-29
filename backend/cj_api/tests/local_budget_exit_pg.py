"""Canonical admission + runtime PG budget module tests; formal host remains PR4."""
import json
import time
import uuid
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import psycopg
from cj_api.local_app import LocalDatabase, ISSUER, AUDIENCE, KEY_ID, scope_for, InvitedSubjects
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import AdmissionStatus
from cj_auth.jwt_adapter import PyJWTVerifier, JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.auth_boundary import Boundary
from cj_message.domain import Service as Messages
from cj_message.postgres import Repository as MessageRepository
from cj_run.core import Service as Runs
from cj_run.postgres import Repository as RunRepository, CommitUnknown as RunCommitUnknown
from cj_run.step_usage import ledger_scope_for, StepStore, OriginalStepOnly
from cj_run.display_snapshot import DisplaySnapshotReader, DisplaySnapshotConfiguration, SnapshotUnavailable
from cj_usage.core import Config, Ledger, Meter
from cj_usage.codec import encode, decode
from cj_usage.postgres import PostgresRepository, CommitUnknown, RepositoryUnavailable
from cj_usage.local_provider_exit import LocalProviderExit, BudgetUnknown
from cj_agent.worker import RunWorker, original_context_valid
from cj_agent.draft import DraftPublisher
from cj_agent.provider import FakeProvider
import local_history_pg as harness


class TestUsageConnection:
    """Test-only transaction hook; real host config is not activated here."""
    def __init__(self, connection, account): self.connection,self.account=connection,account
    def __getattr__(self,name): return getattr(self.connection,name)
    def bind_scope(self,cursor):
        self.connection.bind_scope(cursor)
        cursor.execute("SELECT current_setting('cj.usage_scope',true)")
        assert cursor.fetchone()[0] in (None,'')
        cursor.execute("SELECT set_config('cj.usage_scope',%s,true)",(self.account,))


def exercise(auth, conninfo):
    subjects=['alice','race','draft','output','assoc-ack','reserve-ack','claim-ack','settle-ack','cancel-gap','cancel-ledger','success-draft','period','not-fake','revoke-claim','draft-claim-ack','time-bound']
    harness.dev_auth.init(auth,subjects)
    config=json.loads(conninfo.read_text()); database=LocalDatabase(conninfo)
    checker=AdmissionChecker(PyJWTVerifier(JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
        StaticPublicKeys({KEY_ID:VerificationKey('RS256',(auth/'public.pem').read_bytes())})),InvitedSubjects(auth/'invited.json'))
    tokens={s:harness.dev_auth.token(auth,s,30) for s in subjects}
    def resolve_message(principal):
        scope=scope_for(principal.issuer,principal.subject); database.provision(scope)
        return database.message_repository(scope)
    boundary=Boundary(checker,resolve_message,lambda:uuid.uuid4().hex)
    def setup(subject,budget,output_limit=1000,clock=time.time):
        scope=scope_for(ISSUER,subject); database.provision(scope)
        now=int(clock())
        cfg=Config('provider_call',budget,now-10,now+3600,4,1,10000,600)
        account=ledger_scope_for(scope,cfg)
        with psycopg.connect(**config) as admin:
            admin.execute('INSERT INTO cj_usage_ledger_candidate VALUES(%s,0,1,%s::jsonb)',(account,encode(Ledger(config=cfg))))
        def connect(): return TestUsageConnection(database.connect(scope),account)
        messages=Messages(database.message_repository(scope),lambda:None)
        def make_worker():
            run_repo=RunRepository(connect,scope,expires_at=datetime.now(timezone.utc)+timedelta(days=1),statement_timeout_ms=10000,lock_timeout_ms=5000)
            runs=Runs(run_repo,lambda b:original_context_valid(b,messages,lambda:checker.check(tokens[subject]).status is AdmissionStatus.ALLOWED))
            def meter(binding,requested):
                assert binding.scope==scope and requested==account
                return Meter(PostgresRepository(connect,account),cfg,clock)
            exit=LocalProviderExit(cfg,meter,clock=clock,output_limits={'answer':output_limit,'draft':output_limit},environment='local')
            return RunWorker(scope=scope,messages=messages,runs=runs,provider=FakeProvider(),
                drafts=DraftPublisher(database.trip_repository(scope)),budget_exit=exit)
        return scope,account,make_worker
    def send(subject,intent='none'):
        cid,mid=uuid.uuid4().hex,uuid.uuid4().hex
        chat=boundary.open_conversation(tokens[subject],cid)
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,text='Beijing',trip_id=None,
            creation_intent=intent,expected_generation=chat.generation,expected_sequence=0)).encode()
        return boundary.receive(tokens[subject],raw)
    def ledger(account):
        with psycopg.connect(**config) as admin:
            return decode(admin.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])

    scope,account,factory=setup('alice',1)
    first=send('alice'); worker=factory()
    assert worker._one(first).status=='completed' and worker.provider.calls==1
    second=send('alice'); rejected=factory()
    assert rejected._one(second).status=='failed' and rejected.provider.calls==0
    state=rejected.runs.snapshot(rejected._binding(second))
    assert state.budget_exhausted_stage=='answer'
    saved=ledger(account)
    assert Meter.exposure(saved)==1 and len(saved.attempts)==1
    repeated=factory(); assert repeated._one(first).status=='completed' and repeated.provider.calls==0
    assert Meter.exposure(ledger(account))==1

    scope,account,factory=setup('race',1)
    receipts=[send('race'),send('race')]; workers=[factory(),factory()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:pair[0]._one(pair[1]),zip(workers,receipts)))
    assert sorted(r.status for r in results)==['completed','failed']
    assert sum(w.provider.calls for w in workers)==1 and Meter.exposure(ledger(account))==1

    scope,account,factory=setup('draft',1)
    receipt=send('draft','consider_trip'); worker=factory()
    result=worker._one(receipt)
    assert result.status=='completed' and result.proposal_id is None and worker.provider.calls==1
    state=worker.runs.snapshot(worker._binding(receipt))
    assert state.draft_outcome=='budget_exhausted' and state.budget_exhausted_stage=='draft'
    assert Meter.exposure(ledger(account))==1
    reader=DisplaySnapshotReader(boundary,lambda principal,owner:worker.runs.repository,
                                configuration=DisplaySnapshotConfiguration(200000,400000))
    request_id='00000000-0000-4000-8000-000000000001'
    payload=json.loads(reader.read_draft_status_v2(tokens['draft'],receipt.message_id,request_id))
    assert payload['version']=='RUN-draft-status.2' and payload['budget_exhausted_stage']=='draft'
    assert payload['draft_outcome']=='budget_exhausted' and payload['run_status']=='completed'
    try: reader.read_draft_status(tokens['draft'],receipt.message_id,request_id)
    except SnapshotUnavailable: pass
    else: raise AssertionError('v1 silently accepted unrepresentable budget outcome')

    scope,account,factory=setup('output',1,1)
    receipt=send('output'); worker=factory()
    assert worker._one(receipt).status=='failed' and worker.provider.calls==1
    saved=ledger(account); attempt=next(iter(saved.attempts.values()))
    assert attempt.state=='unknown' and attempt.receipt is None and Meter.exposure(saved)==1
    for phase in ('assoc','reserve','claim','settle'):
        subject=phase+'-ack'
        scope,account,factory=setup(subject,2)
        receipt=send(subject); worker=factory()
        fired=[]
        owner=StepStore if phase=='assoc' else Meter
        method='create' if phase=='assoc' else phase
        original=getattr(owner,method)
        def committed_then_lost(instance,*args,**kwargs):
            result=original(instance,*args,**kwargs)
            if not fired:
                fired.append(True)
                raise (RunCommitUnknown if phase=='assoc' else CommitUnknown)('injected after durable commit')
            return result
        with patch.object(owner,method,committed_then_lost):
            outcome=worker._one(receipt)
        assert fired and outcome.status=='unknown'
        assert worker.provider.calls==(1 if phase=='settle' else 0)
        before=ledger(account)
        assert len(before.attempts)==(0 if phase=='assoc' else 1)
        # Reserve ACK loss may release a proven-unclaimed reservation only via
        # canonical cancel AFTER the durable RUN terminal. Claim keeps exposure.
        expected_exposure=1 if phase in ('claim','settle') else 0
        assert Meter.exposure(before)==expected_exposure
        with psycopg.connect(**config) as admin:
            association=admin.execute('SELECT attempt_id,command_bytes,input_bytes FROM cj_run_step_usage WHERE scope=%s AND run_id=%s',(scope,receipt.run_id)).fetchall()
            assert len(association)==1
        replay=factory(); assert replay._one(receipt).status=='unknown' and replay.provider.calls==0
        assert Meter.exposure(ledger(account))==expected_exposure
        with psycopg.connect(**config) as admin:
            assert admin.execute('SELECT attempt_id,command_bytes,input_bytes FROM cj_run_step_usage WHERE scope=%s AND run_id=%s',(scope,receipt.run_id)).fetchall()==association

    # Cancellation wins after Stage A commit but before any reserve/claim.
    scope,account,factory=setup('cancel-gap',1)
    receipt=send('cancel-gap'); worker=factory()
    prepare=LocalProviderExit.prepare
    def prepare_then_cancel(exit,runs,binding,*args):
        prepared=prepare(exit,runs,binding,*args)
        runs.cancel(binding)
        return prepared
    with patch.object(LocalProviderExit,'prepare',prepare_then_cancel):
        assert worker._one(receipt).status=='cancelled'
    assert worker.provider.calls==0 and not ledger(account).attempts

    # RUN cancellation commits first; a failed Meter.cancel cannot reopen it.
    scope,account,factory=setup('cancel-ledger',1)
    receipt=send('cancel-ledger'); worker=factory(); binding=worker._binding(receipt)
    class CancelInFlight(FakeProvider):
        def stream(self,messages,system=None):
            for index,chunk in enumerate(super().stream(messages,system=system)):
                yield chunk
                if index==0: worker.runs.cancel(binding)
    worker.provider=CancelInFlight()
    cancellation=Meter.cancel; failed=[]
    def unavailable_cancel(meter,*args):
        if not failed:
            failed.append(True)
            raise RepositoryUnavailable('injected cancellation unavailable')
        return cancellation(meter,*args)
    try:
        with patch.object(Meter,'cancel',unavailable_cancel): worker._one(receipt)
    except BudgetUnknown: pass
    else: raise AssertionError('ledger cancellation failure was hidden')
    assert worker.runs.snapshot(binding).status=='cancelled'
    calls=worker.provider.calls
    assert worker._one(receipt).status=='cancelled' and worker.provider.calls==calls==1
    assert Meter.exposure(ledger(account))==1
    stop_calls=[]
    def still_unavailable(meter,*args):
        stop_calls.append(True)
        raise RepositoryUnavailable('injected persistent stop failure')
    try:
        with patch.object(Meter,'cancel',still_unavailable): worker._one(receipt)
    except BudgetUnknown: pass
    else: raise AssertionError('persistent stop failure hidden')
    assert len(stop_calls)==1, 'terminal stop was retried inside the same invocation'
    scope,account,factory=setup('success-draft',2)
    receipt=send('success-draft','consider_trip'); worker=factory()
    result=worker._one(receipt)
    assert result.status=='completed' and result.proposal_id and worker.provider.calls==2
    saved=ledger(account)
    assert len(saved.attempts)==2 and Meter.exposure(saved)==2
    assert all(a.state=='settled' and a.receipt.actual==1 for a in saved.attempts.values())
    with psycopg.connect(**config) as admin:
        steps=admin.execute('SELECT step_key,attempt_id FROM cj_run_step_usage WHERE scope=%s AND run_id=%s',(scope,receipt.run_id)).fetchall()
        assert {s[0] for s in steps}=={'answer','draft'} and len({s[1] for s in steps})==2
    repeated=factory(); assert repeated._one(receipt).status=='completed' and repeated.provider.calls==0
    assert Meter.exposure(ledger(account))==2

    old_time=time.time()
    scope,old_account,old_factory=setup('period',1,clock=lambda:old_time)
    old_receipt=send('period'); old_worker=old_factory()
    assert old_worker._one(old_receipt).status=='completed'
    old_binding=old_worker._binding(old_receipt)
    old_step=StepStore(old_worker.runs,old_worker.budget_exit.config).read_original(old_binding,'answer')
    _,new_account,new_factory=setup('period',1,clock=lambda:old_time+4000)
    new_receipt=send('period'); new_worker=new_factory()
    assert new_worker._one(new_receipt).status=='completed'
    assert old_account!=new_account and Meter.exposure(ledger(old_account))==Meter.exposure(ledger(new_account))==1
    assert StepStore(old_factory().runs,old_worker.budget_exit.config).read_original(old_binding,'answer')==old_step
    try: StepStore(new_worker.runs,new_worker.budget_exit.config).read_original(old_binding,'answer')
    except OriginalStepOnly: pass
    else: raise AssertionError('current period silently replaced original association')

    scope,account,factory=setup('not-fake',1)
    receipt=send('not-fake'); worker=factory()
    class NotFake:
        calls=0
        def stream(self,*args,**kwargs):
            self.calls+=1
            raise AssertionError('unsupported provider called')
    worker.provider=NotFake()
    assert worker._one(receipt).status=='unknown' and worker.provider.calls==0
    assert not ledger(account).attempts
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_run_step_usage WHERE scope=%s',(scope,)).fetchone()[0]==0
    wrong_before=encode(ledger(old_account))
    wrong_meter=old_worker.budget_exit.resolve_meter(old_binding,old_account)
    receipt=send('not-fake'); wrong_worker=factory()
    wrong_worker.budget_exit.resolve_meter=lambda binding,requested:wrong_meter
    try: wrong_worker._one(receipt)
    except BudgetUnknown: pass
    else: raise AssertionError('wrong budget partition was hidden')
    assert wrong_worker.provider.calls==0
    assert wrong_worker.runs.snapshot(wrong_worker._binding(receipt)).status=='unknown'
    assert encode(ledger(old_account))==wrong_before
    scope,account,factory=setup('revoke-claim',1)
    receipt=send('revoke-claim'); worker=factory()
    original_claim=Meter.claim
    def claim_then_revoke(meter,*args):
        result=original_claim(meter,*args)
        (auth/'invited.json').write_text(json.dumps([s for s in subjects if s!='revoke-claim']))
        return result
    try:
        with patch.object(Meter,'claim',claim_then_revoke): outcome=worker._one(receipt)
    finally: (auth/'invited.json').write_text(json.dumps(subjects))
    assert outcome.status=='context_invalid' and worker.provider.calls==0
    saved=ledger(account)
    assert Meter.exposure(saved)==1 and all(a.state=='unknown' and a.receipt is None for a in saved.attempts.values())
    scope,account,factory=setup('draft-claim-ack',2)
    receipt=send('draft-claim-ack','consider_trip'); worker=factory()
    count=[]; claim=Meter.claim
    def second_claim_ack_lost(meter,*args):
        result=claim(meter,*args); count.append(True)
        if len(count)==2: raise CommitUnknown('injected second claim ACK loss')
        return result
    with patch.object(Meter,'claim',second_claim_ack_lost): result=worker._one(receipt)
    state=worker.runs.snapshot(worker._binding(receipt))
    assert result.status=='unknown' and worker.provider.calls==1 and 'Beijing' in state.text
    assert state.draft_outcome is None and Meter.exposure(ledger(account))==2
    with psycopg.connect(**config) as admin:
        assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+receipt.run_id,)).fetchone()[0]==0

    tick=[time.time()]
    scope,account,factory=setup('time-bound',1,clock=lambda:tick[0])
    receipt=send('time-bound'); worker=factory()
    class AdvancesClock(FakeProvider):
        def stream(self,messages,system=None):
            for index,chunk in enumerate(super().stream(messages,system=system)):
                if index==1: tick[0]+=601
                yield chunk
    worker.provider=AdvancesClock()
    result=worker._one(receipt)
    assert result.status=='failed' and worker.provider.calls==1
    assert worker.runs.snapshot(worker._binding(receipt)).budget_exhausted_stage=='answer'
    assert Meter.exposure(ledger(account))==1
    print('PASS PG quota/concurrency, two-step receipts, original periods, ACK/cancel faults and FakeProvider-only gate; host UNRUN')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
