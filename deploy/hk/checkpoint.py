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
from . import staging


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


RELEASE_LOCK=0x4732434D34424B


def runtime_transaction(cursor,control):
    cursor.execute('SELECT pg_advisory_xact_lock_shared(%s)',(RELEASE_LOCK,))
    require_release(cursor.connection,control)


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



def export(destination,control,*,base=None,schema_root=None):
    destination=Path(destination);control=Path(control)
    schema_root=Path(schema_root) if schema_root is not None else Path(__file__).parent/'schema'
    with lock(control),operator() as (connection,_):
        require_release(connection,control);destination.mkdir(mode=0o700)
        prior=verified(Path(base)/'manifest.json') if base is not None else None
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            connection.execute('SELECT pg_advisory_xact_lock(%s)',(RELEASE_LOCK,))
            instance,family=identity(connection)
            tables=migrate.inventory(connection)
            if any(not name.startswith(('public.cj_','cj.')) for name in tables):raise ValueError('unexpected_application_inventory')
            for table in tables:
                connection.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*table.split('.'))))
            fences=local.fence_state(connection)
            if prior is not None:
                for table in ('cj_account_fence','cj_memory_erasure_fence','cj_run_payload_erasure'):
                    if not set(prior['fences'][table])<=set(fences[table]):raise ValueError('irreversible_fence_regressed')
            dump=destination/'database.dump'
            row_state,sequences=staging.dump(connection,tables,dump,schema_root)
            authorization()
            value=dict(version='g2c-beta-data-checkpoint.1',schema=versions(),lineage=family,archived_instance=instance,
                dump_sha256=local.checksum(dump),at=time.time(),tables=tables,fences=fences,row_state=row_state,sequences=sequences,
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
    if target_control.resolve()==source_control.resolve():raise ValueError('distinct_isolated_control_required')
    with lock(source_control),lock(target_control),operator() as (source,_),source.transaction():
        if (target_control/'release.json').exists():raise ValueError('original_isolated_release_must_be_preserved')
        source.execute('SELECT pg_advisory_xact_lock(%s)',(RELEASE_LOCK,))
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
            staging.require_isolated(connection,target)
            if migrate.inventory(connection):raise ValueError('new_empty_isolation_database_required')
            if connection.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('cj_m1_runtime','cj_local_cleanup') LIMIT 1").fetchone():
                raise ValueError('new_isolated_cluster_without_application_roles_required')
        # The source remains behind the exclusive release barrier until the
        # isolated target is released. A later deletion/write invalidates this
        # safety archive rather than resurrecting its older content.
        require_release(source,source_control)
        source.execute("SET TIME ZONE 'UTC'")
        for table in latest['tables']:
            source.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*table.split('.'))))
        if (staging.state(source,latest['tables'])!=latest['row_state'] or local.fence_state(source)!=latest['fences']
                or staging.sequence_state(source,list(latest['sequences']))!=latest['sequences']):
            raise ValueError('current_source_state_differs_from_safety_checkpoint')
        if (source_control/'suspended.json').exists():
            previous=verified(source_control/'suspended.json')
            if previous.get('state')!='COMPLETE':raise ValueError('original_rehearsal_requires_reconciliation')
            history=source_control/'rehearsals';history.mkdir(mode=0o700,exist_ok=True)
            os.link(source_control/'suspended.json',history/(previous['checkpoint']+'.json'))
            (source_control/'suspended.json').unlink();local.sync_directory(history);local.sync_directory(source_control)
        local.invalidate_release(source_control)
        source_instance=rotate(source)
        authority['consumed']=True;atomic(source_control/'latest.json',authority)
        listing=subprocess.check_output(['pg_restore','--list',str(Path(safety)/'database.dump')],text=True)
        lines=listing.splitlines()
        proofs=[line for line in lines if ' TABLE DATA public ' in line and line.split(' TABLE DATA public ',1)[1].split()[0] in local.FENCES]
        lines=proofs+[line for line in lines if line not in proofs]
        with tempfile_order(target_control,lines) as order:
            schema.apply_data(target,Path(safety)/'database.dump',order,schema_root)
        with psycopg.connect(**target) as connection:
            connection.execute("SET TIME ZONE 'UTC'")
            if (local.fence_state(connection)!=latest['fences'] or migrate.applied(connection)!=latest['schema']
                    or staging.state(connection,latest['tables'])!=latest['row_state']
                    or staging.sequence_state(connection,list(latest['sequences']))!=latest['sequences']):
                raise ValueError('restored_fence_or_schema_mismatch')
            connection.execute('UPDATE cj.deployment_identity SET lineage=%s WHERE singleton',(latest['lineage'],))
            active=rotate(connection)
        atomic(source_control/'suspended.json',dict(version='g2c-beta-rehearsal.1',state='ISOLATED_RELEASED',
            source_instance=source_instance,target_instance=active,target=local.fingerprint(target),
            checkpoint=latest['dump_sha256'],lineage=latest['lineage'],row_state=latest['row_state'],sequences=latest['sequences']))
        atomic(target_control/'release.json',dict(version='g2c-beta-release.1',instance=active,lineage=latest['lineage'],checkpoint=latest['dump_sha256']),public=True)


