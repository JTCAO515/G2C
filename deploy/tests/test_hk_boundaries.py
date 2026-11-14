import base64
from datetime import datetime,timezone
import json
import hashlib
import io
import gzip
import os
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from cj_usage.authorization_budget import AuthorizationBudget,BudgetUnknown,HK_PRODUCER
from cj_usage import authorization_budget as budget_module
from deploy.hk import configuration,checkpoint,oss_backup


@pytest.mark.parametrize('demo',[False,True])
def test_hk_app_epoch_display_uses_api_policy_without_worker_configuration(tmp_path,monkeypatch,demo):
    from contextlib import nullcontext
    from fastapi import FastAPI
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.epoch_projection import CurrentScopeEpochReader
    from cj_memory import typed_api
    from cj_trip import local_needs_app,local_manual_app,local_structured_read
    from deploy.hk import demo_login
    who='m4-synthetic-demo-0123456789ab';subjects=frozenset({who})if demo else frozenset()
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={
        'travel.pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)})
    typed=TypedConfiguration.from_bytes(json.dumps(dict(version='local-memory-typed.1',
        collection=dict(version='local-memory-policy.1',expires_at='2099-12-31T00:00:00Z',
            profiles={who:profile}),travel_contexts={who:[]})).encode())if demo else None
    connection=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchone=lambda:(True,)))
    database=SimpleNamespace(connect=lambda scope:nullcontext(connection),travel_profile=lambda scope:True)
    runtime=configuration.Runtime(tmp_path,object(),tmp_path/'unused-context',[],typed_memory=typed,
        subjects=subjects,typed_message_subjects=subjects,demo_subjects=subjects)
    assert runtime.memory_runtime is None  # This is the real API-only shape.
    monkeypatch.setattr(runtime,'database',lambda:database)
    monkeypatch.setattr(configuration,'decoded',lambda name,*,length:b'x'*length)
    monkeypatch.setenv('CJ_LOCAL_NEEDS_PROFILE','manual-v1')
    monkeypatch.setattr(configuration,'assembly_cleanup',lambda db:None)
    monkeypatch.setattr(configuration,'register_assembly_erasure',lambda *args:None)
    for module,name in ((typed_api,'register_typed_routes'),(local_needs_app,'register_local_needs_routes'),
            (local_manual_app,'register_local_manual_routes'),
            (local_structured_read,'register_local_structured_read_routes'),(demo_login,'register_demo_login')):
        monkeypatch.setattr(module,name,lambda *args,**kwargs:None)
    calls=[];factory=CurrentScopeEpochReader.for_api
    def for_api(db,policy):
        calls.append((db,policy));return factory(db,policy)
    monkeypatch.setattr(CurrentScopeEpochReader,'for_api',for_api)
    supplied={}
    def create(**kwargs):supplied.update(kwargs);return FastAPI()
    monkeypatch.setattr(configuration,'create_local_app',create)
    runtime.app()
    assert supplied['lio_exploration_subjects']==(subjects or None)
    assert supplied['lio_dialogue_subjects']==supplied['lio_calendar_subjects']==(subjects or None)
    if demo:
        assert calls==[(database,typed)]
        assert type(supplied['lio_profile_epoch_reader'])is CurrentScopeEpochReader
    else:
        assert not calls and supplied['lio_profile_epoch_reader']is None
from scripts.m4_budget_transfer import seal,adopt
from scripts import m4_budget_transfer as transfer


@pytest.mark.parametrize('schema',[53,54])
def test_schema53_readiness_requires_its_completed_signed_anchor_and_keeps_quota_gate(tmp_path,monkeypatch,schema):
    from deploy.hk import demo_quota,entrypoint
    from contextlib import nullcontext
    key=Ed25519PrivateKey.generate()
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(
        key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,
                          serialization.NoEncryption())).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    raw=json.dumps({'current':{'meter':{'budget':800}}})
    policy=tmp_path/'context.json';policy.write_text(raw)
    runtime=SimpleNamespace(context_path=policy,context=SimpleNamespace(
        current=SimpleNamespace(meter=SimpleNamespace(budget=800))))
    database=SimpleNamespace(_open_runtime_connection=lambda:nullcontext(object()))
    monkeypatch.setattr(entrypoint,'authorization',lambda:None)
    monkeypatch.setattr(entrypoint,'local_database_target',lambda:True)
    monkeypatch.setattr(entrypoint,'control',lambda:tmp_path)
    monkeypatch.setattr(entrypoint.local_postgres,'require_serving',lambda control:None)
    monkeypatch.setattr(checkpoint,'require_release',lambda db,control:{'lineage':'original-lineage'})
    monkeypatch.setattr(checkpoint,'versions',lambda:list(range(1,schema+1)))
    checkpoint.atomic(tmp_path/'demo-schema52.json',dict(state='COMPLETE',lineage='original-lineage',
        quota_policy_sha256=demo_quota.policy_digest(raw,800)))
    for marker in ({'state':'INTENT','lineage':'original-lineage'},
                   {'state':'COMPLETE','lineage':'foreign-lineage'}):
        checkpoint.atomic(tmp_path/'demo-schema53.json',marker)
        with pytest.raises(ValueError,match='wire-origin cutover incomplete'):
            entrypoint._runtime_gate(database,runtime)
    checkpoint.atomic(tmp_path/'demo-schema53.json',dict(state='COMPLETE',lineage='original-lineage'))
    if schema==54:
        for marker in ({'state':'INTENT','lineage':'original-lineage'},
                       {'state':'COMPLETE','lineage':'foreign-lineage'}):
            checkpoint.atomic(tmp_path/'demo-schema54.json',marker)
            with pytest.raises(ValueError,match='exploration-origin cutover incomplete'):
                entrypoint._runtime_gate(database,runtime)
        checkpoint.atomic(tmp_path/'demo-schema54.json',dict(state='COMPLETE',lineage='original-lineage'))
    entrypoint._runtime_gate(database,runtime)
    runtime.context.current.meter.budget=80
    with pytest.raises(ValueError,match='quota cutover incomplete'):
        entrypoint._runtime_gate(database,runtime)


