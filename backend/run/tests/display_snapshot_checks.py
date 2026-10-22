"""Real fixed AUTH/MESSAGE/RUN classes, synthetic identity facts and storage only."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import unittest
from unittest.mock import patch
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import TrustedPrincipal, VerificationResult, VerificationStatus, CJAccessFacts, Fact
from cj_message.auth_boundary import Boundary, AccessBlocked, IdentityChanged
from cj_message.domain import Stored, Receipt, Chat, Unavailable
from cj_run.core import Binding, Event, Service, Denied, Conflict, ResyncRequired
from cj_run.fixture import MemoryRepository
from cj_run.postgres import Repository as PgRepository, CommitUnknown
from cj_run.usage_binding import UsageBinding
from cj_run.display_snapshot import DisplaySnapshotReader, DisplaySnapshotConfiguration, SnapshotUnavailable, SnapshotChanged, SnapshotTooLarge
from cj_run import display_snapshot


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.p=TrustedPrincipal('https://synthetic.invalid','user-a','fixture',1,1,100)
        self.invited=Fact.YES
        self.generation='g1'
        self.msg_active=True
        self.run_resolves=[]
        raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='mé',text='PRIVATE_USER_BODY',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
        self.original=Stored(raw,Receipt('mé','chat','g1',1,'original-run',hashlib.sha256(raw).hexdigest()))
        self.stored=self.original
        owner=self
        class Verifier:
            def verify(self,token): return VerificationResult(VerificationStatus.VALID,owner.p)
        class Access:
            def evaluate(self,p): return CJAccessFacts(p,Fact.YES,Fact.YES,owner.invited)
        class MessageRepo:
            def __init__(self,scope): self.scope=scope
            @contextmanager
            def transaction(self): yield self
            def lock_scope(self): pass
            def find(self,mid): return owner.stored if self.scope=='trusted-a' else None
            def chat(self,cid,generation=None):
                if not owner.msg_active or cid!='chat' or generation!=owner.generation: raise Unavailable()
                return Chat(owner.generation,0,1)
        self.message_repo=MessageRepo('trusted-a')
        self.boundary=Boundary(AdmissionChecker(Verifier(),Access(),clock=lambda:50),
                              lambda p:self.message_repo if p.subject=='user-a' else MessageRepo('trusted-b'),lambda:'unused')
        class RunRepo:
            scope='trusted-a'
            epoch='epoch1'
            active=True
            expired=False
            error=None
            exit_error=None
            def __init__(self): self.memory=MemoryRepository()
            @contextmanager
            def transaction(self):
                if not self.active: raise Denied('inactive')
                if self.expired: raise ResyncRequired('expired')
                if self.error: raise self.error
                with self.memory.transaction() as tx:
                    tx.epoch=self.epoch
                    yield tx
                    if self.exit_error: raise self.exit_error
            recover=PgRepository.recover  # Execute the actual existing recovery method.
        self.repo=RunRepo()
        self.binding=Binding('trusted-a','chat','g1','mé','original-run',1)
        self.service=Service(self.repo,lambda _:True)
        outbound=b'PRIVATE_OUTBOUND'
        usage=UsageBinding(json.dumps(dict(attempt_id='PRIVATE_ATTEMPT',operation_id='PRIVATE_OPERATION',run_id='original-run',kind='model',input_digest=hashlib.sha256(outbound).hexdigest(),reserve=5,output_limit=5)).encode(),outbound)
        self.service.accept_with_usage(self.binding,usage)
        def resolve(principal,scope):
            self.run_resolves.append((principal,scope))
            return self.repo
        self.reader=DisplaySnapshotReader(self.boundary,resolve,configuration=DisplaySnapshotConfiguration(10000,20000))
    def event(self,kind,value=''):
        seq=self.service.snapshot(self.binding).sequence+1
        return self.service.apply(Event(self.binding,seq,f'e{seq}',kind,value))
    def seed_text(self):
        self.event('started')
        self.event('text_delta','已持久显示文本 / stored display text')
        self.event('effect_committed','PRIVATE_EFFECT_RECEIPT')
    def read(self): return self.reader.read('synthetic','mé')

    def test_queued_and_all_persisted_statuses(self):
        queued=json.loads(self.read())
        self.assertEqual((queued['status'],queued['text'],queued['text_state'],queued['event_highwater']),('queued','','partial',0))
        for status in ('running','completed','failed','cancelled','unknown','context_invalid'):
            with self.subTest(status=status):
                self.setUp(); self.seed_text()
                if status!='running': self.event(status)
                result=json.loads(self.read())
                self.assertEqual(result['status'],status)
                self.assertEqual(result['text'],'已持久显示文本 / stored display text')
                self.assertEqual(result['text_state'],'complete' if status=='completed' else 'partial')
                self.assertEqual(result['event_highwater'],3 if status=='running' else 4)

    def test_allowlist_and_exact_source_refs(self):
        self.seed_text()
        raw=self.read(); data=json.loads(raw)
        self.assertEqual(set(data),{'conversation_id','generation','message_id','run_id','message_sequence','status','event_highwater','text','text_state'})
        self.assertEqual((data['conversation_id'],data['generation'],data['message_id'],data['run_id'],data['message_sequence']),('chat','g1','mé','original-run',1))
        for value in (b'PRIVATE_',b'trusted-a',b'input_digest',b'usage',b'effects',b'event_id',b'model_version',b'failure_stage'):
            self.assertNotIn(value,raw)
        self.assertEqual(self.run_resolves,[(self.p,'trusted-a')])

    def test_foreign_user_and_missing_message_never_resolve_run(self):
        self.p=replace(self.p,subject='user-b')
        with self.assertRaises(SnapshotUnavailable): self.read()
        self.assertEqual(self.run_resolves,[])
        self.setUp(); self.stored=None
        with self.assertRaises(SnapshotUnavailable): self.read()
        self.assertEqual(self.run_resolves,[])

    def test_missing_run_and_all_binding_mismatches(self):
        for field,value in [('scope','other'),('conversation_id','other'),('generation','other'),('message_id','other'),('run_id','other'),('message_sequence',2)]:
            with self.subTest(field=field):
                self.setUp()
                state=self.service.snapshot(self.binding)
                self.repo.memory.rows.clear()  # Synthetic fixture setup only.
                wrong=replace(self.binding,**{field:value})
                self.repo.memory.rows[wrong.scope,wrong.run_id]=replace(state,binding=wrong)
                with self.assertRaises(Conflict): self.read()
        self.setUp(); self.repo.memory.rows.clear()
        with self.assertRaises(Conflict): self.read()

    def test_old_generation_and_inactive_or_expired(self):
        self.generation='g2'
        with self.assertRaises(Unavailable): self.read()
        self.setUp(); self.msg_active=False
        with self.assertRaises(Unavailable): self.read()
        self.setUp(); self.repo.active=False
        with self.assertRaises(Denied): self.read()
        self.setUp(); self.repo.expired=True
        with self.assertRaises(ResyncRequired): self.read()

    def test_resolver_wrong_scope_or_changes_original(self):
        self.reader.resolve_run_repository=lambda p,s:self.foreign_repo()
        with self.assertRaises(SnapshotChanged): self.read()
        self.setUp()
        def resolver(p,s):
            self.stored=replace(self.original,receipt=replace(self.original.receipt,run_id='replacement'))
            return self.repo
        self.reader.resolve_run_repository=resolver
        with self.assertRaises(SnapshotChanged): self.read()
    def foreign_repo(self):
        self.repo.scope='foreign'
        return self.repo

    def test_projection_changes_identity_source_or_epoch(self):
        encode=display_snapshot._encode_snapshot
        mutations=(lambda:setattr(self,'p',replace(self.p,subject='other')),
                   lambda:setattr(self,'stored',replace(self.original,receipt=replace(self.original.receipt,sequence=2))),
                   lambda:setattr(self.repo,'epoch','epoch2'),
                   lambda:setattr(self,'generation','g2'))
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.setUp()
                def changed(state,config):
                    result=encode(state,config); mutate(); return result
                with patch.object(display_snapshot,'_encode_snapshot',changed):
                    with self.assertRaises((IdentityChanged,SnapshotChanged,Unavailable)): self.read()

    def test_projection_new_run_event_withholds_stale_response(self):
        encode=display_snapshot._encode_snapshot
        def changed(state,config):
            result=encode(state,config)
            self.event('cancelled')
            return result
        with patch.object(display_snapshot,'_encode_snapshot',changed):
            with self.assertRaises(SnapshotChanged): self.read()
        self.assertEqual(json.loads(self.read())['status'],'cancelled')

    def test_final_owner_guard_withholds_encoded_bytes(self):
        original=self.boundary.with_history_context
        def wrapper(token,operation):
            def revoke(ctx):
                result=operation(ctx); self.invited=Fact.UNKNOWN; return result
            return original(token,revoke)
        self.boundary.with_history_context=wrapper
        with self.assertRaises(AccessBlocked): self.read()

    def test_explicit_bounds_and_no_truncation(self):
        for args in ((0,100),(True,100),(100,-1)):
            with self.assertRaises(ValueError): DisplaySnapshotConfiguration(*args)
        with self.assertRaises(ValueError): DisplaySnapshotReader(self.boundary,lambda p,s:self.repo,configuration=None)
        self.seed_text()
        self.reader.configuration=DisplaySnapshotConfiguration(1,20000)
        with self.assertRaises(SnapshotTooLarge): self.read()
        self.reader.configuration=DisplaySnapshotConfiguration(10000,1)
        with self.assertRaises(SnapshotTooLarge): self.read()
        self.reader.configuration=DisplaySnapshotConfiguration(10000,20000)
        size=len(self.read())
        self.reader.configuration=DisplaySnapshotConfiguration(10000,size)
        self.assertEqual(len(self.read()),size)
        self.reader.configuration=DisplaySnapshotConfiguration(10000,size-1)
        with self.assertRaises(SnapshotTooLarge): self.read()

    def test_io_unknown_exit_and_cancellation_propagate(self):
        for error in (OSError('fixture read failed'),asyncio.CancelledError()):
            self.repo.error=error
            with self.assertRaises(type(error)): self.read()
        self.repo.error=None
        self.repo.exit_error=CommitUnknown()
        with self.assertRaises(CommitUnknown): self.read()
        self.repo.exit_error=None
        with patch.object(display_snapshot,'_encode_snapshot',side_effect=asyncio.CancelledError()):
            with self.assertRaises(asyncio.CancelledError): self.read()

    def test_corrupt_display_projection_not_published(self):
        self.repo.memory.rows[self.binding.scope,self.binding.run_id]=replace(self.service.snapshot(self.binding),text='NOT_A_COMMITTED_DELTA')
        with self.assertRaises(SnapshotUnavailable): self.read()


if __name__=='__main__': unittest.main(verbosity=2)
