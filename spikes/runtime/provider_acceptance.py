"""Bounded real-provider acceptance entry. No fixture execution switch.

The default command is read-only preflight. `run` requires separately approved
non-secret configuration and a dedicated new key injected by the operator.
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import ssl
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path

# Only this short-lived process: discard legacy SDK/cloud routing variables by
# name before importing SDKs. Never inspect their values or modify shell files.
for _legacy_name in tuple(os.environ):
    if _legacy_name.startswith(('DBOS', 'OTEL_', 'OPENAI_', 'DASHSCOPE_')):
        del os.environ[_legacy_name]

import httpx
import certifi
from agentscope.credential import OpenAICredential
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock, UserMsg
from agentscope.model import FinishedReason, OpenAIChatModel
from agentscope.tool import ToolChoice
from dbos import DBOS, SetWorkflowID

HERE = Path(__file__).resolve().parent
PINNED = {'agentscope': '2.0.10', 'dbos': '3.3.0', 'openai': '3.35.1', 'httpx': '0.28.1', 'pydantic': '2.14.1'}
KEY_ENV = 'CJ002_NEW_MODEL_API_KEY'
FIELDS = {'authorization_ref', 'expires_at', 'workspace_id', 'region', 'base_url', 'model_id',
          'max_requests', 'max_output_tokens', 'billing_policy'}
REGIONS = {'ap-southeast-1', 'cn-hongkong', 'cn-beijing'}
TOOL = {'type': 'function', 'function': {'name': 'cj002_echo',
        'description': 'Return the supplied synthetic integer. No travel, network or business write.',
        'parameters': {'type': 'object', 'properties': {'value': {'type': 'integer', 'enum': [7]}},
                       'required': ['value'], 'additionalProperties': False}}}


class GateError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def contains_secret(value, key, depth=0):
    if depth > 6:
        return True  # inspection limit: reject rather than release unknown text
    if hasattr(value, 'model_dump'):
        return contains_secret(value.model_dump(), key, depth)
    if isinstance(value, dict):
        return any(contains_secret(k, key, depth) or contains_secret(v, key, depth) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(v, key, depth) for v in value)
    if isinstance(value, str):
        if len(value) > 1_048_576:
            return True
        # Inspect ordinary JSON escapes even when the surrounding JSON is
        # truncated/malformed. Do not depend on whole-document parsing.
        escape = re.compile(r'\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt])')
        normalized = value
        for _ in range(6):
            if key in normalized:
                return True
            if not escape.search(normalized):
                break
            normalized = escape.sub(lambda m: json.loads('"' + m.group(0) + '"'), normalized)
        if key in normalized or escape.search(normalized):
            return True
        if any(0xD800 <= ord(c) <= 0xDFFF for c in normalized):
            return True  # unpaired/ambiguous surrogate representation
        if depth < 6:
            try:
                decoded = json.loads(value)
            except ValueError:
                return False
            if decoded != value:
                return contains_secret(decoded, key, depth + 1)
    return False


def checked_config(value):
    if set(value) != FIELDS:
        raise GateError('CONFIG_FIELDS')
    if not isinstance(value['authorization_ref'], str) or not value['authorization_ref'].strip():
        raise GateError('NO_AUTHORIZATION_REFERENCE')
    try:
        expiry = datetime.fromisoformat(value['expires_at'].replace('Z', '+00:00'))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError()
    except (AttributeError, TypeError, ValueError):
        raise GateError('AUTHORIZATION_EXPIRED_OR_INVALID') from None
    workspace, region = value['workspace_id'], value['region']
    if not isinstance(workspace, str) or not re.fullmatch('[a-zA-Z0-9-]{1,80}', workspace) or region not in REGIONS:
        raise GateError('RESOURCE_IDENTITY')
    expected = f'https://{workspace}.{region}.maas.aliyuncs.com/compatible-mode/v1'
    if value['base_url'] != expected or value['model_id'] != 'qwen3.8-flash':
        raise GateError('ENDPOINT_OR_MODEL')
    for name, upper in [('max_requests', 6), ('max_output_tokens', 256)]:
        if type(value[name]) is not int or not 1 <= value[name] <= upper:
            raise GateError('LIMITS')
    if value['billing_policy'] != 'bailian_balance_no_test_spend_ceiling':
        raise GateError('BILLING_POLICY')
    return value


class Journal:
    """Dedicated acceptance receipts, not production USAGE or provider billing."""
    def __init__(self, root, config):
        root.mkdir(parents=True, exist_ok=True)
        self.path, self.config = root / 'provider.sqlite', config
        self.config_hash = hashlib.sha256(canonical(config)).hexdigest()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, config_hash TEXT, request_hash TEXT, state TEXT, billing_policy TEXT, result TEXT)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def reserve(self, attempt_id, request_bytes):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT id,config_hash,state,billing_policy FROM attempts').fetchall()
            if any(row[0] == attempt_id for row in rows):
                raise GateError('ORIGINAL_ATTEMPT_EXISTS_READ_ONLY')
            # This journal belongs to exactly one approved resource/budget. A
            # changed config cannot silently reset its allowance.
            if any(row[1] != self.config_hash for row in rows):
                raise GateError('JOURNAL_CONFIG_CHANGED')
            if len(rows) >= self.config['max_requests']:
                raise GateError('ALLOWANCE_EXHAUSTED')
            db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,NULL)',
                       (attempt_id, self.config_hash, hashlib.sha256(request_bytes).hexdigest(), 'INTENT', self.config['billing_policy']))

    def settle(self, attempt_id, state, result):
        with self.connect() as db:
            db.execute('UPDATE attempts SET state=?,result=? WHERE id=?',
                       (state, canonical(result).decode(), attempt_id))

    def inspect(self):
        with self.connect() as db:
            return [dict(zip(('attempt_id', 'request_hash', 'state', 'billing_policy', 'receipt'), row))
                    for row in db.execute('SELECT id,request_hash,state,billing_policy,result FROM attempts')]


class GuardedTransport(httpx.AsyncBaseTransport):
    """One exact approved POST, no redirects/retry; intent committed before send."""
    def __init__(self, config, journal, attempt_id, upstream):
        self.config, self.journal, self.attempt_id, self.upstream = config, journal, attempt_id, upstream
        self.sent = False
        self.response_models = set()

    async def handle_async_request(self, request):
        checked_config(self.config)  # authorization expiry is checked at send time
        if self.sent:
            raise GateError('NO_IMPLICIT_RETRY')
        if request.method != 'POST' or str(request.url) != self.config['base_url'] + '/chat/completions':
            raise GateError('UNAPPROVED_TARGET')
        body = json.loads(request.content)
        # AgentScope 2.0.10 emits max_completion_tokens. Qwen's documented
        # compatible field is max_tokens. Bind the exact adjusted outbound bytes.
        body.pop('max_completion_tokens', None)
        body['max_tokens'] = self.config['max_output_tokens']
        body['enable_thinking'] = False
        if body['model'] != self.config['model_id'] or body.get('stream') is not True:
            raise GateError('REQUEST_MODEL_OR_STREAM')
        if len(canonical(body.get('messages'))) > 4096:
            raise GateError('INPUT_BYTE_LIMIT')
        wire = canonical(body)
        self.journal.reserve(self.attempt_id, wire)
        self.sent = True
        headers = dict(request.headers)
        headers.pop('content-length', None)
        outgoing = httpx.Request('POST', request.url, headers=headers, content=wire, extensions=request.extensions)
        response = await self.upstream.handle_async_request(outgoing)
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=ObservedStream(response.stream, self.response_models),
                              extensions=response.extensions)

    async def aclose(self):
        await self.upstream.aclose()


class ObservedStream(httpx.AsyncByteStream):
    """Observe provider-reported IDs in bounded SSE, without logging raw bytes."""
    def __init__(self, upstream, models):
        self.upstream, self.models = upstream, models

    async def __aiter__(self):
        pending, size = b'', 0
        async for chunk in self.upstream:
            size += len(chunk)
            if size > 1_048_576:
                raise GateError('RESPONSE_BYTE_LIMIT')
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if line.startswith(b'data:') and line[5:].strip() != b'[DONE]':
                    try:
                        model = json.loads(line[5:]).get('model')
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(model, str) and re.fullmatch('[a-zA-Z0-9._:-]{1,128}', model):
                        self.models.add(model)
                    if len(self.models) > 8:
                        raise GateError('RESPONSE_MODEL_ID_LIMIT')
            yield chunk

    async def aclose(self):
        await self.upstream.aclose()


CONTEXT = None  # set only after CLI preflight and an actual external approval


def provider_tls_context():
    # SSLContext itself does not read SSLKEYLOGFILE. Avoid create_default_context,
    # which would create a keylog file before keylog_filename can be cleared.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    if context.keylog_filename is not None or not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise GateError('UNSAFE_TLS_CONTEXT')
    return context


@DBOS.step(retries_allowed=False)
async def provider_step(case, turn, message_payloads, use_tool):
    config, journal, key = CONTEXT
    attempt_id = case + ':' + str(turn)
    transport = GuardedTransport(config, journal, attempt_id,
                                 httpx.AsyncHTTPTransport(verify=provider_tls_context(), retries=0, trust_env=False))
    # Timeout/cancel are explicit distinct planned calls. They can consume a
    # provider charge. Unknown cost remains UNKNOWN; attempts are never resent.
    timeout = 0.001 if case == 'timeout' else 30.0
    chunks = []
    try:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False, timeout=timeout) as client:
            model = OpenAIChatModel(OpenAICredential(api_key=key, base_url=config['base_url']),
                      config['model_id'], max_retries=0,
                      parameters=OpenAIChatModel.Parameters(max_tokens=config['max_output_tokens']),
                      client_kwargs={'http_client': client, 'max_retries': 0, 'timeout': timeout})
            stream = await model([Msg.model_validate(m) for m in message_payloads],
                                 tools=[TOOL] if use_tool else None,
                                 tool_choice=ToolChoice(mode='cj002_echo') if use_tool else None)
            async for chunk in stream:
                if contains_secret(asdict(chunk), key):
                    raise GateError('SECRET_ECHO_REJECTED')
                chunks.append(chunk)
                if case == 'cancel' and not chunk.is_last:
                    raise asyncio.CancelledError()
            if not chunks or not chunks[-1].is_last or chunks[-1].finished_reason != FinishedReason.COMPLETED:
                raise GateError('INCOMPLETE_RESPONSE')
        if any(key in model_id for model_id in transport.response_models):
            raise GateError('SECRET_ECHO_REJECTED')
        receipt = {'outcome': 'COMPLETE', 'requested_model_id': config['model_id'],
                   'provider_reported_model_ids': sorted(transport.response_models),
                   'provider_response_id': chunks[-1].id,
                   'chunk_count': len(chunks),
                   'usage': None if chunks[-1].usage is None else {
                       'input_tokens': chunks[-1].usage.input_tokens,
                       'output_tokens': chunks[-1].usage.output_tokens},
                   'actual_cost_usd': 'UNKNOWN'}
        journal.settle(attempt_id, 'COMPLETE', receipt)
        return {'receipt': receipt, 'response': chunks[-1]}
    except (Exception, asyncio.CancelledError) as exc:
        reason = ('CLIENT_CANCELLED' if isinstance(exc, asyncio.CancelledError) else
                  str(exc) if isinstance(exc, GateError) else type(exc).__name__)
        unresolved_original = reason == 'ORIGINAL_ATTEMPT_EXISTS_READ_ONLY'
        result = {'outcome': 'UNKNOWN' if transport.sent or unresolved_original else 'NOT_SENT', 'reason': reason,
                  'actual_cost_usd': 'UNKNOWN' if transport.sent or unresolved_original else '0'}
        if transport.sent:
            journal.settle(attempt_id, 'UNKNOWN', result)
        return {'receipt': result}


@DBOS.step(retries_allowed=False)
async def echo_step(value):
    if type(value) is not int or value != 7:
        raise GateError('TOOL_INPUT')
    return {'value': value, 'source': 'local-deterministic-tool'}


@DBOS.workflow()
async def acceptance_workflow(case):
    prompt = ('请调用cj002_echo传入整数7，再仅输出JSON：{"value":7}。' if case == 'zh' else
              'Call cj002_echo with integer 7, then output only JSON: {"value":7}.')
    messages = [UserMsg(name='cj002-acceptance', content=prompt, id='acceptance-input', created_at='2026-10-23T00:00:00Z')]
    first = await provider_step(case, 0, [m.model_dump() for m in messages], case in ('en', 'zh'))
    if first['receipt']['outcome'] != 'COMPLETE':
        return {'case': case, 'result': first['receipt'], 'tool_executed': False}
    if case in ('timeout', 'cancel'):
        return {'case': case, 'result': {'outcome': 'FAIL', 'reason': 'REQUEST_COMPLETED_BEFORE_EXPECTED_INTERRUPTION'}, 'tool_executed': False}
    response = first['response']
    calls = [b for b in response.content if isinstance(b, ToolCallBlock)]
    if len(calls) != 1 or calls[0].name != 'cj002_echo':
        return {'case': case, 'result': {'outcome': 'FAIL', 'reason': 'EXPECTED_TOOL_NOT_CALLED'}, 'tool_executed': False}
    try:
        args = json.loads(calls[0].input)
        if set(args) != {'value'}:
            raise GateError('TOOL_INPUT')
        result = await echo_step(args['value'])
    except (ValueError, KeyError, TypeError, GateError):
        return {'case': case, 'result': {'outcome': 'FAIL', 'reason': 'INVALID_TOOL_ARGUMENTS'}, 'tool_executed': False}
    messages.extend([Msg(name='model', role='assistant', content=response.content),
                     Msg(name='tool', role='assistant', content=[ToolResultBlock(id=calls[0].id, name='cj002_echo', output=json.dumps(result), state='success')])])
    second = await provider_step(case, 1, [m.model_dump() for m in messages], False)
    if second['receipt']['outcome'] != 'COMPLETE':
        return {'case': case, 'result': second['receipt'], 'tool_executed': True, 'tool_result': result}
    final = second['response']
    try:
        text = ''.join(b.text for b in final.content if isinstance(b, TextBlock))
        parsed = json.loads(text)
        valid = type(parsed) is dict and set(parsed) == {'value'} and type(parsed['value']) is int and parsed['value'] == 7
    except (ValueError, KeyError, TypeError):
        valid = False
    return {'case': case, 'result': {'outcome': 'PASS' if valid else 'FAIL', 'reason': 'STRUCTURED_OUTPUT_VALID' if valid else 'STRUCTURED_OUTPUT_INVALID'},
            'tool_executed': True, 'tool_result': result, 'model_receipts': [first['receipt'], second['receipt']]}


def preflight(config):
    from importlib.metadata import version
    versions = {p: version(p) for p in PINNED}
    missing = []
    for name in ('workspace_id', 'region', 'base_url', 'model_id'):
        if not config.get(name):
            missing.append('MISSING_' + name.upper())
    try:
        checked_config(config)
    except (GateError, TypeError) as exc:
        missing.append(str(exc) if isinstance(exc, GateError) else 'CONFIG_MISSING')
    if KEY_ENV not in os.environ:
        missing.append('DEDICATED_NEW_KEY_NOT_INJECTED')
    if versions != PINNED:
        missing.append('PINNED_PACKAGE_DRIFT')
    return {'provider': 'UNRUN', 'ready_for_authorized_run': not missing,
            'missing': missing, 'versions': versions, 'key_presence_only': KEY_ENV in os.environ}


async def execute(case, root, config):
    DBOS(config={'name': 'cj002-provider-acceptance', 'application_version': 'cj002-provider-v1',
                 'system_database_url': 'sqlite:///' + str(root / 'dbos.sqlite'),
                 'enable_otlp': False, 'conductor_key': None, 'use_listen_notify': False, 'log_level': 'CRITICAL'})
    DBOS.launch()
    try:
        with SetWorkflowID('provider-' + case):
            handle = await DBOS.start_workflow_async(acceptance_workflow, case)
        return await handle.get_result()
    finally:
        DBOS.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['preflight', 'inspect', 'run'])
    parser.add_argument('--config')
    parser.add_argument('--case', choices=['en', 'zh', 'timeout', 'cancel'])
    args = parser.parse_args()
    try:
        root = HERE / '.runs' / 'provider-acceptance'
        if args.command == 'inspect':
            path = root / 'provider.sqlite'
            if not path.exists():
                print(json.dumps({'provider': 'UNRUN', 'attempts': []})); return
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                rows = db.execute('SELECT id,request_hash,state,billing_policy,result FROM attempts').fetchall()
            print(json.dumps({'provider': 'read-only', 'attempts': [dict(zip(
                ('attempt_id', 'request_hash', 'state', 'billing_policy', 'receipt'), r)) for r in rows]})); return
        if not args.config:
            raise GateError('CONFIG_REQUIRED')
        config = json.loads(Path(args.config).read_text())
        facts = preflight(config)
        if args.command == 'preflight':
            print(json.dumps(facts)); return
        if not facts['ready_for_authorized_run'] and args.command == 'run':
            print(json.dumps(facts)); raise SystemExit(2)
        checked_config(config)
        journal = Journal(root, config)
        if not args.case:
            raise GateError('CASE_REQUIRED')
        global CONTEXT
        # Dedicated explicitly injected new credential only. No old fallback,
        # dotenv, Keychain or key discovery.
        key = os.environ[KEY_ENV]
        if not key.strip():
            raise GateError('EMPTY_DEDICATED_KEY')
        CONTEXT = (config, journal, key)
        logging.disable(logging.CRITICAL)
        result = asyncio.run(execute(args.case, root, config))
        output = {'evidence_scope': 'REAL_PROVIDER_ATTEMPT', 'result': result,
                  'model_id': config['model_id'], 'region': config['region'], 'base_url': config['base_url'],
                  'attempts': journal.inspect()}
        (root / (args.case + '-report.json')).write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(output, ensure_ascii=False))
    except (GateError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({'provider': 'UNRUN_OR_BLOCKED', 'reason_type': type(exc).__name__,
                          'reason': str(exc) if isinstance(exc, GateError) else 'CONFIG_OR_LOCAL_IO_ERROR'}))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
