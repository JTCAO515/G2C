"""Native synthetic day-chip card; no network or account material."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or args.build_dir.resolve().is_relative_to(ROOT):
        parser.error('Keep evidence and builds outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('original_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
    (output / 'G2CControl.swift').write_bytes((HERE / 'LioDayChipCardUITests.swift').read_bytes())
    original = ROOT / 'ios/App/CJProbeApp.swift'
    source = original.read_text().replace('import CJLioUser\n', '@testable import CJLioUser\n')
    marker = '                    lioPreview\n'
    if source.count(marker) != 1: raise ValueError('The preview composition changed')
    source = source.replace(marker, '                    LioDayChipCardFixture(chinese: shell.language == .chinese)\n')
    generated = output / 'CJProbeApp.swift'
    generated.write_text(source + '\n' + (HERE / 'LioDayChipCardFixture.swift').read_text())
    project = output / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
    pbx.write_text(pbx.read_text().replace(str(original), str(generated))
        .replace('space.go2china.foundation.local', 'space.go2china.card.acceptance'))
    result = output / 'card.xcresult'
    selectors = [f'-only-testing:G2CControl/LioDayChipCardUITests/{name}' for name in args.case] if args.case else []
    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination',
        'platform=iOS Simulator,id=' + args.simulator, '-derivedDataPath', str(args.build_dir),
        '-resultBundlePath', str(result), '-onlyUsePackageVersionsFromResolvedFile',
        '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
        'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', *selectors, 'test']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
    with (output / 'card.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
    summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)])
    (output / 'summary.json').write_bytes(summary)
    value = json.loads(summary)
    assert value['passedTests'] == (len(args.case) if args.case else 6)
    assert value['failedTests'] == 0 and value['skippedTests'] == 0


if __name__ == '__main__': main()
