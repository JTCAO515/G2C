"""Signed PG comparison while the registered city catalogue waits for HTTP."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cj_agent.provider import _M4_REQUEST_SENT, DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL
from cj_api.local_app import load_confirmation_signer
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow


def check_city_dispatch(api, headers, database, auth, subject, scope, memory, root):
    import run_worker

    ready, release = Event(), Event()
    writes, model_calls = [], []
    subjects = frozenset({subject})
    key = 'city-fixture-not-live'
    budget = AuthorizationBudget(root / 'city-wire-budget', clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
    provider = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, key, max_output_tokens=1536), budget)
    services = RealServices(provider, key, subjects, demo_subjects=subjects, national_subjects=subjects)
    tools = RealTools(services, buffered_streaming_subjects=subjects)
    worker = run_worker._worker_for_scope(database, provider, auth, scope, checker_for(auth),
        memory_configuration=memory, tools_configuration=tools, draft_profile='needs-structured.1',
        assembly_planning=True, demo_planning=True, national_planning=True, lio_confirmation=load_confirmation_signer(auth))
    question = '成都有哪些好逛的公园？'
    answer = '成都可先从人民公园开始。'
    body = city_catalog()
    response = (f'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'
                'Connection: close\r\n\r\n').encode() + body

    class WaitingReader(asyncio.StreamReader):
        async def readuntil(self, separator=b'\n'):
            if not ready.is_set():
                ready.set()
                assert await asyncio.to_thread(release.wait, 15)
                self.feed_data(response)
                self.feed_eof()
            return await super().readuntil(separator)

    def record_send(raw):
        method, target, _ = raw.split(b' ', 2)
        assert method == b'GET'
        writes.append(target.split(b'?', 1)[0])

    async def connect(host, port, **options):
        assert (host, port, options['server_hostname']) == ('restapi.amap.com', 443, 'restapi.amap.com')
        writer = SimpleNamespace(write=record_send, drain=AsyncMock(), transport=SimpleNamespace(abort=lambda: None))
        return WaitingReader(), writer

    async def provider_wire(config, raw, guard, observation):
        assert guard() is True
        request = json.loads(raw)
        index = request.get('response_format', {}).get('json_schema', {}).get('schema', {}).get(
            'properties', {}).get('current_source_index', {}).get('const')
        if index is None:
            system = request['messages'][0]['content']
            assert '成都' in system and '510100' in system
            stage, reply = 'answer', answer
        else:
            intake = flow(question, city='成都', days=None, intent='consult', questions=(), index=index)
            intake.update(version='LIO-planning-intake.8', planning_request_index=None, needs_tools=True)
            stage, reply = 'intake', json.dumps(intake, ensure_ascii=False)
        model_calls.append(stage)
        yield _M4_REQUEST_SENT
        observation['http_status'] = 200
        packet = dict(id='city-response-fixture-' + stage, model=M4_MODEL,
            choices=[dict(index=0, delta=dict(content=reply), finish_reason='stop')],
            usage=dict(prompt_tokens=100, completion_tokens=100, total_tokens=200))
        yield ('data: ' + json.dumps(packet, ensure_ascii=False) + '\n\ndata: [DONE]\n\n').encode()

    def send(mid, text, **target):
        page = api.post('/v2/lio/messages', headers=headers,
            content=encode(dict(version='LIO-message.2', message_id=mid, locale='zh', text=text, **target)))
        assert page.status_code == 200, page.status_code
        return page.json()['conversation_id']

    def receipts():
        return [(row['kind'], row['state']) for row in budget.inspect()]

    seed, pending = 'city-wire-seed', 'city-wire-wait'
    cid = send(seed, '你是谁', new_conversation=True)
    assert [item.status for item in worker.process()] == ['completed']
    send(pending, question, conversation_id=cid)

    def timeline():
        return api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=cid))

    with patch('asyncio.open_connection', connect), patch('cj_agent.provider._m4_wire', provider_wire), \
         ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker.process)
        try:
            assert ready.wait(10), future.result(timeout=2)
            assert writes == [b'/v3/config/district']
            assert receipts() == [('model', 'RECEIVED'), ('place', 'INTENT')]
            with ThreadPoolExecutor(max_workers=3) as readers:
                pages = tuple(readers.map(lambda _: timeline(), range(3)))
            statuses = [page.status_code for page in pages]
            for page in pages:
                if page.status_code == 200:
                    first, current = page.json()['messages']
                    assert (first['message_id'], first['status']) == (seed, 'completed')
                    assert (current['message_id'], current['status'], current['answer'], current['trip']) == (
                        pending, 'answering', '', None)
        finally:
            release.set()
        outcome, = future.result(timeout=12)
    assert (outcome.status, outcome.proposal_id) == ('completed', None)
    assert writes == [b'/v3/config/district'] and model_calls == ['intake', 'answer']
    assert receipts() == [('model', 'RECEIVED'), ('place', 'RECEIVED'), ('model', 'RECEIVED')]
    settled = timeline()
    assert settled.status_code == 200
    current = settled.json()['messages'][-1]
    assert (current['message_id'], current['status'], current['answer'], current['trip'], current['memory']) == (
        pending, 'completed', answer, None, None)
    assert statuses == [200, 200, 200], ('city catalogue waiting after one request', statuses)


if __name__ == '__main__':
    import lio_projection_pg as projection
    import lio_dispatch_concurrency_pg as dispatch

    with patch.object(dispatch, 'check_dispatch', check_city_dispatch), patch.object(
        projection.harness, 'exercise', lambda auth, db: projection.exercise(
            auth.parent / 'signed-city-response', db, dispatch_check=True)):
        projection.harness.main()
