"""Fresh signed preview -> sourced follow-up -> one saved version, HTTP fixtures."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
import psycopg
from fastapi.testclient import TestClient
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_api.local_app import ISSUER,LocalDatabase,create_local_app,load_confirmation_signer,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_lio_national import SOURCE_LANGUAGE
from cj_api.real_services import RealServices,RealTools
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_usage.authorization_budget import AuthorizationBudget,DEMO_DEADLINE
from deploy.hk import checkpoint,demo_accounts
from deploy.hk.configuration import Runtime
import dev_auth,migrate,pg_suites,run_worker
from test_lio_city import data as city_catalog
from test_lio_planning_flow import flow

SUBJECT='m4-synthetic-demo-0123456789ab'
KEY='cross-language-fixture-only-key'
CASE=json.loads((Path(__file__).parent/'fixtures/lio982-source-rejection.json').read_bytes())
FIXED_CASE=json.loads((Path(__file__).parent/'fixtures/lio991-duplicate-fixed.json').read_bytes())


def exercise(root,conninfo,*,basic_memory=False,fallback_only=False,max_steps=24,native_mode='buffered'):
    auth=root/'auth';dev_auth.init(auth,[SUBJECT]);now=int(time.time())
    config=root/'connection.json';config.write_text(json.dumps(conninfo))
    meter=root/'meter.json';meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=int(DEMO_DEADLINE.timestamp()),
        max_steps=max_steps,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
    context=load_run_context(meter);database=LocalDatabase(config,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at='2099-01-01T00:00:00Z',profiles={SUBJECT:profile}),
        travel_contexts={SUBJECT:[]}),selections={SUBJECT:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})).encode())
    subjects=frozenset({SUBJECT});scope=scope_for(ISSUER,SUBJECT)
    runtime=Runtime(auth,context,meter,[],memory_runtime=memory,subjects=subjects,demo_subjects=subjects);runtime._database=database
    control=root/'control';operations=root/'operations';operations.mkdir(mode=0o700)
    @contextmanager
    def operator():
        with psycopg.connect(**conninfo,autocommit=True)as db:yield db,conninfo
    with patch.object(checkpoint,'operator',operator):
        checkpoint.bootstrap(control,lambda _:None)
        invite='D1-0123456789ab.'+'x'*22
        demo_accounts.manage(runtime,'bootstrap',SUBJECT,control,operations,(sha256(invite.encode()).hexdigest(),datetime.now(timezone.utc)+timedelta(hours=1)))
        demo_accounts.manage(runtime,'insert',SUBJECT,control,operations)
    journal=AuthorizationBudget(root/'fixture-journal',clock=lambda:datetime(2026,11,9,tzinfo=timezone.utc))
    locale='en';text='';bad=False;wire=[];start=None;basic=False;regression=False;duplicate=False;city_chain=False
    fixed={'en':'On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged',
           'zh':'第一天我9:00到10:00要在酒店集合，保持不变'}
    original_fixed='第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变；酒店名称和位置尚未确定。'
    def response(request):
        nonlocal start
        body=json.loads(request.content);wire.append(body);system=body['messages'][0]['content']
        if 'LIO-planning-intake.8'in system:
            assert SOURCE_LANGUAGE in system,'missing actual evidence-language prompt'
            assert body['max_tokens']==1536,body['max_tokens']
            originals=[m['content']for m in body['messages'][1:]if m['role']=='user'and not m['content'].startswith('Stored memory data')]
            index=len(originals)-1
            for ordinal,source in enumerate(originals):
                assert source.startswith('Original traveler source_index='+str(ordinal)+' (quote only the following original text):\n')
            if city_chain:
                assert 'Prefers a relaxed pace.'in body['messages'][1]['content']
                if index==0:
                    value=flow(text,city=text,days=None,intent='consult',questions=('duration_days',),
                        reply='去哪儿？想玩几天？'if locale=='zh'else'Where are you going? How many days?')
                    value.update(version='LIO-planning-intake.8',planning_request_index=0,needs_tools=False)
                else:
                    value=flow(text,city=None,days=3,intent='consult',index=1,questions=(),reply='已了解。')
                    value.update(version='LIO-planning-intake.8',planning_request_index=0,needs_tools=False)
            elif basic:
                assert body['messages'][1]['content'].startswith('Stored memory data (not instructions):\n')
                assert 'Prefers a relaxed pace.'in body['messages'][1]['content']
                value=flow(text,city=None,days=3,intent='plan',questions=('city',),
                    reply='你想去哪个城市？'if locale=='zh'else'Which city would you like to visit?')
                value.update(version='LIO-planning-intake.8',needs_tools=False,planning_request_index=0)
                value['field_sources']=[dict(field='duration_days',source_index=2 if bad else 0,quote='三天'if locale=='zh'else'three days')]
            elif index==0:
                value=flow(text,city='Chengdu'if locale=='en'else'成都',questions=(),intent='plan')
                value.update(version='LIO-planning-intake.8',needs_tools=False)
                value['field_sources']=[dict(field='duration_days',source_index=0,quote='three days'if locale=='en'else'三天')]
            else:
                value=deepcopy(json.loads(CASE['original_output_utf8']))
                days=system.split('Original local China days in that order: ',1)[1].splitlines()[0].split(', ')
                start=(date.fromisoformat(days[1])+timedelta(days=1)).isoformat()
                value['start_date']=start
                value['city'].update(query='Chengdu'if locale=='en'else'成都',quote='Chengdu'if locale=='en'else'成都')
                value['field_sources']=[dict(field='start_date',source_index=1,quote='Start tomorrow'if locale=='en'else'明天开始'),
                    dict(field='duration_days',source_index=0,quote='three days'if locale=='en'else'三天')]
                item=value['fixed_items'][0]
                item.update(kind='appointment',quote=fixed[locale],label='hotel meetup'if locale=='en'else'酒店集合',
                    start_date=start,end_date=start,start_timezone=None,end_timezone=None)
                if regression:
                    item.update(kind='hotel',quote=original_fixed if locale=='zh'else fixed['en'],
                                start_timezone='Asia/Shanghai',end_timezone='Asia/Shanghai')
                    if locale=='zh':item['unknown_fields']=[] # original r09 intake: absent place, not a claimed name
                if bad:value['city'].update(query='成都',quote='成都')
        elif 'MEMORY-EXTRACT@2'in system:
            value=dict(version='MEMORY-EXTRACT@2',entries=[])
        elif body.get('tools'):
            value=('我可以先帮你梳理这三天的方向。你想去哪个城市？'if locale=='zh'else
                   'I can help shape those three days. Which city would you like to visit?')
        elif 'The traveler requested a complete 'in system:
            value=dict(answer=('Day 1: a neighborhood. Day 2: a museum. Day 3: a park. Which day should we adjust?'
                if locale=='en'else'第1天逛街区，第2天看博物馆，第3天去公园。你想先调整哪一天？'))
        else:
            original=json.loads(body['messages'][-1]['content'])
            assert original['version']=='TRIP-source-input.2'
            assert original['fields']['party_size']['state']!='known'
            assert len(original['fields']['fixed_items'])==1
            original_item=original['fields']['fixed_items'][0]
            if regression:
                assert 'including on a first plan'in system
                assert 'Return only NEW suggested stops'in system
                assert json.dumps([original_item['item_id']],separators=(',',':'))in system
            days=[]
            for n in range(3):
                day=(date.fromisoformat(start)+timedelta(days=n)).isoformat()
                rows=[]if n==0 else [[f'am-{n}','Museum（博物馆）','09:00','11:00',['self']]]
                rows.append([f'pm-{n}','Park（公园）','14:00','16:00',['self']]);days.append([day,rows])
            value=dict(version='TRIP-lio-first-plan.2',title='Chengdu（成都）',days=days)
            if regression:
                value=json.loads(FIXED_CASE['draft_utf8'])
                for index,day in enumerate(value['days']):
                    day[0]=(date.fromisoformat(start)+timedelta(days=index)).isoformat()
                if duplicate:value['days'][0][1][0][0]=original_item['item_id']
                else:value['days'][0][1].pop(0) # compliant fixture, never server-side repair
        identity=dict(id='cross-language-fixture-'+str(len(wire)),model=M4_MODEL)
        content=value if type(value)is str else json.dumps(value,ensure_ascii=False)
        if body.get('tools')and native_mode=='compact':
            from cj_agent.provider import M4_TURN_FUNCTION_V2
            assert body['tools'][0]['function']['name']==M4_TURN_FUNCTION_V2
            arguments=json.dumps(dict(answer=dict(zh='我可以帮你梳理三天的旅行。想去哪个城市？',
                en='I can help shape those three days. Which city would you like to visit?')),ensure_ascii=False)
            delta=dict(tool_calls=[dict(index=0,id='fixture-turn',type='function',
                function=dict(name=M4_TURN_FUNCTION_V2,arguments=arguments))])
            finish='tool_calls'
        else:delta=dict(content=content);finish='stop'
        frames=[dict(**identity,choices=[dict(index=0,delta=delta,finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason=finish)]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))]
        raw=''.join('data: '+json.dumps(frame)+'\n\n'for frame in frames)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY,max_output_tokens=1536),journal,transport=httpx.MockTransport(response))
    services=RealServices(model,KEY,subjects,demo_subjects=subjects,national_subjects=subjects)
    tools=RealTools(services,buffered_streaming_subjects=subjects if native_mode=='buffered'else frozenset(),
        assembly_streaming_subjects=subjects if native_mode=='stream'else frozenset())
    signer=load_confirmation_signer(auth)
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,
        confirmation_signer=signer,demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects)
    if basic_memory:
        from cj_memory.typed_api import register_typed_routes
        from cj_api.local_lio_memory import pilot_write_configuration
        register_typed_routes(app,database=database,auth_dir=auth,
                              configuration=pilot_write_configuration(memory.collection,subjects))
    headers={'Authorization':'Bearer '+dev_auth.token(auth,SUBJECT,3600),'Content-Type':'application/octet-stream'}
    async def catalogue(key,guard):assert key==KEY and guard()is True;return city_catalog()
    with TestClient(app)as api,patch('cj_api.lio_city._catalog_exchange',side_effect=catalogue):
        if basic_memory:
            seed=dict(version='MEMORY-manual.2',operation_id='basic-memory-setup',item_id='basic-memory-pace',
                subject='self',slot='travel.pace',kind='preference',text='Prefers a relaxed pace.',extent='long_term',
                context=None,occurred_at='synthetic local regression')
            seeded=api.post('/v2/memories',headers=headers,content=json.dumps(seed,separators=(',',':')).encode())
            assert seeded.status_code==200,seeded.text
            assert seeded.json()['receipt']['status']=='active'
            seed_receipt=api.get('/v2/memory-receipts',headers=headers,params=dict(operation_id=seed['operation_id']))
            assert seed_receipt.status_code==200 and seed_receipt.json()['receipt']==seeded.json()['receipt']
            cases=(
                    ('zh-capability','zh','你能做啥',False),('en-capability','en','What can you do?',False),
                    ('zh-days','zh','三天怎么玩',False),('en-days','en','How should I spend three days?',False),
                    ('zh-model','zh','帮我规划三天的旅行',False),('en-model','en','Please help me plan for three days',False),
                    ('bad-offset','zh','帮我规划三天的旅行',True))
            if fallback_only:
                cases=(('bad-offset-zh','zh','帮我规划三天的旅行',True),
                       ('bad-offset-en','en','Please help me plan for three days',True))
            for label,language,question,invalid in cases:
                locale=language;text=question;basic=True;bad=invalid
                before=len(wire);before_attempts=len(journal.inspect());mid='basic-'+label
                sent=api.post('/v2/lio/messages',headers=headers,content=json.dumps(dict(version='LIO-message.2',
                    message_id=mid,text=text,locale=locale,new_conversation=True),ensure_ascii=False).encode())
                assert sent.status_code==200,sent.text
                cid=sent.json()['conversation_id']
                outcome,=run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
                    memory_configuration_for_scope=lambda owner:memory if owner==scope else None,account_admission=True,
                    hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
                denied=bad and max_steps==1
                assert outcome.status==('failed'if denied else'completed'),outcome
                timeline=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=cid)).json()
                message,=timeline['messages']
                if bad:
                    attempts=journal.inspect()[before_attempts:]
                    assert message['status']==('failed'if denied else'completed')
                    assert len(wire)==before+(1 if denied else 3) # intake, real generic path, existing Memory extraction
                    assert len(attempts)==(1 if denied else 3)and all(row['state']=='RECEIVED'for row in attempts)
                    assert len({row['attempt_id']for row in attempts})==len(attempts)
                    assert (not message['answer'])if denied else('三天'in message['answer']if locale=='zh'else'three days'in message['answer'])
                    with database.connect(scope)as db:
                        rows=db.execute('SELECT kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',
                                        (scope,outcome.run_id)).fetchall()
                        assert db.execute('SELECT count(*)FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',
                                          (scope,mid)).fetchone()[0]==0
                    saved=json.loads(next(v.split(':',1)[1]for _,v in rows if v.startswith('lio_planning_context.1:')))
                    assert saved['authority']=='none'and saved['facts']=={}and saved['authority_barrier_message_id']==mid
                    if denied:assert ('budget_denied','answer')in rows
                else:
                    assert message['status']=='completed'and message['answer']
                    if 'capability'in label or label.endswith('-days'):assert len(wire)==before # code clarification, never model-health evidence
                    else:
                        assert len(wire)==before+1
                    if 'capability'not in label:
                        with database.connect(scope)as db:
                            row=db.execute("SELECT value FROM cj_run_event WHERE scope=%s AND run_id=%s AND value LIKE 'lio_planning_context.1:%%'",
                                           (scope,outcome.run_id)).fetchone()
                        saved=json.loads(row[0].split(':',1)[1]);assert saved['facts']['duration_days']['value']==3
                current=api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=cid)).json()
                assert current['current']is None
                print(json.dumps(dict(case=label,mid=mid,cid=cid,run=outcome.run_id,status=outcome.status,
                    supplier_dispatches=len(wire)-before,budget_denied=denied,
                    memory='actual native active source')),flush=True)
            basic=False;bad=False
            if not fallback_only:
                city_chain=True
                for locale,phrases in (('zh',('去成都','三天')),('en',('Go to Chengdu','Three days'))):
                    cid=None
                    for index,text in enumerate(phrases):
                        mid='literal-city-'+locale+'-'+str(index)
                        request=dict(version='LIO-message.2',message_id=mid,text=text,locale=locale,
                            **({'conversation_id':cid}if cid else{'new_conversation':True}))
                        before=len(wire)
                        sent=api.post('/v2/lio/messages',headers=headers,content=json.dumps(request,ensure_ascii=False).encode())
                        assert sent.status_code==200,sent.text;cid=sent.json()['conversation_id']
                        outcome,=run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
                            memory_configuration_for_scope=lambda owner:memory if owner==scope else None,
                            account_admission=True,hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
                        assert outcome.status=='completed',outcome
                        message=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=cid)).json()['messages'][-1]
                        with database.connect(scope)as db:
                            effect=db.execute("SELECT value FROM cj_run_event WHERE scope=%s AND run_id=%s AND value LIKE 'lio_planning_context.1:%%' ORDER BY sequence DESC LIMIT 1",(scope,outcome.run_id)).fetchone()
                        saved=json.loads(effect[0].split(':',1)[1])
                        if index==0:
                            assert saved['status']=='needs_details'and saved['authority']=='none'
                            assert saved['facts']['city']['value']['query']==('成都'if locale=='zh'else'Chengdu')
                            assert message['answer']==('你打算玩几天？'if locale=='zh'else'For how many days?')
                            assert len(wire)==before+1
                        else:
                            assert saved['status']=='plan_preview'and saved['facts']['duration_days']['value']==3
                            for day in range(1,4):assert ('第'+str(day)+'天'if locale=='zh'else'Day '+str(day))in message['answer']
                            assert len(wire)==before+2
                        assert api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=cid)).json()['current']is None
                        print(json.dumps(dict(case='literal-city-duration',locale=locale,mid=mid,cid=cid,run=outcome.run_id,
                            status=outcome.status,planning_status=saved['status'],model_calls=len(wire)-before,
                            memory='actual native active source')),flush=True)
                city_chain=False
        plan_cases=()if fallback_only else(('en','en',False),('zh','zh',False),('translated','en',True),
                ('r09-zh','zh',False),('r09-en','en',False),('r09-duplicate','zh',False))
        for label,language,invalid in plan_cases:
            locale=language;bad=invalid;cid=None;regression=label.startswith('r09');duplicate=label=='r09-duplicate'
            texts=(CASE['turns']if locale=='en'else('我想去成都玩三天。','明天开始。'+fixed['zh']+'。酒店名称和位置尚未确定。不要声称已经预订。'))
            if regression and locale=='zh':
                texts=('去成都玩三天','从明天开始。 '+original_fixed+'请给每天的上午、下午安排写出计划时间段，不要声称已有预约。')
            for index,text in enumerate(texts):
                mid='cross-'+label+'-'+str(index)
                sent=api.post('/v2/lio/messages',headers=headers,content=json.dumps(dict(version='LIO-message.2',message_id=mid,
                    text=text,locale=locale,**({'conversation_id':cid}if cid else{'new_conversation':True})),ensure_ascii=False).encode())
                assert sent.status_code==200,sent.text;cid=sent.json()['conversation_id']
                outcome,=run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
                    memory_configuration_for_scope=lambda owner:memory if owner==scope else None,account_admission=True,
                    hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
                expected='completed'
                assert outcome.status==expected,outcome
                current=api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=cid)).json()
                if index==0 or bad or duplicate:
                    assert current['current']is None
                    if duplicate and index==1:
                        timeline=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=cid)).json()
                        assert timeline['messages'][-1]['status']=='failed',timeline
                else:
                    card=current['current'];assert card is not None and current['history']==[],current
                    assert [day['date']for day in card['days']]==[(date.fromisoformat(start)+timedelta(days=n)).isoformat()for n in range(3)]
                    event,=[item for day in card['days']for item in day['items']if item['fixed']]
                    assert (event['start_time'],event['end_time'])==('09:00','10:00')
                    with database.connect(scope)as db:
                        assert db.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(card['trip_id'],)).fetchone()==(1,)
                        row=db.execute('SELECT content FROM cj_needs_revision n JOIN cj_message_needs_binding b '
                            'ON(n.scope,n.needs_id,n.version)=(b.needs_scope,b.needs_id,b.needs_version) '
                            'WHERE b.message_scope=%s AND b.message_id=%s',(scope,mid)).fetchone()
                    fields=json.loads(bytes(row[0]));assert fields['party_size']['state']!='known'
                    meeting,=fields['fixed_items'];assert meeting['applies_to']==['self']
                    assert meeting['booking_status']['state']!='known'
                    expected_place='missing'if regression and locale=='zh'else'unknown'
                    assert meeting['start']['place']['state']==expected_place and meeting['end']['place']['state']==expected_place
                print(json.dumps(dict(mid=mid,cid=cid,run=outcome.run_id,status=outcome.status)),flush=True)
            if bad:
                with database.connect(scope)as db:
                    assert db.execute('SELECT count(*)FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',(scope,mid)).fetchone()[0]==0
        with database.connect(scope)as db:assert db.execute('SELECT count(*)FROM cj_memory_item').fetchone()[0]==(1 if basic_memory else 0)
        if basic_memory:
            detail=api.get('/v2/memory-items',headers=headers,params=dict(item_id='basic-memory-pace')).json()['item']
            assert detail['status']=='active'and detail['version']==1
            assert detail['command']['text']==seed['text']and detail['command']['slot']=='travel.pace'
    print('PASS signed ZH/EN strict rejected intake -> charged generic/Memory path or pre-dispatch budget denial, zero NEEDS/Trip; valid plan/fixed-ID guards retained; HTTP fixtures only',flush=True)


def main(*,basic_memory=False,fallback_only=False,max_steps=24,native_mode='buffered'):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
    import base64
    with tempfile.TemporaryDirectory(prefix='g2c-cross-source-')as folder:
        root=Path(folder)
        with pg_suites.cluster('cross-source',port=55659,role='cj_cross_source_initializer',root=root/'pg',socket=root/'s')as conninfo:
            with psycopg.connect(**conninfo,autocommit=True)as db:
                versions=migrate.load();migrate.up(db,versions,versions[-1]['version'])
            key=Ed25519PrivateKey.generate()
            env=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
                CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',CJ_BETA_DEMO_SUBJECTS_JSON=json.dumps([SUBJECT]),
                CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
                CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
            with patch.dict(os.environ,env):exercise(root,conninfo,basic_memory=basic_memory,
                fallback_only=fallback_only,max_steps=max_steps,native_mode=native_mode)


if __name__=='__main__':main()
