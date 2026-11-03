"""CLEANUP-DEVICE-COMPLETION@1: a read-only representation of one own call.

This never exposes arbitrary account progress or turns a device report into
native control-record finalization. No hook, audit, resume or capability issue.
"""
import json
from .core import Denied,Invalid,digest
from .postgres import Unavailable
from .store import CODECS
from .gateway_store import GatewayStore
from .device_bridge import original_call
from .control_records import VERSION as CONTROL
from cj_strict_json import reject_duplicates

VERSION='CLEANUP-DEVICE-COMPLETION@1'


def _object(raw):
    if type(raw) is not bytes or not 0<len(raw)<=16384:raise Unavailable('original device evidence unavailable')
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=reject_duplicates(ValueError,'duplicate original device field'))
    except (ValueError,UnicodeError,RecursionError) as error:raise Unavailable('original device evidence unavailable') from error


def _device(cur,subject,binding_id,version):
    cur.execute('SELECT binding_id,device_id,state_ref,scope_digest,protocol FROM cj_cleanup_device_binding WHERE subject_digest=%s AND binding_id=%s',
                (subject,binding_id))
    row=cur.fetchone()
    if row is None or row[4]!=version or row[3]!=subject:raise Denied('original device binding unavailable')
    return dict(binding_id=row[0],device_id=row[1],state_ref=row[2],scope_digest=row[3],protocol=row[4])


def _call(cur,subject,binding,invocation,expected_digest):
    cur.execute('SELECT operation_id,reason,request_bytes,request_digest,state,receipt_digest,receipt_bytes FROM cj_cleanup_device_call '
        'WHERE subject_digest=%s AND invocation_id=%s AND binding_id=%s',(subject,invocation,binding['binding_id']))
    row=cur.fetchone()
    if row is None or row[3]!=expected_digest:raise Denied('original device call unavailable')
    operation,reason,raw,request_digest,state,receipt_digest,receipt_raw=row
    raw=bytes(raw)
    if digest(raw)!=request_digest:raise Unavailable('original device call bytes unavailable')
    expected_op,expected_inv,expected=original_call(binding,operation if reason=='account_cleanup' else None,reason,
        operation_id=operation if reason=='account_cleanup' else None)
    if (operation,invocation,raw)!=(expected_op,expected_inv,expected):raise Unavailable('original device call binding unavailable')
    if state not in ('pending','unknown','failed','confirmed'):raise Unavailable('original device state unavailable')
    if receipt_raw is not None:
        receipt_raw=bytes(receipt_raw);receipt=_object(receipt_raw)
        fields={'version','action_id','operation_id','invocation_id','binding_id','request_digest','outcome'}
        if (digest(receipt_raw)!=receipt_digest or type(receipt) is not dict or set(receipt)!=fields
            or (receipt['version'],receipt['operation_id'],receipt['invocation_id'],receipt['binding_id'],receipt['request_digest'],receipt['outcome'])
            !=(binding['protocol'],operation,invocation,binding['binding_id'],request_digest,state)):
            raise Unavailable('original authenticated device receipt unavailable')
    elif receipt_digest is not None or state in ('confirmed','failed'):
        raise Unavailable('original device receipt absent')
    return operation,reason,state,receipt_digest


