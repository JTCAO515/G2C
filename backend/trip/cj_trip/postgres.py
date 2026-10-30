"""Injected DB-API PostgreSQL repository. All methods are server-internal.

Per-scope locking deliberately serializes the first slice, including competing
new-trip inserts. No network/provider work belongs in the confirmation callback.
"""
from contextlib import contextmanager
import logging
import json

logger = logging.getLogger(__name__)
from .domain import Action, Proposal, ProposalDetail, Receipt, Trip, Conflict, Denied, CommitUnknown, identifier


class Repository:
    def __init__(self, connect, scope, confirm=None, guard=None, *, structured=False):
        self.connect, self.scope = connect, identifier(scope)
        self.confirm = confirm
        self.guard = guard or (lambda stage: None)
        self.structured = structured
        self.manual_origin = None
        self.needs_actions = None
        self.needs_edits = None

    @contextmanager
    def transaction(self, before_commit=None):
        conn = self.connect()
        accepted = False
        commit_started = False
        primary_error = None
        try:
            # psycopg PostgreSQL status: IDLE=0. Missing/unknown state fails closed.
            # Inspect before cursor creation or any SQL; never take over caller work.
            if (getattr(conn, 'autocommit', None) is not False
                    or getattr(getattr(conn, 'info', None), 'transaction_status', None) != 0
                    or getattr(conn, 'closed', None) is not False):
                raise Denied('fresh non-autocommit PostgreSQL connection required')
            accepted = True
            cur = conn.cursor()
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            bind_scope = getattr(conn, 'bind_scope', None)
            if bind_scope is not None:
                bind_scope(cur)
            cur.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE', (self.scope,))
            if cur.fetchone() is None: raise Denied('scope not provisioned')
            self.guard('transaction')
            yield cur
            self.guard('commit')
            if before_commit is not None: before_commit(cur)
            commit_started = True
            try: conn.commit()
            except BaseException as exc: raise CommitUnknown('query original action; do not replace ID') from exc
            self.guard('return')
        except BaseException as exc:
            primary_error = exc
            if commit_started:
                exc.commit_possible = True
            if accepted:
                try: conn.rollback()
                except BaseException: self._cleanup_warning('rollback')
            raise
        finally:
            try: conn.close()
            except BaseException as exc:
                self._cleanup_warning('close')
                if primary_error is None and not isinstance(exc, Exception):
                    # A new cancellation/interrupt is not successful delivery. Keep
                    # it visible, with original-action reconciliation if commit ran.
                    exc.commit_possible = commit_started
                    raise

    @staticmethod
    def _cleanup_warning(operation):
        # No exception text, token, identifiers, content or connection details.
        # Even a broken log handler must not replace the original business result.
        try: logger.warning('TRIP connection cleanup failed: %s', operation)
        except BaseException: pass

    def _content(self, content, *, validated=False):
        document = json.loads(content)
        if type(document) is dict and document.get('content_version') in ('structured.1','structured.2'):
            if not self.structured:
                raise Denied('structured Trip requires explicit versioned consumer')
            if not validated:
                if document['content_version']=='structured.2':
                    from .structured_v2 import validate_document
                else:
                    from .structured import validate_document
                from .domain import packed
                validate_document(document)
                if packed(document) != content: raise ValueError('canonical stored Trip required')
        return content

    def _proposal(self, cur, pid):
        cur.execute('SELECT proposal_id,trip_id,expected_version,basis_version,expires_at,content,candidate_hash,status FROM cj_trip_proposal WHERE scope=%s AND proposal_id=%s', (self.scope,pid))
        row = cur.fetchone()
        if row is None: raise Denied('candidate unavailable')
        p = Proposal(*row[:5], self._content(bytes(row[5]), validated=True))
        if p.digest(self.scope) != row[6]: raise Conflict('candidate integrity')
        return p, row[6], row[7]

    def publish(self, proposal):
        """Trusted CJ014 ingress only. Never mapped from a user/model request directly."""
        if not isinstance(proposal, Proposal): raise ValueError('validated proposal required')
        self._content(proposal.content, validated=True)
        with self.transaction() as cur:
            return self._publish_in_tx(cur, proposal)

    def _publish_in_tx(self, cur, proposal):
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
        pending = None
        def final_eligibility(cur):
            self._final_action_eligibility(cur, action, pending)
        with self.transaction(before_commit=final_eligibility) as cur:
            receipt, pending = self._act_in_tx(cur, action)
            return receipt

    def _final_action_eligibility(self, cur, action, p):
        if p is not None:
            # Last potentially slow admission check has finished. The scope lock
            # still protects the candidate/content/version checked in this txn.
            cur.execute('SELECT EXTRACT(EPOCH FROM clock_timestamp())')
            database_now = cur.fetchone()[0]
            if p.expires_at <= database_now:
                raise Conflict('candidate expired before commit')
            # Additive expiry check; legacy validators retain their single call.
            # The issuer hook uses DB time and performs no resource callbacks.
            final_confirmation = getattr(self.confirm, 'check_before_commit', None)
            if final_confirmation is not None:
                final_confirmation(self.scope, action, p, database_now)

    def _act_in_tx(self, cur, action):
        previous = self._receipt(cur, action.action_id)
        if previous:
            if previous[1] != action.raw(): raise Conflict('action ID input conflict')
            return previous[0], None
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
        return receipt, p

    def prepare_needs(self,request):
        if self.needs_edits is None:raise Denied('source-bound editor unconfigured')
        return self.needs_edits.prepare(self,request)
    def save_needs(self,request):
        if self.needs_edits is None:raise Denied('source-bound editor unconfigured')
        return self.needs_edits.save(self,request)
    def needs_preparation(self,request_id):
        if self.needs_edits is None:raise Denied('source-bound editor unconfigured')
        return self.needs_edits.query(self,request_id)

    def act_needs(self, request):
        if self.needs_actions is None:raise Denied('explicit needs action host required')
        return self.needs_actions.apply(self,request)

    def prepare_manual(self, edit):
        from .manual_storage import prepare_manual
        return prepare_manual(self, edit)

    def manual_preparation(self, request_id):
        from .manual_storage import manual_preparation
        return manual_preparation(self, request_id)

    def save_manual(self, save):
        from .manual_storage import save_manual
        return save_manual(self, save)

    def prepare_initialization(self, request):
        from .manual_storage import prepare_initialization
        return prepare_initialization(self, request)

    def save_initialization(self, save):
        from .manual_storage import save_initialization
        return save_initialization(self, save)

    def initialization(self, request_id):
        from .manual_storage import manual_preparation
        from .initialization import BASIS
        return manual_preparation(self, request_id, basis_version=BASIS)

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

    def proposal_detail(self, proposal_id):
        """Read-only display snapshot, never review/confirmation authorization."""
        with self.transaction() as cur:
            proposal, digest, status = self._proposal(cur, identifier(proposal_id))
            return ProposalDetail(proposal, digest, status)

    def query_action(self, action_id):
        with self.transaction() as cur:
            row = self._receipt(cur, identifier(action_id))
            return row[0] if row else None

    def detail(self, trip_id):
        with self.transaction() as cur:
            cur.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s AND trip_id=%s', (self.scope,identifier(trip_id)))
            row = cur.fetchone()
            return Trip(row[0],row[1],self._content(bytes(row[2]))) if row else None

    def list_trips(self, after='', limit=20):
        if type(limit) is not int or not 1 <= limit <= 100: raise ValueError('invalid limit')
        if not isinstance(after, str): raise ValueError('invalid cursor')
        if after: identifier(after)
        with self.transaction() as cur:
            cur.execute('SELECT trip_id,version,content FROM cj_trip_record WHERE scope=%s AND trip_id COLLATE "C">%s COLLATE "C" ORDER BY trip_id COLLATE "C" LIMIT %s', (self.scope,after,limit))
            return [Trip(r[0],r[1],self._content(bytes(r[2]))) for r in cur.fetchall()]
