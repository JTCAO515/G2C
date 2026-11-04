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
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,create_local_app
from cj_api.local_run_context import load_run_context
from account_retention_pg import main as account_exercise
from manual_history_erasure_pg import exercise as memory_exercise
from deploy.hk import checkpoint,schema,configuration
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
            with patch.object(checkpoint,'operator',private_operator),patch.object(checkpoint,'pg_environment',checkpoint.local.pg_environment):
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
                        checkpoint.export(base,control);captured.append(True)
                    return original_post(client,url,*args,**kwargs)
                def create(coordinator,operation,*args,**kwargs):
                    if operation=='real-b-domain-erasure':
                        with patch.object(TestClient,'post',post):memory_exercise(memory,path,phase='unknown')
                    return original_create(coordinator,operation,*args,**kwargs)
                with patch.object(Coordinator,'create',create):account_exercise(account,path)
                assert captured==[True]
                latest=checkpoint.export(safety,control,base=base)
                assert latest['fences']['cj_account_fence'] and latest['fences']['cj_memory_erasure_fence']
                isolated=clusters.enter_context(pg_suites.cluster('hk-restore',port=55882,role='cj_hk_restore_operator',root=root/'target-pg',socket=root/'t'))
                target=dict(isolated,dbname='isolated_restore')
                with psycopg.connect(**isolated,autocommit=True) as connection:connection.execute('CREATE DATABASE isolated_restore TEMPLATE template0')
                try:checkpoint.restore(target,base,base,control,target_control,schema_root=schema_root)
                except ValueError:pass
                else:raise AssertionError('old cloud-format backup released without current erasure')
                assert not (target_control/'release.json').exists()
                checkpoint.restore(target,base,safety,control,target_control,schema_root=schema_root)
                with psycopg.connect(**target) as restored,psycopg.connect(**config) as source:
                    restored.execute("SET TIME ZONE 'UTC'")
                    source.execute("SET TIME ZONE 'UTC'")
                    checkpoint.require_release(restored,target_control)
                    assert checkpoint.local.fence_state(restored)==checkpoint.local.fence_state(source)
                    assert restored.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-a'),)).fetchone()==(0,)
                    assert restored.execute('SELECT count(*) FROM cj_message_receipt WHERE scope=%s',(scope_for(ISSUER,'retention-b'),)).fetchone()==(1,)
                    assert restored.execute("SELECT count(*) FROM cj_memory_item WHERE item_id='explicit-item'").fetchone()==(0,)
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
                second=dict(isolated,dbname='second_restore')
                with psycopg.connect(**isolated,autocommit=True) as connection:connection.execute('CREATE DATABASE second_restore TEMPLATE template0')
                try:checkpoint.restore(second,base,safety,control,root/'second-control',schema_root=schema_root)
                except ValueError:pass
                else:raise AssertionError('consumed checkpoint reused')
                assert not (root/'second-control'/'release.json').exists()
    print('PASS L1 private PG canonical account/item erasure → app-only cloud-format checkpoint → new isolated database; physical absence, owner isolation, exact UNKNOWN/usage, fences-first, old/consumed safety refused; real cloud/OSS UNRUN')


if __name__=='__main__':
    import subprocess
    try:main()
    except subprocess.CalledProcessError as error:
        (ROOT/'.local/hk-restore.stderr').write_bytes(error.stderr or b'')
        raise
