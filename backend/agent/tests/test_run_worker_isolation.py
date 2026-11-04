"""run_once keeps processing other scopes when one scope raises, then still raises."""
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_worker  # noqa: E402
from cj_agent.provider import FakeProvider  # noqa: E402


class Database:
    run_context = object()


class Worker:
    def __init__(self, scope, processed):
        self.scope, self.processed = scope, processed

    def process(self):
        self.processed.append(self.scope)
        if self.scope == 'a':
            raise RuntimeError('original quota period unresolved')
        return ['outcome-' + self.scope]


class Background:
    def __init__(self):
        self.calls = 0

    def run_once(self, model):
        self.calls += 1
        return []


class RunOnceIsolationTests(unittest.TestCase):
    def test_failing_scope_does_not_starve_later_scopes_or_background(self):
        processed, background = [], Background()
        with mock.patch.object(run_worker, 'scopes', return_value=['a', 'b', 'c']), \
                mock.patch.object(run_worker, 'checker_for', return_value=object()), \
                mock.patch.object(run_worker, '_worker_for_scope',
                                  side_effect=lambda database, model, auth, scope, checker, **kwargs: Worker(scope, processed)):
            with self.assertRaisesRegex(RuntimeError, 'original quota period unresolved'):
                run_worker.run_once(Database(), FakeProvider(), '/unused', background_jobs=background)
        self.assertEqual(processed, ['a', 'b', 'c'])
        self.assertEqual(background.calls, 1)

    def test_no_failure_returns_all_outcomes(self):
        processed = []
        with mock.patch.object(run_worker, 'scopes', return_value=['b', 'c']), \
                mock.patch.object(run_worker, 'checker_for', return_value=object()), \
                mock.patch.object(run_worker, '_worker_for_scope',
                                  side_effect=lambda database, model, auth, scope, checker, **kwargs: Worker(scope, processed)):
            self.assertEqual(run_worker.run_once(Database(), FakeProvider(), '/unused'), ['outcome-b', 'outcome-c'])


if __name__ == '__main__':
    unittest.main()
