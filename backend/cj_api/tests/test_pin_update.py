"""Targeted fixed AUTH upgrade; synthetic tokens only, no live issuer/profile activation."""
from dataclasses import replace
import unittest
import jwt
from cj_auth.interfaces import VerificationStatus, Fact, AdmissionStatus
from cj_auth.jwt_adapter import JWTProfile, PyJWTVerifier
from cj_message.auth_boundary import AccessBlocked
from cj_api.composition import CompositionUnavailable, build_message_boundary
from test_composition import SyntheticFixture


class PinUpdateTests(SyntheticFixture):
    def signed(self, claims):
        return jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'test-key'})

    def test_new_adapter_default_strict_keeps_nbf_and_scalar_audience(self):
        self.assertIs(self.config.profile,JWTProfile.STRICT_V1)
        verifier = PyJWTVerifier(self.config,self.keys)
        claims = jwt.decode(self.token,options={'verify_signature':False})  # test-generated only
        valid = verifier.verify(self.token)
        self.assertIs(valid.status,VerificationStatus.VALID)
        self.assertEqual((valid.principal.audience,valid.principal.not_before),
                         (claims['aud'],claims['nbf']))
        missing_nbf = dict(claims);del missing_nbf['nbf']
        list_audience = dict(claims,aud=[claims['aud']])
        for malformed in (missing_nbf,list_audience):
            result = verifier.verify(self.signed(malformed))
            self.assertIs(result.status,VerificationStatus.INVALID)
            self.assertIsNone(result.principal)

    def test_factory_consumes_new_pin_with_explicit_strict_and_current_gate(self):
        config = replace(self.config,profile=JWTProfile.STRICT_V1)
        boundary = build_message_boundary(**dict(self.kwargs,jwt_configuration=config))
        self.assertIsNone(boundary.query(self.token,'original-id'))
        self.assertEqual(self.repo.reads,1)
        self.assertEqual(self.policy.calls,4)
        self.assertEqual(self.resolved[0].subject,'synthetic-user')
        self.policy.invited = Fact.NO
        with self.assertRaises(AccessBlocked) as caught:
            boundary.query(self.token,'original-id')
        self.assertIs(caught.exception.status,AdmissionStatus.DENIED)
        self.assertEqual(self.repo.reads,1)

    def test_new_optional_profile_and_missing_config_are_not_automatic_enablement(self):
        other = replace(self.config,profile=JWTProfile.SUPABASE_ACCESS_RC1)
        with self.assertRaises(CompositionUnavailable):
            build_message_boundary(**dict(self.kwargs,jwt_configuration=other))
        with self.assertRaises(CompositionUnavailable):
            build_message_boundary(**dict(self.kwargs,jwt_configuration=None))
        with self.assertRaises(CompositionUnavailable):
            build_message_boundary(**dict(self.kwargs,verification_keys=None))
        self.assertEqual(self.resolved,[])


if __name__ == '__main__':
    unittest.main(verbosity=2)
