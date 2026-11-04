"""Private Unix PG composition of cloud-rehearsal producers; real cloud UNRUN."""
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import json
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
from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_cleanup import Runtime as LocalCleanup
from cj_api.local_run_context import load_run_context
from deploy.hk.cloud_rehearsal import Host
from deploy.hk.configuration import Runtime
import migrate,pg_suites,dev_auth,local_run_context


def main():
    with tempfile.TemporaryDirectory(prefix='g2c-c-rehearsal-') as directory:
        root=Path(directory);key=Ed25519PrivateKey.generate()
        env=dict(CJ_ENV='local',CJ_BETA_CLEANUP_B64=base64.b64encode(b'c'*32).decode(),
            CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode(),
            CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
        with patch.dict(os.environ,env),pg_suites.cluster('cloud-rehearsal',port=55885,role='cj_rehearsal_fixture',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as c:migrate.up(c,migrate.load(),migrate.load()[-1]['version'])
            conninfo=root/'connection.json';conninfo.write_text(json.dumps(config));auth=root/'auth'
            subjects=['m4-synthetic-beta-a','m4-synthetic-beta-b','m4-synthetic-recovery-abcdef123456-a','m4-synthetic-recovery-abcdef123456-b']
            dev_auth.init(auth,subjects)
            now=int(datetime.now(timezone.utc).timestamp());run_path=root/'run.json'
            run_path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,period_start=now-60,period_end=now+3600,
                max_steps=24,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=1000)),history=[])))
            context=load_run_context(run_path)
            for subject in subjects:local_run_context.provision_budget(conninfo,context,subject)
            database=LocalDatabase(conninfo,run_context=context,travel_context=True,trip_context=True)
            runtime=Runtime(auth,context,run_path,[])
            @contextmanager
            def operator():
                with psycopg.connect(**config,autocommit=True) as connection:yield connection,config
            def cleanup(options):return options,LocalCleanup(database,options,scope_for)
            host=Host(runtime,database,cleanup,operator,root/'control');host.control.mkdir(mode=0o700)
            seeded=host.seed();assert seeded['stage']=='SEEDED',seeded
            assert seeded['rows']==dict(account_messages=1,retained_messages=1,selected_memory=1),seeded
            assert host.seed()['rows']==seeded['rows']
            # Only checkpoint metadata is a local fixture; deletion uses the real
            # dedicated cleanup role, C erasure service and B physical hooks.
            from deploy.hk import checkpoint
            checkpoint.atomic(host.control/'latest.json',dict(dump_sha256='a'*64))
            deleted=host.erase();assert deleted['stage']=='DELETED',deleted
            assert deleted['rows']==dict(account_messages=0,retained_messages=1,selected_memory=0),deleted
            assert deleted['account_access']=='denied' and deleted['memory_owner_access']=='allowed',deleted
            assert deleted['fence_counts']['cj_account_fence'] and deleted['fence_counts']['cj_memory_erasure_fence'],deleted
            assert host.erase()['rows']==deleted['rows']
            host.close()
    print('PASS L1 actual private PG: narrowed synthetic invite set, real signed producer/Meter FakeProvider/UNKNOWN, canonical account retirement and item erasure, selected physical absence/other owner retention, original stage only-read; cloud UNRUN')


if __name__=='__main__':main()
