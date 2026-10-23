"""Exact immutable dependency inputs in an OWN-module ignored validation graph.

No sibling writes, network, SDK generation, manifest rewrites or dependency upgrades.
Usage: python3 scripts/prepare_dc29_consumption.py /fixed/shared/repository
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

SDK = 'dc29bb3634e63d8f065c38d39a7a0059f76cfa53'
SHARED = '9b4852dfad418d124d60366ada8efb380a8ffc1d'
BASE = '205fb479b89c7252dc2ad7587d327c578475c2fc'
module = Path(__file__).resolve().parents[1]
repo = module.parents[2]
shared_repo = Path(sys.argv[1]).resolve(strict=True)
graph = module / '.build/dc29-consumption'
modules = graph / 'ios/Modules'
hashes = {}


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def put(path, data):
    # Refuse symlinked preparation roots and different pre-existing bytes.
    for ancestor in (path, *path.parents):
        if ancestor == module:
            break
        if ancestor.is_symlink():
            raise SystemExit('symlinked preparation path: ' + str(ancestor))
    if path.exists() and path.read_bytes() != data:
        raise SystemExit('refusing to overwrite different preparation: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    hashes[str(path.relative_to(graph))] = hashlib.sha256(data).hexdigest()


def export(source, pin, prefix, destination):
    for path in git(source, 'ls-tree', '-r', '--name-only', pin, prefix).decode().splitlines():
        relative = path.removeprefix(prefix + '/')
        if relative in ('Package.swift', 'Package.resolved') or relative.startswith(('Sources/', 'Tests/')):
            put(destination / relative, git(source, 'show', pin + ':' + path))


# Fixed official dependency input bytes only. Root SDK is available from the local
# fixed-object fetch; the original shared owner tree is read by Git, never copied dirty.
export(shared_repo, SHARED, 'ios/Modules/CJMessageClient', modules / 'CJMessageClient')
export(repo, BASE, 'ios/Modules/CJAuth', modules / 'CJAuth')
export(repo, SDK, 'ios', modules / 'CJMessageClient/.generated' / SDK / 'CJFoundation')
for root in ('Sources', 'Tests'):
    for path in sorted((module / root).rglob('*')):
        if path.is_file():
            put(modules / 'CJUsageClient' / path.relative_to(module), path.read_bytes())
for name in ('Package.swift', 'Package.resolved'):
    put(modules / 'CJUsageClient' / name, (module / name).read_bytes())
result = {'base': BASE, 'shared': SHARED, 'sdk': SDK, 'sha256': hashes,
          'graph': str(graph), 'sibling_writes': False}
(module / 'evidence/dc29-preparation.json').write_text(json.dumps(result, indent=2) + '\n')
print('Prepared exact own validation graph:', graph)
print('Files verified:', len(hashes))
