"""Archive, check, export and upload a Go2China TestFlight build (#1760).

Generalises the build-57 release script. The flags come from app_flags.json, the same list CI
builds with every flag on (#1762), so a release and CI cannot disagree about which flags exist.

Usage (run outside the command sandbox: xcodebuild and git write outside the checkout):
  python3 tooling/release/build_app.py archive SHA --record-dir DIR [--work-dir DIR] [--rehearsal]
  python3 tooling/release/build_app.py verify-archive --record-dir DIR
  python3 tooling/release/build_app.py export --record-dir DIR
  python3 tooling/release/build_app.py verify-ipa --record-dir DIR
  python3 tooling/release/build_app.py upload --record-dir DIR
  python3 tooling/release/build_app.py check-app APP [--all-flags]

SHA must be a main commit whose push CI passed. Build, previous build, marketing version and the
flags turned on come from release in app_flags.json. --record-dir keeps the commands, logs and
verification results of one build (outside the repository); --work-dir holds the source checkout,
archive and IPA (default: $TMPDIR/g2c-app-build<N>). --rehearsal makes a build that may not upload:
the release-notes check is reported instead of enforced, and upload refuses.
upload runs once and refuses if a result already exists.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).resolve().with_name('app_flags.json')
NOTES = 'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioBuildUpdates.v1.json'
REPO = 'JTCAO515/G2C'
TEAM = 'NLD68762GG'
BUNDLE_ID = 'space.go2china.app'
BETA_API = b'https://api-beta.go2china.space'


class ReleaseError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def load_manifest(path=MANIFEST):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    flags = manifest['flags']
    settings = [f['setting'] for f in flags]
    keys = [f['plist'] for f in flags]
    require(len(set(settings)) == len(settings) and len(set(keys)) == len(keys), 'duplicate flag in app_flags.json')
    require(all(re.fullmatch(r'G2C_[A-Z0-9_]+_ENABLED', s) for s in settings), 'flag settings are G2C_*_ENABLED')
    require(all(re.fullmatch(r'G2C[A-Za-z0-9]+Enabled', k) for k in keys), 'flag Info.plist keys are G2C*Enabled')
    release = manifest['release']
    on = release['on']
    require(len(set(on)) == len(on) and set(on) <= set(settings), 'release.on names flags that are not listed')
    require(isinstance(release['build'], int) and isinstance(release['previous'], int)
            and release['previous'] < release['build'], 'release.previous must be below release.build')
    return manifest


def expected_flags(manifest, all_flags=False):
    """Info.plist key -> the value the built App must carry ("YES" on, "" off)."""
    on = {f['setting'] for f in manifest['flags']} if all_flags else set(manifest['release']['on'])
    return {f['plist']: 'YES' if f['setting'] in on else '' for f in manifest['flags']}


def flag_build_settings(manifest, all_flags=False):
    """xcodebuild arguments for every flag: YES when on, NO when off (never left to the project)."""
    on = {f['setting'] for f in manifest['flags']} if all_flags else set(manifest['release']['on'])
    return [f"{f['setting']}={'YES' if f['setting'] in on else 'NO'}" for f in manifest['flags']]


def check_flags(info, expected):
    """Every flag key must read exactly as expected; an off flag reads anything but YES."""
    wrong = {}
    for key, value in expected.items():
        actual = info.get(key)
        if (value == 'YES') != (actual == 'YES'):
            wrong[key] = actual
    require(not wrong, f'flags in the built Info.plist differ from app_flags.json: {wrong}')
    return {key: info.get(key) for key in expected}


def check_notes(book, build, previous):
    require(book.get('currentBuild') == build, f"release notes currentBuild is {book.get('currentBuild')}, not {build}")
    # The App decodes exactly two releases (this build and the previous one), as build 57 checked.
    builds = [x['build'] for x in book.get('releases', [])]
    require(builds == [build, previous], f'release notes list builds {builds}, not {[build, previous]}')


def archive_command(manifest, archive, derived, packages):
    release = manifest['release']
    return ['xcodebuild', 'archive', '-project', 'ios/CJProbeApp.xcodeproj', '-scheme', 'G2CBeta',
            '-configuration', 'Beta', '-destination', 'generic/platform=iOS', '-derivedDataPath', str(derived),
            '-clonedSourcePackagesDirPath', str(packages), '-onlyUsePackageVersionsFromResolvedFile',
            '-archivePath', str(archive), f"CURRENT_PROJECT_VERSION={release['build']}",
            f"MARKETING_VERSION={release['marketing_version']}", f'DEVELOPMENT_TEAM={TEAM}',
            'CODE_SIGN_STYLE=Automatic', 'CODE_SIGN_IDENTITY=Apple Development',
            *flag_build_settings(manifest)]


def export_options(destination):
    return {'destination': destination, 'manageAppVersionAndBuildNumber': False, 'method': 'app-store-connect',
            'signingStyle': 'automatic', 'teamID': TEAM, 'testFlightInternalTestingOnly': True}


def out(*argv, cwd=None):
    return subprocess.check_output(argv, cwd=cwd, text=True).strip()


class Record:
    """One build's record directory: commands, logs, results. Steps after archive read state.json."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        require(ROOT not in self.path.parents and self.path != ROOT, 'keep --record-dir outside the repository')
        self.path.mkdir(parents=True, exist_ok=True)

    def save(self, name, value):
        (self.path / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def load(self, name):
        path = self.path / name
        require(path.exists(), f'{path} is missing; run the earlier step first')
        return json.loads(path.read_text(encoding='utf-8'))


def source_ci_passed(sha):
    runs = json.loads(out('gh', 'api', f'repos/{REPO}/actions/runs?head_sha={sha}&event=push'))['workflow_runs']
    ci = [r for r in runs if r['name'] == 'ci']
    require(ci and ci[0]['conclusion'] == 'success', 'main push CI must be green on the exact source')
    jobs = json.loads(out('gh', 'api', f'repos/{REPO}/actions/runs/{ci[0]["id"]}/jobs?per_page=50'))['jobs']
    require(jobs and all(j['conclusion'] in ('success', 'skipped') for j in jobs), 'a CI job of the source did not pass')
    return {'sha': sha, 'run': ci[0]['html_url'], 'jobs': [(j['name'], j['conclusion']) for j in jobs]}


def archive(sha, record, work, rehearsal):
    manifest = load_manifest()
    require(re.fullmatch(r'[0-9a-f]{40}', sha), 'give the full 40-character source SHA')
    require(not (record.path / 'state.json').exists(), 'this record directory already holds a build')
    record.save('source-ci-pass.json', source_ci_passed(sha))
    source, archive_path = work / 'source', work / f"Go2China{manifest['release']['build']}.xcarchive"
    require(not archive_path.exists(), f'{archive_path} already exists')
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'fetch', '-q', 'origin'], cwd=ROOT, check=True)
    if not source.exists():
        subprocess.run(['git', 'worktree', 'add', '-q', '--detach', str(source), sha], cwd=ROOT, check=True)
    require(out('git', 'rev-parse', 'HEAD', cwd=source) == sha, f'{source} is not at {sha}')
    require(not out('git', 'status', '--porcelain', cwd=source), f'{source} has local changes')
    cmd = archive_command(manifest, archive_path, work / 'Derived', work / 'SourcePackages')
    state = {'sha': sha, 'work': str(work), 'archive': str(archive_path), 'rehearsal': rehearsal,
             'release': manifest['release'], 'flags': expected_flags(manifest)}
    record.save('archive-command.json', cmd)
    record.save('state.json', state)
    with (record.path / 'archive.log').open('w') as log:
        result = subprocess.run(cmd, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    record.save('archive-result.json', {'returncode': result.returncode, 'source': sha})
    require(result.returncode == 0, 'archive failed, see archive.log')
    print(f"ARCHIVE SUCCEEDED Go2China {manifest['release']['marketing_version']} "
          f"({manifest['release']['build']}) from {sha}" + (' [rehearsal]' if rehearsal else ''))


def inspect_app(app, flags):
    """The checks every built Beta App must pass, signed or not."""
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    result = {'bundle_id': info.get('CFBundleIdentifier'), 'version': info.get('CFBundleShortVersionString'),
              'build': info.get('CFBundleVersion'), 'display_name': info.get('CFBundleDisplayName'),
              'demo_beta': info.get('G2CDemoBeta'), 'flags': check_flags(info, flags)}
    require(result['demo_beta'] is True, 'G2CDemoBeta is not true: not a Beta configuration build')
    require(result['display_name'] == 'Go2China', f"display name is {result['display_name']}")
    exe = app / info['CFBundleExecutable']
    require(BETA_API in exe.read_bytes(), 'the executable does not carry the Beta API host')
    return info, result


def verify(kind, record):
    state = record.load('state.json')
    work, release = Path(state['work']), state['release']
    if kind == 'archive':
        app = next((Path(state['archive']) / 'Products/Applications').glob('*.app'))
    else:
        ipa = next((work / 'Export').glob('*.ipa'))
        with zipfile.ZipFile(ipa) as z:
            require(not [n for n in z.namelist() if n.startswith('__MACOSX/') or '/._' in n], 'stray files in IPA')
        extract = work / 'ipa-verify'
        extract.mkdir(exist_ok=False)
        subprocess.run(['ditto', '-x', '-k', str(ipa), str(extract)], check=True)
        app = next((extract / 'Payload').glob('*.app'))
    sign = subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)],
                          capture_output=True, text=True)
    require(sign.returncode == 0, sign.stderr)
    info, r = inspect_app(app, state['flags'])
    ent = plistlib.loads(subprocess.run(['codesign', '-d', '--entitlements', ':-', str(app)],
                                        capture_output=True, check=True).stdout)
    exe = app / info['CFBundleExecutable']
    links, symbols = out('otool', '-L', str(exe)), out('nm', '-u', str(exe))
    r.update({'team': ent['com.apple.developer.team-identifier'], 'minimum_os': info['MinimumOSVersion'],
              'amap_linkage': len(re.findall(r'AMap|MAMap', links, re.I)),
              'amap_symbols': len(re.findall(r'AMap|MAMap', symbols)), 'mapkit_linked': 'MapKit.framework' in links,
              'nonexempt_encryption': info.get('ITSAppUsesNonExemptEncryption'),
              'mic_usage': bool(info.get('NSMicrophoneUsageDescription')),
              'camera_usage': bool(info.get('NSCameraUsageDescription')),
              'location_usage': bool(info.get('NSLocationWhenInUseUsageDescription'))})
    require(r['bundle_id'] == BUNDLE_ID and r['version'] == release['marketing_version']
            and r['build'] == str(release['build']), f"identity is {r['bundle_id']} {r['version']} ({r['build']})")
    require(r['team'] == TEAM and r['minimum_os'] == '17.0', f"team {r['team']}, minimum iOS {r['minimum_os']}")
    require(r['amap_linkage'] == 0 and r['amap_symbols'] == 0 and r['mapkit_linked'], 'map linkage changed')
    require(r['nonexempt_encryption'] is False and r['mic_usage'] and r['camera_usage'] and r['location_usage'],
            'export compliance or a usage description is missing')
    notes = list(app.rglob(Path(NOTES).name))
    require(len(notes) == 1, f'expected one {Path(NOTES).name} in the App, found {len(notes)}')
    require(notes[0].read_bytes() == (work / 'source' / NOTES).read_bytes(), 'bundled release notes differ from source')
    r['release_notes_sha256'] = hashlib.sha256(notes[0].read_bytes()).hexdigest()
    try:
        check_notes(json.loads(notes[0].read_text(encoding='utf-8')), release['build'], release['previous'])
        r['release_notes'] = 'PASS'
    except ReleaseError as error:
        if not state['rehearsal']:
            raise
        r['release_notes'] = f'REHEARSAL, not enforced: {error}'
    if kind == 'ipa':
        sig = subprocess.run(['codesign', '-dvv', str(app)], capture_output=True, text=True, check=True)
        require('Authority=Apple Distribution:' in sig.stderr, 'the IPA is not signed for distribution')
        r['get_task_allow'] = ent.get('get-task-allow', False)
        require(r['get_task_allow'] is False, 'get-task-allow is set')
        r['internal_only'] = plistlib.loads((work / 'Export/ExportOptions.plist').read_bytes())['testFlightInternalTestingOnly']
        require(r['internal_only'] is True, 'the export is not limited to internal testing')
        r['ipa_sha256'] = hashlib.sha256(ipa.read_bytes()).hexdigest()
    r['rehearsal'] = state['rehearsal']
    record.save(f'{kind}-verification.json', r)
    print(json.dumps(r, indent=2, ensure_ascii=False))


