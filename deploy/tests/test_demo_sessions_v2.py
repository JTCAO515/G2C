from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

import dev_auth
from cj_api.local_app import ISSUER, scope_for
from deploy.hk import demo_login


SUBJECT='m4-synthetic-demo-0123456789ab'
OTHER='m4-synthetic-demo-abcdef012345'
OUTSIDE='m4-synthetic-outside'
CODE='D1-0123456789ab.'+'x'*22


class Database:
    def __init__(self,row):
        self.row=row
        self.scopes=[]

    @contextmanager
    def connect(self,scope):
        self.scopes.append(scope)
        yield self

    def execute(self,query,parameters):
        assert query.startswith('SELECT')
        assert parameters==(self.scopes[-1],)
        return self

    def fetchone(self):
        return self.row


@pytest.mark.parametrize('code',('G2C@999','CJ_Tester@998'))
def test_short_invite_real_socket_http_and_original_qualification(tmp_path,monkeypatch,code):
    monkeypatch.setenv('CJ_ENV','local')
    subject='m4-synthetic-demo-'+sha256(code.encode('ascii')).hexdigest()[:12]
    assert demo_login.invitation_subject(code)==subject
    auth=tmp_path/'auth';dev_auth.init(auth,[subject,OTHER])
    database=Database((sha256(code.encode('ascii')).hexdigest(),int(time.time())+8*86400,0))
    runtime=SimpleNamespace(auth=auth,demo_subjects=frozenset({subject}),database=lambda:database)
    original=database.row
    database.row=(sha256(b'different invitation').hexdigest(),original[1],0)
    assert demo_login.exchange(runtime,code) is None
    database.row=original
    runtime.demo_subjects=frozenset({OTHER})
    assert demo_login.exchange(runtime,code) is None
    runtime.demo_subjects=frozenset({subject})
    with tempfile.TemporaryDirectory(prefix='g2c-short-',dir='/tmp') as directory:
        app=FastAPI()
        @app.middleware('http')
        async def request_id(request:Request,call_next):
            request.state.request_id=str(uuid4())
            return await call_next(request)
        demo_login.register_demo_login(app)
        with patch.object(demo_login,'SOCKET',Path(directory)/'login.sock'),demo_login.signing_socket(runtime),TestClient(app) as api:
            for version,path in ((demo_login.VERSION,'v1'),(demo_login.ROLLING_VERSION,'v2')):
                response=api.post('/'+path+'/demo-invite-sessions',json=dict(version=version,invite_code=code,consent=True))
                assert response.status_code==200
                result=response.json();token=claims(result['access_token'])
                assert result['subject']==subject and result['version']==version
                assert token['sub']==subject and token['exp']<=database.row[1]
                assert response.headers['cache-control']=='no-store' and code not in response.text
            database.row=None
            denied=api.post('/v2/demo-invite-sessions',json=dict(version=demo_login.ROLLING_VERSION,invite_code=code,consent=True))
            assert denied.status_code==401 and code not in denied.text
    assert set(database.scopes)=={scope_for(ISSUER,subject)}


@pytest.mark.parametrize('code',('G2C@12','G2C@1234','g2c@123','CJ_Tester@12','CJ_Tester@1234','CJ_TESTER@123',' G2C@123','G2C@123\n','G2C@１２３','OTHER@123'))
def test_short_invite_exact_format(code):
    assert demo_login.invitation_subject(code) is None


def test_twelve_explicit_demo_subjects_remain_bounded(monkeypatch):
    from deploy.hk import configuration
    monkeypatch.setattr(configuration,'local_database_target',lambda:True)
    subjects=['m4-synthetic-demo-'+format(i,'012x') for i in range(12)]
    monkeypatch.setenv('CJ_BETA_SUBJECTS_JSON',json.dumps(subjects))
    monkeypatch.setenv(configuration.DEMO_SUBJECTS,json.dumps(subjects))
    assert configuration.beta_subjects()==(subjects,frozenset(subjects))
    subjects.append('m4-synthetic-demo-ffffffffffff')
    monkeypatch.setenv('CJ_BETA_SUBJECTS_JSON',json.dumps(subjects))
    monkeypatch.setenv(configuration.DEMO_SUBJECTS,json.dumps(subjects))
    with pytest.raises(ValueError,match='demo invitation subjects'):configuration.beta_subjects()


@pytest.fixture
def session_runtime(tmp_path,monkeypatch):
    monkeypatch.setenv('CJ_ENV','local')
    auth=tmp_path/'auth'
    dev_auth.init(auth,[SUBJECT,OTHER,OUTSIDE])
    database=Database((sha256(CODE.encode()).hexdigest(),int(time.time())+10*86400,0))
    return SimpleNamespace(auth=auth,demo_subjects=frozenset({SUBJECT,OTHER}),database=lambda:database),database


def claims(token):
    import base64
    middle=token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(middle+'='*(-len(middle)%4)))


def test_legacy_two_hour_and_seven_day_qualification_bound(session_runtime):
    runtime,database=session_runtime
    legacy=demo_login.exchange(runtime,CODE)
    long=demo_login.exchange(runtime,CODE,version=demo_login.ROLLING_VERSION)
    old,new=claims(legacy['access_token']),claims(long['access_token'])
    assert legacy['version']==demo_login.VERSION and 0<old['exp']-old['iat']<=7200
    assert long['version']==demo_login.ROLLING_VERSION and 604798<=new['exp']-new['iat']<=604800
    assert new['exp']<=database.row[1]
    database.row=(database.row[0],int(time.time())+30,0)
    short=demo_login.exchange(runtime,CODE,version=demo_login.ROLLING_VERSION)
    assert int(time.time())<claims(short['access_token'])['exp']<=database.row[1]


