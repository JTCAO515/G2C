"""Offline provider checks: httpx.MockTransport only, synthetic key, no network."""
import json

import httpx
import pytest

from cj_agent.provider import (DashScopeConfig, DashScopeProvider, FakeProvider, ProviderFailed,
                               ProviderUnknown)

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
