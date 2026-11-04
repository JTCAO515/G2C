"""Offline full-checkpoint roll-forward; never reinterpret deletion or retry work.

The non-restored control directory must survive independently of database backups.
A newer full checkpoint is deliberately required: fences alone cannot prove that
all historical copies were physically erased by their canonical domain owners.
"""
import argparse
import hashlib
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

import psycopg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cj_strict_json import reject_duplicates
import migrate

FENCES = ('cj_account_fence', 'cj_memory_erasure_fence', 'cj_memory_history_fence', 'cj_run_payload_erasure')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def read_json(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=reject_duplicates(ValueError, 'duplicate field'))


def key(*,public=False):
    path = Path(os.environ['CJ_DEPLOY_RECOVERY_PUBLIC_KEY_FILE' if public else 'CJ_DEPLOY_RECOVERY_KEY_FILE'])
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        mode=stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISREG(metadata.st_mode) or (mode&0o022 if public else mode!=0o600):
            raise ValueError('private_recovery_key_required')
        value = stream.read(33)
    if len(value) != 32:
        raise ValueError('recovery_key_length')
    return value


def signed(value):
    return dict(value=value, signature=Ed25519PrivateKey.from_private_bytes(key()).sign(canonical(value)).hex())


def verified(path):
    envelope = read_json(path)
    if set(envelope) != {'value','signature'}:raise ValueError('recovery_signature_invalid')
    try:Ed25519PublicKey.from_public_bytes(key(public=True)).verify(bytes.fromhex(envelope['signature']),canonical(envelope['value']))
    except InvalidSignature:raise ValueError('recovery_signature_invalid') from None
    return envelope['value']


