"""Only the new guarded delta; fixed read-only 0045 files and fresh own PG."""
import hashlib
import json
from pathlib import Path
from run_private_pg import main

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT/'.local/canonical-0045'


def run():
    manifest = json.loads((ROOT/'evidence/guard-input.json').read_text())
    if manifest['commit'] != '0045e423f004f873e2786aa98b2600b70772a921':
        raise RuntimeError('unexpected canonical input')
    for name, expected in manifest['sha256'].items():
        if hashlib.sha256((INPUT/name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('canonical input differs: '+name)
    print('PASS canonical archived input: '+manifest['commit'], flush=True)
    main(checks_file=ROOT/'tests/guarded_checks.py',
         memory_input=INPUT/'backend/memory',
         label='CJ019 guarded delta / canonical 0045 / synthetic AUTH and real private PG')


if __name__ == '__main__':
    run()
