"""Cancel HTTP boundary with real AUTH/MESSAGE owner classes and synthetic storage."""
from contextlib import contextmanager
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import pytest
import httpx

from fastapi.testclient import TestClient
from cj_api.app import create_app
from cj_api.run_display_composition import RunDisplayWireConfiguration
from cj_api.run_events_routes import RunEventsConfiguration
from cj_auth.interfaces import Fact
from cj_run import display_snapshot
from cj_run.core import Service
from cj_run.fixture import MemoryRepository
from cj_run.postgres import CommitUnknown, Repository
import display_snapshot_checks as source_fixture


@pytest.fixture(autouse=True)
def explicit_local_profile(monkeypatch):
    monkeypatch.setenv('CJ_ENV', 'local')


class ScopedMemory(MemoryRepository):
    def __init__(self, scope):
        super().__init__()
        self.scope = scope
        self.lose_ack = False
        self.after_commit = lambda: None
    @contextmanager
    def transaction(self, *, require_clean_close=False):
        with super().transaction() as tx:
            tx.epoch = 'fixture'
            yield tx
        self.after_commit()
        if self.lose_ack: raise CommitUnknown()
    recover = Repository.recover


def fixture(*, enabled=True):
    owner = source_fixture.SnapshotTests()
    owner.setUp()
    repo = ScopedMemory(owner.binding.scope)
    reader = display_snapshot.DisplaySnapshotReader(owner.boundary, lambda p, s: repo,
        configuration=display_snapshot.DisplaySnapshotConfiguration(1000, 10000))
    app = create_app(_run_display_reader=reader,
        _run_display_configuration=RunDisplayWireConfiguration(256, 1000, 10000),
        _run_display_modules={'cj_run.display_snapshot': display_snapshot},
        _run_events_configuration=RunEventsConfiguration(.01, 1) if enabled else None)
    return owner, repo, app


def cancel(client, mid='mé', **changes):
    return client.post('/v1/run-cancellations', json=dict(version='RUN-cancel.1', message_id=mid, **changes),
                       headers={'Authorization': 'Bearer synthetic'})


def test_original_cancel_replay_and_readback_have_no_private_payload():
    owner, repo, app = fixture()
    with TestClient(app) as client:
        first = cancel(client)
        assert first.status_code == 200, first.text
        body = first.json()
        assert set(body) == {'request_id', 'message_id', 'run_id', 'status', 'event_highwater'}
        assert (body['message_id'], body['run_id'], body['status'], body['event_highwater']) == ('mé', 'original-run', 'cancelled', 1)
        assert body['request_id'] == first.headers['X-Request-ID']
        repeat = cancel(client).json()
        assert {k: v for k, v in repeat.items() if k != 'request_id'} == {k: v for k, v in body.items() if k != 'request_id'}
        read = client.get('/v1/run-display', params={'message_id': 'mé'}, headers={'Authorization': 'Bearer synthetic'})
        assert read.status_code == 200
        assert read.json()['snapshot']['status'] == 'cancelled'
        assert 'PRIVATE_USER_BODY' not in first.text and owner.binding.scope not in first.text
        assert Service(repo).snapshot(owner.binding).sequence == 1


def test_unconfigured_readonly_missing_and_foreign_are_not_cancelled():
    owner, repo, app = fixture(enabled=False)
    with TestClient(app) as client: assert cancel(client).status_code == 503
    assert repo.rows == {}
    owner, repo, app = fixture()
    with TestClient(app) as client:
        missing = cancel(client, 'absent')
        owner.p = replace(owner.p, subject='other')
        foreign = cancel(client)
        assert missing.status_code == foreign.status_code == 503
        assert missing.json()['error'] == foreign.json()['error']
    assert repo.rows == {}


def test_wrong_or_ambiguous_input_never_mutates_run():
    owner, repo, app = fixture()
    headers = {'Authorization': 'Bearer synthetic', 'Content-Type': 'application/json'}
    with TestClient(app) as client:
        for raw in (b'null', b'{}', b'{"version":"RUN-cancel.1","message_id":"m","message_id":"n"}',
                    b'{"version":"wrong","message_id":"m"}',
                    b'{"version":"RUN-cancel.1","message_id":"m","scope":"foreign"}',
                    b'{"version":"RUN-cancel.1","message_id":true}',
                    b'{"version":"RUN-cancel.1","message_id":" "}', b'[' * 1500 + b'0' + b']' * 1500):
            assert client.post('/v1/run-cancellations', content=raw, headers=headers).status_code == 400
        assert client.post('/v1/run-cancellations', content=b'x' * 4097, headers=headers).status_code == 413
        assert client.post('/v1/run-cancellations', json={'version': 'RUN-cancel.1', 'message_id': 'mé'}).status_code == 401
        assert client.post('/v1/run-cancellations?scope=foreign', json={'version': 'RUN-cancel.1', 'message_id': 'mé'}, headers=headers).status_code == 400
    assert repo.rows == {}


def test_configuration_and_stream_bound_do_not_grant_implicit_permission():
    with pytest.raises(ValueError): create_app(_run_events_configuration=True)
    owner, repo, app = fixture()
    seen = []
    async def chunks():
        for n in range(4):
            seen.append(n)
            yield b'x' * 3000
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://synthetic.invalid') as client:
            return await client.post('/v1/run-cancellations', content=chunks(),
                headers={'Authorization': 'Bearer synthetic', 'Content-Type': 'application/json', 'Content-Length': '1'})
    assert asyncio.run(request()).status_code == 413
    assert seen == [0, 1] and repo.rows == {}


def test_frozen_openapi_negative_examples_and_shape():
    schema = json.loads((Path(__file__).resolve().parents[3] / 'contracts/api/openapi.json').read_text())
    operation = schema['paths']['/v1/run-cancellations']['post']
    owner, repo, app = fixture()
    with TestClient(app) as client:
        for example in operation['x-negative-examples']:
            raw = example['raw'].encode() if 'raw' in example else json.dumps(example['value']).encode()
            response = client.post('/v1/run-cancellations', content=raw,
                headers={'Authorization': 'Bearer synthetic', 'Content-Type': 'application/json'})
            assert response.status_code == example['status']
        example = operation['requestBody']['content']['application/json']['examples']['original']['value']
        positive = dict(example, message_id='mé')
        assert client.post('/v1/run-cancellations', json=positive,
                          headers={'Authorization': 'Bearer synthetic'}).status_code == 200


def test_unknown_commit_and_postcommit_revocation_withhold_success():
    for revoke in (False, True):
        owner, repo, app = fixture()
        if revoke: repo.after_commit = lambda: setattr(owner, 'invited', Fact.NO)
        else: repo.lose_ack = True
        with TestClient(app) as client:
            response = cancel(client)
            assert response.status_code == 503
            assert response.json()['error']['outcome'] == 'unknown'
            assert response.json()['error']['recovery'] == 'reconcile_original'
            assert repo.rows[owner.binding.scope, owner.binding.run_id].status == 'cancelled'
            repo.after_commit = lambda: None; repo.lose_ack = False; owner.invited = Fact.YES
            assert cancel(client).json()['event_highwater'] == 1
