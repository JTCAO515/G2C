"""Synthetic keys and transaction double only; no provider or database connection."""
from contextlib import contextmanager
import time
import unittest

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cj_auth.interfaces import CJAccessFacts, Fact
from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.auth_boundary import AccessBlocked
from cj_api.composition import CompositionUnavailable, build_message_boundary


class LedgerDouble:
    scope = 'explicit-test-partition'
    def __init__(self):
        self.reads = 0
    @contextmanager
    def transaction(self):
        yield self
    def lock_scope(self):
        pass
    def find(self, mid):
        self.reads += 1
        return None


class PolicyDouble:
    def __init__(self):
        self.invited = Fact.YES
        self.calls = 0
    def evaluate(self, principal):
        self.calls += 1
        return CJAccessFacts(principal, Fact.YES, Fact.YES, self.invited)


class SyntheticFixture(unittest.TestCase):
    def setUp(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = self.key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo)
        self.keys = StaticPublicKeys({'test-key': VerificationKey('RS256', public)})
        self.config = JWTConfiguration('https://synthetic.invalid', 'cj-synthetic', 'RS256', 0)
        self.policy, self.repo, self.resolved = PolicyDouble(), LedgerDouble(), []
        def resolve(principal):
            self.resolved.append(principal)
            return self.repo
        self.kwargs = dict(environment='local', jwt_configuration=self.config,
                           verification_keys=self.keys, access_provider=self.policy,
                           resolve_repository=resolve, new_run_id=lambda:'synthetic-only-run')
        now = int(time.time())
        self.token = jwt.encode(dict(iss=self.config.issuer, aud=self.config.audience, sub='synthetic-user',
                                     iat=now-1, nbf=now-1, exp=now+120, invited=True),
                                self.key, algorithm='RS256', headers={'kid':'test-key'})


class CompositionTests(SyntheticFixture):
    def test_real_verifier_gate_and_boundary_query(self):
        boundary = build_message_boundary(**self.kwargs)
        self.assertIsNone(boundary.query(self.token, 'original-id'))
        self.assertEqual(self.repo.reads, 1)
        self.assertEqual(self.policy.calls, 4)
        self.assertEqual(self.resolved[0].subject, 'synthetic-user')

    def test_token_metadata_does_not_grant_invitation(self):
        self.policy.invited = Fact.NO
        with self.assertRaises(AccessBlocked):
            build_message_boundary(**self.kwargs).query(self.token, 'original-id')
        self.assertEqual(self.resolved, [])
        self.assertEqual(self.repo.reads, 0)

    def test_unknown_policy_never_resolves_repository(self):
        self.policy.invited = Fact.UNKNOWN
        with self.assertRaises(AccessBlocked):
            build_message_boundary(**self.kwargs).query(self.token, 'original-id')
        self.assertEqual(self.resolved, [])

    def test_missing_dependencies_or_environment_refuse_composition(self):
        for name in ('jwt_configuration','verification_keys','access_provider','resolve_repository','new_run_id'):
            with self.subTest(missing=name), self.assertRaises(CompositionUnavailable):
                build_message_boundary(**dict(self.kwargs, **{name:None}))
        with self.assertRaises(CompositionUnavailable):
            build_message_boundary(**dict(self.kwargs, environment='production'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
