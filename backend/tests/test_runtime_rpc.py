"""Real Unix socket/filesystem; controlled AUTH/adapter, no provider/fees."""
from hashlib import sha256
from types import SimpleNamespace
from pathlib import Path
import tempfile

import pytest

from cj_api import runtime_client
from cj_api.local_app import ISSUER,scope_for
from cj_api.runtime_rpc import RuntimeRPC,VERSION,runtime_socket
from cj_api.runtime_worker_bindings import pinned_directory
from cj_auth.interfaces import AdmissionStatus
from runtime_adapter import Binding,Invalid,Unavailable
from runtime_adapter.contract import decode,encode


@pytest.fixture
def rpc_fixture():
    token='fixture-token-not-a-live-credential';subject='m4-synthetic-unit'
    binding=Binding(scope_for(ISSUER,subject),sha256(token.encode()).hexdigest(),'original-ledger','original-producer')
    state=dict(allowed=True,calls=0)
    checker=SimpleNamespace(check=lambda supplied:SimpleNamespace(
        status=AdmissionStatus.ALLOWED if state['allowed'] else AdmissionStatus.DENIED,
        principal=SimpleNamespace(issuer=ISSUER,subject=subject)))
    def require(**kwargs):
        if not state['allowed']:raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
    def forbidden(*args,**kwargs):state['calls']+=1;raise AssertionError('training is not ready')
    authority=SimpleNamespace(checker=checker,require=require)
    pins=SimpleNamespace(key='a'*64,value={'original_model':'fixture'},c0=lambda:{'runtime_eligible':False})
    session=dict(line='E',binding=binding,authority=authority,adapter=SimpleNamespace(tasks={'dev-airport':{},'val-owner':{}},
        propose=forbidden,call=forbidden),backend=SimpleNamespace(),dialogue=SimpleNamespace(supported_tasks={'dev-airport'}))
    bindings=SimpleNamespace(by_scope={binding.scope:session},pins=pins)
    def request(method,params,*,bearer=token):return encode(dict(version=VERSION,token=bearer,method=method,params=params))
    return bindings,state,request,token


def test_exact_original_session_and_complete_setup_gate_precede_any_training(rpc_fixture):
    bindings,state,request,token=rpc_fixture;rpc=RuntimeRPC(bindings)
    params=dict(candidate={},feedback={},components=[],attempt_id='original-attempt',timeout=60)
    result=decode(rpc.handle(request('propose',params)))
    assert result['status']=='UNRUN' and result['reason']=='ALL_TASK_LEGAL_SETUPS_NOT_CONNECTED' and state['calls']==0
    with pytest.raises(Unavailable,match='AUTH_NOT_BOUND'):rpc.handle(request('c0',{},bearer='other-session'))
    with pytest.raises(Invalid,match='RPC_METHOD'):rpc.handle(request('c0',{'model':'caller-model'}))


def test_final_revocation_withholds_already_built_private_c0(rpc_fixture):
    bindings,state,request,token=rpc_fixture
    def revoke():state['allowed']=False;return {'runtime_eligible':False,'private':'must not escape'}
    bindings.pins.c0=revoke
    with pytest.raises(Unavailable,match='AUTH_UNAVAILABLE'):RuntimeRPC(bindings).handle(request('c0',{}))


def test_private_socket_and_one_shot_client_never_persist_bearer(rpc_fixture,tmp_path,monkeypatch):
    bindings,state,request,token=rpc_fixture;tmp_path.chmod(0o700)
    token_file=tmp_path/'identity.jwt';token_file.write_text(token);token_file.chmod(0o600)
    params=tmp_path/'params.json';params.write_bytes(encode({}));params.chmod(0o600)
    output=tmp_path/'result.json'
    with tempfile.TemporaryDirectory(prefix='g2c-rpc-',dir='/tmp') as short:
        endpoint=Path(short)/'runtime.sock';monkeypatch.setattr(runtime_client,'SOCKET',endpoint)
        with runtime_socket(bindings,endpoint):
            assert endpoint.stat().st_mode&0o777==0o600
            assert runtime_client.exchange(token_file,'c0',params,output)=='READ'
            assert decode(output.read_bytes())['training_status']=='UNRUN'
            with pytest.raises(FileExistsError):runtime_client.exchange(token_file,'c0',params,output)
    assert output.stat().st_mode&0o777==0o600 and token.encode() not in output.read_bytes()
    assert state['calls']==0 and not endpoint.exists()


def test_lost_connection_retains_unknown_intent_and_never_retries(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);token=tmp_path/'token';token.write_text('fixture-only');token.chmod(0o600)
    params=tmp_path/'params';params.write_bytes(encode({'attempt_id':'original-attempt'}));params.chmod(0o600)
    monkeypatch.setattr(runtime_client,'SOCKET',tmp_path/'absent.sock');output=tmp_path/'unknown.json'
    with pytest.raises(OSError):runtime_client.exchange(token,'query',params,output)
    result=decode(output.read_bytes())
    assert result['status']=='UNKNOWN' and result['attempt_id']=='original-attempt' and b'fixture-only' not in output.read_bytes()
    with pytest.raises(FileExistsError):runtime_client.exchange(token,'query',params,output)


def test_recreated_private_claim_directory_cannot_adopt_old_pin(tmp_path):
    path=tmp_path/'claims';path.mkdir(mode=0o700);info=path.stat()
    pin=dict(path=str(path),device=info.st_dev,inode=info.st_ino)
    assert pinned_directory(pin)==path
    path.rename(tmp_path/'retained-claims');path.mkdir(mode=0o700)
    with pytest.raises(Invalid,match='DIRECTORY_CHANGED'):pinned_directory(pin)