def test_valid_legacy_upgrade_and_actual_sliding_expiry(session_runtime):
    runtime,database=session_runtime
    legacy=demo_login.exchange(runtime,CODE)
    upgraded=demo_login.renew(runtime,legacy['access_token'])
    assert upgraded['subject']==SUBJECT and claims(upgraded['access_token'])['exp']>claims(legacy['access_token'])['exp']
    with patch.object(dev_auth,'time',SimpleNamespace(time=lambda:time.time()-86400)):
        older=dev_auth.token(runtime.auth,SUBJECT,7*24*60)
    renewed=demo_login.renew(runtime,older)
    assert claims(renewed['access_token'])['exp']-claims(older)['exp']>=86398
    assert renewed['subject']==SUBJECT and renewed['version']==demo_login.ROLLING_VERSION
    assert database.scopes and set(database.scopes)=={scope_for(ISSUER,SUBJECT)}


def test_expired_wrong_signature_tampering_and_outside_demo_are_denied(session_runtime,tmp_path):
    runtime,database=session_runtime
    with patch.object(dev_auth,'time',SimpleNamespace(time=lambda:time.time()-7202)):
        expired=dev_auth.token(runtime.auth,SUBJECT,120)
    different=tmp_path/'other-key'
    dev_auth.init(different,[SUBJECT])
    wrong_key=dev_auth.token(different,SUBJECT,30)
    valid=dev_auth.token(runtime.auth,SUBJECT,30)
    segments=valid.split('.')
    segments[1]=('A' if segments[1][0]!='A' else 'B')+segments[1][1:]
    for token in (expired,wrong_key,'.'.join(segments),dev_auth.token(runtime.auth,OUTSIDE,30)):
        assert demo_login.renew(runtime,token) is None
    assert database.scopes==[]


def test_renewal_cannot_choose_another_owner_and_old_floor_stays_revoked(session_runtime):
    runtime,database=session_runtime
    other=dev_auth.token(runtime.auth,OTHER,30)
    grant=demo_login.renew(runtime,other)
    assert grant['subject']==OTHER and database.scopes==[scope_for(ISSUER,OTHER)]
    token=dev_auth.token(runtime.auth,SUBJECT,30)
    database.row=(database.row[0],database.row[1],claims(token)['iat']+1)
    assert demo_login.renew(runtime,token) is None
    database.row=None
    assert demo_login.renew(runtime,token) is None


def test_parent_expiry_is_rechecked_after_the_policy_read(session_runtime):
    runtime,database=session_runtime
    token=dev_auth.token(runtime.auth,SUBJECT,1)
    expiry=claims(token)['exp']
    original=database.fetchone

    def delayed():
        demo_login.time=SimpleNamespace(time=lambda:expiry+1)
        return original()

    with patch.object(database,'fetchone',side_effect=delayed),patch.object(demo_login,'time',demo_login.time):
        assert demo_login.renew(runtime,token) is None


def test_real_private_socket_and_http_versions_errors_and_no_secret_echo(session_runtime,request):
    runtime,database=session_runtime
    temporary=tempfile.TemporaryDirectory(prefix='g2c-renew-',dir='/tmp')
    request.addfinalizer(temporary.cleanup)
    root=Path(temporary.name)
    app=FastAPI()

    @app.middleware('http')
    async def request_id(request:Request,call_next):
        request.state.request_id=str(uuid4())
        return await call_next(request)

    demo_login.register_demo_login(app)
    with patch.object(demo_login,'SOCKET',root/'login.sock'),demo_login.signing_socket(runtime),TestClient(app) as api:
        for version,path in ((demo_login.VERSION,'v1'),(demo_login.ROLLING_VERSION,'v2')):
            result=api.post('/'+path+'/demo-invite-sessions',json=dict(version=version,invite_code=CODE,consent=True))
            assert result.status_code==200 and result.json()['version']==version
            assert result.headers['cache-control']=='no-store'
        token=result.json()['access_token']
        route='/v2/demo-session-renewals'
        command=dict(version=demo_login.RENEW_VERSION)
        success=api.post(route,json=command,headers={'Authorization':'Bearer '+token})
        assert success.status_code==200 and success.json()['subject']==SUBJECT
        denied=api.post(route,json=command,headers={'Authorization':'Bearer invalid'})
        assert denied.status_code==401 and denied.json()['error']['code']=='DEMO_SESSION_DENIED'
        assert denied.headers['cache-control']=='no-store' and token not in denied.text
        forged=api.post(route,json=dict(command,subject=OTHER),headers={'Authorization':'Bearer '+token})
        assert forged.status_code==400 and forged.json()['error']['code']=='INVALID_INPUT'
        duplicate=api.post(route,content='{"version":"DEMO-session-renewal.1","version":"forged"}',
                           headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        assert duplicate.status_code==400
        with patch.object(demo_login,'renew',side_effect=ValueError('synthetic identity infrastructure unavailable')):
            unknown=api.post(route,json=command,headers={'Authorization':'Bearer '+token})
        assert unknown.status_code==503 and unknown.json()['error']['code']=='DEMO_SESSION_UNAVAILABLE'
        assert unknown.json()['error']['outcome']=='unknown' and unknown.headers['cache-control']=='no-store'
        assert token not in unknown.text and 'synthetic identity' not in unknown.text
        assert not (root/'private.pem').exists()
