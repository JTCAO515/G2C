"""Targeted protected host-envelope seam using real fixed domain boundaries."""
import asyncio
from dataclasses import replace
import inspect
import json
import unittest
import display_snapshot_checks as fixture
from cj_message.auth_boundary import AccessBlocked, IdentityChanged
from cj_run.display_snapshot import SnapshotUnavailable, SnapshotChanged, SnapshotTooLarge, DisplaySnapshotConfiguration


class ProjectedTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SnapshotTests()
        self.f.setUp()
        self.f.seed_text()
    def read(self,project):
        return self.f.reader.read_projected('synthetic','mé',project)
    @staticmethod
    def envelope(raw):
        return b'{"request_id":"synthetic-trace","snapshot":'+raw+b'}'

    def test_normal_projection_receives_only_bytes_and_old_read_compatible(self):
        legacy=self.f.read()
        seen=[]
        def project(raw):
            self.assertIs(type(raw),bytes)
            seen.append(raw)
            self.assertNotIn(b'PRIVATE_',raw)
            self.assertNotIn(b'trusted-a',raw)
            return self.envelope(raw)
        result=self.read(project)
        self.assertEqual(seen,[legacy])
        self.assertEqual(json.loads(result),{'request_id':'synthetic-trace','snapshot':json.loads(legacy)})
        self.assertEqual(self.f.read(),legacy)

    def test_final_envelope_byte_bound(self):
        raw=self.f.read()
        self.f.reader.configuration=DisplaySnapshotConfiguration(10000,len(self.envelope(raw)))
        self.assertEqual(self.read(self.envelope),self.envelope(raw))
        self.f.reader.configuration=DisplaySnapshotConfiguration(10000,len(self.envelope(raw))-1)
        with self.assertRaises(SnapshotTooLarge): self.read(self.envelope)
        self.assertEqual(self.f.read(),raw)  # legacy body still fits

    def test_callback_cannot_expand_captured_response_limit(self):
        size=len(self.f.read())
        self.f.reader.configuration=DisplaySnapshotConfiguration(10000,size)
        def project(raw):
            self.f.reader.configuration=DisplaySnapshotConfiguration(10000,999999)
            return self.envelope(raw)
        with self.assertRaises(SnapshotTooLarge): self.read(project)

    def test_invalid_deferred_returns_rejected_without_execution(self):
        called=[]
        async def delayed():
            called.append('awaited')
            return b'not-used'
        def generator():
            called.append('iterated')
            yield b'not-used'
        class Awaitable:
            def __await__(self):
                called.append('awaited')
                yield
        coroutine=delayed()
        for value in (None,'text',{},bytearray(b'body'),memoryview(b'body'),generator(),Awaitable(),coroutine):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(SnapshotUnavailable): self.read(lambda raw:value)
        self.assertEqual(called,[])
        self.assertEqual(inspect.getcoroutinestate(coroutine),inspect.CORO_CLOSED)
        with self.assertRaises(ValueError): self.read(None)

    def test_projection_exception_and_cancellation_propagate(self):
        for error in (ValueError('synthetic schema error'),OSError('synthetic encode error'),asyncio.CancelledError()):
            def project(raw): raise error
            with self.assertRaises(type(error)): self.read(project)
        # No context is retained after failure; next independent protected read works.
        self.assertIs(type(self.f.read()),bytes)

    def test_project_changes_identity_source_epoch_or_run(self):
        changes=('identity','source','epoch','run')
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                def project(raw):
                    if change=='identity': self.f.p=replace(self.f.p,subject='other')
                    elif change=='source': self.f.stored=replace(self.f.original,receipt=replace(self.f.original.receipt,sequence=2))
                    elif change=='epoch': self.f.repo.epoch='epoch2'
                    else: self.f.event('cancelled')
                    return self.envelope(raw)
                with self.assertRaises((IdentityChanged,SnapshotChanged)): self.read(project)

    def test_reentry_rejected_and_expired_context_not_reusable(self):
        captured=[]
        original=self.f.boundary.with_history_context
        def instrument(token,operation):
            def capture(ctx):
                captured.append(ctx)
                return operation(ctx)
            return original(token,capture)
        self.f.boundary.with_history_context=instrument
        def nested(raw):
            return self.f.reader.read('synthetic','mé')
        with self.assertRaises(RuntimeError): self.read(nested)
        with self.assertRaises(RuntimeError): captured[0].query_message('mé')
        self.assertIs(type(self.read(self.envelope)),bytes)
        with self.assertRaises(RuntimeError): captured[-1].query_message('mé')

    def test_final_owner_guard_still_withholds_projected_envelope(self):
        original=self.f.boundary.with_history_context
        def wrapper(token,operation):
            def revoke(ctx):
                result=operation(ctx)
                self.f.invited=fixture.Fact.UNKNOWN
                return result
            return original(token,revoke)
        self.f.boundary.with_history_context=wrapper
        with self.assertRaises(AccessBlocked): self.read(self.envelope)


if __name__=='__main__': unittest.main(verbosity=2)
