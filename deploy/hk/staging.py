"""A fresh private PG17 staging cluster; no cloud credentials reach pg_dump.

Only the already authenticated/reset/TLS-checked source session reads cloud
rows. Binary COPY feeds this Unix-only scratch cluster, never an application
endpoint. Native pg_dump then reads the verified local representation.
"""
from contextlib import contextmanager,nullcontext
import os
import hashlib
import fcntl
import stat
import re
from pathlib import Path
import pwd
import subprocess
import tempfile

import psycopg
from psycopg import sql

from . import schema
from deploy.recovery import FENCES

PG17=Path('/usr/lib/postgresql/17/bin')
ACTIVE_CLUSTERS={}


def environment(config=None):
    # No parent environment: in particular no Supabase URI, OSS or signing keys.
    env=dict(PATH=str(PG17)+':/usr/bin:/bin',LANG='C',LC_ALL='C')
    if config is not None:
        env.update(PGHOST=config['host'],PGPORT=str(config['port']),PGUSER=config['user'],
                   PGDATABASE=config['dbname'],PGSSLMODE='disable',PGPASSFILE=config['passfile'])
    return env


@contextmanager
def cluster(*,root=None,resume=False):
    if os.getuid()==0:raise ValueError('private_staging_requires_unprivileged_operator')
    durable=root is not None
    if durable and Path(root).is_symlink():raise ValueError('original_cluster_directory_symlink_refused')
    directory=nullcontext(str(Path(root).resolve())) if durable else tempfile.TemporaryDirectory(prefix='g2c-stage-')
    with directory as directory_name:
        root=Path(directory_name)
        if durable and not resume:root.mkdir(mode=0o700)
        metadata=root.stat()
        if metadata.st_uid!=os.getuid() or stat.S_IMODE(metadata.st_mode)!=0o700:
            raise ValueError('owned_private_cluster_directory_required')
        with (root/'cluster.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            data=root/'data';pg=PG17;child_environment=environment()
            role=pwd.getpwuid(os.getuid()).pw_name
            passfile=root/'empty.pgpass'
            from . import checkpoint
            birth=None
            if resume:
                if not durable:raise ValueError('original_durable_cluster_required')
                data_metadata=data.lstat()
                if (not stat.S_ISDIR(data_metadata.st_mode) or data_metadata.st_uid!=os.getuid()
                        or stat.S_IMODE(data_metadata.st_mode)!=0o700):raise ValueError('owned_original_PG_directory_required')
                birth=checkpoint.verified(root/'birth.json')
                if (birth.get('version')!='g2c-beta-isolated-cluster.1' or birth['data']!=str(data)
                        or birth['role']!=role or birth['uid']!=os.getuid()):
                    raise ValueError('original_owned_cluster_identity_required')
                socket=Path(birth['socket'])
                if socket.parent!=Path('/tmp').resolve() or not socket.name.startswith('g2c-socket-'):
                    raise ValueError('original_private_socket_path_required')
                socket.mkdir(mode=0o700,exist_ok=True)
            else:socket=Path(tempfile.mkdtemp(prefix='g2c-socket-',dir='/tmp')).resolve()
            socket_metadata=socket.lstat()
            if (not stat.S_ISDIR(socket_metadata.st_mode) or socket_metadata.st_uid!=os.getuid()
                    or stat.S_IMODE(socket_metadata.st_mode)!=0o700):raise ValueError('owned_private_socket_required')
            config=dict(host=str(socket),port=55884,user=role,dbname='postgres',passfile=str(passfile),connect_timeout=5)
            def run(*args,check=True):
                return subprocess.run([str(pg/args[0]),*map(str,args[1:])],env=child_environment,check=check,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
            if not resume:
                passfile.touch(mode=0o600)
                run('initdb','-D',data,'--username='+role,'--auth-local=peer','--auth-host=reject','--encoding=UTF8','--locale=C')
                # Only the owning Unix user can select the two fixed restricted
                # roles for RLS checks on this private socket, never on cloud DB.
                (data/'pg_hba.conf').write_text('local all all peer map=g2c_owned\nhost all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n')
                (data/'pg_ident.conf').write_text(''.join('g2c_owned '+role+' '+database_role+'\n' for database_role in (role,'cj_m1_runtime','cj_local_cleanup')))
            if (data/'PG_VERSION').read_text().strip()!='17':raise ValueError('original_PG17_directory_required')
            control=run('pg_controldata',data).stdout.decode('ascii')
            identifiers=re.findall(r'^Database system identifier:\s+(\d+)\s*$',control,re.M)
            if len(identifiers)!=1 or birth is not None and identifiers[0]!=birth['system_identifier']:
                raise ValueError('original_cluster_system_identity_changed_before_start')
            started=owned=False
            status=run('pg_ctl','-D',data,'status',check=False).returncode
            if status==3:
                run('pg_ctl','-D',data,'-l',root/'postgres.log','-o',f"-c listen_addresses='' -k {socket} -p 55884 -c unix_socket_permissions=0700",'-w','start');started=True
            elif status!=0:raise ValueError('original_cluster_status_unknown')
            try:
                with psycopg.connect(**config) as connection:
                    actual=connection.execute("SELECT system_identifier::text,current_setting('data_directory'),current_setting('listen_addresses'),current_setting('server_version_num') FROM pg_catalog.pg_control_system()").fetchone()
                if actual[0]!=identifiers[0] or actual[1]!=str(data) or actual[2]!='' or actual[3][:2]!='17':
                    raise ValueError('owned_PG17_Unix_only_cluster_required')
                if birth is not None and birth['system_identifier']!=actual[0]:raise ValueError('original_cluster_system_identity_changed')
                owned=True
                if durable and not resume:
                    checkpoint.atomic(root/'birth.json',dict(version='g2c-beta-isolated-cluster.1',system_identifier=actual[0],
                        data=str(data),socket=str(socket),role=role,uid=os.getuid()))
                ACTIVE_CLUSTERS[str(socket)]=(actual[0],str(data),durable)
                try:yield config
                finally:del ACTIVE_CLUSTERS[str(socket)]
            finally:
                # Stop for a bounded operator container lifetime. Durable targets
                # keep all data and signed birth proof, including on any failure.
                if started or owned:
                    run('pg_ctl','-D',data,'-m','fast','-w','stop')
                    socket.rmdir()


def require_isolated(connection,config):
    registered=ACTIVE_CLUSTERS.get(config['host'])
    if registered is None or not registered[2]:raise ValueError('current_process_owned_fresh_PG17_cluster_required')
    actual=connection.execute("SELECT system_identifier::text,current_setting('data_directory'),current_setting('listen_addresses'),current_setting('server_version_num') FROM pg_catalog.pg_control_system()").fetchone()
    if actual[:2]!=registered[:2] or actual[2]!='' or actual[3][:2]!='17':
        raise ValueError('owned_PG17_Unix_only_cluster_required')
    databases=[row[0] for row in connection.execute('SELECT datname FROM pg_catalog.pg_database WHERE NOT datistemplate ORDER BY 1')]
    if databases!=sorted(set(('postgres',config['dbname']))):raise ValueError('isolated_rehearsal_cluster_only_required')


def business_tables(tables):
    return sorted((name for name in tables if name not in ('cj.schema_migrations','cj.deployment_identity')),
                  key=lambda name:(name.removeprefix('public.') not in FENCES,name))


def sequence_names(connection):
    return [row[0] for row in connection.execute("SELECT n.nspname||'.'||c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname IN ('public','cj') AND c.relname LIKE 'cj_%' ORDER BY 1")]


def sequence_state(connection,names):
    return {name:list(connection.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(sql.Identifier(*name.split('.')))).fetchone()) for name in names}


def state(connection,tables):
    """Canonical UTC row multiset hashes; no row text enters a manifest or log."""
    result={}
    for table in business_tables(tables):
        rows=connection.execute(sql.SQL("SELECT encode(sha256(convert_to(row_to_json(t)::text,'UTF8')),'hex') FROM {} t ORDER BY 1").format(
            sql.Identifier(*table.split('.')))).fetchall()
        result[table]=dict(count=len(rows),sha256=hashlib.sha256(''.join(row[0] for row in rows).encode('ascii')).hexdigest())
    return result


def dump(source,tables,destination,schema_root):
    """Source is the caller's checked session and repeatable-read transaction."""
    schema_root=Path(schema_root);profile=schema.load(schema_root)
    if tables!=profile['tables']:raise ValueError('exact_staging_application_inventory_required')
    expected=state(source,tables)
    names=sequence_names(source)
    if names!=profile['sequences']:raise ValueError('exact_staging_sequence_inventory_required')
    sequences=sequence_state(source,names)
    with cluster() as config:
        def apply(*files):
            command=[str(PG17/'psql'),'--no-psqlrc','--single-transaction','--set=ON_ERROR_STOP=1']
            for file in files:command+=['--file='+str(schema_root/file)]
            subprocess.run(command,env=environment(config),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
        apply('roles.sql','pre-data.sql')
        with psycopg.connect(**config) as target:
            target.execute("SET TIME ZONE 'UTC'")
            for table in business_tables(tables):
                ident=sql.Identifier(*table.split('.'))
                with source.cursor().copy(sql.SQL('COPY {} TO STDOUT (FORMAT BINARY)').format(ident)) as incoming:
                    with target.cursor().copy(sql.SQL('COPY {} FROM STDIN (FORMAT BINARY)').format(ident)) as outgoing:
                        for chunk in incoming:outgoing.write(chunk)
            for name,(last,called) in sequences.items():target.execute('SELECT pg_catalog.setval(%s::regclass,%s,%s)',(name,last,called))
        apply('post-data.sql')
        with psycopg.connect(**config) as target:
            target.execute("SET TIME ZONE 'UTC'")
            if state(target,tables)!=expected or sequence_state(target,names)!=sequences:raise ValueError('staging_row_state_mismatch')
        command=[str(PG17/'pg_dump'),'--format=custom','--data-only','--no-owner','--no-acl']
        for table in business_tables(tables)+names:command.append('--table='+table)
        with Path(destination).open('xb') as output:
            subprocess.run(command,env=environment(config),stdout=output,stderr=subprocess.PIPE,check=True,timeout=300)
    return expected,sequences
