"""New empty Unix-only cluster for the close-fence repair; never restarts old clusters."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
WORK=ROOT/'backend/cleanup/.local/cj024-close-20261022'
SOCKET=ROOT/'backend/cleanup/.local/c24c'
PORT=55458
ROLE='cj024close'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pg-bin',type=Path,required=True)
    parser.add_argument('--driver',type=Path,required=True)
    args=parser.parse_args()
    for name in list(os.environ):
        if name.startswith(('PG','LIBPQ')): del os.environ[name]
    sys.path[:0]=[str(args.driver),str(HERE),str(ROOT/'backend/auth'),str(ROOT/'backend/cleanup')]
    import psycopg
    import test_postgres
    import test_close_fence
    if WORK.exists() or SOCKET.exists() or Path('/tmp/.s.PGSQL.55458').exists():
        raise SystemExit('new close-test resource already exists; do not reuse')
    WORK.mkdir(mode=0o700,parents=True)
    SOCKET.mkdir(mode=0o700)
    empty=WORK/'empty.pgpass';empty.touch(mode=0o600)
    env=dict(os.environ,PGPASSFILE=str(empty),PGSERVICEFILE=str(WORK/'no-service'),PGSYSCONFDIR=str(WORK))
    config=dict(host=str(SOCKET),port=PORT,user=ROLE,dbname='postgres',password='',passfile=str(empty),
                sslmode='disable',gssencmode='disable',connect_timeout=3,options='')
    inventory=dict(data=str(WORK/'data'),socket=str(SOCKET),port=PORT,role=ROLE,listen_addresses='',
                   driver=psycopg.__version__,ambient_dsn='NOT_READ',stopped=False)
    def command(*parts):
        result=subprocess.run([str(args.pg_bin/parts[0]),*parts[1:]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        with (WORK/'commands.log').open('a') as f: f.write(result.stdout)
        if result.returncode: raise RuntimeError('private PG command failed; see preserved commands.log')
    started=success=False
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
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_close_fence.CloseFenceTests)
        with (WORK/'tests.log').open('w') as f: result=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        inventory.update(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors))
        print((WORK/'tests.log').read_text())
        logs=(WORK/'commands.log').read_text()+(WORK/'server.log').read_text()
        assert all(word not in logs for word in ('PRIMARY_COMMIT_TEST_SENTINEL','SECONDARY_CLOSE_TEST_SENTINEL','SECONDARY_ROLLBACK_TEST_SENTINEL'))
        inventory['fault_payload_in_logs']='ABSENT'
        success=result.wasSuccessful()
    finally:
        if started: command('pg_ctl','-D',str(WORK/'data'),'-m','fast','-w','stop')
        inventory['pid_exists']=(WORK/'data/postmaster.pid').exists()
        inventory['socket_exists']=(SOCKET/('.s.PGSQL.'+str(PORT))).exists()
        inventory['socket_lock_exists']=(SOCKET/('.s.PGSQL.'+str(PORT)+'.lock')).exists()
        inventory['stopped']=not inventory['pid_exists'] and not inventory['socket_exists'] and not inventory['socket_lock_exists']
        (WORK/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        print('Private close-test inventory:',WORK/'inventory.json')
    return 0 if success and inventory['stopped'] else 1

if __name__=='__main__':sys.exit(main())
