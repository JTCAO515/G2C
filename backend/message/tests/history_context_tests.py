"""Fixed AUTH interface + injected repository, no database/credentials/network."""
import unittest
from contextlib import contextmanager
from dataclasses import replace
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import TrustedPrincipal, VerificationResult, VerificationStatus, CJAccessFacts, Fact
from cj_message.auth_boundary import Boundary, AccessBlocked, IdentityChanged, HistoryReadContext
from cj_message.domain import ChatListCursor, ResyncRequired

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.principal=TrustedPrincipal('https://synthetic.invalid','user-a','synthetic',1,1,100)
        self.invited=Fact.YES; self.resolves=[]; self.reads=0
        test=self
        class Verifier:
            def verify(self,token): return VerificationResult(VerificationStatus.VALID,test.principal)
        class Access:
            def evaluate(self,p): return CJAccessFacts(p,Fact.YES,Fact.YES,test.invited)
        class Repository:
            scope='server-selected-scope'
            @contextmanager
            def transaction(self): yield self
            def lock_scope(self): pass
            def list_boundary(self): return ('scope-generation',0,0)
            def conversations(self,after,through,limit): test.reads+=1; return []
        self.repository=Repository()
        def resolve(p): self.resolves.append(p); return self.repository
        self.boundary=Boundary(AdmissionChecker(Verifier(),Access(),clock=lambda:50),resolve,lambda:'unused')

    def test_codec_metadata_and_domain_use_single_resolved_identity(self):
        seen=[]
        def operation(ctx):
            seen.append((ctx.principal,ctx.scope))
            rows,cursor=ctx.conversations()
            return {'rows':rows,'cursor':cursor}
        self.assertEqual(self.boundary.with_history_context('synthetic',operation),{'rows':[],'cursor':None})
        self.assertEqual(self.resolves,[self.principal])
        self.assertEqual(seen,[(self.principal,'server-selected-scope')])

    def test_forged_cursor_never_selects_repository(self):
        def operation(ctx):
            cursor=ChatListCursor('attacker-scope','scope-generation',0,0,0)
            return ctx.conversations(cursor)
        with self.assertRaises(ResyncRequired): self.boundary.with_history_context('synthetic',operation)
        self.assertEqual(len(self.resolves),1); self.assertEqual(self.reads,0)
        self.assertEqual(self.repository.scope,'server-selected-scope')

    def test_identity_switch_during_codec_blocks_domain_read(self):
        def operation(ctx):
            self.principal=replace(self.principal,subject='user-b')
            return ctx.conversations()
        with self.assertRaises(IdentityChanged): self.boundary.with_history_context('synthetic',operation)
        self.assertEqual(self.reads,0); self.assertEqual(len(self.resolves),1)

    def test_final_projection_recheck_withholds_private_response(self):
        for change in ('denied','unknown','identity'):
            self.setUp()
            def operation(ctx):
                ctx.conversations()
                if change=='identity': self.principal=replace(self.principal,subject='user-b')
                else: self.invited=Fact.NO if change=='denied' else Fact.UNKNOWN
                return b'synthetic-private-projection'
            with self.assertRaises((AccessBlocked,IdentityChanged)):
                self.boundary.with_history_context('synthetic',operation)

    def test_context_expires_on_return_or_error_and_rejects_deferred_work(self):
        captured=[]
        self.boundary.with_history_context('synthetic',lambda ctx:captured.append(ctx))
        with self.assertRaises(RuntimeError): _=captured[0].scope
        with self.assertRaises(RuntimeError): captured[0].conversations()
        with self.assertRaises(TypeError): self.boundary.with_history_context('synthetic',lambda ctx:(x for x in []))
        async def delayed(ctx): return ctx.scope
        with self.assertRaises(TypeError): self.boundary.with_history_context('synthetic',delayed)
        def broken(ctx): captured.append(ctx); raise ValueError('synthetic codec failure')
        with self.assertRaises(ValueError): self.boundary.with_history_context('synthetic',broken)
        with self.assertRaises(RuntimeError): _=captured[-1].principal

    def test_context_cannot_be_constructed_from_caller_claims_or_scope_drift(self):
        with self.assertRaises(TypeError): HistoryReadContext(self.principal,'caller-scope',object())
        def operation(ctx):
            self.repository.scope='replacement-scope'
            return ctx.conversations()
        with self.assertRaises(IdentityChanged): self.boundary.with_history_context('synthetic',operation)
        self.assertEqual(self.reads,0)

    def test_entry_denial_never_calls_codec_or_resolver(self):
        self.invited=Fact.UNKNOWN
        with self.assertRaises(AccessBlocked):
            self.boundary.with_history_context('synthetic',lambda ctx:self.fail('callback must not run'))
        self.assertEqual(self.resolves,[])