def _account(cur,store,operation,current):
    purpose,manifest,blocked,_,targets=store._load(cur,operation)
    prepared=GatewayStore(store)._load(cur,operation)
    cur.execute('SELECT operation_id FROM cj_account_fence WHERE subject_digest=%s',(store.subject_digest,))
    if purpose!='account' or prepared.phase!='confirmed' or cur.fetchone()!=(operation,):
        raise Denied('original retired account operation unavailable')
    if (manifest.raw!=prepared.registry_bytes or manifest.inventory!=prepared.inventory):
        raise Unavailable('original account registry differs')
    if tuple(sorted(targets))!=manifest.inventory:raise Unavailable('original account target inventory differs')
    matches=(manifest.raw,manifest.inventory,manifest.versions)==(current.raw,current.inventory,current.versions)
    policy=CONTROL if CONTROL in manifest.versions and len(manifest.retained_controls)==5 else None
    if blocked or manifest.gaps or current.gaps or not matches:return 'blocked',manifest.digest,policy
    progress=store.read_progress(cur,operation)
    if progress['status']!='complete':return progress['status'],manifest.digest,policy
    entries={entry.registry_id:entry for entry in manifest.entries}
    cur.execute('''SELECT s.target,s.request_digest,s.receipt_bytes,r.request_digest,r.receipt_bytes
        FROM cj_cleanup_step s LEFT JOIN cj_cleanup_domain_result r ON
        (r.subject_digest,r.operation_id,r.invocation_id)=(s.subject_digest,s.operation_id,s.invocation_id)
        WHERE s.subject_digest=%s AND s.operation_id=%s''',(store.subject_digest,operation))
    rows=cur.fetchall()
    if {row[0] for row in rows}!=set(targets):raise Unavailable('original domain result inventory differs')
    for target,request_sha,step_raw,result_sha,result_raw in rows:
        if result_sha!=request_sha or step_raw is None or result_raw is None or bytes(step_raw)!=bytes(result_raw):
            return 'unknown',manifest.digest,policy
        receipt=CODECS[entries[target].protocol].HookReceipt.from_digest(bytes(result_raw),request_sha)
        if receipt.outcome!='confirmed':return 'unknown',manifest.digest,policy
    cur.execute('SELECT reason FROM cj_cleanup_account_gate WHERE subject_digest=%s AND operation_id=%s',(store.subject_digest,operation))
    gate=cur.fetchone()
    if gate is not None and gate[0] is not None:return 'unknown',manifest.digest,policy
    return 'complete',manifest.digest,policy


def read(gateway,capability,invocation,request_digest,project,*,device_version='CLEANUP-DEVICE@3',version=VERSION):
    claims=gateway.issuer.verify(capability,purpose='device')
    if claims.operation_id!=claims.binding_id:raise Denied('original device credential required')
    store=gateway.resolve_subject(claims.subject_digest).store
    if store.subject_digest!=claims.subject_digest:raise Denied('original device subject differs')
    try:current=gateway.current_registry()
    except Invalid as error:raise Unavailable('current registry unavailable') from error
    with store.snapshot('device-completion-read') as cur:
        binding=_device(cur,claims.subject_digest,claims.binding_id,device_version)
        operation,reason,state,receipt_digest=_call(cur,claims.subject_digest,binding,invocation,request_digest)
        cur.execute("SELECT set_config('cj.cleanup_operation',%s,true)",(operation,))
        if reason=='account_cleanup':status,registry,policy=_account(cur,store,operation,current)
        else:status,registry,policy='not_applicable',None,None
        value=dict(version=version,operation_id=operation,binding_id=claims.binding_id,invocation_id=invocation,
            request_digest=request_digest,receipt_digest=receipt_digest,reason=reason,device_state=state,
            content_status=status,registry_digest=registry,control_record_protocol=policy,
            complete_scope='frozen_online_domains_only' if reason=='account_cleanup' else 'original_device_action_only',
            business_access='not_granted')
        encoded=project(value)
        if type(encoded) is not bytes or len(encoded)>4096:raise Unavailable('bounded original completion bytes required')
    # COMMIT, physical close and the Store return guard can all be slow or
    # uncertain. No completed bytes escape until those external actions finish.
    try:latest=gateway.current_registry()
    except Invalid as error:raise Unavailable('current registry unavailable') from error
    if (latest.raw,latest.inventory,latest.versions)!=(current.raw,current.inventory,current.versions):
        raise Unavailable('completion registry changed during projection')
    gateway.issuer.verify(capability,purpose='device',binding_id=claims.binding_id,operation_id=claims.binding_id)
    return encoded
