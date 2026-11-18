"""Offline provider checks with synthetic HTTP responses and no network."""
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import json

import httpx
import pytest

from cj_agent.lio_intake_optional_schema import PROFILE, response_format
from cj_agent.provider import (M4_BASE, M4_MODEL, _M4_REQUEST_SENT, DashScopeConfig, DashScopeProvider,
                               CompleteUnsettledAnswer, FakeProvider, MeteredDashScopeProvider, ProviderFailed, ProviderUnknown)
from cj_usage.authorization_budget import AuthorizationBudget

BASE = 'https://synthetic.invalid/compatible-mode/v1'
KEY = 'sk-synthetic-not-a-real-key'


def config(**changes):
    return DashScopeConfig(**{'base_url': BASE, 'model_id': 'qwen3.8-flash', 'api_key': KEY, **changes})


def sse(*chunks, done=True):
    lines = [f'data: {json.dumps({"choices": [{"delta": {"content": c}}]}, ensure_ascii=False)}' for c in chunks]
    if done:
        lines.append('data: [DONE]')
    return ('\n\n'.join(lines) + '\n\n').encode()


def provider(handler, **changes):
    return DashScopeProvider(config(**changes), transport=httpx.MockTransport(handler))


def test_streams_chinese_and_english_and_sends_expected_request():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=sse('你好，', 'Beijing'))
    assert ''.join(provider(handler).stream([{'role': 'user', 'content': '北京三日游'}])) == '你好，Beijing'
    request = seen[0]
    body = json.loads(request.content)
    assert str(request.url) == BASE + '/chat/completions'
    assert request.headers['authorization'] == 'Bearer ' + KEY
    assert body['model'] == 'qwen3.8-flash' and body['stream'] is True
    assert body['messages'][0]['role'] == 'system' and body['messages'][-1]['content'] == '北京三日游'


def test_http_rejection_is_failed_and_does_not_echo_body():
    def handler(request):
        return httpx.Response(401, content=b'{"error":"invalid key sk-echo"}')
    with pytest.raises(ProviderFailed) as caught:
        list(provider(handler).stream([{'role': 'user', 'content': 'hi'}]))
    assert 'sk-' not in str(caught.value)


def test_missing_done_or_malformed_chunk_is_unknown():
    for content in (sse('partial', done=False), b'data: {not json}\n\n'):
        with pytest.raises(ProviderUnknown):
            list(provider(lambda request, c=content: httpx.Response(200, content=c)).stream(
                [{'role': 'user', 'content': 'hi'}]))


def test_wrongly_shaped_or_duplicate_chunk_is_unknown_not_crash():
    # External model output is a trust boundary: any shape error after send is unknown.
    for chunk in (b'[]', b'"text"', b'{"choices":{}}', b'{"choices":["x"]}', b'{"choices":[{"delta":"x"}]}',
                  b'{"choices":[{"delta":{"content":["x"]}}]}', b'{"choices":[{"delta":{"content":1}}]}',
                  b'{"choices":[],"choices":[]}'):
        content = b'data: ' + chunk + b'\n\ndata: [DONE]\n\n'
        with pytest.raises(ProviderUnknown):
            list(provider(lambda request, c=content: httpx.Response(200, content=c)).stream(
                [{'role': 'user', 'content': 'hi'}]))


def test_usage_only_and_null_content_chunks_are_skipped():
    content = (b'data: {"choices":[{"delta":{"content":null}}]}\n\n'
               b'data: {"choices":[],"usage":{"total_tokens":3}}\n\n' + sse('ok'))
    assert ''.join(provider(lambda request: httpx.Response(200, content=content)).stream(
        [{'role': 'user', 'content': 'hi'}])) == 'ok'


def test_output_bound_is_unknown():
    with pytest.raises(ProviderUnknown):
        list(provider(lambda request: httpx.Response(200, content=sse('x' * 50)), max_output_chars=10).stream(
            [{'role': 'user', 'content': 'hi'}]))


def test_timeout_after_send_is_unknown_and_connect_error_is_failed():
    def timeout(request):
        raise httpx.ReadTimeout('slow', request=request)
    def refused(request):
        raise httpx.ConnectError('refused', request=request)
    with pytest.raises(ProviderUnknown):
        list(provider(timeout).stream([{'role': 'user', 'content': 'hi'}]))
    with pytest.raises(ProviderFailed):
        list(provider(refused).stream([{'role': 'user', 'content': 'hi'}]))


def test_configuration_never_shows_key_and_requires_https():
    assert KEY not in repr(config())
    with pytest.raises(ValueError):
        config(base_url='http://insecure.invalid/v1')
    with pytest.raises(ProviderFailed) as caught:
        DashScopeConfig.from_environment({'CJ_MODEL_ID': 'qwen3.8-flash'})
    assert 'CJ_MODEL_API_KEY' in str(caught.value)


def test_fake_provider_answers_in_the_user_language():
    fake = FakeProvider()
    assert '收到' in ''.join(fake.stream([{'role': 'user', 'content': '你好'}]))
    assert 'Received' in ''.join(fake.stream([{'role': 'user', 'content': 'hello'}]))
    assert fake.calls == 2


