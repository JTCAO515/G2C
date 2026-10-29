"""Local host execution policy; history visibility alone is never dispatch authority."""
from .domain import Unavailable

VERSION='local-budget-needs.1'


def check(cursor,scope,configured):
    """Caller holds the MESSAGE scope row lock; missing schema never means legacy."""
    cursor.execute('SELECT version FROM cj_local_run_protection WHERE scope=%s',(scope,))
    row=cursor.fetchone()
    if row is not None and row!=(VERSION,): raise Unavailable()
    protected=row is not None
    if protected!=configured: raise Unavailable()
    return protected


def require_original(cursor,scope,configured,message_id,run_id):
    if not check(cursor,scope,configured): return
    cursor.execute('SELECT run_id,version FROM cj_local_run_requirement WHERE scope=%s AND message_id=%s',(scope,message_id))
    if cursor.fetchone()!=(run_id,VERSION): raise Unavailable()


def capture(cursor,scope,stored):
    r=stored.receipt
    cursor.execute('INSERT INTO cj_local_run_requirement(scope,message_id,run_id,version) VALUES(%s,%s,%s,%s)',
                   (scope,r.message_id,r.run_id,VERSION))
