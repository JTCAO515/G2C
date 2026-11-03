"""Real loader/HTTP/worker composition plus C-owned physical-erasure fixture."""
from contextlib import redirect_stdout
from dataclasses import replace
import importlib.util
import io,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from cj_api.local_app import app_from_environment,LocalDatabase,scope_for
from cj_api.local_cleanup import load_configuration,Runtime
from cj_api.local_worker_context import checker_for
from cj_auth.interfaces import AdmissionStatus,Fact
from cj_cleanup.account_hooks import MESSAGE,RUN,NEEDS,UsageHook
from cj_cleanup.core import encode,digest
from cj_memory_withdrawal.account_cleanup import account_hooks

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,cleanup_worker

# Independent expected inventory, not derived from the registry's available hooks.
INVENTORY=(
 'business/message','business/usage','business/memory-authoritative','business/trip-authoritative',
 'business/needs-current-planning','business/feedback-private-actions','business/cleanup-metadata',
 'business/memory-management-actions','checkpoints/run','memory-derived',
 'device-cache/encrypted-message-file','device-cache/sdk-session-keychain','device-cache/message-key-keychain',
 'device-cache/trip-pending-file','device-cache/offline-trip','device-cache/feedback-pending',
 'device-cache/feedback-key-keychain','device-cache/memory-manual-pending','device-cache/memory-lifecycle-pending',
 'device-cache/memory-typed-pending','device-cache/memory-key-keychain','device-cache/needs-pending',
 'device-cache/needs-key-keychain','device-cache/memory-history-pending','device-cache/trip-scoped-pending',
 'device-cache/needs-planning-pending','device-cache/trip-key-keychain','device-cache/offline-key-keychain',
 'device-cache/offline-write-residue','device-cache/memory-erasure-pending',
 'external-processing')
C_TARGETS={'business/memory-authoritative','business/memory-management-actions','business/trip-authoritative'}


def configuration_file(root,version,inventory,key=b'K'*32,key_id='local',ttl=3600):
    root.mkdir(parents=True,exist_ok=True);key_file=root/'cleanup.key'
    key_file.write_bytes(key);key_file.chmod(0o600)
    path=root/'cleanup.json';path.write_bytes(encode(dict(version=version,key_file=str(key_file),key_id=key_id,
        lifetime_seconds=ttl,inventory=list(inventory))))
    return path


def verify_binding(binding,inventory):
    assert set(binding.plan)==set(inventory)
    assert C_TARGETS<=set(binding.hooks)
    assert binding.hooks['business/message'].tables==MESSAGE
    assert binding.hooks['checkpoints/run'].tables==RUN
    assert binding.hooks['business/needs-current-planning'].tables==NEEDS
    assert isinstance(binding.hooks['business/usage'],UsageHook)
    assert 'memory-derived' in binding.hooks and 'business/cleanup-metadata' in binding.hooks
    assert all(t in binding.hooks for t in inventory if t.startswith('device-cache/'))


