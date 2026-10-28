"""PostgreSQL DB-API repository source. No connection creation, driver or auth."""
from contextlib import contextmanager
import logging
from .domain import Chat, CommitUnknown, Receipt, Stored, Unavailable, ChatSummary, Draft


class Repository:
    def __init__(self, connect, scope):
        # Internal partition key, NOT a principal schema or client-supplied owner.
        if not isinstance(scope, str) or not scope:
            raise ValueError('explicit internal scope required')
        self.connect, self.scope = connect, scope

    @contextmanager
    def transaction(self):
        # Factory must yield a NEW non-autocommit DB-API connection at READ COMMITTED.
        conn = self.connect()
        cur = None
        outcome = 'setup_failed'

        def cleanup(action, stage):
            try:
                action()
            except BaseException:
                # Fixed diagnostics only: never exception text, SQL, scope or credentials.
                # Even a failing logging handler cannot replace the primary outcome.
                try:
                    logging.getLogger(__name__).warning(
                        'message_repository_cleanup_failed stage=%s outcome=%s', stage, outcome)
                except BaseException:
                    pass

        try:
            if conn.autocommit:
                raise ValueError('autocommit forbidden')
            cur = conn.cursor()
            try:
                cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                bind_scope = getattr(conn, 'bind_scope', None)
                if bind_scope is not None:
                    bind_scope(cur)
                yield Transaction(cur, self.scope)
            except BaseException:
                outcome = 'body_failed'
                cleanup(conn.rollback, 'rollback')
                raise
            else:
                outcome = 'commit_unknown'
                try:
                    conn.commit()
                except Exception as exc:
                    # Do not retry commit or claim rollback after an uncertain commit ACK.
                    raise CommitUnknown() from exc
                outcome = 'committed'
        finally:
            if cur is not None:
                cleanup(cur.close, 'cursor_close')
            cleanup(conn.close, 'connection_close')


class Transaction:
    def __init__(self, cursor, scope):
        self.cur, self.scope = cursor, scope

    def lock_scope(self):
        self.cur.execute('SELECT scope FROM cj_message_scope WHERE scope = %s FOR UPDATE', (self.scope,))
        if self.cur.fetchone() is None:
            raise Unavailable()

    def chat(self, cid, generation=None):
        self.cur.execute('SELECT generation, epoch, last_sequence FROM cj_message_chat WHERE scope = %s AND conversation_id = %s AND active FOR UPDATE', (self.scope, cid))
        row = self.cur.fetchone()
        if row is None or (generation is not None and row[0] != generation):
            raise Unavailable()
        return Chat(*row)

    def open_chat(self, cid, generation):
        self.cur.execute('INSERT INTO cj_message_chat (scope, conversation_id, generation, epoch) VALUES (%s,%s,%s,0) ON CONFLICT DO NOTHING RETURNING generation, epoch, last_sequence', (self.scope, cid, generation))
        row = self.cur.fetchone()
        return Chat(*row) if row else None

    def find(self, mid):
        self.cur.execute('SELECT raw_input, message_id, conversation_id, generation, sequence, run_id, input_sha256 FROM cj_message_receipt WHERE scope = %s AND message_id = %s', (self.scope, mid))
        row = self.cur.fetchone()
        return Stored(bytes(row[0]), Receipt(*row[1:])) if row else None

    def insert(self, stored):
        r = stored.receipt
        self.cur.execute('INSERT INTO cj_message_receipt (scope, message_id, conversation_id, generation, sequence, run_id, input_sha256, raw_input) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                         (self.scope, r.message_id, r.conversation_id, r.generation, r.sequence, r.run_id, r.input_sha256, stored.raw))
        self.cur.execute('UPDATE cj_message_chat SET last_sequence = %s WHERE scope = %s AND conversation_id = %s AND generation = %s AND active', (r.sequence, self.scope, r.conversation_id, r.generation))
        if self.cur.rowcount != 1:
            raise Unavailable()

    def enqueue(self, receipt):
        self.cur.execute('INSERT INTO cj_message_delivery (scope, message_id, run_id) VALUES (%s,%s,%s)', (self.scope, receipt.message_id, receipt.run_id))

    def page(self, cid, generation, after, through, limit):
        self.cur.execute('SELECT message_id, conversation_id, generation, sequence, run_id, input_sha256 FROM cj_message_receipt WHERE scope = %s AND conversation_id = %s AND generation = %s AND sequence > %s AND sequence <= %s ORDER BY sequence LIMIT %s', (self.scope, cid, generation, after, through, limit))
        return [Receipt(*row) for row in self.cur.fetchall()]

    def pending(self, limit):
        self.cur.execute('SELECT r.message_id, r.conversation_id, r.generation, r.sequence, r.run_id, r.input_sha256 FROM cj_message_delivery d JOIN cj_message_receipt r ON (r.scope, r.message_id, r.run_id) = (d.scope, d.message_id, d.run_id) JOIN cj_message_chat c ON (c.scope, c.conversation_id, c.generation) = (r.scope, r.conversation_id, r.generation) WHERE d.scope = %s AND c.active AND NOT d.acknowledged ORDER BY r.conversation_id, r.sequence LIMIT %s', (self.scope, limit))
        return [Receipt(*row) for row in self.cur.fetchall()]

    def acknowledge(self, message_id, run_id):
        self.cur.execute('UPDATE cj_message_delivery SET acknowledged = true WHERE scope = %s AND message_id = %s AND run_id = %s', (self.scope, message_id, run_id))

    def list_boundary(self):
        self.cur.execute('SELECT history_generation::text, history_epoch, (SELECT COALESCE(MAX(list_sequence),0) FROM cj_message_chat WHERE scope=%s AND active) FROM cj_message_scope WHERE scope=%s', (self.scope, self.scope))
        row = self.cur.fetchone()
        if row is None:
            raise Unavailable()
        return row

    def conversations(self, after, through, limit):
        self.cur.execute('SELECT conversation_id,generation,epoch,list_sequence FROM cj_message_chat WHERE scope=%s AND active AND list_sequence>%s AND list_sequence<=%s ORDER BY list_sequence LIMIT %s', (self.scope,after,through,limit))
        return [ChatSummary(*row) for row in self.cur.fetchall()]

    def history(self, cid, generation, after, through, limit):
        self.cur.execute('SELECT raw_input,message_id,conversation_id,generation,sequence,run_id,input_sha256 FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s AND generation=%s AND sequence>%s AND sequence<=%s ORDER BY sequence LIMIT %s', (self.scope,cid,generation,after,through,limit))
        return [Stored(bytes(row[0]), Receipt(*row[1:])) for row in self.cur.fetchall()]

    def draft(self, cid, generation):
        self.cur.execute('SELECT conversation_id,generation,revision,original_utf8 FROM cj_message_draft WHERE scope=%s AND conversation_id=%s AND generation=%s', (self.scope,cid,generation))
        row = self.cur.fetchone()
        return Draft(row[0],row[1],row[2],bytes(row[3])) if row else None

    def save_draft(self, draft):
        self.cur.execute('INSERT INTO cj_message_draft(scope,conversation_id,generation,revision,original_utf8) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(scope,conversation_id,generation) DO UPDATE SET revision=EXCLUDED.revision, original_utf8=EXCLUDED.original_utf8', (self.scope,draft.conversation_id,draft.generation,draft.revision,draft.original_utf8))
