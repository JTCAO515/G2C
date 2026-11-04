"""Private Unix PG only: actual twelve-table/reset mechanics, no cloud/TLS claim."""
import json,os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import psycopg

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import migrate,pg_suites
import supabase_pool_gate as gate
from cj_api.local_app import ISSUER,scope_for
from cj_api.supabase_test_database import require_identity
from cj_api.composition import CompositionUnavailable


def local_identity(conn):
    assert conn.execute("SELECT current_user,session_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()==('cj_m1_runtime','cj_m1_runtime',False)


def main():
    with tempfile.TemporaryDirectory(prefix='cj-pool-local-') as directory,patch.dict(os.environ,pg_suites.clean_env(),clear=True),patch.object(gate,'current_authorization',lambda:None):
        root=Path(directory);subjects=['m4-synthetic-local-pool-a','m4-synthetic-local-pool-b']
        data=gate.fixture(root/'source',subjects)
        scopes=[scope_for(ISSUER,s) for s in subjects];query=gate.Query()
        with pg_suites.cluster('pool_target',port=55884,role='cj_pool_target_init',root=root/'target',socket=root/'s') as config:
            if not str(config['host']).startswith('/'):raise ValueError('private_Unix_fixture_required')
            with psycopg.connect(**config,autocommit=True) as conn:
                migrate.up(conn,migrate.load(),48)
                for table in gate.TABLES:
                    for row in data[table]:gate.insert(conn,table,row,query)
            with psycopg.connect(**dict(config,user='cj_m1_runtime'),autocommit=True) as conn:
                identity=conn.execute("SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),pg_backend_pid()").fetchone()
                assert identity[:2]==('cj_m1_runtime',False)  # Explicitly not cloud TLS evidence.
                for rollback in (False,True):
                    for first,second in (scopes,scopes[::-1]):
                        conn.execute("SELECT set_config('cj.message_scope',%s,false),set_config('cj.trip_scope',%s,false)",('retained-prior-session','retained-prior-session'))
                        gate.scoped_sequence(conn,first,second,rollback,identity[2],query,data,local_identity)
            # A broken policy accepting every nonempty scope used to pass the
            # gate. Inject it only into this private fixture, never a cloud DB.
            with psycopg.connect(**config,autocommit=True) as conn:
                from psycopg import sql
                for (policy,) in conn.execute("SELECT policyname FROM pg_policies WHERE tablename='cj_message_scope' AND permissive='RESTRICTIVE'"):
                    conn.execute(sql.SQL('DROP POLICY {} ON cj_message_scope').format(sql.Identifier(policy)))
                conn.execute("CREATE POLICY review_fault ON cj_message_scope TO cj_m1_runtime USING (nullif(current_setting('cj.message_scope',true),'') IS NOT NULL) WITH CHECK (nullif(current_setting('cj.message_scope',true),'') IS NOT NULL)")
            with psycopg.connect(**dict(config,user='cj_m1_runtime'),autocommit=True) as conn:
                try:gate.scoped_sequence(conn,scopes[0],scopes[1],False,conn.info.backend_pid,query,data,local_identity)
                except gate.GateFailure as error:assert error.args[0]=='bound_foreign_read_not_denied'
                else:raise AssertionError('cross-owner permissive policy incorrectly passed gate')
            # Commit-ack-loss reconciliation reads the original owned contents;
            # local JSON alone never proves a cloud commit or cleanup outcome.
            state=dict(state='SEEDED',scopes=scopes,expected_sha256=gate.digest(data))
            with psycopg.connect(**config,autocommit=True) as conn:
                # Retained pg_temp relations must never hide persistent contents
                # or claim TLS. Only this private Unix fixture creates them.
                from psycopg import sql
                for table in gate.TABLES:
                    conn.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE {})').format(sql.Identifier(table),sql.Identifier('public',table)))
                conn.execute('CREATE TEMP TABLE pg_stat_ssl AS SELECT pg_catalog.pg_backend_pid() AS pid,true AS ssl')
                assert conn.execute('SELECT count(*) FROM cj_message_scope').fetchone()==(0,)
                try:require_identity(conn,'cj_pool_target_init')
                except CompositionUnavailable:pass
                else:raise AssertionError('temporary pg_stat_ssl masqueraded as encrypted transport')
                assert gate.original_observation(conn,state,query)['status']=='OWNED_SEED_MATCH'
                conn.execute('DELETE FROM public.cj_message_draft WHERE scope=%s',(scopes[0],))
                assert gate.original_observation(conn,state,query)['status']=='HOLD_CHANGED_OR_PARTIAL'
                try:gate.cleanup_owned(conn,state,root/'changed-state.json',query)
                except gate.GateFailure as error:assert error.args[0]=='owned_seed_changed_cleanup_withheld'
                else:raise AssertionError('changed original data was cleared')
                for row in data['cj_message_draft']:
                    if row['scope']==scopes[0]:gate.insert(conn,'cj_message_draft',row,query)
                assert gate.original_observation(conn,state,query)['status']=='OWNED_SEED_MATCH'
                gate.cleanup_owned(conn,state,root/'unknown-cleanup.json',query)
                assert gate.original_observation(conn,state,query)['status']=='EMPTY_CONFIRMED'
                assert json.loads((root/'unknown-cleanup.json').read_text())['state']=='CLEANUP_INTENT'
    print('PASS actual local Unix PG: signed seed, same-session DISCARD ALL, commit/rollback two-owner positive and all12 unbound SELECT/UPDATE/INSERT negatives; cloud/TLS/real keys UNRUN')


if __name__=='__main__':main()
