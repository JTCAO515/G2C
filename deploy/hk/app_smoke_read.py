"""B-qualified dynamic App originals, batched under one native Runtime.

stdin carries the existing token; it is never an argument, log or output.
This module sends no MESSAGE/model/tool request and grants no qualification.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

from cj_api.app_smoke_capture import AppSmokeCapture
from cj_api.app_smoke_originals import SmokeOriginals
from cj_api.app_smoke_state import SmokeState
from cj_api.local_account_admission_v2 import account_checker_for,retired_in_transaction
from cj_api.local_app import ISSUER,scope_for
from cj_api.local_worker_context import checker_factory_for
from cj_api.runtime_originals import RuntimeOriginals
from cj_api.runtime_private import read_private,private_directory
from cj_message.auth_boundary import Boundary
from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,canonical
from runtime_adapter.contract import Unavailable,decode
from .configuration import Runtime,load_secret_environment,authorization
from .entrypoint import _runtime_gate
from .app_smoke_outer import OuterControls
from .app_smoke_prepare import write_new


@contextmanager
def readers(api_manifest):
    load_secret_environment('worker')
    with tempfile.TemporaryDirectory(prefix='qualified-app-smoke-read-')as directory:
        runtime=Runtime.load(directory,worker=True)
        try:
            database=runtime.database();_runtime_gate(database,runtime)
            budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
            controls=OuterControls(api_manifest,runtime.demo_subjects)
            capture=AppSmokeCapture(controls.window['policy_path'],runtime.demo_subjects,{},database,budget)
            checker=account_checker_for(runtime.auth,database,selected_subjects=controls.subjects)
            builder=checker_factory_for(runtime.auth,selected_subjects=controls.subjects)
            def transaction(tx,scope):return builder(retired_in_transaction(tx.cur,scope))
            boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),
                lambda:str(uuid4()),checker_in_transaction=transaction)
            native=RuntimeOriginals(boundary,database,budget,capture.evidence.directory,
                query_original=lambda context,mid:context.query_lio_message(mid))
            yield controls,capture,SmokeOriginals(controls,native),SmokeState(controls,boundary,database)
        finally:runtime.close()


def step_claim(capture,selected,step,message_id,checkpoint):
    """Resolve only this frozen send slot, never a null-MID history wildcard."""
    slots=[slot for slot in capture.slots if slot['nonce']==step['nonce']]
    if len(slots)!=1 or step['text']is None:
        raise Unavailable('APP_SMOKE_STEP_HAS_NO_SEND_SLOT')
    matches=[claim for claim in selected if claim['slot_id']==slots[0]['slot_id']]
    if len(matches)!=1:
        raise Unavailable('APP_SMOKE_STEP_CLAIM_NOT_UNIQUE')
    claim=matches[0];actual=claim['binding']['message_id']
    if message_id is not None and message_id!=actual:
        raise Unavailable('APP_SMOKE_STEP_MESSAGE_CHANGED')
    if actual in checkpoint['native_state']['message_ids']:
        raise Unavailable('APP_SMOKE_MESSAGE_PRECEDES_ITS_CHECKPOINT')
    return claim


def perform(request,controls,capture,originals,state):
    required={'version','kind','token','message_id','operation_id','expected_source','plan_sha256','nonce'}
    if(type(request)is not dict or not required<=request.keys()or request['version']!='G2C-App-smoke-read-request.1'
            or request['kind']not in('checkpoint','observe','observe_read','inventory','input','artifact','wire_input','meter','fee','stop_new')):
        raise ValueError('explicit bounded App-smoke read required')
    if(request['expected_source']!=capture.policy['source_commit']or request['plan_sha256']!=capture.policy['plan_sha256']):
        raise Unavailable('APP_SMOKE_READ_PLAN_CHANGED')
    controls.guard();token=request['token'];kind=request['kind'];mid=request['message_id']
    # Every action, including stop-new and metadata-only reads, authenticates
    # this original current owner. A plan/configuration is not a native permit.
    before_state=state.read(token)
    scope_hash=before_state['scope_sha256']
    plan=decode(read_private(Path(controls.window['policy_path']).parent/'plan.json',262144))
    if sha256(canonical(plan)).hexdigest()!=capture.policy['plan_sha256']:
        raise Unavailable('APP_SMOKE_FROZEN_PLAN_CHANGED')
    step=next((x for x in plan['steps']if x['nonce']==request['nonce']),None)
    if step is None:raise Unavailable('APP_SMOKE_UNKNOWN_STEP_NONCE')
    owners={sha256(x['scope'].encode()).hexdigest():x['locale']for x in capture.slots}
    if owners.get(scope_hash)!=step['locale']:raise Unavailable('APP_SMOKE_STEP_OWNER_CHANGED')
    claims=decode(capture.claims_snapshot())
    selected=[c for c in claims['claims']if sha256(c['binding']['scope'].encode()).hexdigest()==scope_hash]
    base=dict(version='G2C-App-smoke-read.1',source=capture.policy['source_commit'],
        plan_sha256=capture.policy['plan_sha256'],policy_sha256=capture.digest,window_id=capture.policy['window_id'],
        nonce=request['nonce'],kind=kind,state=claims['state'],scope_sha256=scope_hash)
    if kind=='stop_new':
        result=decode(capture.stop_new())
        return dict(base,status='READ',control_state=result['state'])
    if kind=='checkpoint':
        point=dict(version='G2C-App-smoke-checkpoint.1',policy_sha256=capture.digest,
            plan_sha256=capture.policy['plan_sha256'],nonce=request['nonce'],scope_sha256=scope_hash,
            native_state=before_state,financial=originals.checkpoint(),http=originals.http_checkpoint(token))
        identity=sha256(canonical([capture.digest,scope_hash,request['nonce']])).hexdigest()+'.checkpoint.json'
        with private_directory(capture.directory,Unavailable('APP_SMOKE_CHECKPOINT_DIRECTORY_AUTHORITY'))as directory:
            info=os.fstat(directory)
            if(info.st_dev,info.st_ino)!=(capture.policy['directory_device'],capture.policy['directory_inode']):
                raise Unavailable('APP_SMOKE_CHECKPOINT_DIRECTORY_CHANGED')
            write_new(identity,point,directory_fd=directory)
        return dict(base,status='READ',native_state=before_state,ledger_anchor=point['financial']['anchor'],claims=selected,
            checkpoint_ref=sha256(canonical(point)).hexdigest())
    if kind in('observe','observe_read'):
        reference=request.get('checkpoint_ref')
        if type(reference)is not str or len(reference)!=64:
            raise Unavailable('APP_SMOKE_ACTUAL_BEFORE_CHECKPOINT_REQUIRED')
        identity=sha256(canonical([capture.digest,scope_hash,request['nonce']])).hexdigest()+'.checkpoint.json'
        with private_directory(capture.directory,Unavailable('APP_SMOKE_CHECKPOINT_DIRECTORY_AUTHORITY'))as directory:
            info=os.fstat(directory)
            if(info.st_dev,info.st_ino)!=(capture.policy['directory_device'],capture.policy['directory_inode']):
                raise Unavailable('APP_SMOKE_CHECKPOINT_DIRECTORY_CHANGED')
            raw=read_private(identity,524288,directory_fd=directory)
        if sha256(raw).hexdigest()!=reference:raise Unavailable('APP_SMOKE_BEFORE_CHECKPOINT_CHANGED')
        before=decode(raw)
        if(before.get('policy_sha256'),before.get('plan_sha256'),before.get('nonce'),before.get('scope_sha256'))!=(
                capture.digest,capture.policy['plan_sha256'],request['nonce'],scope_hash):
            raise Unavailable('APP_SMOKE_BEFORE_CHECKPOINT_BINDING_CHANGED')
        after=state.read(token)
        http=originals.http_observed(token,before['http'])
        if kind=='observe_read':
            financial_after=originals.checkpoint()
            cohort_closed=True
            for retained in selected:
                tail=decode(originals.originals.cost_tail(token,retained['binding']['message_id']))
                if(retained['producer_return']is None or tail['delivery_acknowledged']is not True or
                        any(job['state']not in('completed','cancelled')for job in tail['associated_history_jobs'])):
                    cohort_closed=False
            unchanged=(before['native_state']==after and before['financial']['c_rows']==financial_after['c_rows']
                       and http['post_count']==0 and cohort_closed)
            return dict(base,status='READ',before=before['native_state'],after=after,http=http,
                accounting=dict(coverage='complete'if unchanged else'UNKNOWN',producer_closure_verified=unchanged,
                    closure_ref=reference,missing=[]if unchanged else[dict(field='read_only_state_financial_HTTP_or_producer_closure')],
                    attempts=[],actual_paid_status='UNKNOWN_NO_INVOICE'))
    if kind=='observe':
        claim=step_claim(capture,selected,step,mid,before)
        mid=claim['binding']['message_id']
    else:claim=next((c for c in selected if c['binding']['message_id']==mid),None)
    if claim is None:raise Unavailable('APP_SMOKE_READ_NO_ORIGINAL_CLAIM')
    if kind=='observe':
        message=decode(originals.message(token,mid));outer=decode(originals.outer(token,mid))
        inventory=decode(originals.originals.inventory(token,mid))
        components=[]
        for op in inventory['operations']:
            entry=dict(operation=op)
            for name in('meter','fee'):
                try:entry[name]=decode((originals.originals.meter if name=='meter'else originals.originals.fee)(token,mid,op['operation_id']))
                except Unavailable as error:entry[name]=dict(status='UNAVAILABLE',reason=str(error))
            components.append(entry)
        financial=originals.accounting(token,mid,before['financial'],
            background_before=before['native_state']['background_rows'],background_after=after['background_rows'])
        return dict(base,status='READ',claim=claim,message=message,outer_request=outer,
            inventory=inventory,components=components,accounting=financial,http=http,
            before=before['native_state'],after=after)
    op=request['operation_id'];native=originals.originals
    if kind=='inventory':payload=native.inventory(token,mid)
    elif kind=='wire_input':payload=native.artifact(token,mid,op,wire_input=True)
    else:payload={'input':native.input,'artifact':native.artifact,'meter':native.meter,'fee':native.fee}[kind](token,mid,op)
    return dict(base,status='READ',utf8=payload.decode('utf-8'))


def main():
    if len(sys.argv)!=2:raise ValueError('B-qualified API manifest path required')
    raw=sys.stdin.buffer.read(524289)
    if len(raw)>524288:raise ValueError('bounded App-smoke read request required')
    request=decode(raw)
    try:
        with readers(Path(sys.argv[1]))as components:
            result=perform(request,*components)
    except Unavailable as error:
        result=dict(version='G2C-App-smoke-read.1',status='UNAVAILABLE',reason=str(error))
    print(canonical(result).decode('utf-8'))


if __name__=='__main__':main()
