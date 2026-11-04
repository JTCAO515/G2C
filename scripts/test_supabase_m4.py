import json
import uuid
import httpx
import pytest

import supabase_m4 as subject


def journal(tmp_path,monkeypatch):
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
