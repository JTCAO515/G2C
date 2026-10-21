import json
import threading
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cj_auth.jwt_adapter import JWTConfiguration, PyJWTVerifier
from cj_auth.jwks_provider import BoundedJWKSProvider, JWKSConfiguration
from cj_auth.interfaces import VerificationStatus as V


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


class Response:
    def __init__(self, data, url, status=200, chunks=None):
        self.status, self.final_url, self.content_type = status, url, 'application/json'
        self.chunks = chunks if chunks is not None else [data]
        self.closed = False
    def close(self): self.closed = True


class Transport:
    def __init__(self, handler): self.handler, self.calls = handler, []
    def fetch(self, request): self.calls.append(request); return self.handler(request)


class JWKSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.b = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.clock = Clock()
        self.verification = JWTConfiguration('https://issuer.synthetic.invalid/auth/v1','synthetic-aud','RS256',0)
        self.config = JWKSConfiguration(self.verification.issuer,'https://keys.synthetic.invalid/jwks','RS256',
            cache_ttl_seconds=30,refresh_interval_seconds=10,request_timeout_seconds=5,
            max_response_bytes=8192,max_chunks=8,max_keys=4,max_kid_bytes=64,max_rsa_bits=4096)
        self.document = {'keys':[self.jwk(self.a,'a')]}
        self.transport = Transport(lambda r:Response(json.dumps(self.document).encode(),r.url))
    def jwk(self, key, kid):
        return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))|{'kid':kid,'alg':'RS256','use':'sig'}
    def provider(self, transport=None, config=None):
        return BoundedJWKSProvider(verification=self.verification,configuration=config or self.config,
                                   transport=transport or self.transport,clock=self.clock)
    def token(self, key, kid, **headers):
        now=int(time.time())
        return jwt.encode(dict(iss=self.verification.issuer,aud='synthetic-aud',sub='synthetic-A',
            iat=now-1,nbf=now-1,exp=now+60),key,algorithm='RS256',headers={'kid':kid}|headers)

    def test_default_closed_and_explicit_binding_validation(self):
        self.assertIsNone(BoundedJWKSProvider().resolve('a'))
        self.assertIsNone(BoundedJWKSProvider(verification=self.verification,configuration=self.config).resolve('a'))
        self.assertEqual(self.transport.calls,[])
        for change in ({'issuer':'https://other.invalid'},{'algorithm':'ES256'}):
            with self.assertRaises(ValueError): self.provider(config=replace(self.config,**change))
        for change in ({'url':'http://keys.invalid'},{'url':'https://u:p@keys.invalid'},{'cache_ttl_seconds':0},
                       {'refresh_interval_seconds':float('nan')},{'max_chunks':True},{'max_response_bytes':-1}):
            with self.assertRaises(ValueError): replace(self.config,**change)

    def test_signature_cache_and_token_url_does_not_select_source(self):
        verifier=PyJWTVerifier(self.verification,self.provider())
        with patch('socket.socket',side_effect=AssertionError('no network')):
            self.assertEqual(verifier.verify(self.token(self.a,'a')).status,V.VALID)
            self.assertEqual(verifier.verify(self.token(self.a,'a')).status,V.VALID)
            self.assertEqual(verifier.verify(self.token(self.a,'a',jku='https://attacker.invalid')).status,V.INVALID)
        self.assertEqual(len(self.transport.calls),1)
        self.assertEqual(self.transport.calls[0].url,self.config.url)

    def test_rotation_replaces_set_and_retires_removed_key(self):
        p=self.provider(); self.assertIsNotNone(p.resolve('a'))
        self.clock.now+=11; self.document={'keys':[self.jwk(self.b,'b')]}
        self.assertIsNotNone(p.resolve('b')); self.assertIsNone(p.resolve('a'))
        self.assertEqual(len(self.transport.calls),2)
        self.assertEqual(PyJWTVerifier(self.verification,p).verify(self.token(self.b,'b')).status,V.VALID)

    def test_same_kid_replacement_after_ttl_does_not_keep_old_material(self):
        p=self.provider(); verifier=PyJWTVerifier(self.verification,p)
        self.assertEqual(verifier.verify(self.token(self.a,'a')).status,V.VALID)
        self.document={'keys':[self.jwk(self.b,'a')]}
        self.assertEqual(verifier.verify(self.token(self.b,'a')).status,V.INVALID)
        self.clock.now += 31
        self.assertEqual(verifier.verify(self.token(self.b,'a')).status,V.VALID)
        self.assertEqual(verifier.verify(self.token(self.a,'a')).status,V.INVALID)
        self.assertEqual(len(self.transport.calls),2)

    def test_unknown_kid_flood_and_failure_share_global_cooldown(self):
        p=self.provider(); p.resolve('a')
        for i in range(100): self.assertIsNone(p.resolve(str(i)))
        self.assertEqual(len(self.transport.calls),1)
        self.clock.now+=11
        self.transport.handler=lambda r: (_ for _ in ()).throw(OSError('synthetic outage'))
        self.assertIsNone(p.resolve('missing'))
        for i in range(100): p.resolve(str(i))
        self.assertEqual(len(self.transport.calls),2)
        self.assertIsNotNone(p.resolve('a')) # only within ORIGINAL expiry
        self.clock.now=131
        self.assertEqual(PyJWTVerifier(self.verification,p).verify(self.token(self.a,'a')).status,V.UNKNOWN)
        self.assertEqual(len(self.transport.calls),3)

    def test_expired_cache_no_fallback_and_no_failed_refresh_extension(self):
        p=self.provider(); p.resolve('a'); self.clock.now=131
        self.transport.handler=lambda r:Response(b'{}',r.url,status=503)
        self.assertIsNone(p.resolve('a'))
        self.clock.now=132; self.assertIsNone(p.resolve('a'))
        self.assertEqual(len(self.transport.calls),2)

    def test_body_chunk_keyid_limits_redirect_and_close(self):
        for response in (Response(b'',self.config.url,chunks=[b'x'*8193]),
                         Response(b'',self.config.url,chunks=[b'']*9),
                         Response(b'{}','https://redirect.invalid'),Response(b'{}',self.config.url,status=302)):
            t=Transport(lambda r:response)
            self.assertIsNone(self.provider(transport=t).resolve('a'))
            self.assertTrue(response.closed); self.assertEqual(len(t.calls),1)
        p=self.provider(); self.assertIsNone(p.resolve('x'*65)); self.assertEqual(len(self.transport.calls),0)

    def test_duplicate_private_wrong_type_ops_and_key_count_rejected(self):
        key=self.jwk(self.a,'a')
        for doc in ({'keys':[key,key]},{'keys':[key|{'d':'synthetic-private-field'}]},
                    {'keys':[key|{'kty':'EC'}]},{'keys':[key|{'key_ops':['sign']}]},
                    {'keys':[key|{'use':'enc'}]},{'keys':[key|{'kid':str(i)} for i in range(5)]}):
            t=Transport(lambda r:Response(json.dumps(doc).encode(),r.url))
            self.assertIsNone(self.provider(transport=t).resolve('a'))
        t=Transport(lambda r:Response(b'{"keys":[],"keys":[]}',r.url))
        self.assertIsNone(self.provider(transport=t).resolve('a'))

    def test_explicit_ec_profile_and_wrong_curve(self):
        for curve,valid in ((ec.SECP256R1(),True),(ec.SECP384R1(),False)):
            key=ec.generate_private_key(curve)
            jwk=json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))|{'kid':'e','alg':'ES256'}
            t=Transport(lambda r:Response(json.dumps({'keys':[jwk]}).encode(),r.url))
            p=BoundedJWKSProvider(verification=replace(self.verification,algorithm='ES256'),
                configuration=replace(self.config,algorithm='ES256'),transport=t,clock=self.clock)
            self.assertEqual(p.resolve('e') is not None,valid)

    def test_concurrent_unknowns_do_not_start_parallel_refresh(self):
        entered=threading.Event(); release=threading.Event(); output=[]
        def fetch(r):
            entered.set()
            if not release.wait(2): raise TimeoutError('test synchronization')
            return Response(json.dumps(self.document).encode(),r.url)
        t=Transport(fetch); p=self.provider(transport=t)
        worker=threading.Thread(target=lambda:output.append(p.resolve('a')),daemon=True); worker.start()
        try:
            self.assertTrue(entered.wait(2))
            for i in range(20): self.assertIsNone(p.resolve('missing-'+str(i)))
            self.assertEqual(len(t.calls),1)
        finally: release.set(); worker.join(2)
        self.assertFalse(worker.is_alive()); self.assertIsNotNone(output[0])

    def test_cancel_or_close_discards_late_result_without_resetting_cooldown(self):
        for close in (False,True):
            entered=threading.Event(); release=threading.Event(); output=[]
            def fetch(r):
                entered.set()
                if not release.wait(2): raise TimeoutError('test synchronization')
                return Response(json.dumps(self.document).encode(),r.url)
            t=Transport(fetch); p=self.provider(transport=t)
            worker=threading.Thread(target=lambda:output.append(p.resolve('a')),daemon=True); worker.start()
            try:
                self.assertTrue(entered.wait(2))
                p.close() if close else p.cancel_refresh()
            finally: release.set(); worker.join(2)
            self.assertFalse(worker.is_alive()); self.assertEqual(output,[None]); self.assertIsNone(p.resolve('a'))
            self.assertEqual(len(t.calls),1)
            self.clock.now += 11
            if close:
                self.assertIsNone(p.resolve('a')); self.assertEqual(len(t.calls),1)
            else:
                self.assertIsNotNone(p.resolve('a')); self.assertEqual(len(t.calls),2)

    def test_deadline_and_backward_clock_reject(self):
        def late(r):
            self.clock.now+=6
            return Response(json.dumps(self.document).encode(),r.url)
        p=self.provider(transport=Transport(late)); self.assertIsNone(p.resolve('a'))
        p=self.provider(); self.assertIsNotNone(p.resolve('a'))
        self.clock.now-=1; self.assertIsNone(p.resolve('a'))


if __name__ == '__main__': unittest.main()
