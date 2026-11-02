"""FEEDBACK@1.0 local scope serialization and irreversible account erasure fence."""
from hashlib import sha256
from .domain import Unavailable
from cj_cleanup.core import Denied
from cj_cleanup.store import original_result,record_result,receipt_for,require_intent


def scope_digest(scope):return sha256(scope.encode('utf-8')).hexdigest()


def bind_runtime(cursor,scope):
    """Explicit v1 host binder; old rc hosts receive no implicit mode change."""
    cursor.execute("SELECT current_setting('cj.message_scope',true)")
    if cursor.fetchone()[0] not in (None,''):raise Unavailable()
    cursor.execute("SELECT set_config('cj.message_scope',%s,true)",(scope,))
    key=scope_digest(scope)
    cursor.execute('INSERT INTO cj_feedback_scope(scope_digest) VALUES(%s) ON CONFLICT DO NOTHING',(key,))
    cursor.execute('SELECT retired FROM cj_feedback_scope WHERE scope_digest=%s FOR UPDATE',(key,))
    if cursor.fetchone()!=(False,):raise Unavailable()


def check_current(connect,scope):
    """Final v1 publication fence; no provisioning, mutation or cached allowance."""
    conn=connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_setting('cj.message_scope',true)")
            if cur.fetchone()[0] not in (None,''):raise Unavailable()
            cur.execute("SELECT set_config('cj.message_scope',%s,true)",(scope,))
            cur.execute('SELECT retired FROM cj_feedback_scope WHERE scope_digest=%s',(scope_digest(scope),))
            if cur.fetchone()!=(False,):raise Unavailable()
        conn.commit()
    finally:conn.close()


class FeedbackHook:
    """Only the original local account-cleanup coordinator injects this hook."""
    def __init__(self,store,scope):self.store,self.scope=store,scope

    def execute(self,request):
        if request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.scope or request.selection.kind!='account':
            raise Denied('feedback cleanup unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(self.scope,))
            key=scope_digest(self.scope)
            cur.execute('INSERT INTO cj_feedback_scope(scope_digest,retired) VALUES(%s,true) ON CONFLICT(scope_digest) DO UPDATE SET retired=true',(key,))
            cur.execute('DELETE FROM cj_feedback_action WHERE scope=%s',(self.scope,))
            if cur.execute('SELECT 1 FROM cj_feedback_action WHERE scope=%s',(self.scope,)).fetchone() is not None:
                raise Denied('feedback cleanup unconfirmed')
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:
            value=original_result(cur,request)
        return value if value is not None else receipt_for(request,'unknown')
