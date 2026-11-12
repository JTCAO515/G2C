"""Signed private PG nationwide chain; only HTTP supplier fixtures, never HK proof."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone,date
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
import psycopg
from fastapi.testclient import TestClient
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_api.local_app import ISSUER,LocalDatabase,create_local_app,load_confirmation_signer,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.real_services import RealServices,RealTools
from cj_api.lio_city import fetch_catalog
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_usage.authorization_budget import AuthorizationBudget,DEMO_DEADLINE
from deploy.hk import checkpoint,demo_accounts
from deploy.hk.configuration import Runtime
import dev_auth,local_run_context,migrate,pg_suites
import run_worker
from test_lio_city import data as city_catalog

SUBJECT='m4-synthetic-demo-0123456789ab'
CITIES=(('上海','Shanghai','310000'),('成都','Chengdu','510100'),('西安',"Xi'an",'610100'),
        ('桂林','Guilin','450300'),('广州','Guangzhou','440100'),('杭州','Hangzhou','330100'))
KEY='national-http-fixture-key-only'
PREFERENCE='I prefer fewer stops in a day.'
MISSING_REQUESTS={'去成都玩三天':('zh','成都','三天'), 'Plan a three-day trip to Chengdu.':('en','Chengdu','three-day')}
CHENGDU_CASE=json.loads((ROOT/'eval/lio_national_cases.v1.json').read_bytes())['cases'][0]
FIXED_TEXT={'zh':'第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变',
    'en':'On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged'}
QUOTED_REQUESTS={'zh':'请把“从2026-11-20开始，两个人”翻译成英文。',
    'en':'Please translate \"Starting 2026-11-20, two people\" into Chinese.'}
PARTY_REPLY={'zh':'只有我一人，酒店集合也只有我本人参加。','en':'It is just me; the hotel meetup is also only for me.'}
DISCUSSION_REQUESTS={
    '想去杭州玩两天，日期和人数还没确定，先聊聊不要保存。':('zh','杭州','想去杭州玩两天'),
    'I would like to visit Hangzhou for two days; dates and party size are undecided. Just discuss, do not save.':
        ('en','Hangzhou','visit Hangzhou for two days')}


def exercise(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,[SUBJECT])
    config=root/'connection.json';config.write_text(json.dumps(conninfo));now=int(time.time())
    meter=root/'meter.json';meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=int(DEMO_DEADLINE.timestamp()),
        max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=12000)),history=[])))
    context=load_run_context(meter);database=LocalDatabase(config,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at='2099-01-01T00:00:00Z',profiles={SUBJECT:profile}),travel_contexts={SUBJECT:[]})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=policy,
        selections={SUBJECT:dict(subject='self',slots=['travel.pace'],max_bytes=1000)})).encode())
    runtime=Runtime(auth,context,meter,[],memory_runtime=memory,subjects=frozenset({SUBJECT}),demo_subjects=frozenset({SUBJECT}));runtime._database=database
    control=root/'control';operation=root/'operations';operation.mkdir(mode=0o700)
    @contextmanager
    def operator():
        with psycopg.connect(**conninfo,autocommit=True) as connection:yield connection,conninfo
    with patch.object(checkpoint,'operator',operator):
        checkpoint.bootstrap(control,lambda _:None)
        invite='D1-0123456789ab.'+'x'*22
        demo_accounts.manage(runtime,'bootstrap',SUBJECT,control,operation,
            (hashlib.sha256(invite.encode()).hexdigest(),datetime.now(timezone.utc)+timedelta(hours=1)))
        demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)
    scope=scope_for(ISSUER,SUBJECT);subjects=frozenset({SUBJECT})
    journal=AuthorizationBudget(root/'original-journal',clock=lambda:datetime(2026,11,9,tzinfo=timezone.utc))
    current={};wire=[];city_calls=[]
    def response(request):
        assert str(request.url)==M4_BASE+'/chat/completions'
        body=json.loads(request.content);wire.append(body);system=body['messages'][0]['content']
        if body.get('tools'):
            # Identity is answered only with the actual saved Memory selection.
            visible=json.dumps(body['messages'],ensure_ascii=False)
            has_saved=PREFERENCE in visible
            assert has_saved==current['saved_memory']
            assert 'Use only saved memory' in system
            if current['identity_locale']=='zh':
                content='你曾分享过，旅行时喜欢每天少安排几个地方。' if has_saved else '我还不了解你，愿意介绍一下自己吗？'
            else:
                content=('You have shared that you prefer fewer stops in a day.' if has_saved else
                         "I don't know you yet. Would you like to introduce yourself?")
        elif 'LIO-planning-intake.8' in system:
            text=body['messages'][-1]['content'];current['text']=text
            source_index=len([m for m in body['messages'][1:] if m['role']=='user' and not m['content'].startswith('Stored memory data')])-1
            from cj_agent.lio_intake_optional_schema import response_format
            assert body['response_format']==response_format(source_index)
            if text in QUOTED_REQUESTS.values() or current.get('quoted_replay') and text in ('继续','Please continue.'):
                from test_lio_planning_flow import flow as flow_fixture
                quoted=text in QUOTED_REQUESTS.values()
                if quoted:current['quoted_source_index']=source_index
                data=flow_fixture(text,city=None,days=None,start='2026-11-20',party=2,index=source_index,
                                  questions=('start_date',),reply='Starting 2026-11-20, two people.')
                data.update(version='LIO-planning-intake.8',intent='consult',needs_tools=False,
                            planning_request_index=None if quoted else 0)
                evidence_index=source_index if quoted else current['quoted_source_index']
                data['field_sources']=[dict(field=field,source_index=evidence_index,quote=QUOTED_REQUESTS[current['locale']])
                                      for field in ('start_date','party_size')]
                content=json.dumps(data,ensure_ascii=False)
            elif current.get('clarification_flow'):
                flow=CHENGDU_CASE['variants'][current['locale']]['turns'];fields={'party_size':dict(state='missing'),'fixed_items':[]}
                sources={'duration_days':[dict(source_index=0,quote='三天' if current['locale']=='zh' else 'three days')]}
                start=dict(state='missing')
                if source_index:
                    days=system.split('Original local China days in that order: ',1)[1].splitlines()[0].split(', ')
                    first=(date.fromisoformat(days[1])+timedelta(days=1)).isoformat();current['start_date']=first
                    start=dict(state='known',value=first)
                    sources['start_date']=[dict(source_index=1,quote='从明天开始' if current['locale']=='zh' else 'Start tomorrow')]
                    def fixed_event(clock):return dict(date=dict(state='known',value=first),time=dict(state='known',value=clock),timezone=dict(state='missing'),place=dict(state='missing'))
                    item=dict(item_id='hotel',kind='appointment',label='酒店集合' if current['locale']=='zh' else 'hotel meetup',
                        source_ref=dict(source_index=1,quote=FIXED_TEXT[current['locale']]),detail_refs=[],
                        applies_to=['self'],locked=dict(state='known',value=True),booking_status=dict(state='missing'),
                        start=fixed_event('09:00'),end=fixed_event('10:00'))
                    fields['fixed_items']=[item]
                    if source_index==2:
                        fields['party_size']=dict(state='known',value=1)
                        sources['party_size']=[dict(source_index=2,quote=PARTY_REPLY[current['locale']])]
                        item['detail_refs']=[dict(source_index=2,quote=PARTY_REPLY[current['locale']])]
                content=json.dumps(dict(version='LIO-planning-intake.4',intent='plan',reply='I will retain the supplied facts.',needs_tools=False,
                    city=dict(query=current['mention'],normalized_name=None,province=None,source_index=0,quote=flow[0]),
                    duration_days=3,start_date=start,extraction=dict(version='LIO-execution-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
                    field_sources=sources,current_source_index=source_index),ensure_ascii=False)
            elif text in DISCUSSION_REQUESTS or text in ('继续','Please continue.') and current['missing_question'] in DISCUSSION_REQUESTS:
                _,mention,quote=DISCUSSION_REQUESTS[text if text in DISCUSSION_REQUESTS else current['missing_question']]
                content=json.dumps(dict(version='LIO-planning-intake.4',intent='discuss',reply='可以先讨论，不保存。',needs_tools=False,
                    city=dict(query=mention,normalized_name=None,province=None,source_index=0,quote=quote),duration_days=None,
                    extraction=None,field_sources={},current_source_index=source_index),ensure_ascii=False)
            elif text in MISSING_REQUESTS or text in ('继续','Please continue.'):
                _,mention,duration=MISSING_REQUESTS[text if text in MISSING_REQUESTS else current['missing_question']]
                evidence_index=source_index if text in MISSING_REQUESTS else 0
                content=json.dumps(dict(version='LIO-planning-intake.4',intent='plan',reply='请补充日期和人数。',needs_tools=False,
                    city=dict(query=mention,normalized_name=None,province=None,source_index=evidence_index,quote=mention),duration_days=3,
                    extraction=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[]),
                    field_sources={'duration_days':[dict(source_index=evidence_index,quote=duration)]},current_source_index=source_index),ensure_ascii=False)
            elif text==PREFERENCE:
                content=json.dumps(dict(version='LIO-planning-intake.4',intent='consult',reply='I can suggest a relaxed pace.',needs_tools=False,
                    city=None,duration_days=None,extraction=None,
                    field_sources={},current_source_index=source_index))
            else:
                content=None
            requested_start=current.get('requested_start','2026-11-20')
            fields=dict(arrival=dict(date=dict(state='known',value=requested_start),time=dict(state='missing'),timezone=dict(state='missing'),place=dict(state='missing')),party_size=dict(state='known',value=2))
            sources={k:[dict(source_index=source_index,quote=q)] for k,q in (
                ('arrival.date',requested_start),('party_size',current['party']),('duration_days',current['duration']))}
            if current.get('fixed_description') in text:
                def event(clock):
                    return dict(date=dict(state='known',value='2026-11-20'),time=dict(state='known',value=clock),
                        timezone=dict(state='known',value='Asia/Shanghai'),place=dict(state='missing'))
                fields['fixed_items']=[dict(item_id='hotel',kind='appointment',description=current['fixed_description'],
                    applies_to=['self'],locked=dict(state='known',value=True),booking_status=dict(state='unknown'),
                    start=event('09:00'),end=event('10:00'))]
                sources['fixed_items']=[dict(source_index=source_index,quote=current['fixed_description'])]
            content=content or json.dumps(dict(version='LIO-planning-intake.4',intent='plan',reply='I can arrange the trip.',needs_tools=False,
                city=dict(query=current['mention'],normalized_name=None,province=None,source_index=source_index,quote=current['mention']),
                duration_days=3,extraction=dict(version='NEEDS-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
                field_sources=sources,current_source_index=source_index),ensure_ascii=False)
        elif 'The traveler requested a complete ' in system:
            count=int(re.search(r'The traveler requested a complete ([0-9]+)-day',system)[1])
            assert not body.get('tools')
            content=json.dumps(dict(answer=('；'.join('第'+str(n)+'天：'+current['zh']+'街区散步' for n in range(1,count+1))+'。想先调整哪一天？'
                if current['locale']=='zh' else '\n'.join('Day '+str(n)+': '+current['en']+' neighborhood walk.' for n in range(1,count+1))+' Which day would you like to adjust?')),ensure_ascii=False)
        elif 'MEMORY-EXTRACT@2' in system:
            entries=[]
            source=json.loads(body['messages'][-1]['content'])['messages']
            for original in source:
                if original['text']==PREFERENCE:
                    entries.append(dict(subject='self',slot='travel.pace',kind='preference',text=PREFERENCE,extent='long_term',
                        occurred_at='date unknown',evidence=[dict(ref=original['ref'],quote=PREFERENCE)]))
            content=json.dumps(dict(version='MEMORY-EXTRACT@2',entries=entries))
        else:
            original=json.loads(body['messages'][-1]['content'])
            assert original['version']=='TRIP-source-input.2'
            assert original['fields']['arrival']['place']['value']==current['zh']+'市'
            assert original['fields']['destination_timezone']['value']=='Asia/Shanghai'
            items=[dict(id='visit-'+str(i),text=(current['zh']+'散步'+str(i) if current['locale']=='zh' else current['en']+' Walk '+str(i)),date=(date.fromisoformat(current.get('start_date','2026-11-20'))+timedelta(days=i-1)).isoformat(),
                start_time='19:00' if i==3 else '14:00',end_time='20:00' if i==3 else '15:00',timezone='Asia/Shanghai') for i in (1,2,3)]
            if original['current_trip'] is not None:
                content=json.dumps(dict(version='TRIP-lio-replan-delta.3',items=[],proposed_subjects={}))
            else:
                content=json.dumps(dict(version='TRIP-lio-first-plan.1',title=current['en']+' trip',items=items,
                    proposed_subjects={item['id']:['party'] for item in items}),ensure_ascii=False)
        if 'LIO-planning-intake.8' in system:
            data=json.loads(content)
            if 'start_date' not in data:
                if data['intent'] in ('consult','discuss','cancel'):data['start_date']=None
                else:
                    data['start_date']=data['extraction']['fields'].get('arrival',{}).get('date',dict(state='missing'))
                    if data['start_date']['state']=='known':data['field_sources']['start_date']=data['field_sources']['arrival.date']
                    data['extraction']['version']='LIO-execution-extraction.1'
                    data['extraction']['fields'].setdefault('party_size',dict(state='missing'))
                    data['extraction']['fields'].setdefault('fixed_items',[])
                    for fixed in data['extraction']['fields'].get('fixed_items',[]):
                        original=fixed.pop('description')
                        fixed.update(label='酒店集合' if current['locale']=='zh' else 'hotel meetup',
                            source_ref=next(ref for ref in data['field_sources']['fixed_items'] if ref['quote']==original),detail_refs=[])
                        for edge in ('start','end'):fixed[edge]['timezone']=dict(state='missing')
                content=json.dumps(data,ensure_ascii=False)
            from lio_flat_fixture import facts_fixture
            decoded=json.loads(content)
            if decoded['version']=='LIO-planning-intake.8':
                flow=decoded
            else:
                flow=facts_fixture(decoded)
                flow.update(version='LIO-planning-intake.8',question_fields=[],publication_hold=None,
                    planning_request_index=source_index if flow['intent']in ('plan','save')else None)
            content=json.dumps(flow,ensure_ascii=False)
            from jsonschema import Draft202012Validator
            Draft202012Validator(body['response_format']['json_schema']['schema']).validate(json.loads(content))
        identity=dict(id='fixture-national-'+str(len(wire)),model=M4_MODEL)
        events=[dict(**identity,choices=[dict(index=0,delta=dict(content=content),finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))]
        raw=''.join('data: '+json.dumps(e)+'\n\n' for e in events)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    async def city_exchange(key,guard):
        assert key==KEY and guard() is True
        city_calls.append('original district exchange')
        return city_catalog()
    def fixture_exchange(request):
        try:return response(request)
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),journal,transport=httpx.MockTransport(fixture_exchange))
    services=RealServices(model,KEY,subjects,demo_subjects=subjects,national_subjects=subjects)
    tools=RealTools(services,buffered_streaming_subjects=subjects)
    signer=load_confirmation_signer(auth)
    def process():
        return run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
            memory_configuration_for_scope=lambda owner:memory if owner==scope else None,
            account_admission=True,hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
    from cj_api.lio_memory_routes import LioMemoryCards
    from cj_api.local_lio_memory import lio_candidates
    from cj_memory.typed_api import register_typed_routes
    def memory_host(boundary):
        candidates=lio_candidates(database,boundary,subjects,memory.collection)
        return LioMemoryCards(candidates.collection,candidates.current)
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,
        confirmation_signer=signer,demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects,lio_memory_factory=memory_host)
    register_typed_routes(app,database=database,auth_dir=auth,configuration=memory.collection)
    headers={'Authorization':'Bearer '+dev_auth.token(auth,SUBJECT,3600),'Content-Type':'application/octet-stream'}
    with TestClient(app) as api,patch('cj_api.lio_city._catalog_exchange',side_effect=city_exchange):
        for index,(question,(locale,mention,duration)) in enumerate({**MISSING_REQUESTS,**DISCUSSION_REQUESTS}.items()):
            discussing=question in DISCUSSION_REQUESTS
            current.update(zh='杭州' if discussing else '成都',en='Hangzhou' if discussing else 'Chengdu',locale=locale,mention=mention,party='两个人',duration=duration,fixed_description='not-present',missing_question=question)
            mid='missing-original-'+str(index)
            clarification_request=dict(version='LIO-message.2',message_id=mid,text=question,locale=locale,new_conversation=True)
            accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(clarification_request).encode());assert accepted.status_code==200,accepted.text
            assert [(o.message_id,o.status) for o in process()]==[(mid,'completed')]
            rows=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=accepted.json()['conversation_id'])).json()['messages']
            assert rows[-1]['trip'] is None and rows[-1]['status']=='completed' and rows[-1]['answer']
            continuation=dict(version='LIO-message.2',message_id=mid+'-continue',locale=locale,
                text='继续' if locale=='zh' else 'Please continue.',conversation_id=accepted.json()['conversation_id'])
            followed=api.post('/v2/lio/messages',headers=headers,content=json.dumps(continuation).encode());assert followed.status_code==200,followed.text
            assert [(o.message_id,o.status) for o in process()]==[(mid+'-continue','completed')]
            rows=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=accepted.json()['conversation_id'])).json()['messages']
            assert len(rows)==2 and all(row['trip'] is None and row['status']=='completed' and row['answer'] for row in rows)
            with database.connect(scope) as db:
                assert db.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=ANY(%s)',(scope,[mid,mid+'-continue'])).fetchone()==(0,)
                assert db.execute('SELECT count(*) FROM cj_trip_record').fetchone()==(0,)
                assert db.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
                if discussing:
                    contexts=db.execute("SELECT value FROM cj_run_event WHERE scope=%s AND kind='effect_committed' AND value LIKE 'lio_planning_context.1:%%' AND run_id IN (SELECT run_id FROM cj_message_receipt WHERE scope=%s AND message_id=ANY(%s))",(scope,scope,[mid,mid+'-continue'])).fetchall()
                    assert len(contexts)==2 and all(json.loads(value.removeprefix('lio_planning_context.1:'))['authority']=='none' for value, in contexts)
            if not discussing:
                for quoted in (True,False):
                    current['quoted_replay']=not quoted
                    hostile=dict(version='LIO-message.2',message_id=mid+('-quote' if quoted else '-replay'),locale=locale,
                        conversation_id=accepted.json()['conversation_id'],text=QUOTED_REQUESTS[locale] if quoted else continuation['text'])
                    received=api.post('/v2/lio/messages',headers=headers,content=json.dumps(hostile).encode())
                    assert received.status_code==200,received.text
                    assert [(o.message_id,o.status)for o in process()]==[(hostile['message_id'],'completed')]
                    timeline=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=accepted.json()['conversation_id'])).json()
                    last=timeline['messages'][-1]
                    assert last['trip']is None and last['status']=='completed'
                    if not quoted:assert '2026-11-20' not in last['answer']
                    with database.connect(scope)as db:
                        assert db.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',
                            (scope,hostile['message_id'])).fetchone()==(0,)
                        assert db.execute('SELECT count(*) FROM cj_trip_record').fetchone()==(0,)
                current.pop('quoted_replay');current.pop('quoted_source_index')
                print('PASS signed translation+misreported question cannot publish or replay its facts',locale,flush=True)
            print('PASS signed clarification/discussion and current-source continuation, zero NEEDS/Trip/active Memory',locale,'discussion' if discussing else 'missing',flush=True)
        for zh,en,adcode in CITIES:
            for locale in ('zh','en'):
                current.update(zh=zh,en=en,locale=locale,mention=zh if locale=='zh' else en,
                    fixed_description=('第一天我9:00–10:00要在酒店集合，这项安排已确定，保持不变' if locale=='zh' else
                        'On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged'),
                    party='两个人' if locale=='zh' else 'two people',duration='三天' if locale=='zh' else 'three-day')
                text=(f'计划{zh}三天豪华游，从2026-11-20开始，两个人。' if locale=='zh' else
                      f'Plan a three-day trip to {en} for two people starting 2026-11-20.')
                text+=current['fixed_description']+('。酒店名称和位置尚未确定。' if locale=='zh' else '. The hotel name and location are not known yet.')
                mid='nation-'+adcode+'-'+locale
                payload=dict(version='LIO-message.2',message_id=mid,text=text,locale=locale,new_conversation=True)
                accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(payload).encode())
                assert accepted.status_code==200,accepted.text
                cid=accepted.json()['conversation_id'];params={'conversation_id':cid}
                outcomes=process();assert [(o.message_id,o.status) for o in outcomes]==[(mid,'completed')],outcomes
                saved=api.get('/v2/lio/trip',params=params,headers=headers).json();assert saved['current'] is not None and saved['history']==[],saved
                initial=saved['current'];assert initial['days'][0]['date']=='2026-11-20',initial
                fixed,=[item for day in initial['days'] for item in day['items'] if item['fixed']]
                assert fixed['label']==current['fixed_description'] and (fixed['start_time'],fixed['end_time'])==('09:00','10:00')
                with database.connect(scope) as db:
                    initial_content=bytes(db.execute('SELECT content FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()[0])
                # Consume the exact unchanged public C template with actual
                # returned name/day/time, rather than simplifying its request.
                target=initial['days'][1]['items'][0]
                flow=json.loads((ROOT/'eval/lio_national_cases.v1.json').read_bytes())['common_flow'][2]
                edit=dict(version='LIO-message.2',message_id=mid+'-edit',conversation_id=cid,locale=locale,
                    text=flow[locale].format(actual_item_name=target['label'],
                        actual_time_range=target['start_time']+'–'+target['end_time'],
                        replacement_query='人民公园' if locale=='zh' else 'Riverside Park'))
                changed=api.post('/v2/lio/messages',headers=headers,content=json.dumps(edit).encode());assert changed.status_code==200,changed.text
                outcomes=process();assert [(o.message_id,o.status) for o in outcomes]==[(mid+'-edit','completed')],outcomes
                after=api.get('/v2/lio/trip',params=params,headers=headers).json();assert after['current']!=initial and after['history']==[initial],after
                command=dict(version='LIO-trip-undo.2',action_id=mid+'-undo',conversation_id=cid,target=after['undo_target'])
                undone=api.post('/v2/lio/trip/undo',headers=headers,content=json.dumps(command).encode());assert undone.status_code==200,undone.text
                final=api.get('/v2/lio/trip',params=params,headers=headers).json();assert final['current'] is not None,final
                assert final['current']['days']==initial['days'] and len(final['history'])==2
                with database.connect(scope) as db:
                    record=db.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()
                    assert record[0]==3 and bytes(record[1])==initial_content
                    rows=db.execute('SELECT committed_version FROM cj_trip_receipt WHERE trip_id=%s ORDER BY committed_version',(initial['trip_id'],)).fetchall()
                    assert rows==[(1,),(2,),(3,)],rows
                replay=api.post('/v2/lio/messages',headers=headers,content=json.dumps(payload).encode());assert replay.json()==accepted.json()
                assert process()==[]
                print('PASS signed fixture national plan/save/edit/undo',adcode,locale,flush=True)
        # Replanning the same destination reads the original adcode after an
        # edit and native undo; changing city never rewrites that Trip/NEEDS.
        payload=dict(payload,message_id='national-replan',new_conversation=False,conversation_id=cid)
        payload.pop('new_conversation')
        accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(payload).encode());assert accepted.status_code==200,accepted.text
        assert [o.status for o in process()]==['completed']
        after_replan=api.get('/v2/lio/trip',params=params,headers=headers).json()
        assert after_replan['current']['days']==initial['days'] and len(after_replan['history'])==3
        from cj_message.lio_plan_needs import lio_needs_id
        from cj_api.local_needs import protected_reader
        from cj_api.local_account_admission_v2 import account_checker_for
        from cj_needs.contract_v1 import encode_snapshot
        needs_reader=protected_reader(database,account_checker_for(auth,database,selected_subjects=subjects))
        def current_needs():
            return needs_reader.read(headers['Authorization'].removeprefix('Bearer '),
                lambda operation,context:encode_snapshot(operation.detail(lio_needs_id(scope,cid))))
        before_needs=current_needs()
        for conflict_locale in ('zh','en'):
            current.update(locale=conflict_locale,mention='杭州'if conflict_locale=='zh'else'Hangzhou',
                           party='两个人'if conflict_locale=='zh'else'two people',duration='三天'if conflict_locale=='zh'else'three-day',
                           requested_start='2026-11-27')
            conflict_mid='national-incompatible-window-'+conflict_locale
            question=('计划杭州三天，从2026-11-27开始，两个人'if conflict_locale=='zh'else
                      'Plan a three-day trip to Hangzhou for two people starting 2026-11-27.')
            message=dict(version='LIO-message.2',message_id=conflict_mid,conversation_id=cid,locale=conflict_locale,text=question)
            response_=api.post('/v2/lio/messages',headers=headers,content=json.dumps(message).encode())
            assert response_.status_code==200,response_.text
            assert [(o.message_id,o.status)for o in process()]==[(conflict_mid,'completed')]
            assert api.get('/v2/lio/trip',params=params,headers=headers).json()==after_replan
            last=api.get('/v2/lio/timeline',params=dict(conversation_id=cid),headers=headers).json()['messages'][-1]
            assert last['status']=='completed'and last['trip']is None
            assert (('不保存或替换原行程'in last['answer'])if conflict_locale=='zh'else('without saving or replacing'in last['answer'])),last['answer']
            with database.connect(scope)as db:
                assert db.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',
                    (scope,conflict_mid)).fetchone()==(0,)
                assert db.execute("SELECT count(*) FROM cj_run_metered_operation WHERE scope=%s AND run_id=(SELECT run_id FROM cj_message_receipt WHERE scope=%s AND message_id=%s) AND registration_id='model.draft'",(scope,scope,conflict_mid)).fetchone()==(0,)
            assert current_needs()==before_needs
            print('PASS signed incompatible window: read-only proposal, original NEEDS/Trip unchanged, no draft',conflict_locale,flush=True)
        current.pop('requested_start')
        current.update(zh='上海',en='Shanghai',mention='Shanghai',party='two people',duration='three-day')
        switch=dict(version='LIO-message.2',message_id='national-other-destination',conversation_id=cid,locale='en',
            text='Plan a three-day trip to Shanghai for two people starting 2026-11-20.')
        accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(switch).encode());assert accepted.status_code==200,accepted.text
        assert [o.status for o in process()]==['completed']
        assert api.get('/v2/lio/trip',params=params,headers=headers).json()==after_replan
        print('PASS actual original adcode survives edit/undo/replan and different-city request writes no Trip',flush=True)
        # Exact public C date/locked-hotel wording. The supplier omits arrival
        # and sends a short label, explicit primary source, missing timezone.
        for locale in ('zh','en'):
            current.update(zh='成都',en='Chengdu',locale=locale,mention='成都' if locale=='zh' else 'Chengdu',
                clarification_flow=True,fixed_description=FIXED_TEXT[locale],party=PARTY_REPLY[locale])
            turns=[*CHENGDU_CASE['variants'][locale]['turns'],PARTY_REPLY[locale]]
            for index,text in enumerate(turns):
                mid='date-clarification-'+locale+'-'+str(index)
                message=dict(version='LIO-message.2',message_id=mid,text=text,locale=locale,
                    **({'new_conversation':True} if index==0 else {'conversation_id':flow_cid}))
                result=api.post('/v2/lio/messages',headers=headers,content=json.dumps(message).encode());assert result.status_code==200,result.text
                flow_cid=result.json()['conversation_id']
                outcomes=process();assert [(o.message_id,o.status) for o in outcomes]==[(mid,'completed')],(index,mid,outcomes)
                rows=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=flow_cid)).json()['messages']
                trip=api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=flow_cid)).json()
                if index==0:
                    assert trip['current'] is None
                    with database.connect(scope) as db:
                        assert db.execute('SELECT count(*) FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',(scope,mid)).fetchone()==(0,)
                    answer=rows[-1]['answer']
                    for day in range(1,4):assert ('第'+str(day)+'天' if locale=='zh' else 'Day '+str(day)) in answer
                    assert '2026-' not in answer and '哪天开始' not in answer and 'How many people' not in answer
                elif index==1:
                    assert trip['current'] is not None and trip['history']==[],(locale,index,rows[-1]['answer'],trip)
                    initial=trip['current'];assert initial['days'][0]['date']==current['start_date']
                    fixed,=[i for d in initial['days'] for i in d['items'] if i['fixed']]
                    assert fixed['label']==FIXED_TEXT[locale] and (fixed['start_time'],fixed['end_time'])==('09:00','10:00')
                    with database.connect(scope) as db:
                        row=db.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()
                        assert row[0]==1;initial_bytes=bytes(row[1])
                else:
                    assert trip['current']==initial and trip['history']==[]
                    assert '哪天开始' not in rows[-1]['answer'] and 'What date should' not in rows[-1]['answer']
                    with database.connect(scope) as db:
                        row=db.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()
                        assert row[0]==1 and bytes(row[1])==initial_bytes
            target=initial['days'][1]['items'][0]
            template=json.loads((ROOT/'eval/lio_national_cases.v1.json').read_bytes())['common_flow'][2][locale]
            edit=dict(version='LIO-message.2',message_id=mid+'-edit',conversation_id=flow_cid,locale=locale,
                text=template.format(actual_item_name=target['label'],actual_time_range=target['start_time']+'–'+target['end_time'],
                    replacement_query=CHENGDU_CASE['variants'][locale]['replacement_queries'][0]))
            assert api.post('/v2/lio/messages',headers=headers,content=json.dumps(edit).encode()).status_code==200
            assert [(o.message_id,o.status) for o in process()]==[(mid+'-edit','completed')]
            changed=api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=flow_cid)).json()
            assert changed['history']==[initial] and changed['current']!=initial
            undo=dict(version='LIO-trip-undo.2',action_id=mid+'-undo',conversation_id=flow_cid,target=changed['undo_target'])
            assert api.post('/v2/lio/trip/undo',headers=headers,content=json.dumps(undo).encode()).status_code==200
            with database.connect(scope) as db:
                row=db.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()
                assert row[0]==3 and bytes(row[1])==initial_bytes
                versions=db.execute('SELECT committed_version FROM cj_trip_receipt WHERE trip_id=%s ORDER BY committed_version',(initial['trip_id'],)).fetchall()
                assert versions==[(1,),(2,),(3,)]
                assert db.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
            print('PASS original C wording: undated plan->relative start/fixed save without party->optional party no duplicate->edit->full-byte undo',locale,flush=True)
        current.pop('clarification_flow');current.pop('start_date')
        # An unsaved candidate must not become personal identity in a new chat.
        preference=dict(version='LIO-message.2',message_id='nation-preference',text=PREFERENCE,locale='en',new_conversation=True)
        accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(preference).encode());assert accepted.status_code==200,accepted.text
        preference_chat=accepted.json()['conversation_id']
        assert [o.status for o in process()]==['completed']
        timeline=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=preference_chat)).json()
        tag,=timeline['messages'][-1]['memory']['tags']
        for saved in (False,True):
            if saved:
                action=dict(version='LIO-memory-action.1',action_id='nation-remember',operation='remember',target=tag['target'])
                result=api.post('/v1/lio/memory/actions',headers=headers,content=json.dumps(action).encode())
                assert result.status_code==200 and result.json()['status']=='remembered',result.text
            current['saved_memory']=saved
            for locale,question in (('en','Who am I?'),('zh','我是谁')):
                current['identity_locale']=locale
                identity=dict(version='LIO-message.2',message_id='nation-identity-'+str(saved)+'-'+locale,text=question,locale=locale,new_conversation=True)
                accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(identity).encode());assert accepted.status_code==200,accepted.text
                assert [o.status for o in process()]==['completed']
                read=api.get('/v2/lio/timeline',headers=headers,params=dict(conversation_id=accepted.json()['conversation_id'])).json()
                reply=read['messages'][-1]['answer']
                assert ('fewer stops' in reply or '少安排' in reply) if saved else ("don't know you yet" in reply or '还不了解你' in reply)
        print('PASS national consultation retains Memory candidates and new-chat identity recalls only saved Memory',flush=True)
    # Undated destination/day-count requests now resolve a city for their plan.
    # Two undated requests + twelve dated plans + one destination switch + two C flows.
    # Parameter-only continuations reuse that original resolution; discussions do not resolve.
    assert len(city_calls)==17,len(city_calls)
    assert all(row['state']=='RECEIVED' for row in journal.inspect())
    print('PASS 12 signed private PG chains, original model/tool receipts, no live vendor calls',flush=True)


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-nation-') as folder:
        root=Path(folder)
        with pg_suites.cluster('nation',port=55653,role='cj_nation_initializer',root=root/'pg',socket=root/'s') as conninfo:
            with psycopg.connect(**conninfo,autocommit=True) as db:
                migrations=migrate.load();migrate.up(db,migrations,migrations[-1]['version'])
            import base64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
            recovery=Ed25519PrivateKey.generate()
            env=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
                CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',CJ_BETA_DEMO_SUBJECTS_JSON=json.dumps([SUBJECT]),
                CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(recovery.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
                CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(recovery.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
            with patch.dict(os.environ,env):exercise(root,conninfo)
