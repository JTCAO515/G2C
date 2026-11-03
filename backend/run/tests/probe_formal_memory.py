"""Exact M46 function/ACL roundtrip and the actual compatible MSG3 host."""
from pathlib import Path
import json,sys,tempfile
import psycopg
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import pg_suites as p,migrate


def guard(conn):
    return conn.execute("SELECT pg_get_functiondef(oid),proacl,prosecdef,proconfig FROM pg_proc "
                        "WHERE oid='cj_message_trip_activation_guard()'::regprocedure").fetchone()


def main():
    with tempfile.TemporaryDirectory(prefix='cj-fm-',dir='/tmp') as folder:
        root=Path(folder)
        with p.cluster('formal_memory',port=55837,role='cj_formal_init',root=root/'pg',socket=root/'s') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();assert next(m for m in chain if m['version']==46)['name']=='formal_memory_activation'
                migrate.up(conn,chain,45);original=guard(conn)
                migrate.up(conn,chain,46);assert guard(conn)[1:]==original[1:]
                assert conn.execute("SELECT has_table_privilege('cj_m1_runtime','cj_message_trip_profile','INSERT'),"
                    "has_table_privilege('cj_m1_runtime','cj_message_trip_profile','UPDATE'),"
                    "has_table_privilege('cj_local_cleanup','cj_message_trip_profile','INSERT'),"
                    "pg_has_role('cj_m1_runtime','cj_formal_init','MEMBER')").fetchone()==(False,False,False,False)
                migrate.down(conn,chain,45);assert guard(conn)==original,'M46 down changed the original function/ACL/search_path'
                migrate.up(conn,chain,46)
                print('PASS exact M46 empty up/down/up, original function+ACL/search_path restored; no role or runtime/cleanup activation grant',flush=True)
            path=root/'connection.json';path.write_text(json.dumps(config));path.chmod(0o600)
            result=p.script('backend/cj_api/tests/formal_memory_host_pg.py',env=dict(p.clean_env(),CJ_E2E_CONNINFO=str(path)))
        assert not (root/'pg/data/postmaster.pid').exists()
        return result


if __name__=='__main__':raise SystemExit(main())