def test_typed_policy_encodings_preserve_bytes_and_reject_ambiguous_configuration(monkeypatch):
    raw=b'{"version":"local-memory-typed.1","same":"policy bytes"}'
    monkeypatch.delenv(configuration.TYPED_POLICY,raising=False)
    monkeypatch.delenv(configuration.TYPED_POLICY_GZIP,raising=False)
    monkeypatch.setenv(configuration.TYPED_POLICY,base64.b64encode(raw).decode())
    assert configuration.typed_policy_bytes()==raw
    monkeypatch.setenv(configuration.TYPED_POLICY_GZIP,base64.b64encode(gzip.compress(raw)).decode())
    with pytest.raises(ValueError,match='one_typed'):configuration.typed_policy_bytes()
    monkeypatch.delenv(configuration.TYPED_POLICY)
    assert configuration.typed_policy_bytes()==raw


@pytest.mark.parametrize('plain,field,decoder',[
    (configuration.TYPED_POLICY,configuration.TYPED_POLICY_GZIP,configuration.typed_policy_bytes),
    (configuration.MEMORY_RUN_POLICY,configuration.MEMORY_RUN_POLICY_GZIP,configuration.memory_run_policy_bytes)])
def test_compressed_typed_policy_retains_existing_decoded_bound_and_integrity(monkeypatch,plain,field,decoder):
    monkeypatch.delenv(plain,raising=False)
    exact=b'X'*262144;packed=gzip.compress(exact)
    monkeypatch.setenv(field,base64.b64encode(packed).decode())
    assert decoder()==exact
    bad=[gzip.compress(exact+b'X'),packed[:-4],packed+packed,packed+b'junk',b'not-gzip']
    corrupt=bytearray(packed);corrupt[-8]^=1;bad.append(bytes(corrupt))
    for value in bad:
        monkeypatch.setenv(field,base64.b64encode(value).decode())
        with pytest.raises(ValueError):decoder()


def test_worker_policy_encoding_is_explicit_and_stays_worker_only(tmp_path,monkeypatch):
    raw=b'{"same":"worker runtime policy"}'
    plain=base64.b64encode(raw).decode();packed=base64.b64encode(gzip.compress(raw)).decode()
    with patch.dict(os.environ,{configuration.MEMORY_RUN_POLICY:plain},clear=True):
        assert configuration.memory_run_policy_bytes()==raw
        monkeypatch.setenv(configuration.MEMORY_RUN_POLICY_GZIP,packed)
        with pytest.raises(ValueError,match='one_memory_run'):configuration.memory_run_policy_bytes()
    for role in ('worker','api'):
        text=''.join(name+'=fixture-only\n'for name in sorted(configuration.SECRET_FILES[role][role]))
        path=tmp_path/(role+'.env');path.write_text(text+configuration.MEMORY_RUN_POLICY_GZIP+'='+packed+'\n');path.chmod(0o600)
        with patch.dict(os.environ,{},clear=True):
            if role=='api':
                with pytest.raises(ValueError):configuration.load_secret_environment(role,root=tmp_path)
            else:
                configuration.load_secret_environment(role,root=tmp_path)
                assert configuration.memory_run_policy_bytes()==raw


def test_compressed_policy_enters_only_through_api_owned_secret_file(tmp_path):
    raw=b'{"same":"bounded policy"}'
    packed=base64.b64encode(gzip.compress(raw)).decode()
    def secret(role):
        names=configuration.SECRET_FILES[role][role]
        text=''.join(name+'=fixture-only\n'for name in sorted(names))
        path=tmp_path/(role+'.env')
        path.write_text(text+configuration.TYPED_POLICY_GZIP+'='+packed+'\n')
        path.chmod(0o600)
    secret('api')
    with patch.dict(os.environ,{},clear=True):
        configuration.load_secret_environment('api',root=tmp_path)
        assert configuration.typed_policy_bytes()==raw
    secret('worker')
    with patch.dict(os.environ,{},clear=True),pytest.raises(ValueError):
        configuration.load_secret_environment('worker',root=tmp_path)


