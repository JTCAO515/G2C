"""Exact independent probes + affected cleanup-error ordering controls."""
import unittest
from dataclasses import replace
import IndependentCloseFenceTests as original
import test_postgres as fixtures
from cj_cleanup import core
from cj_cleanup.postgres import Repository, CommitUnknown, Unavailable


class CloseActions:
    def __init__(self,conn,callback=lambda:None,*,fail_commit=False,fail_rollback=False,fail_close=False):
        self.conn,self.callback=conn,callback
        self.fail_commit,self.fail_rollback,self.fail_close=fail_commit,fail_rollback,fail_close
    def __getattr__(self,name): return getattr(self.conn,name)
    def commit(self):
        self.conn.commit()
        if self.fail_commit: raise RuntimeError('PRIMARY_COMMIT_TEST_SENTINEL')
    def rollback(self):
        self.conn.rollback()
        if self.fail_rollback: raise RuntimeError('SECONDARY_ROLLBACK_TEST_SENTINEL')
    def close(self):
        self.conn.close()
        self.callback()
        if self.fail_close: raise RuntimeError('SECONDARY_CLOSE_TEST_SENTINEL')


class CloseFenceTests(unittest.TestCase):
    setUp=fixtures.PostgresTests.setUp
    test_close_callback_revocation_withholds_committed_write=original.test_close_callback_revocation_withholds_committed_write
    test_close_callback_revocation_withholds_read=original.test_close_callback_revocation_withholds_read

    def test_body_conflict_wins_over_close_and_rollback_errors(self):
        fault=Repository(lambda:CloseActions(self.factory(),fail_close=True,fail_rollback=True),self.scope,lambda s:None)
        with self.assertRaises(core.Conflict): fault.intent(self.op.operation_id,999,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id),self.op)

    def test_commit_unknown_wins_over_close_errors(self):
        fault=Repository(lambda:CloseActions(self.factory(),fail_commit=True,fail_close=True),self.scope,lambda s:None)
        with self.assertRaises(CommitUnknown): fault.intent(self.op.operation_id,0,'auth_revocation','original')
        self.assertEqual(self.repo.query(self.op.operation_id).steps[0].invocation,'original')

    def test_query_denied_wins_over_close_errors(self):
        fault=Repository(lambda:CloseActions(self.factory(),fail_close=True),self.scope,lambda s:None)
        with self.assertRaises(core.Denied): fault.query('not-original-operation')

    def test_query_close_error_withholds_private_value(self):
        fault=Repository(lambda:CloseActions(self.factory(),fail_close=True),self.scope,lambda s:None)
        with self.assertRaises(Unavailable): fault.query(self.op.operation_id)

    def test_close_context_mutation_withholds_even_if_guard_allows(self):
        for mutation in ('scope','guard','connect','_scope_bytes'):
            with self.subTest(mutation=mutation):
                fault=Repository(self.factory,self.scope,lambda s:None)
                def mutate():
                    setattr(fault,mutation,{
                        'scope':replace(self.scope,subject='different'),
                        'guard':lambda s:None,
                        'connect':lambda:None,
                        '_scope_bytes':b'different',
                    }[mutation])
                fault.connect=lambda:CloseActions(self.factory(),mutate)
                with self.assertRaises(core.Denied): fault.query(self.op.operation_id)

    # Existing affected faults are reused verbatim; no unrelated state/domain reruns.
    test_post_commit_guard_loss_withholds_result=fixtures.PostgresTests.test_post_commit_guard_loss_withholds_result
    test_lost_create_ack_and_close_failure_preserve_original=fixtures.PostgresTests.test_lost_create_ack_and_close_failure_preserve_original
    test_rollback_guard_before_commit_atomic=fixtures.PostgresTests.test_rollback_guard_before_commit_atomic
