"""B-only bounded installation of an already reviewed App-smoke packet.

Same-image capture composition only; never a source release, sender, account or
quota writer. Unknown work after ingress closure leaves both roles stopped.
Host Python 3.6 compatible; paths and all packet hashes are reviewed by R.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT=Path('/srv/g2c-beta')
CAPTURE_UID=10001
FILES=('policy.json','api.json','evidence.json','plan.json','proof-plan.json','compose.capture.json')
STATIC=('compose.env','common.env','api.env','worker.env','operator.env',
        'deploy/hk/compose.yaml','deploy/hk/compose.local-pg.yaml','control/budget/adoption.json')
EXPORTER_SHA='5c33a5c11d161a76e7fd546d935a8596bd9536e535e14e36d443921c13cab52c'


def private(path,uid=0):
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb')as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode)or info.st_uid!=uid or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned private installation packet required')
        raw=source.read(524289)
    if len(raw)>524288:raise ValueError('bounded installation packet required')
    return raw


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as output:
        output.write(json.dumps(value,sort_keys=True).encode());output.flush();os.fsync(output.fileno())
    fd=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def override(directory):
    common=[dict(type='bind',source=str(directory/name),target='/run/app-smoke/'+name,read_only=True)
            for name in('policy.json','api.json','evidence.json','plan.json')]
    return dict(services={role:dict(command=[role,'--app-smoke-api-manifest'if role=='api'else'--app-smoke-manifest',
        '/run/app-smoke/'+('api.json'if role=='api'else'policy.json')],volumes=common+[
        dict(type='bind',source=str(directory/'claims'),target='/app-smoke-claims',read_only=role=='api'),
        dict(type='bind',source=str(directory/'outer'),target='/app-smoke-outer',read_only=role=='worker')]+
        ([]if role=='api'else[dict(type='bind',source=str(directory/'evidence'),target='/app-smoke-evidence')]))
        for role in('api','worker')})


def fresh(directory,plan):
    """Validate actual container paths/inodes, not a developer-Mac preparation."""
    if set(plan['files'])!=set(FILES):raise ValueError('complete reviewed packet required')
    for name,digest in plan['files'].items():
        if hashlib.sha256(private(directory/name,CAPTURE_UID)).hexdigest()!=digest:
            raise ValueError('reviewed installation packet changed')
    for name in('claims','outer','evidence'):
        p=directory/name;info=p.lstat()
        if not stat.S_ISDIR(info.st_mode)or info.st_uid!=CAPTURE_UID or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('actual owned capture directory required')
        expected={'claims.lock','claims.json'}if name=='claims'else set()
        if {p.name for p in p.iterdir()}!=expected:raise ValueError('fresh capture directories required')
    policy=json.loads(private(directory/'policy.json',CAPTURE_UID))
    api=json.loads(private(directory/'api.json',CAPTURE_UID));evidence=json.loads(private(directory/'evidence.json',CAPTURE_UID))
    frozen=json.loads(private(directory/'plan.json',CAPTURE_UID));proof=json.loads(private(directory/'proof-plan.json',CAPTURE_UID))
    canonical=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if (policy['source_commit']!=plan['source']or policy['plan_sha256']!=hashlib.sha256(canonical(frozen)).hexdigest()
            or frozen['run_id']!=policy['window_id']or proof['cases']!=[]or proof['source_commit']!=plan['source']
            or policy['directory']!='/app-smoke-claims'or policy['evidence_manifest']!='/run/app-smoke/evidence.json'
            or api['policy_path']!='/run/app-smoke/policy.json'or api['directory']!='/app-smoke-outer'
            or api['policy_sha256']!=plan['files']['policy.json']or evidence['directory']!='/app-smoke-evidence'
            or policy['evidence_sha256']!=plan['files']['evidence.json']):
        raise ValueError('exact actual container paths and frozen source required')
    for value,name,keys in((policy,'claims',('directory_device','directory_inode')),
                          (policy,'evidence',('artifact_device','artifact_inode')),
                          (api,'outer',('directory_device','directory_inode'))):
        info=(directory/name).stat()
        if (value[keys[0]],value[keys[1]])!=(info.st_dev,info.st_ino):
            raise ValueError('actual Hong Kong directory inode required')
    claims=json.loads(private(directory/'claims/claims.json',CAPTURE_UID))
    if(claims!=dict(version='G2C-App-smoke-claims.1',policy_sha256=plan['files']['policy.json'],state='ACTIVE',claims=[])
            or json.loads(private(directory/'claims/claims.lock',CAPTURE_UID))!={}):
        raise ValueError('unconsumed original capture claims required')
    if json.loads(private(directory/'compose.capture.json',CAPTURE_UID))!=override(directory):
        raise ValueError('only role-separated App smoke mounts permitted')
    return policy


def idle(proof):
    return (proof['global_pending']==proof['global_active']==0 and
        not any(proof['background_states'].get(k,0)for k in('queued','running','publishing'))and
        not any(proof['memory_states'].get(k,0)for k in('pending','inflight')))


def require_no_pending_reader():
    pending=ROOT/'probes/qualified-reader.inflight.json'
    if pending.exists()or pending.is_symlink():
        raise ValueError('original native reader outcome pending; B reconciliation required')


def transition(directory,before,proof,check,stop,start,ready,window,unchanged):
    """Single execution; no inferred recovery or second apply after UNKNOWN."""
    if not idle(before):raise ValueError('actual global idle required')
    check(False);unchanged();window()
    save(directory/'install.intent.json',dict(state='INSTALLING',ledger=before['ledger']))
    closed=False
    try:
        closed=True;stop(['api']);window()
        drained=proof();save(directory/'install.drained.json',drained)
        if not idle(drained)or drained['ledger']!=before['ledger']:
            raise ValueError('original work arrived during ingress closure')
        unchanged();window();stop(['worker']);window();start();window();ready();window()
        check(True);unchanged();after=proof()
        if not idle(after)or after['ledger']!=before['ledger']:
            raise ValueError('original work changed during capture installation')
        save(directory/'install.result.json',dict(state='CAPTURE_INSTALLED_NOT_DISPATCH',ledger=after['ledger']))
        return after
    except BaseException:
        if closed:stop(['api','worker'])
        raise


def main():
    if len(sys.argv)not in(2,3)or len(sys.argv)==3 and sys.argv[2]!='--apply':
        raise ValueError('explicit B packet preflight or one-shot apply required')
    path=Path(sys.argv[1]);raw=private(path);plan=json.loads(raw);directory=path.parent
    if(plan['version']!='G2C-App-smoke-install.1'or sha(__file__)!=plan['reviewed_script_sha256']
            or plan['independent_review_approved']is not True):raise ValueError('exact reviewed B installation required')
    def window():
        if not plan['starts_at']<=time.time()<plan['ends_at']or not 0<plan['ends_at']-plan['starts_at']<=1800:
            raise ValueError('announced bounded installation window required')
    window()
    lock=os.open(str(ROOT/'probes/application-deploy.lock'),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode)or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned deployment lock required')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require_no_pending_reader()
        fresh(directory,plan)
        if sha(ROOT/'probes/836-release-export.py')!=EXPORTER_SHA:raise ValueError('original exporter changed')
        static={name:sha(ROOT/name)for name in STATIC}
        def unchanged():
            if(private(path)!=raw or {name:sha(ROOT/name)for name in STATIC}!=static
                    or {name:sha(directory/name)for name in FILES}!=plan['files']):
                raise ValueError('original configuration or packet drift')
        base=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),
              '-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
        def command(args):return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=180)
        def inspect(role):return json.loads(command(['docker','inspect','g2c-beta-'+role+'-1']))[0]
        expected=override(directory)['services']
        def check(installed):
            for role in('api','worker'):
                item=inspect(role)
                if (item['Image']!=plan['image']or item['Config']['Labels']['org.opencontainers.image.revision']!=plan['source']
                        or item['Config']['Cmd']!=(expected[role]['command']if installed else[role])or not item['State']['Running']):
                    raise ValueError('actual same-image App roles required')
                mounts={m['Destination']:m for m in item['Mounts']}
                if role=='api'and any(k in mounts for k in('/rejected-intakes','/app-smoke-evidence','/tool-evidence')):
                    raise ValueError('worker-only raw originals must remain private')
                if installed:
                    for mount in expected[role]['volumes']:
                        actual=mounts.get(mount['target'],{})
                        if(actual.get('Source'),actual.get('RW'))!=(mount['source'],not mount.get('read_only',False)):
                            raise ValueError('actual App smoke mount permissions changed')
                elif any(k.startswith('/app-smoke')or k.startswith('/run/app-smoke')or k=='/tool-evidence'for k in mounts):
                    raise ValueError('previous collector must be formally returned')
        def proof():
            args=base+['run','--rm','--no-deps','-T','--entrypoint','python']
            for source,target in((directory/'proof-plan.json','/plan.json'),(ROOT/'probes/836-release-export.py','/export.py'),
                                  (ROOT/'budget','/budget'),(directory/'evidence','/evidence')):
                args+=['-v',str(source)+':'+target+':ro']
            result=json.loads(command(args+['migrate','-B','/export.py']))
            if result['source_commit']!=plan['source']or result['exporter_source_sha256']!=EXPORTER_SHA:
                raise ValueError('actual original proof changed')
            return result
        before=proof();check(False);unchanged();window()
        if not idle(before):raise ValueError('actual global idle required')
        print(json.dumps(dict(state='PREFLIGHT_ONLY_NOT_ACTIVE',source=plan['source'],image=plan['image'],ledger=before['ledger'])),flush=True)
        if '--apply'not in sys.argv:return
        def stop(roles):command(base+['stop','-t','20']+roles)
        def start():command(base+['-f',str(directory/'compose.capture.json'),'up','-d','--no-deps','api','worker'])
        def ready():
            deadline=time.monotonic()+100
            while True:
                check(True)
                if inspect('api')['State'].get('Health',{}).get('Status')=='healthy':return
                if time.monotonic()>=deadline:raise ValueError('App capture readiness UNKNOWN')
                window();time.sleep(3)
        transition(directory,before,proof,check,stop,start,ready,window,unchanged)
        print('CAPTURE_INSTALLED_NOT_DISPATCH',flush=True)
    finally:os.close(lock)


if __name__=='__main__':main()
