"""Local runtime uses the existing NEEDS fence, SQL writer and immutable history."""
from .domain import Denied
from .postgres import Repository


class RuntimeRepository(Repository):
    read_only = False

    def __init__(self, connect, scope, guard, *, strict_close=True):
        super().__init__(connect, scope, guard, strict_close=strict_close)
        self._creating = False

    def _begin(self, conn, cur):
        mode = ' READ ONLY' if self.read_only else ''
        cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'+mode)
        conn.bind_scope(cur)
        if not self.read_only:
            cur.execute("SELECT set_config('cj.needs_runtime_abi','NEEDS-MANUAL-RUNTIME@1',true)")
        cur.execute("SET LOCAL lock_timeout = '5s'")
        cur.execute("SET LOCAL statement_timeout = '10s'")
        # Writer fence precedes any row lock/write. Shared read projections do
        # not require UPDATE or SELECT FOR UPDATE on the scope table.
        lock = 'pg_advisory_xact_lock_shared' if self.read_only else 'pg_advisory_xact_lock'
        cur.execute('SELECT pg_catalog.'+lock+'(public.cj_needs_fence_key(%s))',(self.scope,))
        if self._creating:
            self.guard('create_scope')
            cur.execute('INSERT INTO cj_needs_scope(scope) VALUES(%s) ON CONFLICT DO NOTHING',(self.scope,))
        cur.execute('SELECT scope FROM cj_needs_scope WHERE scope=%s',(self.scope,))
        if cur.fetchone() is None: raise Denied('NEEDS scope unavailable')

    def act(self, command):
        self._creating = True
        try: return super().act(command)
        finally: self._creating = False


class ReadOnlyRuntimeRepository(RuntimeRepository):
    read_only = True
