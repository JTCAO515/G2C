"""Signed local regression for ordinary Lio replies with missing settlement metadata."""
from datetime import datetime, timezone
import json
from unittest.mock import patch

import lio_projection_pg as projection
import lio_dispatch_concurrency_pg
from cj_agent.provider import (
    _M4_REQUEST_SENT, DashScopeConfig, M4_BASE, M4_MODEL, M4_TURN_FUNCTION_V2,
    MeteredDashScopeProvider,
)
from cj_api.local_app import load_confirmation_signer
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices, RealTools
from cj_message.lio_context import UNSETTLED_VISIBLE_ANSWER
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
import run_worker
from test_lio_planning_flow import flow


TRANSIT_QUESTION = 'What are the rules for 240-hour visa-free transit in China?'
UNSUPPORTED_POLICY = 'Admission is guaranteed at any port regardless of passport. ' * 8
PROMPTS = {'zh': '第一次来中国建议怎么玩？', 'en': 'First time in China, any tips?'}
REPLIES = {
    'zh': '可以从一个城市开始，多留时间走街串巷、逛博物馆和看公园。' * 8,
    'en': 'Start in one city and leave time to explore neighborhoods and museums. ' * 8,
}


def wire_delta(profile, locale, case):
    if profile == 'compact':
        arguments = ({'calls': [{'name': 'fact', 'arguments': {'topic': 'visitor'}}]}
                     if case == 'tool' else {'answer': REPLIES})
        return {'tool_calls': [dict(index=0, id='local-envelope', type='function',
            function=dict(name=M4_TURN_FUNCTION_V2, arguments=json.dumps(arguments, ensure_ascii=False)))]}
    if case == 'tool':
        return {'tool_calls': [dict(index=0, id='local-fact', type='function',
            function=dict(name='fact', arguments='{}'))]}
    return {'content': REPLIES[locale]}


