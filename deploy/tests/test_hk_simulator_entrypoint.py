"""Exclusive simulator CLI and actual worker return wiring (local controls)."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from deploy.hk import entrypoint


@pytest.mark.parametrize('argv', [
    ['api','--simulator-manifest','/private/manifest.json'],
    ['migrate','--simulator-manifest','/private/manifest.json'],
    ['worker','--start-simulator'],
    ['worker','--simulator-manifest','/private/manifest.json','--runtime-manifest','/private/runtime.json'],
    ['worker','--simulator-manifest','/private/manifest.json','--app-smoke-manifest','/private/smoke.json'],
    ['worker','--simulator-manifest','/private/manifest.json','--tool-evidence-manifest','/private/evidence.json'],
    ['worker','--simulator-manifest','/private/manifest.json','--app-smoke-api-manifest','/private/http.json'],
])
def test_invalid_combination_refuses_before_loading_secrets(monkeypatch,argv):
    calls=[]
    monkeypatch.setattr(sys,'argv',['worker',*argv])
    monkeypatch.setattr(entrypoint,'load_secret_environment',lambda *a:calls.append(a))
    with pytest.raises(SystemExit) as error:entrypoint.main()
    assert error.value.code==2
    assert calls==[]


@pytest.mark.parametrize('start',[False,True])
def test_manifest_alone_never_implicitly_starts_actor(monkeypatch,tmp_path,start):
    from cj_api import runtime_simulator_host
    journal=tmp_path/'.local/share/g2c/m4-real-services/m4-outflows.sqlite'
    journal.parent.mkdir(parents=True);journal.touch()
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    events=[]
    @contextmanager
    def connect():yield 'original-journal'
    services=SimpleNamespace(model=SimpleNamespace(authorization=SimpleNamespace(
        connect=connect,require_producer=lambda db:events.append(('producer',db)))))
    monkeypatch.setattr(entrypoint.RealServices,'from_environment',lambda *a,**kw:services)
    tools=SimpleNamespace()
    monkeypatch.setattr(entrypoint,'RealTools',lambda *a,**kw:tools)
    for key in ('CJ_BETA_CONFIRMATION_B64',entrypoint.ASSEMBLY_PROBE_MESSAGE,entrypoint.MODEL_STREAM_SUBJECT):
        monkeypatch.delenv(key,raising=False)
    runtime=SimpleNamespace(auth='original-auth',demo_subjects=frozenset({'existing'}),
        assembly_model_stream_subjects=frozenset(),database=lambda:'original-database')
    class Host:
        def __init__(self,path,r,s,t):
            assert (path,r,s,t)==('/private/manifest.json',runtime,services,tools)
            events.append('construct')
        def begin(self):events.append('start')
    monkeypatch.setattr(runtime_simulator_host,'NativeSimulatorHost',Host)
    def loop(r,s,t,db,signer,bindings,**kw):
        assert db=='original-database' and bindings is kw['simulator']
        events.append('loop');return 'original-worker'
    monkeypatch.setattr(entrypoint,'_worker_loop',loop)
    assert entrypoint._run_worker(runtime,simulator_manifest='/private/manifest.json',
                                  start_simulator=start)=='original-worker'
    assert events==[('producer','original-journal'),'construct',*(['start'] if start else []),'loop']


def test_completion_witness_only_after_same_locked_run_once_returns(monkeypatch,tmp_path):
    from cj_api import rejected_intake_capture
    events=[]
    class EndLoop(Exception):pass
    class Lock:
        def __enter__(self):events.append('lock')
        def __exit__(self,*a):events.append('unlock')
    class Sink:
        def __init__(self,*a):pass
        def prune(self):pass
    @contextmanager
    def context(*a):yield
    monkeypatch.setattr(rejected_intake_capture,'RejectedIntakeSink',Sink)
    monkeypatch.setattr(rejected_intake_capture,'use_rejected_intake_sink',context)
    monkeypatch.setattr(entrypoint,'worker_pulse',context)
    monkeypatch.setattr(entrypoint,'_runtime_gate',lambda *a:None)
    monkeypatch.setattr(entrypoint,'heartbeat',lambda:tmp_path/'worker.json')
    monkeypatch.setattr(entrypoint.time,'sleep',lambda seconds:(_ for _ in ()).throw(EndLoop()))
    simulator=SimpleNamespace(execution_lock=Lock(),completed=lambda outcomes:events.append(('returned',outcomes)))
    def once(*args,**kw):
        assert events==['lock'];events.append('native-run')
        return []
    monkeypatch.setattr(entrypoint.run_worker,'run_once',once)
    runtime=SimpleNamespace(auth='original-auth',assembly_subjects=frozenset(),demo_subjects=frozenset(),
        assembly_run_credential_subjects=frozenset(),memory_runtime=None)
    services=SimpleNamespace(model='original-model')
    bindings=SimpleNamespace(registrations='original-registration',reflection='original-reflection',exit_observer=None)
    with pytest.raises(EndLoop):
        entrypoint._worker_loop(runtime,services,'original-tools','original-db',None,bindings,simulator=simulator)
    assert events==['lock','native-run',('returned',[]),'unlock']
