"""Fresh isolated PG per original BG3 consumer scenario, never existing data."""
from pathlib import Path
import json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import pg_suites,migrate,psycopg


def main():
    statuses=[]
    for i,case in enumerate(sys.argv[1:] or ('success','unknown','ack','output','time','tail','budget','corrupt-trip','cancel','account','stale')):
        with tempfile.TemporaryDirectory(prefix='cj-bg3-',dir='/tmp') as folder:
            root=Path(folder)
            with pg_suites.cluster('background_v3_'+case,port=55815,role='cj_bg3_'+str(i),root=root/'pg',socket=root/'s') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    assert conn.execute('SHOW listen_addresses').fetchone()==('',)
                    migrate.up(conn,migrate.load(),migrate.load()[-1]['version'])
                path=root/'conn.json';path.write_text(json.dumps(config));path.chmod(0o600)
                env=dict(pg_suites.clean_env(),BG3_CASE=case,CJ_E2E_CONNINFO=str(path),PYTHONPATH=pg_suites.pythonpath())
                result=subprocess.run([sys.executable,'-B',str(ROOT/'backend/cj_api/tests/background_v3_pg.py')],env=env);statuses.append(result.returncode)
            assert not (root/'pg/data/postmaster.pid').exists()
        if statuses[-1]:break
    print('BG3 cases:',statuses);return int(any(statuses))


if __name__=='__main__':raise SystemExit(main())