def exercise(root,path):
    # Reuse C's supplied seed/physical audit/race assertions, without editing C
    # source or inventing B SQL over C tables. Replace only its manual constructor
    # with the actual v2 file loader; its explicit component registry is retained.
    source=ROOT/'backend/memory_withdrawal/tests/account_hooks_pg.py'
    spec=importlib.util.spec_from_file_location('c_owned_account_fixture',source)
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    fixture_root=root/'owner-fixture';fixture_root.mkdir();loaded_components=[]
    def loaded_component(keys,key_id,lifetime,inventory,registry_path,clock=time.time,extra_hooks=None):
        assert extra_hooks is account_hooks and len(keys)==1
        config_path=configuration_file(root/'component-config','CJ-LOCAL-CLEANUP@2',inventory,key_id=key_id,ttl=lifetime)
        loaded=load_configuration(config_path)
        assert loaded.extra_hooks is account_hooks and loaded.inventory==tuple(inventory)
        loaded_components.append(loaded)
        return replace(loaded,registry_path=registry_path,clock=clock)
    with patch.object(fixture,'Configuration',loaded_component):fixture.exercise(fixture_root,path)
    assert len(loaded_components)==1
    print('PASS real V2 loader feeds C-owned signed physical-erasure/replay/foreign/bootstrap-race fixture; explicit component inventory is not whole-registry acceptance')

    auth=root/'host-auth';dev_auth.init(auth,['host-user'])
    token=dev_auth.token(auth,'host-user',30);headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'}
    full=configuration_file(root/'full-config','CJ-LOCAL-CLEANUP@3',INVENTORY)
    loaded=load_configuration(full);assert loaded.inventory==INVENTORY and loaded.extra_hooks is account_hooks
    database=LocalDatabase(path);principal=checker_for(auth).check(token).principal
    runtime=Runtime(database,loaded,scope_for);manifest=runtime.registry()
    assert not manifest.gaps and set(manifest.inventory)==set(INVENTORY)
    controls={'cleanup-control/selected','cleanup-control/manifest','cleanup-control/execution','cleanup-control/device','cleanup-control/account'}
    assert {name for name,_ in manifest.retained_controls}==controls
    binding=runtime.bind(principal);verify_binding(binding,INVENTORY)
    assert {e.registry_id for e in manifest.entries if not e.hook_available or e.registry_id not in binding.hooks}=={'external-processing'}
    old_full=configuration_file(root/'old-full-config','CJ-LOCAL-CLEANUP@2',INVENTORY)
    old_manifest=Runtime(database,load_configuration(old_full),scope_for).registry()
    assert set(old_manifest.gaps)==controls and not old_manifest.retained_controls
    assert not (controls & set(binding.plan)) and not (controls & set(binding.hooks))
    legacy_path=configuration_file(root/'legacy-config','CJ-LOCAL-CLEANUP@1',INVENTORY)
    legacy=load_configuration(legacy_path);assert legacy.extra_hooks is None and legacy.inventory==INVENTORY
    assert C_TARGETS.isdisjoint(Runtime(database,legacy,scope_for).bind(principal).hooks)

    # Formal environment entry: full registry/inventory remain intact. Missing
    # external proof must still block before retirement, rather than shrink scope.
    env=dict(CJ_ENV='local',CJ_LOCAL_CONNINFO=str(path),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CLEANUP_CONFIG=str(full))
    with patch.dict(os.environ,env),TestClient(app_from_environment()) as client:
        def post(url,value):
            response=client.post(url,content=encode(value),headers=headers)
            assert response.status_code==200,('formal cleanup HTTP',response.status_code)
            return response.json()
        device=post('/v3/cleanup-devices',dict(version='CLEANUP-DEVICE@3',action_id='register',device_id='host-device',state_ref=digest(b'host-state')))
        operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id']))
        progress=post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert progress['status']=='blocked' and progress['business_access']=='unchanged'
        assert {s['target'] for s in progress['steps']}==set(INVENTORY)
        assert all(s['state']=='pending' for s in progress['steps']) and progress['reason']=='domain_hooks_unavailable'
    assert runtime.retired(principal) is Fact.NO
    print('PASS actual app_from_environment V3 preserves all31 independent content targets and5 retained client controls; external blocks without retirement, old V2 full registry has5 real gaps, V1 remains uninstalled; no native finalization claimed')

    # Run the original worker main/argparse/loader/PG path. The observation wrapper
    # adds assertions only; no binding, hook, identity or outcome is substituted.
    observed=[]
    class ObservedRuntime(Runtime):
        def bind(self,principal):
            binding=super().bind(principal);verify_binding(binding,INVENTORY);observed.append(binding)
            return binding
    argv=['cleanup_worker.py','--conninfo-json',str(path),'--auth-dir',str(auth),'--cleanup-config',str(full),'--once']
    output=io.StringIO()
    with patch.object(sys,'argv',argv),patch.object(cleanup_worker,'Runtime',ObservedRuntime),redirect_stdout(output):cleanup_worker.main()
    assert len(observed)==1
    result=json.loads(output.getvalue());assert result['status']=='complete',result
    assert checker_for(auth).check(token).status is AdmissionStatus.ALLOWED
    print('PASS actual cleanup_worker.main --once uses V3/C factory and original retained-control profile; real diagnostic operation completes without account erasure or native-control confirmation')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-host-hooks-') as folder:
        exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
