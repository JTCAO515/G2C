"""Provision only a NEW private empty PG, Unix socket, named roles and empty passfile.

Never reads a DSN. Always stops the cluster and preserves its local inventory/data.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
import psycopg

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'backend/feedback'),str(ROOT/'backend/auth'),str(ROOT/'backend/message'),str(ROOT/'backend/run')]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pg-bin',required=True,type=Path)
    args=parser.parse_args()
    binary=args.pg_bin.resolve()
    root=ROOT/'backend/feedback/.local'
    root.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='pg-',dir=root))
    socket=Path(tempfile.mkdtemp(prefix='cj023-',dir='/tmp'))
    os.chmod(socket,0o700)
    passfile=work/'empty.pgpass'
    passfile.touch(mode=0o600)
    role='cj023_'+uuid.uuid4().hex[:10]
    runtime=role+'_runtime'
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ'))}
    # psycopg itself must also see no ambient PG service/DSN configuration.
    for key in list(os.environ):
        if key.startswith(('PG', 'LIBPQ')): del os.environ[key]
    # Explicit child environment also neutralizes any inherited service/passfile lookup.
    env.update(PGPASSFILE=str(passfile),PGSERVICEFILE=str(work/'no-service'),PGSYSCONFDIR=str(work))
    port=56423
    admin=dict(host=str(socket),port=port,dbname='postgres',user=role,password='',passfile=str(passfile),
               sslmode='disable',gssencmode='disable',connect_timeout=3)
    config=dict(admin,user=runtime)
    inventory=dict(base='8f2ff45519d1d09f178f1fa766b6829d81bda77a',data=str(work/'data'),socket=str(socket),
                   port=port,bootstrap_role=role,runtime_role=runtime,passfile=str(passfile),listen_addresses='',
                   stopped=False,external_services='UNRUN')
    log=work/'commands.log'
    def command(*parts):
        result=subprocess.run([str(binary/parts[0]),*parts[1:]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        with log.open('a') as f:f.write(result.stdout)
        if result.returncode: raise RuntimeError('private PG command failed; see local commands.log')
    started=False
    success=False
    try:
        command('initdb','-D',str(work/'data'),'-U',role,'--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8')
        with (work/'data/postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses = ''\nunix_socket_directories = '"+str(socket)+"'\nport = "+str(port)+"\nlog_statement = 'none'\nlog_min_error_statement = 'panic'\n")
        command('pg_ctl','-D',str(work/'data'),'-l',str(work/'server.log'),'-w','start')
        started=True
        with psycopg.connect(**admin) as conn:
            for domain in ('feedback','message','run'):
                conn.execute((ROOT/('backend/'+domain+'/sql/candidate.sql')).read_text())
            conn.execute(psycopg.sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(psycopg.sql.Identifier(runtime)))
            conn.execute(psycopg.sql.SQL('GRANT SELECT, INSERT ON cj_feedback_action TO {}').format(psycopg.sql.Identifier(runtime)))
            inventory['postgres']=conn.execute('SELECT version()').fetchone()[0]
            assert conn.execute('SHOW listen_addresses').fetchone()[0]==''
            conn.execute(psycopg.sql.SQL('GRANT SELECT, INSERT, UPDATE ON cj_message_scope,cj_message_chat,cj_message_receipt,cj_message_delivery,cj_message_draft,cj_run_scope,cj_run_record,cj_run_event TO {}').format(psycopg.sql.Identifier(runtime)))
            conn.execute(psycopg.sql.SQL('GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}').format(psycopg.sql.Identifier(runtime)))
        import test_domain, test_postgres, test_sources
        test_postgres.CONFIG=config
        test_sources.CONFIG=config
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(test_domain),unittest.defaultTestLoader.loadTestsFromModule(test_postgres),unittest.defaultTestLoader.loadTestsFromModule(test_sources)])
        with (work/'tests.txt').open('w') as output:
            result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
        inventory.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors))
        print((work/'tests.txt').read_text())
        success=result.wasSuccessful()
        from cj_feedback.postgres import Repository
        from cj_feedback import Action
        from test_domain import raw
        repo=Repository(lambda:psycopg.connect(**config),'restart-fixture',lambda stage:None)
        original=repo.submit(Action(raw('restart')))
        linked_scope='sources/test_public_message_run_association_minimal_persisted/a'
        linked=Repository(lambda:psycopg.connect(**config),linked_scope,lambda stage:None).query_action('one')
        assert linked is not None and linked.source is not None
        command('pg_ctl','-D',str(work/'data'),'-m','fast','-w','stop')
        started=False
        command('pg_ctl','-D',str(work/'data'),'-l',str(work/'server.log'),'-w','start')
        started=True
        recovered=Repository(lambda:psycopg.connect(**config),'restart-fixture',lambda stage:None).query_action('restart')
        assert original==recovered
        inventory['restart_original_receipt']='PASS'
        linked_recovered=Repository(lambda:psycopg.connect(**config),linked_scope,lambda stage:None).query_action('one')
        assert linked==linked_recovered
        inventory['restart_linked_receipt']='PASS'
        # No generated server/command log includes submitted text or exception fixture secrets.
        logs=(work/'server.log').read_text()+log.read_text()
        assert 'USER_VOLUNTARILY_TYPED_SENTINEL' not in logs and 'SECRET' not in logs
        inventory['log_content_check']='PASS'
    finally:
        if started:
            command('pg_ctl','-D',str(work/'data'),'-m','fast','-w','stop')
        inventory['stopped']=not (work/'data/postmaster.pid').exists()
        (work/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        print('Preserved private inventory:',work/'inventory.json')
    return 0 if success else 1


if __name__=='__main__':sys.exit(main())
