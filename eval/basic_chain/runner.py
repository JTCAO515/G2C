"""Legacy observation.1 orchestration controls and shared private I/O.

Actual execution uses driver_v2. This old normalized shape is retained solely
for compatibility controls; it must not publish a real release certificate.
"""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
from zoneinfo import ZoneInfo

from .judge import judge
from .plan import VERSION,check_plan, decode, packed, require, Invalid, is_sha, digest


def private_read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode)and info.st_uid==os.getuid()and info.st_nlink==1
                and stat.S_IMODE(info.st_mode)&0o077==0,'owner-only regular original file required')
        require(info.st_size<=4_500_000,'original file exceeds bound')
        with os.fdopen(fd,'rb',closefd=False)as stream:return stream.read(4_500_001)
    finally:os.close(fd)


def save(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as stream:
        stream.write(packed(value));stream.flush();os.fsync(stream.fileno())


def day_guard(now):
    require(8<=now.astimezone(ZoneInfo('Asia/Shanghai')).hour<23,'23:00–08:00: no new synthetic action')


class Programs:
    """Execute reviewed local adapter entrypoints; never shell text or a retry."""
    def __init__(self,config,directory):
        self.config=config;self.directory=directory;self.sequence=0

    def __call__(self,name,request):
        spec=self.config['programs'][name];path=Path(spec['path'])
        require(path.is_absolute()and not path.is_symlink(),'absolute adapter entrypoint required')
        info=path.stat()
        require(stat.S_ISREG(info.st_mode)and info.st_uid==os.getuid()and info.st_mode&0o022==0,
                'operator-owned non-writable adapter required')
        require(is_sha(spec['sha256'])and sha256(path.read_bytes()).hexdigest()==spec['sha256'],
                'reviewed adapter entrypoint changed')
        require(spec['qualification_ref'],'actual A/B adapter qualification reference required')
        self.sequence+=1;prefix=f'{self.sequence:03d}-{name}'
        save(self.directory/(prefix+'-request.json'),request)
        # Private disk capture bounds in-memory reads and preserves an uncertain
        # helper result. Timeouts never trigger a second UI click or remote read.
        with open(self.directory/(prefix+'-stdout.bin'),'xb',opener=_private_opener)as out, \
             open(self.directory/(prefix+'-stderr.bin'),'xb',opener=_private_opener)as err:
            try:
                result=subprocess.run([str(path)],input=packed(request),stdout=out,stderr=err,
                                      timeout=120,check=False)
            except subprocess.TimeoutExpired as error:
                raise Invalid('adapter timeout; reconcile original action before any new run')from error
        require(result.returncode==0,'adapter failed; preserve original and stop')
        return decode(private_read(self.directory/(prefix+'-stdout.bin')))


def _private_opener(path,flags):return os.open(path,flags|os.O_NOFOLLOW,0o600)


def artifacts(observation):
    """Verify original bytes supplied by the pinned producers, not PASS labels."""
    for name in ('ui','backend'):
        entries=observation[name]['artifacts']
        require(type(entries)is list and entries,'actual producer artifact references required')
        for entry in entries:
            require(is_sha(entry['sha256']),'original artifact digest required')
            require(sha256(private_read(entry['path'])).hexdigest()==entry['sha256'],'original artifact bytes changed')


def preflight(value,config,plan,step,now):
    require(value['version']=='LIO-basic-chain-preflight.1','qualified B preflight required')
    for key in ('source','image','schema','qualification_sha256'):
        require(value[key]==config['candidate'][key],'candidate/source/qualification drift')
    require(value['subject']==config['subjects'][step['locale']],'wrong synthetic subject')
    require(value['run_id']==plan['run_id']and value['plan_sha256']==digest(plan)
            and value['nonce']==step['nonce'],'window slot is not bound to this exact plan/action')
    require(value['status']=='ACTIVE'and value['authority_verified']is True
            and value['bounded_app_claims_verified']is True and value['idle_verified']is True
            and value['capture_ready']is True,'actual current B admission is not ready')
    start=datetime.fromisoformat(value['starts_at']);end=datetime.fromisoformat(value['ends_at'])
    require(start.tzinfo and end.tzinfo and start<=now<end
            and (end-start).total_seconds()<=(5400 if plan['first_setup']else 3600),
            'current bounded window required')
    require(Decimal(value['available_cny'])>=Decimal(value['required_remaining_hold_cny'])>=0,
            'actual native admission cannot cover remaining original holds')
    require(value['app']==config['app'],'preflight approved a different App')
    return dict(config['candidate'],subject=value['subject'])


def execute(plan,config,directory,*,clock=lambda:datetime.now(timezone.utc),call=None):
    require(call is not None,'legacy normalized execution is control-only; use the native v2 entry')
    check_plan(plan)
    require(plan['version']==VERSION,'legacy plans remain readable; new dispatch requires the revised source/cash profile')
    require(config['version']=='LIO-basic-chain-host.1'and config['evidence_layer']=='L2+L3',
            'qualified real host configuration required; fixtures have no execution path')
    require(config['app']==plan['app'],'plan/host App differs')
    require(config['native_authority_ref']and config['ledger_anchor_ref'],'B native authority/ledger anchor required')
    require(config['synthetic_only']is True,'synthetic account isolation required')
    directory=Path(directory);directory.mkdir(mode=0o700,parents=False,exist_ok=False)
    save(directory/'plan.json',plan)
    call=call or Programs(config,directory)
    outcomes=[];contexts={locale:dict(old_cid=plan['old_chats'].get(locale),qa_cid=None)for locale in ('zh','en')}
    stop=None;seen_attempts=set()
    for index,step in enumerate(plan['steps']):
        if stop:break
        observation=None
        try:
            day_guard(clock())
            request=dict(run_id=plan['run_id'],plan_sha256=digest(plan),step=step,context=contexts[step['locale']])
            admission=call('backend',dict(request,action='preflight'))
            context=preflight(admission,config,plan,step,clock())|contexts[step['locale']]
            if step['gate_id']=='SM01':require(context['old_cid'],'actual App old chat setup required')
            day_guard(clock())
            ui=call('app',dict(request,action='one_gate',admission_ref=admission['admission_ref']))
            observation=call('backend',dict(request,action='observe_original',ui=ui))
            require(observation['ui']==ui,'observer substituted A original UI facts')
            artifacts(observation)
            result=judge(plan,step,observation,context,config['pricing'])
            for row in observation['backend']['accounting']['attempts']:
                key=(row['ledger_id'],row['attempt_id'])
                require(key not in seen_attempts,'overlapping step accounting; aggregate UNKNOWN')
                seen_attempts.add(key)
            if result['status']=='PASS'and step['gate_id']in('SEED1','SEED2','SM02'):
                cid=observation['backend']['message']['conversation_id']
                contexts[step['locale']]['qa_cid'if step['gate_id']=='SM02'else'old_cid']=cid
        except (Invalid,KeyError,TypeError,ValueError,OSError)as error:
            result=dict(gate_id=step['gate_id'],locale=step['locale'],status='UNKNOWN',
                        reasons=['execution_stopped:'+type(error).__name__],cost=None,timing=None)
        save(directory/f'{index:02d}-{step["locale"]}-{step["gate_id"]}-result.json',result)
        outcomes.append(result)
        if result['status']!='PASS':
            stop=result
            try:call('backend',dict(action='stop_new',run_id=plan['run_id'],reason=result['status']))
            except (Invalid,KeyError,TypeError,ValueError,OSError):
                save(directory/'stop-new-UNKNOWN.json',dict(status='UNKNOWN',reason='B stop-new receipt unavailable; no further dispatch'))
    rows=[r for r in outcomes if r['gate_id'].startswith('SM')]
    for step in plan['steps'][len(outcomes):]:
        if step['kind']=='gate':rows.append(dict(gate_id=step['gate_id'],locale=step['locale'],status='UNRUN'))
    totals={status:sum(row['status']==status for row in rows)for status in ('PASS','FAIL','UNKNOWN','UNRUN')}
    # A run never infers a full bill by adding partial snapshots.
    amounts=[r.get('cost')for r in outcomes]
    complete=bool(amounts)and all(m and m['full_coverage']for m in amounts)
    cost={key:(str(sum((Decimal(m[key])for m in amounts),Decimal(0)))
               if complete and all(m[key]is not None for m in amounts)else None)
          for key in ('conservative_cny','token_estimate_cny','actual_paid_cny')}
    report=dict(version='LIO-basic-chain-control-result.1',run_id=plan['run_id'],evidence_layer='L0_CONTROL',
                app=plan['app'],candidate=config['candidate'],rows=rows,totals=totals,denominator=14,
                success_rate=f'{totals["PASS"]}/14',release_allowed=False,real_gate_status='UNRUN',
                status='PASS'if totals['PASS']==14 and not stop else(stop['status']if stop else'UNKNOWN'),
                cost=cost,fee_status='UNKNOWN_NO_SUPPLIER_INVOICE',stopped=bool(stop),
                attempt_results=outcomes,
                known_conservative_subtotal_cny=str(sum((Decimal(m['observed_conservative_cny'])
                    for m in amounts if m and m.get('observed_conservative_cny')is not None),Decimal(0))))
    save(directory/'report.json',report)
    return report
