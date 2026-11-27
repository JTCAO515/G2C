"""Run the reviewed quick smoke on a new image with the existing plugin settings."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import sys

from cj_strict_json import compact


CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser().resolve()
CONFIG_READBACK = """
import json,subprocess,sys
source,image=sys.argv[1:]
fmt='{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}'
config = '''
import os,stat,sys
from pathlib import Path
from deploy.hk.configuration import DIDI_MCP_KEY,TAXI_INTERNAL_SUBJECTS,TRANSLATION_INTERNAL_SUBJECTS,load_secret_environment
from deploy.hk.plugin_roster import configured_plugin_subjects,configured_translation_subjects
role=sys.argv[1]
load_secret_environment(role)
assert os.getuid()==10001
if role=='api':
    assert len(configured_plugin_subjects(os.environ[TAXI_INTERNAL_SUBJECTS]))==99
    assert os.environ.get(DIDI_MCP_KEY)
    from deploy.hk.taxi_runtime import COUNTS
    for path,kind,mode in ((COUNTS.parent,stat.S_ISDIR,0o700),(COUNTS,stat.S_ISREG,0o600)):
        info=path.lstat()
        assert kind(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==mode
    assert info.st_nlink==1
else:
    from deploy.hk.translation_relay import translation_state
    assert translation_state() is True
    assert len(configured_translation_subjects(os.environ[TRANSLATION_INTERNAL_SUBJECTS]))==101
'''
for role in ('api','worker'):
    name='g2c-beta-'+role+'-1'
    actual=subprocess.check_output(['docker','inspect','--format',fmt,name],timeout=10).decode().split()
    assert actual==[source,image,'true']+(['healthy'] if role=='api' else [])
    subprocess.run(['docker','exec',name,'python','-B','-c',config,role],
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=10)
print(json.dumps(dict(source=source,image=image,translation_subjects=101,taxi_subjects=99,
                      taxi_key_configured=True,counter_mount_verified=True)))
"""


def main():
    (run,) = sys.argv[1:]
    assert re.fullmatch(r'b-smoke-20261118-[2-9][0-9]',run)
    quick_path = CODE / 's-build52-quick.py'
    quick = runpy.run_path(str(quick_path))
    private = quick['private']
    ops = runpy.run_path(str(quick['OPERATOR']))
    gate_bytes = private(STATE/(run+'-forward-gate.json'))
    gate = json.loads(gate_bytes)
    source,image = (gate[name] for name in ('source','image_id'))
    assert re.fullmatch('[a-f0-9]{40}',source) and re.fullmatch('sha256:[a-f0-9]{64}',image)
    preflight = json.loads(private(STATE/(run+'-quick-preflight-proof.json')))
    assert preflight==dict(kind='preflight',status='PASS',provider_calls=0,source=source,
                            previous_source=gate['previous_source'],gate_sha256=sha256(gate_bytes).hexdigest())
    readback = json.loads(private(STATE/(run+'-readback.stdout')))
    assert all(readback[role].split()==[source,image,'true']+(['healthy'] if role=='api' else [])
               for role in ('api','worker'))
    assert not (STATE/(run+'-smoke-run.stdout')).exists()
    now = datetime.now(timezone.utc)
    # run -42 (2026-11-25): the cutover finished at 13:49:38Z, 3 min before the 25-min gate closed, so the
    # same-source smoke uses its own 10-min span (as s55/s58 do) instead of the gate's remaining time.
    end = now+timedelta(minutes=10)
    assert datetime.fromisoformat(gate['starts_at'])<=now<=datetime.fromisoformat(gate['ends_at'])+timedelta(hours=2)
    read = ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',CONFIG_READBACK,
                            source,image],name=run+'-existing-plugin-readback',timeout=45)
    assert read.returncode==0 and json.loads(read.stdout)==dict(source=source,image=image,
                 translation_subjects=101,taxi_subjects=99,taxi_key_configured=True,counter_mount_verified=True)
    auth = runpy.run_path(str(quick['ORIGINAL']))
    login = auth['login']
    code = login.__globals__['LOGIN']
    old_grant = "invite_code=packet['code']))"
    assert code.count('configured_plugin_subjects')==2 and code.count(old_grant)==1
    login.__globals__['LOGIN'] = code.replace('configured_plugin_subjects','configured_translation_subjects').replace(
        old_grant,"invite_code=packet['code'], consent=True))")
    span = dict(starts_at=now.isoformat(),ends_at=end.isoformat())
    ops['save'](STATE/(run+'-quick-intent.json'),compact(dict(span,source=source,image=image,run=run)))
    g2c = login(auth['SAMPLES']/'group-g2c.invite',dict(span,source=source,image=image),ops,expected_member=True)
    packet = dict(span,access_token=private(STATE/'c-20261119-zh.jwt').decode().strip(),
                  translation_access_token=g2c['credential'])
    result = ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',quick['PROGRAM'],
                             source,image,'quick'],compact(packet),name=run+'-smoke-run',
                            timeout=max(5,(end-datetime.now(timezone.utc)).total_seconds()+3))
    events = [json.loads(raw) for raw in result.stdout.splitlines()]
    for row in events:
        if row['kind'] in ('case','translation','taxi','quick_verdict'):
            print(json.dumps({key:row[key] for key in ('kind','status','reason') if key in row}))
    verdict, = [row for row in events if row['kind']=='quick_verdict']
    chat, = [row for row in events if row['kind']=='case']
    ops['save'](STATE/(run+'-quick-verdict.json'),compact(dict(verdict,source=source,image=image)))
    ops['save'](STATE/(run+'-batch-chat-verdict.json'),compact(dict(source=source,image=image,status=chat['status'],
                                                                 reason=chat.get('reason'))))
    if result.returncode==0 and verdict['status']=='PASS':
        cost, = [row for row in events if row['kind']=='cost']
        text, = [row for row in events if row['kind']=='translation']
        taxi, = [row for row in events if row['kind']=='taxi']
        assert chat['status']==text['status']==taxi['status']=='PASS'
        assert cost['unresolved_attempts']==0 and cost['paid_cny']=='UNKNOWN'
        ceiling = max(cost['conservative_cny_1e7'],
                      cost['line_usage_delta_cny_1e7']+text['conservative_cny_1e7'])
        assert 0<=cost['estimated_cny_1e7']<=ceiling<=50_000_000
        fees = dict(conservative_cny_1e7=ceiling,estimated_cny_1e7=cost['estimated_cny_1e7'],
                    paid_cny='UNKNOWN')
        ops['save'](STATE/(run+'-smoke-final.json'),compact(dict(verdict,source=source,image=image,costs=fees)))
    return result.returncode


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('same-source smoke requires readback',file=sys.stderr)
        raise SystemExit(2) from None
