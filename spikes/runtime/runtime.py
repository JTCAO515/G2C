"""AgentScope + DBOS executable local spike. There is no real provider path."""
import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Literal

# Defense in depth: local experiments fail if any SDK tries network access.
# The controller launches workers with a minimal environment (no secrets).
import socket

def no_network(*args, **kwargs):
    raise RuntimeError('NETWORK_DISABLED_IN_LOCAL_SPIKE')

socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network

from agentscope.agent import Agent, InjectionConfig, ModelConfig, ReActConfig
from agentscope.credential import CredentialBase
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg, TextBlock, ToolCallBlock, UserMsg
from agentscope.model import ChatModelBase, ChatResponse
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, Toolkit
from dbos import DBOS, DBOSClient, SetWorkflowID
from pydantic import BaseModel, ConfigDict, ValidationError

import ledger


class Output(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['SUCCESS']
    text: str
    fixture: Literal[True]


class CallUnresolved(RuntimeError):
    pass


def crash_once(root, point):
    """Fault injection only; executes within a DBOS step, never workflow code."""
    if os.environ.get('CJ002_FAULT') != point:
        return
    marker = Path(root) / ('crashed-' + point)
    try:
        with marker.open('x') as f:
            f.write('91\n')
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError:
        return
    os._exit(91)


async def pause(root, point):
    if os.environ.get('CJ002_PAUSE') != point:
        return
    (Path(root) / ('paused-' + point)).write_text('ready\n')
    deadline = time.monotonic() + 20
    while not (Path(root) / ('release-' + point)).exists():
        if time.monotonic() > deadline:
            raise TimeoutError('synthetic pause watchdog')
        await asyncio.sleep(0.02)


@DBOS.step(retries_allowed=False)
async def prepare(root):
    ledger.probe(root, 'prepare')
    return {'prepared': True}


@DBOS.step(retries_allowed=False)
async def boundary(root, point):
    crash_once(root, point)
    await pause(root, point)


@DBOS.step(retries_allowed=False)
async def model_step(root, action_id, principal, locale, scenario, turn, request_hash):
    # Intent ID does not depend on workflow ID: changing workflow cannot evade it.
    attempt_id = ledger.digest([principal, action_id, 'model', turn])
    cached = ledger.begin_attempt(root, attempt_id, principal, request_hash)
    if cached is not None:
        return cached
    crash_once(root, 'intent_before_send')
    ledger.dispatch(root, attempt_id)  # synthetic provider observation, no network
    await pause(root, 'inflight_model')
    crash_once(root, 'during_call')
    if scenario == 'timeout':
        # Whether provider accepted/charged is unknown; never treat as safe retry.
        ledger.unknown_attempt(root, attempt_id, 'model_timeout')
        return {'outcome': 'UNKNOWN', 'reason': 'model_timeout', 'attempt_id': attempt_id}
    if turn == 0:
        response = {'outcome': 'COMPLETE', 'kind': 'tool', 'tool_id': 'fixture-tool-1'}
    else:
        text = '已记录本地测试值。' if locale == 'zh' else 'The local test value was recorded.'
        response = {'outcome': 'COMPLETE', 'kind': 'text',
                    'text': 'invalid json' if scenario == 'bad_structure' else
                    ledger.encode({'outcome': 'SUCCESS', 'text': text, 'fixture': True})}
    crash_once(root, 'after_provider_response')
    ledger.complete_attempt(root, attempt_id, response)
    crash_once(root, 'after_attempt_receipt')
    return response


@DBOS.step(retries_allowed=False)
async def business_step(root, principal, action_id, value, scenario):
    if scenario == 'tool_failure':
        return {'outcome': 'FAILED', 'reason': 'synthetic_tool_failure'}
    try:
        result = ledger.commit_business(root, principal, action_id, value)
    except ValueError as exc:
        return {'outcome': 'CONFLICT', 'reason': str(exc)}
    crash_once(root, 'after_business_commit')
    return result


class DurableFixtureModel(ChatModelBase):
    """Real AgentScope extension point, scripted provider; no model quality claim."""
    def __init__(self, root, principal, action_id, locale, scenario):
        super().__init__(CredentialBase(name='no-secret-local-fixture'),
                         'synthetic-only', self.Parameters(), stream=True, max_retries=0)
        self.root, self.principal, self.action_id = root, principal, action_id
        self.locale, self.scenario, self.turn = locale, scenario, 0
        self.formatter = OpenAIChatFormatter()
        self.unresolved = None

    async def count_tokens(self, *args, **kwargs):
        # Synthetic token estimate only; avoid optional tokenizer downloads.
        return 100

    async def _call_api(self, model_name, messages, tools=None, tool_choice=None, **kwargs):
        if self.turn >= 2:
            raise RuntimeError('LOCAL_MODEL_CALL_LIMIT')
        turn = self.turn
        self.turn += 1
        # The fixture's request identity is explicit and excludes framework IDs.
        # Production must hash the full exact outbound request in its adapter.
        request_hash = ledger.digest([self.principal, self.action_id, self.locale, self.scenario, turn])
        await boundary(self.root, 'before_model_step' if turn == 0 else 'after_business_step')
        response = await model_step(self.root, self.action_id, self.principal, self.locale,
                                    self.scenario, turn, request_hash)
        if response['outcome'] != 'COMPLETE':
            self.unresolved = response
            raise CallUnresolved(response['reason'])
        await boundary(self.root, 'after_model_step' if turn == 0 else 'before_publish')
        if response['kind'] == 'tool':
            return ChatResponse(content=[ToolCallBlock(id=response['tool_id'], name='record_local_value', input='{"value":7}')], is_last=True)
        # Buffered deltas: receipt persisted before any chunk leaves this adapter.
        # This checks AgentScope event transport, not provider streaming or SSE.
        async def chunks():
            text = response['text']
            for part in (text[:len(text)//2], text[len(text)//2:]):
                yield ChatResponse(content=[TextBlock(id='fixture-text', text=part)], is_last=False, id='fixture-response')
            yield ChatResponse(content=[TextBlock(id='fixture-text', text=text)], is_last=True, id='fixture-response')
        return chunks()


@DBOS.workflow()
async def agent_workflow(root, principal, action_id, locale, scenario):
    await prepare(root)
    tool_outcomes = []

    async def record_local_value(value: int):
        """Record a synthetic integer in the local test ledger, not a Trip.

        Args:
            value: Synthetic integer.
        """
        result = await business_step(root, principal, action_id, value, scenario)
        tool_outcomes.append(result)
        return ledger.encode(result)

    model = DurableFixtureModel(root, principal, action_id, locale, scenario)
    agent = Agent(name='CJ002-fixture', system_prompt='Only run the local synthetic test tool.',
                  model=model,
                  toolkit=Toolkit(tools=[FunctionTool(record_local_value, is_concurrency_safe=False,
                                    permission=PermissionDecision(behavior=PermissionBehavior.ALLOW, message='Allow only this local synthetic tool'))]),
                  model_config=ModelConfig(max_retries=0, fallback_model=None),
                  react_config=ReActConfig(max_iters=2, interruption_raise_cancelled_error=True),
                  injection_config=InjectionConfig(inject_runtime_state=False))
    events, final = [], None
    try:
        async for item in agent.reply_stream(UserMsg(name='synthetic-user', content='记录测试值' if locale == 'zh' else 'Record the test value'), yield_final_msg=True):
            if isinstance(item, Msg):
                final = item
            else:
                events.append(str(item.type))
    except CallUnresolved:
        return model.unresolved
    if model.unresolved:
        return model.unresolved
    if final is None:
        return {'outcome': 'FAILED', 'reason': 'missing_final_message'}
    if final.error is not None or str(final.finished_reason) != 'completed':
        return {'outcome': 'FAILED', 'reason': 'agent_error', 'finished_reason': str(final.finished_reason)}
    if not tool_outcomes or tool_outcomes[-1].get('result') != 'COMMITTED':
        return {'outcome': 'FAILED', 'reason': 'tool_not_committed', 'tool_outcomes': tool_outcomes}
    try:
        validated = Output.model_validate_json(final.get_text_content()).model_dump()
    except ValidationError:
        return {'outcome': 'FAILED', 'reason': 'invalid_structured_output', 'tool_outcomes': tool_outcomes}
    # This is the workflow output; DBOS cancellation is checked by the preceding
    # step boundary. Product publication needs its own transaction/version fence.
    return {'outcome': 'SUCCESS', 'output': validated, 'tool_outcomes': tool_outcomes, 'event_types': events}


def system_url(root):
    return 'sqlite:///' + str((Path(root) / 'dbos.sqlite').resolve())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['start', 'recover', 'cancel', 'inspect'])
    p.add_argument('--root', required=True)
    p.add_argument('--workflow', default='workflow-1')
    p.add_argument('--action', default='action-1')
    p.add_argument('--principal', default='fresh-user-a')
    p.add_argument('--locale', default='en', choices=['en', 'zh'])
    p.add_argument('--scenario', default='success', choices=['success', 'timeout', 'bad_structure', 'tool_failure'])
    args = p.parse_args()
    root = str(Path(args.root).resolve())
    ledger.initialize(root)
    if args.command in ('cancel', 'inspect'):
        client = DBOSClient(system_database_url=system_url(root))
        if args.command == 'cancel':
            client.cancel_workflow(args.workflow)
        print(json.dumps({'workflow_status': client.retrieve_workflow(args.workflow).get_status().status,
                          'ledger': ledger.snapshot(root)}, ensure_ascii=False))
        client.destroy()
        return
    DBOS(config={'name': 'cj002-local', 'application_version': 'cj002-v1',
                 'executor_id': 'cj002-single-local-executor',
                 'system_database_url': system_url(root), 'enable_otlp': False,
                 'conductor_key': None, 'log_level': 'ERROR', 'use_listen_notify': False})
    asyncio.run(execute(args, root))


async def execute(args, root):
    DBOS.launch()
    try:
        if args.command == 'start':
            with SetWorkflowID(args.workflow):
                handle = await DBOS.start_workflow_async(agent_workflow, root, args.principal,
                                             args.action, args.locale, args.scenario)
        else:
            handle = await DBOS.retrieve_workflow_async(args.workflow)
        try:
            result = await asyncio.wait_for(handle.get_result(), timeout=25)
        except Exception as exc:
            result = {'outcome': 'WORKFLOW_ERROR', 'error_type': type(exc).__name__}
        status = await DBOS.get_workflow_status_async(args.workflow)
        steps = await DBOS.list_workflow_steps_async(args.workflow)
        print(json.dumps({'workflow_status': status.status, 'result': result,
                          'steps': [{'name': s['function_name'], 'id': s['function_id']} for s in steps],
                          'ledger': ledger.snapshot(root)}, ensure_ascii=False))
    finally:
        DBOS.destroy()


if __name__ == '__main__':
    main()
