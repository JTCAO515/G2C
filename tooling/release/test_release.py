"""Offline checks for the App flag list and the release script (#1760).

Usage: python3 -B -m unittest -v tooling.release.test_release
"""
import copy
import json
from pathlib import Path
import plistlib
import re
import tempfile
import unittest

from tooling.release import build_app

ROOT = Path(__file__).resolve().parents[2]
INFO_PLIST = ROOT / 'ios/App/Info.plist'


def beta_flag_pairs():
    """(Info.plist key, build setting) pairs in the Beta branch of the preprocessed Info.plist."""
    text = INFO_PLIST.read_text(encoding='utf-8')
    beta = text.split('#if G2C_DEMO_BETA_PLIST', 1)[1].split('#else', 1)[0]
    return re.findall(r'<key>(G2C[A-Za-z0-9]+Enabled)</key><string>\$\((G2C_[A-Z0-9_]+_ENABLED)\)</string>', beta)


def swift_flag_keys():
    keys = set()
    for path in (ROOT / 'ios').rglob('*.swift'):
        if '/Tests/' in str(path) or '/Acceptance/' in str(path):
            continue
        keys.update(re.findall(r'"(G2C[A-Za-z0-9]+Enabled)"', path.read_text(encoding='utf-8')))
    return keys


class FlagListTests(unittest.TestCase):
    def setUp(self):
        self.manifest = build_app.load_manifest()
        self.pairs = [(f['plist'], f['setting']) for f in self.manifest['flags']]

    def test_matches_info_plist_beta_keys_in_order(self):
        self.assertEqual(self.pairs, beta_flag_pairs())

    def test_every_flag_key_read_in_swift_is_listed(self):
        listed = {key for key, _ in self.pairs}
        self.assertEqual(swift_flag_keys() - listed, set(), 'a flag read in Swift is missing from app_flags.json')

    def test_every_listed_flag_is_read_in_swift(self):
        unread = {key for key, _ in self.pairs} - swift_flag_keys()
        self.assertEqual(unread, set(), 'a listed flag is read nowhere in the App')

    def test_release_section_is_consistent(self):
        release = self.manifest['release']
        self.assertLess(release['previous'], release['build'])
        self.assertTrue(set(release['on']) <= {s for _, s in self.pairs})


class ManifestValidationTests(unittest.TestCase):
    def write(self, manifest):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(manifest, tmp)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return tmp.name

    def base(self):
        return copy.deepcopy(json.loads(build_app.MANIFEST.read_text(encoding='utf-8')))

    def test_rejects_unknown_release_flag(self):
        m = self.base()
        m['release']['on'].append('G2C_UNKNOWN_ENABLED')
        with self.assertRaises(build_app.ReleaseError):
            build_app.load_manifest(self.write(m))

    def test_rejects_duplicate_flag(self):
        m = self.base()
        m['flags'].append(dict(m['flags'][0]))
        with self.assertRaises(build_app.ReleaseError):
            build_app.load_manifest(self.write(m))

    def test_rejects_previous_not_below_build(self):
        m = self.base()
        m['release']['previous'] = m['release']['build']
        with self.assertRaises(build_app.ReleaseError):
            build_app.load_manifest(self.write(m))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.manifest = build_app.load_manifest()
        self.manifest['release']['on'] = [self.manifest['flags'][0]['setting']]

    def test_archive_sets_every_flag_explicitly(self):
        cmd = build_app.archive_command(self.manifest, Path('a'), Path('d'), Path('p'))
        settings = {arg.split('=')[0]: arg.split('=')[1] for arg in cmd if arg.startswith('G2C_')}
        self.assertEqual(set(settings), {f['setting'] for f in self.manifest['flags']})
        self.assertEqual([k for k, v in settings.items() if v == 'YES'], self.manifest['release']['on'])
        self.assertIn('-configuration', cmd)
        self.assertEqual(cmd[cmd.index('-configuration') + 1], 'Beta')
        self.assertIn(f"CURRENT_PROJECT_VERSION={self.manifest['release']['build']}", cmd)

    def test_all_flags_turns_every_flag_on(self):
        args = build_app.flag_build_settings(self.manifest, all_flags=True)
        self.assertTrue(args and all(a.endswith('=YES') for a in args))

    def test_export_stays_internal(self):
        self.assertIs(build_app.export_options('upload')['testFlightInternalTestingOnly'], True)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.manifest = build_app.load_manifest()

    def test_flags_must_match(self):
        expected = build_app.expected_flags(self.manifest, all_flags=True)
        info = dict(expected)
        self.assertEqual(build_app.check_flags(info, expected), expected)
        key = next(iter(expected))
        for wrong in ('', 'NO', None, 'yes'):
            info[key] = wrong
            with self.subTest(value=wrong), self.assertRaises(build_app.ReleaseError):
                build_app.check_flags(info, expected)

    def test_off_flag_must_not_read_yes(self):
        self.manifest['release']['on'] = []
        expected = build_app.expected_flags(self.manifest)
        self.assertEqual(set(expected.values()), {''})
        build_app.check_flags({}, expected)
        with self.assertRaises(build_app.ReleaseError):
            build_app.check_flags({next(iter(expected)): 'YES'}, expected)

    def test_release_notes_must_name_this_build_first(self):
        build_app.check_notes({'currentBuild': 58, 'releases': [{'build': 58}, {'build': 57}]}, 58, 57)
        for book in ({'currentBuild': 57, 'releases': [{'build': 57}, {'build': 56}]},
                     {'currentBuild': 58, 'releases': [{'build': 58}, {'build': 56}]}):
            with self.subTest(book=book), self.assertRaises(build_app.ReleaseError):
                build_app.check_notes(book, 58, 57)

    def test_check_app_reads_a_built_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / 'CJProbeApp.app'
            app.mkdir()
            info = {'CFBundleExecutable': 'CJProbeApp', 'CFBundleDisplayName': 'Go2China', 'G2CDemoBeta': True,
                    **build_app.expected_flags(self.manifest, all_flags=True)}
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            (app / 'CJProbeApp').write_bytes(b'\0' + build_app.BETA_API + b'\0')
            self.assertEqual(build_app.main(['check-app', str(app), '--all-flags']), 0)
            info[next(iter(build_app.expected_flags(self.manifest)))] = ''
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            self.assertEqual(build_app.main(['check-app', str(app), '--all-flags']), 1)
            info.update(build_app.expected_flags(self.manifest, all_flags=True), G2CDemoBeta=False)
            (app / 'Info.plist').write_bytes(plistlib.dumps(info))
            self.assertEqual(build_app.main(['check-app', str(app), '--all-flags']), 1)

    def test_record_dir_must_be_outside_the_repository(self):
        with self.assertRaises(build_app.ReleaseError):
            build_app.Record(ROOT / 'release-record')

    def test_upload_refuses_a_rehearsal(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = build_app.Record(Path(tmp) / 'record')
            record.save('state.json', {'work': tmp, 'archive': tmp, 'rehearsal': True,
                                       'release': self.manifest['release'], 'flags': {}})
            self.assertEqual(build_app.main(['upload', '--record-dir', str(record.path)]), 1)
            self.assertFalse((record.path / 'upload-result.json').exists())


if __name__ == '__main__':
    unittest.main()
