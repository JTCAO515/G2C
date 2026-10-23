"""Prepare the fixed FEAS candidate with the actual canonical full Shell sources.

Only own ignored files are written. All peer packages are original formal dc29
fixed inputs; no peer manifest rewrite or root identity override is required.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

SDK = 'dc29bb3634e63d8f065c38d39a7a0059f76cfa53'
OLD_SDK = '20aa50ed5c8449e6026155a6151f22041dee7fd4'
MAIN = 'b66b0c487a54f519f7b6a7f661171705b634e717'
HOST = '895d9edb93f4a3bcd1d03e666b9e6c60fc79a88a'
INPUTS = {
    'CJMessageClient': ('cj-009-memory-api-pin', '9b4852dfad418d124d60366ada8efb380a8ffc1d'),
    'CJMemoryClient': ('cj-011-memory-client', '66a33a602bbadcdf84b0285bc9835722a3fd2f2f'),
    'CJAuth': ('cj-007-auth', '4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e'),
    'CJTripClient': ('cj-015-trip-client', '7bcab1b13bc683c205f3ff0fa4446657427a5225'),
    'CJNeedsClient': ('cj-013-needs-client', 'b94db006efe732751291f68d364b81a9b9f3acb7'),
    'CJFeedbackClient': ('cj-023-feedback-client', 'fcffa3e97b6bd7b51abc3b87f3628c7e070b0665'),
    'CJRunClient': ('cj-010-run-client', 'fac970dbeb46f4a7632ba59743acb326205f7b6f'),
    'CJUsageClient': ('cj-008-usage-client', '023257b9b47d7ec7fc4dd840c25d157d45e68eaa'),
    'CJCleanupClient': ('cj-024-cleanup-client', 'ec8346fa1d3789776d455c96bf42e7bdfb24c0f0'),
    'CJManualPreviewClient': ('cj-017-manual-preview-client', 'ccd5425cbb8d86dbad4ede15196ac86cc91fb3bc'),
    'CJOfflineTrip': ('cj-022-offline-trip', 'c42a72bcc5ad06eea40e904f2765950b45506bd6'),
    'CJFeasibilityClient': ('cj-035-feasibility-client', '3a8ded38fd8113672b1f2c3dfaf056e1af4f9058'),
}
HOST_FILES = {'NeedsContainerHost.swift', 'NeedsContainerView.swift', 'FeasibilityHostView.swift'}
MAIN_SHARED_SUPPLEMENTS = [
    'Tests/CJMessageHTTPTests/PreviewHostHeaderBoundaryTests.swift',
    'evidence/PREVIEW-HOST-FIX.md', 'evidence/preview-host-after.txt',
    'evidence/preview-host-before.txt', 'evidence/preview-host-provenance.json',
    'evidence/preview-host-runtime.patch',
]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def prepare(checkouts):
    module = Path(__file__).resolve().parents[1]
    main = checkouts / 'cj-publish/Go2China'
    exports = {}
    provenance = {'main': MAIN, 'host_candidate': HOST, 'inputs': INPUTS, 'sdk': SDK,
                  'actual_shell_state': True, 'candidate_not_accepted': True}
    for name, (checkout, pin) in INPUTS.items():
        prefix = f'ios/Modules/{name}/'
        for path in git(checkouts / checkout, 'ls-tree', '-r', '--name-only', pin, prefix).decode().splitlines():
            tail = path.removeprefix(prefix)
            if tail in ('Package.swift', 'Package.resolved') or tail.startswith(('Sources/', 'Tests/')):
                exports[f'Modules/{name}/{tail}'] = git(checkouts / checkout, 'show', pin + ':' + path)
    pin_bytes = git(checkouts / 'cj-009-memory-api-pin', 'show', INPUTS['CJMessageClient'][1] + ':ios/Modules/CJMessageClient/evidence/generated-pin.json')
    sdk_manifest = json.loads(pin_bytes)
    assert sdk_manifest['commit'] == SDK
    provenance['sdk_manifest_sha256'] = hashlib.sha256(pin_bytes).hexdigest()
    for path, sha in sdk_manifest['sha256'].items():
        assert path.startswith('ios/') and '..' not in Path(path).parts
        data = git(checkouts / 'cj-005-foundation', 'show', SDK + ':' + path)
        assert hashlib.sha256(data).hexdigest() == sha
        exports[f'Modules/CJMessageClient/.generated/{SDK}/CJFoundation/' + path.removeprefix('ios/')] = data
    # Preserve canonical main-only shared files, never replace an owner's blob.
    prefix = 'ios/Modules/CJMessageClient/'
    retained = {}
    for tail in MAIN_SHARED_SUPPLEMENTS:
        path, dest = prefix + tail, 'Modules/CJMessageClient/' + tail
        data = git(main, 'show', MAIN + ':' + path)
        if dest in exports and exports[dest] != data:
            raise ValueError('Fixed shared conflicts with main supplement: ' + path)
        exports[dest] = data; retained[path] = hashlib.sha256(data).hexdigest()
    provenance['main_shared_supplements'] = retained
    prefix = 'ios/Modules/CJShell/'
    preserved = {}
    for path in git(main, 'ls-tree', '-r', '--name-only', MAIN, prefix).decode().splitlines():
        tail = path.removeprefix(prefix)
        if tail in ('Package.swift', 'Package.resolved', 'scripts/build-demo.sh') or tail.startswith(('Sources/', 'Tests/', 'Demo/')):
            if tail.startswith('Sources/') and Path(tail).name in HOST_FILES:
                continue
            data = git(main, 'show', MAIN + ':' + path)
            exports['Modules/CJShell/' + tail] = data
            if tail.startswith('Sources/'):
                preserved[path] = hashlib.sha256(data).hexdigest()
    provenance['main_shell_preserved'] = preserved
    for name in HOST_FILES:
        path = 'ios/Modules/CJShell/Sources/CJShell/' + name
        exports['Modules/CJShell/Sources/CJShell/' + name] = git(checkouts / 'cj-035-feasibility-shell', 'show', HOST + ':' + path)
    # Only this verification root's necessary package wiring is authored here.
    path = 'Modules/CJShell/Package.swift'
    manifest = exports[path].decode()
    assert manifest.count(OLD_SDK) == 1
    manifest = manifest.replace(OLD_SDK, SDK)
    manifest = manifest.replace('dependencies: [.package(path:', 'dependencies: [.package(path: "../CJFeasibilityClient"), .package(path:', 1)
    manifest = manifest.replace('dependencies: [.product(name:', 'dependencies: [.product(name: "CJFeasibilityClient", package: "CJFeasibilityClient"), .product(name:', 1)
    exports[path] = manifest.encode()
    for name in INPUTS:
        peer_manifest = exports[f'Modules/{name}/Package.swift'].decode()
        if name != 'CJAuth':
            assert SDK in peer_manifest and OLD_SDK not in peer_manifest, name
    provenance['verification_manifest_adjustments'] = {'CJShell': 'own FEAS dependency + direct dc29 path; every peer Package remains original'}
    # The existing standalone Demo script expects the canonical relative icons.
    # Export fixed branding assets too; do not borrow mutable build resources.
    for path in git(main, 'ls-tree', '-r', '--name-only', MAIN, 'ios/Branding/Assets').decode().splitlines():
        if Path(path).name.startswith('AppIcon') and path.endswith('.png'):
            exports[path.removeprefix('ios/')] = git(main, 'show', MAIN + ':' + path)
    test = module / 'Tests/CJShellTests/FeasibilityRealShellIntegrationTests.swift'
    exports['Modules/CJShell/Tests/CJShellTests/' + test.name] = test.read_bytes()
    assert not any(Path(p).name in ('ShellFacts.swift', 'SyntheticShell.swift') for p in exports)
    provenance['sha256'] = {p: hashlib.sha256(b).hexdigest() for p, b in sorted(exports.items())}
    digest = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()[:16]
    destination = module / '.local/feasibility-real-shell' / digest
    for path, data in exports.items():
        out = destination / path
        if any(p.is_symlink() for p in (out, *out.parents)):
            raise ValueError('symlink refused: ' + str(out))
        if out.exists() and out.read_bytes() != data:
            raise ValueError('existing export mismatch: ' + str(out))
    for path, data in exports.items():
        out = destination / path; out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists(): out.write_bytes(data)
    (destination / 'inputs.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkouts', type=Path)
    prepare(parser.parse_args().checkouts)
