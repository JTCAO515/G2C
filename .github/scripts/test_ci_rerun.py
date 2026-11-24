"""Unit tests for the capacity-miss re-run decision used by ci-rerun.yml."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_rerun import MAX_RERUNS, decide, handle  # noqa: E402

MISS = [{'message': 'The job was not acquired by Runner of type hosted even after multiple attempts'},
        {'message': 'Due to capacity constraints, jobs targeting macOS arm64 runners may experience longer queue times.'}]
CANCELLED_BY_USER = [{'message': 'The operation was canceled.'}]


def job(name, conclusion='success', runner='GitHub Actions 1', steps=3, annotations=()):
    return {'id': name, 'name': name, 'conclusion': conclusion, 'runner_name': runner,
            'steps': [{'n': i} for i in range(steps)], '_annotations': list(annotations)}


def miss(name, conclusion='cancelled'):
    return job(name, conclusion, runner='', steps=0, annotations=MISS)


def run(jobs, attempt=1):
    return decide(jobs, lambda j: j['_annotations'], attempt)


class DecideTests(unittest.TestCase):
    def test_macos_capacity_miss_is_rerun(self):
        rerun, reason = run([job('python'), miss('ios-app'), miss('swift'), job('postgres')])
        self.assertTrue(rerun)
        self.assertIn('ios-app', reason)

    def test_failure_conclusion_with_the_same_annotation_is_rerun(self):
        self.assertTrue(run([miss('ios-app', 'failure')])[0])

    def test_real_test_failure_is_never_rerun(self):
        self.assertFalse(run([job('swift', 'failure')])[0])
        self.assertFalse(run([miss('ios-app'), job('python', 'failure')])[0])

    def test_job_with_steps_or_runner_is_not_a_capacity_miss(self):
        ran = job('ios-app', 'cancelled', runner='', steps=2, annotations=MISS)
        self.assertFalse(run([ran])[0])
        acquired = job('ios-app', 'cancelled', runner='GitHub Actions 9', steps=0, annotations=MISS)
        self.assertFalse(run([acquired])[0])

    def test_cancelled_by_someone_is_not_rerun(self):
        self.assertFalse(run([job('ios-app', 'cancelled', runner='', steps=0, annotations=CANCELLED_BY_USER)])[0])
        self.assertFalse(run([job('ios-app', 'cancelled', runner='', steps=0)])[0])

    def test_postgres_summary_follows_unacquired_shards_only(self):
        self.assertTrue(run([miss('postgres-shard (2)'), job('postgres', 'failure')])[0])
        self.assertFalse(run([job('postgres', 'failure')])[0])
        self.assertFalse(run([miss('postgres-shard (2)'), job('postgres-shard (1)', 'failure'),
                              job('postgres', 'failure')])[0])

    def test_rerun_limit(self):
        jobs = [miss('ios-app')]
        self.assertTrue(run(jobs, attempt=MAX_RERUNS)[0])
        self.assertFalse(run(jobs, attempt=MAX_RERUNS + 1)[0])
        self.assertEqual(MAX_RERUNS, 2)

    def test_annotations_are_read_only_for_jobs_that_never_ran(self):
        asked = []
        def annotations_for(j):
            asked.append(j['name'])
            return j['_annotations']
        decide([job('swift', 'failure'), miss('ios-app')], annotations_for, 1)
        self.assertEqual(asked, ['ios-app'])

    def test_nothing_failed(self):
        self.assertFalse(run([job('python'), job('swift', 'skipped')])[0])


class FakeGitHub:
    """A run whose attempts follow `outcomes`: each is a list of jobs for that attempt."""
    def __init__(self, outcomes, newest=7, event='push', branch='main'):
        self.outcomes, self.newest, self.event, self.branch = outcomes, newest, event, branch
        self.attempt, self.reruns = 1, 0

    def conclusion(self):
        jobs = self.outcomes[self.attempt - 1]
        return 'failure' if any(j['conclusion'] in ('failure', 'cancelled') for j in jobs) else 'success'

    def __call__(self, path, method='GET'):
        if method == 'POST':
            self.reruns += 1
            self.attempt += 1
            return None
        if path.startswith('actions/workflows/'):
            return {'workflow_runs': [{'id': self.newest}]}
        if '/attempts/' in path:
            return {'jobs': self.outcomes[int(path.split('/attempts/')[1].split('/')[0]) - 1]}
        if path.startswith('check-runs/'):
            return MISS
        return {'id': 7, 'event': self.event, 'head_branch': self.branch, 'status': 'completed',
                'run_attempt': self.attempt, 'conclusion': self.conclusion()}


class HandleTests(unittest.TestCase):
    def go(self, github):
        return handle(7, call=github, sleep=lambda _: None)

    def test_reruns_until_green(self):
        github = FakeGitHub([[miss('ios-app')], [job('ios-app')]])
        self.go(github)
        self.assertEqual(github.reruns, 1)

    def test_at_most_two_reruns(self):
        github = FakeGitHub([[miss('ios-app')]] * 4)
        self.go(github)
        self.assertEqual(github.reruns, 2)

    def test_real_failure_after_a_rerun_stops(self):
        github = FakeGitHub([[miss('ios-app')], [job('ios-app', 'failure')], [job('ios-app')]])
        self.go(github)
        self.assertEqual(github.reruns, 1)

    def test_superseded_or_non_main_runs_are_left_alone(self):
        for github in (FakeGitHub([[miss('ios-app')]], newest=8),
                       FakeGitHub([[miss('ios-app')]], event='pull_request'),
                       FakeGitHub([[miss('ios-app')]], branch='feature')):
            with self.subTest(newest=github.newest, event=github.event, branch=github.branch):
                self.go(github)
                self.assertEqual(github.reruns, 0)

    def test_dry_run_never_posts(self):
        github = FakeGitHub([[miss('ios-app')]])
        handle(7, call=github, sleep=lambda _: None, dry_run=True)
        self.assertEqual(github.reruns, 0)


if __name__ == '__main__':
    unittest.main()
