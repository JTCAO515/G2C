"""Read-only observed readiness; query never authorizes a business write."""
import fcntl,hashlib,json,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/srv/g2c-beta')

class StatusCommandError(Exception):
 def __init__(self,phase,return_code,stdout,stderr,kind):
  self.data=dict(phase=phase,return_code=return_code,error_kind=kind,
   stdout_bytes=len(stdout),stdout_sha256=hashlib.sha256(stdout).hexdigest(),
   stderr_bytes=len(stderr),stderr_sha256=hashlib.sha256(stderr).hexdigest())
  super().__init__('original readiness command unavailable')

def command(args,phase):
 try:r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
 except subprocess.TimeoutExpired as error:
  raise StatusCommandError(phase,None,error.stdout or b'',error.stderr or b'','native_wait_timeout')from None
 if r.returncode:raise StatusCommandError(phase,r.returncode,r.stdout,r.stderr,'native_exit')
 return r.stdout
def inspect(name,phase):return json.loads(command(['docker','inspect',name],phase))[0]
def instant(value):
 # B issues aware ISO timestamps; Python 3.6 needs +HHMM.
 pattern='%Y-%m-%dT%H:%M:%S.%f%z'if'.'in value else'%Y-%m-%dT%H:%M:%S%z'
 return datetime.strptime(value[:-3]+value[-2:],pattern)
def main():
 request=json.loads(sys.stdin.buffer.read(16384));qpath=Path(request['qualification'])
 qraw=qpath.read_bytes();q=json.loads(qraw);purpose=request['purpose']
 if q['version']!='G2C-HK-synthetic-qualification.1'or purpose not in('query','dispatch'):raise ValueError('qualified read-only status request required')
 if hashlib.sha256(qraw).hexdigest()!=request['qualification_sha256']:raise ValueError('qualification drift')
 lock=(ROOT/'probes/application-deploy.lock').open('r')
 try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
 except BlockingIOError:
  print(json.dumps(dict(version='G2C-HK-capture-status.1',purpose=purpose,status='NOT_READY_DEPLOYMENT_IN_PROGRESS',business_dispatch_allowed_by_observed_conditions=False)));return
 api=inspect('g2c-beta-api-1','inspect_api_before');worker=inspect('g2c-beta-worker-1','inspect_worker_before');mounts={m['Destination']:m for m in worker['Mounts']}
 actual=all(x['Image']==q['image']and x['Config']['Labels']['org.opencontainers.image.revision']==q['source']for x in(api,worker))
 manifest=Path(q['server_directory'])/'window.json'
 capture=(hashlib.sha256(manifest.read_bytes()).hexdigest()==q['manifest_sha256']
  and worker['Config']['Cmd']==['worker','--tool-evidence-manifest','/run/tool-evidence/window.json']
  and mounts.get('/run/tool-evidence/window.json',{}).get('Source')==str(manifest)
  and mounts.get('/run/tool-evidence/window.json',{}).get('RW')is False
  and mounts.get('/tool-evidence',{}).get('Source')==q['artifact_directory']
  and mounts.get('/tool-evidence',{}).get('RW')is True)
 base=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),'-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
 args=base+['run','--rm','--no-deps','-T','--entrypoint','python']
 for source,target in ((q['proof_plan'],'/plan.json'),(str(ROOT/'probes/836-release-export.py'),'/export.py'),(str(ROOT/'budget'),'/budget'),(q['artifact_directory'],'/evidence')):args+=['-v',source+':'+target+':ro']
 proof=json.loads(command(args+['migrate','-B','/export.py'],'proof'))
 financial=json.loads(command(['docker','exec',worker['Id'],'python','-B','/app/scripts/hk_sublimits.py','read'],'financial'))
 after_api=inspect('g2c-beta-api-1','inspect_api_after');after_worker=inspect('g2c-beta-worker-1','inspect_worker_after')
 def fingerprint(x):return(x['Id'],x['Image'],x['Config']['Labels']['org.opencontainers.image.revision'],x['Config']['Cmd'],x['State']['Running'],x['State'].get('Health',{}).get('Status'),sorted(x['Mounts'],key=lambda m:m['Destination']))
 observed_unchanged=(qpath.read_bytes()==qraw and fingerprint(after_api)==fingerprint(api)and fingerprint(after_worker)==fingerprint(worker))
 now=datetime.now(timezone.utc);start=instant(q['starts_at']);stop=instant(q['stop_new_at']);end=instant(q['ends_at'])
 healthy=api['State']['Running']and worker['State']['Running']and api['State'].get('Health',{}).get('Status')=='healthy'
 empty=(proof['global_pending']==proof['global_active']==0 and not any(proof['background_states'].get(k,0)for k in('queued','running','publishing'))and not any(proof['memory_states'].get(k,0)for k in('pending','inflight')))
 common=observed_unchanged and actual and capture and healthy and q['state']=='ACTIVE'and not q.get('incident_hold',False)
 read_ready=common and start<=now<end
 line=financial['lines'][q['line']];used=line['usage'];policy=line['policy']
 availability={}
 for kind,limit in q['financial_policy']['limits'].items():
  hold=limit['hold_per_attempt_cny_1e7'];category='model'if kind=='model'else'tool'
  category_cost=used['model']if category=='model'else used['tools'];category_calls=used[category+'_calls']
  availability[kind]=all((policy['cap']is None or used['total']+hold<=policy['cap'],
   policy['active_cap']is None or used['total']+hold<=policy['active_cap'],
   policy[category+'_cap']is None or category_cost+hold<=policy[category+'_cap'],
   policy['max_calls']is None or used['calls']<policy['max_calls'],
   policy[category+'_calls']is None or category_calls<policy[category+'_calls']))
 room=availability['model']
 dispatch=(purpose=='dispatch'and common and start<=now<stop and empty and room)
 ready=dispatch if purpose=='dispatch'else read_ready
 print(json.dumps(dict(version='G2C-HK-capture-status.1',purpose=purpose,
  status='READY_FOR_FIXED_WINDOW'if ready else'PREPARED_NOT_ACTIVE'if q['state']=='PREPARED_NOT_ACTIVE'else'STOP_NEW_OR_NOT_READY',
  business_dispatch_allowed_by_observed_conditions=dispatch,source=worker['Config']['Labels']['org.opencontainers.image.revision'],image=worker['Image'],schema=q['schema'],
  observed_at=now.isoformat(),lease_id=q['lease_id'],capture_matches=capture,source_image_matches=actual,healthy=healthy,empty_inflight=empty,
  pending=proof['global_pending'],active=proof['global_active'],background_states=proof['background_states'],memory_states=proof['memory_states'],ledger=proof['ledger'],
  line_sublimit=line,availability_by_kind=availability,observation_unchanged=observed_unchanged,incident_hold=q.get('incident_hold',False),private_training_runtime='DISABLED',
  requires_native_admission='Original credential/AUTH/RUN/Meter/financial guards remain mandatory; observation is not a capability')))

if __name__=='__main__':
 try:main()
 except StatusCommandError as error:
  sys.stderr.write('G2C_STATUS_FAILURE '+json.dumps(error.data,sort_keys=True)+'\n');raise SystemExit(1)
