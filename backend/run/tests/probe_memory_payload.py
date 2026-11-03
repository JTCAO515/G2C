"""M45 original ACL roundtrip and actual signed memory-payload consumer."""
from pathlib import Path
import json,sys,tempfile
import psycopg
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import pg_suites as p,migrate


def acls(conn):
    return (conn.execute("SELECT c.relname,c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                         "WHERE n.nspname='public' AND c.relname LIKE 'cj_%' AND c.relkind='r' ORDER BY 1").fetchall(),
            conn.execute("SELECT c.relname,a.attname,a.attacl FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                         "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname LIKE 'cj_%' "
                         "AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2").fetchall(),
            conn.execute("SELECT proacl,prosecdef FROM pg_proc WHERE oid='cj_run_guard_original_binding()'::regprocedure").fetchone())


def main():
    with tempfile.TemporaryDirectory(prefix='cj-mp-',dir='/tmp') as directory:
        root=Path(directory)
        with p.cluster('memory_payload',port=55829,role='cj_mp_private',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();assert next(m for m in chain if m['version']==45)['name']=='memory_payload_erasure'
                migrate.up(conn,chain,44);before=acls(conn)
                migrate.up(conn,chain,45)
                assert conn.execute("SELECT proacl,prosecdef FROM pg_proc WHERE oid='cj_run_guard_original_binding()'::regprocedure").fetchone()==before[2]
                for role in ('cj_m1_runtime','cj_local_cleanup'):
                    assert conn.execute('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s',(role,)).fetchone()==(False,)*5
                assert conn.execute("SELECT has_table_privilege('cj_m1_runtime','cj_run_payload_erasure','SELECT'),"
                    "has_table_privilege('cj_m1_runtime','cj_run_payload_erasure','INSERT'),has_table_privilege('cj_m1_runtime','cj_run_payload_erasure','UPDATE'),"
                    "has_table_privilege('cj_m1_runtime','cj_run_payload_erasure','DELETE'),has_table_privilege('cj_m1_runtime','cj_run_payload_erasure','TRUNCATE'),"
                    "pg_has_role('cj_m1_runtime','cj_local_cleanup','MEMBER'),has_function_privilege('cj_m1_runtime','cj_payload_write(text,text)','EXECUTE'),"
                    "has_function_privilege('cj_m1_runtime','cj_payload_plan(text)','EXECUTE')").fetchone()==(True,False,False,False,False,False,False,False)
                assert conn.execute("SELECT has_column_privilege('cj_local_cleanup','cj_run_record','usage_input_bytes','UPDATE'),"
                    "has_column_privilege('cj_local_cleanup','cj_run_record','usage_command_bytes','UPDATE'),"
                    "has_column_privilege('cj_local_cleanup','cj_run_background_job','input_bytes','UPDATE'),"
                    "has_column_privilege('cj_local_cleanup','cj_run_background_job','command_bytes','UPDATE')").fetchone()==(True,False,True,False)
                migrate.down(conn,chain,44);assert acls(conn)==before,'M45 down changed original table/column/function ACLs'
                migrate.up(conn,chain,45)
                print('PASS M45 empty up/down/up exact original table/column/function ACLs; dedicated minimal columns, runtime no DELETE/TRUNCATE/membership/private intent functions, neither role bypasses RLS',flush=True)
            path=root/'connection.json';path.write_text(json.dumps(config));path.chmod(0o600)
            result=p.script('backend/cj_api/tests/memory_payload_pg.py',env=dict(p.clean_env(),CJ_E2E_CONNINFO=str(path)))
        assert not (root/'pg/data/postmaster.pid').exists()
        return result


if __name__=='__main__':raise SystemExit(main())
