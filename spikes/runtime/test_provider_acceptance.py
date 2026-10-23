"""New entry tests only. Every HTTP response here is explicitly a local fixture."""
import asyncio
import json
import logging
import os
import socket
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from agentscope.message import TextBlock, ToolCallBlock
from agentscope.model import ChatResponse
from dbos import DBOS

import provider_acceptance as target

# Any accidental real network access in these tests is a hard failure.
def no_network(*args, **kwargs):
    raise AssertionError('TEST_NETWORK_FORBIDDEN')
socket.socket.connect = no_network
socket.create_connection = no_network

HERE = Path(__file__).resolve().parent
CHECKS = []


def config():
    return {'authorization_ref': 'OFFLINE-TEST-ONLY-NOT-A-HUMAN-GRANT',
        'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        'workspace_id': 'offline-fixture', 'region': 'ap-southeast-1',
        'base_url': 'https://offline-fixture.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1',
        'model_id': 'qwen3.8-flash', 'max_requests': 6, 'max_output_tokens': 256,
        'billing_policy': 'bailian_balance_no_test_spend_ceiling'}


async def transport_checks(root):
    c = config()
    journal = target.Journal(root / 'budget', c)
    requests = []
    async def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'fixture': True})
    def request(url=None, **body):
        return httpx.Request('POST', url or c['base_url'] + '/chat/completions',
            json={'model': c['model_id'], 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}], **body})
    transport = target.GuardedTransport(c, journal, 'en:0', httpx.MockTransport(handler))
    await transport.handle_async_request(request(max_completion_tokens=256))
    wire = json.loads(requests[-1].content)
    assert wire['max_tokens'] == 256 and wire['enable_thinking'] is False
    assert 'max_completion_tokens' not in wire
    try:
        await transport.handle_async_request(request())
        raise AssertionError('implicit retry accepted')
    except target.GateError as exc:
        assert str(exc) == 'NO_IMPLICIT_RETRY'
    duplicate = target.GuardedTransport(c, journal, 'en:0', httpx.MockTransport(handler))
    try:
        await duplicate.handle_async_request(request())
        raise AssertionError('duplicate original intent resent')
    except target.GateError as exc:
        assert str(exc) == 'ORIGINAL_ATTEMPT_EXISTS_READ_ONLY'
    assert len(requests) == 1
    assert journal.inspect()[0]['state'] == 'INTENT'
    CHECKS.append({'case': 'exact-wire-limit-intent-no-retry', 'status': 'PASS', 'fixture_sends': 1})
    for name, bad in [('redirect', request('https://other.invalid/chat/completions')),
                      ('large-input', request(messages=[{'role': 'user', 'content': 'x' * 4097}]))]:
        t = target.GuardedTransport(c, journal, name, httpx.MockTransport(handler))
        try:
            await t.handle_async_request(bad)
            raise AssertionError('invalid request sent')
        except target.GateError:
            pass
    assert len(requests) == 1
    CHECKS.append({'case': 'wrong-host-and-oversized-input-no-send', 'status': 'PASS'})
    for n in range(1, 6):
        journal.reserve(str(n), b'fixture')
        journal.settle(str(n), 'UNKNOWN', {'outcome': 'UNKNOWN'})
    try:
        journal.reserve('seventh', b'fixture')
        raise AssertionError('request limit bypass')
    except target.GateError as exc:
        assert str(exc) == 'ALLOWANCE_EXHAUSTED'
    assert len(journal.inspect()) == 6
    assert all(r['billing_policy'] == 'bailian_balance_no_test_spend_ceiling' for r in journal.inspect())
    CHECKS.append({'case': 'finite-requests-balance-controlled-unknown-attempts-retained', 'status': 'PASS'})
    for field, value in [('authorization_ref', ''), ('expires_at', '2000-01-01T00:00:00Z'),
                         ('max_requests', True), ('base_url', 'http://localhost'),
                         ('model_id', 'other-model'), ('billing_policy', 'unapproved')]:
        bad = config(); bad[field] = value
        try:
            target.checked_config(bad)
            raise AssertionError('bad config accepted: ' + field)
        except target.GateError:
            pass
    CHECKS.append({'case': 'approval-expiry-resource-billing-negative-inputs', 'status': 'PASS'})


