"""Check actual warm-session retained conversation in a disposable no-network native fixture."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or args.build_dir.resolve().is_relative_to(ROOT):
        parser.error('Keep products and evidence outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
    (output / 'G2CControl.swift').write_bytes((HERE / 'LioWarmSessionUITests.swift').read_bytes())
    app_source = ROOT / 'ios/App/CJProbeApp.swift'
    text = app_source.read_text().replace('import CJLioUser\n', '@testable import CJLioUser\nimport CJMessageHTTP\n')
    marker = '                    lioPreview\n'
    if text.count(marker) != 1:
        raise ValueError('Existing preview composition changed')
    text = text.replace(marker, '                    LioWarmSessionFixture(language: shell.language.lio)\n')
    generated = output / 'CJProbeApp.swift'
    generated.write_text(text + '\n' + (HERE / 'LioWarmSessionFixture.swift').read_text())
    project = output / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
    pbx.write_text(pbx.read_text().replace(str(app_source), str(generated))
                   .replace('space.go2china.foundation.local', 'space.go2china.warm-session.acceptance'))
    result = output / 'warm-session.xcresult'
    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl',
               '-destination', f'platform=iOS Simulator,id={args.simulator}', '-derivedDataPath', str(args.build_dir),
               '-resultBundlePath', str(result), '-onlyUsePackageVersionsFromResolvedFile',
               '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
               'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
               *([f'-only-testing:G2CControl/LioWarmSessionUITests/{case}' for case in args.case] if args.case else []), 'test']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
    with (output / 'warm-session.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)])
    (output / 'summary.json').write_bytes(summary)
    value = json.loads(summary)
    assert value['passedTests'] == (len(args.case) if args.case else 4) and value['failedTests'] == 0 and value['skippedTests'] == 0


if __name__ == '__main__': main()
