"""Fresh private FEEDBACK API/PG/Swift loopback; synthetic voluntary feedback and canonical source fixtures only."""
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
PRIVATE=ROOT/'.local-cj005-feedback-pg'
PORT=55451


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--feedback-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-feedback-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-feedback-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private feedback directory required')
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
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/manual input only','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-feedback-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.feedback_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/feedback_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/feedback'),str(Path(exported)/'backend/message'),str(Path(exported)/'backend/run')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
        from cj_feedback.domain import Action
        from cj_api.feedback_composition import create_feedback_composed_app,FeedbackWireConfiguration
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((PRIVATE/'driver').resolve())
        evidence['driver']={'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg/'initdb','-D',data,'--username=cj005f','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005f',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005f','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            sql_inputs=[]
            for name,path in [('message','backend/message/sql/candidate.sql'),('run','backend/run/sql/candidate.sql'),('feedback','backend/feedback/sql/candidate.sql')]:
                revision=next(x['commit'] for x in pins['sources'] if x['name']==name)
                schema=subprocess.check_output(['git','-C',str(args.feedback_repository),'show',revision+':'+path])
                (PRIVATE/(name+'-candidate.sql')).write_bytes(schema);c.execute(schema.decode())
                sql_inputs.append(dict(domain=name,commit=revision,path=path,sha256=hashlib.sha256(schema).hexdigest()))
            assert c.execute('SELECT count(*) FROM cj_feedback_action').fetchone()[0]==0
            for scope in ['fixture-a','fixture-b']:
                c.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)',(scope,))
                c.execute("INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,'chat','gen',1)",(scope,))
                c.execute("INSERT INTO cj_run_scope(scope,epoch,active) VALUES (%s,'epoch',true)",(scope,))
        evidence['sql_inputs']=sql_inputs
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero feedback rows and separate canonical MESSAGE/RUN fixture tables')
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from cj_api.composition import create_composed_app
        from cj_message.postgres import Repository as MessageRepository
        from cj_run.postgres import Repository as RunRepository
        from cj_run.core import Binding,Event,Service as RunService
        import asyncio
        issuer='https://synthetic.invalid/cj005-feedback';audience='cj005-feedback-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'invited':True,'ack':None,'run_count':0,'source_reads':0,'mutate_on':None,'mutate_binding':None}
        bindings=set()
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES if controls['invited'] else Fact.NO)
        facts=Facts()
        class CommitProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,k):return getattr(self.connection,k)
            def commit(self):
                self.connection.commit();fault=controls['ack'];controls['ack']=None
                if fault=='lost':raise OSError('synthetic feedback ACK loss after real COMMIT')
                if fault=='cancel':raise asyncio.CancelledError()
        def scope(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return scopes[p.subject]
        def resolve_feedback(p):return CommitProxy,scope(p)
        def resolve_message(p):return MessageRepository(connect,scope(p))
        def run_repo(selected):return RunRepository(connect,selected,expires_at=datetime.now(timezone.utc)+timedelta(hours=1),statement_timeout_ms=5000,lock_timeout_ms=5000)
        run=RunService(run_repo('fixture-a'),lambda b:b in bindings)
        def resolve_run(p,selected):
            assert selected==scope(p)
            controls['source_reads']+=1
            if controls['source_reads']==controls['mutate_on']:
                run.apply(Event(controls['mutate_binding'],1,'synthetic-cancel','cancelled'))
            return run_repo(selected)
        def new_run_id():controls['run_count']+=1;return 'run-'+str(controls['run_count'])
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0);os.environ['CJ_ENV']='local'
        dependencies=dict(environment='local',jwt_configuration=configuration,verification_keys=keys,access_provider=facts)
        options=FeedbackWireConfiguration(16384,65536)
        app=create_composed_app(**dependencies,resolve_repository=resolve_message,new_run_id=new_run_id,max_body_bytes=16384,
            feedback_configuration=options,resolve_feedback=resolve_feedback,resolve_feedback_run=resolve_run)
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        def raw(aid,refs=None):return json.dumps(dict(action_id=aid,problem='Synthetic e\u0301 中文 problem',expectation='',references=refs or []),ensure_ascii=False,indent=1).encode()
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            headers={'Authorization':'Bearer '+token_a,'Content-Type':'application/octet-stream'}
            def post(value):return client.post('/v1/feedback',content=value,headers=headers)
            def query(aid):return client.get('/v1/feedback-action-receipts',params={'action_id':aid},headers=headers)
            general=raw('general');first=post(general);assert first.status_code==200
            receipt=first.json()['receipt'];assert receipt['source'] is None and receipt['input_sha256']==hashlib.sha256(general).hexdigest()
            assert receipt['status']=='submitted' and receipt['message_zh']=='反馈已提交。'
            assert post(general).json()['receipt']==receipt and query('general').json()['receipt']==receipt
            assert post(general+b' ').status_code==409
            record('general feedback real persisted original hash/UTC receipt, source null, exact replay and byte conflict')
            def message(mid):
                message_raw=json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id=mid,
                    text='PRIVATE_MESSAGE_SENTINEL',trip_id=None,creation_intent='none'),ensure_ascii=False).encode()
                result=client.post('/v1/messages',content=message_raw,headers=headers);assert result.status_code==200
                r=result.json()['receipt']
                b=Binding('fixture-a',r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
                bindings.add(b)
                return b,r,message_raw
            binding,message_receipt,message_raw=message('message-e\u0301')
            refs=[{'kind':'message','id':binding.message_id},{'kind':'run','id':binding.run_id}]
            assert post(raw('no_run',refs)).status_code==503 and query('no_run').json()['receipt'] is None
            run.accept(binding)
            run.apply(Event(binding,1,'start','started'));run.apply(Event(binding,2,'text','text_delta','PRIVATE_RUN_SENTINEL'));run.apply(Event(binding,3,'end','completed'))
            linked=raw('linked',refs);saved=post(linked);assert saved.status_code==200
            linked_receipt=saved.json()['receipt'];source=linked_receipt['source']
            assert source['message_input_sha256']==message_receipt['input_sha256']==hashlib.sha256(message_raw).hexdigest()
            assert (source['run_status_at_read'],source['event_highwater_at_read'])==('completed',3)
            assert set(source)=={'message_id','conversation_id','generation','message_sequence','run_id','message_input_sha256','run_status_at_read','event_highwater_at_read'}
            assert 'PRIVATE_' not in json.dumps(linked_receipt)
            with connect() as c:
                row=c.execute("SELECT original_input,source_reference::text FROM cj_feedback_action WHERE scope='fixture-a' AND action_id='linked'").fetchone()
                assert bytes(row[0])==linked and b'PRIVATE_' not in bytes(row[0]) and 'PRIVATE_' not in row[1]
            record('same-app canonical MESSAGE/RUN source read, missing RUN rejection, minimal read-time metadata only and no private payload copy')
            bare=create_feedback_composed_app(**dependencies,resolve=resolve_feedback,configuration=options)
            with TestClient(bare) as bare_client:
                denied=bare_client.post('/v1/feedback',content=raw('missing_sources',refs),headers=headers)
                assert denied.status_code==503
            assert query('missing_sources').json()['receipt'] is None
            assert post(raw('bad_run',[refs[0],{'kind':'run','id':'other-run'}])).status_code==503
            b_headers={'Authorization':'Bearer '+token_b,'Content-Type':'application/octet-stream'}
            denied=client.post('/v1/feedback',content=raw('foreign',refs),headers=b_headers)
            missing=post(raw('missing',[{'kind':'message','id':'not-found'}]))
            assert denied.status_code==missing.status_code==503 and denied.json()['error']==missing.json()['error']
            assert client.get('/v1/feedback-action-receipts',params={'action_id':'linked'},headers=b_headers).json()['receipt'] is None
            record('missing Sources fails referenced submit with real DB/ASGI; numeric HTTP wrong RUN/foreign/missing and original query isolation')
            queued,_,_=message('queued-before');run.accept(queued)
            controls.update(source_reads=0,mutate_on=2,mutate_binding=queued)
            failure=post(raw('before_change',[{'kind':'message','id':queued.message_id}]))
            controls['mutate_on']=None
            assert failure.status_code==503 and query('before_change').json()['receipt'] is None
            record('observed RUN change before feedback commit rejects without feedback row; no cross-domain atomicity assertion')
            after,_,_=message('queued-after');run.accept(after)
            from cj_api import feedback_routes
            original_project=feedback_routes.FeedbackReceipt.model_validate_json
            def changing(*a,**kw):
                value=original_project(*a,**kw);run.apply(Event(after,1,'cancel-after','cancelled'));return value
            after_raw=raw('after_change',[{'kind':'message','id':after.message_id}])
            with patch.object(feedback_routes.FeedbackReceipt,'model_validate_json',side_effect=changing):
                failure=post(after_raw);assert failure.status_code==503 and failure.json()['error']['recovery']=='reconcile_original'
            old=query('after_change').json()['receipt']
            assert old['source']['run_status_at_read']=='queued' and old['source']['event_highwater_at_read']==0
            assert old['input_sha256']==hashlib.sha256(after_raw).hexdigest()
            record('postcommit source change withholds final bytes; original query returns historical queued observation without rereading current source')
            for mode in ['lost','cancel']:
                original=raw(mode);controls['ack']=mode
                failure=post(original);assert failure.status_code==503 and failure.json()['error']['recovery']=='reconcile_original'
                assert query(mode).json()['receipt']['input_sha256']==hashlib.sha256(original).hexdigest()
            def withdrawing(*a,**kw):
                value=original_project(*a,**kw);controls['invited']=False;return value
            with patch.object(feedback_routes.FeedbackReceipt,'model_validate_json',side_effect=withdrawing):
                failure=post(raw('auth_after'));assert failure.status_code==503 and 'receipt' not in failure.json()
            controls['invited']=True;assert query('auth_after').json()['receipt']['status']=='submitted'
            record('real feedback COMMIT followed by ACK loss/cancellation or projection AUTH loss remains original-action recovery')
            general_swift=raw('swift_general');linked_swift=raw('swift_linked',refs)
            settings={'baseURL':base,'token':token_a,'generalBase64':base64.b64encode(general_swift).decode(),'linkedBase64':base64.b64encode(linked_swift).decode(),
                'messageID':binding.message_id,'runID':binding.run_id,'messageInputHash':message_receipt['input_sha256'],'highwater':3}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            command([ROOT/'.local/feedback-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            with connect() as c:
                rows=c.execute("SELECT original_input FROM cj_feedback_action WHERE scope='fixture-a' AND action_id IN ('swift_general','swift_linked') ORDER BY action_id").fetchall()
                assert [bytes(r[0]) for r in rows]==[general_swift,linked_swift]
            record('official generated Swift general/linked submit and original query, UTC date/digest/source/null over real numeric HTTP')
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
