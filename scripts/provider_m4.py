"""M1#1 bounded synthetic Qwen/AgentScope acceptance. Never production dispatch.

Run with spikes/runtime's locked environment. INTENT is durable before the sole
HTTP send; an existing attempt is read-only, including after process death.
No keys, request bodies or model text are persisted or printed.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import time

import certifi
import httpx
from agentscope.credential import OpenAICredential
from agentscope.message import Msg, UserMsg, TextBlock, ToolCallBlock, ToolResultBlock
from agentscope.model import OpenAIChatModel, FinishedReason
from agentscope.tool import ToolChoice

TARGETS = {
    'beijing': ('cn-beijing', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'g2c-dashscope'),
    'singapore': ('ap-southeast-1', 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1', 'g2c-dashscope-intl'),
}
MODEL = 'qwen3.8-flash'
class ClientCancelled(Exception):
    """Cancellation already delivered into and acknowledged by the SDK stream."""
TOOL = {'type': 'function', 'function': {'name': 'synthetic_echo', 'description': 'Echo synthetic integer 7 locally; no network or business write.',
        'parameters': {'type': 'object', 'properties': {'value': {'type': 'integer', 'enum': [7]}},
                       'required': ['value'], 'additionalProperties': False}}}


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


class Journal:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / 'attempts.sqlite'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempt(id TEXT PRIMARY KEY, request_sha TEXT, state TEXT, receipt TEXT)')
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def reserve(self, attempt, wire):
        if datetime.now(timezone.utc).date().isoformat() > '2026-11-30':
            raise ValueError('authorization_expired')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM attempt WHERE id=?', (attempt,)).fetchone():
                raise ValueError('original_attempt_read_only')
            # A deliberately conservative ¥1 hold per <=4096-byte/256-output
            # request; unknown requests retain their hold. Never reset this log.
            if db.execute('SELECT count(*) FROM attempt').fetchone()[0] >= 64:
                raise ValueError('bounded_acceptance_allowance_exhausted')
            db.execute('INSERT INTO attempt VALUES(?,?,?,NULL)', (attempt, hashlib.sha256(wire).hexdigest(), 'INTENT'))

    def finish(self, attempt, state, receipt):
        with self.connect() as db:
            db.execute('UPDATE attempt SET state=?,receipt=? WHERE id=?', (state, canonical(receipt).decode(), attempt))

    def inspect(self):
        with self.connect() as db:
            return [dict(attempt_id=row[0], state=row[1], receipt=None if row[2] is None else json.loads(row[2]))
                    for row in db.execute('SELECT id,state,receipt FROM attempt ORDER BY rowid')]


class Transport(httpx.AsyncBaseTransport):
    def __init__(self, journal, attempt, base, case):
        self.journal, self.attempt, self.base, self.case = journal, attempt, base, case
        self.sent = False
        self.models = set()
        self.status = None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        self.upstream = httpx.AsyncHTTPTransport(verify=context, retries=0, trust_env=False)

    async def handle_async_request(self, request):
        if self.sent or request.method != 'POST' or str(request.url) != self.base + '/chat/completions':
            raise ValueError('unapproved_outflow_or_retry')
        body = json.loads(request.content)
        body.pop('max_completion_tokens', None)
        body.update(max_tokens=256, enable_thinking=False, stream_options={'include_usage': True})
        if self.attempt.endswith(':1'):
            body['response_format'] = {'type':'json_object'}
        if body.get('model') != MODEL or body.get('stream') is not True or len(canonical(body['messages'])) > 4096:
            raise ValueError('request_outside_authorization')
        wire = canonical(body)
        self.journal.reserve(self.attempt, wire)
        if self.case == 'kill-before-send':
            os._exit(75)
        self.sent = True
        headers = dict(request.headers)
        headers.pop('content-length', None)
        response = await self.upstream.handle_async_request(httpx.Request('POST', request.url, headers=headers,
                                                        content=wire, extensions=request.extensions))
        self.status = response.status_code
        if self.case == 'kill-after-send':
            os._exit(75)
        return httpx.Response(response.status_code, headers=response.headers,
                              stream=ObservedStream(response.stream, self.models), extensions=response.extensions)

    async def aclose(self):
        await self.upstream.aclose()


class ObservedStream(httpx.AsyncByteStream):
    def __init__(self, upstream, models):
        self.upstream, self.models = upstream, models

    async def __aiter__(self):
        pending, size = b'', 0
        async for chunk in self.upstream:
            size += len(chunk)
            if size > 1_048_576:
                raise ValueError('provider_stream_exceeded_bound')
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n',1)
                if line.startswith(b'data:') and line[5:].strip() != b'[DONE]':
                    value = json.loads(line[5:])
                    if type(value.get('model')) is str:
                        self.models.add(value['model'])
            yield chunk

    async def aclose(self):
        await self.upstream.aclose()


async def request(journal, region, case, turn, messages, key, *, tool=False):
    locality, base, _ = TARGETS[region]
    attempt = region + ':' + case + ':' + str(turn)
    transport = Transport(journal, attempt, base, case)
    timeout = httpx.Timeout(30, read=0.001 if case == 'timeout' else 30)
    chunks, first, started = [], None, time.monotonic()
    receipt = dict(attempt_id=attempt, requested_model_id=MODEL, endpoint_region=locality, endpoint=base,
                   actual_cost_cny='UNKNOWN', usage='UNKNOWN')
    try:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False, timeout=timeout) as client:
            model = OpenAIChatModel(OpenAICredential(api_key=key, base_url=base), MODEL, max_retries=0,
                parameters=OpenAIChatModel.Parameters(max_tokens=256),
                client_kwargs={'http_client': client, 'max_retries': 0, 'timeout': timeout})
            stream = await model(messages, tools=[TOOL] if tool else None,
                                 tool_choice=ToolChoice(mode='synthetic_echo') if tool else None)
            async for chunk in stream:
                # ChatResponse is a dataclass, but nested AgentScope Blocks are
                # typed objects; asdict is not a JSON wire codec for this SDK.
                if key in str(chunk):
                    raise ValueError('secret_echo_rejected')
                chunks.append(chunk)
                if first is None:
                    first = time.monotonic() - started
                if case == 'cancel' and not chunk.is_last:
                    interrupted = await stream.athrow(asyncio.CancelledError())
                    if interrupted.finished_reason != FinishedReason.INTERRUPTED:
                        raise ValueError('sdk_did_not_acknowledge_cancellation')
                    await stream.aclose()
                    raise ClientCancelled()
            if not chunks or not chunks[-1].is_last or chunks[-1].finished_reason != FinishedReason.COMPLETED:
                raise ValueError('incomplete_response')
        final = chunks[-1]
        receipt.update(outcome='COMPLETE', chunk_count=len(chunks), first_chunk_seconds=first,
                       elapsed_seconds=time.monotonic()-started, response_id=final.id,
                       provider_reported_model_ids=sorted(transport.models), http_status=transport.status,
                       usage='UNKNOWN' if final.usage is None else dict(input_tokens=final.usage.input_tokens,
                                                                      output_tokens=final.usage.output_tokens))
        if key in canonical(receipt).decode():
            raise ValueError('secret_echo_rejected')
        journal.finish(attempt, 'COMPLETE', receipt)
        return receipt, final
    except (Exception, asyncio.CancelledError) as error:
        receipt.update(outcome='UNKNOWN' if transport.sent else 'NOT_SENT',
                       reason='CLIENT_CANCELLED' if isinstance(error, (asyncio.CancelledError, ClientCancelled)) else type(error).__name__,
                       elapsed_seconds=time.monotonic()-started, http_status=transport.status,
                       provider_reported_model_ids=sorted(transport.models))
        if transport.sent:
            journal.finish(attempt, 'UNKNOWN', receipt)
        return receipt, None


async def run(journal, region, case, key):
    chinese = case.startswith('zh')
    use_tool = case in ('zh-tool', 'en-tool', 'tool-failure')
    prompt = ('这是合成测试。请用一句中文给首次来北京的游客建议，不编造价格或开放时间。' if chinese else
              'Synthetic test. Give a first-time Beijing visitor one English sentence; do not invent prices or hours.')
    if use_tool:
        prompt = '请调用synthetic_echo传入整数7，然后仅输出JSON {"value":7}。' if chinese else 'Call synthetic_echo with integer 7, then output only JSON {"value":7}.'
    if case == 'structured-invalid':
        prompt = 'Synthetic parser negative case. Output exactly the non-JSON string NOT_JSON.'
    messages = [UserMsg(name='synthetic', content=prompt)]
    receipt, final = await request(journal, region, case, 0, messages, key, tool=use_tool)
    result = dict(case=case, receipt=receipt, versions={name:version(name) for name in ('agentscope','dbos','openai','httpx','pydantic')})
    if final is None:
        result['status'] = 'PASS' if case in ('timeout','cancel') and receipt['outcome']=='UNKNOWN' else 'FAIL'
        return result
    text = ''.join(block.text for block in final.content if isinstance(block, TextBlock))
    result.update(text_chars=len(text), output_sha256=hashlib.sha256(text.encode()).hexdigest())
    if case == 'structured-invalid':
        try:
            json.loads(text)
        except ValueError:
            result.update(status='PASS', structured_output='REJECTED', business_success=False)
        else:
            result.update(status='FAIL', structured_output='UNEXPECTED_VALID_JSON')
    elif use_tool:
        calls = [block for block in final.content if isinstance(block, ToolCallBlock)]
        if len(calls) != 1 or calls[0].name != 'synthetic_echo' or json.loads(calls[0].input) != {'value':7}:
            result.update(status='FAIL', tool='INVALID_CALL')
            return result
        def echo(value):
            if case == 'tool-failure':
                raise RuntimeError('synthetic_local_tool_failure')
            return {'value':value}
        try:
            tool_result = json.dumps(echo(json.loads(calls[0].input)['value']))
        except RuntimeError:
            result.update(status='PASS', tool='FAILED_SYNTHETIC_LOCAL_TOOL', business_success=False, following_model_calls=0)
            return result
        messages.extend([Msg(name='model', role='assistant', content=final.content),
                         Msg(name='tool', role='assistant', content=[ToolResultBlock(id=calls[0].id, name='synthetic_echo', output=tool_result, state='success')])])
        second, final = await request(journal, region, case, 1, messages, key)
        result['second_receipt'] = second
        if final is None:
            result['status'] = 'FAIL'
        else:
            text = ''.join(block.text for block in final.content if isinstance(block, TextBlock))
            try:
                result['status'] = 'PASS' if json.loads(text)=={'value':7} else 'FAIL'
            except ValueError:
                result['status'] = 'FAIL'
            result.update(tool='EXECUTED_LOCAL_SYNTHETIC_ECHO', structured_output=result['status'])
    else:
        result['status'] = 'PASS' if text and receipt['chunk_count']>1 else 'FAIL'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--region', choices=TARGETS, required=True)
    parser.add_argument('--case', choices=('zh-answer','en-answer','zh-tool','en-tool','structured-invalid','tool-failure','timeout','cancel','kill-before-send','kill-after-send'))
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--sample', choices=('original', 'parser-fixed'), default='original')
    args = parser.parse_args()
    journal = Journal(args.root)
    if args.inspect:
        print(json.dumps(journal.inspect()))
        return
    if args.case is None:
        parser.error('case required')
    # Existing actions are read-only BEFORE even loading credentials/SDK client.
    case = args.case
    if args.sample == 'parser-fixed':
        if args.case != 'zh-answer':
            parser.error('parser-fixed is one distinct replacement validation sample, only for zh-answer')
        case = 'zh-answer-parser-fixed'
    if any(row['attempt_id']==args.region+':'+case+':0' for row in journal.inspect()):
        print(json.dumps(dict(status='READ_ONLY', attempts=journal.inspect())))
        return
    found = subprocess.run(['security','find-generic-password','-s',TARGETS[args.region][2],'-w'],capture_output=True,text=True)
    if found.returncode != 0 or not found.stdout.strip():
        print(json.dumps(dict(status='UNRUN',reason='KEYCHAIN_UNAVAILABLE',region=args.region)))
        return
    print(json.dumps(asyncio.run(run(journal,args.region,case,found.stdout.strip()))))


if __name__ == '__main__':
    main()
