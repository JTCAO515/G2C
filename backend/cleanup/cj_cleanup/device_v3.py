"""CLEANUP-DEVICE@3: atomic client action→server call, read-only first-ACK recovery."""
from .core import Conflict,Denied,digest
from .device_bridge import DeviceBridge,original_call,persist_call
from .device_v2 import TARGETS as V2_TARGETS

VERSION='CLEANUP-DEVICE@3'
TARGETS=V2_TARGETS+('device-cache/memory-history-pending','device-cache/trip-scoped-pending',
    'device-cache/needs-planning-pending','device-cache/trip-key-keychain',
    'device-cache/offline-key-keychain','device-cache/offline-write-residue')


class DeviceActions:
    version=VERSION
    def __init__(self,metadata,issuer):self.metadata,self.store,self.issuer=metadata,metadata.store,issuer

    def create(self,binding_id,reason,action_id,input_sha256):
        binding=self.metadata.device(binding_id)
        if binding['protocol']!=self.version or reason not in ('session_invalid','offline_expired'):
            raise Denied('original device binding/reason required')
        with self.store.transaction('device-action-'+digest(action_id.encode())) as cur:
            self.metadata.lock_subject(cur)
            cur.execute('SELECT input_digest,invocation_id,binding_id FROM cj_cleanup_device_action WHERE subject_digest=%s AND action_id=%s',
                        (self.store.subject_digest,action_id))
            row=cur.fetchone()
            if row is not None:
                if row[0]!=input_sha256 or row[2]!=binding_id:raise Conflict('original device action bytes required')
            else:
                cur.execute('SELECT operation_id FROM cj_account_fence WHERE subject_digest=%s',(self.store.subject_digest,))
                fence=cur.fetchone();active=None if fence is None else fence[0]
                operation,invocation,request=original_call(binding,active,reason)
                persist_call(cur,self.store.subject_digest,operation,invocation,binding_id,
                             'account_cleanup' if active is not None else reason,request)
                cur.execute('INSERT INTO cj_cleanup_device_action(subject_digest,action_id,input_digest,binding_id,invocation_id) VALUES(%s,%s,%s,%s,%s)',
                            (self.store.subject_digest,action_id,input_sha256,binding_id,invocation))
        return self.query(binding_id,action_id,input_sha256)

    def query(self,binding_id,action_id,input_sha256):
        with self.store.transaction('device-action-read',writing=False) as cur:
            cur.execute('SELECT input_digest,invocation_id,binding_id FROM cj_cleanup_device_action WHERE subject_digest=%s AND action_id=%s',
                        (self.store.subject_digest,action_id))
            row=cur.fetchone()
        if row is not None and row[2]!=binding_id:raise Denied('original device binding required')
        if row is not None and row[0]!=input_sha256:raise Conflict('original device action digest required')
        result=None if row is None else DeviceBridge(self.metadata,self.issuer).query(row[1],binding_id)
        return dict(version=self.version,action_id=action_id,input_sha256=input_sha256,invocation=result)
