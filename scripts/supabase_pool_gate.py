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
from cj_api.supabase_test_database import decode_uri,pin_ca,current_authorization,discard_session,require_environment,require_identity
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
        current_authorization();require_environment();self.count+=1
        return conn.execute(statement,parameters)
    def connect(self,config,*,operator=False):
        current_authorization();require_environment();self.connections+=1
        connection=psycopg.connect(**config,autocommit=True,prepare_threshold=None)
        try:
            require_identity(connection,'postgres' if operator else 'cj_m1_runtime')
            return connection
        except BaseException:
            connection.close()
            raise


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


def bound_negatives(conn,own,other,data,query):
    for table in TABLES:
        relation=sql.Identifier(table)
        own_scope=trip_scope_for(own) if table.startswith('cj_trip_') else own
        other_scope=trip_scope_for(other) if table.startswith('cj_trip_') else other
        privileges=query.execute(conn,"SELECT has_table_privilege(current_user,%s,'SELECT'),has_table_privilege(current_user,%s,'UPDATE'),has_table_privilege(current_user,%s,'INSERT')",(table,table,table)).fetchone()
        if privileges!=(True,True,True):raise GateFailure('positive_table_privileges_required_for_negative_probe')
        if query.execute(conn,sql.SQL('SELECT count(*) FROM {} WHERE scope<>%s').format(relation),(own_scope,)).fetchone()!=(0,):
            raise GateFailure('bound_foreign_read_not_denied')
        with conn.transaction(force_rollback=True):
            if query.execute(conn,sql.SQL('UPDATE {} SET scope=scope WHERE scope=%s RETURNING scope').format(relation),(other_scope,)).fetchall():
                raise GateFailure('bound_foreign_update_not_denied')
        foreign=[row for row in data[table] if row['scope']==other_scope]
        if not foreign:raise GateFailure('foreign_positive_fixture_required')
        try:
            with conn.transaction(force_rollback=True):insert(conn,table,foreign[0],query)
        except psycopg.errors.InsufficientPrivilege:pass
        except psycopg.Error:raise GateFailure('bound_foreign_insert_did_not_produce_permission_refusal') from None
        else:raise GateFailure('bound_foreign_insert_not_denied')


def fixture(root,subjects):
    """Original signed Trip flow; no callback or handcrafted private records."""
    with pg_suites.cluster('pool_gate_source',port=55883,role='cj_pool_gate_source',root=root/'pg',socket=root/'s') as config:
        with psycopg.connect(**config,autocommit=True) as conn:
            chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
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


def scoped_sequence(conn,first,second,rollback,pid,query,data,identity_check):
    discard_session(conn)
    identity_check(conn)
    templates={}
    with conn.transaction(force_rollback=rollback):
        query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(first,trip_scope_for(first)))
        for table in TABLES:
            values=rows(conn,table,[first,trip_scope_for(first)],query)
            if not values:raise GateFailure('positive_RLS_seed_not_visible')
            templates[table]=values[0]
        bound_negatives(conn,first,second,data,query)
    with conn.cursor() as cursor:_require_unbound(cursor)
    if query.execute(conn,'SELECT pg_backend_pid()').fetchone()[0]!=pid:raise GateFailure('physical_session_changed')
    unbound_negatives(conn,templates,query)
    with conn.transaction():
        query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(second,trip_scope_for(second)))
        for table in TABLES:
            values=rows(conn,table,[second,trip_scope_for(second)],query)
            expected=trip_scope_for(second) if table.startswith('cj_trip_') else second
            if not values or {v['scope'] for v in values}!={expected}:raise GateFailure('next_owner_scope_mismatch')
        bound_negatives(conn,second,first,data,query)


def matrix(config,scopes,data,query):
    outcomes=[]
    for rollback in (False,True):
        for first,second in (scopes,scopes[::-1]):
            with query.connect(config) as conn:
                pid=query.execute(conn,'SELECT pg_backend_pid()').fetchone()[0]
                scoped_sequence(conn,first,second,rollback,pid,query,data,lambda c:require_identity(c,'cj_m1_runtime'))
                outcomes.append(dict(rollback=rollback,tables=12,same_physical_backend=True,positive_and_unbound_SELECT_UPDATE_INSERT='PASS'))
    return outcomes


def disconnects(config,scopes,data,query):
    result=[];templates={t:items[0] for t,items in data.items()}
    for abrupt in (False,True):
        with query.connect(config) as conn:
            first=query.execute(conn,"SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),pg_backend_pid()").fetchone()
            if first[:2]!=('cj_m1_runtime',True):raise GateFailure('actual_runtime_TLS_required')
            discard_session(conn)
            require_identity(conn,'cj_m1_runtime')
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
            discard_session(conn);require_identity(conn,'cj_m1_runtime')
            unbound_negatives(conn,templates,query)
            with conn.transaction():
                query.execute(conn,"SELECT set_config('cj.message_scope',%s,true),set_config('cj.trip_scope',%s,true)",(scopes[1],trip_scope_for(scopes[1])))
                for table in TABLES:
                    if not rows(conn,table,[scopes[1],trip_scope_for(scopes[1])],query):raise GateFailure('post_disconnect_positive_seed_missing')
                bound_negatives(conn,scopes[1],scopes[0],data,query)
            result.append(dict(abrupt=abrupt,supplier_reset_observation=before,application_reset_and_12_table_gate='PASS'))
    return result


