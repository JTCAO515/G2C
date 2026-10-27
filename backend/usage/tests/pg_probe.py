"""Opt-in private empty PostgreSQL cluster probe; never accepts a DSN."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import psycopg
from cj_usage.core import Config, Ledger, Meter, Command, Receipt, Blocked
from cj_usage.codec import encode, decode, CorruptLedger
from cj_usage.postgres import PostgresRepository, CommitUnknown, RepositoryUnavailable
from cj_usage.local_exit import LocalExit

BIN = Path(os.environ.get('CJ_PG17_BINDIR', '/opt/homebrew/opt/postgresql@17/bin'))
ROOT = Path(tempfile.mkdtemp(prefix='cj008-pg-', dir='/tmp'))
DATA, SOCKET, PASS = ROOT/'data', ROOT/'socket', ROOT/'empty.pgpass'
SOCKET.mkdir(mode=0o700)
PASS.touch(mode=0o600)
PORT = 55438  # Unix socket namespace only; TCP listen is disabled.
ENV = {'PATH': str(BIN)+':/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
       'PGPASSFILE': str(PASS), 'PGSERVICEFILE': str(ROOT/'absent-service')}
CFG = Config('synthetic-unit', 10, 0, 1000, 30, 3, 30, 50)
checks = []


def command(name, reserve=1):
    return Command(name, 'operation', 'run', 'model', 'a'*64, reserve, 1)


def ctl(*args):
    result = subprocess.run([str(BIN/'pg_ctl'), '-D', str(DATA), *args],
                            env=ENV, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('private pg_ctl failed: '+result.stdout+result.stderr)


def connect(user='cj008_a', **kwargs):
    # Explicit parameters, no inherited PG* settings, no service/old DSN.
    return psycopg.connect(host=str(SOCKET), port=PORT, dbname='postgres',
                           user=user, password='', passfile=str(PASS),
                           connect_timeout=5, options='-c statement_timeout=5000 -c lock_timeout=4000',
                           **kwargs)


def meter(scope='cj008_a', factory=None):
    return Meter(PostgresRepository(factory or (lambda: connect(scope)), scope), CFG, lambda: 100)


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS', name, flush=True)


def rejects(error, action):
    try: action()
    except error: return True
    return False


def reset(scope='cj008_a'):
    with connect('cj008_admin') as c:
        c.execute('UPDATE public.cj_usage_ledger_candidate SET ledger=%s::jsonb, revision=0 WHERE scope_id=%s', (encode(Ledger(CFG)), scope))


class Wrapped:
    def __init__(self, conn, mode): self.conn, self.mode = conn, mode
    def __getattr__(self, name): return getattr(self.conn, name)
    def commit(self):
        if self.mode == 'before': raise OSError('synthetic before commit')
        self.conn.commit()
        if self.mode == 'after': raise OSError('synthetic ACK lost')
    def close(self):
        self.conn.close()
        if self.mode == 'cleanup': raise OSError('synthetic cleanup failure')


started = False
try:
    # Scrub inherited libpq variables for psycopg as well as child tools.
    for key in list(os.environ):
        if key.startswith('PG'): del os.environ[key]
    os.environ.update({k: v for k,v in ENV.items() if k.startswith('PG')})
    result = subprocess.run([str(BIN/'initdb'), '-D', str(DATA), '-U', 'cj008_admin',
        '--no-locale', '--encoding=UTF8', '--auth-local=trust', '--auth-host=reject'],
        env=ENV, text=True, capture_output=True)
    if result.returncode: raise RuntimeError('private initdb failed')
    (ROOT/'initdb.log').write_text(result.stdout+result.stderr)
    with (DATA/'postgresql.conf').open('a') as f:
        f.write("\nlisten_addresses = ''\nport = 55438\nunix_socket_directories = '"+str(SOCKET)+"'\nunix_socket_permissions = 0700\n")
    ctl('-l', str(ROOT/'server.log'), '-w', 'start'); started = True
    with connect('cj008_admin') as c:
        identity = c.execute("SELECT current_user,current_database(),current_setting('data_directory'),current_setting('listen_addresses'),current_setting('unix_socket_directories'),current_setting('port'),version()").fetchone()
        assert identity[:6] == ('cj008_admin','postgres',str(DATA),'',str(SOCKET),str(PORT))
        assert c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0
        print('IDENTITY_BEFORE_SQL', json.dumps(identity), flush=True)
        c.execute((Path(__file__).parents[1]/'sql/001_candidate.sql').read_text())
        # Test-only identities and policy, NOT product authority or proposed grants.
        for role in ('cj008_a', 'cj008_b'):
            c.execute('CREATE ROLE '+role+' LOGIN NOSUPERUSER NOBYPASSRLS')
            c.execute('GRANT SELECT, UPDATE ON public.cj_usage_ledger_candidate TO '+role)
            c.execute('INSERT INTO public.cj_usage_ledger_candidate VALUES (%s,0,1,%s::jsonb)', (role, encode(Ledger(CFG))))
        c.execute('CREATE POLICY fixture_scope ON public.cj_usage_ledger_candidate USING (scope_id = current_user) WITH CHECK (scope_id = current_user)')
    with connect() as c:
        row = c.execute('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        check('runtime non-superuser non-bypassrls', row == ('cj008_a',False,False))
    check('cross scope RLS denies', rejects(RepositoryUnavailable,
        lambda: Meter(PostgresRepository(connect,'cj008_b'),CFG,lambda:100).reserve(command('x'))))
    check('missing scope never auto creates', rejects(RepositoryUnavailable,
        lambda: Meter(PostgresRepository(connect,'absent'),CFG,lambda:100).reserve(command('x'))))
    def reserve(i):
        try: meter().reserve(command(str(i))); return True
        except Blocked: return False
    with ThreadPoolExecutor(12) as pool:
        check('concurrent independent connections budget <=10', sum(pool.map(reserve, range(30))) == 10)
    reset()
    meter().reserve(command('a',6))
    def claim(_):
        try: meter().claim('a'); return True
        except Blocked: return False
    with ThreadPoolExecutor(8) as pool:
        check('concurrent claim exactly once', sum(pool.map(claim,range(16))) == 1)
    meter().cancel('run')
    check('cancel unknown retains six', meter().query('a').state == 'unknown')
    # Actual server restart, not just a recreated Python service.
    ctl('-m','fast','-w','stop'); started = False
    ctl('-l',str(ROOT/'server.log'),'-w','start'); started = True
    check('server restart preserves unknown cancelled attempt', meter().query('a').cancelled and meter().query('a').state == 'unknown')
    check('restart cannot reclaim original attempt', rejects(Blocked, lambda: meter().claim('a')))
    receipt = Receipt('a','receipt-a','synthetic-unit',3,1)
    check('late synthetic receipt settles once', meter().settle(receipt) == meter().settle(receipt))
    check('different late receipt conflicts', rejects(Blocked,lambda: meter().settle(Receipt('a','receipt-a','synthetic-unit',4,1))))
    with PostgresRepository(connect,'cj008_a').transaction() as ledger:
        check('late receipt actual exposure is three', Meter.exposure(ledger) == 3)
    reset(); meter().reserve(command('a',6)); meter().cancel('run')
    with PostgresRepository(connect,'cj008_a').transaction() as ledger:
        check('cancel before claim releases reservation', Meter.exposure(ledger) == 0 and ledger.attempts['a'].state == 'released')
    check('released attempt never claims', rejects(Blocked,lambda:meter().claim('a')))
    reset(); meter().reserve(command('a',6))
    from threading import Barrier
    barrier = Barrier(2)
    def cancel_race():
        barrier.wait(); meter().cancel('run')
    def claim_race():
        barrier.wait()
        try: meter().claim('a')
        except Blocked: pass
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(cancel_race),pool.submit(claim_race)]
        for future in futures: future.result()
    with PostgresRepository(connect,'cj008_a').transaction() as ledger:
        a = ledger.attempts['a']
        check('cancel claim serialized no ambiguous release', a.cancelled and
              ((a.state == 'unknown' and Meter.exposure(ledger) == 6) or
               (a.state == 'released' and Meter.exposure(ledger) == 0)))
    reset()
    repo = PostgresRepository(connect,'cj008_a')
    try:
        with repo.transaction() as ledger:
            ledger.last_clock = 123
            raise RuntimeError('synthetic body failure')
    except RuntimeError: pass
    with repo.transaction() as ledger: check('body failure rolls back', ledger.last_clock is None)
    reset()
    for mode, expected in [('before',False),('after',True)]:
        reset()
        check(mode+' commit reported unknown', rejects(CommitUnknown,
            lambda: meter(factory=lambda: Wrapped(connect(),mode)).reserve(command('a'))))
        with repo.transaction() as l: check(mode+' commit original readback', ('a' in l.attempts) == expected)
    reset(); meter().reserve(command('a',6))
    calls=[]
    # Fail ACK on claim, not reserve: LocalExit's reserve replay commits first.
    n=[0]
    def factory():
        n[0]+=1
        return Wrapped(connect(), 'after' if n[0]==2 else 'normal')
    check('claim ACK loss prevents executor', rejects(CommitUnknown,
        lambda: LocalExit(meter(factory=factory),lambda c:calls.append(c)).execute(command('a',6))) and not calls)
    check('claim ACK loss retains durable unknown', meter().query('a').state == 'unknown')
    reset()
    check('cleanup error does not replace success', meter(factory=lambda:Wrapped(connect(),'cleanup')).reserve(command('a')).state == 'reserved')
    with connect('cj008_admin') as c:
        c.execute("UPDATE public.cj_usage_ledger_candidate SET ledger='{}'::jsonb WHERE scope_id='cj008_a'")
    check('corruption denied never reset', rejects(CorruptLedger,lambda:meter().reserve(command('b'))))
    with connect('cj008_admin') as c:
        check('corrupt row preserved', c.execute("SELECT ledger FROM public.cj_usage_ledger_candidate WHERE scope_id='cj008_a'").fetchone()[0] == {})
    print('RESULT',json.dumps({'checks':len(checks),'root':str(ROOT),'driver':psycopg.__version__,'real_cost':'UNRUN','product_RLS':'UNRUN'}),flush=True)
finally:
    if started:
        ctl('-m','fast','-w','stop')
    result = subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'status'],env=ENV,capture_output=True,text=True)
    print('STOP_READBACK', result.returncode, 'root', str(ROOT),flush=True)
    if result.returncode != 3: raise RuntimeError('private cluster stop not confirmed')