def test_full_205_profile_policy_fits_secret_bound_without_changing_permissions(tmp_path):
    from cj_memory.typed_local import TypedConfiguration
    profile=dict(subjects=['self'],extents=['long_term','current'],context_ids=[],slots={
        name:dict(kind='preference',collection_allowed=True,semantic_resolved=True)
        for name in ('travel.pace','travel.budget','lodging.style','travel.interests','diet.taste')})
    subjects=['m4-synthetic-demo-'+format(i,'012x')for i in range(205)]
    value=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at='2026-12-31T00:00:00+00:00',profiles={s:profile for s in subjects}),
        travel_contexts={s:[]for s in subjects})
    raw=json.dumps(value,separators=(',',':')).encode()
    assert len(base64.b64encode(raw))>65536
    original=TypedConfiguration.from_bytes(raw)
    text=''.join(name+'=fixture-only\n'for name in sorted(configuration.SECRET_FILES['api']['api']))
    text+=configuration.TYPED_POLICY_GZIP+'='+base64.b64encode(gzip.compress(raw)).decode()+'\n'
    assert len(text.encode())<=65536
    path=tmp_path/'api.env';path.write_text(text);path.chmod(0o600)
    with patch.dict(os.environ,{},clear=True):
        configuration.load_secret_environment('api',root=tmp_path)
        decoded=TypedConfiguration.from_bytes(configuration.typed_policy_bytes())
    assert decoded==original and len(decoded.collection.profiles)==205
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    runtime=dict(version='local-memory-run.2',collection=value,selections={
        s:dict(subject='self',slots=list(profile['slots']),max_bytes=1000)for s in subjects})
    runtime_raw=json.dumps(runtime,separators=(',',':')).encode()
    assert len(base64.b64encode(runtime_raw))>65536
    text=''.join(name+'=fixture-only\n'for name in sorted(configuration.SECRET_FILES['worker']['worker']))
    text+=configuration.MEMORY_RUN_POLICY_GZIP+'='+base64.b64encode(gzip.compress(runtime_raw)).decode()+'\n'
    assert len(text.encode())<=65536
    path=tmp_path/'worker.env';path.write_text(text);path.chmod(0o600)
    with patch.dict(os.environ,{},clear=True):
        configuration.load_secret_environment('worker',root=tmp_path)
        decoded_runtime=TypedRuntimeConfiguration.from_bytes(configuration.memory_run_policy_bytes())
    assert decoded_runtime==TypedRuntimeConfiguration.from_bytes(runtime_raw)


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)


def activate(monkeypatch):
    monkeypatch.setattr(configuration,'datetime',Clock)
    for k,v in dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL='2026-11-20T00:00:00+00:00').items():monkeypatch.setenv(k,v)


def test_trial_and_explicit_environment_fail_closed(monkeypatch):
    activate(monkeypatch);configuration.authorization()
    monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-03T00:00:00+00:00')
    with pytest.raises(ValueError):configuration.authorization()
    monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-20T00:00:00+00:00');monkeypatch.setenv('CJ_ENV','production')
    with pytest.raises(ValueError):configuration.authorization()


def test_hk_pg_business_gate_requires_signed_forward_only_backup(tmp_path,monkeypatch):
    from deploy.hk import local_postgres
    key=Ed25519PrivateKey.generate()
    private=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(private).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(public).decode())
    monkeypatch.delenv('CJ_BETA_DB_TARGET',raising=False)
    local_postgres.require_serving(tmp_path)
    monkeypatch.setenv('CJ_BETA_DB_TARGET','hk-local')
    with pytest.raises(FileNotFoundError):local_postgres.require_serving(tmp_path)
    marker=tmp_path/local_postgres.STATE
    checkpoint.atomic(marker,dict(version='g2c-hk-local.1',state='BACKUP_REQUIRED'))
    with pytest.raises(ValueError,match='manual backup gate'):local_postgres.require_serving(tmp_path)
    checkpoint.atomic(marker,dict(version='g2c-hk-local.1',state='FORWARD_ONLY'))
    local_postgres.require_serving(tmp_path)
    value=json.loads(marker.read_bytes());value['value']['state']='BACKUP_REQUIRED';marker.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='signature'):local_postgres.require_serving(tmp_path)


def test_shared_budget_transfer_keeps_unknown_and_fences_stale_instances(tmp_path,monkeypatch):
    monkeypatch.setattr(transfer,'MAC_ROOT',tmp_path/'mac')
    monkeypatch.setattr(transfer,'HK_ROOT',tmp_path/'hk')
    monkeypatch.setattr(budget_module,'HK_JOURNAL_ROOT',tmp_path/'hk')
    monkeypatch.setattr(budget_module,'HK_ANCHOR',tmp_path/'control/budget/adoption.json')
    clock=lambda:Clock.now(timezone.utc)
    original=AuthorizationBudget(tmp_path/'mac',clock=clock)
    stale=AuthorizationBudget(tmp_path/'mac',clock=clock)
    original.begin('unknown-original','model',b'synthetic')
    original.begin('weather-original','weather',b'synthetic');original.finish('weather-original',{'status':'RECEIVED'})
    before=original.inspect();destination=tmp_path/'transferred.sqlite'
    sha=seal(original.path,destination)
    for budget in (original,stale,AuthorizationBudget(tmp_path/'mac',clock=clock)):
        with pytest.raises(BudgetUnknown):budget.begin('new-mac','model',b'synthetic')
        with pytest.raises(BudgetUnknown):budget.finish('unknown-original',{'status':'RECEIVED'})
        assert budget.inspect()==before
    activate(monkeypatch);monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER',HK_PRODUCER)
    with pytest.raises(ValueError):adopt(destination,'0'*64)
    adopt(destination,sha)
    root=tmp_path/'hk'
    moved=AuthorizationBudget(root,clock=clock);assert moved.inspect()==before
    with pytest.raises(BudgetUnknown):moved.begin('unknown-original','model',b'synthetic')
    original_live=(root/'m4-outflows.sqlite').read_bytes()
    moved.begin('new-hk','model',b'synthetic')
    assert len(moved.inspect())==3 and original.inspect()==before
    with pytest.raises(ValueError,match='no_replay'):adopt(destination,sha)
    with pytest.raises(ValueError,match='no_second_export'):seal(original.path,tmp_path/'second.sqlite')
    live=root/'m4-outflows.sqlite';saved=root/'live.saved';live.rename(saved)
    with pytest.raises(BudgetUnknown):AuthorizationBudget(root,clock=clock)
    with pytest.raises(ValueError,match='no_replay'):adopt(destination,sha)
    saved.rename(live)
    current=live.read_bytes();live.write_bytes(original_live)
    with pytest.raises(BudgetUnknown):AuthorizationBudget(root,clock=clock)
    live.write_bytes(current)
    updates=[0];write=budget_module.save_anchor
    def interrupted(value):
        updates[0]+=1
        if updates[0]==2:raise OSError('synthetic anchor completion ACK lost')
        return write(value)
    with patch.object(budget_module,'save_anchor',interrupted),pytest.raises(OSError):moved.begin('unknown-cross-store','model',b'synthetic')
    assert json.loads(budget_module.HK_ANCHOR.read_bytes())['state']=='WRITE_INTENT'
    with pytest.raises(BudgetUnknown):AuthorizationBudget(root,clock=clock)
    with pytest.raises(BudgetUnknown):moved.begin('unknown-cross-store','model',b'synthetic')


