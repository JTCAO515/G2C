"""B-only return of original C100 after an acknowledged manual close.

Version1 retains the zero-business startup-failure path. Version2 additionally
checks full before/after inventories for a bounded ordinary business window.
Both accept the actual manual close, never an invented automatic close. An
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
BUSINESS_VERSION='G2C-App-manual-smoke-standing-return-plan.2'
NATIVE='G2C-App-manual-smoke-closed-standing-restore.1'
STATIC=('compose.env','common.env','worker.env','deploy/hk/compose.yaml','deploy/hk/compose.local-pg.yaml')


def business_closed_ledger(plan,closed,stopped,restriction,before_metadata,after_metadata):
    """Verify the real manual close; never impersonate automatic capture return."""
    for key in('ledger_before','ledger_after'):
        anchor=closed.get(key)
        if(type(anchor)is not dict or set(anchor)!={'count','sha256'}
                or type(anchor['count'])is not int or anchor['count']<0
                or type(anchor['sha256'])is not str or re.fullmatch('[a-f0-9]{64}',anchor['sha256'])is None):
            raise ValueError('complete original manual-close ledger anchors required')
    if(plan.get('version')!=BUSINESS_VERSION or closed.get('version')!='B-manual14-close.2'
            or closed.get('lease_id')!=plan['window_id']
            or closed.get('standing_budget_restored')is not False
            or stopped.get('state')!='STOP_NEW'or stopped.get('verdict')!=closed.get('verdict')
            or closed.get('ledger_before')!=restriction['original_ledger']
            or(closed.get('tested_source'),closed.get('tested_image'))!=(plan['tested_source'],plan['tested_image'])):
        raise ValueError('actual stopped manual business close required')
    if(type(plan['tested_source'])is not str or re.fullmatch('[a-f0-9]{40}',plan['tested_source'])is None
            or type(plan['tested_image'])is not str or re.fullmatch('sha256:[a-f0-9]{64}',plan['tested_image'])is None
            or(restriction.get('model_call_bound'),restriction.get('tool_call_bound'),
               restriction.get('cash_ceiling_cny'))!=(40,32,60)):
        raise ValueError('original ordinary manual purpose and tested source required')
    inventories=[]
    for value in(before_metadata,after_metadata):
        if(type(value)is not dict or value.get('subject')!=plan['subject']
                or type(value.get('messages'))is not list or len(value['messages'])>512):
            raise ValueError('complete same-owner manual inventories required')
        records={}
        for row in value['messages']:
            if(type(row)is not dict or type(row.get('message_id'))is not str
                    or not 0<len(row['message_id'])<=256 or row['message_id']in records):
                raise ValueError('unique original message inventory required')
            records[row['message_id']]=row
        inventories.append(records)
    before,after=inventories
    if any(after.get(mid)!=row for mid,row in before.items()):
        raise ValueError('original manual history changed')
    new=set(after)-set(before);selected=closed.get('message_ids');count=closed.get('message_delta')
    if(type(selected)is not list or any(type(mid)is not str for mid in selected)
            or len(set(selected))!=len(selected)or set(selected)!=new
            or type(count)is not int or count!=len(new)or not 0<=count<=8):
        raise ValueError('complete bounded actual new-message set required')
    if closed.get('state')=='CLOSED_PASS':
        if(closed.get('verdict')!='PASS'or count!=8 or closed.get('rollback')is not None
                or(plan['source'],plan['image'])!=(plan['tested_source'],plan['tested_image'])
                or any(sum(after[mid].get('locale')==locale for mid in new)!=4 for locale in('zh','en'))):
            raise ValueError('actual bilingual manual pass close required')
    elif closed.get('state')=='CLOSED_FAIL_ROLLED_BACK':
        if closed.get('verdict')not in('FAIL','UNKNOWN'):
            raise ValueError('actual manual failure verdict required')
        rollback=closed['rollback'];cutover=rollback['cutover']
        if(rollback.get('state')!='ROLLBACK_VERIFIED'or cutover.get('stage')!='CUTOVER_PASS'
                or(cutover.get('source'),cutover.get('image'))!=(plan['source'],plan['image'])
                or cutover.get('ledger_unchanged')is not True
                or cutover.get('ledger_before')!=cutover.get('ledger_after')
                or cutover.get('ledger_after')!=closed['ledger_after']
                or type(cutover.get('pending'))is not int or type(cutover.get('active'))is not int
                or cutover['pending']!=0 or cutover['active']!=0
                or not idle(dict(global_pending=cutover['pending'],global_active=cutover['active'],
                    background_states=cutover['background_states'],memory_states=cutover['memory_states']))):
            raise ValueError('actual manual failure rollback required')
    else:raise ValueError('actual ended manual window required')
    return closed['ledger_after']


def perform(directory,plan,closed,stopped,restriction,inspect,proof,native,*,apply,
            before_metadata=None,after_metadata=None):
    if plan.get('version')==BUSINESS_VERSION:
        anchor=business_closed_ledger(plan,closed,stopped,restriction,before_metadata,after_metadata)
        return return_standing(directory,plan,anchor,inspect,proof,native,restriction,apply=apply)
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
    return return_standing(directory,plan,cutover['ledger_after'],inspect,proof,native,restriction,apply=apply)


def return_standing(directory,plan,anchor,inspect,proof,native,restriction,*,apply):
    before=roles(plan,inspect)
    current=proof()
    if not idle(current)or current['ledger']!=anchor:
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
    if(plan['version']not in(VERSION,BUSINESS_VERSION)or plan['independent_review_approved']is not True
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
        if plan['version']==BUSINESS_VERSION:
            fixed.update({'before.metadata.json':plan['before_metadata_sha256'],
                          'after.metadata.json':plan['after_metadata_sha256']})
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
        inventories={}if plan['version']==VERSION else dict(
            before_metadata=json.loads(values['before.metadata.json']),
            after_metadata=json.loads(values['after.metadata.json']))
        print(json.dumps(perform(directory,plan,json.loads(values['close.result.json']),
            json.loads(values['stop.result.json']),json.loads(values['restriction.result.json']),
            inspect,proof,native,apply='--apply'in sys.argv,**inventories)),flush=True)
    finally:os.close(lock)


if __name__=='__main__':main()
