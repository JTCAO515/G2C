"""Same-context message source query; synthetic repository and actual fixed AUTH gate."""
import hashlib
import json
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import TrustedPrincipal, VerificationResult, VerificationStatus, CJAccessFacts, Fact
from cj_message.auth_boundary import Boundary, IdentityChanged, AccessBlocked
from cj_message.domain import Stored, Receipt, Chat, Unavailable


class QueryContextTests(unittest.TestCase):
    def setUp(self):
        self.p = TrustedPrincipal('https://synthetic.invalid','account-a','fixture',1,1,100)
        self.invited = Fact.YES
        self.finds = []; self.resolves = []
        raw = json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id='mé',text='合成',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
        self.original = Stored(raw,Receipt('mé','chat','g1',1,'original-run',hashlib.sha256(raw).hexdigest()))
        self.stored = self.original; self.generation = 'g1'; self.active = True; self.failure = None
        owner = self
        class Verifier:
            def verify(self,token): return VerificationResult(VerificationStatus.VALID,owner.p)
        class Access:
            def evaluate(self,p): return CJAccessFacts(p,Fact.YES,Fact.YES,owner.invited)
        class Repo:
            scope='trusted-a'
            @contextmanager
            def transaction(self): yield self
            def lock_scope(self): pass
            def find(self,mid):
                owner.finds.append(mid)
                if owner.failure: raise owner.failure
                return owner.stored
            def chat(self,cid,generation=None):
                if not owner.active or cid!='chat' or generation!=owner.generation: raise Unavailable()
                return Chat(owner.generation,0,1)
        self.repo = Repo()
        def resolve(p): self.resolves.append(p); return self.repo
        self.boundary = Boundary(AdmissionChecker(Verifier(),Access(),clock=lambda:50),resolve,lambda:'unused')

    def query(self,mid='mé'):
        return self.boundary.with_history_context('synthetic',lambda ctx:ctx.query_message(mid))

    def test_exact_original_receipt_and_same_context_metadata(self):
        def read(ctx):
            item=ctx.query_message('mé')
            self.assertEqual(ctx.principal,self.p); self.assertEqual(ctx.scope,'trusted-a')
            self.assertIs(item,self.original)
            return item
        self.assertEqual(self.boundary.with_history_context('synthetic',read),self.original)
        self.assertEqual(self.resolves,[self.p]); self.assertEqual(self.finds,['mé'])
        self.assertEqual(self.original.receipt.run_id,'original-run')

    def test_missing_is_none_but_dependency_and_generation_errors_are_not(self):
        self.stored=None; self.assertIsNone(self.query())
        self.stored=self.original
        self.failure=OSError('synthetic unavailable')
        with self.assertRaises(OSError): self.query()
        self.failure=None; self.generation='new-generation'
        with self.assertRaises(Unavailable): self.query()
        self.generation='g1'; self.active=False
        with self.assertRaises(Unavailable): self.query()

    def test_changed_hash_input_message_or_conversation_rejected(self):
        r=self.original.receipt
        for stored in (
            replace(self.original,raw=self.original.raw+b' '),
            replace(self.original,receipt=replace(r,input_sha256='0'*64)),
            replace(self.original,receipt=replace(r,message_id='me\u0301')),
            replace(self.original,receipt=replace(r,conversation_id='other')),
            replace(self.original,raw=b'not json'),
            replace(self.original,receipt=replace(r,sequence=True)),
            replace(self.original,receipt=replace(r,run_id='')),
        ):
            self.stored=stored
            with self.assertRaises(Unavailable): self.query()
        self.stored=self.original
        with self.assertRaises(Unavailable): self.query('me\u0301')

    def test_identity_and_final_gate_changes_withhold_source(self):
        def switched(ctx):
            self.p=replace(self.p,subject='other')
            return ctx.query_message('mé')
        with self.assertRaises(IdentityChanged): self.boundary.with_history_context('synthetic',switched)
        self.assertEqual(self.finds,[])
        def revoked(ctx):
            result=ctx.query_message('mé'); self.invited=Fact.UNKNOWN; return result
        with self.assertRaises(AccessBlocked): self.boundary.with_history_context('synthetic',revoked)

    def test_expired_and_cross_thread_even_with_copied_context_rejected(self):
        captured=[]
        def read(ctx):
            captured.append(ctx)
            copied=copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(copied.run,ctx.query_message,'mé')
                with self.assertRaises(RuntimeError): future.result()
            return ctx.query_message('mé')
        self.boundary.with_history_context('synthetic',read)
        self.assertEqual(self.finds,['mé'])
        with self.assertRaises(RuntimeError): captured[0].query_message('mé')

    def test_resolver_reentry_is_refused_before_second_auth_binding(self):
        original_resolver=self.boundary.resolve_repository
        def resolver(p):
            with self.assertRaises(RuntimeError):
                self.boundary.with_history_context('synthetic',lambda ctx:self.fail('nested callback'))
            return original_resolver(p)
        self.boundary.resolve_repository=resolver
        self.assertEqual(self.query(),self.original)
        self.assertEqual(self.resolves,[self.p])

    def test_nested_context_refused_without_replacing_outer_binding(self):
        def read(ctx):
            with self.assertRaises(RuntimeError):
                self.boundary.with_history_context('synthetic',lambda inner:inner.query_message('mé'))
            return ctx.query_message('mé')
        self.assertEqual(self.boundary.with_history_context('synthetic',read),self.original)
        self.assertEqual(len(self.resolves),1)
        # Context reset permits a later independent call, not a retained old authority.
        self.assertEqual(self.query(),self.original)


if __name__=='__main__': unittest.main(verbosity=2)
