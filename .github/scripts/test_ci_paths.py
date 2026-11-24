"""Unit tests for the pull-request path classifier used by ci.yml."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_paths import classify  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / 'ci_paths.py'


class ClassifyTests(unittest.TestCase):
    def check(self, paths, docs_only, ios_only, app_changed):
        self.assertEqual(classify(paths), {
            'docs_only': docs_only, 'ios_only': ios_only, 'app_changed': app_changed})

    def test_docs_only(self):
        self.check(['docs/plan/issue-plan.md', 'HANDOFF.md'], 'true', 'false', 'false')

    def test_ios_only_skips_postgres_but_keeps_app(self):
        self.check(['ios/Modules/CJShell/Sources/A.swift'], 'false', 'true', 'true')
        self.check(['ios/App/B.swift', 'docs/x.md', 'HANDOFF.md'], 'false', 'true', 'true')

    def test_server_only_skips_app(self):
        self.check(['backend/cj_api/app.py', 'scripts/pg_suites.py', 'deploy/hk/x.py', 'uv.lock'],
                   'false', 'false', 'false')

    def test_paths_the_app_reads_keep_app_jobs(self):
        for path in ('contracts/message/x.json', 'digital-assets/ios-avatar/a.png',
                     '.github/workflows/ci.yml', '.github/swift-packages.json', '.gitattributes'):
            with self.subTest(path=path):
                self.check([path, 'backend/a.py'], 'false', 'false', 'true')

    def test_any_non_ios_path_keeps_postgres(self):
        for path in ('backend/a.py', 'contracts/a.json', '.github/workflows/ci.yml', 'AGENTS.md',
                     'iosx/a', 'README.md', 'scripts/build-ios.sh'):
            with self.subTest(path=path):
                self.assertEqual(classify(['ios/App/a.swift', path])['ios_only'], 'false')

    def test_prefixes_are_anchored(self):
        self.check(['backend/ios/a.py'], 'false', 'false', 'false')
        self.check(['docs-old/a.md'], 'false', 'false', 'false')

    def test_blank_lines_ignored_and_empty_refused(self):
        self.check(['', 'ios/a.swift', ''], 'false', 'true', 'true')
        with self.assertRaises(ValueError):
            classify(['', '  '])

    def test_cli_prints_outputs_and_fails_closed_on_empty_input(self):
        ok = subprocess.run([sys.executable, '-B', str(SCRIPT)], input='ios/a.swift\n',
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout, 'docs_only=false\nios_only=true\napp_changed=true\n')
        empty = subprocess.run([sys.executable, '-B', str(SCRIPT)], input='',
                               capture_output=True, text=True)
        self.assertNotEqual(empty.returncode, 0)
        self.assertEqual(empty.stdout, '')


if __name__ == '__main__':
    unittest.main()
