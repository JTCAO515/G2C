"""Specified synthetic Supabase test project; never a default/production DSN.

Session mode owns a physical backend for this client. DISCARD ALL is mandatory
on every checkout before binding LOCAL authority. Transaction pooler is refused:
resetting one transaction-mode backend cannot reset all future borrowed backends.
"""
from datetime import datetime
import logging
import os
import json
from pathlib import Path
import re
import tempfile
from time import monotonic
from zoneinfo import ZoneInfo

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus
from psycopg_pool import ConnectionPool, PoolTimeout

from .composition import CompositionUnavailable
from .local_app import LocalDatabase,_require_unbound

REF='sajkhvjpllldfyfryalx'
SUPABASE_TEST_SCHEMA=48
HOST='aws-0-ap-southeast-1.pooler.supabase.com'
CA_SHA='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
HK_SOCKET='/run/g2c-pg'
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))
DEMO_DEADLINE=datetime(2027,1,1,tzinfo=ZoneInfo('Asia/Shanghai'))
_timing_log=logging.getLogger('cj_usage.audit')


def hk_demo_enabled():
    return os.environ.get('CJ_BETA_DB_TARGET')=='hk-local' and bool(json.loads(os.environ.get('CJ_BETA_DEMO_SUBJECTS_JSON','[]')))


def current_authorization(*,local_socket=False):
    deadline=DEMO_DEADLINE if local_socket and hk_demo_enabled() else DEADLINE
    if datetime.now(ZoneInfo('Asia/Shanghai'))>=deadline:
        raise CompositionUnavailable('Supabase synthetic test authorization expired')


def require_environment():
    if (os.environ.get('CJ_ENV')!='local' or any(k.startswith(('PG','LIBPQ')) for k in os.environ)
            or 'SSLKEYLOGFILE' in os.environ):
        raise CompositionUnavailable('explicit unpolluted Supabase test environment required')


def decode_uri(uri,*,operator=False):
    return _decode_uri(uri,'postgres' if operator else 'cj_m1_runtime')


def decode_cleanup_uri(uri):
    return _decode_uri(uri,'cj_local_cleanup')