@patch('asyncio.open_connection', new=lio_dispatch_concurrency_pg.reject_unmocked_connection)
def check_ordinary(api, headers, database, auth, subject, scope, memory, root):
    subjects = frozenset({subject})
    signer = load_confirmation_signer(auth)
    missing, leaked = [], []
    cases = (
        ('zh','complete','done'), ('en','complete','done'),
        ('en','complete','usage'), ('en','complete','model'),
        ('zh','truncated','done'), ('en','truncated','done'), ('en','tool','done'),
    )
    with database.connect(scope) as db:
        initial_memory = db.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]
        initial_trips = db.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]
        initial_bindings = db.execute('SELECT count(*) FROM cj_message_needs_binding').fetchone()[0]
    for profile in ('buffered', 'streaming', 'compact'):
        profile_cases = cases + ((('en','transit','done'),) if profile == 'streaming' else ())
        for locale, case, omitted in profile_cases:
            tag = '-'.join((profile, locale, case, omitted))
            budget = AuthorizationBudget(root / tag, clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
            model = MeteredDashScopeProvider(
                DashScopeConfig(M4_BASE, M4_MODEL, 'local-ordinary-fixture-only', max_output_tokens=1536), budget,
            )
            services = RealServices(model, 'local-ordinary-fixture-only', subjects,
                                    demo_subjects=subjects, national_subjects=subjects)
            tools = RealTools(services,
                buffered_streaming_subjects=subjects if profile=='buffered'else frozenset(),
                assembly_streaming_subjects=subjects if profile=='streaming'else frozenset())
            worker = run_worker._worker_for_scope(database,model,auth,scope,checker_for(auth),
                memory_configuration=memory,tools_configuration=tools,draft_profile='needs-structured.1',
                assembly_planning=True,demo_planning=True,national_planning=True,
                lio_confirmation=signer,lio_memory_enabled=True)
            mid = 'ordinary-' + tag
            question = TRANSIT_QUESTION if case == 'transit' else PROMPTS[locale]
            received = api.post('/v2/lio/messages', headers=headers, content=encode(dict(
                version='LIO-message.2',message_id=mid,text=question,locale=locale,new_conversation=True)))
            assert received.status_code == 200
            cid = received.json()['conversation_id']
            attempts = []
            streamed_truncation = profile == 'streaming' and case == 'truncated'

            async def wire(config,raw,guard,observation):
                assert guard() is True
                packet = json.loads(raw)
                system = packet['messages'][0]['content']
                if 'LIO-planning-intake' in system:
                    assert case == 'transit'
                    index = packet['response_format']['json_schema']['schema']['properties']['current_source_index']['const']
                    intake = flow(question,city=None,days=None,intent='consult',questions=(),index=index)
                    intake.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=True)
                    attempts.append('intake')
                    yield _M4_REQUEST_SENT
                    observation['http_status'] = 200
                    envelope = dict(id=tag+'-intake',model=M4_MODEL,choices=[dict(index=0,
                        delta=dict(content=json.dumps(intake)),finish_reason='stop')],
                        usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
                    yield ('data: '+json.dumps(envelope)+'\n\ndata: [DONE]\n\n').encode()
                    return
                if case == 'transit':
                    assert 'use the official entry notice' in system
                expected_tool = M4_TURN_FUNCTION_V2 if profile=='compact'else'fact'
                assert [tool['function']['name'] for tool in packet['tools']]==[expected_tool]
                attempts.append('answer')
                yield _M4_REQUEST_SENT
                observation['http_status'] = 200
                finish = 'length' if case=='truncated' else 'tool_calls' if case=='tool' or profile=='compact' else 'stop'
                delta = {'content': UNSUPPORTED_POLICY} if case == 'transit' else wire_delta(profile, locale, case)
                if streamed_truncation:
                    first = dict(id=tag, model=M4_MODEL,
                        choices=[dict(index=0, delta=delta, finish_reason=None)])
                    yield ('data: '+json.dumps(first,ensure_ascii=False)+'\n\n').encode('utf-8')
                    delta = {}
                value = dict(id=tag,model=M4_MODEL,
                    choices=[dict(index=0,delta=delta,finish_reason=finish)],
                    usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
                if omitted!='done':del value[omitted]
                yield ('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode('utf-8')
                if omitted!='done':yield b'data: [DONE]\n\n'

            with patch('cj_agent.provider._m4_wire',wire):
                outcome, = worker.process()
            expected_attempts = ['intake','answer'] if case == 'transit' else ['answer']
            expected_states = ['RECEIVED','INTENT'] if case == 'transit' else ['INTENT']
            assert attempts == expected_attempts and outcome.status == 'unknown' and outcome.proposal_id is None
            assert [fee['state'] for fee in budget.inspect()] == expected_states
            signed = api.get('/v2/lio/timeline',headers=headers,params={'conversation_id':cid})
            assert signed.status_code==200
            message, = signed.json()['messages']
            assert message['message_id']==mid and message['trip'] is None and message['memory'] is None
            binding=worker._binding(worker.messages.query(mid).receipt)
            native=worker.runs.snapshot(binding)
            assert native.status=='unknown'
            retained=UNSETTLED_VISIBLE_ANSWER in native.effects
            if case=='transit':
                unsupported = 'Admission is guaranteed at any port'
                assert unsupported not in message['answer'] and unsupported not in native.text
                assert message['sources'] == []
                continue
            if case=='complete':
                if not (retained and message['status']=='completed' and message['answer']==REPLIES[locale]):
                    missing.append(tag)
                elif profile=='streaming':
                    with database.connect(scope) as db:
                        count=db.execute("SELECT count(*) FROM cj_run_event WHERE scope=%s AND run_id=%s AND kind='text_delta'",
                                         (scope,binding.run_id)).fetchone()[0]
                    assert count>=2, 'the streamed prefix was not exercised'
            else:
                assert message['status']=='failed' and not retained
                if streamed_truncation:
                    assert native.text and REPLIES[locale].startswith(native.text)
                if message['answer']:
                    leaked.append(tag)
    with database.connect(scope) as db:
        assert db.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]==initial_memory
        assert db.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==initial_trips
        assert db.execute('SELECT count(*) FROM cj_message_needs_binding').fetchone()[0]==initial_bindings
    assert not (missing or leaked), dict(complete_replies_hidden=missing, rejected_replies_exposed=leaked)
    print('PASS ordinary missing DONE/usage/model in 3 modes; original UNKNOWN/INTENT and no writes',flush=True)


def main():
    harness=projection.harness
    with patch.object(lio_dispatch_concurrency_pg,'check_dispatch',check_ordinary), \
         patch.object(harness,'exercise',lambda auth,config:projection.exercise(
             auth.parent/'ordinary-unsettled',config,dispatch_check=True)):
        harness.main()


if __name__=='__main__':
    main()
