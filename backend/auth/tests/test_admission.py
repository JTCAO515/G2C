import unittest
from dataclasses import replace
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import *


class FixedVerifier:
    def __init__(self, result): self.result = result
    def verify(self, token): return self.result


class Access:
    def __init__(self, member=Fact.YES, email=Fact.YES, invited=Fact.YES):
        self.member, self.email, self.invited, self.calls = member, email, invited, 0
    def evaluate(self, p):
        self.calls += 1
        return CJAccessFacts(p, self.member, self.email, self.invited)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.p = TrustedPrincipal('https://synthetic.invalid', 'synthetic-user', 'synthetic-aud', 10, 10, 100)
        self.verifier = FixedVerifier(VerificationResult(VerificationStatus.VALID, self.p))
    def check(self, access):
        return AdmissionChecker(self.verifier, access, clock=lambda: 50).check('synthetic-not-a-token')

    def test_missing_provider_and_every_unknown_deny_permission(self):
        self.assertEqual(self.check(None).status, AdmissionStatus.UNKNOWN)
        for name in ('member', 'email', 'invited'):
            with self.subTest(name=name):
                result = self.check(Access(**{name: Fact.UNKNOWN}))
                self.assertEqual(result.status, AdmissionStatus.UNKNOWN)
                self.assertIsNone(result.principal)

    def test_each_negative_fact_blocks_even_with_valid_identity(self):
        for name in ('member', 'email', 'invited'):
            with self.subTest(name=name):
                self.assertEqual(self.check(Access(**{name: Fact.NO})).status, AdmissionStatus.DENIED)
        self.assertEqual(self.check(Access(member=Fact.NO)).reason, AdmissionReason.NOT_CJ_MEMBER)

    def test_rechecks_provider_at_each_boundary(self):
        access = Access()
        self.assertEqual(self.check(access).principal, self.p)
        access.invited = Fact.NO
        self.assertEqual(self.check(access).reason, AdmissionReason.NOT_INVITED)
        self.assertEqual(access.calls, 2)

    def test_mismatched_binding_exception_or_bool_cannot_authorize(self):
        class Wrong:
            def evaluate(inner, p): return CJAccessFacts(replace(p, subject='other'), Fact.YES, Fact.YES, Fact.YES)
        class Broken:
            def evaluate(inner, p): raise RuntimeError('must not escape')
        for access in (Wrong(), Broken(), Access(member=True)):
            self.assertEqual(self.check(access).status, AdmissionStatus.UNKNOWN)

    def test_expires_during_lookup(self):
        result = AdmissionChecker(self.verifier, Access(), clock=lambda: 100).check('synthetic')
        self.assertEqual(result.status, AdmissionStatus.DENIED)
        self.assertIsNone(result.principal)

    def test_invalid_unknown_skip_policy_and_are_distinct(self):
        access = Access()
        for verification, admission in ((VerificationStatus.INVALID, AdmissionStatus.DENIED),
                                        (VerificationStatus.UNKNOWN, AdmissionStatus.UNKNOWN)):
            v = FixedVerifier(VerificationResult(verification))
            result = AdmissionChecker(v, access).check('synthetic')
            self.assertEqual(result.status, admission)
        self.assertEqual(access.calls, 0)
        with self.assertRaises(ValueError): VerificationResult(VerificationStatus.INVALID, self.p)
        with self.assertRaises(ValueError): VerificationResult(VerificationStatus.VALID)


if __name__ == '__main__': unittest.main()
