"""Private Unix PG composition, real checkpoint and canonical erasure; cloud UNRUN."""
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import hashlib
import uuid
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cj_api.local_app import LocalDatabase
from cj_api.local_account_admission_v2 import account_checker_for
from cj_api.local_cleanup import Runtime as LocalCleanup
from cj_api.local_run_context import load_run_context
from cj_auth.interfaces import AdmissionStatus
from cj_run.core import WorkerOwnershipLost
from deploy.hk.cloud_rehearsal import Host
from deploy.hk.configuration import Runtime
from deploy.hk import checkpoint,schema,staging
import migrate,pg_suites,dev_auth,local_run_context


def exercise(*,interrupted=False):
    with tempfile.TemporaryDirectory(prefix='g2c-c-rehearsal-') as directory:
        root=Path(directory);key=Ed25519PrivateKey.generate()
        env=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL='2027-02-03T00:00:00+08:00',
            CJ_BETA_CLEANUP_B64=base64.b64encode(b'c'*32).decode(),
            CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode(),
            CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
        with patch.dict(os.environ,env),pg_suites.cluster('cloud-rehearsal',port=55885,role='cj_rehearsal_fixture',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as c:migrate.up(c,migrate.load(),migrate.load()[-1]['version'])
            schema.generate(config,root/'schema')
            conninfo=root/'connection.json';conninfo.write_text(json.dumps(config));auth=root/'auth';beta=root/'beta-auth'
            subjects=['m4-synthetic-recovery-abcdef123456-a','m4-synthetic-recovery-abcdef123456-b']
            beta_subjects=['m4-synthetic-beta-a','m4-synthetic-beta-b']
            dev_auth.init(auth,subjects);dev_auth.init(beta,beta_subjects)
            now=int(datetime.now(timezone.utc).timestamp());run_path=root/'run.json'
            run_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,period_start=now-60,period_end=now+3600,
                max_steps=24,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
            context=load_run_context(run_path);database=LocalDatabase(conninfo,run_context=context,travel_context=True,trip_context=True)
            # Real local fixture with the same trusted release-binding seam;
            # never substitute Supabase identity/TLS or widen the app allowlist.
            database._before_scope=lambda cursor:checkpoint.runtime_transaction(cursor,root/'control')
            runtime=Runtime(auth,context,run_path,[])
            @contextmanager
            def operator():
                with psycopg.connect(**config,autocommit=True) as connection:
                    connection.execute("SET TIME ZONE 'UTC'")
                    yield connection,config
            def cleanup(options):return options,LocalCleanup(database,options,local_run_context.scope_for)
            host=Host(runtime,database,cleanup,operator,root/'control',root/'backups');host.control.mkdir(mode=0o700)
            def initialize(connection):
                for subject in beta_subjects:local_run_context.provision_budget_connection(connection,context,subject)
            with patch.object(checkpoint,'operator',operator),patch.object(staging,'PG17',pg_suites.bindir()):
                try:host.seed()
                except FileNotFoundError:pass
                else:raise AssertionError('unreleased source seeded')
                assert not host.state_path.exists()
                with operator() as (connection,_):assert connection.execute('SELECT count(*) FROM cj_usage_ledger_candidate').fetchone()==(0,)
                checkpoint.bootstrap(host.control,initialize)
                release=host.control/'release.json';release.rename(host.control/'fixture-suspended-release.json')
                try:host.seed()
                except FileNotFoundError:pass
                else:raise AssertionError('suspended source seeded')
                assert not host.state_path.exists()
                with operator() as (connection,_):assert connection.execute('SELECT count(*) FROM cj_usage_ledger_candidate').fetchone()==(2,)
                (host.control/'fixture-suspended-release.json').rename(release)
                # Different keys and invite sets: neither can act in the other host.
                assert account_checker_for(beta,database).check(dev_auth.token(auth,beta_subjects[0],15)).status is AdmissionStatus.DENIED
                assert host.checker.check(dev_auth.token(beta,subjects[0],15)).status is AdmissionStatus.DENIED
                if interrupted:
                    with patch('run_worker.run_once',side_effect=WorkerOwnershipLost('synthetic failure before RUN acceptance')):
                        try:host.seed()
                        except WorkerOwnershipLost:pass
                        else:raise AssertionError('missing simulated original interruption')
                    with operator() as (connection,_):
                        original_record=connection.execute('SELECT run_id,input_sha256,raw_input FROM cj_message_receipt WHERE scope=%s',(host.scope(subjects[0]),)).fetchone();original,original_sha,original_bytes=original_record
                        assert connection.execute('SELECT count(*) FROM cj_run_record').fetchone()==(0,)
                    legacy=host.load();del legacy['account_original_run_id'];del legacy['account_original_input_sha256'];host.save(legacy)
                    for run_id,message_sha in ((str(uuid.uuid4()),original_sha),(original,'0'*64)):
                        with patch.object(host,'finish_seed',side_effect=AssertionError('wrong original dispatched')):
                            try:host.resume_seed(expected_run_id=run_id,expected_message_sha256=message_sha)
                            except ValueError:pass
                            else:raise AssertionError('wrong original evidence accepted')
                        assert host.load()['stage']=='SEED_INTENT'
                    # Private fixture operator fault injection only; runtime has
                    # no UPDATE grant. A different valid body/hash cannot pass.
                    wrong=bytes(original_bytes).replace(b'SYNTHETIC recovery',b'SYNTHETIC altered')
                    with operator() as (connection,_):connection.execute('UPDATE cj_message_receipt SET raw_input=%s,input_sha256=%s WHERE scope=%s',
                        (wrong,hashlib.sha256(wrong).hexdigest(),host.scope(subjects[0])))
                    try:
                        with patch.object(host,'finish_seed',side_effect=AssertionError('wrong bytes dispatched')):
                            try:host.resume_seed(expected_run_id=original,expected_message_sha256=hashlib.sha256(wrong).hexdigest())
                            except ValueError:pass
                            else:raise AssertionError('different message bytes accepted')
                        assert host.load()['stage']=='SEED_INTENT'
                    finally:
                        with operator() as (connection,_):connection.execute('UPDATE cj_message_receipt SET raw_input=%s,input_sha256=%s WHERE scope=%s',
                            (original_bytes,original_sha,host.scope(subjects[0])))
                    send=host.send
                    def without_resend(client,subject):
                        if subject==subjects[0]:raise AssertionError('original account message resent')
                        return send(client,subject)
                    with patch.object(host,'send',without_resend):seeded=host.resume_seed(expected_run_id=original,expected_message_sha256=original_sha)
                    assert host.load()['account_original_run_id']==original
                    with operator() as (connection,_):
                        assert connection.execute('SELECT run_id FROM cj_message_receipt WHERE scope=%s',(host.scope(subjects[0]),)).fetchall()==[(original,)]
                else:seeded=host.seed()
                assert seeded['stage']=='SEEDED',seeded
                assert seeded['rows']==dict(account_messages=1,retained_messages=1,selected_memory=1),seeded
                assert host.seed()['rows']==seeded['rows']
                # A signed hash alone is deliberately insufficient for deletion.
                host.base.mkdir(parents=True);checkpoint.atomic(host.base/'manifest.json',dict(dump_sha256='a'*64))
                checkpoint.atomic(host.control/'latest.json',dict(dump_sha256='a'*64))
                try:host.erase()
                except ValueError:pass
                else:raise AssertionError('signed hash-only base accepted')
                assert host.inspect()['stage']=='SEEDED'
                (host.base/'manifest.json').unlink();host.base.rmdir()
                checkpoint.export(host.base,host.control,schema_root=root/'schema')
                original_state=staging.state
                def checked_snapshot(connection,tables):
                    assert connection.execute('SHOW transaction_isolation').fetchone()==('repeatable read',)
                    with psycopg.connect(**config) as writer:
                        assert writer.execute('SELECT pg_try_advisory_xact_lock_shared(%s)',(checkpoint.RELEASE_LOCK,)).fetchone()==(False,)
                    return original_state(connection,tables)
                with patch.object(staging,'state',checked_snapshot):host.require_base(host.load())
                deleted=host.erase();assert deleted['stage']=='DELETED',deleted
                assert deleted['rows']==dict(account_messages=0,retained_messages=1,selected_memory=0),deleted
                assert deleted['account_access']=='denied' and deleted['memory_owner_access']=='allowed',deleted
                assert deleted['fence_counts']==dict(cj_account_fence=1,item=1,action=1),deleted
                assert host.erase()['rows']==deleted['rows']
                interrupted=host.load();interrupted['stage']='ERASURE_INTENT'
                del interrupted['account_operation_id'];del interrupted['memory_operation_id']
                host.save(interrupted)
                with patch.object(host.erasure,'delete',side_effect=AssertionError('no original resend')),patch('fastapi.testclient.TestClient.post',side_effect=AssertionError('no original resend')):
                    reconciled=host.erase()
                assert reconciled['account_operation_id']==deleted['account_operation_id']
                assert reconciled['memory_operation_id']==deleted['memory_operation_id']
                assert reconciled['fence_counts']==deleted['fence_counts']
            host.close()
    print('PASS L1 actual private PG: separate signatures/invites in both directions, signed producer/Meter FakeProvider/UNKNOWN, real native base dump before canonical retirement/item erasure, target-specific physical/fence proof, retained owner, original stage only-read; cloud UNRUN')


def main():
    exercise();exercise(interrupted=True)


if __name__=='__main__':main()
