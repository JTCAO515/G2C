"""Targeted P2 fault matrix; all SQLite files are new task-private temp files."""
import asyncio
from contextlib import contextmanager
import unittest

import test_jobs as fixtures
from cj_memory_jobs.codec import CommitUnknown, Unavailable
from cj_memory_jobs.queue import InternalQueue, LocalStore


class FaultConnection:
    def __init__(self, native, *, commit=None, rollback=None, close=None):
        self.native = native
        self.commit_fault = commit
        self.rollback_fault = rollback
        self.close_fault = close
        self.events = []

    def __getattr__(self, name):
        return getattr(self.native, name)

    def commit(self):
        self.events.append('commit')
        if self.commit_fault:
            stage, error = self.commit_fault
            if stage == 'after':
                self.native.commit()
            raise error
        self.native.commit()

    def rollback(self):
        self.events.append('rollback')
        if self.rollback_fault:
            stage, error = self.rollback_fault
            if stage == 'after':
                self.native.rollback()
            raise error
        self.native.rollback()

    def close(self):
        self.events.append('close')
        # Simulate cleanup failure AFTER actual local close, as in original probe.
        self.native.close()
        if self.close_fault:
            raise self.close_fault


class TransactionFaults(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.Jobs()
        self.fixture.setUp()
        self.fixture.enqueue()
        self.fixture.begin()
        self.native = self.fixture.store.db

    def tearDown(self):
        # Explicit fixture cleanup; no product retry, dispatch or new attempt.
        self.native.close()
        self.fixture.store.close()
        self.fixture.tmp.cleanup()

    def wrap(self, **faults):
        wrapped = FaultConnection(self.native, **faults)
        self.fixture.store.db = wrapped
        return wrapped

    def readback(self):
        self.native.close()
        self.fixture.store = LocalStore(self.fixture.path)
        self.fixture.queue = InternalQueue(self.fixture.store, self.fixture.host)
        self.fixture.host.deny_on_final = False
        return self.fixture.query().state

    def body_failure(self, error):
        original = self.fixture.host.current

        def current():
            result = original()
            if self.fixture.host.calls > 1:
                raise error
            return result

        self.fixture.host.current = current
        return original

    def test_original_review_commit_then_close_double_fault(self):
        commit_error = OSError('synthetic lost commit ACK')
        wrapped = self.wrap(commit=('after', commit_error),
                            close=RuntimeError('synthetic cleanup failure'))
        with self.assertRaises(CommitUnknown) as caught:
            self.fixture.complete()
        self.assertIs(caught.exception.__cause__, commit_error)
        self.assertEqual(wrapped.events, ['commit', 'close'])
        # Matches Review's real SQLite result, with corrected exception priority.
        self.assertEqual(self.readback(), 'completed')
        self.assertEqual(self.fixture.complete().state, 'completed')

    def test_commit_cancel_and_close_cancel_preserve_uncertainty(self):
        commit_error = asyncio.CancelledError('synthetic cancel after actual commit')
        wrapped = self.wrap(commit=('after', commit_error),
                            close=asyncio.CancelledError('synthetic cleanup cancellation'))
        with self.assertRaises(CommitUnknown) as caught:
            self.fixture.complete()
        self.assertIs(caught.exception.__cause__, commit_error)
        self.assertEqual(wrapped.events, ['commit', 'close'])
        self.assertEqual(self.readback(), 'completed')

    def test_before_commit_failure_still_reports_unknown_not_rollback(self):
        wrapped = self.wrap(commit=('before', OSError('synthetic commit failure')),
                            close=RuntimeError('synthetic close failure'))
        with self.assertRaises(CommitUnknown): self.fixture.complete()
        self.assertEqual(wrapped.events, ['commit', 'close'])
        # Test can observe noncommit, product did not claim it from the exception.
        self.assertEqual(self.readback(), 'inflight')

    def test_body_failure_successful_rollback_preserves_body(self):
        body_error = Unavailable('synthetic source revoked before commit')
        original = self.body_failure(body_error)
        wrapped = self.wrap()
        with self.assertRaises(Unavailable) as caught: self.fixture.complete()
        self.assertIs(caught.exception, body_error)
        self.assertEqual(wrapped.events, ['rollback'])
        self.fixture.host.current = original
        self.assertEqual(self.readback(), 'inflight')

    def test_body_cancel_successful_rollback_preserves_cancel(self):
        body_error = asyncio.CancelledError('synthetic body cancellation')
        original = self.body_failure(body_error)
        wrapped = self.wrap()
        with self.assertRaises(asyncio.CancelledError) as caught: self.fixture.complete()
        self.assertIs(caught.exception, body_error)
        self.assertEqual(wrapped.events, ['rollback'])
        self.fixture.host.current = original
        self.assertEqual(self.readback(), 'inflight')

    def test_body_rollback_close_faults_select_unknown_with_body_cause(self):
        body_error = Unavailable('synthetic body failure')
        original = self.body_failure(body_error)
        wrapped = self.wrap(rollback=('before', OSError('synthetic rollback failure')),
                            close=RuntimeError('synthetic close failure'))
        with self.assertRaises(CommitUnknown) as caught: self.fixture.complete()
        self.assertIs(caught.exception.__cause__, body_error)
        self.assertEqual(wrapped.events, ['rollback', 'close'])
        self.fixture.host.current = original
        self.assertEqual(self.readback(), 'inflight')

    def test_body_cancel_rollback_cancel_close_cancel_select_unknown(self):
        body_error = asyncio.CancelledError('synthetic body cancellation')
        original = self.body_failure(body_error)
        wrapped = self.wrap(rollback=('after', asyncio.CancelledError('rollback cancel')),
                            close=asyncio.CancelledError('close cancel'))
        with self.assertRaises(CommitUnknown) as caught: self.fixture.complete()
        self.assertIs(caught.exception.__cause__, body_error)
        self.assertEqual(wrapped.events, ['rollback', 'close'])
        self.fixture.host.current = original
        self.assertEqual(self.readback(), 'inflight')

    def test_guard_close_does_not_mask_commit_unknown(self):
        original_guard = self.fixture.host.guard

        @contextmanager
        def guard(source):
            try:
                with original_guard(source) as lease:
                    yield lease
            finally:
                raise RuntimeError('synthetic guard close failure')

        self.fixture.host.guard = guard
        self.wrap(commit=('after', OSError('synthetic lost ACK')),
                  close=RuntimeError('synthetic local close failure'))
        with self.assertRaises(CommitUnknown): self.fixture.complete()
        self.fixture.host.guard = original_guard
        self.assertEqual(self.readback(), 'completed')

    def test_guard_close_preserves_rolled_back_body_cancel(self):
        original_guard = self.fixture.host.guard
        body_error = asyncio.CancelledError('synthetic body cancel')
        original_current = self.body_failure(body_error)

        @contextmanager
        def guard(source):
            try:
                with original_guard(source) as lease:
                    yield lease
            finally:
                raise RuntimeError('synthetic guard cleanup failure')

        self.fixture.host.guard = guard
        wrapped = self.wrap()
        with self.assertRaises(asyncio.CancelledError) as caught: self.fixture.complete()
        self.assertIs(caught.exception, body_error)
        self.assertEqual(wrapped.events, ['rollback'])
        self.fixture.host.guard = original_guard
        self.fixture.host.current = original_current
        self.assertEqual(self.readback(), 'inflight')


if __name__ == '__main__':
    unittest.main(verbosity=2)
