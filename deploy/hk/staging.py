"""A fresh private PG17 staging cluster; no cloud credentials reach pg_dump.

Only the already authenticated/reset/TLS-checked source session reads cloud
rows. Binary COPY feeds this Unix-only scratch cluster, never an application
endpoint. Native pg_dump then reads the verified local representation.
"""
from contextlib import contextmanager
import os
import hashlib
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
def cluster():
    if os.getuid()==0:raise ValueError('private_staging_requires_unprivileged_operator')
    with tempfile.TemporaryDirectory(prefix='g2c-stage-') as directory:
        root=Path(directory);data=root/'data';socket=root/'s';socket.mkdir(mode=0o700)
        pg=PG17;child_environment=environment()
        role=pwd.getpwuid(os.getuid()).pw_name
        passfile=root/'empty.pgpass';passfile.touch(mode=0o600)
        def run(*args):
            subprocess.run([str(pg/args[0]),*map(str,args[1:])],env=child_environment,check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        run('initdb','-D',data,'--username='+role,'--auth-local=peer','--auth-host=reject','--encoding=UTF8','--locale=C')
        # The owning Unix user is the sole local operator. Fixed peer mappings
        # let the restored application's two restricted roles exercise RLS;
        # no other OS user can reach this 0700 socket and no TCP is enabled.
        (data/'pg_hba.conf').write_text('local all all peer map=g2c_owned\nhost all all 0.0.0.0/0 reject\nhost all all ::0/0 reject\n')
        (data/'pg_ident.conf').write_text(''.join('g2c_owned '+role+' '+database_role+'\n' for database_role in (role,'cj_m1_runtime','cj_local_cleanup')))
        run('pg_ctl','-D',data,'-l',root/'postgres.log','-o',f"-c listen_addresses='' -k {socket} -p 55884 -c unix_socket_permissions=0700",'-w','start')
        config=dict(host=str(socket),port=55884,user=role,dbname='postgres',passfile=str(passfile),connect_timeout=5)
        try:
            with psycopg.connect(**config) as connection:
                if connection.execute('SHOW server_version_num').fetchone()[0][:2]!='17':
                    raise ValueError('private_PG17_staging_required')
            with psycopg.connect(**config) as connection:
                system=connection.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
            ACTIVE_CLUSTERS[str(socket)]=(system,str(data))
            try:yield config
            finally:del ACTIVE_CLUSTERS[str(socket)]
        finally:run('pg_ctl','-D',data,'-m','immediate','-w','stop')


def require_isolated(connection,config):
    registered=ACTIVE_CLUSTERS.get(config['host'])
    if registered is None:raise ValueError('current_process_owned_fresh_PG17_cluster_required')
    actual=connection.execute("SELECT system_identifier::text,current_setting('data_directory'),current_setting('listen_addresses'),current_setting('server_version_num') FROM pg_catalog.pg_control_system()").fetchone()
    if actual[:2]!=registered or actual[2]!='' or actual[3][:2]!='17':
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
