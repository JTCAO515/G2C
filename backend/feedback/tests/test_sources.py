"""Real local MESSAGE/RUN repositories under their pinned public boundaries."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import unittest
import psycopg
from cj_auth.admission import AdmissionChecker
from cj_message.auth_boundary import Boundary as MessageBoundary
from cj_message.postgres import Repository as MessageRepository
from cj_run.core import Binding, Event, Service as RunService
from cj_run.postgres import Repository as RunRepository
from cj_feedback import Action, Boundary, Sources, ReferenceUnavailable, OperationWithheld, Unavailable
from test_domain import raw
from test_postgres import Verifier, Access

CONFIG=None


class SourceTests(unittest.TestCase):
    def setUp(self):
        if CONFIG is None:self.skipTest('private_pg.py required')
        self.prefix='sources/'+self.id().split('.')[-1]
        self.scope=self.prefix+'/a'
        self.verifier,self.access=Verifier(),Access()
        self.checker=AdmissionChecker(self.verifier,self.access,clock=lambda:100)
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.message=MessageBoundary(self.checker,lambda p:MessageRepository(self.factory,self.prefix+'/'+p.subject),lambda:'run-1')
        self.run_factory=self.factory
        self.resolve_count=0
        self.on_resolve=None
        def resolve(p,scope):
            self.resolve_count+=1
            if self.on_resolve:self.on_resolve(self.resolve_count)
            return RunRepository(self.run_factory,scope,expires_at=datetime.now(timezone.utc)+timedelta(hours=1),statement_timeout_ms=1000,lock_timeout_ms=1000)
        self.sources=Sources(self.message,resolve)
        self.boundary=Boundary(self.checker,lambda p:(self.factory,self.prefix+'/'+p.subject),sources=self.sources)
        with psycopg.connect(**CONFIG) as conn:
            for scope in (self.scope,self.prefix+'/b'):
                conn.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)',(scope,))
                conn.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,'chat','gen',1)",(scope,))
                conn.execute("INSERT INTO cj_run_scope VALUES (%s,'epoch',true)",(scope,))
        message_raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='message-1',text='PRIVATE_CHAT_SENTINEL',trip_id=None,creation_intent='none')).encode()
        receipt=self.message.receive('fixture-token',message_raw)
        self.binding=Binding(self.scope,receipt.conversation_id,receipt.generation,receipt.message_id,receipt.run_id,receipt.sequence)
        self.run=RunService(resolve(self.verifier.verify('fixture-token').principal,self.scope),lambda _:True)
        self.run.accept(self.binding)
        self.run.apply(Event(self.binding,1,'start','started'))
        self.run.apply(Event(self.binding,2,'text','text_delta','PRIVATE_RUN_SENTINEL'))
        self.run.apply(Event(self.binding,3,'effect','effect_committed','PRIVATE_TOOL_RECEIPT_SENTINEL'))
        self.run.apply(Event(self.binding,4,'end','completed'))
        self.resolve_count=0

    def encode(self,value):return json.dumps(asdict(value) if value else None).encode()
    def submit(self,refs=None,aid='one'):
        data=raw(aid,references=refs if refs is not None else [dict(kind='message',id='message-1')])
        return self.boundary.with_operation('fixture-token',lambda op:self.encode(op.submit(Action(data))))
    def query(self):return self.boundary.with_operation('fixture-token',lambda op:self.encode(op.query_action('one')))
    def sql(self,sql,*values):
        with psycopg.connect(**CONFIG) as conn:conn.execute(sql,values)
    def count(self):
        with psycopg.connect(**CONFIG) as conn:return conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(self.scope,)).fetchone()[0]

    def test_public_message_run_association_minimal_persisted(self):
        result=json.loads(self.submit())
        source=result['source']
        self.assertEqual(('message-1','run-1','completed',4),(source['message_id'],source['run_id'],source['run_status_at_read'],source['event_highwater_at_read']))
        self.assertEqual({'message_id','conversation_id','generation','message_sequence','run_id','message_input_sha256','run_status_at_read','event_highwater_at_read'},set(source))
        self.assertEqual(result,json.loads(self.query()))
        self.assertNotIn('PRIVATE_',json.dumps(result))
        with psycopg.connect(**CONFIG) as conn:
            data=conn.execute('SELECT original_input,source_reference::text FROM cj_feedback_action WHERE scope=%s',(self.scope,)).fetchone()
            self.assertNotIn(b'PRIVATE_',bytes(data[0]));self.assertNotIn('PRIVATE_',data[1])
        for unknown in ('model_version','rule_version','usage','duration','tool_result','failure_stage'):
            self.assertNotIn(unknown,source)

    def test_matching_run_only_from_original_message(self):
        result=json.loads(self.submit([dict(kind='message',id='message-1'),dict(kind='run',id='run-1')]))
        self.assertEqual('run-1',result['source']['run_id'])

    def test_foreign_and_missing_same_rejection(self):
        self.verifier.subject='b'
        for mid in ('message-1','missing'):
            with self.assertRaises(ReferenceUnavailable) as cm:self.submit([dict(kind='message',id=mid)])
            self.assertEqual('feedback unavailable',str(cm.exception))
        self.assertEqual(0,self.count())

    def test_run_substitution_rejected(self):
        for rid in ('other-user-run','missing'):
            with self.assertRaises(ReferenceUnavailable):self.submit([dict(kind='message',id='message-1'),dict(kind='run',id=rid)])
        self.assertEqual(0,self.count())

    def test_different_message_scope_rejected(self):
        self.message.resolve_repository=lambda p:MessageRepository(self.factory,self.prefix+'/b')
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_different_run_scope_rejected(self):
        original=self.sources.resolve_run
        self.sources.resolve_run=lambda p,s:original(p,self.prefix+'/b')
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_message_hash_corruption_rejected(self):
        self.sql('UPDATE cj_message_receipt SET input_sha256=%s WHERE scope=%s','0'*64,self.scope)
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_inactive_message_and_expired_run_rejected(self):
        self.sql('UPDATE cj_message_chat SET active=false WHERE scope=%s',self.scope)
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.sql('UPDATE cj_message_chat SET active=true WHERE scope=%s',self.scope)
        self.sql("UPDATE cj_run_record SET expires_at=clock_timestamp()-interval '1 second' WHERE scope=%s",self.scope)
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_inactive_run_scope_rejected(self):
        self.sql('UPDATE cj_run_scope SET active=false WHERE scope=%s',self.scope)
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_source_changed_during_run_read_rejected(self):
        def mutate(n):
            if n==1:self.sql('UPDATE cj_message_chat SET active=false WHERE scope=%s',self.scope)
        self.on_resolve=mutate
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_source_changed_before_feedback_commit_rollback(self):
        def mutate(n):
            if n==2:self.sql('UPDATE cj_message_chat SET active=false WHERE scope=%s',self.scope)
        self.on_resolve=mutate
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_source_changed_during_final_projection_commit_preserved(self):
        data=raw(references=[dict(kind='message',id='message-1')])
        def operation(op):
            result=op.submit(Action(data))
            self.sql('UPDATE cj_message_chat SET active=false WHERE scope=%s',self.scope)
            return self.encode(result)
        with self.assertRaises(OperationWithheld) as cm:self.boundary.with_operation('fixture-token',operation)
        self.assertTrue(cm.exception.commit_possible)
        self.assertEqual(1,self.count())
        # Recovery returns the immutable historical receipt, not current source status.
        self.assertEqual('completed',json.loads(self.query())['source']['run_status_at_read'])
        self.assertEqual(json.loads(self.query()),json.loads(self.submit()))

    def test_run_read_failure_never_null_success(self):
        self.run_factory=lambda:(_ for _ in ()).throw(RuntimeError('SECRET source DSN'))
        with self.assertRaises(ReferenceUnavailable) as cm:self.submit()
        self.assertNotIn('SECRET',str(cm.exception))
        self.assertEqual(0,self.count())

    def test_run_read_cancellation_never_null_success(self):
        import asyncio
        self.run_factory=lambda:(_ for _ in ()).throw(asyncio.CancelledError('SECRET'))
        with self.assertRaises(Unavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_message_receipt_not_run_completion(self):
        # A second accepted MESSAGE whose RUN has not been accepted is unavailable.
        self.message.new_run_id=lambda:'run-unaccepted'
        value=dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='message-2',text='PRIVATE',trip_id=None,creation_intent='none')
        self.message.receive('fixture-token',json.dumps(value).encode())
        with self.assertRaises(ReferenceUnavailable):self.submit([dict(kind='message',id='message-2')])
        self.assertEqual(0,self.count())

    def test_cancelled_and_unknown_status_not_successful_answer(self):
        # Distinct real bindings with canonical terminal events, never fake diagnostics.
        for index,status in enumerate(('cancelled','unknown'),2):
            self.message.new_run_id=lambda:'run-'+str(index)
            value=dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='message-'+str(index),text='PRIVATE',trip_id=None,creation_intent='none')
            r=self.message.receive('fixture-token',json.dumps(value).encode())
            b=Binding(self.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
            self.run.accept(b)
            if status=='unknown':
                # A preceding cancelled run is terminal, so original chat order permits start.
                self.run.apply(Event(b,1,'start-'+str(index),'started'))
                self.run.apply(Event(b,2,'end-'+str(index),status))
            else:self.run.apply(Event(b,1,'end-'+str(index),status))
            result=json.loads(self.submit([dict(kind='message',id=r.message_id)],aid='action-'+str(index)))
            self.assertEqual(status,result['source']['run_status_at_read'])

    def test_run_read_unknown_commit_is_unavailable(self):
        from test_postgres import Wrapped
        self.run_factory=lambda:Wrapped(psycopg.connect(**CONFIG),'lost_ack')
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_identity_changes_during_source_read_rejected(self):
        self.on_resolve=lambda n:setattr(self.verifier,'subject','b')
        with self.assertRaises(ReferenceUnavailable):self.submit()
        self.assertEqual(0,self.count())

    def test_run_observation_changes_before_commit_rejected(self):
        self.message.new_run_id=lambda:'queued-run'
        value=dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='queued-message',text='PRIVATE',trip_id=None,creation_intent='none')
        r=self.message.receive('fixture-token',json.dumps(value).encode())
        b=Binding(self.scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence)
        self.run.accept(b)
        def mutate(n):
            if n==2:self.run.apply(Event(b,1,'cancel-queued','cancelled'))
        self.on_resolve=mutate
        with self.assertRaises(ReferenceUnavailable):self.submit([dict(kind='message',id=r.message_id)])
        self.assertEqual(0,self.count())
