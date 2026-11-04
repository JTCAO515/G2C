"""Specified synthetic Supabase test project; never a default/production DSN.

Session mode owns a physical backend for this client. DISCARD ALL is mandatory
on every checkout before binding LOCAL authority. Transaction pooler is refused:
resetting one transaction-mode backend cannot reset all future borrowed backends.
"""
from datetime import datetime
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
import psycopg
from psycopg.conninfo import conninfo_to_dict

from .composition import CompositionUnavailable
from .local_app import LocalDatabase,_require_unbound

REF='sajkhvjpllldfyfryalx'
HOST='aws-0-ap-southeast-1.pooler.supabase.com'
CA_SHA='807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa'
DEADLINE=datetime(2026,12,1,tzinfo=ZoneInfo('Asia/Shanghai'))


def current_authorization():
    if datetime.now(ZoneInfo('Asia/Shanghai'))>=DEADLINE:
        raise CompositionUnavailable('Supabase synthetic test authorization expired')


def decode_uri(uri,*,operator=False):
    current_authorization()
    if (os.environ.get('CJ_ENV')!='local' or any(k.startswith(('PG','LIBPQ')) for k in os.environ)
            or 'SSLKEYLOGFILE' in os.environ or type(uri) is not str or not uri.startswith(('postgres://','postgresql://'))):
        raise CompositionUnavailable('explicit authorized Supabase test connection required')
    try:config=conninfo_to_dict(uri)
    except psycopg.Error:raise CompositionUnavailable('invalid Supabase test URI') from None
    role='postgres' if operator else 'cj_m1_runtime'
    if (set(config)-{'host','port','user','password','dbname','sslmode','connect_timeout'}
            or config.get('host')!=HOST or config.get('user')!=role+'.'+REF
            or config.get('port','5432')!='5432' or config.get('dbname')!='postgres'
            or not config.get('password') or config.get('sslmode','verify-full') not in ('require','verify-full')):
        raise CompositionUnavailable('fixed project/session/role connection required')
    return dict(config,port=5432,sslmode='verify-full',connect_timeout=10,
                options='-c statement_timeout=10000 -c lock_timeout=5000 -c search_path=public')


def discard_session(connection):
    connection.execute('DISCARD ALL')
    with connection.cursor() as cursor:_require_unbound(cursor)


def pin_ca(ca_file):
    certificate=x509.load_pem_x509_certificate(Path(ca_file).read_bytes())
    if certificate.fingerprint(hashes.SHA256()).hex()!=CA_SHA:
        raise CompositionUnavailable('fixed Supabase CA required')
    pinned=tempfile.NamedTemporaryFile(prefix='cj-supabase-pinned-ca-')
    pinned.write(certificate.public_bytes(serialization.Encoding.PEM));pinned.flush()
    return pinned


class SupabaseTestDatabase(LocalDatabase):
    def __init__(self,uri,ca_file,*,run_context=None,travel_context=False,needs_context=False,trip_context=False,edit_configuration=None):
        self._ca=None;self._empty_passfile=None
        config=decode_uri(uri)
        self._ca=pin_ca(ca_file)
        self._configure(run_context=run_context,travel_context=travel_context,needs_context=needs_context,
                        trip_context=trip_context,edit_configuration=edit_configuration)
        self.conninfo=dict(config,sslrootcert=self._ca.name)

    def __del__(self):
        if self._ca is not None:self._ca.close()

    def _open_runtime_connection(self):
        current_authorization()
        conn=psycopg.connect(**self.conninfo,autocommit=True,prepare_threshold=None)
        try:
            row=conn.execute("SELECT current_user,(SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid())").fetchone()
            if row!=('cj_m1_runtime',True):
                raise CompositionUnavailable('runtime login and pooler-to-database TLS required')
            # Owned session-mode physical backend: this is an explicit reset,
            # never overwriting a retained scope with a new tenant's value.
            discard_session(conn)
            current_authorization()
            return conn
        except BaseException:
            conn.close()
            raise
