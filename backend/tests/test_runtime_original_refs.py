"""Opaque reference lifetime/corruption controls; no live AUTH/data/fees opened."""
import json
from types import SimpleNamespace

import pytest

from cj_api.runtime_original_refs import OriginalReferences
from runtime_adapter import Binding,Invalid,Unavailable


@pytest.fixture
def refs(tmp_path):
    directory=tmp_path/'refs';directory.mkdir(mode=0o700)
    state=dict(allowed=True,raw=b'private original synthetic bytes')
    def guard(**kwargs):
        if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_REVOKED')
    def original(*args,**kwargs):return state['raw']
    reader=SimpleNamespace(inventory=original,input=original,meter=original,fee=original,artifact=original)
    binding=Binding('original-owner','original-session','original-ledger','original-producer')
    return OriginalReferences(directory,binding,reader,guard=guard),state,directory,reader,binding,guard


def test_references_persist_only_bound_source_and_hash_not_private_bytes(refs):
    store,state,directory,reader,binding,guard=refs
    reference=store.issue('original-token',kind='input',message_id='original-mid',operation_id='original-op')
    path,=directory.iterdir()
    assert path.stat().st_mode&0o777==0o600
    assert state['raw'] not in path.read_bytes() and b'original-token' not in path.read_bytes()
    assert store.resolve('original-token',reference['ref'])==state['raw']
    assert store.issue('original-token',kind='input',message_id='original-mid',operation_id='original-op')==reference
    assert len(list(directory.iterdir()))==1
    rebuilt=OriginalReferences(directory,binding,reader,guard=guard)
    assert rebuilt.resolve('original-token',reference['ref'])==state['raw']


def test_changed_original_is_unknown_never_cached_as_success(refs):
    store,state,*_=refs
    ref=store.issue('token',kind='inventory',message_id='mid')
    state['raw']=b'original snapshot advanced'
    with pytest.raises(Unavailable,match='BYTES_CHANGED'):store.resolve('token',ref['ref'])


def test_new_owner_session_and_revocation_cannot_read_prior_reference(refs):
    store,state,directory,reader,binding,guard=refs
    ref=store.issue('token',kind='artifact',message_id='mid',operation_id='op')
    another=OriginalReferences(directory,Binding('original-owner','another-session','original-ledger','original-producer'),reader,guard=guard)
    with pytest.raises(Unavailable,match='OWNER_CHANGED'):another.resolve('token',ref['ref'])
    state['allowed']=False
    with pytest.raises(Unavailable,match='REVOKED'):store.resolve('token',ref['ref'])


def test_tampered_descriptor_or_arbitrary_path_is_rejected(refs):
    store,state,directory,*_=refs
    ref=store.issue('token',kind='wire_input',message_id='mid',operation_id='op')
    path,=directory.iterdir();record=json.loads(path.read_bytes());record['source']['message_id']='other-mid';path.write_text(json.dumps(record))
    with pytest.raises(Invalid,match='INTEGRITY'):store.resolve('token',ref['ref'])
    for value in ('../../private','https://example.invalid/original','file:///tmp/original'):
        with pytest.raises(Invalid,match='REFERENCE_ID'):store.resolve('token',value)


def test_auth_revoked_by_storage_callback_withholds_issued_reference(refs):
    store,state,directory,reader,*_=refs
    def revoked(*args):state['allowed']=False;return state['raw']
    reader.inventory=revoked
    with pytest.raises(Unavailable,match='REVOKED'):store.issue('token',kind='inventory',message_id='mid')
    assert state['raw'] not in next(directory.iterdir()).read_bytes()