def atomic(path, value, *, public=False):
    temporary = path.with_suffix('.tmp')
    with temporary.open('x') as stream:
        os.chmod(temporary, 0o644 if public else 0o600)
        json.dump(signed(value), stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def sync_directory(path):
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def invalidate_release(control):
    (control/'release.json').unlink(missing_ok=True)
    sync_directory(control)


@contextmanager
def control_lock(control):
    with (control/'operator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        yield


def connection(path):
    # Reuse the exact local-only boundary. No cloud, DSN/environment fallback.
    from cj_api.local_app import local_conninfo
    return local_conninfo(path)


def fingerprint(config):
    return hashlib.sha256(canonical({name: config.get(name) for name in ('host', 'port', 'dbname')})).hexdigest()


def identity(conn):
    row=conn.execute('SELECT instance::text FROM cj.deployment_identity WHERE singleton').fetchone()
    if row is None:raise ValueError('database_instance_identity_missing')
    return row[0]


def lineage(conn):
    return conn.execute('SELECT lineage::text FROM cj.deployment_identity WHERE singleton').fetchone()[0]


def rotate(conn):
    return conn.execute('UPDATE cj.deployment_identity SET instance=gen_random_uuid() WHERE singleton RETURNING instance::text').fetchone()[0]


def fence_state(conn):
    # Code-owned tables only, from the accepted migration chain. No content in
    # the manifest; json hashes cover every column including permanent fences.
    return {table: sorted(row[0] for row in conn.execute(
        f"SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {table} t"))
        for table in FENCES}


def pg_environment(config):
    if any(name.startswith(('PG', 'LIBPQ')) for name in os.environ):
        raise ValueError('ambient_pg_configuration_refused')
    # Only the native child receives the explicit local operator identity.
    return dict(os.environ, PGHOST=config['host'], PGPORT=str(config.get('port', 5432)),
                PGUSER=config['user'], PGDATABASE=config['dbname'],
                PGPASSFILE=config.get('passfile', '/dev/null'))


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def backup(config,destination,control,*,base=None):
    with control_lock(control):return _backup(config,destination,control,base=base)


def _backup(config, destination, control, *, base=None):
    require_release(config,control)
    current=verified(control/'latest.json')
    destination.mkdir(mode=0o700)  # Refuse an existing package; no overwrite.
    prior = verified(base / 'manifest.json') if base is not None else None
    invalidate_release(control)
    with psycopg.connect(**config) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        if conn.execute("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND usename IN "
                            "('cj_m1_runtime','cj_local_cleanup') LIMIT 1").fetchone():
            raise ValueError('stop_and_drain_writers_before_checkpoint')
        for table in migrate.inventory(conn):conn.execute('LOCK TABLE ' + table + ' IN SHARE MODE')
        versions = migrate.applied(conn)
        if versions != [m['version'] for m in migrate.load()]:
            raise ValueError('application_schema_mismatch')
        fences = fence_state(conn)
        instance=identity(conn)
        family=lineage(conn)
        if prior is not None:
            if prior['source'] != fingerprint(config) or prior['lineage'] != family or prior['schema'] != versions:
                raise ValueError('safety_source_or_schema_differs')
            # Account and item/run fences are immutable; history fence erased
            # may change false->true and is checked through the complete snapshot.
            for table in ('cj_account_fence', 'cj_memory_erasure_fence', 'cj_run_payload_erasure'):
                if not set(prior['fences'][table]) <= set(fences[table]):
                    raise ValueError('irreversible_fence_regressed')
        snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        dump = destination / 'database.dump'
        with dump.open('xb') as output:
            os.chmod(dump, 0o600)
            subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--snapshot=' + snapshot],
                           env=pg_environment(config), stdout=output, stderr=subprocess.PIPE, check=True)
        value = dict(version='g2c-local-full-checkpoint.1', source=fingerprint(config),
                     instance=instance,lineage=family,schema=versions, fences=fences, dump_sha256=checksum(dump), at=time.time(),
                     base=None if prior is None else prior['dump_sha256'])
        atomic(destination / 'manifest.json', value)
        active=rotate(conn)
    # No exported archive retains the currently released live-instance token.
    # A normal backup resumes only its exact source with a new signed token.
    if base is None:
        current.update(active_instance=active,lineage=family)
        atomic(control/'latest.json',current,public=True)
        atomic(control/'release.json',dict(target=fingerprint(config),database_identity=active,
            lineage=family,checkpoint=current['dump_sha256']),public=True)
    if base is not None:
        atomic(control / 'latest.json', dict(dump_sha256=value['dump_sha256'],at=value['at'],
            consumed=False,active_instance=active,lineage=family),public=True)
    return value


def require_release(config, control):
    release = verified(control / 'release.json')
    latest = verified(control / 'latest.json')
    if (release['target'] != fingerprint(config) or release['checkpoint'] != latest['dump_sha256']
            or release['database_identity']!=latest['active_instance'] or release['lineage']!=latest['lineage']):
        raise ValueError('restore_not_released')
    with psycopg.connect(**config, autocommit=True) as conn:
        if identity(conn) != release['database_identity']:
            raise ValueError('restore_target_changed')


def bootstrap(config,control,*,initialize=lambda:None):
    with control_lock(control):return _bootstrap(config,control,initialize)


def _bootstrap(config, control, initialize):
    # Only a database with no business data may acquire an initial release.
    with psycopg.connect(**config) as conn:
        for table in migrate.inventory(conn):
            if table in ('cj.schema_migrations','cj.deployment_identity'):
                continue
            if conn.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone() is not None:
                raise ValueError('bootstrap_requires_empty_business_state')
        oid = identity(conn)
        family=lineage(conn)
    if (control / 'latest.json').exists() or (control / 'release.json').exists():
        raise ValueError('existing_control_must_not_be_reset')
    initialize()  # Only after empty-business proof; never on an existing release.
    atomic(control / 'latest.json', dict(dump_sha256='fresh',at=time.time(),consumed=True,
        active_instance=oid,lineage=family),public=True)
    atomic(control / 'release.json', dict(target=fingerprint(config), database_identity=oid,
        lineage=family,checkpoint='fresh'),public=True)


def restore(config, base, safety, control):
    with control_lock(control):return _restore(config,base,safety,control)


def _restore(config,base,safety,control):
    # Invalidate availability even when a subsequent check fails.
    invalidate_release(control)
    original, checkpoint = verified(base / 'manifest.json'), verified(safety / 'manifest.json')
    latest = verified(control / 'latest.json')
    if (checkpoint['base'] != original['dump_sha256'] or checkpoint['source'] != original['source']
            or checkpoint['at'] < original['at'] or checkpoint['schema'] != original['schema']
            or checkpoint['lineage'] != original['lineage'] or checkpoint['lineage']!=latest['lineage']
            or checkpoint['dump_sha256'] != latest['dump_sha256']
            or checksum(base / 'database.dump') != original['dump_sha256']
            or checksum(safety / 'database.dump') != checkpoint['dump_sha256']):
        raise ValueError('latest_complete_checkpoint_required')
    if latest['consumed']:raise ValueError('checkpoint_already_consumed_obtain_fresh_safety_state')
    with psycopg.connect(**config, autocommit=True) as conn:
        if migrate.inventory(conn):
            raise ValueError('restore_requires_new_empty_database')
        for name in ('cj_m1_runtime', 'cj_local_cleanup'):
            role = conn.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolreplication,rolbypassrls '
                                'FROM pg_roles WHERE rolname=%s', (name,)).fetchone()
            if role is None:
                conn.execute(f'CREATE ROLE {name} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS')
            elif role != (False, False, False, False, False, False):
                raise ValueError('unsafe_existing_local_role')
    # Reserve once before the first restore write. Unknown/failed restores do
    # not silently retry the same checkpoint or authorize another target.
    latest['consumed']=True
    atomic(control/'latest.json',latest,public=True)
    # Full current state is the replay unit. This preserves domain-owned
    # physical erasure/proofs, epochs, canonical jobs, original costs/UNKNOWN.
    # No --clean, --disable-triggers, session_replication_role, or old writers.
    # CHECK constraints in M45 consult permanent erasure proofs while COPY is
    # running. Native pg_dump's table order does not encode that dependency.
    # Load those proofs first, retaining every archive entry and constraint.
    listing = subprocess.check_output(['pg_restore', '--list', str(safety / 'database.dump')], text=True)
    lines = listing.splitlines()
    proofs = [line for line in lines if ' TABLE DATA public ' in line
              and line.split(' TABLE DATA public ', 1)[1].split()[0] in FENCES]
    if len(proofs) != len(FENCES):
        raise ValueError('complete_fence_archive_required')
    ordered = [line for line in lines if line not in proofs]
    first = next(i for i, line in enumerate(ordered) if ' TABLE DATA ' in line)
    ordered[first:first] = proofs
    with tempfile.NamedTemporaryFile(mode='w', prefix='g2c-restore-order-') as toc:
        toc.write('\n'.join(ordered) + '\n')
        toc.flush()
        subprocess.run(['pg_restore', '--exit-on-error', '--single-transaction', '--no-owner',
                        '--use-list=' + toc.name, '--dbname=' + config['dbname'], str(safety / 'database.dump')],
                       env=pg_environment(config), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    with psycopg.connect(**config) as conn:
        if (migrate.applied(conn) != checkpoint['schema'] or fence_state(conn) != checkpoint['fences']
                or identity(conn)!=checkpoint['instance']):
            raise ValueError('restored_fences_or_schema_differ')
        oid = rotate(conn)
    latest.update(active_instance=oid,lineage=checkpoint['lineage'])
    atomic(control/'latest.json',latest,public=True)
    atomic(control / 'release.json', dict(target=fingerprint(config), database_identity=oid,
        lineage=checkpoint['lineage'],checkpoint=checkpoint['dump_sha256']),public=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('bootstrap', 'backup', 'safety', 'restore'))
    parser.add_argument('--conninfo', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--safety', type=Path)
    args = parser.parse_args()
    config = connection(args.conninfo)
    if args.command == 'bootstrap':
        bootstrap(config, args.control)
    elif args.command in ('backup', 'safety'):
        if args.package is None or args.command == 'safety' and args.base is None:
            parser.error('package required; safety also requires base')
        backup(config, args.package, args.control, base=args.base)
    else:
        if args.base is None or args.safety is None:
            parser.error('restore requires base and safety')
        restore(config, args.base, args.safety, args.control)
    print(json.dumps({'status': 'PASS', 'operation': args.command}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, psycopg.Error, subprocess.CalledProcessError):
        print('{"status":"FAIL","reason":"recovery_unproven_keep_unavailable"}')
        raise SystemExit(1) from None
