"""Private PostgreSQL and real JWT/Unix socket; no external model or account."""
import base64
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
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
from cj_api.local_app import ISSUER,LocalDatabase,create_local_app,scope_for
from cj_api.local_run_context import load_run_context
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from deploy.hk import checkpoint,demo_accounts,demo_login
from deploy.hk.configuration import Runtime,demo_periods
from cj_run.step_usage import ledger_scope_for
from cj_usage.authorization_budget import DEADLINE,DEMO_DEADLINE
import dev_auth
import migrate
import pg_suites

SUBJECT='m4-synthetic-demo-0123456789ab'
CODE='D1-0123456789ab.'+'x'*22
NEW_CODE='D1-0123456789ab.'+'y'*22


def digest(code):return hashlib.sha256(code.encode('ascii')).hexdigest()


def exercise(root,conninfo):
    auth=root/'auth'
    dev_auth.init(auth,[SUBJECT])
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
        app=create_local_app(conninfo_path=None,auth_dir=auth,run_context=context,database=database,account_admission=True)
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
            assert login(CODE).status_code==200
            assert demo_accounts.manage(runtime,'revoke',SUBJECT,control,operation)=='revoked'
            assert login(CODE).status_code==401
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
            for number in range(1,41):
                response=api.post('/v2/messages',content=command(number),headers=headers)
                assert response.status_code==200,(number,response.status_code,response.text)
                receipts.append(response.json()['receipt'])
            limited=api.post('/v2/messages',content=command(41),headers=headers)
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
            assert api.post('/v2/messages',content=command(41),headers=headers).status_code==200
            with psycopg.connect(**conninfo) as db:
                assert db.execute("SELECT count(*) FROM public.cj_message_receipt WHERE scope=%s AND demo_question_day=(clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date",(scope,)).fetchone()==(1,)
    print('PASS Demo signed login/socket, renewal/revoke/rotate, original profile, 40/day, replay and Beijing day rollover')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-demo-',dir='/tmp') as temp:
        root=Path(temp)
        with pg_suites.cluster('demo',port=55649,role='cj_demo_init',root=root/'pg',socket=root/'s') as conninfo:
            with psycopg.connect(**conninfo,autocommit=True) as connection:
                migrations=migrate.load();migrate.up(connection,migrations,migrations[-1]['version'])
            exercise(root,conninfo)
