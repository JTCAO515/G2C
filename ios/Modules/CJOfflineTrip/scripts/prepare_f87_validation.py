"""Fixed-input local verification mirror; writes only a NEW directory in this module's .build."""
from pathlib import Path
import hashlib
import json
import subprocess

MODULE = Path(__file__).resolve().parents[1]
REPO = MODULE.parents[2]
BASE = 'e590f94ff367a9821d06558b7c35c2d020b40629'
SHARED = '5075bcf604e959d5c4592071a1e9de39d8687395'
TRIP = 'a5cc42005c69811ccb05754793107141fb4a9f02'
AUTH = '4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e'
SDK = 'f87a78a9d8984c59905e385483f17dddd8144d8a'
SOURCE_ROOT = REPO.parent
OUT = MODULE / '.build' / 'f87-validation-5075bcf-a5cc420-v2'


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def original(repo, pin, path):
    return git(repo, 'show', f'{pin}:{path}')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def package_inputs(repo, pin, prefix):
    paths = git(repo, 'ls-tree', '-r', '--name-only', pin, prefix).decode().splitlines()
    return [p for p in paths if p in (prefix + '/Package.swift', prefix + '/Package.resolved')
            or p.startswith((prefix + '/Sources/', prefix + '/Tests/'))]


def write(relative, data):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise RuntimeError('unsafe fixed input path')
    target = OUT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


if OUT.exists() or OUT.is_symlink():
    raise SystemExit('refusing to replace existing validation mirror: ' + str(OUT))
if (MODULE / '.build').is_symlink():
    raise SystemExit('refusing symlinked .build')
OUT.mkdir(parents=True)
manifest = {'base': BASE, 'shared': SHARED, 'trip': TRIP, 'auth': AUTH, 'sdk': SDK, 'inputs': {}}

# Producer bytes come only from exact Git objects, never a moving checkout HEAD.
for name, repo, pin in [
    ('CJMessageClient', SOURCE_ROOT / 'cj-009-memory-api-pin', SHARED),
    ('CJTripClient', SOURCE_ROOT / 'cj-015-trip-client', TRIP),
    ('CJAuth', SOURCE_ROOT / 'cj-007-auth', AUTH),
]:
    prefix = 'ios/Modules/' + name
    for path in package_inputs(repo, pin, prefix):
        data = original(repo, pin, path)
        write(path, data)
        manifest['inputs'][path] = {'owner': pin, 'sha256': digest(data)}

# Only this consumer's manifest pin differs; its source/tests/lock remain fixed base bytes.
prefix = 'ios/Modules/CJOfflineTrip'
for path in package_inputs(REPO, BASE, prefix):
    data = (REPO / path).read_bytes()
    old = original(REPO, BASE, path)
    expected = old.replace(b'33cec5ba71d74820cb0acd3c89ecbe39ba125590', SDK.encode()) if path.endswith('/Package.swift') else old
    if data != expected:
        raise RuntimeError('unexpected consumer input change: ' + path)
    write(path, data)
    manifest['inputs'][path] = {'owner': 'CJ022 local manifest / unchanged ' + BASE, 'sha256': digest(data)}

# Export the one official SDK into its canonical relative location inside the mirror.
producer = SOURCE_ROOT / 'cj-009-memory-api-pin'
pin_manifest = json.loads(original(producer, SHARED, 'ios/Modules/CJMessageClient/evidence/generated-pin.json'))
if pin_manifest['commit'] != SDK:
    raise RuntimeError('fixed shared SDK mismatch')
foundation = SOURCE_ROOT / 'cj-005-foundation'
for path, expected_hash in pin_manifest['sha256'].items():
    data = original(foundation, SDK, path)
    if digest(data) != expected_hash:
        raise RuntimeError('official SDK input mismatch: ' + path)
    destination = 'ios/Modules/CJMessageClient/.generated/' + SDK + '/CJFoundation/' + path.removeprefix('ios/')
    write(destination, data)
    manifest['inputs'][destination] = {'owner': SDK, 'sha256': expected_hash}
manifest['sdk_input_count'] = len(pin_manifest['sha256'])
(OUT / 'INPUTS.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(OUT)
