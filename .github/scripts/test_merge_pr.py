"""Unit tests for the merge guard (merge_pr.py) and the open-PR overlap rules (pr_overlap.py)."""
import datetime
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge_pr  # noqa: E402
from merge_pr import Blocked, Frozen, check_ci, check_freeze, check_overlap, check_pr, check_review  # noqa: E402
from pr_overlap import overlap, pr_paths, report  # noqa: E402

HEAD = 'a' * 40
OTHER = 'b' * 40


def note(text):
    handle = tempfile.NamedTemporaryFile('w', suffix='.md', delete=False, encoding='utf-8')
    handle.write(text)
    handle.close()
    return handle.name


class FreezeTests(unittest.TestCase):
    def test_open_main(self):
        self.assertTrue(check_freeze(note('# main\n\n**当前：未冻结**（S 部署后解除）\n')).startswith('未冻结'))

    def test_any_other_state_stops(self):
        for state in ('已冻结', '暂停合并（main 编译不过）', '冻结中'):
            with self.assertRaises(Frozen):
                check_freeze(note(f'**当前：{state}**\n'))

    def test_paused_main_admits_only_declared_fixes(self):
        paused = note('**当前：暂停合并（main 编译不过）**\n')
        with self.assertRaises(Frozen):
            check_freeze(paused)
        self.assertTrue(check_freeze(paused, fix_main=True).startswith('暂停合并'))
        with self.assertRaises(Frozen):
            check_freeze(note('**当前：已冻结**\n'), fix_main=True)

    def test_missing_line_or_file_stops(self):
        with self.assertRaises(Frozen):
            check_freeze(note('当前未冻结\n'))
        with self.assertRaises(Frozen):
            check_freeze('/nonexistent/main-freeze.md')

    def test_frozen_exit_code(self):
        self.assertEqual(Frozen.code, 3)
        self.assertEqual(Blocked.code, 2)


def pr(**changes):
    value = {'state': 'open', 'merged': False, 'draft': False, 'base': {'ref': 'main'}, 'head': {'sha': HEAD}}
    value.update(changes)
    return value


class PullRequestTests(unittest.TestCase):
    def test_open_main_pr_at_head(self):
        check_pr(pr(), HEAD)

    def test_stops(self):
        for bad in (pr(state='closed'), pr(draft=True), pr(base={'ref': 'app/feature'}),
                    pr(head={'sha': OTHER})):
            with self.assertRaises(Blocked):
                check_pr(bad, HEAD)


def comment(id_, body, association='OWNER'):
    return {'id': id_, 'body': body, 'author_association': association}


class ReviewTests(unittest.TestCase):
    def test_approval_of_the_exact_head(self):
        check_review([comment(1, f'Review: APPROVE {HEAD}\n\n- checked')], HEAD)

    def test_newest_decision_wins(self):
        with self.assertRaises(Blocked):
            check_review([comment(1, f'Review: APPROVE {HEAD}'),
                          comment(2, f'Review: REQUEST CHANGES {HEAD}\n- bug')], HEAD)
        check_review([comment(1, f'Review: REQUEST CHANGES {HEAD}'), comment(2, f'Review: APPROVE {HEAD}')], HEAD)

    def test_other_heads_strangers_and_loose_text_do_not_count(self):
        for comments in ([comment(1, f'Review: APPROVE {OTHER}')],
                         [comment(1, f'Review: APPROVE {HEAD}', association='NONE')],
                         [comment(1, f'LGTM. Review: APPROVE {HEAD}')],
                         [comment(1, f'Review: APPROVE {HEAD[:8]}')],
                         [comment(1, f'Review: REQUEST_CHANGES {HEAD}')]):
            with self.assertRaises(Blocked):
                check_review(comments, HEAD)


def run(id_, created, status='completed', conclusion='success'):
    return {'id': id_, 'created_at': created, 'status': status, 'conclusion': conclusion}


_ids = iter(range(1, 10**6))


def check(name, conclusion='success', status='completed'):
    return {'id': next(_ids), 'name': name, 'status': status, 'conclusion': conclusion}


GREEN = [check('python'), check('swift', 'skipped'), check('pr-lint'), check('Vercel Preview Comments', 'neutral')]


