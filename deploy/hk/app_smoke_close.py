"""Detach a returned App capture once; preserve every original and fee.

No source rollback, budget restore, deletion, send or full-cost certificate.
Failure after closing ingress leaves both roles stopped for reconciliation.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime

if __package__ in(None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from deploy.hk.app_smoke_install import ROOT,STATIC,FILES,EXPORTER_SHA,private,sha,save,idle,override,require_no_pending_reader


def transition(directory,before,proof,check,stop,start,ready,window,unchanged):
    if not idle(before):raise ValueError('original producers are not idle')
    check(True);unchanged();window()
    save(directory/'close.intent.json',dict(state='CLOSING',ledger=before['ledger']))
    closed=False
    try:
        closed=True;stop(['api']);window()
        drained=proof();save(directory/'close.drained.json',drained)
        if not idle(drained)or drained['ledger']!=before['ledger']:
            raise ValueError('original work arrived during capture closure')
        unchanged();window();stop(['worker']);window();start();window();ready();window()
        check(False);unchanged();after=proof()
        if not idle(after)or after['ledger']!=before['ledger']:
            raise ValueError('original work changed while detaching capture')
        result=dict(version='G2C-App-smoke-close.1',state='DEFAULT_ROLES_RESTORED',
            ledger_before=before['ledger'],ledger_after=after['ledger'],originals_deleted=0,
            budget_restored=False,smoke_status='NOT_ASSERTED',full_cost_coverage='NOT_ASSERTED')
        save(directory/'close.result.json',result)
        return result
    except BaseException:
        if closed:stop(['api','worker'])
        raise


def main():
    if len(sys.argv)not in(2,3)or len(sys.argv)==3 and sys.argv[2]!='--apply':
        raise ValueError('explicit reviewed close preflight or once apply required')
    path=Path(sys.argv[1]);raw=private(path);plan=json.loads(raw);directory=path.parent
    if(plan['version']!='G2C-App-smoke-close-plan.1'or sha(__file__)!=plan['reviewed_script_sha256']
            or sha(Path(__file__).with_name('app_smoke_install.py'))!=plan['install_helper_sha256']
            or plan['independent_review_approved']is not True or set(plan['files'])!=set(FILES)):
        raise ValueError('exact reviewed close programs and packet required')
    def window():
        if not plan['starts_at']<=time.time()<plan['ends_at']or not 0<plan['ends_at']-plan['starts_at']<=1800:
            raise ValueError('announced bounded capture-return window required')
    window()
    lock=os.open(str(ROOT/'probes/application-deploy.lock'),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        import stat
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode)or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned deployment lock required')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_no_pending_reader()
        for name,digest in plan['files'].items():
            if sha(directory/name)!=digest:raise ValueError('original capture packet changed')
        policy=json.loads(private(directory/'policy.json',10001))
        claims=json.loads(private(directory/'claims/claims.json',10001))
        if (policy['version']!='G2C-App-smoke-capture.1'or policy['source_commit']!=plan['source']
                or claims['version']!='G2C-App-smoke-claims.1'or claims['policy_sha256']!=sha(directory/'policy.json')
                or claims['state']!='STOP_NEW'and time.time()<datetime.fromisoformat(policy['ends_at']).timestamp()):
            raise ValueError('original capture must stop new work before return')
        if sha(ROOT/'probes/836-release-export.py')!=EXPORTER_SHA:raise ValueError('original exporter changed')
        static={name:sha(ROOT/name)for name in STATIC}
        claims_sha=sha(directory/'claims/claims.json')
        def unchanged():
            if(private(path)!=raw or {name:sha(ROOT/name)for name in STATIC}!=static
                    or sha(directory/'claims/claims.json')!=claims_sha
                    or any(sha(directory/name)!=digest for name,digest in plan['files'].items())):
                raise ValueError('original configuration, claims or packet drift')
        base=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),
              '-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
        def command(args):return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=180)
        def inspect(role):return json.loads(command(['docker','inspect','g2c-beta-'+role+'-1']))[0]
        expected=override(directory)['services']
        def check(installed):
            for role in('api','worker'):
                item=inspect(role);mounts={m['Destination']:m for m in item['Mounts']}
                if(item['Image']!=plan['image']or item['Config']['Labels']['org.opencontainers.image.revision']!=plan['source']
                        or item['Config']['Cmd']!=(expected[role]['command']if installed else[role])or not item['State']['Running']):
                    raise ValueError('actual original App capture roles changed')
                if installed:
                    for mount in expected[role]['volumes']:
                        actual=mounts.get(mount['target'],{})
                        if(actual.get('Source'),actual.get('RW'))!=(mount['source'],not mount.get('read_only',False)):
                            raise ValueError('original capture mount changed')
                elif any(k.startswith('/app-smoke')or k.startswith('/run/app-smoke')or k=='/tool-evidence'for k in mounts):
                    raise ValueError('capture not actually detached')
                if role=='api'and any(k in mounts for k in('/rejected-intakes','/app-smoke-evidence','/tool-evidence')):
                    raise ValueError('worker-only originals exposed to API')
                if role=='worker':
                    raw_mount=mounts.get('/rejected-intakes',{})
                    if(raw_mount.get('Source'),raw_mount.get('RW'))!=(str(ROOT/'rejected-intakes'),True):
                        raise ValueError('default private rejection sink changed')
        def proof():
            args=base+['run','--rm','--no-deps','-T','--entrypoint','python']
            for source,target in((directory/'proof-plan.json','/plan.json'),(ROOT/'probes/836-release-export.py','/export.py'),
                                  (ROOT/'budget','/budget'),(directory/'evidence','/evidence')):
                args+=['-v',str(source)+':'+target+':ro']
            value=json.loads(command(args+['migrate','-B','/export.py']))
            if value['source_commit']!=plan['source']or value['exporter_source_sha256']!=EXPORTER_SHA:
                raise ValueError('actual original close proof changed')
            return value
        before=proof();check(True);unchanged();window()
        if not idle(before):raise ValueError('actual global idle required')
        print(json.dumps(dict(state='CLOSE_PREFLIGHT_NOT_CLOSED',source=plan['source'],image=plan['image'],ledger=before['ledger'])),flush=True)
        if '--apply'not in sys.argv:return
        def stop(roles):command(base+['stop','-t','20']+roles)
        def start():command(base+['up','-d','--no-deps','api','worker'])
        def ready():
            deadline=time.monotonic()+100
            while True:
                check(False)
                if inspect('api')['State'].get('Health',{}).get('Status')=='healthy':return
                if time.monotonic()>=deadline:raise ValueError('default roles readiness UNKNOWN')
                window();time.sleep(3)
        print(json.dumps(transition(directory,before,proof,check,stop,start,ready,window,unchanged)),flush=True)
    finally:os.close(lock)


if __name__=='__main__':main()
