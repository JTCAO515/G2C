"""JT-approved credentials for two fixed existing test roles; never GRANT.

One durable change intent. Re-execution only checks the original credential,
including after unknown commit; it never generates a replacement password.
"""
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import quote

import psycopg
from psycopg import sql

from cj_api.supabase_test_database import decode_uri,decode_cleanup_uri,pin_ca,current_authorization,require_environment,require_identity,prepare_owned_session,HOST,REF
from cj_strict_json import reject_duplicates

ROOT=Path.home()/'.local/share/g2c/m4-supabase-runtime'
SERVICE='g2c-supabase-runtime-db'
CLEANUP_ROOT=Path.home()/'.local/share/g2c/m4-supabase-cleanup'


def target(role):
    if role=='cj_m1_runtime':return ROOT,SERVICE,decode_uri
    if role=='cj_local_cleanup':return CLEANUP_ROOT,'g2c-supabase-cleanup-db',decode_cleanup_uri
    raise ValueError('explicit_preexisting_authorized_test_role_required')


def runtime_keychain(*,value=None,role='cj_m1_runtime'):
    """Fixed newly authorized item via macOS API, never a password in argv.

    No automatic system authorization/unlock. A locked or interaction-requiring
    keychain fails closed; this does not change ACLs or operate SecurityAgent.
    """
    _,service_name,decode=target(role)
    if sys.platform!='darwin':raise ValueError('Mac_runtime_keychain_required')
    current_authorization()
    if value is not None:decode(value)
    security=ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
    foundation=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    pointer=ctypes.c_void_p;integer=ctypes.c_uint32;chars=ctypes.c_char_p
    security.SecKeychainOpen.argtypes=[chars,ctypes.POINTER(pointer)];security.SecKeychainOpen.restype=ctypes.c_int32
    security.SecKeychainAddGenericPassword.argtypes=[pointer,integer,chars,integer,chars,integer,pointer,ctypes.POINTER(pointer)]
    security.SecKeychainAddGenericPassword.restype=ctypes.c_int32
    security.SecKeychainFindGenericPassword.argtypes=[pointer,integer,chars,integer,chars,ctypes.POINTER(integer),ctypes.POINTER(pointer),ctypes.POINTER(pointer)]
    security.SecKeychainFindGenericPassword.restype=ctypes.c_int32
    security.SecKeychainItemFreeContent.argtypes=[pointer,pointer];security.SecKeychainItemFreeContent.restype=ctypes.c_int32
    security.SecKeychainGetUserInteractionAllowed.argtypes=[ctypes.POINTER(ctypes.c_ubyte)];security.SecKeychainGetUserInteractionAllowed.restype=ctypes.c_int32
    security.SecKeychainSetUserInteractionAllowed.argtypes=[ctypes.c_ubyte];security.SecKeychainSetUserInteractionAllowed.restype=ctypes.c_int32
    foundation.CFRelease.argtypes=[pointer];foundation.CFRelease.restype=None
    old=ctypes.c_ubyte();reference=pointer();data=pointer();length=integer()
    if security.SecKeychainGetUserInteractionAllowed(ctypes.byref(old)) or security.SecKeychainSetUserInteractionAllowed(0):
        raise ValueError('keychain_interaction_policy_unavailable')
    try:
        if security.SecKeychainOpen(os.fsencode(Path.home()/'Library/Keychains/login.keychain-db'),ctypes.byref(reference)):
            raise ValueError('login_keychain_unavailable')
        service=service_name.encode();account=b'G2C'
        if value is not None:
            secret=value.encode('utf8');buffer=ctypes.create_string_buffer(secret)
            current_authorization()
            if security.SecKeychainAddGenericPassword(reference,len(service),service,len(account),account,len(secret),buffer,None):
                raise ValueError('runtime_keychain_store_refused_or_requires_user_interaction')
        if security.SecKeychainFindGenericPassword(reference,len(service),service,len(account),account,ctypes.byref(length),ctypes.byref(data),None):
            raise ValueError('runtime_keychain_read_refused_or_requires_user_interaction')
        if not 1<=length.value<=4096:raise ValueError('runtime_keychain_value_invalid')
        result=ctypes.string_at(data,length.value).decode('utf8')
        if value is not None and result!=value:raise ValueError('runtime_keychain_readback_mismatch')
        return result
    finally:
        if data.value:security.SecKeychainItemFreeContent(None,data)
        if reference.value:foundation.CFRelease(reference)
        security.SecKeychainSetUserInteractionAllowed(old.value)


def keychain(name):
    if name==SERVICE:return runtime_keychain()
    if name=='g2c-supabase-cleanup-db':return runtime_keychain(role='cj_local_cleanup')
    if name!='g2c-supabase-db':raise ValueError('authorized_keychain_service_required')
    result=subprocess.run(['security','find-generic-password','-s',name,'-w',str(Path.home()/'Library/Keychains/login.keychain-db')],
                          capture_output=True,text=True,timeout=15)
    if result.returncode or not result.stdout.strip():raise ValueError('authorized_keychain_item_unavailable')
    return result.stdout.strip()


def save(path,value):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary,0o600);json.dump(value,output);output.flush();os.fsync(output.fileno())
    temporary.replace(path)


