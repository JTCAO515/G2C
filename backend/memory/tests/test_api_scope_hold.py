"""API policy/lifetime controls; actual native locks are covered separately."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from threading import Thread
from unittest.mock import patch
import pytest
from cj_auth.interfaces import TrustedPrincipal
from cj_api.local_app import ISSUER,scope_for
from cj_memory.api_scope_hold import ApiMemoryScopeHolder
from cj_memory.runtime import RuntimeDenied
from cj_memory.domain import Unavailable,CommitUnknown


def fixture():
    principal=TrustedPrincipal(ISSUER,'alice','aud',0,0,9999999999)
    state=dict(active=True,checks=0,held=False)
    def check():
        if not state['active']:raise RuntimeDenied('MESSAGE frame ended')
        state['checks']+=1
    frame=SimpleNamespace(principal=principal,scope=scope_for(ISSUER,'alice'),check=check)
    configuration=SimpleNamespace(collection=SimpleNamespace(profiles={'alice':SimpleNamespace(expires_at=datetime.now(timezone.utc)+timedelta(hours=1))}))
    class Memory:
        def lock_scope(self):return 7
    class Repo:
        def __init__(self,*a,**kw):pass
        @contextmanager
        def transaction(self):
            state['held']=True
            try:yield Memory()
            finally:state['held']=False
    return ApiMemoryScopeHolder(object(),configuration),frame,state,Repo


def test_actual_guard_and_lifetime_are_not_an_epoch_permit():
    holder,frame,state,repo=fixture()
    with patch('cj_memory.api_scope_hold.Repository',repo):
        with holder.hold(frame)as value:
            assert value.epoch==7 and state['held'];value.check()
        assert not state['held']
        with pytest.raises(RuntimeDenied):value.check()


def test_policy_expiry_and_original_M_withdrawal_withhold():
    for kind in ('policy','M'):
        holder,frame,state,repo=fixture()
        with patch('cj_memory.api_scope_hold.Repository',repo),pytest.raises(RuntimeDenied):
            with holder.hold(frame)as value:
                if kind=='M':state['active']=False
                else:holder.configuration.collection.profiles['alice'].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
                value.check()


def test_cross_owner_and_missing_profile_do_not_open_memory():
    for kind in ('owner','profile'):
        holder,frame,state,repo=fixture()
        if kind=='owner':frame.scope=scope_for(ISSUER,'bob')
        else:holder.configuration.collection.profiles.clear()
        with patch('cj_memory.api_scope_hold.Repository')as opened,pytest.raises(RuntimeDenied):
            with holder.hold(frame):pass
        opened.assert_not_called()


def test_thread_copy_cannot_extend_the_real_frame():
    holder,frame,state,repo=fixture();errors=[]
    with patch('cj_memory.api_scope_hold.Repository',repo),holder.hold(frame)as value:
        def other():
            try:value.check()
            except RuntimeDenied:errors.append(True)
        thread=Thread(target=other);thread.start();thread.join()
        assert errors==[True]


def test_missing_active_scope_is_not_initialized():
    holder,frame,state,repo=fixture()
    class Missing(repo):
        @contextmanager
        def transaction(self):
            yield SimpleNamespace(lock_scope=lambda:(_ for _ in()).throw(Unavailable('missing')))
    with patch('cj_memory.api_scope_hold.Repository',Missing),pytest.raises(RuntimeDenied):
        with holder.hold(frame):pass
