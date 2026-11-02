"""CLEANUP@1.0 private PG intent/result storage. No implicit dispatch or retries."""
from contextlib import contextmanager
import json
import psycopg
from psycopg.pq import TransactionStatus

from .core import Conflict, Denied, Invalid, encode, hash_value, identifier, digest
from .hooks import HookRequest, HookReceipt, make_receipt
from . import hooks, hooks_v1_1
from cj_strict_json import reject_duplicates
from .registry import freeze
from .postgres import CommitUnknown, Unavailable


CODECS={hooks.VERSION:hooks,hooks_v1_1.VERSION:hooks_v1_1}


def receipt_for(request,outcome):
    return CODECS[request.protocol].make_receipt(request,outcome)


def _receipt(raw, request_digest, protocol):
    # The same frozen receipt validator; a reconstructed request would be false evidence.
    return CODECS[protocol].HookReceipt.from_digest(raw, request_digest)


def original_result(cursor, request: HookRequest):
    """Public owner hook helper. Absence grants no permission to retry execute."""
    cursor.execute('SELECT request_digest,receipt_bytes FROM cj_cleanup_domain_result WHERE subject_digest=%s AND operation_id=%s AND invocation_id=%s',
                   (request.subject_digest,request.operation_id,request.invocation_id))
    row=cursor.fetchone()
    if row is None:return None
    if row[0]!=request.digest:raise Conflict('original invocation conflict')
    return _receipt(bytes(row[1]),request.digest,request.protocol)


def record_result(cursor, request: HookRequest, outcome: str):
    """Call in the SAME transaction as the owner's verified deletion/fence.

    Do not persist unknown as a final domain result; retain original intent instead.
    """
    if outcome not in ('confirmed','failed'):raise Invalid('durable final result required')
    result=receipt_for(request,outcome)
    cursor.execute('INSERT INTO cj_cleanup_domain_result(subject_digest,operation_id,invocation_id,request_digest,receipt_bytes) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
        (request.subject_digest,request.operation_id,request.invocation_id,request.digest,result.original_utf8))
    old=original_result(cursor,request)
    if old.original_utf8!=result.original_utf8:raise Conflict('original result conflict')
    return old


def _load_operation(cur,subject_digest,operation_id,*,lock_mode=None):
    cur.execute('SELECT confirmation_digest,purpose,registry_bytes,inventory,blocked,plan_bytes,plan_digest,protocol_versions,targets FROM cj_cleanup_operation WHERE subject_digest=%s AND operation_id=%s'+({None:'','update':' FOR UPDATE','share':' FOR SHARE'}[lock_mode]),
                (subject_digest,operation_id))
    row=cur.fetchone()
    if row is None:raise Denied('operation unavailable')
    confirmation,purpose,raw,inventory,blocked,plan_raw,plan_digest,versions,targets=row
    hash_value(confirmation)
    if purpose not in ('account','memory','diagnostics') or type(blocked) is not bool or type(inventory) is not list or type(versions) is not list or type(targets) is not list:
        raise Unavailable('cleanup state unavailable')
    manifest=freeze(bytes(raw),tuple(inventory),versions=tuple(versions))
    targets=tuple(identifier(t) for t in targets)
    if not targets or len(set(targets))!=len(targets) or set(targets)-set(manifest.inventory):raise Unavailable('cleanup targets unavailable')
    if plan_raw is None:plan=None
    else:
        plan_raw=bytes(plan_raw)
        if digest(plan_raw)!=plan_digest:raise Unavailable('cleanup plan unavailable')
        try:
            plan=json.loads(plan_raw.decode('utf-8'),object_pairs_hook=reject_duplicates(Invalid,'duplicate cleanup plan'))
            if type(plan) is not dict:raise Invalid('invalid cleanup plan')
        except (ValueError,UnicodeError,RecursionError):raise Unavailable('cleanup plan unavailable') from None
    return purpose,manifest,blocked,plan,targets


def require_account_retirement(cursor,request:HookRequest) -> None:
    """CLEANUP-ACCOUNT-RETIREMENT@1, after require_intent in the same Store tx.

    Only the original irreversible account fence is asserted. This is neither
    a domain-scope grant nor erasure evidence, and performs no write or dispatch.
    """
    if request.selection.kind!='account':raise Denied('account revocation unconfirmed')
    cursor.execute('SELECT 1 FROM cj_account_fence WHERE subject_digest=%s AND operation_id=%s',
                   (request.subject_digest,request.operation_id))
    if cursor.fetchone() is None:raise Denied('account revocation unconfirmed')


