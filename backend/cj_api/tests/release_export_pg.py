"""Real signed admission before RUN creation; readonly proof and versioned ledgers."""
from contextlib import contextmanager
from datetime import datetime,timezone
import base64,json,os,sys,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import httpx,psycopg
import dev_auth,local_history_pg as harness,local_run_context,run_worker
from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
from cj_api.local_app import LocalDatabase,ISSUER,scope_for,load_confirmation_signer
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.real_services import RealServices,RealTools
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_strict_json import compact
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.codec import decode_stored,encode_v2
from cj_usage.core import LedgerV2
from dataclasses import asdict
from deploy.hk import checkpoint,release_export
from test_lio_planning_flow import flow


def exercise(auth,conninfo):
 root=auth.parent;control=root/'control';config=json.loads(conninfo.read_bytes())
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
 recovery=Ed25519PrivateKey.generate()
 os.environ.update(CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_BETA_DB_TARGET='hk-local',CJ_TRIAL_VALID_UNTIL='2026-12-31T16:00:00+00:00',CJ_BETA_RECOVERY_PRIVATE_B64=base64.b64encode(recovery.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),CJ_BETA_RECOVERY_PUBLIC_B64=base64.b64encode(recovery.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode())
 @contextmanager
 def operator():
  with psycopg.connect(**config,autocommit=True)as db:yield db,config
 with patch.object(checkpoint,'operator',operator):checkpoint.bootstrap(control,lambda _:None)
 subject='m4-synthetic-local-proof';subjects=frozenset((subject,));dev_auth.init(auth,subjects)
 now=int(time.time());context_file=root/'context.json'
 context_file.write_bytes(compact(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=800,period_start=now-60,period_end=now+3600,max_steps=12,max_tools=12,max_output=65536,max_seconds=600),output_limits=dict(model=12000,tool=48000,memory=2000)),history=[])))
 context=load_run_context(context_file);local_run_context.provision_budget(conninfo,context,subject);dev_auth.activate_travel(conninfo,subject,context,ABI)
 database=LocalDatabase(conninfo,run_context=context,travel_context=True,needs_context=True)
 checker=checker_for(auth);token=dev_auth.token(auth,subject,300);scope=scope_for(ISSUER,subject)
 boundary=Boundary(checker,lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:str(uuid.uuid4()))
 budget=AuthorizationBudget(root/'financial',clock=lambda:datetime(2026,11,14,tzinfo=timezone.utc))
 with budget.connect()as db:
  db.execute('INSERT INTO attempt VALUES(?,?,?,?,?)',('existing-fixture-history','model','a'*64,'RECEIVED','{}'))
 calls=[]
 def response(request):
  body=json.loads(request.content);calls.append(body)
  if 'response_format' not in body:
   # JT 2026-11-25 B: after intake, a consult message continues to the detailed answer path.
   event=dict(id='chatcmpl-proof-answer-'+str(len(calls)),model=M4_MODEL,choices=[dict(index=0,delta=dict(content='Which places interest you?'),finish_reason='stop')],usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
   return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
  index=body['response_format']['json_schema']['schema']['properties']['current_source_index']['const']
  value=flow('Synthetic question',city=None,days=None,intent='consult',reply='Which places interest you?',questions=(),index=index)
  value.update(version='LIO-planning-intake.8',planning_request_index=None,needs_tools=False)
  event=dict(id='chatcmpl-proof-fixture-'+str(len(calls)),model=M4_MODEL,choices=[dict(index=0,delta=dict(content=json.dumps(value)),finish_reason='stop')],usage=dict(prompt_tokens=100,completion_tokens=100,total_tokens=200))
  return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
 model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,'fixture-only-not-live'),budget,transport=httpx.MockTransport(response))
 tools=RealTools(RealServices(model,'fixture-only-not-live',subjects,demo_subjects=subjects,national_subjects=subjects),buffered_streaming_subjects=subjects)
 worker=run_worker._worker_for_scope(database,model,auth,scope,checker,tools_configuration=tools,draft_profile='needs-structured.1',assembly_planning=True,demo_planning=True,national_planning=True,lio_confirmation=load_confirmation_signer(auth))
 evidence=root/'artifacts';evidence.mkdir(mode=0o700)
 for version in (1,2):
  if version==2:
   with psycopg.connect(**config)as db:
    account,stored_version,raw=db.execute('SELECT scope_id,format_version,ledger FROM cj_usage_ledger_candidate').fetchone()
    old=decode_stored(stored_version,raw);new=LedgerV2(**asdict(old),run_profiles={},attempt_providers={})
    db.execute('UPDATE cj_usage_ledger_candidate SET format_version=2,ledger=%s::jsonb WHERE scope_id=%s',(encode_v2(new),account))
  mid='pending-run-v'+str(version)
  plan=dict(window_id='local-proof',source_commit='b'*40,identities=[dict(locale='en',subject=subject)],cases=[dict(locale='en',message_id=mid)])
  def collect():
   with patch.object(checkpoint,'operator',operator):return release_export.collect(plan,control,evidence,budget.path)
  before=collect()
  receipt=boundary.receive_lio(token,compact(dict(version='LIO-message.2',message_id=mid,text='Please explain travel history.',locale='en',new_conversation=True)),prepare_scope=database._provision_scope,version='LIO-message.2')
  pending=collect();record=pending['observations'][0]['message_record']
  assert pending['global_pending']==1 and pending['global_active']==0
  assert record['run_id']==receipt.run_id and record['status']is None and record['operations']==[]
  assert pending['ledger']==before['ledger']
  outcomes=[x.status for x in worker.process()]
  assert outcomes==['completed'],(outcomes,len(calls))
  completed=collect();record=completed['observations'][0]['message_record']
  assert completed['global_pending']==completed['global_active']==0 and record['status']=='completed'
  # JT 2026-11-25 B: intake + detailed answer, each settled and received.
  assert len(record['operations'])==2 and all(op['meter']['state']=='settled'for op in record['operations'])
  assert len(completed['shared_outflows'])==2 and all(x['state']=='RECEIVED'for x in completed['shared_outflows'].values())
 assert len(calls)==4
 print('PASS fresh signed M before RUN is status null with original pending/unchanged journal; original worker completion/ACK and settled Meter/fees readable in ledger formats1/2;4 fixture model HTTP/live0')


if __name__=='__main__':
 harness.exercise=exercise
 harness.main()
