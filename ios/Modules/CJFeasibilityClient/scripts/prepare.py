"""Fixed Git preparation in this module only. Never alters sibling owner trees."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

module = Path(__file__).resolve().parents[1]
repo = module.parents[2]
shared, api = (Path(x).resolve() for x in sys.argv[1:3])
SHARED = '9b4852dfad418d124d60366ada8efb380a8ffc1d'
API = 'dc29bb3634e63d8f065c38d39a7a0059f76cfa53'
BASE = '02f672605ad5521f9360e42be8f43ebfd022a0e8'

def show(root, pin, path):
    return subprocess.check_output(['git', '-C', str(root), 'show', pin + ':' + path])

def snapshot(root, pin, prefix, destination):
    paths = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', '--name-only', pin, prefix]).decode().splitlines()
    for path in paths:
        target = destination / path.removeprefix(prefix + '/')
        data = show(root, pin, path)
        if target.exists():
            assert target.is_file() and target.read_bytes() == data, str(target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    return {p: hashlib.sha256(show(root, pin, p)).hexdigest() for p in paths}

def link(destination, target):
    if destination.is_symlink():
        assert destination.resolve() == target.resolve()
    else:
        assert not destination.exists(), str(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(target, target_is_directory=True)

manifest = json.loads(show(shared, SHARED, 'ios/Modules/CJMessageClient/evidence/generated-pin.json'))
assert manifest['commit'] == API
export = shared / 'ios/Modules/CJMessageClient/.generated' / API / 'CJFoundation'
for path, sha in manifest['sha256'].items():
    data = (export / path.removeprefix('ios/')).read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha and data == show(api, API, path), path
prepared = module / '.prepare/Modules'
inputs = {'message': snapshot(shared, SHARED, 'ios/Modules/CJMessageClient', prepared / 'CJMessageClient'),
          'auth': snapshot(repo, BASE, 'ios/Modules/CJAuth', prepared / 'CJAuth'),
          'sdk': manifest['sha256']}
link(prepared / 'CJMessageClient/.generated' / API / 'CJFoundation', export)
consumer = prepared / 'CJFeasibilityClient'; consumer.mkdir(parents=True, exist_ok=True)
for name in ['Sources', 'Tests']:
    link(consumer / name, module / name)
# Consumer manifests are owned here and can change during development.
for name in ['Package.swift', 'Package.resolved']:
    (consumer / name).write_bytes((module / name).read_bytes())
(module / 'evidence/inputs.json').write_text(json.dumps({'base': BASE, 'shared': SHARED, 'api': API, 'sha256': inputs}, indent=2) + '\n')
print(consumer)
