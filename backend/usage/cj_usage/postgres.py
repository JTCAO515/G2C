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
