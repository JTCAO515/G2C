import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'preflight.py'
spec = importlib.util.spec_from_file_location('preflight', MODULE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payload = b'synthetic inventory only\n'
        (self.root / 'sample.bin').write_bytes(self.payload)
        self.data = {'manifest_version': preflight.FORMAT,
                     'candidate_commit': 'a' * 40,
                     'backup_time': '2026-10-23T10:00:00+08:00',
                     'component_versions': {'synthetic_component': '1.0.0'},
                     'files': [{'path': 'sample.bin', 'size_bytes': len(self.payload),
                                'sha256': hashlib.sha256(self.payload).hexdigest()}]}

    def run_check(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.data))
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file() and not p.is_symlink()}
        report = preflight.inspect(str(self.root), 'manifest.json')
        self.assertEqual(report['restore_authorization'], 'UNRUN')
        self.assertIs(report['read_enable'], False)
        after = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file() and not p.is_symlink()}
        self.assertEqual(before, after)
        return report

    def statuses(self, report):
        return {c['item']: c['status'] for c in report['checks']}

    def test_complete_bytes_still_unknown(self):
        result = self.run_check()
        self.assertEqual(result['offline_check_status'], 'UNKNOWN')
        self.assertEqual(self.statuses(result)['files[0]'], 'PASS')
        for name in ('actual_restore', 'application_compatibility', 'latest_withdrawal_replay'):
            self.assertEqual(self.statuses(result)[name], 'UNKNOWN')

    def test_missing(self):
        (self.root / 'sample.bin').unlink()
        result = self.run_check()
        self.assertEqual(result['missing_files'], ['sample.bin'])
        self.assertEqual(result['offline_check_status'], 'FAIL')

    def test_hash_mismatch(self):
        self.data['files'][0]['sha256'] = '0' * 64
        self.assertEqual(self.statuses(self.run_check())['files[0]'], 'FAIL')

    def test_size_mismatch(self):
        self.data['files'][0]['size_bytes'] += 1
        self.assertEqual(self.statuses(self.run_check())['files[0]'], 'FAIL')

    def test_duplicate(self):
        self.data['files'] *= 2
        self.assertEqual(self.statuses(self.run_check())['files[1]'], 'FAIL')

    def test_missing_metadata(self):
        for field in ('manifest_version', 'candidate_commit', 'backup_time', 'component_versions'):
            with self.subTest(field=field):
                original = copy.deepcopy(self.data)
                del self.data[field]
                self.assertEqual(self.statuses(self.run_check())[field], 'UNKNOWN')
                self.data = original

    def test_invalid_metadata(self):
        for field, value in [('manifest_version', True), ('candidate_commit', 'main'),
                             ('backup_time', '2026-10-23T10:00:00'),
                             ('component_versions', {'x': 'UNKNOWN'})]:
            with self.subTest(field=field):
                original = copy.deepcopy(self.data)
                self.data[field] = value
                self.assertNotEqual(self.statuses(self.run_check())[field], 'PASS')
                self.data = original

    def test_claimed_pass_never_grants_read(self):
        self.data.update({'read_enable': True, 'restore_authorization': 'PASS',
                          'actual_restore': True, 'application_compatibility': 'PASS',
                          'latest_withdrawal_replay': {'status': 'PASS'}})
        self.assertEqual(self.run_check()['offline_check_status'], 'UNKNOWN')

    def test_traversal_and_aliases_rejected(self):
        for path in ('../sample.bin', '/sample.bin', 'a/../sample.bin', './sample.bin',
                     'a//b', 'a\\b', '', None):
            with self.subTest(path=path):
                self.data['files'][0]['path'] = path
                self.assertEqual(self.statuses(self.run_check())['files[0]'], 'FAIL')

    def test_nonregular_and_link_paths(self):
        (self.root / 'directory').mkdir()
        os.mkfifo(self.root / 'fifo')
        (self.root / 'link').symlink_to(self.root / 'sample.bin')
        (self.root / 'parent-link').symlink_to(self.root, target_is_directory=True)
        for path in ('directory', 'fifo', 'link', 'parent-link/sample.bin'):
            with self.subTest(path=path):
                self.data['files'][0]['path'] = path
                # Avoid fixture snapshots opening the FIFO.
                (self.root / 'manifest.json').write_text(json.dumps(self.data))
                real_open = os.open
                with patch.object(preflight.os, 'open', wraps=real_open) as opened:
                    result = preflight.inspect(str(self.root), 'manifest.json')
                self.assertNotIn(path.split('/')[-1], [call.args[0] for call in opened.call_args_list])
                self.assertEqual(self.statuses(result)['files[0]'], 'FAIL')
                self.assertFalse(result['read_enable'])

    def test_hardlink_rejected(self):
        os.link(self.root / 'sample.bin', self.root / 'alias')
        self.assertEqual(self.statuses(self.run_check())['files[0]'], 'FAIL')

    def test_invalid_and_duplicate_key_manifests(self):
        for raw in ('{', '[]', '{"files":[],"files":[]}', '[' * 2000 + ']' * 2000, 'x' * (preflight.MANIFEST_LIMIT + 1)):
            (self.root / 'manifest.json').write_text(raw)
            result = preflight.inspect(str(self.root), 'manifest.json')
            self.assertEqual(result['offline_check_status'], 'FAIL')
            self.assertFalse(result['read_enable'])

    def test_manifest_and_root_links_rejected(self):
        self.run_check()
        (self.root / 'manifest-link').symlink_to(self.root / 'manifest.json')
        self.assertEqual(preflight.inspect(str(self.root), 'manifest-link')['offline_check_status'], 'FAIL')
        (self.root / 'root-link').symlink_to(self.root, target_is_directory=True)
        self.assertEqual(preflight.inspect(str(self.root / 'root-link'), 'manifest.json')['offline_check_status'], 'FAIL')

    def test_bad_inventory(self):
        for files in (None, [], [True], [{'path': 'sample.bin', 'size_bytes': True, 'sha256': '0' * 64}]):
            self.data['files'] = files
            self.assertEqual(self.run_check()['offline_check_status'], 'FAIL')

    def test_cli_unknown_and_fail_exit_codes_no_content(self):
        self.run_check()
        args = [sys.executable, str(MODULE), '--root', str(self.root), '--manifest', 'manifest.json']
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(self.payload.decode().strip(), result.stdout)
        self.assertFalse(json.loads(result.stdout)['read_enable'])
        (self.root / 'sample.bin').unlink()
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
