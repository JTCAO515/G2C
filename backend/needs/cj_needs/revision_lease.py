"""Authenticated local revision lease; distinct from the read-only projection API."""
from contextlib import contextmanager
import hashlib
import threading
from psycopg import Error as DatabaseError
from psycopg.pq import TransactionStatus
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
from .domain import Denied, decode, validate_fields


class LeaseUnavailable(Exception):
    """Original authority or stored state cannot be established; never permission."""


class RevisionLease:
    """Explicit canonical checker + trusted resolver for one local identity profile.

    resolve(principal) returns (fresh_connect, message_scope, needs_scope). The
    connection factory must implement the transaction-entry scope hook; absent
    scope fails via RLS. hold(token, original_run_binding) yields a throwing check
    only during its authenticated, same-thread READ ONLY lifetime. Callers acquire
    RUN before entering and keep this context alive until RUN commit completes.
    This does not activate or change the formal local_app/run_worker assembly.
    """
    def __init__(self, checker, resolve, *, environment, issuer, audience):
        if environment != 'local' or not issuer or not audience:
            raise ValueError('explicit local identity profile required')
        self.checker, self.resolve = checker, resolve
        self.issuer, self.audience = issuer, audience

    def _admit(self, token, original=None):
        try: result = self.checker.check(token)
        except Exception: raise LeaseUnavailable('NEEDS admission unavailable') from None
        if result.status is AdmissionStatus.UNKNOWN:
            raise LeaseUnavailable('NEEDS admission unknown')
        principal = result.principal
        if (result.status is not AdmissionStatus.ALLOWED or not isinstance(principal,TrustedPrincipal)
                or (principal.issuer,principal.audience) != (self.issuer,self.audience)
                or original is not None and principal != original):
            raise Denied('NEEDS admission changed or denied')
        return principal

    @contextmanager
    def hold(self, token, binding):
        principal = self._admit(token)
        connect, message_scope, needs_scope = self.resolve(principal)
        if message_scope != binding.scope:
            raise Denied('original RUN owner mismatch')
        try: connection = connect()
        except DatabaseError:
            raise LeaseUnavailable('NEEDS connection unavailable') from None
        cursor = None
        active = False
        failed = False
        thread = threading.get_ident()
        try:
            if connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE or connection.closed:
                raise LeaseUnavailable('fresh idle connection required')
            cursor = connection.cursor()
            cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY')
            bind_scope = getattr(connection, 'bind_scope', None)  # documented scoped DB-API extension
            if bind_scope is not None: bind_scope(cursor)
            cursor.execute("SET LOCAL lock_timeout='5s'")
            cursor.execute("SET LOCAL statement_timeout='10s'")
            cursor.execute('SELECT pg_advisory_xact_lock_shared(public.cj_needs_fence_key(%s))',(needs_scope,))
            active = True

            def check():
                if not active or threading.get_ident() != thread:
                    raise LeaseUnavailable('NEEDS lease no longer active')
                self._admit(token, principal)
                cursor.execute('SELECT b.needs_id,b.needs_version,b.content_sha256,r.conversation_id,r.generation,r.sequence '
                    'FROM cj_message_needs_binding b JOIN cj_message_receipt r '
                    'ON (r.scope,r.message_id,r.run_id)=(b.message_scope,b.message_id,b.run_id) '
                    'WHERE b.message_scope=%s AND b.message_id=%s AND b.run_id=%s AND b.needs_scope=%s',
                    (message_scope,binding.message_id,binding.run_id,needs_scope))
                original = cursor.fetchone()
                if original is None or original[3:] != (binding.conversation_id,binding.generation,binding.message_sequence):
                    raise Denied('original NEEDS binding unavailable')
                cursor.execute('SELECT n.version,n.content,h.content,h.source_kind FROM cj_needs_record n '
                    'JOIN cj_needs_revision h ON (h.scope,h.needs_id,h.version)=(n.scope,n.needs_id,n.version) '
                    'WHERE n.scope=%s AND n.needs_id=%s',(needs_scope,original[0]))
                current = cursor.fetchone()
                if current is None or current[0] != original[1]:
                    raise Denied('original NEEDS revision changed')
                content = bytes(current[1])
                if (current[3] != 'user_provided' or content != bytes(current[2])
                        or hashlib.sha256(content).hexdigest() != original[2]):
                    raise LeaseUnavailable('NEEDS content integrity unavailable')
                try: validate_fields(decode(content), complete=True)
                except (ValueError, TypeError, UnicodeError):
                    raise LeaseUnavailable('invalid NEEDS content') from None
                self._admit(token, principal)

            check()
            yield check
            check()
        except DatabaseError:
            failed = True
            raise LeaseUnavailable('NEEDS storage outcome unavailable') from None
        except BaseException:
            failed = True
            raise
        finally:
            active = False
            cleanup_failed = False
            for cleanup in ([connection.rollback] + ([cursor.close] if cursor is not None else []) + [connection.close]):
                try: cleanup()
                except BaseException: cleanup_failed = True
            if not failed:
                if cleanup_failed: raise LeaseUnavailable('NEEDS lease cleanup unavailable')
                self._admit(token, principal)