def original_observation(conn,state,query):
    scopes=state['scopes']+[trip_scope_for(s) for s in state['scopes']]
    actual={t:rows(conn,t,scopes,query) for t in TABLES}
    empty=all(not values for values in actual.values())
    matched=not empty and digest(actual)==state['expected_sha256']
    return dict(status='EMPTY_CONFIRMED' if empty else 'OWNED_SEED_MATCH' if matched else 'HOLD_CHANGED_OR_PARTIAL',
                counts={t:len(v) for t,v in actual.items()},actual_sha256=digest(actual))


def cleanup_owned(conn,state,path,query):
    scopes=state['scopes']+[trip_scope_for(s) for s in state['scopes']]
    with conn.transaction():
        query.execute(conn,'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
        actual={t:rows(conn,t,scopes,query,lock=True) for t in TABLES}
        if all(not values for values in actual.values()):return 'ALREADY_EMPTY_CONFIRMED'
        if digest(actual)!=state['expected_sha256']:raise GateFailure('owned_seed_changed_cleanup_withheld')
        state['state']='CLEANUP_INTENT';save(path,state)
        for table in reversed(TABLES):query.execute(conn,sql.SQL('DELETE FROM {} WHERE scope=ANY(%s)').format(sql.Identifier(table)),(scopes,))
    if original_observation(conn,state,query)['status']!='EMPTY_CONFIRMED':raise GateFailure('owned_gate_cleanup_unconfirmed')
    return 'CONFIRMED_empty_owned_scopes'


def reconcile(ca,state,*,cleanup=False,path=None):
    current_authorization();query=Query()
    with pin_ca(ca) as pinned:
        config=dict(decode_uri(keychain('g2c-supabase-db'),operator=True),sslrootcert=pinned.name)
        with query.connect(config,operator=True) as conn:
            observation=original_observation(conn,state,query)
            cleared=None
            if cleanup:
                if observation['status']=='HOLD_CHANGED_OR_PARTIAL':raise GateFailure('owned_seed_changed_cleanup_withheld')
                cleared=cleanup_owned(conn,state,path,query)
                state['cleanup']='CONFIRMED_empty_owned_scopes';save(path,state)
                observation=original_observation(conn,state,query)
    return dict(mode='RECONCILED_CLEANUP' if cleanup else 'READ_ONLY_ORIGINAL',result=state,
                cloud_observation=observation,cleanup=cleared,new_data_writes=0 if not cleanup else 'original_owned_cleanup_only',
                instrumented_execute_calls=query.count,total_SQL='UNKNOWN',actual_cost='UNKNOWN')


def run(ca):
    current_authorization();STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);path=STATE/'state.json'
        if path.exists():return reconcile(ca,load_state(path))
        batch=secrets.token_hex(12);subjects=['m4-synthetic-cloud-gate-'+batch+'-'+label for label in ('a','b')]
        scopes=[scope_for(ISSUER,s) for s in subjects];all_scopes=scopes+[trip_scope_for(s) for s in scopes]
        with tempfile.TemporaryDirectory(prefix='cj-cloud-gate-source-') as directory:
            data=fixture(Path(directory),subjects)
        state=dict(state='PLANNED',project_ref='sajkhvjpllldfyfryalx',batch=batch,scopes=scopes,expected_sha256=digest(data),counts={k:len(v) for k,v in data.items()})
        save(path,state);query=Query()
        with pin_ca(ca) as pinned:
            operator=dict(decode_uri(keychain('g2c-supabase-db'),operator=True),sslrootcert=pinned.name)
            runtime=dict(decode_uri(keychain('g2c-supabase-runtime-db')),sslrootcert=pinned.name)
            with query.connect(operator,operator=True) as conn:
                if migrate.applied(conn)!=[m['version'] for m in migrate.load()]:raise GateFailure('exact_application_schema_required')
                if query.execute(conn,'SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()!=(True,):raise GateFailure('database_side_TLS_required')
                if any(rows(conn,t,all_scopes,query) for t in TABLES):raise GateFailure('owned_random_scopes_already_exist')
                state['state']='SEED_INTENT';save(path,state)
                with conn.transaction():
                    for table in TABLES:
                        for row in data[table]:insert(conn,table,row,query)
                state['state']='SEEDED';save(path,state)
            try:
                state['matrix']=matrix(runtime,scopes,data,query)
                state['disconnects']=disconnects(runtime,scopes,data,query)
            finally:
                # Re-read the original state before cleanup, including after any
                # uncertain test operation. Refuse mixed/changed owned contents.
                primary=sys.exception()
                try:
                    with query.connect(operator,operator=True) as conn:
                        cleanup_owned(conn,state,path,query)
                    state['cleanup']='CONFIRMED_empty_owned_scopes';save(path,state)
                except Exception as cleanup_error:
                    if primary is None:raise
                    primary.add_note('owned cleanup unconfirmed; inspect original cloud state before further action')
                    print(json.dumps(dict(event='OWNED_CLEANUP_UNCONFIRMED',error_type=type(cleanup_error).__name__)),file=sys.stderr)
        state.update(state='COMPLETE',instrumented_execute_calls=query.count,total_SQL='UNKNOWN',connections=query.connections,actual_cost='UNKNOWN');save(path,state)
        return dict(mode='EXECUTED',result=state)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('run','inspect','cleanup'));parser.add_argument('--ca-file',type=Path,required=True);args=parser.parse_args()
    if args.command=='run':result=run(args.ca_file)
    else:
        with (STATE/'lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            path=STATE/'state.json';result=reconcile(args.ca_file,load_state(path),cleanup=args.command=='cleanup',path=path)
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except GateFailure as error:
        print(json.dumps(dict(state='FAIL',reason=error.args[0])))
        raise SystemExit(1) from None
    except Exception as error:
        print(json.dumps(dict(state='UNKNOWN_OR_UNAVAILABLE',error_type=type(error).__name__)))
        raise SystemExit(1) from None
