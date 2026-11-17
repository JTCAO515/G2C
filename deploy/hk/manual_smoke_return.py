"""B-only return of C100 after a zero-business manual startup failure.

This accepts the actual manual close, never an invented automatic close. An
explicit reviewed tool image supplies the native restore module when the
compatible serving rollback image predates it. No application is deployed.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

if __package__ in(None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from deploy.hk.app_smoke_install import ROOT,private,save,sha,require_no_pending_reader,idle,EXPORTER_SHA
from deploy.hk.app_smoke_restore import roles

VERSION='G2C-App-manual-smoke-standing-return-plan.1'
NATIVE='G2C-App-manual-smoke-closed-standing-restore.1'
STATIC=('compose.env','common.env','worker.env','deploy/hk/compose.yaml','deploy/hk/compose.local-pg.yaml')


def perform(directory,plan,closed,stopped,restriction,inspect,proof,native,*,apply):
    if(closed.get('version')!='B-manual14-close.1'or closed.get('state')!='CLOSED_FAIL_ROLLED_BACK'
            or closed.get('lease_id')!=plan['window_id']or type(closed.get('message_delta'))is not int
            or closed['message_delta']!=0 or closed.get('verdict')!='FAIL_LOGIN_UI'
            or closed.get('standing_budget_restored')is not False
            or stopped.get('state')!='STOP_NEW'or closed.get('verdict')!=stopped.get('verdict')):
        raise ValueError('actual stopped zero-business manual close required')
    rollback=closed['rollback'];cutover=rollback['cutover']
    if(rollback['state']!='ROLLBACK_VERIFIED'or cutover['stage']!='CUTOVER_PASS'
            or(cutover['source'],cutover['image'])!=(plan['source'],plan['image'])
            or cutover['ledger_unchanged']is not True or cutover['ledger_before']!=cutover['ledger_after']
            or cutover['ledger_after']!=restriction['original_ledger']
            or type(cutover['pending'])is not int or type(cutover['active'])is not int
            or cutover['pending']!=0 or cutover['active']!=0
            or not idle(dict(global_pending=cutover['pending'],global_active=cutover['active'],
                background_states=cutover['background_states'],memory_states=cutover['memory_states']))):
        raise ValueError('verified original rollback and unchanged ledger required')
    before=roles(plan,inspect)
    current=proof()
    if not idle(current)or current['ledger']!=cutover['ledger_after']:
        raise ValueError('fresh original ledger and empty in-flight work required')
    request=dict(version=NATIVE,expected_policy_sha256=plan['restricted_policy_sha256'],
        restriction=restriction,closed_manual_sha256=plan['close_sha256'],
        expected_ledger=current['ledger'],ledger_id=plan['ledger_id'],
        producer_id=plan['producer_id'],apply=apply)
    if apply:save(directory/'manual-standing-return.intent.json',dict(window_id=plan['window_id'],
        source=plan['source'],image=plan['image'],tool_image=plan['tool_image'],
        closed_manual_sha256=plan['close_sha256'],ledger=current['ledger']))
    result=native(request)
    after=proof()
    if roles(plan,inspect)!=before or not idle(after)or after['ledger']!=current['ledger']:
        raise ValueError('manual return state changed; inspect original outcome only')
    expected='C_ORIGINAL_STANDING_RESTORED_ACKED'if apply else'READONLY_NOT_RESTORED'
    if(result.get('version')!='G2C-App-manual-smoke-closed-standing-result.1'
            or result.get('state')!=expected or result.get('ledger')!=current['ledger']):
        raise ValueError('native manual return acknowledgement required')
    if apply:save(directory/'manual-standing-return.result.json',result)
    return result


def tool_command(plan):
    return ['docker','run','--rm','-i','--pull=never','--network=none','--read-only','--tmpfs','/tmp',
        '--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--memory','128m','--cpus','.25','--pids-limit','128',
        '--env-file',str(ROOT/'common.env'),'-e','CJ_M4_BUDGET_PRODUCER=hk-beta-47.83.147.176',
        '-v',str(ROOT/'worker.env')+':/run/secrets/worker.env:ro',
        '-v',str(ROOT/'control')+':/control:ro',
        '-v',str(ROOT/'control/budget')+':/control/budget',
        '-v',str(ROOT/'budget')+':/home/cj/.local/share/g2c/m4-real-services',
        '--entrypoint','python',plan['tool_image'],'-B','-m','deploy.hk.app_smoke_restore_worker']


def main():
    if os.geteuid()!=0 or len(sys.argv)not in(2,3)or len(sys.argv)==3 and sys.argv[2]!='--apply':
        raise ValueError('B root explicit manual return preflight or one-shot apply required')
    path=Path(sys.argv[1]);raw=private(path);plan=json.loads(raw);directory=path.parent
    if(plan['version']!=VERSION or plan['independent_review_approved']is not True
            or sha(__file__)!=plan['reviewed_script_sha256']
            or re.fullmatch('sha256:[a-f0-9]{64}',plan['tool_image'])is None
            or re.fullmatch('[a-f0-9]{40}',plan['tool_source'])is None):
        raise ValueError('exact reviewed manual return and immutable tool image required')
    def window():
        if not plan['starts_at']<=time.time()<plan['ends_at']or not 0<plan['ends_at']-plan['starts_at']<=1800:
            raise ValueError('current bounded manual return window required')
    window();lock=os.open(str(ROOT/'probes/application-deploy.lock'),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        import stat
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode)or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
            raise ValueError('owned deployment lock required')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);require_no_pending_reader()
        def command(args,**kw):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,**kw).stdout
        def inspect(role):return json.loads(command(['docker','inspect','g2c-beta-'+role+'-1']))[0]
        fixed={'close.result.json':plan['close_sha256'],'stop.result.json':plan['stop_sha256'],
               'restriction.result.json':plan['restriction_sha256']}
        values={name:private(directory/name)for name in fixed}
        if any(hashlib.sha256(values[name]).hexdigest()!=digest for name,digest in fixed.items()):
            raise ValueError('reviewed original manual return evidence changed')
        static={name:sha(ROOT/name)for name in STATIC}
        def unchanged():
            window()
            if(private(path)!=raw or {name:sha(ROOT/name)for name in STATIC}!=static
                    or any(private(directory/name)!=value for name,value in values.items())):
                raise ValueError('manual return configuration or evidence drift')
        image=json.loads(command(['docker','image','inspect',plan['tool_image']]))[0]
        if(image['Id']!=plan['tool_image']or image['Architecture']!='amd64'
                or image['Config']['Labels']['org.opencontainers.image.revision']!=plan['tool_source']):
            raise ValueError('actual reviewed tool source/image required')
        check="from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/app/deploy/hk/app_smoke_restore_worker.py').read_bytes()).hexdigest())"
        actual=command(['docker','run','--rm','--pull=never','--network=none','--read-only',
            '--user','10001:10001','--entrypoint','python',plan['tool_image'],'-B','-c',check]).decode().strip()
        if actual!=plan['native_module_sha256']:raise ValueError('reviewed native return module changed')
        base=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),
              '-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
        def proof():
            unchanged()
            if sha(ROOT/'probes/836-release-export.py')!=EXPORTER_SHA:
                raise ValueError('original read-only exporter changed')
            if(json.loads((ROOT/'probes/836-platform-release-proof-plan.json').read_bytes())['cases']!=[]
                    or list((ROOT/'836-platform-release-evidence').glob('*.json'))):
                raise ValueError('metadata-only original idle export required')
            value=json.loads(command(base+['run','--rm','--no-deps','-T','--entrypoint','python',
                '-v',str(ROOT/'probes/836-platform-release-proof-plan.json')+':/plan.json:ro',
                '-v',str(ROOT/'probes/836-release-export.py')+':/export.py:ro',
                '-v',str(ROOT/'budget')+':/budget:ro',
                '-v',str(ROOT/'836-platform-release-evidence')+':/evidence:ro','migrate','-B','/export.py']))
            if value['observations']!=[]or value['artifacts']!=[]or value['shared_outflows']!={}:
                raise ValueError('metadata-only original export required')
            return value
        def native(request):
            unchanged()
            result=json.loads(command(tool_command(plan),input=json.dumps(request).encode()))
            unchanged();return result
        print(json.dumps(perform(directory,plan,json.loads(values['close.result.json']),
            json.loads(values['stop.result.json']),json.loads(values['restriction.result.json']),
            inspect,proof,native,apply='--apply'in sys.argv)),flush=True)
    finally:os.close(lock)


if __name__=='__main__':main()
