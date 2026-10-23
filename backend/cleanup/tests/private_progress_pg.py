"""New private SELECT-only authenticated progress tests; no old instance access."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
WORK=ROOT/'backend/cleanup/.local/cj024-progress-20261023'
SOCKET=ROOT/'backend/cleanup/.local/c24p'
PORT=55459
ROLE='cj024progress'
READ_ROLE='cj024progress_read'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pg-bin',required=True,type=Path)
    p.add_argument('--driver',required=True,type=Path)
    p.add_argument('--auth-root',required=True,type=Path)
    args=p.parse_args()
    for name in list(os.environ):
        if name.startswith(('PG','LIBPQ')): del os.environ[name]
    sys.path[:0]=[str(args.driver),str(args.auth_root),str(HERE),str(ROOT/'backend/cleanup')]
    import psycopg
    import test_progress_read
    if WORK.exists() or SOCKET.exists() or Path('/tmp/.s.PGSQL.55459').exists():
        raise SystemExit('new progress test resource exists; do not reuse')
    WORK.mkdir(mode=0o700,parents=True);SOCKET.mkdir(mode=0o700)
    empty=WORK/'empty.pgpass';empty.touch(mode=0o600)
    env=dict(os.environ,PGPASSFILE=str(empty),PGSERVICEFILE=str(WORK/'no-service'),PGSYSCONFDIR=str(WORK))
    config=dict(host=str(SOCKET),port=PORT,user=ROLE,dbname='postgres',password='',passfile=str(empty),
                sslmode='disable',gssencmode='disable',connect_timeout=3,options='')
    inventory=dict(data=str(WORK/'data'),socket=str(SOCKET),port=PORT,role=ROLE,read_role=READ_ROLE,
                   listen_addresses='',driver=psycopg.__version__,ambient_dsn='NOT_READ',stopped=False)
    def command(*parts):
        r=subprocess.run([str(args.pg_bin/parts[0]),*parts[1:]],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        with (WORK/'commands.log').open('a') as f:f.write(r.stdout)
        if r.returncode:raise RuntimeError('private PG failed; inspect preserved commands.log')
    started=success=False
    try:
        command('initdb','-D',str(WORK/'data'),'-U',ROLE,'--auth-local=trust','--auth-host=reject','--no-locale','--encoding=UTF8')
        with (WORK/'data/postgresql.conf').open('a') as f:
            f.write("\nlisten_addresses = ''\nunix_socket_directories = '"+str(SOCKET)+"'\nport = "+str(PORT)+"\nlog_statement = 'none'\nlog_min_error_statement = 'panic'\n")
        command('pg_ctl','-D',str(WORK/'data'),'-l',str(WORK/'server.log'),'-w','start');started=True
        with psycopg.connect(**config) as c:
            inventory['postgres']=c.execute('SELECT version()').fetchone()[0]
            assert c.execute('SHOW listen_addresses').fetchone()[0]==''
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            c.execute((ROOT/'backend/cleanup/sql/candidate.sql').read_text())
            c.execute('CREATE ROLE cj024progress_read LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
            c.execute('GRANT SELECT ON cj_cleanup_journal_candidate TO cj024progress_read')
        test_progress_read.ADMIN=config
        test_progress_read.READ=dict(config,user=READ_ROLE)
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_progress_read.ProgressTests)
        with (WORK/'tests.log').open('w') as f:r=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
        print((WORK/'tests.log').read_text())
        inventory.update(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors))
        logs=(WORK/'commands.log').read_text()+(WORK/'server.log').read_text()
        assert 'PRIVATE_CLOSE_ERROR' not in logs and 'SYNTHETIC-NOT-A-REAL-TOKEN' not in logs
        inventory['sensitive_log_payloads']='ABSENT'
        success=r.wasSuccessful()
    finally:
        if started:command('pg_ctl','-D',str(WORK/'data'),'-m','fast','-w','stop')
        inventory['pid_exists']=(WORK/'data/postmaster.pid').exists()
        inventory['socket_exists']=(SOCKET/('.s.PGSQL.'+str(PORT))).exists()
        inventory['socket_lock_exists']=(SOCKET/('.s.PGSQL.'+str(PORT)+'.lock')).exists()
        inventory['stopped']=not inventory['pid_exists'] and not inventory['socket_exists'] and not inventory['socket_lock_exists']
        (WORK/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
        print('Private progress inventory:',WORK/'inventory.json')
    return 0 if success and inventory['stopped'] else 1
if __name__=='__main__':sys.exit(main())
