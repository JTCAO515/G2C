import json
import uuid
import httpx
import pytest

import supabase_m4 as subject


def journal(tmp_path,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    class SyntheticClock(datetime):
        @classmethod
        def now(cls,tz=None):
            value=datetime(2026,11,4,12,tzinfo=ZoneInfo('Asia/Shanghai'))
            return value if tz is None else value.astimezone(tz)
    monkeypatch.setattr(subject,'datetime',SyntheticClock)
    monkeypatch.setattr(subject,'STATE',tmp_path/'auth')
    return subject.AuthJournal()


def test_journal_allocates_exact_two_subjects_and_retains_original(tmp_path,monkeypatch):
    first=journal(tmp_path,monkeypatch)
    assert len(first.value['subjects'])==2
    assert all(item['email'].endswith('@example.invalid') for item in first.value['subjects'])
    rebuilt=subject.AuthJournal()
    assert not rebuilt.fresh and rebuilt.value==first.value
    assert 'password' not in first.path.read_text() and 'token' not in first.path.read_text()


def test_modified_subject_binding_is_rejected(tmp_path,monkeypatch):
    value=journal(tmp_path,monkeypatch)
    value.value['subjects'][0]['email']='not-owned@example.invalid';value.save()
    with pytest.raises(subject.TestUnavailable,match='binding'):subject.AuthJournal()


def test_incomplete_subjects_cannot_claim_completed_record(tmp_path,monkeypatch):
    value=journal(tmp_path,monkeypatch);value.value['complete']=True;value.save()
    with pytest.raises(subject.TestUnavailable,match='inconsistent'):subject.AuthJournal()


def test_auth_errors_never_echo_server_body_or_keys(tmp_path,monkeypatch):
    value=journal(tmp_path,monkeypatch)
    secret='sb_secret_synthetic_not_real'
    api=subject.AuthClient(secret,'sb_publishable_synthetic',value)
    api.client.close()
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(500,json={'message':secret})
    api.client=httpx.Client(transport=httpx.MockTransport(handler),trust_env=False)
    try:
        with pytest.raises(subject.TestUnavailable) as error:
            api.request('create_own_synthetic','POST','/admin/users',admin=True,body={'synthetic':True})
        assert secret not in str(error.value) and secret not in json.dumps(api.events)
        assert seen[0].headers['apikey']==secret and 'authorization' not in seen[0].headers
        assert value.value['calls']==1
    finally:api.close()


def test_cleanup_cannot_follow_a_changed_subject_id(tmp_path,monkeypatch):
    value=journal(tmp_path,monkeypatch)
    own=str(uuid.uuid4());different=str(uuid.uuid4())
    value.value['subjects'][0].update(id=own,state='created');value.save()
    class DB:
        def user_id(self,email):return different
    class API:
        def request(self,*args,**kwargs):raise AssertionError('must not call admin for another ID')
    with pytest.raises(subject.TestUnavailable,match='subject_changed'):
        subject.cleanup_auth(value,API(),DB())


def test_expired_authorization_refuses_before_http(tmp_path,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    value=journal(tmp_path,monkeypatch)
    monkeypatch.setattr(subject,'DEADLINE',datetime(2000,1,1,tzinfo=ZoneInfo('Asia/Shanghai')))
    api=subject.AuthClient('sb_secret_synthetic','sb_publishable_synthetic',value)
    try:
        with pytest.raises(subject.TestUnavailable,match='expired'):api.request('synthetic','GET','/health')
        assert value.value['calls']==0
    finally:api.close()


@pytest.mark.parametrize('known_id',[None,str(uuid.uuid4())])
def test_unknown_create_absence_does_not_claim_deletion(tmp_path,monkeypatch,known_id):
    value=journal(tmp_path,monkeypatch);value.value['subjects'][0].update(state='intent',id=known_id);value.save()
    class DB:
        def user_id(self,email):return None
    class API:
        def request(self,*args,**kwargs):raise AssertionError('must not send')
    assert subject.cleanup_auth(value,API(),DB())==['UNKNOWN_create_may_be_pending']
    assert value.value['subjects'][0]['state']=='intent'


def test_delete_timeout_is_not_sent_twice_or_blindly_replayed(tmp_path,monkeypatch):
    value=journal(tmp_path,monkeypatch);own=str(uuid.uuid4())
    value.value['subjects'][0].update(id=own,state='created');value.save()
    public=tmp_path/'public';public.write_text('sb_publishable_synthetic')
    monkeypatch.setattr(subject,'keychain',lambda name:'sb_secret_synthetic')
    original=httpx.Client;sent=[]
    def handler(request):sent.append(request.method);raise httpx.ReadTimeout('synthetic uncertainty')
    monkeypatch.setattr(subject.httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),trust_env=False))
    class DB:
        def user_id(self,email):return own if email.endswith('-a@example.invalid') else None
    result=subject.auth_test(DB(),public)
    assert sent==['DELETE'] and result['cleanup_status']=='UNKNOWN'
    again=subject.auth_test(DB(),public)
    assert sent==['DELETE'] and again['cleanup_status']=='UNKNOWN'
    assert subject.AuthJournal().value['subjects'][0]['state']=='deleting'


