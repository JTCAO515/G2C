"""Canonical admission mechanics only; no real backend/window/fee qualification."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from threading import Barrier
from unittest.mock import patch

import pytest

from cj_api.runtime_claims import CanonicalClaims
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import VERSION,decode,digest,encode
from runtime_adapter.profiles import C0


@pytest.fixture
def context(tmp_path):
    directory=tmp_path/'canonical';directory.mkdir(mode=0o700)
    binding=Binding('original-owner','original-session','original-ledger','original-producer')
    pins=SimpleNamespace(key='a'*64)
    def build(*,bound=binding,guard=lambda **kwargs:None,exists=lambda step:False):
        return CanonicalClaims(directory,bound,pins,guard=guard,original_exists=exists,admission_lock=nullcontext)
    request=dict(version=VERSION,attempt_id='original-attempt',
        step_id='runtime-'+digest([binding.scope,'original-attempt',0]),binding_sha256=binding.key,
        pins_sha256=pins.key,kind='message',payload={'text':'Original synthetic message'},candidate=C0,prior_step_ids=[])
    return directory,binding,pins,build,encode(request)


def test_claim_sends_nothing_and_capability_is_request_bound_and_once(context):
    directory,binding,pins,build,raw=context
    store=build();claim=store.claim(raw)
    assert claim.fresh and claim.capability is not None
    path,=directory.iterdir();assert path.stat().st_mode&0o777==0o600
    assert path.read_bytes()==raw==store.read(decode(raw)['step_id'])
    changed=decode(raw);changed['candidate']={**C0,'prompt.answer_style':'Different voice'}
    with pytest.raises(Unavailable):store.consume(encode(changed),claim.capability)
    with pytest.raises(Unavailable):store.consume(raw,claim.capability)
    assert not store.claim(raw).fresh


def test_valid_capability_consumes_once_and_reconstruction_never_dispatches(context):
    directory,binding,pins,build,raw=context
    store=build();claim=store.claim(raw)
    assert store.consume(raw,claim.capability)==decode(raw)
    with pytest.raises(Unavailable):store.consume(raw,claim.capability)
    # Lose every G mapping and all process-local capability state.
    restored=build()
    assert not restored.claim(raw).fresh
    assert restored.read(decode(raw)['step_id'])==raw


def test_new_session_and_changed_candidate_do_not_mint_second_namespace(context):
    directory,binding,pins,build,raw=context
    assert build().claim(raw).fresh
    rotated=replace(binding,auth_session_id='rotated-original-session')
    request=decode(raw);request['binding_sha256']=rotated.key
    request['candidate']={**C0,'prompt.answer_style':'Another voice'}
    assert not build(bound=rotated).claim(encode(request)).fresh
    assert len(list(directory.iterdir()))==1


def test_existing_native_original_and_unknown_durable_claim_are_query_only(context):
    directory,binding,pins,build,raw=context
    assert not build(exists=lambda step:True).claim(raw).fresh
    assert list(directory.iterdir())==[]
    with patch('cj_api.runtime_claims.os.fsync',side_effect=OSError('synthetic fsync ACK loss')):
        with pytest.raises(OSError):build().claim(raw)
    assert not build().claim(raw).fresh
    assert len(list(directory.iterdir()))==1


def test_concurrent_canonical_claim_has_one_winner(context):
    directory,binding,pins,build,raw=context
    barrier=Barrier(2)
    def absent_before_both_claims(step):
        barrier.wait(timeout=5)
        return False
    stores=[build(exists=absent_before_both_claims),build(exists=absent_before_both_claims)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        result=list(executor.map(lambda store:store.claim(raw),stores))
    assert sum(claim.fresh for claim in result)==1
    assert len(list(directory.iterdir()))==1


def test_revoke_after_claim_keeps_original_and_withholds_capability(context):
    directory,binding,pins,build,raw=context
    count=0
    def guard(**kwargs):
        nonlocal count
        count+=1
        if count==2:raise Unavailable('ORIGINAL_AUTH_REVOKED')
    with pytest.raises(Unavailable):build(guard=guard).claim(raw)
    assert not build().claim(raw).fresh


def test_bad_canonical_id_owner_and_private_path_are_rejected(context):
    directory,binding,pins,build,raw=context
    for changes in ({'step_id':'arbitrary-id'},{'binding_sha256':'b'*64},{'prior_step_ids':['forged']}):
        with pytest.raises(Invalid):build().claim(encode({**decode(raw),**changes}))
    assert list(directory.iterdir())==[]
    directory.chmod(0o755)
    with pytest.raises(Unavailable):build()


def test_replaced_directory_and_tampered_original_do_not_reopen_claim(context):
    directory,binding,pins,build,raw=context
    store=build();claim=store.claim(raw)
    path,=directory.iterdir();path.write_bytes(b'corrupt original')
    with pytest.raises(Invalid):store.consume(raw,claim.capability)
    assert not store.claim(raw).fresh
    directory.rename(directory.with_name('retained'))
    directory.mkdir(mode=0o700)
    with pytest.raises(Unavailable,match='DIRECTORY_CHANGED'):store.claim(raw)