def test_budget_transfer_refuses_empty_and_wrong_original_paths(tmp_path,monkeypatch):
    root=tmp_path/'original';root.mkdir();source=root/'m4-outflows.sqlite';source.touch()
    monkeypatch.setattr(transfer,'MAC_ROOT',root)
    with pytest.raises(ValueError,match='schema_required'):seal(source,tmp_path/'export.sqlite')
    assert not (root/'transfer.json').exists() and not (tmp_path/'export.sqlite').exists()
    with pytest.raises(ValueError,match='fixed_original_source'):seal(tmp_path/'other.sqlite',tmp_path/'export.sqlite')


class Objects:
    def __init__(self,*,lose_ack=False):self.objects={};self.puts=0;self.lose_ack=lose_ack
    def head_object(self,request):
        if request.key not in self.objects:
            error=oss_backup.oss.exceptions.ServiceError(status_code=404,code='NoSuchKey',request_id='synthetic',message='missing',ec='',timestamp='',request_target='synthetic')
            raise oss_backup.oss.exceptions.OperationError(name='HeadObject',error=error)
        return self.objects[request.key]
    def get_object_acl(self,request):return SimpleNamespace(acl='private')
    def put_object(self,request):
        self.puts+=1
        assert request.bucket==oss_backup.BUCKET and request.acl=='private' and request.forbid_overwrite
        assert request.server_side_encryption=='AES256'
        data=request.body.read();assert len(data)==request.content_length
        self.objects[request.key]=SimpleNamespace(content_length=len(data),metadata=request.metadata,server_side_encryption='AES256')
        if self.lose_ack:raise TimeoutError('synthetic response lost after write')


def test_unknown_put_checks_original_head_and_never_reissues(tmp_path,monkeypatch):
    activate(monkeypatch);path=tmp_path/'database.dump';path.write_bytes(b'synthetic checkpoint')
    key='backups/20261104T000000Z-'+'a'*64+'/database.dump';journal=tmp_path/'intent.json';objects=Objects(lose_ack=True)
    with pytest.raises(TimeoutError):oss_backup.upload_file(objects,path,key,journal)
    assert json.loads(journal.read_bytes())['state']=='INTENT'
    assert oss_backup.upload_file(objects,path,key,journal)=='HEAD_CONFIRMED' and objects.puts==1
    objects.objects.clear()
    with pytest.raises(ValueError,match='unknown_no_resend'):oss_backup.upload_file(objects,path,key,journal)
    assert objects.puts==1


def test_backup_existing_object_mismatch_or_prefix_is_rejected(tmp_path,monkeypatch):
    activate(monkeypatch);path=tmp_path/'manifest.json';path.write_bytes(b'synthetic')
    objects=Objects();key='backups/20261104T000000Z-'+'a'*64+'/manifest.json'
    objects.objects[key]=SimpleNamespace(content_length=9,metadata={'sha256':'wrong'},server_side_encryption='AES256')
    with pytest.raises(ValueError):oss_backup.upload_file(objects,path,key,tmp_path/'journal.json')
    with pytest.raises(ValueError):oss_backup.upload_file(objects,path,'other-prefix/file',tmp_path/'journal.json')
    assert objects.puts==0


def test_checkpoint_signature_tamper_wrong_key_and_public_release(tmp_path,monkeypatch):
    activate(monkeypatch);key=Ed25519PrivateKey.generate()
    private=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(private).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(public).decode())
    path=tmp_path/'release.json';checkpoint.atomic(path,{'version':'synthetic'},public=True)
    assert path.stat().st_mode&0o777==0o644 and checkpoint.verified(path)=={'version':'synthetic'}
    value=json.loads(path.read_bytes());value['value']['version']='tampered';path.write_text(json.dumps(value))
    with pytest.raises(ValueError):checkpoint.verified(path)
    checkpoint.atomic(path,{'version':'synthetic'})
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(bytes(32)).decode())
    with pytest.raises(ValueError):checkpoint.verified(path)


def test_backup_download_validates_bytes_and_never_reissues_partial(tmp_path,monkeypatch):
    activate(monkeypatch);data=b'synthetic archive';sha=hashlib.sha256(data).hexdigest()
    key='backups/20261104T000000Z-'+sha+'/database.dump'
    class Download:
        calls=0
        def get_object_acl(self,request):return SimpleNamespace(acl='private')
        def get_object(self,request):
            self.calls+=1
            class Body(io.BytesIO):
                def iter_bytes(self,*,block_size):
                    while chunk:=self.read(block_size):yield chunk
            return SimpleNamespace(content_length=len(data),metadata={'sha256':sha},server_side_encryption='AES256',body=Body(data))
    service=Download();path=tmp_path/'database.dump'
    assert oss_backup.download_file(service,key,path,sha,limit=1024)=='GET_VERIFIED'
    assert oss_backup.download_file(service,key,path,sha,limit=1024)=='READ_ONLY_ORIGINAL' and service.calls==1
    path.write_bytes(b'partial')
    with pytest.raises(ValueError,match='unknown_no_resend'):oss_backup.download_file(service,key,path,sha,limit=1024)
    assert service.calls==1


