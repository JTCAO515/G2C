"""Fresh private PostgreSQL + actual loopback HTTP; canonical synthetic AUTH only."""
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[3]
PORT=55455

def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--cleanup-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-cleanup-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-cleanup-[a-z0-9-]+',args.private_name):raise RuntimeError('task-private cleanup directory required')
    private=ROOT/args.private_name
    if any(k.startswith('PG') or k.startswith('LIBPQ') or k in ('DATABASE_URL','CJ_DATABASE_URL') for k in os.environ):raise RuntimeError('ambient DB configuration refused')
    if private.exists() or private.is_symlink():raise RuntimeError('existing private directory refused')
    assert len(str(private/'s'/('.s.PGSQL.'+str(PORT))).encode())<104
    private.mkdir(mode=0o700);(private/'s').mkdir(mode=0o700);(private/'empty.pgpass').touch(mode=0o600)
    clean={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg=Path(subprocess.check_output(['pg_config','--bindir'],env=clean,text=True).strip())
    data=private/'data';server=thread=http_socket=None
    evidence={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'scope':'new private empty PG + loopback HTTP; actual canonical AUTH with synthetic keys/accounts; no C2 real account','result':'FAIL','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-cleanup-progress-deps.py'),'--auth-repository',str(args.auth_repository),'--source-repository',str(args.cleanup_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/cleanup_progress_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(private/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/cleanup')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from unittest.mock import patch
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts,Fact
        from cj_auth.jwt_adapter import JWTConfiguration,PyJWTVerifier,StaticPublicKeys,VerificationKey
        from cj_cleanup import core
        from cj_cleanup.postgres import Repository,state_bytes
        from cj_api.cleanup_progress_composition import CleanupProgressConfiguration,create_cleanup_progress_app
        from cj_api import cleanup_progress_routes
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((private/'driver').resolve())
        evidence['driver']['implementation']=psycopg.pq.__impl__
        command([pg/'initdb','-D',data,'--username=cj005c_admin','--auth-local=trust','--auth-host=reject','--encoding=UTF8','--locale=C','--no-clean'],private/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',private/'postgres.log','-o',shlex.join(['-c','listen_addresses=','-k',str(private/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],private/'pg-start.txt',clean)
        def connect(user='cj005c_admin'):
            return psycopg.connect(host=str(private/'s'),port=PORT,user=user,dbname='postgres',passfile=str(private/'empty.pgpass'),connect_timeout=5,options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(private/'s'),'cj005c_admin','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            schema=subprocess.check_output(['git','-C',str(args.cleanup_repository),'show',pins['sources'][1]['commit']+':backend/cleanup/sql/candidate.sql'])
            (private/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_cleanup_journal_candidate').fetchone()[0]==0
            c.execute('CREATE ROLE cj005c_read LOGIN NOSUPERUSER NOBYPASSRLS')
            c.execute('GRANT SELECT ON public.cj_cleanup_journal_candidate TO cj005c_read')
        with connect('cj005c_read') as c:
            assert c.execute("SELECT rolsuper,rolbypassrls,has_table_privilege(current_user,'public.cj_cleanup_journal_candidate','SELECT'),has_table_privilege(current_user,'public.cj_cleanup_journal_candidate','INSERT'),has_table_privilege(current_user,'public.cj_cleanup_journal_candidate','UPDATE'),has_table_privilege(current_user,'public.cj_cleanup_journal_candidate','DELETE') FROM pg_roles WHERE rolname=current_user").fetchone()==(False,False,True,False,False,False)
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest(),'runtime_role':'cj005c_read','runtime_capability':'SELECT only; no new RLS policy; canonical scope WHERE is tested, not production RLS authority'}
        record('fresh private PG exact identity/empty schema; SELECT-only nonsuperuser runtime; no RLS or product authority added')
        issuer='https://synthetic.invalid/cj005-cleanup';audience='cj005-cleanup-synthetic'
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        config=JWTConfiguration(issuer,audience,'RS256',0)
        def token(subject,shift=0):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-2+shift,nbf=now-2+shift,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        subjects=['account-a','account-b','account-c','account-d','account-missing']
        tokens={s:token(s) for s in subjects}
        principals={s:PyJWTVerifier(config,keys).verify(t).principal for s,t in tokens.items()}
        original_id='original/operation'
        fixtures={}
        def seed(subject,state,environment='local'):
            scope=core.Scope.from_principal(environment,principals[subject]);memory=core.Repository()
            available=state!='blocked'
            manifest=core.Manifest('synthetic-v1',core.digest(b'fixture manifest'),(core.Entry('metadata',core.digest(b'fixture metadata'),available),),())
            caps=tuple(core.BARRIERS)+('store:metadata',) if available else ()
            op=memory.create(core.request(scope,original_id,core.digest(b'PRIVATE_EXPLICIT_CONFIRMATION'),manifest,caps))
            targets=[s.target for s in op.steps] if state=='complete' else ['auth_revocation'] if state in ('unknown','in_progress') else []
            for target in targets:
                op=memory.intent(scope,original_id,op.revision,target,'PRIVATE_ORIGINAL_CALL-'+str(op.revision))
                if state!='in_progress':
                    step=next(s for s in op.steps if s.target==target)
                    raw=core.encode(dict(protocol=core.VERSION,scope_digest=core.digest(core.encode(asdict(scope))),operation_id=original_id,target=target,version=step.version,invocation=step.invocation,outcome='unknown' if state=='unknown' else 'confirmed'))
                    op=memory.receipt(scope,original_id,op.revision,target,raw)
            with connect() as c:c.execute('INSERT INTO cj_cleanup_journal_candidate VALUES (%s,%s,%s,%s,%s)',(core.encode(asdict(scope)),op.operation_id,op.revision,memory.journal(),state_bytes(op)))
            fixtures[(subject,environment)]=op
        seed('account-a','unknown');seed('account-b','blocked');seed('account-c','in_progress');seed('account-d','complete');seed('account-a','complete','other-local-fixture')
        def inventory():
            with connect() as c:return c.execute('SELECT scope_bytes,operation_id,revision,journal_bytes,state_bytes FROM cj_cleanup_journal_candidate ORDER BY scope_bytes').fetchall()
        before=inventory();statements=[];resolved=[]
        controls={'invited':Fact.YES,'calls':0,'close_mode':None,'final_mode':None,'target':None,'wrong_scope':False}
        class CursorProxy:
            def __init__(self,c):self.c=c
            def execute(self,sql,args=None):statements.append(sql);self.c.execute(sql,args)
            def fetchone(self):return self.c.fetchone()
        class ConnProxy:
            def __init__(self):self.c=connect('cj005c_read')
            @property
            def autocommit(self):return self.c.autocommit
            @property
            def closed(self):return self.c.closed
            @property
            def info(self):return self.c.info
            def cursor(self):return CursorProxy(self.c.cursor())
            def commit(self):self.c.commit()
            def rollback(self):self.c.rollback()
            def close(self):
                self.c.close()
                if controls['close_mode']=='revoke':controls['invited']=Fact.NO
                if controls['close_mode']=='fail':raise OSError('PRIVATE_CLOSE_FAILURE')
                if controls['final_mode']:controls['target']=controls['calls']+4
        latest_repo=[None]
        class Facts:
            def evaluate(self,p):
                controls['calls']+=1
                if controls['target']==controls['calls'] and controls['final_mode']=='binding':latest_repo[0].connect=lambda:ConnProxy()
                return CJAccessFacts(p,Fact.YES if p.subject in subjects else Fact.NO,Fact.YES,controls['invited'])
        def resolve(p,environment,guard):
            resolved.append((p.subject,environment))
            scope=core.Scope.from_principal('other-local-fixture' if controls['wrong_scope'] else environment,p)
            repo=Repository(lambda:ConnProxy(),scope,guard);latest_repo[0]=repo;return repo
        os.environ['CJ_ENV']='local'
        app=create_cleanup_progress_app(configuration=CleanupProgressConfiguration(128,65536),environment='local',jwt_configuration=config,verification_keys=keys,access_provider=Facts(),resolve=resolve)
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            def get(subject='account-a',oid=original_id,bearer=None,extra=None):
                return client.get('/v1/account-cleanup-progress',params=dict(operation_id=oid,**(extra or {})),headers={'Authorization':'Bearer '+(bearer or tokens[subject])})
            responses={}
            for subject,status,step in [('account-a','unknown','unknown'),('account-b','blocked','pending'),('account-c','awaiting_revocation','in_progress'),('account-d','complete','confirmed')]:
                response=get(subject);assert response.status_code==200,(subject,response.status_code)
                body=response.json();progress=body['progress'];responses[subject]=progress
                assert set(body)=={'request_id','progress'} and set(progress)=={'operation_id','revision','status','steps','reasons'}
                assert progress['status']==status and progress['steps'][0]['state']==step and progress['revision']==fixtures[(subject,'local')].revision
                assert all(set(s)=={'target','state','reason'} for s in progress['steps'])
                assert body['request_id']==response.headers['X-Request-ID'] and response.headers['Cache-Control']=='no-store'
                assert 'PRIVATE_' not in response.text and 'scope' not in progress and subject not in response.text
            assert 'hook_unavailable' in responses['account-b']['reasons']
            assert get('account-missing').status_code==503 and get(oid='missing-original').status_code==503
            assert get(bearer=token('account-a',1)).json()['progress']==responses['account-a']
            record('real HTTP/PG exact original unknown, blocked missing-hook, in-flight revision, finite complete and missing original unavailable; refreshed JWT stable partition')
            assert responses['account-a']['status']!='complete' and responses['account-b']['status']!='complete'
            controls['wrong_scope']=True;response=get();assert response.status_code==503 and 'progress' not in response.json();controls['wrong_scope']=False
            assert get(extra={'environment':'other-local-fixture'}).status_code==400
            assert get(extra={'owner':'account-d'}).status_code==400
            assert all(environment=='local' for _,environment in resolved)
            # Same operation ID exists separately for each account and environment.
            assert fixtures[('account-a','other-local-fixture')].status=='complete' and get().json()['progress']['status']=='unknown'
            for fact,status in [(Fact.NO,403),(Fact.UNKNOWN,503)]:
                controls['invited']=fact;count=len(resolved);response=get();assert response.status_code==status and 'progress' not in response.json() and len(resolved)==count
            controls['invited']=Fact.YES
            record('account/environment scope isolation in actual PG; caller owner/env forbidden; current denied/unknown never resolve storage')
            captured=[];project=cleanup_progress_routes.encode_response
            def capture(*args):
                raw=project(*args);captured.append(raw);return raw
            with patch.object(cleanup_progress_routes,'encode_response',side_effect=capture):response=get()
            assert response.status_code==200 and response.content==captured[-1]
            record('actual HTTP returns exact full BASE bytes encoded inside native protected lifetime')
            for mode,status in [('revoke',503),('fail',503)]:
                controls['close_mode']=mode;response=get();assert response.status_code==status and 'progress' not in response.json() and 'PRIVATE_' not in response.text
                controls.update(close_mode=None,invited=Fact.YES)
            record('real PG connection-close revocation/failure withholds all already-read original progress')
            verify=PyJWTVerifier.verify
            def transition(verifier,raw):
                selected=tokens['account-b'] if controls['final_mode']=='identity' and controls['target']==controls['calls']+1 else raw
                return verify(verifier,selected)
            for mode in ['identity','binding']:
                controls.update(final_mode=mode,target=None)
                with patch.object(PyJWTVerifier,'verify',new=transition):response=get()
                assert controls['calls']==controls['target']
                assert response.status_code==503 and 'progress' not in response.json()
                controls.update(final_mode=None,target=None)
            record('after real PG close, final outer canonical AUTH changed verified identity or same-principal binding swap withholds all bytes')
            settings={'baseURL':base,'token':tokens['account-a'],'operationID':original_id}
            path=private/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            command([ROOT/'.local/cleanup-progress-loopback-client',path],private/'swift-client.txt',os.environ.copy())
            record('official generated Swift GET over real loopback HTTP/PG preserves original unknown, request ID and pending hook barriers')
            assert all(sql.startswith(('SET ','SELECT ')) and 'FOR UPDATE' not in sql for sql in statements)
            assert inventory()==before
            evidence['sql']={'statements':len(statements),'allowed':'SET/SELECT only, no FOR UPDATE','all_rows_bytes_revisions_unchanged':True}
            evidence['fixtures']={'rows':len(before),'accounts':4,'environments':2,'source':'canonical metadata-only request/intent/receipt journal; no hook calls'}
            record('all original journal/state/scope bytes and revisions unchanged; runtime SELECT-only SQL, no recover, write or hook')
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
        print('PASS HTTP thread and exact new private PostgreSQL stopped; data retained',flush=True)

if __name__=='__main__':main()
