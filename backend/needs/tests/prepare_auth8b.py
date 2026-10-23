"""Export one exact read-only AUTH Git object into this task's ignored test deps."""
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys

AUTH_HEAD = '8b6abb236cf10c1865a9cc8c6155bd8ac732c07e'
ROOT = Path(__file__).resolve().parents[3]
source = Path(sys.argv[1]).resolve(strict=True)
def git(*args):
    return subprocess.check_output(['git', '-C', str(source), *args])
assert git('cat-file', '-t', AUTH_HEAD).strip() == b'commit'
files = git('ls-tree', '-r', '--name-only', AUTH_HEAD, 'backend/auth/cj_auth').decode().splitlines()
manifest = {'auth_head':AUTH_HEAD,'sha256':{}}
for name in files:
    path=Path(name)
    assert path.parts[:3] == ('backend','auth','cj_auth') and '..' not in path.parts
    raw=git('show', AUTH_HEAD+':'+name)
    target=ROOT/'backend/needs/.local/auth8b'/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest['sha256'][name]=sha256(raw).hexdigest()
(ROOT/'backend/needs/evidence/auth8b-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Exported fixed AUTH8b only; source tree unchanged')
