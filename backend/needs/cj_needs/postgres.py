"""Task-private PostgreSQL adapter; only a trusted Boundary may expose its results."""
from contextlib import contextmanager
import json
import logging
from .domain import (Command, CommitUnknown, Conflict, Denied, Receipt, Revision,
                     Snapshot, identifier, validate_fields)

logger = logging.getLogger(__name__)


class Repository:
    def __init__(self, connect, scope, guard):
        self.connect, self.scope, self.guard = connect, identifier(scope), guard

    @contextmanager
    def transaction(self):
        conn = self.connect()
        accepted = commit_started = False
        primary = None
        try:
            if (getattr(conn, 'autocommit', None) is not False
                    or getattr(getattr(conn, 'info', None), 'transaction_status', None) != 0
                    or getattr(conn, 'closed', None) is not False):
                raise Denied('fresh idle non-autocommit PostgreSQL connection required')
            accepted = True
            cur = conn.cursor()
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("SET LOCAL statement_timeout = '10s'")
            cur.execute('SELECT scope FROM cj_needs_scope WHERE scope=%s FOR UPDATE', (self.scope,))
            if cur.fetchone() is None: raise Denied('scope unavailable')
            self.guard('transaction')
            yield cur
            self.guard('commit')
            commit_started = True
            try: conn.commit()
            except BaseException: raise CommitUnknown('reconcile original action') from None
            self.guard('return')
        except BaseException as exc:
            primary = exc
            if commit_started: exc.commit_possible = True
            if accepted:
                try: conn.rollback()
                except BaseException: self._warning('rollback')
            raise
        finally:
            try: conn.close()
            except BaseException as exc:
                self._warning('close')
                if primary is None and not isinstance(exc, Exception):
                    exc.commit_possible = commit_started
                    raise

    @staticmethod
    def _warning(stage):
        try: logger.warning('NEEDS connection cleanup failed: %s', stage)
        except BaseException: pass

    def _receipt(self, cur, action_id):
        cur.execute('SELECT action_id,needs_id,version,original_input FROM cj_needs_revision WHERE scope=%s AND operation=%s AND action_id=%s',
                    (self.scope, 'manual_patch', action_id))
        row = cur.fetchone()
        return (Receipt(*row[:3]), bytes(row[3])) if row else None

    def _snapshot(self, cur, needs_id):
        cur.execute('SELECT needs_id,version,content FROM cj_needs_record WHERE scope=%s AND needs_id=%s', (self.scope, needs_id))
        row = cur.fetchone()
        return Snapshot(row[0], row[1], bytes(row[2])) if row else None

    def act(self, command):
        if type(command) is not Command: raise ValueError('validated command required')
        obj = command.data
        with self.transaction() as cur:
            old = self._receipt(cur, command.action_id)
            if old:
                if old[1] != command.raw: raise Conflict('original action bytes differ')
                return old[0]
            current = self._snapshot(cur, obj['needs_id'])
            version = current.version if current else 0
            if version != obj['expected_version']: raise Conflict('needs version changed')
            fields = current.fields if current else {}
            fields.update(obj['changes'])
            validate_fields(fields, complete=True)
            content = json.dumps(fields, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
            # Bound cumulative growth as well as each command.
            if len(content) > 131072: raise ValueError('needs record too large')
            version += 1
            cur.execute('INSERT INTO cj_needs_record VALUES (%s,%s,%s,%s) ON CONFLICT(scope,needs_id) DO UPDATE SET version=EXCLUDED.version,content=EXCLUDED.content',
                        (self.scope, obj['needs_id'], version, content))
            cur.execute('INSERT INTO cj_needs_revision(scope,needs_id,version,action_id,operation,original_input,content,source_kind) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                        (self.scope, obj['needs_id'], version, command.action_id, 'manual_patch', command.raw, content, 'user_provided'))
            return Receipt(command.action_id, obj['needs_id'], version)

    def query_action(self, action_id):
        with self.transaction() as cur:
            found = self._receipt(cur, identifier(action_id))
            return found[0] if found else None

    def detail(self, needs_id):
        with self.transaction() as cur:
            return self._snapshot(cur, identifier(needs_id))

    def revision(self, needs_id, version):
        if type(version) is not int or not 1 <= version < 2**63: raise ValueError('invalid version')
        with self.transaction() as cur:
            cur.execute('SELECT needs_id,version,action_id,original_input,content FROM cj_needs_revision WHERE scope=%s AND needs_id=%s AND version=%s',
                        (self.scope, identifier(needs_id), version))
            row = cur.fetchone()
            return Revision(*row[:3], bytes(row[3]), bytes(row[4])) if row else None
