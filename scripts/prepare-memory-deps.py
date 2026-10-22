"""Export only fixed memory/AUTH runtime Git blobs. No network or source checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-repository',type=Path,required=True)
p.add_argument('--auth-repository',type=Path,required=True)
a=p.parse_args()
pins=json.loads((ROOT/'backend/cj_api/memory_pins.json').read_text())
target=ROOT/'.local/memory-deps'/'-'.join(s['commit'] for s in pins['sources'])
for component in [target,*target.parents]:
    if component.is_symlink():raise ValueError('symlink export parent refused')
for source in pins['sources']:
    repo=a.auth_repository if source['name']=='auth' else a.source_repository
    for name,expected in source['files'].items():
        raw=subprocess.check_output(['git','-C',str(repo),'show',source['commit']+':'+name])
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('fixed dependency mismatch')
        output=target/name
        if output.is_symlink() or output.exists() and output.read_bytes()!=raw:
            raise ValueError('existing dependency differs')
        for component in output.parents:
            if component.is_symlink():raise ValueError('symlink export parent refused')
        output.parent.mkdir(parents=True,exist_ok=True)
        if not output.exists():output.write_bytes(raw)
print(target)
