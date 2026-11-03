"""Bounded comparison preparation; not a persisted erasure intent or B grant."""
import json
from hashlib import sha256

from cj_memory.domain import Conflict,Unavailable
from cj_memory.typed import parse_stored
from cj_memory_jobs.postgres import Transaction,encode
from .source_graph import capture


def prepare(memory,item_id,*,expected_version,expected_scope_epoch,max_sources,max_jobs,max_bytes):
    """Include ALL matching C jobs, not only the first publication producer.

    The caller holds the canonical Memory transaction. This function stops,
    deletes and persists nothing. Its result cannot authorize a cleanup hook.
    """
    if (type(expected_version) is not int or not 1<=expected_version<=2**63-1
            or type(expected_scope_epoch) is not int or not 1<=expected_scope_epoch<=2**63-1
            or type(max_jobs) is not int or not 1<=max_jobs<=1000):
        raise ValueError('explicit bounded original erasure selection required')
    graph=json.loads(capture(memory,item_id,max_sources=max_sources,max_bytes=max_bytes))
    if (graph['item_version'],graph['scope_epoch'])!=(expected_version,expected_scope_epoch):
        raise Conflict('original erasure selection changed')
    scope,cur=memory.scope,memory.cur
    sources=[ref['source_id'] for ref in graph['source_refs']]
    cur.execute('SELECT approved_input FROM cj_memory_source WHERE scope=%s AND source_id=ANY(%s)',(scope,sources))
    operation_refs={}
    for (raw,) in cur.fetchall():
        command=parse_stored(bytes(raw))
        # Confirm/edit commands are canonical source originals even when their
        # receipt lives in a dedicated action ledger, not cj_memory_operation.
        digest=sha256(command.raw).hexdigest()
        previous=operation_refs.setdefault(command.operation_id,digest)
        if previous!=digest:raise Unavailable('source operation identity is ambiguous')
    # Canonical source and save-ledger original bytes identify every operation.
    # There is no text/slot inference or cross-owner SQL.
    cur.execute('''SELECT operation_id FROM cj_memory_operation WHERE scope=%s
        AND (item_id=%s OR convert_from(original_input,'UTF8')::jsonb->>'source_id'=ANY(%s))
        ORDER BY operation_id LIMIT %s''',(scope,item_id,sources,max_sources+1))
    operations=cur.fetchall()
    if len(operations)>max_sources:raise Unavailable('erasure operation inventory exceeds bound')
    for (operation_id,) in operations:
        original,receipt=memory.operation(operation_id)
        command=parse_stored(original)
        if (command.item_id!=item_id or command.source_id not in sources
                or receipt.item_id!=item_id):
            raise Unavailable('selected operation source association differs')
        previous=operation_refs.setdefault(operation_id,receipt.input_sha256)
        if previous!=receipt.input_sha256:raise Unavailable('saved operation original differs from source')
    if len(operation_refs)>max_sources:raise Unavailable('erasure operation inventory exceeds bound')
    refs=graph['message_refs']
    # Overlap is exact canonical MESSAGE coordinates + original input hash.
    # Include pending/inflight/UNKNOWN/terminal work at any original source or
    # Memory basis: withdrawal is no evidence that old payload has disappeared.
    cur.execute('''SELECT j.job_id,j.attempt_id FROM cj_memory_history_job j
        WHERE j.scope=%s AND (EXISTS(
          SELECT 1 FROM jsonb_array_elements(convert_from(j.batch,'UTF8')::jsonb->'messages') m,
                        jsonb_array_elements(%s::jsonb) r
          WHERE m->'receipt' @> r)
          OR convert_from(j.batch,'UTF8')::jsonb->>'decision_source_sha256'=ANY(%s))
        ORDER BY j.job_id LIMIT %s''',(scope,json.dumps(refs),graph['decision_source_sha256s'],max_jobs+1))
    matches=set(cur.fetchall())
    matches.update((ref['job_id'],ref['attempt_id']) for ref in graph['origin_producers'])
    if len(matches)>max_jobs:raise Unavailable('overlapping original jobs exceed bound')
    jobs=Transaction(memory);job_refs=[]
    for jid,attempt in sorted(matches):
        row=jobs.job(jid,attempt)
        job_refs.append(dict(job_id=jid,attempt_id=attempt,original_input_sha256=row[0].input_sha256,
                             state=row[0].state))
    result=dict(version='MEMORY-ERASURE-ASSOCIATION-DRAFT@1',item_id=item_id,item_version=expected_version,
        scope_epoch=expected_scope_epoch,source_refs=graph['source_refs'],
        operation_refs=[dict(operation_id=oid,input_sha256=digest) for oid,digest in sorted(operation_refs.items())],
        message_refs=refs,job_refs=job_refs,decision_source_sha256s=graph['decision_source_sha256s'])
    raw=encode(result)
    if len(raw)>max_bytes:raise Unavailable('erasure association exceeds explicit byte bound')
    return raw