def require_intent(cursor,request:HookRequest) -> None:
    """Read-only owner seam, in the SAME transaction before domain deletion.

    Only SELECTs with parent/step SHARE locks: never create an intent, write state,
    dispatch or retry. Host has already bound its dedicated connection and scope.
    Query original_result first for an already committed owner result; reconcile
    remains a separate read and cannot obtain execution permission from UNKNOWN.
    """
    purpose,manifest,blocked,plan,targets=_load_operation(cursor,request.subject_digest,
        request.operation_id,lock_mode='share')
    entry=next((e for e in manifest.entries if e.registry_id==request.target),None)
    if (blocked or manifest.gaps or plan is None or request.target not in targets
            or entry is None or not entry.hook_available
            or (purpose,manifest.digest,entry.version,entry.protocol)!=(request.selection.kind,
                request.registry_digest,request.entry_digest,request.protocol)
            or plan.get(request.target)!={'domain_scope':request.domain_scope,'selection':request.selection.to_dict()}):
        raise Denied('original cleanup intent unavailable')
    cursor.execute('SELECT invocation_id,request_digest,request_bytes,state FROM cj_cleanup_step '
        'WHERE subject_digest=%s AND operation_id=%s AND target=%s FOR SHARE',
        (request.subject_digest,request.operation_id,request.target))
    row=cursor.fetchone()
    if (row is None or row[0]!=request.invocation_id or row[1]!=request.digest
            or row[2] is None or bytes(row[2])!=request.original_utf8 or row[3]!='in_progress'):
        raise Denied('original cleanup intent unavailable')


