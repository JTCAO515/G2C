"""Bounded comparison preparation; not a persisted erasure intent or B grant."""
import json
from hashlib import sha256
from dataclasses import replace

from cj_memory.domain import Conflict,Unavailable,strict_object
from cj_memory.typed import parse_stored,parse_manual as parse_typed_manual
from cj_memory.manual import parse_manual as parse_legacy_manual
from cj_memory_jobs.postgres import Transaction,encode
from .source_graph import capture


def prepare(memory,item_id,*,expected_version,expected_scope_epoch,max_sources,max_jobs,max_bytes,
            headers=None,require_coverage=False):
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
    if require_coverage:
        cur.execute('SELECT DISTINCT source_id FROM cj_memory_history_origin WHERE scope=%s AND source_id=ANY(%s)',(scope,sources))
        represented={row[0] for row in cur.fetchall()}
        if set(sources)-represented:
            if headers is None:raise Unavailable('complete owned history metadata required for unlinked source erasure')
            headers.check()
            if headers.scope!=scope or headers.complete is not True:raise Unavailable('complete original history scope unavailable')
            # No text matching or collection grant: the explicit owner deletion
            # conservatively excludes pre-delete history when an individual
            # source has no exact origin. Other canonical items remain intact.
            original={encode(ref) for ref in graph['message_refs']}
            references={encode(ref.to_dict()):ref.to_dict() for ref in headers.references}
            if not original<=set(references):raise Unavailable('original source missing from complete metadata')
            graph['message_refs']=[references[key] for key in sorted(references)]
    cur.execute('SELECT approved_input FROM cj_memory_source WHERE scope=%s AND source_id=ANY(%s)',(scope,sources))
    operation_refs={};source_commands={}
    for (raw,) in cur.fetchall():
        command=parse_stored(bytes(raw))
        source_commands[command.source_id]=command
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
        value=strict_object(original)
        manual=value.get('version')=='MEMORY-manual.2' or ('version' not in value and 'source_id' not in value)
        if value.get('version')=='MEMORY-manual.2':command=parse_typed_manual(original)
        elif manual:command=parse_legacy_manual(original)
        else:command=parse_stored(original)
        if (command.item_id!=item_id or command.source_id not in sources
                or receipt.item_id!=item_id):
            raise Unavailable('selected operation source association differs')
        approved=source_commands[command.source_id]
        if (replace(command,raw=approved.raw)!=approved if manual else command.raw!=approved.raw):
            raise Unavailable('selected operation does not derive the approved source')
        # Manual input has server-derived source fields in approved_input. Its
        # canonical decoder above proves that exact derivation; retain the real
        # user original ledger hash, not the derived stored-command hash.
        operation_refs[operation_id]=receipt.input_sha256
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
    decisions=set(graph['decision_source_sha256s'])
    for jid,attempt in sorted(matches):
        ref_digest=sha256(encode(dict(job_id=jid,attempt_id=attempt))).hexdigest()
        cur.execute("SELECT original_input_sha256 FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='job' AND reference_sha256=%s",
                    (sha256(scope.encode()).hexdigest(),ref_digest))
        erased=cur.fetchone()
        cur.execute('SELECT 1 FROM cj_memory_history_job WHERE scope=%s AND job_id=%s',(scope,jid))
        if cur.fetchone() is None:
            # An earlier overlapping item erasure may have removed this shared
            # payload. Only its permanent exact original hash proves that fact.
            if erased is None or erased[0] is None:raise Unavailable('original job absent without erasure proof')
            job_refs.append(dict(job_id=jid,attempt_id=attempt,original_input_sha256=erased[0],state='erased'))
            continue
        row=jobs.job(jid,attempt)
        decision=json.loads(row[2]).get('decision_source_sha256')
        if decision is not None:
            if type(decision) is not str or len(decision)!=64 or any(c not in '0123456789abcdef' for c in decision):
                raise Unavailable('original copied decision digest unavailable')
            decisions.add(decision)
        if erased is not None and erased[0]!=row[0].input_sha256:
            raise Unavailable('current job differs from permanently erased original input')
        job_refs.append(dict(job_id=jid,attempt_id=attempt,original_input_sha256=row[0].input_sha256,
                             state=row[0].state))
    result=dict(version='MEMORY-ERASURE-ASSOCIATION-DRAFT@1',item_id=item_id,item_version=expected_version,
        scope_epoch=expected_scope_epoch,source_refs=graph['source_refs'],
        operation_refs=[dict(operation_id=oid,input_sha256=digest) for oid,digest in sorted(operation_refs.items())],
        message_refs=refs,job_refs=job_refs,decision_source_sha256s=sorted(decisions))
    raw=encode(result)
    if len(raw)>max_bytes:raise Unavailable('erasure association exceeds explicit byte bound')
    return raw
