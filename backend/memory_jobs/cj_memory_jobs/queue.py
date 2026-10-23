"""Explicit local SQLite adapter and internal trusted-domain state machine.

No workers, timers, network, model invocation, consent issuer or MEMORY writes.
Host guard is an UNIMPLEMENTED production seam; see contracts/memory-jobs.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3

from .codec import (CommitUnknown, Conflict, InvalidInput, Source, Unavailable,
                    decode, encode, identity)


@dataclass(frozen=True)
class Status:
    job_id: str
    attempt_id: str
    state: str
    processed_through: int
    # A completed job is only a derived candidate, never "remembered".


class LocalStore:
    """Caller supplies an explicit path. Only create a NEW isolated candidate DB.

    Reopen validates this module's exact schema marker; no production DB discovery.
    Single connection per instance; SQLite serializes competing local writers.
    """
    def __init__(self, path, *, create=False):
        from pathlib import Path
        path = Path(path).resolve()
        if create:
            # Exclusive creation refuses existing files, including empty DBs.
            with path.open('xb'):
                pass
        elif not path.is_file():
            raise Unavailable('original local candidate store absent')
        self.db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True,
                                  isolation_level=None, timeout=1)
        try:
            if create:
                self.db.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE marker(version TEXT NOT NULL);
                INSERT INTO marker VALUES('CJ020-local.1');
                CREATE TABLE jobs(
                  scope TEXT NOT NULL, job_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                  raw BLOB NOT NULL, state TEXT NOT NULL CHECK(state IN
                    ('pending','inflight','unknown','completed')),
                  processed INTEGER NOT NULL, candidate BLOB,
                  PRIMARY KEY(scope,job_id), UNIQUE(scope,attempt_id));
                CREATE TABLE cursors(
                  scope TEXT NOT NULL, conversation TEXT NOT NULL, generation TEXT NOT NULL,
                  epoch INTEGER NOT NULL, source_version INTEGER NOT NULL,
                  memory_epoch INTEGER NOT NULL, mode TEXT NOT NULL, processed INTEGER NOT NULL,
                  PRIMARY KEY(scope,conversation,generation,epoch,source_version,memory_epoch,mode));
                COMMIT;
                ''')
            if self.db.execute('SELECT version FROM marker').fetchall() != [('CJ020-local.1',)]:
                raise Unavailable('unsupported local store')
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _close_after_uncertainty(self):
        # Cleanup is best effort once an uncertain transaction has been selected.
        # Even cancellation/cleanup failure cannot turn it into an ordinary error
        # that callers might mistake for a safe retry. Reopen/query the original ID.
        try:
            self.db.close()
        except BaseException:
            pass

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield self.db
        except BaseException as body_error:
            try:
                self.db.rollback()
            except BaseException:
                self._close_after_uncertainty()
                raise CommitUnknown('rollback uncertain; reopen and query original job and attempt') from body_error
            raise
        else:
            try:
                self.db.commit()
            except BaseException as commit_error:
                # Do not retry any mutation under a new ID or claim rollback.
                self._close_after_uncertainty()
                raise CommitUnknown('reopen store and query original job and attempt') from commit_error


class InternalQueue:
    """Trusted-domain ONLY, not an authorization entry point.

    host.guard(source) must verify exact currently enabled source interval, MESSAGE
    ownership/generation/epoch, source_version and MEMORY scope epoch. It holds the
    relevant authority locks through the local commit and validates again on close.
    lease.current() returns that same Source, never a bool. Only synthetic tests
    implement this seam today. An arbitrary Python host is trusted code, not a token.
    """
    def __init__(self, store, host):
        self.store, self.host = store, host

    @contextmanager
    def _guard(self, source):
        if type(source) is not Source:
            raise InvalidInput('internal source binding required')
        source.validate()
        if not callable(getattr(self.host, 'guard', None)):
            raise Unavailable('trusted source host unavailable')
        operation_returned = False
        operation_error = None
        try:
            with self.host.guard(source) as lease:
                try:
                    if lease.current() != source:
                        raise Unavailable('source authority changed')
                    yield lease
                    operation_returned = True
                except BaseException as error:
                    operation_error = error
                    raise
        except BaseException:
            if operation_error is not None:
                raise operation_error
            if operation_returned:
                raise CommitUnknown('guard close failed; query original job and attempt') from None
            raise
        if operation_error is not None:
            # A trusted host must not suppress a transaction's primary error.
            raise operation_error

    @staticmethod
    def _check(lease, source):
        if lease.current() != source:
            raise Unavailable('source authority changed')

    @staticmethod
    def _key(source, mode):
        c = source.cursor
        return (c.scope, c.conversation_id, c.generation, c.epoch,
                source.source_version, source.memory_epoch, mode)

    @staticmethod
    def _status(row):
        return Status(row[0], row[1], row[3], row[4])

    @staticmethod
    def _find(db, source, job_id, attempt_id):
        identity(job_id)
        identity(attempt_id)
        row = db.execute('SELECT job_id,attempt_id,raw,state,processed,candidate FROM jobs '
                         'WHERE scope=? AND job_id=?', (source.cursor.scope, job_id)).fetchone()
        if row is None:
            raise Unavailable('original job absent; absence does not authorize resend')
        if row[1] != attempt_id or decode(row[2])[0] != source:
            raise Conflict('original attempt/source binding differs')
        return row

    def enqueue(self, source, rows, mode, job_id, attempt_id):
        identity(job_id)
        identity(attempt_id)
        raw = encode(source, rows, mode)
        with self._guard(source) as lease:
            with self.store.transaction() as db:
                old = db.execute('SELECT job_id,attempt_id,raw,state,processed,candidate FROM jobs '
                                 'WHERE scope=? AND (job_id=? OR attempt_id=?)',
                                 (source.cursor.scope, job_id, attempt_id)).fetchall()
                if old:
                    if len(old) != 1 or old[0][:3] != (job_id, attempt_id, raw):
                        raise Conflict('original ID payload differs')
                    result = self._status(old[0])
                else:
                    count = db.execute('SELECT count(*) FROM jobs WHERE scope=?',
                                       (source.cursor.scope,)).fetchone()[0]
                    if count >= 1000:
                        raise Unavailable('local candidate ledger full; no automatic eviction')
                    key = self._key(source, mode)
                    previous = db.execute('SELECT processed FROM cursors WHERE '
                        'scope=? AND conversation=? AND generation=? AND epoch=? AND '
                        'source_version=? AND memory_epoch=? AND mode=?', key).fetchone()
                    # Require initial after=0. A future trusted seed needs its own seam.
                    if source.cursor.after != (previous[0] if previous else 0):
                        raise Conflict('processing cursor gap/overlap')
                    active = db.execute('SELECT raw FROM jobs WHERE scope=? AND state!=?',
                                        (source.cursor.scope, 'completed')).fetchall()
                    if any(self._key(decode(r[0])[0], decode(r[0])[2]) == key for r in active):
                        raise Conflict('original interval still pending or unknown')
                    db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,NULL)',
                               (source.cursor.scope, job_id, attempt_id, raw,
                                'pending', source.cursor.after))
                    result = Status(job_id, attempt_id, 'pending', source.cursor.after)
                self._check(lease, source)
        return result

    def query_original(self, source, job_id, attempt_id):
        # No candidate bytes are returned or injected into a prompt by this adapter.
        with self._guard(source) as lease:
            with self.store.transaction() as db:
                result = self._status(self._find(db, source, job_id, attempt_id))
                self._check(lease, source)
        return result

    def begin_internal(self, source, job_id, attempt_id):
        # Records ownership of a LOCAL attempt, not permission for model dispatch.
        return self._transition(source, job_id, attempt_id, 'inflight')

    def recover_original(self, source, job_id, attempt_id):
        # Never requeue unknown/inflight under another attempt or replay a model call.
        return self._transition(source, job_id, attempt_id, 'unknown')

    def complete_candidate(self, source, job_id, attempt_id, candidate):
        if (type(candidate) is not bytes or not 1 <= len(candidate) <= 16384):
            raise InvalidInput('bounded immutable derived candidate required')
        try:
            candidate.decode('utf-8')
        except UnicodeError:
            raise InvalidInput('UTF-8 candidate required') from None
        return self._transition(source, job_id, attempt_id, 'completed', candidate)

    def _transition(self, source, job_id, attempt_id, target, candidate=None):
        with self._guard(source) as lease:
            with self.store.transaction() as db:
                row = self._find(db, source, job_id, attempt_id)
                state = row[3]
                if target == 'inflight':
                    if state != 'pending':
                        raise Conflict('attempt already started; reconcile original ID only')
                elif target == 'unknown':
                    if state not in ('inflight', 'unknown'):
                        raise Conflict('only original in-flight attempt may become unknown')
                elif target == 'completed':
                    if state == 'completed':
                        if row[5] != candidate:
                            raise Conflict('original result bytes differ')
                        self._check(lease, source)
                        return self._status(row)
                    if state not in ('inflight', 'unknown'):
                        raise Conflict('attempt not started')
                processed = source.cursor.through if target == 'completed' else row[4]
                db.execute('UPDATE jobs SET state=?,processed=?,candidate=? WHERE scope=? AND job_id=?',
                           (target, processed, candidate, source.cursor.scope, job_id))
                if target == 'completed':
                    _, _, mode = decode(row[2])
                    db.execute('INSERT INTO cursors VALUES(?,?,?,?,?,?,?,?) ON CONFLICT '
                               'DO UPDATE SET processed=excluded.processed',
                               self._key(source, mode) + (processed,))
                self._check(lease, source)
                result = Status(job_id, attempt_id, target, processed)
        return result
