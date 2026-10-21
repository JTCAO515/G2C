"""Offline wire-format and retry probe for installed AgentScope/OpenAI SDKs.

httpx.MockTransport handles every request; runtime also forbids sockets.
No real provider compatibility, billing, region, or model quality is tested.
"""
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import openai
from agentscope.credential import OpenAICredential
from agentscope.message import UserMsg
from agentscope.model import OpenAIChatModel
from agentscope.tool import ToolChoice
from agentscope.exception import StructuredOutputError
from pydantic import BaseModel

import runtime  # install no-network guard, but never launch DBOS

HERE = Path(__file__).resolve().parent


class Shape(BaseModel):
    value: int


async def probe():
    checks, requests = [], []
    mode = 'stream'

    def handler(request):
        payload = json.loads(request.content)
        requests.append({'mode': mode, 'url': str(request.url), 'json': payload})
        if mode == 'timeout':
            raise httpx.ReadTimeout('synthetic timeout after dispatch', request=request)
        if mode == 'structure':
            return httpx.Response(200, json={'id': 'fixture-response', 'object': 'chat.completion',
                'created': 1, 'model': 'qwen3.8-flash',
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': 'not-valid-structured-output'}}]})
        chunks = [{'id': 'fixture-response', 'object': 'chat.completion.chunk', 'created': 1,
                   'model': 'qwen3.8-flash', 'choices': [{'index': 0, 'delta': {'content': part}, 'finish_reason': None}]}
                  for part in ('你好', ' hello')]
        chunks.append({'id': 'fixture-response', 'object': 'chat.completion.chunk', 'created': 1,
                       'model': 'qwen3.8-flash', 'choices': [],
                       'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}})
        body = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, content=body, headers={'content-type': 'text/event-stream'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        model = OpenAIChatModel(credential=OpenAICredential(api_key='unused-local-fixture',
                                    base_url='https://model.invalid/compatible-mode/v1'),
                     model='qwen3.8-flash', parameters=OpenAIChatModel.Parameters(max_tokens=64),
                     max_retries=0, client_kwargs={'max_retries': 0, 'http_client': client, 'timeout': 1.0})
        messages = [UserMsg(name='synthetic-user', content='你好 / hello')]
        response = await model(messages)
        chunks = [c async for c in response]
        assert chunks[-1].is_last
        assert chunks[-1].content[0].text == '你好 hello'
        assert requests[-1]['json']['model'] == 'qwen3.8-flash'
        # Installed SDK maps max_tokens to max_completion_tokens; backend
        # acceptance is NOT proved by a mock accepting this request.
        assert requests[-1]['json']['max_completion_tokens'] == 64
        checks.append({'case': 'sdk-local-stream', 'status': 'PASS',
                       'last_text': chunks[-1].content[0].text,
                       'wire_limit_field': 'max_completion_tokens',
                       'real_qwen_accepts_field': 'UNKNOWN'})
        mode = 'timeout'
        before = len(requests)
        try:
            await model(messages)
            raise AssertionError('timeout was hidden')
        except openai.APITimeoutError:
            pass
        assert len(requests) - before == 1
        checks.append({'case': 'both-retry-layers-disabled', 'status': 'PASS', 'sends': 1})
        # Explicit strategy prevents AgentScope native structured-output ladder
        # from initiating additional requests after a response fails validation.
        mode = 'structure'
        model.stream = False
        before = len(requests)
        try:
            await model.generate_structured_output(messages, Shape, tool_choice=ToolChoice(mode='generate_structured_output'))
            raise AssertionError('invalid structured output was accepted')
        except StructuredOutputError:
            pass
        assert len(requests) - before == 1
        checks.append({'case': 'native-structured-failure-explicit-strategy', 'status': 'PASS', 'sends': 1})
    source_files = {
        'agentscope.model._openai_chat._model': Path(__import__('agentscope.model._openai_chat._model', fromlist=['x']).__file__),
        'agentscope.model._base': Path(__import__('agentscope.model._base', fromlist=['x']).__file__),
        'agentscope.agent._agent': Path(__import__('agentscope.agent._agent', fromlist=['x']).__file__),
        'dbos._dbos': Path(__import__('dbos._dbos', fromlist=['x']).__file__),
    }
    output = {'scope': 'offline MockTransport with network guard; real provider UNRUN',
              'checks': checks, 'requests': requests,
              'source_hashes': {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in source_files.items()},
              'script_sha256': hashlib.sha256((HERE / 'sdk_probe.py').read_bytes()).hexdigest()}
    (HERE / 'evidence' / 'sdk-probe.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(probe())
