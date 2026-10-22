"""Run ONLY via private_pg.py against its newly provisioned empty cluster."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import unittest
import uuid
import psycopg
from cj_cleanup import core
from cj_cleanup.postgres import Repository, CommitUnknown, Unavailable
from test_cleanup import CleanupTests

CONFIG = None

class Wrapped:
    def __init__(self, conn, mode): self.conn,self.mode=conn,mode
    def __getattr__(self,name): return getattr(self.conn,name)
    def commit(self):
        if self.mode == 'before_commit': raise RuntimeError('SENSITIVE_FAULT_PAYLOAD')
        self.conn.commit()
        if self.mode == 'after_commit': raise RuntimeError('SENSITIVE_FAULT_PAYLOAD')
    def close(self):
        self.conn.close()
        if self.mode == 'close_after': raise RuntimeError('SENSITIVE_FAULT_PAYLOAD')


class PostgresTests(unittest.TestCase):
    def setUp(self):
        if CONFIG is None: self.skipTest('only task-private new cluster runner may supply config')
        self.f=CleanupTests();self.f.setUp()
        self.scope=replace(self.f.scope,subject='synthetic-'+uuid.uuid4().hex)
        self.initial=self.f.op(True,self.scope)
        self.factory=lambda:psycopg.connect(**CONFIG)
        self.repo=Repository(self.factory,self.scope,lambda stage:None)
        self.op=self.repo.create(self.initial)

    def settle(self,op,target,outcome='confirmed',repo=None):
        repo=repo or self.repo
        op=repo.intent(op.operation_id,op.revision,target,'call-'+str(op.revision))
        return repo.receipt(op.operation_id,op.revision,target,self.f.result(op,target,outcome))

    def test_original_create_conflict_and_other_scope(self):
        self.assertEqual(self.repo.create(self.initial),self.op)
        with self.assertRaises(core.Conflict): self.repo.create(replace(self.initial,confirmation_digest='0'*64))
        with self.assertRaises(core.Conflict): self.repo.create(replace(self.initial,operation_id='new-operation'))
        other=Repository(self.factory,replace(self.scope,subject='other'),lambda s:None)
        with self.assertRaises(core.Denied): other.query(self.op.operation_id)
        with self.assertRaises(core.Denied): other.create(self.initial)
        self.assertEqual(self.repo.query(self.op.operation_id),self.op)

    def test_intent_original_bytes_restart_and_unknown_reconciliation(self):
        op=self.repo.intent(self.op.operation_id,0,'auth_revocation','original')
        another=Repository(self.factory,self.scope,lambda s:None)
        self.assertEqual(another.query(op.operation_id),op)
        op=another.recover(op.operation_id,op.revision)
        self.assertEqual(op.status,'unknown')
        with self.assertRaises(core.Conflict): another.intent(op.operation_id,op.revision,'auth_revocation','new-id')
        raw=b' '+self.f.result(op,'auth_revocation')+b'\n'
        op=another.receipt(op.operation_id,op.revision,'auth_revocation',raw)
        self.assertEqual(op.steps[0].receipt_bytes,raw)
        self.assertEqual(another.receipt(op.operation_id,op.revision,'auth_revocation',raw),op)
        with self.assertRaises(core.Conflict): another.receipt(op.operation_id,op.revision,'auth_revocation',raw.strip())
        self.assertEqual(core.Repository.rebuild(another.journal(op.operation_id),recover_inflight=False).query(self.scope,op.operation_id),op)

    def test_concurrent_cas_one_original_intent(self):
        def act(n):
            try: return self.repo.intent(self.op.operation_id,0,'auth_revocation','original-'+str(n))
            except core.Conflict: return None
        with ThreadPoolExecutor(2) as pool: out=list(pool.map(act,range(2)))
        self.assertEqual(sum(x is not None for x in out),1)
        self.assertEqual(self.repo.query(self.op.operation_id).revision,1)

    def test_invalid_receipts_atomic_no_state_or_journal_change(self):
        op=self.repo.intent(self.op.operation_id,0,'auth_revocation','original')
        original=self.repo.journal(op.operation_id)
        valid=self.f.result(op,'auth_revocation')
        for raw in (valid.decode().encode('utf-16'),valid.replace(b'"outcome":"confirmed"',b'"outcome":"unknown","outcome":"confirmed"')):
            with self.assertRaises(core.Invalid): self.repo.receipt(op.operation_id,op.revision,'auth_revocation',raw)
            self.assertEqual(self.repo.query(op.operation_id),op)
            self.assertEqual(self.repo.journal(op.operation_id),original)

    def test_rollback_guard_before_commit_atomic(self):
        def deny(stage):
            if stage=='commit': raise core.Denied('synthetic guard revoked')
        guarded=Repository(self.factory,self.scope,deny)
        original=self.repo.journal(self.op.operation_id)
        with self.assertRaises(core.Denied): guarded.intent(self.op.operation_id,0,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id),self.op)
        self.assertEqual(self.repo.journal(self.op.operation_id),original)

    def test_commit_lost_ack_reads_original_without_retry(self):
        fault=Repository(lambda:Wrapped(self.factory(),'after_commit'),self.scope,lambda s:None)
        with self.assertRaises(CommitUnknown): fault.intent(self.op.operation_id,0,'auth_revocation','original')
        op=self.repo.query(self.op.operation_id)
        self.assertEqual(op.steps[0].invocation,'original')
        op=self.repo.recover(op.operation_id,op.revision)
        self.assertEqual(op.status,'unknown')
        # Original actual receipt commit also loses ACK; read, never dispatch again.
        with self.assertRaises(CommitUnknown): fault.receipt(op.operation_id,op.revision,'auth_revocation',self.f.result(op,'auth_revocation','unknown'))
        read=self.repo.query(op.operation_id)
        self.assertEqual(read.status,'unknown')
        self.assertEqual(read.steps[0].receipt_bytes,self.f.result(op,'auth_revocation','unknown'))

    def test_commit_did_not_happen_still_unknown_caller_no_fake_rollback_claim(self):
        fault=Repository(lambda:Wrapped(self.factory(),'before_commit'),self.scope,lambda s:None)
        with self.assertRaises(CommitUnknown): fault.intent(self.op.operation_id,0,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id),self.op)

    def test_lost_create_ack_and_close_failure_preserve_original(self):
        scope=replace(self.scope,subject=self.scope.subject+'-new')
        initial=replace(self.initial,scope=scope)
        fault=Repository(lambda:Wrapped(self.factory(),'after_commit'),scope,lambda s:None)
        with self.assertRaises(CommitUnknown): fault.create(initial)
        reader=Repository(self.factory,scope,lambda s:None)
        self.assertEqual(reader.query(initial.operation_id),initial)
        fault=Repository(lambda:Wrapped(self.factory(),'close_after'),scope,lambda s:None)
        with self.assertRaises(CommitUnknown): fault.intent(initial.operation_id,0,'auth_revocation','original')
        self.assertEqual(reader.query(initial.operation_id).steps[0].invocation,'original')

    def test_post_commit_guard_loss_withholds_result(self):
        def deny(stage):
            if stage=='return': raise core.Denied('synthetic return denied')
        fault=Repository(self.factory,self.scope,deny)
        with self.assertRaises(CommitUnknown): fault.intent(self.op.operation_id,0,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id).revision,1)

    def test_autocommit_rejected_before_sql(self):
        def connect():
            c=self.factory();c.autocommit=True;return c
        with self.assertRaises(Unavailable): Repository(connect,self.scope,lambda s:None).intent(self.op.operation_id,0,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id),self.op)

    def test_partial_failure_and_retention_not_complete(self):
        op=self.settle(self.op,'auth_revocation')
        op=self.settle(op,'tasks_stopped')
        op=self.settle(op,'store:business')
        op=self.settle(op,'store:business/message','failed')
        loaded=Repository(self.factory,self.scope,lambda s:None).query(op.operation_id)
        self.assertEqual(loaded,op)
        self.assertEqual(loaded.status,'failed')
        self.assertEqual(next(s for s in loaded.steps if s.target=='store:business').state,'confirmed')
        self.assertTrue(all(s.state=='pending' for s in loaded.steps if s.target in ('offline_devices','backup_retention','external_retention')))

    def test_corrupted_state_fails_closed_without_rewriting_journal(self):
        before=self.repo.journal(self.op.operation_id)
        with self.factory() as c:
            c.execute('UPDATE cj_cleanup_journal_candidate SET state_bytes=%s WHERE scope_bytes=%s',(b'{}',core.encode(__import__('dataclasses').asdict(self.scope))))
        with self.assertRaises(Unavailable): self.repo.query(self.op.operation_id)
        with self.factory() as c:
            self.assertEqual(bytes(c.execute('SELECT journal_bytes FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s',(core.encode(__import__('dataclasses').asdict(self.scope)),)).fetchone()[0]),before)