@pytest.mark.parametrize('terminated', [True, False])
def test_registered_optional_intake_returns_after_send_before_reading_sse(tmp_path, monkeypatch, terminated):
    budget = AuthorizationBudget(tmp_path, clock=lambda: datetime(2026, 11, 4, tzinfo=timezone.utc))
    provider = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, KEY), budget)
    response_ready = asyncio.Event()
    requests = []
    output = '{"mode":"clarify"}'
    chunk = {'id': 'synthetic-receipt', 'model': M4_MODEL,
             'choices': [{'index': 0, 'delta': {'content': output}, 'finish_reason': 'stop'}],
             'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}}

    async def wire(config, raw, guard, observation):
        assert guard() is True
        assert budget.inspect()[0]['state'] == 'INTENT'
        requests.append(json.loads(raw))
        yield _M4_REQUEST_SENT
        await asyncio.wait_for(response_ready.wait(), timeout=1)
        sse = f'data: {json.dumps(chunk)}\n\n'
        if terminated:
            sse += 'data: [DONE]\n\n'
        yield sse.encode()

    monkeypatch.setattr('cj_agent.provider._m4_wire', wire)
    receipt = {}
    with closing(provider.invoke([{'role': 'user', 'content': 'Synthetic intake'}], 'Extract the trip',
                                 'original-intake', receipt=receipt, guard=lambda: True,
                                 structured_profile=PROFILE, intake_source_index=0)) as reply:
        assert next(reply) == ''
        assert receipt == {}
        assert budget.inspect()[0]['state'] == 'INTENT'
        assert len(requests) == 1
        assert requests[0]['response_format'] == response_format(0)
        response_ready.set()
        if terminated:
            assert list(reply) == [output]
            assert receipt['usage']['total_tokens'] == 5
            assert budget.inspect()[0]['state'] == 'RECEIVED'
        else:
            with pytest.raises(ProviderUnknown):
                next(reply)
            assert receipt == {}
            assert budget.inspect()[0]['state'] == 'INTENT'
    assert len(requests) == 1


@pytest.mark.parametrize(('missing','finish','stream_error','answer_visible'), [
    ('model', 'stop', False, True),
    ('id', 'stop', False, True),
    ('usage', 'stop', False, True),
    ('done', 'stop', False, True),
    ('model', 'length', False, False),
    ('model', 'stop', True, False),
    ('wrong_model', 'stop', False, False),
    ('provider_error', 'stop', False, False),
    ('non_utf8', 'stop', False, False),
    ('original_output_limit', 'stop', False, False),
])
def test_only_complete_discussion_surfaces_with_missing_receipt(
        tmp_path, missing, finish, stream_error, answer_visible):
    budget = AuthorizationBudget(tmp_path, clock=lambda: datetime(2026, 11, 4, tzinfo=timezone.utc))
    answer = ('北京有丰富的历史遗迹和街巷。' * 200)[:2436]
    assert len(answer) == 2436
    value = {'id': 'synthetic-original', 'model': M4_MODEL, 'choices': [
        {'index': 0, 'delta': {'content': json.dumps({'answer': answer}, ensure_ascii=False)},
         'finish_reason': finish}],
        'usage': {'prompt_tokens': 20, 'completion_tokens': 500, 'total_tokens': 520}}
    if missing in value:
        del value[missing]
    elif missing=='wrong_model':
        value['model'] = 'unexpected-model'
    elif missing=='non_utf8':
        del value['model']
        value['choices'][0]['delta']['content'] = r'{"answer":"\ud800"}'
    elif missing=='original_output_limit':
        del value['model']
    lines = 'data: ' + json.dumps(value, ensure_ascii=False) + '\n\n'
    if missing=='provider_error':
        lines += 'data: ' + json.dumps(dict(model=M4_MODEL,id='synthetic-original',error={'message':'fixture error'})) + '\n\n'
    if missing not in ('done','provider_error'):
        lines += 'data: [DONE]\n\n'
    wire_body = lines.encode()

    class Wire(httpx.SyncByteStream):
        def __iter__(self):
            yield wire_body
            if stream_error:
                raise httpx.ReadError('synthetic transport ended mid-stream')

    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, stream=Wire())

    provider = MeteredDashScopeProvider(
        DashScopeConfig(M4_BASE, M4_MODEL, KEY), budget, transport=httpx.MockTransport(respond))
    receipt = {}
    with pytest.raises(ProviderUnknown) as indeterminate:
        list(provider.invoke([{'role': 'user', 'content': '北京有什么可看的？'}],
                             'Return JSON with the requested answer.', 'original-answer',
                             receipt=receipt, guard=lambda: True, release_after_send=True,
                             unsettled_answer_limit=len(answer) if missing=='original_output_limit' else 4000))
    assert len(calls) == 1
    assert receipt == {}
    assert budget.inspect()[0]['state'] == 'INTENT'
    if answer_visible:
        assert indeterminate.value.complete_answer == answer
    else:
        assert not isinstance(indeterminate.value, CompleteUnsettledAnswer)
