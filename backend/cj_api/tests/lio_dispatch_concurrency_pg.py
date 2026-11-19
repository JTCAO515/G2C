"""Signed timeline reads while the original provider response is deliberately held."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from threading import Event
from unittest.mock import AsyncMock, Mock, patch

from cj_agent import provider as agent_provider
from cj_agent.provider import (
    _M4_REQUEST_SENT, DashScopeConfig, MeteredDashScopeProvider, M4_BASE, M4_MODEL, ProviderUnknown,
)
from cj_api import lio_city
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


async def confirm_model_write(guard, send_under_fence):
    def confirm():
        assert guard() is True

    if send_under_fence is None:
        confirm()
    else:
        await send_under_fence(confirm)


@patch('asyncio.open_connection', new=reject_unmocked_connection)
def check_dispatch(api, headers, database, auth, subject, scope, memory, root):
    check_tool_dispatch(api, headers, database, auth, subject, scope, memory, root)
    subjects = frozenset({subject})
    signer = load_confirmation_signer(auth)
    for paused, missing_done, missing_model in (
        ('intake', False, False), ('discussion', False, False), ('discussion', True, False),
        ('discussion', False, True), ('memory', False, False), ('draft', False, False),
        ('city-connect', False, False), ('city-response', False, False), ('city-deadline', False, False),
        ('memory-connect', False, False),
        ('intake-connect', False, False), ('ordinary-connect', False, False),
        ('discussion-connect', False, False), ('draft-connect', False, False), ('cancel-connect', False, False),
    ):
        case = paused + ('-missing-done' if missing_done else '-missing-model' if missing_model else '')
        model_connect_stage = {
            'intake-connect': 'intake', 'discussion-connect': 'discussion', 'draft-connect': 'draft',
            'memory-connect': 'memory', 'ordinary-connect': 'answer', 'cancel-connect': 'intake',
        }.get(paused)
        memory_case = paused in ('memory', 'memory-connect')
        city_case = paused in ('city-connect', 'city-response', 'city-deadline')
        ordinary_case = paused == 'ordinary-connect'
        draft_case = paused in ('draft', 'draft-connect')
        cancel_case = paused == 'cancel-connect'
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
            lio_memory_enabled=memory_case,
        )

        def send(mid, text, conversation=None):
            target = dict(new_conversation=True) if conversation is None else dict(conversation_id=conversation)
            body = encode(dict(version='LIO-message.2', message_id=mid, text=text, locale='zh', **target))
            received = api.post('/v2/lio/messages', headers=headers, content=body)
            assert received.status_code == 200, received.text
            return received.json()['conversation_id']

        seed_mid = 'dispatch-' + case + '-previous'
        mid = 'dispatch-' + case + '-pending'
        text = ('规划成都三天，2026-12-01出发' if draft_case else
                '第一次来中国应该怎么玩？' if memory_case or ordinary_case else '去成都玩三天')
        ordinary = '可以先从老街和公园开始。你更想逛哪一类？'
        conversation = send(seed_mid, '你是谁')
        assert [outcome.status for outcome in worker.process()] == ['completed']
        send(mid, text, conversation)

        async def catalogue(key, guard, *, send_under_fence):
            assert guard() is True
            return city_catalog()

        writer = Mock(drain=AsyncMock())

        async def pause_city(*phases):
            if paused in phases:
                request_waiting.set()
                assert await asyncio.to_thread(release.wait, 15), 'timeline test never released the city call'

        async def city_connect(host, port, **kwargs):
            assert (host, port, kwargs['server_hostname']) == ('restapi.amap.com', 443, 'restapi.amap.com')
            await pause_city('city-connect', 'city-deadline')
            return object(), writer

        async def city_response(reader, max_bytes):
            writer.write.assert_called_once()
            await pause_city('city-response')
            return 200, city_catalog()

        real_catalog = lio_city.catalog_response

        async def city_crosses_deadline(key, guard, *, send_under_fence):
            loop = asyncio.get_running_loop()
            real_time = loop.time
            time_offset = 0

            async def delayed_write(write):
                def expire_before_write():
                    nonlocal time_offset
                    time_offset = 21
                    try:write()
                    finally:time_offset = 0
                await send_under_fence(expire_before_write)

            with patch.object(loop, 'time', side_effect=lambda: real_time() + time_offset):
                return await real_catalog(key, guard, send_under_fence=delayed_write)

        real_wire = agent_provider._m4_wire
        model_writer = Mock(drain=AsyncMock())
        wire_payload = None

        async def model_connect(host, port, **kwargs):
            assert (host, port, kwargs['server_hostname']) == ('dashscope.aliyuncs.com', 443, 'dashscope.aliyuncs.com')
            request_waiting.set()
            assert await asyncio.to_thread(release.wait, 15), 'timeline test never released the model connection'
            reader = asyncio.StreamReader()
            reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: '+
                             str(len(wire_payload)).encode()+b'\r\n\r\n'+wire_payload)
            reader.feed_eof()
            return reader, model_writer

        async def wire(config, raw, guard, observation, *, send_under_fence=None):
            nonlocal wire_payload
            body = json.loads(raw)
            system = body['messages'][0]['content']
            index = body.get('response_format', {}).get('json_schema', {}).get(
                'schema', {}).get('properties', {}).get('current_source_index', {}).get('const')
            if memory_case or ordinary_case:
                stage = 'memory' if 'MEMORY-EXTRACT@2' in system else 'answer'
                value = dict(version='MEMORY-EXTRACT@2', entries=[]) if stage == 'memory' else ordinary
            elif index is not None:
                stage = 'intake'
                assert index == 1
                value = flow(text, city='成都', days=3, intent='plan', questions=(), index=index)
                value.update(version='LIO-planning-intake.8', needs_tools=False,
                             field_sources=[dict(field='duration_days', source_index=index, quote='三天')])
                if draft_case:
                    value.update(start_date='2026-12-01')
                    value['field_sources'].append(dict(field='start_date', source_index=index, quote='2026-12-01出发'))
            elif draft_case:
                stage = 'draft'
                assert json.loads(body['messages'][-1]['content'])['version'] == 'TRIP-source-input.2'
                value = {}  # The provider receives a complete object; the draft publisher must reject it.
            else:
                stage = 'discussion'
                assert 'The traveler requested a complete ' in system
                value = dict(answer=complete_unsettled_reply if missing_model else
                             '第1天逛街区，第2天看博物馆，第3天试当地美食。想先细化哪一天？')
            sent.append(stage)
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
            payload = ('data: ' + json.dumps(event) + '\n\n' + done).encode()
            if stage == model_connect_stage:
                wire_payload = payload
                async for chunk in real_wire(config, raw, guard, observation, send_under_fence=send_under_fence):
                    yield chunk
                return
            await confirm_model_write(guard, send_under_fence)
            yield _M4_REQUEST_SENT
            if stage == paused:
                request_waiting.set()
                assert await asyncio.to_thread(release.wait, 15), 'timeline test never released the response'
            observation['http_status'] = 200
            yield payload

        def timeline():
            return api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=conversation))

        with ExitStack() as mocks, ThreadPoolExecutor(max_workers=1) as executor:
            if city_case:
                mocks.enter_context(patch('cj_api.lio_city.asyncio.open_connection', side_effect=city_connect))
                mocks.enter_context(patch('cj_api.lio_city._read_response', side_effect=city_response))
            else:
                mocks.enter_context(patch('cj_api.lio_city.catalog_response', side_effect=catalogue))
            if model_connect_stage is not None:
                mocks.enter_context(patch('cj_agent.provider.asyncio.open_connection', side_effect=model_connect))
            if paused == 'city-deadline':
                mocks.enter_context(patch('cj_api.lio_city.catalog_response', side_effect=city_crosses_deadline))
            mocks.enter_context(patch('cj_agent.provider._m4_wire', wire))
            future = executor.submit(worker.process)
            try:
                assert request_waiting.wait(10), ('provider request did not reach ' + paused, future.result(timeout=2))
                if city_case:
                    original_city_ledger = budget.inspect()[-1]
                    assert (original_city_ledger['kind'], original_city_ledger['state']) == ('place', 'INTENT')
                    assert writer.write.call_count == (1 if paused == 'city-response' else 0)
                if model_connect_stage is not None:
                    original_model_fees = budget.inspect()
                    original_model_ledger = original_model_fees[-1]
                    assert (original_model_ledger['kind'], original_model_ledger['state']) == ('model', 'INTENT')
                    model_writer.write.assert_not_called()
                if cancel_case:
                    stopped = api.post('/v2/run-cancellations', headers={**headers, 'Content-Type': 'application/json'},
                        json={'version': 'RUN-cancel.2', 'message_id': mid})
                    assert stopped.status_code == 200 and stopped.json()['status'] == 'cancelled'
                    model_writer.write.assert_not_called()
                else:
                    with ThreadPoolExecutor(max_workers=3) as readers:
                        pages = tuple(readers.map(lambda _: timeline(), range(3)))
                    for page in pages:
                        assert page.status_code == 200, (case, page.status_code)
                        original, pending = page.json()['messages']
                        assert (original['message_id'], original['status']) == (seed_mid, 'completed')
                        assert (pending['message_id'], pending['status'], pending['answer'], pending['trip']) == (
                            mid, 'answering', ordinary if memory_case else '', None,
                        )
            finally:
                release.set()
            outcome, = future.result(timeout=10)
        if paused == 'city-deadline':
            assert (outcome.status, outcome.proposal_id) == ('unknown', None)
            writer.write.assert_not_called()
            writer.transport.abort.assert_called_once()
            assert sent == ['intake']
            model_entry, city_entry = budget.inspect()
            assert (model_entry['state'], city_entry['state']) == ('RECEIVED', 'INTENT')
            assert city_entry == original_city_ledger and city_entry['receipt'] is None
            print('PASS late original city write blocked with original INTENT retained', flush=True)
            continue
        if cancel_case:
            assert (outcome.status, outcome.proposal_id) == ('cancelled', None)
            assert sent == ['intake'] and budget.inspect() == original_model_fees
            model_writer.write.assert_not_called()
            model_writer.transport.abort.assert_called_once()
            page = timeline()
            assert page.status_code == 200
            row = page.json()['messages'][-1]
            assert (row['message_id'], row['answer'], row['trip'], row['memory']) == (mid, '', None, None)
            print('PASS signed owner cancellation during model connection blocks POST and preserves its INTENT', flush=True)
            continue
        assert outcome.status == ('unknown' if missing_done or missing_model else 'completed')
        path = (['answer', 'memory'] if memory_case else ['answer'] if ordinary_case else
                ['intake', 'draft' if draft_case else 'discussion'])
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
        elif draft_case:
            assert completed['status'] == 'completed' and '保存确认' in completed['answer']
        elif memory_case or ordinary_case:
            assert completed['status'] == 'completed' and completed['answer'] == ordinary
        else:
            assert '第2天看博物馆' in completed['answer']
        settled = ['RECEIVED'] * (1 if ordinary_case else 2 if memory_case else 3)
        if missing_done or missing_model:
            settled[-1] = 'INTENT'
        assert [row['state'] for row in budget.inspect()] == settled
        if paused in ('city-connect', 'city-response'):
            writer.write.assert_called_once()
            writer.transport.abort.assert_called_once()
            city_entry, = (row for row in budget.inspect() if row['kind'] == 'place')
            assert city_entry['attempt_id'] == original_city_ledger['attempt_id']
            assert city_entry['input_sha'] == original_city_ledger['input_sha']
        if model_connect_stage is not None:
            model_writer.write.assert_called_once()
            model_writer.transport.abort.assert_called_once()
            original_entry, = (row for row in budget.inspect() if row['attempt_id'] == original_model_ledger['attempt_id'])
            assert original_entry['input_sha'] == original_model_ledger['input_sha']
            assert original_entry['state'] == 'RECEIVED'
        if missing_model:
            async def no_followup_response(config, raw, guard, observation, *, send_under_fence=None):
                await confirm_model_write(guard, send_under_fence)
                yield _M4_REQUEST_SENT
                raise ProviderUnknown('synthetic follow-up provider receipt unavailable')
            with patch('cj_agent.provider._m4_wire', no_followup_response):
                followup_outcome, = worker.process()
            assert followup_outcome.message_id == 'dispatch-unsettled-followup'
            assert followup_outcome.proposal_id is None
        print('PASS three signed Lio timeline reads while the original ' + case + ' response waits', flush=True)


@patch('asyncio.open_connection', new=reject_unmocked_connection)
def check_tool_dispatch(api, headers, database, auth, subject, scope, memory, root):
    """Pause at the registered tool's send boundary, before its first response."""
    from types import SimpleNamespace
    from cj_place.gaode import Response
    from cj_place.https_transport import TransportResult
    from test_m4_real_services import turn_sse

    dates = dict(start_date='2026-11-18', end_date='2026-11-18')
    place_args = dict(keyword='synthetic park', city='北京', page=1, page_size=1)
    for kind, tool_name, arguments, phase in (
        ('place', 'place_search', place_args, 'connection'),
        ('place', 'place_search', place_args, 'response'),
        ('place', 'place_search', place_args, 'cancel-before-send'),
        ('weather', 'weather', dates, 'response'),
        ('fact', 'fact', dates, 'response'),
    ):
        case = kind + '-' + phase
        budget = AuthorizationBudget(root / ('tool-dispatch-' + case),
                                     clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
        provider = MeteredDashScopeProvider(
            DashScopeConfig(M4_BASE, M4_MODEL, 'local-fixture-not-live'), budget,
        )
        tools = RealTools(RealServices(provider, 'local-fixture-not-live', frozenset({subject})))
        worker = run_worker._worker_for_scope(
            database, provider, auth, scope, checker_for(auth), memory_configuration=memory,
            tools_configuration=tools, demo_planning=True,
        )
        started, release = Event(), Event()
        sent = []
        model_turns = []
        seeding = True

        async def pause():
            started.set()
            assert await asyncio.to_thread(release.wait, 20), 'tool fixture was not released'

        async def exchange(tool_kind, guard, send_under_fence):
            assert kind == tool_kind
            if phase != 'response':
                await pause()
            def write():
                assert guard() is True
                sent.append(tool_kind)
            await send_under_fence(write)
            if phase == 'response':
                await pause()

        async def place(config, request, credentials, *, before_send, basic, send_under_fence):
            await exchange('place', before_send, send_under_fence)
            raw = json.dumps(dict(status='1', info='OK', infocode='10000', count='1',
                                  pois=[dict(id='SYNTH_ONLY', name='合成公园', location='116.1,39.1')])).encode()
            response = Response(request.binding_digest, request.origin, request.path, 200, raw,
                                datetime.now(timezone.utc))
            return TransportResult('received', 'fixture', response)

        async def weather(key, guard, *, adcode, send_under_fence):
            assert adcode == '110000'
            await exchange('weather', guard, send_under_fence)
            return json.dumps(dict(status='1', infocode='10000', count='1',
                                   forecasts=[dict(adcode=adcode, casts=[dict(date=dates['start_date'])])])).encode()

        async def fact(transport, target):
            await exchange('fact', transport.before_send, transport.send_under_fence)

            async def body():
                yield (b'<h2>240-Hour Visa-Free Transit Policy</h2>'
                       b'<p>This synthetic fixture contains the 240 hours source wording.</p>')

            async def close():
                return None

            return SimpleNamespace(status=200, content_encoding='identity', body=body(), close=close)

        async def dns(*args, **kwargs):
            return [(2, 1, 6, '', ('93.184.216.34', 443))]

        async def model_wire(config, raw, guard, observation, *, send_under_fence=None):
            await confirm_model_write(guard, send_under_fence)
            body = json.loads(raw)
            has_result = seeding or body['messages'][-1]['role'] == 'tool'
            if not seeding:
                model_turns.append(has_result)
            turn = (dict(version='MODEL-tool-turn.1', kind='tool', answer=None,
                         calls=[dict(name=tool_name, arguments=arguments)]) if not has_result else
                    dict(version='MODEL-tool-turn.1', kind='answer',
                         answer=dict(zh='这是合成资料的答复。', en='The synthetic result is ready.'), calls=[]))
            yield _M4_REQUEST_SENT
            observation['http_status'] = 200
            response = turn_sse(turn=turn, compact=True)
            yield response.replace('chatcmpl-synthetic', f'fixture-{case}-{len(model_turns)}').encode()

        def send(mid, text, conversation=None):
            target = dict(new_conversation=True) if conversation is None else dict(conversation_id=conversation)
            body = encode(dict(version='LIO-message.2', message_id=mid, text=text, locale='zh', **target))
            response = api.post('/v2/lio/messages', headers=headers, content=body)
            assert response.status_code == 200, response.status_code
            return response.json()['conversation_id']

        earlier = 'tool-' + case + '-previous'
        current = 'tool-' + case + '-current'
        conversation = send(earlier, '你是谁')
        with patch('cj_agent.provider._m4_wire', model_wire):
            assert [row.status for row in worker.process()] == ['completed']
        seed_ledger = budget.inspect()
        seeding = False
        send(current, '请查一下这条资料', conversation)

        with (patch('cj_agent.provider._m4_wire', model_wire),
              patch('cj_api.real_services.fetch_candidate', place),
              patch('cj_fact.live_source._weather_exchange', weather),
              patch('cj_fact.live_source.PinnedHTTPSTransport.__call__', fact),
              patch('asyncio.BaseEventLoop.getaddrinfo', dns),
              ThreadPoolExecutor(max_workers=1) as executor):
            future = executor.submit(worker.process)
            try:
                assert started.wait(10), (kind, future.result(timeout=2))
                entries = budget.inspect()
                assert entries[:len(seed_ledger)] == seed_ledger
                before = entries[len(seed_ledger):]
                assert [(row['kind'], row['state']) for row in before] == [
                    ('model', 'RECEIVED'), (kind, 'INTENT'),
                ]
                assert before[1]['receipt'] is None
                timeline = api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=conversation))
                assert timeline.status_code == 200, (kind, timeline.status_code)
                prior, pending = timeline.json()['messages']
                assert (prior['message_id'], prior['status']) == (earlier, 'completed')
                assert (pending['message_id'], pending['status']) == (current, 'answering')
                assert budget.inspect() == [*seed_ledger, *before]
                assert sent == ([kind] if phase == 'response' else [])
                if phase == 'cancel-before-send':
                    cancelled = api.post('/v2/run-cancellations',
                        json=dict(version='RUN-cancel.2', message_id=current),
                        headers={**headers,'Content-Type':'application/json'})
                    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled', (
                        cancelled.status_code, cancelled.json().get('error', {}).get('code'))
            finally:
                release.set()
            outcome, = future.result(timeout=10)

        if phase == 'cancel-before-send':
            assert (outcome.message_id, outcome.status, outcome.proposal_id) == (current, 'cancelled', None)
            assert not sent and model_turns == [False]
            assert budget.inspect() == [*seed_ledger, *before]
            print('PASS signed cancellation during connection withheld the original tool write and retained INTENT', flush=True)
            continue
        assert (outcome.message_id, outcome.status, outcome.proposal_id) == (current, 'completed', None)
        entries = budget.inspect()
        assert entries[:len(seed_ledger)] == seed_ledger
        after = entries[len(seed_ledger):]
        assert [(row['kind'], row['state']) for row in after] == [
            ('model', 'RECEIVED'), (kind, 'RECEIVED'), ('model', 'RECEIVED'),
        ]
        assert after[0] == before[0]
        for field in ('attempt_id', 'input_sha'):
            assert after[1][field] == before[1][field]
        assert after[1]['receipt'] is not None
        assert sent == [kind] and model_turns == [False, True]
        result_page = api.get('/v2/lio/timeline', headers=headers, params=dict(conversation_id=conversation))
        assert result_page.status_code == 200
        final = result_page.json()['messages'][-1]
        assert (final['message_id'], final['status'], final['trip']) == (current, 'completed', None)
        assert final['answer'].strip()
        print(f'PASS signed timeline 200 during original {kind} {phase} wait, one original settled tool', flush=True)
