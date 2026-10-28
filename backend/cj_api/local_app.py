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
import uuid

import psycopg

from cj_auth.interfaces import CJAccessFacts, Fact
from cj_auth.jwt_adapter import JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.postgres import Repository as MessageRepository
from cj_run.postgres import Repository as RunRepository
from cj_trip.postgres import Repository as TripRepository
from cj_agent.draft import trip_scope_for

from .composition import CompositionUnavailable, create_composed_app
from .run_display_composition import RunDisplayWireConfiguration
from .run_events_routes import RunEventsConfiguration
from .trip_composition import TripWireConfiguration

ISSUER = 'https://local.g2c.invalid'
AUDIENCE = 'g2c-local'
KEY_ID = 'local-dev'
RUN_RETENTION = timedelta(days=30)


def scope_for(issuer, subject):
    return f'local:{issuer}:{subject}'


class LocalDatabase:
    def __init__(self, conninfo_path):
        config = json.loads(Path(conninfo_path).read_text())
        if (os.environ.get('CJ_ENV') != 'local' or type(config) is not dict
                or type(config.get('host')) is not str or not config['host'].startswith('/')
                or ',' in config['host'] or config.get('hostaddr') or 'service' in config
                or any(k.startswith(('PG', 'LIBPQ')) for k in os.environ)):
            raise CompositionUnavailable('explicit local Unix-socket database required')
        # The initialization identity is never used for application/worker SQL.
        self._empty_passfile = tempfile.NamedTemporaryFile(prefix='cj-m1-runtime-', suffix='.pgpass')
        self.conninfo = dict(config, user='cj_m1_runtime', passfile=self._empty_passfile.name)
        self.conninfo.pop('password', None)

    def __del__(self):
        passfile = getattr(self, '_empty_passfile', None)
        if passfile is not None:
            passfile.close()

    def connect(self, scope):
        if type(scope) is not str or not scope.startswith('local:' + ISSUER + ':') or not scope.removeprefix('local:' + ISSUER + ':'):
            raise CompositionUnavailable('verified local scope required')
        conn = psycopg.connect(**self.conninfo, autocommit=True)
        try:
            role = conn.execute("SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication,"
                                "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid),"
                                "EXISTS(SELECT 1 FROM pg_class WHERE relowner=r.oid) "
                                "FROM pg_roles r WHERE rolname=current_user").fetchone()
            if role != (False, False, False, False, False, False, False):
                raise CompositionUnavailable('unsafe local runtime database role')
            # A fresh connection belongs to exactly one verified scope and one
            # repository transaction; no pool/reuse or caller owner is accepted.
            # Configure outside a transaction so repositories still receive IDLE.
            conn.execute("SELECT set_config('cj.message_scope',%s,false), set_config('cj.trip_scope',%s,false)",
                         (scope, trip_scope_for(scope)))
            conn.autocommit = False
            return conn
        except BaseException:
            conn.close()
            raise

    def provision(self, scope):
        """Trusted, idempotent scope provisioning for the local host only."""
        with self.connect(scope) as conn:
            conn.execute('INSERT INTO cj_message_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (scope,))
            conn.execute("INSERT INTO cj_run_scope(scope, epoch, active) VALUES (%s, '1', true) ON CONFLICT DO NOTHING", (scope,))
            conn.execute('INSERT INTO cj_trip_scope(scope) VALUES (%s) ON CONFLICT DO NOTHING', (trip_scope_for(scope),))

    def message_repository(self, scope):
        return MessageRepository(lambda: self.connect(scope), scope)

    def trip_repository(self, scope):
        return TripRepository(lambda: self.connect(scope), trip_scope_for(scope), confirm=local_confirmation)

    def run_repository(self, scope):
        return RunRepository(lambda: self.connect(scope), scope, expires_at=datetime.now(timezone.utc) + RUN_RETENTION,
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


def create_local_app(*, conninfo_path, auth_dir, confirmation_signer=None):
    if os.environ.get('CJ_ENV') != 'local':
        raise CompositionUnavailable('CJ_ENV must explicitly be local')
    auth_dir = Path(auth_dir)
    database = LocalDatabase(conninfo_path)
    keys = StaticPublicKeys({KEY_ID: VerificationKey('RS256', (auth_dir / 'public.pem').read_bytes())})
    config = JWTConfiguration(ISSUER, AUDIENCE, 'RS256', 0)

    def message_repository(principal):
        scope = scope_for(principal.issuer, principal.subject)
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

    return create_composed_app(
        environment='local', jwt_configuration=config, verification_keys=keys,
        access_provider=InvitedSubjects(auth_dir / 'invited.json'),
        resolve_repository=message_repository, new_run_id=lambda: str(uuid.uuid4()),
        max_body_bytes=16384,
        run_display_configuration=RunDisplayWireConfiguration(max_message_id_bytes=256, max_text_bytes=200000,
                                                              max_response_bytes=400000),
        resolve_run_display=run_repository,
        run_events_configuration=RunEventsConfiguration(poll_interval_seconds=0.2, max_stream_seconds=120),
        trip_configuration=TripWireConfiguration(max_action_bytes=4096, max_page_limit=50,
                                                 max_private_response_bytes=1_000_000),
        resolve_trip=trip, trip_confirmation_validator=local_confirmation if confirmation_signer is None else None,
        trip_confirmation_signer=confirmation_signer)


CONFIRMATION_KEY_FILE = 'trip-confirmation.key'


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


def app_from_environment():
    """uvicorn factory: CJ_LOCAL_CONNINFO and CJ_LOCAL_AUTH_DIR point at local files.

    Always uses the signed Trip confirmation path. The permissive P2b validator remains
    reachable only through create_local_app's default for existing tests.
    """
    auth_dir = os.environ['CJ_LOCAL_AUTH_DIR']
    return create_local_app(conninfo_path=os.environ['CJ_LOCAL_CONNINFO'], auth_dir=auth_dir,
                            confirmation_signer=load_confirmation_signer(auth_dir))
