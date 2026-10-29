"""Local host execution policy; history visibility alone is never dispatch authority."""
from .domain import Unavailable

VERSION='local-budget-needs.1'
REGISTERED_VERSION='registered-exit.1'


def check(cursor,scope,configured,registered=False):
    """Caller holds the MESSAGE scope row lock; missing schema never means legacy."""
    cursor.execute('SELECT version FROM cj_local_run_protection WHERE scope=%s',(scope,))
    row=cursor.fetchone()
    if row is not None and row!=(VERSION,): raise Unavailable()
    protected=row is not None
    if protected!=configured: raise Unavailable()
    if registered:
        cursor.execute('SELECT version FROM cj_local_metered_profile WHERE scope=%s',(scope,))
        if cursor.fetchone()!=(REGISTERED_VERSION,): raise Unavailable()
    return protected


def require_original(cursor,scope,configured,message_id,run_id,registered=False):
    if not check(cursor,scope,configured,registered): return
    table='cj_message_metered_requirement' if registered else 'cj_local_run_requirement'
    version=REGISTERED_VERSION if registered else VERSION
    cursor.execute('SELECT run_id,version FROM '+table+' WHERE scope=%s AND message_id=%s',(scope,message_id))
    if cursor.fetchone()!=(run_id,version): raise Unavailable()


def capture(cursor,scope,stored,registered=False):
    r=stored.receipt
    table='cj_message_metered_requirement' if registered else 'cj_local_run_requirement'
    version=REGISTERED_VERSION if registered else VERSION
    cursor.execute('INSERT INTO '+table+'(scope,message_id,run_id,version) VALUES(%s,%s,%s,%s)',
                   (scope,r.message_id,r.run_id,version))
