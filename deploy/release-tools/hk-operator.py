"""Exact-source B operator transport. Application controls remain in the reviewed scripts."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser()
OLD = '2e5560cf3c794df4aff48c8431e8424330580e10'
NEW = '7f8dbe9617833a4af4900f21499a6db5616d5eb6'
OLD_IMAGE = 'sha256:0ad586bea92662028112887ba37351fb307a06717cb84e17a507039c727feeba'
NEW_IMAGE = 'sha256:8d6bc9f8edfab02a98c6c423b7654292b6f36fcdb0171995e3ba8bc069d6b467'
FORWARD_SHA = '90d802f0802080852d7af919afeef2069f88305d7d5649cea86bde3783ac78b3'
ROOT = '/srv/g2c-beta'
PREVIOUS = STATE.parent / 'b1048-m1-deploy-20261116'
SESSION = STATE.parent / 'b759-national-20261112-03/zh.jwt'
# Callers (s-build53-batch-stage.py) rebind both to the exact release checkout before use.
WORKTREE = Path.cwd()
GATE_WORKTREE = Path.cwd()
SSH = ['ssh', '-i', os.path.expanduser(os.environ.get('G2C_RELEASE_SSH_KEY', '~/.ssh/g2c-beta.pem')), '-o', 'BatchMode=yes', '-o',
       'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8', 'root@47.83.147.176']
COMPOSE = ['docker','compose','--env-file',ROOT+'/compose.env','-f',ROOT+'/deploy/hk/compose.yaml',
           '-f',ROOT+'/deploy/hk/compose.local-pg.yaml']
LOCK = ROOT+'/probes/application-deploy.lock'


def remote(args, data=None, timeout=400):
    return subprocess.run([*SSH, shlex.join(args)], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout, check=False)


def save(path, raw):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def captured(args, data=None, *, name, timeout=400):
    result = remote(args, data=data, timeout=timeout)
    save(STATE/(name+'.stdout'), result.stdout)
    save(STATE/(name+'.stderr'), result.stderr)
    return result


def safe_upload(path, raw):
    program = """import hashlib, sys
from pathlib import Path
path, expected = Path(sys.argv[1]), sys.argv[2]
content=sys.stdin.buffer.read(5000000)
if hashlib.sha256(content).hexdigest()!=expected: raise SystemExit(2)
with path.open('xb') as output:
    import os
    os.fchmod(output.fileno(), 0o600)
    output.write(content)
    output.flush()
    os.fsync(output.fileno())
