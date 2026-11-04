"""JT-approved credential for the existing test runtime role; never GRANT.

One durable change intent. Re-execution only checks the original credential,
including after unknown commit; it never generates a replacement password.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import quote

import psycopg
from psycopg import sql

from cj_api.supabase_test_database import decode_uri,pin_ca,current_authorization,HOST,REF
from cj_strict_json import reject_duplicates

ROOT=Path.home()/'.local/share/g2c/m4-supabase-runtime'
SERVICE='g2c-supabase-runtime-db'


def keychain(name):
    result=subprocess.run(['security','find-generic-password','-s',name,'-w',str(Path.home()/'Library/Keychains/login.keychain-db')],
                          capture_output=True,text=True,timeout=15)
    if result.returncode or not result.stdout.strip():raise ValueError('authorized_keychain_item_unavailable')
    return result.stdout.strip()


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary,0o600);json.dump(value,output);output.flush();os.fsync(output.fileno())
    temporary.replace(path)


def load_state(path):
    raw=path.read_bytes()
    if len(raw)>4096:raise ValueError('bounded_original_credential_state_required')
    state=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_credential_state_field'))
    required={'state','project_ref','role','credential_sha256','sql_change_attempts'}
    if (type(state) is not dict or not required<=set(state) or set(state)-required-{'sqlstate'}
            or state['project_ref']!=REF or state['role']!='cj_m1_runtime'
            or state['state'] not in ('KEYCHAIN_INTENT','PASSWORD_CHANGE_INTENT','PASSWORD_CHANGE_UNKNOWN','PASSWORD_CHANGE_REJECTED','VERIFIED')
            or type(state['sql_change_attempts']) is not int or state['sql_change_attempts'] not in (0,1)
            or (state['state']=='KEYCHAIN_INTENT')!=(state['sql_change_attempts']==0)
            or type(state['credential_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',state['credential_sha256']) is None
            or 'sqlstate' in state and (type(state['sqlstate']) is not str or state['sqlstate']!='UNKNOWN' and re.fullmatch('[0-9A-Z]{5}',state['sqlstate']) is None)):
        raise ValueError('original_runtime_credential_state_invalid')
    return state


def inspect(ca,state):
    current_authorization()
    uri=keychain(SERVICE)
    if hashlib.sha256(uri.encode()).hexdigest()!=state['credential_sha256']:
        raise ValueError('original_runtime_credential_changed')
    with pin_ca(ca) as pinned:
        config=dict(decode_uri(uri),sslrootcert=pinned.name)
        with psycopg.connect(**config,autocommit=True,prepare_threshold=None) as conn:
            row=conn.execute("SELECT current_user,session_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()),"
                             "rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,"
                             "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),"
                             "EXISTS(SELECT 1 FROM pg_class WHERE relowner=r.oid) FROM pg_roles r WHERE rolname=current_user").fetchone()
    if row is None or row[:2]!=('cj_m1_runtime','cj_m1_runtime') or row[3:]!=(False,)*7:
        raise ValueError('restricted_runtime_identity_required')
    return dict(identity=row[0],session_identity=row[1],pooler_to_database_tls=row[2],
                privileges='restricted_runtime',actual_cost='UNKNOWN',new_password_changes=0)


def apply(ca):
    current_authorization();ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (ROOT/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=ROOT/'state.json'
        if path.exists():
            state=load_state(path)
            return dict(mode='READ_ONLY_ORIGINAL',state=state,result=inspect(ca,state))
        present=subprocess.run(['security','find-generic-password','-s',SERVICE,str(Path.home()/'Library/Keychains/login.keychain-db')],capture_output=True,timeout=15)
        if present.returncode!=44:raise ValueError('existing_runtime_keychain_entry_not_overwritten')
        operator=keychain('g2c-supabase-db')
        with pin_ca(ca) as pinned:
            config=dict(decode_uri(operator,operator=True),sslrootcert=pinned.name)
            with psycopg.connect(**config,autocommit=True,prepare_threshold=None) as conn:
                if conn.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()!=(True,):
                    raise ValueError('database_side_TLS_required_before_credential_change')
                before=conn.execute("SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,"
                    "(SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime') FROM pg_roles WHERE rolname='cj_m1_runtime'").fetchone()
                if before!=(True,False,False,False,False,False,0):
                    raise ValueError('existing_idle_restricted_runtime_role_required')
                password=secrets.token_urlsafe(48)
                uri='postgresql://cj_m1_runtime.'+REF+':'+quote(password,safe='')+'@'+HOST+':5432/postgres?sslmode=verify-full'
                state=dict(state='KEYCHAIN_INTENT',project_ref=REF,role='cj_m1_runtime',
                           credential_sha256=hashlib.sha256(uri.encode()).hexdigest(),sql_change_attempts=0)
                save(path,state)
                stored=subprocess.run(['security','add-generic-password','-a','G2C','-s',SERVICE,'-w',uri,
                    str(Path.home()/'Library/Keychains/login.keychain-db')],capture_output=True,timeout=15)
                if stored.returncode:raise ValueError('runtime_credential_keychain_store_unconfirmed')
                if keychain(SERVICE)!=uri:raise ValueError('runtime_credential_keychain_readback_mismatch')
                # libpq prepares SCRAM locally; plaintext is never sent as SQL or
                # printed in activity/logs. Do not implement a password KDF here.
                verifier=conn.pgconn.encrypt_password(password.encode(),b'cj_m1_runtime',b'scram-sha-256').decode('ascii')
                current_authorization()
                state.update(state='PASSWORD_CHANGE_INTENT',sql_change_attempts=1);save(path,state)
                try:conn.execute(sql.SQL('ALTER ROLE cj_m1_runtime PASSWORD {}').format(sql.Literal(verifier)))
                except psycopg.Error as error:
                    unknown=error.sqlstate is None or error.sqlstate.startswith('08')
                    state.update(state='PASSWORD_CHANGE_UNKNOWN' if unknown else 'PASSWORD_CHANGE_REJECTED',sqlstate=error.sqlstate or 'UNKNOWN');save(path,state)
                    raise
        result=inspect(ca,state)
        state['state']='VERIFIED';save(path,state)
        return dict(mode='EXECUTED',state=state,result={**result,'new_password_changes':1})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('apply','inspect'));parser.add_argument('--ca-file',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='apply':result=apply(args.ca_file)
    else:
        state=load_state(ROOT/'state.json');result=dict(mode='READ_ONLY_ORIGINAL',state=state,result=inspect(args.ca_file,state))
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(state='UNAVAILABLE_OR_UNKNOWN',error_type=type(error).__name__)))
        raise SystemExit(1) from None
