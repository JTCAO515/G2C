"""ACCOUNT-TASK-STOP@1: revoke publication and observe original worker ownership."""
import hashlib,json,uuid


def worker_key(chat):
    raw=b'CJ-RUN-WORKER-LEASE@1\0'+json.dumps(chat,ensure_ascii=False,separators=(',',':')).encode()
    value=int.from_bytes(hashlib.sha256(raw).digest()[:8],'big')
    return value if value<1<<63 else value-(1<<64)


def stop_scope(cursor,scope):
    """Caller already committed the durable account fence; no new dispatch allowed.

    False means a physical original worker still owns a chat. It is not permission
    to delete its state/usage or relabel its provider result as cancelled/settled.
    """
    cursor.execute('SELECT scope FROM cj_run_scope WHERE scope=%s FOR UPDATE',(scope,))
    if cursor.fetchone() is not None:
        cursor.execute('UPDATE cj_run_scope SET active=false,epoch=%s WHERE scope=%s',(uuid.uuid4().hex,scope))
    cursor.execute('SELECT DISTINCT conversation_id,generation FROM cj_run_record WHERE scope=%s',(scope,))
    stopped=True
    for conversation,generation in cursor.fetchall():
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s)',(worker_key((scope,conversation,generation)),))
        stopped=cursor.fetchone()[0] and stopped
    from .background_store import LEASE_NAMESPACE
    cursor.execute('SELECT run_id FROM cj_run_background_job WHERE scope=%s',(scope,))
    for (run_id,) in cursor.fetchall():
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s)',(worker_key((scope,LEASE_NAMESPACE,run_id)),))
        stopped=cursor.fetchone()[0] and stopped
    return stopped
