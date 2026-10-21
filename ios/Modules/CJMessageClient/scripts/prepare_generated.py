"""Export exact official CJAPI package inputs; no generated-file rewriting."""
from pathlib import Path
import hashlib, json, subprocess, sys
PIN='d886677a805db51759a3116f8d2c0d4f3b8dddb3'
root=Path(__file__).resolve().parents[1]
source=sys.argv[1]
paths=subprocess.check_output(['git','-C',source,'ls-tree','-r','--name-only',PIN,'ios']).decode().splitlines()
selected=[p for p in paths if p in ('ios/Package.swift','ios/Package.resolved') or p.startswith(('ios/Sources/','ios/Tests/'))]
out=root/'.generated/CJFoundation'
hashes={}
for path in selected:
    data=subprocess.check_output(['git','-C',source,'show',f'{PIN}:{path}'])
    dest=out/path.removeprefix('ios/')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and dest.read_bytes()!=data: raise SystemExit('refusing to overwrite different export: '+str(dest))
    dest.write_bytes(data)
    hashes[path]=hashlib.sha256(data).hexdigest()
(root/'evidence/generated-pin.json').write_text(json.dumps({'commit':PIN,'sha256':hashes},indent=2)+'\n')
print('verified exact official export:',PIN,len(selected),'files')
