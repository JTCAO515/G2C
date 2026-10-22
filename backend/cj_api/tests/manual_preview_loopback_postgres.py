"""Fresh readonly manual preview API/PG/Swift; canonical synthetic Trip fixtures only."""
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
PRIVATE=ROOT/'.local-cj005-preview-pg'
PORT=55453


def command(argv,log,env):
    with log.open('w') as output:
        subprocess.run([str(x) for x in argv],env=env,stdout=output,stderr=subprocess.STDOUT,check=True)


def main():
    global PRIVATE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--auth-repository',type=Path,required=True)
    parser.add_argument('--manual-repository',type=Path,required=True)
    parser.add_argument('--driver-source',type=Path,required=True)
    parser.add_argument('--private-name',default='.local-cj005-preview-pg')
    args=parser.parse_args()
    if not re.fullmatch(r'\.local-cj005-preview-[a-z0-9-]+',args.private_name):
        raise RuntimeError('Explicit task-private preview directory required')
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
              'scope':'new private PostgreSQL + numeric HTTP loopback; synthetic JWT/formal Trip fixtures; readonly preview only','checks':[]}
    def record(name):
        evidence['checks'].append({'name':name,'status':'PASS'});print('PASS '+name,flush=True)
    try:
        exported=subprocess.check_output([sys.executable,'-B',str(ROOT/'scripts/prepare-manual-preview-deps.py'),
            '--auth-repository',str(args.auth_repository),'--source-repository',str(args.manual_repository)],cwd=ROOT,text=True).strip()
        pins=json.loads((ROOT/'backend/cj_api/manual_preview_pins.json').read_text());evidence['pins']=pins
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
        sys.path[:0]=[str(PRIVATE/'driver'),str(ROOT/'backend'),str(Path(exported)/'backend/auth'),str(Path(exported)/'backend/trip'),str(Path(exported)/'backend/manual_edit')]
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
        command([pg/'initdb','-D',data,'--username=cj005p','--auth-local=trust','--auth-host=reject',
                 '--encoding=UTF8','--locale=C','--no-clean'],PRIVATE/'initdb.txt',clean)
        command([pg/'pg_ctl','-D',data,'-l',PRIVATE/'postgres.log','-o',shlex.join(['-c','listen_addresses=',
                 '-k',str(PRIVATE/'s'),'-p',str(PORT),'-c','unix_socket_permissions=0700']),'-w','start'],PRIVATE/'pg-start.txt',clean)
        def connect():return psycopg.connect(host=str(PRIVATE/'s'),port=PORT,user='cj005p',dbname='postgres',
            passfile=str(PRIVATE/'empty.pgpass'),connect_timeout=5,
            options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')
        with connect() as c:
            identity=c.execute("SELECT current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_user,current_database(),version()").fetchone()
            assert identity[:5]==(str(data),'',str(PRIVATE/'s'),'cj005p','postgres')
            assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
            revision=pins['sources'][1]['commit']
            schema=subprocess.check_output(['git','-C',str(args.manual_repository),'show',revision+':backend/trip/sql/candidate.sql'])
            (PRIVATE/'candidate.sql').write_bytes(schema);c.execute(schema.decode())
            assert c.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==0
            c.execute("INSERT INTO cj_trip_scope(scope) VALUES ('fixture-a'),('fixture-b')")
        evidence['postgres']={'identity':list(identity),'schema_sha256':hashlib.sha256(schema).hexdigest()}
        record('verified fresh private PG identity, candidate schema only, zero formal Trip records')
        from unittest.mock import patch
        from cj_api.manual_preview_composition import ManualPreviewConfiguration
        import asyncio
        issuer='https://synthetic.invalid/cj005-preview';audience='cj005-preview-synthetic'
        scopes={'subject-a':'fixture-a','subject-b':'fixture-b'}
        controls={'invited':True,'read_fault':None};proofs={}
        class Facts:
            def evaluate(self,p):return CJAccessFacts(p,Fact.YES if p.subject in scopes else Fact.NO,Fact.YES,Fact.YES if controls['invited'] else Fact.NO)
        class ReadProxy:
            def __init__(self):self.connection=connect()
            def __getattr__(self,key):return getattr(self.connection,key)
            def commit(self):
                self.connection.commit();fault=controls['read_fault'];controls['read_fault']=None
                if fault=='unknown':raise OSError('synthetic read ACK unknown')
                if fault=='cancel':raise asyncio.CancelledError()
        def resolve(p):
            if p.issuer!=issuer or p.audience!=audience or p.subject not in scopes:raise RuntimeError('Unknown fixture binding')
            return ReadProxy,scopes[p.subject]
        # Canonical fixture writer exists only in this test, not in preview composition.
        def confirm(scope,action,proposal):return proofs.get(action.confirmation_ref)==(scope,action,proposal)
        writer=Repository(connect,'fixture-a',confirm)
        original_document={'title':'Synthetic 原题','items':[{'id':'a','text':'A original','verification':'verified','evidence':['synthetic-a']},
            {'id':'b','text':'B unchanged','verification':'pending','evidence':[]},{'id':'c','text':'C original','verification':'verified','evidence':['synthetic-c']}]}
        def create(pid,tid,expected=0,document=None):
            content=packed(document or original_document)
            proposal=Proposal(pid,tid,expected,'synthetic-basis',int(time.time())+3600,content)
            digest=writer.publish(proposal);a=Action('fixture-'+pid,'accept',pid,digest,'proof-'+pid)
            proofs[a.confirmation_ref]=('fixture-a',a,proposal);writer.act(a)
            return content
        original=create('p-main','t-main');race_original=create('p-race','t-race')
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        keys=StaticPublicKeys({'synthetic-key':VerificationKey('RS256',public)})
        configuration=JWTConfiguration(issuer,audience,'RS256',0);os.environ['CJ_ENV']='local'
        app=create_trip_composed_app(environment='local',jwt_configuration=configuration,verification_keys=keys,
            access_provider=Facts(),resolve=resolve,configuration=TripWireConfiguration(1024,100,131072),
            manual_preview_configuration=ManualPreviewConfiguration(262144,131072,4096,524288))
        def token(subject):
            now=int(time.time())
            return jwt.encode(dict(iss=issuer,aud=audience,sub=subject,iat=now-1,nbf=now-1,exp=now+600),key,algorithm='RS256',headers={'kid':'synthetic-key'})
        token_a,token_b=token('subject-a'),token('subject-b')
        def request(tid='t-main',content=original):return dict(trip_id=tid,expected_version=1,original_content_utf8_base64=base64.b64encode(content).decode(),
            selected_ids=['a','c'],title_selected=True,title='Changed title',text_updates=[{'item_id':'a','text':'Changed e\u0301 中文'}],order=['c','b','a'])
        http_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);http_socket.bind(('127.0.0.1',0));http_socket.listen(64)
        base='http://127.0.0.1:'+str(http_socket.getsockname()[1])
        server=uvicorn.Server(uvicorn.Config(app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[http_socket]},daemon=False);thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        def inventory():
            with connect() as c:
                return c.execute('SELECT (SELECT count(*) FROM cj_trip_proposal),(SELECT count(*) FROM cj_trip_receipt),(SELECT count(*) FROM cj_trip_record)').fetchone()
        with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=10) as client:
            headers={'Authorization':'Bearer '+token_a}
            def post(value,selected_headers=None):return client.post('/v1/trip-manual-previews',json=value,headers=selected_headers or headers)
            before=inventory();payload=request();result=post(payload);assert result.status_code==200
            p=result.json()['preview'];assert not p['can_save'] and p['protection_status']=='UNKNOWN' and p['preview_status']=='LOCAL'
            assert result.json()['request_id']==result.headers['X-Request-ID'] and result.headers['Cache-Control']=='no-store'
            assert base64.b64decode(p['original']['content_utf8_base64'])==original
            after=json.loads(base64.b64decode(p['content_utf8_base64']));assert [i['id'] for i in after['items']]==['c','b','a']
            assert after['items'][1]==original_document['items'][1] and after['items'][0]==original_document['items'][2]
            assert after['items'][2]['verification']=='pending' and after['items'][2]['evidence']==[]
            assert [c['path'] for c in p['diff']]==[['title'],['items','order'],['items','id','a']]
            assert inventory()==before and writer.detail('t-main').version==1 and writer.detail('t-main').content==original
            record('protected current own Trip preview exact selection/order/diff, fact reset, UNKNOWN protection and no write/save/receipt')
            noop=request();noop.update(selected_ids=[],title_selected=False,title=None,text_updates=[],order=None)
            n=post(noop);assert n.status_code==200 and n.json()['preview']['diff']==[]
            title_only=dict(noop,title_selected=True,title='Title only');t=post(title_only)
            assert t.status_code==200 and [d['path'] for d in t.json()['preview']['diff']]==[['title']]
            stale=dict(payload,expected_version=2);retained=json.dumps(stale,sort_keys=True)
            assert post(stale).status_code==409 and json.dumps(stale,sort_keys=True)==retained
            unsupported=dict(payload,protected_ids=[]);assert post(unsupported).status_code==400
            assert post(dict(payload,order=['b','a','c'])).status_code==400
            assert inventory()==before
            record('noop/title-only, stale original conflict keeps draft, unselected movement and caller protected metadata rejected with no writes')
            foreign=post(payload,{'Authorization':'Bearer '+token_b});missing=post(dict(payload,trip_id='missing'))
            assert foreign.status_code==missing.status_code==503 and foreign.json()['error']==missing.json()['error']
            assert client.post('/v1/trip-manual-previews',json=payload).status_code==401
            record('second account/missing Trip unavailable without preview; absent bearer rejected')
            from cj_api import manual_preview_routes
            encode=manual_preview_routes.encode_response
            def changed(session,rid,domain):
                body=encode(session,rid,domain);doc=json.loads(race_original);doc['title']='Concurrent canonical correction'
                create('p-race-v2','t-race',expected=1,document=doc);return body
            race=request('t-race',race_original);saved_input=json.dumps(race,sort_keys=True)
            with patch.object(manual_preview_routes,'encode_response',side_effect=changed):
                r=post(race);assert r.status_code==409 and 'preview' not in r.json()
            assert json.dumps(race,sort_keys=True)==saved_input
            record('canonical concurrent Trip correction during encoding is detected by final protected read, conflict never returns old preview')
            for failure in ['unknown','cancel']:
                def interrupted(session,rid,domain):
                    body=encode(session,rid,domain);controls['read_fault']=failure;return body
                with patch.object(manual_preview_routes,'encode_response',side_effect=interrupted):
                    r=post(payload);assert r.status_code==503 and 'preview' not in r.json()
            def denied(session,rid,domain):
                body=encode(session,rid,domain);controls['invited']=False;return body
            with patch.object(manual_preview_routes,'encode_response',side_effect=denied):
                r=post(payload);assert r.status_code==503 and 'preview' not in r.json()
            controls['invited']=True
            assert writer.detail('t-main').content==original and writer.detail('t-main').version==1
            record('late read ACK/cancellation or original AUTH loss withholds encoded preview and keeps original draft/source')
            settings={'baseURL':base,'token':token_a,'requestBase64':base64.b64encode(json.dumps(payload,ensure_ascii=False).encode()).decode()}
            path=PRIVATE/'swift-config.json';path.touch(mode=0o600);path.write_text(json.dumps(settings))
            counts=inventory()
            command([ROOT/'.local/manual-preview-loopback-client',path],PRIVATE/'swift-client.txt',os.environ.copy())
            assert inventory()==counts and writer.detail('t-main').content==original and writer.detail('t-main').version==1
            with connect() as c:
                assert c.execute("SELECT to_regclass('cj_memory_item'),to_regclass('cj_manual_edit_session')").fetchone()==(None,None)
            record('official generated Swift readonly preview exact before/diff/after, retained409 draft, no Proposal/ledger/Trip/Memory persistence')
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
