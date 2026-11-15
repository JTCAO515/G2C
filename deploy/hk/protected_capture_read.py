"""B-selected original read only. Credentials use stdin; output is fresh0600."""
import argparse,hashlib,json,os,re,shlex,stat,subprocess
from pathlib import Path

def private(path,limit):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb')as f:
  m=os.fstat(f.fileno())
  if not stat.S_ISREG(m.st_mode)or m.st_uid!=os.getuid()or stat.S_IMODE(m.st_mode)!=0o600:raise ValueError('owned0600 resource required')
  raw=f.read(limit+1)
 if len(raw)>limit:raise ValueError('bounded original resource required')
 return raw


HOST_PROGRAM=r'''
import fcntl,json,sys,subprocess,hashlib,os,stat,time
from pathlib import Path
v=json.loads(sys.stdin.buffer.read(131073));path=Path(v['qualification']);raw=path.read_bytes();q=json.loads(raw)
if hashlib.sha256(raw).hexdigest()!=v['qualification_sha256']:raise ValueError('qualified original changed')
if hashlib.sha256(v['program'].encode()).hexdigest()!=q['reader_sha256']['server']:raise ValueError('fixed original reader required')
lock=Path('/srv/g2c-beta/probes/application-deploy.lock').open('r');fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
reader_fd=os.open('/srv/g2c-beta/probes/qualified-reader.lock',os.O_RDONLY|os.O_NOFOLLOW);info=os.fstat(reader_fd)
if not stat.S_ISREG(info.st_mode)or info.st_uid!=os.geteuid()or stat.S_IMODE(info.st_mode)!=0o600:raise ValueError('owned private reader serialization lock required')
wait_until=time.monotonic()+10
while True:
 try:fcntl.flock(reader_fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
 except BlockingIOError:
  if time.monotonic()>=wait_until:raise ValueError('original reader queue deadline reached')
  time.sleep(.1)
# Recheck the selector after waiting; raw expiry remains native-reader-owned.
if path.read_bytes()!=raw:raise ValueError('qualification changed while waiting')
def current():return json.loads(subprocess.check_output(['docker','inspect','g2c-beta-worker-1'],timeout=10))[0]
before=current();mounts={m['Destination']:m for m in before['Mounts']}
if(before['Image']!=q['image']or before['Config']['Labels']['org.opencontainers.image.revision']!=q['source']or not before['State']['Running']):raise ValueError('original source/image changed')
for target,source in(('/run/tool-evidence/qualification.json',str(path)),('/run/tool-evidence/window.json',str(Path(q['server_directory'])/'window.json')),('/tool-evidence',q['artifact_directory'])):
 if mounts.get(target,{}).get('Source')!=source:raise ValueError('exact original reader mounts required')
if mounts['/run/tool-evidence/qualification.json']['RW']or mounts['/run/tool-evidence/window.json']['RW']:raise ValueError('read-only selection mounts required')
pending=Path('/srv/g2c-beta/probes/qualified-reader.inflight.json')
if pending.exists()or pending.is_symlink():raise ValueError('previous native reader outcome pending; B reconciliation required')
import uuid
nonce='g2c-reader-'+uuid.uuid4().hex
record=json.dumps(dict(version='G2C-native-reader-intent.1',worker_id=before['Id'],source=q['source'],image=q['image'],lease_id=q['lease_id'],message_id=v['request']['message_id'],kind=v['request']['kind'],nonce=nonce),sort_keys=True).encode()
fd=os.open(str(pending),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb')as output:output.write(record);output.flush();os.fsync(output.fileno())
directory_fd=os.open(str(pending.parent),os.O_RDONLY|os.O_DIRECTORY)
try:os.fsync(directory_fd)
finally:os.close(directory_fd)
try:
 r=subprocess.run(['docker','exec','-i',before['Id'],'python','-B','-c',v['program'],nonce],input=json.dumps(v['request']).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
except subprocess.TimeoutExpired as error:
 # The Docker CLI may die while its exec child survives. Keep the intent;
 # releasing flock never authorizes a replacement until B proves termination.
 diagnostic=dict(version='G2C-protected-reader-failure.1',source=q['source'],image=q['image'],lease_id=q['lease_id'],cohort=v['request']['cohort'],kind=v['request']['kind'],message_id=v['request']['message_id'],phase='native_wait_timeout',return_code=None,stderr_sha256=hashlib.sha256(error.stderr or b'').hexdigest())
 sys.stderr.write('G2C_READER_FAILURE '+json.dumps(diagnostic)+'\n');raise SystemExit(1)
if r.returncode:
 diagnostic=dict(version='G2C-protected-reader-failure.1',source=q['source'],image=q['image'],lease_id=q['lease_id'],cohort=v['request']['cohort'],kind=v['request']['kind'],message_id=v['request']['message_id'],phase='native_read',return_code=r.returncode,stderr_sha256=hashlib.sha256(r.stderr).hexdigest())
 sys.stderr.write('G2C_READER_FAILURE '+json.dumps(diagnostic)+'\n');raise SystemExit(1)
after=current()
if(after['Id'],after['Image'],after['Config']['Labels']['org.opencontainers.image.revision'])!=(before['Id'],q['image'],q['source']):raise ValueError('reader changed during original read')
if path.read_bytes()!=raw:raise ValueError('qualification changed during original read')
if pending.read_bytes()!=record:raise ValueError('original native reader intent changed')
pending.unlink()
sys.stdout.buffer.write(r.stdout)
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--qualification',type=Path,required=True);p.add_argument('line',choices=['L','C']);p.add_argument('message_id');p.add_argument('kind',choices=['inventory','bindings','clock','input','artifact','wire_input','meter','fee']);p.add_argument('--cohort');p.add_argument('--locale',choices=['zh','en']);p.add_argument('--operation-id');p.add_argument('--expected-input-sha256');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if (a.kind in('inventory','bindings','clock'))!=(a.operation_id is None):p.error('exact original operation selector required')
 if a.expected_input_sha256 is not None and re.fullmatch('[a-f0-9]{64}',a.expected_input_sha256)is None:p.error('original input SHA256 required')
 qpath=a.qualification;root=qpath.parent;qraw=private(qpath,131072);q=json.loads(qraw)
 if q['version']!='G2C-HK-synthetic-qualification.1'or q['line']!=a.line or q['state']not in('ACTIVE','STOP_NEW','CLOSED'):p.error('B-issued original-read qualification required')
 cohort=a.cohort
 if cohort is None:
  if len(q['cohorts'])!=1:p.error('explicit cohort required')
  cohort=next(iter(q['cohorts']))
 if cohort not in q['cohorts']:p.error('qualified cohort required')
 selected=[m for m in q['cohorts'][cohort]['messages']if m['message_id']==a.message_id]
 if len(selected)!=1:p.error('original MID outside fixed cohort')
 message=selected[0]
 if a.locale is not None and a.locale!=message['locale']:p.error('locale differs from original selection')
 identities=[i for i in q['identities']if i['subject']==message['subject']and i['locale']in(message['locale'],'both')]
 if len(identities)!=1:p.error('one original subject/locale credential required')
 identity=identities[0];material=private(identity['token_file'],16384)
 if identity['token_format']=='plain':token=material.decode().strip()
 elif identity['token_format']=='grant_json':token=json.loads(material)['access_token']
 else:p.error('qualified credential format required')
 if type(token)is not str or not token or len(token)>4096:p.error('bounded original credential required')
 if a.output.exists():p.error('fresh output required; never overwrite original evidence')
 program=(root/'read_server.py').read_text()
 if hashlib.sha256(program.encode()).hexdigest()!=q['reader_sha256']['server']:p.error('original reader program changed')
 request=dict(token=token,subject=message['subject'],message_id=a.message_id,kind=a.kind,operation_id=a.operation_id,
  expected_source=q['source'],cohort=cohort,expected_input_sha256=a.expected_input_sha256)
 remote=HOST_PROGRAM
 payload=dict(program=program,request=request,qualification=q['server_qualification'],qualification_sha256=hashlib.sha256(qraw).hexdigest())
 r=subprocess.run(['ssh','-i',q['ssh_key_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',q['host'],'python3 -c '+shlex.quote(remote)],input=json.dumps(payload).encode(),capture_output=True,timeout=90)
 if r.returncode:
  lines=[s[len('G2C_READER_FAILURE '):]for s in r.stderr.decode('utf-8',errors='replace').splitlines()if s.startswith('G2C_READER_FAILURE ')]
  if len(lines)==1:
   try:diagnostic=json.loads(lines[0])
   except ValueError:raise SystemExit('UNAVAILABLE: original failure diagnostic malformed')from None
   expected=dict(version='G2C-protected-reader-failure.1',source=q['source'],image=q['image'],lease_id=q['lease_id'],cohort=cohort,kind=a.kind,message_id=a.message_id)
   if(type(diagnostic)is not dict or set(diagnostic)!=set(expected)|{'phase','return_code','stderr_sha256'}or any(diagnostic.get(k)!=v for k,v in expected.items())or diagnostic['phase']not in('native_read','native_wait_timeout')or(diagnostic['phase']=='native_wait_timeout'and diagnostic['return_code']is not None)or(diagnostic['phase']=='native_read'and(type(diagnostic['return_code'])is not int or not -255<=diagnostic['return_code']<=255 or diagnostic['return_code']==0)) or type(diagnostic['stderr_sha256'])is not str or re.fullmatch('[a-f0-9]{64}',diagnostic['stderr_sha256'])is None):raise SystemExit('UNAVAILABLE: original failure diagnostic binding changed')
   raise SystemExit('UNAVAILABLE: native protected read refused; '+json.dumps(diagnostic,sort_keys=True))
  raise SystemExit('UNAVAILABLE: native protected read refused; no dispatch or retry')
 result=json.loads(r.stdout)
 expected=dict(version='G2C-protected-capture-read.3',source=q['source'],image=q['image'],schema=q['schema'],lease_id=q['lease_id'],cohort=cohort,kind=a.kind,message_id=a.message_id)
 if(type(result)is not dict or any(result.get(k)!=v for k,v in expected.items())or type(result.get('schema'))is not int):
  raise SystemExit('UNAVAILABLE: original response binding changed')
 fields=set(expected)|{'status'}
 if result.get('status')=='READ':
  if set(result)!=fields|{'utf8'}or type(result['utf8'])is not str:raise SystemExit('UNAVAILABLE: original response shape changed')
 elif result.get('status')=='UNAVAILABLE':
  if set(result)!=fields|{'reason'}or type(result['reason'])is not str:raise SystemExit('UNAVAILABLE: original denial shape changed')
 else:raise SystemExit('UNAVAILABLE: original response status changed')
 fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as f:f.write(r.stdout);f.flush();os.fsync(f.fileno())
 print(json.dumps({k:result[k]for k in('version','status','source','kind','message_id','cohort')},ensure_ascii=False))

if __name__=='__main__':main()
