"""Bounded M4 tests for the single JT-authorized synthetic Supabase project.

No hosting/settings/billing changes. Auth owns exactly two journaled synthetic
subjects; passwords/tokens/keys never enter the journal or report. No HTTP retry.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import tempfile
import time
import uuid

import certifi
from cryptography import x509
from cryptography.hazmat.primitives import hashes
import httpx
import jwt
import psycopg
from psycopg.conninfo import conninfo_to_dict
from cj_strict_json import reject_duplicates

REF='sajkhvjpllldfyfryalx'
REGION='ap-southeast-1'
HOST='aws-0-ap-southeast-1.pooler.supabase.com'
AUTH='https://'+REF+'.supabase.co/auth/v1'
CA_SHA='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
STATE=Path.home()/'.local/share/g2c/m4-supabase-auth'
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))


class TestUnavailable(Exception):pass


def expiry():
    if datetime.now(ZoneInfo('Asia/Shanghai'))>=DEADLINE:raise TestUnavailable('authorization_expired')


def decode(raw):
    return json.loads(raw,object_pairs_hook=reject_duplicates(TestUnavailable,'duplicate_response_field'))


def keychain(name):
    result=subprocess.run(['security','find-generic-password','-s',name,'-w'],capture_output=True,text=True)
    if result.returncode or not result.stdout.strip():raise TestUnavailable('keychain_unavailable')
    return result.stdout.strip()


@contextmanager
def database_config(ca):
    expiry()
    if any(k.startswith(('PG','LIBPQ')) for k in os.environ) or 'SSLKEYLOGFILE' in os.environ:
        raise TestUnavailable('ambient_database_or_tls_configuration_refused')
    raw=keychain('g2c-supabase-db')
    if not raw.startswith(('postgresql://','postgres://')):raise TestUnavailable('explicit_project_uri_required')
    config=conninfo_to_dict(raw)
    if (set(config)-{'host','port','user','password','dbname','sslmode','connect_timeout'}
            or config.get('host')!=HOST or config.get('user')!='postgres.'+REF
            or config.get('dbname')!='postgres' or config.get('port','5432') not in ('5432','6543')):
        raise TestUnavailable('authorized_project_connection_mismatch')
    data=ca.read_bytes();certificate=x509.load_pem_x509_certificate(data)
    if certificate.fingerprint(hashes.SHA256()).hex()!=CA_SHA:raise TestUnavailable('supabase_ca_mismatch')
    with tempfile.NamedTemporaryFile(prefix='g2c-m4-ca-') as pinned:
        pinned.write(data);pinned.flush()
        config.update(sslmode='verify-full',sslrootcert=pinned.name,connect_timeout=10)
        yield config


class Database:
    def __init__(self,config):self.config=config;self.connections=0;self.statements=0
    def connect(self,*,port=None):
        self.connections+=1
        options=dict(self.config)
        if port is not None:options['port']=port
        return psycopg.connect(**options,autocommit=True,prepare_threshold=None)
    def query(self,conn,sql,parameters=None):
        self.statements+=1
        return conn.execute(sql,parameters)
    def user_id(self,email):
        with self.connect() as conn:
            rows=self.query(conn,'SELECT id::text FROM auth.users WHERE email=%s',(email,)).fetchall()
        if len(rows)>1:raise TestUnavailable('synthetic_subject_not_unique')
        return None if not rows else rows[0][0]
    def sessions(self,user):
        with self.connect() as conn:
            return self.query(conn,'SELECT count(*) FROM auth.sessions WHERE user_id=%s',(user,)).fetchone()[0]


class AuthJournal:
    def __init__(self):
        STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=STATE/'state.json';self.fresh=not self.path.exists()
        if self.fresh:
            run=uuid.uuid4().hex
            self.value=dict(run_id=run,complete=False,calls=0,subjects=[dict(label=label,
                email=f'm4-{run}-{label}@example.invalid',id=None,state='planned') for label in ('a','b')])
            self.save()
        else:self.value=decode(self.path.read_bytes())
        if (type(self.value) is not dict or set(self.value)!={'run_id','complete','calls','subjects'}
                or type(self.value['complete']) is not bool or type(self.value['calls']) is not int
                or not 0<=self.value['calls']<=32 or type(self.value['run_id']) is not str
                or type(self.value['subjects']) is not list):raise TestUnavailable('auth_journal_invalid')
        run=self.value['run_id']
        if (len(run)!=32 or uuid.UUID(hex=run).hex!=run or len(self.value['subjects'])!=2
                or [x['label'] for x in self.value['subjects']]!=['a','b']):raise TestUnavailable('auth_journal_invalid')
        for item in self.value['subjects']:
            if (set(item)!={'label','email','id','state'} or item['email']!=f"m4-{run}-{item['label']}@example.invalid"
                    or item['state'] not in ('planned','intent','created','deleted')
                    or item['id'] is not None and str(uuid.UUID(item['id']))!=item['id']):
                raise TestUnavailable('auth_subject_binding_invalid')
    def save(self):
        temporary=self.path.with_suffix('.tmp')
        with temporary.open('w') as out:
            os.chmod(temporary,0o600);json.dump(self.value,out);out.flush();os.fsync(out.fileno())
        temporary.replace(self.path)
        fd=os.open(STATE,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)


class AuthClient:
    def __init__(self,secret,public,journal):
        if not secret.startswith('sb_secret_') or any(c in secret for c in ('\n','\r')):
            raise TestUnavailable('server_secret_key_required')
        if not public.startswith('sb_publishable_') or any(c in public for c in ('\n','\r')):
            raise TestUnavailable('public_client_key_required')
        self.secret,self.public,self.journal=secret,public,journal
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.load_verify_locations(cafile=certifi.where())
        self.client=httpx.Client(verify=context,trust_env=False,follow_redirects=False,timeout=15)
        self.events=[]
    def request(self,operation,method,path,*,admin=False,token=None,body=None,expected=(200,)):
        expiry()
        if self.journal.value['calls']>=32:raise TestUnavailable('bounded_auth_request_limit')
        self.journal.value['calls']+=1;self.journal.save()
        headers={'apikey':self.secret if admin else self.public}
        if token is not None:headers['Authorization']='Bearer '+token
        started=time.monotonic()
        response=self.client.request(method,AUTH+path,headers=headers,json=body)
        self.events.append(dict(operation=operation,http_status=response.status_code,seconds=time.monotonic()-started))
        if response.status_code not in expected:raise TestUnavailable(operation+'_http_'+str(response.status_code))
        if response.status_code==204 or not response.content:return None
        if len(response.content)>1_048_576:raise TestUnavailable('auth_response_too_large')
        return decode(response.content)
    def close(self):self.client.close()


def cleanup_auth(journal,api,db):
    outcomes=[]
    for subject in journal.value['subjects']:
        if subject['state']=='planned':continue
        current=db.user_id(subject['email'])
        if current is None:
            subject['state']='deleted';journal.save();outcomes.append('absent');continue
        if subject['id'] is not None and subject['id']!=current:raise TestUnavailable('original_auth_subject_changed')
        # A lost create response is resolved by the exact preallocated synthetic
        # email, never by listing users or inventing another subject/identity.
        subject['id']=current;journal.save()
        api.request('delete_own_synthetic','DELETE','/admin/users/'+current,admin=True)
        if db.user_id(subject['email']) is not None:raise TestUnavailable('auth_delete_unconfirmed')
        subject['state']='deleted';journal.save();outcomes.append('deleted')
    return outcomes


def auth_test(db,public_file):
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'operator.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        journal=AuthJournal()
        if journal.value['complete']:return dict(status='READ_ONLY_COMPLETE',created_total=2,additional_calls=0)
        api=AuthClient(keychain('g2c-supabase-auth-test'),public_file.read_text().strip(),journal)
        report=dict(status='FAIL',synthetic_only=True,email_delivery='UNRUN',iOS_SDK='UNRUN',CJ_cloud_host='UNRUN')
        try:
            if not journal.fresh:
                report['cleanup']=cleanup_auth(journal,api,db)
                report['status']='CLEANUP_ONLY_NO_RECREATE'
                return report
            tokens=[]
            for subject in journal.value['subjects']:
                if db.user_id(subject['email']) is not None:raise TestUnavailable('unexpected_existing_synthetic_email')
                password=secrets.token_urlsafe(32)
                subject['state']='intent';journal.save()
                user=api.request('create_own_synthetic','POST','/admin/users',admin=True,
                    body=dict(email=subject['email'],password=password,email_confirm=True))
                if type(user) is not dict or user.get('email')!=subject['email']:
                    raise TestUnavailable('created_auth_subject_binding_unknown')
                subject['id']=str(uuid.UUID(user['id']));subject['state']='created';journal.save()
                if db.user_id(subject['email'])!=subject['id']:raise TestUnavailable('created_auth_subject_not_confirmed')
                logged=api.request('public_password_login','POST','/token?grant_type=password',
                    body=dict(email=subject['email'],password=password))
                token=logged['access_token'];refresh=logged['refresh_token']
                if logged['user']['id']!=subject['id'] or type(token) is not str or type(refresh) is not str:
                    raise TestUnavailable('original_login_binding_unknown')
                current=api.request('public_get_own_user','GET','/user',token=token)
                if current['id']!=subject['id']:raise TestUnavailable('user_identity_mismatch')
                tokens.append((token,refresh))
            denied=api.request('user_cannot_read_admin_other_subject','GET','/admin/users/'+journal.value['subjects'][1]['id'],
                token=tokens[0][0],expected=(401,403))
            api.request('tampered_user_token_rejected','GET','/user',token=tokens[0][0]+'x',expected=(401,403))
            keys=api.request('public_jwks','GET','/.well-known/jwks.json')
            verified=[]
            for subject,(token,_) in zip(journal.value['subjects'],tokens):
                header=jwt.get_unverified_header(token)
                if header.get('alg') not in ('ES256','RS256'):
                    verified.append('UNRUN_unsupported_public_algorithm');continue
                candidates=[value for value in keys['keys'] if value.get('kid')==header.get('kid')]
                if len(candidates)!=1:raise TestUnavailable('unique_project_jwk_unavailable')
                claims=jwt.decode(token,jwt.PyJWK.from_dict(candidates[0]).key,algorithms=[header['alg']],
                    issuer=AUTH,audience='authenticated',options={'require':['iss','aud','sub','exp','iat','session_id']})
                if claims['sub']!=subject['id'] or claims.get('role')!='authenticated':raise TestUnavailable('verified_principal_mismatch')
                verified.append('PASS')
            report['public_jwt_verification']=verified
            outcomes=[]
            for subject,(token,refresh) in zip(journal.value['subjects'],tokens):
                before=db.sessions(subject['id'])
                api.request('sign_out_own_session','POST','/logout?scope=global',token=token,expected=(200,204))
                after=db.sessions(subject['id'])
                api.request('old_refresh_refused','POST','/token?grant_type=refresh_token',body={'refresh_token':refresh},expected=(400,401,403))
                old=api.request('old_access_observation','GET','/user',token=token,expected=(200,401,403))
                if old is not None and 'id' in old and old['id']!=subject['id']:raise TestUnavailable('old_access_subject_changed')
                outcomes.append(dict(sessions_before=before,sessions_after=after))
                if before<1 or after!=0:raise TestUnavailable('session_revocation_not_confirmed')
            report.update(status='PASS',accounts=2,session_results=outcomes,
                note='admin-confirmed synthetic email; logout does not itself prove cryptographic access-JWT revocation')
        except (TestUnavailable,httpx.HTTPError,psycopg.Error,ValueError,KeyError,TypeError) as error:
            report.update(status='FAIL',error=type(error).__name__,reason=str(error) if type(error) is TestUnavailable else 'operation_unproven')
        finally:
            try:report['cleanup']=cleanup_auth(journal,api,db)
            except (TestUnavailable,httpx.HTTPError,psycopg.Error,ValueError,KeyError,TypeError) as error:
                report.update(cleanup_status='UNKNOWN',cleanup_error=type(error).__name__,status='FAIL')
            report['events']=api.events;report['http_calls']=journal.value['calls'];api.close()
            if report['status']=='PASS':journal.value['complete']=True;journal.save()
        return report


def pool_test(db):
    reports=[]
    for mode,port in (('session',5432),('transaction',6543)):
        name='cj.m4_probe_'+uuid.uuid4().hex;value='synthetic-'+uuid.uuid4().hex
        with db.connect(port=port) as conn:
            row=db.query(conn,"SELECT current_user,current_setting('server_version'),(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
            with conn.transaction():
                db.query(conn,'SELECT set_config(%s,%s,true)',(name,value))
                if db.query(conn,'SELECT current_setting(%s,true)',(name,)).fetchone()[0]!=value:
                    raise TestUnavailable('transaction_local_probe_not_installed')
            expired=db.query(conn,'SELECT current_setting(%s,true)',(name,)).fetchone()[0] in (None,'')
            before=db.query(conn,'SELECT pg_backend_pid(),set_config(%s,%s,false)',(name,value)).fetchone()[0]
        with db.connect(port=port) as conn:
            pid,returned=db.query(conn,'SELECT pg_backend_pid(),current_setting(%s,true)',(name,)).fetchone()
            reset='UNKNOWN_DIFFERENT_PHYSICAL_SESSION' if pid!=before else 'PASS_OBSERVED' if returned in (None,'') else 'FAIL_SESSION_STATE_RETAINED'
            if returned==value:db.query(conn,'SELECT set_config(%s,%s,false)',(name,''))
        reports.append(dict(mode=mode,port=port,server_version=row[1],initializer_role=row[0],
            client_tls='verify-full',upstream_tls=row[2],transaction_local_expired=expired,
            disconnect_reset=reset,product_pooler_activation='HOLD_no_runtime_login_or_complete_12_table_gate'))
    return dict(status='MEASURED',modes=reports)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('auth','pool','inspect'))
    parser.add_argument('--ca-file',type=Path,required=True)
    parser.add_argument('--public-key-file',type=Path)
    args=parser.parse_args()
    with database_config(args.ca_file) as config:
        db=Database(config)
        if args.command=='auth':
            if args.public_key_file is None:parser.error('public client key file required')
            report=auth_test(db,args.public_key_file)
        elif args.command=='pool':report=pool_test(db)
        else:
            with db.connect() as conn:
                row=db.query(conn,"SELECT current_setting('server_version'),to_regclass('cj.schema_migrations') IS NOT NULL").fetchone()
            report=dict(status='PASS',server_version=row[0],migration_ledger_present=row[1])
        report.update(project_ref=REF,region=REGION,sql_connections=db.connections,sql_statements=db.statements,
            actual_cost='UNKNOWN',versions={name:version(name) for name in ('psycopg','httpx','PyJWT')})
        print(json.dumps(report))


if __name__=='__main__':
    try:main()
    except (TestUnavailable,psycopg.Error,httpx.HTTPError,ValueError,KeyError,TypeError,OSError) as error:
        print(json.dumps(dict(status='FAIL',error=type(error).__name__,reason=str(error) if type(error) is TestUnavailable else 'operation_unproven')))
        raise SystemExit(1) from None
