"""Promote an approved cloud checkpoint to a persistent HK Unix-only PG17."""
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
from datetime import datetime,timezone
from urllib.parse import quote

import psycopg
from psycopg import sql

import migrate
from cj_api.supabase_test_database import HK_SOCKET
from . import checkpoint,staging
from .configuration import authorization,load_secret_environment,local_database_target

ROOT=Path('/local-pg')
BACKUPS=Path('/backups')
ROLES={'OPERATOR':'cj','RUNTIME':'cj_m1_runtime','CLEANUP':'cj_local_cleanup'}
SOURCE_ROLES=('cj_m1_runtime','cj_local_cleanup')
ARCHIVE='b2-supabase-frozen'
STATE='b2.json'
FROZEN='supabase-frozen.json'


def private_directory(path):
    info=path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o700):
        raise ValueError('explicit owned private HK PG directory required')


def cutover_state(control):
    return checkpoint.verified(Path(control)/STATE)


def require_serving(control):
    if local_database_target():
        state=cutover_state(control)
        if state.get('version')!='g2c-hk-local.1' or state.get('state')!='FORWARD_ONLY':
            raise ValueError('HK PG manual backup gate closed')


def freeze_supabase(control,expected,manifest):
    with checkpoint.lock(control),checkpoint.operator() as (source,_):
        with source.transaction():
            source.execute('SELECT pg_advisory_xact_lock(%s)',(checkpoint.RELEASE_LOCK,))
            record=checkpoint.verified(control/'suspended.json')
            if (record!=expected or (control/'release.json').exists()
                    or checkpoint.identity(source)!=(record['source_instance'],record['lineage'])):
                raise ValueError('original suspended Supabase source required')
            empty=source.execute("SELECT (SELECT count(*) FROM public.cj_message_delivery WHERE NOT acknowledged),"
                "(SELECT count(*) FROM public.cj_run_record WHERE status IN ('queued','running'))").fetchone()
            if empty!=(0,0):raise ValueError('original application still in flight')
            for role in SOURCE_ROLES:
                source.execute(sql.SQL('ALTER ROLE {} NOLOGIN').format(sql.Identifier(role)))
            source.execute('ALTER DATABASE postgres SET default_transaction_read_only=on')
        sessions=source.execute('SELECT pid FROM pg_stat_activity WHERE usename=ANY(%s)',(list(SOURCE_ROLES),)).fetchall()
        for pid, in sessions:
            source.execute('SELECT pg_terminate_backend(%s,5000)',(pid,)).fetchone()
        rows=source.execute('SELECT rolname,rolcanlogin FROM pg_roles WHERE rolname=ANY(%s) ORDER BY rolname',
                            (list(SOURCE_ROLES),)).fetchall()
        if rows!=[(name,False) for name in sorted(SOURCE_ROLES)]:
            raise ValueError('original application logins still enabled')
    with checkpoint.operator() as (source,_),source.transaction():
        source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if (source.execute('SHOW default_transaction_read_only').fetchone()!=('on',)
                or source.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=ANY(%s)',
                                  (list(SOURCE_ROLES),)).fetchone()!=(0,)
                or staging.state(source,manifest['tables'])!=manifest['row_state']
                or staging.sequence_state(source,list(manifest['sequences']))!=manifest['sequences']
                or checkpoint.local.fence_state(source)!=manifest['fences']):
            raise ValueError('original Supabase freeze not confirmed')