"""
    result = remote(['python3','-B','-c',program,path,hashlib.sha256(raw).hexdigest()],raw,20)
    if result.returncode != 0:
        raise ValueError('exact private staging failed')


def gate(run, rollback=False):
    before = json.loads((PREVIOUS/('incident-20261118-1205-rollback-gate.json' if rollback
                                 else 'dual-7f8dbe96-actual-release-gate.json')).read_bytes())
    now = datetime.now(timezone.utc)
    if rollback:
        before.update(previous_source=NEW, previous_image_id=NEW_IMAGE,
                      authority='M4 approved compatible rollback on real server smoke FAIL/UNKNOWN',
                      reason='Observed post-deployment server smoke FAIL or UNKNOWN')
    else:
        before.update(authority='JT #495/6972695033 and M4 existing HK deployment scope',
                      reason='Exact application CI and R; post-release API smoke')
        if run!='b-smoke-20261118-01':
            before['related_reviews']=[dict(
                source='addf4d4f51ba1098e1aace128fe4f1a25edaeb13',
                pr_number=1170,review_comment=6969732819,
                review_approved_head='d5a4a3ebfa4e4deda78899da1cd327e165e37c3a') ]
    before.update(starts_at=now.isoformat(timespec='microseconds'),
                  ends_at=(now+timedelta(minutes=25)).isoformat(timespec='microseconds'))
    filename = 'rollback-gate.json' if rollback else 'forward-gate.json'
    raw = json.dumps(before,sort_keys=True).encode()
    save(STATE/(run+'-'+filename), raw)
    safe_upload(ROOT+'/probes/'+run+'/'+filename, raw)
    print(json.dumps(dict(starts_at=before['starts_at'], ends_at=before['ends_at'])))


def run_bootstrap(head):
    def read(path):
        return subprocess.check_output(['git','show',head+':deploy/hk/'+path],cwd=WORKTREE).decode()
    smoke = read('server_smoke.py')
    modules = [
        ('deploy.hk.app_smoke_ceiling', subprocess.check_output(
            ['git','show',NEW+':deploy/hk/app_smoke_ceiling.py'],cwd=WORKTREE).decode()),
        ('deploy.hk.server_smoke_budget', read('server_smoke_budget.py')),
    ]
    return ("import sys, types\n"
            f"for name, source in {modules!r}:\n"
            "    module=types.ModuleType(name)\n"
            "    sys.modules[name]=module\n"
            "    exec(compile(source, name, 'exec'), module.__dict__)\n"
            f"exec(compile({smoke!r}, 'server_smoke.py', 'exec'), globals())\n")


def smoke_action(run, phase, head, permit_file=None):
    before = json.loads((STATE/(run+'-forward-gate.json')).read_bytes())
    packet = {'starts_at':before['starts_at'],'ends_at':before['ends_at']}
    if phase == 'restore':
        data = Path(permit_file).read_bytes()
    else:
        if stat.S_IMODE(SESSION.stat().st_mode) != 0o600 or SESSION.is_symlink():
            raise ValueError('existing private C session required')
        packet['access_token'] = SESSION.read_text().strip()
        data = json.dumps(packet).encode()
    code = run_bootstrap(head)
    program = """import json,subprocess,sys
rev,img,code,phase=sys.argv[1:]
for role in ('api','worker'):
    view=subprocess.check_output(['docker','inspect','--format',
        '{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Image}} {{.State.Running}}',
        'g2c-beta-'+role+'-1'], universal_newlines=True).strip()
    if view.split()!=[rev,img,'true']:raise SystemExit(2)
raise SystemExit(subprocess.call(['docker','exec','-i','g2c-beta-worker-1','python','-B','-c',code,phase]))
"""
    source, image = (OLD, OLD_IMAGE) if phase=='preflight' else (NEW, NEW_IMAGE)
    result = captured(['flock','-n',LOCK,'python3','-B','-c',program,source,image,code,phase],
                      data, name=run+'-smoke-'+phase, timeout=600)
    print(json.dumps(dict(phase=phase, exit=result.returncode,
                          records=[(row.get('kind'),row.get('case'),row.get('status'),row.get('reason'))
                                   for line in result.stdout.splitlines() if line.startswith(b'{')
                                   for row in [json.loads(line)]])))
    return result.returncode


def filtered_wire(run):
    before = json.loads((STATE/(run+'-forward-gate.json')).read_bytes())
    program = """import subprocess,sys
p=subprocess.Popen(['docker','logs','--since',sys.argv[1],'g2c-beta-worker-1'],
                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT, universal_newlines=True)
for line in p.stdout:
    if line.lstrip().startswith(('M4_MODEL_WIRE_TIMING attempt_sha256=',
            'M4_MODEL_IDENTITY_REJECTION attempt_sha256=', 'M4_MODEL_UNKNOWN attempt_sha256=')):
        print(line.rstrip())
