"""Opt-in new Unix-only cluster; no external DSN, no existing server restart."""
from pathlib import Path
from dataclasses import asdict
import json
import os
import subprocess
import tempfile
import psycopg
from cj_usage.core import Config,Ledger,Run,Attempt,Command,Receipt
from cj_usage.codec import encode
from cj_usage.postgres import PostgresRepository,CommitUnknown,RepositoryUnavailable
from cj_usage.read_status import ReadUnavailable

BIN=Path('/opt/homebrew/opt/postgresql@17/bin')
ROOT=Path(tempfile.mkdtemp(prefix='cj008-read-',dir='/tmp'))
DATA,SOCKET,PASS=ROOT/'data',ROOT/'socket',ROOT/'empty.pgpass'
SOCKET.mkdir(mode=0o700);PASS.touch(mode=0o600)
PORT=55439
ENV={'PATH':str(BIN)+':/usr/bin:/bin','LANG':'C','LC_ALL':'C',
     'PGPASSFILE':str(PASS),'PGSERVICEFILE':str(ROOT/'absent-service')}
for key in list(os.environ):
    if key.startswith('PG'):del os.environ[key]
os.environ.update({k:v for k,v in ENV.items() if k.startswith('PG')})
checks=[];statements=[];authority=[True]

def ctl(*args):
    p=subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),*args],env=ENV,text=True,capture_output=True)
    if p.returncode:raise RuntimeError('private pg_ctl failed')
def connect(user='cj008_read_a'):
    return psycopg.connect(host=str(SOCKET),port=PORT,dbname='postgres',user=user,
        password='',passfile=str(PASS),connect_timeout=5,
        options='-c statement_timeout=5000 -c lock_timeout=4000')
def guard():
    if not authority[0]:raise ReadUnavailable('synthetic current context revoked')
def record(name,ok):
    assert ok,name
    checks.append(name);print('PASS',name,flush=True)
def rejects(kind,fn):
    try:fn()
    except kind:return True
    return False

class Cursor:
    def __init__(self,c):self.c=c
    def execute(self,sql,args=None):
        statements.append(sql)
        result=self.c.execute(sql,args)
        if sql.startswith('SET '):
            # Separate test-only observer, after READ ONLY was set.
            with self.c.connection.cursor() as probe:
                assert probe.execute("SELECT current_setting('transaction_read_only')").fetchone()[0]=='on'
        return result
    def fetchone(self):return self.c.fetchone()
    def close(self):self.c.close()
class Conn:
    autocommit=False
    def __init__(self,mode='normal'):self.c=connect();self.mode=mode
    def cursor(self):return Cursor(self.c.cursor())
    def commit(self):
        self.c.commit()
        if self.mode=='ack':raise OSError('synthetic ACK loss')
    def rollback(self):self.c.rollback()
    def close(self):
        self.c.close()
        if self.mode=='revoke':authority[0]=False
        if self.mode=='close':raise OSError('synthetic close failure')

def read(scope='cj008_read_a',mode='normal',attempt='a',project=None):
    return PostgresRepository(lambda:Conn(mode),scope).read_status(attempt,
        guard=guard,max_response_bytes=4096,project=project)
