"""B host verifies actual default roles and closed capture before C100 restore.

No business replay or new money. Source/image, packet and exact native module
are fixed; an uncertain native restore keeps its one-shot intent for audit.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

if __package__ in(None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from deploy.hk.app_smoke_install import ROOT,private,sha,save,require_no_pending_reader


def roles(plan,inspect):
    result={}
    for role in('api','worker'):
        value=inspect(role);mounts={m['Destination']:m for m in value['Mounts']}
        normalized={k:dict(source=m['Source'],rw=m['RW'])for k,m in mounts.items()}
        if normalized!=plan['mounts'][role]:raise ValueError('complete actual default mounts changed')
        if(value['Image']!=plan['image']or value['Config']['Labels']['org.opencontainers.image.revision']!=plan['source']
                or value['Config']['Cmd']!=[role]or not value['State']['Running']):
            raise ValueError('actual same-source default roles required before standing restore')
        if any(k.startswith('/app-smoke')or k.startswith('/run/app-smoke')or k=='/tool-evidence'for k in mounts):
            raise ValueError('actual collector is still attached')
        if role=='api'and any(k in mounts for k in('/rejected-intakes','/run/secrets/worker.env',
                '/home/cj/.local/share/g2c/m4-real-services')):raise ValueError('API raw isolation changed')
        if role=='api'and value['State'].get('Health',{}).get('Status')!='healthy':raise ValueError('actual API not ready')
        result[role]=dict(id=value['Id'],image=value['Image'],source=plan['source'],command=value['Config']['Cmd'])
    return result


def perform(directory,plan,restriction,closed,inspect,native,*,apply):
    if(closed.get('version')!='G2C-App-smoke-close.1'or closed.get('state')!='DEFAULT_ROLES_RESTORED'
            or closed.get('ledger_before')!=closed.get('ledger_after')or closed.get('budget_restored')is not False):
        raise ValueError('actual acknowledged formal close receipt required')
    before=roles(plan,inspect)
    request=dict(version='G2C-App-smoke-closed-standing-restore.1',expected_policy_sha256=plan['restricted_policy_sha256'],
        restriction=restriction,closed_capture_sha256=plan['close_sha256'],ledger_id=plan['ledger_id'],
        producer_id=plan['producer_id'],apply=apply)
    if apply:save(directory/'standing-restore.intent.json',dict(source=plan['source'],image=plan['image'],
        close_sha256=plan['close_sha256'],restricted_policy_sha256=plan['restricted_policy_sha256']))
    value=native(before['worker']['id'],request)
    if roles(plan,inspect)!=before:raise ValueError('original roles changed during standing restore; inspect only')
    expected='C_ORIGINAL_STANDING_RESTORED_ACKED'if apply else'READONLY_NOT_RESTORED'
    if value.get('state')!=expected:raise ValueError('native standing restore outcome unavailable')
    if apply:save(directory/'standing-restore.result.json',value)
    return value


def main():
    if len(sys.argv)not in(2,3)or len(sys.argv)==3 and sys.argv[2]!='--apply':
        raise ValueError('explicit reviewed preflight or once standing restore required')
    path=Path(sys.argv[1]);raw=private(path);plan=json.loads(raw);directory=path.parent
    if(plan['version']!='G2C-App-smoke-standing-restore-plan.1'or plan['independent_review_approved']is not True
            or sha(__file__)!=plan['reviewed_script_sha256']):raise ValueError('exact reviewed standing restore required')
    def window():
        if not plan['starts_at']<=time.time()<plan['ends_at']or not 0<plan['ends_at']-plan['starts_at']<=1800:
            raise ValueError('announced original return window required')
    window();lock=os.open(str(ROOT/'probes/application-deploy.lock'),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        import stat
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode)or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned original deployment lock required')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);require_no_pending_reader()
        closed_raw=private(directory/'close.result.json');restriction_raw=private(directory/'restriction.result.json')
        if(hashlib.sha256(closed_raw).hexdigest()!=plan['close_sha256']
                or hashlib.sha256(restriction_raw).hexdigest()!=plan['restriction_sha256']):
            raise ValueError('original close or restriction receipt changed')
        def command(args,**kwargs):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,**kwargs).stdout
        def inspect(role):return json.loads(command(['docker','inspect','g2c-beta-'+role+'-1']))[0]
        actual=roles(plan,inspect)
        proof="from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/app/deploy/hk/app_smoke_restore_worker.py').read_bytes()).hexdigest())"
        observed=command(['docker','exec',actual['worker']['id'],'python','-B','-c',proof]).decode().strip()
        if observed!=plan['native_module_sha256']:raise ValueError('original native restore module changed')
        def native(worker,request):
            window()
            if private(path)!=raw:raise ValueError('restore qualification changed')
            result=command(['docker','exec','-i',worker,'python','-B','-m','deploy.hk.app_smoke_restore_worker'],
                input=json.dumps(request).encode())
            window()
            if(private(path)!=raw or private(directory/'close.result.json')!=closed_raw
                    or private(directory/'restriction.result.json')!=restriction_raw):
                raise ValueError('original standing restore evidence changed')
            return json.loads(result)
        print(json.dumps(perform(directory,plan,json.loads(restriction_raw),json.loads(closed_raw),inspect,native,
            apply='--apply'in sys.argv)),flush=True)
    finally:os.close(lock)


if __name__=='__main__':main()
