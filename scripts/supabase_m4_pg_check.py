"""Local synthetic managed-namespace permission and RLS probe, never cloud."""
import os,json,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import psycopg
import pg_suites,migrate,supabase_m4


def main():
    with tempfile.TemporaryDirectory(prefix='g2c-managed-') as directory:
        root=Path(directory)
        with pg_suites.cluster('managed_namespace',port=55867,role='cj_managed_test',root=root/'pg',socket=root/'s') as config:
            database=supabase_m4.Database(config)
            with database.connect() as conn:
                for role in ('anon','authenticated','service_role'):
                    conn.execute('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS')
                conn.execute('GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role')
                conn.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role')
                with conn.transaction():supabase_m4.quarantine_empty_public(database,conn)
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                assert not any(conn.execute("SELECT has_schema_privilege(%s,'public','USAGE')",(role,)).fetchone()[0]
                    for role in ('anon','authenticated','service_role'))
            result=supabase_m4.rls_probe(database)
            assert result['persistent_rows']==0 and result['status']=='PASS'
    print('PASS local managed namespace: inherited public API grants denied, real non-bypass role scope SELECT/UPDATE/INSERT negatives, all synthetic rows rolled back')


if __name__=='__main__':main()
