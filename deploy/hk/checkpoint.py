"""Application-only cloud snapshots. Provider/Auth/vault objects are never copied.

The accepted local archive remains unchanged. This cloud data checkpoint loads
the exact committed schema first, then the current full canonical data/fences;
an older archive is an authenticated anchor, never released as current data.
"""
import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
import psycopg
from psycopg import sql

import migrate
from cj_api.supabase_test_database import decode_uri,pin_ca,prepare_owned_session
from cj_strict_json import reject_duplicates
from deploy import recovery as local
from .configuration import authorization,decoded


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def envelope(value):
    return dict(value=value,signature=Ed25519PrivateKey.from_private_bytes(decoded('CJ_BETA_RECOVERY_PRIVATE_B64',length=32)).sign(canonical(value)).hex())


def verified(path):
    raw=Path(path).read_bytes()
    if len(raw)>1048576:raise ValueError('bounded_checkpoint_manifest_required')
    value=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_checkpoint_field'))
    if (type(value) is not dict or set(value)!={'value','signature'}
            or type(value['value']) is not dict or type(value['signature']) is not str):raise ValueError('signed_checkpoint_required')
    try:Ed25519PublicKey.from_public_bytes(decoded('CJ_BETA_RECOVERY_PUBLIC_B64',length=32)).verify(bytes.fromhex(value['signature']),canonical(value['value']))
    except (InvalidSignature,ValueError):raise ValueError('checkpoint_signature_invalid') from None
    return value['value']


def atomic(path,value,*,public=False):
    path=Path(path);temporary=path.with_suffix('.tmp')
    with temporary.open('x') as output:
        os.chmod(temporary,0o644 if public else 0o600);json.dump(envelope(value),output);output.flush();os.fsync(output.fileno())
    temporary.replace(path);local.sync_directory(path.parent)


@contextmanager
def lock(control):
    control=Path(control);control.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (control/'operator.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX);yield


@contextmanager
def operator():
    authorization()
    with pin_ca(os.environ['CJ_SUPABASE_CA_FILE']) as ca:
        config=dict(decode_uri(os.environ['CJ_SUPABASE_OPERATOR_URI'],operator=True),sslrootcert=ca.name)
        with psycopg.connect(**config,autocommit=True,prepare_threshold=None) as connection:
            prepare_owned_session(connection,'postgres')
            connection.execute("SET TIME ZONE 'UTC'")
            yield connection,config


def versions():return [item['version'] for item in migrate.load()]


def identity(connection):
    row=connection.execute('SELECT instance::text,lineage::text FROM cj.deployment_identity WHERE singleton').fetchone()
    if row is None:raise ValueError('checkpoint_identity_missing')
    return row


def rotate(connection):
    return connection.execute('UPDATE cj.deployment_identity SET instance=gen_random_uuid() WHERE singleton RETURNING instance::text').fetchone()[0]


def require_release(connection,control):
    authorization();release=verified(Path(control)/'release.json')
    current=identity(connection)
    if (release.get('version')!='g2c-beta-release.1' or release.get('instance')!=current[0]
            or release.get('lineage')!=current[1] or migrate.applied(connection)!=versions()):
        raise ValueError('beta_database_not_released')


def bootstrap(control,initialize):
    with lock(control),operator() as (connection,_):
        release=Path(control)/'release.json'
        if release.exists():require_release(connection,control);return
        if (Path(control)/'latest.json').exists():raise ValueError('existing_control_not_resettable')
        if migrate.applied(connection)!=versions():raise ValueError('exact_schema_required')
        for table in migrate.inventory(connection):
            if table in ('cj.schema_migrations','cj.deployment_identity'):continue
            if connection.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(*table.split('.')))).fetchone():
                raise ValueError('fresh_empty_business_state_required')
        initialize(connection)
        instance,family=identity(connection)
        atomic(release,dict(version='g2c-beta-release.1',instance=instance,lineage=family,checkpoint='fresh'),public=True)


def pg_environment(config):
    # Child only; native pg_dump never receives a password in argv.
    return dict(os.environ,PGHOST=config['host'],PGPORT=str(config['port']),PGUSER=config['user'],PGDATABASE=config['dbname'],
        PGPASSWORD=config['password'],PGSSLMODE='verify-full',PGSSLROOTCERT=config['sslrootcert'],PGCONNECT_TIMEOUT='10')


