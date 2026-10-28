"""Public worker concurrency behavior; synthetic storage, no process/PG claim."""
from concurrent.futures import ThreadPoolExecutor
import threading

from cj_agent.provider import FakeProvider
from cj_agent.worker import RunWorker
from cj_run.core import Service
from test_worker_cancel import fixture


class PausedProvider:
    def __init__(self, runs, binding):
        self.calls = 0
        self.paused, self.release = threading.Event(), threading.Event()
    def stream(self, messages, system=None):
        self.calls += 1
        yield 'first committed chunk ' * 2
        self.paused.set()
        if not self.release.wait(10): raise AssertionError('test release missing')
        yield ' final chunk'


def test_second_worker_does_not_invalidate_a_still_owned_run():
    first, runs, binding, provider, drafts = fixture(PausedProvider)
    other_provider = FakeProvider()
    second = RunWorker(scope='scope', messages=first.messages,
        runs=Service(runs.repository, lambda _: True), provider=other_provider, drafts=drafts)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(first.process)
        try:
            assert provider.paused.wait(10)
            observed = second.process()
            during = runs.snapshot(binding)
        finally: provider.release.set()
        completed = running.result(timeout=10)
    assert observed[0].status == 'waiting'
    assert during.status == 'running'
    assert completed[0].status == 'completed'
    assert provider.calls == 1 and other_provider.calls == 0
    assert runs.snapshot(binding).text == 'first committed chunk ' * 2 + ' final chunk'
