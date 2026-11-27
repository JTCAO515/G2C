"""Private transport for the reviewed same-source quick probe. Credentials stay in memory."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import stat
import sys

from cj_strict_json import compact

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser().resolve()
ORIGINAL = CODE / 'build52-quick-translation.py'
OPERATOR = CODE / 'hk-operator.py'
LOGIN_ANCHOR = 'configured_plugin_subjects'
PROGRAM = """
import json,subprocess,sys
source,image,action=sys.argv[1:]
fmt='{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Image}} {{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}'
for role in ('api','worker'):
    row=subprocess.check_output(['docker','inspect','--format',fmt,'g2c-beta-'+role+'-1'],timeout=10)
    expected=[source,image,'true']+(['healthy'] if role=='api' else [])
    if row.decode().split()!=expected:
        raise SystemExit(2)
raise SystemExit(subprocess.call(['docker','exec','-i','g2c-beta-worker-1',
    'python','-B','-m','deploy.hk.server_smoke',action]))
"""

def private(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('original_private_file_required')
    return path.read_bytes()

def main():
    phase, envelope_path = sys.argv[1:]
    if phase not in {'preflight', 'quick'}:
        raise ValueError('quick_operation_required')
    ops=runpy.run_path(str(OPERATOR))
    verified=runpy.run_path(str(ORIGINAL))
    legacy_login=verified['login']
    code=legacy_login.__globals__['LOGIN']
    assert code.count(LOGIN_ANCHOR)==2
    old_grant="invite_code=packet['code']))"
    assert code.count(old_grant)==1
    legacy_login.__globals__['LOGIN']=code.replace(LOGIN_ANCHOR,'configured_translation_subjects').replace(
        old_grant,"invite_code=packet['code'], consent=True))")
    raw=private(Path(envelope_path))
    envelope=json.loads(raw)
    source,image=(envelope[name] for name in ('source','image'))
    start,end=(datetime.fromisoformat(envelope[name]) for name in ('starts_at','ends_at'))
    now=datetime.now(timezone.utc)
    if not start<=now<end or not 105 <= (end-now).total_seconds() <= (end-start).total_seconds() <= 600:
        raise ValueError('original_ten_minute_window_required')
    prefix=envelope['run']
    if not prefix.startswith('b-smoke-20261118-') or not prefix.rsplit('-',1)[-1].isdigit():
        raise ValueError('original_run_reference_required')
    for name,count in (('roster',101),('taxi_key',99)):
        receipt=json.loads(private(Path(envelope[name+'_receipt'])))
        assert (receipt['source'],receipt['image'],receipt['phase'])==(source,image,'APPLIED')
        if name=='roster':
            assert receipt['translation_roster_count']==count and receipt['taxi_roster_count']==99
        else:
            assert receipt['taxi_key_configured'] is True and receipt['counter_mount_verified'] is True

    if phase=='quick':
        gate=private(STATE/(prefix+'-forward-gate.json'))
        previous=json.loads(private(STATE/(prefix+'-quick-preflight-proof.json')))
        assert previous==dict(kind='preflight',status='PASS',provider_calls=0,source=source,
                              previous_source=json.loads(gate)['previous_source'],
                              gate_sha256=sha256(gate).hexdigest())
    intent=STATE/(prefix+'-'+phase+'-intent.json')
    ops['save'](intent,compact(dict(source=source,image=image,operation=phase,
                                  envelope_sha256=sha256(raw).hexdigest()),sort_keys=True))
    g2c=legacy_login(verified['SAMPLES']/'group-g2c.invite',envelope,ops,expected_member=True)
    packet={name:envelope[name] for name in ('starts_at','ends_at')}
    packet.update(access_token=private(STATE/'c-20261119-zh.jwt').decode().strip(),
                  translation_access_token=g2c['credential'])
    name=prefix+('-quick-preflight' if phase=='preflight' else '-smoke-run')
    result=ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',PROGRAM,
                           source,image,'quick-preflight' if phase=='preflight' else phase],compact(packet),name=name,timeout=(end-now).total_seconds()+3)
    for raw_row in result.stdout.splitlines():
        row=json.loads(raw_row)
        if row['kind'] in ('case','translation','taxi','quick_verdict','preflight'):
            print(json.dumps({key:row[key] for key in ('kind','status','reason','rollback') if key in row}))
        if phase=='quick' and row['kind']=='quick_verdict':
            ops['save'](STATE/(prefix+'-quick-verdict.json'),compact(dict(row,source=source,image=image)))
    return result.returncode

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt):
        print('original quick operation requires readback',file=sys.stderr)
        raise SystemExit(2) from None
