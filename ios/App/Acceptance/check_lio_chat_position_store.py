"""Run the App-owned encrypted position store against synthetic official key providers only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error('Keep generated packages and logs outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    sources = output / 'Sources/LioPositionStoreAcceptance'
    tests = output / 'Tests/LioPositionStoreAcceptanceTests'
    sources.mkdir(parents=True); tests.mkdir(parents=True)
    source = ROOT / 'ios/App/LioChatPositionStore.swift'
    shutil.copy2(source, sources / source.name)
    shutil.copy2(ROOT / 'ios/App/LioChatPositionBinding.swift', sources / 'LioChatPositionBinding.swift')
    shutil.copy2(HERE / 'LioChatPositionStoreTests.swift', tests / 'LioChatPositionStoreTests.swift')
    package = f'''// swift-tools-version: 6.1
import PackageDescription
let package = Package(name: "LioPositionStoreAcceptance", platforms: [.macOS(.v14)], dependencies: [
    .package(path: {json.dumps(str(ROOT / 'ios/Modules/CJShell'))}),
    .package(path: {json.dumps(str(ROOT / 'ios/Modules/CJAuth'))}),
    .package(path: {json.dumps(str(ROOT / 'ios/Modules/CJMessageClient'))})
], targets: [
    .target(name: "LioPositionStoreAcceptance", dependencies: [.product(name: "CJLioUser", package: "CJShell"), .product(name: "CJMessageKeys", package: "CJAuth"), .product(name: "CJMessageClient", package: "CJMessageClient")]),
    .testTarget(name: "LioPositionStoreAcceptanceTests", dependencies: ["LioPositionStoreAcceptance", .product(name: "CJLioUser", package: "CJShell"), .product(name: "CJMessageKeys", package: "CJAuth")])
])
'''
    (output / 'Package.swift').write_text(package)
    shutil.copy2(ROOT / 'ios/Package.resolved', output / 'Package.resolved')
    inputs = [source, ROOT / 'ios/App/LioChatPositionBinding.swift',
              ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioChatLibrary.swift',
              ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioChatPosition.swift']
    manifest = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    (output / 'source.json').write_text(json.dumps({'source_files': manifest,
        'evidence': 'local synthetic; not full App, Hong Kong or device'}, indent=2) + '\n')
    with (output / 'tests.log').open('w') as log:
        subprocess.run(['swift', 'test', '--package-path', str(output)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)


if __name__ == '__main__':
    main()