@contextmanager
def tempfile_order(root,lines):
    path=Path(root)/'restore.order'
    with path.open('x') as output:output.write('\n'.join(lines)+'\n')
    try:yield path
    finally:path.unlink()


def finish_rehearsal(target,source_control,target_control):
    """Revoke the isolated target before resuming the unchanged primary source.

    No row is deleted, no request retried, no archive promoted. Any uncertain
    intermediate state keeps both gates closed for original-state inspection.
    """
    from cj_api.local_app import local_connection
    target=local_connection(target);source_control=Path(source_control);target_control=Path(target_control)
    with lock(source_control),lock(target_control),operator() as (source,_),source.transaction():
        source.execute('SELECT pg_advisory_xact_lock(%s)',(RELEASE_LOCK,))
        record=verified(source_control/'suspended.json')
        if (record.get('version')!='g2c-beta-rehearsal.1' or record.get('state')!='ISOLATED_RELEASED'
                or record['target']!=local.fingerprint(target) or (source_control/'release.json').exists()
                or identity(source)!=(record['source_instance'],record['lineage'])):
            raise ValueError('original_isolated_rehearsal_required')
        source.execute("SET TIME ZONE 'UTC'")
        if (staging.state(source,migrate.inventory(source))!=record['row_state']
                or staging.sequence_state(source,list(record['sequences']))!=record['sequences']):
            raise ValueError('suspended_source_state_changed')
        with psycopg.connect(**target) as isolated:
            staging.require_isolated(isolated,target)
            isolated.execute('SELECT pg_advisory_xact_lock(%s)',(RELEASE_LOCK,))
            require_release(isolated,target_control)
            if identity(isolated)!=(record['target_instance'],record['lineage']):
                raise ValueError('original_isolation_target_required')
            isolated.execute("SET TIME ZONE 'UTC'")
            for table in migrate.inventory(isolated):
                isolated.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.Identifier(*table.split('.'))))
            if (staging.state(isolated,migrate.inventory(isolated))!=record['row_state']
                    or staging.sequence_state(isolated,list(record['sequences']))!=record['sequences']):
                raise ValueError('isolated_target_state_changed_keep_source_closed')
            local.invalidate_release(target_control);rotate(isolated)
        record['state']='ISOLATION_REVOKED';atomic(source_control/'suspended.json',record)
        atomic(source_control/'release.json',dict(version='g2c-beta-release.1',instance=record['source_instance'],
            lineage=record['lineage'],checkpoint=record['checkpoint']),public=True)
        record['state']='COMPLETE';atomic(source_control/'suspended.json',record)
    return 'SOURCE_RESUMED_ISOLATION_REVOKED'
