"""Image schema artifact derived only from the verified committed migrations.

Build on a new private PG17 blueprint, never dump a provider's schema. Restore
uses the standard pre-data / data / post-data sequence with all final original
constraints, ACLs, RLS and triggers. No trigger is disabled or weakened.
"""
import json
from pathlib import Path
import re
import subprocess

import psycopg
import migrate
from cj_api.local_app import local_connection
from deploy.recovery import pg_environment,checksum


def migration_identity():return [dict(version=m['version'],sha256=m['sha256']) for m in migrate.load()]


def generate(config,root):
    config=local_connection(config);root=Path(root);root.mkdir(mode=0o700)
    with psycopg.connect(**config) as connection:
        if connection.execute('SHOW server_version_num').fetchone()[0][:2]!='17':raise ValueError('private_PG17_blueprint_required')
        if migrate.applied(connection)!=[m['version'] for m in migrate.load()]:raise ValueError('exact_blueprint_migrations_required')
        tables=migrate.inventory(connection)
        for table in tables:
            if table not in ('cj.schema_migrations','cj.deployment_identity') and connection.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():
                raise ValueError('schema_blueprint_must_have_no_business_data')
    roles=[]
    for migration in migrate.load():
        roles+=re.findall(r'^CREATE ROLE cj_(?:m1_runtime|local_cleanup)\b[^\n]*;', (migrate.ROOT/migration['file']).read_text(),re.M)
    if len(roles)!=2:raise ValueError('exact_committed_application_roles_required')
    (root/'roles.sql').write_text('\n'.join(roles)+'\n')
    for section in ('pre-data','post-data'):
        with (root/(section+'.sql')).open('xb') as output:
            subprocess.run(['pg_dump','--schema-only','--no-owner','--section='+section],
                env=pg_environment(config),stdout=output,stderr=subprocess.PIPE,check=True,timeout=120)
    profile=dict(version='g2c-beta-image-schema.1',migrations=migration_identity(),tables=tables,
        files={name:checksum(root/name) for name in ('roles.sql','pre-data.sql','post-data.sql')})
    (root/'profile.json').write_text(json.dumps(profile,sort_keys=True))


def load(root):
    root=Path(root);value=json.loads((root/'profile.json').read_bytes())
    if (value['version']!='g2c-beta-image-schema.1' or value['migrations']!=migration_identity()
            or set(value['files'])!={'roles.sql','pre-data.sql','post-data.sql'}
            or any(checksum(root/name)!=sha for name,sha in value['files'].items())):
        raise ValueError('exact_image_schema_required')
    return value


def apply_data(target,archive,order,root):
    root=Path(root);load(root)
    import tempfile
    with tempfile.NamedTemporaryFile(prefix='g2c-beta-restore-',suffix='.sql') as data:
        subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-acl','--use-list',str(order),'--file=-',str(archive)],
            stdout=data,stderr=subprocess.PIPE,check=True,timeout=300)
        versions=','.join('('+str(m['version'])+')' for m in migrate.load())
        command=['psql','--no-psqlrc','--single-transaction','--set=ON_ERROR_STOP=1','--dbname='+target['dbname']]
        for file in (root/'roles.sql',root/'pre-data.sql',Path(data.name),root/'post-data.sql'):command+=['--file='+str(file)]
        command+=['--command=INSERT INTO cj.schema_migrations(version) VALUES'+versions,
                  '--command=INSERT INTO cj.deployment_identity(singleton) VALUES(true)']
        subprocess.run(command,env=pg_environment(target),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=300)
