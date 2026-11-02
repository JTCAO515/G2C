"""Original daily diagnostic maintenance, through the approved cleanup role only."""
import json
from .core import Denied,digest
from .coordinator import Coordinator
from .diagnostic_retention import DiagnosticHook,SECONDS
from .hooks_v1_1 import Selection
from .store import _load_operation

TARGET='checkpoints/run'


def maintain_diagnostics(store,owner_scope,current_registry,clock):
    now=int(clock());day=now//86400*86400
    current_id='diagnostic-day-'+str(day)
    with store.transaction('diagnostic-maintenance-read',writing=False) as cur:
        cur.execute("SELECT operation_id FROM cj_cleanup_operation WHERE subject_digest=%s "
            "AND purpose='diagnostics' AND operation_id LIKE 'diagnostic-day-%%' "
            "AND NOT EXISTS(SELECT 1 FROM cj_cleanup_step s WHERE s.subject_digest=cj_cleanup_operation.subject_digest "
            "AND s.operation_id=cj_cleanup_operation.operation_id AND s.target='checkpoints/run' AND s.state='confirmed') ORDER BY operation_id",
            (store.subject_digest,))
        pending=[row[0] for row in cur.fetchall()]
        plans=[]
        for op in pending:
            purpose,manifest,blocked,plan,targets=_load_operation(cur,store.subject_digest,op)
            if plan is None or targets!=(TARGET,) or plan[TARGET]['domain_scope']!=owner_scope:
                raise Denied('original diagnostic maintenance plan unavailable')
            plans.append((op,Selection.from_dict(plan[TARGET]['selection'])))
    if current_id not in pending:plans.append((current_id,Selection('diagnostics',before_unix=day-SECONDS)))
    results=[]
    for operation,selection in plans:
        cutoff=selection.before_unix
        if cutoff>now-SECONDS:raise Denied('clock precedes original diagnostic cutoff')
        # Freeze the operation's original approved clock boundary across restart.
        hook=DiagnosticHook(store,owner_scope,lambda cutoff=cutoff:cutoff+SECONDS)
        host=Coordinator(store,current_registry,{TARGET:hook})
        state=host.create(operation,digest(('daily-90-day-diagnostics:'+str(cutoff)).encode()),'diagnostics',
            {TARGET:{'domain_scope':owner_scope,'selection':selection.to_dict()}})
        if state['status'] in ('blocked','failed'):return state
        request=host.request(operation,TARGET,owner_scope,selection)
        step=state['steps'][0]['state']
        if step=='pending':state=host.advance(request)
        elif step!='confirmed':state=host.reconcile(request)
        results.append(state)
        if state['status']!='complete':return state
    return results[-1]
