import json
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from cj_auth.interfaces import TrustedPrincipal
from cj_cleanup.core import *

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ('business','business/message','business/usage','business/memory-authoritative',
 'business/trip-authoritative','business/needs-current-planning','business/feedback-private-actions',
 'business/cleanup-metadata','business/memory-management-actions',
 'checkpoints','checkpoints/run','memory-derived','device-cache','device-cache/encrypted-message-file',
 'device-cache/sdk-session-keychain','device-cache/message-key-keychain',
 'device-cache/trip-pending-file','external-processing')

class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.scope = Scope.from_principal('synthetic',TrustedPrincipal('issuer','A','aud',1,1,2))
        self.other = replace(self.scope,subject='B')
        self.manifest = freeze_registry((ROOT/'backend/storage-registry.json').read_bytes(),INVENTORY)
        self.repo = Repository()

    def op(self, synthetic=False, scope=None):
        m=self.manifest
        if synthetic: m=replace(m,entries=tuple(replace(e,hook_available=True) for e in m.entries))
        caps=tuple(BARRIERS)+tuple('store:'+e.registry_id for e in m.entries) if synthetic else ()
        op=request(scope or self.scope,'operation-1',digest(b'explicit confirmation'),m,caps)
        return self.repo.create(op)

    def result(self,op,step_target,outcome='confirmed',**overrides):
        s=next(s for s in op.steps if s.target==step_target)
        data=dict(protocol=VERSION,scope_digest=digest(encode(asdict(op.scope))),operation_id=op.operation_id,
                  target=step_target,version=s.version,invocation=s.invocation,outcome=outcome)
        data.update(overrides)
        return encode(data)

    def settle(self,op,target,outcome='confirmed'):
        op=self.repo.intent(op.scope,op.operation_id,op.revision,target,'call-'+str(op.revision))
        return self.repo.receipt(op.scope,op.operation_id,op.revision,target,self.result(op,target,outcome))

    def test_real_registry_never_empty_complete(self):
        op=self.op()
        self.assertEqual(op.status,'blocked')
        self.assertEqual(len(op.steps),len(INVENTORY)+len(BARRIERS))
        self.assertTrue(any(s.target=='store:business/trip-authoritative' for s in op.steps))
        self.assertTrue(any(s.target=='store:device-cache/trip-pending-file' for s in op.steps))
        with self.assertRaises(Denied): intent(op,'auth_revocation','call')

    def test_missing_manifest_or_inventory(self):
        for raw,inv in [(b'{}',INVENTORY),(b'{"version":"1","stores":[]}',INVENTORY),
                        ((ROOT/'backend/storage-registry.json').read_bytes(),())]:
            with self.assertRaises(Invalid): freeze_registry(raw,inv)

    def test_unregistered_domain(self):
        m=freeze_registry((ROOT/'backend/storage-registry.json').read_bytes(),INVENTORY+('new-domain',))
        self.assertEqual(request(self.scope,'o',digest(b'c'),m).status,'blocked')
        self.assertIn('unregistered:new-domain',m.gaps)

    def test_new_or_changed_registry_latches_gap(self):
        op=self.op(True)
        raw=json.loads((ROOT/'backend/storage-registry.json').read_bytes())
        raw['stores'].append(dict(id='new-domain',cleanup_hook='UNIMPLEMENTED'))
        changed=freeze_registry(encode(raw),INVENTORY)
        op=self.repo.audit(op.scope,op.operation_id,op.revision,changed)
        self.assertEqual(op.status,'blocked')
        op=self.repo.audit(op.scope,op.operation_id,op.revision,self.manifest)
        self.assertEqual(op.status,'blocked')

    def test_prerequisites(self):
        op=self.op(True)
        self.assertEqual(op.status,'awaiting_revocation')
        with self.assertRaises(Denied): intent(op,'tasks_stopped','call')
        op=self.settle(op,'auth_revocation')
        with self.assertRaises(Denied): intent(op,'store:business','call')

    def test_unknown_revocation_no_retry(self):
        op=self.settle(self.op(True),'auth_revocation','unknown')
        self.assertEqual(op.status,'unknown')
        with self.assertRaises(Conflict): intent(op,'auth_revocation','new-call')
        with self.assertRaises(Denied): intent(op,'tasks_stopped','call')
        op=self.repo.receipt(op.scope,op.operation_id,op.revision,'auth_revocation',self.result(op,'auth_revocation'))
        self.assertEqual(op.steps[0].state,'confirmed')

    def test_wrong_original_receipt_bindings(self):
        op=self.repo.intent(self.scope,'operation-1',self.op(True).revision,'auth_revocation','original')
        for changes in [dict(scope_digest='0'*64),dict(operation_id='other'),dict(version='old'),
                        dict(invocation='other'),dict(target='tasks_stopped')]:
            with self.assertRaises(Conflict): receipt(op,'auth_revocation',self.result(op,'auth_revocation',**changes))

    def test_duplicate_and_conflicting_bytes(self):
        op=self.settle(self.op(True),'auth_revocation')
        raw=op.steps[0].receipt_bytes
        self.assertIs(receipt(op,'auth_revocation',raw),op)
        with self.assertRaises(Conflict): receipt(op,'auth_revocation',raw+b' ')
        self.assertEqual(self.repo.create(request(self.scope,'operation-1',op.confirmation_digest,op.manifest)),op)
        with self.assertRaises(Conflict): self.repo.create(request(self.scope,'operation-1',digest(b'changed'),op.manifest))
        with self.assertRaises(Conflict): self.repo.create(request(self.scope,'new-op',op.confirmation_digest,op.manifest))

    def test_concurrent_cas(self):
        op=self.op(True)
        def run(n):
            try: return self.repo.intent(self.scope,op.operation_id,0,'auth_revocation','call-'+str(n))
            except Conflict: return None
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(run,range(2)))
        self.assertEqual(sum(x is not None for x in results),1)

    def test_crash_intent_unknown_rebuild(self):
        op=self.repo.intent(self.scope,'operation-1',self.op(True).revision,'auth_revocation','original')
        rebuilt=Repository.rebuild(self.repo.journal())
        op=rebuilt.query(self.scope,'operation-1')
        self.assertEqual(op.status,'unknown')
        self.assertEqual(op.steps[0].invocation,'original')
        with self.assertRaises(Conflict): rebuilt.intent(self.scope,'operation-1',op.revision,'auth_revocation','retry')
        raw=self.result(op,'auth_revocation')
        op=rebuilt.receipt(self.scope,'operation-1',op.revision,'auth_revocation',raw)
        again=Repository.rebuild(rebuilt.journal()).query(self.scope,'operation-1')
        self.assertEqual(again,op)
        self.assertEqual(again.steps[0].receipt_bytes,raw)

    def test_partial_failure_restart_never_resurrects(self):
        op=self.settle(self.op(True),'auth_revocation')
        op=self.settle(op,'tasks_stopped')
        op=self.settle(op,'store:business')
        op=self.settle(op,'store:business/message','failed')
        again=Repository.rebuild(self.repo.journal()).query(self.scope,'operation-1')
        self.assertEqual(again.status,'failed')
        self.assertEqual(next(s for s in again.steps if s.target=='store:business').state,'confirmed')
        with self.assertRaises(Conflict): intent(again,'store:business/message','retry')

    def test_retention_gaps_prevent_complete(self):
        op=self.op(True)
        for s in op.steps:
            if s.target not in ('backup_retention','offline_devices','external_retention'):
                op=self.settle(op,s.target)
        self.assertNotEqual(op.status,'complete')
        for t in ('backup_retention','offline_devices','external_retention'): op=self.settle(op,t)
        self.assertEqual(op.status,'complete') # synthetic exact manifest only
        self.assertEqual(Repository.rebuild(self.repo.journal()).query(self.scope,'operation-1'),op)

    def test_other_user_and_disabled_entries(self):
        op=self.op(True); b=self.op(True,self.other)
        self.settle(op,'auth_revocation')
        self.assertEqual(self.repo.query(self.other,'operation-1'),b)
        with self.assertRaises(Denied): self.repo.query(self.other,'missing')
        for f in (execute_destructive_action,public_query):
            with self.assertRaises(Denied): f()

    def test_sensitive_body_rejected_not_journaled(self):
        op=self.repo.intent(self.scope,'operation-1',self.op(True).revision,'auth_revocation','original')
        data=json.loads(self.result(op,'auth_revocation'));data['body']='PRIVATE_SECRET_BODY'
        with self.assertRaises(Invalid): self.repo.receipt(self.scope,'operation-1',op.revision,'auth_revocation',encode(data))
        self.assertNotIn(b'PRIVATE_SECRET_BODY',self.repo.journal())
        self.assertNotIn('subject',repr(op))
        with self.assertRaises(Invalid): Repository.rebuild(self.repo.journal()[:-1])

if __name__=='__main__': unittest.main()
