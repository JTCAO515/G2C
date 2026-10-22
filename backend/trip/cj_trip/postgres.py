"""Injected DB-API PostgreSQL repository. All methods are server-internal.

Per-scope locking deliberately serializes the first slice, including competing
new-trip inserts. No network/provider work belongs in the confirmation callback.
"""
from contextlib import contextmanager
from .domain import Action, Proposal, Receipt, Trip, Conflict, Denied, CommitUnknown, identifier


class Repository:
    def __init__(self, connect, scope, confirm=None, guard=None):
        self.connect, self.scope = connect, identifier(scope)
        self.confirm = confirm
        self.guard = guard or (lambda stage: None)

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE', (self.scope,))
            if cur.fetchone() is None: raise Denied('scope not provisioned')
            self.guard('transaction')
            yield cur
            self.guard('commit')
            try: conn.commit()
            except Exception as exc: raise CommitUnknown('query original action; do not replace ID') from exc
            self.guard('return')
        except BaseException:
            try: conn.rollback()
            except Exception: pass  # Preserve original unknown outcome / denial.
            raise
        finally:
            conn.close()

    def _proposal(self, cur, pid):
        cur.execute('SELECT proposal_id,trip_id,expected_version,basis_version,expires_at,content,candidate_hash,status FROM cj_trip_proposal WHERE scope=%s AND proposal_id=%s', (self.scope,pid))
        row = cur.fetchone()
        if row is None: raise Denied('candidate unavailable')
        p = Proposal(*row[:5], bytes(row[5]))
        if p.digest(self.scope) != row[6]: raise Conflict('candidate integrity')
        return p, row[6], row[7]

    def publish(self, proposal):
        """Trusted CJ014 ingress only. Never mapped from a user/model request directly."""
        if not isinstance(proposal, Proposal): raise ValueError('validated proposal required')
        with self.transaction() as cur:
            cur.execute('SELECT candidate_hash FROM cj_trip_proposal WHERE scope=%s AND proposal_id=%s', (self.scope,proposal.proposal_id))
            old = cur.fetchone()
            digest = proposal.digest(self.scope)
            if old:
                if old[0] != digest: raise Conflict('immutable candidate')
                return digest
            cur.execute('INSERT INTO cj_trip_proposal VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (self.scope,proposal.proposal_id,proposal.trip_id,proposal.expected_version,proposal.basis_version,proposal.expires_at,proposal.content,digest,'pending'))
            return digest

    def _receipt(self, cur, aid):
        cur.execute('SELECT action_id,kind,proposal_id,candidate_hash,trip_id,committed_version,original_input FROM cj_trip_receipt WHERE scope=%s AND action_id=%s', (self.scope,aid))
        row = cur.fetchone()
        return (Receipt(*row[:6]), bytes(row[6])) if row else None

    def act(self, action):
        if not isinstance(action, Action): raise ValueError('validated action required')
        with self.transaction() as cur:
            previous = self._receipt(cur, action.action_id)
            if previous:
                if previous[1] != action.raw(): raise Conflict('action ID input conflict')
                return previous[0]
            p, digest, status = self._proposal(cur, action.proposal_id)
            if action.candidate_hash != digest: raise Conflict('candidate changed')
            cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
            now = cur.fetchone()[0]
            if status != 'pending' or p.expires_at <= now: raise Conflict('candidate not eligible')
            if self.confirm is None or self.confirm(self.scope, action, p) is not True:
                raise Denied('trusted review and confirmation unavailable')
            cur.execute('SELECT version FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (self.scope,p.trip_id))
            row = cur.fetchone()
            if (row[0] if row else 0) != p.expected_version: raise Conflict('trip version conflict')
            version = None
            if action.kind == 'accept':
                version = p.expected_version + 1
                cur.execute('INSERT INTO cj_trip_record VALUES (%s,%s,%s,%s) ON CONFLICT(scope,trip_id) DO UPDATE SET version=EXCLUDED.version,content=EXCLUDED.content', (self.scope,p.trip_id,version,p.content))
            receipt = Receipt(action.action_id,action.kind,p.proposal_id,digest,p.trip_id,version)
            cur.execute('UPDATE cj_trip_proposal SET status=%s WHERE scope=%s AND proposal_id=%s', ('accepted' if action.kind == 'accept' else 'rejected',self.scope,p.proposal_id))
            cur.execute('INSERT INTO cj_trip_receipt VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (self.scope,receipt.action_id,receipt.kind,receipt.proposal_id,receipt.candidate_hash,receipt.trip_id,receipt.committed_version,action.raw()))
            # Time may advance while trusted validation runs. Roll back everything.
            cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
            if p.expires_at <= cur.fetchone()[0]: raise Conflict('candidate expired before commit')
            return receipt

    def retire(self, proposal_id, state, replacement_id=None):
        """Trusted lifecycle; generation cancellation must never call this method."""
        if state not in ('expired','superseded'): raise ValueError('invalid retirement')
        with self.transaction() as cur:
            p, _, status = self._proposal(cur, identifier(proposal_id))
            if status == state: return state
            if status != 'pending': raise Conflict('terminal candidate')
            if state == 'expired':
                cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
                if p.expires_at > cur.fetchone()[0]: raise Conflict('not expired')
            else:
                replacement, _, replacement_status = self._proposal(cur, identifier(replacement_id))
                if replacement.proposal_id == p.proposal_id or replacement.trip_id != p.trip_id or replacement_status != 'pending': raise Conflict('invalid replacement')
            cur.execute('UPDATE cj_trip_proposal SET status=%s WHERE scope=%s AND proposal_id=%s', (state,self.scope,p.proposal_id))
            return state

    def query_action(self, action_id):
        with self.transaction() as cur:
            row = self._receipt(cur, identifier(action_id))
            return row[0] if row else None

    def detail(self, trip_id):
        with self.transaction() as cur:
            cur.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (self.scope,identifier(trip_id)))
            row = cur.fetchone()
            return Trip(row[0],row[1],bytes(row[2])) if row else None

    def list_trips(self, after='', limit=20):
        if type(limit) is not int or not 1 <= limit <= 100: raise ValueError('invalid limit')
        if after: identifier(after)
        with self.transaction() as cur:
            cur.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s AND trip_id>%s ORDER BY trip_id LIMIT %s', (self.scope,after,limit))
            return [Trip(r[0],r[1],bytes(r[2])) for r in cur.fetchall()]
