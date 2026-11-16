"""Build the actual ordinary-Home render function as a pinned, read-only host executable.

This proves source-bound text projection only. macOS Foundation and actual iOS AX
must still be compared; app/build metadata echoed by the program is not attested.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
RENDER_SOURCES = (
    'ios/Modules/CJShell/Sources/CJLioUser/LioReplyMarkdown.swift',
    'ios/Modules/CJMessageClient/Sources/CJMessageHTTP/LioPublicDisplay.swift',
    'ios/Modules/CJShell/Sources/CJLioUser/LioTheme.swift',
    'ios/Modules/CJShell/Sources/CJLioUser/LioStreamingText.swift',
)


def source_pin(root):
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--', 'ios'], text=True)
    if dirty:
        raise ValueError('Projector source must be a clean pinned iOS checkout')
    files = [{'path': name, 'sha256': hashlib.sha256((root / name).read_bytes()).hexdigest()} for name in RENDER_SOURCES]
    encoded = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    return commit, files, hashlib.sha256(encoded).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.source_root.resolve(), args.output.resolve()
    if output.is_relative_to(root):
        parser.error('Keep the executable, package and logs outside the repository')
    before = source_pin(root)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = output / 'Sources/LioReplyProjector'; source.mkdir(parents=True)
    shutil.copy2(HERE / 'LioReplyProjector.swift', source / 'main.swift')
    (source / 'Pin.swift').write_text('enum ProjectorPin { static let source = ' + json.dumps(before[0])
                                    + '; static let renderer = ' + json.dumps(before[2]) + ' }\n')
    (output / 'Package.swift').write_text('''// swift-tools-version: 6.1
import PackageDescription
let package = Package(name: "LioReplyProjector", platforms: [.macOS(.v14)], dependencies: [
    .package(path: ''' + json.dumps(str(root / 'ios/Modules/CJShell')) + ''')
], targets: [.executableTarget(name: "LioReplyProjector", dependencies: [.product(name: "CJLioUser", package: "CJShell")])])
''')
    shutil.copy2(root / 'ios/Package.resolved', output / 'Package.resolved')
    with (output / 'build.log').open('w') as log:
        subprocess.run(['swift', 'build', '--package-path', str(output), '-Xswiftc', '-enable-testing'],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1200)
    binary_path = Path(subprocess.check_output(['swift', 'build', '--package-path', str(output), '--show-bin-path'], text=True).strip()) / 'LioReplyProjector'
    if source_pin(root) != before:
        raise ValueError('Pinned source changed while building the projector')
    manifest = dict(source_commit=before[0], renderer_source_sha256=before[2], renderer_sources=before[1],
                    executable=str(binary_path), executable_sha256=hashlib.sha256(binary_path.read_bytes()).hexdigest(),
                    projection_environment='macOS Foundation; not an iOS/device or UI witness',
                    scope='source projection only; no release, provider or App artifact authority')
    path = output / 'projector.json'; path.write_text(json.dumps(manifest, indent=2) + '\n'); path.chmod(0o600)
    print(json.dumps({'manifest': str(path), 'source_commit': before[0], 'renderer_source_sha256': before[2]}))


if __name__ == '__main__':
    main()
