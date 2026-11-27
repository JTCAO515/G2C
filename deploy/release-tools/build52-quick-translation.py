"""One-time, same-source translation smoke after the Build 52 roster activation."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from uuid import uuid4

from cj_api.translation import VERSION
from cj_strict_json import compact
from deploy.hk.demo_login import ROLLING_VERSION, invitation_subject
from deploy.hk.plugin_roster import generate_plugin_subjects



CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser().resolve()
SAMPLES = STATE.parent/'b1048-m1-deploy-20261116/A1124-198-shortcode-samples-20261117'
PLAN = STATE/'translation-supplement-20261123-fixtures/build52-translation-plan.json'
PLAN_SHA = 'fb882be12056777f16977f44025cb36d0719fa5400085b675c71a82d9b05a624'
WORKER = CODE / 'build52-quick-translation-worker.py'
LIMIT = 300 * 10_000_000
ROLES = """import json,subprocess,sys
if not __debug__:
 raise SystemExit(2)
source,image,program=sys.argv[1:]
fmt='{{index .Config.Labels "org.opencontainers.image.revision"}}\\t{{.Image}}\\t{{.State.Running}}\\t{{json .Config.Cmd}}'
for role in ('api','worker'):
 row=subprocess.check_output(['docker','inspect','--format',fmt,'g2c-beta-'+role+'-1'],timeout=15)
 actual=row.decode().strip().split('\\t')
 assert actual[:3]==[source,image,'true'] and json.loads(actual[3])==[role]
raise SystemExit(subprocess.call(['docker','exec','-i','g2c-beta-worker-1','python','-B','-c',program]))
"""


def private(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('private_smoke_input_required')
    return path.read_bytes()


LOGIN = r"""
import json,os,sys
from datetime import datetime,timezone
from urllib.request import Request,build_opener
from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS,load_secret_environment
from deploy.hk.demo_login import ROLLING_VERSION,invitation_subject
from deploy.hk.plugin_roster import configured_plugin_subjects
from deploy.hk.server_smoke import NoRedirect,ORIGIN
from deploy.hk.translation_relay import translation_state
from cj_strict_json import compact

try:
 if not __debug__:
  raise ValueError('non_optimized_worker_required')
 packet=json.load(sys.stdin)
 load_secret_environment('worker')
 roster=configured_plugin_subjects(os.environ[TRANSLATION_INTERNAL_SUBJECTS])
 assert translation_state() is True
 subject=invitation_subject(packet['code'])
 assert subject is not None and subject==packet['subject']
 assert (subject in roster) is packet['expected_member']
 start,end=[datetime.fromisoformat(packet[n]) for n in ('starts_at','ends_at')]
 now=datetime.now(timezone.utc)
 assert start<=now and (end-now).total_seconds()>=12
 raw=compact(dict(version=ROLLING_VERSION, invite_code=packet['code']))
 req=Request(ORIGIN+'/v2/demo-invite-sessions', data=raw,method='POST',
             headers={'Content-Type':'application/json'})
 with build_opener(NoRedirect()).open(req,timeout=10) as response:
  result=response.read(8193)
  assert response.status==200 and len(result)<=8192
 grant=json.loads(result)
 assert grant['version']==ROLLING_VERSION and grant['subject']==subject
 assert datetime.fromisoformat(grant['expires_at'].replace('Z','+00:00'))>=end
 print(json.dumps(dict(subject=subject,credential=grant['access_token'])),flush=True)
except Exception:
 raise SystemExit(2) from None
