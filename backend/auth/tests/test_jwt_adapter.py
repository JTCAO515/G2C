import base64
import json
import time
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cj_auth.jwt_adapter import JWTConfiguration, VerificationKey, StaticPublicKeys, PyJWTVerifier
from cj_auth.interfaces import *
from cj_auth.admission import AdmissionChecker


def b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


class JWTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Test signing keys generated in memory, never saved or printed.
        cls.rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.ec = ec.generate_private_key(ec.SECP256R1())

    def setUp(self):
        self.now = int(time.time())
        self.claims = dict(iss='https://new-cj.synthetic.invalid', aud='cj-synthetic', sub='synthetic-A',
                           iat=self.now-10, nbf=self.now-10, exp=self.now+120)
        self.config = JWTConfiguration(self.claims['iss'], self.claims['aud'], 'RS256', 0)
        self.keys = StaticPublicKeys({'synthetic-rsa': self.material(self.rsa, 'RS256')})
        self.verifier = PyJWTVerifier(self.config, self.keys)

    def material(self, key, alg):
        return VerificationKey(alg, key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def token(self, changes=None, *, key=None, algorithm='RS256', headers=None):
        return jwt.encode(self.claims | (changes or {}), key or self.rsa, algorithm=algorithm,
                          headers=headers or {'kid': 'synthetic-rsa'})

    def assertInvalid(self, token):
        result = self.verifier.verify(token)
        self.assertEqual(result.status, VerificationStatus.INVALID)
        self.assertIsNone(result.principal)

    def test_valid_rsa_has_only_verified_identity_fields(self):
        result = self.verifier.verify(self.token({'email': 'forged@example.invalid', 'owner': 'B',
                                                'invited': True, 'user_metadata': {'member': True}}))
        self.assertEqual(result.status, VerificationStatus.VALID)
        self.assertEqual(result.principal.subject, 'synthetic-A')
        self.assertFalse(hasattr(result.principal, 'email'))
        self.assertFalse(hasattr(result.principal, 'invited'))

    def test_valid_es256_and_algorithm_configuration_is_not_token_controlled(self):
        config = JWTConfiguration(self.config.issuer, self.config.audience, 'ES256', 0)
        verifier = PyJWTVerifier(config, StaticPublicKeys({'synthetic-ec': self.material(self.ec, 'ES256')}))
        token = self.token(key=self.ec, algorithm='ES256', headers={'kid': 'synthetic-ec'})
        self.assertEqual(verifier.verify(token).status, VerificationStatus.VALID)
        self.assertInvalid(token)

    def test_wrong_signature_and_modified_payload(self):
        self.assertInvalid(self.token(key=self.other))
        parts = self.token().split('.')
        parts[1] = b64(json.dumps(self.claims | {'sub': 'synthetic-B'}).encode())
        self.assertInvalid('.'.join(parts))

    def test_exact_issuer_audience_and_subject(self):
        for changes in ({'iss': self.config.issuer+'/'}, {'iss': 'https://old-vp.synthetic.invalid'},
                        {'aud': 'other'}, {'aud': ['cj-synthetic']}, {'sub': ''}, {'sub': 1}):
            with self.subTest(changes=changes): self.assertInvalid(self.token(changes))

    def test_required_claims(self):
        for missing in ('iss', 'aud', 'sub', 'iat', 'nbf', 'exp'):
            claims = dict(self.claims); del claims[missing]
            token = jwt.encode(claims, self.rsa, algorithm='RS256', headers={'kid': 'synthetic-rsa'})
            with self.subTest(missing=missing): self.assertInvalid(token)

    def test_expired_future_times_and_exact_types(self):
        for changes in ({'exp': self.now-1, 'iat': self.now-100, 'nbf': self.now-100},
                        {'iat': self.now+60}, {'nbf': self.now+60}, {'exp': self.now-10}):
            self.assertInvalid(self.token(changes))
        for claim in ('iat', 'nbf', 'exp'):
            for value in (True, str(self.now), float(self.now), None, [], {}):
                with self.subTest(claim=claim, value=value): self.assertInvalid(self.token({claim: value}))

    def test_none_hmac_and_remote_key_headers_rejected_without_network(self):
        none = jwt.encode(self.claims, key='', algorithm='none', headers={'kid': 'synthetic-rsa'})
        hmac = self.token(key=b'synthetic-hmac-key-of-sufficient-length-only', algorithm='HS256')
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertInvalid(none); self.assertInvalid(hmac)
            for field in ('jku', 'x5u', 'jwk', 'x5c', 'crit'):
                self.assertInvalid(self.token(headers={'kid': 'synthetic-rsa', field: 'https://never.invalid'}))

    def test_missing_key_provider_unavailable_and_unknown_kid_stay_unknown(self):
        class Unavailable:
            def resolve(self, key_id): raise OSError('synthetic provider outage')
        for verifier, token in ((PyJWTVerifier(), self.token()), (PyJWTVerifier(self.config), self.token()),
                                (PyJWTVerifier(self.config, Unavailable()), self.token()),
                                (self.verifier, self.token(headers={'kid': 'unknown'}))):
            with self.subTest(verifier=type(verifier).__name__):
                result = verifier.verify(token)
                self.assertEqual(result.status, VerificationStatus.UNKNOWN)
                self.assertIsNone(result.principal)

    def test_malformed_size_and_duplicate_members(self):
        for token in ('', 'a.b.c', 'x'*16385, self.token().replace('.', '..', 1), None):
            self.assertInvalid(token)
        for duplicate_header in (True, False):
            header = b'{"alg":"RS256","typ":"JWT","kid":"synthetic-rsa"}'
            payload = json.dumps(self.claims).encode()
            if duplicate_header: header = header[:-1]+b',"alg":"RS256"}'
            else: payload = payload[:-1]+b',"sub":"synthetic-A"}'
            signing = (b64(header)+'.'+b64(payload)).encode()
            signature = self.rsa.sign(signing, padding.PKCS1v15(), hashes.SHA256())
            self.assertInvalid(signing.decode()+'.'+b64(signature))

    def test_bad_configuration_and_key_material_are_not_accepted(self):
        for values in (('', 'aud', 'RS256', 0), ('iss', '', 'RS256', 0),
                       ('iss', 'aud', 'HS256', 0), ('iss', 'aud', 'RS256', -1)):
            with self.assertRaises(ValueError): JWTConfiguration(*values)
        small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        for material in (self.material(small, 'RS256'), self.material(self.ec, 'RS256'),
                         VerificationKey('RS256', b'not a public key')):
            with self.assertRaises(ValueError): StaticPublicKeys({'synthetic-rsa': material})

    def test_same_project_old_user_and_forged_email_invitation_not_cj_access(self):
        token = self.token({'email_verified': True, 'invited': True, 'member': True, 'owner': 'synthetic-A'})
        class NotCJ:
            def evaluate(self, p): return CJAccessFacts(p, Fact.NO, Fact.YES, Fact.YES)
        self.assertEqual(self.verifier.verify(token).status, VerificationStatus.VALID)
        self.assertEqual(AdmissionChecker(self.verifier).check(token).status, AdmissionStatus.UNKNOWN)
        result = AdmissionChecker(self.verifier, NotCJ()).check(token)
        self.assertEqual(result.reason, AdmissionReason.NOT_CJ_MEMBER)
        self.assertIsNone(result.principal)

    def test_real_crypto_composes_with_separate_authoritative_facts(self):
        class Confirmed:
            def evaluate(self, p): return CJAccessFacts(p, Fact.YES, Fact.YES, Fact.YES)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            result = AdmissionChecker(self.verifier, Confirmed()).check(self.token())
        self.assertEqual(result.status, AdmissionStatus.ALLOWED)
        self.assertEqual(result.principal.subject, 'synthetic-A')


if __name__ == '__main__': unittest.main()
