"""Full twelve-table test using only two owned random synthetic DB scopes.

Local signed API/Fake prepares valid records. Only the fixed cloud target is
allowed; read-only on an existing run. Data creation/cleanup is M1#2 authorized.
This gate does not create Auth users, change roles, or activate a public backend.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import date,datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import tempfile
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'backend/agent/tests'))
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER,_require_unbound
from cj_api.supabase_test_database import decode_uri,pin_ca,current_authorization,discard_session
from cj_agent.draft import trip_scope_for
from cj_message.domain import Service as MessageService
from cj_trip.confirmation import ConfirmationSigner
import dev_auth,migrate,pg_suites
from supabase_runtime_credential import keychain,save
from cj_strict_json import reject_duplicates

class GateFailure(Exception):pass


STATE=Path.home()/'.local/share/g2c/m4-supabase-pool-gate'
TABLES=('cj_message_scope','cj_message_chat','cj_message_receipt','cj_message_delivery','cj_message_draft',
        'cj_run_scope','cj_run_record','cj_run_event','cj_trip_scope','cj_trip_proposal','cj_trip_record','cj_trip_receipt')


def load_state(path):
    raw=path.read_bytes()
    if len(raw)>65536:raise GateFailure('bounded_original_gate_state_required')
    value=json.loads(raw,object_pairs_hook=reject_duplicates(GateFailure,'duplicate_gate_state_field'))
    required={'state','project_ref','batch','scopes','expected_sha256','counts'}
    optional={'matrix','disconnects','cleanup','instrumented_execute_calls','total_SQL','connections','actual_cost'}
    if (type(value) is not dict or not required<=set(value) or set(value)-required-optional
            or value['project_ref']!='sajkhvjpllldfyfryalx' or type(value['batch']) is not str
            or re.fullmatch('[0-9a-f]{24}',value['batch']) is None
            or value['state'] not in ('PLANNED','SEED_INTENT','SEEDED','CLEANUP_INTENT','COMPLETE')
            or type(value['expected_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value['expected_sha256']) is None
            or type(value['counts']) is not dict or set(value['counts'])!=set(TABLES)
            or any(type(n) is not int or not 1<=n<=1024 for n in value['counts'].values())):
        raise GateFailure('original_gate_state_invalid')
    expected=[scope_for(ISSUER,'m4-synthetic-cloud-gate-'+value['batch']+'-'+label) for label in ('a','b')]
    if value['scopes']!=expected:raise GateFailure('original_gate_scope_mismatch')
    for key in ('instrumented_execute_calls','connections'):
        if key in value and (type(value[key]) is not int or not 0<=value[key]<=100000):raise GateFailure('original_gate_counter_invalid')
    for key,allowed in (('cleanup','CONFIRMED_empty_owned_scopes'),('total_SQL','UNKNOWN'),('actual_cost','UNKNOWN')):
        if key in value and value[key]!=allowed:raise GateFailure('original_gate_result_invalid')
    if 'matrix' in value:
        if type(value['matrix']) is not list or len(value['matrix'])!=4:raise GateFailure('original_gate_matrix_invalid')
        for item in value['matrix']:
            if (type(item) is not dict or set(item)!={'rollback','tables','same_physical_backend','positive_and_unbound_SELECT_UPDATE_INSERT'}
                    or type(item['rollback']) is not bool or item['tables']!=12 or item['same_physical_backend'] is not True
                    or item['positive_and_unbound_SELECT_UPDATE_INSERT']!='PASS'):
                raise GateFailure('original_gate_matrix_invalid')
    if 'disconnects' in value:
        if type(value['disconnects']) is not list or len(value['disconnects'])!=2:raise GateFailure('original_disconnect_evidence_invalid')
        for item in value['disconnects']:
            if (type(item) is not dict or set(item)!={'abrupt','supplier_reset_observation','application_reset_and_12_table_gate'}
                    or type(item['abrupt']) is not bool or item['supplier_reset_observation'] not in ('OBSERVED_RETAINED','OBSERVED_CLEAN','UNKNOWN_different_backend')
                    or item['application_reset_and_12_table_gate']!='PASS'):
                raise GateFailure('original_disconnect_evidence_invalid')
    if value['state']=='COMPLETE' and (len(value.get('matrix',[]))!=4 or len(value.get('disconnects',[]))!=2 or 'cleanup' not in value):
        raise GateFailure('original_gate_complete_evidence_missing')
    return value


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [canonical(v) for v in value]
    if isinstance(value,(bytes,bytearray,memoryview)):return {'bytes':base64.b64encode(bytes(value)).decode()}
    if isinstance(value,(date,datetime)):return {'timestamp':value.isoformat()}
    if value is None or type(value) in (str,int,bool,float):return value
    return str(value)


class Query:
    def __init__(self):self.count=0;self.connections=0
    def execute(self,conn,statement,parameters=None):
        current_authorization();self.count+=1
        return conn.execute(statement,parameters)
    def connect(self,config):
        current_authorization();self.connections+=1
        return psycopg.connect(**config,autocommit=True,prepare_threshold=None)


def rows(conn,table,scopes,query,*,lock=False):
    statement=sql.SQL('SELECT * FROM {} WHERE scope=ANY(%s) ORDER BY scope').format(sql.Identifier(table))
    if lock:statement+=sql.SQL(' FOR UPDATE')
    cursor=query.execute(conn,statement,(scopes,))
    columns=[c.name for c in cursor.description]
    result=[dict(zip(columns,row)) for row in cursor.fetchall()]
    if len(result)>1024:raise GateFailure('owned_gate_row_bound_exceeded')
    for row in result:row.pop('list_sequence',None)
    return result


def digest(data):
    # No row/order changes during cloud copy: generated list sequences alone are
    # allocated by the target. Compare every retained source column for cleanup.
    normalized={table:sorted((json.dumps(canonical(row),sort_keys=True,separators=(',',':')) for row in items)) for table,items in data.items()}
    return hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()


def adapt(value):return Jsonb(value) if isinstance(value,(dict,list)) else value


def insert(conn,table,row,query):
    fields=list(row)
    query.execute(conn,sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(sql.Identifier(table),
        sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(sql.Placeholder() for _ in fields)),tuple(adapt(row[k]) for k in fields))


def unbound_negatives(conn,templates,query):
    with conn.cursor() as cursor:_require_unbound(cursor)
    for table in TABLES:
        relation=sql.Identifier(table)
        if query.execute(conn,sql.SQL('SELECT count(*) FROM {}').format(relation)).fetchone()!=(0,):raise GateFailure('unbound_read_not_denied')
        with conn.transaction(force_rollback=True):
            if query.execute(conn,sql.SQL('UPDATE {} SET scope=scope RETURNING scope').format(relation)).fetchall():raise GateFailure('unbound_update_not_denied')
        try:
            with conn.transaction(force_rollback=True):insert(conn,table,templates[table],query)
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise GateFailure('RLS_specific_insert_refusal_required')


def fixture(root,subjects):
    """Original signed Trip flow; no callback or handcrafted private records."""
    with pg_suites.cluster('pool_gate_source',port=55883,role='cj_pool_gate_source',root=root/'pg',socket=root/'s') as config:
        with psycopg.connect(**config,autocommit=True) as conn:migrate.up(conn,migrate.load(),48)
        conninfo=root/'conn.json';conninfo.write_text(json.dumps(config))
        auth=root/'auth';dev_auth.init(auth,list(subjects))
        with patch.dict(os.environ,{'CJ_E2E_CONNINFO':str(conninfo)}):
            from e2e_local import SignedTripConfirmation
        h=SignedTripConfirmation();h.auth=auth;h.database=LocalDatabase(conninfo)
        app=create_local_app(conninfo_path=conninfo,auth_dir=auth,confirmation_signer=ConfirmationSigner(secrets.token_bytes(32)))
        with TestClient(app) as client:
            for subject in subjects:
                _,outcome=h.draft(client,subject,'Synthetic Beijing plan')
                if outcome.status!='completed':raise GateFailure('original_synthetic_seed_failed')
                messages=MessageService(h.database.message_repository(scope_for(ISSUER,subject)),new_run_id=lambda:None)
                receipt=messages.query(outcome.message_id).receipt
                messages.save_draft(receipt.conversation_id,receipt.generation,b'synthetic twelve-table gate draft',0)
                proposal=client.get('/v1/trip-proposals',params={'proposal_id':outcome.proposal_id},headers=h.headers(subject)).json()['proposal']
                prepared=h.prepare(client,proposal,subject=subject)
                if prepared.status_code!=200:raise GateFailure('original_confirmation_seed_failed')
                raw=base64.b64decode(prepared.json()['action_utf8_base64'],validate=True)
                if h.post_action(client,raw,subject).status_code!=200:raise GateFailure('original_signed_accept_seed_failed')
        scopes=[scope_for(ISSUER,s) for s in subjects]
        all_scopes=scopes+[trip_scope_for(s) for s in scopes]
        query=Query()
        with psycopg.connect(**config,autocommit=True) as conn:
            data={table:rows(conn,table,all_scopes,query) for table in TABLES}
        if any(not values for values in data.values()):raise GateFailure('twelve_table_positive_seed_required')
        return data


def scoped_sequence(conn,first,second,rollback,pid,query):
    discard_session(conn)
    templates={}
    with conn.transaction(force_rollback=rollback):
        query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(first,trip_scope_for(first)))
        for table in TABLES:
            values=rows(conn,table,[first,trip_scope_for(first)],query)
            if not values:raise GateFailure('positive_RLS_seed_not_visible')
            templates[table]=values[0]
    with conn.cursor() as cursor:_require_unbound(cursor)
    if query.execute(conn,'SELECT pg_backend_pid()').fetchone()[0]!=pid:raise GateFailure('physical_session_changed')
    unbound_negatives(conn,templates,query)
    with conn.transaction():
        query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(second,trip_scope_for(second)))
        for table in TABLES:
            values=rows(conn,table,[second,trip_scope_for(second)],query)
            expected=trip_scope_for(second) if table.startswith('cj_trip_') else second
            if not values or {v['scope'] for v in values}!={expected}:raise GateFailure('next_owner_scope_mismatch')


def matrix(config,scopes,query):
    outcomes=[]
    for rollback in (False,True):
        for first,second in (scopes,scopes[::-1]):
            with query.connect(config) as conn:
                identity=query.execute(conn,"SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),pg_backend_pid()").fetchone()
                if identity[:2]!=('cj_m1_runtime',True):raise GateFailure('actual_runtime_TLS_required')
                scoped_sequence(conn,first,second,rollback,identity[2],query)
                outcomes.append(dict(rollback=rollback,tables=12,same_physical_backend=True,positive_and_unbound_SELECT_UPDATE_INSERT='PASS'))
    return outcomes


def disconnects(config,scopes,data,query):
    result=[];templates={t:items[0] for t,items in data.items()}
    for abrupt in (False,True):
        with query.connect(config) as conn:
            first=query.execute(conn,"SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),pg_backend_pid()").fetchone()
            if first[:2]!=('cj_m1_runtime',True):raise GateFailure('actual_runtime_TLS_required')
            discard_session(conn)
            query.execute(conn,"SELECT set_config('cj.message_scope',%s,false),set_config('cj.trip_scope',%s,false)",(scopes[0],trip_scope_for(scopes[0])))
            if abrupt:
                # Drop only our client's connection; no server-side terminate,
                # arbitrary backend PID, role change or destructive DB operation.
                own=socket.socket(fileno=os.dup(conn.pgconn.socket))
                try:own.shutdown(socket.SHUT_RDWR)
                finally:own.close()
                conn.close()
        with query.connect(config) as conn:
            next_=query.execute(conn,"SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),pg_backend_pid(),current_setting('cj.message_scope',true),current_setting('cj.trip_scope',true)").fetchone()
            if next_[:2]!=('cj_m1_runtime',True):raise GateFailure('actual_runtime_TLS_required')
            before=('UNKNOWN_different_backend' if next_[2]!=first[2] else
                    'OBSERVED_RETAINED' if any(x not in ('',None) for x in next_[3:]) else 'OBSERVED_CLEAN')
            discard_session(conn);unbound_negatives(conn,templates,query)
            with conn.transaction():
                query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(scopes[1],trip_scope_for(scopes[1])))
                for table in TABLES:
                    if not rows(conn,table,[scopes[1],trip_scope_for(scopes[1])],query):raise GateFailure('post_disconnect_positive_seed_missing')
            result.append(dict(abrupt=abrupt,supplier_reset_observation=before,application_reset_and_12_table_gate='PASS'))
    return result


def run(ca):
    current_authorization();STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);path=STATE/'state.json'
        if path.exists():return dict(mode='READ_ONLY_ORIGINAL',result=load_state(path),new_SQL=0)
        batch=secrets.token_hex(12);subjects=['m4-synthetic-cloud-gate-'+batch+'-'+label for label in ('a','b')]
        scopes=[scope_for(ISSUER,s) for s in subjects];all_scopes=scopes+[trip_scope_for(s) for s in scopes]
        with tempfile.TemporaryDirectory(prefix='cj-cloud-gate-source-') as directory:
            data=fixture(Path(directory),subjects)
        state=dict(state='PLANNED',project_ref='sajkhvjpllldfyfryalx',batch=batch,scopes=scopes,expected_sha256=digest(data),counts={k:len(v) for k,v in data.items()})
        save(path,state);query=Query()
        with pin_ca(ca) as pinned:
            operator=dict(decode_uri(keychain('g2c-supabase-db'),operator=True),sslrootcert=pinned.name)
            runtime=dict(decode_uri(keychain('g2c-supabase-runtime-db')),sslrootcert=pinned.name)
            with query.connect(operator) as conn:
                if query.execute(conn,'SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()!=(True,):raise GateFailure('database_side_TLS_required')
                if any(rows(conn,t,all_scopes,query) for t in TABLES):raise GateFailure('owned_random_scopes_already_exist')
                state['state']='SEED_INTENT';save(path,state)
                with conn.transaction():
                    for table in TABLES:
                        for row in data[table]:insert(conn,table,row,query)
                state['state']='SEEDED';save(path,state)
            try:
                state['matrix']=matrix(runtime,scopes,query)
                state['disconnects']=disconnects(runtime,scopes,data,query)
            finally:
                # Re-read the original state before cleanup, including after any
                # uncertain test operation. Refuse mixed/changed owned contents.
                with query.connect(operator) as conn:
                    with conn.transaction():
                        query.execute(conn,'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                        actual={t:rows(conn,t,all_scopes,query,lock=True) for t in TABLES}
                        if digest(actual)!=state['expected_sha256']:raise GateFailure('owned_seed_changed_cleanup_withheld')
                        state['state']='CLEANUP_INTENT';save(path,state)
                        for table in reversed(TABLES):query.execute(conn,sql.SQL('DELETE FROM {} WHERE scope=ANY(%s)').format(sql.Identifier(table)),(all_scopes,))
                    if any(rows(conn,t,all_scopes,query) for t in TABLES):raise GateFailure('owned_gate_cleanup_unconfirmed')
                state['cleanup']='CONFIRMED_empty_owned_scopes';save(path,state)
        state.update(state='COMPLETE',instrumented_execute_calls=query.count,total_SQL='UNKNOWN',connections=query.connections,actual_cost='UNKNOWN');save(path,state)
        return dict(mode='EXECUTED',result=state)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('run','inspect'));parser.add_argument('--ca-file',type=Path,required=True);args=parser.parse_args()
    result=run(args.ca_file) if args.command=='run' else dict(mode='READ_ONLY',result=load_state(STATE/'state.json'))
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except GateFailure as error:
        print(json.dumps(dict(state='FAIL',reason=error.args[0])))
        raise SystemExit(1) from None
    except Exception as error:
        print(json.dumps(dict(state='UNKNOWN_OR_UNAVAILABLE',error_type=type(error).__name__)))
        raise SystemExit(1) from None