class CiTests(unittest.TestCase):
    def test_newest_run_is_used(self):
        runs = [run(1, '2026-11-25T06:00:00Z', conclusion='cancelled'), run(2, '2026-11-25T07:00:00Z')]
        self.assertEqual(check_ci(runs, GREEN)['id'], 2)

    def test_stops(self):
        with self.assertRaises(Blocked):
            check_ci([], GREEN)
        with self.assertRaises(Blocked):
            check_ci([run(1, '2026-11-25T06:00:00Z'), run(2, '2026-11-25T07:00:00Z', 'in_progress', None)], GREEN)
        with self.assertRaises(Blocked):
            check_ci([run(1, '2026-11-25T06:00:00Z', conclusion='failure')], GREEN)
        with self.assertRaises(Blocked):
            check_ci([run(1, '2026-11-25T06:00:00Z')], GREEN + [check('pr-lint', None, 'in_progress')])
        with self.assertRaises(Blocked):  # a re-run that failed outranks the earlier success
            check_ci([run(1, '2026-11-25T06:00:00Z')], GREEN + [check('python', 'failure')])
        for conclusion in ('failure', 'cancelled', 'timed_out', 'action_required', 'stale'):
            with self.assertRaises(Blocked):
                check_ci([run(1, '2026-11-25T06:00:00Z')], GREEN + [check('ios-app', conclusion)])


    def test_newest_check_of_a_name_counts(self):
        # pushing then editing the PR body cancels one pr-lint run; the later pr-lint run decides
        cancelled, later = check('pr-lint', 'cancelled'), check('pr-lint')
        self.assertEqual(check_ci([run(1, '2026-11-25T06:00:00Z')], [later, cancelled, check('python')])['id'], 1)
        with self.assertRaises(Blocked):
            check_ci([run(1, '2026-11-25T06:00:00Z')], [check('pr-lint'), check('pr-lint', 'cancelled')])


class OverlapTests(unittest.TestCase):
    def test_same_file(self):
        self.assertEqual(overlap({'a.swift', 'b.swift'}, {'b.swift', 'c.swift'}), ['b.swift'])
        self.assertEqual(overlap({'a.swift'}, {'c.swift'}), [])

    def test_shared_areas_overlap_on_different_files(self):
        self.assertEqual(overlap({'backend/migrations/0101_a.sql'}, {'backend/migrations/0102_b.sql'}),
                         ['backend/migrations/'])
        self.assertEqual(overlap({'contracts/api/A.md'}, {'contracts/api/B.md'}), ['contracts/'])
        self.assertEqual(overlap({'docs/plan/issue-plan.md'}, {'docs/plan/issue-plan.md'}),
                         ['docs/plan/', 'docs/plan/issue-plan.md'])
        self.assertEqual(overlap({'docs/ui.md'}, {'docs/beta/x.md'}), [])

    def test_renames_count_both_paths(self):
        self.assertEqual(pr_paths([{'filename': 'new.swift', 'previous_filename': 'old.swift'},
                                   {'filename': 'x.py'}]), {'new.swift', 'old.swift', 'x.py'})

    def test_guard_stops_on_overlap_and_names_the_fix(self):
        with self.assertRaises(Blocked) as stop:
            check_overlap([{'filename': 'ios/LioRoadbook.swift'}], {'ios/LioRoadbook.swift', 'x.py'},
                          lambda paths: f'  3388ea5c Merge #1604 ({",".join(paths)})')
        self.assertIn('ios/LioRoadbook.swift', str(stop.exception))
        self.assertIn('update-branch', str(stop.exception))
        self.assertIn('Merge #1604 (ios/LioRoadbook.swift)', str(stop.exception))
        check_overlap([{'filename': 'ios/A.swift'}], {'ios/B.swift'})


class ReportTests(unittest.TestCase):
    def test_reports_overlapping_open_prs_only(self):
        files = {1: [{'filename': 'a.swift'}], 2: [{'filename': 'a.swift'}], 3: [{'filename': 'z.py'}],
                 4: [{'filename': 'backend/migrations/9.sql'}]}
        files[1].append({'filename': 'backend/migrations/8.sql'})
        prs = [{'number': n, 'head': {'ref': f'b{n}'}} for n in files]

        def call(path):
            if path.startswith('pulls?state=open'):
                return prs
            return files[int(path.split('/')[1])]
        with mock.patch.dict(os.environ, {'BASE_REF': 'b2'}):
            lines = report(1, call)
        self.assertEqual(lines, ['#2 (stacked) overlaps on a.swift', '#4 overlaps on backend/migrations/'])


