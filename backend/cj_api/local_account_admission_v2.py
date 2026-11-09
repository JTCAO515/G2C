"""ACCOUNT-ADMISSION@2: fresh local retirement read through cj_m1_runtime."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from threading import get_ident

from psycopg.pq import TransactionStatus

from cj_auth.interfaces import Fact
from cj_cleanup.core import Scope,digest,encode
from .composition import CompositionUnavailable


_retirement_permission = ContextVar('retirement_read_permission', default=None)
_retirement_lease = ContextVar('retirement_read_lease', default=None)


class _RetirementReadLease:
    def __init__(self, database, require_current, purpose):
        self.database = database
        self.require_current = require_current
        self.purpose = purpose
        self.thread = get_ident()
        self.owner = None
        self.connection = None

    def read(self, owner):
        if get_ident() != self.thread or self.owner not in (None, owner):
            raise CompositionUnavailable('retirement read scope changed')
        self.require_current()
        if self.connection is None:
            self.connection = self.database.connect(owner)
            self.owner = owner
        # Keep each release lock and each snapshot within a single admission.
        # A concurrent retirement must be visible to the next SELECT.
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY')
            self.connection.bind_scope(cursor)
            cursor.execute('SELECT public.cj_account_scope_current(%s)', (owner,))
            return _retirement_fact(cursor.fetchone())

    def borrow(self, database, owner):
        connection = self.connection
        if (database is not self.database or get_ident() != self.thread or owner != self.owner
                or connection is None or connection.closed
                or connection.info.transaction_status != TransactionStatus.IDLE):
            raise CompositionUnavailable('idle original request connection required')
        self.require_current()
        return connection


@contextmanager
def permit_retirement_read_lease(database, require_current):
    """Let an explicit host route opt its synchronous read operation in."""
    token = _retirement_permission.set((database, require_current))
    try:
        yield
    finally:
        _retirement_permission.reset(token)


@contextmanager
def retirement_read_operation(*, purpose=None):
    """Acquire and close the leased connection in the guarded worker thread."""
    permission = _retirement_permission.get()
    if permission is None:
        yield
        return
    lease = _RetirementReadLease(*permission, purpose)
    token = _retirement_lease.set(lease)
    try:
        yield
    finally:
        _retirement_lease.reset(token)
        if lease.connection is not None:
            lease.connection.close()


def request_scope_connection(database, scope, *, purpose):
    """Borrow the already authenticated scope in the current synchronous operation."""
    lease = _retirement_lease.get()
    if lease is None or lease.purpose != purpose:
        return None
    return lease.borrow(database, scope)


def subject_digest(principal):
    return digest(encode(asdict(Scope.from_principal('local',principal))))


def retired_for(database):
    """Canonical owner-scoped runtime SELECT only, with no cleanup credential.

    Missing schema/role/read certainty raises; the canonical AdmissionChecker
    converts the unavailable lookup to UNKNOWN, never presumed membership.
    """
    def retired(principal):
        from .local_app import scope_for
        owner=scope_for(principal.issuer,principal.subject)
        lease = _retirement_lease.get()
        if lease is not None and lease.database is database:
            return lease.read(owner)
        with database.connect(owner) as conn:
            row=conn.execute('SELECT public.cj_account_scope_current(%s)',(owner,)).fetchone()
        return _retirement_fact(row)
    return retired


def _retirement_fact(row):
    if row not in ((True,), (False,)):
        raise CompositionUnavailable('account retirement state unavailable')
    return Fact.NO if row[0] else Fact.YES


def retired_in_transaction(cursor, scope):
    """Check fresh retirement state on the same locked, bound MESSAGE transaction."""
    from .local_app import scope_for

    def retired(principal):
        if scope_for(principal.issuer, principal.subject) != scope:
            raise CompositionUnavailable('account retirement scope changed')
        cursor.execute('SELECT public.cj_account_scope_current(%s)', (scope,))
        return _retirement_fact(cursor.fetchone())

    return retired


def account_checker_for(auth_dir,database,*,selected_subjects=None):
    from .local_worker_context import checker_for
    return checker_for(auth_dir,account_retired=retired_for(database),selected_subjects=selected_subjects)
