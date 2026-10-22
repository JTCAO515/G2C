"""Only run through private_pg.py, which injects a fresh Unix-socket configuration."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import threading
import unittest
import psycopg
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (TrustedPrincipal, VerificationResult, VerificationStatus,
                                CJAccessFacts, Fact)
from cj_feedback import (Action, Boundary, Conflict, Unavailable, ReferenceUnavailable,
                         CommitUnknown, OperationWithheld, InvalidInput)
from cj_feedback.postgres import Repository
from test_domain import raw

CONFIG = None


class Verifier:
    def __init__(self): self.subject = 'a'
    def verify(self, token):
        return VerificationResult(VerificationStatus.VALID,
            TrustedPrincipal('fixture-issuer',self.subject,'fixture-audience',1,1,9999999999))


class Access:
    def __init__(self): self.allowed = True; self.calls = 0; self.hook = None
    def evaluate(self, principal):
        self.calls += 1
        if self.hook: self.hook()
        return CJAccessFacts(principal,Fact.YES if self.allowed else Fact.NO,Fact.YES,Fact.YES)


class Wrapped:
    def __init__(self, connection, mode): self.c, self.mode = connection, mode
    def __getattr__(self, name): return getattr(self.c,name)
    def commit(self):
        if self.mode == 'cancel_before': raise asyncio.CancelledError('SECRET')
        self.c.commit()
        if self.mode == 'lost_ack': raise RuntimeError('SECRET credentials')
        if self.mode == 'cancel_after': raise asyncio.CancelledError('SECRET')
    def close(self):
        self.c.close()
        if self.mode == 'close_interrupt': raise KeyboardInterrupt('SECRET')


class PostgresTests(unittest.TestCase):
    def setUp(self):
        if CONFIG is None: self.skipTest('requires private_pg.py; no ambient DSN')
        self.scope = self.id().split('.')[-1]
        self.verifier, self.access = Verifier(), Access()
        self.checker = AdmissionChecker(self.verifier,self.access,clock=lambda:100)
        self.factory = lambda: psycopg.connect(**CONFIG)
        self.resolve = lambda p: (self.factory, self.scope+'/'+p.subject)
        self.boundary = Boundary(self.checker,self.resolve)

    def encode(self, result):
        return json.dumps(asdict(result) if result is not None else None).encode()
    def submit(self, data=None):
        return self.boundary.with_operation('fixture-token',lambda op:self.encode(op.submit(Action(data or raw()))))
    def query(self, aid='one'):
        return self.boundary.with_operation('fixture-token',lambda op:self.encode(op.query_action(aid)))
    def count(self):
        with psycopg.connect(**CONFIG) as conn:
            return conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(self.scope+'/a',)).fetchone()[0]

    def test_exact_replay_conflict_and_one_record(self):
        first = self.submit()
        self.assertEqual(first,self.submit())
        self.assertEqual(first,self.query())
        for value in (b' '+raw(),raw(problem='different')):
            with self.assertRaises(Conflict): self.submit(value)
        self.assertEqual(1,self.count())
        self.assertEqual('submitted',json.loads(first)['status'])

    def test_cross_account_isolation_and_same_action(self):
        first = self.submit()
        self.verifier.subject = 'b'
        self.assertEqual(b'null',self.query())
        second = self.submit(raw(problem='B feedback'))
        self.assertNotEqual(first,second)
        self.verifier.subject = 'a'
        self.assertEqual(first,self.query())

    def test_cross_environment_scope_isolation(self):
        self.submit()
        other = Boundary(self.checker,lambda p:(self.factory,'different-environment/'+p.subject))
        self.assertEqual(b'null',other.with_operation('fixture-token',lambda op:self.encode(op.query_action('one'))))

    def test_references_foreign_missing_and_unconfirmed_same_rejection(self):
        for kind in ('message','run'):
            for aid in ('known-fixture','foreign','missing'):
                with self.subTest(kind=kind,aid=aid), self.assertRaises(ReferenceUnavailable) as cm:
                    self.submit(raw(references=[dict(kind='message',id=aid)] + ([dict(kind='run',id=aid)] if kind == 'run' else [])))
                self.assertEqual('feedback unavailable',str(cm.exception))
        self.assertEqual(0,self.count())

    def test_cannot_claim_user_diagnostics(self):
        with self.assertRaises(InvalidInput): self.submit(raw(usage={'tokens':99}))
        self.assertEqual(0,self.count())

    def test_concurrent_same_bytes_single_receipt(self):
        barrier = threading.Barrier(4)
        def worker(_):
            barrier.wait()
            return self.submit()
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(worker,range(4)))
        self.assertEqual(1,len(set(results)))
        self.assertEqual(1,self.count())

    def test_concurrent_different_bytes_conflict(self):
        barrier=threading.Barrier(2)
        def worker(index):
            barrier.wait()
            try: self.submit(raw(problem=str(index))); return 'submitted'
            except Conflict: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,range(2)))
        self.assertCountEqual(['submitted','conflict'],results)
        self.assertEqual(1,self.count())

    def test_guard_failure_before_commit_rolls_back(self):
        def guard(stage):
            if stage=='commit': raise Unavailable()
        repo=Repository(self.factory,self.scope+'/a',guard)
        with self.assertRaises(Unavailable): repo.submit(Action(raw()))
        self.assertEqual(0,self.count())

    def test_lost_commit_ack_original_query(self):
        self.factory=lambda:Wrapped(psycopg.connect(**CONFIG),'lost_ack')
        with self.assertRaises(OperationWithheld) as cm: self.submit()
        self.assertTrue(cm.exception.commit_possible)
        self.assertEqual('reconcile_original',cm.exception.recovery)
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.assertEqual('submitted',json.loads(self.query())['status'])
        self.assertEqual(1,self.count())

    def test_cancel_before_commit_is_unknown_until_query(self):
        self.factory=lambda:Wrapped(psycopg.connect(**CONFIG),'cancel_before')
        with self.assertRaises(OperationWithheld) as cm:self.submit()
        self.assertTrue(cm.exception.commit_possible)
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.assertEqual(b'null',self.query())
        self.assertEqual(0,self.count())

    def test_cancel_after_commit_retains_receipt(self):
        self.factory=lambda:Wrapped(psycopg.connect(**CONFIG),'cancel_after')
        with self.assertRaises(OperationWithheld):self.submit()
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.assertEqual('submitted',json.loads(self.query())['status'])
        self.assertEqual(1,self.count())

    def test_close_interrupt_is_not_success(self):
        self.factory=lambda:Wrapped(psycopg.connect(**CONFIG),'close_interrupt')
        with self.assertRaises(OperationWithheld):self.submit()
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.assertEqual(1,self.count())
        self.assertEqual('submitted',json.loads(self.query())['status'])

    def test_revoke_during_projection_withholds_but_preserves_commit(self):
        def operation(op):
            receipt=op.submit(Action(raw()))
            self.access.allowed=False
            return self.encode(receipt)
        with self.assertRaises(OperationWithheld) as cm:self.boundary.with_operation('fixture-token',operation)
        self.assertTrue(cm.exception.commit_possible)
        self.access.allowed=True
        self.assertEqual('submitted',json.loads(self.query())['status'])

    def test_identity_change_during_query_projection(self):
        self.submit()
        def operation(op):
            result=op.query_action('one')
            self.verifier.subject='b'
            return self.encode(result)
        with self.assertRaises(Unavailable):self.boundary.with_operation('fixture-token',operation)
        self.assertEqual(b'null',self.query())

    def test_resolver_mutation_withholds(self):
        def operation(op):
            receipt=op.submit(Action(raw()))
            self.boundary.resolve=lambda p:(self.factory,'attacker')
            return self.encode(receipt)
        with self.assertRaises(OperationWithheld):self.boundary.with_operation('fixture-token',operation)
        self.assertEqual(1,self.count())

    def test_swallowed_failure_poisoned_operation(self):
        def operation(op):
            try: op.submit(Action(raw(references=[dict(kind='message',id='missing')])))
            except ReferenceUnavailable: pass
            return b'false success'
        with self.assertRaises(OperationWithheld):self.boundary.with_operation('fixture-token',operation)
        self.assertEqual(0,self.count())

    def test_lifetime_and_second_write(self):
        saved=[]
        self.boundary.with_operation('fixture-token',lambda op:(saved.append(op) or b'ok'))
        with self.assertRaises(OperationWithheld):saved[0].query_action('one')
        def operation(op):
            op.submit(Action(raw()))
            op.submit(Action(raw('two')))
            return b'false success'
        with self.assertRaises(OperationWithheld):self.boundary.with_operation('fixture-token',operation)
        self.assertEqual(1,self.count())

    def test_foreign_thread_context_rejected(self):
        def operation(op):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(OperationWithheld):pool.submit(op.query_action,'one').result()
            return b'false success'
        with self.assertRaises(OperationWithheld):self.boundary.with_operation('fixture-token',operation)

    def test_async_callback_forbidden(self):
        async def callback(op): return b'no'
        with self.assertRaises(InvalidInput):self.boundary.with_operation('fixture-token',callback)
        self.assertEqual(0,self.count())

    def test_fresh_connection_required_preserves_foreign_work(self):
        conn=psycopg.connect(**CONFIG)
        conn.execute('SELECT 1')
        try:
            repo=Repository(lambda:conn,self.scope+'/a',lambda stage:None)
            with self.assertRaises(Unavailable):repo.submit(Action(raw()))
            self.assertFalse(conn.closed)
            self.assertEqual(2, conn.info.transaction_status)
        finally:conn.close()
        self.assertEqual(0,self.count())

    def test_private_content_minimized_and_no_exception_logging(self):
        secret='USER_VOLUNTARILY_TYPED_SENTINEL'
        self.submit(raw(problem=secret))
        with psycopg.connect(**CONFIG) as conn:
            row=conn.execute('SELECT original_input FROM cj_feedback_action WHERE scope=%s',(self.scope+'/a',)).fetchone()
            self.assertEqual(raw(problem=secret),bytes(row[0]))
            cols=[r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='cj_feedback_action'")]
            self.assertCountEqual(['scope','operation','action_id','original_input','input_sha256','source_reference','submitted_at'],cols)
        self.assertNotIn(secret,self.query().decode())
        self.factory=lambda:(_ for _ in ()).throw(RuntimeError('SECRET token=...'))
        with self.assertNoLogs(), self.assertRaises(Unavailable) as cm:self.query()
        self.assertNotIn('SECRET',str(cm.exception))

    def test_auth_rechecked_inside_transaction(self):
        normal=self.factory
        def connect():
            conn=normal()
            self.access.allowed=False
            return conn
        self.factory=connect
        with self.assertRaises(Unavailable):self.submit()
        self.assertEqual(0,self.count())