def test_secret_environment_only_enters_process_after_owned_file_validation(tmp_path,monkeypatch):
    values={'CJ_SUPABASE_RUNTIME_URI':'synthetic-uri','CJ_BETA_CONFIRMATION_B64':'synthetic-confirm','CJ_BETA_HISTORY_B64':'synthetic-history'}
    path=tmp_path/'api.env';path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');path.chmod(0o644)
    with patch.dict(os.environ):
        with pytest.raises(ValueError,match='0600'):configuration.load_secret_environment('api',root=tmp_path)
        assert all(name not in os.environ for name in values)
        path.chmod(0o600);configuration.load_secret_environment('api',root=tmp_path)
        for name,value in values.items():assert os.environ[name]==value
        with pytest.raises(ValueError,match='persistent_container_secret'):configuration.load_secret_environment('api',root=tmp_path)


def test_typed_policy_is_optional_and_api_file_only(tmp_path):
    name='CJ_BETA_TYPED_MEMORY_POLICY_B64'
    required={'CJ_SUPABASE_RUNTIME_URI':'synthetic-uri','CJ_BETA_CONFIRMATION_B64':'synthetic-confirm','CJ_BETA_HISTORY_B64':'synthetic-history'}
    values={**required,name:'synthetic-private-policy'}
    path=tmp_path/'api.env';path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');path.chmod(0o600)
    with patch.dict(os.environ):
        for key in values:os.environ.pop(key,None)
        configuration.load_secret_environment('api',root=tmp_path)
        assert os.environ[name]==values[name]
        with pytest.raises(ValueError,match='persistent_container_secret'):
            configuration.load_secret_environment('api',root=tmp_path)
    # The existing mandatory credentials and rejection of unknown fields stay
    # binding; the policy is configuration, never a new worker credential.
    for change in ({name:'policy'}, {**required,'UNKNOWN_POLICY_FIELD':'policy'}):
        path.write_text('\n'.join(k+'='+v for k,v in change.items())+'\n')
        with patch.dict(os.environ):
            for key in values:os.environ.pop(key,None)
            with pytest.raises(ValueError):configuration.load_secret_environment('api',root=tmp_path)
    worker={k:'synthetic-value' for k in configuration.SECRET_FILES['worker']['worker']}
    path=tmp_path/'worker.env';path.write_text('\n'.join(k+'='+v for k,v in {**worker,name:'policy'}.items())+'\n');path.chmod(0o600)
    with patch.dict(os.environ):
        for key in {*worker,name}:os.environ.pop(key,None)
        with pytest.raises(ValueError):configuration.load_secret_environment('worker',root=tmp_path)


def test_typed_run_policy_requires_original_worker_file_and_mandatory_keys(tmp_path):
    name=configuration.MEMORY_RUN_POLICY
    credential=configuration.ASSEMBLY_RUN_CREDENTIAL_SUBJECTS
    streaming=configuration.ASSEMBLY_MODEL_STREAM_SUBJECTS
    required={k:'synthetic-value' for k in configuration.SECRET_FILES['worker']['worker']}
    path=tmp_path/'worker.env'
    for values,accepted in ((required,True),({**required,name:'synthetic-policy',credential:'[]',streaming:'[]'},True),
                            ({name:'synthetic-policy'},False),({**required,configuration.TYPED_POLICY:'wrong-role'},False)):
        path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');path.chmod(0o600)
        with patch.dict(os.environ):
            for key in {*required,name,credential,streaming,configuration.TYPED_POLICY}:os.environ.pop(key,None)
            if accepted:
                configuration.load_secret_environment('worker',root=tmp_path)
                assert all(os.environ[k]==v for k,v in values.items())
                with pytest.raises(ValueError,match='persistent_container_secret'):
                    configuration.load_secret_environment('worker',root=tmp_path)
            else:
                with pytest.raises(ValueError):configuration.load_secret_environment('worker',root=tmp_path)
                assert all(key not in os.environ for key in values)
    api={k:'synthetic-value' for k in configuration.SECRET_FILES['api']['api']}
    for worker_only in (name,credential,streaming):
        (tmp_path/'api.env').write_text('\n'.join(k+'='+v for k,v in {**api,worker_only:'wrong-role'}.items())+'\n')
        (tmp_path/'api.env').chmod(0o600)
        with patch.dict(os.environ):
            for key in {*api,worker_only}:os.environ.pop(key,None)
            with pytest.raises(ValueError):configuration.load_secret_environment('api',root=tmp_path)


