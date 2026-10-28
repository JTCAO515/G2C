"""Canonical AUTH8b composition + actual task-private PG; no fake AUTH boundary."""
import asyncio
from dataclasses import asdict, replace
import json
import unittest
import uuid
import psycopg
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import TrustedPrincipal,VerificationResult,VerificationStatus,CJAccessFacts,Fact
from cj_auth.read_context import ProtectedReadBoundary,ReadAdmissionFailure,ReadContextViolation
from cj_cleanup import core
from cj_cleanup.postgres import Repository,Unavailable,CommitUnknown
from cj_cleanup.protected_progress import Configuration,ProgressReader,ProgressUnavailable,post_logout_query
import test_cleanup as fixtures

ADMIN=None
READ=None

class Verifier:
    def __init__(self,principal): self.principal,self.status=principal,VerificationStatus.VALID
    def verify(self,token):
        return VerificationResult(self.status,self.principal if self.status is VerificationStatus.VALID else None)

class Access:
    def __init__(self): self.invited,self.calls,self.hooks=Fact.YES,0,{}
    def evaluate(self,principal):
        self.calls+=1
        hook=self.hooks.pop(self.calls,None)
        if hook: hook()
        return CJAccessFacts(principal,Fact.YES,Fact.YES,self.invited)

class Close:
    def __init__(self,conn,callback): self.conn,self.callback=conn,callback
    def __getattr__(self,name): return getattr(self.conn,name)
    def close(self): self.conn.close();self.callback()