def decode_hk_socket_uri(uri,role):
    current_authorization(local_socket=True);require_environment()
    if type(uri) is not str or not uri.startswith('postgresql://'):
        raise CompositionUnavailable('explicit HK socket URI required')
    try:config=conninfo_to_dict(uri)
    except psycopg.Error:raise CompositionUnavailable('invalid HK socket URI') from None
    if (set(config)!={'host','port','user','password','dbname','sslmode'} or config['host']!=HK_SOCKET
            or config['port']!='5432' or config['dbname']!='postgres' or config['user']!=role
            or config['sslmode']!='disable' or re.fullmatch(r'[A-Za-z0-9_-]{43}',config['password']) is None):
        raise CompositionUnavailable('fixed HK socket and role connection required')
    return dict(config,connect_timeout=5,
                options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=pg_catalog,public,pg_temp')


def _decode_uri(uri,role):
    current_authorization()
    require_environment()
    if type(uri) is not str or not uri.startswith(('postgres://','postgresql://')):
        raise CompositionUnavailable('explicit authorized Supabase test connection required')
    try:config=conninfo_to_dict(uri)
    except psycopg.Error:raise CompositionUnavailable('invalid Supabase test URI') from None
    if (set(config)-{'host','port','user','password','dbname','sslmode','connect_timeout'}
            or config.get('host')!=HOST or config.get('user')!=role+'.'+REF
            or config.get('port','5432')!='5432' or config.get('dbname')!='postgres'
            or not config.get('password') or config.get('sslmode','verify-full') not in ('require','verify-full')):
        raise CompositionUnavailable('fixed project/session/role connection required')
    return dict(config,port=5432,sslmode='verify-full',connect_timeout=10,
                options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=pg_catalog,public,pg_temp')


def discard_session(connection):
    connection.execute('DISCARD ALL')
    connection.execute('SET search_path TO pg_catalog, public, pg_temp')
    with connection.cursor() as cursor:_require_unbound(cursor)


def require_identity(connection,role):
    current_authorization();require_environment()
    if connection.execute("SELECT current_user,session_user,(SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid())").fetchone()!=(role,role,True):
        raise CompositionUnavailable('independent login and database-side TLS required')


def prepare_owned_session(connection,role):
    require_identity(connection,role)
    discard_session(connection)
    require_identity(connection,role)


def require_hk_socket_identity(connection,role):
    current_authorization(local_socket=True);require_environment()
    if connection.execute("SELECT current_user,session_user,inet_server_addr(),current_setting('listen_addresses')").fetchone()!=(role,role,None,''):
        raise CompositionUnavailable('independent HK socket login without TCP required')


def prepare_hk_socket_session(connection,role):
    require_hk_socket_identity(connection,role)
    discard_session(connection)
    require_hk_socket_identity(connection,role)


def pin_ca(ca_file):
    certificate=x509.load_pem_x509_certificate(Path(ca_file).read_bytes())
    if certificate.fingerprint(hashes.SHA256()).hex()!=CA_SHA:
        raise CompositionUnavailable('fixed Supabase CA required')
    pinned=tempfile.NamedTemporaryFile(prefix='cj-supabase-pinned-ca-')
    pinned.write(certificate.public_bytes(serialization.Encoding.PEM));pinned.flush()
    return pinned


class _TimedConnection(psycopg.Connection):
    @classmethod
    def connect(cls, *args, **kwargs):
        started = monotonic()
        connection = super().connect(*args, **kwargs)
        _timing_log.info('M4_DB_PHYSICAL_TIMING pid=%d connect_tls_ms=%.3f',
                         connection.info.backend_pid,(monotonic()-started)*1000)
        return connection


class _RuntimeLease:
    """Preserve the existing DB-API transaction and close boundaries."""

    def __init__(self, pool, connection):
        self._pool = pool
        self._connection = connection
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._active_connection(), name)

    def _active_connection(self):
        if self.closed:
            raise psycopg.OperationalError('runtime session lease ended')
        return self._connection

    @property
    def closed(self):
        return self._returned or self._connection.closed

    @property
    def autocommit(self):
        return self._active_connection().autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._active_connection().autocommit = value

    def __enter__(self):
        if self.closed:
            raise psycopg.OperationalError('runtime session lease ended')
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if not self.closed:
                if exc_type is None:
                    self.commit()
                else:
                    self.rollback()
        except psycopg.Error:
            if exc_type is None:
                raise
        finally:
            self.close()

    def commit(self):
        connection = self._active_connection()
        try:
            connection.commit()
        except BaseException:
            connection.close()
            raise

    def rollback(self):
        connection = self._active_connection()
        try:
            connection.rollback()
        except BaseException:
            connection.close()
            raise

    def close(self):
        if self._returned:
            return
        self._returned = True
        if self._connection.info.transaction_status != TransactionStatus.IDLE:
            self._connection.close()
        self._pool.putconn(self._connection)


class SupabaseTestDatabase(LocalDatabase):
    _pool:ConnectionPool|None=None
    _local_socket=False

    def __init__(self,uri,ca_file,*,run_context=None,travel_context=False,needs_context=False,trip_context=False,edit_configuration=None,transaction_guard=None,pool_size=None,local_socket=False):
        self._ca=None;self._empty_passfile=None;self._transaction_guard=transaction_guard
        self._local_socket=local_socket
        if local_socket:
            config=decode_hk_socket_uri(uri,'cj_m1_runtime')
        else:
            config=decode_uri(uri)
            self._ca=pin_ca(ca_file)
            config=dict(config,sslrootcert=self._ca.name)
        self._configure(run_context=run_context,travel_context=travel_context,needs_context=needs_context,
                        trip_context=trip_context,edit_configuration=edit_configuration)
        self.conninfo=config
        if pool_size is not None:
            if type(pool_size) is not int or not 1 <= pool_size <= 8:
                raise CompositionUnavailable('bounded beta runtime pool required')
            self._pool = ConnectionPool(connection_class=_TimedConnection,
                                        kwargs=dict(self.conninfo,autocommit=True,prepare_threshold=None),
                                        min_size=0,max_size=pool_size,max_waiting=32,timeout=10,
                                        max_lifetime=900,max_idle=60,open=True,name='hk-beta-runtime')

    def __del__(self):
        self.close()

    def close(self):
        if self._pool is not None:self._pool.close()
        if self._ca is not None:self._ca.close()

    def _before_scope(self,cursor):
        if self._transaction_guard is not None:self._transaction_guard(cursor)

    def run_repository(self,scope,*,usage_profile=None):
        connect_worker=None
        if self._pool is not None:
            connect_worker=lambda: self.connect(scope,usage_profile=usage_profile,dedicated=True)
        return super().run_repository(scope,usage_profile=usage_profile,connect_worker=connect_worker)

    def _check_execution_connection(self, cursor):
        identity=require_hk_socket_identity if self._local_socket else require_identity
        identity(cursor,'cj_m1_runtime')
        super()._check_execution_connection(cursor)

    def _prepare_session(self,connection):
        prepare=prepare_hk_socket_session if self._local_socket else prepare_owned_session
        prepare(connection,'cj_m1_runtime')

    def _open_runtime_connection(self):
        if self._pool is None:
            return self._open_dedicated_runtime_connection()
        current_authorization(local_socket=self._local_socket);require_environment()
        started=monotonic()
        try:
            connection = self._pool.getconn()
        except PoolTimeout:
            raise CompositionUnavailable('beta runtime pool checkout unavailable') from None
        lease = _RuntimeLease(self._pool, connection)
        try:
            connection.autocommit = True
            self._prepare_session(connection)
            _timing_log.info('M4_DB_CHECKOUT_TIMING pid=%d pooled=true elapsed_ms=%.3f',
                             connection.info.backend_pid,(monotonic()-started)*1000)
            return lease
        except BaseException:
            connection.close()
            lease.close()
            raise

    def _open_dedicated_runtime_connection(self):
        current_authorization(local_socket=self._local_socket);require_environment()
        started=monotonic()
        connect=psycopg.connect if self._pool is None else _TimedConnection.connect
        conn=connect(**self.conninfo,autocommit=True,prepare_threshold=None)
        try:
            # Reset only our owned session, with actual login/TLS checked before
            # and after. Persistent targets never resolve through pg_temp.
            self._prepare_session(conn)
            current_authorization(local_socket=self._local_socket);require_environment()
            if self._pool is not None:
                _timing_log.info('M4_DB_CHECKOUT_TIMING pid=%d pooled=false elapsed_ms=%.3f',
                                 conn.info.backend_pid,(monotonic()-started)*1000)
            return conn
        except BaseException:
            conn.close()
            raise
