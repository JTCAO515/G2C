"""Targeted DB-API cleanup failure injection; no database."""
import unittest
from unittest.mock import patch
from cj_message.domain import CommitUnknown
from cj_message.postgres import Repository


SECRET = 'private-credential-and-SQL-body'


class FaultConnection:
    autocommit = False
    def __init__(self, commit=False, rollback=False, cursor_close=False, connection_close=False):
        self.faults = dict(commit=commit, rollback=rollback, cursor_close=cursor_close,
                           connection_close=connection_close)
        self.events = []
    def event(self, name):
        self.events.append(name)
        if self.faults.get(name): raise OSError(SECRET)
    def cursor(self):
        conn = self
        class Cursor:
            def execute(self, *args): conn.event('execute')
            def close(self): conn.event('cursor_close')
        return Cursor()
    def commit(self): self.event('commit')
    def rollback(self): self.event('rollback')
    def close(self): self.event('connection_close')


class CleanupPriorityTests(unittest.TestCase):
    def test_commit_unknown_survives_both_close_failures(self):
        conn = FaultConnection(commit=True, cursor_close=True, connection_close=True)
        with self.assertRaises(CommitUnknown):
            with Repository(lambda: conn, 'test-scope').transaction(): pass
        self.assertEqual(conn.events, ['execute', 'commit', 'cursor_close', 'connection_close'])

    def test_original_body_error_survives_rollback_and_close_failures(self):
        conn = FaultConnection(rollback=True, cursor_close=True, connection_close=True)
        original = ValueError('original-body-error')
        with self.assertRaises(ValueError) as caught:
            with Repository(lambda: conn, 'test-scope').transaction(): raise original
        self.assertIs(caught.exception, original)
        self.assertEqual(conn.events, ['execute', 'rollback', 'cursor_close', 'connection_close'])

    def test_success_is_not_changed_to_failure_by_close(self):
        conn = FaultConnection(cursor_close=True, connection_close=True)
        with Repository(lambda: conn, 'test-scope').transaction(): result = 'accepted'
        self.assertEqual(result, 'accepted')
        self.assertEqual(conn.events, ['execute', 'commit', 'cursor_close', 'connection_close'])

    def test_cleanup_diagnostics_are_fixed_and_redacted(self):
        conn = FaultConnection(rollback=True, cursor_close=True, connection_close=True)
        with self.assertLogs('cj_message.postgres', level='WARNING') as logs:
            with self.assertRaises(ValueError):
                with Repository(lambda: conn, 'private-scope').transaction(): raise ValueError('body')
        self.assertEqual(len(logs.output), 3)
        self.assertNotIn(SECRET, str(logs.output))
        self.assertNotIn('private-scope', str(logs.output))
        self.assertIn('stage=rollback outcome=body_failed', logs.output[0])
        self.assertIn('stage=cursor_close', logs.output[1])
        self.assertIn('stage=connection_close', logs.output[2])

    def test_diagnostic_handler_failure_cannot_mask_commit_unknown(self):
        conn = FaultConnection(commit=True, cursor_close=True, connection_close=True)
        with patch('cj_message.postgres.logging.getLogger', side_effect=RuntimeError('sink failed')):
            with self.assertRaises(CommitUnknown):
                with Repository(lambda: conn, 'test-scope').transaction(): pass
        self.assertEqual(conn.events, ['execute', 'commit', 'cursor_close', 'connection_close'])

    def test_successful_rollback_preserves_body_error_and_closes(self):
        conn = FaultConnection()
        with self.assertRaisesRegex(ValueError, '^body$'):
            with Repository(lambda: conn, 'test-scope').transaction(): raise ValueError('body')
        self.assertEqual(conn.events, ['execute', 'rollback', 'cursor_close', 'connection_close'])


if __name__ == '__main__': unittest.main(verbosity=2)
