"""Five concurrent synthetic accounts on signed private PostgreSQL and FakeProvider."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event
from time import time

from fastapi.testclient import TestClient

from cj_agent.provider import FakeProvider
from cj_api.local_app import ISSUER, LocalDatabase, create_local_app, load_history_configuration, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_message.travel import ABI
from runtime_adapter.contract import encode

import dev_auth
import local_history_pg as harness
import local_run_context
import run_worker


class PausedSupplier(FakeProvider):
    def __init__(self, shared_release):
        super().__init__()
        self.waiting = Event()
        self.release = shared_release

    def stream(self, messages, system=None):
        # The Fake boundary mirrors the real send-only handoff. A regression
        # draining the whole remote stream under the initial fence exposes 503.
        yield ''
        self.waiting.set()
        assert self.release.wait(20), 'private supplier fixture release timed out'
        yield from super().stream(messages, system)


def exercise(auth, conninfo):
    owners = tuple(f'hk-parallel-{index}' for index in range(5))
    dev_auth.init(auth, owners)
    now = int(time())
    meter = auth.parent/'hk-multiuser-meter.json'
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',
        current=dict(meter=dict(unit='provider_call', budget=40, period_start=now-60,
                               period_end=now+3600, max_steps=10, max_tools=4,
                               max_output=60000, max_seconds=180),
                     output_limits=dict(model=12000, tool=4000, memory=12000)), history=[])))
    context = load_run_context(meter)
    for owner in owners:
        local_run_context.provision_budget(conninfo, context, owner)
        dev_auth.activate_travel(conninfo, owner, context, ABI)
    database = LocalDatabase(conninfo, run_context=context, travel_context=True,
                             needs_context=True, trip_context=True)
    app = create_local_app(conninfo_path=None, auth_dir=auth, database=database, run_context=context,
                           history_configuration=load_history_configuration(auth),
                           account_admission=True, demo_dialogue_subjects=frozenset(owners),
                           lio_dialogue_subjects=frozenset(owners))
    headers = {owner: {'Authorization': 'Bearer '+dev_auth.token(auth, owner, 300),
                       'Content-Type': 'application/octet-stream'} for owner in owners}
    release = Event()
    release.set()
    suppliers = {owner: PausedSupplier(release) for owner in owners}
    checker = checker_for(auth)
    workers = {owner: run_worker._worker_for_scope(
        database, suppliers[owner], auth, scope_for(ISSUER, owner), checker, demo_planning=True)
        for owner in owners}

    def send(client, owner, suffix):
        message_id = owner+'-'+suffix
        result = client.post('/v1/lio/messages', headers=headers[owner], content=encode(dict(
            version='LIO-message.1', message_id=message_id, text='Tell me about Beijing parks.', locale='en')))
        assert result.status_code == 200, (suffix, result.status_code)
        assert result.json()['message_id'] == message_id
        return result.json()['conversation_id']

    def read_both(client, owner, conversation):
        timeline = client.get('/v1/lio/timeline', headers=headers[owner])
        history = client.get('/v5/message-history', headers=headers[owner],
                             params={'conversation_id': conversation, 'limit': 10})
        assert (timeline.status_code, history.status_code) == (200, 200), (
            owner, timeline.status_code, history.status_code, history.json().get('error'))
        assert history.json()['version'] == 'MESSAGE-history.5'
        return (timeline.json()['messages'],
                [entry['receipt']['message_id'] for entry in history.json()['messages']])

    def verify_reads(values, owner, status):
        timeline, history = values
        expected_ids = {owner+'-previous', owner+'-parallel'}
        assert {message['message_id'] for message in timeline} == expected_ids
        assert set(history) == expected_ids
        current = next(item for item in timeline if item['message_id']==owner+'-parallel')
        assert current['status'] == status
        if status=='completed':
            assert current['answer'].strip()

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=5) as requests, \
            ThreadPoolExecutor(max_workers=5) as running:
        previous = {owner: send(client, owner, 'previous') for owner in owners}
        for owner in owners:
            assert [result.status for result in workers[owner].process()] == ['completed']
            suppliers[owner].waiting.clear()
        release.clear()
        barrier = Barrier(len(owners), timeout=10)

        def simultaneous_send(owner):
            barrier.wait()
            return send(client, owner, 'parallel')

        worker_futures = []
        try:
            sends = {owner: requests.submit(simultaneous_send, owner) for owner in owners}
            conversations = {owner: sent.result(timeout=15) for owner,sent in sends.items()}
            assert conversations == previous
            worker_futures = [running.submit(workers[owner].process) for owner in owners]
            for supplier in suppliers.values():
                assert supplier.waiting.wait(10), 'original model fixture did not start'
            active_reads = {owner: requests.submit(read_both, client, owner, conversations[owner])
                            for owner in owners}
            for owner, reads in active_reads.items():
                verify_reads(reads.result(timeout=12), owner, 'answering')
        finally:
            release.set()
        for future in worker_futures:
            assert [result.status for result in future.result(timeout=15)] == ['completed']
        final_reads = {owner: requests.submit(read_both, client, owner, conversations[owner])
                       for owner in owners}
        for owner, reads in final_reads.items():
            verify_reads(reads.result(timeout=12), owner, 'completed')
    print('PASS 5 parallel owners: sends, same-owner timeline/history during simulated model wait, original completion')


if __name__ == '__main__':
    harness.exercise = exercise
    harness.main()
