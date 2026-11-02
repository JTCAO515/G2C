"""Fixed-candidate prototype only; never applies the fixture to an existing DB.

Run with the B background candidate combined in a disposable checkout with C's
explicit filtered-processing V2 candidate. This is not main/migration acceptance.
"""
from pathlib import Path
import json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import pg_suites,migrate,psycopg


def main():
    os.environ.update(pg_suites.clean_env())
    for name in list(os.environ):
        if name.startswith(('PG','LIBPQ')) or name in ('DATABASE_URL','CJ_DATABASE_URL'):os.environ.pop(name,None)
    with tempfile.TemporaryDirectory(prefix='cj-bg-probe-',dir='/tmp') as folder:
        root=Path(folder)
        with pg_suites.cluster('background_probe',port=55793,role='cj_bg_probe',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                assert conn.execute("SELECT to_regclass('cj_run_background_job')").fetchone()==(None,)
                conn.execute((ROOT/'backend/run/tests/background_schema_fixture.sql').read_text())
            path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            env=dict(pg_suites.clean_env(),CJ_E2E_CONNINFO=str(path),PYTHONPATH=pg_suites.pythonpath())
            for name in ('background_jobs_pg.py','background_inflight_pg.py','background_current_pg.py','background_limits_pg.py'):
                result=subprocess.run([sys.executable,'-B',str(ROOT/'backend/cj_api/tests'/name)],cwd=ROOT,env=env)
                if result.returncode:return result.returncode
        assert not (root/'pg/data/postmaster.pid').exists()
    print('PASS prototype private PG stopped; registered-migration/main acceptance UNRUN')
    return 0


if __name__=='__main__':raise SystemExit(main())
