"""Fresh empty-source manual MEMORY API/PG/Swift loopback; synthetic policy only."""
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
PRIVATE=ROOT/'.local-cj005-memory-pg'
PORT=55448


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--memory-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-memory-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-memory-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private memory directory required')
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
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/collection policy only','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-memory-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.memory_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/memory_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/memory')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
        from cj_memory.domain import Service
        from cj_memory.postgres import Repository
        from cj_memory.manual import ManualPolicy
        from cj_api.memory_boundary import create_memory_composed_app, MemoryBinding, MemoryWireConfiguration
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((PRIVATE/'driver').resolve())
        evidence['driver']={'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg/'initdb','-D',data,'--username=cj005m','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005m',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005m','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            revision=pins['sources'][1]['commit']
            schema=subprocess.check_output(['git','-C',str(args.memory_repository),'show',revision+':backend/memory/schema.sql'])
            (PRIVATE/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_memory_source').fetchone()[0]==0
            c.execute("INSERT INTO cj_memory_scope(scope) VALUES ('fixture-a'),('fixture-b')")
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero source/item/operation rows')
        issuer='https://synthetic.invalid/cj005-memory';audience='cj005-memory-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'invited':True,'fault_operation':None,'fault_stage':None,'ack_next':False}
        approved=set()
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,
                                                     Fact.YES if controls['invited'] else Fact.NO)
        class CommitProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,k):return getattr(self.connection,k)
            def commit(self):
                self.connection.commit()
                if controls['ack_next']:
                    controls['ack_next']=False
                    raise OSError('synthetic ACK lost after real commit')
        # An explicitly scoped synthetic collection policy, not a product default.
        policy=ManualPolicy(frozenset({'self'}),frozenset({'diet.spicy'}),frozenset({'long_term'}),frozenset(),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda c,raw:raw in approved,lambda c,raw:True)
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return MemoryBinding(scopes[p.subject],Service(Repository(CommitProxy,scopes[p.subject]),manual_policy=policy))
        def source_policy(p,scope,kind,c,argument,stage):
            if c is not None and c.operation_id==controls['fault_operation'] and stage==controls['fault_stage']:
                controls['invited']=False
            return p.subject in scopes and scopes[p.subject]==scope
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0)
        os.environ['CJ_ENV']='local'
        app=create_memory_composed_app(environment='local',jwt_configuration=configuration,verification_keys=keys,
            access_provider=Facts(),resolve_binding=resolve,source_policy=source_policy,
            configuration=MemoryWireConfiguration(32768,100,131072))
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,
                algorithm='RS256',headers={'kid':'synthetic-key'})
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
            def raw(oid,iid,kind='inference'):
                return json.dumps(dict(operation_id=oid,item_id=iid,subject='self',slot='diet.spicy',kind=kind,
                    text='Synthetic e\u0301 中文',extent='long_term',context_id=None,occurred_at='date unknown'),ensure_ascii=False,indent=1).encode()
            def post(value):return client.post('/v1/memories',content=value,headers=headers)
            def query(oid):return client.get('/v1/memory-receipts',params={'operation_id':oid},headers=headers)
            first_raw=raw('original +/%&é','first-item','preference');approved.add(first_raw)
            first=post(first_raw);assert first.status_code==200
            first_receipt=first.json()['receipt'];assert first_receipt['status']=='active'
            assert first_receipt['input_sha256']==hashlib.sha256(first_raw).hexdigest()
            assert query('original +/%&é').json()['receipt']==first_receipt
            assert post(first_raw).json()['receipt']==first_receipt
            with connect() as c:
                assert c.execute('SELECT count(*) FROM cj_memory_source').fetchone()[0]==1
                assert bytes(c.execute('SELECT original_input FROM cj_memory_operation').fetchone()[0])==first_raw
            assert post(first_raw+b' ').status_code==409
            record('first HTTP manual save without source seed, original UTF8 persisted, exact replay/no source renewal, byte conflict')
            missing=post(raw('unapproved','unapproved'))
            assert missing.status_code==503
            assert query('unapproved').json()['receipt'] is None
            record('unknown sensitive collection policy rejected without source/item/receipt')
            controls.update(fault_operation='precommit',fault_stage='precommit')
            value=raw('precommit','precommit');approved.add(value)
            failed=post(value);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
            controls.update(invited=True,fault_operation=None,fault_stage=None)
            assert query('precommit').json()['receipt'] is None
            with connect() as c:assert c.execute('SELECT count(*) FROM cj_memory_source').fetchone()[0]==1
            record('fresh AUTH precommit withdrawal rolls back source/item/original receipt together; no guessed success')
            controls.update(fault_operation='postcommit',fault_stage='private_return')
            value=raw('postcommit','postcommit');approved.add(value)
            failed=post(value);assert failed.status_code==503 and 'receipt' not in failed.json()
            controls.update(invited=True,fault_operation=None,fault_stage=None)
            assert query('postcommit').json()['receipt']['item_id']=='postcommit'
            record('postcommit withdrawal withholds private bytes and original action remains queryable')
            value=raw('lost-ack','lost-ack');approved.add(value);controls['ack_next']=True
            failed=post(value);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
            assert query('lost-ack').json()['receipt']['item_id']=='lost-ack'
            record('real COMMIT followed by injected ACK loss; original receipt read, no resend')
            for n,iid in enumerate(['A','a',' leading','trailing ','é','e\u0301','中','😀']):
                value=raw('id-op-'+str(n),iid);approved.add(value);assert post(value).status_code==200
            got=[];after=None
            while True:
                page=client.get('/v1/memories',params={'limit':3,**({'after':after} if after is not None else {})},headers=headers).json()
                got.extend(x['command']['item_id'].encode() for x in page['items'])
                after=page['next_after']
                if after is None:break
            assert got==sorted(set(got)) and len(got)==11
            b_headers={'Authorization':'Bearer '+token_b}
            assert client.get('/v1/memories',params={'limit':1},headers=b_headers).json()['items']==[]
            assert client.get('/v1/memory-receipts',params={'operation_id':'lost-ack'},headers=b_headers).json()['receipt'] is None
            record('live API C-byte keyset/opaque Unicode IDs and independent verified B empty partition')
            swift_raw=raw('swift +/%&é','swift-item','inference');approved.add(swift_raw)
            # Inference is deliberately candidate; live consumer checks the returned state.
            settings={'baseURL':base,'token':token_a,'operationID':'swift +/%&é','itemID':'swift-item',
                      'originalBase64':base64.b64encode(swift_raw).decode(),'expectedItems':12,
                      'expectedInputHash':hashlib.sha256(swift_raw).hexdigest()}
            config=PRIVATE/'swift-config.json';config.touch(mode=0o600);config.write_text(json.dumps(settings))
            command([ROOT/'.local/memory-loopback-client',config],PRIVATE/'swift-client.txt',os.environ.copy())
            record('official generated Swift Client actual memory save/query/list/groups/detail over real HTTP and PG')
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
