"""Signed private PG nationwide chain; only HTTP supplier fixtures, never HK proof."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone,date
import hashlib
import json
import os
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
        elif 'LIO-planning-intake.1' in system:
            text=body['messages'][-1]['content'];current['text']=text
            source_index=len([m for m in body['messages'][1:] if m['role']=='user' and not m['content'].startswith('Stored memory data')])-1
            if text==PREFERENCE:
                content=json.dumps(dict(version='LIO-planning-intake.1',intent='consult',reply='I can suggest a relaxed pace.',needs_tools=False,
                    city=None,duration_days=None,extraction=dict(version='NEEDS-extraction.1',fields={},unresolved=[],long_term_requests=[]),
                    field_sources={},current_request=text))
            else:
                content=None
            fields=dict(arrival=dict(date=dict(state='known',value='2026-11-20')),party_size=dict(state='known',value=2))
            content=content or json.dumps(dict(version='LIO-planning-intake.1',intent='plan',reply='I can arrange the trip.',needs_tools=False,
                city=dict(query=current['mention'],normalized_name=None,province=None,source_index=source_index,quote=current['mention']),
                duration_days=3,extraction=dict(version='NEEDS-extraction.1',fields=fields,unresolved=[],long_term_requests=[]),
                field_sources={k:[dict(source_index=source_index,quote=q)] for k,q in (
                    ('arrival.date','2026-11-20'),('party_size',current['party']),('duration_days',current['duration']))},current_request=text),ensure_ascii=False)
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
            items=[dict(id='visit-'+str(i),text=current['en']+' Walk '+str(i),date='2026-11-'+str(19+i),
                start_time='19:00' if i==3 else '14:00',end_time='20:00' if i==3 else '15:00',timezone='Asia/Shanghai') for i in (1,2,3)]
            if original['current_trip'] is not None:
                content=json.dumps(dict(version='TRIP-lio-replan-delta.3',items=[],proposed_subjects={}))
            else:
                content=json.dumps(dict(version='TRIP-lio-first-plan.1',title=current['en']+' trip',items=items,
                    proposed_subjects={item['id']:['party'] for item in items}),ensure_ascii=False)
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
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),journal,transport=httpx.MockTransport(response))
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
        for zh,en,adcode in CITIES:
            for locale in ('zh','en'):
                current.update(zh=zh,en=en,mention=zh if locale=='zh' else en,
                    party='两个人' if locale=='zh' else 'two people',duration='三天' if locale=='zh' else 'three-day')
                text=(f'计划{zh}三天豪华游，从2026-11-20开始，两个人。' if locale=='zh' else
                      f'Plan a three-day trip to {en} for two people starting 2026-11-20.')
                mid='nation-'+adcode+'-'+locale
                payload=dict(version='LIO-message.2',message_id=mid,text=text,locale=locale,new_conversation=True)
                accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(payload).encode())
                assert accepted.status_code==200,accepted.text
                cid=accepted.json()['conversation_id'];params={'conversation_id':cid}
                outcomes=process();assert [(o.message_id,o.status) for o in outcomes]==[(mid,'completed')],outcomes
                saved=api.get('/v2/lio/trip',params=params,headers=headers).json();assert saved['current'] is not None and saved['history']==[],saved
                initial=saved['current'];assert initial['days'][0]['date']=='2026-11-20',initial
                edit=dict(version='LIO-message.2',message_id=mid+'-edit',conversation_id=cid,locale=locale,
                    text='把第二天下午换成“人民公园”。' if locale=='zh' else f'Replace {en} Walk 2 with "Riverside Park".')
                changed=api.post('/v2/lio/messages',headers=headers,content=json.dumps(edit).encode());assert changed.status_code==200,changed.text
                outcomes=process();assert [(o.message_id,o.status) for o in outcomes]==[(mid+'-edit','completed')],outcomes
                after=api.get('/v2/lio/trip',params=params,headers=headers).json();assert after['current']!=initial and after['history']==[initial],after
                command=dict(version='LIO-trip-undo.2',action_id=mid+'-undo',conversation_id=cid,target=after['undo_target'])
                undone=api.post('/v2/lio/trip/undo',headers=headers,content=json.dumps(command).encode());assert undone.status_code==200,undone.text
                final=api.get('/v2/lio/trip',params=params,headers=headers).json();assert final['current'] is not None,final
                assert final['current']['days']==initial['days'] and len(final['history'])==2
                with database.connect(scope) as db:
                    assert db.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(initial['trip_id'],)).fetchone()==(3,)
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
        current.update(zh='上海',en='Shanghai',mention='Shanghai',party='two people',duration='three-day')
        switch=dict(version='LIO-message.2',message_id='national-other-destination',conversation_id=cid,locale='en',
            text='Plan a three-day trip to Shanghai for two people starting 2026-11-20.')
        accepted=api.post('/v2/lio/messages',headers=headers,content=json.dumps(switch).encode());assert accepted.status_code==200,accepted.text
        assert [o.status for o in process()]==['completed']
        assert api.get('/v2/lio/trip',params=params,headers=headers).json()==after_replan
        print('PASS actual original adcode survives edit/undo/replan and different-city request writes no Trip',flush=True)
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
    assert len(city_calls)==13
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
