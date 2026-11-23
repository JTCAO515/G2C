"""Signed PG contract test for activities in each day of a read-only plan."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import time
from unittest.mock import patch
from uuid import uuid4

import lio_projection_pg as projection
from lio_dispatch_concurrency_pg import confirm_model_write
import psycopg
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from cj_agent.provider import DashScopeConfig, M4_BASE, M4_MODEL, MeteredDashScopeProvider, _M4_REQUEST_SENT
from cj_api.local_app import ISSUER, LocalDatabase, create_local_app, load_confirmation_signer, scope_for
from cj_api.local_run_context import load_run_context
from cj_api.real_services import RealServices, RealTools
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget
from runtime_adapter.contract import encode
import dev_auth
import local_run_context
import run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow


def exercise(auth, conninfo):
    root = auth.parent
    subject = 'm4-synthetic-demo-999999999999'
    other_subject = 'm4-synthetic-demo-999999999998'
    subjects = frozenset({subject})
    admitted = frozenset({subject, other_subject})
    dev_auth.init(auth, admitted)
    scope = scope_for(ISSUER, subject)
    now = int(time.time())
    meter_file = root / 'meter.json'
    meter_file.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2', current=dict(meter=dict(
        unit='provider_call', budget=80, period_start=now-60, period_end=now+3600,
        max_steps=12, max_tools=4, max_output=60000, max_seconds=600),
        output_limits=dict(model=12000, tool=4000, memory=12000)), history=[])))
    meter = load_run_context(meter_file)
    for person in (subject, other_subject):
        local_run_context.provision_budget(conninfo, meter, person)
        dev_auth.activate_travel(conninfo, person, meter, ABI)
    with psycopg.connect(**json.loads(conninfo.read_bytes())) as admin:
        for person in admitted:
            assert admin.execute("UPDATE cj_message_scope SET demo_invite_digest=%s,"
                                 "demo_invite_expires_at=clock_timestamp()+interval '1 hour',demo_session_floor=0 WHERE scope=%s",
                                 (sha256(person.encode()).hexdigest(),scope_for(ISSUER, person))).rowcount==1
    db = LocalDatabase(conninfo, run_context=meter, travel_context=True, needs_context=True, trip_context=True)
    memory = TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',
        collection=dict(version='local-memory-typed.1', collection=dict(version='local-memory-policy.1',
            expires_at='2099-01-01T00:00:00Z', profiles={subject:dict(subjects=['self'], extents=['long_term'],
                context_ids=[], slots={'travel.pace':dict(kind='preference', collection_allowed=True,
                                                         semantic_resolved=True)})}),
            travel_contexts={subject: []}),
        selections={subject:dict(subject='self', slots=['travel.pace'], max_bytes=1000)})))
    budget = AuthorizationBudget(root / 'financial', clock=lambda:datetime(2026,11,19,tzinfo=timezone.utc))
    model = MeteredDashScopeProvider(DashScopeConfig(M4_BASE, M4_MODEL, 'local-fixture-not-live'), budget)
    services = RealServices(model, 'local-fixture-not-live', subjects,
                            demo_subjects=subjects, national_subjects=subjects)
    tools = RealTools(services, buffered_streaming_subjects=subjects)
    seen = []
    expected_ledger = []

    cases = {
        'zh': ('北京三日游','北京','三日','第1天：参观〈地点〉。',
               '第一天：参观故宫。\n第二天：登上慕田峪长城。\n第三天：游览颐和园。\n想先细化哪天？',
               '第一天：故宫、景山。\n第二天：慕田峪长城。\n第三天：颐和园。\n想先细化哪天？'),
        'en': ('A three-day trip to Beijing','Beijing','three-day','Day 1: Visit <place>.',
               'Day 1: Visit the Forbidden City.\nDay 2: Walk the Great Wall.\nDay 3: Tour the Summer Palace.\nWhich day should we adjust?',
               'Day 1: Forbidden City.\nDay 2: Great Wall.\nDay 3: Summer Palace.\nWhich day should we adjust?'),
    }
    locations = dict(zh=('故宫博物院', '慕田峪长城', '颐和园'),
                     en=('Forbidden City', 'Mutianyu Great Wall', 'Summer Palace'))
    cancelled_answer = dict(zh='故宫这项参观已取消，可以改去景山。',
                            en='The Forbidden City visit is cancelled. Jingshan Park is an alternative.')
    chosen_reply = None
    continuation = None

    async def fake_wire(config, raw, guard, observation, *, send_under_fence=None):
        nonlocal chosen_reply
        packet=json.loads(raw)
        await confirm_model_write(guard,send_under_fence)
        index=packet.get('response_format',{}).get('json_schema',{}).get('schema',{}).get(
            'properties',{}).get('current_source_index',{}).get('const')
        if index is not None:
            seen.append('intake')
            if continuation is None:
                assert index==0
                assert all('你能做什么' not in row['content'] and '你是谁' not in row['content']
                           for row in packet['messages'])
                value=flow(prompt,city=city,days=3,intent='plan',questions=(),index=index)
                value.update(field_sources=[dict(field='duration_days',source_index=index,quote=duration_quote)])
            else:
                first,followup,city_name,question,_,_=continuation
                if index==0:
                    value=flow(first,city=city_name,days=None,intent='plan',questions=('duration_days',),reply=question)
                    value['planning_request_index']=0
                else:
                    assert index==1
                    value=flow(followup,city=city_name,intent='plan',questions=(),index=index)
                    value['city'].update(source_index=0,quote=first,normalized_name='成都')
                    value['unknown_fields']=['start_date','party_size']
                    value['field_sources']=[dict(field='start_date',source_index=0,quote=''),
                                            dict(field='party_size',source_index=0,quote=''),
                                            dict(field='duration_days',source_index=1,quote=followup)]
            value.update(version='LIO-planning-intake.8',needs_tools=False)
        else:
            response_format=packet['response_format']
            assert response_format['type']=='json_schema',response_format
            schema=response_format['json_schema']['schema']
            assert set(schema['required'])=={'answer','days','follow_up'}
            [days,_]=schema['properties']['days']['anyOf']
            assert days['minItems']==days['maxItems']==3
            assert packet['max_tokens']==1024 and 'tools' not in packet
        if index is None and continuation is not None:
            seen.append('discussion')
            assert 'Start every day line with the day label and an explicit activity verb' in packet['messages'][0]['content']
            assert continuation[0] in [m['content']for m in packet['messages']if m['role']=='user']
            assert continuation[1] in [m['content']for m in packet['messages']if m['role']=='user']
            value={'answer':continuation[4]}
        elif index is None:
            seen.append('discussion')
            system=packet['messages'][0]['content']
            # Hold model behavior fixed as a contract fixture. Only a prompt
            # with an explicit per-day activity and a locale example produces
            # the schedule shape. The alternative reproduces a place list.
            chosen_reply=answer if ('Start every day line with the day label and an explicit activity verb'
                                   in system and example in system) else bare
            if structured == 'cancelled':chosen_reply=cancelled_answer[locale]
            value={'answer':chosen_reply}
            if structured == 'declined':
                value.update(days=None,follow_up=None)
            elif structured:
                places = list(locations[locale])
                if structured == 'cancelled':
                    places[0]+='（参观取消）' if locale=='zh' else ' (visit cancelled)'
                if structured == 'bare_site':
                    places=('故宫','颐和园','长城') if locale=='zh' else ('Forbidden City','Summer Palace','Great Wall')
                value['days'] = [dict(day_index=i, activities=[dict(place_name=place, verb='visit', period=None)])
                                 for i, place in enumerate(places, 1)]
                if structured == 'invalid':
                    value['days'].pop()
                if structured in ('valid','bare_site'):
                    value['follow_up']=None
            if structured in ('valid','declined'):
                Draft202012Validator(schema).validate(value)
            elif structured == 'bare_site':
                assert not Draft202012Validator(schema).is_valid(value)
        yield _M4_REQUEST_SENT
        observation['http_status']=200
        frame=dict(id='legacy-plan-fixture-'+str(len(seen)),model=M4_MODEL,choices=[
            dict(index=0,delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason='stop')],
            usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
        end = '' if index is None and structured == 'unsettled' else 'data: [DONE]\n\n'
        yield ('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n'+end).encode()

    async def catalog(key, guard, *, send_under_fence=None):
        def admitted():
            assert guard() is True
        if send_under_fence is None:
            admitted()
        else:
            await send_under_fence(admitted)
        return city_catalog()

    async def no_network(*args, **kwargs):
        raise AssertionError('private fixture attempted an unmocked connection')

    app = create_local_app(conninfo_path=None,auth_dir=auth,database=db,run_context=meter,account_admission=True,
                           demo_dialogue_subjects=admitted,lio_dialogue_subjects=admitted)
    headers = {'Authorization':'Bearer '+dev_auth.token(auth,subject,300),
               'Content-Type':'application/octet-stream'}
    other_headers = {'Authorization': 'Bearer '+dev_auth.token(auth,other_subject,300)}

    def worker():
        return run_worker.run_once(db,model,auth,memory_configuration_for_scope=lambda _:memory,
            tools_configuration=tools,real_services=services,account_admission=True,
            hk_beta_b_run_credential=True,hk_assembly_scopes=frozenset({scope}),
            hk_assembly_run_credential_scopes=frozenset({scope}),hk_demo_scopes=frozenset({scope}),
            lio_confirmation=load_confirmation_signer(auth))

    with TestClient(app) as api, patch('asyncio.open_connection',new=no_network), patch(
            'cj_agent.provider._m4_wire',new=fake_wire), patch('cj_api.lio_city.catalog_response',new=catalog):
        for locale,(prompt,city,duration_quote,example,answer,bare) in cases.items():
            scenarios = (None, 'valid', 'declined', 'invalid', 'cancelled', 'bare_site')
            if locale=='en':scenarios+=('unsettled',)
            for structured in scenarios:
                mid=str(uuid4())
                receipt=api.post('/v2/lio/messages',headers=headers,content=encode(dict(
                    version='LIO-message.2',message_id=mid,locale=locale,text=prompt,new_conversation=True)))
                assert receipt.status_code==200,receipt.status_code
                cid=receipt.json()['conversation_id']
                route = '/v2/lio/itinerary-preview'
                query = dict(conversation_id=cid, message_id=mid)
                pending = api.get(route, headers=headers, params=query)
                assert pending.status_code == 200 and pending.json()['preview'] is None
                before=len(seen)
                outcome,=worker()
                assert outcome.status==('unknown' if structured=='unsettled' else 'completed')
                assert seen[before:]==['intake','discussion']
                expected_ledger.extend(('RECEIVED','RECEIVED','INTENT' if structured=='unsettled' else 'RECEIVED'))
                page=api.get('/v2/lio/timeline',headers=headers,params={'conversation_id':cid})
                assert page.status_code==200
                row,=page.json()['messages']
                assert (row['message_id'],row['status'],row['trip'],row['memory'])==(mid,'completed',None,None)
                expected_reply=cancelled_answer[locale] if structured=='cancelled' else answer
                assert chosen_reply==expected_reply, (locale,'place-only reply did not meet the plan contract')
                result = api.get(route, headers=headers, params=query)
                assert result.status_code == 200, result.status_code
                assert result.headers['Cache-Control'] == 'no-store'
                assert api.get(route, params=query).status_code == 401
                foreign = api.get(route, headers=other_headers, params=query)
                assert foreign.status_code == 404, foreign.status_code
                assert api.get(route, headers=headers, params=dict(query, conversation_id='lio-dialogue-'+'0'*32)).status_code==404
                expected = None
                if structured == 'valid':
                    names = locations[locale]
                    expected = dict(destination=None, days=[dict(day_index=i,
                        activities=[dict(place_name=name, cancelled=False)]) for i, name in enumerate(names, 1)])
                    lines = row['answer'].splitlines()[1:]
                    assert len(lines) == len(names) and all(name in line for name, line in zip(names, lines, strict=True))
                else:
                    assert row['answer'].endswith(expected_reply)
                assert result.json() == dict(version='LIO-itinerary-preview.1', preview=expected, **query)
                with db.connect(scope) as c:
                    assert c.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                                     (outcome.run_id,)).fetchone()==(True,)
                    assert c.execute('SELECT count(*) FROM cj_run_metered_operation WHERE run_id=%s',
                                     (outcome.run_id,)).fetchone()==(3,)
                    for table in ('cj_trip_record','cj_message_needs_binding','cj_memory_item'):
                        assert c.execute('SELECT count(*) FROM '+table).fetchone()==(0,)
                print(f'{locale} {structured or "legacy"}: visible answer, one discussion, no Trip or Memory write',flush=True)
        assert [entry['state'] for entry in budget.inspect()]==expected_ledger
        structured=None
        for locale,continuation in (
                ('zh',('去成都','三天','成都','你打算玩几天？',
                       '第一天：参观武侯祠。\n第二天：逛锦里。\n第三天：游览人民公园。','第三天')),
                ('en',('Go to Chengdu','Three days','Chengdu','How many days for Chengdu?',
                       'Day 1: Visit Wuhou Shrine.\nDay 2: Explore Jinli.\nDay 3: Walk in People’s Park.','Day 3'))):
            first,followup,city_name,question,plan,daily=continuation
            before=len(seen)
            first_receipt=api.post('/v2/lio/messages',headers=headers,content=encode(dict(
                version='LIO-message.2',message_id=str(uuid4()),locale=locale,text=first,new_conversation=True)))
            assert first_receipt.status_code==200
            cid=first_receipt.json()['conversation_id']
            asked,=worker();assert asked.status=='completed'
            first_row=api.get('/v2/lio/timeline',headers=headers,params={'conversation_id':cid}).json()['messages'][-1]
            assert first_row['answer']==question
            mid=str(uuid4())
            next_receipt=api.post('/v2/lio/messages',headers=headers,content=encode(dict(
                version='LIO-message.2',message_id=mid,locale=locale,text=followup,conversation_id=cid)))
            assert next_receipt.status_code==200
            result,=worker();assert result.status=='completed'
            row=api.get('/v2/lio/timeline',headers=headers,params={'conversation_id':cid}).json()['messages'][-1]
            assert (row['message_id'],row['status'],row['trip'],row['memory'])==(mid,'completed',None,None)
            assert city_name in row['answer'] and daily in row['answer'] and row['answer'].endswith(plan)
            assert seen[before:]==['intake','intake','discussion']
            with db.connect(scope) as c:
                for table in ('cj_trip_record','cj_message_needs_binding','cj_memory_item'):
                    assert c.execute('SELECT count(*) FROM '+table).fetchone()==(0,)
            print(f'{locale}: rejected r06 intake preserves the literal city and day count, no write',flush=True)


if __name__=='__main__':
    with patch.object(projection.harness,'exercise',exercise):
        projection.harness.main()
