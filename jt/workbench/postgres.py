"""Transactions and repositories for the dedicated workbench database."""

from asyncio import to_thread
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from jt.common import Signal

from .auth import ExpiredSession
from .queue import QueueItem, Review, SignalConflict, response_deadline
from .security import PasswordHash, new_token
from .store import Account, AuditAction, AuditEvent, AuditResult, CaseAuditDetail, Failures, OperationsAuditDetail, Role, Session


DATABASE_VARIABLE = "JT_WORKBENCH_DATABASE_URL"
MIGRATION_ROLE = "jt_workbench_owner"
RUNTIME_ROLE = "jt_workbench_runtime"
SCHEMA_VERSION = 4
LOCK_ID = 0x4A54574F524B
ACCOUNT_COLUMNS = "username, role, password_salt, password_digest, enabled"


def _connect(dsn: str, role: str) -> Connection:
    target = conninfo_to_dict(dsn)
    if target.get("dbname") != "jt_workbench" or target.get("user") != role or not target.get("host"):
        raise RuntimeError("workbench connection must name its dedicated database, role and host")
    return psycopg.connect(dsn, connect_timeout=5, options="-c search_path=pg_catalog -c TimeZone=UTC")


def _guard_role(db: Connection, role: str) -> None:
    identity = db.execute("""
        SELECT current_database(), current_user, rolsuper, rolcreaterole, rolcreatedb, rolbypassrls
        FROM pg_roles WHERE rolname = current_user
    """).fetchone()
    if identity != ("jt_workbench", role, False, False, False, False):
        raise RuntimeError("workbench database or role is not authorized")


def _installed_versions(db: Connection) -> list[int]:
    versions = [version for version, in db.execute("SELECT version FROM jt_workbench.schema_version ORDER BY version")]
    for table, number in (("case_audit_version", 2), ("operations_audit_version", 3), ("password_auth_version", 4)):
        qualified = f"jt_workbench.{table}"
        has_extension, = db.execute("SELECT to_regclass(%s) IS NOT NULL", (qualified,)).fetchone()
        if has_extension:
            if db.execute(f"SELECT version FROM {qualified}").fetchall() != [(number,)]:
                raise RuntimeError("unsupported workbench audit schema version")
            versions.append(number)
    return versions


def _check_version(db: Connection) -> None:
    if _installed_versions(db) != list(range(1, SCHEMA_VERSION + 1)):
        raise RuntimeError("unsupported workbench schema version")


def migrate(dsn: str, *, down: bool = False, steps: int | None = None) -> None:
    directory = Path(__file__).with_name("migrations")
    with _connect(dsn, MIGRATION_ROLE) as db:
        _guard_role(db, MIGRATION_ROLE)
        db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
        exists, = db.execute("SELECT to_regclass('jt_workbench.schema_version') IS NOT NULL").fetchone()
        versions = _installed_versions(db) if exists else []
        if len(versions) > SCHEMA_VERSION or versions != list(range(1, len(versions) + 1)) or (exists and not versions):
            raise RuntimeError("unsupported workbench schema version")
        order = list(reversed(versions)) if down else range(len(versions) + 1, SCHEMA_VERSION + 1)
        if down and steps is not None:
            order = order[:steps]
        direction = "down" if down else "up"
        for version in order:
            db.execute((directory / f"{version:03}_{direction}.sql").read_text())


def _load_account(row) -> Account:
    username, role, salt, digest, enabled = row
    password = PasswordHash(salt, digest) if salt is not None else None
    return Account(username, Role(role), password, enabled)