raise SystemExit(p.wait())
"""
    result = captured(['python3','-B','-c',program,before['starts_at']],name=run+'-wire',timeout=60)
    if result.returncode:
        raise ValueError('wire metadata unavailable')
    print('Filtered wire metadata saved')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run')
    parser.add_argument('phase',choices=('stage','stage-permanent','gate','rollback-gate','preflight','apply',
        'readback','rollback-readback','timings','weekly','drain','rollback-preflight','rollback-apply','smoke-preflight','smoke-run','smoke-restore','wire'))
    parser.add_argument('--head')
    parser.add_argument('--release-head')
    parser.add_argument('--permit-file')
    args=parser.parse_args()
    run, phase=args.run,args.phase
    if not run.startswith('b-smoke-20261118-') or not run.rsplit('-',1)[-1].isdigit():
        raise ValueError('unique fixed B operation id required')
    path=ROOT+'/probes/'+run
    if phase == 'stage-permanent':
        if run=='b-smoke-20261118-01' or not args.release_head:
            raise ValueError('permanent exact-head bundle required')
        result=remote(['mkdir','-m','0700',path],timeout=20)
        if result.returncode:
            raise ValueError('unique staging directory required; inspect previous operation')
        for name in ('application_release.py','application_release_host.py'):
            code=subprocess.check_output(
                ['git','show',args.release_head+':deploy/hk/'+name],cwd=GATE_WORKTREE)
            safe_upload(path+'/'+name,code)
        save(STATE/(run+'-bundle.json'),json.dumps({'release_head':args.release_head}).encode())
        print('Versioned permanent host release bundle staged')
    elif phase == 'stage':
        if run!='b-smoke-20261118-01':
            raise ValueError('one-time candidate is already spent')
        script=(PREVIOUS/'dual-7f8dbe96-release-observe-candidate.py').read_bytes()
        if hashlib.sha256(script).hexdigest() != FORWARD_SHA:
            raise ValueError('reviewed exact script changed')
        result=remote(['mkdir','-m','0700',path],timeout=20)
        if result.returncode:
            raise ValueError('unique staging directory required; inspect previous operation')
        safe_upload(path+'/forward.py', script)
        print('Exact one-time candidate staged')
    elif phase in ('gate','rollback-gate'):
        gate(run, rollback=phase=='rollback-gate')
    elif phase in ('preflight','apply'):
        script = 'forward.py' if run=='b-smoke-20261118-01' else 'application_release_host.py'
        if run!='b-smoke-20261118-01':
            bundle=json.loads((STATE/(run+'-bundle.json')).read_bytes())
            for name in ('application_release.py', script):
                code=subprocess.check_output(
                    ['git','show',bundle['release_head']+':deploy/hk/'+name],cwd=GATE_WORKTREE)
                actual=remote(['sha256sum',path+'/'+name],timeout=20)
                if actual.returncode or actual.stdout.split()[0].decode()!=hashlib.sha256(code).hexdigest():
                    raise ValueError('permanent host release program differs from its merged bundle')
        command=['python3','-B',path+'/'+script,path+'/forward-gate.json']
        if phase=='apply':
            command+=['--apply']
        result=captured(command,name=run+'-'+phase,timeout=300)
        print(result.stdout.decode())
        return result.returncode
    elif phase in ('readback','rollback-readback'):
        program = """import json,subprocess
def run(args):return subprocess.check_output(args, universal_newlines=True).strip()
fmt='{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}'
print(json.dumps({r:run(['docker','inspect','--format',fmt,'g2c-beta-'+r+'-1'])
                  for r in ('api','worker')}))