def git(cwd, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
               GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid')
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


class MainChangesTests(unittest.TestCase):
    """main_changes_since reads main's first-parent history by commit time, as GitHub merges it."""

    def test_files_changed_on_main_after_the_ci_run_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin, work = os.path.join(tmp, 'origin.git'), os.path.join(tmp, 'work')
            git(tmp, 'init', '--quiet', '--bare', '-b', 'main', origin)
            git(tmp, 'clone', '--quiet', origin, work)
            git(work, 'checkout', '--quiet', '-b', 'main')

            def commit(path, date, message):
                Path(work, path).write_text(message)
                git(work, 'add', path)
                git(work, 'commit', '--quiet', '-m', message, date=date)
            commit('old.swift', '2026-11-25T06:00:00Z', 'before ci')
            # A branch commit authored before the ci run, merged into main after it.
            git(work, 'checkout', '--quiet', '-b', 'side')
            commit('side.swift', '2026-11-25T06:30:00Z', 'side work')
            git(work, 'checkout', '--quiet', 'main')
            commit('main.swift', '2026-11-25T07:10:00Z', 'after ci')
            git(work, 'mv', 'old.swift', 'renamed old.swift')
            git(work, 'commit', '--quiet', '-m', 'rename after ci', date='2026-11-25T07:12:00Z')
            git(work, 'merge', '--quiet', '--no-ff', '-m', 'Merge pull request #9', 'side', date='2026-11-25T07:20:00Z')
            git(work, 'push', '--quiet', 'origin', 'main')
            cwd = os.getcwd()
            os.chdir(work)
            try:
                started = datetime.datetime(2026, 11, 25, 7, 0, tzinfo=datetime.timezone.utc)
                files, log_for = merge_pr.main_changes_since(started)
                side_log, main_log = log_for(['side.swift']), log_for(['main.swift'])
            finally:
                os.chdir(cwd)
        self.assertEqual(files, {'main.swift', 'side.swift', 'old.swift', 'renamed old.swift'})
        self.assertIn('Merge pull request #9', side_log)
        self.assertNotIn('after ci', side_log)
        self.assertIn('after ci', main_log)


class MergeReadBackTests(unittest.TestCase):
    def merge_with(self, reads):
        done = mock.Mock(returncode=1, stderr='base branch policy prohibits the merge', stdout='')
        with mock.patch.object(merge_pr.subprocess, 'run', return_value=done), \
                mock.patch.object(merge_pr.time, 'sleep'), \
                mock.patch.object(merge_pr, 'gh', side_effect=reads):
            return merge_pr.merge(12, HEAD)

    def test_merge_reported_done_but_unmerged_is_unknown(self):
        done = mock.Mock(returncode=0, stderr='', stdout='')
        with mock.patch.object(merge_pr.subprocess, 'run', return_value=done), \
                mock.patch.object(merge_pr.time, 'sleep'), \
                mock.patch.object(merge_pr, 'gh', side_effect=[{'merged': False, 'head': {'sha': HEAD}}] * 5), \
                self.assertRaises(RuntimeError):
            merge_pr.merge(12, HEAD)

    def test_merge_reported_as_error_but_done(self):
        merged = {'merged': True, 'head': {'sha': HEAD}, 'merge_commit_sha': 'c' * 40}
        self.assertEqual(self.merge_with([merged]), 'c' * 40)

    def test_not_merged_is_blocked_and_unreadable_is_unknown(self):
        with self.assertRaises(Blocked):
            self.merge_with([{'merged': False, 'head': {'sha': HEAD}}] * 5)
        with self.assertRaises(RuntimeError):
            self.merge_with([RuntimeError('503')] * 5)


class ArgumentTests(unittest.TestCase):
    def test_full_head_and_freeze_note_required(self):
        with mock.patch.dict(os.environ, {'G2C_FREEZE_NOTE': ''}), self.assertRaises(SystemExit) as stop:
            merge_pr.main(['12', '--head', HEAD])
        self.assertEqual(stop.exception.code, 64)
        with self.assertRaises(SystemExit) as stop:
            merge_pr.main(['12', '--head', HEAD[:8], '--freeze-note', 'x'])
        self.assertEqual(stop.exception.code, 64)

    def test_frozen_main_stops_before_any_github_call(self):
        with mock.patch.object(merge_pr, 'gh', side_effect=AssertionError('no GitHub call when frozen')):
            self.assertEqual(merge_pr.main(['12', '--head', HEAD, '--freeze-note', note('**当前：已冻结**')]), 3)


if __name__ == '__main__':
    unittest.main()
