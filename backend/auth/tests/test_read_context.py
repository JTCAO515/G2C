import asyncio
import threading
import unittest
from dataclasses import replace

from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (TrustedPrincipal, VerificationResult, VerificationStatus as V,
    CJAccessFacts, Fact, AdmissionStatus)
from cj_auth.read_context import (ProtectedReadBoundary, ProtectedReadContext, ReadContextViolation,
    ReadAdmissionFailure, ReadViolationCode as C)


class Verifier:
    def __init__(self, p): self.principal, self.status = p, V.VALID
    def verify(self, token): return VerificationResult(self.status, self.principal if self.status is V.VALID else None)


class Access:
    def __init__(self): self.invited, self.calls, self.hook = Fact.YES, 0, None
    def evaluate(self, principal):
        self.calls += 1
        hook, self.hook = self.hook, None
        if hook: hook()
        return CJAccessFacts(principal, Fact.YES, Fact.YES, self.invited)


class ReadContextTests(unittest.TestCase):
    def setUp(self):
        self.p = TrustedPrincipal('https://synthetic.invalid', 'synthetic-A', 'synthetic-aud', 1, 1, 100)
        self.verifier, self.access = Verifier(self.p), Access()
        self.checker = AdmissionChecker(self.verifier, self.access, clock=lambda:50)
        self.boundary = ProtectedReadBoundary(self.checker, max_response_bytes=128)
    def run_read(self, callback): return self.boundary.with_read_context('SYNTHETIC-NOT-A-TOKEN', callback)
    def test_same_principal_guards_materialized_bytes_and_callback_expiry(self):
        captured=[]
        def callback(ctx):
            captured.append(ctx); self.assertEqual(ctx.principal,self.p)
            self.assertIsNone(ctx.guard()); self.assertIsNone(ctx.require_current())
            return b'original-final-response'
        self.assertEqual(self.run_read(callback),b'original-final-response')
        self.assertEqual(self.access.calls,4) # entry + 2 caller guards + outer final
        with self.assertRaises(ReadContextViolation): captured[0].guard()
        with self.assertRaises(ReadContextViolation): _=captured[0].principal
        self.assertNotIn('synthetic-A',repr(captured[0]))
    def test_denied_and_unknown_skip_callback(self):
        for status, expected in ((V.INVALID,AdmissionStatus.DENIED),(V.UNKNOWN,AdmissionStatus.UNKNOWN)):
            self.verifier.status=status; called=[]
            with self.assertRaises(ReadAdmissionFailure) as caught:
                self.run_read(lambda ctx:called.append(ctx) or b'private')
            self.assertEqual(caught.exception.status,expected);self.assertEqual(called,[])
    def test_revoked_unknown_or_identity_change_at_final_withhold_bytes(self):
        for change in ('deny','unknown','identity','time'):
            self.setUp()
            def callback(ctx):
                if change=='deny': self.access.invited=Fact.NO
                elif change=='unknown': self.verifier.status=V.UNKNOWN
                elif change=='identity': self.verifier.principal=replace(self.p,subject='synthetic-B')
                else: self.verifier.principal=replace(self.p,issued_at=2)
                return b'private'
            with self.subTest(change=change), self.assertRaises((ReadAdmissionFailure,ReadContextViolation)):
                self.run_read(callback)
    def test_lost_lifetime_never_revives_after_authority_restored_new_context_can_start(self):
        captured=[]
        def callback(ctx):
            captured.append(ctx);self.access.invited=Fact.NO
            with self.assertRaises(ReadAdmissionFailure):ctx.guard()
            self.access.invited=Fact.YES
            with self.assertRaises(ReadAdmissionFailure):ctx.guard()
            return b'never-returned'
        with self.assertRaises(ReadAdmissionFailure):self.run_read(callback)
        self.assertEqual(self.run_read(lambda ctx:b'fresh'),b'fresh')
        with self.assertRaises(ReadAdmissionFailure):captured[0].guard()
    def test_nested_context_cannot_replace_or_revive_outer_even_when_caught(self):
        def callback(ctx):
            with self.assertRaises(ReadContextViolation): self.run_read(lambda inner:b'nested')
            with self.assertRaises(ReadContextViolation):ctx.guard()
            return b'outer'
        with self.assertRaises(ReadContextViolation) as caught:self.run_read(callback)
        self.assertEqual(caught.exception.code,C.REENTRY)
        self.assertEqual(self.run_read(lambda ctx:b'new'),b'new')
    def test_admission_callback_reentry_is_rejected_before_any_read_callback(self):
        def reenter():
            with self.assertRaises(ReadContextViolation):self.run_read(lambda ctx:b'nested')
        self.access.hook=reenter; called=[]
        with self.assertRaises(ReadContextViolation):self.run_read(lambda ctx:called.append(ctx) or b'private')
        self.assertEqual(called,[])
    def test_recursive_guard_in_checker_invalidates_the_original(self):
        def callback(ctx):
            self.access.hook=ctx.guard
            with self.assertRaises(ReadContextViolation):ctx.guard()
            return b'never'
        with self.assertRaises(ReadContextViolation):self.run_read(callback)
    def test_other_thread_cannot_read_principal_or_guard(self):
        def callback(ctx):
            errors=[]
            def foreign():
                try:ctx.guard()
                except ReadContextViolation as error:errors.append(error.code)
            worker=threading.Thread(target=foreign);worker.start();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertEqual(errors,[C.WRONG_THREAD])
            return b'private'
        with self.assertRaises(ReadContextViolation):self.run_read(callback)
    def test_deferred_nonbytes_and_oversized_results_rejected(self):
        async def deferred():return b'private'
        for factory in (lambda:deferred(),lambda:iter([b'private']),lambda:bytearray(b'private'),
                        lambda:memoryview(b'private'),lambda:None,lambda:b'x'*129):
            with self.assertRaises(ReadContextViolation):self.run_read(lambda ctx:factory())
        async def async_callback(ctx):return b'private'
        with self.assertRaises(ReadContextViolation):self.run_read(async_callback)
        with self.assertRaises(ValueError):ProtectedReadBoundary(self.checker,max_response_bytes=True)
    def test_exception_and_explicit_cancellation_close_lifetime_without_masking_primary(self):
        captured=[]
        class OriginalReadFailure(Exception):pass
        def failed(ctx):captured.append(ctx);raise OriginalReadFailure()
        with self.assertRaises(OriginalReadFailure):self.run_read(failed)
        with self.assertRaises(ReadContextViolation):captured[0].guard()
        def cancelled(ctx):ctx.invalidate();return b'private'
        with self.assertRaises(ReadContextViolation) as caught:self.run_read(cancelled)
        self.assertEqual(caught.exception.code,C.CANCELLED)
        self.assertEqual(self.run_read(lambda ctx:b''),b'')
    def test_public_construction_does_not_create_an_unbounded_lifetime(self):
        with self.assertRaises(ValueError):ProtectedReadContext(self.checker,'synthetic')
    def test_overlapping_boundary_call_invalidates_original_without_starting_second_callback(self):
        nested=[]
        def callback(ctx):
            errors=[]
            def overlap():
                try:self.run_read(lambda other:nested.append(other) or b'private')
                except ReadContextViolation as error:errors.append(error.code)
            worker=threading.Thread(target=overlap);worker.start();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertEqual(errors,[C.REENTRY])
            return b'private'
        with self.assertRaises(ReadContextViolation):self.run_read(callback)
        self.assertEqual(nested,[])
        self.assertEqual(self.run_read(lambda ctx:b'fresh-after-close'),b'fresh-after-close')
    def test_missing_authoritative_access_provider_fails_closed(self):
        boundary=ProtectedReadBoundary(AdmissionChecker(self.verifier,clock=lambda:50),max_response_bytes=128)
        with self.assertRaises(ReadAdmissionFailure) as caught:boundary.with_read_context('synthetic',lambda ctx:b'private')
        self.assertEqual(caught.exception.status,AdmissionStatus.UNKNOWN)


if __name__=='__main__':unittest.main()
