"""Availability/owner checks stop before any paid preparatory action."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

import pytest

from cj_api.runtime_memory_setup import NativeMemorySetup
from runtime_adapter.contract import Unavailable


def setup(profile,*,scope='original-owner'):
    context=SimpleNamespace(scope=scope,principal=SimpleNamespace(subject='original-subject'))
    boundary=SimpleNamespace(with_history_context=lambda token,project:project(context))
    configuration=SimpleNamespace(collection=SimpleNamespace(profiles={'original-subject':profile}))
    claims=SimpleNamespace(binding=SimpleNamespace(scope='original-owner'))
    return NativeMemorySetup(claims,boundary,None,lambda:'fixture-token',configuration,None,None,None)


def profile():
    return SimpleNamespace(expires_at=datetime.now(timezone.utc)+timedelta(hours=1),subjects={'self'},
        extents={'long_term'},slots={name:SimpleNamespace(kind='preference',collection_allowed=True,semantic_resolved=True)
            for name in ('quiet.entrance','travel.pace')})


def test_only_existing_nonsensitive_legal_profile_is_available():
    current=profile();setup(current).require_available()
    del current.slots['travel.pace']
    with pytest.raises(Unavailable,match='LEGAL_PROFILE_NOT_AVAILABLE'):setup(current).require_available()
    current=profile();current.slots['travel.pace'].collection_allowed=False
    with pytest.raises(Unavailable,match='LEGAL_PROFILE_NOT_AVAILABLE'):setup(current).require_available()
    current=profile();current.slots['travel.pace'].semantic_resolved=False
    with pytest.raises(Unavailable,match='LEGAL_PROFILE_NOT_AVAILABLE'):setup(current).require_available()
    current=profile();current.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    with pytest.raises(Unavailable,match='LEGAL_PROFILE_NOT_AVAILABLE'):setup(current).require_available()


def test_another_verified_owner_cannot_supply_this_runtime_setup():
    with pytest.raises(Unavailable,match='ORIGINAL_OWNER_CHANGED'):
        setup(profile(),scope='another-owner').require_available()
