"""OFFLINE targeted P2 regression. Real packages; synthetic keys/MockTransport."""
import asyncio
import hashlib
import json
import logging
import os
import socket
import ssl
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
from dbos import DBOS
import provider_acceptance as target
from test_provider_acceptance import config

P = Path(__file__).parent
logging.disable(logging.CRITICAL)
def no_network(*args, **kwargs):
    raise AssertionError('OFFLINE_NETWORK_FORBIDDEN')
socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network


async def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='p2-entry-', dir=P) as folder:
        root = Path(folder)
        keylog = root / 'keylog.txt'
        with patch.dict(os.environ, {'SSLKEYLOGFILE': str(keylog)}):
            context = target.provider_tls_context()
            assert context.keylog_filename is None
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            transport = httpx.AsyncHTTPTransport(verify=context, retries=0, trust_env=False)
            assert transport._pool._ssl_context is context
            assert not keylog.exists()
            await transport.aclose()
        checks.append({'case': 'explicit-verifying-context-no-ambient-keylog-file', 'status': 'PASS'})
        c = config(); key = 'fixture-runtime-secret-only-6a8'
        escaped = ''.join('\\u%04x' % ord(ch) for ch in key)
        nested = escaped.replace('\\', '\\\\')
        cases = {'truncated': '{"echo":"' + escaped + '"',
                 'complete': '{"echo":"' + escaped + '"}',
                 'nested-truncated': '{"echo":"' + nested,
                 'mixed': 'prefix-' + key[:8] + ''.join('\\u%04X' % ord(ch) for ch in key[8:])}
        for text in cases.values():
            assert target.contains_secret(text, key)
        for safe in ['hello', '{"value":7}', '{"unfinished":"safe', 'snowman \\u2603', '你好 / hello']:
            assert not target.contains_secret(safe, key)
        assert target.contains_secret('\\' * 256 + 'u0061', key)  # bounded fail closed
        checks.append({'case': 'truncated-complete-nested-mixed-escape-and-safe-controls', 'status': 'PASS'})
        journal = target.Journal(root / 'journal', c); target.CONTEXT = (c, journal, key)
        DBOS(config={'name': 'cj002-p2-targeted', 'application_version': 'p2-test-v1',
                     'system_database_url': 'sqlite:///' + str(root / 'dbos.sqlite'),
                     'enable_otlp': False, 'log_level': 'CRITICAL', 'use_listen_notify': False})
        DBOS.launch()
        current = ['']
        captured_contexts = []
        async def handler(request):
            chunk = {'id': 'offline-response', 'object': 'chat.completion.chunk', 'created': 1,
                'model': c['model_id'], 'choices': [{'index': 0, 'delta': {'content': current[0]}, 'finish_reason': None}]}
            return httpx.Response(200, content='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n',
                                  headers={'content-type': 'text/event-stream'})
        def factory(**kwargs):
            ctx = kwargs['verify']
            assert isinstance(ctx, ssl.SSLContext) and ctx.keylog_filename is None
            assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
            captured_contexts.append(True)
            return httpx.MockTransport(handler)
        try:
            with patch.dict(os.environ, {'SSLKEYLOGFILE': str(keylog)}), patch.object(target.httpx, 'AsyncHTTPTransport', factory):
                for name, text in cases.items():
                    current[0] = text
                    out = await target.provider_step('p2-' + name, 0,
                        [target.UserMsg(name='fixture', content='hello').model_dump()], False)
                    assert out['receipt'] == {'outcome': 'UNKNOWN', 'reason': 'SECRET_ECHO_REJECTED', 'actual_cost_usd': 'UNKNOWN'}
                    assert 'response' not in out
                current[0] = '{"value":7}'
                safe = await target.provider_step('p2-safe', 0,
                    [target.UserMsg(name='fixture', content='hello').model_dump()], False)
                assert safe['receipt']['outcome'] == 'COMPLETE'
                assert not keylog.exists()
            assert len(captured_contexts) == 5
            receipts = json.dumps(journal.inspect())
            assert key not in receipts and escaped not in receipts
            assert all(r['state'] == 'UNKNOWN' for r in journal.inspect()[:4])
        finally:
            DBOS.destroy()
        checks.append({'case': 'actual-provider-step-escape-rejection-safe-output-and-pretransport-tls-control', 'status': 'PASS',
                       'rejected_responses': 4, 'safe_completed': 1, 'verified_context_constructions': 5})
    result = {'scope': 'OFFLINE_P2_REGRESSION_ONLY', 'real_provider': 'UNRUN', 'checks': checks,
              'original_probe_sha256': hashlib.sha256((P/'offline_security_probe.py').read_bytes()).hexdigest(),
              'candidate_source_sha256': hashlib.sha256((P.parent.parent/'provider_acceptance.py').read_bytes()).hexdigest(),
              'prior_17_plus_3_and_7_groups': 'REUSED_NOT_RERUN'}
    (P/'entry-security-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
