"""Check both original sessions on the old service before changing either role."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys

from cj_strict_json import compact

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser().resolve()
OPERATOR = CODE / 'hk-operator.py'
MODULES = ('app_smoke_ceiling', 'server_smoke_budget', 'plugin_roster')

def private(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError('original_private_file_required')
    return path.read_bytes()

def reviewed_source(source, name):
    return subprocess.check_output(['git','show',source+':deploy/hk/'+name+'.py'],timeout=20).decode()

def main():
    (run,) = sys.argv[1:]
    if not re.fullmatch(r'b-smoke-20261118-[0-9]{2}',run):
        raise ValueError('original_operator_or_run_unverified')
    raw=private(STATE/(run+'-forward-gate.json'))
    gate=json.loads(raw)
    source=gate['source']
    old,image=gate['previous_source'],gate['previous_image_id']
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=source:
        raise ValueError('exact_release_checkout_required')
    start,end=(datetime.fromisoformat(gate[field]) for field in ('starts_at','ends_at'))
    if not start<=datetime.now(timezone.utc)<end or not 0<(end-start).total_seconds()<=1800:
        raise ValueError('original_cutover_window_required')
    ops=runpy.run_path(str(OPERATOR))
    probe=runpy.run_path(str(CODE / 'build52-quick-translation.py'))
    login=probe['login']
    code=login.__globals__['LOGIN']
    for line in (
        'from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS,load_secret_environment',
        'from deploy.hk.plugin_roster import configured_plugin_subjects',
        'from deploy.hk.translation_relay import translation_state',
        ' load_secret_environment(\'worker\')',
        ' roster=configured_plugin_subjects(os.environ[TRANSLATION_INTERNAL_SUBJECTS])',
        ' assert translation_state() is True',
        " assert (subject in roster) is packet['expected_member']",
    ):
        if code.count(line+'\n')!=1:
            raise ValueError('original_login_transport_changed')
        code=code.replace(line+'\n','')
    old_grant = "invite_code=packet['code']))"
    assert code.count(old_grant)==1
    # The internal synthetic test account explicitly accepts the demo rules.
    login.__globals__['LOGIN']=code.replace(old_grant, "invite_code=packet['code'], consent=True))")
    envelope=dict(source=old,image=image,starts_at=gate['starts_at'],ends_at=gate['ends_at'])
    g2c=login(probe['SAMPLES']/'group-g2c.invite',envelope,ops,expected_member=True)
    modules=[('deploy.hk.'+name,reviewed_source(source,name)) for name in MODULES]
    smoke=reviewed_source(source,'server_smoke')
    program=('import sys, types\n'
             'sys.argv=["server_smoke", "quick-preflight"]\n'
             'for name, source in '+repr(modules)+':\n'
             '    module=types.ModuleType(name)\n'
             '    sys.modules[name]=module\n'
             '    exec(compile(source, name, "exec"), module.__dict__)\n'
             'exec(compile('+repr(smoke)+', "server_smoke.py", "exec"), globals())\n')
    packet={name:gate[name] for name in ('starts_at','ends_at')}
    packet.update(access_token=private(STATE/'c-20261119-zh.jwt').decode().strip(),
                  translation_access_token=g2c['credential'])
    result=ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',probe['ROLES'],old,image,program],
                           compact(packet),name=run+'-quick-preflight',timeout=50)
    expected=dict(kind='preflight',status='PASS',provider_calls=0)
    if result.returncode!=0 or json.loads(result.stdout)!=expected:
        raise ValueError('original_combined_session_preflight_unverified')
    receipt=dict(expected,source=source,previous_source=old,gate_sha256=sha256(raw).hexdigest())
    ops['save'](STATE/(run+'-quick-preflight-proof.json'),compact(receipt))
    print('PASS original C and shared G2C sessions cover the same window with zero provider calls')

if __name__=='__main__':
    try:
        main()
    except Exception:
        print('original pre-cutover admission requires readback',file=sys.stderr)
        raise SystemExit(2) from None