def test_worker_typed_runtime_invites_role_and_database_capability(tmp_path,monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cj_api.local_app import scope_for,ISSUER
    activate(monkeypatch)
    who='m4-synthetic-worker-policy'
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    context=dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(meter=dict(unit='provider_call',budget=20,
        period_start=1,period_end=2000000000,max_steps=8,max_tools=1,max_output=5000,max_seconds=120),
        output_limits=dict(model=2000,tool=2000,memory=1000)))
    for k,v in dict(CJ_BETA_SUBJECTS_JSON=json.dumps([who]),CJ_BETA_RUN_CONTEXT_JSON=json.dumps(context),
        CJ_BETA_SIGNING_PRIVATE_B64=base64.b64encode(private).decode(),CJ_BETA_SIGNING_PUBLIC_B64=base64.b64encode(public).decode(),
        CJ_SUPABASE_RUNTIME_URI='synthetic-not-connected',CJ_SUPABASE_CA_FILE='synthetic-not-opened').items():monkeypatch.setenv(k,v)
    monkeypatch.delenv(configuration.TYPED_POLICY,raising=False)
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                 extents=['long_term','current'],context_ids=[])
    collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at='2099-11-30T23:59:59+08:00',profiles={who:profile}),travel_contexts={who:[]})
    policy=dict(version='local-memory-run.2',collection=collection,selections={who:dict(subject='self',slots=['preference'],max_bytes=1000)})
    def choose(value):monkeypatch.setenv(configuration.MEMORY_RUN_POLICY,base64.b64encode(json.dumps(value).encode()).decode())
    # A private, immediately unlinked descriptor keeps this test portable to Mac.
    # The Linux runtime_check separately verifies native memfd -> signing token.
    def descriptor(*args):
        p=tmp_path/'unlinked-signing';fd=os.open(p,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);p.unlink();return fd
    monkeypatch.setattr(configuration.os,'memfd_create',descriptor,raising=False)
    choose(policy)
    with pytest.raises(ValueError,match='worker_only'):configuration.Runtime.load(tmp_path/'wrong-api')
    runtime=configuration.Runtime.load(tmp_path/'valid',worker=True)
    try:
        assert runtime.typed_memory is None
        assert runtime.memory_configuration_for_scope(scope_for(ISSUER,who)) is runtime.memory_runtime
        assert runtime.memory_configuration_for_scope(scope_for(ISSUER,'m4-synthetic-other')) is None
        with patch.object(configuration,'SupabaseTestDatabase') as database:
            runtime.database();assert database.call_args.kwargs['travel_context'] is True
    finally:runtime.close()
    bad=json.loads(json.dumps(policy));bad['collection']['collection']['profiles']['m4-synthetic-unselected']=profile
    bad['collection']['travel_contexts']['m4-synthetic-unselected']=[];choose(bad)
    with pytest.raises(ValueError,match='explicit_memory_run_selection'):configuration.Runtime.load(tmp_path/'unselected',worker=True)
    bad=json.loads(json.dumps(policy));bad['selections']['m4-synthetic-foreign']=bad['selections'].pop(who)
    bad['collection']['collection']['profiles']={'m4-synthetic-foreign':profile};bad['collection']['travel_contexts']={'m4-synthetic-foreign':[]};choose(bad)
    with pytest.raises(ValueError,match='explicit_memory_run_selection'):configuration.Runtime.load(tmp_path/'foreign',worker=True)
    choose(dict(policy,version='UNKNOWN'))
    with pytest.raises(ValueError):configuration.Runtime.load(tmp_path/'unknown',worker=True)
    choose(policy);monkeypatch.setenv(configuration.TYPED_POLICY,base64.b64encode(json.dumps(collection).encode()).decode())
    with pytest.raises(ValueError,match='API_only'):configuration.Runtime.load(tmp_path/'mixed',worker=True)
    monkeypatch.delenv(configuration.MEMORY_RUN_POLICY);monkeypatch.delenv(configuration.TYPED_POLICY)
    runtime=configuration.Runtime.load(tmp_path/'default',worker=True)
    try:
        assert runtime.memory_runtime is None and runtime.memory_configuration_for_scope(scope_for(ISSUER,who)) is None
        with patch.object(configuration,'SupabaseTestDatabase') as database:
            runtime.database();assert database.call_args.kwargs['travel_context'] is False
    finally:runtime.close()

    pair=['m4-synthetic-660-0123456789ab-'+language for language in ('zh','en')]
    monkeypatch.setenv('CJ_BETA_SUBJECTS_JSON',json.dumps([who,*pair]))
    monkeypatch.setenv(configuration.ASSEMBLY_SUBJECTS,json.dumps(pair))
    for subject in pair:
        collection['collection']['profiles'][subject]=profile
        collection['travel_contexts'][subject]=[]
        policy['selections'][subject]=policy['selections'][who]
    choose(policy)
    runtime=configuration.Runtime.load(tmp_path/'assembly-default',worker=True)
    try:assert runtime.assembly_run_credential_subjects==runtime.assembly_model_stream_subjects==frozenset()
    finally:runtime.close()
    name=configuration.ASSEMBLY_RUN_CREDENTIAL_SUBJECTS
    for invalid in ([],pair[:1],[pair[0],pair[0]],[who,pair[1]],[*pair,who]):
        monkeypatch.setenv(name,json.dumps(invalid))
        with pytest.raises(ValueError,match='assembly_run_credential_pair'):
            configuration.Runtime.load(tmp_path/'invalid-credential-pair',worker=True)
    monkeypatch.setenv(name,json.dumps(pair[::-1]))
    with pytest.raises(ValueError,match='assembly_run_credential_pair'):
        configuration.Runtime.load(tmp_path/'wrong-credential-role')
    runtime=configuration.Runtime.load(tmp_path/'approved-credential-pair',worker=True)
    try:assert runtime.assembly_run_credential_subjects==frozenset(pair)
    finally:runtime.close()
    name=configuration.ASSEMBLY_MODEL_STREAM_SUBJECTS
    for invalid in ([],pair[:1],[pair[0],pair[0]],[who,pair[1]],[*pair,who]):
        monkeypatch.setenv(name,json.dumps(invalid))
        with pytest.raises(ValueError,match='assembly_model_stream_pair'):
            configuration.Runtime.load(tmp_path/'invalid-stream-pair',worker=True)
    monkeypatch.setenv(name,json.dumps(pair))
    runtime=configuration.Runtime.load(tmp_path/'approved-stream-pair',worker=True)
    try:assert runtime.assembly_model_stream_subjects==frozenset(pair)
    finally:runtime.close()
    monkeypatch.delenv(configuration.ASSEMBLY_RUN_CREDENTIAL_SUBJECTS)
    with pytest.raises(ValueError,match='assembly_model_stream_pair'):
        configuration.Runtime.load(tmp_path/'wrong-stream-role')


