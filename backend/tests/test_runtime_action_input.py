"""Exact target persistence only; no native business action/fee is performed."""
from contextlib import nullcontext
import os
from types import SimpleNamespace

import pytest

from cj_api.runtime_action_input import NativeActionInputs
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import encode


def test_native_target_is_exact_once_and_private_before_any_action(tmp_path):
    tmp_path.chmod(0o700);fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    request={'step_id':'original-step','kind':'lio_undo_current_trip','payload':{}}
    binding=Binding('owner','session','ledger','producer')
    claims=SimpleNamespace(binding=binding,read=lambda step,**kwargs:encode(request),
        claims=SimpleNamespace(_directory=lambda:nullcontext(fd)))
    store=NativeActionInputs(claims);target={'operation':'remember','opaque_target':'fixture-only'}
    try:
        store.record(request,target,deadline=30)
        path,=tmp_path.iterdir();assert path.stat().st_mode&0o777==0o600
        assert store.read(request,deadline=30)==target
        with pytest.raises(FileExistsError):store.record(request,{'opaque_target':'different'},deadline=30)
        assert store.read(request,deadline=30)==target
        with pytest.raises(Unavailable,match='CLAIM_CHANGED'):store.record({**request,'payload':{'changed':True}},target,deadline=30)
        path.write_bytes(b'{}')
        with pytest.raises(Invalid,match='BINDING_CHANGED'):store.read(request,deadline=30)
    finally:os.close(fd)
