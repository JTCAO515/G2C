from datetime import datetime,timedelta,timezone
import hashlib,importlib.util,io,json,sys
from pathlib import Path
import pytest

@pytest.fixture
def observer(tmp_path,monkeypatch):
 p=Path(__file__).resolve().parents[1]/'hk/status_remote.py';s=importlib.util.spec_from_file_location('qualifiedstatus',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.ROOT=tmp_path
 (tmp_path/'probes').mkdir();(tmp_path/'probes/application-deploy.lock').touch();directory=tmp_path/'probes/window';directory.mkdir();manifest=directory/'window.json';manifest.write_bytes(b'fixed-original-selection')
 now=datetime.now(timezone.utc);q=dict(version='G2C-HK-synthetic-qualification.1',line='C',state='ACTIVE',incident_hold=False,lease_id='fixture-only',source='a'*40,image='sha256:'+'b'*64,schema=55,server_directory=str(directory),artifact_directory=str(directory/'artifacts'),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),proof_plan=str(directory/'proof-plan.json'),starts_at=(now-timedelta(minutes=1)).isoformat(),stop_new_at=(now+timedelta(minutes=1)).isoformat(),ends_at=(now+timedelta(minutes=2)).isoformat(),financial_policy={'limits':{'model':{'hold_per_attempt_cny_1e7':10000000}}})
 path=directory/'qualification.json';path.write_text(json.dumps(q));fault={'value':None};calls=[]
 def command(args,phase):
  calls.append(args)
  if args[:2]==['docker','inspect']:
   role='api'if args[-1].endswith('api-1')else'worker'
   mounts=[]if role=='api'else[dict(Destination='/run/tool-evidence/window.json',Source=str(manifest),RW=False),dict(Destination='/tool-evidence',Source=q['artifact_directory'],RW=True)]
   if role=='worker'and len([a for a in calls if a[:2]==['docker','inspect']])>2:
    if fault['value']=='mount_order':mounts.reverse()
    if fault['value']=='mount_rw':mounts[0]['RW']=True
    if fault['value']=='mount_source':mounts[0]['Source']='foreign-selector'
   row=dict(Id=role,Image=q['image'],Config={'Labels':{'org.opencontainers.image.revision':q['source']},'Cmd':['api']if role=='api'else['worker','--tool-evidence-manifest','/run/tool-evidence/window.json']},State={'Running':True,'Health':{'Status':'healthy'}},Mounts=mounts)
   if fault['value']=='source':row['Image']='sha256:'+'c'*64
   return json.dumps([row]).encode()
  if args[:2]==['docker','compose']:return json.dumps(dict(global_pending=0,global_active=1 if fault['value']=='inflight'else 0,background_states={},memory_states={'unknown':2},ledger={'count':1,'sha256':'d'*64},observations=[dict(message_record=dict(status=None))]if fault['value']=='missing_run'else [])).encode()
  if args[:2]==['docker','exec']:
   if fault['value']=='late_source':fault['value']='source'
   if fault['value']=='late_stop':q['state']='STOP_NEW';path.write_text(json.dumps(q))
   policy={'cap':1000000000,'active_cap':1000000000,'model_cap':None,'tool_cap':None,'max_calls':None,'model_calls':None,'tool_calls':None}
   if fault['value']in('model_cap','model_calls','cap','max_calls'):policy[fault['value']]=0
   return json.dumps({'lines':{'C':{'policy':policy,'usage':{'total':0,'calls':0,'model':0,'tools':0,'model_calls':0,'tool_calls':0}}}}).encode()
  raise AssertionError(args)
 monkeypatch.setattr(m,'command',command)
 def run(purpose):
  request=dict(qualification=str(path),qualification_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),purpose=purpose)
  monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(json.dumps(request).encode())));m.main()
 return q,path,fault,run,calls


def test_query_never_authorizes_dispatch_even_idle(observer,capsys):
 q,p,f,run,calls=observer;run('query');x=json.loads(capsys.readouterr().out)
 assert x['status']=='READY_FOR_FIXED_WINDOW'and x['purpose']=='query'and x['business_dispatch_allowed_by_observed_conditions']is False


def test_dispatch_requires_actual_idle(observer,capsys):
 q,p,f,run,calls=observer;run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['business_dispatch_allowed_by_observed_conditions']is True
 f['value']='inflight';run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['status']=='STOP_NEW_OR_NOT_READY'and x['business_dispatch_allowed_by_observed_conditions']is False
 run('query');x=json.loads(capsys.readouterr().out)
 assert x['status']=='READY_FOR_FIXED_WINDOW'and x['business_dispatch_allowed_by_observed_conditions']is False


def test_missing_original_run_is_readable_but_never_dispatch_idle(observer,capsys):
 q,p,f,run,calls=observer;f['value']='missing_run'
 run('query');x=json.loads(capsys.readouterr().out)
 assert x['status']=='READY_FOR_FIXED_WINDOW'and x['empty_inflight']is False
 assert x['business_dispatch_allowed_by_observed_conditions']is False
 run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['status']=='STOP_NEW_OR_NOT_READY'and x['empty_inflight']is False
 assert x['business_dispatch_allowed_by_observed_conditions']is False


@pytest.mark.parametrize('fault',['hold','source','stop_new','closed'])
def test_new_dispatch_not_ready_on_qualification_or_source_drift(observer,capsys,fault):
 q,p,f,run,calls=observer
 if fault=='hold':q['incident_hold']=True
 elif fault=='source':f['value']='source'
 elif fault=='stop_new':q['stop_new_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
 else:q['state']='CLOSED'
 p.write_text(json.dumps(q));run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['status']=='STOP_NEW_OR_NOT_READY'and x['business_dispatch_allowed_by_observed_conditions']is False


@pytest.mark.parametrize('fault',['late_source','late_stop'])
def test_status_return_rechecks_original_snapshot(observer,capsys,fault):
 q,p,f,run,calls=observer;f['value']=fault;run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['business_dispatch_allowed_by_observed_conditions']is False and x['observation_unchanged']is False


@pytest.mark.parametrize('fault',['model_cap','model_calls','cap','max_calls'])
def test_original_category_limits_not_ignored(observer,capsys,fault):
 q,p,f,run,calls=observer;f['value']=fault;run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['business_dispatch_allowed_by_observed_conditions']is False and x['availability_by_kind']['model']is False


def test_host36_aware_timestamp_variants(observer):
 q,p,f,run,calls=observer
 import importlib.util
 spec=importlib.util.spec_from_file_location('status_time',Path(__file__).resolve().parents[1]/'hk/status_remote.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 from datetime import timezone
 assert m.instant('2026-11-15T10:10:00+08:00').astimezone(timezone.utc).hour==2
 assert m.instant('2026-11-15T02:10:00.123456+00:00').microsecond==123456


@pytest.mark.parametrize('fault,ready',[('mount_order',True),('mount_rw',False),('mount_source',False)])
def test_mount_order_equivalence_preserves_full_value_checks(observer,capsys,fault,ready):
 q,p,f,run,calls=observer;f['value']=fault;run('dispatch');x=json.loads(capsys.readouterr().out)
 assert x['observation_unchanged']is ready
 assert x['business_dispatch_allowed_by_observed_conditions']is ready