class Store:
    def __init__(self, connect, subject_digest: str, guard):
        self.connect,self.subject_digest,self.guard=connect,hash_value(subject_digest),guard

    @contextmanager
    def transaction(self, operation_id, *, writing=True):
        identifier(operation_id)
        conn=self.connect()
        started=failed=False
        try:
            if conn.autocommit or conn.info.transaction_status != TransactionStatus.IDLE:
                raise Unavailable('fresh cleanup connection required')
            with conn.cursor() as cur:
                cur.execute('SELECT current_user')
                if cur.fetchone()!=('cj_local_cleanup',):raise Denied('dedicated cleanup role required')
                cur.execute("SELECT set_config('cj.cleanup_subject',%s,true),set_config('cj.cleanup_operation',%s,true)",
                            (self.subject_digest,operation_id))
                self.guard('transaction')
                yield cur
                self.guard('commit')
                started=True
                conn.commit()
        except BaseException:
            failed=True
            if not started:
                try:conn.rollback()
                except psycopg.Error:pass
            if started and writing:raise CommitUnknown('query original cleanup operation') from None
            raise
        finally:
            try:conn.close()
            except BaseException:
                if not failed:
                    if started and writing:raise CommitUnknown('query original cleanup operation') from None
                    raise Unavailable('cleanup connection unavailable') from None
            if not failed:
                try:self.guard('return')
                except BaseException:
                    if started and writing:raise CommitUnknown('query original cleanup operation') from None
                    raise

    def _load(self,cur,operation_id,*,lock=False):
        return _load_operation(cur,self.subject_digest,operation_id,lock_mode='update' if lock else None)

    def create(self,operation_id,confirmation_digest,manifest,purpose,capabilities,plan):
        identifier(operation_id);hash_value(confirmation_digest)
        if purpose not in ('account','memory','diagnostics'):raise Invalid('invalid cleanup purpose')
        targets=manifest.inventory if purpose=='account' else tuple(sorted(plan))
        if not targets:raise Invalid('explicit cleanup targets required')
        blocked=bool(manifest.gaps) or any(not e.hook_available or e.registry_id not in capabilities or e.registry_id not in plan for e in manifest.entries if e.registry_id in targets)
        if set(plan)-set(manifest.inventory):raise Invalid('unregistered selection')
        plan_raw=encode(plan)
        with self.transaction(operation_id) as cur:
            cur.execute('INSERT INTO cj_cleanup_operation(subject_digest,operation_id,confirmation_digest,purpose,registry_bytes,inventory,blocked,plan_digest,plan_bytes,protocol_versions,targets) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING',
                (self.subject_digest,operation_id,confirmation_digest,purpose,manifest.raw,json.dumps(manifest.inventory),blocked,digest(plan_raw),plan_raw,json.dumps(manifest.versions),json.dumps(targets)))
            loaded,old,_,_,old_targets=self._load(cur,operation_id,lock=True)
            cur.execute('SELECT confirmation_digest,plan_digest FROM cj_cleanup_operation WHERE subject_digest=%s AND operation_id=%s',(self.subject_digest,operation_id))
            if (loaded,old.raw,old.inventory,old.versions,old_targets,cur.fetchone())!=(purpose,manifest.raw,manifest.inventory,manifest.versions,targets,(confirmation_digest,digest(plan_raw))):
                raise Conflict('cleanup confirmation conflict')

    def audit(self,operation_id,current):
        with self.transaction(operation_id) as cur:
            _,old,_,_,_=self._load(cur,operation_id,lock=True)
            if (old.raw,old.inventory,old.versions)!=(current.raw,current.inventory,current.versions):
                cur.execute('UPDATE cj_cleanup_operation SET blocked=true WHERE subject_digest=%s AND operation_id=%s',(self.subject_digest,operation_id))

    def query(self,operation_id):
        with self.transaction(operation_id,writing=False) as cur:
            return self.read_progress(cur,operation_id)

    def read_progress(self,cur,operation_id):
        _,manifest,blocked,_,targets=self._load(cur,operation_id)
        cur.execute('SELECT target,state FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s',(self.subject_digest,operation_id))
        states=dict(cur.fetchall())
        if any(k not in targets or v not in ('in_progress','unknown','failed','confirmed') for k,v in states.items()):
            raise Unavailable('cleanup state unavailable')
        steps=tuple(dict(target=target,state=states.get(target,'pending')) for target in targets)
        status=('blocked' if blocked else 'unknown' if 'unknown' in states.values() else 'failed' if 'failed' in states.values()
                else 'complete' if len(states)==len(steps) and all(v=='confirmed' for v in states.values()) else 'in_progress')
        value=dict(operation_id=operation_id,status=status,steps=steps)
        return value

    def intent(self,request:HookRequest):
        if request.subject_digest!=self.subject_digest:raise Denied('operation unavailable')
        with self.transaction(request.operation_id) as cur:
            purpose,manifest,blocked,plan,targets=self._load(cur,request.operation_id,lock=True)
            entry=next((e for e in manifest.entries if e.registry_id==request.target),None)
            if blocked or entry is None or not entry.hook_available or request.target not in targets:raise Denied('cleanup hook unavailable')
            if (purpose,manifest.digest,entry.version)!=(request.selection.kind,request.registry_digest,request.entry_digest):
                raise Conflict('cleanup request binding mismatch')
            if entry.protocol!=request.protocol:raise Conflict('cleanup protocol mismatch')
            cur.execute('SELECT invocation_id,request_digest FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND target=%s',
                        (self.subject_digest,request.operation_id,request.target))
            old=cur.fetchone()
            if old is not None:
                if old!=(request.invocation_id,request.digest):raise Conflict('original cleanup invocation required')
                return False
            if plan is None or plan.get(request.target)!={'domain_scope':request.domain_scope,'selection':request.selection.to_dict()}:
                raise Conflict('confirmed cleanup selection mismatch')
            cur.execute('INSERT INTO cj_cleanup_step(subject_digest,operation_id,target,invocation_id,request_digest,request_bytes,state) VALUES(%s,%s,%s,%s,%s,%s,\'in_progress\') ON CONFLICT DO NOTHING RETURNING target',
                (self.subject_digest,request.operation_id,request.target,request.invocation_id,request.digest,request.original_utf8))
            created=cur.fetchone() is not None
            cur.execute('SELECT invocation_id,request_digest FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND target=%s',
                        (self.subject_digest,request.operation_id,request.target))
            if cur.fetchone()!=(request.invocation_id,request.digest):raise Conflict('original cleanup invocation required')
        return created

    def receipt(self,request,result):
        result=CODECS[request.protocol].HookReceipt.from_bytes(result.original_utf8,request)
        with self.transaction(request.operation_id) as cur:
            _,manifest,_,_,_=self._load(cur,request.operation_id,lock=True)
            if next(e.protocol for e in manifest.entries if e.registry_id==request.target)!=request.protocol:
                raise Conflict('cleanup protocol mismatch')
            cur.execute('SELECT invocation_id,request_digest,state,receipt_bytes FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND target=%s FOR UPDATE',
                (self.subject_digest,request.operation_id,request.target))
            row=cur.fetchone()
            if row is None or row[:2]!=(request.invocation_id,request.digest):raise Conflict('original cleanup invocation required')
            if row[2] in ('confirmed','failed'):
                if bytes(row[3])!=result.original_utf8:raise Conflict('terminal cleanup result conflict')
            else:
                cur.execute('UPDATE cj_cleanup_step SET state=%s,receipt_bytes=%s WHERE subject_digest=%s AND operation_id=%s AND target=%s',
                    (result.outcome,result.original_utf8,self.subject_digest,request.operation_id,request.target))

    def recover(self,operation_id):
        """Explicit lost-writer recovery: no hook call or delete; actual result wins."""
        with self.transaction(operation_id) as cur:
            _,manifest,_,_,_=self._load(cur,operation_id,lock=True)
            cur.execute('SELECT target,invocation_id,request_digest FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND state IN (\'in_progress\',\'unknown\') FOR UPDATE',
                        (self.subject_digest,operation_id))
            for target,invocation,request_digest in cur.fetchall():
                cur.execute('SELECT request_digest,receipt_bytes FROM cj_cleanup_domain_result WHERE subject_digest=%s AND operation_id=%s AND invocation_id=%s',
                            (self.subject_digest,operation_id,invocation))
                row=cur.fetchone()
                if row is None:state,raw='unknown',None
                else:
                    if row[0]!=request_digest:raise Conflict('original result binding mismatch')
                    protocol=next(e.protocol for e in manifest.entries if e.registry_id==target)
                    value=_receipt(bytes(row[1]),request_digest,protocol);state,raw=value.outcome,value.original_utf8
                cur.execute('UPDATE cj_cleanup_step SET state=%s,receipt_bytes=%s WHERE subject_digest=%s AND operation_id=%s AND target=%s',
                            (state,raw,self.subject_digest,operation_id,target))
