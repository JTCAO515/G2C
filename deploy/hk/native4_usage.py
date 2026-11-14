"""Operator-only same-account qualification after the compatible reader is deployed.

The B deployment coordinator owns the stopped-service window, exact source/image
proof, private before/after evidence and UNKNOWN handling. This is not a runtime
entrypoint, a quota grant, a new identity, or permission to send provider requests.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from cj_api.local_app import ISSUER,scope_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode_stored,decode_v2,encode_v2
from cj_usage.core import LedgerV2,NATIVE4_PROFILE
from . import checkpoint,assembly_profiles


def qualify(connection,runtime,subject,control,*,apply=False):
    """Call inside the existing operator transaction/lock, never with runtime SQL."""
    if subject not in runtime.planning_subjects:
        raise ValueError('explicit existing HK planning subject required')
    scope=scope_for(ISSUER,subject)
    checkpoint.require_release(connection,control)
    # Freeze producer writes before inspecting emptiness. Old reader images must
    # already be stopped: the coordinator verifies that deployment separately.
    connection.execute('LOCK TABLE cj_message_receipt,cj_message_delivery,cj_run_record,cj_account_fence IN SHARE ROW EXCLUSIVE MODE')
    owner_digest=sha256(scope.encode()).hexdigest()
    if connection.execute('SELECT 1 FROM cj_account_fence WHERE owner_digest=%s OR namespace_digests ? %s LIMIT 1',
            (owner_digest,owner_digest)).fetchone()is not None:
        raise ValueError('retired original account; qualification refused')
    profile,namespace=assembly_profiles.inspect(connection,control,scope)
    if profile!=assembly_profiles.PROFILE or not namespace:
        raise ValueError('existing native MESSAGE profile required')
    contexts=[runtime.context]
    if subject in runtime.demo_subjects and runtime.demo_next_context is not None:
        contexts.append(runtime.demo_next_context)
    snapshots=[]
    for context in contexts:
        config=context.current.meter;account=ledger_scope_for(scope,config)
        row=connection.execute('SELECT revision,format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s FOR UPDATE',(account,)).fetchone()
        if row is None:raise ValueError('original account unavailable; no provisioning')
        ledger=decode_stored(row[1],row[2])
        if ledger.config!=config:raise ValueError('original configuration differs; no reset')
        old=connection.execute('SELECT policy FROM cj_native4_usage_profile WHERE scope=%s AND ledger_scope=%s',(scope,account)).fetchone()
        if old is not None and (old!=(NATIVE4_PROFILE,)or not isinstance(ledger,LedgerV2)):
            raise ValueError('original qualification inconsistent; inspect only')
        if old is None and isinstance(ledger,LedgerV2)and ledger.run_profiles:
            raise ValueError('unqualified original native usage; inspect only')
        snapshots.append((account,row,ledger,old))
    changes=[]
    for account,row,ledger,old in snapshots:
        before=asdict(ledger)
        if isinstance(ledger,LedgerV2):updated=ledger
        else:
            original=dict(before,run_profiles={},attempt_providers={})
            updated=decode_v2(original)
        if apply and old is None:
            if row[1]==1:
                result=connection.execute('UPDATE cj_usage_ledger_candidate SET format_version=2,ledger=%s::jsonb,revision=revision+1 WHERE scope_id=%s AND revision=%s',
                    (encode_v2(updated),account,row[0]))
                if result.rowcount!=1:raise ValueError('original account changed')
            connection.execute('INSERT INTO cj_native4_usage_profile VALUES(%s,%s,%s)',(scope,account,NATIVE4_PROFILE))
        changes.append(dict(account=account,previous_format=row[1],existing=old is not None,
            original_ledger_sha256=sha256(json.dumps(before,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            attempts=len(ledger.attempts),new_budget_units=0))
    return dict(status='NATIVE4_USAGE_QUALIFIED_TRANSACTION_PENDING'if apply else'NATIVE4_USAGE_PREFLIGHT_ONLY',
                policy=NATIVE4_PROFILE,accounts=changes,provider_calls=0)