def test_api_typed_message_subjects_require_private_policy_and_role(tmp_path,monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    activate(monkeypatch)
    a,b='m4-synthetic-gate-a','m4-synthetic-gate-b'
    public=rsa.generate_private_key(public_exponent=65537,key_size=2048).public_key().public_bytes(
        serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    context=dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(meter=dict(unit='provider_call',budget=20,
        period_start=1,period_end=2000000000,max_steps=8,max_tools=1,max_output=5000,max_seconds=120),
        output_limits=dict(model=2000,tool=2000,memory=1000)))
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
        extents=['long_term','current'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at='2099-11-30T23:59:59+08:00',profiles={b:profile}),travel_contexts={b:[]})
    for k,v in dict(CJ_BETA_SUBJECTS_JSON=json.dumps([a,b]),CJ_BETA_RUN_CONTEXT_JSON=json.dumps(context),
        CJ_BETA_SIGNING_PUBLIC_B64=base64.b64encode(public).decode()).items():monkeypatch.setenv(k,v)
    monkeypatch.delenv(configuration.MEMORY_RUN_POLICY,raising=False)
    monkeypatch.setenv(configuration.TYPED_POLICY,base64.b64encode(json.dumps(policy).encode()).decode())
    for selected in ({},None,[],[b,b],[a],['m4-synthetic-uninvited'],b):
        monkeypatch.setenv(configuration.TYPED_MESSAGE_SUBJECTS,json.dumps(selected))
        with pytest.raises(ValueError,match='explicit_typed_message_policy'):
            configuration.Runtime.load(tmp_path/'invalid')
    monkeypatch.setenv(configuration.TYPED_MESSAGE_SUBJECTS,json.dumps([b]))
    runtime=configuration.Runtime.load(tmp_path/'valid')
    try:assert runtime.typed_message_subjects==frozenset((b,))
    finally:runtime.close()
    # The same opt-in cannot enter Config.Env or the worker's private file.
    required={k:'synthetic-value' for k in configuration.SECRET_FILES['api']['api']}
    values={**required,configuration.TYPED_MESSAGE_SUBJECTS:json.dumps([b])}
    (tmp_path/'api.env').write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');(tmp_path/'api.env').chmod(0o600)
    with patch.dict(os.environ):
        for key in {*values,configuration.TYPED_POLICY}:os.environ.pop(key,None)
        configuration.load_secret_environment('api',root=tmp_path)
        assert os.environ[configuration.TYPED_MESSAGE_SUBJECTS]==json.dumps([b])
    monkeypatch.delenv(configuration.TYPED_POLICY)
    with pytest.raises(ValueError,match='explicit_typed_message_policy'):configuration.Runtime.load(tmp_path/'missing-policy')
    with pytest.raises(ValueError,match='API_only'):configuration.Runtime.load(tmp_path/'worker',worker=True)
    worker={k:'synthetic-value' for k in configuration.SECRET_FILES['worker']['worker']}
    (tmp_path/'worker.env').write_text('\n'.join(k+'='+v for k,v in {**worker,configuration.TYPED_MESSAGE_SUBJECTS:'[]'}.items())+'\n')
    (tmp_path/'worker.env').chmod(0o600)
    with patch.dict(os.environ):
        for key in {*worker,configuration.TYPED_MESSAGE_SUBJECTS}:os.environ.pop(key,None)
        with pytest.raises(ValueError):configuration.load_secret_environment('worker',root=tmp_path)


def test_trial_expiry_at_final_model_and_fact_guard_sends_nothing(tmp_path,monkeypatch):
    import asyncio
    import httpx
    from unittest.mock import AsyncMock
    from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,ProviderUnknown
    from cj_api.real_services import RealServices,RealTools,ModelInput,TOOL_SYSTEM
    activate(monkeypatch)
    now=[datetime(2026,11,4,tzinfo=timezone.utc)]
    class MovingClock(datetime):
        @classmethod
        def now(cls,tz=None):return now[0]
    monkeypatch.setattr(configuration,'datetime',MovingClock)
    monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-04T00:00:01+00:00')
    budget=AuthorizationBudget(tmp_path,authorization_guard=configuration.authorization)
    sent=[]
    def forbidden(request):sent.append(request);raise AssertionError('expired send')
    provider=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'synthetic-model-key-000000'),budget,
        transport=httpx.MockTransport(forbidden))
    services=RealServices(provider,'synthetic-amap-key-000000',frozenset({'m4-synthetic-trial'}))
    tools=RealTools(services)
    operation=SimpleNamespace(binding=SimpleNamespace(scope='local:https://local.g2c.invalid:m4-synthetic-trial'),
        command=SimpleNamespace(attempt_id='trial-model'))
    prepared=tools._model_input(ModelInput([dict(role='user',content='Synthetic trial boundary')],TOOL_SYSTEM,provider,{}))
    def expired_guard():now[0]=datetime(2026,11,4,0,0,2,tzinfo=timezone.utc);return True
    with pytest.raises(ProviderUnknown):list(prepared.bind_operation(operation,expired_guard)())
    assert sent==[] and [(r['kind'],r['state']) for r in budget.inspect()]==[('model','INTENT')]
    now[0]=datetime(2026,11,4,tzinfo=timezone.utc)
    raw=json.dumps(dict(version='FACT-query.1',fact_key='entry_notice',region='China',dates=dict(start='2026-11-04',end='2026-11-04'),conditions={})).encode()
    prepared=tools._tool_input('fact',(raw,'synthetic-trial-ref'))
    operation.command.attempt_id='trial-fact'
    async def dns(*args,**kwargs):return [(2,1,6,'',('93.184.216.34',443))]
    with patch('asyncio.BaseEventLoop.getaddrinfo',dns),patch('cj_fact.live_source.PinnedHTTPSTransport.__call__',new_callable=AsyncMock) as send:
        with pytest.raises(BudgetUnknown):list(prepared.bind_operation(operation,expired_guard)())
        send.assert_not_called()
    assert [(r['kind'],r['state']) for r in budget.inspect()]==[('model','INTENT'),('fact','INTENT')]


