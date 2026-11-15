import importlib.util,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import subprocess
import fcntl
import hashlib
import signal

READER=Path(__file__).resolve().parents[1]/'hk/protected_capture_read.py'

def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


@pytest.fixture
def host(tmp_path):
 root=tmp_path/'probes';root.mkdir(mode=0o700)
 for name in('application-deploy.lock','qualified-reader.lock'):
  path=root/name;path.touch(mode=0o600)
 q=dict(image='sha256:'+'b'*64,source='a'*40,lease_id='fixture-only',
  server_directory=str(root),artifact_directory=str(root/'artifacts'),
  reader_sha256={'server':hashlib.sha256(b'trusted-fixture').hexdigest()})
 path=root/'qualification.json';raw=json.dumps(q).encode();path.write_bytes(raw);path.chmod(0o600)
 worker=dict(Id='fixture-original-worker',Image=q['image'],Config={'Labels':{'org.opencontainers.image.revision':q['source']}},
  State={'Running':True},Mounts=[dict(Destination=dst,Source=src,RW=rw)for dst,src,rw in(
   ('/run/tool-evidence/qualification.json',str(path),False),
   ('/run/tool-evidence/window.json',str(root/'window.json'),False),('/tool-evidence',q['artifact_directory'],True))])
 program=module(READER,'host_subject').HOST_PROGRAM.replace('/srv/g2c-beta/probes',str(root))
 wrapper=tmp_path/'docker-fixture.py'
 wrapper.write_text('''import sys,json,os,time,subprocess
from pathlib import Path
v=json.load(sys.stdin);mode=v.pop('mode');worker=v.pop('worker');root=Path(v.pop('fixture_root'));program=v.pop('host_program');inspections=0
def inspect(args,**kwargs):
 global inspections
 assert args[:2]==['docker','inspect']and kwargs['timeout']==10
 inspections+=1
 if mode=='changed_worker'and inspections>1:worker['Id']='replaced-worker'
 return json.dumps([worker]).encode()
def event(kind):
 fd=os.open(root/'events',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
 with os.fdopen(fd,'w')as f:f.write(kind+'\\n');f.flush();os.fsync(f.fileno())
def native(args,**kwargs):
 assert args[:3]==['docker','exec','-i']and kwargs['timeout']==45
 event('start')
 if mode=='native_error':return subprocess.CompletedProcess(args,137,b'private-output',b'fixture-private-stderr')
 if mode=='timeout':
  child=subprocess.Popen([sys.executable,'-c',"import time;from pathlib import Path;p=Path(__import__('sys').argv[1]);p.write_text('alive');time.sleep(30)",str(root/'alive')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  (root/'child.pid').write_text(str(child.pid))
  limit=time.monotonic()+5
  while not(root/'alive').exists():
   assert time.monotonic()<limit;time.sleep(.01)
  raise subprocess.TimeoutExpired(args,45,stderr=b'fixture-private-stderr')
 time.sleep(.2);event('end');return subprocess.CompletedProcess(args,0,b'original-result',b'')
subprocess.check_output=inspect;subprocess.run=native
if mode=='queue_timeout':
 ticks=iter((0,11));time.monotonic=lambda:next(ticks)
import io
sys.stdin=io.TextIOWrapper(io.BytesIO(json.dumps(v).encode()))
exec(compile(program,'original-host-program','exec'),{'__name__':'__main__'})
''')
 payload=dict(qualification=str(path),qualification_sha256=hashlib.sha256(raw).hexdigest(),program='trusted-fixture',
  request=dict(message_id='original',kind='inventory',cohort='fixture',token='fixture-token-not-live'),worker=worker,
  fixture_root=str(root),host_program=program)
 def launch(mode):
  child=subprocess.Popen([sys.executable,'-B',str(wrapper)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  child.stdin.write(json.dumps(dict(payload,mode=mode)).encode());child.stdin.close();child.stdin=None
  return child
 try:yield root,launch
 finally:
  if(root/'child.pid').exists():
   try:os.kill(int((root/'child.pid').read_text()),signal.SIGTERM)
   except ProcessLookupError:pass


def test_real_processes_serialize_the_native_read_and_clear_only_on_success(host):
 root,launch=host;a=launch('normal');b=launch('normal')
 for child in(a,b):
  stdout,stderr=child.communicate(timeout=10)
  assert child.returncode==0 and stdout==b'original-result'and not stderr
 assert(root/'events').read_text().splitlines()==['start','end','start','end']
 assert not(root/'qualified-reader.inflight.json').exists()


def test_timeout_keeps_intent_and_blocks_next_reader_while_native_child_lives(host):
 root,launch=host;first=launch('timeout');out,error=first.communicate(timeout=10)
 assert first.returncode==1 and not out
 diagnostic=json.loads(next(line[len('G2C_READER_FAILURE '):]for line in error.decode().splitlines()if line.startswith('G2C_READER_FAILURE ')))
 assert diagnostic['phase']=='native_wait_timeout'and diagnostic['return_code']is None
 assert b'fixture-private-stderr'not in error
 os.kill(int((root/'child.pid').read_text()),0)
 assert(root/'qualified-reader.inflight.json').exists()
 second=launch('normal');out,error=second.communicate(timeout=10)
 assert second.returncode!=0 and not out and b'previous native reader outcome pending'in error
 assert(root/'events').read_text().splitlines()==['start']


@pytest.mark.parametrize('mode',['native_error','changed_worker'])
def test_nonzero_or_post_read_worker_drift_retains_unknown_intent(host,mode):
 root,launch=host;child=launch(mode);out,error=child.communicate(timeout=10)
 assert child.returncode!=0 and not out and(root/'qualified-reader.inflight.json').exists()
 assert b'private-output'not in error and b'fixture-private-stderr'not in error
 if mode=='native_error':
  diagnostic=json.loads(next(line[len('G2C_READER_FAILURE '):]for line in error.decode().splitlines()if line.startswith('G2C_READER_FAILURE ')))
  assert diagnostic['phase']=='native_read'and diagnostic['return_code']==137


def test_queue_deadline_refuses_without_starting_native_process(host):
 root,launch=host
 with(root/'qualified-reader.lock').open('r')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  child=launch('queue_timeout');out,error=child.communicate(timeout=10)
 assert child.returncode!=0 and not out and b'queue deadline reached'in error
 assert not(root/'events').exists()and not(root/'qualified-reader.inflight.json').exists()

@pytest.fixture
def package(tmp_path,monkeypatch):
 (tmp_path/'read_server.py').write_text('trusted native reader fixture')
 q=dict(version='G2C-HK-synthetic-qualification.1',state='PREPARED_NOT_ACTIVE',incident_hold=True,
  line='C',source='a'*40,image='sha256:'+'b'*64,schema=55,lease_id='fixture-not-a-live-lease',
  cohorts={'national16':dict(messages=[dict(subject='fixture-C',message_id='original',locale='zh')])},
  identities=[dict(subject='fixture-C',locale='zh',token_file=str(tmp_path/'token'),token_format='plain')])
 import hashlib
 q.update(reader_sha256={'server':hashlib.sha256((tmp_path/'read_server.py').read_bytes()).hexdigest()},
  server_qualification='/fixture-only/qualification.json',ssh_key_file='/fixture-only/no-key',host='fixture.invalid')
 p=tmp_path/'qualification.json';p.write_text(json.dumps(q));p.chmod(0o600)
 token=tmp_path/'token';token.write_text('fixture-token-not-live');token.chmod(0o600)
 calls=[]
 def forbidden(*a,**kw):calls.append(a);raise AssertionError('offline controls prohibit subprocess/network')
 monkeypatch.setattr('subprocess.run',forbidden)
 return tmp_path,q,p,calls


@pytest.mark.parametrize('fault',['prepared','wrong_mid','wrong_cohort','wrong_locale','wrong_owner'])
def test_reader_refuses_before_network(package,monkeypatch,fault):
 root,q,p,calls=package
 if fault!='prepared':q['state']='ACTIVE';p.write_text(json.dumps(q))
 argv=['read','--qualification',str(p),'C','other'if fault=='wrong_mid'else'original','inventory','--cohort','other'if fault=='wrong_cohort'else'national16','--locale','en'if fault=='wrong_locale'else'zh','--output',str(root/'result')]
 if fault=='wrong_owner':q['identities'][0]['subject']='other';p.write_text(json.dumps(q))
 m=module(READER,'reader_'+fault);monkeypatch.setattr(sys,'argv',argv)
 with pytest.raises(SystemExit):m.main()
 assert calls==[]and not(root/'result').exists()


def test_token_symlink_is_not_followed(package,monkeypatch):
 root,q,p,calls=package;q['state']='ACTIVE';q['identities'][0]['token_file']=str(root/'link');p.write_text(json.dumps(q));(root/'link').symlink_to(root/'token')
 m=module(READER,'readerlink');monkeypatch.setattr(sys,'argv',['read','--qualification',str(p),'C','original','inventory','--cohort','national16','--output',str(root/'result')])
 with pytest.raises(OSError):m.main()
 assert calls==[]


def test_reader_preserves_original_envelope_and_fresh0600(package,monkeypatch,capsys):
 root,q,p,calls=package;q['state']='ACTIVE';p.write_text(json.dumps(q))
 response=dict(version='G2C-protected-capture-read.3',status='READ',source=q['source'],image=q['image'],schema=55,lease_id=q['lease_id'],cohort='national16',kind='inventory',message_id='original',utf8='{"original":"bytes"}')
 def original(args,**kw):
  calls.append(args);request=json.loads(kw['input'])['request'];assert request['token']=='fixture-token-not-live'
  assert request['message_id']=='original'and request['kind']=='inventory'
  return SimpleNamespace(returncode=0,stdout=json.dumps(response).encode(),stderr=b'')
 m=module(READER,'readerpositive');monkeypatch.setattr(m.subprocess,'run',original)
 output=root/'result';monkeypatch.setattr(sys,'argv',['read','--qualification',str(p),'C','original','inventory','--cohort','national16','--output',str(output)]);m.main()
 assert json.loads(output.read_bytes())==response and output.stat().st_mode&0o777==0o600
 assert 'fixture-token'not in capsys.readouterr().out
 with pytest.raises(SystemExit):m.main()
 assert len(calls)==1


@pytest.mark.parametrize('field,value',[('source','f'*40),('image','sha256:'+'f'*64),('schema',54),('lease_id','foreign'),('cohort','foreign'),('kind','input'),('message_id','foreign'),('version','G2C-protected-capture-read.2')])
def test_original_response_binding_rejected_before_publication(package,monkeypatch,field,value):
 root,q,p,calls=package;q['state']='ACTIVE';p.write_text(json.dumps(q))
 response=dict(version='G2C-protected-capture-read.3',status='READ',source=q['source'],image=q['image'],schema=55,lease_id=q['lease_id'],cohort='national16',kind='inventory',message_id='original',utf8='private original')
 response[field]=value
 m=module(READER,'readerforeign_'+field)
 monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=json.dumps(response).encode()))
 output=root/'result';monkeypatch.setattr(sys,'argv',['read','--qualification',str(p),'C','original','inventory','--cohort','national16','--output',str(output)])
 with pytest.raises(SystemExit):m.main()
 assert not output.exists()


