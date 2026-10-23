"""Root opt-in + actual canonical signed JWT/session checker/protected ASGI lifetime.

The fixture-only route is not a product endpoint or an OpenAPI addition.
"""
import json,os,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import UUID
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from fastapi.responses import JSONResponse,Response
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool
from cj_auth import composition as old_auth
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import AdmissionStatus,Fact,CJAccessFacts
from cj_auth.jwt_adapter import JWTConfiguration,JWTProfile,StaticPublicKeys,VerificationKey,PyJWTVerifier
from cj_auth.read_context import ReadAdmissionFailure
from cj_auth.session_binding import SessionAccessFacts
from cj_auth.session_admission import SessionAdmissionChecker
from cj_api.app import create_app
from cj_api.composition import build_verified_session_checker,with_verified_session_read,CompositionUnavailable
from cj_api.message_routes import _error,_token

A=UUID('11111111-1111-4111-8111-111111111111');B=UUID('22222222-2222-4222-8222-222222222222')
SUB='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
class Facts:
    def __init__(self):
        self.states={A:Fact.YES,B:Fact.YES};self.calls=[];self.mode='fresh';self.late=None;self.invited=Fact.YES
        self.wait_a=False;self.entered=threading.Event();self.release=threading.Event()
    def evaluate_session(self,binding):
        self.calls.append(binding)
        if self.wait_a and binding.session_id==A:
            self.entered.set()
            if not self.release.wait(5):raise TimeoutError('PRIVATE_DELAY')
        if self.mode=='exception':raise OSError('PRIVATE_PROVIDER_FAILURE')
        if self.mode=='missing':return None
        if self.mode=='late':return SessionAccessFacts(self.late,CJAccessFacts(self.late.principal,Fact.YES,Fact.YES,Fact.YES),Fact.YES)
        return SessionAccessFacts(binding,CJAccessFacts(binding.principal,Fact.YES,Fact.YES,self.invited),self.states[binding.session_id])