def export(destination, record):
    state = record.load('state.json')
    work = Path(state['work'])
    if destination == 'upload':
        require(not state['rehearsal'], 'a rehearsal build is never uploaded')
        verified = record.load('ipa-verification.json')
        require(verified['build'] == str(state['release']['build']), 'verify-ipa first')
    options = record.path / f'{destination}-options.plist'
    options.write_bytes(plistlib.dumps(export_options(destination)))
    target = work / ('Export' if destination == 'export' else 'Upload')
    result = record.path / f'{destination}-result.json'
    require(not result.exists(), f'{destination} already ran once')
    require(not target.exists(), f'{target} already exists')
    cmd = ['xcodebuild', '-exportArchive', '-archivePath', state['archive'], '-exportPath', str(target),
           '-exportOptionsPlist', str(options), '-allowProvisioningUpdates']
    with (record.path / f'{destination}.log').open('w') as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    record.save(result.name, {'returncode': r.returncode, 'build': state['release']['build']})
    require(r.returncode == 0, f'{destination} failed, see {destination}.log')
    print(f"{destination.upper()} SUCCEEDED for build {state['release']['build']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=['archive', 'verify-archive', 'export', 'verify-ipa', 'upload', 'check-app'])
    parser.add_argument('target', nargs='?', help='archive: source SHA; check-app: path to the built .app')
    parser.add_argument('--record-dir')
    parser.add_argument('--work-dir')
    parser.add_argument('--rehearsal', action='store_true')
    parser.add_argument('--all-flags', action='store_true', help='check-app: expect every flag on (CI)')
    args = parser.parse_args(argv)
    try:
        if args.step == 'check-app':
            require(args.target, 'give the .app path')
            _, result = inspect_app(Path(args.target), expected_flags(load_manifest(), args.all_flags))
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        require(args.record_dir, '--record-dir is required')
        record = Record(args.record_dir)
        if args.step == 'archive':
            require(args.target, 'give the source SHA')
            build = load_manifest()['release']['build']
            work = Path(args.work_dir) if args.work_dir else Path(tempfile.gettempdir()) / f'g2c-app-build{build}'
            archive(args.target, record, work.resolve(), args.rehearsal)
        elif args.step in ('verify-archive', 'verify-ipa'):
            verify(args.step.split('-')[1], record)
        else:
            export(args.step, record)
    except ReleaseError as error:
        print(f'{args.step} refused: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
