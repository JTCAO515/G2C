"""Fresh private TRIP API/PG/Swift loopback; immutable synthetic candidates and confirmation only."""
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
PRIVATE=ROOT/'.local-cj005-trip-pg'
PORT=55449


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--trip-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-trip-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-trip-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private trip directory required')
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
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/review/confirmation only','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-trip-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.trip_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/trip_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/trip')]
        import psycopg
        import httpx
        import jwt
        import uvicorn
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cj_auth.interfaces import CJAccessFacts, Fact
        from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
        from cj_trip.domain import Proposal,Action,packed
        from cj_trip.postgres import Repository
        from cj_api.trip_composition import create_trip_composed_app,TripWireConfiguration
        assert psycopg.__version__=='3.2.10' and Path(psycopg.__file__).resolve().is_relative_to((PRIVATE/'driver').resolve())
        evidence['driver']={'version':psycopg.__version__,'implementation':psycopg.pq.__impl__}
        command([pg/'initdb','-D',data,'--username=cj005t','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005t',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005t','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            revision=pins['sources'][1]['commit']
            schema=subprocess.check_output(['git','-C',str(args.trip_repository),'show',revision+':backend/trip/sql/candidate.sql'])
            (PRIVATE/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==0
            c.execute("INSERT INTO cj_trip_scope(scope) VALUES ('fixture-a'),('fixture-b')")
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero formal Trip records')
        from unittest.mock import patch
        import asyncio
        issuer='https://synthetic.invalid/cj005-trip';audience='cj005-trip-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'calls':0,'deny_at':None,'invited':True,'ack':None,'confirm_enabled':False}
        proofs={}
        class Facts:
            def evaluate(self,p):
                controls['calls']+=1
                invited=controls['invited'] and controls['calls']!=controls['deny_at']
                return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES if invited else Fact.NO)
        class CommitProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,k):return getattr(self.connection,k)
            def commit(self):
                self.connection.commit()
                fault=controls['ack'];controls['ack']=None
                if fault=='cancel':raise asyncio.CancelledError()
                if fault=='lost':raise OSError('synthetic lost ACK after real COMMIT')
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return CommitProxy,scopes[p.subject]
        def confirm(scope,action,proposal):
            # Synthetic server-held exact review evidence, never a caller viewed flag.
            return controls['confirm_enabled'] and proofs.get(action.confirmation_ref)==(scope,action.kind,action.proposal_id,action.candidate_hash,proposal)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0)
        os.environ['CJ_ENV']='local'
        app=create_trip_composed_app(environment='local',jwt_configuration=configuration,verification_keys=keys,
            access_provider=Facts(),resolve=resolve,confirmation_validator=confirm,
            configuration=TripWireConfiguration(1024,100,131072))
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,
                algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        def publish(pid,tid,expected=0,expires=None,text='Synthetic pending item'):
            content=packed({'title':'Synthetic e\u0301 中文','items':[{'id':'i1','text':text,'verification':'pending','evidence':[]}]})
            proposal=Proposal(pid,tid,expected,'basis1',expires or int(time.time())+3600,content)
            digest=Repository(connect,'fixture-a').publish(proposal)  # trusted test ingress only; no HTTP publish route
            return proposal,digest
        def action(aid,kind,proposal,digest):
            value=Action(aid,kind,proposal.proposal_id,digest,'proof-'+aid)
            proofs[value.confirmation_ref]=('fixture-a',kind,proposal.proposal_id,digest,proposal)
            return value
        p1,h1=publish('p1','t1');a1=action('a1','accept',p1,h1)
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
            def post(a):return client.post('/v1/trip-actions',content=a.raw(),headers=headers)
            def original(aid):return get('/v1/trip-action-receipts',action_id=aid)
            shown=get('/v1/trip-proposals',proposal_id='p1');assert shown.status_code==200
            shown=shown.json()['proposal'];assert shown['candidate_hash']==h1 and base64.b64decode(shown['content_utf8_base64'])==p1.content
            assert post(a1).status_code==503  # display is not confirmation
            assert get('/v1/trip-details',trip_id='t1').json()['trip'] is None
            controls['confirm_enabled']=True
            missing=Action('unreviewed','accept','p1',h1,'caller-viewed')
            assert post(missing).status_code==503
            first=post(a1);assert first.status_code==200,first.status_code
            receipt=first.json()['receipt'];assert receipt['committed_version']==1
            assert post(a1).json()['receipt']==receipt
            assert post(Action('a1','reject','p1',h1,'proof-a1')).status_code==409
            trip=get('/v1/trip-details',trip_id='t1').json()['trip']
            assert trip['version']==1 and base64.b64decode(trip['content_utf8_base64'])==p1.content
            assert trip['document']['items'][0]['verification']=='pending'
            record('protected candidate read, missing confirmation rejection, exact acceptance/replay/conflict and pending formal content')
            pr,hr=publish('p-reject','t-reject');reject=action('a-reject','reject',pr,hr)
            rejected=post(reject);assert rejected.status_code==200 and rejected.json()['receipt']['committed_version'] is None
            assert post(reject).json()['receipt']==rejected.json()['receipt']
            assert get('/v1/trip-details',trip_id='t-reject').json()['trip'] is None
            assert post(action('a-after-reject','accept',pr,hr)).status_code==409
            expired,he=publish('p-expired','t-expired',expires=int(time.time())-1)
            assert get('/v1/trip-proposals',proposal_id='p-expired').json()['proposal']['status']=='pending'
            assert post(action('a-expired','accept',expired,he)).status_code==409
            record('reject required-null/no formal Trip, terminal refusal, elapsed pending display and expiry conflict')
            p2,h2=publish('p2','t1',expected=1,text='Synthetic changed pending item')
            assert post(action('a2','accept',p2,h2)).json()['receipt']['committed_version']==2
            assert original('a1').json()['receipt']==receipt
            assert get('/v1/trip-details',trip_id='t1').json()['trip']['version']==2
            stale,hs=publish('p-stale','t1',expected=0)
            assert post(action('a-stale','accept',stale,hs)).status_code==409
            record('original action remains then-version1 while latest Trip is2; stale expected version denied')
            pre,hp=publish('p-pre','t-pre');ap=action('a-pre','accept',pre,hp)
            controls['deny_at']=controls['calls']+4  # bind/entry/transaction/commit in fixed public seam
            failed=post(ap);assert failed.status_code==503 and 'receipt' not in failed.json()
            controls['deny_at']=None
            assert original('a-pre').json()['receipt'] is None
            assert get('/v1/trip-details',trip_id='t-pre').json()['trip'] is None
            assert get('/v1/trip-proposals',proposal_id='p-pre').json()['proposal']['status']=='pending'
            record('fresh precommit AUTH denial rolls back Trip/proposal transition/receipt together')
            postp,hh=publish('p-post','t-post');apost=action('a-post','accept',postp,hh)
            from cj_api import trip_routes
            real_projection=trip_routes.receipt_projection
            def withdrawing(value,domain):
                projected=real_projection(value,domain);controls['invited']=False;return projected
            with patch.object(trip_routes,'receipt_projection',side_effect=withdrawing):
                failed=post(apost);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
            controls['invited']=True
            assert original('a-post').json()['receipt']['committed_version']==1
            record('postcommit JSON projection authority withdrawal withholds bytes and preserves original receipt')
            for mode in ['lost','cancel']:
                proposal,digest=publish('p-'+mode,'t-'+mode);a=action('a-'+mode,'accept',proposal,digest)
                controls['ack']=mode
                failed=post(a);assert failed.status_code==503 and failed.json()['error']['recovery']=='reconcile_original'
                assert original(a.action_id).json()['receipt']['committed_version']==1
            record('real COMMIT followed by lost ACK and CancelledError both recover original action without resend')
            b={'Authorization':'Bearer '+token_b}
            assert client.get('/v1/trips',params={'limit':2},headers=b).json()['trips']==[]
            assert client.get('/v1/trip-action-receipts',params={'action_id':'a1'},headers=b).json()['receipt'] is None
            denied=client.get('/v1/trip-proposals',params={'proposal_id':'p1'},headers=b)
            missing=get('/v1/trip-proposals',proposal_id='missing')
            assert denied.status_code==missing.status_code==503 and denied.json()['error']==missing.json()['error']
            record('verified second account cannot read first records/receipts/candidates; missing and wrong-scope identical denial')
            swiftp,swifth=publish('p-swift','t-swift');swifta=action('a-swift','accept',swiftp,swifth)
            with connect() as c:expected=c.execute("SELECT count(*) FROM cj_trip_record WHERE scope='fixture-a'").fetchone()[0]+1
            settings={'baseURL':base,'token':token_a,'proposalID':swiftp.proposal_id,'actionID':swifta.action_id,
                'confirmationRef':swifta.confirmation_ref,'tripID':swiftp.trip_id,
                'contentBase64':base64.b64encode(swiftp.content).decode(),'expectedTotalTrips':expected}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            command([ROOT/'.local/trip-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            with connect() as c:
                stored=bytes(c.execute("SELECT original_input FROM cj_trip_receipt WHERE scope='fixture-a' AND action_id='a-swift'").fetchone()[0])
                assert stored==swifta.raw()
            record('official generated Swift Client five real operations and exact canonical original action persisted')
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
