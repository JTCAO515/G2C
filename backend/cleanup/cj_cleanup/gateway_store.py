"""Original HTTP operation/device metadata; all identities are host-bound digests."""
from dataclasses import dataclass
import json,uuid
from .core import Conflict,Denied,digest,encode,identifier


@dataclass(frozen=True,repr=False)
class Prepared:
    operation_id:str
    action_id:str
    registry_bytes:bytes
    inventory:tuple[str,...]
    plan_bytes:bytes|None
    plan_digest:str
    binding_id:str
    phase:str
    confirmation_digest:str|None
    revision:int


class GatewayStore:
    def __init__(self,store):self.store=store

    def lock_subject(self,cur):
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,27))',(self.store.subject_digest,))

    def _load(self,cur,operation_id,*,lock=False,share=False):
        cur.execute('SELECT operation_id,action_id,registry_bytes,inventory,plan_bytes,plan_digest,binding_id,phase,confirmation_digest,revision '
            'FROM cj_cleanup_request WHERE subject_digest=%s AND operation_id=%s'+(' FOR UPDATE' if lock else ' FOR SHARE' if share else ''),
            (self.store.subject_digest,operation_id))
        row=cur.fetchone()
        if row is None:raise Denied('cleanup operation unavailable')
        return Prepared(row[0],row[1],bytes(row[2]),tuple(row[3]),bytes(row[4]) if row[4] is not None else None,*row[5:])

    def query(self,operation_id):
        with self.store.transaction(operation_id,writing=False) as cur:
            result=self._load(cur,operation_id)
        return result

    def snapshot(self,operation_id):
        with self.store.transaction(operation_id,writing=False) as cur:
            prepared=self._load(cur,operation_id,share=True)
            progress=None if prepared.phase=='prepared' else self.store.read_progress(cur,operation_id)
            cur.execute('SELECT binding_id,invocation_id,state FROM cj_cleanup_device_call WHERE subject_digest=%s AND operation_id=%s ORDER BY binding_id',
                        (self.store.subject_digest,operation_id))
            devices=[dict(binding_id=b,invocation_id=i,state=s,provenance='authenticated_current_device_report') for b,i,s in cur.fetchall()]
        return prepared,progress,devices

    def by_action(self,action_id):
        with self.store.transaction('preparation-read',writing=False) as cur:
            cur.execute('SELECT operation_id FROM cj_cleanup_request WHERE subject_digest=%s AND action_id=%s',
                        (self.store.subject_digest,action_id))
            row=cur.fetchone()
            result=None if row is None else self._load(cur,row[0])
        return result

    def active_operation(self):
        with self.store.transaction('account-fence-read',writing=False) as cur:
            cur.execute('SELECT operation_id FROM cj_account_fence WHERE subject_digest=%s',(self.store.subject_digest,))
            row=cur.fetchone()
        return None if row is None else row[0]

    def register_device(self,action_id,input_digest,device_id,state_ref):
        identifier(action_id);identifier(device_id)
        with self.store.transaction('device-'+action_id) as cur:
            self.lock_subject(cur)
            cur.execute('SELECT 1 FROM cj_account_fence WHERE subject_digest=%s',(self.store.subject_digest,))
            if cur.fetchone() is not None:raise Denied('ordinary device registration unavailable')
            cur.execute('INSERT INTO cj_cleanup_device_binding(subject_digest,binding_id,action_id,input_digest,device_id,state_ref,scope_digest) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(subject_digest,action_id) DO NOTHING',
                (self.store.subject_digest,str(uuid.uuid4()),action_id,input_digest,device_id,state_ref,self.store.subject_digest))
            cur.execute('SELECT binding_id,input_digest,device_id,state_ref,scope_digest FROM cj_cleanup_device_binding '
                        'WHERE subject_digest=%s AND action_id=%s',(self.store.subject_digest,action_id))
            row=cur.fetchone()
            if row[1]!=input_digest:raise Conflict('original device registration required')
            result=dict(binding_id=row[0],device_id=row[2],state_ref=row[3],scope_digest=row[4])
        return result

    def device(self,binding_id):
        with self.store.transaction('device-read',writing=False) as cur:
            cur.execute('SELECT binding_id,device_id,state_ref,scope_digest FROM cj_cleanup_device_binding WHERE subject_digest=%s AND binding_id=%s',
                        (self.store.subject_digest,binding_id))
            row=cur.fetchone()
            if row is None:raise Denied('device binding unavailable')
            result=dict(binding_id=row[0],device_id=row[1],state_ref=row[2],scope_digest=row[3])
        return result

    def devices(self):
        with self.store.transaction('device-list',writing=False) as cur:
            cur.execute('SELECT binding_id FROM cj_cleanup_device_binding WHERE subject_digest=%s ORDER BY binding_id',(self.store.subject_digest,))
            return tuple(row[0] for row in cur.fetchall())

    def prepare(self,action_id,input_digest,manifest,plan,binding_id):
        identifier(action_id)
        with self.store.transaction('prepare-'+action_id) as cur:
            self.lock_subject(cur)
            cur.execute('SELECT 1 FROM cj_account_fence WHERE subject_digest=%s',(self.store.subject_digest,))
            if cur.fetchone() is not None:raise Denied('query original operation only')
            cur.execute('SELECT 1 FROM cj_cleanup_device_binding WHERE subject_digest=%s AND binding_id=%s',
                        (self.store.subject_digest,binding_id))
            if cur.fetchone() is None:raise Denied('device binding unavailable')
            raw=encode(plan)
            cur.execute("INSERT INTO cj_cleanup_request(subject_digest,operation_id,action_id,input_digest,registry_bytes,inventory,plan_bytes,plan_digest,binding_id,phase) "
                "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,'prepared') ON CONFLICT(subject_digest,action_id) DO NOTHING",
                (self.store.subject_digest,str(uuid.uuid4()),action_id,input_digest,manifest.raw,json.dumps(manifest.inventory),raw,digest(raw),binding_id))
            cur.execute('SELECT operation_id,input_digest FROM cj_cleanup_request WHERE subject_digest=%s AND action_id=%s',
                        (self.store.subject_digest,action_id))
            row=cur.fetchone()
            if row[1]!=input_digest:raise Conflict('original preparation bytes required')
            result=self._load(cur,row[0],lock=True)
        return result

    def confirm(self,operation_id,confirmation_digest,current,*,owner_scope,namespaces,check_admission):
        with self.store.transaction(operation_id) as cur:
            self.lock_subject(cur)
            current_op=self._load(cur,operation_id,lock=True)
            check_admission()
            cur.execute('SELECT operation_id FROM cj_account_fence WHERE subject_digest=%s',(self.store.subject_digest,))
            if cur.fetchone() is not None:raise Denied('query original operation only')
            if current_op.phase!='prepared' or current_op.registry_bytes!=current.raw:
                raise Conflict('cleanup scope changed; original preparation cannot be expanded')
            cur.execute('SELECT confirmation_digest FROM cj_cleanup_operation WHERE subject_digest=%s AND operation_id=%s',
                        (self.store.subject_digest,operation_id))
            original=cur.fetchone()
            if original!=(confirmation_digest,):raise Conflict('original confirmed operation required')
            cur.execute('INSERT INTO cj_account_fence(subject_digest,owner_digest,operation_id,namespace_digests) VALUES(%s,%s,%s,%s::jsonb)',
                (self.store.subject_digest,digest(owner_scope.encode('utf-8')),operation_id,json.dumps(sorted({digest(s.encode('utf-8')) for s in namespaces}))))
            cur.execute("UPDATE cj_cleanup_request SET phase='confirmed',confirmation_digest=%s,revision=revision+1 WHERE subject_digest=%s AND operation_id=%s",
                        (confirmation_digest,self.store.subject_digest,operation_id))
        return self.query(operation_id)