class SessionWireChecks(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'CJ_ENV':'local'});env.start();self.addCleanup(env.stop)
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.keys=StaticPublicKeys({'fixture-key':VerificationKey('RS256',public)})
        self.config=JWTConfiguration('https://synthetic.invalid/auth/v1','authenticated','RS256',0,profile=JWTProfile.SUPABASE_ACCESS_RC1)
        self.provider=Facts();self.checker=self.build();self.projected=[];self.contexts=[];self.scope_hits=[];self.encoded=[];self.after_encode=None
        self.token_a=self.token(A);self.token_b=self.token(B)
        app=create_app()
        @app.get('/__fixture/verified-session-read')
        async def read(request:Request):
            token=_token(request)
            if token is None:return _error(request,401,'ACCESS_DENIED','access','failed','do_not_retry')
            rid=request.state.request_id
            def project(ctx):
                ctx.require_current();self.contexts.append(ctx);p=ctx.principal
                self.scope_hits.append((p.issuer,p.subject,p.audience))
                self.projected.append(True)
                raw=JSONResponse(dict(request_id=rid,value='PRIVATE_FIXTURE_READ')).body
                self.encoded.append(raw)
                if self.after_encode:self.after_encode()
                return raw
            try:
                raw=await run_in_threadpool(with_verified_session_read,checker=self.checker,token=token,max_response_bytes=4096,project=project)
                return Response(content=raw,media_type='application/json')
            except ReadAdmissionFailure as exc:
                if exc.status is AdmissionStatus.DENIED:return _error(request,401 if exc.reason.value=='identity_invalid' else 403,'ACCESS_DENIED','access','failed','do_not_retry')
                return _error(request,503,'ACCESS_UNKNOWN','access','unknown','retry_safe_read')
            except Exception:return _error(request,503,'SESSION_READ_UNAVAILABLE','dependency','unknown','retry_safe_read')
        self.client=TestClient(app);self.addCleanup(self.client.close)
    def build(self,**changes):
        args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,session_access_provider=self.provider);args.update(changes)
        return build_verified_session_checker(**args)
    def token(self,sid,shift=0,**changes):
        now=int(time.time());claims=dict(iss=self.config.issuer,aud=self.config.audience,sub=SUB,iat=now-5+shift,exp=now+120,session_id=str(sid),role='authenticated',is_anonymous=False,aal='aal1',email='synthetic@example.invalid',phone='')
        claims.update(changes)
        if claims.get('session_id') is None:claims.pop('session_id',None)
        return jwt.encode(claims,self.key,algorithm='RS256',headers={'kid':'fixture-key'})
    def get(self,token=None):return self.client.get('/__fixture/verified-session-read',headers={'Authorization':'Bearer '+(token or self.token_a)})
    def no_private(self,result,status):
        self.assertEqual(result.status_code,status,result.text);self.assertNotIn('value',result.json());self.assertNotIn('PRIVATE_',result.text)
    def test_root_opt_in_exact_checker_final_bytes_and_stable_subject_scope(self):
        self.assertIs(type(self.checker),SessionAdmissionChecker);self.assertIsInstance(self.checker,AdmissionChecker)
        r=self.get();self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.content,self.encoded[-1]);self.assertEqual(r.json()['request_id'],r.headers['X-Request-ID']);self.assertEqual(r.headers['Cache-Control'],'no-store')
        refresh=self.token(A,shift=3);self.assertEqual(self.get(refresh).status_code,200)
        self.assertEqual(len(set(self.scope_hits)),1)
        self.assertTrue(all(b.session_id==A for b in self.provider.calls));self.assertGreaterEqual(len(self.provider.calls),6)
    def test_no_provider_keys_missing_facts_or_unknown_never_project(self):
        for changes in [dict(session_access_provider=None),dict(verification_keys=None)]:
            self.checker=self.build(**changes);self.no_private(self.get(),503)
        self.checker=self.build()
        for mode in ['missing','exception']:
            self.provider.mode=mode;self.no_private(self.get(),503)
        self.provider.mode='fresh';self.provider.states[A]=Fact.UNKNOWN;self.no_private(self.get(),503)
        self.assertEqual(self.projected,[])
    def test_same_subject_session_a_revoked_does_not_revoke_b_or_grant_invitation(self):
        self.provider.states[A]=Fact.NO;self.no_private(self.get(),401)
        r=self.get(self.token_b);self.assertEqual(r.status_code,200,r.text)
        self.provider.invited=Fact.NO;self.no_private(self.get(self.token_b),403)
        self.assertEqual({b.principal.subject for b in self.provider.calls},{SUB})
    def test_late_wrong_session_or_refresh_snapshot_facts_withheld(self):
        verifier=PyJWTVerifier(self.config,self.keys)
        self.provider.mode='late';self.provider.late=verifier.verify_session(self.token_b).binding
        self.no_private(self.get(self.token_a),503)
        self.provider.late=verifier.verify_session(self.token_a).binding
        refresh=self.token(A,shift=3);self.no_private(self.get(refresh),503)
        self.assertEqual(self.projected,[])
        self.provider.mode='fresh';self.assertEqual(self.get(refresh).status_code,200)
    def test_final_revocation_withholds_encoded_result_and_old_context_stays_retired(self):
        self.after_encode=lambda:self.provider.states.__setitem__(A,Fact.NO)
        self.no_private(self.get(),401);self.assertEqual(len(self.projected),1)
        old=self.contexts[-1];self.provider.states[A]=Fact.YES;self.after_encode=None
        with self.assertRaises(Exception):old.require_current()
        self.assertEqual(self.get(self.token_b).status_code,200)
        self.assertEqual(self.get(self.token_a).status_code,200);self.assertIsNot(self.contexts[-1],old)
    def test_delayed_a_denial_cannot_settle_b_or_replace_original_token(self):
        self.provider.wait_a=True
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(self.get,self.token_a)
            self.assertTrue(self.provider.entered.wait(5))
            r=self.get(self.token_b);self.assertEqual(r.status_code,200,r.text)
            self.provider.states[A]=Fact.NO;self.provider.release.set();self.no_private(pending.result(timeout=5),401)
        self.assertEqual(self.get(self.token_b).status_code,200)
        self.assertEqual({b.session_id for b in self.provider.calls},{A,B})
    def test_missing_claim_profile_provider_type_and_bounds_fail_closed(self):
        self.no_private(self.get(self.token(A,session_id=None)),401)
        self.assertEqual(self.provider.calls,[])
        strict=replace(self.config,profile=JWTProfile.STRICT_V1)
        class PrincipalOnly:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.YES)
        for changes in [dict(jwt_configuration=None),dict(jwt_configuration=strict),dict(session_access_provider=PrincipalOnly()),dict(environment='c2')]:
            with self.assertRaises(CompositionUnavailable):self.build(**changes)
        legacy=AdmissionChecker(PyJWTVerifier(self.config,self.keys),PrincipalOnly())
        with self.assertRaises(CompositionUnavailable):with_verified_session_read(checker=legacy,token=self.token_a,max_response_bytes=100,project=lambda c:b'{}')
        for limit in [True,0,1048577]:
            with self.assertRaises(CompositionUnavailable):with_verified_session_read(checker=self.checker,token=self.token_a,max_response_bytes=limit,project=lambda c:b'{}')
    def test_old_build_auth_remains_original_principal_only_path_and_feas_closed(self):
        class OldFacts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.YES)
        self.provider.states[A]=Fact.NO
        auth=old_auth.build_auth(configuration=self.config,keys=self.keys,access=OldFacts())
        self.assertIs(auth.authorize('Bearer '+self.token_a).decision.status,AdmissionStatus.ALLOWED)
        self.assertEqual(self.provider.calls,[])
        self.no_private(self.get(),401)
        self.assertEqual(self.client.get('/v1/needs-feasibility?needs_id=none',headers={'Authorization':'Bearer '+self.token_a}).status_code,503)
