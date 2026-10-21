"""Official documented claim shapes, signed with local in-memory test keys only."""
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cj_auth.jwt_adapter import JWTProfile, JWTConfiguration, VerificationKey, StaticPublicKeys, PyJWTVerifier
from cj_auth.interfaces import Fact, CJAccessFacts, VerificationStatus as V, AdmissionStatus
from cj_auth.composition import build_auth, COMPOSITION_VERSION


class Facts:
    def __init__(self, member=Fact.YES, email=Fact.YES, invited=Fact.YES):
        self.values = member, email, invited
    def evaluate(self, p): return CJAccessFacts(p, *self.values)


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    def setUp(self):
        now = int(time.time())
        self.claims = dict(iss='https://new-cj.synthetic.invalid/auth/v1', aud='synthetic-audience',
            sub='11111111-1111-4111-8111-111111111111', exp=now+120, iat=now-10, role='authenticated',
            aal='aal1', session_id='22222222-2222-4222-8222-222222222222',
            email='synthetic@example.invalid', phone='', is_anonymous=False)
        self.config = JWTConfiguration(self.claims['iss'], self.claims['aud'], 'RS256', 0,
                                       profile=JWTProfile.SUPABASE_ACCESS_RC1)
        pem = self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.keys = StaticPublicKeys({'synthetic': VerificationKey('RS256',pem)})
        self.verifier = PyJWTVerifier(self.config,self.keys)
    def token(self, changes=None, missing=None, kid='synthetic'):
        claims = self.claims | (changes or {})
        if missing: del claims[missing]
        return jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':kid})
    def boundary(self, access=None): return build_auth(configuration=self.config, keys=self.keys, access=access)
    def invalid(self, changes): self.assertEqual(self.verifier.verify(self.token(changes)).status,V.INVALID)

    def test_optional_nbf_new_profile_only(self):
        result = self.verifier.verify(self.token())
        self.assertEqual(result.status,V.VALID)
        self.assertEqual(result.principal.not_before,self.claims['iat'])
        strict = PyJWTVerifier(replace(self.config,profile=JWTProfile.STRICT_V1),self.keys)
        self.assertEqual(strict.verify(self.token()).status,V.INVALID)
        self.assertEqual(strict.verify(self.token({'nbf':self.claims['iat']})).status,V.VALID)

    def test_array_audience_requires_expected_recipient(self):
        for aud in ([self.config.audience],['other',self.config.audience],self.config.audience):
            result = self.verifier.verify(self.token({'aud':aud}))
            self.assertEqual(result.status,V.VALID)
            self.assertEqual(result.principal.audience,self.config.audience)
        for aud in ([],['other'],['other',1],[self.config.audience]*2,None,''): self.invalid({'aud':aud})

    def test_optional_nbf_present_stays_strict_and_other_time_checks_remain(self):
        for nbf in (int(time.time())+60,None,True,str(self.claims['iat']),1.5): self.invalid({'nbf':nbf})
        for changes in ({'iat':int(time.time())+60},{'exp':int(time.time())-1},
                        {'iss':self.config.issuer+'/'},{'aud':'other'},{'exp':None}): self.invalid(changes)
        for missing in ('iat','exp'):
            self.assertEqual(self.verifier.verify(self.token(missing=missing)).status,V.INVALID)

    def test_user_shape_excludes_anonymous_service_and_malformed_fields(self):
        for changes in ({'role':'service_role'},{'role':'anon'},{'is_anonymous':True},
                        {'is_anonymous':'false'},{'sub':'not-uuid'},{'session_id':''},{'aal':'other'}): self.invalid(changes)
        for missing in ('role','session_id','is_anonymous','aal','email','phone'):
            self.assertEqual(self.verifier.verify(self.token(missing=missing)).status,V.INVALID)

    def test_explicit_configuration_and_no_fallback(self):
        for changes in ({'issuer':'http://synthetic.invalid'},{'issuer':'https://u:p@synthetic.invalid'},
                        {'issuer':'https://synthetic.invalid?x=1'},{'audience':' padded '},
                        {'algorithm':'HS256'},{'clock_skew_seconds':True},{'profile':'auto'}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): replace(self.config,**changes)
        with self.assertRaises(TypeError): build_auth()
        result = build_auth(configuration=None,keys=None,access=None).authorize('Bearer '+self.token())
        self.assertEqual(result.http_status_hint,503)
        self.assertEqual(result.error.outcome,'unknown')

    def test_bearer_and_base_semantics_no_fabricated_receipt(self):
        boundary = self.boundary(Facts())
        for header in (None,'','Basic x','Bearer','Bearer  x','Bearer x,y','Bearer x\ny'):
            result = boundary.authorize(header)
            self.assertEqual(result.http_status_hint,401)
            self.assertEqual((result.error.outcome,result.error.recovery),('failed','do_not_retry'))
            self.assertIsNone(result.decision.principal)
            self.assertFalse(hasattr(result,'request_id'))
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            allowed = boundary.authorize('bearer '+self.token())
        self.assertEqual(allowed.decision.status,AdmissionStatus.ALLOWED)
        self.assertIsNone(allowed.error)

    def test_missing_membership_cannot_use_signed_email_or_role_as_grant(self):
        token = self.token({'member':True,'invited':True,'email_verified':True,'user_metadata':{'invited':True}})
        for access in (None,Facts(member=Fact.UNKNOWN),Facts(email=Fact.UNKNOWN),Facts(invited=Fact.UNKNOWN)):
            result = self.boundary(access).authorize('Bearer '+token)
            self.assertEqual(result.http_status_hint,503)
            self.assertEqual(result.error.recovery,'retry_safe_read')
        for access in (Facts(member=Fact.NO),Facts(email=Fact.NO),Facts(invited=Fact.NO)):
            result = self.boundary(access).authorize('Bearer '+token)
            self.assertEqual(result.http_status_hint,403)
            self.assertIsNone(result.decision.principal)

    def test_unknown_key_differs_from_invalid_signature(self):
        boundary = self.boundary(Facts())
        self.assertEqual(boundary.authorize('Bearer '+self.token(kid='unknown')).http_status_hint,503)
        parts = self.token().split('.'); parts[2] = 'AAAA'
        self.assertEqual(boundary.authorize('Bearer '+'.'.join(parts)).http_status_hint,401)
        self.assertEqual(COMPOSITION_VERSION,'CJ-AUTH-COMPOSITION@0.1.0-rc.1')


if __name__ == '__main__': unittest.main()
