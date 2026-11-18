"""Actual Home and existing timeline fixture; synthetic only, no account/provider."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent


def source_pin():
    names = set(subprocess.check_output(['git', 'ls-files', 'ios'], cwd=ROOT, text=True).splitlines())
    names.update(('ios/App/Acceptance/check_lio_failure_next_step.py',
                  'ios/App/Acceptance/LioFailureNextStepUITests.swift', 'scripts/check_ios_trip_confirm.py'))
    files = [dict(path=name, sha256=hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
             for name in sorted(names)]
    return dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                files_sha256=hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--language', choices=('en', 'zh-Hans'), required=True)
    parser.add_argument('--appearance', choices=('light', 'dark'), default='light')
    parser.add_argument('--failure', choices=('unavailable', 'limit'), default='unavailable')
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        parser.error('Keep evidence and products outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    before = source_pin()
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'Go2China-A-Failure-Help-' + output.name,
        'com.apple.CoreSimulator.SimDeviceType.iPhone-15-Pro', 'com.apple.CoreSimulator.SimRuntime.iOS-17-5'], text=True).strip()
    report = dict(source=before, simulator=simulator, language=args.language,
                  appearance=args.appearance, failure=args.failure, real_service='UNRUN')
    try:
        spec = importlib.util.spec_from_file_location('original_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
        tests = (HERE / 'LioFailureNextStepUITests.swift').read_text()
        texts = {'unavailable': {'en': 'I couldn’t complete this request.', 'zh-Hans': '这次没能完成你的请求。'},
                 'limit': {'en': 'Lio couldn’t finish this request within the current limit.', 'zh-Hans': '这次没能在限额内答完。'}}
        scenario = '--lio-accepted-' + ('failure' if args.failure == 'unavailable' else 'limit') + '-acceptance'
        for key, value in {'__FAILURE_LANGUAGE__': args.language, '__FAILURE_APPEARANCE__': args.appearance,
                           '__FAILURE_SCENARIO__': scenario, '__FAILURE_TEXT__': texts[args.failure][args.language],
                           '__EMPTY_NOTES_TEXT__': '暂无问题记录。' if args.language == 'zh-Hans' else 'No problems noted.'}.items():
            tests = tests.replace(key, value)
        (output / 'G2CControl.swift').write_text(tests)
        original = ROOT / 'ios/App/CJProbeApp.swift'; source = original.read_text()
        marker = '        if let encoded = ProcessInfo.processInfo.environment["G2C_LIO_PREVIEW_TRIP"] {'
        assert source.count(marker) == 1
        source = source.replace(marker, '        if ProcessInfo.processInfo.arguments.contains("--lio-timeline-acceptance") {\n            LioTimelineFixture(shell: shell, exerciseResend: false)\n        } else ' + marker.lstrip())
        source = source.replace('import CJLioUser\n', '@testable import CJLioUser\n')
        generated = output / 'CJProbeApp.swift'
        generated.write_text(source + '\n' + (HERE / 'LioTimelineFixture.swift').read_text())
        project = output / 'G2CAcceptance.xcodeproj'; settings = project / 'project.pbxproj'
        settings.write_text(settings.read_text().replace(str(original), str(generated))
                            .replace('space.go2china.foundation.local', 'space.go2china.failure-help.acceptance'))
        result = output / 'failure-help.xcresult'
        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination',
                   'platform=iOS Simulator,id=' + simulator, '-derivedDataPath', str(build),
                   '-resultBundlePath', str(result), '-onlyUsePackageVersionsFromResolvedFile',
                   '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
                   'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                   '-only-testing:G2CControl/LioFailureNextStepUITests', 'test']
        (output / 'command.json').write_text(json.dumps(command, indent=2)+'\n')
        report['generated_source_sha256'] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
            for f in (generated, output / 'G2CControl.swift')}
        env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
        with (output / 'xcodebuild.log').open('w') as log:
            run = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)])
        (output / 'summary.json').write_bytes(summary)
        value = json.loads(summary)
        report['xcodebuild_exit'] = run.returncode
        report['actual_devices'] = [item['device']['deviceId'] for item in value['devicesAndConfigurations']]
        assert report['actual_devices'] == [simulator]
        assert run.returncode == 0 and [value[k] for k in ('passedTests', 'failedTests', 'skippedTests')] == [1, 0, 0]
    finally:
        stopped = subprocess.run(['xcrun', 'simctl', 'shutdown', simulator], capture_output=True)
        report['shutdown_exit'] = stopped.returncode
        report['source_after'] = source_pin()
        report['source_unchanged'] = before == report['source_after']
        (output / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        assert report['source_unchanged'], 'Preserve results but do not qualify changed source'


if __name__ == '__main__':
    main()
