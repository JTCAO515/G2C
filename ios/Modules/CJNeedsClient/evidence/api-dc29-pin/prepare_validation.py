"""Prepare fixed dependency inputs inside NEEDS ignored build area; never write siblings."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

module = Path(__file__).resolve().parents[2]
repo = module.parents[2]
shared = Path(sys.argv[1]).resolve()
api = Path(sys.argv[2]).resolve()
shared_pin = '9b4852dfad418d124d60366ada8efb380a8ffc1d'
api_pin = 'dc29bb3634e63d8f065c38d39a7a0059f76cfa53'

def show(root, pin, path):
    return subprocess.check_output(['git', '-C', str(root), 'show', pin + ':' + path])

manifest = json.loads(show(shared, shared_pin, 'ios/Modules/CJMessageClient/evidence/generated-pin.json'))
assert manifest['commit'] == api_pin
export = shared / 'ios/Modules/CJMessageClient/.generated' / api_pin / 'CJFoundation'
for path, expected in manifest['sha256'].items():
    data = (export / path.removeprefix('ios/')).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected
    assert data == show(api, api_pin, path)

validation = module / '.build/dc29-validation/Modules'
message = validation / 'CJMessageClient'
consumer = validation / 'CJNeedsClient'
message.mkdir(parents=True, exist_ok=True)
consumer.mkdir(parents=True, exist_ok=True)
files = subprocess.check_output(['git', '-C', str(shared), 'ls-tree', '-r', '--name-only', shared_pin,
                                 'ios/Modules/CJMessageClient']).decode().splitlines()
for path in files:
    dest = message / path.removeprefix('ios/Modules/CJMessageClient/')
    data = show(shared, shared_pin, path)
    if dest.exists():
        assert dest.is_file() and dest.read_bytes() == data, 'conflicting prepared input: ' + str(dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

def link(dest, target):
    if dest.is_symlink():
        assert dest.resolve() == target.resolve()
    else:
        assert not dest.exists(), 'refusing to replace existing input: ' + str(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(target, target_is_directory=True)

link(message / '.generated' / api_pin / 'CJFoundation', export)
link(validation / 'CJAuth', repo / 'ios/Modules/CJAuth')
for name in ['Sources', 'Tests']:
    link(consumer / name, module / name)
for name in ['Package.swift', 'Package.resolved']:
    dest = consumer / name
    data = (module / name).read_bytes()
    if dest.exists():
        assert dest.read_bytes() == data, 'conflicting consumer input: ' + str(dest)
    else:
        dest.write_bytes(data)
print(json.dumps({'validation_package': str(consumer), 'shared_snapshot': shared_pin,
                  'shared_files': len(files), 'official_export': str(export), 'official_files': len(manifest['sha256']),
                  'sdk_copied': False, 'sibling_writes': False}, indent=2))
