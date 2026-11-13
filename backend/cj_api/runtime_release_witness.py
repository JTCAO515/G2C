"""Original signed HK release identity for bounded source qualification.

The existing checkpoint protocol rotates deployment_identity on backup/restore
and owns RELEASE_LOCK exclusively. This reader uses that same native barrier;
it creates neither a parallel epoch nor another deployment authority.
"""
from dataclasses import dataclass

from psycopg import Error as DatabaseError
from runtime_adapter.contract import Unavailable


@dataclass(frozen=True)
class ReleaseWitness:
    instance: str
    lineage: str


class NativeReleaseWitness:
    def __init__(self,database,scope,control,*,guard,release):
        # Trusted host composition: no caller-selected database/control path.
        self.database,self.scope,self.control=database,scope,control
        self.guard,self.release=guard,release

    def _read(self,connection):
        try:release=self.release.require_release(connection,self.control)
        except ValueError:raise Unavailable('ORIGINAL_DATABASE_RELEASE_UNAVAILABLE')from None
        return ReleaseWitness(release['instance'],release['lineage'])

    def observe(self):
        return self._protected(None,lambda value:value)

    def with_current(self,expected:ReleaseWitness,project):
        """Short local projection only; never wrap a provider/network operation.

        This excludes native checkpoint restore while projecting. Other native
        Trip/Memory/MESSAGE/account guards are still separately required.
        """
        def materialized(value):
            result=project(value)
            if type(result)is not bytes or len(result)>1_048_576:
                raise Unavailable('BOUNDED_RELEASE_PROJECTION_REQUIRED')
            return result
        return self._protected(expected,materialized)

    def _protected(self,expected,project):
        self.guard()
        try:
            connection=self.database.connect(self.scope)
            try:
                with connection.transaction(),connection.cursor()as cursor:
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL lock_timeout='5s'")
                    cursor.execute("SET LOCAL statement_timeout='10s'")
                    # Set timeouts before the host's bind hook can take the
                    # same native shared release barrier.
                    connection.bind_scope(cursor)
                    try:self.release.runtime_transaction(cursor,self.control)
                    except ValueError:raise Unavailable('ORIGINAL_DATABASE_RELEASE_UNAVAILABLE')from None
                    before=self._read(connection)
                    if expected is not None and before!=expected:
                        raise Unavailable('ORIGINAL_DATABASE_RELEASE_CHANGED')
                    result=project(before)
                    if self._read(connection)!=before:
                        raise Unavailable('ORIGINAL_DATABASE_RELEASE_CHANGED')
                    self.guard()
            finally:connection.close()
            # A failed transaction/return never publishes the earlier result.
            self.guard()
            return result
        except (DatabaseError,OSError):
            raise Unavailable('ORIGINAL_DATABASE_RELEASE_UNAVAILABLE')from None