class PostgresStore:
    """One database transaction for each application operation, across all workers."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._transaction: ContextVar[Connection] = ContextVar("workbench_transaction")

    @contextmanager
    def locked(self) -> Iterator[None]:
        if self._transaction.get(None) is not None:
            yield
            return
        expired = None
        with _connect(self._dsn, RUNTIME_ROLE) as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            token = self._transaction.set(db)
            try:
                with db.transaction():
                    yield
            except ExpiredSession as error:
                # Roll back the operation, then commit revocation while still holding the lock.
                self.revoke_session(error.digest)
                expired = error
            finally:
                self._transaction.reset(token)
        if expired is not None:
            raise expired

    def _db(self) -> Connection:
        return self._transaction.get()

    def check_ready(self) -> None:
        with self.locked():
            db = self._db()
            _guard_role(db, RUNTIME_ROLE)
            allowed, can_modify, is_owner_member = db.execute("""
                SELECT has_table_privilege('jt_workbench.audit', 'SELECT')
                       AND has_table_privilege('jt_workbench.audit', 'INSERT'),
                       has_any_column_privilege('jt_workbench.audit', 'UPDATE')
                       OR has_table_privilege('jt_workbench.audit', 'DELETE, TRUNCATE')
                       OR has_schema_privilege('jt_workbench', 'CREATE'),
                       pg_has_role(current_user, 'jt_workbench_owner', 'MEMBER')
            """).fetchone()
            if not allowed or can_modify or is_owner_member:
                raise RuntimeError("workbench audit grants are not safe")
            _check_version(db)

    def clock(self) -> float:
        value, = self._db().execute("SELECT extract(epoch FROM clock_timestamp())::double precision").fetchone()
        return value

    def account(self, username: str) -> Account | None:
        row = self._db().execute(
            f"SELECT {ACCOUNT_COLUMNS} FROM jt_workbench.accounts WHERE username = %s", (username,),
        ).fetchone()
        return _load_account(row) if row else None

    def accounts(self) -> tuple[Account, ...]:
        return tuple(map(_load_account, self._db().execute(f"SELECT {ACCOUNT_COLUMNS} FROM jt_workbench.accounts")))

    def save_account(self, account: Account) -> None:
        password = account.password
        # last_totp_step is a legacy NOT NULL column; the second factor itself no longer exists.
        self._db().execute("""
            INSERT INTO jt_workbench.accounts (
                username, role, password_salt, password_digest, last_totp_step, enabled
            ) VALUES (%s, %s, %s, %s, -1, %s)
            ON CONFLICT (username) DO UPDATE SET
                role = EXCLUDED.role, password_salt = EXCLUDED.password_salt,
                password_digest = EXCLUDED.password_digest, enabled = EXCLUDED.enabled
        """, (account.username, account.role, password.salt if password else None,
              password.digest if password else None, account.enabled))

    def failures(self, username: str, now: float) -> Failures:
        row = self._db().execute("""
            SELECT count, expires FROM jt_workbench.failures WHERE username = %s AND expires > %s
        """, (username, now)).fetchone()
        return Failures(*row) if row else Failures()

    def save_failures(self, username: str, failures: Failures) -> None:
        self._db().execute("""
            INSERT INTO jt_workbench.failures VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET count = EXCLUDED.count, expires = EXCLUDED.expires
        """, (username, failures.count, failures.until))

    def allow_login_attempt(self, now: float, *, window: float, limit: int) -> bool:
        db = self._db()
        db.execute("DELETE FROM jt_workbench.attempts WHERE attempted_at <= %s", (now - window,))
        count, = db.execute("SELECT count(*) FROM jt_workbench.attempts").fetchone()
        if count >= limit:
            return False
        db.execute("INSERT INTO jt_workbench.attempts (attempted_at) VALUES (%s)", (now,))
        return True

    def session(self, digest: bytes) -> Session | None:
        row = self._db().execute("""
            SELECT username, role, csrf, expires_at, idle_until FROM jt_workbench.sessions WHERE digest = %s
        """, (digest,)).fetchone()
        return Session(row[0], Role(row[1]), *row[2:]) if row else None

    def save_session(self, digest: bytes, session: Session) -> None:
        self._db().execute("""
            INSERT INTO jt_workbench.sessions VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (digest) DO UPDATE SET idle_until = EXCLUDED.idle_until
        """, (digest, session.username, session.role, session.csrf, session.expires_at, session.idle_until))

    def revoke_session(self, digest: bytes) -> None:
        self._db().execute("DELETE FROM jt_workbench.sessions WHERE digest = %s", (digest,))

    def prune_sessions(self, now: float) -> None:
        self._db().execute("""
            DELETE FROM jt_workbench.sessions WHERE expires_at <= %s OR idle_until <= %s
        """, (now, now))

    def revoke_staff_sessions(self, username: str) -> None:
        self._db().execute("DELETE FROM jt_workbench.sessions WHERE username = %s", (username,))

    def append_audit(self, event: AuditEvent) -> None:
        detail = event.case_detail
        operations = event.operations_detail
        self._db().execute("""
            INSERT INTO jt_workbench.audit (
                timestamp, action, actor, case_id, result, staff_target, signal_reference,
                case_action, case_step, case_revision, case_reason, operations_action, operations_reference
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (event.timestamp, event.action, event.actor, event.case_id, event.result, event.staff_target,
              event.signal_reference, detail.action if detail else None, detail.step_id if detail else None,
              detail.revision if detail else None, detail.reason if detail else None,
              operations.action if operations else None, operations.reference if operations else None))

    def audit_events(self) -> tuple[AuditEvent, ...]:
        events = []
        for row in self._db().execute("""
            SELECT timestamp, action, actor, case_id, result, staff_target, signal_reference,
                   case_action, case_step, case_revision, case_reason, operations_action, operations_reference
            FROM jt_workbench.audit ORDER BY id
        """):
            timestamp, action, actor, case_id, result, staff_target, reference, *fields = row
            detail = CaseAuditDetail(*fields[:4]) if fields[0] else None
            operations = OperationsAuditDetail(*fields[4:]) if fields[4] else None
            events.append(AuditEvent(timestamp, AuditAction(action), actor, str(case_id) if case_id else None,
                                     AuditResult(result), staff_target, reference, detail, operations))
        return tuple(events)

    def seed(self, signals: tuple[Signal, ...]) -> None:
        with self.locked():
            for signal in signals:
                self._accept(signal)

    def _accept(self, signal: Signal) -> None:
        db = self._db()
        payload = signal.model_dump(mode="json")
        row = db.execute("SELECT payload FROM jt_workbench.signals WHERE signal_id = %s",
                         (signal.signal_id,)).fetchone()
        if row:
            if Signal.model_validate(row[0]) != signal:
                raise SignalConflict("conflicting signal")
            return
        db.execute("""
            INSERT INTO jt_workbench.signals (signal_id, reference, payload, due_at)
            VALUES (%s, %s, %s, %s)
        """, (signal.signal_id, new_token(), Jsonb(payload), response_deadline(signal.detected_at)))

    async def publish(self, signal: Signal) -> None:
        await to_thread(self.seed, (signal,))

    def _items(self, reference: str | None = None) -> tuple[QueueItem, ...]:
        db = self._db()
        select = "SELECT reference, payload, due_at, case_id FROM jt_workbench.signals"
        if reference is None:
            rows = db.execute(select).fetchall()
        else:
            rows = db.execute(select + " WHERE reference = %s", (reference,)).fetchall()
        reviews_by_reference = defaultdict(list)
        if rows:
            for key, severity, false_positive, missed, note, actor, at in db.execute("""
                SELECT reference, actual_severity, false_positive, missed, note, actor, recorded_at
                FROM jt_workbench.reviews WHERE reference = ANY(%s) ORDER BY id
            """, ([row[0] for row in rows],)):
                reviews_by_reference[key].append(Review(severity, false_positive, missed, note, actor, at))
        return tuple(QueueItem(key, Signal.model_validate(payload), due, str(case_id) if case_id else None,
                               tuple(reviews_by_reference[key])) for key, payload, due, case_id in rows)

    def snapshot(self) -> tuple[QueueItem, ...]:
        with self.locked():
            return tuple(sorted(self._items(), key=lambda item: (
                item.signal.severity, item.due_at, item.signal.detected_at, item.signal.signal_id,
            )))

    def item(self, reference: str) -> QueueItem | None:
        with self.locked():
            items = self._items(reference)
            return items[0] if items else None

    def append_review(self, item: QueueItem, review: Review) -> None:
        with self.locked():
            self._db().execute("""
                INSERT INTO jt_workbench.reviews
                    (reference, actual_severity, false_positive, missed, note, actor, recorded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (item.reference, review.actual_severity, review.false_positive, review.missed,
                  review.note, review.actor, review.recorded_at))

    def alerts(self) -> tuple[int, int]:
        with self.locked():
            return self._db().execute("""
                SELECT count(*) FILTER (WHERE NOT EXISTS (
                    SELECT 1 FROM jt_workbench.reviews r WHERE r.reference = s.reference
                )), count(*)
                FROM jt_workbench.signals s WHERE payload->>'severity' = 'P0'
            """).fetchone()


def main() -> None:
    from argparse import ArgumentParser
    from os import environ

    parser = ArgumentParser(description="工作台数据库迁移")
    parser.add_argument("direction", choices=("up", "down"))
    parser.add_argument("--steps", type=int, help="down 时只回退最近的 N 个迁移")
    args = parser.parse_args()
    if args.steps is not None and (args.direction != "down" or args.steps < 1):
        parser.error("--steps 只用于 down，且至少为 1。")
    dsn = environ.get(DATABASE_VARIABLE)
    if not dsn:
        parser.error(f"缺少 {DATABASE_VARIABLE}。")
    try:
        migrate(dsn, down=args.direction == "down", steps=args.steps)
    except (psycopg.Error, RuntimeError):
        parser.exit(1, "工作台迁移未完成。请核对独立库、迁移角色、版本与存量数据。\n")


if __name__ == "__main__":
    main()
