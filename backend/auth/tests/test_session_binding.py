"""Local signed JWT/session-fact tests only. No real token, account, key store or network."""
import importlib.util
import subprocess
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cj_auth.interfaces import (VerificationStatus as V, AdmissionStatus as A, AdmissionReason as R,
                               Fact, CJAccessFacts, TrustedPrincipal)
from cj_auth.jwt_adapter import JWTConfiguration, JWTProfile, StaticPublicKeys, VerificationKey, PyJWTVerifier
from cj_auth.session_binding import (VerifiedSessionBinding, SessionVerificationResult, SessionAccessFacts)
from cj_auth.session_admission import SessionAdmissionChecker
from cj_auth.admission import AdmissionChecker
from cj_auth.read_context import ProtectedReadBoundary, ReadAdmissionFailure


class CurrentSessions:
    def __init__(self):
        self.active = {}; self.calls = []; self.member = Fact.YES
        self.email = Fact.YES; self.invited = Fact.YES; self.transform = None
    def evaluate_session(self, binding):
        self.calls.append(binding)
        facts = SessionAccessFacts(binding,CJAccessFacts(binding.principal,self.member,self.email,self.invited),
                                   self.active.get(binding.session_id,Fact.UNKNOWN))
        return self.transform(facts) if self.transform else facts


class SessionBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.private = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        now=int(time.time()); self.a=UUID('11111111-1111-4111-8111-111111111111');self.b=UUID('22222222-2222-4222-8222-222222222222')
        self.claims=dict(iss='https://new-cj.synthetic.invalid/auth/v1',aud='synthetic-aud',
            sub='33333333-3333-4333-8333-333333333333',iat=now-10,exp=now+120,
            session_id=str(self.a),role='authenticated',is_anonymous=False,aal='aal1',email='',phone='')
        self.config=JWTConfiguration(self.claims['iss'],self.claims['aud'],'RS256',0,profile=JWTProfile.SUPABASE_ACCESS_RC1)
        pem=self.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.keys=StaticPublicKeys({'synthetic':VerificationKey('RS256',pem)})
        self.verifier=PyJWTVerifier(self.config,self.keys)
        self.provider=CurrentSessions();self.provider.active={self.a:Fact.YES,self.b:Fact.YES}
        self.checker=SessionAdmissionChecker(self.verifier,self.provider)
    def token(self,**changes): return jwt.encode(self.claims|changes,self.private,algorithm='RS256',headers={'kid':'synthetic'})
    def test_only_verified_original_session_claim_becomes_binding(self):
        result=self.verifier.verify_session(self.token(session_id=str(self.b),owner='caller',invited=True))
        self.assertEqual(result.status,V.VALID);self.assertEqual(result.binding.session_id,self.b)
        self.assertEqual(result.binding.principal,self.verifier.verify(self.token(session_id=str(self.b))).principal)
        parts=self.token().split('.')
        import base64,json
        parts[1]=base64.urlsafe_b64encode(json.dumps(self.claims|{'session_id':str(self.b)}).encode()).rstrip(b'=').decode()
        tampered=self.verifier.verify_session('.'.join(parts))
        self.assertEqual(tampered.status,V.INVALID);self.assertIsNone(tampered.binding)
    def test_same_subject_distinct_sessions_have_independent_current_access(self):
        first=self.verifier.verify_session(self.token()).binding
        second=self.verifier.verify_session(self.token(session_id=str(self.b))).binding
        self.assertEqual(first.principal,second.principal);self.assertNotEqual(first,second)
        self.provider.active[self.a]=Fact.NO
        denied=self.checker.check_session(self.token());allowed=self.checker.check_session(self.token(session_id=str(self.b)))
        self.assertEqual(denied.decision.status,A.DENIED);self.assertIsNone(denied.binding)
        self.assertEqual(denied.decision.reason,R.IDENTITY_INVALID)
        self.assertEqual(allowed.decision.status,A.ALLOWED);self.assertEqual(allowed.binding.session_id,self.b)
    def test_refresh_keeps_session_id_but_does_not_create_a_partition(self):
        original=self.verifier.verify_session(self.token()).binding
        refreshed=self.verifier.verify_session(self.token(iat=self.claims['iat']+1,exp=self.claims['exp']+1)).binding
        self.assertEqual(original.session_id,refreshed.session_id)
        self.assertEqual((original.principal.issuer,original.principal.subject,original.principal.audience),
                         (refreshed.principal.issuer,refreshed.principal.subject,refreshed.principal.audience))
        self.assertNotEqual(original.principal,refreshed.principal)
        self.provider.active[self.a]=Fact.NO
        self.assertEqual(self.checker.check(self.token(iat=self.claims['iat']+1,exp=self.claims['exp']+1)).status,A.DENIED)
    def test_unknown_missing_or_failed_session_provider_never_grants(self):
        self.assertEqual(SessionAdmissionChecker(self.verifier).check(self.token()).status,A.UNKNOWN)
        self.provider.active[self.a]=Fact.UNKNOWN
        self.assertEqual(self.checker.check(self.token()).status,A.UNKNOWN)
        def outage(facts):raise OSError('synthetic unavailable')
        self.provider.transform=outage
        self.assertEqual(self.checker.check(self.token()).status,A.UNKNOWN)
    def test_current_session_does_not_bypass_existing_membership_email_invitation(self):
        for name,reason in (('member',R.NOT_CJ_MEMBER),('email',R.EMAIL_UNVERIFIED),('invited',R.NOT_INVITED)):
            for value,status in ((Fact.NO,A.DENIED),(Fact.UNKNOWN,A.UNKNOWN)):
                setattr(self.provider,name,value)
                decision=self.checker.check(self.token())
                self.assertEqual(decision.status,status)
                if value is Fact.NO:self.assertEqual(decision.reason,reason)
                setattr(self.provider,name,Fact.YES)
    def test_missing_claim_wrong_audience_and_unsupported_profile(self):
        for change in ({'session_id':None},{'session_id':'not-uuid'},{'aud':'other'},{'role':'service_role'}):
            result=self.verifier.verify_session(self.token(**change));self.assertEqual(result.status,V.INVALID);self.assertIsNone(result.binding)
        claims=dict(self.claims);del claims['session_id']
        token=jwt.encode(claims,self.private,algorithm='RS256',headers={'kid':'synthetic'})
        self.assertEqual(self.verifier.verify_session(token).status,V.INVALID)
        strict=PyJWTVerifier(replace(self.config,profile=JWTProfile.STRICT_V1),self.keys)
        self.assertEqual(strict.verify(self.token(nbf=self.claims['iat'])).status,V.VALID)
        self.assertEqual(strict.verify_session(self.token(nbf=self.claims['iat'])).status,V.UNKNOWN)
    def test_binding_result_invariants_reject_nonvalid_payloads(self):
        binding=self.verifier.verify_session(self.token()).binding
        for status in (V.INVALID,V.UNKNOWN):
            for value in (binding,'',True,{},[]):
                with self.assertRaises(ValueError):SessionVerificationResult(status,value)
        with self.assertRaises(ValueError):SessionVerificationResult(V.VALID)
        with self.assertRaises(ValueError):VerifiedSessionBinding(binding.principal,str(self.a))
    def test_late_facts_for_other_session_subject_audience_or_refresh_are_rejected(self):
        for transform in (
            lambda f:replace(f,binding=replace(f.binding,session_id=self.b)),
            lambda f:replace(f,binding=replace(f.binding,principal=replace(f.binding.principal,subject='other'))),
            lambda f:replace(f,binding=replace(f.binding,principal=replace(f.binding.principal,audience='other'))),
            lambda f:replace(f,binding=replace(f.binding,principal=replace(f.binding.principal,issued_at=f.binding.principal.issued_at+1))),
            lambda f:replace(f,access=replace(f.access,principal=replace(f.access.principal,subject='other'))),
            lambda f:replace(f,session_active=True)):
            self.provider.transform=transform
            result=self.checker.check_session(self.token())
            self.assertEqual(result.decision.status,A.UNKNOWN);self.assertIsNone(result.binding)
    def test_recheck_revocation_and_no_cache(self):
        self.assertEqual(self.checker.check(self.token()).status,A.ALLOWED)
        self.provider.active[self.a]=Fact.NO
        self.assertEqual(self.checker.check(self.token()).status,A.DENIED)
        self.assertEqual(len(self.provider.calls),2)
    def test_existing_read_context_accepts_checker_and_original_session_cannot_revive(self):
        boundary=ProtectedReadBoundary(self.checker,max_response_bytes=128)
        captured=[]
        def callback(ctx):
            captured.append(ctx);self.provider.active[self.a]=Fact.NO
            with self.assertRaises(ReadAdmissionFailure):ctx.guard()
            self.provider.active[self.a]=Fact.YES
            with self.assertRaises(ReadAdmissionFailure):ctx.guard()
            return b'never-returned'
        with self.assertRaises(ReadAdmissionFailure):boundary.with_read_context(self.token(),callback)
        self.assertEqual(boundary.with_read_context(self.token(session_id=str(self.b)),lambda ctx:b'new-session'),b'new-session')
        with self.assertRaises(ReadAdmissionFailure):captured[0].guard()
    def test_expires_during_session_lookup_never_grants(self):
        checker=SessionAdmissionChecker(self.verifier,self.provider,clock=lambda:self.claims['exp'])
        self.assertEqual(checker.check(self.token()).status,A.DENIED)
    def test_invalid_host_clock_does_not_authorize_session_access(self):
        for value in (None, True, float('nan'), float('inf')):
            checker=SessionAdmissionChecker(self.verifier,self.provider,clock=lambda:value)
            self.assertEqual(checker.check(self.token()).status,A.UNKNOWN)

    def test_actual_parent_legacy_verifier_and_checker_remain_compatible(self):
        # Load only two fixed parent blobs; no old dependencies/config/resources are used.
        root=Path(__file__).resolve().parents[3]
        parent='8b6abb236cf10c1865a9cc8c6155bd8ac732c07e'
        if subprocess.run(['git','-C',str(root),'cat-file','-e',parent+'^{commit}'],capture_output=True).returncode:
            self.skipTest('legacy parent commit '+parent[:7]+' is not in this repository')
        with tempfile.TemporaryDirectory(prefix='cj007-legacy-binding-') as directory:
            modules=[]
            for name in ('jwt_adapter','admission'):
                data=subprocess.check_output(['git','-C',str(root),'show','8b6abb236cf10c1865a9cc8c6155bd8ac732c07e:backend/auth/cj_auth/'+name+'.py'])
                path=Path(directory)/(name+'.py');path.write_bytes(data)
                spec=importlib.util.spec_from_file_location('cj_auth._parent_'+name,path)
                module=importlib.util.module_from_spec(spec)
                import sys
                sys.modules[spec.name]=module
                try:spec.loader.exec_module(module)
                finally:sys.modules.pop(spec.name,None)
                modules.append(module)
            oldjwt,oldadmission=modules
            oldconfig=oldjwt.JWTConfiguration(self.config.issuer,self.config.audience,'RS256',0,
                                             profile=oldjwt.JWTProfile.SUPABASE_ACCESS_RC1)
            pem=self.keys.resolve('synthetic').public_pem
            old=oldjwt.PyJWTVerifier(oldconfig,oldjwt.StaticPublicKeys({'synthetic':oldjwt.VerificationKey('RS256',pem)}))
            for token in (self.token(),self.token(aud='other'),self.token(session_id=None)):
                self.assertEqual(old.verify(token),self.verifier.verify(token))
            class OldFacts:
                def evaluate(self,p):return CJAccessFacts(p,Fact.YES,Fact.YES,Fact.YES)
            self.assertEqual(oldadmission.AdmissionChecker(old,OldFacts()).check(self.token()),
                             AdmissionChecker(self.verifier,OldFacts()).check(self.token()))


if __name__=='__main__':unittest.main()
