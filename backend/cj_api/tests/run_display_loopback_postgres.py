"""Fresh private RUN display API/PG/Swift loopback; synthetic persisted RUN state and original MESSAGE only."""
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
PRIVATE=ROOT/'.local-cj005-display-pg'
PORT=55452


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--run-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-display-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-display-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private display directory required')
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
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/facts and persisted MESSAGE/RUN fixtures, display-only API','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-run-display-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.run_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/run_display_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/message'),str(Path(exported)/'backend/run')]
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
        command([pg/'initdb','-D',data,'--username=cj005d','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005d',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005d','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            sql_inputs=[]
            for name,path in [('message','backend/message/sql/candidate.sql'),('run','backend/run/sql/candidate.sql')]:
                revision=next(x['commit'] for x in pins['sources'] if x['name']==name)
                schema=subprocess.check_output(['git','-C',str(args.run_repository),'show',revision+':'+path])
                (PRIVATE/(name+'-candidate.sql')).write_bytes(schema);c.execute(schema.decode())
                sql_inputs.append(dict(domain=name,commit=revision,path=path,sha256=hashlib.sha256(schema).hexdigest()))
            for scope in ['fixture-a','fixture-b']:
                c.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)',(scope,))
                c.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,'chat','gen',1)",(scope,))
                c.execute("INSERT INTO cj_run_scope(scope,epoch,active) VALUES (%s,'epoch',true)",(scope,))
        evidence['sql_inputs']=sql_inputs
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, separate canonical MESSAGE/RUN fixture tables and no display store')
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from cj_api.composition import create_composed_app
        from cj_api.run_display_composition import RunDisplayWireConfiguration,create_run_display_app
        from cj_message.postgres import Repository as MessageRepository
        from cj_run.postgres import Repository as RunRepository
        from cj_run.core import Binding,Event,Service as RunService
        import asyncio
        issuer='https://synthetic.invalid/cj005-display';audience='cj005-display-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'invited':True,'run_count':0,'read_fault':None};bindings=set()
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES if controls['invited'] else Fact.NO)
        facts=Facts()
        def scope(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return scopes[p.subject]
        def resolve_message(p):return MessageRepository(connect,scope(p))
        class ReadCommitProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,key):return getattr(self.connection,key)
            def commit(self):
                self.connection.commit()
                if controls['read_fault']=='cancel':raise asyncio.CancelledError()
                if controls['read_fault']=='unknown':raise OSError('synthetic read COMMIT ACK unknown')
        def run_repo(selected,read=False):return RunRepository(ReadCommitProxy if read else connect,selected,
            expires_at=datetime.now(timezone.utc)+timedelta(hours=1),statement_timeout_ms=5000,lock_timeout_ms=5000)
        def resolve_run(p,selected):
            assert selected==scope(p)
            return run_repo(selected,read=True)
        run=RunService(run_repo('fixture-a'),lambda b:b in bindings)
        def new_run_id():controls['run_count']+=1;return 'run-'+str(controls['run_count'])
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0);os.environ['CJ_ENV']='local'
        common=dict(environment='local',jwt_configuration=configuration,verification_keys=keys,access_provider=facts)
        limits=RunDisplayWireConfiguration(1024,4096,16384)
        app=create_composed_app(**common,resolve_repository=resolve_message,new_run_id=new_run_id,max_body_bytes=16384,
            run_display_configuration=limits,resolve_run_display=resolve_run)
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            headers={'Authorization':'Bearer '+token_a,'Content-Type':'application/octet-stream'}
            def message(mid):
                original=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id=mid,text='PRIVATE_USER_INPUT_SENTINEL',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
                result=client.post('/v1/messages',content=original,headers=headers);assert result.status_code==200
                r=result.json()['receipt'];binding=Binding('fixture-a',r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence']);bindings.add(binding)
                return binding
            def get(mid,extra_headers=None):return client.get('/v1/run-display',params={'message_id':mid},headers=extra_headers or headers)
            def checked(mid,status,text,highwater):
                response=get(mid);assert response.status_code==200
                body=response.json();snapshot=body['snapshot']
                assert body['request_id']==response.headers['X-Request-ID'] and response.headers['Cache-Control']=='no-store'
                assert len(snapshot)==9 and snapshot['message_id']==mid and snapshot['status']==status
                assert snapshot['text']==text and snapshot['text_state']==('complete' if status=='completed' else 'partial')
                assert snapshot['event_highwater']==highwater
                assert 'PRIVATE_' not in response.text
                return snapshot
            main=message('display +/%&e\u0301')
            missing=get(main.message_id);assert missing.status_code==503 and 'snapshot' not in missing.json()
            with connect() as c:assert c.execute('SELECT count(*) FROM cj_run_record').fetchone()[0]==0
            run.accept(main);checked(main.message_id,'queued','',0)
            text='Synthetic display e\u0301 中文\n'
            run.apply(Event(main,1,'start-main','started'));run.apply(Event(main,2,'text-main','text_delta',text))
            run.apply(Event(main,3,'effect-main','effect_committed','PRIVATE_TOOL_EFFECT_SENTINEL'))
            checked(main.message_id,'running',text,3)
            run.apply(Event(main,4,'complete-main','completed'));normal=checked(main.message_id,'completed',text,4)
            assert normal['message_sequence']==1
            record('actual missing RUN not synthesized, queued empty/running partial/completed exact text and BASE trace, private input/effects excluded')
            for status in ['failed','cancelled','context_invalid','unknown']:
                b=message('display-'+status);run.accept(b)
                run.apply(Event(b,1,'start-'+status,'started'));run.apply(Event(b,2,'text-'+status,'text_delta',text));run.apply(Event(b,3,'end-'+status,status))
                checked(b.message_id,status,text,3)
            record('all noncompleted persisted statuses retain partial text semantics; no SSE/cancel/worker endpoint or fallback answer')
            bare_bound=len(json.dumps(normal,ensure_ascii=False,separators=(',',':')).encode())
            for cap in [RunDisplayWireConfiguration(1024,4096,bare_bound),RunDisplayWireConfiguration(1024,1,16384)]:
                small=create_run_display_app(**common,resolve_message_repository=resolve_message,resolve_run=resolve_run,configuration=cap)
                with TestClient(small) as c:
                    response=c.get('/v1/run-display',params={'message_id':main.message_id},headers=headers)
                    assert response.status_code==413 and 'snapshot' not in response.json()
            record('real DB plus ASGI exact bare-body cap rejects larger BASE envelope, UTF8 text cap rejects without truncation')
            from cj_api import run_display_routes
            encoder=run_display_routes.encode_response
            def changed(raw,rid):
                encoded=encoder(raw,rid)
                with connect() as c:c.execute("UPDATE cj_run_scope SET epoch='changed-epoch' WHERE scope='fixture-a'")
                return encoded
            with patch.object(run_display_routes,'encode_response',side_effect=changed):
                response=get(main.message_id);assert response.status_code==503 and 'snapshot' not in response.json()
            def denied(raw,rid):
                encoded=encoder(raw,rid);controls['invited']=False;return encoded
            with patch.object(run_display_routes,'encode_response',side_effect=denied):
                response=get(main.message_id);assert response.status_code==503 and 'snapshot' not in response.json()
            controls['invited']=True
            record('epoch change during final encoding and late original AUTH denial withhold already encoded envelope')
            for fault in ['unknown','cancel']:
                controls['read_fault']=fault;response=get(main.message_id)
                assert response.status_code==503 and 'snapshot' not in response.json()
            controls['read_fault']=None
            with connect() as c:c.execute("UPDATE cj_run_scope SET active=false WHERE scope='fixture-a'")
            assert get(main.message_id).status_code==503
            with connect() as c:c.execute("UPDATE cj_run_scope SET active=true WHERE scope='fixture-a'")
            foreign=get(main.message_id,{'Authorization':'Bearer '+token_b});absent=get('nonexistent')
            assert foreign.status_code==absent.status_code==503 and foreign.json()['error']==absent.json()['error']
            record('read COMMIT unknown/cancellation, inactive RUN scope and foreign/missing originals are unavailable, never null snapshots')
            settings={'baseURL':base,'token':token_a,'messageID':main.message_id,'expectedStatus':'completed',
                'expectedTextBase64':base64.b64encode(text.encode()).decode(),'expectedHighwater':4}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            with connect() as c:
                before=c.execute('SELECT (SELECT count(*) FROM cj_run_record),(SELECT count(*) FROM cj_run_event)').fetchone()
            command([ROOT/'.local/run-display-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            with connect() as c:assert c.execute('SELECT (SELECT count(*) FROM cj_run_record),(SELECT count(*) FROM cj_run_event)').fetchone()==before
            record('official generated Swift GET preserves opaque ID/Unicode text/highwater and header-envelope trace; display read creates no RUN/events')
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
