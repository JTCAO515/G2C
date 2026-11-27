"""Restore the original C standing policy after read-only reconciliation."""
from hashlib import sha256
import json
from pathlib import Path
import runpy
import stat
import sys

HERE = Path(__file__).resolve().parent
OPERATOR = HERE / 'hk-operator.py'
EXPECTED_OPERATOR = '012cf79e0f552a8cb9d7c90eaaa08c177246c19265419c6a13632c0e1efee5b4'
RUNNER = HERE / 's-build52-quick.py'
EXPECTED_RUNNER = 'e312b0c0291ead41f22b7ce2cc4c6089e6bef33a4b18601f9b2fc52e11859f17'

def private(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
    return path.read_bytes()

def main():
    (run,) = sys.argv[1:]
    assert run.startswith('b-smoke-20261118-') and run.rsplit('-',1)[-1].isdigit()
    assert sha256(private(OPERATOR)).hexdigest()==EXPECTED_OPERATOR
    assert sha256(private(RUNNER)).hexdigest()==EXPECTED_RUNNER
    ops=runpy.run_path(str(OPERATOR))
    program=runpy.run_path(str(RUNNER))['PROGRAM']
    gate=json.loads(private(HERE/(run+'-forward-gate.json')))
    source,image=(gate[name] for name in ('source','image_id'))
    quick_path=HERE/(run+'-smoke-run.stdout')
    events=[json.loads(row) for row in private(quick_path).splitlines()]
    restricted,=[row for row in events if row['kind']=='restricted']
    drain=json.loads(private(HERE/(run+'-drain.stdout')))
    assert drain['global_pending']==drain['global_active']==0
    assert not any(drain['background_states'].get(k,0) for k in ('queued','running','publishing'))
    assert not any(drain['memory_states'].get(k,0) for k in ('pending','inflight'))
    ledger=drain['ledger']
    packet=dict(before=restricted['before'],restricted=restricted['restricted'],
                drained_ledger=[ledger['count'],ledger['sha256']])
    raw=json.dumps(packet,sort_keys=True,separators=(',',':')).encode()
    ops['save'](HERE/(run+'-quick-restore-permit.json'),raw)
    output=ops['captured'](['flock','-n',ops['LOCK'],'python3','-I','-B','-c',program,
                           source,image,'restore'],raw,name=run+'-smoke-restore',timeout=65)
    assert output.returncode==0
    assert json.loads(output.stdout)==dict(kind='budget_restore',status='PASS')
    print('PASS original C standing restored; original journal and holds retained')

if __name__=='__main__':
    try:
        main()
    except Exception:
        print('original restore state requires readback',file=sys.stderr)
        raise SystemExit(2) from None
