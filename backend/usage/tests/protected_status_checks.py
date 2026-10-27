"""Working-tree AUTH + synthetic DB callbacks, no resource/service operations."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import unittest

USAGE=Path(__file__).resolve().parents[1]
# Working-tree AUTH (ADR-0004: the repository commit is the pin).
sys.path.insert(0,str(USAGE.parent/'auth'));sys.path.insert(0,str(USAGE));sys.path.insert(0,str(USAGE/'tests'))
# Load fixed package before storage helper adds its older sibling import path.
from cj_auth.read_context import ProtectedReadBoundary,ReadAdmissionFailure,ReadContextViolation
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import VerificationStatus,TrustedPrincipal
from cj_usage.protected_status import AttemptStatusReader,StatusReadConfiguration
from cj_usage.postgres import PostgresRepository,RepositoryUnavailable,CommitUnknown
from cj_usage.read_status import ReadUnavailable
import test_read_status as storage


class CompositionChecks(unittest.TestCase):
    def setUp(self):
        self.s=storage.ReadTests();self.s.setUp()
        self.resolutions=[];self.hook=None
        self.config=StatusReadConfiguration('synthetic-test','synthetic-issuer','synthetic-aud',0,1000,4096)
        self.boundary=ProtectedReadBoundary(self.s.checker,max_response_bytes=4096)
        def resolve(p,environment,start,end):
            self.resolutions.append((p,environment,start,end))
            if self.hook:self.hook()
            return self.s.repo
        self.reader=AttemptStatusReader(self.boundary,resolve,configuration=self.config)
    def read(self,**kwargs):return self.reader.read('synthetic-only','a',**kwargs)

    def test_actual_auth_and_storage_minimal_bytes(self):
        value=json.loads(self.read())
        self.assertEqual(value['status'],'unknown');self.assertIsNone(value['confirmed_units'])
        self.assertNotIn('input_digest',value)
        self.assertEqual(self.resolutions,[(self.s.p,'synthetic-test',0,1000)])
        sql=[x[0] for x in self.s.log if isinstance(x,tuple)]
        self.assertEqual(len(sql),2);self.assertTrue(sql[1].startswith('SELECT '))

    def test_no_current_admission_no_resolver_connection(self):
        self.s.allowed=False
        with self.assertRaises(ReadAdmissionFailure):self.read()
        self.assertEqual(self.resolutions,[]);self.assertEqual(self.s.log,[])

    def test_resolver_unknown_or_identity_switch_never_selects(self):
        for change in ('unknown','identity'):
            self.setUp()
            def mutate():
                if change=='unknown':self.s.allowed=False
                else:self.s.p=TrustedPrincipal('synthetic-issuer','other','synthetic-aud',0,0,1000)
            self.hook=mutate
            with self.assertRaises((ReadAdmissionFailure,ReadContextViolation)):self.read()
            self.assertNotIn('select',self.s.log)

    def test_resolver_missing_or_wrong_repo_no_fallback(self):
        for result in (None,object()):
            self.reader.resolve_repository=lambda *args:result
            with self.assertRaises(ReadUnavailable):self.read()

    def test_host_issuer_audience_period_config_failclosed(self):
        from dataclasses import replace
        for field,value in [('issuer','other'),('audience','other'),('period_end',1001)]:
            self.setUp();self.reader.configuration=replace(self.config,**{field:value})
            with self.assertRaises(ReadUnavailable):self.read()
        with self.assertRaises(ReadUnavailable):AttemptStatusReader(self.boundary,lambda *a:self.s.repo,configuration=None)

    def test_cross_scope_unavailable_not_zeros(self):
        self.s.row=None
        with self.assertRaises(RepositoryUnavailable):self.read()

    def test_all_storage_callbacks_and_last_close_revoke(self):
        for stage in ('cursor','set','select','fetch','commit','cursor_close','connection_close'):
            self.setUp();self.s.hooks[stage]=lambda:setattr(self.s,'allowed',False)
            with self.subTest(stage=stage),self.assertRaises(ReadAdmissionFailure):self.read()

    def test_projection_finishes_envelope_inside_context(self):
        self.assertIn('envelope',json.loads(self.read(project=lambda b:b'{"envelope":'+b+b'}')))
        def revoke(data):self.s.allowed=False;return data
        with self.assertRaises(ReadAdmissionFailure):self.read(project=revoke)

    def test_scope_change_after_projection_or_close(self):
        def change(data):self.s.repo.scope='other';return data
        with self.assertRaises(ReadUnavailable):self.read(project=change)
        self.setUp();self.s.hooks['connection_close']=lambda:setattr(self.s.repo,'scope','other')
        with self.assertRaises(ReadUnavailable):self.read()

    def test_read_commit_unknown_and_cleanup_error_keep_priority(self):
        self.s.errors['commit']=OSError('synthetic ACK lost')
        self.s.errors['connection_close']=RuntimeError('synthetic close')
        with self.assertRaises(CommitUnknown):self.read()
        self.setUp();self.s.errors['connection_close']=RuntimeError('synthetic close')
        with self.assertRaises(ReadUnavailable):self.read()

    def test_outer_auth_final_return_rechecks_after_domain_and_storage(self):
        original=self.s.checker._access
        s=self.s
        class FinalAccess:
            after_close=0
            def evaluate(self,p):
                if 'connection_close' in s.log:
                    self.after_close+=1
                    if self.after_close==3:s.allowed=False
                return original.evaluate(p)
        self.s.checker._access=FinalAccess()
        with self.assertRaises(ReadAdmissionFailure):self.read()
        self.assertEqual(self.s.checker._access.after_close,3)

    def test_last_auth_callback_scope_replacement_withholds(self):
        self._last_callback_rebind('scope')

    def test_last_auth_callback_configuration_replacement_withholds(self):
        self._last_callback_rebind('configuration')

    def _last_callback_rebind(self, kind):
        from dataclasses import replace
        original=self.s.checker._access
        owner=self
        class LastAccess:
            after_close=0
            def evaluate(self,p):
                if 'connection_close' in owner.s.log:
                    self.after_close+=1
                    if self.after_close==3:
                        if kind=='scope':owner.s.repo.scope='synthetic-replacement-scope'
                        else:owner.reader.configuration=replace(owner.config,environment='synthetic-replacement-environment')
                return original.evaluate(p)
        access=LastAccess();self.s.checker._access=access
        try:
            with self.assertRaises((ReadUnavailable,ReadContextViolation)):
                self.read()
        finally:
            self.assertEqual(access.after_close,3)

    def test_cancellation_and_reentry_withhold(self):
        def project(data):
            try:self.read()
            except ReadContextViolation:pass
            return data
        with self.assertRaises(ReadContextViolation):self.read(project=project)
        self.setUp();self.s.errors['fetch']=storage.Cancelled()
        with self.assertRaises(storage.Cancelled):self.read()

if __name__=='__main__':unittest.main(verbosity=2)
