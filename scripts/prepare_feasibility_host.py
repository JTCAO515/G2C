"""Prepare ONLY a synthetic local host slice. No peer manifest edits or second SDK."""
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
BASE = 'b66b0c487a54f519f7b6a7f661171705b634e717'
CLIENT = 'c607358dc8475a1fdcc90d05ad47ef8450503a04'
NEEDS = 'e03da1b2f1c22a28da5b8c9110166108a44af936'
SHARED = '9b4852dfad418d124d60366ada8efb380a8ffc1d'
SDK = 'dc29bb3634e63d8f065c38d39a7a0059f76cfa53'
OUT = ROOT / 'contracts/ui/evidence/feasibility-host/.prepare'
MODULES = OUT / 'Modules'
manifest = {'base': BASE, 'client': CLIENT, 'needs': NEEDS, 'shared': SHARED, 'sdk': SDK,
            'scope': 'synthetic ShellState facts; actual owned three host sources and fixed consumers', 'files': {}}
def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink(): raise ValueError(path)
    path.write_bytes(data)
def snapshot(repo, pin, name):
    prefix = f'ios/Modules/{name}/'
    for path in git(repo, 'ls-tree', '-r', '--name-only', pin, prefix).decode().splitlines():
        tail = path.removeprefix(prefix)
        if tail.startswith('Sources/') or tail in ['Package.swift', 'Package.resolved']:
            data = git(repo, 'show', pin + ':' + path)
            write(MODULES / name / tail, data)
            manifest['files'][f'{name}/{tail}'] = hashlib.sha256(data).hexdigest()
snapshot(PARENT / 'cj-035-feasibility-client', CLIENT, 'CJFeasibilityClient')
snapshot(PARENT / 'cj-009-memory-api-pin', SHARED, 'CJMessageClient')
snapshot(ROOT, BASE, 'CJAuth')
snapshot(ROOT, NEEDS, 'CJNeedsClient')
# CJNeeds' older graph is NOT repinned. Build a harness-owned manifest for these exact sources.
needs_manifest = (MODULES / 'CJNeedsClient/Package.swift').read_text()
assert needs_manifest.count('20aa50ed5c8449e6026155a6151f22041dee7fd4') == 1
write(MODULES / 'CJNeedsClient/Package.swift', needs_manifest.replace('20aa50ed5c8449e6026155a6151f22041dee7fd4', SDK).encode())
manifest['needs_manifest_adjustment'] = 'ONLY .prepare synthetic graph: 20aa SDK path to sole dc29; original unchanged'
shared = PARENT / 'cj-009-memory-api-pin'
fixed = json.loads(git(shared, 'show', SHARED + ':ios/Modules/CJMessageClient/evidence/generated-pin.json'))
assert fixed['commit'] == SDK
export = shared / f'ios/Modules/CJMessageClient/.generated/{SDK}/CJFoundation'
for path, sha in fixed['sha256'].items():
    data = (export / path.removeprefix('ios/')).read_bytes()
    assert hashlib.sha256(data).hexdigest() == sha
    assert data == git(PARENT / 'cj-005-foundation', 'show', SDK + ':' + path)
manifest['sdk_sha256'] = fixed['sha256']
link = MODULES / f'CJMessageClient/.generated/{SDK}/CJFoundation'
link.parent.mkdir(parents=True, exist_ok=True)
if link.is_symlink(): assert link.resolve() == export.resolve()
else:
    assert not link.exists()
    link.symlink_to(export, target_is_directory=True)
source = ROOT / 'ios/Modules/CJShell/Sources/CJShell'
for name in ['NeedsContainerHost.swift', 'NeedsContainerView.swift', 'FeasibilityHostView.swift']:
    data = (source / name).read_bytes()
    write(MODULES / 'CJShell/Sources/CJShell' / name, data)
    manifest['files']['CJShell/' + name] = hashlib.sha256(data).hexdigest()
fixtures = ROOT / 'ios/Modules/CJShell/Tests/FeasibilityHostHarness'
write(MODULES / 'CJShell/Sources/CJShell/ShellFacts.swift', (fixtures / 'ShellFacts.swift').read_bytes())
write(MODULES / 'CJShell/Package.swift', (fixtures / 'Package.swift').read_bytes())
for test in fixtures.glob('*Tests.swift'):
    write(MODULES / 'CJShell/Tests/CJShellTests' / test.name, test.read_bytes())
write(MODULES / 'CJShell/Package.resolved', (ROOT / 'ios/Modules/CJShell/Package.resolved').read_bytes())
manifest['harness_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.glob('*.swift')}
write(OUT.parent / 'inputs.json', (json.dumps(manifest, indent=2) + '\n').encode())
print(MODULES / 'CJShell')