def export(destination,control,*,base=None):
    destination=Path(destination);control=Path(control)
    with lock(control),operator() as (connection,config):
        require_release(connection,control);destination.mkdir(mode=0o700)
        prior=verified(Path(base)/'manifest.json') if base is not None else None
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            if connection.execute("SELECT 1 FROM pg_catalog.pg_stat_activity WHERE datname=current_database() AND usename='cj_m1_runtime' LIMIT 1").fetchone():
                raise ValueError('stop_and_drain_beta_writers_before_checkpoint')
            instance,family=identity(connection)
            tables=migrate.inventory(connection)
            if any(not name.startswith(('public.cj_','cj.')) for name in tables):raise ValueError('unexpected_application_inventory')
            for table in tables:
                connection.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*table.split('.'))))
            fences=local.fence_state(connection)
            if prior is not None:
                for table in ('cj_account_fence','cj_memory_erasure_fence','cj_run_payload_erasure'):
                    if not set(prior['fences'][table])<=set(fences[table]):raise ValueError('irreversible_fence_regressed')
            snapshot=connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
            command=['pg_dump','--format=custom','--data-only','--no-owner','--no-acl','--snapshot='+snapshot]
            for table in tables:
                if table not in ('cj.schema_migrations','cj.deployment_identity'):command.append('--table='+table)
            dump=destination/'database.dump'
            with dump.open('xb') as output:
                subprocess.run(command,env=pg_environment(config),stdout=output,stderr=subprocess.PIPE,check=True,timeout=300)
            authorization()
            value=dict(version='g2c-beta-data-checkpoint.1',schema=versions(),lineage=family,archived_instance=instance,
                dump_sha256=local.checksum(dump),at=time.time(),tables=tables,fences=fences,
                base=None if prior is None else prior['dump_sha256'])
            if prior is not None and (prior['lineage']!=family or prior['schema']!=value['schema']):raise ValueError('checkpoint_anchor_mismatch')
            atomic(destination/'manifest.json',value)
            active=rotate(connection)
        atomic(control/'latest.json',dict(version='g2c-beta-latest.1',dump_sha256=value['dump_sha256'],lineage=family,consumed=False))
        atomic(control/'release.json',dict(version='g2c-beta-release.1',instance=active,lineage=family,checkpoint=value['dump_sha256']),public=True)
    return value


def restore(target,base,safety,source_control,target_control,*,schema_root=None):
    """New isolated Unix DB only; current full state replays canonical deletion."""
    from cj_api.local_app import local_connection
    target=local_connection(target)
    if 'dbname' not in target:raise ValueError('explicit_isolated_database_required')
    from . import schema
    schema_root=Path(schema_root) if schema_root is not None else Path(__file__).parent/'schema'
    profile=schema.load(schema_root)
    source_control=Path(source_control);target_control=Path(target_control)
    target_control.mkdir(mode=0o700,parents=True,exist_ok=True)
    (target_control/'release.json').unlink(missing_ok=True);local.sync_directory(target_control)
    with lock(source_control):
        old=verified(Path(base)/'manifest.json');latest=verified(Path(safety)/'manifest.json');authority=verified(source_control/'latest.json')
        if (old['version']!='g2c-beta-data-checkpoint.1' or latest['version']!=old['version']
                or latest['base']!=old['dump_sha256'] or latest['lineage']!=old['lineage']
                or latest['schema']!=versions() or old['schema']!=latest['schema'] or latest['at']<old['at']
                or latest['tables']!=profile['tables']
                or authority['dump_sha256']!=latest['dump_sha256'] or authority['lineage']!=latest['lineage']
                or authority['consumed'] or local.checksum(Path(base)/'database.dump')!=old['dump_sha256']
                or local.checksum(Path(safety)/'database.dump')!=latest['dump_sha256']):
            raise ValueError('fresh_complete_cloud_checkpoint_required')
        with psycopg.connect(**target,autocommit=True) as connection:
            if migrate.inventory(connection):raise ValueError('new_empty_isolation_database_required')
            if connection.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('cj_m1_runtime','cj_local_cleanup') LIMIT 1").fetchone():
                raise ValueError('new_isolated_cluster_without_application_roles_required')
        authority['consumed']=True;atomic(source_control/'latest.json',authority)
        listing=subprocess.check_output(['pg_restore','--list',str(Path(safety)/'database.dump')],text=True)
        lines=listing.splitlines()
        proofs=[line for line in lines if ' TABLE DATA public ' in line and line.split(' TABLE DATA public ',1)[1].split()[0] in local.FENCES]
        lines=proofs+[line for line in lines if line not in proofs]
        with tempfile_order(target_control,lines) as order:
            schema.apply_data(target,Path(safety)/'database.dump',order,schema_root)
        with psycopg.connect(**target) as connection:
            connection.execute("SET TIME ZONE 'UTC'")
            if local.fence_state(connection)!=latest['fences'] or migrate.applied(connection)!=latest['schema']:
                raise ValueError('restored_fence_or_schema_mismatch')
            connection.execute('UPDATE cj.deployment_identity SET lineage=%s WHERE singleton',(latest['lineage'],))
            active=rotate(connection)
        atomic(target_control/'release.json',dict(version='g2c-beta-release.1',instance=active,lineage=latest['lineage'],checkpoint=latest['dump_sha256']),public=True)


@contextmanager
def tempfile_order(root,lines):
    path=Path(root)/'restore.order'
    with path.open('x') as output:output.write('\n'.join(lines)+'\n')
    try:yield path
    finally:path.unlink()