async def workflow_checks(root):
    c = config(); journal = target.Journal(root / 'workflow', c)
    target.CONTEXT = (c, journal, 'fixture-new-key-not-a-secret')
    DBOS(config={'name': 'cj002-provider-offline-test', 'application_version': 'test-v1',
                 'system_database_url': 'sqlite:///' + str(root / 'test-dbos.sqlite'),
                 'enable_otlp': False, 'log_level': 'CRITICAL', 'use_listen_notify': False})
    DBOS.launch()
    async def sdk_handler(request):
        if 'timeout' in sdk_mode[0]:
            raise httpx.ReadTimeout('OFFLINE_TIMEOUT', request=request)
        response_id = target.CONTEXT[2] if sdk_mode[0] == 'secret' else 'offline-response'
        chunks = [{'id': response_id, 'object': 'chat.completion.chunk', 'created': 1,
                   'model': c['model_id'], 'choices': [{'index': 0, 'delta': {'content': 'hello'}, 'finish_reason': None}]}]
        data = ''.join('data: ' + json.dumps(x) + '\n\n' for x in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=data, headers={'content-type': 'text/event-stream'})
    sdk_mode = ['success']
    async def fake_step(case, turn, messages, use_tool):
        receipt = {'outcome': 'COMPLETE', 'test_only': True}
        if turn == 0:
            response = ChatResponse(content=[ToolCallBlock(id='test-tool', name='cj002_echo', input='{"value":7}')], is_last=True)
        else:
            response = ChatResponse(content=[TextBlock(text='{"value":7}')], is_last=True)
        return {'receipt': receipt, 'response': response}
    try:
        with patch.object(target.httpx, 'AsyncHTTPTransport', lambda **kwargs: httpx.MockTransport(sdk_handler)):
            payloads = [target.UserMsg(name='fixture', content='hello').model_dump()]
            complete = await target.provider_step('probe', 0, payloads, False)
            assert complete['receipt']['outcome'] == 'COMPLETE'
            duplicate = await target.provider_step('probe', 0, payloads, False)
            assert duplicate['receipt']['outcome'] == 'UNKNOWN'
            assert duplicate['receipt']['actual_cost_usd'] == 'UNKNOWN'
            sdk_mode[0] = 'timeout'
            timeout_result = await target.provider_step('timeout', 0, payloads, False)
            assert timeout_result['receipt']['outcome'] == 'UNKNOWN'
            sdk_mode[0] = 'success'
            cancel_result = await target.provider_step('cancel', 0, payloads, False)
            assert cancel_result['receipt']['reason'] == 'CLIENT_CANCELLED'
            assert cancel_result['receipt']['outcome'] == 'UNKNOWN'
            sdk_mode[0] = 'secret'
            secret_result = await target.provider_step('secret', 0, payloads, False)
            assert secret_result['receipt']['reason'] == 'SECRET_ECHO_REJECTED'
            assert target.CONTEXT[2] not in json.dumps(journal.inspect())
            escaped_key = ''.join('\\u%04x' % ord(c) for c in target.CONTEXT[2])
            assert target.contains_secret({'nested': TextBlock(text='{"echo":"' + escaped_key + '"}')}, target.CONTEXT[2])
        CHECKS.append({'case': 'new-provider-step-sdk-complete-unknown-timeout-cancel-secret-rejection-offline', 'status': 'PASS'})
        with patch.object(target, 'provider_step', fake_step):
            for locale in ('en', 'zh'):
                result = await target.acceptance_workflow(locale)
                assert result['result']['outcome'] == 'PASS'
                assert result['tool_executed'] and result['tool_result']['value'] == 7
        CHECKS.append({'case': 'new-entry-fixed-tool-and-structure-offline', 'status': 'PASS'})
        async def unknown(*args):
            return {'receipt': {'outcome': 'UNKNOWN', 'reason': 'TEST_TIMEOUT'}}
        with patch.object(target, 'provider_step', unknown):
            result = await target.acceptance_workflow('timeout')
            assert result['result']['outcome'] == 'UNKNOWN' and not result['tool_executed']
        CHECKS.append({'case': 'new-entry-unknown-blocks-tool-offline', 'status': 'PASS'})
    finally:
        DBOS.destroy()


async def main():
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix='provider-entry-', dir=HERE / '.runs') as folder:
        root = Path(folder)
        await transport_checks(root)
        await workflow_checks(root)
    record = {'evidence_scope': 'OFFLINE_NEW_ENTRY_ONLY', 'real_provider': 'UNRUN', 'checks': CHECKS,
              'existing_17_plus_3': 'REUSED_WITHOUT_RERUN'}
    (HERE / 'evidence' / 'provider-entry-tests.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    asyncio.run(main())
