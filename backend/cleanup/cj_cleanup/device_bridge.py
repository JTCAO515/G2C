"""CLEANUP-DEVICE@1 original invocation bridge; no device filesystem code here."""
import json,uuid
from .core import Conflict,Denied,digest,encode

VERSION='CLEANUP-DEVICE@1'
TARGETS=('device-cache/encrypted-message-file','device-cache/sdk-session-keychain',
         'device-cache/message-key-keychain','device-cache/trip-pending-file','device-cache/offline-trip',
         'device-cache/feedback-pending','device-cache/feedback-key-keychain')


class DeviceBridge:
    def __init__(self,gateway,issuer):self.gateway,self.store,self.issuer=gateway,gateway.store,issuer

    def call(self,binding_id,reason,*,operation_id=None):
        if reason not in ('account_cleanup','session_invalid','offline_expired'):
            raise Denied('device cleanup reason unavailable')
        binding=self.gateway.device(binding_id)
        active=self.gateway.active_operation()
        if active is not None:
            if operation_id is not None and operation_id!=active:raise Denied('original operation required')
            operation_id=active;reason='account_cleanup'
        elif reason=='account_cleanup':raise Denied('account operation unavailable')
        elif operation_id is not None:raise Denied('device operation ID is server-owned')
        elif operation_id is None:
            # Stable invalidation operation for this binding/state/reason. No UI ID.
            operation_id='device-'+digest(encode([binding_id,binding['state_ref'],reason]))
        invocation='device-'+digest(encode([operation_id,binding_id,reason]))
        targets=TARGETS if reason!='offline_expired' else ('device-cache/offline-trip',)
        request=encode(dict(version=VERSION,operation_id=operation_id,invocation_id=invocation,
            binding_id=binding_id,scope_digest=binding['scope_digest'],state_ref=binding['state_ref'],
            reason=reason,targets=targets,business_access='not_granted'))
        with self.store.transaction(operation_id) as cur:
            cur.execute('INSERT INTO cj_cleanup_device_call(subject_digest,operation_id,invocation_id,binding_id,reason,request_digest,request_bytes) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(operation_id,binding_id,reason) DO NOTHING',
                (self.store.subject_digest,operation_id,invocation,binding_id,reason,digest(request),request))
            cur.execute('SELECT request_bytes FROM cj_cleanup_device_call WHERE subject_digest=%s AND invocation_id=%s',
                        (self.store.subject_digest,invocation))
            if bytes(cur.fetchone()[0])!=request:raise Conflict('original device invocation conflict')
        return self.query(invocation,binding_id)

    def query(self,invocation_id,binding_id):
        with self.store.transaction('device-call-read',writing=False) as cur:
            cur.execute('SELECT operation_id,request_bytes,request_digest,state,receipt_digest FROM cj_cleanup_device_call '
                'WHERE subject_digest=%s AND invocation_id=%s AND binding_id=%s',
                (self.store.subject_digest,invocation_id,binding_id))
            row=cur.fetchone()
            if row is None:raise Denied('device invocation unavailable')
            original=bytes(row[1])
            if digest(original)!=row[2]:raise Denied('device invocation unavailable')
            request=json.loads(original)
            result=dict(call=request,request_digest=row[2],state=row[3],receipt_digest=row[4],
                receipt_token=self.issuer.issue(subject_digest=self.store.subject_digest,operation_id=row[0],
                    binding_id=binding_id,purpose='device_receipt',invocation_id=invocation_id))
        return result

    def receipt(self,claims,action_id,request_digest,outcome,raw):
        if claims.subject_digest!=self.store.subject_digest or outcome not in ('confirmed','unknown','failed'):
            raise Denied('device receipt unavailable')
        with self.store.transaction(claims.operation_id) as cur:
            cur.execute('SELECT request_digest,state,receipt_digest FROM cj_cleanup_device_call WHERE subject_digest=%s '
                'AND operation_id=%s AND invocation_id=%s AND binding_id=%s FOR UPDATE',
                (self.store.subject_digest,claims.operation_id,claims.invocation_id,claims.binding_id))
            row=cur.fetchone()
            if row is None or row[0]!=request_digest:raise Denied('original device invocation required')
            receipt_digest=digest(raw)
            if row[1] in ('confirmed','failed'):
                if row[2]!=receipt_digest:raise Conflict('terminal original device receipt conflict')
            else:
                cur.execute('UPDATE cj_cleanup_device_call SET state=%s,receipt_action_id=%s,receipt_digest=%s,receipt_bytes=%s,received_at=clock_timestamp() '
                    'WHERE subject_digest=%s AND invocation_id=%s',
                    (outcome,action_id,receipt_digest,raw,self.store.subject_digest,claims.invocation_id))
        return self.query(claims.invocation_id,claims.binding_id)

    def summary(self,operation_id):
        with self.store.transaction(operation_id,writing=False) as cur:
            cur.execute('SELECT binding_id,invocation_id,state FROM cj_cleanup_device_call WHERE subject_digest=%s AND operation_id=%s ORDER BY binding_id',
                        (self.store.subject_digest,operation_id))
            rows=cur.fetchall()
        return [dict(binding_id=b,invocation_id=i,state=s,provenance='authenticated_current_device_report') for b,i,s in rows]


class DeviceHook:
    """One frozen target across the account's registered original device bindings."""
    def __init__(self,gateway,issuer):self.gateway,self.issuer=gateway,issuer

    def execute(self,request):
        from .store import require_intent,original_result,record_result,receipt_for
        if request.subject_digest!=self.gateway.store.subject_digest or request.domain_scope!=request.subject_digest or request.selection.kind!='account':
            raise Denied('original device domain unavailable')
        with self.gateway.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
        bridge=DeviceBridge(self.gateway,self.issuer)
        bindings=self.gateway.devices()
        if not bindings:raise Denied('actual device binding required')
        results=[bridge.call(binding,'account_cleanup',operation_id=request.operation_id) for binding in bindings]
        if not all(r['state']=='confirmed' for r in results):return receipt_for(request,'unknown')
        with self.gateway.store.transaction(request.operation_id) as cur:
            # The accepted authenticated original reports are the owner's results,
            # not a claim of remote physical verification or any unregistered device.
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        from .store import original_result,record_result,receipt_for
        with self.gateway.store.transaction(request.operation_id,writing=False) as cur:
            old=original_result(cur,request)
            if old is not None:return old
        rows=DeviceBridge(self.gateway,self.issuer).summary(request.operation_id)
        expected=set(self.gateway.devices())
        if not expected or {r['binding_id'] for r in rows}!=expected or any(r['state']!='confirmed' for r in rows):
            return receipt_for(request,'unknown')
        with self.gateway.store.transaction(request.operation_id) as cur:return record_result(cur,request,'confirmed')
