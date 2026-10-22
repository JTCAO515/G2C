import sys,os,subprocess,json,uuid,stat,time,importlib.util
from pathlib import Path
OUT=Path(__file__).parent;ROOT=OUT.parents[3];MODULE=ROOT/'backend/trip';PG=Path('/opt/homebrew/Cellar/postgresql@17/17.11/bin')
PRIVATE=OUT/('private-pg-'+uuid.uuid4().hex[:10]);DATA=PRIVATE/'data';SOCKET=Path('/private/tmp')/('cj015-owner-repair-'+uuid.uuid4().hex[:10]);PRIVATE.mkdir(mode=0o700);SOCKET.mkdir(mode=0o700)
passroot=MODULE/'private-pg';passroot.mkdir(mode=0o700,exist_ok=True);(passroot/'no-password-file').write_text('');(passroot/'no-password-file').chmod(0o600)
ENV={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TRIP_TEST_SOCKET':str(SOCKET),'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
started=False;result={'private':str(PRIVATE),'socket':str(SOCKET),'port':55435,'postgres':'17.11','role':'cj015_private'}
def run(argv,label,env=ENV):
 p=subprocess.run([str(x) for x in argv],env=env,capture_output=True,text=True);(PRIVATE/(label+'.log')).write_text(p.stdout+p.stderr);p.check_returncode();return p
try:
 run([PG/'initdb','-D',DATA,'--username=cj015_private','--auth-local=trust','--auth-host=reject','--encoding=UTF8','--locale=C','--no-clean'],'initdb')
 run([PG/'pg_ctl','-D',DATA,'-l',PRIVATE/'postgres.log','-o',f'-c listen_addresses= -k {SOCKET} -p 55435 -c unix_socket_permissions=0700','-w','start'],'start');started=True
 sys.path[:0]=[str(MODULE),str(ROOT/'backend/auth'),str(MODULE/'tests')];os.environ.clear();os.environ.update(ENV)
 import psycopg
 with psycopg.connect(host=str(SOCKET),port=55435,user='cj015_private',dbname='postgres',passfile=str(passroot/'no-password-file'),autocommit=True) as c:c.execute("CREATE DATABASE cj015_test ENCODING 'UTF8' TEMPLATE template0")
 import test_trip as m
 with m.connect() as c:
  c.execute((MODULE/'sql/candidate.sql').read_text());identity=c.execute("SELECT current_user,current_database(),current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories')").fetchone();assert identity==('cj015_private','cj015_test',str(DATA),'',str(SOCKET));result['identity']=list(identity)
 run([sys.executable,'-B','-m','pytest',str(MODULE/'tests/test_proposal_read.py'),'-q','-p','no:cacheprovider','--basetemp',PRIVATE/'pytest-temp'],'fixed-suite')
 result['fixed_suite']='12 PASS proposal display and pagination controls'
 def clear():
  with m.connect() as c:c.execute('TRUNCATE cj_trip_receipt,cj_trip_record,cj_trip_proposal,cj_trip_scope');c.execute("INSERT INTO cj_trip_scope VALUES ('A'),('B')")
 # Slow fresh AUTH check on commit runs after the domain's final expiry check.
 clear();r=m.repo();p=m.proposal(expires=int(time.time())+2);a=m.action(r,p)
 principal=m.TrustedPrincipal('issuer','subject','audience',1,1,9999999999)
 class SlowChecker:
  def __init__(self):self.calls=0
  def check(self,token):
   self.calls+=1
   if self.calls==3:
    while time.time()<=p.expires_at+.05:time.sleep(.01)
   return m.AdmissionDecision(m.AdmissionStatus.ALLOWED,m.AdmissionReason.ACCEPTED,principal)
 observed=None
 try:receipt=m.Boundary(SlowChecker(),lambda _:(m.connect,'A'),lambda *args:True).act('synthetic',a);observed='Receipt'
 except BaseException as e:observed=type(e).__name__
 with m.connect() as c:now=float(c.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())').fetchone()[0])
 result['expiry_after_commit_guard']={'outcome':observed,'expired_at_return':now>=p.expires_at,'trip_exists':r.detail('trip1') is not None,'receipt_exists':r.query_action('a1') is not None,'expected':'Conflict/no new Trip or receipt','status':'PASS' if observed=='Conflict' and r.detail('trip1') is None else 'FAIL'}
 # A nontransactional connection must be rejected before any statement can persist.
 clear();r=m.repo();a=m.action(r,m.proposal())
 class CursorFailReceipt:
  def __init__(self,cur):self.cur=cur
  def __getattr__(self,k):return getattr(self.cur,k)
  def execute(self,sql,*args):
   if sql.startswith('INSERT INTO cj_trip_receipt'):raise OSError('synthetic before receipt insert')
   return self.cur.execute(sql,*args)
 class Autocommit:
  def __init__(self):self.c=m.connect();self.c.autocommit=True
  def __getattr__(self,k):return getattr(self.c,k)
  def cursor(self):return CursorFailReceipt(self.c.cursor())
 error=None
 try:m.repo(factory=Autocommit).act(a)
 except BaseException as e:error=type(e).__name__
 result['autocommit_partial']={'error':error,'trip_exists':r.detail('trip1') is not None,'receipt_exists':r.query_action('a1') is not None,'expected':'Reject autocommit before any effect','status':'PASS' if r.detail('trip1') is None else 'FAIL'}
 # Cleanup must not replace the immutable receipt or the primary CommitUnknown.
 cleanup=[]
 for lost_ack in [False,True]:
  clear();r=m.repo();a=m.action(r,m.proposal())
  class CloseFailure:
   def __init__(self):self.c=m.connect()
   def __getattr__(self,k):return getattr(self.c,k)
   def commit(self):
    self.c.commit()
    if lost_ack:raise ConnectionError('synthetic lost ACK')
   def close(self):self.c.close();raise OSError('synthetic cleanup failure')
  observed=None
  try:m.repo(factory=CloseFailure).act(a);observed='Receipt'
  except BaseException as e:observed=type(e).__name__
  exists=r.query_action('a1') is not None;assert exists
  cleanup.append({'lost_ack':lost_ack,'outcome':observed,'original_receipt_exists':exists,'expected':'CommitUnknown' if lost_ack else 'Receipt','status':'PASS' if observed==('CommitUnknown' if lost_ack else 'Receipt') else 'FAIL'})
 result['cleanup_outcomes']=cleanup
 run([sys.executable,'-B',MODULE/'tests/restart_probe.py','seed'],'restart-seed')
 run([PG/'pg_ctl','-D',DATA,'-m','fast','-w','stop'],'restart-stop');started=False
 run([PG/'pg_ctl','-D',DATA,'-l',PRIVATE/'postgres.log','-o',f'-c listen_addresses= -k {SOCKET} -p 55435 -c unix_socket_permissions=0700','-w','start'],'restart-start');started=True
 run([sys.executable,'-B',MODULE/'tests/restart_probe.py','read'],'restart-read');result['restart_original_v1_latest_v2']='PASS'
finally:
 if started or (DATA/'postmaster.pid').exists():run([PG/'pg_ctl','-D',DATA,'-m','fast','-w','stop'],'final-stop')
 result['postmaster_pid_absent']=not (DATA/'postmaster.pid').exists();result['sockets_absent']=not list(SOCKET.glob('.s.PGSQL.*'));result['modes']={str(p):oct(stat.S_IMODE(p.stat().st_mode)) for p in [PRIVATE,DATA,SOCKET] if p.exists()}
 (OUT/'pg-results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
