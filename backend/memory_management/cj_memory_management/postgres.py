"""Extend CJ011's public transaction seam; same connection, lock and authority."""
from contextlib import contextmanager
import hashlib

from cj_memory.domain import Command, Conflict, Receipt, Unavailable
from .edit import Edit, approve_edit, parse_action
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
        action = parse_action(raw)
        if action.action_id != row[1] or action.item_id != row[2] or action.expected_version + 1 != row[3]:
            raise Unavailable('action projection mismatch')
        if isinstance(action, Edit):
            self.cur.execute('''SELECT a.previous_source_id,a.new_source_id,a.disabled_by_version,
                p.approved_input,n.approved_input FROM cj_memory_management_action a
                JOIN cj_memory_source p ON (p.scope,p.source_id)=(a.scope,a.previous_source_id)
                JOIN cj_memory_source n ON (n.scope,n.source_id)=(a.scope,a.new_source_id)
                WHERE a.scope=%s AND a.action_id=%s''', (self.scope,action_id))
            history = self.cur.fetchone()
            if history is None:
                raise Unavailable('edit history unavailable')
            previous = Command.parse(bytes(history[3]))
            current = action.command(previous)
            if (previous.item_id != action.item_id or previous.source_id != history[0]
                    or previous.source_version != action.expected_source_version
                    or current.source_id != history[1] or current.raw != bytes(history[4])):
                raise Unavailable('edit source projection mismatch')
            if row[4] == 'disabled':
                self.cur.execute('''SELECT 1 FROM cj_memory_management_action WHERE scope=%s
                    AND item_id=%s AND version=%s AND operation='pause' AND status='disabled' ''',
                                 (self.scope,action.item_id,history[2]))
                if self.cur.fetchone() is None:
                    raise Unavailable('edit pause history unavailable')
        receipt = Receipt(*row[1:], hashlib.sha256(raw).hexdigest())
        from cj_memory_withdrawal.stop_use import StopUse, validate_stored
        if isinstance(action, StopUse):
            validate_stored(self, action, receipt)
        return raw, receipt

    def pause_anchor(self, item):
        self.cur.execute('''SELECT operation,status FROM cj_memory_management_action
            WHERE scope=%s AND item_id=%s AND version=%s''',
                         (self.scope, item.command.item_id, item.version))
        row = self.cur.fetchone()
        if row is None or row[1] != 'disabled':
            raise Unavailable('own pause history required')
        if row[0] == 'pause':
            return item.version
        if row[0] != 'edit':
            raise Unavailable('own pause history required')
        self.cur.execute('''SELECT disabled_by_version FROM cj_memory_management_action
            WHERE scope=%s AND item_id=%s AND version=%s''',
                         (self.scope, item.command.item_id, item.version))
        anchor = self.cur.fetchone()[0]
        if anchor is None:
            raise Unavailable('own pause history required')
        self.cur.execute('''SELECT 1 FROM cj_memory_management_action
            WHERE scope=%s AND item_id=%s AND version=%s AND operation='pause' AND status='disabled' ''',
                         (self.scope, item.command.item_id, anchor))
        if self.cur.fetchone() is None:
            raise Unavailable('pause anchor unavailable')
        return anchor

    def edit(self, action, policy):
        item = self.detail(action.item_id)
        if item is None:
            raise Unavailable('memory unavailable')
        if item.version != action.expected_version:
            raise Conflict('item version changed')
        original = item.command
        if original.source_version != action.expected_source_version:
            raise Conflict('source version changed')
        if item.status not in ('active', 'disabled') or original.kind == 'inference':
            raise Unavailable('confirmed memory required')
        # Reuse the authoritative source check, including exact bytes and wall clock.
        if self.source(original) is not True:
            raise Unavailable('confirmed source required')
        anchor = self.pause_anchor(item) if item.status == 'disabled' else None
        command = action.command(original)
        approve_edit(policy, command, action.raw)
        self.create_manual_source(command, True, policy.expires_at)
        self.cur.execute('''UPDATE cj_memory_item SET original_input=%s,source_id=%s,
            source_version=1,version=version+1 WHERE scope=%s AND item_id=%s
            AND version=%s AND source_version=%s RETURNING version''',
                         (command.raw, command.source_id, self.scope, action.item_id,
                          action.expected_version, action.expected_source_version))
        row = self.cur.fetchone()
        if row is None:
            raise Conflict('item version changed')
        self.cur.execute('UPDATE cj_memory_scope SET epoch=epoch+1 WHERE scope=%s', (self.scope,))
        self.cur.execute('''INSERT INTO cj_memory_management_action
            (scope,action_id,operation,original_input,item_id,version,status,
             previous_source_id,new_source_id,disabled_by_version)
            VALUES (%s,%s,'edit',%s,%s,%s,%s,%s,%s,%s)''',
                         (self.scope, action.action_id, action.raw, action.item_id, row[0],
                          item.status, original.source_id, command.source_id, anchor))
        return self.action(action.action_id)[1]

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
            self.pause_anchor(item)
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
