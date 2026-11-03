"""Candidate same-transaction stop/freeze; no physical delete or B intent issuer."""
from hashlib import sha256
import json
from cj_memory.domain import Conflict,Unavailable
from cj_memory_jobs.postgres import encode
from .association import prepare
from .association_codec import VERSION
from .erasure_evidence import freeze_jobs,VERSION as EVIDENCE_VERSION,MAX_BYTES as MAX_EVIDENCE_BYTES


def reference_digest(kind,value):
    if kind=='decision':return value
    raw=value.encode('utf-8') if type(value) is str else encode(value)
    return sha256(raw).hexdigest()


def freeze(memory,command,subject_digest,*,max_sources,max_jobs,max_bytes):
    """Caller owns canonical current principal + Memory transaction and guard.

    Stops and freezes exactly one item. No DTO authorizes account deletion,
    physical mutation through a cleanup role, model work or intent dispatch.
    """
    epoch=memory.lock_scope();cur,scope=memory.cur,memory.scope
    cur.execute('SELECT original_input,association,association_sha256 FROM cj_memory_erasure_manifest WHERE scope=%s AND action_id=%s',
                (scope,command.action_id))
    old=cur.fetchone()
    if old is not None:
        if bytes(old[0])!=command.raw:raise Conflict('original erasure action bytes differ')
        raw=bytes(old[1])
        if sha256(raw).hexdigest()!=old[2]:raise Unavailable('original erasure association unavailable')
        return raw
    cur.execute('SELECT 1 FROM cj_memory_erasure_manifest WHERE scope=%s AND item_id=%s',(scope,command.item_id))
    if cur.fetchone() is not None:raise Conflict('item already belongs to an original erasure')
    original=json.loads(prepare(memory,command.item_id,expected_version=command.expected_version,
        expected_scope_epoch=epoch,max_sources=max_sources,max_jobs=max_jobs,max_bytes=max_bytes))
    if command.expected_version==2**63-1 or epoch==2**63-1:raise Unavailable('erasure version advancement unavailable')
    sources=[ref['source_id'] for ref in original['source_refs']]
    cur.execute('UPDATE cj_memory_source SET active=false WHERE scope=%s AND source_id=ANY(%s)',(scope,sources))
    cur.execute("UPDATE cj_memory_item SET status='withdrawn',version=version+1 WHERE scope=%s AND item_id=%s AND version=%s RETURNING version",
                (scope,command.item_id,command.expected_version))
    stopped=cur.fetchone()
    if stopped is None:raise Conflict('selected item changed')
    cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s RETURNING epoch',(scope,))
    stopped_epoch=cur.fetchone()[0];operation=command.operation_id(scope)
    selection=dict(kind='memory',item_id=command.item_id,item_version=stopped[0],scope_epoch=stopped_epoch)
    value=dict(version=VERSION,operation_id=operation,subject_digest=subject_digest,
        memory_scope_digest=sha256(scope.encode()).hexdigest(),selection=selection,original_selection=dict(
            item_id=command.item_id,item_version=command.expected_version,scope_epoch=epoch),
        source_refs=original['source_refs'],operation_refs=original['operation_refs'],message_refs=original['message_refs'],
        job_refs=original['job_refs'],decision_source_sha256s=original['decision_source_sha256s'],
        derived_range=dict(kind='owned_trip_derived_scope',precise_item_match=False,preserve_formal_trips=True))
    raw=encode(value)
    if len(raw)>max_bytes:raise Unavailable('immutable erasure association exceeds bound')
    evidence=encode(dict(version=EVIDENCE_VERSION,operation_id=operation,subject_digest=subject_digest,
        memory_scope_digest=value['memory_scope_digest'],selection=selection,association_sha256=sha256(raw).hexdigest(),
        jobs=freeze_jobs(memory,original)))
    if len(evidence)>MAX_EVIDENCE_BYTES:raise Unavailable('immutable original source proof exceeds bound')
    cur.execute('''INSERT INTO cj_memory_erasure_manifest
        (scope,action_id,operation_id,original_input,input_sha256,association,association_sha256,evidence,evidence_sha256,item_id,item_version,scope_epoch)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(scope,command.action_id,operation,command.raw,sha256(command.raw).hexdigest(),
        raw,sha256(raw).hexdigest(),evidence,sha256(evidence).hexdigest(),command.item_id,stopped[0],stopped_epoch))
    scope_digest=value['memory_scope_digest']
    def fence(kind,identifier,original_sha=None):
        cur.execute('''INSERT INTO cj_memory_erasure_fence(scope_digest,kind,reference_sha256,original_input_sha256)
            VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''',(scope_digest,kind,reference_digest(kind,identifier),original_sha))
    fence('item',command.item_id)
    for ref in original['source_refs']:fence('source',ref['source_id'])
    for ref in original['operation_refs']:fence('operation',ref['operation_id'],ref['input_sha256'])
    for ref in original['message_refs']:fence('message',ref)
    for digest in original['decision_source_sha256s']:fence('decision',digest)
    for ref in original['job_refs']:
        fence('job',dict(job_id=ref['job_id'],attempt_id=ref['attempt_id']),ref['original_input_sha256'])
        fence('job_id',ref['job_id'],ref['original_input_sha256'])
        fence('attempt_id',ref['attempt_id'],ref['original_input_sha256'])
    cur.execute('''INSERT INTO cj_memory_erasure_fence
        (scope_digest,kind,reference_sha256,original_input_sha256,operation_id,item_version,scope_epoch)
        VALUES(%s,'action',%s,%s,%s,%s,%s)''',(scope_digest,reference_digest('action',command.action_id),
        sha256(command.raw).hexdigest(),operation,stopped[0],stopped_epoch))
    return raw
