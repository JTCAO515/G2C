"""B-issued read-only readiness observation; no credentials or dispatch."""
import argparse,json,hashlib,subprocess,shlex,os,re,uuid
from pathlib import Path
from datetime import datetime,timezone
from cj_api.runtime_private import read_private,private_directory


def record_failure(root,q,purpose,phase,return_code,stdout,stderr,native=None,*,qualification_sha256):
 directory=root/'readiness-failures'
 try:directory.mkdir(mode=0o700)
 except FileExistsError:pass
 value=dict(version='G2C-readiness-failure.1',lease_id=q['lease_id'],line=q['line'],purpose=purpose,
  expected_source=q['source'],expected_image=q['image'],expected_schema=q['schema'],
  qualification_sha256=qualification_sha256,
  observed_at=datetime.now(timezone.utc).isoformat(),phase=phase,return_code=return_code,
  stdout_bytes=len(stdout),stdout_sha256=hashlib.sha256(stdout).hexdigest(),
  stderr_bytes=len(stderr),stderr_sha256=hashlib.sha256(stderr).hexdigest(),native=native,
  business_dispatch_allowed_by_observed_conditions=False)
 with private_directory(directory,ValueError('private readiness diagnostic directory required'))as opened:
  name='readiness-'+uuid.uuid4().hex+'.json'
  fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=opened)
  with os.fdopen(fd,'w')as output:json.dump(value,output,sort_keys=True);output.flush();os.fsync(output.fileno())
  os.fsync(opened)
 raise SystemExit('UNAVAILABLE: original readiness withheld; diagnostic '+str(directory/name)+'; no dispatch or retry')


def native_failure(stderr):
 lines=[line[len('G2C_STATUS_FAILURE '):]for line in stderr.decode('utf-8',errors='replace').splitlines()if line.startswith('G2C_STATUS_FAILURE ')]
 if len(lines)!=1:return None
 try:value=json.loads(lines[0])
 except ValueError:return None
 fields={'phase','return_code','error_kind','stdout_bytes','stdout_sha256','stderr_bytes','stderr_sha256'}
 phases={'inspect_api_before','inspect_worker_before','proof','financial','inspect_api_after','inspect_worker_after'}
 if(type(value)is not dict or set(value)!=fields or type(value['phase'])is not str or value['phase']not in phases
  or type(value['error_kind'])is not str or value['error_kind']not in('native_exit','native_wait_timeout')
  or value['error_kind']=='native_wait_timeout'and value['return_code']is not None
  or value['error_kind']=='native_exit'and(type(value['return_code'])is not int or value['return_code']==0 or not -255<=value['return_code']<=255)
  or any(type(value[k])is not int or value[k]<0 for k in('stdout_bytes','stderr_bytes'))
  or any(type(value[k])is not str or re.fullmatch('[a-f0-9]{64}',value[k])is None for k in('stdout_sha256','stderr_sha256'))):return None
 return value

def main():
 p=argparse.ArgumentParser();p.add_argument('line',choices=['L','C']);p.add_argument('--purpose',choices=['query','dispatch'],default='query');a=p.parse_args()
 root=Path(__file__).parent;qpath=root/'qualification.json'
 if not qpath.exists():raise SystemExit('UNAVAILABLE: no B qualification; no dispatch')
 qraw=read_private(qpath,131072);q=json.loads(qraw)
 if q['line']!=a.line or q['version']!='G2C-HK-synthetic-qualification.1':raise SystemExit('UNAVAILABLE: wrong B qualification')
 if q['state']!='ACTIVE':
  print(json.dumps(dict(version='G2C-HK-capture-status.1',purpose=a.purpose,status='PREPARED_NOT_ACTIVE'if q['state']=='PREPARED_NOT_ACTIVE'else'STOP_NEW_OR_NOT_READY',source=q['source'],image=q['image'],schema=q['schema'],lease_id=q['lease_id'],business_dispatch_allowed_by_observed_conditions=False,incident_hold=q.get('incident_hold',False))));return
 program=read_private(root/'status_remote.py',65536).decode()
 if hashlib.sha256(program.encode()).hexdigest()!=q['status_remote_sha256']:raise SystemExit('UNAVAILABLE: status program changed')
 remote="import sys,json,hashlib;v=json.loads(sys.stdin.buffer.read(65536));\nif hashlib.sha256(v['program'].encode()).hexdigest()!=v['sha256']:raise ValueError('fixed status program required')\nimport io;sys.stdin=io.TextIOWrapper(io.BytesIO(json.dumps(v['request']).encode()));exec(compile(v['program'],'B_qualified_status','exec'),{'__name__':'__main__'})"
 payload=dict(program=program,sha256=q['status_remote_sha256'],request=dict(qualification=q['server_qualification'],qualification_sha256=hashlib.sha256(qraw).hexdigest(),purpose=a.purpose))
 try:result=subprocess.run(['ssh','-i',q['ssh_key_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',q['host'],'python3 -c '+shlex.quote(remote)],input=json.dumps(payload).encode(),capture_output=True,timeout=90)
 except subprocess.TimeoutExpired as error:
  record_failure(root,q,a.purpose,'ssh_wait_timeout',None,error.stdout or b'',error.stderr or b'',qualification_sha256=hashlib.sha256(qraw).hexdigest())
 if result.returncode:
  record_failure(root,q,a.purpose,'ssh_return',result.returncode,result.stdout,result.stderr,native_failure(result.stderr),qualification_sha256=hashlib.sha256(qraw).hexdigest())
 observed=json.loads(result.stdout)
 if type(observed)is not dict or observed.get('version')!='G2C-HK-capture-status.1'or observed.get('purpose')!=a.purpose or type(observed.get('business_dispatch_allowed_by_observed_conditions'))is not bool:
  raise SystemExit('UNAVAILABLE: original readiness shape/purpose changed')
 if observed.get('status')=='NOT_READY_DEPLOYMENT_IN_PROGRESS':
  if observed['business_dispatch_allowed_by_observed_conditions']:raise SystemExit('UNAVAILABLE: deployment cannot authorize dispatch')
 else:
  if any(observed.get(k)!=q[k]for k in('source','image','schema','lease_id'))or type(observed.get('schema'))is not int:raise SystemExit('UNAVAILABLE: readiness binding changed')
  stamp=datetime.fromisoformat(observed['observed_at'])
  if stamp.tzinfo is None:raise SystemExit('UNAVAILABLE: original readiness timezone missing')
  age=(datetime.now(timezone.utc)-stamp).total_seconds()
  if not -5<=age<=45:raise SystemExit('UNAVAILABLE: stale original readiness')
 if a.purpose=='query'and observed['business_dispatch_allowed_by_observed_conditions']:raise SystemExit('UNAVAILABLE: query cannot authorize business')
 if observed['business_dispatch_allowed_by_observed_conditions']and(observed.get('status')!='READY_FOR_FIXED_WINDOW'or not all(observed.get(k)is True for k in('capture_matches','source_image_matches','healthy','empty_inflight','observation_unchanged'))):raise SystemExit('UNAVAILABLE: dispatch prerequisites absent')
 print(json.dumps(observed,ensure_ascii=False))

if __name__=='__main__':main()
