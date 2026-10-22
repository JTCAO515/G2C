"""One new private Unix-only PG cluster; never an existing instance or ambient DSN."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
WORK=ROOT/'backend/cleanup/.local/cj024-journal-20261022'
SOCKET=ROOT/'backend/cleanup/.local/c24s'
PORT=55457
ROLE='cj024journal'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pg-bin',type=Path,required=True)
    parser.add_argument('--driver',type=Path,required=True)
    args=parser.parse_args()
    # No secrets/ambient values are printed. Explicit config only.
    for name in list(os.environ):
        if name.startswith(('PG','LIBPQ')): del os.environ[name]
    sys.path[:0]=[str(args.driver),str(HERE),str(ROOT/'backend/auth'),str(ROOT/'backend/cleanup')]
    import psycopg
    from dataclasses import replace
    from cj_cleanup.postgres import Repository,CommitUnknown
    from test_cleanup import CleanupTests
    import test_postgres
    if WORK.exists() or SOCKET.exists() or Path('/tmp/.s.PGSQL.55457').exists():
        raise SystemExit('private resource already exists; do not reuse')
    WORK.mkdir(mode=0o700,parents=True)
    SOCKET.mkdir(mode=0o700)
    empty=WORK/'empty.pgpass';empty.touch(mode=0o600)
    env=dict(os.environ,PGPASSFILE=str(empty),PGSERVICEFILE=str(WORK/'no-service'),PGSYSCONFDIR=str(WORK))
    config=dict(host=str(SOCKET),port=PORT,user=ROLE,dbname='postgres',password='',passfile=str(empty),
                sslmode='disable',gssencmode='disable',connect_timeout=3,options='')
    inventory=dict(data=str(WORK/'data'),socket=str(SOCKET),port=PORT,role=ROLE,listen_addresses='',
                   driver=psycopg.__version__,ambient_dsn='NOT_READ',stopped=False)
    started=False
    def command(*parts):
        result=subprocess.run([str(args.pg_bin/parts[0]),*parts[1:]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        with (WORK/'commands.log').open('a') as f: f.write(result.stdout)
        if result.returncode: raise RuntimeError('private PG command failed; see preserved commands.log')
    success=False
    try:
        command('initdb','-D',str(WORK/'data'),'-U',ROLE,'--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8')
        with (WORK/'data/postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses = ''\nunix_socket_directories = '"+str(SOCKET)+"'\nport = "+str(PORT)+"\nlog_statement = 'none'\nlog_min_error_statement = 'panic'\n")
        command('pg_ctl','-D',str(WORK/'data'),'-l',str(WORK/'server.log'),'-w','start');started=True
        with psycopg.connect(**config) as c:
            inventory['postgres']=c.execute('SELECT version()').fetchone()[0]
            assert c.execute('SHOW listen_addresses').fetchone()[0]==''
            assert c.execute('SHOW unix_socket_directories').fetchone()[0]==str(SOCKET)
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            c.execute((ROOT/'backend/cleanup/sql/candidate.sql').read_text())
            inventory['tables']=[r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()]
            assert inventory['tables']==['cj_cleanup_journal_candidate']
        test_postgres.CONFIG=config
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_postgres.PostgresTests)
        with (WORK/'tests.log').open('w') as f: result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        inventory.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors))
        print((WORK/'tests.log').read_text())
        # Fixed original scope fixture: confirmed revocation, one durable task-stop
        # intent whose COMMIT ACK is lost. Stop/start same new instance exactly once.
        fixtures=CleanupTests();fixtures.setUp()
        scope=replace(fixtures.scope,subject='synthetic-restart-original')
        initial=fixtures.op(True,scope)
        factory=lambda:psycopg.connect(**config)
        repo=Repository(factory,scope,lambda s:None)
        op=repo.create(initial)
        op=repo.intent(op.operation_id,op.revision,'auth_revocation','original-revocation')
        revocation_raw=b' '+fixtures.result(op,'auth_revocation')+b'\n'
        op=repo.receipt(op.operation_id,op.revision,'auth_revocation',revocation_raw)
        fault=Repository(lambda:test_postgres.Wrapped(factory(),'after_commit'),scope,lambda s:None)
        try: fault.intent(op.operation_id,op.revision,'tasks_stopped','original-task-stop')
        except CommitUnknown: pass
        else: raise AssertionError('commit ACK fault did not fire')
        before=repo.query(op.operation_id);history=repo.journal(op.operation_id)
        command('pg_ctl','-D',str(WORK/'data'),'-m','fast','-w','stop');started=False
        command('pg_ctl','-D',str(WORK/'data'),'-l',str(WORK/'server.log'),'-w','start');started=True
        rebuilt=Repository(factory,scope,lambda s:None)
        after=rebuilt.query(op.operation_id)
        assert before==after and rebuilt.journal(op.operation_id)==history
        assert after.steps[0].receipt_bytes==revocation_raw
        assert after.steps[1].invocation=='original-task-stop'
        after=rebuilt.recover(after.operation_id,after.revision)
        assert after.status=='unknown' and after.steps[1].state=='unknown'
        assert after.steps[0].state=='confirmed'
        assert rebuilt.query(op.operation_id)==after
        # Read-only observation cannot silently settle unknown to complete.
        final_history=rebuilt.journal(op.operation_id)
        assert rebuilt.query(op.operation_id).status=='unknown'
        assert rebuilt.journal(op.operation_id)==final_history
        inventory['restart_original_operation_history_unknown']='PASS'
        inventory['restart_fixture_revision']=after.revision
        logs=(WORK/'commands.log').read_text()+(WORK/'server.log').read_text()
        assert 'SENSITIVE_FAULT_PAYLOAD' not in logs
        inventory['logs_sensitive_fault_payload']='ABSENT'
        success=result.wasSuccessful()
    finally:
        if started: command('pg_ctl','-D',str(WORK/'data'),'-m','fast','-w','stop')
        inventory['pid_exists']=(WORK/'data/postmaster.pid').exists()
        inventory['socket_exists']=(SOCKET/('.s.PGSQL.'+str(PORT))).exists()
        inventory['socket_lock_exists']=(SOCKET/('.s.PGSQL.'+str(PORT)+'.lock')).exists()
        inventory['stopped']=not inventory['pid_exists'] and not inventory['socket_exists'] and not inventory['socket_lock_exists']
        (WORK/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        print('Private inventory:',WORK/'inventory.json')
    return 0 if success and inventory['stopped'] else 1


if __name__=='__main__': sys.exit(main())
