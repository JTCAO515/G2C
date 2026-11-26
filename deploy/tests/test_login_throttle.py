"""Failed invite sign-in throttle and long-code-only external testers (#1718)."""
import hashlib
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from starlette.datastructures import Headers

from deploy.hk import demo_accounts,demo_login,login_throttle
from deploy.hk.login_throttle import Throttle,client_key

LONG='D1-'+'a'*12+'.'+'B'*22


class Clock:
    def __init__(self):self.now=1000.0
    def __call__(self):return self.now


def test_client_key_trusts_only_one_clean_proxy_address():
    assert client_key(Headers(raw=[(b'x-forwarded-for',b'203.0.113.9')]))=='203.0.113.9'
    assert client_key(Headers(raw=[(b'x-forwarded-for',b'2001:db8:0:0::1')]))=='2001:db8::1'
    for raw in ([],[(b'x-forwarded-for',b'203.0.113.9, 198.51.100.1')],
                [(b'x-forwarded-for',b'203.0.113.9'),(b'x-forwarded-for',b'198.51.100.1')],[(b'x-forwarded-for',b'not-an-ip')]):
        assert client_key(Headers(raw=raw))=='unattributed'


def test_per_client_failures_lock_only_that_client_until_the_window_slides():
    clock=Clock();throttle=Throttle(clock=clock)
    assert all(throttle.reserve('a',short=False) for _ in range(login_throttle.PER_CLIENT))
    assert throttle.reserve('a',short=False) is None and throttle.reserve('b',short=False) is not None
    clock.now+=login_throttle.CLIENT_WINDOW
    assert throttle.reserve('a',short=False) is not None


def test_granted_sessions_release_only_their_own_reservation():
    throttle=Throttle(clock=Clock())
    for _ in range(20):throttle.release(throttle.reserve('a',short=False))
    failures=[throttle.reserve('a',short=False) for _ in range(login_throttle.PER_CLIENT)]
    assert all(failures) and throttle.reserve('a',short=False) is None
    throttle.release(failures[0]);assert throttle.reserve('a',short=False) is not None
    assert throttle.reserve('a',short=False) is None


def test_public_short_format_has_one_strict_global_window_long_codes_continue():
    clock=Clock();throttle=Throttle(clock=clock)
    for index in range(login_throttle.SHORT_GLOBAL):assert throttle.reserve(f'c{index}',short=True)
    assert throttle.reserve('fresh',short=True) is None and throttle.reserve('fresh',short=False) is not None
    clock.now+=login_throttle.SHORT_WINDOW
    assert throttle.reserve('fresh',short=True) is not None


def test_global_failures_and_client_table_are_bounded(monkeypatch):
    throttle=Throttle(clock=Clock())
    for index in range(login_throttle.GLOBAL):assert throttle.reserve(f'c{index}',short=False)
    assert throttle.reserve('fresh',short=False) is None
    monkeypatch.setattr(login_throttle,'MAX_CLIENTS',2);throttle=Throttle(clock=Clock())
    assert throttle.reserve('a',short=False) and throttle.reserve('b',short=False)
    assert throttle.reserve('c',short=False) is None and throttle.reserve('a',short=False) is not None


def app_with(exchange,monkeypatch):
    app=FastAPI()
    @app.middleware('http')
    async def request_id(request,call_next):
        request.state.request_id=str(uuid.uuid4());return await call_next(request)
    calls=[]
    def fake(code,*,version):
        calls.append(code);return exchange(code,version)
    monkeypatch.setattr(demo_login,'socket_exchange',fake)
    demo_login.register_demo_login(app,throttle=Throttle(clock=Clock()))
    return TestClient(app),calls


def login(api,code,address='203.0.113.9'):
    return api.post('/v2/demo-invite-sessions',json=dict(version=demo_login.ROLLING_VERSION,invite_code=code,consent=True),
                    headers={'X-Forwarded-For':address})


def granted(code,version):
    if code!=LONG:return None
    return dict(version=version,access_token='t',subject='m4-synthetic-demo-'+'a'*12,expires_at='2026-12-01T00:00:00Z')


def test_consecutive_wrong_codes_are_refused_before_the_signer(monkeypatch):
    api,calls=app_with(granted,monkeypatch)
    wrong='D1-'+'a'*12+'.'+'C'*22
    assert [login(api,wrong).status_code for _ in range(4)]==[401]*4
    assert login(api,'not a code').status_code==401
    refused=login(api,LONG)
    assert refused.status_code==503 and refused.json()['error']['code']=='DEMO_LOGIN_UNAVAILABLE'
    assert refused.headers['retry-after']==str(login_throttle.CLIENT_WINDOW) and refused.headers['cache-control']=='no-store'
    assert calls==[wrong]*4 and login(api,LONG,'198.51.100.7').status_code==200


def test_successful_sign_ins_never_lock_the_holder_out(monkeypatch):
    api,calls=app_with(granted,monkeypatch)
    assert all(login(api,LONG).status_code==200 for _ in range(3*login_throttle.PER_CLIENT))


def test_signer_outage_is_not_counted_as_a_wrong_code(monkeypatch):
    def down(code,version):raise OSError('signer unavailable')
    api,_=app_with(down,monkeypatch)
    assert all(login(api,LONG).status_code==503 for _ in range(3*login_throttle.PER_CLIENT))
    monkeypatch.setattr(demo_login,'socket_exchange',lambda code,*,version:granted(code,version))
    assert login(api,LONG).status_code==200


def test_public_short_codes_map_to_a_fixed_public_subject_set():
    assert len(demo_login.SHORT_CODES)==len(demo_login.SHORT_CODE_SUBJECTS)==len(demo_login.SHORT_CODE_DIGESTS)==198
    assert demo_login.invitation_subject('G2C@07') in demo_login.SHORT_CODE_SUBJECTS
    assert demo_login.invitation_subject(LONG) not in demo_login.SHORT_CODE_SUBJECTS


def test_external_testers_only_get_long_codes():
    short='G2C@07';short_subject=demo_login.invitation_subject(short);short_digest=hashlib.sha256(short.encode()).hexdigest()
    long_subject=demo_login.invitation_subject(LONG);long_digest=hashlib.sha256(LONG.encode()).hexdigest()
    demo_accounts.invitation_class(long_subject,long_digest,False)
    demo_accounts.invitation_class(short_subject,short_digest,True)
    with pytest.raises(ValueError,match='explicit_internal_short_code_choice_required'):
        demo_accounts.invitation_class(short_subject,short_digest,False)
    with pytest.raises(ValueError,match='explicit_internal_short_code_choice_required'):
        demo_accounts.invitation_class(long_subject,long_digest,True)
    with pytest.raises(ValueError,match='long_invite_code_required_for_external_testers'):
        demo_accounts.invitation_class(long_subject,short_digest,False)
