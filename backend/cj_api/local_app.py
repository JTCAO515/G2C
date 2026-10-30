"""Local-only composition on real PostgreSQL with a local development signing key (P2a).

Never a production entry point: requires CJ_ENV=local, an explicit connection JSON
file and a key directory created by scripts/dev_auth.py. Identity is the local
issuer/subject; the internal scope is derived on the server and provisioned here.
Real email OTP (Supabase) replaces the local key in P2c.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import stat
import time
import uuid

import psycopg
from psycopg.pq import TransactionStatus

from cj_auth.interfaces import CJAccessFacts, Fact
from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.postgres import Repository as MessageRepository
from cj_run.postgres import Repository as RunRepository
from cj_trip.postgres import Repository as TripRepository
from cj_agent.draft import trip_scope_for

from .composition import CompositionUnavailable, create_composed_app
from .local_run_context import load_run_context
from cj_message.needs_binding import needs_scope_for
from cj_run.step_usage import ledger_scope_for
from cj_usage.codec import decode as decode_ledger
from .run_display_composition import RunDisplayWireConfiguration
from .run_events_routes import RunEventsConfiguration
from .trip_composition import TripWireConfiguration

ISSUER = 'https://local.g2c.invalid'
AUDIENCE = 'g2c-local'
KEY_ID = 'local-dev'
RUN_RETENTION = timedelta(days=30)


def scope_for(issuer, subject):
    return f'local:{issuer}:{subject}'


def _require_unbound(cursor):
    """Reject any M1 authority GUC; never overwrite retained session authority."""
    cursor.execute("SELECT current_setting('cj.message_scope',true), current_setting('cj.trip_scope',true), "
                   "current_setting('cj.needs_scope',true), current_setting('cj.usage_scope',true)")
    if any(value not in (None, '') for value in cursor.fetchone()):
        raise CompositionUnavailable('database scope already present')


class _ScopedConnection:
    """IDLE DB-API connection with an explicit transaction-entry binding hook.

    Domain repositories call bind_scope after setting transaction isolation and
    before reading data. Direct host `with` consumers use the same hook here.
    Plain execute/cursor calls never silently rebind after commit or rollback.
    """
    def __init__(self, connection, scope, *, needs_scope=None, usage_scope=None):
        self._connection, self._scope = connection, scope
        self._needs_scope, self._usage_scope = needs_scope, usage_scope

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def bind_scope(self, cursor):
        try:
            if self._connection.info.transaction_status != TransactionStatus.INTRANS:
                raise CompositionUnavailable('active transaction required for scope binding')
            _require_unbound(cursor)
            cursor.execute("SELECT set_config('cj.message_scope',%s,true), set_config('cj.trip_scope',%s,true)",
                           (self._scope, trip_scope_for(self._scope)))
            if self._needs_scope is not None:
                cursor.execute("SELECT set_config('cj.needs_scope',%s,true), set_config('cj.usage_scope',%s,true)",
                               (self._needs_scope,self._usage_scope))
        except BaseException:
            self._connection.close()
            raise

    def __enter__(self):
        self._connection.__enter__()
        try:
            with self._connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                self.bind_scope(cursor)
        except BaseException:
            self._connection.close()
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._connection.__exit__(exc_type, exc, traceback)


def local_conninfo(conninfo_path):
    config = json.loads(Path(conninfo_path).read_text())
    if (os.environ.get('CJ_ENV') != 'local' or type(config) is not dict
            or type(config.get('host')) is not str or not config['host'].startswith('/')
            or ',' in config['host'] or config.get('hostaddr') or 'service' in config
            or any(k.startswith(('PG', 'LIBPQ')) for k in os.environ)):
        raise CompositionUnavailable('explicit local Unix-socket database required')
    return config


class LocalDatabase:
    def __init__(self, conninfo_path, *, run_context=None):
        config = local_conninfo(conninfo_path)
        self.run_context = run_context
        # The initialization identity is never used for application/worker SQL.
        self._empty_passfile = tempfile.NamedTemporaryFile(prefix='cj-m1-runtime-', suffix='.pgpass')
        self.conninfo = dict(config, user='cj_m1_runtime', passfile=self._empty_passfile.name)
        self.conninfo.pop('password', None)

    def __del__(self):
        passfile = getattr(self, '_empty_passfile', None)
        if passfile is not None:
            passfile.close()

    def connect(self, scope, *, usage_profile=None):
        if type(scope) is not str or not scope.startswith('local:' + ISSUER + ':') or not scope.removeprefix('local:' + ISSUER + ':'):
            raise CompositionUnavailable('verified local scope required')
        conn = psycopg.connect(**self.conninfo, autocommit=True)
        try:
            if conn.closed or conn.info.transaction_status != TransactionStatus.IDLE or conn.autocommit is not True:
                raise CompositionUnavailable('fresh idle runtime connection required')
            with conn.cursor() as cursor:
                _require_unbound(cursor)
            role = conn.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,"
                                "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),"
                                "EXISTS(SELECT 1 FROM pg_class WHERE relowner=r.oid) "
                                "FROM pg_roles r WHERE rolname=current_user").fetchone()
            if role != (False, False, False, False, False, False, False):
                raise CompositionUnavailable('unsafe local runtime database role')
            # No scope is installed at checkout. Repositories still receive IDLE;
            # their transaction entry installs LOCAL authority which PostgreSQL
            # removes on commit/rollback even when a physical connection survives.
            conn.autocommit = False
            if self.run_context is None:
                if usage_profile is not None: raise CompositionUnavailable('run context unavailable')
                return _ScopedConnection(conn, scope)
            profile=self.run_context.current if usage_profile is None else usage_profile
            if profile not in self.run_context.profiles:
                raise CompositionUnavailable('unregistered original period')
            return _ScopedConnection(conn,scope,needs_scope=needs_scope_for(scope),
                                     usage_scope=ledger_scope_for(scope,profile.meter))
        except BaseException:
            conn.close()
            raise

    def require_budget_account(self, scope, *, profile=None):
        if self.run_context is None: return
        profile=self.run_context.current if profile is None else profile
        account=ledger_scope_for(scope,profile.meter)
        with self.connect(scope,usage_profile=profile) as conn:
            row=conn.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
            if row is None or row[0]!=1 or decode_ledger(row[1]).config!=profile.meter:
                raise CompositionUnavailable('original budget account unavailable or changed')

    def provision(self, scope):
        """Trusted, idempotent scope provisioning for the local host only."""
        with self.connect(scope) as conn:
            conn.execute('INSERT INTO cj_message_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (scope,))
            conn.execute('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE',(scope,))
            if self.run_context is None and conn.execute('SELECT 1 FROM cj_local_run_protection WHERE scope=%s',(scope,)).fetchone():
                # Safe original history stays readable without creating new runtime
                # state; writes/dispatch check protection inside their own scope lock.
                return
            conn.execute("INSERT INTO cj_run_scope(scope, epoch, active) VALUES (%s, '1', true) ON CONFLICT DO NOTHING", (scope,))
            conn.execute('INSERT INTO cj_trip_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (trip_scope_for(scope),))

    def message_repository(self, scope):
        return MessageRepository(lambda: self.connect(scope), scope, bind_needs=self.run_context is not None,
                                 local_run_mode=self.run_context is not None,
                                 registered_usage=self.run_context is not None and self.run_context.version=='CJ-LOCAL-RUN@2')

    def require_execution(self, scope, binding=None):
        with self.message_repository(scope).transaction() as tx:
            tx.lock_scope()
            tx.local_execution(None if binding is None else binding.message_id,
                               None if binding is None else binding.run_id)

    def trip_repository(self, scope):
        return TripRepository(lambda: self.connect(scope), trip_scope_for(scope), confirm=local_confirmation)

    def run_repository(self, scope, *, usage_profile=None):
        connect = (lambda: self.connect(scope)) if usage_profile is None else (lambda: self.connect(scope,usage_profile=usage_profile))
        return RunRepository(connect, scope, expires_at=datetime.now(timezone.utc) + RUN_RETENTION,
                             statement_timeout_ms=10000, lock_timeout_ms=5000)


def local_confirmation(scope, action, proposal):
    """Local only: the authenticated owner's explicit accept/reject action is the confirmation.

    The candidate hash, expiry and expected version are still checked by TRIP. A
    server-issued confirmation reference shown in the UI is a P2c item.
    """
    return True


class InvitedSubjects:
    """Server-owned invite list (auth_dir/invited.json); token claims never grant access."""

    def __init__(self, path):
        self.path = Path(path)

    def evaluate(self, principal):
        invited = principal.subject in json.loads(self.path.read_text())
        return CJAccessFacts(principal, Fact.YES, Fact.YES, Fact.YES if invited else Fact.NO)


def create_local_app(*, conninfo_path, auth_dir, confirmation_signer=None, history_configuration=None,
                     memory_configuration=None, run_context=None):
    if os.environ.get('CJ_ENV') != 'local':
        raise CompositionUnavailable('CJ_ENV must explicitly be local')
    auth_dir = Path(auth_dir)
    database = LocalDatabase(conninfo_path,run_context=run_context)
    keys = StaticPublicKeys({KEY_ID: VerificationKey('RS256', (auth_dir / 'public.pem').read_bytes())})
    config = JWTConfiguration(ISSUER, AUDIENCE, 'RS256', 0)

    def message_repository(principal):
        scope = scope_for(principal.issuer, principal.subject)
        database.require_budget_account(scope)
        database.provision(scope)
        return database.message_repository(scope)

    def run_repository(principal, scope):
        if scope != scope_for(principal.issuer, principal.subject):
            raise CompositionUnavailable('scope mismatch')
        return database.run_repository(scope)

    def trip(principal):
        scope = scope_for(principal.issuer, principal.subject)
        database.provision(scope)
        return lambda: database.connect(scope), trip_scope_for(scope)

    memory_wire, resolve_memory, memory_source_policy = None, None, None
    if memory_configuration is not None:
        from cj_memory.local import LocalMemoryConfiguration
        from cj_memory.domain import Service as MemoryService
        from cj_memory.postgres import Repository as MemoryRepository
        from .memory_boundary import MemoryBinding, MemorySourceRejected, MemoryWireConfiguration
        if type(memory_configuration) is not LocalMemoryConfiguration:
            raise CompositionUnavailable('explicit local memory policy required')
        memory_wire = MemoryWireConfiguration(32768, 50, 1_000_000)

        def resolve_memory(principal):
            profile = memory_configuration.profiles.get(principal.subject)
            if profile is None:
                raise MemorySourceRejected()
            scope = scope_for(principal.issuer, principal.subject)
            with database.connect(scope) as conn:
                # Existing scope reads never reinsert/update a row locked by the
                # current save's epoch update during fresh AUTH guard stages.
                exists = conn.execute('SELECT 1 FROM cj_memory_scope WHERE scope=%s', (scope,)).fetchone()
                if exists is None:
                    conn.execute('INSERT INTO cj_memory_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (scope,))
            repository = MemoryRepository(lambda: database.connect(scope), scope,
                                           transaction_binder=lambda conn, cursor: conn.bind_scope(cursor))
            return MemoryBinding(scope, MemoryService(repository, manual_policy=profile.manual_policy()))

        def memory_source_policy(principal, scope, kind, command, argument, stage):
            profile = memory_configuration.profiles.get(principal.subject)
            if profile is None or scope != scope_for(principal.issuer, principal.subject):
                return False
            if command is not None:
                # Historical byte-identical replay is a read of the original
                # result, not renewed collection/source authority. An in-flight
                # new ledger row is invisible to this independent guard read.
                with database.connect(scope) as conn:
                    old = conn.execute('SELECT original_input FROM cj_memory_operation WHERE scope=%s AND operation_id=%s',
                                       (scope, command.operation_id)).fetchone()
                if old is not None and bytes(old[0]) == argument:
                    return True
                if profile.expires_at <= datetime.now(timezone.utc):
                    return False
            if command is not None and command.extent == 'current':
                # Local current-context references are explicitly selected owned
                # MESSAGE conversations, never arbitrary caller ownership claims.
                with database.connect(scope) as conn:
                    row = conn.execute('SELECT active FROM cj_message_chat WHERE scope=%s AND conversation_id=%s',
                                       (scope, command.context_id)).fetchone()
                return row is not None and row[0] is True
            return True

    return create_composed_app(
        environment='local', jwt_configuration=config, verification_keys=keys,
        memory_configuration=memory_wire, resolve_memory_binding=resolve_memory,
        memory_source_policy=memory_source_policy,
        access_provider=InvitedSubjects(auth_dir / 'invited.json'),
        resolve_repository=message_repository, new_run_id=lambda: str(uuid.uuid4()),
        max_body_bytes=16384, history_configuration=history_configuration,
        run_display_configuration=RunDisplayWireConfiguration(max_message_id_bytes=256, max_text_bytes=200000,
                                                              max_response_bytes=400000),
        resolve_run_display=run_repository,
        run_events_configuration=RunEventsConfiguration(poll_interval_seconds=0.2, max_stream_seconds=120),
        trip_configuration=TripWireConfiguration(max_action_bytes=4096, max_page_limit=50,
                                                 max_private_response_bytes=1_000_000),
        resolve_trip=trip, trip_confirmation_validator=local_confirmation if confirmation_signer is None else None,
        trip_confirmation_signer=confirmation_signer)


CONFIRMATION_KEY_FILE = 'trip-confirmation.key'


def create_local_memory_management_app(*, conninfo_path, auth_dir, memory_configuration):
    """Explicit C1 local host, separately assembled from the old closed factory."""
    from cj_memory.local import LocalMemoryConfiguration
    from cj_memory.postgres import Repository
    from cj_memory_management.guarded import GuardedService
    from .memory_boundary import MemoryBinding, MemorySourceRejected
    from .memory_management_boundary import (MemoryManagementConfiguration,
        create_local_edit_management_app)
    if os.environ.get('CJ_ENV') != 'local' or type(memory_configuration) is not LocalMemoryConfiguration:
        raise CompositionUnavailable('explicit local management collection policy required')
    database = LocalDatabase(conninfo_path)
    auth_dir = Path(auth_dir)

    def resolve(principal):
        profile = memory_configuration.profiles.get(principal.subject)
        if profile is None:
            raise MemorySourceRejected()
        scope = scope_for(principal.issuer, principal.subject)
        repository = Repository(lambda: database.connect(scope), scope,
                               transaction_binder=lambda conn, cursor: conn.bind_scope(cursor))
        return MemoryBinding(scope, GuardedService(repository, manual_policy=profile.manual_policy()))

    return create_local_edit_management_app(configuration=MemoryManagementConfiguration(32768,65536),
        environment='local', jwt_configuration=JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
        verification_keys=StaticPublicKeys({KEY_ID:VerificationKey('RS256',(auth_dir/'public.pem').read_bytes())}),
        access_provider=InvitedSubjects(auth_dir/'invited.json'), resolve_binding=resolve)


def load_confirmation_signer(auth_dir):
    """Dedicated local signing key created by scripts/dev_auth.py; never a default or generated here."""
    from cj_trip.confirmation import ConfirmationSigner
    path = Path(auth_dir) / CONFIRMATION_KEY_FILE
    try:
        mode = path.stat().st_mode & 0o777
        key = path.read_bytes()
    except OSError:
        raise CompositionUnavailable('trip confirmation key missing; run scripts/dev_auth.py confirmation-key') from None
    if mode & 0o077 or len(key) < 32:
        raise CompositionUnavailable('trip confirmation key must be private (0600) and at least 32 bytes')
    return ConfirmationSigner(key)


HISTORY_KEY_FILE = 'history-cursor.key'


def load_history_configuration(auth_dir):
    """Load the dedicated local cursor key; never create or substitute key material."""
    from .aead_cursor import AeadCursorCodec
    from .history_config import CursorPolicy, HistoryWireConfiguration
    if os.environ.get('CJ_ENV') != 'local':
        raise CompositionUnavailable('CJ_ENV must explicitly be local')
    path = Path(auth_dir) / HISTORY_KEY_FILE
    try:
        # Inspect and read the same descriptor; reject links, devices and unsafe modes.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise CompositionUnavailable('history cursor key must be a regular 0600 file')
            key = source.read(33)
    except OSError:
        raise CompositionUnavailable('history cursor key unavailable; run scripts/dev_auth.py history-key') from None
    if len(key) != 32:
        raise CompositionUnavailable('history cursor key must be exactly 32 bytes')
    codec = AeadCursorCodec(keys={'local-history-v1': key}, active_key_id='local-history-v1',
                            version='local-history-v1', clock=lambda: int(time.time()),
                            max_ttl_seconds=300, max_token_bytes=2048,
                            max_plaintext_bytes=512, max_binding_bytes=2048)
    return HistoryWireConfiguration(20, 16384, 1_000_000, CursorPolicy(codec, 300, 2048))


def app_from_environment():
    """uvicorn factory: CJ_LOCAL_CONNINFO and CJ_LOCAL_AUTH_DIR point at local files.

    Always uses the signed Trip confirmation path. The permissive P2b validator remains
    reachable only through create_local_app's default for existing tests.
    """
    if os.environ.get('CJ_ENV') != 'local':
        raise CompositionUnavailable('CJ_ENV must explicitly be local')
    auth_dir = os.environ['CJ_LOCAL_AUTH_DIR']
    memory_configuration = None
    if 'CJ_LOCAL_MEMORY_POLICY' in os.environ:
        from cj_memory.local import load_local_memory_configuration, LocalMemoryConfigurationError
        try:
            memory_configuration = load_local_memory_configuration(os.environ['CJ_LOCAL_MEMORY_POLICY'])
        except LocalMemoryConfigurationError:
            raise CompositionUnavailable('local memory policy unavailable') from None
    return create_local_app(conninfo_path=os.environ['CJ_LOCAL_CONNINFO'], auth_dir=auth_dir,
                            confirmation_signer=load_confirmation_signer(auth_dir),
                            history_configuration=load_history_configuration(auth_dir),
                            memory_configuration=memory_configuration,
                            run_context=load_run_context(os.environ['CJ_LOCAL_RUN_CONTEXT'])
                            if 'CJ_LOCAL_RUN_CONTEXT' in os.environ else None)
