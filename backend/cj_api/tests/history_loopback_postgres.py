"""One fresh CJ005 cluster + real HTTP/crypto/MESSAGE/PG integration; no production authority.

No environment DSN, cleanup deletion, other-instance control or automatic POST retry.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / '.local-cj005-history-pg'
SQL_SHA256 = '4060541a06fdd1233b787b212917ecd69728aa272f2e9ce46b34d48d44b1107b'
PG_PORT = 55446  # Unix socket identifier only, never a TCP listener


def command(argv, log, env):
    with log.open('w') as out:
        subprocess.run([str(v) for v in argv],stdout=out,stderr=subprocess.STDOUT,env=env,check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--message-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    args = parser.parse_args()
    if any(k.startswith('PG') or k in ('CJ_DATABASE_URL','DATABASE_URL') for k in os.environ):
        raise RuntimeError('Inherited database configuration forbidden; no values printed')
    if PRIVATE.exists() or PRIVATE.is_symlink():
        raise RuntimeError('Task PG directory already exists; preserve it, never auto-reuse or delete')
    PRIVATE.mkdir(mode=0o700)
    (PRIVATE/'s').mkdir(mode=0o700)
    (PRIVATE/'empty.pgpass').touch(mode=0o600)
    clean_env = {'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg_bin = Path(subprocess.check_output(['pg_config','--bindir'],text=True,env=clean_env).strip())
    data = PRIVATE/'data'
    server = thread = http_socket = None
    evidence = {'scope':'synthetic authority, real loopback HTTP and private Unix-socket PostgreSQL',
                'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'checks':[],'private_directory':str(PRIVATE)}
    def record(name, **facts):
        evidence['checks'].append(dict(name=name,status='PASS',**facts))
        print('PASS '+name,flush=True)
    try:
        command([sys.executable,ROOT/'scripts/prepare-composition-deps.py',
                 '--auth-repository',args.auth_repository,'--message-repository',args.message_repository],
                PRIVATE/'export.txt',os.environ.copy())
        pins = json.loads((ROOT/'backend/cj_api/composition_pins.json').read_text())
        key = '-'.join(s['commit'] for s in pins['sources'])
        exports = ROOT/'.local/composition-deps'/key
        # Explicit approved offline library input; copy package code only, never a cluster/DSN.
        package=args.driver_source/'psycopg'
        metadata=args.driver_source/'psycopg-3.2.10.dist-info'
        if args.driver_source.is_symlink() or not package.is_dir() or not metadata.is_dir():raise RuntimeError('Explicit offline psycopg3.2.10 package required')
        if any(p.is_symlink() for p in [package,metadata,*package.rglob('*'),*metadata.rglob('*')]):
            raise RuntimeError('Offline dependency symlink forbidden')
        dependency_files={}
        for source in (package,metadata):
            for item in sorted(source.rglob('*')):
                if item.is_file() and '__pycache__' not in item.parts and item.suffix!='.pyc':
                    if not item.resolve().is_relative_to(args.driver_source.resolve()):raise RuntimeError('Dependency outside whitelist')
                    dependency_files[str(item.relative_to(args.driver_source))]=hashlib.sha256(item.read_bytes()).hexdigest()
        contents=(metadata/'METADATA').read_text()
        if 'Name: psycopg\n' not in contents or 'Version: 3.2.10\n' not in contents:raise RuntimeError('Wrong offline driver')
        (PRIVATE/'driver').mkdir(mode=0o700)
        for source in (package,metadata):
            shutil.copytree(source,PRIVATE/'driver'/source.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for relative,expected in dependency_files.items():
            if hashlib.sha256((PRIVATE/'driver'/relative).read_bytes()).hexdigest()!=expected:raise RuntimeError('Offline dependency copy mismatch')
        (PRIVATE/'driver-source.json').write_text(json.dumps({'source':str(args.driver_source),'version':'3.2.10','mode':'read-only exact package/dist-info whitelist; no old data/socket/pgpass/config/log','manifest_sha256':hashlib.sha256(json.dumps(dependency_files,sort_keys=True).encode()).hexdigest(),'files':dependency_files},indent=2)+'\n')
        sys.path[:0] = [str(PRIVATE/'driver'),str(ROOT/'backend'),
                       str(exports/'backend/auth'),str(exports/'backend/message')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_api.composition import create_composed_app, CompositionUnavailable
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, JWTProfile, StaticPublicKeys, VerificationKey
        from cj_message.postgres import Repository
        from cj_api.aead_cursor import AeadCursorCodec
        from cj_api.history_config import CursorPolicy, HistoryWireConfiguration
        evidence['pins'] = pins
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).is_relative_to(PRIVATE/'driver')
        evidence['driver'] = {'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg_bin/'initdb','-D',data,'--username=cj005h','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean_env)
        import shlex
        options = shlex.join(['-c','listen_addresses=','-k',str(PRIVATE/'s'),'-p',str(PG_PORT),
                              '-c','unix_socket_permissions=0700'])
        command([pg_bin/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',options,'-w','start'],
                PRIVATE/'pg-start.txt',clean_env)
        def connect():
            return psycopg.connect(host=str(PRIVATE/'s'),port=PG_PORT,user='cj005h',dbname='postgres',
                passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
                options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            row = c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,version()").fetchone()
            assert Path(row[0]).resolve()==data.resolve() and row[1]=='' and row[2]==str(PRIVATE/'s') and row[3]=='cj005h'
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            message_pin = next(s['commit'] for s in pins['sources'] if s['name']=='message')
            sql = subprocess.check_output(['git','-C',str(args.message_repository),'show',message_pin+':backend/message/sql/candidate.sql'])
            assert hashlib.sha256(sql).hexdigest()==SQL_SHA256
            (PRIVATE/'candidate.sql').write_bytes(sql)
            c.execute(sql.decode('utf-8'))
        evidence['postgres'] = {'version':row[4],'listen_addresses':row[1],'socket':row[2],
                                'user':row[3],'candidate_sql_sha256':SQL_SHA256}
        record('first real PG connection and candidate SQL only in verified empty private cluster')
        print('FIRST_CONNECTION '+json.dumps(evidence['postgres']),flush=True)
        issuer,audience='https://synthetic.invalid/cj005-history','cj005-history-synthetic'
        cid,generation='chat +/%&é','generation +/%&é'
        empty_cid,empty_generation='empty-chat','empty-generation'
        scopes={s:'cj005h-'+uuid.uuid4().hex for s in ('subject-a','subject-b')}
        with connect() as c:
            for scope in scopes.values():
                c.execute('INSERT INTO cj_message_scope(scope) VALUES (%s)',(scope,))
                for chat,gen in ((cid,generation),(empty_cid,empty_generation)):
                    c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',(scope,chat,gen))
        lock=threading.Lock()
        class SyntheticFacts:
            calls=0;deny_at=None
            def evaluate(self,p):
                with lock:
                    self.calls+=1;invited=Fact.NO if self.calls==self.deny_at else Fact.YES
                return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,invited)
            def reset(self,deny_at=None):
                with lock:self.calls=0;self.deny_at=deny_at
        policy=SyntheticFacts()
        faults={'ack_next':False,'ack_count':0,'run_count':0,'missing_mutations':0}
        class CommitProxy:
            def __init__(self,c):self.c=c
            def __getattr__(self,name):return getattr(self.c,name)
            def commit(self):
                self.c.commit()
                with lock:
                    inject=faults['ack_next'];faults['ack_next']=False
                    if inject:faults['ack_count']+=1
                if inject:raise OSError('test ACK exception only after actual PG commit')
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('No synthetic binding')
            return Repository(lambda:CommitProxy(connect()),scopes[p.subject])
        def run_id():
            faults['run_count']+=1
            return 'synthetic-run-'+uuid.uuid4().hex
        private_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=private_key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        profile=JWTConfiguration(issuer,audience,'RS256',0,profile=JWTProfile.STRICT_V1)
        clock={'now':100}
        # Only test memory keys, never default/persisted/real keys or external key lookup.
        codec=AeadCursorCodec(keys={'synthetic-cursor-key':os.urandom(32)},active_key_id='synthetic-cursor-key',
            version='synthetic-v1',clock=lambda:clock['now'],max_ttl_seconds=300,
            max_token_bytes=4096,max_plaintext_bytes=1024,max_binding_bytes=4096)
        options=HistoryWireConfiguration(2,512,16384,CursorPolicy(codec,30,4096))
        os.environ['CJ_ENV']='local'
        app=create_composed_app(environment='local',jwt_configuration=profile,verification_keys=keys,
            access_provider=policy,resolve_repository=resolve,new_run_id=run_id,max_body_bytes=4096,
            history_configuration=options)
        class MalformedRequiredField:
            """Only this harness: mutate successful response after actual context/PG read."""
            async def __call__(self,scope,receive,send):
                field=dict(scope.get('headers',[])).get(b'x-cj005-test-omit-field')
                path=scope.get('path')
                selected=(scope['type']=='http' and (path,field) in
                          (('/v1/conversations',b'next_cursor'),('/v1/message-drafts',b'draft')))
                if not selected:return await app(scope,receive,send)
                messages=[]
                async def capture(message):messages.append(message)
                await app(scope,receive,capture)
                start=next(m for m in messages if m['type']=='http.response.start')
                payload=json.loads(b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body'))
                assert start['status']==200 and field.decode() in payload
                del payload[field.decode()];body=json.dumps(payload).encode()
                start['headers']=[(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(body)).encode())]
                faults['missing_mutations']+=1
                await send(start);await send({'type':'http.response.body','body':body})
        http_socket=socket.socket();http_socket.bind(('127.0.0.1',0));http_socket.listen(32)
        port=http_socket.getsockname()[1];assert http_socket.getsockname()[0]=='127.0.0.1'
        server=uvicorn.Server(uvicorn.Config(MalformedRequiredField(),host='127.0.0.1',port=port,
            access_log=False,proxy_headers=False,log_level='warning',lifespan='off'))
        thread=threading.Thread(target=lambda:server.run(sockets=[http_socket]),name='cj005-owned-history-http');thread.start()
        for _ in range(200):
            if server.started:break
            if not thread.is_alive():raise RuntimeError('Owned HTTP failed')
            time.sleep(.025)
        assert server.started
        evidence['http_origin']=f'http://127.0.0.1:{port}'
        print('HTTP_READY '+evidence['http_origin'],flush=True)
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+1200),
                              private_key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        headers={'Authorization':'Bearer '+token_a}
        def raw_message(mid):
            return json.dumps(dict(version='MESSAGE-draft.1',conversation_id=cid,message_id=mid,
                text='synthetic history e\u0301 + 中文',trip_id=None,creation_intent='none'),ensure_ascii=False,indent=1).encode()
        def delivery_counts():
            with connect() as c:
                return tuple(c.execute('SELECT count(*) FROM '+table+' WHERE scope=%s',(scopes['subject-a'],)).fetchone()[0]
                             for table in ('cj_message_receipt','cj_message_delivery'))
        with httpx.Client(base_url=evidence['http_origin'],trust_env=False,timeout=15) as client:
            def get(path,params,h=headers):return client.get(path,params=params,headers=h)
            def save(raw,revision):return client.put('/v1/message-drafts',params=dict(conversation_id=cid,generation=generation,expected_revision=revision),content=raw,headers=dict(headers,**{'Content-Type':'application/octet-stream'}))
            def read_draft():return get('/v1/message-drafts',dict(conversation_id=cid,generation=generation))
            for mid in ('history-one','history-two'):
                assert client.post('/v1/messages',content=raw_message(mid),headers=dict(headers,**{'Content-Type':'application/octet-stream'})).status_code==200
            before_counts=delivery_counts();assert before_counts==(2,2)
            first=get('/v1/conversations',{'limit':1});assert first.status_code==200
            cursor=first.json()['next_cursor'];assert isinstance(cursor,str)
            second=get('/v1/conversations',{'limit':1,'cursor':cursor})
            assert second.status_code==200 and 'next_cursor' in second.json() and second.json()['next_cursor'] is None
            record('real HTTP/PG conversations AEAD pagination and required explicit null')
            middle=len(cursor)//2
            tampered=cursor[:middle]+('A' if cursor[middle]!='A' else 'B')+cursor[middle+1:]
            assert get('/v1/conversations',{'limit':1,'cursor':tampered}).status_code==409
            wrong=get('/v1/conversations',{'limit':1,'cursor':cursor},{'Authorization':'Bearer '+token_b})
            assert wrong.status_code==409 and 'conversations' not in wrong.json()
            clock['now']=130
            assert get('/v1/conversations',{'limit':1,'cursor':cursor}).status_code==409
            clock['now']=100  # independent case reset of explicitly synthetic clock
            record('AEAD tamper wrong current subject/scope and expiry resync without private response')
            history=get('/v1/message-history',dict(conversation_id=cid,limit=1));assert history.status_code==200
            item=history.json()['messages'][0]
            assert base64.b64decode(item['original_utf8_base64'],validate=True)==raw_message('history-one')
            assert item['receipt']['input_sha256']==hashlib.sha256(raw_message('history-one')).hexdigest()
            end=get('/v1/message-history',dict(conversation_id=cid,limit=1,cursor=history.json()['next_cursor']))
            assert end.status_code==200 and end.json()['messages'][0]['receipt']['message_id']=='history-two'
            assert 'next_cursor' in end.json() and end.json()['next_cursor'] is None
            record('real private message history exact original UTF8/hash through authenticated pages')
            absent=read_draft();assert absent.status_code==200 and 'draft' in absent.json() and absent.json()['draft'] is None
            empty=save(b'',0);assert empty.status_code==200 and empty.json()['draft']['revision']==1
            assert empty.json()['draft']['original_utf8_base64']==''
            draft_raw='synthetic draft e\u0301 + 中文\n'.encode()
            assert save(draft_raw,1).json()['draft']['revision']==2
            assert save(b'conflict',1).status_code==409
            assert base64.b64decode(read_draft().json()['draft']['original_utf8_base64'],validate=True)==draft_raw
            assert delivery_counts()==before_counts and faults['run_count']==2
            record('draft required null empty/exact bytes and revision CAS; no message/run/delivery creation')
            unknown_raw='synthetic unknown e\u0301'.encode();faults['ack_next']=True
            unknown=save(unknown_raw,2)
            assert unknown.status_code==503 and unknown.json()['error']['recovery']=='reconcile_original'
            actual=read_draft();assert actual.status_code==200 and actual.json()['draft']['revision']==3
            assert base64.b64decode(actual.json()['draft']['original_utf8_base64'],validate=True)==unknown_raw
            assert faults['ack_count']==1 and delivery_counts()==before_counts
            record('actual PG draft COMMIT then injected ACK exception; read original draft revision, no text-based inference')
            policy.reset(deny_at=3)
            pre=save(b'withdraw before commit',3)
            assert pre.status_code==503 and pre.json()['error']['recovery']=='reconcile_original'
            policy.reset();assert read_draft().json()['draft']['revision']==3
            record('synthetic precommit withdrawal actual PG rollback leaves prior draft; API conservatively unknown')
            policy.reset(deny_at=6)
            withheld=get('/v1/conversations',{'limit':1})
            assert withheld.status_code==503 and 'conversations' not in withheld.json() and 'next_cursor' not in withheld.json()
            policy.reset()
            record('synthetic final callback authority withdrawal after real read/AEAD encoding withholds private output')
        swift_raw='generated Swift exact e\u0301 + 中文\n'.encode()
        control=dict(baseURL=evidence['http_origin'],token=token_a,conversationID=cid,generation=generation,
            emptyConversationID=empty_cid,emptyGeneration=empty_generation,expectedDraftRevision=3,
            expectedDraftBase64=base64.b64encode(unknown_raw).decode(),newDraftBase64=base64.b64encode(swift_raw).decode(),
            firstMessageBase64=base64.b64encode(raw_message('history-one')).decode())
        result=subprocess.run([str(ROOT/'.local/history-loopback-client')],input=json.dumps(control),text=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,env=clean_env)
        (PRIVATE/'generated-client.txt').write_text(result.stdout)
        assert result.returncode==0,'generated Swift check failed; only safe stdout retained'
        assert faults['missing_mutations']==2 and delivery_counts()==before_counts and faults['run_count']==2
        with connect() as c:
            revision,stored=c.execute('SELECT revision,original_utf8 FROM cj_message_draft WHERE scope=%s AND conversation_id=%s AND generation=%s',
                (scopes['subject-a'],cid,generation)).fetchone()
            assert revision==4 and bytes(stored)==swift_raw
        record('actual generated Swift live pages history draft CAS/null and missing-key safety',consumer_groups=4)
        evidence['fault_counts']={k:v for k,v in faults.items() if k!='ack_next'}
        evidence['synthetic_clock']='100 advanced to130 for expiry, reset to100 for independent scenarios; not production clock proof'
    except BaseException as exc:
        evidence['failure_type']=type(exc).__name__
        print('FAIL integration type='+type(exc).__name__,flush=True)
        raise
    finally:
        if server is not None:server.should_exit=True
        if thread is not None:
            thread.join(timeout=20)
            if thread.is_alive():server.force_exit=True;thread.join(timeout=5)
            evidence['http_stopped']=not thread.is_alive()
        if http_socket is not None:http_socket.close()
        if (data/'postmaster.pid').exists():
            command([pg_bin/'pg_ctl','-D',data,'-m','fast','-w','stop'],PRIVATE/'pg-stop.txt',clean_env)
        evidence['pg_stopped']=not (data/'postmaster.pid').exists() and not (PRIVATE/'s'/('.s.PGSQL.'+str(PG_PORT))).exists()
        evidence['data_preserved']=data.exists()
        (PRIVATE/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('STOPPED '+json.dumps({k:evidence.get(k) for k in ('http_stopped','pg_stopped','data_preserved')}),flush=True)
        if evidence.get('http_stopped') is False or not evidence['pg_stopped']:raise RuntimeError('Owned cleanup incomplete')


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        # No trace/error interpolation: transport errors can retain private query token/body.
        print('Runner failed; retained safe evidence; type='+type(exc).__name__,flush=True)
        raise SystemExit(1) from None
