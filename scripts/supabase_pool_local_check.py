"""Private Unix PG only: actual twelve-table/reset mechanics, no cloud/TLS claim."""
import os
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
                        gate.scoped_sequence(conn,first,second,rollback,identity[2],query)
    print('PASS actual local Unix PG: signed seed, same-session DISCARD ALL, commit/rollback two-owner positive and all12 unbound SELECT/UPDATE/INSERT negatives; cloud/TLS/real keys UNRUN')


if __name__=='__main__':main()
