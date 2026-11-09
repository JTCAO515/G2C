"""Private PostgreSQL and real JWT/Unix socket; no external model or account."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
from threading import Event
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,NoEncryption,PrivateFormat,PublicFormat
from fastapi.testclient import TestClient
from cj_api.local_app import ISSUER,LocalDatabase,create_local_app,load_confirmation_signer,scope_for
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_api.local_run_context import load_run_context
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_message.travel import ABI
from deploy.hk import checkpoint,demo_accounts,demo_login,demo_schema,schema,staging
from deploy.hk.configuration import Runtime,demo_periods
from cj_run.step_usage import ledger_scope_for
from cj_usage.authorization_budget import DEADLINE,DEMO_DEADLINE
import dev_auth
import local_run_context
import migrate
import pg_suites
import run_worker

SUBJECT='m4-synthetic-demo-0123456789ab'
CODE='D1-0123456789ab.'+'x'*22
NEW_CODE='D1-0123456789ab.'+'y'*22


def digest(code):return hashlib.sha256(code.encode('ascii')).hexdigest()


def verify_upgrade(root, blueprint, target):
    root.mkdir(mode=0o700)
    schema_root=root/'schema'
    schema.generate(blueprint,schema_root)
    control=root/'upgrade-control'
    backups=root/'upgrade-backups'
    backups.mkdir(mode=0o700)
    prior=backups/'previous'
    prior.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    env=dict(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
        CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
    with pg_suites.cluster('demo-upgrade',port=55650,role='cj_demo_upgrade',root=root/'old',socket=root/'old-s') as config:
        with psycopg.connect(**config,autocommit=True) as db:
            migrate.up(db,migrate.load(),target-1)
            original=checkpoint.local.fence_state(db)

        @contextmanager
        def operator():
            with psycopg.connect(**config,autocommit=True) as db:
                yield db,config

        with patch.dict(os.environ,env),patch.object(checkpoint,'operator',operator),                patch.object(staging,'PG17',pg_suites.bindir()):
            with patch.object(checkpoint,'versions',return_value=list(range(1,target))):
                checkpoint.bootstrap(control,lambda _:None)
            old=checkpoint.verified(control/'release.json')
            checkpoint.atomic(control/'b2.json',dict(version='g2c-hk-local.1',state='FORWARD_ONLY'))
            checkpoint.atomic(prior/'manifest.json',dict(schema=list(range(1,target)),
                lineage=old['lineage'],fences=original))
            demo_schema.upgrade(control,backups,target=target,schema_root=schema_root)
            base=demo_schema.daily_base(control,backups,'previous')
            assert base==backups/f'demo-schema{target}'
            result=checkpoint.verified(base/'manifest.json')
            assert result['fences']==original and result['lineage']==old['lineage']
            with operator() as (db,_):
                checkpoint.require_release(db,control)
            try:
                demo_schema.upgrade(control,backups,target=target,schema_root=schema_root)
            except ValueError as exc:
                assert 'reconcile original' in str(exc)
            else:
                raise AssertionError('schema upgrade accepted a second application')


def check_planning(api, headers, foreign, database, auth, memory, conninfo):
    from cj_api.local_needs_preview import DIALOGUE_SYSTEM
    from cj_draft.needs_publisher import SYSTEM
    from cj_message.needs_binding import needs_scope_for
    from cj_agent.draft import trip_scope_for

    def known(value):
        return dict(state='known',value=value)

    def event(day, clock=None):
        return dict(date=known(day),time=known(clock) if clock else dict(state='missing'),
                    timezone=known('Asia/Shanghai'),place=known('酒店大堂'))

    item=dict(item_id='lobby',kind='appointment',description='酒店大堂集合',applies_to=['party'],
              locked=known(True),booking_status=dict(state='unknown'),
              start=event('2026-11-10','09:00'),end=event('2026-11-10','10:00'))
    extracted=dict(party_size=known(2),pace=known('轻松'),arrival=event('2026-11-10'),
                   departure=event('2026-11-11'),fixed_items=[item])

    class PlanModel(FakeProvider):
        def stream(self,messages,system=None):
            if system and system.startswith(DIALOGUE_SYSTEM):
                self.calls+=1
                assert len(messages)==1 and messages[0]['role']=='user'
                text=messages[0]['content']
                city='Beijing' if 'Beijing' in text else '北京'
                yield json.dumps(dict(city=city,extraction=dict(version='NEEDS-extraction.1',
                    fields=extracted,unresolved=[],long_term_requests=[])),ensure_ascii=False)
            elif system and system.startswith(SYSTEM):
                self.calls+=1
                source=json.loads(messages[-1]['content'])
                assert source['fields']['fixed_items']==[item]
                schedule={edge:{key:item[edge][key] for key in ('date','time','timezone')}
                          for edge in ('start','end')}
                for value in schedule.values():
                    value['utc_offset']=dict(state='unknown')
                yield json.dumps(dict(version='TRIP-model-plan.1',title='Synthetic confirmed plan',items=[
                    dict(id=item['item_id'],text=item['description'],verification='pending',evidence=[],
                         schedule=schedule,fixed=item['locked'],source_category='user_provided',source_refs=[])],
                    proposed_subjects={}),ensure_ascii=False)
            else:
                yield from super().stream(messages,system=system)

    scope=scope_for(ISSUER,SUBJECT)
    worker_model=PlanModel()
    worker=run_worker._worker_for_scope(database,worker_model,auth,scope,checker_for(auth),
        memory_configuration=memory,draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True)
    messages='/v1/demo-dialogue/messages'
    actions='/v1/demo-dialogue/actions'
    events='/v1/demo-dialogue/events'

    def post(route, payload, code=200, bearer=headers):
        response=api.post(route,content=json.dumps(payload,ensure_ascii=False).encode(),headers=bearer)
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()

    def send(mid,text,locale='en',**extra):
        return post(messages,dict(version='DEMO-dialogue-message.2',message_id=mid,text=text,
                                  locale=locale,**extra))['receipt']

    def preview_card(receipt):
        response=api.get(events,params={'message_id':receipt['message_id']},headers=headers)
        assert response.status_code==200,response.text
        data=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert all(event['run_id']==receipt['run_id'] and event['event_id'].isdigit() for event in data)
        return next(event['payload'] for event in data if event['kind']=='needs_card')

    original=send('need-first','Could you plan a relaxed two-day Beijing visit for two people?')
    result,=worker.process()
    assert result.status=='completed' and result.proposal_id is None and worker_model.calls==1,result
    card=preview_card(original)
    assert card==dict(card_id=card['card_id'],version=1,status='pending',
        dates=dict(start='2026-11-10',end='2026-11-11'),city='Beijing',party_size=2,pace='轻松',
        fixed_items=[dict(item_id='lobby',label='酒店大堂集合',starts_at='2026-11-10T09:00',
                          ends_at='2026-11-10T10:00',time_zone='Asia/Shanghai')])
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT count(*) FROM cj_needs_record WHERE scope=%s AND needs_id=%s',
            (needs_scope_for(scope),card['card_id'])).fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM cj_trip_proposal WHERE scope=%s',
            (trip_scope_for(scope),)).fetchone()==(0,)
        try:
            with db.transaction():
                migrate.down(db,migrate.load(),50)
        except psycopg.errors.RaiseException as exc:
            assert 'demo needs card originals must be preserved' in str(exc)
        else:
            raise AssertionError('migration down erased original needs cards')
    second=send('need-second','Please plan a Beijing trip for two people?',
                conversation_id=original['conversation_id'])
    assert worker.process()[0].status=='completed'
    assert preview_card(second)['card_id']!=card['card_id']
    post(messages,dict(version='DEMO-dialogue-message.2',message_id='ambiguous-yes',text='yes',
                       locale='en',conversation_id=original['conversation_id']),409)
    assert not worker.process()
    action=dict(version='DEMO-dialogue-action.1',action_id='edit-people',
        conversation_id=original['conversation_id'],card_id=card['card_id'],expected_version=1,
        operation='correct_needs',changes=dict(party_size=known(3)))
    corrected=post(actions,action)['receipt']
    assert corrected['card']['party_size']==3 and corrected['version']==2 and corrected['run_id'] is None
    assert post(actions,action)['receipt']==corrected
    post(actions,dict(action,changes=dict(party_size=known(4))),409)
    assert api.get(actions,params={'action_id':'edit-people'},headers=foreign).json()['receipt'] is None
    post(actions,dict(action,action_id='foreign-correction'),503,bearer=foreign)
    assert preview_card(original)==card
    confirm={key:value for key,value in action.items() if key!='changes'}
    confirm.update(action_id='needs-confirm',operation='confirm_needs')
    post(actions,confirm,409)
    confirm['expected_version']=2
    from cj_message import demo_needs_cards
    with patch.object(demo_needs_cards,'enqueue_dialogue',side_effect=RuntimeError('synthetic enqueue failure')):
        post(actions,dict(confirm,action_id='fault-before-enqueue'),503)
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT count(*) FROM cj_needs_record WHERE scope=%s AND needs_id=%s',
            (needs_scope_for(scope),card['card_id'])).fetchone()==(0,)
    confirmed=post(actions,confirm)['receipt']
    assert confirmed['card']['status']=='confirmed' and confirmed['version']==3
    assert post(actions,confirm)['receipt']==confirmed
    assert api.get(actions,params={'action_id':'needs-confirm'},headers=headers).json()['receipt']==confirmed
    next_message=api.get(messages,params={'message_id':confirmed['message_id']},headers=headers).json()['receipt']
    assert next_message['run_id']==confirmed['run_id'] and next_message['conversation_id']==original['conversation_id']
    result,=worker.process()
    assert result.status=='completed' and result.proposal_id and result.run_id==confirmed['run_id'],result
    response=api.get(events,params={'message_id':next_message['message_id']},headers=headers)
    assert response.status_code==200,response.text
    rows=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    trip_card=next(event['payload'] for event in rows if event['kind']=='trip_candidate')
    assert trip_card['proposal_id']==result.proposal_id and trip_card['status']=='pending'
    assert trip_card['days']==[dict(date='2026-11-10',items=[dict(item_id='lobby',label='酒店大堂集合',
        place='酒店大堂',starts_at='2026-11-10T09:00',ends_at='2026-11-10T10:00',
        time_zone='Asia/Shanghai',source_ids=trip_card['days'][0]['items'][0]['source_ids'],fixed=True)])]
    with psycopg.connect(**conninfo) as db:
        fields=db.execute('SELECT content FROM cj_needs_record WHERE scope=%s AND needs_id=%s',
            (needs_scope_for(scope),card['card_id'])).fetchone()[0]
        assert json.loads(fields)['party_size']==known(3)
        assert db.execute('SELECT status FROM cj_trip_proposal WHERE scope=%s AND proposal_id=%s',
            (trip_scope_for(scope),result.proposal_id)).fetchone()==('pending',)
        assert db.execute('SELECT count(*) FROM cj_trip_record WHERE scope=%s',
            (trip_scope_for(scope),)).fetchone()==(0,)

    legacy=post(messages,dict(version='DEMO-dialogue-message.1',message_id='legacy-planning',
        text='Could you plan a relaxed two-day Beijing visit for two people?',locale='en'))['receipt']
    result,=worker.process()
    assert result.status=='completed' and result.proposal_id is None and result.run_id==legacy['run_id']
    legacy_events=api.get(events,params={'message_id':legacy['message_id']},headers=headers)
    assert legacy_events.status_code==200 and 'needs_card' not in legacy_events.text

    zh=send('need-zh','帮我们两个人规划从明天开始的北京两天游，节奏轻松。','zh',new_conversation=True)
    assert worker.process()[0].status=='completed'
    zh_card=preview_card(zh)
    assert zh_card['city']=='北京'
    spoken=send('spoken-confirm','可以','zh',conversation_id=zh['conversation_id'])
    assert send('spoken-confirm','可以','zh',conversation_id=zh['conversation_id'])==spoken
    result,=worker.process()
    assert result.status=='completed' and result.proposal_id and result.run_id==spoken['run_id'],result
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT count(*) FROM cj_demo_needs_card WHERE scope=%s AND operation=%s',
            (scope,'confirm_needs')).fetchone()==(2,)
        assert db.execute('SELECT count(*) FROM cj_trip_record WHERE scope=%s',
            (trip_scope_for(scope),)).fetchone()==(0,)
    from cj_api.demo_dialogue_trip import DialogueTripCards
    from cj_message.domain import CommitUnknown

    adoption=dict(version='DEMO-dialogue-action.1',action_id='demo-trip-adopt',
        conversation_id=original['conversation_id'],card_id=trip_card['card_id'],
        expected_version=trip_card['version'],operation='accept_trip')
    post(actions,dict(adoption,expected_version=2),400)
    post(actions,dict(adoption,action_id='foreign-trip-adopt'),503,bearer=foreign)
    canonical_adopt=DialogueTripCards.adopt
    invocations=[]

    def commit_then_lose(instance,token,intent):
        invocations.append(intent.trip_action_id)
        canonical_adopt(instance,token,intent)
        raise CommitUnknown('synthetic committed adoption ACK loss')

    with patch.object(DialogueTripCards,'adopt',autospec=True,side_effect=commit_then_lose):
        post(actions,adoption,503)
        accepted=api.get(actions,params={'action_id':'demo-trip-adopt'},headers=headers).json()['receipt']
        assert accepted['committed_version']==1 and accepted['trip_id']==trip_card['trip_id']
        assert post(actions,adoption)['receipt']==accepted and len(invocations)==1
    assert api.get(actions,params={'action_id':'demo-trip-adopt'},headers=foreign).json()['receipt'] is None
    post(actions,dict(adoption,card_id='p-'+'0'*36),409)
    with psycopg.connect(**conninfo) as db:
        assert db.execute('SELECT version FROM cj_trip_record WHERE scope=%s AND trip_id=%s',
                          (trip_scope_for(scope),accepted['trip_id'])).fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM cj_trip_receipt WHERE scope=%s AND proposal_id=%s',
                          (trip_scope_for(scope),trip_card['proposal_id'])).fetchone()==(1,)
        try:
            with db.transaction():
                migrate.down(db,migrate.load(),51)
        except psycopg.errors.RaiseException as exc:
            assert 'demo Trip adoption originals must be preserved' in str(exc)
        else:
            raise AssertionError('migration down erased original Trip adoption')
    terminal_cursor=rows[-1]['event_id']
    resumed=api.get(events,params={'message_id':next_message['message_id']},
        headers={**headers,'Last-Event-ID':terminal_cursor})
    assert resumed.status_code==200 and resumed.text==''
    print('PASS explicit C Trip adoption, real original receipt, committed ACK loss readback and no second invocation')
    print('PASS signed needs card, correction/replay, failed enqueue rollback, typed and text confirmation, original planning outbox and protected pending Trip')


def exercise(root,conninfo):
    auth=root/'auth'
    other='other-dialogue-owner'
    dev_auth.init(auth,[SUBJECT,other,'invited-outside-dialogue'])
    path=root/'conn.json'
    path.write_text(json.dumps(conninfo))
    now=int(time.time())
    context_path=root/'meter.json'
    context_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',
        budget=100,period_start=now-60,period_end=int(DEADLINE.timestamp()),max_steps=8,max_tools=2,max_output=60000,max_seconds=600),
        output_limits=dict(model=4000,tool=2000,memory=1000)),history=[])))
    context=load_run_context(context_path)
    _,following=demo_periods(context,now)
    assert demo_periods(context,int(DEADLINE.timestamp()))==(following,None)
    assert following.history==(context.current,) and following.current.meter.period_end==int(DEMO_DEADLINE.timestamp())
    database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True)
    profile=dict(subjects=['self'],slots={'quiet.entrance':dict(kind='preference',collection_allowed=True,
        semantic_resolved=True)},extents=['long_term'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={SUBJECT:profile}),
        travel_contexts={SUBJECT:[]})
    memory=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=collection,
        selections={SUBJECT:dict(subject='self',slots=['quiet.entrance'],max_bytes=1000)})).encode())
    runtime=Runtime(auth,context,context_path,[],memory_runtime=memory,subjects=frozenset({SUBJECT}),
        demo_subjects=frozenset({SUBJECT}),demo_next_context=following)
    runtime._database=database
    control=root/'control';operation=root/'operation';operation.mkdir(mode=0o700)
    endpoint=root/'signer';endpoint.mkdir(mode=0o700)
    key=Ed25519PrivateKey.generate()
    env=dict(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',
        CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',CJ_BETA_DEMO_SUBJECTS_JSON=json.dumps([SUBJECT]),
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())

    @contextmanager
    def operator():
        with psycopg.connect(**conninfo,autocommit=True) as connection:
            yield connection,conninfo

    with patch.dict(os.environ,env),patch.object(checkpoint,'operator',operator),patch.object(demo_login,'SOCKET',endpoint/'login.sock'):
        checkpoint.bootstrap(control,lambda _:None)
        expiry=datetime.now(timezone.utc)+timedelta(hours=1)
        assert demo_accounts.manage(runtime,'bootstrap',SUBJECT,control,operation,(digest(CODE),expiry))=='bootstrapped'
        assert demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)=='activated'
        assert demo_accounts.manage(runtime,'insert',SUBJECT,control,operation)=='existing'
        local_run_context.provision_budget(path,context,other)
        dev_auth.activate_travel(path,other,context,ABI)
        app=create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,account_admission=True,
            confirmation_signer=load_confirmation_signer(auth),demo_dialogue_subjects=frozenset({SUBJECT,other}))
        demo_login.register_demo_login(app)
        with demo_login.signing_socket(runtime),TestClient(app) as api:
            def login(code,consent=True):
                return api.post('/v1/demo-invite-sessions',json=dict(version=demo_login.VERSION,invite_code=code,consent=consent))
            assert login(CODE,False).status_code==400
            assert login(CODE[:-1]+'z').status_code==401
            signed=login(CODE)
            assert signed.status_code==200 and signed.headers['cache-control']=='no-store'
            assert login(CODE).status_code==200
            old={'Authorization':'Bearer '+signed.json()['access_token'],'Content-Type':'application/octet-stream'}
            params={'conversation_id':'demo-original'}
            assert api.put('/v1/conversations',params=params,headers=old).status_code==200
            with patch.object(dev_auth,'time',SimpleNamespace(time=lambda:time.time()-7202)):
                expired=dev_auth.token(auth,SUBJECT,120)
            assert api.put('/v1/conversations',params=params,headers={**old,'Authorization':'Bearer '+expired}).status_code==401
            route='/v1/demo-dialogue/messages'
            def dialogue(mid, **extra):
                return json.dumps(dict(version='DEMO-dialogue-message.1',message_id=mid,text='虚构北京行程',
                                       locale='zh',**extra),ensure_ascii=False).encode()
            assert api.post(route,content=dialogue('outside'),headers={
                **old,'Authorization':'Bearer '+dev_auth.token(auth,'invited-outside-dialogue',30)}).status_code==403
            assert api.post(route,content=dialogue('invalid',new_conversation=True,
                conversation_id='demo-dialogue-'+'0'*32),headers=old).status_code==400
            assert api.post(route,content=dialogue('client-owner',owner='forged'),headers=old).status_code==400
            first_raw=dialogue('first')
            with ThreadPoolExecutor(max_workers=3) as pool:
                responses=list(pool.map(lambda raw: api.post(route,content=raw,headers=old),
                    (first_raw,first_raw,dialogue('second'))))
            assert all(response.status_code==200 for response in responses),[(r.status_code,r.text) for r in responses]
            first, replay, second=(response.json()['receipt'] for response in responses)
            assert first==replay and first['input_sha256']==hashlib.sha256(first_raw).hexdigest()
            assert first['run_id']!=second['run_id'] and first['conversation_id']==second['conversation_id']
            lookup=api.get(route,params={'message_id':'first'},headers=old)
            assert lookup.status_code==200 and lookup.json()['receipt']==first
            foreign={**old,'Authorization':'Bearer '+dev_auth.token(auth,other,30)}
            assert api.get(route,params={'message_id':'first'},headers=foreign).json()['receipt'] is None
            assert api.post(route,content=dialogue('foreign-resume',
                conversation_id=first['conversation_id']),headers=foreign).status_code==503
            conflict=api.post(route,content=first_raw+b' ',headers=old)
            assert conflict.status_code==409 and conflict.json()['error']['code']=='INPUT_CONFLICT'
            new=api.post(route,content=dialogue('new',new_conversation=True),headers=old)
            assert new.status_code==200 and new.json()['receipt']['conversation_id']!=first['conversation_id']
            resumed=api.post(route,content=dialogue('continued',
                conversation_id=new.json()['receipt']['conversation_id']),headers=old)
            assert resumed.status_code==200 and resumed.json()['receipt']['conversation_id']==new.json()['receipt']['conversation_id']
            with psycopg.connect(**conninfo) as db:
                rows=db.execute("""SELECT f.context_id,f.context_version,r.demo_dialogue_input_sha256,r.input_sha256,
                    r.raw_input,d.acknowledged FROM cj_message_receipt r
                    JOIN cj_message_travel_reference f USING(scope,message_id,run_id)
                    JOIN cj_message_delivery d USING(scope,message_id,run_id)
                    WHERE r.scope=%s AND r.demo_dialogue_locale='zh'""",(scope_for(ISSUER,SUBJECT),)).fetchall()
                assert len(rows)==4 and len({row[0] for row in rows})==1
                assert all(version==1 and sha==hashlib.sha256(bytes(raw)).hexdigest()
                    and outer!=sha and not ack and json.loads(raw)['version']=='MESSAGE-send.2'
                    for _,version,outer,sha,raw,ack in rows)
                assert db.execute("SELECT count(*) FROM cj_travel_context_action WHERE scope=%s AND context_id=%s",
                    (scope_for(ISSUER,SUBJECT),rows[0][0])).fetchone()==(1,)
                try:
                    with db.transaction():
                        migrate.down(db,migrate.load(),49)
                except psycopg.errors.RaiseException as exc:
                    assert 'demo dialogue originals must be preserved' in str(exc)
                else:
                    raise AssertionError('migration down erased original dialogue evidence')
            model=FakeProvider()
            worker=run_worker._worker_for_scope(database,model,auth,scope_for(ISSUER,SUBJECT),
                checker_for(auth),memory_configuration=memory)
            from cj_api.demo_dialogue_events import _project
            event_route='/v1/demo-dialogue/events'
            event_params={'message_id':'first'}
            accepted_only=Event()

            def observe_queue(binding,state,after,**extra):
                if state is None and binding.run_id==first['run_id']:
                    accepted_only.set()
                return _project(binding,state,after,**extra)

            with patch('cj_api.demo_dialogue_events._project',side_effect=observe_queue),                    ThreadPoolExecutor(max_workers=1) as pool:
                watch=pool.submit(api.get,event_route,params=event_params,headers=old)
                assert accepted_only.wait(5), 'protected original outbox was not observed before the RUN'
                outcomes=worker.process()
                streamed=watch.result(timeout=15)
            assert len(outcomes)==4 and all(outcome.status=='completed' for outcome in outcomes)
            assert model.calls==4
            assert streamed.status_code==200
            def frames(response):
                return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            actual=frames(streamed)
            assert [entry['payload']['stage'] for entry in actual if entry['kind']=='status']==['queued','running','completed']
            assert all(entry['run_id']==first['run_id'] and entry['message_id']==first['message_id'] for entry in actual)
            assert ''.join(entry['payload']['text'] for entry in actual if entry['kind']=='answer_delta')
            cursor=actual[1]['event_id']
            assert frames(api.get(event_route,params=event_params,headers={**old,'Last-Event-ID':str(cursor)}))==actual[2:]
            assert api.get(event_route,params=event_params,headers={**old,'Last-Event-ID':'99999'}).status_code==409
            assert api.get(event_route,params=event_params,headers=foreign).status_code==503
            with psycopg.connect(**conninfo) as db:
                assert db.execute('SELECT count(*) FROM cj_message_delivery WHERE scope=%s AND acknowledged',
                    (scope_for(ISSUER,SUBJECT),)).fetchone()==(4,)
            check_planning(api,old,foreign,database,auth,memory,conninfo)
            assert login(CODE).status_code==200
            assert demo_accounts.manage(runtime,'revoke',SUBJECT,control,operation)=='revoked'
            assert login(CODE).status_code==401
            assert api.get(route,params={'message_id':'first'},headers=old).status_code==403
            assert api.get(event_route,params={'message_id':'first'},headers=old).status_code==403
            assert api.post(route,content=dialogue('revoked'),headers=old).status_code==403
            assert api.put('/v1/conversations',params=params,headers=old).status_code==403
            assert demo_accounts.manage(runtime,'rotate',SUBJECT,control,operation,(digest(NEW_CODE),expiry))=='active'
            time.sleep(1.05)
            assert login(CODE).status_code==401 and api.put('/v1/conversations',params=params,headers=old).status_code==403
            renewed=login(NEW_CODE)
            assert renewed.status_code==200,renewed.status_code
            headers={**old,'Authorization':'Bearer '+renewed.json()['access_token']}
            opened=api.put('/v1/conversations',params=params,headers=headers)
            assert opened.status_code==200
            generation=opened.json()['generation']
            def command(number):
                return json.dumps(dict(version='MESSAGE-send.2',conversation_id=params['conversation_id'],
                    message_id='demo-'+str(number),text='Fictional trip',trip_id=None,creation_intent='none',
                    expected_generation=generation,expected_sequence=number-1,travel_context=None,needs_reference=None)).encode()
            receipts=[]
            for number in range(1,31):
                response=api.post('/v2/messages',content=command(number),headers=headers)
                assert response.status_code==200,(number,response.status_code,response.text)
                receipts.append(response.json()['receipt'])
            limited=api.post(route,content=dialogue('daily-limit'),headers=headers)
            assert limited.status_code==429 and limited.json()['error']['code']=='DEMO_DAILY_LIMIT',limited.text
            replay=api.post('/v2/messages',content=command(1),headers=headers)
            assert replay.status_code==200 and replay.json()['receipt']==receipts[0]
            scope=scope_for(ISSUER,SUBJECT)
            with psycopg.connect(**conninfo) as db:
                assert db.execute("SELECT count(*) FROM public.cj_message_receipt WHERE scope=%s AND demo_question_day=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",(scope,)).fetchone()==(40,)
                assert db.execute("SELECT has_table_privilege('cj_m1_runtime','cj_message_context_profile','INSERT')").fetchone()==(False,)
                periods=[ledger_scope_for(scope,p.meter) for p in following.profiles]
                assert db.execute('SELECT count(*) FROM public.cj_usage_ledger_candidate WHERE scope_id=ANY(%s)',(periods,)).fetchone()==(2,)
                for label,sql,parameters in (
                    ('invitation update','UPDATE public.cj_message_scope SET demo_revoked_at=clock_timestamp(),demo_session_floor=123 WHERE scope=%s',(scope,)),
                    ('receipt day update','UPDATE public.cj_message_receipt SET demo_question_day=demo_question_day-1 WHERE scope=%s',(scope,)),
                    ('invitation insert','INSERT INTO public.cj_message_scope(scope,demo_invite_digest,demo_invite_expires_at,demo_session_floor) VALUES (%s,%s,%s,0)',
                        (scope_for(ISSUER,'m4-synthetic-demo-001122334455'),digest(NEW_CODE),expiry)),
                ):
                    try:
                        with database.connect(parameters[0]) as runtime_connection:
                            runtime_connection.execute(sql,parameters)
                    except psycopg.errors.InsufficientPrivilege:pass
                    else:raise AssertionError('runtime changed protected state: '+label)
                db.execute("UPDATE public.cj_message_receipt SET demo_question_day=demo_question_day-1 WHERE scope=%s",(scope,))
            assert api.post('/v2/messages',content=command(31),headers=headers).status_code==200
            with psycopg.connect(**conninfo) as db:
                assert db.execute("SELECT count(*) FROM public.cj_message_receipt WHERE scope=%s AND demo_question_day=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",(scope,)).fetchone()==(1,)
    print('PASS signed zero-setup dialogue, concurrent original replay, default Travel, no downgrade, revoke, 40/day, migration data protection and Beijing day rollover')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-demo-',dir='/tmp') as temp:
        root=Path(temp)
        with pg_suites.cluster('demo',port=55649,role='cj_demo_init',root=root/'pg',socket=root/'s') as conninfo:
            with psycopg.connect(**conninfo,autocommit=True) as connection:
                migrations=migrate.load();migrate.up(connection,migrations,migrations[-1]['version'])
            for target in (50,51):
                with patch.object(migrate,'load',return_value=migrations[:target]):
                    with pg_suites.cluster('old-blueprint',port=55651,role='cj_demo_blueprint',
                            root=root/f'old-blueprint-{target}',socket=root/'old-blueprint-s') as previous:
                        with psycopg.connect(**previous,autocommit=True) as connection:
                            migrate.up(connection,migrations,target)
                        verify_upgrade(root/f'upgrade-{target}',previous,target)
            verify_upgrade(root/'upgrade-52',conninfo,52)
            exercise(root,conninfo)
