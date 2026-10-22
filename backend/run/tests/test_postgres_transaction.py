"""Injected DB-API lifecycle failures, not database integration evidence."""
from datetime import datetime, timezone
import unittest
from cj_run.postgres import Repository, CommitUnknown
from cj_run.core import Denied


class Connection:
    autocommit = False
    def __init__(self, *, lost=False, cleanup=False, active=True):
        self.lost, self.cleanup, self.active = lost, cleanup, active
        self.actions = []
    def cursor(self): return self
    def execute(self, *args): self.actions.append('execute')
    def fetchone(self): return ('epoch', self.active)
    def commit(self):
        self.actions.append('commit')
        if self.lost: raise OSError('fixture')
    def rollback(self):
        self.actions.append('rollback')
        if self.cleanup: raise OSError('fixture')
    def close(self):
        self.actions.append('close')
        if self.cleanup: raise OSError('fixture')


def repo(c):
    return Repository(lambda:c,'fixture',expires_at=datetime(2099,1,1,tzinfo=timezone.utc),
                      statement_timeout_ms=10,lock_timeout_ms=10)


class LifecycleTests(unittest.TestCase):
    def test_commit_unknown_does_not_rollback_or_retry(self):
        c=Connection(lost=True,cleanup=True)
        with self.assertLogs('cj_run.postgres'):
            with self.assertRaises(CommitUnknown):
                with repo(c).transaction(): pass
        self.assertEqual(c.actions.count('commit'),1)
        self.assertNotIn('rollback',c.actions)
        self.assertEqual(c.actions.count('close'),2)

    def test_body_error_preserved_when_cleanup_fails(self):
        c=Connection(cleanup=True)
        with self.assertLogs('cj_run.postgres'):
            with self.assertRaisesRegex(RuntimeError,'original'):
                with repo(c).transaction(): raise RuntimeError('original')
        self.assertEqual(c.actions.count('rollback'),1)
        self.assertNotIn('commit',c.actions)

    def test_success_close_error_not_commit_unknown(self):
        c=Connection(cleanup=True)
        with self.assertLogs('cj_run.postgres'):
            with repo(c).transaction(): pass
        self.assertEqual(c.actions.count('commit'),1)

    def test_autocommit_forbidden(self):
        c=Connection()
        c.autocommit=True
        with self.assertRaises(ValueError):
            with repo(c).transaction(): pass
        self.assertNotIn('commit',c.actions)
        self.assertEqual(c.actions,['close'])

    def test_inactive_scope_rollback(self):
        c=Connection(active=False)
        with self.assertRaises(Denied):
            with repo(c).transaction(): pass
        self.assertIn('rollback',c.actions)
        self.assertNotIn('commit',c.actions)

    def test_configuration_explicit(self):
        for args in ({'statement_timeout_ms':0,'lock_timeout_ms':1},
                     {'statement_timeout_ms':1,'lock_timeout_ms':True}):
            with self.assertRaises(ValueError):
                Repository(lambda:Connection(),'scope',expires_at=datetime.now(timezone.utc),**args)