class ProgressTests(unittest.TestCase):
    def setUp(self):
        if ADMIN is None or READ is None: self.skipTest('requires task-private new cluster runner')
        self.principal=TrustedPrincipal('issuer','synthetic-'+uuid.uuid4().hex,'aud',1,1,100)
        self.scope=core.Scope.from_principal('synthetic',self.principal)
        f=fixtures.CleanupTests();f.setUp();self.f=f
        self.op=f.op(True,self.scope)
        self.admin=lambda:psycopg.connect(**ADMIN)
        self.writer=Repository(self.admin,self.scope,lambda s:None)
        self.op=self.writer.create(self.op)
        self.verifier,self.access=Verifier(self.principal),Access()
        self.checker=AdmissionChecker(self.verifier,self.access,clock=lambda:50)
        self.boundary=ProtectedReadBoundary(self.checker,max_response_bytes=32768)
        self.config=Configuration('synthetic','issuer','aud',64,32768)
        self.connection=lambda:psycopg.connect(**READ)
        self.resolutions=0
        self.selected=None
        def resolve(principal,environment,guard):
            self.resolutions+=1
            self.selected=Repository(self.connection,core.Scope.from_principal(environment,principal),guard)
            return self.selected
        self.resolver=resolve
        self.reader=ProgressReader(self.boundary,self.resolver,configuration=self.config)
        self.token='SYNTHETIC-NOT-A-REAL-TOKEN'

    def read(self,**kw): return self.reader.read(self.token,self.op.operation_id,**kw)
    def before(self):
        with self.admin() as c:
            return c.execute('SELECT revision,journal_bytes,state_bytes FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s',
                             (core.encode(asdict(self.scope)),)).fetchone()

    def test_read_is_projected_and_exactly_read_only(self):
        before=self.before()
        value=json.loads(self.read())
        self.assertEqual(set(value),{'operation_id','revision','status','steps','reasons'})
        self.assertEqual(value['operation_id'],self.op.operation_id)
        self.assertEqual(value['status'],'awaiting_revocation')
        self.assertEqual(set(value['steps'][0]),{'target','state','reason'})
        self.assertEqual(self.before(),before)
        # Runtime role has SELECT only; no mutation privileges hidden by the reader.
        with psycopg.connect(**READ) as c:
            flags=c.execute("SELECT has_table_privilege(current_user,'cj_cleanup_journal_candidate','SELECT'),has_table_privilege(current_user,'cj_cleanup_journal_candidate','INSERT'),has_table_privilege(current_user,'cj_cleanup_journal_candidate','UPDATE'),has_table_privilege(current_user,'cj_cleanup_journal_candidate','DELETE')").fetchone()
            self.assertEqual(flags,(True,False,False,False))

    def test_unknown_intent_and_original_receipt_are_not_exposed_or_recovered(self):
        self.op=self.writer.intent(self.op.operation_id,self.op.revision,'auth_revocation','PRIVATE_ORIGINAL_INVOCATION')
        self.op=self.writer.receipt(self.op.operation_id,self.op.revision,'auth_revocation',self.f.result(self.op,'auth_revocation','unknown'))
        before=self.before();raw=self.read();value=json.loads(raw)
        self.assertEqual(value['status'],'unknown')
        self.assertEqual(value['steps'][0]['reason'],'original_result_unknown')
        for secret in (self.scope.subject,self.op.confirmation_digest,'PRIVATE_ORIGINAL_INVOCATION','scope_digest','receipt_bytes','manifest','journal','confirmation_digest'):
            self.assertNotIn(secret.encode(),raw)
        self.assertEqual(self.before(),before)

    def test_inflight_query_does_not_recover_write(self):
        self.op=self.writer.intent(self.op.operation_id,0,'auth_revocation','original')
        before=self.before();value=json.loads(self.read())
        self.assertEqual(value['steps'][0]['state'],'in_progress')
        self.assertEqual(value['revision'],self.op.revision)
        self.assertNotEqual(value['status'],'complete')
        self.assertEqual(self.before(),before)

    def test_missing_or_other_account_never_becomes_empty_complete(self):
        with self.assertRaises(core.Denied): self.reader.read(self.token,'missing-operation')
        self.verifier.principal=replace(self.principal,subject='other-account')
        with self.assertRaises(core.Denied): self.read()

    def test_denied_unknown_or_postlogout_cannot_obtain_progress(self):
        for state in (VerificationStatus.INVALID,VerificationStatus.UNKNOWN):
            self.verifier.status=state
            with self.assertRaises(ReadAdmissionFailure): self.read()
        self.assertEqual(self.resolutions,0)
        with self.assertRaises(ProgressUnavailable): post_logout_query(self.op.operation_id)
        with self.assertRaises(core.Denied): core.public_query(self.op.operation_id)

    def test_missing_hooks_and_retention_not_reported_cleaned(self):
        principal=replace(self.principal,subject=self.principal.subject+'-blocked')
        scope=core.Scope.from_principal('synthetic',principal)
        op=core.request(scope,'blocked-op',core.digest(b'confirmation'),self.f.manifest)
        Repository(self.admin,scope,lambda s:None).create(op)
        self.verifier.principal=principal
        value=json.loads(self.reader.read(self.token,'blocked-op'))
        self.assertEqual(value['status'],'blocked')
        self.assertIn('hook_unavailable',value['reasons'])
        self.assertTrue(all(x['state']=='pending' for x in value['steps']))
        self.assertTrue(any(x['target']=='offline_devices' for x in value['steps']))

    def test_illegal_persisted_target_never_returned(self):
        # journal and state agree; only the persisted registry ID is not a bounded ID.
        principal=replace(self.principal,subject=self.principal.subject+'-target')
        scope=core.Scope.from_principal('synthetic',principal)
        m=self.f.manifest
        for bad in ('PRIVATE_BODY\ncustomer note','x'*200):
            with self.subTest(bad=bad[:20]):
                manifest=replace(m,entries=(replace(m.entries[0],registry_id=bad),)+m.entries[1:])
                op=core.request(scope,'target-op-'+str(len(bad)),core.digest(b'confirmation'),manifest)
                Repository(self.admin,scope,lambda s:None).create(op)
                self.verifier.principal=principal
                with self.assertRaises(ProgressUnavailable):self.reader.read(self.token,op.operation_id)
                with psycopg.connect(**ADMIN) as conn:
                    conn.execute('DELETE FROM cj_cleanup_journal_candidate WHERE operation_id=%s',(op.operation_id,))

    def test_non_bool_persisted_hook_available_never_returned(self):
        # Legal target, journal and state agree; only persisted hook_available is not a bool.
        principal=replace(self.principal,subject=self.principal.subject+'-available')
        scope=core.Scope.from_principal('synthetic',principal)
        m=self.f.manifest
        target='store:'+m.entries[0].registry_id
        for index,(bad,capabilities) in enumerate(((None,()),('yes',()),('yes',(target,)),(0,()))):
            with self.subTest(bad=bad,capabilities=capabilities):
                manifest=replace(m,entries=(replace(m.entries[0],hook_available=bad),)+m.entries[1:])
                op=core.request(scope,'available-op-'+str(index),core.digest(b'confirmation'),manifest,capabilities)
                Repository(self.admin,scope,lambda s:None).create(op)
                self.verifier.principal=principal
                try:
                    with self.assertRaises(ProgressUnavailable):self.reader.read(self.token,op.operation_id)
                finally:
                    with psycopg.connect(**ADMIN) as conn:
                        conn.execute('DELETE FROM cj_cleanup_journal_candidate WHERE operation_id=%s',(op.operation_id,))

    def test_scope_cannot_come_from_resolver_or_request(self):
        def wrong(p,e,g): return Repository(self.connection,replace(self.scope,subject='other'),g)
        self.reader.resolve_repository=wrong
        with self.assertRaises(ProgressUnavailable): self.read()
        self.reader.resolve_repository=self.resolver
        with self.assertRaises(TypeError): self.reader.read(self.token,self.op.operation_id,scope=self.scope)

    def test_close_callback_revocation_close_ack_and_cancellation_withhold_bytes(self):
        def revoked(): self.access.invited=Fact.NO
        def ack(): raise RuntimeError('PRIVATE_CLOSE_ERROR')
        def cancel(): raise asyncio.CancelledError()
        for callback in (revoked,ack,cancel):
            self.access.invited=Fact.YES
            self.connection=lambda:Close(psycopg.connect(**READ),callback)
            with self.assertRaises((Unavailable,ReadAdmissionFailure,ReadContextViolation,asyncio.CancelledError)):
                self.read()

    def test_projection_executes_in_auth_lifetime_and_can_revoke(self):
        def project(raw): self.access.invited=Fact.NO;return b'{"envelope":'+raw+b'}'
        with self.assertRaises(ReadAdmissionFailure): self.read(project=project)
        self.access.invited=Fact.YES
        value=json.loads(self.read(project=lambda raw:b'{"envelope":'+raw+b'}'))
        self.assertEqual(value['envelope']['operation_id'],self.op.operation_id)

    def test_response_and_step_bounds_withhold_whole_result(self):
        self.reader.configuration=replace(self.config,max_steps=1)
        with self.assertRaises(ProgressUnavailable): self.read()
        self.reader.configuration=replace(self.config,max_response_bytes=1)
        with self.assertRaises(ProgressUnavailable): self.read()
        self.reader.configuration=self.config
        for result in (None,bytearray(b'private'),iter([b'private'])):
            with self.assertRaises(ProgressUnavailable): self.read(project=lambda raw:result)

    def test_primary_projection_commitunknown_is_preserved(self):
        def original(raw): raise CommitUnknown('query original operation; do not retry hook')
        with self.assertRaises(CommitUnknown): self.read(project=original)
