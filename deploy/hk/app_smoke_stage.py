"""B root stages reviewed frozen JSON on actual HK storage; never activates.

Host Python3.6 only/stdlib. One new directory, original files never overwritten.
No account, quota, configuration, service, provider or MESSAGE operation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

if __package__ in(None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from deploy.hk.app_smoke_install import ROOT,override,save

CAPTURE_UID=10001
CAPTURE_GID=10001
FILES=('policy.json','api.json','evidence.json','plan.json')


def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def stage(base,packet):
    if(type(packet)is not dict or set(packet)!={'version','files','sha256'}or packet['version']!='G2C-App-smoke-stage-request.1'
            or type(packet['files'])is not dict or set(packet['files'])!=set(FILES)
            or packet['sha256']!={name:digest(value)for name,value in packet['files'].items()}):
        raise ValueError('complete frozen source packet required')
    values=json.loads(canonical(packet['files']));p=values['policy.json'];a=values['api.json'];e=values['evidence.json'];plan=values['plan.json']
    run=plan['run_id']
    if(type(run)is not str or re.fullmatch('[A-Za-z0-9_-]{1,96}',run)is None
            or plan.get('version')!='LIO-basic-chain-plan.2'or p.get('version')!='G2C-App-smoke-capture.1'
            or a.get('version')!='G2C-App-smoke-outer-window.1'or e.get('version')!='G2C-runtime-evidence-window.4'
            or p['window_id']!=run or p['plan_sha256']!=digest(plan)
            or a['policy_sha256']!=digest(p)or p['evidence_sha256']!=digest(e)
            or p['source_commit']!=e['source_commit']or re.fullmatch('[a-f0-9]{40}',p['source_commit'])is None
            or len(p['slots'])!=plan['planned_message_count']or len(p['slots'])not in(8,12)):
        raise ValueError('fixed current plan, source and control hashes required')
    subjects={slot['locale']:slot['subject']for slot in p['slots']}
    if set(subjects)!={'zh','en'}or len(set(subjects.values()))!=2 or set(subjects.values())!=set(e['subjects']):
        raise ValueError('two original C subjects required')
    root=Path(base)/run
    root.mkdir(mode=0o700,exist_ok=False)
    for name in('claims','evidence','outer'):
        path=root/name;path.mkdir(mode=0o700);os.chown(str(path),CAPTURE_UID,CAPTURE_GID)
    def owned(name,value):
        path=root/name;save(path,value);os.chown(str(path),CAPTURE_UID,CAPTURE_GID)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    claims=(root/'claims').stat();artifacts=(root/'evidence').stat();outer=(root/'outer').stat()
    e['directory']='/app-smoke-evidence';e_sha=owned('evidence.json',e)
    p.update(directory='/app-smoke-claims',directory_device=claims.st_dev,directory_inode=claims.st_ino,
        evidence_manifest='/run/app-smoke/evidence.json',evidence_sha256=e_sha,
        artifact_device=artifacts.st_dev,artifact_inode=artifacts.st_ino)
    p_sha=owned('policy.json',p)
    a.update(policy_path='/run/app-smoke/policy.json',policy_sha256=p_sha,directory='/app-smoke-outer',
        directory_device=outer.st_dev,directory_inode=outer.st_ino)
    owned('api.json',a);owned('plan.json',plan)
    owned('claims/claims.lock',{})
    owned('claims/claims.json',dict(version='G2C-App-smoke-claims.1',policy_sha256=p_sha,state='ACTIVE',claims=[]))
    owned('proof-plan.json',dict(version='G2C-App-smoke-global-idle-plan.1',window_id=run,
        source_commit=p['source_commit'],identities=[dict(locale=locale,subject=subjects[locale])for locale in('zh','en')],cases=[]))
    owned('compose.capture.json',override(root))
    names=(*FILES,'proof-plan.json','compose.capture.json')
    result=dict(version='G2C-App-smoke-server-staged.1',state='STAGED_NOT_ACTIVE',window_id=run,source=p['source_commit'],
        input_sha256=packet['sha256'],files={name:hashlib.sha256((root/name).read_bytes()).hexdigest()for name in names},
        new_message_ids=0,new_accounts=0,new_money=0,services_changed=False,
        note='Actual source/image, AUTH, C budget/ledger/idle, live API instance and independently reviewed installation remain required')
    save(root/'stage.result.json',result)
    return result


def main():
    if os.geteuid()!=0:raise ValueError('B existing host root operator required')
    raw=sys.stdin.buffer.read(1048577)
    if len(raw)>1048576:raise ValueError('bounded frozen packet required')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('duplicate staged field')
            value[key]=item
        return value
    packet=json.loads(raw,object_pairs_hook=pairs)
    base=ROOT/'app-smoke-windows'
    if not base.exists():base.mkdir(mode=0o700)
    info=base.lstat()
    if not stat.S_ISDIR(info.st_mode)or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('owned private B staging directory required')
    print(json.dumps(stage(base,packet),sort_keys=True))


if __name__=='__main__':main()
