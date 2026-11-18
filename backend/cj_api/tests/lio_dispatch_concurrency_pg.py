"""Signed timeline reads while the original provider response is deliberately held."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from threading import Event
from unittest.mock import patch

from cj_agent.provider import (
    _M4_REQUEST_SENT, DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL,
)
from cj_api.local_app import load_confirmation_signer
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
import run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow


def check_dispatch(api, headers, database, auth, subject, scope, memory, root):
    subjects = frozenset({subject})
    signer = load_confirmation_signer(auth)
    for paused, missing_done in (('intake', False), ('discussion', False), ('discussion', True)):
        case = paused + ('-missing-done' if missing_done else '')
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
        )

        def send(mid, text, conversation=None):
            target = dict(new_conversation=True) if conversation is None else dict(conversation_id=conversation)
            body = encode(dict(version='LIO-message.2', message_id=mid, text=text, locale='zh', **target))
            received = api.post('/v2/lio/messages', headers=headers, content=body)
            assert received.status_code == 200, received.text
            return received.json()['conversation_id']

        seed_mid = 'dispatch-' + case + '-previous'
        mid = 'dispatch-' + case + '-pending'
        text = '去成都玩三天'
        conversation = send(seed_mid, '你是谁')
        assert [outcome.status for outcome in worker.process()] == ['completed']
        send(mid, text, conversation)

        async def catalogue(key, guard):
            assert guard() is True
            return city_catalog()

        async def wire(config, raw, guard, observation):
            assert guard() is True
            body = json.loads(raw)
            system = body['messages'][0]['content']
            index = body.get('response_format', {}).get('json_schema', {}).get(
                'schema', {}).get('properties', {}).get('current_source_index', {}).get('const')
            if index is not None:
                stage = 'intake'
                assert index == 1
                value = flow(text, city='成都', days=3, intent='plan', questions=(), index=index)
                value.update(version='LIO-planning-intake.8', needs_tools=False,
                             field_sources=[dict(field='duration_days', source_index=index, quote='三天')])
            else:
                stage = 'discussion'
                assert 'The traveler requested a complete ' in system
                value = dict(answer='第1天逛街区，第2天看博物馆，第3天试当地美食。想先细化哪一天？')
            sent.append(stage)
            yield _M4_REQUEST_SENT
            if stage == paused:
                request_waiting.set()
                assert await asyncio.to_thread(release.wait, 15), 'timeline test never released the response'
            observation['http_status'] = 200
            truncated = missing_done and stage == paused
            content = '{"answer":"第1天' if truncated else json.dumps(value, ensure_ascii=False)
            event = dict(id='dispatch-fixture-' + case + '-' + stage, model=M4_MODEL, choices=[
                dict(index=0, delta=dict(content=content), finish_reason=None if truncated else 'stop'),
            ])
            if not truncated:
                event['usage'] = dict(prompt_tokens=100, completion_tokens=100, total_tokens=200)
            done = '' if truncated else 'data: [DONE]\n\n'
            yield ('data: ' + json.dumps(event) + '\n\n' + done).encode()

        def timeline():
            return api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=conversation))

        with patch('cj_api.lio_city._catalog_exchange', side_effect=catalogue), \
             patch('cj_agent.provider._m4_wire', wire), ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(worker.process)
            try:
                assert request_waiting.wait(10), ('provider request did not reach ' + paused, future.result(timeout=2))
                with ThreadPoolExecutor(max_workers=3) as readers:
                    pages = tuple(readers.map(lambda _: timeline(), range(3)))
                for page in pages:
                    assert page.status_code == 200, (case, page.status_code)
                    original, pending = page.json()['messages']
                    assert (original['message_id'], original['status']) == (seed_mid, 'completed')
                    assert (pending['message_id'], pending['status'], pending['answer'], pending['trip']) == (
                        mid, 'answering', '', None,
                    )
            finally:
                release.set()
            outcome, = future.result(timeout=10)
        assert outcome.status == ('unknown' if missing_done else 'completed')
        assert sent == ['intake', 'discussion'], sent
        page = timeline()
        assert page.status_code == 200
        completed = page.json()['messages'][-1]
        assert completed['trip'] is None
        if missing_done:
            assert (completed['status'], completed['answer']) == ('failed', '')
        else:
            assert '第2天看博物馆' in completed['answer']
        assert [row['state'] for row in budget.inspect()] == [
            'RECEIVED', 'RECEIVED', 'INTENT' if missing_done else 'RECEIVED',
        ]
        print('PASS three signed Lio timeline reads while the original ' + case + ' response waits', flush=True)
