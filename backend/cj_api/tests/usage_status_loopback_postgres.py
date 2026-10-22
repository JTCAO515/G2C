"""Fresh SELECT-only authenticated original USAGE status API and Swift fixture."""
import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[3]
PRIVATE=ROOT/'.local-cj005-usage-read-pg'
PORT=55454


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--usage-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-usage-read-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-usage-read-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private usage read directory required')
    PRIVATE=ROOT/args.private_name
    if any(k.startswith('PG') or k in ('DATABASE_URL','CJ_DATABASE_URL') for k in os.environ):
        raise RuntimeError('Inherited database configuration refused')
    if PRIVATE.exists() or PRIVATE.is_symlink():raise RuntimeError('Existing private directory refused')
    PRIVATE.mkdir(mode=0o700);(PRIVATE/'s').mkdir(mode=0o700)
    (PRIVATE/'empty.pgpass').touch(mode=0o600)
    clean={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg=Path(subprocess.check_output(['pg_config','--bindir'],env=clean,text=True).strip())
    assert len(str(PRIVATE/'s'/('.s.PGSQL.'+str(PORT))).encode())<104
    data=PRIVATE/'data';server=thread=http_socket=None
    evidence={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/historical usage fixtures; SELECT-only status','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-usage-status-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.usage_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/usage_status_pins.json').read_text());evidence['pins']=pins
        packages=[args.driver_source/'psycopg',args.driver_source/'psycopg-3.2.10.dist-info']
        assert not args.driver_source.is_symlink() and all(p.is_dir() for p in packages)
        files={}
        for package in packages:
            for path in [package,*package.rglob('*')]:
                assert not path.is_symlink() and path.resolve().is_relative_to(args.driver_source.resolve())
                if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                    files[str(path.relative_to(args.driver_source))]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert 'Version: 3.2.10\n' in (packages[1]/'METADATA').read_text()
        (PRIVATE/'driver').mkdir(mode=0o700)
        for package in packages:
            shutil.copytree(package,PRIVATE/'driver'/package.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name,digest in files.items():assert hashlib.sha256((PRIVATE/'driver'/name).read_bytes()).hexdigest()==digest
        (PRIVATE/'driver-source.json').write_text(json.dumps({'source':str(args.driver_source),'version':'3.2.10','files':files,
            'manifest_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()},indent=2)+'\n')
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/usage')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((PRIVATE/'driver').resolve())
        evidence['driver']={'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg/'initdb','-D',data,'--username=cj005u_admin','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect(user='cj005u_admin'):return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user=user,dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005u_admin','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            revision=pins['sources'][1]['commit']
            schema=subprocess.check_output(['git','-C',str(args.usage_repository),'show',revision+':backend/usage/sql/001_candidate.sql'])
            (PRIVATE/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_usage_ledger_candidate').fetchone()[0]==0
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero USAGE rows')
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from cj_usage.core import Config,Ledger,Run,Attempt,Command,Receipt
        from cj_usage.codec import encode
        from cj_usage.postgres import PostgresRepository
        from cj_api.usage_status_composition import UsageStatusConfiguration,create_usage_status_app
        import asyncio
        roles={'subject-a':'cj005u_a','subject-b':'cj005u_b'}
        unit='fixture-work/opaque-v1';reserved=10**41;big=10**40;unknown_id='attempt +/%&e\u0301'
        cfg=Config(unit,10**43,0,1000,20,20,10**43,1000)
        attempts={}
        for aid,state,actual in [(unknown_id,'unknown',None),('zero','settled',0),('big','settled',big)]:
            c=Command(aid,'original-'+('unknown' if actual is None else aid),'original-run','model','a'*64,reserved,reserved)
            r=Receipt(aid,'receipt-'+aid,unit,actual,0) if actual is not None else None
            attempts[aid]=Attempt(c,state,r,False,False)
        ledger=Ledger(cfg,attempts,{'original-run':Run(10,3,0,False)},10)
        bcmd=Command('own-b','op-b','run-b','model','b'*64,1,1)
        ledger_b=Ledger(cfg,{'own-b':Attempt(bcmd)},{'run-b':Run(10,1,0,False)},10)
        with connect() as c:
            for role in roles.values():
                c.execute('CREATE ROLE '+role+' LOGIN NOSUPERUSER NOBYPASSRLS')
                c.execute('GRANT SELECT ON public.cj_usage_ledger_candidate TO '+role)
            c.execute('CREATE POLICY fixture_scope ON public.cj_usage_ledger_candidate USING (scope_id=current_user)')
            for role,value in [(roles['subject-a'],ledger),(roles['subject-b'],ledger_b)]:
                c.execute('INSERT INTO public.cj_usage_ledger_candidate VALUES (%s,17,1,%s::jsonb)',(role,encode(value)))
        for role in roles.values():
            with connect(role) as c:
                assert c.execute("SELECT rolsuper,rolbypassrls,has_table_privilege(current_user,'public.cj_usage_ledger_candidate','SELECT'),has_table_privilege(current_user,'public.cj_usage_ledger_candidate','UPDATE'),has_table_privilege(current_user,'public.cj_usage_ledger_candidate','INSERT') FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False,True,False,False)
        def inventory():
            with connect() as c:return c.execute('SELECT scope_id,revision,format_version,ledger::text FROM public.cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
        before=inventory();statements=[]
        controls={'invited':True,'mode':None,'after_close':False,'wrong_connection':False};period_calls=[]
        class CursorProxy:
            def __init__(self,c):self.c=c
            def execute(self,sql,args=None):
                statements.append(sql);self.c.execute(sql,args)
                if sql.startswith('SET TRANSACTION'):
                    with self.c.connection.cursor() as probe:assert probe.execute("SELECT current_setting('transaction_read_only')").fetchone()[0]=='on'
            def fetchone(self):return self.c.fetchone()
            def close(self):self.c.close()
        class ConnProxy:
            def __init__(self,role):self.c=connect(role)
            @property
            def autocommit(self):return self.c.autocommit
            def cursor(self):return CursorProxy(self.c.cursor())
            def commit(self):
                self.c.commit()
                if controls['mode']=='unknown':raise OSError('synthetic read ACK lost')
                if controls['mode']=='cancel':raise asyncio.CancelledError()
            def rollback(self):self.c.rollback()
            def close(self):
                self.c.close()
                if controls['after_close']:controls['invited']=False
                if controls['mode']=='close':raise OSError('synthetic close failure')
        issuer='https://synthetic.invalid/cj005-usage-read';audience='cj005-usage-read-synthetic'
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in roles else Fact.NO,Fact.YES,Fact.YES if controls['invited'] else Fact.NO)
        def resolve(p,environment,start,end):
            assert p.issuer==issuer and p.audience==audience and p.subject in roles and environment=='local'
            period_calls.append((p.subject,environment,start,end))
            selected=roles[p.subject];connection_role=roles['subject-b'] if controls['wrong_connection'] else selected
            return PostgresRepository(lambda:ConnProxy(connection_role),selected)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        jwt_config=JWTConfiguration(issuer,audience,'RS256',0);os.environ['CJ_ENV']='local'
        common=dict(environment='local',jwt_configuration=jwt_config,verification_keys=keys,access_provider=Facts(),resolve=resolve)
        limits=UsageStatusConfiguration(0,1000,800,65536)
        app=create_usage_status_app(configuration=limits,**common)
        def token(subject,shift=0):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-2+shift,nbf=now-2+shift,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            headers={'Authorization':'Bearer '+token_a}
            def get(aid,selected=None):return client.get('/v1/usage-attempt-status',params={'attempt_id':aid},headers=selected or headers)
            for aid,expected in [(unknown_id,None),('zero','0'),('big',str(big))]:
                response=get(aid);assert response.status_code==200
                body=response.json();a=body['attempt']
                assert a['reserved_units']==str(reserved) and a['confirmed_units']==expected
                assert a['confirmed_output']==('0' if expected is not None else None) and a['unit']==unit
                assert a['attempt_id']==aid and 'input_digest' not in a and 'budget' not in a and 'ledger' not in a
                assert body['request_id']==response.headers['X-Request-ID'] and response.headers['Cache-Control']=='no-store'
            assert all(call[1:]==('local',0,1000) for call in period_calls)
            record('SELECT-only runtime NOBYPASSRLS, original unknown-null/confirmed-zero/>Int64 exact units and original host historical period')
            with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:get(unknown_id),range(2)))
            assert all(r.status_code==200 for r in responses)
            refreshed=get(unknown_id,{'Authorization':'Bearer '+token('subject-a',1)})
            assert refreshed.status_code==200 and refreshed.json()['attempt']==responses[0].json()['attempt']
            record('two concurrent numeric HTTP reads succeed with separate native lifetimes; refreshed token stays original partition')
            assert get(unknown_id,{'Authorization':'Bearer '+token_b}).status_code==503
            own=get('own-b',{'Authorization':'Bearer '+token_b});assert own.status_code==200 and own.json()['attempt']['reserved_units']=='1'
            controls['wrong_connection']=True;assert get(unknown_id).status_code==503;controls['wrong_connection']=False
            wrong=create_usage_status_app(configuration=UsageStatusConfiguration(1,1001,800,65536),**common)
            with TestClient(wrong) as c:assert c.get('/v1/usage-attempt-status',params={'attempt_id':unknown_id},headers=headers).status_code==503
            assert client.get('/v1/usage-attempt-status?attempt_id=zero&period_start=0',headers=headers).status_code==400
            record('foreign/missing attempt and RLS connection-scope mismatch unavailable; wrong host period rejected, caller period forbidden')
            from cj_api import usage_status_routes
            original_project=usage_status_routes.encode_response
            def revoked(*args):
                value=original_project(*args);controls['invited']=False;return value
            with patch.object(usage_status_routes,'encode_response',side_effect=revoked):
                response=get(unknown_id);assert response.status_code==403 and 'attempt' not in response.json()
            controls['invited']=True;controls['after_close']=True
            response=get(unknown_id);assert response.status_code==403 and 'attempt' not in response.json()
            controls.update(invited=True,after_close=False)
            record('authority lost during protected projection or final connection-close withholds all original status bytes')
            for mode in ['unknown','cancel','close']:
                controls['mode']=mode;response=get(unknown_id)
                assert response.status_code==503 and 'attempt' not in response.json()
            controls.update(mode='unknown',after_close=True)
            response=get(unknown_id);assert response.status_code==503 and response.json()['error']['category']=='dependency'
            controls.update(mode=None,after_close=False,invited=True)
            record('read COMMIT unknown/cancellation/close failure unavailable; primary unknown outranks later close revocation')
            settings={'baseURL':base,'token':token_a,'unknownID':unknown_id,'zeroID':'zero','bigID':'big','reservedUnits':str(reserved),'bigUnits':str(big),'unit':unit}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            command([ROOT/'.local/usage-status-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            assert all(sql.startswith('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY') or sql.startswith('SELECT ') for sql in statements)
            assert inventory()==before
            record('official generated Swift original status, exact strings/null/zero and opaque unit; every ledger/revision unchanged, no FOR UPDATE or mutator SQL')
        evidence['result']='PASS'
    finally:
        if server:server.should_exit=True
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():server.force_exit=True;thread.join(timeout=5)
            assert not thread.is_alive()
        if http_socket:http_socket.close()
        if (data/'postmaster.pid').exists():command([pg/'pg_ctl','-D',data,'-m','fast','-w','stop'],PRIVATE/'pg-stop.txt',clean)
        assert not (data/'postmaster.pid').exists() and not (PRIVATE/'s'/('.s.PGSQL.'+str(PORT))).exists()
        evidence['safe_stop']='PASS'
        (PRIVATE/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('PASS HTTP thread and exact private PostgreSQL stopped; data retained',flush=True)


if __name__=='__main__':main()