@pytest.mark.parametrize('fault',['none','timeout','wrong_mid','extra_private','missing_phase','invented_timeout_code'])
def test_reader_failure_diagnostics_bound_private_and_never_saved(package,monkeypatch,fault):
 root,q,p,calls=package;q['state']='ACTIVE';p.write_text(json.dumps(q))
 diagnostic=dict(version='G2C-protected-reader-failure.1',source=q['source'],image=q['image'],lease_id=q['lease_id'],cohort='national16',kind='inventory',message_id='original',phase='native_read',return_code=137,stderr_sha256='d'*64)
 if fault=='timeout':diagnostic.update(phase='native_wait_timeout',return_code=None)
 elif fault=='wrong_mid':diagnostic['message_id']='foreign'
 elif fault=='extra_private':diagnostic['private']='must-not-publish'
 elif fault=='missing_phase':del diagnostic['phase']
 elif fault=='invented_timeout_code':diagnostic.update(phase='native_wait_timeout',return_code=124)
 m=module(READER,'reader_failure_'+fault)
 monkeypatch.setattr(m.subprocess,'run',lambda*a,**kw:SimpleNamespace(returncode=1,stdout=b'private raw must not escape',stderr=('G2C_READER_FAILURE '+json.dumps(diagnostic)).encode()))
 output=root/'result';monkeypatch.setattr(sys,'argv',['read','--qualification',str(p),'C','original','inventory','--cohort','national16','--output',str(output)])
 with pytest.raises(SystemExit)as error:m.main()
 message=str(error.value);assert not output.exists()and'private raw'not in message and'fixture-token'not in message and'must-not-publish'not in message
 if fault in('none','timeout'):assert '"return_code"'in message
 else:assert 'diagnostic binding changed'in message