"""
        result=captured(['python3','-B','-c',program],name=run+'-'+phase,timeout=60)
        print(result.stdout.decode())
        return result.returncode
    elif phase=='weekly':
        source=(CODE / 'weekly-run-metadata.py').read_text()
        result=captured([*COMPOSE, 'run','--rm','--no-deps','-T','--entrypoint','python',
                         'migrate','-B','-c',source],name=run+'-'+phase,timeout=60)
        print(result.stdout.decode())
        return result.returncode
    elif phase=='timings':
        gate_info=json.loads((STATE/(run+'-forward-gate.json')).read_bytes())
        queries=[dict(case=row['case'],message_id=row.get('message_id'),request_id=row.get('message_ref'))
                 for line in (STATE/(run+'-smoke-run.stdout')).read_bytes().splitlines()
                 for row in [json.loads(line)] if row.get('kind')=='case']
        program = '''import json,re,sys
from pathlib import Path
day=sys.argv[1]
assert re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',day)
queries=json.load(sys.stdin)
path=Path('/srv/g2c-beta/access-log')/('access-'+day+'.jsonl')
records=[]
if path.is_file():
    with path.open() as source:
        for line in source:
            row=json.loads(line)
            if row.get('v')=='G2C-HK-access-log.2' and row.get('method')=='POST':
                records.append(row)
result=[]
for query in queries:
    sample=dict(case=query['case'],message_id=query['message_id'],api_started_at=None)
    result.append(sample)
    if not query['request_id'] or not query['message_id']:continue
    finished=[row for row in records if row.get('phase')=='finished'
              and row.get('request_id')==query['request_id'] and row.get('status')==200
              and row.get('route') in ('/v1/lio/messages','/v2/lio/messages')]
    if len(finished)!=1:continue
    start=[row for row in records if row.get('phase')=='started'
           and row.get('exchange_id')==finished[0]['exchange_id']]
    if len(start)!=1 or start[0]['ts']!=finished[0]['ts']:continue
    sample['api_started_at']=start[0]['ts']
print(json.dumps(result))
'''
        matched=remote(['python3','-B','-c',program,gate_info['starts_at'][:10]],
                       json.dumps(queries).encode(),30)
        if matched.returncode:
            raise ValueError('original HTTP timeline metadata unavailable')
        source=(CODE / 'smoke-run-latency.py').read_text()
        result=captured([*COMPOSE,'run','--rm','--no-deps','-T','--entrypoint','python',
                         'migrate','-B','-c',source],matched.stdout,name=run+'-timings',timeout=70)
        print(result.stdout.decode())
        return result.returncode
    elif phase=='drain':
        plan = ROOT+'/probes/836-platform-release-proof-plan.json'
        program = '''import json,subprocess,sys
cp=subprocess.run(sys.argv[1:], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
view=json.loads(cp.stdout)
print(json.dumps({k:view[k] for k in ('ledger','global_pending','global_active','background_states','memory_states')}))
'''
        cmd = [*COMPOSE,'run','--rm','--no-deps','-T','--entrypoint','python',
               '-v',plan+':/plan.json:ro',
               '-v',ROOT+'/probes/836-release-export.py:/export.py:ro',
               '-v',ROOT+'/budget:/budget:ro',
               '-v',ROOT+'/836-platform-release-evidence:/evidence:ro',
               'migrate','-B','/export.py']
        result=captured(['python3','-B','-c',program,*cmd],name=run+'-drain',timeout=70)
        print(result.stdout.decode())
        return result.returncode
    elif phase in ('rollback-preflight','rollback-apply'):
        approved='app-release-idle55-compat3-gatebytes-20261117.py'
        script=ROOT+'/quota-self-service-20261112/'+approved
        expected=hashlib.sha256((PREVIOUS/approved).read_bytes()).hexdigest()
        actual=remote(['sha256sum',script],timeout=20)
        if actual.returncode or actual.stdout.split()[0].decode()!=expected:
            raise ValueError('original approved rollback tool changed')
        command=['python3','-B',script,path+'/rollback-gate.json']
        if phase=='rollback-apply':
            command.append('--apply')
        result=captured(command,name=run+'-'+phase,timeout=300)
        print(result.stdout.decode())
        return result.returncode
    elif phase=='wire':
        filtered_wire(run)
    elif phase.startswith('smoke-'):
        if not args.head:
            raise ValueError('reviewed exact smoke head required')
        return smoke_action(run, phase[6:], args.head,args.permit_file)
    return 0


if __name__=='__main__':raise SystemExit(main())
