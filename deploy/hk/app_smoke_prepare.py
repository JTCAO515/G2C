"""Prepare a new owner-only App-smoke package; no network or live activation.

The B installation step must map paths/inodes to actual UID10001 directories,
recheck real pins/authority/ledger/idle state, and independently qualify the
package before issuing ACTIVE. A locally prepared file is never that permit.
"""
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path

from cj_usage.authorization_budget import canonical,HK_PRODUCER
from cj_api.runtime_private import read_private


def write_new(path,value,*,directory_fd=None):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd)
    with os.fdopen(fd,'wb')as output:
        output.write(canonical(value));output.flush();os.fsync(output.fileno())
    if directory_fd is not None:os.fsync(directory_fd)


def prepare(directory,plan,subjects,*,source,ledger_id,starts_at,ends_at):
    """Generate only from C's frozen complete plan, without choosing any MID."""
    from eval.basic_chain.plan import check_plan,digest
    from .app_smoke_outer import VERSION as OUTER_WINDOW
    check_plan(plan)
    if set(subjects)!={'zh','en'}or len(set(subjects.values()))!=2:
        raise ValueError('two explicitly assigned existing C identities required')
    start,end=map(datetime.fromisoformat,(starts_at,ends_at))
    cap=5400 if plan['first_setup']else 3600
    if start.tzinfo is None or end.tzinfo is None or not 0<(end-start).total_seconds()<=cap:
        raise ValueError('quoted bounded App window required')
    root=Path(directory);root.mkdir(mode=0o700,exist_ok=False)
    claims=root/'claims';claims.mkdir(mode=0o700)
    evidence=root/'evidence';evidence.mkdir(mode=0o700)
    outer=root/'outer';outer.mkdir(mode=0o700)
    write_new(claims/'claims.lock',{})
    evidence_policy=dict(version='G2C-runtime-evidence-window.4',directory=str(evidence),
        subjects=list(subjects.values()),kinds=['model','tool'],source_commit=source,expires_at=ends_at)
    write_new(root/'evidence.json',evidence_policy)
    slots=[];previous={}
    for step in plan['steps']:
        if step['text']is None:continue
        locale=step['locale'];name=locale+'.'+step['gate_id']
        mode='new'if step['new_conversation']else'continuation'
        prior=None if mode=='new'else previous.get(locale)
        if mode=='continuation'and prior is None:raise ValueError('actual prior seed slot required')
        slots.append(dict(slot_id=name,nonce=step['nonce'],subject=subjects[locale],locale=locale,
            protocol=plan['app']['protocol'],text_sha256=step['text_sha256'],setup=step['kind']=='setup',
            conversation_mode=mode,prior_slot_id=prior))
        previous[locale]=name
    policy=dict(version='G2C-App-smoke-capture.1',window_id=plan['run_id'],source_commit=source,
        app_source=plan['app']['source_sha'],plan_sha256=digest(plan),starts_at=starts_at,ends_at=ends_at,
        directory=str(claims),directory_device=claims.stat().st_dev,directory_inode=claims.stat().st_ino,
        evidence_manifest=str(root/'evidence.json'),evidence_sha256=sha256((root/'evidence.json').read_bytes()).hexdigest(),
        artifact_device=evidence.stat().st_dev,artifact_inode=evidence.stat().st_ino,
        slots=slots,ledger_id=ledger_id,producer_id=HK_PRODUCER)
    write_new(root/'policy.json',policy)
    policy_sha=sha256((root/'policy.json').read_bytes()).hexdigest()
    write_new(claims/'claims.json',dict(version='G2C-App-smoke-claims.1',policy_sha256=policy_sha,state='ACTIVE',claims=[]))
    write_new(root/'api.json',dict(version=OUTER_WINDOW,policy_path=str(root/'policy.json'),policy_sha256=policy_sha,
        directory=str(outer),directory_device=outer.stat().st_dev,directory_inode=outer.stat().st_ino))
    write_new(root/'plan.json',plan)
    result=dict(version='G2C-App-smoke-prepared.1',state='PREPARED_NOT_ACTIVE',
        plan_sha256=digest(plan),policy_sha256=policy_sha,source=source,window_id=plan['run_id'],
        message_slots=len(slots),new_message_ids_allocated=0,new_accounts=0,new_money=0,
        note='Local paths/inodes are not Hong Kong qualification; no dispatch allowed')
    write_new(root/'prepared.json',result)
    return result
