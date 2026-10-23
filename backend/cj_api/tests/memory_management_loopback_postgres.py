"""Fresh private PostgreSQL official Swift/numeric HTTP guarded lifecycle chain; canonical synthetic AUTH only."""
import argparse
import base64
import socket
import threading
import time
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
PORT=55458

def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--management-repository',type=Path,required=True)
    parser.add_argument('--memory-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-mmnet-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-mmnet-[a-z0-9-]+',args.private_name):raise RuntimeError('task-private lifecycle directory required')
    private=ROOT/args.private_name
    if any(k.startswith('PG') or k.startswith('LIBPQ') or k in ('DATABASE_URL','CJ_DATABASE_URL') for k in os.environ):raise RuntimeError('ambient DB configuration refused')
    if private.exists() or private.is_symlink():raise RuntimeError('existing private directory refused')
    assert len(str(private/'s'/('.s.PGSQL.'+str(PORT))).encode())<104
    private.mkdir(mode=0o700);(private/'s').mkdir(mode=0o700);(private/'empty.pgpass').touch(mode=0o600)
    clean={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg=Path(subprocess.check_output(['pg_config','--bindir'],env=clean,text=True).strip())
    data=private/'data';server=thread=http_socket=None
    evidence={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'scope':'new private empty PG + official Swift URLSession/numeric HTTP tests; actual canonical AUTH with synthetic keys/accounts; no real account C2','result':'FAIL','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-memory-management-deps.py'),'--auth-repository',str(args.auth_repository),'--source-repository',str(args.management_repository),'--memory-repository',str(args.memory_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/memory_management_pins.json').read_text());evidence['pins']=pins
        evidence['cohost_memory_pins']=json.loads((ROOT/'backend/cj_api/memory_pins.json').read_text())
        # Reuse only immutable driver code, never old data/config/socket/logs.
        packages=[args.driver_source/'psycopg',args.driver_source/'psycopg-3.2.10.dist-info']
        assert not args.driver_source.is_symlink() and all(p.is_dir() for p in packages)
        files={}
        for package in packages:
            for path in [package,*package.rglob('*')]:
                assert not path.is_symlink() and path.resolve().is_relative_to(args.driver_source.resolve())
                if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':files[str(path.relative_to(args.driver_source))]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert 'Version: 3.2.10\n' in (packages[1]/'METADATA').read_text()
        (private/'driver').mkdir(mode=0o700)
        for package in packages:shutil.copytree(package,private/'driver'/package.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name,digest in files.items():assert hashlib.sha256((private/'driver'/name).read_bytes()).hexdigest()==digest
        evidence['driver']={'version':'3.2.10','file_count':len(files),'manifest_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}
        (private/'driver-manifest.json').write_text(json.dumps(files,indent=2)+'\n')
        sys.path[:0]=[str(private/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/memory'),str(Path(exported)/'backend/memory_management'),str(ROOT/'backend/message'),str(ROOT/'backend/cj_api/tests')]
        import psycopg
        import unittest
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((private/'driver').resolve())
        evidence['driver']['implementation']=psycopg.pq.__impl__
        command([pg/'initdb','-D',data,'--username=cj005mmnet','--auth-local=trust','--auth-host=reject','--encoding=UTF8','--locale=C','--no-clean'],private/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',private/'postgres.log','-o',shlex.join(['-c','listen_addresses=','-k',str(private/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],private/'pg-start.txt',clean)
        config=dict(host=str(private/'s'),port=PORT,user='cj005mmnet',dbname='postgres',passfile=str(private/'empty.pgpass'),connect_timeout=5,options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with psycopg.connect(**config) as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(private/'s'),'cj005mmnet','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            evidence['schemas']={}
            for repo,rev,name in [(args.memory_repository,pins['sources'][1]['commit'],'backend/memory/schema.sql'),(args.management_repository,pins['sources'][2]['commit'],'backend/memory_management/schema.sql')]:
                raw=subprocess.check_output(['git','-C',str(repo),'show',rev+':'+name])
                c.execute(raw.decode());evidence['schemas'][name]=hashlib.sha256(raw).hexdigest()
            assert c.execute('SELECT count(*) FROM cj_memory_management_action').fetchone()[0]==0
        evidence['postgres']={'identity':list(identity),'role_scope':'new fixture bootstrap role only; no production grants/RLS/permissions proof'}
        record('verified new empty private PostgreSQL, no TCP, exact two candidate schemas only')
        import jwt,uvicorn
        from datetime import datetime,timedelta,timezone
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts,Fact
        from cj_auth.jwt_adapter import JWTConfiguration,StaticPublicKeys,VerificationKey
        from cj_memory import domain,postgres
        from cj_memory.manual import ManualPolicy
        from cj_memory_management import guarded
        from cj_api.app import create_app
        from cj_api.memory_boundary import MemoryBinding,MemoryWireConfiguration,build_memory_boundary
        from cj_api.memory_management_boundary import MemoryManagementConfiguration,_candidate_boundary_from_checker
        scopes={'account-a':'network-fixture-a','account-b':'network-fixture-b'}
        item='same item e\u0301/中文';pause_id=' pause e\u0301/中文 ';resume_id=' resume +e\u0301/中文 ';unknown_id=' unknown e\u0301/中文 '
        def action(aid,operation,version):return json.dumps(dict(action_id=aid,operation=operation,item_id=item,expected_version=version,expected_source_version=1),ensure_ascii=False,indent=2).encode()+b'\n'
        actions={pause_id:action(pause_id,'pause',1),resume_id:action(resume_id,'resume',2),unknown_id:action(unknown_id,'pause',3)}
        attempts={};encoded={};received={};faulted=set();connections=[]
        class Cursor:
            def __init__(self,c,owner):self.c,self.owner=c,owner
            def execute(self,sql,args=None):
                self.c.execute(sql,args)
                if sql.lstrip().startswith('INSERT INTO cj_memory_management_action'):self.owner.action_id=args[1]
                return self
            def fetchone(self):return self.c.fetchone()
            def fetchall(self):return self.c.fetchall()
            @property
            def rowcount(self):return self.c.rowcount
            def close(self):self.c.close()
        class Conn:
            def __init__(self):self.c=psycopg.connect(**config);self.action_id=None;connections.append(self)
            @property
            def autocommit(self):return self.c.autocommit
            def cursor(self):return Cursor(self.c.cursor(),self)
            def commit(self):
                self.c.commit()
                if self.action_id==unknown_id and self.action_id not in faulted:
                    faulted.add(self.action_id);raise OSError('PRIVATE_AFTER_REAL_COMMIT_ACK_LOSS')
            def rollback(self):self.c.rollback()
            def close(self):self.c.close()
        repositories={p:postgres.Repository(Conn,scope) for p,scope in scopes.items()}
        old_services={};new_services={}
        for subject,scope in scopes.items():
            with psycopg.connect(**config) as c:c.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s)',(scope,))
            seed=json.dumps(dict(operation_id='fixture-save-'+subject,item_id=item,subject='self',slot='diet',kind='preference',text='explicit synthetic source '+subject,extent='long_term',context_id=None,occurred_at='date unknown'),ensure_ascii=False).encode()
            policy=ManualPolicy(frozenset({'self'}),frozenset({'diet'}),frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,raw,approved=seed:raw==approved,lambda c,raw:True)
            old_services[subject]=domain.Service(repositories[subject],manual_policy=policy)
            # Fixture setup only; every actual action below uses the guarded HTTP route.
            old_services[subject].save_manual(seed)
            new_services[subject]=guarded.GuardedService(repositories[subject])
        issuer='https://synthetic.invalid/cj005-mm-network';audience='cj005-mm-network'
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        jwt_config=JWTConfiguration(issuer,audience,'RS256',0)
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES)
        def token(subject):
            now=int(time.time());return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        old=build_memory_boundary(environment='local',jwt_configuration=jwt_config,verification_keys=keys,access_provider=Facts(),resolve_binding=lambda p:MemoryBinding(scopes[p.subject],old_services[p.subject]),source_policy=lambda *_:True)
        new=_candidate_boundary_from_checker(environment='local',checker=old.checker,resolve_binding=lambda p:MemoryBinding(scopes[p.subject],new_services[p.subject]))
        assert old.checker is new.checker and old.modules['cj_memory.domain'] is new.modules['cj_memory.domain']
        assert guarded.GuardedService.__mro__[1] is domain.Service
        for p in scopes:assert old_services[p].repository is new_services[p].repository
        original=new.invoke
        def invoke(token,kind,argument,project):
            if kind=='save':
                aid=new.modules['cj_memory_management.domain'].Action.parse(argument).action_id
                attempts[aid]=attempts.get(aid,0)+1;received[aid]=argument
            def capture(value):
                raw=project(value);rid=json.loads(raw)['request_id'];encoded[rid]=hashlib.sha256(raw).hexdigest();return raw
            return original(token,kind,argument,capture)
        new.invoke=invoke  # Test-only observation, not a product route/factory change.
        os.environ['CJ_ENV']='local'
        app=create_app(_memory_boundary=old,_memory_configuration=MemoryWireConfiguration(32768,20,65536),_memory_management_boundary=new,_memory_management_configuration=MemoryManagementConfiguration(32768,65536))
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1]);evidence['http']={'binding':'127.0.0.1 only','port':http_socket.getsockname()[1],'access_logs':False}
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        record('single canonical0045/a7 module identity, shared checker/repositories; numeric loopback HTTP server started')
        client_output=private/'swift-result.json';client_output.touch(mode=0o600)
        settings=dict(baseURL=base,tokenA=token('account-a'),tokenB=token('account-b'),pauseBase64=base64.b64encode(actions[pause_id]).decode(),resumeBase64=base64.b64encode(actions[resume_id]).decode(),unknownBase64=base64.b64encode(actions[unknown_id]).decode(),pauseID=pause_id,resumeID=resume_id,unknownID=unknown_id,outputPath=str(client_output))
        path=private/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
        command([ROOT/'.local/memory-management-loopback-client',path],private/'swift-client.txt',os.environ.copy())
        observations=json.loads(client_output.read_text());assert len(observations)==8
        assert len({o['requestID'] for o in observations})==8
        positive=[o for o in observations if o['status']==200];assert len(positive)==7
        for observation in positive:assert encoded[observation['requestID']]==observation['sha256']
        assert sorted(o['status'] for o in observations)==[200]*7+[503]
        record('official generated Swift URLSession performed eight actual HTTP/PG calls; pause/read/resume/historical receipt and unknown original query passed')
        record('all seven HTTP200 response bodies equal exact whole BASE bytes projected in original protected lifetime, SHA matched in real Swift transport')
        assert attempts=={pause_id:1,resume_id:1,unknown_id:1} and received==actions and faulted=={unknown_id}
        with psycopg.connect(**config) as c:
            rows=c.execute('SELECT scope,action_id,original_input,version,status FROM cj_memory_management_action ORDER BY action_id').fetchall()
            assert len(rows)==3
            for scope,aid,raw,version,status in rows:
                assert scope==scopes['account-a'] and bytes(raw)==actions[aid]
                assert (version,status)==({pause_id:(2,'disabled'),resume_id:(3,'active'),unknown_id:(4,'disabled')}[aid])
            states=c.execute('SELECT scope,version,status FROM cj_memory_item ORDER BY scope').fetchall()
            assert states==[(scopes['account-a'],4,'disabled'),(scopes['account-b'],1,'active')]
            assert c.execute('SELECT count(*) FROM cj_memory_management_action WHERE scope=%s',(scopes['account-b'],)).fetchone()[0]==0
        assert all(c.c.closed for c in connections)
        evidence['network_assertions']={'requests':8,'http200_exact_base':7,'http503_after_real_commit':1,'apply_attempts':3,'no_action_resend':True,'original_bytes_exact':True,'persisted_historical_versions':[2,3,4],'foreign_receipt_null':True,'foreign_item_unchanged':True}
        record('three exact original action UTF8/IDs persisted once; committed-unknown queried under original ID only, no resend or new ID')
        record('synthetic authenticated B original receipt lookup is explicit null; B item/version and lifecycle ledger unchanged in real PG')
        for name,digest in files.items():
            assert hashlib.sha256((private/'driver'/name).read_bytes()).hexdigest()==digest
            assert hashlib.sha256((args.driver_source/name).read_bytes()).hexdigest()==digest
        evidence['result']='PASS'
    finally:
        if server:server.should_exit=True
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():server.force_exit=True;thread.join(timeout=5)
            assert not thread.is_alive()
        if http_socket:http_socket.close()
        if (data/'postmaster.pid').exists():command([pg/'pg_ctl','-D',data,'-m','fast','-w','stop'],private/'pg-stop.txt',clean)
        assert not (data/'postmaster.pid').exists() and not (private/'s'/('.s.PGSQL.'+str(PORT))).exists()
        evidence['safe_stop']='PASS'
        (private/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('PASS HTTP thread joined and exact new private PostgreSQL stopped; data retained',flush=True)

if __name__=='__main__':main()
