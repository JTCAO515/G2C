"""W4-6 (#1750): different scopes run at once behind CJ_WORKER_SCOPE_CONCURRENCY; one scope stays sequential."""
from pathlib import Path
import os
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_worker  # noqa: E402
from cj_agent.provider import FakeProvider  # noqa: E402
from cj_api.worker_concurrency import configured_concurrency, effective_concurrency  # noqa: E402


class Database:
    run_context = object()

    def __init__(self, pool_max_size=None):
        self.pool_max_size = pool_max_size


class Tracker:
    def __init__(self, *, barrier=None, fail=(), delay=None):
        self.lock = threading.Lock()
        self.active = self.peak = 0
        self.processed = []
        self.barrier, self.fail, self.delay = barrier, set(fail), delay or {}

    def worker(self, database, model, auth, scope, checker, **kwargs):
        tracker = self

        class Worker:
            def process(self):
                with tracker.lock:
                    tracker.active += 1
                    tracker.peak = max(tracker.peak, tracker.active)
                    tracker.processed.append(scope)
                try:
                    if tracker.barrier is not None:
                        tracker.barrier.wait(timeout=5)
                    time.sleep(tracker.delay.get(scope, 0))
                    if scope in tracker.fail:
                        raise RuntimeError('original quota period unresolved for ' + scope)
                    return ['outcome-' + scope]
                finally:
                    with tracker.lock:
                        tracker.active -= 1
        return Worker()


def run(tracker, scopes, *, switch, pool=None, background=None):
    with mock.patch.dict(os.environ, {'CJ_WORKER_SCOPE_CONCURRENCY': switch}), \
            mock.patch.object(run_worker, 'scopes', return_value=list(scopes)), \
            mock.patch.object(run_worker, 'checker_for', return_value=object()), \
            mock.patch.object(run_worker, '_worker_for_scope', side_effect=tracker.worker):
        return run_worker.run_once(Database(pool), FakeProvider(), '/unused', background_jobs=background)


class ScopeConcurrency(unittest.TestCase):
    def test_default_is_the_old_sequential_loop(self):
        tracker = Tracker()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_WORKER_SCOPE_CONCURRENCY', None)
            self.assertEqual(configured_concurrency(), 1)
        self.assertEqual(run(tracker, ['a', 'b', 'c'], switch='1', pool=16), ['outcome-a', 'outcome-b', 'outcome-c'])
        self.assertEqual((tracker.processed, tracker.peak), (['a', 'b', 'c'], 1))

    def test_two_accounts_run_at_the_same_time_when_the_pool_allows(self):
        # Acceptance: two accounts asking at once do not queue behind each other.
        tracker = Tracker(barrier=threading.Barrier(2))
        self.assertEqual(run(tracker, ['a', 'b'], switch='2', pool=16), ['outcome-a', 'outcome-b'])
        self.assertEqual(tracker.peak, 2)

    def test_a_pool_without_room_for_two_plan_saves_keeps_one_scope_at_a_time(self):
        tracker = Tracker()
        self.assertEqual(run(tracker, ['a', 'b', 'c'], switch='4', pool=8), ['outcome-a', 'outcome-b', 'outcome-c'])
        self.assertEqual(tracker.peak, 1)
        self.assertEqual([effective_concurrency(4, size) for size in (6, 8, 13, 14, 16, 21, 28, 64, None)],
                         [1, 1, 1, 2, 2, 3, 4, 4, 4])

    def test_results_keep_scope_order_and_each_scope_runs_once(self):
        tracker = Tracker(delay={'a': 0.2})
        self.assertEqual(run(tracker, ['a', 'b', 'c'], switch='3', pool=21), ['outcome-a', 'outcome-b', 'outcome-c'])
        self.assertEqual(sorted(tracker.processed), ['a', 'b', 'c'])

    def test_a_failing_scope_still_lets_the_others_run_then_raises(self):
        class Background:
            calls = 0
            def run_once(self, model):
                Background.calls += 1
                return []
        tracker = Tracker(fail={'b'})
        with self.assertRaisesRegex(RuntimeError, 'unresolved for b'):
            run(tracker, ['a', 'b', 'c'], switch='2', pool=16, background=Background())
        self.assertEqual(sorted(tracker.processed), ['a', 'b', 'c'])
        self.assertEqual(Background.calls, 1)

    def test_switch_accepts_only_one_to_four(self):
        for value in ('0', '5', 'two', ''):
            with self.subTest(value=value), mock.patch.dict(os.environ, {'CJ_WORKER_SCOPE_CONCURRENCY': value}), \
                    self.assertRaises(ValueError):
                configured_concurrency()


if __name__ == '__main__':
    unittest.main()