def test_ca_bundle_copies_only_the_fingerprinted_certificate(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.x509.oid import NameOID
    def certificate(name):
        key=Ed25519PrivateKey.generate();identity=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)])
        return (x509.CertificateBuilder().subject_name(identity).issuer_name(identity).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(datetime(2020,1,1,tzinfo=timezone.utc))
            .not_valid_after(datetime(2099,1,1,tzinfo=timezone.utc)).add_extension(x509.BasicConstraints(ca=True,path_length=None),True).sign(key,None))
    journal(tmp_path,monkeypatch)
    trusted,other=certificate('synthetic-pinned'),certificate('synthetic-extra')
    path=tmp_path/'bundle';path.write_bytes(trusted.public_bytes(serialization.Encoding.PEM)+other.public_bytes(serialization.Encoding.PEM))
    monkeypatch.setattr(subject,'CA_SHA',trusted.fingerprint(hashes.SHA256()).hex())
    monkeypatch.setattr(subject,'keychain',lambda name:'postgresql://postgres.'+subject.REF+':synthetic@'+subject.HOST+':5432/postgres')
    with subject.database_config(path) as config:
        loaded=x509.load_pem_x509_certificates(open(config['sslrootcert'],'rb').read())
        assert len(loaded)==1 and loaded[0].fingerprint(hashes.SHA256())==trusted.fingerprint(hashes.SHA256())


def test_refused_namespace_cannot_be_adopted_on_second_call(tmp_path,monkeypatch):
    from contextlib import nullcontext
    import migrate
    root=subject.Path(subject.__file__).resolve().parents[1]
    manifest=(root/'backend/migrations/manifest.json').read_bytes()
    monkeypatch.setattr(subject.subprocess,'check_output',lambda *args,**kwargs:manifest)
    monkeypatch.setattr(subject,'SCHEMA_STATE',tmp_path/'schema')
    monkeypatch.setattr(migrate,'applied',lambda conn:[])
    def refuse(*args):raise subject.TestUnavailable('fresh_public_namespace_required_before_quarantine')
    monkeypatch.setattr(subject,'quarantine_empty_public',refuse)
    entered=[];monkeypatch.setattr(migrate,'up',lambda *args:entered.append(True))
    class Connection:
        def transaction(self):return nullcontext()
    class DB:
        def check(self):pass
        def connect(self):return nullcontext(Connection())
    for _ in range(2):
        with pytest.raises(subject.TestUnavailable,match='fresh_public'):subject.migrate_test(DB(),apply=True)
    assert not entered and not (subject.SCHEMA_STATE/'state.json').exists()


def test_admitted_marker_with_empty_ledger_revalidates_namespace(tmp_path,monkeypatch):
    from contextlib import nullcontext
    import migrate,hashlib
    root=subject.Path(subject.__file__).resolve().parents[1];manifest=(root/'backend/migrations/manifest.json').read_bytes()
    monkeypatch.setattr(subject.subprocess,'check_output',lambda *args,**kwargs:manifest)
    folder=tmp_path/'schema';folder.mkdir();monkeypatch.setattr(subject,'SCHEMA_STATE',folder)
    (folder/'state.json').write_text(json.dumps(dict(project_ref=subject.REF,manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        admission='empty_namespace_quarantine_committed')))
    monkeypatch.setattr(migrate,'applied',lambda conn:[])
    checks=[]
    def refuse(*args):checks.append(True);raise subject.TestUnavailable('fresh_public_namespace_required_before_quarantine')
    monkeypatch.setattr(subject,'quarantine_empty_public',refuse)
    def forbidden(*args):raise AssertionError('must not enter migration')
    monkeypatch.setattr(migrate,'up',forbidden)
    class Connection:
        def transaction(self):return nullcontext()
    class DB:
        def check(self):pass
        def connect(self):return nullcontext(Connection())
    with pytest.raises(subject.TestUnavailable,match='fresh_public'):subject.migrate_test(DB(),apply=True)
    assert checks==[True]


def test_expiry_after_lock_stops_migration_before_connection(tmp_path,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    root=subject.Path(subject.__file__).resolve().parents[1];manifest=(root/'backend/migrations/manifest.json').read_bytes()
    monkeypatch.setattr(subject.subprocess,'check_output',lambda *args,**kwargs:manifest)
    monkeypatch.setattr(subject,'SCHEMA_STATE',tmp_path/'schema')
    def acquired(*args):monkeypatch.setattr(subject,'DEADLINE',datetime(2000,1,1,tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(subject.fcntl,'flock',acquired)
    def forbidden(*args,**kwargs):raise AssertionError('expired action reached driver')
    monkeypatch.setattr(subject.psycopg,'connect',forbidden)
    with pytest.raises(subject.TestUnavailable,match='expired'):subject.migrate_test(subject.Database({}),apply=True)


def test_each_connection_execute_rechecks_deadline(monkeypatch):
    class Raw:
        def execute(self,*args,**kwargs):raise AssertionError('must not reach driver')
    def expired():raise subject.TestUnavailable('authorization_expired')
    connection=subject.CheckedConnection(Raw(),subject.Database({},check=expired))
    with pytest.raises(subject.TestUnavailable,match='expired'):connection.execute('SELECT 1')