def test_worker_pulse_keeps_queries_and_stop_gate_available_during_dispatch(tmp_path,monkeypatch):
    import time
    from deploy.hk import entrypoint
    activate(monkeypatch);monkeypatch.setenv('CJ_DEPLOY_HEARTBEAT',str(tmp_path))
    monkeypatch.setenv('CJ_DEPLOY_CONTROL',str(tmp_path/'control'))
    now=[100.0];monkeypatch.setattr(entrypoint.time,'time',lambda:now[0])
    database=SimpleNamespace(_open_runtime_connection=lambda:nullcontext(None))
    from contextlib import nullcontext
    with patch.object(entrypoint.checkpoint,'require_release',return_value=None),entrypoint.worker_pulse():
        deadline=time.monotonic()+6
        while not (tmp_path/'worker.json').exists() and time.monotonic()<deadline:time.sleep(.01)
        assert entrypoint.ready(database) is None
        now[0]=120.0
        # This is the same worker pulse while its dispatch body is still blocked.
        assert entrypoint.ready(database)=='worker_heartbeat_stale'
        while json.loads((tmp_path/'worker.json').read_bytes())['at']<120 and time.monotonic()<deadline:time.sleep(.01)
        assert entrypoint.ready(database) is None


def test_recovery_preserves_existing_target_gate_before_any_source_failure(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from deploy.hk import schema,staging
    source=tmp_path/'source';target=tmp_path/'target';source.mkdir();target.mkdir()
    release=target/'release.json';release.write_bytes(b'original untouched release')
    @contextmanager
    def failed_operator():
        raise ValueError('synthetic source unavailable')
        yield
    monkeypatch.setattr(checkpoint,'operator',failed_operator)
    monkeypatch.setattr(schema,'load',lambda root:{})
    config=dict(host='/tmp/synthetic-unconnected-only',dbname='postgres',user='synthetic')
    with pytest.raises(ValueError,match='source unavailable'):
        checkpoint.restore(config,tmp_path/'base',tmp_path/'safety',source,target,schema_root=tmp_path)
    assert release.read_bytes()==b'original untouched release'
    with pytest.raises(ValueError,match='distinct_isolated_control'):
        checkpoint.restore(config,tmp_path/'base',tmp_path/'safety',target,target,schema_root=tmp_path)
    assert release.read_bytes()==b'original untouched release'
    from unittest.mock import MagicMock
    connection=MagicMock()
    with pytest.raises(ValueError,match='owned_fresh_PG17_cluster'):
        staging.require_isolated(connection,config)
    connection.execute.assert_not_called()


def test_resume_wrong_data_system_id_never_starts_or_stops_postgres(tmp_path,monkeypatch):
    from deploy.hk import staging
    root=tmp_path/'original';root.mkdir(mode=0o700);data=root/'data';data.mkdir(mode=0o700);(data/'PG_VERSION').write_text('17')
    import pwd
    role=pwd.getpwuid(os.getuid()).pw_name
    birth=dict(version='g2c-beta-isolated-cluster.1',data=str(data.resolve()),socket='/private/tmp/g2c-socket-synthetic' if Path('/tmp').resolve()==Path('/private/tmp') else '/tmp/g2c-socket-synthetic',role=role,uid=os.getuid(),system_identifier='111')
    # A real private socket directory, but a readonly control-file mismatch.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='g2c-socket-',dir='/tmp') as socket:
        birth['socket']=str(Path(socket).resolve())
        monkeypatch.setattr(checkpoint,'verified',lambda path:birth)
        calls=[]
        def process(argv,**kwargs):
            calls.append(argv)
            assert Path(argv[0]).name=='pg_controldata'
            return SimpleNamespace(stdout=b'Database system identifier: 222\n',returncode=0)
        monkeypatch.setattr(staging.subprocess,'run',process)
        with pytest.raises(ValueError,match='identity_changed_before_start'):
            with staging.cluster(root=root,resume=True):raise AssertionError('wrong PG admitted')
        assert len(calls)==1 and (data/'PG_VERSION').read_text()=='17'


def test_hk_cli_requires_explicit_persistent_mount_and_fixed_identity(tmp_path,monkeypatch):
    from deploy.hk import recovery
    base=tmp_path/'rehearsals';base.mkdir(mode=0o700)
    monkeypatch.setattr(recovery,'REHEARSALS',base)
    original=Path.read_text
    mount=[f'1 2 0:3 / {base} rw - tmpfs tmpfs rw\n']
    def read(path,*args,**kwargs):
        if path==Path('/proc/self/mountinfo'):return mount[0]
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    identity='a'*32
    with pytest.raises(ValueError,match='persistent_rehearsal_bind_mount'):recovery.persistent_target(identity)
    mount[0]=f'1 2 8:1 /srv/g2c-beta/rehearsals {base} rw - ext4 /dev/vda1 rw\n'
    assert recovery.persistent_target(identity)==base/identity
    with pytest.raises(ValueError):recovery.persistent_target('../outside')
    (base/identity).symlink_to(tmp_path/'other')
    with pytest.raises(ValueError):recovery.persistent_target(identity)
