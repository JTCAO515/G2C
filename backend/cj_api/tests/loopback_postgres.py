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
PRIVATE = ROOT / '.local-cj005-pg'
SQL_SHA256 = '44707ea75b7c48ebe8c6f7e51a29099a34bf66ea7ac79d0808de451ee5dd3790'
PG_PORT = 55445  # Unix socket identifier only, never a TCP listener


def command(argv, log, env):
    with log.open('w') as out:
        subprocess.run([str(v) for v in argv],stdout=out,stderr=subprocess.STDOUT,env=env,check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--message-repository',type=Path,required=True)
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
        install_env = dict(clean_env,UV_CACHE_DIR=str(PRIVATE/'uv-cache'))
        command([shutil.which('uv'),'pip','install','--python',sys.executable,'--target',PRIVATE/'driver',
                 '--no-deps','-r',ROOT/'backend/cj_api/tests/loopback_pg_requirements.lock'],PRIVATE/'driver-install.txt',install_env)
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
        evidence['pins'] = pins
        evidence['driver'] = {'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg_bin/'initdb','-D',data,'--username=cj005','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean_env)
        import shlex
        options = shlex.join(['-c','listen_addresses=','-k',str(PRIVATE/'s'),'-p',str(PG_PORT),
                              '-c','unix_socket_permissions=0700'])
        command([pg_bin/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',options,'-w','start'],
                PRIVATE/'pg-start.txt',clean_env)
        def connect():
            return psycopg.connect(host=str(PRIVATE/'s'),port=PG_PORT,user='cj005',dbname='postgres',
                passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
                options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            row = c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,version()").fetchone()
            assert Path(row[0]).resolve()==data.resolve() and row[1]=='' and row[2]==str(PRIVATE/'s') and row[3]=='cj005'
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
        issuer, audience = 'https://synthetic.invalid/cj005','cj005-local-integration'
        scopes = {subject:'cj005-'+uuid.uuid4().hex for subject in ('subject-a','subject-b')}
        with connect() as c:
            for subject,scope in scopes.items():
                c.execute('INSERT INTO cj_message_scope VALUES (%s)',(scope,))
                c.execute('INSERT INTO cj_message_chat(scope,conversation_id,generation,epoch) VALUES (%s,%s,%s,0)',
                          (scope,'chat','generation-'+subject))
        lock = threading.Lock()
        class SyntheticPolicy:
            calls = 0
            deny_at = None
            invited = Fact.YES
            def evaluate(self,p):
                with lock:
                    self.calls += 1
                    invited = Fact.NO if self.calls==self.deny_at else self.invited
                return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,invited)
            def reset(self, *, invited=Fact.YES,deny_at=None):
                with lock:
                    self.calls,self.invited,self.deny_at = 0,invited,deny_at
        policy = SyntheticPolicy()
        faults = {'ack_next':False,'ack_injected':0,'commits':0,'runs':0,'malformed_responses':0}
        class CommitProxy:
            def __init__(self,c): self.c=c
            def __getattr__(self,name): return getattr(self.c,name)
            def commit(self):
                self.c.commit()  # actual PG commit precedes the explicit lost-ACK fault
                with lock:
                    faults['commits']+=1
                    inject=faults['ack_next'];faults['ack_next']=False
                    if inject:faults['ack_injected']+=1
                if inject:raise OSError('test-only ACK loss after actual commit')
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:
                raise RuntimeError('No synthetic scope binding')
            return Repository(lambda:CommitProxy(connect()),scopes[p.subject])
        def new_run():
            with lock:faults['runs']+=1
            return 'test-run-'+uuid.uuid4().hex
        private_key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public = private_key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys = StaticPublicKeys({'test-key':VerificationKey('RS256',public)})
        config = JWTConfiguration(issuer,audience,'RS256',0,profile=JWTProfile.STRICT_V1)
        kwargs=dict(environment='local',jwt_configuration=config,verification_keys=keys,
                    access_provider=policy,resolve_repository=resolve,new_run_id=new_run,max_body_bytes=4096)
        try:create_composed_app(**dict(kwargs,verification_keys=None))
        except CompositionUnavailable:record('missing configuration refuses API composition before HTTP bind')
        else:raise AssertionError('missing configuration allowed')
        os.environ['CJ_ENV']='local'
        app=create_composed_app(**kwargs)
        class TestMalformedQuery:
            """Test-only response mutation AFTER actual API/gate/PG query, never production source."""
            async def __call__(self,scope,receive,send):
                mutate=(scope['type']=='http' and scope.get('path')=='/v1/message-receipts' and
                        (b'x-cj005-test-omit-receipt',b'1') in scope.get('headers',[]))
                if not mutate:return await app(scope,receive,send)
                messages=[]
                async def capture(message):messages.append(message)
                await app(scope,receive,capture)
                start=next(m for m in messages if m['type']=='http.response.start')
                body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
                assert start['status']==200
                obj=json.loads(body);assert obj['receipt'] is not None
                del obj['receipt'];body=json.dumps(obj).encode()
                start['headers']=[(k,v) for k,v in start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(body)).encode())]
                faults['malformed_responses']+=1
                await send(start);await send({'type':'http.response.body','body':body})
        http_socket=socket.socket();http_socket.bind(('127.0.0.1',0));http_socket.listen(32)
        assert http_socket.getsockname()[0]=='127.0.0.1'
        port=http_socket.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(TestMalformedQuery(),host='127.0.0.1',port=port,
            access_log=False,log_level='warning',lifespan='off',proxy_headers=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[http_socket]),name='cj005-owned-http')
        thread.start()
        for _ in range(200):
            if server.started:break
            if not thread.is_alive():raise RuntimeError('HTTP failed to start')
            time.sleep(.025)
        assert server.started
        evidence['http_origin']=f'http://127.0.0.1:{port}'
        print('HTTP_READY '+evidence['http_origin'],flush=True)
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+1200,invited=True),
                              private_key,algorithm='RS256',headers={'kid':'test-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        headers={'Authorization':'Bearer '+token_a,'Content-Type':'application/octet-stream'}
        def raw(mid):
            return json.dumps(dict(version='MESSAGE-draft.1',conversation_id='chat',message_id=mid,
                text='synthetic e\u0301 + 中文',trip_id=None,creation_intent='none'),ensure_ascii=False,indent=1).encode()
        def counts(mid):
            with connect() as c:
                return tuple(c.execute('SELECT count(*) FROM '+table+' WHERE scope=%s AND message_id=%s',
                    (scopes['subject-a'],mid)).fetchone()[0] for table in ('cj_message_receipt','cj_message_delivery'))
        with httpx.Client(base_url=evidence['http_origin'],trust_env=False,timeout=15) as client:
            def post(mid,body=None,custom_headers=None):
                return client.post('/v1/messages',content=raw(mid) if body is None else body,
                                   headers=headers if custom_headers is None else custom_headers)
            def query(mid,h=headers):return client.get('/v1/message-receipts',params={'message_id':mid},headers=h)
            original=raw('original')
            first=post('original',original);second=post('original',original)
            assert first.status_code==second.status_code==200
            receipt=first.json()['receipt'];assert second.json()['receipt']==receipt
            assert first.headers['x-request-id']==first.json()['request_id']
            assert post('original',original+b' ').status_code==409
            with connect() as c:
                saved=bytes(c.execute('SELECT raw_input FROM cj_message_receipt WHERE scope=%s AND message_id=%s',
                                     (scopes['subject-a'],'original')).fetchone()[0])
            assert saved==original and receipt['input_sha256']==hashlib.sha256(original).hexdigest() and counts('original')==(1,1)
            record('real HTTP exact bytes duplicate returns original; altered bytes conflict; one receipt/delivery',bytes=len(original))
            assert query('original').json()['receipt']==receipt
            assert query('original',dict(headers,Authorization='Bearer '+token_b)).json()['receipt'] is None
            record('server-owned synthetic subject scopes keep receipt queries separate; not production RLS proof')
            faults['ack_next']=True
            unknown=post('commit-unknown')
            assert unknown.status_code==503 and unknown.json()['error']['outcome']=='unknown'
            assert unknown.json()['error']['recovery']=='reconcile_original' and counts('commit-unknown')==(1,1)
            recovered=query('commit-unknown');assert recovered.status_code==200 and recovered.json()['receipt'] is not None
            assert faults['ack_injected']==1
            record('actual PG COMMIT then injected ACK failure returns unknown; independent HTTP query recovers original')
            policy.reset(deny_at=3)
            before=post('precommit-withdraw')
            assert before.status_code==503 and before.json()['error']['recovery']=='reconcile_original'
            assert counts('precommit-withdraw')==(0,0)
            policy.reset();assert query('precommit-withdraw').json()['receipt'] is None
            record('synthetic precommit withdrawal actual PG rollback; conservative API unknown remains, null not resend permission')
            policy.reset(deny_at=4)
            after=post('return-withdraw')
            assert after.status_code==503 and after.json()['error']['recovery']=='reconcile_original'
            assert counts('return-withdraw')==(1,1)
            policy.reset();assert query('return-withdraw').json()['receipt'] is not None
            record('synthetic postcommit withdrawal preserves actual committed receipt and original query')
            policy.reset(invited=Fact.NO);assert post('uninvited').status_code==403 and counts('uninvited')==(0,0)
            policy.reset(invited=Fact.UNKNOWN);r=post('policy-unknown')
            assert r.status_code==503 and r.json()['error']['recovery']=='retry_safe_read'
            policy.reset()
            assert post('invalid-token',custom_headers=dict(headers,Authorization='Bearer malformed')).status_code==401
            assert post('wrong-media',custom_headers=dict(headers,**{'Content-Type':'application/json'})).status_code==415
            assert post('too-large',b'x'*4097).status_code==413
            assert post('bad-json',b'{').status_code==400
            record('real HTTP API separates 400/401/403/409/413/415/503 without fake identity or acceptance')
        # Actual generated Swift uses the same live server and PG, via stdin-only synthetic token/bytes.
        mid='swift +/%&é'
        swift_raw=raw(mid)
        control=json.dumps(dict(baseURL=evidence['http_origin'],token=token_a,rawBase64=base64.b64encode(swift_raw).decode(),
                                messageID=mid,expectedSHA256=hashlib.sha256(swift_raw).hexdigest()))
        result=subprocess.run([str(ROOT/'.local/loopback-generated-client')],input=control,text=True,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40)
        (PRIVATE/'generated-client.txt').write_text(result.stdout)
        # Never persist stderr: ClientError descriptions can retain operation input/token/body.
        assert result.returncode==0,'generated Swift check failed; safe stdout retained'
        assert counts(mid)==(1,1) and faults['malformed_responses']==1
        record('actual generated Swift HTTP receive/repeat/object/null/missing-after-real-query checks',checks=4)
        evidence['fault_counts']={k:v for k,v in faults.items() if k!='ack_next'}
    except BaseException as exc:
        evidence['failure_type']=type(exc).__name__  # do not serialize possible token/DSN/error body
        print('FAIL integration; type='+type(exc).__name__,flush=True)
        raise
    finally:
        if server is not None:server.should_exit=True
        if thread is not None:
            thread.join(timeout=20)
            evidence['http_stopped']=not thread.is_alive()
            if thread.is_alive():
                server.force_exit=True
                thread.join(timeout=5)
                evidence['http_stopped']=not thread.is_alive()
        if http_socket is not None:http_socket.close()
        if (data/'postmaster.pid').exists():
            command([pg_bin/'pg_ctl','-D',data,'-m','fast','-w','stop'],PRIVATE/'pg-stop.txt',clean_env)
        evidence['pg_stopped']=not (data/'postmaster.pid').exists() and not (PRIVATE/'s'/('.s.PGSQL.'+str(PG_PORT))).exists()
        evidence['data_preserved']=data.exists()
        (PRIVATE/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('STOPPED '+json.dumps({k:evidence.get(k) for k in ('http_stopped','pg_stopped','data_preserved')}),flush=True)
        if evidence.get('http_stopped') is False or not evidence['pg_stopped']:
            raise RuntimeError('Owned task cleanup incomplete; inspect retained evidence')


if __name__=='__main__':
    main()
