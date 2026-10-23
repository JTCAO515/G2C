"""Narrow protected-read regressions against fixed canonical AUTH8b, real private PG."""
from dataclasses import replace
import json
import pytest
from cj_auth.admission import AdmissionChecker
from cj_auth.read_context import ProtectedReadBoundary
from cj_needs import Denied, OperationWithheld
from cj_needs.boundary import Operation
from cj_needs.protected_read import ProtectedReader, ReadConfiguration
from helpers import Identity, command, host, call


class Storage:
    def __init__(self, pg):
        self.pg, self.error, self.hook, self.closed = pg, None, None, 0
    def connect(self):
        owner = self
        class Connection:
            def __init__(self): self.base = owner.pg.connect()
            def __getattr__(self, name): return getattr(self.base, name)
            def close(self):
                self.base.close()
                owner.closed += 1
                if owner.hook: owner.hook()
                if owner.error: raise owner.error
        return Connection()


@pytest.fixture
def reader(pg, scope):
    b, _ = host(pg, scope)
    call(b, 'act', command('seed1'))
    call(b, 'act', command('seed2', 1, {'pace':{'state':'known','value':'慢 / relaxed'}}))
    identity = Identity()
    checker = AdmissionChecker(identity, identity)
    config = ReadConfiguration('synthetic-a', 'synthetic-only', 'cj013-test', 131072)
    storage = Storage(pg)
    # Keep the exact callable identity stable across repeated resolver calls.
    connect = storage.connect
    mapping = {'scope':scope}
    resolve = lambda principal, environment: (connect, mapping['scope'])
    protected = ProtectedReader(ProtectedReadBoundary(checker, max_response_bytes=131072),
                                resolve, configuration=config)
    return protected, storage, identity, mapping


def project(op, context):
    assert type(op) is Operation
    assert op.metadata.principal == context.principal
    first = op.detail('n1')
    revisions = [op.revision('n1', n) for n in range(1, first.version+1)]
    assert op.detail('n1') == first
    return json.dumps({'version':first.version, 'content':first.fields,
                       'sources':[r.original_input.decode('utf-8') for r in revisions]},
                      ensure_ascii=False).encode('utf-8')


def test_original_close_failure_probe_now_withheld(reader):
    protected, storage, _, _ = reader
    storage.error = RuntimeError('synthetic ordinary close failure')
    with pytest.raises(Exception): protected.read('synthetic', project)
    assert storage.closed == 1


def test_original_close_host_environment_scope_probe_now_withheld(reader):
    protected, storage, _, mapping = reader
    storage.hook = lambda: mapping.update(scope='different-host-scope')
    with pytest.raises(Exception): protected.read('synthetic', project)
    assert storage.closed == 1


def test_complete_bounded_original_bytes_and_history(reader):
    protected, storage, _, _ = reader
    out = protected.read('synthetic', project)
    assert type(out) is bytes and storage.closed == 4
    obj = json.loads(out)
    assert obj['version'] == 2
    for n, raw in enumerate(obj['sources'],1):
        assert raw.encode('utf-8') == command('seed1' if n==1 else 'seed2',n-1,
                    None if n==1 else {'pace':{'state':'known','value':'慢 / relaxed'}}).raw


@pytest.mark.parametrize('error', [KeyboardInterrupt(), SystemExit(), RuntimeError('close')])
def test_close_cancellation_and_error_no_bytes(reader,error):
    protected, storage, _, _ = reader
    storage.error=error
    with pytest.raises(BaseException): protected.read('synthetic',project)


def test_post_close_auth_revocation_and_identity_change(reader):
    protected, storage, identity, _=reader
    storage.hook=lambda:setattr(identity,'allowed',False)
    with pytest.raises(Exception): protected.read('synthetic',project)
    identity.allowed=True
    storage.hook=lambda:setattr(identity,'subject','other')
    with pytest.raises(Exception): protected.read('synthetic',project)


def test_projection_config_and_final_encoding_changes_denied(reader):
    protected, _, _, _=reader
    def changing(op,ctx):
        out=project(op,ctx)
        protected.configuration=replace(protected.configuration,environment='synthetic-b')
        return out
    with pytest.raises(Exception): protected.read('synthetic',changing)


def test_final_auth_callback_changes_configuration_withheld(reader):
    protected, _, identity, _=reader
    original=identity.evaluate
    count=0
    def evaluate(principal):
        nonlocal count
        count+=1
        if count==target:
            protected.configuration=replace(protected.configuration,environment='synthetic-b')
        return original(principal)
    identity.evaluate=evaluate
    # A no-read projection still runs exactly the same entry/final settlement gate.
    target=999999
    protected.read('synthetic',lambda op,ctx:b'{}')
    target=count*2
    with pytest.raises(Denied): protected.read('synthetic',lambda op,ctx:b'{}')
    assert count==target


def test_final_auth_callback_repo_binding_change_withheld(reader,monkeypatch):
    protected, _, identity, _=reader
    from cj_needs import protected_read
    real=protected_read.Repository
    captured=[]
    def capture(*args,**kwargs):
        repo=real(*args,**kwargs);captured.append(repo);return repo
    monkeypatch.setattr(protected_read,'Repository',capture)
    original=identity.evaluate
    arm=False
    count=0
    def evaluate(principal):
        nonlocal count
        count+=1
        if arm and count==target: captured[-1].scope='changed-after-final-auth'
        return original(principal)
    identity.evaluate=evaluate
    protected.read('synthetic',lambda op,ctx:b'{}')
    target=count*2;arm=True
    with pytest.raises(Denied): protected.read('synthetic',lambda op,ctx:b'{}')


def test_output_bound_exact_bytes_and_inactive_handles(reader):
    protected, _, _, _=reader
    captured=[]
    assert protected.read('synthetic',lambda op,ctx:captured.append((op,ctx)) or b'{}')==b'{}'
    with pytest.raises(OperationWithheld): captured[0][0].detail('n1')
    with pytest.raises(Exception): captured[0][1].require_current()
    protected.configuration=replace(protected.configuration,max_response_bytes=1)
    with pytest.raises(Denied): protected.read('synthetic',lambda op,ctx:b'{}')


@pytest.mark.parametrize('value',[{},bytearray(b'{}'), iter([b'{}'])])
def test_non_materialized_result_rejected(reader,value):
    with pytest.raises(Denied): reader[0].read('synthetic',lambda op,ctx:value)


def test_protected_operation_cannot_write_or_hide_failure(reader):
    protected,_,_,_=reader
    def forbidden(op,ctx):
        try: op.act(command('forbidden'))
        except Denied: pass
        return b'{}'
    with pytest.raises(Denied): protected.read('synthetic',forbidden)
    assert json.loads(protected.read('synthetic',project))['version']==2


def test_project_cancel_and_reentry_cannot_return_bytes(reader):
    protected,_,_,_=reader
    def cancel(op,ctx): raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): protected.read('synthetic',cancel)
    def reenter(op,ctx):
        try: protected.read('synthetic',lambda *_:b'{}')
        except Exception: pass
        return b'{}'
    with pytest.raises(Exception): protected.read('synthetic',reenter)
