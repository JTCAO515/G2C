"""Injected DB-API repository. No DSN, role, provider or automatic provisioning."""
from contextlib import contextmanager
import logging
from .codec import decode, encode, CorruptLedger
from .core import integer, label


class CommitUnknown(Exception):
    """Query original attempt; never redispatch after uncertain commit acknowledgement."""


class RepositoryUnavailable(Exception):
    pass


class PostgresRepository:
    def __init__(self, connect, scope):
        label(scope)
        if not callable(connect):
            raise ValueError('connection factory required')
        self.connect, self.scope = connect, scope

    @contextmanager
    def transaction(self):
        # Factory supplies a NEW idle non-autocommit connection, with canonical
        # runtime identity/RLS scope already established. No pooled dirty session.
        conn = self.connect()
        cur = None

        def cleanup(action):
            try:
                action()
            except BaseException:
                try:
                    logging.getLogger(__name__).warning('usage_repository_cleanup_failed')
                except BaseException:
                    pass

        try:
            if conn.autocommit:
                raise RepositoryUnavailable('autocommit forbidden')
            cur = conn.cursor()
            try:
                cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                bind_scope = getattr(conn, 'bind_scope', None)  # existing scoped DB-API extension
                if bind_scope is not None: bind_scope(cur)
                cur.execute('SELECT revision, format_version, ledger FROM public.cj_usage_ledger_candidate WHERE scope_id=%s FOR UPDATE', (self.scope,))
                row = cur.fetchone()
                if row is None:
                    raise RepositoryUnavailable('scope unavailable')
                revision, version, raw = row
                integer(revision)
                if type(version) is not int or version != 1:
                    raise CorruptLedger('unsupported ledger version')
                ledger = decode(raw)
                yield ledger
                encoded = encode(ledger)
                cur.execute('UPDATE public.cj_usage_ledger_candidate SET ledger=%s::jsonb, revision=revision+1 WHERE scope_id=%s AND revision=%s', (encoded, self.scope, revision))
                if cur.rowcount != 1:
                    raise RepositoryUnavailable('scope changed')
            except BaseException:
                cleanup(conn.rollback)
                raise
            try:
                conn.commit()
            except BaseException:
                # Commit may have succeeded. Cleanup is not a rollback receipt.
                raise CommitUnknown('usage commit acknowledgement unknown') from None
        finally:
            if cur is not None:
                cleanup(cur.close)
            cleanup(conn.close)

    def read_status(self, attempt_id, *, guard, max_response_bytes, project=None, expected_period=None):
        """SELECT-only bytes under an ORIGINAL canonical authority lifetime.

        guard is its synchronous throwing check, not a cached ALLOWED boolean.
        This storage seam does not authenticate, resolve identity or grant access.
        project receives only minimal status bytes, never ledger/input digest.
        """
        import inspect
        from .read_status import ReadUnavailable, encode_status, status_of
        label(attempt_id)
        integer(max_response_bytes, 1)
        if not callable(guard) or (project is not None and not callable(project)):
            raise ReadUnavailable('original authority guard required')
        if expected_period is not None:
            if type(expected_period) is not tuple or len(expected_period) != 2:
                raise ReadUnavailable('explicit historical period required')
            integer(expected_period[0])
            integer(expected_period[1], expected_period[0] + 1)
        scope, connect = self.scope, self.connect
        conn = cur = None
        encoded = None
        primary = cleanup_error = None

        def check():
            result = guard()
            if inspect.iscoroutine(result):
                result.close()
            if result is not None or self.scope != scope or self.connect is not connect:
                raise ReadUnavailable('read binding changed or invalid guard')

        try:
            check()
            conn = connect()
            check()
            if conn.autocommit:
                raise ReadUnavailable('autocommit forbidden')
            cur = conn.cursor()
            check()
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            check()
            cur.execute('SELECT revision, format_version, ledger FROM public.cj_usage_ledger_candidate WHERE scope_id=%s', (scope,))
            check()
            row = cur.fetchone()
            check()
            if row is None:
                raise RepositoryUnavailable('scope unavailable')
            revision, version, raw = row
            integer(revision)
            if type(version) is not int or version != 1:
                raise CorruptLedger('unsupported ledger version')
            ledger = decode(raw)
            if expected_period is not None and (ledger.config.period_start, ledger.config.period_end) != expected_period:
                raise ReadUnavailable('historical period binding changed')
            attempt = ledger.attempts.get(attempt_id)
            if attempt is None:
                raise RepositoryUnavailable('attempt unavailable')
            encoded = encode_status(status_of(attempt, ledger.config))
            if len(encoded) > max_response_bytes:
                raise ReadUnavailable('status exceeds configured bound')
            if project is not None:
                encoded = project(encoded)
                if inspect.iscoroutine(encoded):
                    encoded.close()
                if type(encoded) is not bytes:
                    raise ReadUnavailable('projection must return materialized bytes')
            if len(encoded) > max_response_bytes:
                raise ReadUnavailable('projection exceeds configured bound')
            check()
            try:
                conn.commit()
            except BaseException:
                raise CommitUnknown('usage read completion acknowledgement unknown') from None
            check()
        except BaseException as exc:
            primary = exc
            if conn is not None and not isinstance(exc, CommitUnknown):
                try:
                    conn.rollback()
                except BaseException:
                    pass
        finally:
            # Close callbacks precede final guard; errors always withhold bytes.
            for resource in (cur, conn):
                if resource is not None:
                    try:
                        resource.close()
                    except BaseException as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
        if primary is not None:
            raise primary
        if cleanup_error is not None:
            raise ReadUnavailable('usage read cleanup failed') from None
        check()
        return encoded
