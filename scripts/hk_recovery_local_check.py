"""Private Unix PG only: canonical erasure producers → cloud-format recovery.

No Supabase/OSS/SSH or real model is contacted. The cloud operator boundary is
replaced only inside this local test; all dump/restore/owner/fence SQL is actual.
"""
import base64
from contextlib import contextmanager,ExitStack
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'backend/memory_withdrawal/tests')]
import psycopg
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.core import encode,digest
from cj_api.local_cleanup import Configuration
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,create_local_app
from cj_api.local_run_context import load_run_context
from account_retention_pg import main as account_exercise
from manual_history_erasure_pg import exercise as memory_exercise
from deploy.hk import checkpoint,schema,configuration,staging
import migrate
import pg_suites
import dev_auth


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)


def main():
    key=Ed25519PrivateKey.generate()
    env=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL='2026-11-30T16:00:00+00:00',
        CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode(),
        CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    with patch.dict(os.environ,env),patch.object(configuration,'datetime',Clock),tempfile.TemporaryDirectory(prefix='g2c-hk-recovery-') as directory:
        root=Path(directory);control=root/'control';target_control=root/'isolated-control'
        with ExitStack() as clusters:
            config=clusters.enter_context(pg_suites.cluster('hk-recovery',port=55881,role='cj_hk_fixture_operator',root=root/'pg',socket=root/'s'))
            path=root/'conn.json';path.write_text(json.dumps(config))
            with psycopg.connect(**config,autocommit=True) as connection:migrate.up(connection,migrate.load(),checkpoint.versions()[-1])
            @contextmanager
            def private_operator():
                with psycopg.connect(**config,autocommit=True) as connection:
                    connection.execute("SET TIME ZONE 'UTC'")
                    yield connection,config
            # pg_dump's source is explicitly a Unix fixture, not the real URI.
            with patch.object(checkpoint,'operator',private_operator),patch.object(staging,'PG17',pg_suites.bindir()):
                schema_root=root/'schema';schema.generate(config,schema_root)
                checkpoint.bootstrap(control,lambda connection:None)
                account=root/'account';memory=root/'memory';account.mkdir();memory.mkdir()
                base=root/'base';safety=root/'safety';captured=[]
                original_post=TestClient.post;original_create=Coordinator.create
                def post(client,url,*args,**kwargs):
                    if url=='/v1/memory-erasures' and not captured:
                        with psycopg.connect(**config) as connection:
                            assert connection.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='explicit-item'").fetchone()==(1,)
                            assert connection.execute('SELECT count(*) FROM cj_account_fence').fetchone()==(0,)
                        checkpoint.export(base,control,schema_root=schema_root);captured.append(True)
                    return original_post(client,url,*args,**kwargs)
                def create(coordinator,operation,*args,**kwargs):
                    if operation=='real-b-domain-erasure':
                        with patch.object(TestClient,'post',post):memory_exercise(memory,path,phase='unknown')
                    return original_create(coordinator,operation,*args,**kwargs)
                with patch.object(Coordinator,'create',create):account_exercise(account,path)
                assert captured==[True]
                # This additional retirement comes through the actual signed
                # HTTP confirmation AFTER the first safety archive exists.
                late='m4-synthetic-late-retirement'
                invited=json.loads((account/'auth/invited.json').read_bytes());invited.append(late)
                (account/'auth/invited.json').write_text(json.dumps(invited))
                registry=root/'late-registry.json';target_id='business/feedback-private-actions'
                registry.write_bytes(encode(dict(version='hk-late-retirement-fixture',stores=[dict(id='business',objects=[
                    dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1')])])))
                options=Configuration({'hk-test':b'hk-late-only-synthetic-cleanup-key'},'hk-test',3600,(target_id,),registry)
                late_app=create_local_app(conninfo_path=path,auth_dir=account/'auth',cleanup_configuration=options)
                late_headers={'Authorization':'Bearer '+dev_auth.token(account/'auth',late,300),'Content-Type':'application/octet-stream'}
                with TestClient(late_app) as client:
                    response=client.post('/v1/feedback',headers=late_headers,content=encode(dict(action_id='late-feedback',problem='synthetic late erasure',expectation='',references=[])))
                    assert response.status_code==200,response.status_code
                latest=checkpoint.export(safety,control,base=base,schema_root=schema_root)
                assert latest['fences']['cj_account_fence'] and latest['fences']['cj_memory_erasure_fence']
                isolated=clusters.enter_context(staging.cluster())
                target=dict(isolated,dbname='isolated_restore')
                with psycopg.connect(**isolated,autocommit=True) as connection:connection.execute('CREATE DATABASE isolated_restore TEMPLATE template0')
                try:checkpoint.restore(target,base,base,control,target_control,schema_root=schema_root)
                except ValueError:pass
                else:raise AssertionError('old cloud-format backup released without current erasure')
                assert not (target_control/'release.json').exists()
                with TestClient(late_app) as client:
                    def post(url,value):
                        response=client.post(url,content=encode(value),headers=late_headers)
                        assert response.status_code==200,response.status_code
                        return response.json()
                    device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register-late',device_id='late-device',state_ref=digest(b'synthetic-late-device')))
                    prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare-late',binding_id=device['binding_id']))
                    result=post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',dict(
                        version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
                    assert result['business_access']=='revoked' and result['online_status']=='complete'
                try:checkpoint.restore(target,base,safety,control,target_control,schema_root=schema_root)
                except ValueError as error:assert str(error)=='current_source_state_differs_from_safety_checkpoint',str(error)
                else:raise AssertionError('late retirement resurrected from stale safety archive')
                with psycopg.connect(**target) as connection:assert migrate.inventory(connection)==[]
                assert (control/'release.json').exists() and not (target_control/'release.json').exists()
                assert checkpoint.verified(control/'latest.json')['consumed'] is False
                safety=root/'fresh-safety';latest=checkpoint.export(safety,control,base=base,schema_root=schema_root)
                checkpoint.restore(target,base,safety,control,target_control,schema_root=schema_root)
                assert not (control/'release.json').exists(), 'source and restored target were both released'
                guarded_source=LocalDatabase(path)
                guarded_source._before_scope=lambda cursor:checkpoint.runtime_transaction(cursor,control)
                try:
                    with guarded_source.connect(scope_for(ISSUER,'retention-b')) as connection:connection.execute('SELECT 1')
                except (OSError,ValueError):pass
                else:raise AssertionError('suspended source admitted a new business transaction')

                with psycopg.connect(**target) as restored,psycopg.connect(**config) as source:
                    restored.execute("SET TIME ZONE 'UTC'")
                    source.execute("SET TIME ZONE 'UTC'")
                    checkpoint.require_release(restored,target_control)
                    assert staging.sequence_state(restored,list(latest['sequences']))==latest['sequences']
                    assert checkpoint.local.fence_state(restored)==checkpoint.local.fence_state(source)
                    assert restored.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-a'),)).fetchone()==(0,)
                    assert restored.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-b'),)).fetchone()==(1,)
                    assert restored.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='explicit-item'").fetchone()==(0,)
                    assert restored.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(scope_for(ISSUER,late),)).fetchone()==(0,)
                    assert restored.execute('SELECT scope_id,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()==source.execute('SELECT scope_id,ledger FROM cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
                    chain=migrate.load()
                    with patch.object(migrate,'load',lambda:chain[:-1]):
                        try:checkpoint.require_release(restored,target_control)
                        except ValueError:pass
                        else:raise AssertionError('old application accepted cloud-format schema')
                restored_path=root/'restored.json';restored_path.write_text(json.dumps(target));runtime=LocalDatabase(restored_path)
                app=create_local_app(conninfo_path=restored_path,auth_dir=account/'auth',account_admission=True,
                    run_context=load_run_context(account/'run.json'))
                with TestClient(app) as client:
                    for subject,status in (('retention-a',403),('retention-b',200)):
                        response=client.get('/v1/message-receipts',params={'message_id':'retained-message'},
                            headers={'Authorization':'Bearer '+dev_auth.token(account/'auth',subject,60)})
                        assert response.status_code==status,(subject,response.status_code)
                try:
                    with runtime.connect(scope_for(ISSUER,'retention-a')) as connection:connection.execute('INSERT INTO cj_message_scope VALUES(%s)',(scope_for(ISSUER,'retention-a'),))
                except psycopg.Error:pass
                else:raise AssertionError('retired namespace recreated')
                original_release=(target_control/'release.json').read_bytes()
                try:checkpoint.restore(target,base,safety,control,target_control,schema_root=schema_root)
                except ValueError:pass
                else:raise AssertionError('original successful target restore command repeated')
                assert (target_control/'release.json').read_bytes()==original_release
                second=clusters.enter_context(staging.cluster())
                try:checkpoint.restore(second,base,safety,control,root/'second-control',schema_root=schema_root)
                except ValueError:pass
                else:raise AssertionError('consumed checkpoint reused')
                assert not (root/'second-control'/'release.json').exists()
                assert checkpoint.finish_rehearsal(target,control,target_control)=='SOURCE_RESUMED_ISOLATION_REVOKED'
                assert not (target_control/'release.json').exists()
                with psycopg.connect(**config) as connection:checkpoint.require_release(connection,control)
                with guarded_source.connect(scope_for(ISSUER,'retention-b')) as connection:assert connection.execute('SELECT 1').fetchone()==(1,)
                runtime._before_scope=lambda cursor:checkpoint.runtime_transaction(cursor,target_control)
                try:
                    with runtime.connect(scope_for(ISSUER,'retention-b')) as connection:connection.execute('SELECT 1')
                except (OSError,ValueError):pass
                else:raise AssertionError('retired isolation target admitted a new transaction')
                # New rehearsal, with its own checkpoints/target: prove that
                # a write accepted on the active isolated side cannot be lost
                # by switching back to the older source state.
                next_base=root/'next-base';next_safety=root/'next-safety'
                checkpoint.export(next_base,control,schema_root=schema_root)
                checkpoint.export(next_safety,control,base=next_base,schema_root=schema_root)
                changing=clusters.enter_context(staging.cluster());changing_control=root/'changing-control'
                checkpoint.restore(changing,next_base,next_safety,control,changing_control,schema_root=schema_root)
                changing_path=root/'changing.json';changing_path.write_text(json.dumps(changing))
                targets=('checkpoints/run','business/message','business/needs-current-planning','business/usage')
                changing_registry=root/'changing-registry.json'
                changing_registry.write_bytes(encode(dict(version='hk-target-retirement-fixture',stores=[
                    dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
                    dict(id='business',objects=[dict(id=name.split('/')[1],cleanup_protocol='CLEANUP@1.1') for name in targets[1:]])])))
                changing_options=Configuration({'target-test':b'hk-target-only-synthetic-key-0000'},'target-test',3600,targets,changing_registry)
                changing_app=create_local_app(conninfo_path=changing_path,auth_dir=account/'auth',run_context=load_run_context(account/'run.json'),cleanup_configuration=changing_options)
                target_headers={'Authorization':'Bearer '+dev_auth.token(account/'auth','retention-b',300),'Content-Type':'application/octet-stream'}
                with TestClient(changing_app) as client:
                    def retire_post(url,value):
                        response=client.post(url,content=encode(value),headers=target_headers)
                        assert response.status_code==200,response.status_code
                        return response.json()
                    device=retire_post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register-target',device_id='target-device',state_ref=digest(b'synthetic-target-device')))
                    prepared=retire_post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare-target',binding_id=device['binding_id']))
                    result=retire_post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
                    assert result['business_access']=='revoked' and result['online_status']=='complete'
                with psycopg.connect(**changing) as connection,psycopg.connect(**config) as source:
                    assert connection.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-b'),)).fetchone()==(0,)
                    assert source.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-b'),)).fetchone()==(1,)
                    for name,(last,called) in latest['sequences'].items():
                        actual=connection.execute('SELECT pg_catalog.nextval(%s::regclass)',(name,)).fetchone()[0]
                        assert actual==(last+1 if called else last),(name,last,called,actual)
                try:checkpoint.finish_rehearsal(changing,control,changing_control)
                except ValueError as error:assert str(error)=='isolated_target_state_changed_keep_source_closed'
                else:raise AssertionError('isolation write was lost on source resume')
                assert not (control/'release.json').exists() and (changing_control/'release.json').exists()


    print('PASS L1 private PG canonical account/item erasure → app-only cloud-format checkpoint → new isolated database; physical absence, owner isolation, exact UNKNOWN/usage, fences-first, real post-safety HTTP retirement rejects stale archive before target writes, exclusive release/resume, old/consumed safety refused; real cloud/OSS UNRUN')


if __name__=='__main__':
    import subprocess
    try:main()
    except subprocess.CalledProcessError as error:
        (ROOT/'.local/hk-restore.stderr').write_bytes(error.stderr or b'')
        raise
