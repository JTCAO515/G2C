"""Fresh private NEEDS API/PG/Swift loopback; manual user-provided synthetic needs only."""
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
PRIVATE=ROOT/'.local-cj005-needs-pg'
PORT=55450


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--needs-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-needs-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-needs-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private needs directory required')
    PRIVATE=ROOT/args.private_name
    if any(k.startswith('PG') or k in ('DATABASE_URL','CJ_DATABASE_URL') for k in os.environ):
        raise RuntimeError('Inherited database configuration refused')
    if PRIVATE.exists() or PRIVATE.is_symlink():raise RuntimeError('Existing private directory refused')
    PRIVATE.mkdir(mode=0o700);(PRIVATE/'s').mkdir(mode=0o700)
    (PRIVATE/'empty.pgpass').touch(mode=0o600)
    clean={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','LANG':'C','LC_ALL':'C'}
    pg=Path(subprocess.check_output(['pg_config','--bindir'],env=clean,text=True).sneeds())
    assert len(str(PRIVATE/'s'/('.s.PGSQL.'+str(PORT))).encode())<104
    data=PRIVATE/'data';server=thread=http_socket=None
    evidence={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).sneeds(),
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/manual input only','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-needs-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.needs_repository)],cwd=ROOT,text=True).sneeds()
        pins=json.loads((ROOT/'backend/cj_api/needs_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/needs')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
        from cj_needs.domain import Command
        from cj_api.needs_composition import create_needs_composed_app,NeedsWireConfiguration
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((PRIVATE/'driver').resolve())
        evidence['driver']={'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg/'initdb','-D',data,'--username=cj005n','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005n',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005n','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            revision=pins['sources'][1]['commit']
            schema=subprocess.check_output(['git','-C',str(args.needs_repository),'show',revision+':backend/needs/sql/candidate.sql'])
            (PRIVATE/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_needs_record').fetchone()[0]==0
            c.execute("INSERT INTO cj_needs_scope(scope) VALUES ('fixture-a'),('fixture-b')")
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero formal Needs records')
        from unittest.mock import patch
        from concurrent.futures import ThreadPoolExecutor
        import asyncio
        issuer='https://synthetic.invalid/cj005-needs';audience='cj005-needs-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'calls':0,'deny_at':None,'invited':True,'ack':None}
        class Facts:
            def evaluate(self,p):
                controls['calls']+=1
                allowed=controls['invited'] and controls['calls']!=controls['deny_at']
                return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES if allowed else Fact.NO)
        class CommitProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,k):return getattr(self.connection,k)
            def commit(self):
                self.connection.commit();fault=controls['ack'];controls['ack']=None
                if fault=='lost':raise OSError('synthetic lost ACK after real COMMIT')
                if fault=='cancel':raise asyncio.CancelledError()
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return CommitProxy,scopes[p.subject]
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0)
        os.environ['CJ_ENV']='local'
        app=create_needs_composed_app(environment='local',jwt_configuration=configuration,verification_keys=keys,
            access_provider=Facts(),resolve=resolve,configuration=NeedsWireConfiguration(131072,524288))
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        def raw(aid,nid,version,changes):
            return json.dumps(dict(action_id=aid,needs_id=nid,expected_version=version,
                source={'kind':'manual','text':'Synthetic e\u0301 中文 explicit current needs'},changes=changes),ensure_ascii=False,indent=1).encode()
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            headers={'Authorization':'Bearer '+token_a,'Content-Type':'application/octet-stream'}
            def get(path,**q):return client.get(path,params=q,headers=headers)
            def post(value):return client.post('/v1/needs-actions',content=value,headers=headers)
            def query(aid):return get('/v1/needs-action-receipts',action_id=aid)
            first_raw=raw('a1','n1',0,{'party_size':{'state':'known','value':3}})
            first=post(first_raw);assert first.status_code==200
            receipt=first.json()['receipt'];assert receipt['version']==1 and receipt['operation']=='manual_patch'
            assert post(first_raw).json()['receipt']==receipt
            assert post(first_raw+b' ').status_code==409
            revision=get('/v1/needs-revisions',needs_id='n1',version=1).json()['revision']
            assert base64.b64decode(revision['original_input_utf8_base64'])==first_raw
            assert revision['fields']=={'party_size':{'state':'known','value':3}}
            assert get('/v1/needs',needs_id='n1').json()['needs']['fields']==revision['fields']
            record('manual partial needs save without invented budget, exact-byte replay/conflict and immutable original revision')
            correction=raw('a2','n1',1,{'pace':{'state':'uncertain','note':'Undecided / 未定'}})
            assert post(correction).json()['receipt']['version']==2
            assert query('a1').json()['receipt']==receipt
            latest=get('/v1/needs',needs_id='n1').json()['needs'];assert latest['version']==2
            assert latest['fields']['party_size']['value']==3 and 'budget_total' not in latest['fields']
            assert get('/v1/needs-revisions',needs_id='n1',version=1).json()['revision']==revision
            race=[raw('race-'+str(i),'n1',2,{'party_size':{'state':'known','value':4+i}}) for i in range(2)]
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(post,race))
            assert sorted(r.status_code for r in results)==[200,409]
            assert get('/v1/needs',needs_id='n1').json()['needs']['version']==3
            record('CAS correction preserves prior fields/revisions; two concurrent same-version HTTP actions yield one winner')
            unknown={'state':'unknown'}
            event={'date':{'state':'known','value':'2026-11-01'},'time':{'state':'known','value':'01:30'},'timezone':{'state':'known','value':'America/New_York'},'place':unknown}
            rich={'arrival':event,'budget_total':{'state':'known','value':'1000.00'},'budget_paid':{'state':'missing'},
                'budget_per_person':unknown,'pace':{'state':'uncertain','note':'Undecided / 未定'},'companions':{'mother':'Synthetic companion'},
                'fixed_items':[{'item_id':'i1','kind':'hotel','description':'User reports booking','applies_to':['companion:mother'],
                    'locked':{'state':'known','value':True},'booking_status':{'state':'known','value':'booked'},'start':event,'end':{k:unknown for k in event}}]}
            rich_raw=raw('rich','n-rich',0,rich);assert post(rich_raw).status_code==200
            snapshot=get('/v1/needs',needs_id='n-rich').json()['needs'];assert snapshot['fields']==rich and snapshot['source_kind']=='user_provided'
            invalid=raw('invalid-remove','n-rich',1,{'companions':{}})
            assert post(invalid).status_code==400 and query('invalid-remove').json()['receipt'] is None
            assert get('/v1/needs',needs_id='n-rich').json()['needs']==snapshot
            clear=raw('clear','n-rich',1,{'companions':{},'fixed_items':[]});assert post(clear).status_code==200
            cleared=get('/v1/needs',needs_id='n-rich').json()['needs']['fields']
            assert cleared['companions']=={} and cleared['fixed_items']==[] and cleared['arrival']==event
            record('decimal/local DST walltime and locked user booking claim retained; companion reference failure atomic and explicit clear works')
            pre=raw('pre','n-pre',0,{'party_size':{'state':'known','value':2}})
            controls['deny_at']=controls['calls']+4
            failed=post(pre);assert failed.status_code==503 and 'receipt' not in failed.json()
            controls['deny_at']=None
            assert query('pre').json()['receipt'] is None and get('/v1/needs',needs_id='n-pre').json()['needs'] is None
            record('fresh precommit AUTH withdrawal rolls back current record and revision/receipt together')
            from cj_api import needs_projection
            real_receipt=needs_projection.receipt
            def withdrawing(value,domain):
                output=real_receipt(value,domain);controls['invited']=False;return output
            after=raw('after','n-after',0,{'party_size':{'state':'unknown'}})
            with patch.object(needs_projection,'receipt',side_effect=withdrawing):
                failed=post(after);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
            controls['invited']=True
            got=query('after').json()['receipt'];assert got['version']==1
            assert base64.b64decode(get('/v1/needs-revisions',needs_id=got['needs_id'],version=got['version']).json()['revision']['original_input_utf8_base64'])==after
            record('postcommit projection AUTH loss withholds private bytes; original receipt and exact historical input recover')
            for mode in ['lost','cancel']:
                value=raw(mode,'n-'+mode,0,{'party_size':{'state':'unknown'}});controls['ack']=mode
                failed=post(value);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
                got=query(mode).json()['receipt'];assert got['version']==1
                assert base64.b64decode(get('/v1/needs-revisions',needs_id=got['needs_id'],version=got['version']).json()['revision']['original_input_utf8_base64'])==value
            record('real COMMIT then lost ACK/CancelledError recovers original action bytes without latest-value inference or resend')
            b={'Authorization':'Bearer '+token_b}
            for path,q,key_name in [('/v1/needs',{'needs_id':'n1'},'needs'),('/v1/needs-action-receipts',{'action_id':'a1'},'receipt'),('/v1/needs-revisions',{'needs_id':'n1','version':1},'revision')]:
                assert client.get(path,params=q,headers=b).json()[key_name] is None
            with connect() as c:
                assert c.execute("SELECT to_regclass('public.cj_memory_item'),to_regclass('public.cj_trip_record')").fetchone()==(None,None)
            record('verified B cannot read A needs/revisions/receipts; no Memory or Trip storage created')
            swift_raw=raw('swift','n-swift',0,rich)
            settings={'baseURL':base,'token':token_a,'actionID':'swift','needsID':'n-swift','originalBase64':base64.b64encode(swift_raw).decode()}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            command([ROOT/'.local/needs-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            with connect() as c:
                assert bytes(c.execute("SELECT original_input FROM cj_needs_revision WHERE scope='fixture-a' AND action_id='swift'").fetchone()[0])==swift_raw
            record('official generated Swift Client four real operations and exact original bytes, missing states, walltime/decimal/lock retained')
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