started=False
try:
    p=subprocess.run([str(BIN/'initdb'),'-D',str(DATA),'-U','cj008_read_admin',
        '--no-locale','--encoding=UTF8','--auth-local=trust','--auth-host=reject'],
        env=ENV,text=True,capture_output=True)
    if p.returncode:raise RuntimeError('private initdb failed')
    (ROOT/'initdb.log').write_text(p.stdout+p.stderr)
    with (DATA/'postgresql.conf').open('a') as f:
        f.write("\nlisten_addresses=''\nport=55439\nunix_socket_directories='"+str(SOCKET)+"'\nunix_socket_permissions=0700\n")
    ctl('-l',str(ROOT/'server.log'),'-w','start');started=True
    cfg=Config('synthetic-unit',10,0,1000,20,3,20,50)
    cmd=Command('a','operation','run','model','a'*64,6,2)
    ledger=Ledger(cfg,{'a':Attempt(cmd,'unknown')},{'run':Run(100,1)},100)
    settled=Ledger(cfg,{'a':Attempt(cmd,'settled',Receipt('a','receipt','synthetic-unit',0,0))}, {'run':Run(100,1)},100)
    with connect('cj008_read_admin') as c:
        identity=c.execute("SELECT current_user,current_database(),current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_setting('port'),version()").fetchone()
        assert identity[:6]==('cj008_read_admin','postgres',str(DATA),'',str(SOCKET),str(PORT))
        assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
        print('IDENTITY_BEFORE_SQL',json.dumps(identity),flush=True)
        c.execute((Path(__file__).parents[1]/'sql/001_candidate.sql').read_text())
        for role,value in [('cj008_read_a',ledger),('cj008_read_b',settled)]:
            c.execute('CREATE ROLE '+role+' LOGIN NOSUPERUSER NOBYPASSRLS')
            c.execute('GRANT SELECT ON public.cj_usage_ledger_candidate TO '+role)
            c.execute('INSERT INTO public.cj_usage_ledger_candidate VALUES (%s,17,1,%s::jsonb)',(role,encode(value)))
        c.execute('CREATE POLICY fixture_scope ON public.cj_usage_ledger_candidate USING (scope_id=current_user)')
    with connect() as c:
        permissions=c.execute("SELECT rolsuper,rolbypassrls,has_table_privilege(current_user,'public.cj_usage_ledger_candidate','UPDATE'),has_table_privilege(current_user,'public.cj_usage_ledger_candidate','INSERT') FROM pg_roles WHERE rolname=current_user").fetchone()
        record('runtime SELECT only non-superuser non-bypassrls',permissions==(False,False,False,False))
    before={}
    with connect('cj008_read_admin') as c:
        before=c.execute('SELECT scope_id,revision,format_version,ledger FROM public.cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
    value=json.loads(read())
    record('unknown amount remains null and source private digest absent',value['confirmed_units'] is None and 'input_digest' not in value)
    record('same original run and operation',value['run_id']=='run' and value['operation_id']=='operation')
    record('cross-scope RLS denial',rejects(RepositoryUnavailable,lambda:read(scope='cj008_read_b')))
    record('missing attempt denial',rejects(RepositoryUnavailable,lambda:read(attempt='missing')))
    record('connection close revocation withholds bytes',rejects(ReadUnavailable,lambda:read(mode='revoke')))
    authority[0]=True
    record('connection close failure withholds bytes',rejects(ReadUnavailable,lambda:read(mode='close')))
    record('read commit ACK unknown withholds bytes',rejects(CommitUnknown,lambda:read(mode='ack')))
    def project(data):authority[0]=False;return b'{"result":'+data+b'}'
    record('projection final envelope revoke withholds',rejects(ReadUnavailable,lambda:read(project=project)))
    authority[0]=True
    record('only SET READ ONLY and plain SELECT issued', all(s.startswith('SET TRANSACTION') or (s.startswith('SELECT ') and 'FOR UPDATE' not in s) for s in statements))
    with connect('cj008_read_admin') as c:
        after=c.execute('SELECT scope_id,revision,format_version,ledger FROM public.cj_usage_ledger_candidate ORDER BY scope_id').fetchall()
    record('all rows revisions and ledgers unchanged',before==after)
    print('RESULT',json.dumps({'checks':len(checks),'root':str(ROOT),'driver':psycopg.__version__,'real_auth':'UNRUN','real_fee':'UNRUN'}),flush=True)
finally:
    if started:ctl('-m','fast','-w','stop')
    result=subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'status'],env=ENV,capture_output=True)
    print('STOP_READBACK',result.returncode,'root',str(ROOT),flush=True)
    if result.returncode!=3:raise RuntimeError('stop not confirmed')
