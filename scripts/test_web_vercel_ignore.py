"""Offline checks for web/vercel.json ignoreCommand (#1719): the site deploys only when web/ changed.

Vercel runs ignoreCommand in the Root Directory (web/) after cloning: exit 0 skips the build,
any other exit builds. Each case runs the command from vercel.json with sh in a throwaway repo.

Usage: python3 -B -m unittest -v scripts.test_web_vercel_ignore
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = json.loads((ROOT / 'web/vercel.json').read_text(encoding='utf-8'))['ignoreCommand']


class Repo:
    def __init__(self, path):
        self.path = path
        self.git('init', '-q', '-b', 'main')
        self.commit('web/index.html', 'v1')

    def git(self, *args):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
               'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
        return subprocess.run(['git', *args], cwd=self.path, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, name, text):
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', name)
        return self.git('rev-parse', 'HEAD')

    def merge(self, branch_files):
        """A pull request branch merged into main with a merge commit, like the GitHub merge button."""
        self.git('checkout', '-q', '-b', 'pr')
        for name, text in branch_files:
            self.commit(name, text)
        self.git('checkout', '-q', 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'merge pr', 'pr')
        self.git('branch', '-q', '-D', 'pr')
        return self.git('rev-parse', 'HEAD')

    def ignore(self, env='production', previous=''):
        current = {k: v for k, v in os.environ.items() if not k.startswith('VERCEL_')}
        current.update(VERCEL_ENV=env, VERCEL_GIT_PREVIOUS_SHA=previous)
        return subprocess.run(['sh', '-c', COMMAND], cwd=self.path / 'web', env=current,
                              capture_output=True).returncode


class IgnoreCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def assertSkips(self, **kwargs):
        self.assertEqual(self.repo.ignore(**kwargs), 0)

    def assertBuilds(self, **kwargs):
        self.assertNotEqual(self.repo.ignore(**kwargs), 0)

    def test_fits_vercel_length_limit(self):
        self.assertLessEqual(len(COMMAND), 256)

    def test_merge_without_web_change_skips_production(self):
        self.repo.merge([('backend/app.py', 'x'), ('ios/App.swift', 'y')])
        self.assertSkips()

    def test_merge_with_web_change_deploys_production(self):
        self.repo.merge([('backend/app.py', 'x'), ('web/styles.css', 'y')])
        self.assertBuilds()

    def test_web_change_in_earlier_pr_commit_deploys(self):
        self.repo.merge([('web/app.js', 'x'), ('backend/app.py', 'y')])
        self.assertBuilds()

    def test_web_change_since_previous_deployment_deploys(self):
        previous = self.repo.git('rev-parse', 'HEAD')
        self.repo.merge([('web/app.js', 'x')])
        self.repo.merge([('backend/app.py', 'y')])
        self.assertBuilds(previous=previous)

    def test_no_web_change_since_previous_deployment_skips(self):
        self.repo.merge([('web/app.js', 'x')])
        previous = self.repo.git('rev-parse', 'HEAD')
        self.repo.merge([('backend/app.py', 'y')])
        self.repo.merge([('docs/a.md', 'z')])
        self.assertSkips(previous=previous)

    def test_previous_deployment_outside_shallow_clone_falls_back_to_merge_parent(self):
        self.repo.merge([('backend/app.py', 'y')])
        self.assertSkips(previous='0' * 40)
        self.repo.merge([('web/app.js', 'x')])
        self.assertBuilds(previous='0' * 40)

    def test_first_preview_of_a_branch_builds(self):
        self.repo.commit('backend/app.py', 'x')
        self.assertBuilds(env='preview')

    def test_preview_without_web_change_since_its_last_deployment_skips(self):
        previous = self.repo.commit('web/app.js', 'x')
        self.repo.commit('backend/app.py', 'y')
        self.assertSkips(env='preview', previous=previous)

    def test_single_commit_history_builds(self):
        self.assertBuilds()


if __name__ == '__main__':
    unittest.main()
