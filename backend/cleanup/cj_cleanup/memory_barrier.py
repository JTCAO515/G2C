"""B pre-dispatch worker/payload barrier for MEMORY-ERASURE-COMPOSITION@2."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import get_ident
from psycopg.pq import TransactionStatus
from .core import Denied,digest
from .store import require_plan
from cj_run.account_stop import worker_key
from cj_run.background_store import LEASE_NAMESPACE
from cj_memory_withdrawal.association_codec import parse_original

ACTIVE=ContextVar('memory_payload_barrier',default=None)


@dataclass
class Lease:
    subject:str
    operation:str
    scope:str
    association_sha256:str
    thread:int
    active:bool=True
    plan:object=None


def require_lease(request,scope,association_raw):
    lease=ACTIVE.get()
    if (lease is None or not lease.active or lease.thread!=get_ident()
        or (lease.subject,lease.operation,lease.scope,lease.association_sha256)!=
           (request.subject_digest,request.operation_id,scope,digest(association_raw))):
        raise Denied('original physical payload barrier unavailable')
    return lease


@contextmanager
def hold_payloads(store,scope,association_raw,prototype):
    if (prototype.subject_digest!=store.subject_digest or prototype.domain_scope!=scope
        or prototype.selection.kind!='memory' or prototype.protocol!='CLEANUP@1.1'
        or prototype.target not in ('business/message','checkpoints/run','business/usage')):
        raise Denied('original payload preflight binding unavailable')
    # Pure comparison data here. Private evidence is read only by an executing
    # hook after Coordinator durably commits that target's physical intent.
    parse_original(association_raw,prototype,scope)
    connection=store.connect();token=None;lease=None
    try:
        if connection.autocommit or connection.info.transaction_status!=TransactionStatus.IDLE:
            raise Denied('fresh payload barrier connection required')
        with connection.cursor() as cursor:
            if store.before_transaction is not None:store.before_transaction(cursor)
            cursor.execute('SELECT current_user')
            if cursor.fetchone()!=('cj_local_cleanup',):raise Denied('dedicated payload barrier role required')
            cursor.execute("SELECT set_config('cj.cleanup_subject',%s,true),set_config('cj.cleanup_operation',%s,true),"
                "set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','memory',true)",
                (store.subject_digest,prototype.operation_id,scope))
            store.guard('payload_preflight')
            require_plan(cursor,prototype)
            ready=cursor.execute('SELECT pg_try_advisory_lock(public.cj_payload_barrier_key(%s))',(scope,)).fetchone()[0]
            if ready:
                cursor.execute('SELECT conversation_id,generation FROM cj_message_chat WHERE scope=%s',(scope,))
                keys=[worker_key((scope,cid,generation)) for cid,generation in cursor.fetchall()]
                cursor.execute('SELECT run_id FROM cj_run_background_job WHERE scope=%s',(scope,))
                keys.extend(worker_key((scope,LEASE_NAMESPACE,run_id)) for (run_id,) in cursor.fetchall())
                for key in sorted(set(keys)):
                    if not cursor.execute('SELECT pg_try_advisory_lock(%s)',(key,)).fetchone()[0]:
                        ready=False;break
        # Release parent SHARE locks before C commits each first target intent.
        # The real session advisory locks survive only until this connection closes.
        connection.commit()
        if ready:
            lease=Lease(store.subject_digest,prototype.operation_id,scope,digest(association_raw),get_ident())
            token=ACTIVE.set(lease)
        yield ready is True
    finally:
        if lease is not None:lease.active=False;lease.plan=None
        if token is not None:ACTIVE.reset(token)
        connection.close()
