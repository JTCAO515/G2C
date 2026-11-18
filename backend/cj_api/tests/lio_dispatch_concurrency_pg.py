"""Signed timeline reads while the original provider response is deliberately held."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cj_agent.provider import (
    _M4_REQUEST_SENT, DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, ProviderUnknown,
)
from cj_api.local_app import load_confirmation_signer
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
import run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow


async def reject_unmocked_connection(*args, **kwargs):
    raise AssertionError('signed PG fixture attempted a real external connection')


@patch('asyncio.open_connection', new=reject_unmocked_connection)
def check_dispatch(api, headers, database, auth, subject, scope, memory, root, *, before_send=False):
    subjects = frozenset({subject})
    signer = load_confirmation_signer(auth)
    cases = [('intake', False, False), ('discussion', False, False),
             ('memory', False, False), ('draft', False, False)]
    if not before_send:
        cases[2:2] = [('discussion', True, False), ('discussion', False, True)]
    timeline_statuses = {}
    for paused, missing_done, missing_model in cases:
        case = paused + ('-missing-done' if missing_done else '-missing-model' if missing_model else '')
        complete_unsettled_reply = ('北京有丰富的历史遗迹和街巷。' * 200)[:2436]
        sent = []
        request_waiting, release = Event(), Event()
        budget = AuthorizationBudget(root / ('dispatch-' + case),
                                     clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
        provider = MeteredDashScopeProvider(
            DashScopeConfig(M4_BASE, M4_MODEL, 'local-fixture-not-live', max_output_tokens=1536), budget,
        )
        services = RealServices(provider, 'local-fixture-not-live', subjects,
                                demo_subjects=subjects, national_subjects=subjects)
        tools = RealTools(services, buffered_streaming_subjects=subjects)
        worker = run_worker._worker_for_scope(
            database, provider, auth, scope, checker_for(auth),
            memory_configuration=memory, tools_configuration=tools, draft_profile='needs-structured.1',
            assembly_planning=True, demo_planning=True, national_planning=True, lio_confirmation=signer,
            lio_memory_enabled=paused == 'memory',
        )

        def send(mid, text, conversation=None):
            target = dict(new_conversation=True) if conversation is None else dict(conversation_id=conversation)
            body = encode(dict(version='LIO-message.2', message_id=mid, text=text, locale='zh', **target))
            received = api.post('/v2/lio/messages', headers=headers, content=body)
            assert received.status_code == 200, received.text
            return received.json()['conversation_id']

        seed_mid = 'dispatch-' + case + '-previous'
        mid = 'dispatch-' + case + '-pending'
        text = {'draft': '规划成都三天，2026-12-01出发',
                'memory': '第一次来中国应该怎么玩？'}.get(paused, '去成都玩三天')
        ordinary = '可以先从老街和公园开始。你更想逛哪一类？'
        conversation = send(seed_mid, '你是谁')
        assert [outcome.status for outcome in worker.process()] == ['completed']
        send(mid, text, conversation)

        async def catalogue(key, guard):
            assert guard() is True
            return city_catalog()

        def fixture_response(raw):
            body = json.loads(raw)
            system = body['messages'][0]['content']
            index = body.get('response_format', {}).get('json_schema', {}).get(
                'schema', {}).get('properties', {}).get('current_source_index', {}).get('const')
            if paused == 'memory':
                stage = 'memory' if 'MEMORY-EXTRACT@2' in system else 'answer'
                value = dict(version='MEMORY-EXTRACT@2', entries=[]) if stage == 'memory' else ordinary
            elif index is not None:
                stage = 'intake'
                assert index == 1
                value = flow(text, city='成都', days=3, intent='plan', questions=(), index=index)
                value.update(version='LIO-planning-intake.8', needs_tools=False,
                             field_sources=[dict(field='duration_days', source_index=index, quote='三天')])
                if paused == 'draft':
                    value.update(start_date='2026-12-01')
                    value['field_sources'].append(dict(field='start_date', source_index=index, quote='2026-12-01出发'))
            elif paused == 'draft':
                stage = 'draft'
                assert json.loads(body['messages'][-1]['content'])['version'] == 'TRIP-source-input.2'
                value = {}  # The provider receives a complete object; the draft publisher must reject it.
            else:
                stage = 'discussion'
                assert 'The traveler requested a complete ' in system
                value = dict(answer=complete_unsettled_reply if missing_model else
                             '第1天逛街区，第2天看博物馆，第3天试当地美食。想先细化哪一天？')
            truncated = missing_done and stage == paused
            content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            if truncated:
                content = '{"answer":"第1天'
            event = dict(id='dispatch-fixture-' + case + '-' + stage, model=M4_MODEL, choices=[
                dict(index=0, delta=dict(content=content), finish_reason=None if truncated else 'stop'),
            ])
            if missing_model and stage == paused:
                del event['model']
            if not truncated:
                event['usage'] = dict(prompt_tokens=100, completion_tokens=100, total_tokens=200)
            done = '' if truncated else 'data: [DONE]\n\n'
            return stage, ('data: ' + json.dumps(event) + '\n\n' + done).encode()

        async def wait_for_timeline():
            request_waiting.set()
            assert await asyncio.to_thread(release.wait, 15), 'timeline test never released the wire'

        async def wire(config, raw, guard, observation):
            assert guard() is True
            stage, payload = fixture_response(raw)
            sent.append(stage)
            yield _M4_REQUEST_SENT
            if stage == paused:
                await wait_for_timeline()
            observation['http_status'] = 200
            yield payload

        expected_before_connection = 0 if paused == 'intake' else 1

        async def connect(host, port, *, server_hostname, **options):
            assert (host, port, server_hostname) == ('dashscope.aliyuncs.com', 443, 'dashscope.aliyuncs.com')
            if len(sent) == expected_before_connection:
                await wait_for_timeline()
            reader = asyncio.StreamReader()

            def post(raw):
                headers, _, body = raw.partition(b'\r\n\r\n')
                assert headers.startswith(b'POST /compatible-mode/v1/chat/completions ')
                stage, payload = fixture_response(body)
                sent.append(stage)
                response = (f'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                            f'Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode()
                reader.feed_data(response + payload)
                reader.feed_eof()

            return reader, SimpleNamespace(write=post, drain=AsyncMock(), transport=SimpleNamespace(abort=lambda: None))

        def timeline():
            return api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=conversation))

        model_transport = (patch('asyncio.open_connection', new=connect) if before_send else
                           patch('cj_agent.provider._m4_wire', new=wire))
        with patch('cj_api.lio_city._catalog_exchange', side_effect=catalogue), \
             model_transport, ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(worker.process)
            try:
                assert request_waiting.wait(10), ('provider request did not reach ' + paused, future.result(timeout=2))
                if before_send:
                    assert len(sent) == expected_before_connection, 'POST occurred during the connection pause'
                with ThreadPoolExecutor(max_workers=3) as readers:
                    pages = tuple(readers.map(lambda _: timeline(), range(3)))
                timeline_statuses[case] = tuple(page.status_code for page in pages)
                for page in pages:
                    if page.status_code != 200:
                        continue
                    original, pending = page.json()['messages']
                    assert (original['message_id'], original['status']) == (seed_mid, 'completed')
                    assert (pending['message_id'], pending['status'], pending['answer'], pending['trip']) == (
                        mid, 'answering', ordinary if paused == 'memory' else '', None,
                    )
            finally:
                release.set()
            outcome, = future.result(timeout=10)
        assert outcome.status == ('unknown' if missing_done or missing_model else 'completed')
        path = {'memory': ['answer', 'memory'], 'draft': ['intake', 'draft']}.get(paused, ['intake', 'discussion'])
        assert sent == path, sent
        page = timeline()
        assert page.status_code == 200
        completed = page.json()['messages'][-1]
        assert completed['trip'] is None
        if missing_done:
            assert (completed['status'], completed['answer']) == ('failed', '')
        elif missing_model:
            assert completed['status'] == 'completed' and completed['answer'] == complete_unsettled_reply
            assert len(completed['answer']) == 2436 and completed['memory'] is None
            from cj_api.local_lio_national import CONTEXT
            from cj_api.local_lio_planning import PlanningTurn
            prior_binding = worker._binding(worker.messages.query(mid).receipt)
            original_effects = worker.runs.snapshot(prior_binding).effects
            previews = [json.loads(effect.removeprefix(CONTEXT)) for effect in original_effects
                        if effect.startswith(CONTEXT)]
            assert any(row['status'] == 'plan_preview' and row['authority'] != 'none' for row in previews)
            followup = '保存这个行程'
            send('dispatch-unsettled-followup', followup, conversation)
            original = worker.messages.query('dispatch-unsettled-followup')
            followup_binding = worker._binding(original.receipt)
            followup_original = worker.lio_original(followup_binding)
            _, _, prior = worker.lio_planning.legacy.context(
                followup_binding, PlanningTurn(followup, followup_original.question_day)
            )
            assert prior is None or prior['authority'] == 'none', prior
            assert prior is None or prior['status'] != 'plan_preview', prior
        elif paused == 'draft':
            assert completed['status'] == 'completed' and '保存确认' in completed['answer']
        elif paused == 'memory':
            assert completed['status'] == 'completed' and completed['answer'] == ordinary
        else:
            assert '第2天看博物馆' in completed['answer']
        settled = ['RECEIVED'] * (2 if paused == 'memory' else 3)
        if missing_done or missing_model:
            settled[-1] = 'INTENT'
        assert [row['state'] for row in budget.inspect()] == settled
        if missing_model:
            async def no_followup_response(config, raw, guard, observation):
                assert guard() is True
                yield _M4_REQUEST_SENT
                raise ProviderUnknown('synthetic follow-up provider receipt unavailable')
            with patch('cj_agent.provider._m4_wire', no_followup_response):
                followup_outcome, = worker.process()
            assert followup_outcome.message_id == 'dispatch-unsettled-followup'
            assert followup_outcome.proposal_id is None
        phase = 'during connection' if before_send else 'while waiting for a response'
        print('Signed Lio timeline ' + case + ' ' + phase + ': ' + str(timeline_statuses[case]), flush=True)
    assert all(codes == (200, 200, 200) for codes in timeline_statuses.values()), timeline_statuses
