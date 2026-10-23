"""Assemble fixed official dependencies only under this module's ignored .build.
Never writes a sibling, never overwrites conflicting bytes, never regenerates SDK.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

MODULE = Path(__file__).resolve().parents[2]
REPO = MODULE.parents[2]
BASE = 'c48016f3188380f33570b8c7e01ded797821c0bd'
OWNER = '5075bcf604e959d5c4592071a1e9de39d8687395'
API = 'f87a78a9d8984c59905e385483f17dddd8144d8a'
SHARED = Path(sys.argv[1])
API_REPO = Path(sys.argv[2])
OUT = MODULE / '.build' / 'f87-pin-validation' / 'assembly'

def git(repository, *args):
    return subprocess.check_output(['git', '-C', str(repository), *args])
def blob(repository, pin, path): return git(repository, 'show', pin + ':' + path)
def sha(data): return hashlib.sha256(data).hexdigest()
def check_destination(path, data):
    cursor = MODULE
    for part in path.relative_to(MODULE).parts:
        cursor = cursor / part
        if cursor.is_symlink(): raise SystemExit('refusing symlink: ' + str(cursor))
    if path.exists() and (not path.is_file() or path.read_bytes() != data):
        raise SystemExit('refusing conflicting preparation: ' + str(path))
def write(path, data):
    check_destination(path, data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
def export_module(repository, pin, name):
    prefix = 'ios/Modules/' + name + '/'
    paths = git(repository, 'ls-tree', '-r', '--name-only', pin, prefix).decode().splitlines()
    selected = [p for p in paths if p[len(prefix):] in ('Package.swift', 'Package.resolved')
                or p.startswith((prefix + 'Sources/', prefix + 'Tests/'))]
    selected = [p for p in selected if not (name == 'CJTripClient' and p == prefix + 'Package.swift')]
    for path in selected: write(OUT / path, blob(repository, pin, path))
    return {p: sha(blob(repository, pin, p)) for p in selected}

candidate = (MODULE / 'Package.swift').read_bytes()
expected = blob(REPO, BASE, 'ios/Modules/CJTripClient/Package.swift').replace(
    b'33cec5ba71d74820cb0acd3c89ecbe39ba125590', API.encode())
assert candidate == expected, 'candidate must be exactly the authorized one-path pin'
metadata_path = 'ios/Modules/CJMessageClient/evidence/generated-pin.json'
metadata = blob(SHARED, OWNER, metadata_path)
manifest = json.loads(metadata)
assert manifest['commit'] == API
sdk = OUT / 'ios/Modules/CJMessageClient/.generated' / API / 'CJFoundation'
# Preflight official SHA and every existing export destination before invoking owner script.
for path, digest in manifest['sha256'].items():
    data = blob(API_REPO, API, path)
    assert sha(data) == digest, path
    check_destination(sdk / path.removeprefix('ios/'), data)

protected = export_module(REPO, BASE, 'CJTripClient')
# Pin is the only candidate delta in the copied consumer. Do not overwrite source checkout.
copy_package = OUT / 'ios/Modules/CJTripClient/Package.swift'
write(copy_package, candidate)
protected.update(export_module(REPO, BASE, 'CJAuth'))
shared_bytes = export_module(SHARED, OWNER, 'CJMessageClient')
script = 'ios/Modules/CJMessageClient/scripts/prepare_generated.py'
write(OUT / script, blob(SHARED, OWNER, script))
write(OUT / metadata_path, metadata)
subprocess.run([sys.executable, str(OUT / script), str(API_REPO)], check=True)
assert (OUT / metadata_path).read_bytes() == metadata
for path, digest in manifest['sha256'].items():
    assert sha((sdk / path.removeprefix('ios/')).read_bytes()) == digest
transport = 'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/Transport.swift'
assert sha((OUT / transport).read_bytes()) == 'fe1b002d25e56290e7518b96110ff5a17440d304436bfca4842a4a4be6c76472'
print(json.dumps({'base': BASE, 'shared_owner': OWNER, 'api': API, 'assembly': str(OUT),
    'candidate_package_sha256': sha(candidate), 'sdk_files_exact': manifest['sha256'],
    'fixed_module_files': protected, 'fixed_shared_files': shared_bytes,
    'writes_only_under': str(MODULE / '.build'), 'original_tree_graph': 'UNRUN: sibling still33 and f87 export absent'}, indent=2))
