"""RUN-FEEDBACK-LOCATOR@1: original references/stages only, never payload copies."""
from dataclasses import dataclass
from .core import Binding, ResyncRequired
from cj_usage.core import label, Blocked


@dataclass(frozen=True)
class FeedbackLocator:
    status: str
    event_highwater: int
    last_event_kind: str | None
    draft_outcome: str | None
    budget_exhausted_stage: str
    registered_source_abi: str | None
    operations: tuple[dict, ...]
    first_recorded_at: str | None
    last_recorded_at: str | None
    run_event_interval_seconds: float | None


def read_locator(repository,binding:Binding):
    with repository.transaction() as tx:
        state=tx.get(binding)
        tx.cur.execute('SELECT source_abi FROM cj_run_metered_binding WHERE scope=%s AND run_id=%s',
                       (binding.scope,binding.run_id))
        row=tx.cur.fetchone()
        abi=None if row is None else row[0]
        if abi not in (None,'RUN-USAGE-OPERATIONS@1'):raise ResyncRequired('original run unavailable')
        tx.cur.execute("SELECT operation_key,registration_id,kind,attempt_id,operation_id,encode(sha256(input_bytes),'hex') FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s ORDER BY operation_key LIMIT 257",
                       (binding.scope,binding.run_id))
        rows=tx.cur.fetchall()
        if len(rows)>256:raise ResyncRequired('original diagnostic bound exceeded')
        operations=[]
        for key,registration,kind,attempt,operation,input_hash in rows:
            try:
                for value in (key,registration,attempt,operation):label(value)
            except Blocked:raise ResyncRequired('original run unavailable') from None
            if kind not in ('model','tool','memory') or abi is None:raise ResyncRequired('original run unavailable')
            operations.append(dict(operation_key=key,registration_id=registration,kind=kind,
                                   attempt_id=attempt,operation_id=operation,input_sha256=input_hash))
        tx.cur.execute('SELECT sequence,diagnostic_at FROM cj_run_event WHERE scope=%s AND run_id=%s AND sequence IN (1,%s) ORDER BY sequence',
                       (binding.scope,binding.run_id,state.sequence))
        times=dict(tx.cur.fetchall())
        first,last=times.get(1),times.get(state.sequence)
        elapsed=(last-first).total_seconds() if first is not None and last is not None and last>=first else None
        value=FeedbackLocator(state.status,state.sequence,state.events[-1].kind if state.events else None,
            state.draft_outcome,state.budget_exhausted_stage,abi,tuple(operations),
            first.isoformat() if first else None,last.isoformat() if last else None,elapsed)
    return value
