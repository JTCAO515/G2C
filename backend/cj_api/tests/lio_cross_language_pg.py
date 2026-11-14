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


def exercise(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,[SUBJECT]);now=int(time.time())
    config=root/'connection.json';config.write_text(json.dumps(conninfo))
    meter=root/'meter.json';meter.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(
        unit='provider_call',budget=800,period_start=now-60,period_end=int(DEMO_DEADLINE.timestamp()),
        max_steps=24,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
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
    locale='en';text='';bad=False;wire=[];start=None
    fixed={'en':'On day 1 I have a fixed hotel meetup from 9 to 10 a.m.; keep it unchanged',
           'zh':'第一天我9:00到10:00要在酒店集合，保持不变'}
    def response(request):
        nonlocal start
        body=json.loads(request.content);wire.append(body);system=body['messages'][0]['content']
        if 'LIO-planning-intake.8'in system:
            assert SOURCE_LANGUAGE in system,'missing actual evidence-language prompt'
            assert body['max_tokens']==1536,body['max_tokens']
            originals=[m['content']for m in body['messages'][1:]if m['role']=='user'and not m['content'].startswith('Stored memory data')]
            index=len(originals)-1
            if index==0:
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
                if bad:value['city'].update(query='成都',quote='成都')
        elif 'The traveler requested a complete 'in system:
            value=dict(answer=('Day 1: a neighborhood. Day 2: a museum. Day 3: a park. Which day should we adjust?'
                if locale=='en'else'第1天逛街区，第2天看博物馆，第3天去公园。你想先调整哪一天？'))
        else:
            original=json.loads(body['messages'][-1]['content'])
            assert original['version']=='TRIP-source-input.2'
            assert original['fields']['party_size']['state']!='known'
            assert len(original['fields']['fixed_items'])==1
            days=[]
            for n in range(3):
                day=(date.fromisoformat(start)+timedelta(days=n)).isoformat()
                rows=[]if n==0 else [[f'am-{n}','Museum（博物馆）','09:00','11:00',['self']]]
                rows.append([f'pm-{n}','Park（公园）','14:00','16:00',['self']]);days.append([day,rows])
            value=dict(version='TRIP-lio-first-plan.2',title='Chengdu（成都）',days=days)
        identity=dict(id='cross-language-fixture-'+str(len(wire)),model=M4_MODEL)
        frames=[dict(**identity,choices=[dict(index=0,delta=dict(content=json.dumps(value,ensure_ascii=False)),finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=40,completion_tokens=10,total_tokens=50))]
        raw=''.join('data: '+json.dumps(frame)+'\n\n'for frame in frames)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY,max_output_tokens=1536),journal,transport=httpx.MockTransport(response))
    services=RealServices(model,KEY,subjects,demo_subjects=subjects,national_subjects=subjects)
    tools=RealTools(services,buffered_streaming_subjects=subjects)
    signer=load_confirmation_signer(auth)
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,account_admission=True,
        confirmation_signer=signer,demo_dialogue_subjects=subjects,lio_dialogue_subjects=subjects)
    headers={'Authorization':'Bearer '+dev_auth.token(auth,SUBJECT,3600),'Content-Type':'application/octet-stream'}
    async def catalogue(key,guard):assert key==KEY and guard()is True;return city_catalog()
    with TestClient(app)as api,patch('cj_api.lio_city._catalog_exchange',side_effect=catalogue):
        for label,language,invalid in (('en','en',False),('zh','zh',False),('translated','en',True)):
            locale=language;bad=invalid;cid=None
            texts=(CASE['turns']if locale=='en'else('我想去成都玩三天。','明天开始。'+fixed['zh']+'。酒店名称和位置尚未确定。不要声称已经预订。'))
            for index,text in enumerate(texts):
                mid='cross-'+label+'-'+str(index)
                sent=api.post('/v2/lio/messages',headers=headers,content=json.dumps(dict(version='LIO-message.2',message_id=mid,
                    text=text,locale=locale,**({'conversation_id':cid}if cid else{'new_conversation':True})),ensure_ascii=False).encode())
                assert sent.status_code==200,sent.text;cid=sent.json()['conversation_id']
                outcome,=run_worker.run_once(database,model,auth,tools_configuration=tools,real_services=services,
                    memory_configuration_for_scope=lambda owner:memory if owner==scope else None,account_admission=True,
                    hk_demo_scopes=frozenset({scope}),lio_confirmation=signer)
                expected='unknown'if bad and index==1 else'completed'
                assert outcome.status==expected,outcome
                current=api.get('/v2/lio/trip',headers=headers,params=dict(conversation_id=cid)).json()
                if index==0 or bad:
                    assert current['current']is None
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
                    assert meeting['start']['place']['state']=='unknown'and meeting['end']['place']['state']=='unknown'
                print(json.dumps(dict(mid=mid,cid=cid,run=outcome.run_id,status=outcome.status)),flush=True)
            if bad:
                with database.connect(scope)as db:
                    assert db.execute('SELECT count(*)FROM cj_message_needs_binding WHERE message_scope=%s AND message_id=%s',(scope,mid)).fetchone()[0]==0
        with database.connect(scope)as db:assert db.execute('SELECT count(*)FROM cj_memory_item').fetchone()[0]==0
    print('PASS signed ZH/EN preview -> date/fixed self -> one saved version; translated source remains UNKNOWN/zero binding/Trip, no retries; HTTP fixtures only',flush=True)


def main():
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
            with patch.dict(os.environ,env):exercise(root,conninfo)


if __name__=='__main__':main()