"""


def login(path, envelope, ops, *, expected_member):
    code = private(path).decode('ascii').strip()
    subject = invitation_subject(code)
    if subject is None or (subject in generate_plugin_subjects()) != expected_member:
        raise ValueError('wrong_frozen_login_group')
    request = compact(dict(code=code,subject=subject,expected_member=expected_member,
                           starts_at=envelope['starts_at'],ends_at=envelope['ends_at']))
    # Capture strictly in memory. The durable capture helper writes stdout to a file.
    response = ops['remote'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',
        ROLES,envelope['source'],envelope['image'],LOGIN],request,timeout=38)
    if response.returncode != 0:
        raise ValueError('roster_smoke_admission_unverified')
    grant = json.loads(response.stdout)
    if grant.get('subject') != subject or not isinstance(grant.get('credential'),str):
        raise ValueError('wrong_qualified_smoke_group')
    return grant


def main():
    if not __debug__:
        raise ValueError('non_optimized_interpreter_required')
    (envelope_path,) = sys.argv[1:]
    envelope = json.loads(private(Path(envelope_path)))
    source,image = (envelope[k] for k in ('source','image'))
    if not re.fullmatch('[0-9a-f]{40}',source) or not re.fullmatch('sha256:[0-9a-f]{64}',image):
        raise ValueError('same_source_required')
    start,end = (datetime.fromisoformat(envelope[k]) for k in ('starts_at','ends_at'))
    if not 0 < (end-start).total_seconds() <= 1800 or not start <= datetime.now(timezone.utc)<end:
        raise ValueError('approved_smoke_window_required')
    activation_raw = private(Path(envelope['activation_receipt']))
    proof_raw = private(Path(envelope['fixed_smoke_receipt']))
    if (sha256(activation_raw).hexdigest()!=envelope['activation_sha256']
            or sha256(proof_raw).hexdigest()!=envelope['fixed_smoke_sha256']):
        raise ValueError('operator_receipts_differ_from_approved_envelope')
    activation,proof = json.loads(activation_raw),json.loads(proof_raw)
    if (activation['source'],activation['image'],activation['phase'],activation['translation_roster_count']) != (
            source,image,'APPLIED',99) or (proof.get('kind'),proof.get('source'),proof.get('image'),proof.get('status'),proof.get('budget_restored')) != ('build52-quick-chat',source,image,'PASS',True):
        raise ValueError('approved_roster_and_fixed_smoke_required')

    original_plan = private(PLAN)
    program = WORKER.read_bytes()
    if sha256(original_plan).hexdigest()!=PLAN_SHA:
        raise ValueError('frozen_fixtures_changed')
    cases = json.loads(original_plan)['cases']
    if [r['case'] for r in cases] != ['text.zh','text.en','image.zh','speech.en']:
        raise ValueError('unexpected_frozen_plan')
    operator=CODE / 'hk-operator.py'
    original_operator=operator.read_bytes()
    ops={'__file__':str(operator),'__name__':'pinned_hk_operator'}
    exec(compile(original_operator,str(operator),'exec'),ops)
    prefix='build52-quick-translation-'+source[:8]
    ops['save'](STATE/(prefix+'-batch-intent.json'),compact(dict(
        source=source,image=image,starts_at=envelope['starts_at'],ends_at=envelope['ends_at'],plan_sha256=PLAN_SHA)))
    g2c=login(SAMPLES/'group-g2c.invite',envelope,ops,expected_member=True)
    row=cases[0]
    plan=[(row['case'],row['document'],g2c)]
    results=[]
    spent=0
    stopped=False
    for case,document,actor in plan:
        file_prefix=prefix+'-'+case
        if stopped or (end-datetime.now(timezone.utc)).total_seconds()<80:
            row=dict(case=case,status='UNRUN',reason='earlier_nonpass_or_window_closed')
        else:
            ops['save'](STATE/(file_prefix+'-intent.json'),compact(dict(
                source=source,image=image,case=case,request_id=document['request_id'],
                payload_sha256=sha256(compact(document,sort_keys=True)).hexdigest())))
            try:
                receipt=ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',
                    ROLES,source,image,program.decode()],
                    compact(dict(case=case,document=document,ends_at=envelope['ends_at'],**actor)),name=file_prefix,timeout=80)
                row=json.loads(receipt.stdout) if receipt.returncode==0 else None
            except (OSError,subprocess.TimeoutExpired,ValueError):
                row=None
            if (type(row) is not dict or row.get('case')!=case
                    or row.get('request_sha256')!=sha256(document['request_id'].replace('-','').encode()).hexdigest()
                    or row.get('status') not in {'PASS','FAIL','UNKNOWN'}
                    or row.get('within_translation_ceiling') is not True
                    or row.get('exact_translation_subledger') is not True):
                row=dict(case=case,status='UNKNOWN',reason='read_back_original_request_and_journal',
                         fees=dict(paid='UNKNOWN',observed_only=True))
            else:
                amount=row['fees']['conservative_cny_1e7']
                if type(amount) is not int or amount<0:
                    raise ValueError('original_receipt_unusable')
                spent+=amount
                if spent>LIMIT:
                    row['status']='UNKNOWN'
                    row['reason']='translation_authorization_limit'
                    row['fees'].update(paid='UNKNOWN',observed_only=True)
        stopped = stopped or row['status']!='PASS'
        ops['save'](STATE/(file_prefix+'-result.json'),compact(row,sort_keys=True))
        results.append(row)
        print(json.dumps(row,ensure_ascii=False),flush=True)
    ops['save'](STATE/(prefix+'-final.json'),compact(dict(source=source,image=image,
        activation_sha256=sha256(activation_raw).hexdigest(),
        status='PASS' if all(r['status']=='PASS' for r in results) else 'NEEDS_ORIGINAL_READBACK',
        cases=results,conservative_cny_1e7=spent),sort_keys=True))


if __name__=='__main__':
    try:
        main()
    except Exception:
        print(json.dumps(dict(status='UNKNOWN',reason='build52_probe_requires_original_state_review')),flush=True)
        raise SystemExit(2) from None
