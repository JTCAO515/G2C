"""#228 typed message history readiness: actual local APIs, not native acceptance.

Requires an explicit bounded operator run configuration. Never changes backend,
contracts, applied migrations or existing data. Every PG/auth directory is private
and temporary; historical FAIL reports are retained in the external output.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,time,uuid
import argparse
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description='Actual signed local send.2 → worker → typed reads → history compatibility. FakeProvider/private PG only; no App UI claim.')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--run-context',type=Path,required=True)
args=parser.parse_args();OUTPUT=args.output.resolve()
if OUTPUT.is_relative_to(ROOT):raise ValueError('external evidence directory required')
OUTPUT.mkdir(parents=True)
if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
for key in tuple(os.environ):
    if key.startswith(('PG','LIBPQ','CJ_LOCAL_')) or key in ('DATABASE_URL','CJ_DATABASE_URL'):os.environ.pop(key)
os.environ.update(CJ_ENV='local')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend'),*[str(p) for p in (ROOT/'backend').iterdir() if p.is_dir()]]
import psycopg,dev_auth,migrate,local_run_context
from pg_suites import cluster
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER,load_history_configuration
from cj_api.local_run_context import load_run_context
from cj_message.travel import ABI
report=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 backend_tree=subprocess.check_output(['git','rev-parse','HEAD:backend'],cwd=ROOT,text=True).strip(),
 script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),checks=[],
 unrun=['App UI','typed Memory recall (separate consumer acceptance)','real services/models/cloud/device'])
def save(): (OUTPUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def check(label,response,expected=200):
    item=dict(check=label,expected=expected,actual=response.status_code,result='PASS' if response.status_code==expected else 'FAIL')
    value=response.json()
    if 'error' in value:item['error']={k:value['error'][k] for k in ('code','category','outcome','recovery')}
    report['checks'].append(item);save();return value
try:
    with tempfile.TemporaryDirectory(prefix='cj228h-',dir='/tmp') as temporary:
        root=Path(temporary);pg=Path(os.environ['CJ_PG_BINDIR']) if 'CJ_PG_BINDIR' in os.environ else Path(subprocess.check_output(['pg_config','--bindir'],text=True).strip())
        with cluster('historygap',port=55782,role='cj228_history_initializer',root=root/'pg',pg=pg) as config:
            with psycopg.connect(**config,autocommit=True) as connection:
                chain=migrate.load();migrate.up(connection,chain,chain[-1]['version'])
            conn=root/'connection.json';conn.write_text(json.dumps(config));conn.chmod(0o600)
            auth=root/'auth';identity='cj228-'+uuid.uuid4().hex;dev_auth.init(auth,[identity])
            context=load_run_context(args.run_context)
            local_run_context.provision_budget(conn,context,identity)
            token=dev_auth.token(auth,identity,60)
            headers={'Authorization':'Bearer '+token};binary={**headers,'Content-Type':'application/octet-stream'}
            legacy_app=create_local_app(conninfo_path=conn,auth_dir=auth,run_context=context,history_configuration=load_history_configuration(auth))
            with TestClient(legacy_app) as client:
                control_head=check('legacy control open before typed activation',client.put('/v1/conversations',params={'conversation_id':'legacy-chat'},headers=headers))
                if 'head' in control_head:control_head=control_head['head']
                legacy=json.dumps(dict(version='MESSAGE-send.1',message_id=uuid.uuid4().hex,conversation_id='legacy-chat',text='legacy control',trip_id=None,
                    creation_intent='none',expected_generation=control_head['generation'],expected_sequence=control_head['last_sequence'])).encode()
                check('actual legacy control accepted before typed activation',client.post('/v1/messages',content=legacy,headers=binary))
                check('actual legacy history before typed activation',client.get('/v1/message-history',params={'conversation_id':'legacy-chat','limit':20},headers=headers))
            from run_worker import run_once
            from cj_agent.provider import FakeProvider
            legacy_database=LocalDatabase(conn,run_context=context)
            report['legacy_worker_outcomes']=[dict(message_id=x.message_id,run_id=x.run_id,status=x.status) for x in run_once(legacy_database,FakeProvider(),auth)]
            dev_auth.activate_travel(conn,identity,context,ABI)
            app=create_local_app(conninfo_path=conn,auth_dir=auth,run_context=context,travel_context=True,history_configuration=load_history_configuration(auth))
            database=LocalDatabase(conn,run_context=context,travel_context=True)
            with database.connect(scope_for(ISSUER,identity)) as scoped:
                role=scoped.execute('SELECT current_user,current_role').fetchone()
                report['runtime_role']=list(role)
                if tuple(role)!=('cj_m1_runtime','cj_m1_runtime'):raise RuntimeError('restricted runtime role required')
            with TestClient(app) as client:
                check('configured conversation list after activation',client.get('/v1/conversations',params={'limit':20},headers=headers))
                legacy_history=check('actual legacy row readable after typed activation',client.get('/v1/message-history',params={'conversation_id':'legacy-chat','limit':20},headers=headers))
                report['legacy_rows_after_activation']=len(legacy_history.get('messages',[]))
                if report['legacy_rows_after_activation']!=1:raise RuntimeError('actual legacy control row required')
                created=check('signed travel create',client.post('/v1/travel-context-actions',headers=binary,
                    content=json.dumps(dict(version='TRAVEL-context-action.1',action_id=uuid.uuid4().hex,operation='create',travel_context=None)).encode()))
                travel=created['receipt']['travel_context']
                opened=check('signed conversation open',client.put('/v1/conversations',params={'conversation_id':'typed-chat'},headers=headers))
                head=check('typed head',client.get('/v2/message-send-status',params={'conversation_id':'typed-chat'},headers=headers))['head']
                mid=uuid.uuid4().hex
                raw=json.dumps(dict(version='MESSAGE-send.2',message_id=mid,conversation_id='typed-chat',text='history compatibility probe',trip_id=None,
                    creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence'],
                    travel_context=dict(id=travel['id'],expected_version=travel['version']),needs_reference=None),separators=(',',':')).encode()
                accepted=check('typed send accepted',client.post('/v2/messages',content=raw,headers=binary))
                report['original_sha256_matches']=accepted['receipt']['input_sha256']==hashlib.sha256(raw).hexdigest()
                if not report['original_sha256_matches']:raise RuntimeError('original receipt hash mismatch')
                report['typed_worker_outcomes']=[dict(message_id=x.message_id,run_id=x.run_id,status=x.status) for x in run_once(database,FakeProvider(),auth)]
                check('typed RUN snapshot after formal worker',client.get('/v2/run-display',params={'message_id':mid},headers=headers))
                check('typed RUN draft status after formal worker',client.get('/v3/run-draft-status',params={'message_id':mid},headers=headers))
                check('original typed status',client.get('/v2/message-send-status',params={'conversation_id':'typed-chat','message_id':mid},headers=headers))
                check('conversation list',client.get('/v1/conversations',params={'limit':20},headers=headers))
                check('history of actually accepted typed message',client.get('/v1/message-history',params={'conversation_id':'typed-chat','limit':20},headers=headers))
                from cj_message.domain import Command
                Command.parse_stored(legacy)
                try:Command.parse_stored(raw);report['typed_stored_parser']='accepted'
                except Exception as error:report['typed_stored_parser']=type(error).__name__
            report['passed']=sum(x['result']=='PASS' for x in report['checks']);report['failed']=sum(x['result']=='FAIL' for x in report['checks']);save()
        status=subprocess.run([str(pg/'pg_ctl'),'-D',str(root/'pg/data'),'status'],capture_output=True)
        report['private_pg_stopped']=status.returncode==3
except BaseException as error:
    report['infrastructure_error']=type(error).__name__;save();raise
finally:save()
print(json.dumps({k:report[k] for k in ('head','passed','failed','runtime_role','original_sha256_matches','private_pg_stopped') if k in report}))
raise SystemExit(1 if report['failed'] else 0)
