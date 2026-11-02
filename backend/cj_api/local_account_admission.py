"""ACCOUNT-ADMISSION@1: key-free fresh local account-retirement lookup."""
from dataclasses import asdict
import psycopg
from cj_auth.interfaces import Fact
from cj_cleanup.core import Scope,digest,encode


def subject_digest(principal):
    return digest(encode(asdict(Scope.from_principal('local',principal))))


def retired_for(database):
    """Trusted host database only; accepts a canonical verified principal.

    No caller scope/GUC, capability key, resource provisioning or missing-table
    fallback. AdmissionChecker converts lookup failures to UNKNOWN.
    """
    def retired(principal):
        subject=subject_digest(principal)
        with psycopg.connect(**dict(database.conninfo,user='cj_local_cleanup')) as conn:
            conn.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(subject,))
            row=conn.execute('SELECT 1 FROM cj_account_fence WHERE subject_digest=%s',(subject,)).fetchone()
        return Fact.YES if row is not None else Fact.NO
    return retired
