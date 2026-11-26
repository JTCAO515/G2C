"""Unit tests for the pull-request path classifier used by ci.yml."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_paths import classify, split  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / 'ci_paths.py'


class ClassifyTests(unittest.TestCase):
    def check(self, paths, docs_only, ios_only, app_changed, web_only='false'):
        self.assertEqual(classify(paths), {
            'docs_only': docs_only, 'ios_only': ios_only, 'web_only': web_only, 'app_changed': app_changed})

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
                     '.github/workflows/ci.yml', '.github/swift-packages.json', '.gitattributes',
                     'tooling/release/app_flags.json', 'tooling/release/build_app.py'):
            with self.subTest(path=path):
                self.check([path, 'backend/a.py'], 'false', 'false', 'true')

    def test_any_non_ios_path_keeps_postgres(self):
        for path in ('backend/a.py', 'contracts/a.json', '.github/workflows/ci.yml', 'AGENTS.md',
                     'iosx/a', 'README.md', 'scripts/build-ios.sh'):
            with self.subTest(path=path):
                self.assertEqual(classify(['ios/App/a.swift', path])['ios_only'], 'false')

    def test_website_only_skips_postgres_but_keeps_python(self):
        """Approved 2026-11-26: web/, scripts/test_web_* and docs only -> no PostgreSQL shards."""
        self.check(['web/index.html'], 'false', 'false', 'false', web_only='true')
        self.check(['web/api/early-access.js', 'web/i18n.js', 'scripts/test_web_early_access.cjs',
                    'scripts/test_web_vercel_ignore.py', 'docs/privacy/privacy-policy.md', 'HANDOFF.md'],
                   'false', 'false', 'false', web_only='true')
        self.check(['scripts/test_web_service_request.cjs'], 'false', 'false', 'false', web_only='true')

    def test_any_other_path_with_the_website_runs_every_job(self):
        """The coordinating thread's required counter-examples, plus the neighbours of each prefix."""
        for other in ('backend/cj_api/app.py', 'ios/App/A.swift', '.github/workflows/ci.yml',
                      '.github/scripts/ci_paths.py', 'scripts/test.py', 'scripts/test_test_entry.py',
                      'scripts/build_privacy_page.cjs', 'contracts/service-request/V1.md', 'deploy/hk/x.py',
                      'eval/release_eval/bank.v2.json', 'knowledge/visitor/x.json', 'uv.lock', 'webx/a.html',
                      'scripts/test_web_x/inner.py', 'scripts/sub/test_web_a.cjs', 'tooling/release/app_flags.json'):
            with self.subTest(other=other):
                self.assertEqual(classify(['web/index.html', other])['web_only'], 'false')
        self.assertEqual(classify(['docs/a.md'])['web_only'], 'false')  # docs alone stays docs_only
        self.assertEqual(classify(['"web/\\346.html"'])['web_only'], 'false')  # unknown path: every job

    def test_website_only_still_runs_swift_when_the_app_reads_a_path(self):
        self.assertEqual(classify(['web/index.html', 'contracts/x.json'])['app_changed'], 'true')
        self.assertEqual(classify(['web/index.html', 'contracts/x.json'])['web_only'], 'false')

    def test_prefixes_are_anchored(self):
        self.check(['backend/ios/a.py'], 'false', 'false', 'false')
        self.check(['docs-old/a.md'], 'false', 'false', 'false')
        for path in ('iosx/a', '.github-old/x', 'contracts-v2/x', 'digital-assets-old/x', '.gitattributes.bak',
                     'tooling/releases/x', 'tooling/datasets/x'):
            with self.subTest(path=path):
                self.check([path], 'false', 'false', 'false')

    def test_quoted_or_non_ascii_paths(self):
        # With core.quotePath=false and -z, non-ASCII names arrive raw and classify normally.
        self.check(['ios/App/新.swift'], 'false', 'true', 'true')
        self.check(['docs/说明.md'], 'true', 'false', 'false')
        # A C-quoted name (quotePath left on) is unknown, so every job runs.
        self.check(['"ios/App/\\346\\226\\260.swift"'], 'false', 'false', 'true')
        self.check(['backend/a.py', '"docs/\\346.md"'], 'false', 'false', 'true')

    def test_nul_separated_input(self):
        self.assertEqual(split('ios/a b.swift\0docs/x.md\0'), ['ios/a b.swift', 'docs/x.md', ''])
        self.assertEqual(split('a\nb\n'), ['a', 'b'])
        self.check(split('ios/a b.swift\0docs/x.md\0'), 'false', 'true', 'true')

    def test_blank_lines_ignored_and_empty_refused(self):
        self.check(['', 'ios/a.swift', ''], 'false', 'true', 'true')
        with self.assertRaises(ValueError):
            classify(['', ''])

    def test_edge_spaces_are_part_of_the_path(self):
        # " docs/a.md" and "\tios/x.swift" are not under docs/ or ios/, so nothing is skipped
        # for them as documentation or iOS.
        self.check([' docs/a.md'], 'false', 'false', 'false')
        self.check(['HANDOFF.md '], 'false', 'false', 'false')
        self.check(['\tios/x.swift', 'ios/a.swift'], 'false', 'false', 'true')

    def test_cli_prints_outputs_and_fails_closed_on_empty_input(self):
        ok = subprocess.run([sys.executable, '-B', str(SCRIPT)], input='ios/a.swift\0',
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout, 'docs_only=false\nios_only=true\nweb_only=false\napp_changed=true\n')
        empty = subprocess.run([sys.executable, '-B', str(SCRIPT)], input='',
                               capture_output=True, text=True)
        self.assertNotEqual(empty.returncode, 0)
        self.assertEqual(empty.stdout, '')


if __name__ == '__main__':
    unittest.main()