def load_state(path,*,role='cj_m1_runtime'):
    raw=path.read_bytes()
    if len(raw)>4096:raise ValueError('bounded_original_credential_state_required')
    state=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate_credential_state_field'))
    required={'state','project_ref','role','credential_sha256','sql_change_attempts'}
    if (type(state) is not dict or not required<=set(state) or set(state)-required-{'sqlstate'}
            or state['project_ref']!=REF or state['role']!=role
            or state['state'] not in ('KEYCHAIN_INTENT','PASSWORD_CHANGE_INTENT','PASSWORD_CHANGE_UNKNOWN','PASSWORD_CHANGE_REJECTED','VERIFIED')
            or type(state['sql_change_attempts']) is not int or state['sql_change_attempts'] not in (0,1)
            or (state['state']=='KEYCHAIN_INTENT')!=(state['sql_change_attempts']==0)
            or type(state['credential_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',state['credential_sha256']) is None
            or 'sqlstate' in state and (type(state['sqlstate']) is not str or state['sqlstate']!='UNKNOWN' and re.fullmatch('[0-9A-Z]{5}',state['sqlstate']) is None)):
        raise ValueError('original_runtime_credential_state_invalid')
    return state


def inspect(ca,state,*,role='cj_m1_runtime'):
    current_authorization();require_environment()
    _,service_name,decode=target(role)
    uri=keychain(service_name)
    if hashlib.sha256(uri.encode()).hexdigest()!=state['credential_sha256']:
        raise ValueError('original_runtime_credential_changed')
    with pin_ca(ca) as pinned:
        config=dict(decode(uri),sslrootcert=pinned.name)
        with psycopg.connect(**config,autocommit=True,prepare_threshold=None) as conn:
            prepare_owned_session(conn,role)
            row=conn.execute("SELECT current_user,session_user,(SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid=pg_backend_pid()),"
                             "rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit,"
                             "EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid),"
                             "EXISTS(SELECT 1 FROM pg_catalog.pg_class WHERE relowner=r.oid) FROM pg_catalog.pg_roles r WHERE rolname=current_user").fetchone()
    if row is None or row[:3]!=(role,role,True) or row[3:]!=(False,)*8:
        raise ValueError('restricted_runtime_identity_required')
    return dict(identity=row[0],session_identity=row[1],pooler_to_database_tls=row[2],
                privileges='restricted_runtime',actual_cost='UNKNOWN',new_password_changes=0)


def role_safety(conn,*,role='cj_m1_runtime'):
    before=conn.execute("SELECT rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,rolinherit,"
        "EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid),EXISTS(SELECT 1 FROM pg_catalog.pg_class WHERE relowner=r.oid),"
        "(SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE usename=%s) FROM pg_catalog.pg_roles r WHERE rolname=%s",(role,role)).fetchone()
    if before!=(True,False,False,False,False,False,False,False,False,0):
        raise ValueError('existing_idle_restricted_runtime_role_required')


def apply(ca,*,role='cj_m1_runtime'):
    root,service_name,decode=target(role)
    current_authorization();require_environment();root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=root/'state.json'
        if path.exists():
            state=load_state(path,role=role)
            return dict(mode='READ_ONLY_ORIGINAL',state=state,result=inspect(ca,state,role=role))
        present=subprocess.run(['security','find-generic-password','-s',service_name,str(Path.home()/'Library/Keychains/login.keychain-db')],capture_output=True,timeout=15)
        if present.returncode!=44:raise ValueError('existing_runtime_keychain_entry_not_overwritten')
        operator=keychain('g2c-supabase-db')
        with pin_ca(ca) as pinned:
            config=dict(decode_uri(operator,operator=True),sslrootcert=pinned.name)
            with psycopg.connect(**config,autocommit=True,prepare_threshold=None) as conn:
                prepare_owned_session(conn,'postgres')
                role_safety(conn,role=role)
                password=secrets.token_urlsafe(48)
                uri='postgresql://'+role+'.'+REF+':'+quote(password,safe='')+'@'+HOST+':5432/postgres?sslmode=verify-full'
                state=dict(state='KEYCHAIN_INTENT',project_ref=REF,role=role,
                           credential_sha256=hashlib.sha256(uri.encode()).hexdigest(),sql_change_attempts=0)
                save(path,state)
                runtime_keychain(value=uri,role=role)
                # libpq prepares SCRAM locally; plaintext is never sent as SQL or
                # printed in activity/logs. Do not implement a password KDF here.
                verifier=conn.pgconn.encrypt_password(password.encode(),role.encode('ascii'),b'scram-sha-256').decode('ascii')
                current_authorization();require_environment();require_identity(conn,'postgres');role_safety(conn,role=role)
                state.update(state='PASSWORD_CHANGE_INTENT',sql_change_attempts=1);save(path,state)
                current_authorization();require_environment()
                try:conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(verifier)))
                except psycopg.Error as error:
                    unknown=error.sqlstate is None or error.sqlstate.startswith('08')
                    state.update(state='PASSWORD_CHANGE_UNKNOWN' if unknown else 'PASSWORD_CHANGE_REJECTED',sqlstate=error.sqlstate or 'UNKNOWN');save(path,state)
                    raise
        result=inspect(ca,state,role=role)
        state['state']='VERIFIED';save(path,state)
        return dict(mode='EXECUTED',state=state,result={**result,'new_password_changes':1})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('apply','inspect'));parser.add_argument('--ca-file',type=Path,required=True)
    parser.add_argument('--role',choices=('cj_m1_runtime','cj_local_cleanup'),default='cj_m1_runtime')
    args=parser.parse_args();root,_,_=target(args.role)
    if args.command=='apply':result=apply(args.ca_file,role=args.role)
    else:
        state=load_state(root/'state.json',role=args.role);result=dict(mode='READ_ONLY_ORIGINAL',state=state,result=inspect(args.ca_file,state,role=args.role))
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(state='UNAVAILABLE_OR_UNKNOWN',error_type=type(error).__name__)))
        raise SystemExit(1) from None
