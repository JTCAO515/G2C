"""Injected DB-API repository. No DSN, connection creation, auth or dispatch."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import logging
from .core import Binding, State, Event, Cursor, Conflict, Denied, ResyncRequired, advance, page
from .usage_binding import UsageBinding


class CommitUnknown(Exception):
    """Commit may have happened. Query original binding; never blind retry."""


@dataclass(frozen=True)
class Recovery:
    state: State
    cursor: Cursor
    action: str


class Repository:
    def __init__(self, connect, scope, *, expires_at, statement_timeout_ms, lock_timeout_ms):
        if not callable(connect) or type(scope) is not str or not scope.strip():
            raise ValueError('trusted scope and connection factory required')
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError('explicit timezone-aware expiry required')
        for n in (statement_timeout_ms, lock_timeout_ms):
            if type(n) is not int or not 1 <= n <= 2147483647:
                raise ValueError('explicit positive timeout required')
        self.connect, self.scope, self.expires_at = connect, scope, expires_at
        self.statement_timeout_ms, self.lock_timeout_ms = statement_timeout_ms, lock_timeout_ms

    @contextmanager
    def transaction(self):
        conn = self.connect()
        cur = None
        outcome = 'setup_failed'

        def cleanup(action, stage):
            try:
                action()
            except BaseException:
                try:
                    logging.getLogger(__name__).warning('run_cleanup_failed stage=%s outcome=%s', stage, outcome)
                except BaseException:
                    pass

        try:
            if conn.autocommit:
                raise ValueError('autocommit forbidden')
            cur = conn.cursor()
            try:
                cur.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                cur.execute("SELECT set_config('statement_timeout',%s,true), set_config('lock_timeout',%s,true)",
                            (str(self.statement_timeout_ms), str(self.lock_timeout_ms)))
                cur.execute('SELECT epoch,active FROM cj_run_scope WHERE scope=%s FOR UPDATE', (self.scope,))
                row = cur.fetchone()
                if row is None or row[1] is not True:
                    raise Denied('scope unavailable')
                yield Transaction(cur, self.scope, row[0], self.expires_at)
            except BaseException:
                outcome = 'body_failed'
                cleanup(conn.rollback, 'rollback')
                raise
            else:
                outcome = 'commit_unknown'
                try:
                    conn.commit()
                except Exception as exc:
                    raise CommitUnknown() from exc
                outcome = 'committed'
        finally:
            if cur is not None:
                cleanup(cur.close, 'cursor_close')
            cleanup(conn.close, 'connection_close')

    def recover(self, binding):
        """Deterministic original-run read, never a worker execution authorization."""
        with self.transaction() as tx:
            state = tx.get(binding)
            result = Recovery(state, Cursor(binding, tx.epoch, state.sequence, 0),
                              'query_only' if state.status in {'running', 'unknown'} else
                              'queued_no_dispatch' if state.status == 'queued' else 'terminal')
        return result

    def events(self, cursor, *, limit):
        if type(cursor) is not Cursor:
            raise ResyncRequired('internal cursor required')
        with self.transaction() as tx:
            state = tx.get(cursor.binding)
            result = page(state, tx.epoch, cursor, limit)
        return result


class Transaction:
    def __init__(self, cur, scope, epoch, expires_at):
        self.cur, self.scope, self.epoch, self.expires_at = cur, scope, epoch, expires_at

    def _scope(self, binding):
        if type(binding) is not Binding or binding.scope != self.scope:
            raise Denied('scope unavailable')

    def _record(self, binding):
        self._scope(binding)
        self.cur.execute('SELECT conversation_id,generation,message_id,message_sequence,status,event_sequence,expires_at>clock_timestamp(),usage_command_bytes,usage_input_bytes FROM cj_run_record WHERE scope=%s AND run_id=%s FOR UPDATE',
                         (self.scope, binding.run_id))
        return self.cur.fetchone()

    def accept(self, binding, usage=None, require_new=False):
        if usage is not None:
            if type(usage) is not UsageBinding:
                raise ValueError('usage binding required')
            usage.check_run(binding.run_id)
        row = self._record(binding)
        if row is not None:
            old = self.get(binding)
            if require_new or (usage is not None and old.usage != usage):
                raise Conflict('original usage binding absent or changed')
            return old
        self.cur.execute('SELECT 1 FROM cj_run_record WHERE scope=%s AND (message_id=%s OR (conversation_id=%s AND generation=%s AND message_sequence=%s))',
                         (self.scope, binding.message_id, binding.conversation_id, binding.generation, binding.message_sequence))
        if self.cur.fetchone() is not None:
            raise Conflict('binding reused')
        self.cur.execute('SELECT %s::timestamptz>clock_timestamp()', (self.expires_at,))
        if self.cur.fetchone()[0] is not True:
            raise ResyncRequired('expired acceptance window')
        self.cur.execute("INSERT INTO cj_run_record(scope,run_id,conversation_id,generation,message_id,message_sequence,status,event_sequence,expires_at,usage_command_bytes,usage_input_bytes) VALUES (%s,%s,%s,%s,%s,%s,'queued',0,%s,%s,%s)",
                         (self.scope, binding.run_id, binding.conversation_id, binding.generation,
                          binding.message_id, binding.message_sequence, self.expires_at,
                          usage.command_bytes if usage else None, usage.input_bytes if usage else None))
        return State(binding, usage=usage)

    def get(self, binding):
        row = self._record(binding)
        if row is None:
            raise Conflict('unavailable')
        if row[:4] != (binding.conversation_id, binding.generation, binding.message_id, binding.message_sequence):
            raise Conflict('binding changed')
        if row[6] is not True:
            raise ResyncRequired('run recovery expired; not absent')
        self.cur.execute('SELECT sequence,event_id,kind,value FROM cj_run_event WHERE scope=%s AND run_id=%s ORDER BY sequence',
                         (self.scope, binding.run_id))
        usage = None
        if row[7] is not None or row[8] is not None:
            try:
                usage = UsageBinding(bytes(row[7]), bytes(row[8]))
                usage.check_run(binding.run_id)
            except (ValueError, TypeError) as exc:
                raise ResyncRequired('invalid stored usage binding') from exc
        state = State(binding, usage=usage)
        for sequence, identity, kind, value in self.cur.fetchall():
            # Reconstruct already committed facts; no output or execution occurs here.
            state = advance(state, Event(binding, sequence, identity, kind, value), lambda _: True)
        if (state.status, state.sequence) != (row[4], row[5]):
            raise ResyncRequired('stored event gap or projection mismatch')
        return state

    def put(self, state):
        old = self.get(state.binding)
        if state == old:
            return
        if state.events[:-1] != old.events or len(state.events) != len(old.events) + 1:
            raise Conflict('append only')
        event = state.events[-1]
        # Validate exact projection, even if a caller bypasses Service.
        if advance(old, event, lambda _: True) != state:
            raise Conflict('projection mismatch')
        b = state.binding
        self.cur.execute('INSERT INTO cj_run_event(scope,run_id,sequence,event_id,kind,value) VALUES (%s,%s,%s,%s,%s,%s)',
                         (self.scope,b.run_id,event.sequence,event.event_id,event.kind,event.value))
        self.cur.execute('UPDATE cj_run_record SET status=%s,event_sequence=%s WHERE scope=%s AND run_id=%s AND event_sequence=%s AND status=%s',
                         (state.status,state.sequence,self.scope,b.run_id,old.sequence,old.status))
        if self.cur.rowcount != 1:
            raise Conflict('concurrent append')

    def previous_terminal(self, binding):
        self._scope(binding)
        self.cur.execute("SELECT count(*),count(*) FILTER (WHERE status IN ('completed','failed','cancelled','context_invalid')) FROM cj_run_record WHERE scope=%s AND conversation_id=%s AND generation=%s AND message_sequence<%s",
                         (self.scope,binding.conversation_id,binding.generation,binding.message_sequence))
        count, terminal = self.cur.fetchone()
        return count == terminal == binding.message_sequence - 1
