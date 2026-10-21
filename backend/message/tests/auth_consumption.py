"""Loads actual fixed CJ007 module through run_auth_consumption.py, no copied types."""
import unittest
import json
from dataclasses import replace
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import (TrustedPrincipal, VerificationResult, VerificationStatus,
                                CJAccessFacts, Fact, AdmissionStatus)
from cj_message.auth_boundary import Boundary, AccessBlocked, IdentityChanged
from cj_message.domain import InvalidInput
from test_message import FakeRepository, wire


class Verifier:
    def __init__(self, principal):
        self.principal = principal
        self.status = VerificationStatus.VALID
    def verify(self, token):
        return VerificationResult(self.status, self.principal if self.status is VerificationStatus.VALID else None)


class Policy:
    def __init__(self):
        self.calls = 0
        self.invited = Fact.YES
        self.email = Fact.YES
        self.deny_at = None
    def evaluate(self, p):
        self.calls += 1
        invited = Fact.NO if self.calls == self.deny_at else self.invited
        return CJAccessFacts(p, Fact.YES, self.email, invited)


class AuthConsumption(unittest.TestCase):
    def setUp(self):
        self.p = TrustedPrincipal('https://synthetic.invalid', 'user-a', 'cj-test', 1, 1, 100)
        self.verifier = Verifier(self.p); self.policy = Policy()
        self.repo = FakeRepository(); self.resolved = []
        def resolve(p):
            self.resolved.append(p)
            return self.repo
        self.boundary = Boundary(AdmissionChecker(self.verifier, self.policy, clock=lambda:50), resolve, lambda:'run-original')

    def test_allowed_real_gate_consumed_and_rechecked(self):
        r = self.boundary.receive('synthetic-token', wire())
        self.assertEqual(r.run_id, 'run-original')
        self.assertEqual(self.resolved, [self.p])
        self.assertEqual(self.policy.calls, 4)
        self.assertEqual(self.boundary.query('synthetic-token', 'm1').receipt, r)

    def test_unknown_invalid_not_invited_unverified_never_resolve(self):
        for status in (VerificationStatus.UNKNOWN, VerificationStatus.INVALID):
            self.verifier.status = status
            with self.assertRaises(AccessBlocked) as result:
                self.boundary.receive('synthetic-token', wire())
            self.assertEqual(result.exception.status, AdmissionStatus.UNKNOWN if status is VerificationStatus.UNKNOWN else AdmissionStatus.DENIED)
        self.verifier.status = VerificationStatus.VALID
        for fact in (Fact.UNKNOWN, Fact.NO):
            self.policy.invited = fact
            with self.assertRaises(AccessBlocked): self.boundary.receive('synthetic-token', wire())
        self.policy.invited = Fact.YES; self.policy.email = Fact.NO
        with self.assertRaises(AccessBlocked): self.boundary.receive('synthetic-token', wire())
        self.assertEqual(self.resolved, []); self.assertEqual(self.repo.rows, {})

    def test_commit_boundary_revocation_rolls_back(self):
        self.policy.deny_at = 3
        with self.assertRaises(AccessBlocked) as result: self.boundary.receive('synthetic-token', wire())
        self.assertEqual(result.exception.stage, 'commit')
        self.assertFalse(result.exception.commit_possible)
        self.assertEqual(self.repo.rows, {}); self.assertEqual(self.repo.jobs, {})

    def test_after_commit_denial_preserves_original_recovery(self):
        self.policy.deny_at = 4
        with self.assertRaises(AccessBlocked) as result: self.boundary.receive('synthetic-token', wire())
        self.assertTrue(result.exception.commit_possible)
        self.policy.deny_at = None
        recovered = self.boundary.query('synthetic-token', 'm1')
        self.assertEqual(recovered.receipt.run_id, 'run-original')
        self.assertEqual(len(self.repo.jobs), 1)

    def test_identity_changed_during_repository_resolution_rejected(self):
        self.boundary.resolve_repository = lambda p: self.change_identity()
        with self.assertRaises(IdentityChanged): self.boundary.receive('synthetic-token', wire())
        self.assertEqual(self.repo.rows, {})

    def change_identity(self):
        self.verifier.principal = replace(self.p, subject='user-b')
        return self.repo

    def test_client_owner_rejected_and_revocation_blocks_pending(self):
        forged = json.loads(wire()); forged['owner'] = 'client-owner'
        with self.assertRaises(InvalidInput):
            self.boundary.receive('synthetic-token', json.dumps(forged).encode())
        self.assertEqual(self.repo.rows, {})
        self.boundary.receive('synthetic-token', wire())
        self.policy.invited = Fact.NO
        with self.assertRaises(AccessBlocked): self.boundary.pending('synthetic-token')
        self.assertEqual(len(self.repo.jobs), 1)


if __name__ == '__main__': unittest.main(verbosity=2)