def configure_socket(target,root):
    # These are three new host-local passwords for the existing PG identities.
    # The runtime receives its own 0600 file, not the combined operator input.
    with open(root/'local-db.env','x',opener=private_open) as secrets_file:
        with psycopg.connect(**target) as connection:
            connection.execute("SET LOCAL password_encryption='scram-sha-256'")
            for purpose,role in ROLES.items():
                password=secrets.token_urlsafe(32)
                connection.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(
                    sql.Identifier(role),sql.Literal(password)))
                url=f'postgresql://{role}:{password}@/postgres?host={quote(HK_SOCKET,safe="")}&port=5432&sslmode=disable'
                secrets_file.write(f'CJ_SUPABASE_{purpose}_URI={url}\n')
            secrets_file.flush()
            os.fsync(secrets_file.fileno())
    hba=root/'pg/data/pg_hba.conf'
    temporary=hba.with_suffix('.b2-next')
    with open(temporary,'x',opener=private_open) as output:
        output.write('local postgres cj,cj_m1_runtime,cj_local_cleanup scram-sha-256\n'
                     'local all all reject\nhost all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(hba)
    checkpoint.local.sync_directory(hba.parent)
    checkpoint.local.sync_directory(root)


def private_open(path,flags):
    return os.open(path,flags|os.O_NOFOLLOW,0o600)


def stage(control,root):
    if local_database_target():raise ValueError('explicit original Supabase source required')
    private_directory(root)
    if any(root.iterdir()):raise ValueError('nonempty original staging target; inspect only')
    day=checkpoint.verified(control/'daily.json')
    if day['state']!='COMPLETE' or not day['day'].isdigit() or len(day['day'])!=8:
        raise ValueError('original completed daily checkpoint required')
    if day['day']==datetime.now(timezone.utc).strftime('%Y%m%d'):
        raise ValueError('same UTC day already has a backup; manual cutover slot unavailable')
    base=BACKUPS/day['day']
    safety=root/'safety'
    target_control=root/'target-control'
    checkpoint.export(safety,control,base=base)
    with staging.cluster(root=root/'pg') as target:
        checkpoint.restore(target,base,safety,control,target_control)
        record=checkpoint.verified(control/'suspended.json')
        configure_socket(target,root)
        freeze_supabase(control,record,checkpoint.verified(safety/'manifest.json'))
    checkpoint.atomic(root/FROZEN,dict(version='g2c-hk-local-source-freeze.1',
        source_instance=record['source_instance'],lineage=record['lineage'],checkpoint=record['checkpoint']))
    print('PASS original Supabase frozen and local PG17 staged with original fences')


def serve(root):
    if not local_database_target():raise ValueError('explicit HK socket target required')
    private_directory(root)
    private_directory(Path(HK_SOCKET))
    data=root/'pg/data'
    private_directory(data)
    birth=checkpoint.verified(root/'pg/birth.json')
    sealed=checkpoint.verified(root/FROZEN)
    if (birth.get('version')!='g2c-beta-isolated-cluster.1' or birth['data']!=str(data)
            or birth['role']!='cj' or birth['uid']!=os.getuid() or (data/'PG_VERSION').read_text().strip()!='17'
            or sealed.get('version')!='g2c-hk-local-source-freeze.1'):
        raise ValueError('original HK PG17 data required')
    pg_control=subprocess.check_output([str(staging.PG17/'pg_controldata'),str(data)],
        env=staging.environment(),text=True,timeout=10)
    if re.findall(r'^Database system identifier:\s+(\d+)\s*$',pg_control,re.M)!=[birth['system_identifier']]:
        raise ValueError('HK PG17 cluster identity changed')
    binary=staging.PG17/'postgres'
    os.execv(binary,[str(binary),'-D',str(data),'-c','listen_addresses=','-c','unix_socket_directories='+HK_SOCKET,
                    '-c','unix_socket_permissions=0700','-p','5432'])


def activate(control,root):
    if not local_database_target():raise ValueError('explicit HK socket target required')
    with checkpoint.lock(control),checkpoint.operator() as (target,_),target.transaction():
        target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        frozen=checkpoint.verified(control/'suspended.json')
        sealed=checkpoint.verified(root/FROZEN)
        release=checkpoint.verified(root/'target-control/release.json')
        manifest=checkpoint.verified(root/'safety/manifest.json')
        archive=control/ARCHIVE
        if ((control/'release.json').exists() or (control/STATE).exists() or archive.exists()
                or frozen['state']!='ISOLATED_RELEASED' or frozen['target_instance']!=release['instance']
                or sealed.get('version')!='g2c-hk-local-source-freeze.1'
                or (sealed['source_instance'],sealed['lineage'],sealed['checkpoint'])
                   !=(frozen['source_instance'],frozen['lineage'],frozen['checkpoint'])
                or checkpoint.identity(target)!=(release['instance'],release['lineage'])
                or release['checkpoint']!=manifest['dump_sha256']
                or migrate.applied(target)!=manifest['schema']
                or staging.state(target,manifest['tables'])!=manifest['row_state']
                or staging.sequence_state(target,list(manifest['sequences']))!=manifest['sequences']
                or checkpoint.local.fence_state(target)!=manifest['fences']):
            raise ValueError('exact original cutover state required')
        archive.mkdir(mode=0o700)
        for name in ('suspended.json','latest.json'):
            (control/name).rename(archive/name)
        checkpoint.local.sync_directory(archive)
        checkpoint.atomic(control/STATE,dict(version='g2c-hk-local.1',state='BACKUP_REQUIRED',instance=release['instance'],
            lineage=release['lineage'],checkpoint=release['checkpoint']))
        checkpoint.atomic(control/'release.json',release,public=True)
    print('PASS HK release verified; business gate waits for manual backup')


def allow_writes(control,root):
    if not local_database_target():raise ValueError('explicit HK socket target required')
    with checkpoint.lock(control),checkpoint.operator() as (target,_),target.transaction():
        target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        checkpoint.require_release(target,control)
        pending=cutover_state(control)
        day=checkpoint.verified(control/'daily.json')
        if day['state']!='COMPLETE' or day['day']!=datetime.now(timezone.utc).strftime('%Y%m%d'):
            raise ValueError('verified first HK manual backup required')
        signed=checkpoint.verified(BACKUPS/day['day']/'manifest.json')
        before=checkpoint.verified(root/'safety/manifest.json')
        active=checkpoint.verified(control/'release.json')
        if (pending.get('version')!='g2c-hk-local.1' or pending['state']!='BACKUP_REQUIRED'
                or signed['archived_instance']!=pending['instance'] or signed['lineage']!=pending['lineage']
                or signed['dump_sha256']!=active['checkpoint'] or signed['row_state']!=before['row_state']
                or signed['fences']!=before['fences'] or signed['sequences']!=before['sequences']
                or staging.state(target,signed['tables'])!=signed['row_state']
                or checkpoint.local.fence_state(target)!=signed['fences']
                or staging.sequence_state(target,list(signed['sequences']))!=signed['sequences']):
            raise ValueError('verified first HK manual backup required')
        checkpoint.atomic(control/STATE,dict(pending,state='FORWARD_ONLY',first_backup=signed['dump_sha256']))
    print('PASS HK manual backup complete; forward-only business gate opened')


def main():
    authorization()
    if sys.argv[1:]==['serve']:
        serve(ROOT)
    operations={'stage':stage,'activate':activate,'allow-writes':allow_writes}
    if len(sys.argv)!=2 or sys.argv[1] not in operations:raise ValueError('explicit HK PG operation required')
    load_secret_environment('recovery')
    operations[sys.argv[1]](Path(os.environ['CJ_DEPLOY_CONTROL']),ROOT)


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,psycopg.Error,subprocess.SubprocessError):
        print('ALERT HK PG cutover unavailable; reconcile original state',file=sys.stderr)
        raise SystemExit(1) from None
