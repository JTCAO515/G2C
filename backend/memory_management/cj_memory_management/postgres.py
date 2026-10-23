"""Extend CJ011's public transaction seam; same connection, lock and authority."""
from contextlib import contextmanager
import hashlib

from cj_memory.domain import Conflict, Receipt, Unavailable
from cj_memory.postgres import Repository as MemoryRepository, Transaction as MemoryTransaction


class Repository(MemoryRepository):
    @contextmanager
    def transaction(self):
        # Reuse rollback, BaseException/commit uncertainty and resource cleanup.
        with super().transaction() as tx:
            yield Transaction(tx.cur, tx.scope)


class Transaction(MemoryTransaction):
    def action(self, action_id):
        self.cur.execute('''SELECT original_input,action_id,item_id,version,status
            FROM cj_memory_management_action WHERE scope=%s AND action_id=%s''',
                         (self.scope, action_id))
        row = self.cur.fetchone()
        if row is None:
            return None
        raw = bytes(row[0])
        return raw, Receipt(*row[1:], hashlib.sha256(raw).hexdigest())

    def change_status(self, action):
        item = self.detail(action.item_id)
        if item is None:
            raise Unavailable('memory unavailable')
        if item.version != action.expected_version:
            raise Conflict('item version changed')
        command = item.command
        self.cur.execute('''SELECT version,approved_input,authorized,confirmed,
            semantic_resolved,active,expires_at>clock_timestamp()
            FROM cj_memory_source WHERE scope=%s AND source_id=%s FOR UPDATE''',
                         (self.scope, command.source_id))
        source = self.cur.fetchone()
        if source is None:
            raise Unavailable('memory unavailable')
        if (source[0] != action.expected_source_version
                or command.source_version != action.expected_source_version):
            raise Conflict('source version changed')
        if source[1] != command.raw:
            raise Unavailable('memory unavailable')
        if action.operation == 'pause':
            # This first extension manages confirmed active items only. No candidate
            # promotion, withdrawn recovery, source renewal or consent inference.
            if item.status != 'active':
                raise Conflict('item is not active')
            status = 'disabled'
        else:
            if item.status != 'disabled':
                raise Conflict('item is not disabled')
            if not all(source[2:]) or command.kind == 'inference':
                raise Unavailable('memory unavailable')
            # A generic disabled row could have been a candidate, or disabled by
            # another lifecycle for a different reason. Only undo our own pause.
            self.cur.execute('''SELECT 1 FROM cj_memory_management_action
                WHERE scope=%s AND item_id=%s AND version=%s AND operation='pause' ''',
                             (self.scope, action.item_id, item.version))
            if self.cur.fetchone() is None:
                raise Unavailable('memory unavailable')
            self.cur.execute('''SELECT 1 FROM cj_memory_item WHERE scope=%s
                AND subject=%s AND slot=%s AND extent=%s AND context_id=%s
                AND status='active' ''',
                             (self.scope, command.subject, command.slot,
                              command.extent, command.context_id or ''))
            if self.cur.fetchone() is not None:
                raise Conflict('canonical slot occupied; review current item')
            status = 'active'
        self.cur.execute('''UPDATE cj_memory_item SET status=%s,version=version+1
            WHERE scope=%s AND item_id=%s AND version=%s AND source_version=%s
            RETURNING version''',
                         (status, self.scope, action.item_id, action.expected_version,
                          action.expected_source_version))
        updated = self.cur.fetchone()
        if updated is None:
            raise Conflict('item version changed')
        self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s',
                         (self.scope,))
        self.cur.execute('''INSERT INTO cj_memory_management_action
            (scope,action_id,operation,original_input,item_id,version,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                         (self.scope, action.action_id, action.operation, action.raw,
                          action.item_id, updated[0], status))
        stored = self.action(action.action_id)
        if stored is None:
            raise Unavailable('action receipt missing')
        return stored[1]
