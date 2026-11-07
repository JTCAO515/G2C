"""ACCOUNT-ADMISSION@2: fresh local retirement read through cj_m1_runtime."""
from dataclasses import asdict
from cj_auth.interfaces import Fact
from cj_cleanup.core import Scope,digest,encode
from .composition import CompositionUnavailable


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


def account_checker_for(auth_dir,database):
    from .local_worker_context import checker_for
    return checker_for(auth_dir,account_retired=retired_for(database))
