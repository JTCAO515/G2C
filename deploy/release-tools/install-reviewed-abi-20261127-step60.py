"""Install the exact R-reviewed current/next source pair under the release lock."""

import hashlib
from pathlib import Path
import runpy
import sys

DIR = Path(__file__).resolve().parent
OPS = runpy.run_path(str(DIR / 'hk-operator.py'))
OLD = '94f78d0ae64281aeb0018de035debeb9bef5c5e426ae83f7e23af252fdceaeed'
NEW = 'c449d04115f5911c5187c03e7a80032cc98627bd4647eb5d25ef251c9bdf7b7b'
INPUT = DIR / 'policy-e0bea843-dfc8a8d8-20261127.json'
PROGRAM = r"""
import hashlib,os,stat,subprocess,sys
from pathlib import Path

target=Path('/srv/g2c-beta/quota-self-service-20261112/app-release-policy.json')
backup=Path('/srv/g2c-beta/probes/b-smoke-20261118-53/prior-app-release-policy-20261127-step60.json')
current='e0bea8430d1223b23919d82ae276af03b878b575'
current_image='sha256:5fa290ce84d0f19fca881bcc1518d82b155bc07d307952f6b100c9691edf756e'
old,new=sys.argv[1:]
meta=target.lstat()
assert stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and stat.S_IMODE(meta.st_mode)==0o600
initial=target.read_bytes()
candidate=sys.stdin.buffer.read(65537)
assert 0<len(candidate)<=65536 and hashlib.sha256(initial).hexdigest()==old
assert hashlib.sha256(candidate).hexdigest()==new
for role in ('api','worker'):
    state=subprocess.check_output(['docker','inspect','--format',
        '{{index .Config.Labels "org.opencontainers.image.revision"}} {{.State.Running}} {{.Image}}',
        'g2c-beta-'+role+'-1'],universal_newlines=True).split()
    assert state==[current,'true',current_image]

def save(path,data):
    descriptor=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())

save(backup,initial)
pending=target.with_name('.app-release-policy.20261127-step60.pending')
save(pending,candidate)
pending.replace(target)
descriptor=os.open(str(target.parent),os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(descriptor)
finally:os.close(descriptor)
assert hashlib.sha256(target.read_bytes()).hexdigest()==new
print('Exact reviewed application compatibility input installed')
"""

if __name__=='__main__':
    if sys.flags.optimize or sys.argv[1:] != [NEW]:
        raise SystemExit('Explicit R-approved digest required')
    raw=INPUT.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=NEW:
        raise SystemExit('Compatibility input bytes changed')
    result=OPS['captured'](['flock','-n',OPS['LOCK'],'python3','-I','-B','-c',PROGRAM,OLD,NEW],
                            raw,name='20261127-abi-e0be-dfc8-install',timeout=40)
    if result.stdout:
        print(result.stdout.decode().strip())
    raise SystemExit(result.returncode)
