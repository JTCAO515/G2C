"""Reconcile the current ledger with the original reviewed read-only witness."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import sys

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser()
OPERATOR = CODE / 'hk-operator.py'
PROGRAM = """
from hashlib import sha256
from pathlib import Path
import json,runpy,subprocess,sys
source,image=sys.argv[1:]
fmt='{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Image}} {{.State.Running}}'
def exact_running_roles():
    for role in ('api','worker'):
        out=subprocess.check_output(['docker','inspect','--format',fmt,'g2c-beta-'+role+'-1'],
                                    stderr=subprocess.PIPE,timeout=12)
        assert out.decode().split()==[source,image,'true']
exact_running_roles()
path=Path('/srv/g2c-beta/probes/b-archive-detach-1d5d538b-45db9e23/next-release-readonly-journal.py')
assert sha256(path.read_bytes()).hexdigest()=='dacb83c0709131ed6f112e871fa6e1e65e44ffb16e9bee1f066cf57a7baef62e'
approved=runpy.run_path(str(path))
argv=approved['PROOF_COMMAND']
cmd=[*argv[:-3],*approved['verified_mount'](),*argv[-3:]]
result=subprocess.check_output(cmd,stderr=subprocess.PIPE,timeout=45)
proof=json.loads(result)
exact_running_roles()
print(json.dumps({key:proof[key] for key in ('ledger','global_pending','global_active','background_states','memory_states')}))
"""

def main():
    run, phase, source, image = sys.argv[1:]
    if (not re.fullmatch(r'b-smoke-20261118-[0-9]{2}',run) or phase not in ('activation-drain','drain')
            or not re.fullmatch('[0-9a-f]{40}',source) or not re.fullmatch('sha256:[0-9a-f]{64}',image)):
        raise ValueError('same_source_drain_required')
    ops=runpy.run_path(str(OPERATOR))
    result=ops['captured'](['flock','-s','-n',ops['LOCK'],'python3','-I','-B','-c',PROGRAM,source,image],
                           name=run+'-'+phase,timeout=70)
    if result.returncode:
        raise ValueError('original_drain_outcome_unverified')
    proof=json.loads(result.stdout)
    if (proof['global_pending']!=0 or proof['global_active']!=0
            or any(proof['background_states'].get(k,0) for k in ('queued','running','publishing'))
            or any(proof['memory_states'].get(k,0) for k in ('pending','inflight'))):
        raise ValueError('existing_operations_still_inflight')
    print('PASS original ledger read and all original operations drained')

if __name__=='__main__':
    try:
        main()
    except Exception:
        print('original drain requires readback',file=sys.stderr)
        raise SystemExit(2) from None
