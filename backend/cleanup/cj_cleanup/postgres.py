"""Scoped PostgreSQL metadata candidate; no hook execution, auth mutation, or wire.

Injected new DB-API connection per transaction, no DSN/environment lookup.
Only cj_cleanup_journal_candidate is accessed. Full original journal + derived
state are committed in the same row/transaction; state is verified on every load.
"""
from contextlib import contextmanager
from dataclasses import asdict
from . import core


class Unavailable(Exception): pass
class CommitUnknown(Exception): pass


def state_bytes(op):
    value = asdict(op)
    for step in value['steps']:
        if step['receipt_bytes'] is not None:
            step['receipt_bytes'] = step['receipt_bytes'].hex()
    return core.encode(value)


class Repository:
    def __init__(self, connect, scope, guard):
        if connect is None or not isinstance(scope, core.Scope) or not callable(guard):
            raise Unavailable('trusted composition required')
        self.connect, self.scope, self.guard = connect, scope, guard
        self._scope_bytes = core.encode(asdict(scope))

    @contextmanager
    def _transaction(self, *, writing):
        conn = None
        accepted = commit_started = failed = False
        connect, scope, guard = self.connect, self.scope, self.guard
        scope_bytes = self._scope_bytes
        def check(stage):
            if (self.connect is not connect or self.scope != scope or self.guard is not guard
                    or self._scope_bytes != scope_bytes):
                raise core.Denied('cleanup binding changed')
            guard(stage)
            if (self.connect is not connect or self.scope != scope or self.guard is not guard
                    or self._scope_bytes != scope_bytes):
                raise core.Denied('cleanup binding changed')
        try:
            conn = connect()
            if conn.autocommit is not False or conn.closed is not False or conn.info.transaction_status != 0:
                raise Unavailable('fresh transaction required')
            accepted = True
            cur = conn.cursor()
            cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            check('transaction')
            yield cur
            check('commit')
            commit_started = True
            conn.commit()
        except BaseException as exc:
            failed = True
            if writing and commit_started: raise CommitUnknown('query original operation; do not retry hook') from None
            if isinstance(exc, (core.Invalid, core.Conflict, core.Denied, Unavailable)):
                raise
            raise Unavailable('cleanup metadata unavailable') from None
        finally:
            if conn is not None:
                if accepted and not commit_started:
                    try: conn.rollback()
                    except BaseException: pass  # preserve original failure; no success is returned
                try: conn.close()
                except BaseException:
                    # Cleanup must never replace an earlier body/commit failure.
                    if not failed:
                        if writing and commit_started: raise CommitUnknown('query original operation; do not retry hook') from None
                        raise Unavailable('cleanup metadata unavailable') from None
                if not failed:
                    # close() is external code too: only publish after its callbacks,
                    # and with no further connection cleanup after this final fence.
                    try: check('return')
                    except BaseException as exc:
                        if writing and commit_started: raise CommitUnknown('query original operation; do not retry hook') from None
                        if isinstance(exc, (core.Denied, Unavailable)): raise
                        raise Unavailable('cleanup metadata unavailable') from None

    def _load(self, cur, operation_id, *, lock=False):
        core.identifier(operation_id)
        cur.execute('SELECT operation_id,revision,journal_bytes,state_bytes FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s' + (' FOR UPDATE' if lock else ''), (self._scope_bytes,))
        row = cur.fetchone()
        if row is None or row[0] != operation_id: raise core.Denied('operation unavailable')
        memory = core.Repository.rebuild(bytes(row[2]), recover_inflight=False)
        op = memory.query(self.scope, operation_id)
        # A row contains exactly one scope operation, never an embedded unrelated history.
        if len(memory._operations) != 1 or op.revision != row[1] or state_bytes(op) != bytes(row[3]):
            raise Unavailable('journal/state mismatch')
        return memory, op

    def create(self, op):
        if op.scope != self.scope: raise core.Denied('scope mismatch')
        memory = core.Repository()
        pristine = core.request(op.scope, op.operation_id, op.confirmation_digest, op.manifest,
                                tuple(s.target for s in op.steps if s.available))
        if op != pristine: raise core.Invalid('new operation must be pristine')
        memory.create(op)
        with self._transaction(writing=True) as cur:
            cur.execute('INSERT INTO cj_cleanup_journal_candidate(scope_bytes,operation_id,revision,journal_bytes,state_bytes) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(scope_bytes) DO NOTHING',
                        (self._scope_bytes,op.operation_id,op.revision,memory.journal(),state_bytes(op)))
            # Concurrent INSERT conflict waits for its owning transaction; lock exact scope.
            cur.execute('SELECT operation_id FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s FOR UPDATE',(self._scope_bytes,))
            existing = cur.fetchone()
            if existing[0] != op.operation_id: raise core.Conflict('original scope operation must be recovered')
            memory, current = self._load(cur,op.operation_id)
            return memory.create(op)  # exact same confirmation+manifest recovers original

    def query(self, operation_id):
        # No recovery write, lease grant, dispatch, receipt settlement, or automatic retry.
        with self._transaction(writing=False) as cur:
            return self._load(cur,operation_id)[1]

    def journal(self, operation_id):
        with self._transaction(writing=False) as cur:
            return self._load(cur,operation_id)[0].journal()

    def _apply(self, operation_id, expected_revision, method, *args):
        with self._transaction(writing=True) as cur:
            memory, old = self._load(cur,operation_id,lock=True)
            new = getattr(memory,method)(self.scope,operation_id,expected_revision,*args)
            cur.execute('UPDATE cj_cleanup_journal_candidate SET revision=%s,journal_bytes=%s,state_bytes=%s WHERE scope_bytes=%s AND operation_id=%s AND revision=%s',
                        (new.revision,memory.journal(),state_bytes(new),self._scope_bytes,operation_id,old.revision))
            if cur.rowcount != 1: raise core.Conflict('revision conflict')
            return new

    def intent(self, operation_id, expected_revision, target, invocation):
        return self._apply(operation_id,expected_revision,'intent',target,invocation)

    def receipt(self, operation_id, expected_revision, target, raw):
        return self._apply(operation_id,expected_revision,'receipt',target,raw)

    def audit(self, operation_id, expected_revision, manifest):
        return self._apply(operation_id,expected_revision,'audit',manifest)

    def recover(self, operation_id, expected_revision):
        # Explicit original-operation reconciliation after loss of the prior writer.
        return self._apply(operation_id,expected_revision,'recover')
